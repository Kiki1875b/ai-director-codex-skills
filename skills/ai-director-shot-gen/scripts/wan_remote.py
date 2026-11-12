"""Wan 2.2 image-to-video on a remote ComfyUI (e.g. a GPU PC over Tailscale).

Uploads a keyframe, builds the API workflow here (no workflow file needed on the server), queues it, waits,
downloads the PNG frames, and writes <out>.mp4 (camera original) and, with --lut, <out>_graded.mp4
(frames -> S-Log3 -> .cube, the same grade the stills got).

  better motion / negatives / interpolation (custom nodes PainterI2V, ComfyUI-NAG, Frame-Interpolation):
      --motion-amp 1.15 --nag 5 --rife
  first-last-frame (transition into the next shot): add --end-image media/S1-2-key-v6.png
  python wan_remote.py --image media/S1-1-key-v2.png --prompt-file prompts/S1-1-motion.txt \
      --out media/video/S1-1-v1.mp4 --lut luts/sl_blue.cube [--model 14b|5b] [--frames 81] [--seed 1]

Models (must exist on the server):
  14b : Wan2.2 I2V A14B GGUF Q4_K_M high+low noise, lightx2v 4-step LoRAs, wan_2.1_vae   (default)
  5b  : wan2.2_ti2v_5B_fp16, wan2.2_vae
Server: --server or env COMFY_URL (default http://127.0.0.1:8188). Never expose this server publicly.
"""
import argparse
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ai-director-edit", "scripts"))
import log_lut  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "..", "ai-director", "scripts"))
import ledger  # noqa: E402
import comfy_guard  # noqa: E402

NEG = ("色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，"
       "多余的手指，画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走, "
       "slow motion, slow-mo, sluggish movement, frozen, morphing face, identity change, extra people, text, watermark, flicker, warping")


LORAS = {  # 4-step speed LoRA pairs (high, low)
    "lightx2v": ("wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
                 "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"),
    "motionfix": ("wan2.2_i2v_lightx2v_motion_fix_high.safetensors",   # rzgar slow-mo fix: less slow-motion drag
                  "wan2.2_i2v_lightx2v_motion_fix_low.safetensors"),
    # lightx2v 4-step 720p distilled MODELS (2026-04-12): the speed-up is baked in, so no LoRA (strength 0)
    "distill260412": ("wan2.2_i2v_lightx2v_motion_fix_high.safetensors",
                      "wan2.2_i2v_lightx2v_motion_fix_low.safetensors"),
    # lightx2v Wan2.2-Lightning T2V 4-step (Apache-2.0): for T2V-based models such as VACE-Fun
    "t2v-lightning": ("wan2.2_t2v_lightning_4step_250928_high.safetensors",
                      "wan2.2_t2v_lightning_4step_250928_low.safetensors"),
}
UNETS = {"distill260412": ("wan2.2_i2v_A14b_high_noise_lightx2v_4step_720p_260412-Q4_K_M.gguf",
                           "wan2.2_i2v_A14b_low_noise_lightx2v_4step_720p_260412-Q4_K_M.gguf")}
BASE_UNETS = ("Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf", "Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf")
# Wan2.2-Fun-A14B-Control (Apache-2.0, QuantStack GGUF): motion follows a pose/canny control video
FUN_CONTROL_UNETS = ("Wan2.2-Fun-A14B-Control_HighNoise-Q4_K_M.gguf", "Wan2.2-Fun-A14B-Control_LowNoise-Q4_K_M.gguf")
# Wan2.2-VACE-Fun-A14B (Apache-2.0, QuantStack GGUF): keyframes at any frame, masks, reference image
VACE_UNETS = ("Wan2.2-VACE-Fun-A14B-high-noise-Q4_K_S.gguf", "Wan2.2-VACE-Fun-A14B-low-noise-Q4_K_S.gguf")


