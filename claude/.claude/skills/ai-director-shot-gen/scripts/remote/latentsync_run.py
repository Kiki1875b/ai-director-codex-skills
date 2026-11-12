"""LatentSync 1.5 lip sync on an existing 24 fps shot, keeping every original frame (no regeneration of the shot).

  python latentsync_run.py --video shot.mp4 --audio voice_on_shot_timeline.wav --out out.mp4 [--steps 20 --cfg 1.5 --seed 1247]

- The audio must already sit on the shot's timeline (same start, same length as the video).
- LatentSync works at 25 fps. Instead of resampling frames (which duplicates/drops frames), the 24 fps frames are fed
  1:1 as if they were 25 fps and the audio is time-compressed by 24/25 (atempo, pitch kept). The output frames are then
  written back at 24 fps against the original audio, so frame k still pairs with the same moment of speech.
- InsightFace (non-commercial models) is replaced by MediaPipe FaceMesh; decord is stubbed (soundfile reads audio).
- Writes <out> (with original audio), <out>_noaudio.mp4 and <out>_crop.png (aligned face + model mask, for checking).
Run from anywhere; repo is C:\\ai\\latentsync\\LatentSync.
"""
import argparse, os, subprocess, sys, types
import numpy as np

ROOT = r"C:\ai\latentsync"
REPO = os.path.join(ROOT, "LatentSync")
VAE = os.path.join(ROOT, "models", "sd-vae")   # sd-vae-ft-mse (safetensors), copied from the removed MuseTalk install
os.environ["PATH"] = os.path.join(ROOT, "bin") + os.pathsep + os.environ["PATH"]   # pinned static ffmpeg 7.1.1
os.environ["HF_HUB_OFFLINE"] = "1"

# ---- stubs so the repo imports without insightface / decord -------------------------------------------------------
ins = types.ModuleType("insightface"); ins_app = types.ModuleType("insightface.app")
class _NoFaceAnalysis:  # never used: FaceDetector is replaced below
    def __init__(self, *a, **k): raise RuntimeError("insightface disabled")
ins_app.FaceAnalysis = _NoFaceAnalysis; ins.app = ins_app
sys.modules["insightface"] = ins; sys.modules["insightface.app"] = ins_app
dec = types.ModuleType("decord")
dec.AudioReader = dec.VideoReader = None
sys.modules["decord"] = dec

sys.path.insert(0, REPO); os.chdir(REPO)
import cv2, torch, soundfile as sf
import mediapipe as mp
from omegaconf import OmegaConf
from diffusers import AutoencoderKL, DDIMScheduler
import latentsync.utils.image_processor as ip_mod
import latentsync.pipelines.lipsync_pipeline as pl_mod
from latentsync.models.unet import UNet3DConditionModel
from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
from latentsync.whisper.audio2feature import Audio2Feature

# MediaPipe FaceMesh indices (image-left / image-right eyebrow, nose)
BROW_A = [70, 63, 105, 66, 107]
BROW_B = [336, 296, 334, 293, 300]
NOSE = [195, 4, 98, 327]


def track_face(frames, pick="largest"):
    """Landmarks for every frame of ONE person: first frame picks the face (largest/left/right), later frames take the
    detection whose centre is nearest the previous one (a background false positive can be larger than the real face -
    S3-5 v1 run: 6 frames jumped to the shelf, so the real mouth flipped back to the original there). Frames whose best
    match jumps more than 15% of the face width are treated as missing and interpolated. Returns (n, 468, 2) floats."""
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=3, refine_landmarks=False,
                                         min_detection_confidence=0.3, min_tracking_confidence=0.3)
    h, w = frames.shape[1:3]
    out, prev = [], None
    for f in frames:
        r = fm.process(np.ascontiguousarray(f))
        cands = [np.array([[q.x * w, q.y * h] for q in lm.landmark]) for lm in (r.multi_face_landmarks or [])]
        p = None
        if cands:
            if prev is None:
                key = {"left": lambda c: -c[:, 0].mean(), "right": lambda c: c[:, 0].mean()}.get(
                    pick, lambda c: np.ptp(c[:, 0]) * np.ptp(c[:, 1]))
                p = max(cands, key=key)
            else:
                p = min(cands, key=lambda c: np.linalg.norm(c.mean(0) - prev.mean(0)))
                if np.linalg.norm(p.mean(0) - prev.mean(0)) > 0.15 * np.ptp(prev[:, 0]):
                    p = None
        out.append(p)
        if p is not None: prev = p
    fm.close()
    ok = [i for i, p in enumerate(out) if p is not None]
    if not ok: raise RuntimeError("no face found")
    L = np.stack([out[i] if out[i] is not None else np.full((468, 2), np.nan) for i in range(len(out))])
    for j in range(468):  # interpolate missing frames
        for k in range(2):
            v = L[:, j, k]; bad = np.isnan(v)
            if bad.any(): v[bad] = np.interp(np.where(bad)[0], np.where(~bad)[0], v[~bad])
    missing = len(out) - len(ok)
    print(f"face track: {len(ok)}/{len(out)} frames detected, {missing} interpolated")
    return L


