"""InfiniteTalk (Wan2.1 I2V 14B + InfiniteTalk patch) talking-shot generation on the remote ComfyUI.

Image + speech audio -> a clip whose mouth, head and face move with the audio (no lip-sync pass afterwards).
Uses ComfyUI's native nodes (WanInfiniteTalkToVideo, ModelPatchLoader, AudioEncoderLoader) + ComfyUI-GGUF.
Chunks of 81 frames at 25 fps; each extra chunk continues from the last `motion` frames of the previous one.

  python infinitetalk_remote.py --image start.png --audio line.wav --prompt-file p.txt --out out.mp4 \
      [--width 848 --height 480] [--seconds 5.04] [--seed 1] [--steps 6] [--audio-scale 1.0]

Models (server, all Apache-2.0 / MIT, checked 2026-11-09):
  unet/wan2.1-i2v-14b-480p-Q4_K_M.gguf                       city96 (Apache-2.0)
  model_patches/wan2.1_infiniteTalk_single_fp16.safetensors   Comfy-Org/Wan-2.1 (Apache-2.0, MeiGen-AI InfiniteTalk)
  audio_encoders/wav2vec2-chinese-base_fp16.safetensors       Kijai (MIT, TencentGameMate)
  loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64.safetensors  lightx2v (Apache-2.0)
  text_encoders/umt5_xxl_fp8_e4m3fn_scaled, vae/wan_2.1_vae
"""
import argparse
import io
import os
import random
import subprocess
import sys
import tempfile
import time
import uuid

import requests
from PIL import Image

FPS = 25
NEG = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
       "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景")


