"""Objective checks for SFX candidates: length, sample rate, peak, near-clip samples, HF noise floor, clicks.
usage: python sfx_measure.py files..."""
import subprocess, sys, json, numpy as np
if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"): sys.exit(__doc__)
for p in sys.argv[1:]:
    sr = int(json.loads(subprocess.run(["ffprobe","-v","error","-show_streams","-of","json",p],capture_output=True,text=True).stdout)["streams"][0]["sample_rate"])
    x = np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",p,"-f","f32le","-ac","1","-"],capture_output=True).stdout,np.float32)
    if len(x) == 0: print(p, "EMPTY"); continue
    pk = np.abs(x).max(); clip = int((np.abs(x) > 0.99).sum())
    w = int(0.02*sr); n = len(x)//w; rms = np.sqrt((x[:n*w].reshape(n,w)**2).mean(1)+1e-12); db = 20*np.log10(rms)
    d = np.abs(np.diff(x)); click = int((d > 0.3).sum())
    tail = db[-5:].mean()
    print(f"{p.split('/')[-1]:24s} sr={sr} len={len(x)/sr:.2f}s peak={20*np.log10(pk+1e-9):6.1f}dB clip={clip} jumps>0.3={click} loudest20ms={db.max():6.1f} floor={np.percentile(db,10):6.1f} end={tail:6.1f}")
