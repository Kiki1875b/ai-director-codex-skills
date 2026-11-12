"""MuseTalk 1.5 lip sync wrapper (server copy: C:\\ai\\musetalk\\lipsync.py).

    python lipsync.py --video in.mp4 --audio in.wav --out out.mp4 [--bbox-shift N]
                      [--start S --end E] [--with-audio] [--fade N] [--batch-size 8]

- Processes frames [start, end) of the video (seconds; default whole clip). The output has exactly
  those frames at the source fps. The audio starts at `start`.
- Only frames covered by the audio are generated (MuseTalk 1.5, fp16). Frames after the audio ends,
  and frames where no face is found, are the untouched source frames. The last --fade generated
  frames are blended toward the source frames to avoid a pop where the audio ends.
- Output is video only unless --with-audio (then the wav is muxed as AAC; video length is kept).

Deviation from upstream (repo 0a89dec, left unmodified): musetalk/utils/preprocessing.py needs
mmpose + DWPose for 68 face landmarks and S3FD for a "face present" check. Both are replaced here by
MediaPipe FaceMesh (Apache-2.0, model bundled in the wheel), mapped to the iBUG-68 layout
(MP68 below). The bbox / half-face logic of get_landmark_and_bbox is reproduced line for line:
half_face = lm[29]; top = lm29.y + shift - (max_y - (lm29.y + shift)); box = (min_x, top, max_x, max_y);
v1.5 adds extra_margin=10 below the chin. Blending (face parsing "jaw" mode, cheek width 90),
VAE/UNet/Whisper usage and audio chunking are upstream code.
"""
import argparse, json, math, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))  # C:\ai\musetalk
REPO = os.path.join(ROOT, "MuseTalk")
FFMPEG = os.path.join(ROOT, "bin", "ffmpeg.exe")
FFPROBE = os.path.join(ROOT, "bin", "ffprobe.exe")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# iBUG-68 order -> MediaPipe FaceMesh index (jaw 0-16, brows 17-26, nose 27-35, eyes 36-47, mouth 48-67).
MP68 = [162, 234, 93, 58, 172, 136, 149, 148, 152, 377, 378, 365, 397, 288, 323, 454, 389,
        71, 63, 105, 66, 107, 336, 296, 334, 293, 301,
        168, 197, 5, 4, 75, 97, 2, 326, 305,
        33, 160, 158, 133, 153, 144, 362, 385, 387, 263, 373, 380,
        61, 39, 37, 0, 267, 269, 291, 405, 314, 17, 84, 181,
        78, 82, 13, 312, 308, 317, 14, 87]


def probe(video):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames",
                          "-of", "json", video], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), int(s["nb_read_frames"])


def read_frames(video, w, h, first, last):
    import numpy as np
    vf = f"select=between(n\\,{first}\\,{last - 1})"
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", video, "-vf", vf, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    arr = np.frombuffer(raw, np.uint8)[: n * w * h * 3].reshape(n, h, w, 3)
    return [f.copy() for f in arr]


