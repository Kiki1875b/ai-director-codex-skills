"""Decoder A/B for ACE-Step 1.5 on the GPU server: generate once, decode the SAME latents with the stock VAE decoder (A)
and an alternative decoder such as ScragVAE (B). Generation with the same seed is not reproducible (LM planning), so
comparing two separate runs would compare two different pieces.

  C:\ai\acestep\.venv\Scripts\python.exe ace_decoder_ab.py job.json
job: same as ace_bgm.py plus "vae_decoder_dir" (required) and optional "only": [[id, seed], ...],
     "dit_config" (e.g. acestep-v15-xl-turbo), "quantization" (int8_weight_only|fp8_weight_only|w8a8_dynamic), "offload_dit", "vram_fraction".
Writes <out>/<id>_s<seed>_A_stock.wav, _B_alt.wav (48 kHz float, peak-limited to 1.0 like the pipeline) and _latents.npy.
"""
import json, os, sys, wave
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
ROOT = r"C:\ai\acestep"
sys.path.insert(0, ROOT)
import numpy as np, torch
from diffusers import AutoencoderOobleck
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music


def save_wav(path, x, sr):
    x = np.clip(x.T, -1, 1)  # [T, C]
    with wave.open(path, "wb") as w:
        w.setnchannels(x.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def main(job):
    os.makedirs(job["out"], exist_ok=True)
    frac = float(job.get("vram_fraction", 0))  # cap this process's VRAM so the shared 12 GB card does not OOM other apps
    if frac > 0:
        torch.cuda.set_per_process_memory_fraction(frac, 0)
        print(f"VRAM cap {frac:.2f} of {torch.cuda.get_device_properties(0).total_memory / 2**30:.1f}GB", flush=True)
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ROOT, config_path=job.get("dit_config", "acestep-v15-turbo"), device="cuda",
                                     offload_to_cpu=job.get("offload", True), offload_dit_to_cpu=job.get("offload_dit", False),
                                     quantization=job.get("quantization"))
    print("dit:", ok, msg, flush=True)
    llm = LLMHandler()
    msg, ok2 = llm.initialize(checkpoint_dir=os.path.join(ROOT, "checkpoints"), lm_model_path=job.get("lm", "acestep-5Hz-lm-1.7B"),
                              backend="pt", device="cuda", offload_to_cpu=job.get("offload", True))
    print("lm:", ok2, msg, flush=True)
    if not (ok and ok2): sys.exit(1)
    stock = {k: v.detach().cpu().clone() for k, v in dit.vae.decoder.state_dict().items()}
    alt = AutoencoderOobleck.from_pretrained(job["vae_decoder_dir"], torch_dtype=torch.float32).decoder.state_dict()
    sr = int(getattr(dit, "sample_rate", 48000) or 48000)
    captured = {}
    orig_tiled = dit.tiled_decode
    def tiled(latents, *a, **k):
        captured["z"] = latents.detach().cpu().clone()
        return orig_tiled(latents, *a, **k)
    dit.tiled_decode = tiled
    def decode(z, sd):
        ref = next(dit.vae.decoder.parameters())
        dit.vae.decoder.load_state_dict({k: v.to(ref.dtype) for k, v in sd.items()}, strict=True)
        dev = next(dit.vae.parameters()).device
        with torch.no_grad():
            w = orig_tiled(z.to(dev, dtype=next(dit.vae.parameters()).dtype)).float()
        peak = w.abs().amax(dim=[1, 2], keepdim=True)
        w = w / peak.clamp(min=1.0)
        return w[0].cpu().numpy()
    tmp = os.path.join(job["out"], "_tmp")
    for c in job["cues"]:
        for seed in job.get("seeds", [11, 22, 33]):
            if job.get("only") and [c["id"], seed] not in job["only"]:
                continue
            captured.clear()
            p = GenerationParams(task_type="text2music", thinking=True, instrumental=True, lyrics="[Instrumental]",
                                 caption=f"{c['caption']}, {job.get('common', '')}".strip(", "),
                                 bpm=c.get("bpm", job.get("bpm")), keyscale=c.get("key", job.get("key", "")),
                                 timesignature=str(c.get("ts", job.get("ts", "4"))), duration=c["dur"],
                                 inference_steps=8, shift=3.0, seed=seed)
            r = generate_music(dit, llm, params=p, config=GenerationConfig(batch_size=1, audio_format="wav"), save_dir=tmp)
            if not r.success or "z" not in captured:
                print("FAIL", c["id"], seed, r.status_message, "captured" in captured, flush=True); continue
            z = captured["z"]; base = os.path.join(job["out"], f"{c['id']}_s{seed}")
            np.save(base + "_latents.npy", z.float().numpy())
            save_wav(base + "_A_stock.wav", decode(z, stock), sr)
            save_wav(base + "_B_alt.wav", decode(z, alt), sr)
            dit.vae.decoder.load_state_dict({k: v.to(next(dit.vae.decoder.parameters()).dtype) for k, v in stock.items()})
            print("wrote", base, "A/B", tuple(z.shape), "sr", sr, flush=True)
    print("== done", flush=True)


if __name__ == "__main__":
    main(json.load(open(sys.argv[1], encoding="utf8")))
