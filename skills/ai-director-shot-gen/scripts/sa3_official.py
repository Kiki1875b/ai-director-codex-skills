"""Generate with the official Stable Audio 3 HF Space (reference implementation) for comparison.
usage: python sa3_official.py <variant medium|small-sfx> <seconds> <seed> <out_file> "<prompt>" """
import json, sys, urllib.request
B = "https://stabilityai-stable-audio-3.hf.space/gradio_api"
if len(sys.argv) != 6: sys.exit(__doc__)
v, secs, seed, out, prompt = sys.argv[1:6]
req = urllib.request.Request(f"{B}/call/infer", json.dumps({"data": [v, prompt, float(secs), 8, 1.0, "pingpong", int(seed)]}).encode(), {"Content-Type": "application/json"})
eid = json.load(urllib.request.urlopen(req, timeout=60))["event_id"]
data = None
for line in urllib.request.urlopen(f"{B}/call/infer/{eid}", timeout=900):
    line = line.decode().strip()
    if line.startswith("event: error"): sys.exit("space error")
    if line.startswith("data:") and line[5:].strip() not in ("null", ""):
        data = json.loads(line[5:])
if not data: sys.exit("no data")
f = data[0]; url = f.get("url") or f"{B}/file={f['path']}"
open(out, "wb").write(urllib.request.urlopen(url, timeout=120).read()); print(out, f.get("orig_name"))