def workflow_14b(img, pos, neg, w, h, frames, seed, steps, shift, prefix, lora="motionfix"):
    half = steps // 2
    lo_hi, lo_lo = LORAS[lora]
    un_hi, un_lo = UNETS.get(lora, BASE_UNETS)
    ls = 0.0 if lora in UNETS else 1.0
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": un_hi}},
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": un_lo}},
        "3": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "strength_model": ls,
              "lora_name": lo_hi}},
        "4": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["2", 0], "strength_model": ls,
              "lora_name": lo_lo}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["3", 0], "shift": shift}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["4", 0], "shift": shift}},
        "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": pos}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["7", 0], "text": neg}},
        "11": {"class_type": "LoadImage", "inputs": {"image": img}},
        "12": {"class_type": "WanImageToVideo", "inputs": {"positive": ["9", 0], "negative": ["10", 0], "vae": ["8", 0],
               "start_image": ["11", 0], "width": w, "height": h, "length": frames, "batch_size": 1}},
        "13": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["5", 0], "add_noise": "enable", "noise_seed": seed,
               "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0],
               "negative": ["12", 1], "latent_image": ["12", 2], "start_at_step": 0, "end_at_step": half,
               "return_with_leftover_noise": "enable"}},
        "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "disable", "noise_seed": seed,
               "steps": steps, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0],
               "negative": ["12", 1], "latent_image": ["13", 0], "start_at_step": half, "end_at_step": 10000,
               "return_with_leftover_noise": "disable"}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["8", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }


def workflow_5b(img, pos, neg, w, h, frames, seed, steps, shift, prefix):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": pos}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": neg}},
        "7": {"class_type": "LoadImage", "inputs": {"image": img}},
        "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["4", 0], "start_image": ["7", 0],
              "width": w, "height": h, "length": frames, "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["2", 0], "seed": seed, "steps": steps, "cfg": 5.0,
              "sampler_name": "uni_pc", "scheduler": "simple", "positive": ["5", 0], "negative": ["6", 0],
              "latent_image": ["8", 0], "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["4", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
    }


def fit(src, w, h):
    """cover-resize and centre-crop the keyframe to exactly w x h"""
    im = Image.open(src).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    l, t = (im.width - w) // 2, (im.height - h) // 2
    buf = io.BytesIO()
    im.crop((l, t, l + w, t + h)).save(buf, "PNG")
    return buf.getvalue()


