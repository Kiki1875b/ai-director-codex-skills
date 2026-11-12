"""LTX-2.5 (22B audio-video, distilled GGUF) on the remote ComfyUI: start key [+ end key] [+ given voice].

Built from the ComfyUI templates video_ltx2_5_flf2v (keys as LTXVAddGuide at frame 0 / -1, 8 sigmas, DualCFG 1/1)
and video_ltx2_3_ia2v (given audio: LTXVAudioVAEEncode + SetLatentNoiseMask(0) so the voice is kept, not generated).

  python ltx_remote.py --image media/S3-5-key-v7.png --end-image media/S3-5-end-key-v3.png \
      --audio export/sync_so/S3-5_dialogue.wav --prompt-file prompts/motion/S3-5-ltx-v3.txt \
      --out media/video/S3-5-ltx-v4.mp4 --seed 3501

DEFAULTS = the S3-5 v4 recipe (project default video model since 2026-11-10, user decision):
  video CFG 2.0 (so the negative works; NAG does not hook LTX), negatives below incl. smile / looking at the camera /
  head tilting back / exaggerated mouth, auto mid guides of the start key every 24 frames up to 2 s before the end
  (strength 0.25), model-input voice -10 dB (the edit keeps the original voice), keys strength 0.7, no ModalityGuidance,
  two-stage upscale (S3-5 v7, user decision 2026-11-10: sync 0.63->0.67, 5 min; sharpness unchanged).
  Old behaviour: --video-cfg 1 --mid-guides none --audio-gain 0 --no-upscale.
Frames = round(seconds*fps) rounded to 8k+1 (--seconds defaults to the audio length, else 5).
Models on the server: unet/ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf, text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot,
vae/ltx-2.5-video-vae-bf16, vae/ltx-2.5-audio-vae-bf16. Licence: LTX-2.x Community (paid only for >= $10M revenue).
Server: --server or env COMFY_URL (default http://127.0.0.1:8188). Never expose this server publicly.
"""
import argparse
import io
import json
import os
import random
import subprocess
import sys
import time
import uuid
import wave

import requests
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "ai-director", "scripts"))
import ledger  # noqa: E402
import comfy_guard  # noqa: E402

UNET = "ltx-2.5-22b-distilled-UD-Q3_K_XL.gguf"
TE = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
VVAE = "ltx-2.5-video-vae-bf16.safetensors"
AVAE = "ltx-2.5-audio-vae-bf16.safetensors"
SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"  # distilled 8-step (template)
SIGMAS_REFINE = "0.85, 0.7250, 0.4219, 0.0"  # stage-2 refine after the x2 upsampler (video_ltx2_5_i2v template)
UPSCALER = "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"
NEG = ("blurry, out of focus, overexposed, low contrast, washed out colors, flickering, distorted proportions, "
       "morphing face, identity change, face shape changing, exaggerated facial expressions, grimace, frown, "
       "extra people, text, subtitles, watermark, camera movement, zoom, "
       # S3-5 v2-v4: act only with CFG > 1; removed the smile and the talking-to-camera drift
       "smiling, smile, grin, raised lip corners, looking at the camera, staring into the lens, eye contact with the viewer, "
       "frontal face, head tilting back, head bobbing, eyes closing, puckered lips, exaggerated mouth movements, "
       "wide open mouth, over-articulated lips, big jaw movement, showing teeth")


def fit(src, w, h):
    """cover-resize and centre-crop to exactly w x h"""
    im = Image.open(src).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    buf = io.BytesIO()
    im.crop((l, t, l + w, t + h)).save(buf, "PNG")
    return buf.getvalue()


def upload(srv, data, ext, mime):
    name = f"aid_{uuid.uuid4().hex[:8]}{ext}"
    r = requests.post(f"{srv}/upload/image", files={"image": (name, data, mime)}, data={"overwrite": "true"}, timeout=120)
    r.raise_for_status()
    return r.json()["name"]