def face_boxes(frames, bbox_shift):
    """MediaPipe replacement for preprocessing.get_landmark_and_bbox (same box arithmetic)."""
    import numpy as np, cv2
    from mediapipe.python.solutions import face_mesh
    boxes, lms = [], []
    with face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False,
                            min_detection_confidence=0.5, min_tracking_confidence=0.5) as fm:
        for fr in frames:
            h, w = fr.shape[:2]
            res = fm.process(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
            if not res.multi_face_landmarks:
                boxes.append(None); lms.append(None); continue
            pts = np.array([[p.x * w, p.y * h] for p in res.multi_face_landmarks[0].landmark])
            lm = pts[MP68].astype(np.int32)
            half = lm[29].copy()
            if bbox_shift != 0:
                half[1] = bbox_shift + half[1]
            half_dist = np.max(lm[:, 1]) - half[1]
            upper = max(0, half[1] - half_dist)
            x1, y1, x2, y2 = int(np.min(lm[:, 0])), int(upper), int(np.max(lm[:, 0])), int(np.max(lm[:, 1]))
            if y2 - y1 <= 0 or x2 - x1 <= 0 or x1 < 0:  # upstream falls back to the detector box
                x1, y1 = [int(max(0, v)) for v in pts.min(0)]
                x2, y2 = [int(v) for v in pts.max(0)]
            boxes.append((x1, y1, x2, y2)); lms.append(lm.tolist())
    return boxes, lms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True); ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bbox-shift", type=int, default=0, help="px; + moves the mask top down (v1.5 trained with 0)")
    ap.add_argument("--start", type=float, default=0.0); ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--with-audio", action="store_true")
    ap.add_argument("--fade", type=int, default=2, help="frames blended back to source at the audio end")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--extra-margin", type=int, default=10)
    ap.add_argument("--crf", type=int, default=14)
    ap.add_argument("--save-coords", action="store_true", help="write <out>.coords.json")
    a = ap.parse_args()
    video, audio, out = (os.path.abspath(p) for p in (a.video, a.audio, a.out))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.chdir(ROOT)  # upstream modules load ./models/... relative paths
    sys.path.insert(0, REPO)
    t0 = time.time()

    import numpy as np, cv2, torch, librosa
    from transformers import WhisperModel
    from musetalk.utils.audio_processor import AudioProcessor
    from musetalk.utils.face_parsing import FaceParsing
    from musetalk.utils.face_parsing import resnet as _bisenet_resnet
    from musetalk.utils.blending import get_image
    # resnet18-5c106cde.pth is a legacy pickle that refuses weights_only=True. It only initialises the
    # BiSeNet backbone, which 79999_iter.pth then overwrites completely (strict load, all keys), so skip it.
    _bisenet_resnet.Resnet18.init_weight = lambda self, model_path: None

    w, h, fps, nb = probe(video)
    first = max(0, round(a.start * fps))
    last = nb if a.end is None else min(nb, round(a.end * fps))
    if last <= first:
        sys.exit("empty range")
    frames = read_frames(video, w, h, first, last)
    n_range = len(frames)
    if n_range != last - first:
        sys.exit(f"decoded {n_range} frames, expected {last - first}")

    audio_len = len(librosa.load(audio, sr=16000)[0])
    n_gen = min(n_range, math.floor(audio_len / 16000 * int(fps)))  # same count as get_whisper_chunk

    device = torch.device("cuda")
    torch.cuda.reset_peak_memory_stats()
    # Same models as upstream load_all_model, but the 3.4 GB fp32 UNet state dict is loaded on the CPU and
    # cast to fp16 before moving to the GPU (upstream torch.loads it straight onto CUDA: ~7 GB peak).
    from diffusers import UNet2DConditionModel
    from musetalk.models.vae import VAE
    from musetalk.models.unet import PositionalEncoding
    vae = VAE(model_path="models/sd-vae")
    vae.vae = vae.vae.half().to(device)
    with open("models/musetalkV15/musetalk.json") as f:
        unet_model = UNet2DConditionModel(**json.load(f))
    unet_model.load_state_dict(torch.load("models/musetalkV15/unet.pth", map_location="cpu", weights_only=True))

    class _U:  # minimal stand-in for musetalk.models.unet.UNet (only .model is used)
        model = unet_model.half().to(device).eval()
    unet = _U()
    pe = PositionalEncoding(d_model=384).half().to(device)
    ap_ = AudioProcessor(feature_extractor_path="models/whisper")
    whisper = WhisperModel.from_pretrained("models/whisper").to(device=device, dtype=torch.float16).eval()
    whisper.requires_grad_(False)
    fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)
    t_load = time.time()

    with torch.no_grad():
        feats, librosa_len = ap_.get_audio_feature(audio)
        chunks = ap_.get_whisper_chunk(feats, device, torch.float16, whisper, librosa_len, fps=fps,
                                       audio_padding_length_left=2, audio_padding_length_right=2)
    boxes, lms = face_boxes(frames[:n_gen], a.bbox_shift)
    t_lm = time.time()

    idx = [i for i in range(n_gen) if boxes[i] is not None]
    crops = {}
    for i in idx:
        x1, y1, x2, y2 = boxes[i]
        y2 = min(y2 + a.extra_margin, h)
        crops[i] = (x1, y1, x2, y2)
    timesteps = torch.tensor([0], device=device)
    outframes = [f.copy() for f in frames]
    with torch.no_grad():
        for b in range(0, len(idx), a.batch_size):
            bi = idx[b:b + a.batch_size]
            lat = []
            for i in bi:
                x1, y1, x2, y2 = crops[i]
                c = cv2.resize(frames[i][y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
                lat.append(vae.get_latents_for_unet(c))
            lat = torch.cat(lat, 0).to(device=device, dtype=torch.float16)
            wb = torch.stack([chunks[i] for i in bi]).to(device)
            pred = unet.model(lat, timesteps, encoder_hidden_states=pe(wb)).sample
            recon = vae.decode_latents(pred)
            for i, r in zip(bi, recon):
                x1, y1, x2, y2 = crops[i]
                r = cv2.resize(r.astype(np.uint8), (x2 - x1, y2 - y1))
                outframes[i] = get_image(frames[i], r, [x1, y1, x2, y2], mode="jaw", fp=fp)
    torch.cuda.synchronize()
    t_gen = time.time()

    for k in range(min(a.fade, n_gen)):  # fade the last generated frames back to source
        i = n_gen - 1 - k
        al = (a.fade - k) / (a.fade + 1)  # source weight: fade=2 -> 2/3 on the last frame, 1/3 before it
        outframes[i] = cv2.addWeighted(outframes[i], 1.0 - al, frames[i], al, 0)

    cmd = [FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
           "-r", f"{fps:g}", "-i", "-"]
    if a.with_audio:
        cmd += ["-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-crf", str(a.crf), "-preset", "slow", "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in outframes:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        sys.exit("ffmpeg encode failed")
    t_end = time.time()

    info = {"out": out, "fps": fps, "range_frames": [first, last], "n_out": n_range, "n_generated": len(idx),
            "n_audio_frames": n_gen, "no_face_frames": [i for i in range(n_gen) if boxes[i] is None],
            "sec_total": round(t_end - t0, 2), "sec_load": round(t_load - t0, 2),
            "sec_landmarks": round(t_lm - t_load, 2), "sec_generate": round(t_gen - t_lm, 2),
            "sec_per_video_sec": round((t_end - t0) / max(1e-6, n_gen / fps), 2),
            "vram_peak_alloc_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            "vram_peak_reserved_gb": round(torch.cuda.max_memory_reserved() / 2**30, 2)}
    if a.save_coords:
        with open(out + ".coords.json", "w") as f:
            json.dump({"boxes": boxes, "crops": [crops.get(i) for i in range(n_gen)], "lm68": lms}, f)
    print("RESULT " + json.dumps(info))


if __name__ == "__main__":
    main()
