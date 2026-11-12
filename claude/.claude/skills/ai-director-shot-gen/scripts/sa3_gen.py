"""Generate SFX candidates with Stable Audio 3 on the remote ComfyUI (one job at a time).
defaults = official ComfyUI template for the post-trained checkpoints (8 steps, cfg 1, lcm, simple); base checkpoints use SA3_STEPS=50 SA3_CFG=7.
usage: python sa3_gen.py <out_dir> <ckpt> <seconds> <seed> <name> "<prompt>" ["<negative>"]
Server: env COMFY_URL (default http://127.0.0.1:8188, Tailscale only). Server-side output subfolder: env SA3_PREFIX
(default sa3_sfx). Optional env SA3_STEPS, SA3_CFG, SA3_DTYPE, SA3_VAE_DTYPE."""
import json, sys, time, urllib.request, urllib.parse, os
SRV = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
if len(sys.argv) not in (7, 8): sys.exit(__doc__)
PREFIX = os.environ.get("SA3_PREFIX", "sa3_sfx")
out, ckpt, secs, seed, name, pos = sys.argv[1:7]; neg = sys.argv[7] if len(sys.argv) > 7 else ""
g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
     "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5gemma_b_b_ul2.safetensors", "type": "stable_audio", "device": "default"}},
     "3": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["2", 0]}},
     "4": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["2", 0]}},
     "5": {"class_type": "EmptyLatentAudio", "inputs": {"seconds": float(secs), "batch_size": 1}},
     "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0],
            "seed": int(seed), "steps": int(os.environ.get("SA3_STEPS", 8)), "cfg": float(os.environ.get("SA3_CFG", 1.0)), "sampler_name": "lcm", "scheduler": "simple", "denoise": 1.0}},
     "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
     "8": {"class_type": "SaveAudio", "inputs": {"audio": ["7", 0], "filename_prefix": f"{PREFIX}/{name}"}}}
dt = os.environ.get("SA3_DTYPE")  # fp32 / bf16 / fp16: compute dtype of the diffusion model (ComfyUI default casts SA3 to fp16)
if dt:
    g["9"] = {"class_type": "ModelComputeDtype", "inputs": {"model": ["1", 0], "dtype": dt}}
    g["6"]["inputs"]["model"] = ["9", 0]
vdt = os.environ.get("SA3_VAE_DTYPE")  # fp32 / bf16: compute dtype of the audio VAE decoder (ComfyUI loads SA3AudioVAE as bf16)
if vdt:
    g["10"] = {"class_type": "VAEComputeDtype", "inputs": {"vae": ["1", 2], "dtype": vdt}}
    g["7"]["inputs"]["vae"] = ["10", 0]
q = json.loads(urllib.request.urlopen(SRV + "/queue").read())
if q["queue_running"] or q["queue_pending"]: sys.exit("GPU busy, not submitting")
pid = json.loads(urllib.request.urlopen(urllib.request.Request(SRV + "/prompt", json.dumps({"prompt": g}).encode(), {"Content-Type": "application/json"})).read())["prompt_id"]
t0 = time.time()
while True:
    h = json.loads(urllib.request.urlopen(f"{SRV}/history/{pid}").read())
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error": sys.exit("error: " + json.dumps(st)[:400])
        outs = h[pid]["outputs"]
        if outs: break
    time.sleep(2)
f = next(iter(outs["8"]["audio"]))
data = urllib.request.urlopen(f"{SRV}/view?" + urllib.parse.urlencode({"filename": f["filename"], "subfolder": f["subfolder"], "type": f["type"]})).read()
os.makedirs(out, exist_ok=True); p = os.path.join(out, name + os.path.splitext(f["filename"])[1])
open(p, "wb").write(data); print(f"{name}: {p} ({time.time()-t0:.0f}s)")