def wav_seconds(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def add_guides(wf, base, cond, latent, end, strength, mid_guides):
    """chain LTXVAddGuide nodes (start key 0, end key -1, weak mid guides); returns the last node id.
    Node ids: base, base+1 (end), base+10+i (mids). The guide image is resized to the latent inside the node."""
    nid = str(base)
    wf[nid] = {"class_type": "LTXVAddGuide", "inputs": {"positive": [cond, 0], "negative": [cond, 1], "vae": ["3", 0],
               "latent": latent, "image": ["11", 0], "frame_idx": 0, "strength": strength}}
    if end:
        prev, nid = nid, str(base + 1)
        wf[nid] = {"class_type": "LTXVAddGuide", "inputs": {"positive": [prev, 0], "negative": [prev, 1], "vae": ["3", 0],
                   "latent": [prev, 2], "image": ["14", 0], "frame_idx": -1, "strength": strength}}
    for i, (fidx, st, *src) in enumerate(mid_guides or []):
        prev, nid = nid, str(base + 10 + i)
        wf[nid] = {"class_type": "LTXVAddGuide", "inputs": {"positive": [prev, 0], "negative": [prev, 1], "vae": ["3", 0],
                   "latent": [prev, 2], "image": ["14" if src and src[0] == "end" else "11", 0], "frame_idx": fidx, "strength": st}}
    return nid


def build(img, end, aud, pos, neg, w, h, frames, fps, seed, strength, prefix, video_cfg=1.0, mid_guides=None, modality=1.0,
          upscale=False):
    # video_cfg 1 = negative prompt ignored (distilled default). >1 runs a real CFG pass (~2x time) so the
    # negative works; NAG does not hook LTX attention in ComfyUI 0.44. audio_cfg stays 1 (voice is given/fixed).
    # upscale: official two-stage (video_ltx2_5_i2v template): stage 1 at half size, x2 latent upsampler, guides again
    # at full size, 3 refine steps (0.85..0). Without it the clip is generated once at full size (FLF template).
    if upscale:
        return build_two_stage(img, end, aud, pos, neg, w, h, frames, fps, seed, strength, prefix, video_cfg, mid_guides, modality)
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": TE, "type": "ltxv", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VVAE}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": AVAE}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": pos}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": neg}},
        "7": {"class_type": "LTXVConditioning", "inputs": {"positive": ["5", 0], "negative": ["6", 0], "frame_rate": fps}},
        "8": {"class_type": "EmptyLTXVLatentVideo", "inputs": {"width": w, "height": h, "length": frames, "batch_size": 1}},
        "10": {"class_type": "LoadImage", "inputs": {"image": img}},
        "11": {"class_type": "LTXVPreprocess", "inputs": {"image": ["10", 0], "img_compression": 18}},
        "12": {"class_type": "LTXVAddGuide", "inputs": {"positive": ["7", 0], "negative": ["7", 1], "vae": ["3", 0],
               "latent": ["8", 0], "image": ["11", 0], "frame_idx": 0, "strength": strength}},
    }
    guide = "12"
    if end:
        wf["13"] = {"class_type": "LoadImage", "inputs": {"image": end}}
        wf["14"] = {"class_type": "LTXVPreprocess", "inputs": {"image": ["13", 0], "img_compression": 18}}
        wf["15"] = {"class_type": "LTXVAddGuide", "inputs": {"positive": ["12", 0], "negative": ["12", 1], "vae": ["3", 0],
                    "latent": ["12", 2], "image": ["14", 0], "frame_idx": -1, "strength": strength}}
        guide = "15"
    for i, (fidx, st, *src) in enumerate(mid_guides or []):  # weak extra guides inside the clip (start key, or end key with "e")
        nid = str(50 + i)
        wf[nid] = {"class_type": "LTXVAddGuide", "inputs": {"positive": [guide, 0], "negative": [guide, 1], "vae": ["3", 0],
                   "latent": [guide, 2], "image": ["14" if src and src[0] == "end" else "11", 0], "frame_idx": fidx, "strength": st}}
        guide = nid
    if aud:  # given voice: encode it and mask it out of denoising (mask 0 = keep)
        wf["20"] = {"class_type": "LoadAudio", "inputs": {"audio": aud}}
        wf["21"] = {"class_type": "LTXVAudioVAEEncode", "inputs": {"audio": ["20", 0], "audio_vae": ["4", 0]}}
        wf["22"] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": w, "height": h}}
        wf["23"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["21", 0], "mask": ["22", 0]}}
        alat = ["23", 0]
    else:
        wf["21"] = {"class_type": "LTXVEmptyLatentAudio", "inputs": {"audio_vae": ["4", 0], "frames_number": frames,
                    "frame_rate": fps, "batch_size": 1}}
        alat = ["21", 0]
    model = ["1", 0]
    if modality and modality != 1.0:  # A/V coupling (lip-sync) guidance: one extra pass per step, reference default 3.0
        wf["25"] = {"class_type": "LTXVModalityGuidance", "inputs": {"model": model, "modality_scale": modality,
                    "start_percent": 0.0, "end_percent": 1.0}}
        model = ["25", 0]
    wf.update({
        "30": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [guide, 2], "audio_latent": alat}},
        "31": {"class_type": "LTXVDualCFGGuider", "inputs": {"model": model, "positive": [guide, 0], "negative": [guide, 1],
               "video_cfg": video_cfg, "audio_cfg": 1.0}},
        "32": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "33": {"class_type": "SamplerEulerAncestral", "inputs": {"eta": 0.0, "s_noise": 1.0}},
        "34": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS}},
        "35": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["32", 0], "guider": ["31", 0], "sampler": ["33", 0],
               "sigmas": ["34", 0], "latent_image": ["30", 0]}},
        "36": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["35", 1]}},
        "37": {"class_type": "LTXVCropGuides", "inputs": {"positive": [guide, 0], "negative": [guide, 1], "latent": ["36", 0]}},
        "38": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["37", 2], "vae": ["3", 0], "tile_size": 512,
               "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}},
        "39": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["36", 1], "audio_vae": ["4", 0]}},
        "40": {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "audio": ["39", 0], "fps": fps}},
        "41": {"class_type": "SaveVideo", "inputs": {"video": ["40", 0], "filename_prefix": prefix, "format": "auto", "format.codec": "auto"}},
    })
    return wf


