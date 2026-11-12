"""Stable Audio 3 exactly as the official ComfyUI template (audio_stable_audio_3_medium.json):
short idea -> Qwen3.5-2B reprompt with the template's category system prompt -> T5Gemma -> SA3 (8 steps, cfg 1, lcm, simple).
The system prompts are read from the template JSON copied from the server.
usage: python sa3_template.py <out_dir> <ckpt> <seconds> <seed> <name> <category SFX|One-shot> "<short idea>"
writes <name>.flac and <name>.txt (the rewritten prompt).
Server: env COMFY_URL (default http://127.0.0.1:8188, Tailscale only). Server-side output subfolder: env SA3_PREFIX
(default sa3_sfx). Optional env SA3_CFG, SA3_STEPS, SA3_NEG."""
import json, os, sys, time, urllib.parse, urllib.request

SRV = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa3_template_medium.json")
if len(sys.argv) != 8: sys.exit(__doc__)
out, ckpt, secs, seed, name, cat, idea = sys.argv[1:8]
PREFIX = os.environ.get("SA3_PREFIX", "sa3_sfx")
CFG = float(os.environ.get("SA3_CFG", 1.0))  # template value 1.0 (base checkpoints: 7)
STEPS = int(os.environ.get("SA3_STEPS", 8))  # template value 8 (base checkpoints: 50, audio_stable_audio_3_medium_base.json)
NEG = os.environ.get("SA3_NEG", "")  # template value empty

w = json.load(open(TEMPLATE, encoding="utf-8"))
nodes = {n["id"]: n for sg in w["definitions"]["subgraphs"] for n in sg["nodes"]}
system = json.loads(nodes[49]["widgets_values"][0])[cat]
wrapper = nodes[38]["widgets_values"][0]  # "SYSTEM_PROMPTS\n\nInput: USER_INPUT\nTarget audio length: AUDIO_LENGTH seconds.\nOutput:"
length = str(int(round(float(secs))))
qprompt = wrapper.replace("SYSTEM_PROMPTS", system).replace("USER_INPUT", idea).replace("AUDIO_LENGTH", length)
tg = nodes[28]["widgets_values"]  # ["", 256, "on", 0.7, 64, 0.95, 0.05, 1.05, 0, 0, false, true]

g = {
    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "t5gemma_b_b_ul2.safetensors", "type": "stable_audio", "device": "default"}},
    "20": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3.5_2b_bf16.safetensors", "type": "stable_diffusion", "device": "default"}},
    "21": {"class_type": "TextGenerate", "inputs": {"clip": ["20", 0], "prompt": qprompt, "max_length": tg[1], "sampling_mode": "on",
            "sampling_mode.temperature": tg[3], "sampling_mode.top_k": tg[4], "sampling_mode.top_p": tg[5], "sampling_mode.min_p": tg[6],
            "sampling_mode.repetition_penalty": tg[7], "sampling_mode.seed": int(seed), "thinking": False, "use_default_template": True}},
    "22": {"class_type": "PreviewAny", "inputs": {"source": ["21", 0]}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": ["21", 0], "clip": ["2", 0]}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["2", 0]}},  # template: empty; ignored when cfg == 1
    "5": {"class_type": "EmptyLatentAudio", "inputs": {"seconds": float(secs), "batch_size": 1}},
    "6": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["3", 0], "negative": ["4", 0], "latent_image": ["5", 0],
           "seed": int(seed), "steps": STEPS, "cfg": CFG, "sampler_name": "lcm", "scheduler": "simple", "denoise": 1.0}},
    "7": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
    "8": {"class_type": "SaveAudio", "inputs": {"audio": ["7", 0], "filename_prefix": f"{PREFIX}/{name}"}},
}
q = json.loads(urllib.request.urlopen(SRV + "/queue").read())
if q["queue_running"] or q["queue_pending"]:
    sys.exit("GPU busy, not submitting")
pid = json.loads(urllib.request.urlopen(urllib.request.Request(SRV + "/prompt", json.dumps({"prompt": g}).encode(), {"Content-Type": "application/json"})).read())["prompt_id"]
t0 = time.time()
while True:
    h = json.loads(urllib.request.urlopen(f"{SRV}/history/{pid}").read())
    if pid in h:
        st = h[pid].get("status", {})
        if st.get("status_str") == "error":
            sys.exit("error: " + json.dumps([m for m in st["messages"] if m[0] == "execution_error"])[:800])
        if st.get("completed"):
            break
    time.sleep(2)
outs = h[pid]["outputs"]
f = outs["8"]["audio"][0]
data = urllib.request.urlopen(f"{SRV}/view?" + urllib.parse.urlencode({"filename": f["filename"], "subfolder": f["subfolder"], "type": f["type"]})).read()
os.makedirs(out, exist_ok=True)
open(os.path.join(out, name + os.path.splitext(f["filename"])[1]), "wb").write(data)
text = outs.get("22", {}).get("text", [""])
text = text[0] if isinstance(text, list) else text
open(os.path.join(out, name + ".txt"), "w", encoding="utf-8").write(f"idea: {idea}\ncategory: {cat}\nckpt: {ckpt}\nseed: {seed}\nsteps: {STEPS}\ncfg: {CFG}\nnegative: {NEG}\nrewritten: {text}\n")
print(f"{name} ({time.time()-t0:.0f}s): {text[:160]}")
