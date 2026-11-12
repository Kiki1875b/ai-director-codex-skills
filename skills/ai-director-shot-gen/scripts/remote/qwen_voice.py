"""Qwen3-TTS on the GPU server: design character voices from text, then speak lines in a chosen voice.

  design: python qwen_voice.py design job.json   # job: {"out": dir, "voices": [{"id", "instruct", "ref_text", "n"}]}
  clone:  python qwen_voice.py clone  job.json   # job: {"out": dir, "ref_audio", "ref_text", "takes",
                                                 #       "lines": [{"id", "text"}]}
Runs offline (HF_HUB_OFFLINE=1) from local model folders under C:\\ai\\qwen3tts\\models.
"""
import json, os, sys
os.environ.setdefault("HF_HUB_OFFLINE", "1")
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

MODELS = r"C:\ai\qwen3tts\models"


def load(name):
    return Qwen3TTSModel.from_pretrained(os.path.join(MODELS, name), device_map="cuda:0",
                                         dtype=torch.bfloat16, attn_implementation="sdpa")


def design(job):
    tts = load("Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    for v in job["voices"]:
        for k in range(v.get("n", 4)):
            torch.manual_seed(1000 + k)
            wavs, sr = tts.generate_voice_design(text=v["ref_text"], language="Korean",
                                                 instruct=v["instruct"], max_new_tokens=2048)
            p = os.path.join(job["out"], f"{v['id']}_cand{k + 1}.wav")
            sf.write(p, wavs[0], sr)
            print("wrote", p, round(len(wavs[0]) / sr, 2), "s", flush=True)


def design_lines(job):
    """Each line spoken by the VoiceDesign model: the character's voice description + a per-line acting direction
    written from the shot. Timbre can drift between lines; a later voice-conversion pass can unify it."""
    tts = load("Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    for ln in job["lines"]:
        instruct = job["voice"] + " " + ln["direction"]
        for k in range(job.get("takes", 4)):
            torch.manual_seed(job.get("seed0", 1002) + k)
            wavs, sr = tts.generate_voice_design(text=ln["text"], language="Korean", instruct=instruct,
                                                 max_new_tokens=2048)
            p = os.path.join(job["out"], f"{ln['id']}_d{k + 1}.wav")
            sf.write(p, wavs[0], sr)
            print("wrote", p, round(len(wavs[0]) / sr, 2), "s", flush=True)


def custom(job):
    """Built-in speaker (e.g. Sohee, native Korean female) with a style instruction."""
    tts = load("Qwen3-TTS-12Hz-1.7B-CustomVoice")
    for v in job["voices"]:
        for k in range(v.get("n", 3)):
            torch.manual_seed(3000 + k)
            wavs, sr = tts.generate_custom_voice(text=v["ref_text"], language="Korean", speaker=v["speaker"],
                                                 instruct=v.get("instruct"), max_new_tokens=2048)
            p = os.path.join(job["out"], f"{v['id']}_cand{k + 1}.wav")
            sf.write(p, wavs[0], sr)
            print("wrote", p, round(len(wavs[0]) / sr, 2), "s", flush=True)


def clone(job):
    """Optional: "refs": [{"tag", "wav"}] (several reference takes of the same voice, e.g. one with a flattened pitch
    range), "gen": sampling overrides (temperature, top_p, subtalker_temperature, ...; defaults 0.9/1.0),
    "seed0". Output: <line id>[_<tag>]_t<k>.wav."""
    tts = load(job.get("model", "Qwen3-TTS-12Hz-1.7B-Base"))
    refs = job.get("refs") or [{"tag": "", "wav": job["ref_audio"]}]
    gen = job.get("gen", {})
    for r in refs:
        prompt = tts.create_voice_clone_prompt(ref_audio=r["wav"], ref_text=job["ref_text"])
        tag = f"_{r['tag']}" if r["tag"] else ""
        for ln in job["lines"]:
            for k in range(job.get("takes", 3)):
                torch.manual_seed(job.get("seed0", 2000) + k)
                wavs, sr = tts.generate_voice_clone(text=ln["text"], language="Korean",
                                                    voice_clone_prompt=prompt, max_new_tokens=2048, **gen)
                p = os.path.join(job["out"], f"{ln['id']}{tag}_t{k + 1}.wav")
                sf.write(p, wavs[0], sr)
                print("wrote", p, round(len(wavs[0]) / sr, 2), "s", flush=True)


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    job = json.load(open(path, encoding="utf8"))
    os.makedirs(job["out"], exist_ok=True)
    {"design": design, "design_lines": design_lines, "custom": custom, "clone": clone}[mode](job)
    print("== done", flush=True)