def build_two_stage(img, end, aud, pos, neg, w, h, frames, fps, seed, strength, prefix, video_cfg, mid_guides, modality):
    if (w // 2) % 32 or (h // 2) % 32:
        sys.exit("--upscale needs width/height divisible by 64 (stage 1 runs at half size)")
    # stage 1 = the single-stage graph at half size, ending at the cropped (guide-free) video latent
    wf = build(img, end, aud, pos, neg, w // 2, h // 2, frames, fps, seed, strength, prefix, video_cfg, mid_guides, modality)
    for k in ("38", "39", "40", "41"):
        del wf[k]
    model = wf["31"]["inputs"]["model"]
    alat = wf["30"]["inputs"]["audio_latent"]
    if aud:  # the voice mask must match the full-size latent in stage 2
        wf["22"]["inputs"].update(width=w, height=h)
    wf["60"] = {"class_type": "LatentUpscaleModelLoader", "inputs": {"model_name": UPSCALER}}
    wf["61"] = {"class_type": "LTXVLatentUpsampler", "inputs": {"samples": ["37", 2], "upscale_model": ["60", 0], "vae": ["3", 0]}}
    g2 = add_guides(wf, 100, "7", ["61", 0], end, strength, mid_guides)
    wf.update({
        "70": {"class_type": "LTXVConcatAVLatent", "inputs": {"video_latent": [g2, 2], "audio_latent": alat}},
        "71": {"class_type": "LTXVDualCFGGuider", "inputs": {"model": model, "positive": [g2, 0], "negative": [g2, 1],
               "video_cfg": video_cfg, "audio_cfg": 1.0}},
        "72": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + 1}},
        "73": {"class_type": "SamplerEulerAncestral", "inputs": {"eta": 0.0, "s_noise": 1.0}},
        "74": {"class_type": "ManualSigmas", "inputs": {"sigmas": SIGMAS_REFINE}},
        "75": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["72", 0], "guider": ["71", 0], "sampler": ["73", 0],
               "sigmas": ["74", 0], "latent_image": ["70", 0]}},
        "76": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["75", 1]}},
        "77": {"class_type": "LTXVCropGuides", "inputs": {"positive": [g2, 0], "negative": [g2, 1], "latent": ["76", 0]}},
        "38": {"class_type": "VAEDecodeTiled", "inputs": {"samples": ["77", 2], "vae": ["3", 0], "tile_size": 512,
               "overlap": 64, "temporal_size": 64, "temporal_overlap": 16}},
        "39": {"class_type": "LTXVAudioVAEDecode", "inputs": {"samples": ["76", 1], "audio_vae": ["4", 0]}},
        "40": {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "audio": ["39", 0], "fps": fps}},
        "41": {"class_type": "SaveVideo", "inputs": {"video": ["40", 0], "filename_prefix": prefix, "format": "auto", "format.codec": "auto"}},
    })
    return wf


