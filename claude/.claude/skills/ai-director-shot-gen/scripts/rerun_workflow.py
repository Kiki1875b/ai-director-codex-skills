"""Re-run a saved ComfyUI API workflow (<clip>_workflow.json) with ONLY the positive prompt changed.

For prompt A/B tests: model, keys, audio, seed, cfg, guides and steps stay byte-identical to the baseline clip,
so the prompt is the only variable. Uploaded inputs (LoadImage/LoadAudio) must still be on the server; the script
checks them first and stops without queueing if any is missing (then re-run the baseline with ltx_remote.py).

  python rerun_workflow.py --workflow stories/<slug>/media/video/<clip>_workflow.json \
      --prompt-file stories/<slug>/prompts/motion/<new>.txt --out stories/<slug>/media/video/<new>.mp4 [--dry-run]
"""
import argparse
import json
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "ai-director", "scripts"))
import ledger  # noqa: E402
import comfy_guard  # noqa: E402
from ltx_remote import wait_and_fetch  # noqa: E402


def positive_node(wf):
    """The CLIPTextEncode feeding the 'positive' input of the conditioning node."""
    for n in wf.values():
        if n["class_type"] == "LTXVConditioning":
            ref = n["inputs"]["positive"]
            return ref[0]
    sys.exit("no LTXVConditioning node: not an LTX workflow from ltx_remote.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"))
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=6 * 3600)
    ap.add_argument("--dry-run", action="store_true", help="show the diff and input check only; do not queue")
    a = ap.parse_args()
    srv = a.server.rstrip("/")
    wf = json.load(open(a.workflow, encoding="utf-8"))
    pid_node = positive_node(wf)
    old = wf[pid_node]["inputs"]["text"]
    new = open(a.prompt_file, encoding="utf-8").read().strip()
    wf[pid_node]["inputs"]["text"] = new
    prefix = f"aid/{os.path.splitext(os.path.basename(a.out))[0]}"
    for n in wf.values():
        if n["class_type"] == "SaveVideo":
            n["inputs"]["filename_prefix"] = prefix
    inputs = [(n["class_type"], n["inputs"].get("image") or n["inputs"].get("audio")) for n in wf.values()
              if n["class_type"] in ("LoadImage", "LoadAudio")]
    seeds = [n["inputs"]["noise_seed"] for n in wf.values() if n["class_type"] == "RandomNoise"]
    print(f"positive node {pid_node}: {len(old.split())} -> {len(new.split())} words; seeds {seeds}; inputs {inputs}")
    missing = []
    for _, name in inputs:
        try:
            r = requests.get(f"{srv}/view", params={"filename": name, "type": "input"}, timeout=30, stream=True)
            ok = r.status_code == 200
            r.close()
        except requests.RequestException as e:
            sys.exit(f"server not reachable: {e}")
        if not ok:
            missing.append(name)
    if missing:
        sys.exit(f"inputs not on the server any more: {missing}. Re-run the baseline with ltx_remote.py instead.")
    if a.dry_run:
        print("dry run: inputs present, not queued")
        return
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(os.path.splitext(a.out)[0] + "_workflow.json", "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=1)
    r = comfy_guard.submit(srv, {"prompt": wf})
    if r.status_code != 200:
        sys.exit(f"queue rejected: {r.text[:2000]}")
    pid = r.json()["prompt_id"]
    ledger.record(a.out, "gen_submit", tool="rerun_workflow", job_id=pid, seed=seeds[0] if seeds else None, prompt=new,
                  settings={"baseline_workflow": os.path.basename(a.workflow), "only_change": "positive prompt"})
    print(f"queued {pid} (baseline {os.path.basename(a.workflow)}, prompt only)", flush=True)
    t0 = time.time()
    wait_and_fetch(srv, pid, a.out, a.timeout, tool="rerun_workflow")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
