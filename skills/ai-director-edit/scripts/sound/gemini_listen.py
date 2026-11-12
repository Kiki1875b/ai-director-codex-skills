"""Ask Gemini to listen to sound-effect candidates and judge each one.

usage: python gemini_listen.py --brief brief.txt --out review.json a.flac b.wav ...
Needs GEMINI_API_KEY. Files are sent inline (keep the total under ~15 MB).
Gemini's claims are not trusted as-is: check them with measurements (sound-rubric.md 9).
"""
import argparse, base64, json, os, sys, urllib.request

MIME = {".wav": "audio/wav", ".flac": "audio/flac", ".mp3": "audio/mp3", ".ogg": "audio/ogg"}

SCHEMA_TEXT = """Answer in JSON only:
{"files":[{"file":"<name>","sounds_like":"<what you actually hear, concrete>",
"defects":[{"time_s":<number or null>,"type":"distortion|crackle|clipping|metallic_artifact|phasing|click|noise|cutoff|other","detail":"..."}],
"fits_brief":<1-5>,"technically_clean":<1-5>,"usable":true|false,"fix":"<what to change in the prompt or settings>"}],
"best":"<file name or none>","overall":"<one paragraph>"}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--brief", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    a = ap.parse_args()
    brief = open(a.brief, encoding="utf-8").read()
    parts = [{"text": brief + "\n\n" + SCHEMA_TEXT + "\n\nFiles in order:"}]
    for f in a.files:
        parts.append({"text": f"--- file: {os.path.basename(f)} ---"})
        parts.append({"inline_data": {"mime_type": MIME[os.path.splitext(f)[1].lower()],
                                      "data": base64.b64encode(open(f, "rb").read()).decode()}})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{a.model}:generateContent?key={os.environ['GEMINI_API_KEY']}"
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:800]}")
    text = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    data = json.loads(text)
    data["_model"] = a.model
    data["_files"] = a.files
    json.dump(data, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for f in data["files"]:
        print(f"{f['file']}: usable={f['usable']} fit={f['fits_brief']} clean={f['technically_clean']} | {f['sounds_like'][:90]}")
        for d in f["defects"]:
            print(f"    - {d.get('time_s')}s {d['type']}: {d['detail'][:100]}")
    print("best:", data.get("best")); print("overall:", data.get("overall"))


if __name__ == "__main__":
    main()