def run(a):
    srv = a.server.rstrip("/")
    if a.negative_extra:
        a.negative = a.negative.rstrip(", ") + ", " + a.negative_extra
    if not a.negative.strip():
        sys.exit("empty negative prompt")
    pos = open(a.prompt_file, encoding="utf-8").read().strip() if a.prompt_file else a.prompt
    if not pos:
        sys.exit("need --prompt or --prompt-file")
    seed, steps, out_fps = a.seed, a.steps, a.fps
    if a.fetch:  # re-attach to a job already queued (e.g. the waiting process died)
        pid = a.fetch
        out_fps = a.fps * 3 // 2 if a.rife else a.fps
        print(f"fetching {pid}", flush=True)
    else:
        comfy_guard.require_free(srv, a.allow_queue)
        name = f"aid_{uuid.uuid4().hex[:8]}.png"
        r = requests.post(f"{srv}/upload/image", files={"image": (name, fit(a.image, a.width, a.height), "image/png")},
                          data={"overwrite": "true"}, timeout=60)
        r.raise_for_status()
        img = r.json()["name"]
        seed = a.seed if a.seed is not None else random.randint(0, 2**31)
        prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
        build = workflow_14b if a.model == "14b" else workflow_5b
        steps = a.steps or (4 if a.model == "14b" else 20)
        shift = a.shift or (5.0 if a.model == "14b" else 8.0)
        if a.model == "14b":
            wf = build(img, pos, a.negative, a.width, a.height, a.frames, seed, steps, shift, prefix, a.lora)
        else:
            wf = build(img, pos, a.negative, a.width, a.height, a.frames, seed, steps, shift, prefix)
        if a.end_image:  # first-last-frame: the model fills the motion between this keyframe and the next one
            if a.model != "14b":
                sys.exit("--end-image needs --model 14b")
            ename = f"aid_{uuid.uuid4().hex[:8]}_end.png"
            r = requests.post(f"{srv}/upload/image", files={"image": (ename, fit(a.end_image, a.width, a.height), "image/png")},
                              data={"overwrite": "true"}, timeout=60)
            r.raise_for_status()
            wf["17"] = {"class_type": "LoadImage", "inputs": {"image": r.json()["name"]}}
            wf["12"]["class_type"] = "WanFirstLastFrameToVideo"
            wf["12"]["inputs"]["end_image"] = ["17", 0]
        if a.control_video:  # Fun Control: the key is the look reference, the control video drives the motion
            if a.model != "14b" or a.end_image:
                sys.exit("--control-video needs --model 14b and no --end-image")
            vname = f"aid_{uuid.uuid4().hex[:8]}_ctl.mp4"
            r = requests.post(f"{srv}/upload/image", files={"image": (vname, open(a.control_video, "rb").read(), "video/mp4")},
                              data={"overwrite": "true"}, timeout=120)
            r.raise_for_status()
            wf["1"]["inputs"]["unet_name"], wf["2"]["inputs"]["unet_name"] = FUN_CONTROL_UNETS
            wf["30"] = {"class_type": "LoadVideo", "inputs": {"file": r.json()["name"]}}
            wf["31"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}}
            n12 = wf["12"]["inputs"]
            wf["12"] = {"class_type": "Wan22FunControlToVideo", "inputs": {
                "positive": n12["positive"], "negative": n12["negative"], "vae": n12["vae"], "width": n12["width"],
                "height": n12["height"], "length": n12["length"], "batch_size": 1, "ref_image": ["11", 0], "control_video": ["31", 0]}}
        if a.vace_control:  # VACE: keys pinned at frames (mask black = keep), the rest filled; --image is the identity reference
            if a.model != "14b" or a.end_image or a.control_video or not a.vace_mask:
                sys.exit("--vace-control needs --vace-mask, --model 14b and no --end-image/--control-video")
            names = []
            for path in (a.vace_control, a.vace_mask):
                vn = f"aid_{uuid.uuid4().hex[:8]}_vace.mp4"
                r = requests.post(f"{srv}/upload/image", files={"image": (vn, open(path, "rb").read(), "video/mp4")},
                                  data={"overwrite": "true"}, timeout=120)
                r.raise_for_status()
                names.append(r.json()["name"])
            wf["1"]["inputs"]["unet_name"], wf["2"]["inputs"]["unet_name"] = VACE_UNETS
            wf["30"] = {"class_type": "LoadVideo", "inputs": {"file": names[0]}}
            wf["31"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["30", 0]}}
            wf["32"] = {"class_type": "LoadVideo", "inputs": {"file": names[1]}}
            wf["33"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["32", 0]}}
            wf["34"] = {"class_type": "ImageToMask", "inputs": {"image": ["33", 0], "channel": "red"}}
            n12 = wf["12"]["inputs"]
            wf["12"] = {"class_type": "WanVaceToVideo", "inputs": {
                "positive": n12["positive"], "negative": n12["negative"], "vae": n12["vae"], "width": n12["width"],
                "height": n12["height"], "length": n12["length"], "batch_size": 1, "strength": a.vace_strength,
                "control_video": ["31", 0], "control_masks": ["34", 0], "reference_image": ["11", 0]}}
            # the reference frame is prepended in latent space: cut it off before decoding
            wf["35"] = {"class_type": "TrimVideoLatent", "inputs": {"samples": ["14", 0], "trim_amount": ["12", 3]}}
            wf["15"]["inputs"]["samples"] = ["35", 0]
        dec, save = ("15", "16") if a.model == "14b" else ("10", "11")
        if a.motion_amp and not a.end_image:  # PainterI2V: larger motion with the 4-step LoRA (1.0 = stock node)
            if a.model != "14b":
                sys.exit("--motion-amp needs --model 14b")
            wf["12"]["class_type"] = "PainterI2V"
            wf["12"]["inputs"]["motion_amplitude"] = a.motion_amp
        if a.nag:  # NAG: negative prompt that still works at CFG 1
            for j, m in enumerate(("5", "6") if a.model == "14b" else ("2",)):
                nid = str(20 + j)  # numeric ids so the graph opens in the ComfyUI canvas with node highlighting
                wf[nid] = {"class_type": "NAGuidance", "inputs": {"model": [m, 0], "nag_scale": a.nag,
                           "nag_alpha": a.nag_alpha, "nag_tau": a.nag_tau}}
                for node in wf.values():
                    for k, v in node["inputs"].items():
                        if k == "model" and v == [m, 0] and node is not wf[nid]:
                            node["inputs"][k] = [nid, 0]
        out_fps = a.fps
        if a.rife:  # RIFE x3 on the GPU (16 -> 48 fps), every 2nd frame kept here -> 24 fps
            wf["18"] = {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": [dec, 0],
                        "clear_cache_after_n_frames": 10, "multiplier": 3, "fast_mode": False, "ensemble": True,
                        "scale_factor": 1.0, "dtype": "float32", "torch_compile": False, "batch_size": 1}}
            wf[save]["inputs"]["images"] = ["18", 0]
            out_fps = a.fps * 3 // 2
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(os.path.splitext(a.out)[0] + "_workflow.json", "w", encoding="utf-8") as f:  # exact graph sent (API format)
            json.dump(wf, f, ensure_ascii=False, indent=1)
        if a.publish_workflow:  # copy to the server so it can be opened there (drag into the ComfyUI tab)
            subprocess.run(["scp", "-q", os.path.splitext(a.out)[0] + "_workflow.json",
                            f"{a.publish_workflow}:C:/ai/workflows/current_job_api.json"], check=False)
        # no client_id: ComfyUI then broadcasts progress to every open browser tab (watch it at <server>/)
        r = comfy_guard.submit(srv, {"prompt": wf, "front": bool(a.front), "extra_data": {"extra_pnginfo": {"workflow_api": wf}}},
                               a.allow_queue)
        if r.status_code != 200:
            sys.exit(f"queue failed {r.status_code}: {r.text[:2000]}")
        pid = r.json()["prompt_id"]
        ledger.record(a.out, "gen_submit", tool="wan_remote", job_id=pid, seed=seed, model=a.model,
                      inputs=[a.image, getattr(a, "end_image", None)],
                      settings={"frames": a.frames, "size": f"{a.width}x{a.height}", "steps": steps})
        print(f"queued {pid} model={a.model} {a.width}x{a.height} frames={a.frames} steps={steps} seed={seed}", flush=True)
    t0 = time.time()
    while True:
        time.sleep(5)
        h = requests.get(f"{srv}/history/{pid}", timeout=30).json()
        if pid in h:
            st = h[pid]["status"]
            if st.get("status_str") != "success":
                ledger.record(a.out, "gen_fail", tool="wan_remote", job_id=pid, wall_s=round(time.time() - t0, 1),
                              exec_s=ledger.exec_seconds(h[pid]))
                sys.exit(f"failed: {json.dumps(st.get('messages'), ensure_ascii=False)[:3000]}")
            outs = h[pid]["outputs"]
            server_exec_s = ledger.exec_seconds(h[pid])  # gen_done is recorded once the output file exists
            break
        if time.time() - t0 > a.timeout:
            ledger.record(a.out, "gen_timeout", tool="wan_remote", job_id=pid, wall_s=round(time.time() - t0, 1))
            sys.exit("timeout")
    secs = time.time() - t0  # server wait; wall_s below is measured when the output is finished
    try:
        imgs = [i for o in outs.values() for i in o.get("images", [])]
        tmp = tempfile.mkdtemp(prefix="wan_")
        imgs = sorted(imgs, key=lambda x: x["filename"])
        if a.rife:  # frames are on a 48 fps grid (16 x3); 24 fps output at a.speed x -> keep every 2*speed-th frame
            step = 2 * a.speed
            if abs(step - round(step)) > 1e-6:
                sys.exit("--speed with --rife must make 2*speed an integer (1, 1.5, 2, 2.5, 3)")
            imgs = imgs[::int(round(step))]
        for k, i in enumerate(imgs):
            b = requests.get(f"{srv}/view", params={"filename": i["filename"], "subfolder": i["subfolder"],
                             "type": i["type"]}, timeout=120).content
            open(os.path.join(tmp, f"f{k:05d}.png"), "wb").write(b)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        enc = ["-c:v", "libx264", "-crf", "12", "-preset", "slow", "-pix_fmt", "yuv420p"]
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(out_fps), "-i", os.path.join(tmp, "f%05d.png"),
                        *enc, a.out], check=True)
        graded = None
        if a.lut:
            for f in sorted(os.listdir(tmp)):
                if f.startswith("f"):
                    log_lut.to_log(os.path.join(tmp, f), os.path.join(tmp, "l" + f[1:]))
            c = os.path.abspath(a.lut).replace("\\", "/").replace(":", "\\:")
            graded = os.path.splitext(a.out)[0] + "_graded.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(out_fps), "-i", os.path.join(tmp, "l%05d.png"),
                            "-vf", f"lut3d=file='{c}':interp=tetrahedral", *enc, graded], check=True)
        shutil.rmtree(tmp, ignore_errors=True)
        if a.interp and a.interp != out_fps:  # cinema rate: motion-compensated interpolation of the finished clips
            for src in [a.out] + ([graded] if graded else []):
                dst = os.path.splitext(src)[0] + f"_{a.interp}fps.mp4"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf",
                                f"minterpolate=fps={a.interp}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                                "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", dst], check=True)
    except Exception as e:  # noqa: BLE001 - download/encode failed: keep the known server time
        ledger.record(a.out, "gen_fetch_fail", tool="wan_remote", job_id=pid, wall_s=round(time.time() - t0, 1),
                      exec_s=server_exec_s, reason=f"{type(e).__name__}: {e}"[:300])
        sys.exit(f"post-processing failed ({type(e).__name__}: {e}); re-export with --fetch {pid}")
    ledger.record(a.out, "gen_done", tool="wan_remote", job_id=pid, wall_s=round(time.time() - t0, 1), exec_s=server_exec_s)
    print(json.dumps({"prompt_id": pid, "seed": seed, "seconds": round(secs, 1), "frames": len(imgs),
                      "out": a.out, "graded": graded, "fps": out_fps, "model": a.model, "steps": steps,
                      "motion_amp": a.motion_amp, "speed": a.speed, "nag": a.nag, "rife": a.rife}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    p.add_argument("--image", required=True)
    p.add_argument("--nag-alpha", type=float, default=0.25)
    p.add_argument("--nag-tau", type=float, default=2.5)
    p.add_argument("--front", action="store_true", help="put this job at the front of the server queue")
    p.add_argument("--fetch", help="prompt_id of a job already on the server: wait, download and grade it only")
    p.add_argument("--end-image", help="optional last frame (first-last-frame transition, 14b only)")
    p.add_argument("--vace-control", help="VACE control video: keys at their frames, grey elsewhere (Wan2.2-VACE-Fun-A14B)")
    p.add_argument("--vace-mask", help="VACE mask video, same length: black = keep the control frame, white = generate")
    p.add_argument("--vace-strength", type=float, default=1.0)
    p.add_argument("--control-video", help="pose/canny control video (same size and frame count): Wan2.2-Fun-A14B-Control, --image is the reference")
    p.add_argument("--prompt")
    p.add_argument("--prompt-file")
    p.add_argument("--negative", default=NEG)
    p.add_argument("--negative-extra", default="", help="appended to the negative prompt (keeps the default list)")
    p.add_argument("--out", required=True)
    p.add_argument("--lut")
    p.add_argument("--model", choices=["14b", "5b"], default="14b")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--frames", type=int, default=81, help="4n+1; 81 = 5 s at 16 fps")
    p.add_argument("--fps", type=int, default=16)
    p.add_argument("--interp", type=int, default=24, help="also write <out>_<N>fps.mp4 (0 = off)")
    p.add_argument("--rife", action="store_true", help="RIFE x3 on the server, kept at 24 fps (skips ffmpeg interp)")
    p.add_argument("--motion-amp", type=float, default=0, help="PainterI2V motion amplitude, e.g. 1.15 (0 = off)")
    p.add_argument("--nag", type=float, default=0, help="NAG scale for the negative prompt at CFG 1, e.g. 5 (0 = off)")
    p.add_argument("--publish-workflow", default="gpu-host", help="ssh host to copy the job graph to (\"\" = off)")
    p.add_argument("--speed", type=float, default=1.0, help="playback speed baked into the output (with --rife: 1, 1.5, 2, ...)")
    p.add_argument("--lora", choices=sorted(LORAS), default="motionfix", help="4-step LoRA pair for 14b")
    p.add_argument("--steps", type=int)
    p.add_argument("--shift", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--timeout", type=int, default=6 * 3600, help="seconds to wait, queue time included")
    p.add_argument("--allow-queue", action="store_true", help="queue even if the GPU is busy (only when the user asked)")
    run(p.parse_args())


if __name__ == "__main__":
    main()
