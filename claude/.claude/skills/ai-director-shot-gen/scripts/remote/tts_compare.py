"""Same Korean lines through CosyVoice3 and Chatterbox multilingual, for a side-by-side listening test.

  <cosyvoice venv python> tts_compare.py cosy  job.json
  <chatterbox venv python> tts_compare.py chatter job.json

job.json: {"out": dir, "refs": {"name": {"wav": path, "text": transcript}},
           "lines": [{"id", "text", "ref", "direction"}]}
"""
import json, os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch, torchaudio


def cosy(job):
    sys.path.insert(0, r"C:\ai\cosyvoice\repo"); sys.path.insert(0, r"C:\ai\cosyvoice\repo\third_party\Matcha-TTS")
    from cosyvoice.cli.cosyvoice import AutoModel
    m = AutoModel(model_dir=r"C:\ai\cosyvoice\models\Fun-CosyVoice3-0.5B")
    for ln in job["lines"]:
        ref = job["refs"][ln["ref"]]
        for k in range(2):
            torch.manual_seed(100 + k)
            out = list(m.inference_zero_shot(ln["text"], "You are a helpful assistant.<|endofprompt|>" + ref["text"],
                                             ref["wav"], stream=False))
            w = torch.cat([o["tts_speech"] for o in out], 1)
            p = os.path.join(job["out"], f"cosy_zs_{ln['id']}_{ln['ref']}_{k + 1}.wav")
            torchaudio.save(p, w, m.sample_rate); print("wrote", p, round(w.shape[1] / m.sample_rate, 2), flush=True)
            torch.manual_seed(200 + k)
            out = list(m.inference_instruct2(ln["text"], "You are a helpful assistant. " + ln["direction"] + "<|endofprompt|>",
                                             ref["wav"], stream=False))
            w = torch.cat([o["tts_speech"] for o in out], 1)
            p = os.path.join(job["out"], f"cosy_ins_{ln['id']}_{ln['ref']}_{k + 1}.wav")
            torchaudio.save(p, w, m.sample_rate); print("wrote", p, round(w.shape[1] / m.sample_rate, 2), flush=True)


def chatter(job):
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    m = ChatterboxMultilingualTTS.from_local(r"C:\ai\chatterbox\models", "cuda")
    for ln in job["lines"]:
        ref = job["refs"][ln["ref"]]
        for tag, ex, cfg in (("std", 0.5, 0.5), ("expr", 0.7, 0.3)):
            torch.manual_seed(300)
            w = m.generate(ln["text"], language_id="ko", audio_prompt_path=ref["wav"], exaggeration=ex, cfg_weight=cfg)
            p = os.path.join(job["out"], f"chat_{tag}_{ln['id']}_{ln['ref']}.wav")
            torchaudio.save(p, w.cpu(), m.sr); print("wrote", p, round(w.shape[-1] / m.sr, 2), flush=True)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    job = json.load(open(path, encoding="utf8"))
    os.makedirs(job["out"], exist_ok=True)
    {"cosy": cosy, "chatter": chatter}[mode](job)
    print("== done", flush=True)
