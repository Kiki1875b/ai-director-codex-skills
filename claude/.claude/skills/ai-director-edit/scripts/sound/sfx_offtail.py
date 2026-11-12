"""Turn a struck glass/bowl candidate into an OFF sound: drop the strike, keep the dying tail.
optional flicker: dips at fixed offsets (0, 0.29, 0.62 s, from the mystic-forest S1-6 flicker), gone by ~0.9 s;
edit the offsets in the --flicker block for another shot.
usage: python sfx_offtail.py in.flac out.wav --skip 0.08 [--flicker]"""
import argparse, subprocess, numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--skip", type=float, default=0.08)
ap.add_argument("--flicker", action="store_true"); ap.add_argument("--len", type=float, default=1.4); a = ap.parse_args()
SR = 48000
x = np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",a.inp,"-f","f32le","-ac","2","-ar",str(SR),"-"],capture_output=True).stdout,np.float32).reshape(-1,2).copy()
e = np.abs(x).max(1); onset = int(np.argmax(e > e.max()*0.1))
x = x[onset+int(a.skip*SR): onset+int(a.skip*SR)+int(a.len*SR)]
t = np.arange(len(x))/SR
g = np.minimum(t/0.04, 1.0)                      # 40 ms fade-in, no attack
g *= np.clip(1 - t/a.len, 0, 1)**1.5             # die away
if a.flicker:
    for c, depth in ((0.29, 0.85), (0.62, 0.9)):  # short dips = the cap flickering
        g *= 1 - depth*np.exp(-((t-c)/0.035)**2)
    g *= np.clip((0.95 - t)/0.25, 0, 1)            # dark by ~0.95 s
x *= g[:, None]; x *= 0.5/(np.abs(x).max()+1e-9)
subprocess.run(["ffmpeg","-v","error","-y","-f","f32le","-ac","2","-ar",str(SR),"-i","-","-c:a","pcm_s24le",a.out],input=x.astype(np.float32).tobytes(),check=True)
print(a.out, round(len(x)/SR,2))
