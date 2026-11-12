"""Instrumental film cues with ACE-Step 1.5 (MIT) on the GPU server, offline, no web server.

  C:\\ai\\acestep\\.venv\\Scripts\\python.exe ace_bgm.py job.json
job: {"out": dir, "bpm": 60, "key": "D minor", "seeds": [11, 22, 33], "lm": "acestep-5Hz-lm-1.7B",
      "common": "film score, no drums, no vocals",
      "cues": [{"id": "M1", "dur": 18, "caption": "..."}],
      "vae_decoder_dir": optional alt decoder (e.g. C:/ai/acestep/checkpoints/vae_scrag), "only": optional [[id, seed], ...]}
Writes <out>/<id>_s<seed>.wav. Turbo DiT (8 steps, shift 3); LM "thinking" plans the music codes from the caption.
"""
import json, os, sys, time, shutil
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
ROOT = r"C:\ai\acestep"
sys.path.insert(0, ROOT)
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music


def main(job):
    os.makedirs(job["out"], exist_ok=True)
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(project_root=ROOT, config_path="acestep-v15-turbo", device="cuda",
                                     offload_to_cpu=job.get("offload", True))
    print("dit:", ok, msg, flush=True)
    if not ok: sys.exit(1)
    if job.get("vae_decoder_dir"):  # e.g. checkpoints\vae_scrag (ScragVAE, MIT): same config, retrained decoder only
        import torch
        from diffusers import AutoencoderOobleck
        alt = AutoencoderOobleck.from_pretrained(job["vae_decoder_dir"], torch_dtype=torch.float32)
        ref = next(dit.vae.decoder.parameters())
        res = dit.vae.decoder.load_state_dict({k: v.to(ref.dtype) for k, v in alt.decoder.state_dict().items()}, strict=True)
        print("decoder swapped from", job["vae_decoder_dir"], "dtype", ref.dtype, res, flush=True)
        del alt
    llm = LLMHandler()
    msg, ok = llm.initialize(checkpoint_dir=os.path.join(ROOT, "checkpoints"), lm_model_path=job.get("lm", "acestep-5Hz-lm-1.7B"),
                             backend="pt", device="cuda", offload_to_cpu=job.get("offload", True))
    print("lm:", ok, msg, flush=True)
    if not ok: sys.exit(1)
    tmp = os.path.join(job["out"], "_tmp")
    for c in job["cues"]:
        for seed in job.get("seeds", [11, 22, 33]):
            if job.get("only") and [c["id"], seed] not in job["only"]:
                continue
            t = time.time()
            p = GenerationParams(task_type="text2music", thinking=True, instrumental=True, lyrics="[Instrumental]",
                                 caption=f"{c['caption']}, {job.get('common', '')}".strip(", "),
                                 bpm=c.get("bpm", job.get("bpm")), keyscale=c.get("key", job.get("key", "")),
                                 timesignature=str(c.get("ts", job.get("ts", "4"))), duration=c["dur"],
                                 inference_steps=8, shift=3.0, seed=seed)
            r = generate_music(dit, llm, params=p, config=GenerationConfig(batch_size=1, audio_format="wav"), save_dir=tmp)
            if not r.success:
                print("FAIL", c["id"], seed, r.status_message, flush=True); continue
            dst = os.path.join(job["out"], f"{c['id']}_s{seed}.wav")
            shutil.move(r.audios[0]["path"], dst)
            print("wrote", dst, f"{time.time() - t:.1f}s", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("== done", flush=True)


if __name__ == "__main__":
    main(json.load(open(sys.argv[1], encoding="utf8")))
