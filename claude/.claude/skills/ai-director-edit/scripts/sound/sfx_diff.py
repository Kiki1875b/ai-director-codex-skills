"""Compare two decodes of the same seed: correlation and residual level over time.
usage: python sfx_diff.py base.flac test.flac"""
import subprocess, sys, numpy as np
if len(sys.argv) != 3: sys.exit(__doc__)
def load(p): return np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",p,"-f","f32le","-ac","1","-ar","44100","-"],capture_output=True).stdout,np.float32)
x, y = load(sys.argv[1]), load(sys.argv[2]); n0 = min(len(x), len(y)); x, y = x[:n0], y[:n0]; d = y - x
db = lambda v: 20*np.log10(v + 1e-9); w = 2205; n = n0 // w
sig = np.sqrt((x[:n*w].reshape(n, w)**2).mean(1)); res = np.sqrt((d[:n*w].reshape(n, w)**2).mean(1))
print(f"{sys.argv[2].split('/')[-1]}: corr {np.corrcoef(x, y)[0,1]:.4f}  residual vs signal {db(np.sqrt((d**2).mean())) - db(np.sqrt((x**2).mean())):.1f} dB")
for i in range(0, n, 8): print(f"  t={i*0.05:4.2f}s signal {db(sig[i]):6.1f}  diff {db(res[i]):6.1f}  (diff-signal {db(res[i]) - db(sig[i]):6.1f} dB)")
