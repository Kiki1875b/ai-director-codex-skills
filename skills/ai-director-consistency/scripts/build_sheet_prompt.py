"""Build an OpenArt-style production sheet prompt for one scene of a story.json.

Usage:
  python build_sheet_prompt.py stories/<slug>/story.json S1 [--out prompts/S1-sheet.txt]
                               [--layout smart-shot|film-bible] [--max-cuts 6]

Layouts (see references/production-sheet.md):
  smart-shot  light paper sheet, one scene: header + spatial anchor + 1 character ref +
              2 environment/top-down map + 3 storyboard cuts + 4 lighting/mood notes
  film-bible  dark presentation board for the whole film (like OpenArt's "Create your own
              short films" promo): character turnaround column, storyboard grid of every
              scene, set/lighting column, colour palette strip and spec row
Prints the reference images as --ref "label=path" pairs, in order (character_image1..3, env_image1,
object_image1). Pass them to the image generator as references with the same labels.
"""
import argparse
import json
import sys
from pathlib import Path

MAX_CHAR_REFS = 3


def first_ref(ent, base):
    for r in ent.get("ref_images") or []:
        p = (base / r).resolve()
        if p.exists():
            return p
    return None


def cut_line(i, shot):
    meta = [f"SHOT/CAMERA: {shot.get('camera', '')}".strip(),
            f"DURATION: ~{round(shot.get('duration_ms', 0) / 1000)}s"]
    if shot.get("lens"):
        meta.insert(0, f"LENS: {shot['lens']}")
    return f"Cut {i}: {shot.get('action', '')}. " + " | ".join(meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("scene", help="scene id, or ALL for the film-bible layout")
    ap.add_argument("--out")
    ap.add_argument("--layout", choices=["smart-shot", "film-bible"], default="smart-shot")
    ap.add_argument("--max-cuts", type=int, default=6)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    story_path = Path(args.story).resolve()
    base = story_path.parent
    doc = json.loads(story_path.read_text(encoding="utf-8"))
    bible = doc.get("bible", {})
    ents = {e["id"]: e for g in ("characters", "objects", "worlds") for e in bible.get(g, [])}
    style = bible.get("style", {})
    scenes = sorted(doc.get("scenes", []), key=lambda s: s.get("order", 0))
    if args.scene.upper() == "ALL":
        chosen = scenes
    else:
        chosen = [s for s in scenes if s["id"] == args.scene]
        if not chosen:
            sys.exit(f"scene {args.scene} not found")
    shots = [sh for sc in chosen for sh in sorted(sc.get("shots", []), key=lambda s: s.get("order", 0))]
    if len(shots) > args.max_cuts:
        print(f"WARN {len(shots)} shots; only the first {args.max_cuts} fit legibly. "
              f"Split the scene or raise --max-cuts.", file=sys.stderr)
        shots = shots[:args.max_cuts]

    char_ids, obj_ids = [], []
    for sh in shots:
        char_ids += [c for c in sh.get("characters", []) if c not in char_ids]
        obj_ids += [o for o in sh.get("objects", []) if o not in obj_ids]
    world_ids = [w for w in dict.fromkeys(sc.get("world_id") for sc in chosen) if w]

    refs, labels = [], {}
    for n, cid in enumerate(char_ids[:MAX_CHAR_REFS], 1):
        p = first_ref(ents.get(cid, {}), base)
        if p:
            refs.append(f"character_image{n}={p}")
            labels[cid] = f"character_image{n}"
    for n, wid in enumerate(world_ids[:1], 1):
        p = first_ref(ents.get(wid, {}), base)
        if p:
            refs.append(f"env_image{n}={p}")
            labels[wid] = f"env_image{n}"
    for n, oid in enumerate(obj_ids[:1], 1):
        p = first_ref(ents.get(oid, {}), base)
        if p:
            refs.append(f"object_image{n}={p}")
            labels[oid] = f"object_image{n}"
    missing = [i for i in char_ids[:MAX_CHAR_REFS] + world_ids[:1] if i not in labels]
    if missing:
        print(f"WARN no existing ref image for {', '.join(missing)}; the sheet will rely on text anchors only.",
              file=sys.stderr)
    if len(char_ids) > MAX_CHAR_REFS:
        print(f"WARN {len(char_ids)} characters; only {MAX_CHAR_REFS} get reference images.", file=sys.stderr)

    def who(eid):
        e = ents.get(eid, {})
        tag = f" (= {labels[eid]})" if eid in labels else ""
        return f"- {e.get('name', eid)}{tag}: {e.get('anchor', '')}"

    title = doc.get("story", {}).get("title") or chosen[0].get("title", "")
    palette = ", ".join(style.get("palette", [])) or "derive 5 named swatches from the style"
    spatial = " ".join(sc.get("spatial_anchor", "") for sc in chosen).strip() or \
        "State where each landmark sits (compass/left-right), where the characters stand and which way they move."
    lighting = " ".join(sc.get("lighting", "") for sc in chosen).strip()

    if args.layout == "smart-shot":
        L = [
            "Landscape 3:2 production document sheet on light paper, clean editorial layout, small serif labels.",
            f"HEADER: 'SHARED CHOICES' / {title} | CUT COUNT: {len(shots)} | COLOR PALETTE: {palette} with 5 swatches | ENVIRONMENT FINGERPRINT.",
            f"SPATIAL ANCHOR (EXPLICIT): {spatial} Every storyboard cut must honor this same geography and lighting continuity.",
            "SECTION 1 CHARACTER REFERENCE: for each character full-body FRONT, SIDE, BACK; FACE CLOSE-UP and SIDE CLOSE-UP; COSTUME DETAILS as labelled item cut-outs; PALETTE MATCH swatches.",
            *[who(c) for c in char_ids],
            *([who(o) for o in obj_ids]),
            "SECTION 2 ENVIRONMENT / SET DESIGN: one hero wide of the location, and a FLOOR PLAN / BLOCKING MAP (TOP-DOWN) with landmarks, the movement path as a dashed line and a numbered camera icon per cut.",
            *[who(w) for w in world_ids],
            f"SECTION 3 STORYBOARD ({len(shots)} CUTS): one panel per cut in a row, 'Cut N' tag, under each panel LENS, SHOT, DURATION, MOVEMENT, CAMERA POSITION and a one-line description.",
            *[cut_line(i, sh) for i, sh in enumerate(shots, 1)],
            f"SECTION 4 LIGHTING + MOOD + STYLE NOTES: 4 lighting reference thumbnails with names{': ' + lighting if lighting else ''}; MOOD KEYWORDS (5 words); LENS + CAMERA rules.",
            f"Style: {style.get('anchor', '')}",
            "The same person must look identical in every panel. Text may be small; images matter most.",
        ]
    else:
        L = [
            f"Landscape 16:9 dark presentation board, near-black background, thin grey grid lines, small white technical labels: the complete visual bible for the short film '{title}'.",
            "LEFT COLUMN: character turnaround for each character (front, three-quarter, side, back) in one row, then 2 close-ups and key props with callouts.",
            *[who(c) for c in char_ids],
            *([who(o) for o in obj_ids]),
            f"CENTER: storyboard grid of {len(shots)} cinematic frames in story order, each with a frame number and 2-3 lines of notes (shot, camera, action).",
            *[cut_line(i, sh) for i, sh in enumerate(shots, 1)],
            "RIGHT COLUMN: set design wides of each location, a top-down blocking map, and lighting setups with short notes.",
            *[who(w) for w in world_ids],
            f"BOTTOM: a colour palette strip ({palette}) and one spec row: format, aspect ratio, lens set, look, mood keywords.",
            f"Spatial continuity: {spatial}",
            f"Style: {style.get('anchor', '')}",
            "Every frame shows the same characters with identical design. Text may be small; images matter most.",
        ]
    if style.get("negative"):
        L.append(f"Avoid inside the images: {style['negative']}.")
    prompt = "\n".join(l for l in L if l.strip())

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt + "\n", encoding="utf-8")
        print(f"prompt: {out}")
    else:
        print(prompt)
        print()
    print("refs: " + " ".join(f'--ref "{r}"' for r in refs))


if __name__ == "__main__":
    main()
