"""Runs ON the GPU server inside C:\\ai\\moss_sfx\\.venv. Generates MOSS-SoundEffect v2.0 candidates from a JSON job list.
job list: [{"name": "...", "prompt": "...", "seconds": 3, "seed": 1}, ...]
usage: python moss_gen_server.py jobs.json out_dir [steps] [cfg] [shift]
Defaults are the model card's recommended settings: 100 steps, cfg 4.0, sigma shift 5.0."""
import inspect, json, os, sys, time
if len(sys.argv) < 3: sys.exit(__doc__)
import torch
from moss_soundeffect_v2 import MossSoundEffectPipeline

jobs = json.load(open(sys.argv[1], encoding="utf-8"))
out = sys.argv[2]
steps = int(sys.argv[3]) if len(sys.argv) > 3 else 100
cfg = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0
shift = float(sys.argv[5]) if len(sys.argv) > 5 else 5.0
os.makedirs(out, exist_ok=True)

frac = float(os.environ.get("MOSS_VRAM_FRACTION", "0"))  # cap this process's VRAM (0 = no cap)
if frac > 0:
    torch.cuda.set_per_process_memory_fraction(frac, 0)
    print(f"VRAM cap: {frac:.2f} of {torch.cuda.get_device_properties(0).total_memory / 2**30:.1f}GB", flush=True)
pipe = MossSoundEffectPipeline.from_pretrained("OpenMOSS-Team/MOSS-SoundEffect-v2.0", torch_dtype=torch.bfloat16, device="cuda")
params = inspect.signature(pipe.__call__).parameters
print("call params:", list(params))
for j in jobs:
    kw = {"prompt": j["prompt"], "seconds": j["seconds"], "num_inference_steps": steps, "cfg_scale": cfg}
    if "sigma_shift" in params:
        kw["sigma_shift"] = shift
    if "seed" in params:
        kw["seed"] = j["seed"]
    elif "generator" in params:
        kw["generator"] = torch.Generator("cuda").manual_seed(j["seed"])
    else:
        torch.manual_seed(j["seed"])
    t0 = time.time()
    audio = pipe(**kw)
    path = os.path.join(out, j["name"] + ".wav")
    pipe.save_audio(audio, path)
    print(f"{j['name']}: {time.time() - t0:.1f}s peak_vram={torch.cuda.max_memory_allocated() / 2**30:.1f}GB", flush=True)