def wait_and_fetch(srv, pid, out, timeout, tool="ltx_remote"):
    """Wait for the server job and download its output. Every exit leaves a terminal ledger event; a failure after
    the server finished keeps the known server time (gen_fetch_fail) so a later --fetch can complete the same job."""
    t0 = time.time()
    exec_s = None
    try:
        while time.time() - t0 < timeout:
            h = requests.get(f"{srv}/history/{pid}", timeout=30).json()
            if pid in h:
                exec_s = ledger.exec_seconds(h[pid])
                st = h[pid].get("status", {})
                if st.get("status_str") == "error":
                    msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                    ledger.record(out, "gen_fail", tool=tool, job_id=pid, wall_s=round(time.time() - t0, 1), exec_s=exec_s)
                    sys.exit(f"server error: {json.dumps(msgs, ensure_ascii=False)[:1500]}")
                files = [f for o in h[pid].get("outputs", {}).values() for k in ("images", "videos", "gifs") for f in o.get(k, [])]
                if files:
                    f = files[0]
                    r = requests.get(f"{srv}/view", params={"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                                             "type": f.get("type", "output")}, timeout=300)
                    r.raise_for_status()
                    with open(out, "wb") as fh:
                        fh.write(r.content)
                    ledger.record(out, "gen_done", tool=tool, job_id=pid, wall_s=round(time.time() - t0, 1), exec_s=exec_s)
                    print(f"saved {out} ({len(r.content)/1e6:.1f} MB) after {time.time()-t0:.0f}s", flush=True)
                    return
            time.sleep(15)
    except (SystemExit, KeyboardInterrupt) as e:
        if isinstance(e, KeyboardInterrupt):
            ledger.record(out, "gen_interrupted", tool=tool, job_id=pid, wall_s=round(time.time() - t0, 1), exec_s=exec_s)
        raise
    except Exception as e:  # noqa: BLE001 - network or disk error: the server job may still be fine
        ledger.record(out, "gen_fetch_fail", tool=tool, job_id=pid, wall_s=round(time.time() - t0, 1), exec_s=exec_s,
                      reason=f"{type(e).__name__}: {e}"[:300])
        sys.exit(f"could not fetch the result ({type(e).__name__}: {e}); the server job may still be fine: "
                 f"re-run with --fetch {pid}")
    ledger.record(out, "gen_timeout", tool=tool, job_id=pid, wall_s=round(time.time() - t0, 1))
    sys.exit(f"timeout; re-run with --fetch {pid}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    p.add_argument("--image")
    p.add_argument("--end-image")
    p.add_argument("--audio", help="voice WAV kept as-is (audio-to-video); omit to let the model make sound")
    p.add_argument("--prompt"); p.add_argument("--prompt-file")
    p.add_argument("--negative", default=NEG)
    p.add_argument("--negative-extra", default="", help="appended to --negative")
    p.add_argument("--video-cfg", type=float, default=2.0, help=">1 makes the negative prompt work; 1 = distilled default, negative ignored")
    p.add_argument("--audio-gain", type=float, default=-10.0, help="dB applied to the voice fed to the model only (v4 recipe -10)")
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=1280); p.add_argument("--height", type=int, default=704)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--seconds", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--strength", type=float, default=0.7, help="key guide strength (template 0.7)")
    p.add_argument("--modality", type=float, default=1.0, help="LTXVModalityGuidance A/V coupling for lip sync (ref 3.0; 1 = off)")
    p.add_argument("--mid-guides", default="auto", help="weak guides of the START key: 'auto' (every 24 f, 0.25, ending 2 s "
                   "before the last frame), 'none', or 'frame:strength,...' e.g. 24:0.25,48:0.25; prefix e = end key (e72:0.4)")
    p.add_argument("--upscale", action=argparse.BooleanOptionalAction, default=True,
                   help="official two-stage: half size + x2 latent upsampler + 3 refine steps (default since S3-5 v7; "
                        "--no-upscale = single stage at full size). Needs the server's --reserve-vram 2")
    p.add_argument("--timeout", type=int, default=6 * 3600)
    p.add_argument("--fetch", help="prompt_id of a job already queued")
    p.add_argument("--allow-queue", action="store_true", help="queue even if the GPU is busy (only when the user asked)")
    a = p.parse_args()
    srv = a.server.rstrip("/")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    if a.fetch:
        return wait_and_fetch(srv, a.fetch, a.out, a.timeout)
    if a.width % 32 or a.height % 32:
        sys.exit("width/height must be divisible by 32")
    pos = open(a.prompt_file, encoding="utf-8").read().strip() if a.prompt_file else a.prompt
    if not pos or not a.image:
        sys.exit("need --image and --prompt/--prompt-file")
    secs = a.seconds or (wav_seconds(a.audio) if a.audio else 5.0)
    frames = max(9, round(secs * a.fps / 8) * 8 + 1)
    seed = a.seed if a.seed is not None else random.randint(0, 2**31)
    comfy_guard.require_free(srv, a.allow_queue)
    img = upload(srv, fit(a.image, a.width, a.height), ".png", "image/png")
    end = upload(srv, fit(a.end_image, a.width, a.height), ".png", "image/png") if a.end_image else None
    aud = None
    if a.audio:
        data = open(a.audio, "rb").read()
        if a.audio_gain:  # quieter voice for the model only; the edit keeps the original file
            data = subprocess.run(["ffmpeg", "-v", "error", "-i", a.audio, "-af", f"volume={a.audio_gain}dB", "-f", "wav", "-"],
                                  capture_output=True, check=True).stdout
        aud = upload(srv, data, ".wav", "audio/wav")
    prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
    neg = a.negative.rstrip(", ") + (", " + a.negative_extra if a.negative_extra else "")
    if a.mid_guides == "auto":
        mids = [(f, 0.25) for f in range(24, frames - 48, 24)]  # 121 f -> 24, 48, 72 (S3-5 v4)
    elif a.mid_guides == "none":
        mids = []
    else:
        # "48:0.25" = start key at frame 48; "e72:0.4" = END key at frame 72 (hold the end pose early, S1-3 v4)
        mids = [(int(f.lstrip("e")), float(s), "end") if f.startswith("e") else (int(f), float(s))
                for f, s in (x.split(":") for x in a.mid_guides.split(",") if x.strip())]
        if any(len(m) == 3 for m in mids) and not a.end_image:
            sys.exit("e<frame> mid guides need --end-image")
    if any(not 0 < m[0] < frames - 1 for m in mids):
        sys.exit(f"mid guide frames must be inside 1..{frames - 2}")
    wf = build(img, end, aud, pos, neg, a.width, a.height, frames, a.fps, seed, a.strength, prefix, a.video_cfg, mids, a.modality, a.upscale)
    with open(os.path.splitext(a.out)[0] + "_workflow.json", "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=1)
    r = comfy_guard.submit(srv, {"prompt": wf}, a.allow_queue)
    if r.status_code != 200:
        sys.exit(f"queue rejected: {r.text[:2000]}")
    pid = r.json()["prompt_id"]
    ledger.record(a.out, "gen_submit", tool="ltx_remote", job_id=pid, seed=seed, prompt=pos,
                  inputs=[a.image, a.end_image, a.audio],
                  settings={"frames": frames, "fps": a.fps, "size": f"{a.width}x{a.height}", "video_cfg": a.video_cfg,
                            "mid_guides": mids, "upscale": a.upscale, "strength": a.strength, "audio_gain": a.audio_gain,
                            "negative_sha256": ledger.hashlib.sha256(neg.encode("utf-8")).hexdigest()})
    print(f"queued {pid}: {frames} frames ({frames/a.fps:.2f}s) {a.width}x{a.height} seed {seed} cfg {a.video_cfg} "
          f"mid {mids} audio {a.audio_gain if a.audio else '-'} dB", flush=True)
    wait_and_fetch(srv, pid, a.out, a.timeout)


if __name__ == "__main__":
    main()
