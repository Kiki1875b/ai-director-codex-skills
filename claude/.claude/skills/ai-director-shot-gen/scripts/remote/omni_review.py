"""Ask Qwen2.5-Omni-3B (Apache-2.0) to watch AND listen to short clips of the film and answer review questions.

  C:\\ai\\audiojudge\\.venv\\Scripts\\python.exe omni_review.py job.json
job: {"out": "answers.json", "fps": 2, "max_pixels": 200704,
      "clips": [{"id": "S2-5", "path": "C:\\...\\S2-5.mp4", "context": "what happens in the shot",
                 "questions": ["...", "..."]}]}
Each clip is a few seconds (12 GB GPU). The talker (speech output) is disabled; text answers only, greedy decoding.
The model is a first-pass reviewer: it can miss or misjudge things; the user's ears decide.
"""
import json, sys, time
import torch
from transformers import Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor
from qwen_omni_utils import process_mm_info

M = r"C:\ai\audiojudge\models\Qwen2.5-Omni-3B"
SYSTEM = ("You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory "
          "and visual inputs, as well as generating text and speech.")   # the model card requires this system prompt for audio


def main(job):
    model = Qwen2_5OmniForConditionalGeneration.from_pretrained(M, torch_dtype=torch.bfloat16, device_map="cuda",
                                                                attn_implementation="sdpa")
    model.disable_talker()
    proc = Qwen2_5OmniProcessor.from_pretrained(M)
    res = []
    for c in job["clips"]:
        ans = []
        for q in c["questions"]:
            t = time.time()
            conv = [{"role": "system", "content": [{"type": "text", "text": SYSTEM}]},
                    {"role": "user", "content": [
                        {"type": "video", "video": c["path"], "fps": job.get("fps", 2), "max_pixels": job.get("max_pixels", 200704)},
                        {"type": "text", "text": (f"Context: {c.get('context', '')}\n" if c.get("context") else "") + q}]}]
            text = proc.apply_chat_template(conv, add_generation_prompt=True, tokenize=False)
            audios, images, videos = process_mm_info(conv, use_audio_in_video=True)
            inp = proc(text=text, audio=audios, images=images, videos=videos, return_tensors="pt", padding=True,
                       use_audio_in_video=True).to(model.device).to(model.dtype)
            with torch.no_grad():
                out = model.generate(**inp, use_audio_in_video=True, return_audio=False, max_new_tokens=200, do_sample=False)
            a = proc.batch_decode(out[:, inp["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip()
            ans.append({"q": q, "a": a})
            print(f"[{c['id']}] {time.time() - t:.1f}s peak {torch.cuda.max_memory_allocated() / 2**30:.1f} GB\n  Q: {q}\n  A: {a}", flush=True)
            torch.cuda.empty_cache()
        res.append({"id": c["id"], "answers": ans})
        json.dump(res, open(job["out"], "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print("== done", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(json.load(open(sys.argv[1], encoding="utf8")))