def fit(src, w, h):
    im = Image.open(src).convert("RGB")
    sw, sh = im.size
    s = max(w / sw, h / sh)
    im = im.resize((round(sw * s), round(sh * s)), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    b = io.BytesIO()
    im.crop((l, t, l + w, t + h)).save(b, "PNG")
    return b.getvalue()


def build(img, aud, pos, w, h, chunks, seed, steps, scale, motion, prefix, unet, lora, lora_strength, cfg=1.0, neg=NEG):
    wf = {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": unet}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": lora, "strength_model": lora_strength}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": pos}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "7": {"class_type": "ModelPatchLoader", "inputs": {"name": "wan2.1_infiniteTalk_single_fp16.safetensors"}},
        "8": {"class_type": "AudioEncoderLoader", "inputs": {"audio_encoder_name": "wav2vec2-chinese-base_fp16.safetensors"}},
        "9": {"class_type": "LoadAudio", "inputs": {"audio": aud}},
        "10": {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["8", 0], "audio": ["9", 0]}},
        "11": {"class_type": "LoadImage", "inputs": {"image": img}},
        "12": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
    }
    prev = None
    for c in range(chunks):
        b = 100 + c * 10
        it = {"mode": "single_speaker", "model": ["2", 0], "model_patch": ["7", 0], "positive": ["4", 0],
              "negative": ["5", 0], "vae": ["6", 0], "width": w, "height": h, "length": 81,
              "audio_encoder_output_1": ["10", 0], "motion_frame_count": motion, "audio_scale": scale}
        if prev is None:
            it["start_image"] = ["11", 0]
        else:
            it["previous_frames"] = prev
        wf[str(b)] = {"class_type": "WanInfiniteTalkToVideo", "inputs": it}
        wf[str(b + 1)] = {"class_type": "BasicScheduler", "inputs": {"model": [str(b), 0], "scheduler": "normal", "steps": steps, "denoise": 1.0}}
        wf[str(b + 2)] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed + c}}
        wf[str(b + 3)] = {"class_type": "CFGGuider", "inputs": {"model": [str(b), 0], "positive": [str(b), 1], "negative": [str(b), 2], "cfg": cfg}}
        wf[str(b + 4)] = {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": [str(b + 2), 0], "guider": [str(b + 3), 0],
                                                                          "sampler": ["12", 0], "sigmas": [str(b + 1), 0], "latent_image": [str(b), 3]}}
        wf[str(b + 5)] = {"class_type": "VAEDecode", "inputs": {"samples": [str(b + 4), 0], "vae": ["6", 0]}}
        if prev is None:
            cur = [str(b + 5), 0]
        else:  # drop the motion frames the chunk re-decodes, then append
            wf[str(b + 6)] = {"class_type": "ImageFromBatch", "inputs": {"image": [str(b + 5), 0], "batch_index": motion, "length": 81 - motion}}
            wf[str(b + 7)] = {"class_type": "ImageBatch", "inputs": {"image1": prev, "image2": [str(b + 6), 0]}}
            cur = [str(b + 7), 0]
        prev = cur
    wf["900"] = {"class_type": "SaveImage", "inputs": {"images": prev, "filename_prefix": prefix}}
    return wf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--audio", required=True, help="speech wav, already padded/placed for the whole clip")
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--width", type=int, default=848)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--seconds", type=float, default=None, help="clip length to keep (default: audio length)")
    p.add_argument("--seed", type=int, default=random.randint(0, 2**31))
    p.add_argument("--steps", type=int, default=6)
    p.add_argument("--audio-scale", type=float, default=1.0)
    p.add_argument("--motion", type=int, default=9)
    p.add_argument("--unet", default="wan2.1-i2v-14b-480p-Q4_K_M.gguf")
    p.add_argument("--lora", default="lightx2v_I2V_14B_480p_cfg_step_distill_rank64.safetensors")
    p.add_argument("--lora-strength", type=float, default=1.0)
    p.add_argument("--cfg", type=float, default=1.0, help=">1 makes the negative prompt work (slower, ~2x)")
    p.add_argument("--neg-extra", default="", help="appended to the default negative prompt")
    p.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    a = p.parse_args()

    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.audio]))
    keep = a.seconds or dur
    need = int(round(keep * FPS)) + 1
    chunks = 1 if need <= 81 else 1 + -(-(need - 81) // (81 - a.motion))
    total = 81 + (chunks - 1) * (81 - a.motion)
    print(f"audio {dur:.2f}s keep {keep:.2f}s -> {chunks} chunk(s), {total} frames, seed {a.seed}")

    tag = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory() as td:  # pad audio with silence to the generated length
        pad = os.path.join(td, "a.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", a.audio, "-af", f"apad=whole_dur={total / FPS:.3f}",
                        "-ar", "16000", "-ac", "1", pad], check=True)
        srv = a.server
        iname, aname = f"it_{tag}.png", f"it_{tag}.wav"
        requests.post(f"{srv}/upload/image", files={"image": (iname, fit(a.image, a.width, a.height), "image/png")},
                      data={"overwrite": "true"}, timeout=60).raise_for_status()
        requests.post(f"{srv}/upload/image", files={"image": (aname, open(pad, "rb").read(), "audio/wav")},
                      data={"overwrite": "true"}, timeout=60).raise_for_status()
    pos = open(a.prompt_file, encoding="utf-8").read().strip()
    wf = build(iname, aname, pos, a.width, a.height, chunks, a.seed, a.steps, a.audio_scale, a.motion,
               f"it_{tag}", a.unet, a.lora, a.lora_strength, a.cfg, NEG + (", " + a.neg_extra if a.neg_extra else ""))
    r = requests.post(f"{srv}/prompt", json={"prompt": wf}, timeout=60)
    if r.status_code != 200:
        sys.exit(r.text)
    pid = r.json()["prompt_id"]
    print("queued", pid)
    t0 = time.time()
    while True:
        time.sleep(15)
        h = requests.get(f"{srv}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                sys.exit(f"error: {st.get('messages')}")
            if st.get("completed"):
                break
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    imgs = h[pid]["outputs"]["900"]["images"]
    with tempfile.TemporaryDirectory() as td:
        for k, i in enumerate(imgs):
            b = requests.get(f"{srv}/view", params={"filename": i["filename"], "subfolder": i["subfolder"], "type": i["type"]}, timeout=60)
            open(os.path.join(td, f"f_{k:05d}.png"), "wb").write(b.content)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        n = min(len(imgs), need)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(td, "f_%05d.png"),
                        "-i", a.audio, "-frames:v", str(n), "-af", f"apad", "-t", f"{n / FPS:.3f}",
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", a.out], check=True)
    print(f"wrote {a.out} ({n} frames, {len(imgs)} generated)")


if __name__ == "__main__":
    main()