def smooth(x, win=9):
    """Savitzky-Golay along time (order 2) - removes frame-to-frame landmark noise, keeps real head motion."""
    from scipy.signal import savgol_filter
    win = min(win, len(x) - (1 - len(x) % 2))
    return savgol_filter(x, win, 2, axis=0) if win >= 5 else x


class TrackedFaceDetector:
    """Drop-in for latentsync FaceDetector. Ignores the frame content and returns the pre-computed, smoothed anchors for
    the next frame in order (the pipeline calls it once per frame, in order, before any looping)."""
    anchors = None   # (n, 3, 2): image-left brow centre, image-right brow centre, nose centre
    boxes = None

    def __init__(self, device="cuda"):
        self.i = 0

    def __call__(self, frame, threshold=0.5):
        k = min(self.i, len(self.anchors) - 1); self.i += 1
        left, right, nose = self.anchors[k]
        lmk = np.zeros((106, 2))
        lmk[[43, 48, 49, 50, 51]] = left
        lmk[101:106] = right
        lmk[[74, 77, 83, 86]] = nose
        return self.boxes[k], lmk


ip_mod.FaceDetector = TrackedFaceDetector


def lower_face_mask(L, h, w, feather):
    """Per-frame soft mask of the area LatentSync is allowed to change: below the nose bridge, inside the jaw line.
    Everything else (eyes, hair, background) stays pixel-identical to the original."""
    JAW = [234, 93, 132, 58, 172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397, 288, 361, 323, 454]
    M = np.zeros((len(L), h, w), np.float32)
    for i, p in enumerate(L):
        top = p[[195]][0][1]                      # nose bridge (mid) - mouth/nose area only
        poly = p[JAW].copy()
        poly[0, 1] = poly[-1, 1] = top            # cheek points lifted to the cut line
        poly = np.concatenate([[[p[234][0], top]], poly, [[p[454][0], top]]])
        m = np.zeros((h, w), np.uint8)
        cv2.fillPoly(m, [np.round(poly).astype(np.int32)], 255)
        m = cv2.erode(m, np.ones((feather // 2 * 2 + 1,) * 2, np.uint8))
        M[i] = cv2.GaussianBlur(m, (0, 0), feather / 2).astype(np.float32) / 255.0
    return M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--audio", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=20); ap.add_argument("--cfg", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=1247)
    ap.add_argument("--pick", default="largest", choices=["largest", "left", "right"])
    ap.add_argument("--audio-lead", type=float, default=0.0,
                    help="seconds to feed the audio EARLIER to the model (S3-5 v1: mouth lagged voice by ~0.2 s)")
    ap.add_argument("--smooth", type=int, default=9, help="landmark smoothing window in frames (0 = off)")
    ap.add_argument("--feather", type=int, default=15, help="soft edge of the lower-face composite mask, px")
    ap.add_argument("--ref-image", help="full-frame image used as the model's REFERENCE face for every frame instead of "
                    "the frame itself (e.g. a frame of this shot edited to an open mouth with teeth). The frame's own "
                    "closed mouth otherwise leaks into the result: small mouth shapes, no teeth (S3-5 eval)")
    ap.add_argument("--ref-frame", type=int, default=0, help="frame index the --ref-image was made from (alignment)")
    ap.add_argument("--max-vram", type=float, default=0,
                    help="GB cap for THIS process (torch); above it the run fails with OOM instead of starving other "
                         "programs on the GPU. 0 = no cap")
    ap.add_argument("--lowmem", action="store_true",
                    help="same result, less memory: guidance halves (with/without audio) run one after the other "
                         "instead of as one double batch, and the VAE encodes/decodes one frame at a time. For 1.6 (512px)")
    ap.add_argument("--throttle", type=float, default=1.0,
                    help="GPU duty cycle 0.1-1.0 (0.5 = idle as long as each UNet pass took). Use while someone plays "
                         "a game on the server: fewer stutters, run time x 1/duty")
    ap.add_argument("--config", default="configs/unet/stage2.yaml")
    ap.add_argument("--ckpt", default=os.path.join(ROOT, "checkpoints", "latentsync_unet.pt"))
    a = ap.parse_args()
    out = os.path.abspath(a.out); os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = os.path.join(ROOT, "tmp"); os.makedirs(tmp, exist_ok=True)

    # frames 1:1
    cap = cv2.VideoCapture(a.video); frames = []
    while True:
        ok, f = cap.read()
        if not ok: break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    fps_in = cap.get(cv2.CAP_PROP_FPS); cap.release()
    frames = np.stack(frames); n = len(frames)
    print(f"frames {n} @ {fps_in:.3f} fps, {frames.shape[2]}x{frames.shape[1]}")

    # one tracked face, smoothed anchors (no per-frame re-detection inside the pipeline)
    L = track_face(frames, a.pick)
    raw = np.stack([L[:, BROW_A].mean(1), L[:, BROW_B].mean(1), L[:, NOSE].mean(1)], 1)
    sw = np.where(raw[:, 0, 0] > raw[:, 1, 0])[0]; raw[sw, 0], raw[sw, 1] = raw[sw, 1].copy(), raw[sw, 0].copy()
    anc = smooth(raw, a.smooth) if a.smooth else raw
    jit = lambda X: np.linalg.norm(X[2:] - 2 * X[1:-1] + X[:-2], axis=-1).mean()
    print(f"anchor jitter px: raw {jit(raw):.2f} -> smoothed {jit(anc):.2f}")
    TrackedFaceDetector.anchors = anc
    TrackedFaceDetector.boxes = [(int(p[:, 0].min()), int(p[:, 1].min()), int(p[:, 0].max()), int(p[:, 1].max())) for p in L]
    Ls = smooth(L, a.smooth) if a.smooth else L

    # audio: optional lead, then compress by fps_in/25 so n frames at 25 fps cover it, pad so whisper chunks >= n
    a16 = os.path.join(tmp, "audio16k.wav")
    tempo = 25.0 / fps_in
    lead = f"atrim=start={a.audio_lead:.4f},asetpts=PTS-STARTPTS," if a.audio_lead > 0 else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.audio, "-af", f"{lead}atempo={tempo:.6f},apad=pad_dur=0.5",
                    "-ac", "1", "-ar", "16000", a16], check=True)

    pl_mod.read_video = lambda path, change_fps=True, use_decord=True: frames.copy()
    pl_mod.read_audio = lambda path, audio_sample_rate=16000: torch.from_numpy(sf.read(path, dtype="float32")[0])
    captured = {}
    def _cap(path, video_frames, fps):
        captured["f"] = np.asarray(video_frames)
        cv2.imwrite(path.replace(".mp4", ".png"), cv2.cvtColor(captured["f"][0], cv2.COLOR_RGB2BGR))
    pl_mod.write_video = _cap
    pl_mod.subprocess = types.SimpleNamespace(run=lambda *x, **k: None)   # skip the repo's own ffmpeg mux

    # keep one aligned crop for checking the MediaPipe alignment against the model mask
    orig_aff = ip_mod.ImageProcessor.affine_transform
    def _aff(self, image):
        face, box, m = orig_aff(self, image)
        if "crop" not in captured:
            c = face.permute(1, 2, 0).cpu().numpy().astype(np.uint8)
            mask = cv2.resize(cv2.imread("latentsync/utils/mask.png"), (c.shape[1], c.shape[0]))
            vis = np.concatenate([c, (c * (mask / 255.0)).astype(np.uint8)], 1)
            cv2.imwrite(out.replace(".mp4", "_crop.png"), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR)); captured["crop"] = 1
        return face, box, m
    ip_mod.ImageProcessor.affine_transform = _aff

    if a.ref_image:
        ref_rgb = cv2.cvtColor(cv2.imread(a.ref_image), cv2.COLOR_BGR2RGB)
        if ref_rgb.shape[:2] != frames.shape[1:3]:
            ref_rgb = cv2.resize(ref_rgb, (frames.shape[2], frames.shape[1]), interpolation=cv2.INTER_AREA)
        orig_pil = LipsyncPipeline.prepare_image_latents

        def _ref_latents(self, images, device, dtype, generator, cfg):
            # reference latents from the edited image; mask/paste-back still use the real frames
            if not hasattr(self, "_ref_px"):
                ip = self.image_processor
                face, _ = ip.restorer.align_warp_face(ref_rgb.copy(), landmarks3=np.round(anc[a.ref_frame]), smooth=False)
                face = cv2.resize(face, (ip.resolution, ip.resolution), interpolation=cv2.INTER_LANCZOS4)
                t = torch.from_numpy(face).permute(2, 0, 1).float()
                self._ref_px = ip.normalize(t / 255.0)
                c = face.copy(); cv2.imwrite(out.replace(".mp4", "_refcrop.png"), cv2.cvtColor(c, cv2.COLOR_RGB2BGR))
            imgs = self._ref_px.unsqueeze(0).repeat(images.shape[0], 1, 1, 1).to(images.device, images.dtype)
            return orig_pil(self, imgs, device, dtype, generator, cfg)
        LipsyncPipeline.prepare_image_latents = _ref_latents
        print("reference face:", a.ref_image, "aligned with frame", a.ref_frame)

    config = OmegaConf.load(a.config)
    dtype = torch.float16
    scheduler = DDIMScheduler.from_pretrained("configs")
    audio_encoder = Audio2Feature(model_path=os.path.join(ROOT, "checkpoints", "whisper", "tiny.pt"), device="cuda",
                                  num_frames=config.data.num_frames, audio_feat_length=config.data.audio_feat_length)
    vae = AutoencoderKL.from_pretrained(VAE, torch_dtype=dtype)
    vae.config.scaling_factor = 0.18215; vae.config.shift_factor = 0
    unet, _ = UNet3DConditionModel.from_pretrained(OmegaConf.to_container(config.model), a.ckpt, device="cpu")
    unet = unet.to(dtype=dtype)
    if a.max_vram:
        total = torch.cuda.get_device_properties(0).total_memory / 1e9
        torch.cuda.set_per_process_memory_fraction(min(1.0, a.max_vram / total), 0)
        print(f"VRAM cap {a.max_vram} GB of {total:.1f}")
    if a.lowmem:
        unet_fwd = unet.forward

        def _seq_cfg(sample, timestep, encoder_hidden_states=None, **kw):
            # CFG batch [uncond, cond] -> two single passes (identical maths, half the activations)
            if sample.shape[0] == 2 and encoder_hidden_states is not None:
                h = encoder_hidden_states.shape[0] // 2
                o1 = unet_fwd(sample[:1], timestep, encoder_hidden_states=encoder_hidden_states[:h], **kw).sample
                o2 = unet_fwd(sample[1:], timestep, encoder_hidden_states=encoder_hidden_states[h:], **kw).sample
                return types.SimpleNamespace(sample=torch.cat([o1, o2]))
            return unet_fwd(sample, timestep, encoder_hidden_states=encoder_hidden_states, **kw)
        unet.forward = _seq_cfg
    if a.throttle < 1.0:
        import time
        inner_fwd = unet.forward

        def _throttled(*x, **kw):
            # GPU duty cycle: after each UNet pass, idle for elapsed*(1/duty-1) so a game on the same GPU gets
            # scheduled often (consumer GPUs on Windows have no per-process compute share)
            torch.cuda.synchronize(); t0 = time.perf_counter()
            r = inner_fwd(*x, **kw)
            torch.cuda.synchronize(); dt = time.perf_counter() - t0
            time.sleep(dt * (1.0 / a.throttle - 1.0))
            return r
        unet.forward = _throttled
        print(f"throttle: GPU duty {a.throttle:.0%}")
    pipe = LipsyncPipeline(vae=vae, audio_encoder=audio_encoder, unet=unet, scheduler=scheduler).to("cuda")
    if a.lowmem:
        pipe.enable_vae_slicing()
        print("lowmem: sequential CFG + VAE slicing")
    torch.manual_seed(a.seed)
    pipe(video_path=a.video, audio_path=a16, video_out_path=out, num_frames=config.data.num_frames,
         num_inference_steps=a.steps, guidance_scale=a.cfg, weight_dtype=dtype, width=config.data.resolution,
         height=config.data.resolution, mask_image_path=config.data.mask_image_path, temp_dir=tmp)
    syn = captured["f"][:n]
    if len(syn) < n:  # should not happen (audio padded); keep original tail
        syn = np.concatenate([syn, frames[len(syn):]])
    print("max VRAM GB", round(torch.cuda.max_memory_allocated() / 1e9, 2))
    # keep only the lower face from the model; eyes/hair/background stay the original pixels
    M = lower_face_mask(Ls, frames.shape[1], frames.shape[2], a.feather)[..., None]
    syn = np.clip(frames * (1 - M) + syn.astype(np.float32) * M, 0, 255).astype(np.uint8)
    cv2.imwrite(out.replace(".mp4", "_mask.png"), (M[n // 2, :, :, 0] * 255).astype(np.uint8))

    noa = out.replace(".mp4", "_noaudio.mp4")
    h, w = syn.shape[1:3]
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", f"{fps_in:.6f}", "-i", "-", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", noa],
                         stdin=subprocess.PIPE)
    p.stdin.write(np.ascontiguousarray(syn).tobytes()); p.stdin.close(); p.wait()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", noa, "-i", a.audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", out], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
