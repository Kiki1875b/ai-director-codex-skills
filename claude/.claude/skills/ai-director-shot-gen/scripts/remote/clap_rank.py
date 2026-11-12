"""Rank sound-effect files (and the best window inside each) against text descriptions with LAION CLAP
(laion/larger_clap_general, Apache-2.0). Inference only (the Sonniss licence forbids training on the sounds).

  C:\\ai\\audiojudge\\.venv\\Scripts\\python.exe clap_rank.py job.json
job: {"dir": "C:\\ai\\audiojudge\\sfx", "out": "rank.json", "win": 2.0, "hop": 0.5, "top": 8,
      "needs": {"cup_down": ["a ceramic cup placed on a steel counter", ...], ...},
      "avoid": ["music", "speech", "rain"]}
Every .wav under dir is cut into win-second windows (hop apart, silent windows skipped). Score of a window for a need =
mean cosine similarity to the need's sentences minus 0.5 x the max similarity to the avoid sentences.
Output per need: top windows (file, start s, score), at most 2 windows per file.
"""
import glob, json, os, sys
import numpy as np, soundfile as sf, torch
from scipy.signal import resample_poly
from transformers import ClapModel, ClapProcessor

M = r"C:\ai\audiojudge\models\larger_clap_general"
SR = 48000


def windows(path, win, hop):
    x, sr = sf.read(path, always_2d=True); x = x.mean(1)
    if sr != SR: x = resample_poly(x, SR, sr)
    n, h = int(win * SR), int(hop * SR)
    if len(x) < n: x = np.pad(x, (0, n - len(x)))
    peak = np.abs(x).max() + 1e-9
    out = []
    for s in range(0, len(x) - n + 1, h):
        w = x[s:s + n]
        if np.sqrt((w ** 2).mean()) < peak * 0.02: continue          # near-silent
        out.append((s / SR, w / peak))
    return out


def main(job):
    dev = "cuda"
    model = ClapModel.from_pretrained(M).to(dev).eval(); proc = ClapProcessor.from_pretrained(M)
    with torch.no_grad():
        def temb(t):
            e = model.get_text_features(**proc(text=t, return_tensors="pt", padding=True).to(dev))
            return torch.nn.functional.normalize(e, dim=-1)
        needs = {k: temb(v) for k, v in job["needs"].items()}
        avoid = temb(job.get("avoid", ["music"]))
        files = sorted(glob.glob(os.path.join(job["dir"], "**", "*.wav"), recursive=True))
        rows = []
        for i, f in enumerate(files):
            try: W = windows(f, job.get("win", 2.0), job.get("hop", 0.5))
            except Exception as e: print("skip", f, e); continue
            for b in range(0, len(W), 32):
                chunk = W[b:b + 32]
                a = proc(audios=[w for _, w in chunk], sampling_rate=SR, return_tensors="pt").to(dev)
                e = torch.nn.functional.normalize(model.get_audio_features(**a), dim=-1)
                pen = (e @ avoid.T).max(1).values
                sc = {k: ((e @ v.T).mean(1) - 0.5 * pen).cpu().numpy() for k, v in needs.items()}
                for j, (t, _) in enumerate(chunk):
                    rows.append((f, t, {k: float(s[j]) for k, s in sc.items()}))
            if i % 25 == 0: print(f"{i}/{len(files)} files, {len(rows)} windows", flush=True)
    res = {}
    for k in needs:
        best, per = [], {}
        for f, t, s in sorted(rows, key=lambda r: -r[2][k]):
            if per.get(f, 0) >= 2: continue
            per[f] = per.get(f, 0) + 1
            best.append({"file": os.path.relpath(f, job["dir"]), "start": round(t, 2), "score": round(s[k], 4)})
            if len(best) >= job.get("top", 8): break
        res[k] = best
        print(k, [(os.path.basename(b["file"])[:40], b["start"], b["score"]) for b in best[:4]], flush=True)
    json.dump(res, open(job["out"], "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("== done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(json.load(open(sys.argv[1], encoding="utf8")))
