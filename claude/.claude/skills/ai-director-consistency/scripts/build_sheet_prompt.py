"""Build a production sheet prompt from a story.json.

Usage:
  python build_sheet_prompt.py stories/<slug>/story.json <target> [--out prompts/x-sheet.txt]
        [--layout scene|film-bible|character|object|location|storyboard]
        [--max-cuts 6] [--per-page 12] [--page 1]

Layouts (see references/production-sheet.md):
  scene       target = scene id. Light paper sheet, one scene: header + spatial anchor +
              1 character ref + 2 environment/top-down map + 3 storyboard cuts + 4 lighting/mood notes
  film-bible  target = ALL. Dark presentation board for the whole film: character turnaround
              column, storyboard grid, set/lighting column, colour palette strip and spec row
  character   target = character id. One character only: turnaround, face close-ups,
              expressions taken from the script, state variants from notes, costume and carried props
  object      target = object id, comma list, or ALL. Prop sheet: 3 angles + scale + detail per prop
  location    target = world id. Location sheet, no people: hero wide, key angles used by the
              scenes, top-down floor plan with landmarks, one lighting variant per scene
  storyboard  target = scene id or ALL. Conti sheet: grid of cuts (--per-page, --page) with shot id,
              camera, duration, action and dialogue under each panel
Prints the reference images as --ref "label=path" pairs (character_image1..3, env_image1..2,
object_image1..3). Pass them to the image generator as references with the same labels.
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


def all_refs(ent, base, limit):
    out = []
    for r in ent.get("ref_images") or []:
        p = (base / r).resolve()
        if p.exists() and p not in out:
            out.append(p)
    return out[:limit]


def dialogue_text(shot, ents):
    lines = []
    for d in shot.get("dialogue") or []:
        if not d.get("text"):
            continue
        name = ents.get(d.get("character"), {}).get("name", d.get("character", ""))
        lines.append(f"{name}: \"{d['text']}\"")
    return " / ".join(lines)


def finish(L, style, refs, out_path):
    if style.get("negative"):
        L.append(f"Avoid inside the images: {style['negative']}.")
    prompt = "\n".join(l for l in L if l and l.strip())
    if out_path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt + "\n", encoding="utf-8")
        print(f"prompt: {out}")
    else:
        print(prompt)
        print()
    print("refs: " + " ".join(f'--ref "{r}"' for r in refs))


def entity_sheets(args, doc, ents, style, base, scenes):
    """character / object / location layouts: one bible entity (or a few props) per sheet."""
    bible = doc.get("bible", {})
    title = doc.get("story", {}).get("title", "")
    target = args.scene
    refs, L = [], []

    def shots_with(key, eid):
        return [(sc, sh) for sc in scenes for sh in sorted(sc.get("shots", []), key=lambda s: s.get("order", 0))
                if eid in (sh.get(key) or [])]

    if args.layout == "character":
        e = ents.get(target)
        if not e or e not in bible.get("characters", []):
            sys.exit(f"character {target} not found in bible.characters")
        for p in all_refs(e, base, 1):
            refs.append(f"character_image1={p}")
        if not refs:
            print(f"WARN no existing ref image for {target}; the sheet will rely on the text anchor only.", file=sys.stderr)
        appearances = shots_with("characters", target)
        freq = {}
        for _, sh in appearances:
            for o in sh.get("objects", []):
                freq[o] = freq.get(o, 0) + 1
        props = sorted(freq, key=lambda o: -freq[o])[:2]
        close = [sh for _, sh in appearances if sh.get("characters") == [target]
                 and any(k in sh.get("camera", "").upper() for k in ("CU", "MCU", "ECU"))]
        lines = [sh.get("action", "") for sh in close if sh.get("action")][:4]
        tag = " (= character_image1)" if refs else ""
        L = [
            f"Landscape 3:2 character model sheet on light paper, clean editorial layout, small serif labels. Title: '{e.get('name', target)}' — {title}.",
            f"CHARACTER{tag}: {e.get('anchor', '')}",
            "ROW 1 TURNAROUND: full body FRONT, THREE-QUARTER, SIDE, BACK on a plain light-grey ground, same scale, with a thin height ruler.",
            "ROW 2 FACE: front close-up, side close-up, and an EXPRESSION row of 4 head-and-shoulder shots with small labels.",
            f"Expressions come from the film's close-ups; base them on these moments: {' | '.join(lines) or 'neutral, listening, faint smile, sorrow'}.",
            f"STATE VARIANTS (small column, one image per state, same outfit): {e['notes']}" if e.get("notes") else "",
            "COSTUME DETAILS: labelled item crops (fabric, collar, buttons, shoes, accessories) and a PALETTE MATCH strip of 5 swatches.",
            *([f"SIGNATURE PROPS (small callouts, most used with this character): " + "; ".join(f"{ents[o].get('name', o)}: {ents[o].get('anchor', '')}" for o in props if o in ents)] if props else []),
            f"Style: {style.get('anchor', '')}",
            "The same person must look identical in every image. Text may be small; images matter most.",
        ]
    elif args.layout == "object":
        all_objs = bible.get("objects", [])
        ids = [o["id"] for o in all_objs] if target.upper() == "ALL" else [t.strip() for t in target.split(",")]
        objs = [ents[i] for i in ids if i in ents]
        if not objs:
            sys.exit(f"object(s) {target} not found in bible.objects")
        if len(objs) > 3:
            print(f"WARN {len(objs)} props; only 3 get reference images. Split into several sheets for detail.", file=sys.stderr)
        labels = {}
        for n, o in enumerate(objs[:3], 1):
            for p in all_refs(o, base, 1):
                refs.append(f"object_image{n}={p}")
                labels[o["id"]] = f"object_image{n}"
        rows = []
        for o in objs:
            used = shots_with("objects", o["id"])
            where = ", ".join(sh["id"] for _, sh in used[:6])
            tag = f" (= {labels[o['id']]})" if o["id"] in labels else ""
            rows.append(f"- {o.get('name', o['id'])}{tag}: {o.get('anchor', '')}"
                        + (f" | notes: {o['notes']}" if o.get("notes") and ".png" not in o["notes"] else "")
                        + (f" | used in {where}" if where else ""))
        L = [
            f"Landscape 3:2 prop design sheet on light paper, clean editorial layout, small serif labels — {title}.",
            f"One horizontal band per prop ({len(objs)} bands). In each band: FRONT, SIDE, TOP (or three-quarter) views on a plain mid-grey ground, "
            "a SCALE view next to an outline hand, 1-2 DETAIL macro crops, and a STATE strip if the notes describe states.",
            *rows,
            "Each prop looks exactly like its reference image in every view; no extra props, no hands holding them except the scale outline.",
            f"Style: {style.get('anchor', '')}",
        ]
    else:  # location
        e = ents.get(target)
        if not e or e not in bible.get("worlds", []):
            sys.exit(f"world {target} not found in bible.worlds")
        for n, p in enumerate(all_refs(e, base, 2), 1):
            refs.append(f"env_image{n}={p}")
        if not refs:
            print(f"WARN no existing ref image for {target}; the sheet will rely on the text anchor only.", file=sys.stderr)
        used = [sc for sc in scenes if sc.get("world_id") == target]
        cams = []
        for sc in used:
            for sh in sorted(sc.get("shots", []), key=lambda s: s.get("order", 0)):
                c = sh.get("camera", "")
                if c and ("wide" in c.lower() or "two-shot" in c.lower()) and c not in cams:
                    cams.append(c)
        tag = " (= env_image1)" if refs else ""
        L = [
            f"Landscape 3:2 location design sheet on light paper, clean editorial layout, small serif labels — {title}. NO PEOPLE anywhere.",
            f"LOCATION{tag}: {e.get('anchor', '')}",
            f"Notes: {e['notes']}" if e.get("notes") else "",
            "TOP LEFT: one large HERO WIDE matching the reference exactly.",
            "TOP RIGHT: 3 KEY ANGLES of the same set from the camera positions the film uses"
            + (f" ({'; '.join(cams[:3])})" if cams else "") + ", each with a small label.",
            "BOTTOM LEFT: FLOOR PLAN (TOP-DOWN) with every landmark labelled, entrances, the camera side, and a north/left-right marker.",
            *[f"Spatial anchor ({sc['id']}): {sc['spatial_anchor']}" for sc in used if sc.get("spatial_anchor")],
            f"BOTTOM RIGHT: LIGHTING VARIANTS, one small frame per scene ({len(used)}): "
            + " | ".join(f"{sc['id']} {sc.get('lighting', '')}" for sc in used),
            "Plus a texture/material strip (4 crops) and a 5-swatch palette.",
            f"Style: {style.get('anchor', '')}",
            "Same geography and landmarks in every image. Text may be small; images matter most.",
        ]
    finish(L, style, refs, args.out)


def storyboard_sheet(args, doc, ents, style, base, scenes):
    title = doc.get("story", {}).get("title", "")
    chosen = scenes if args.scene.upper() == "ALL" else [s for s in scenes if s["id"] == args.scene]
    if not chosen:
        sys.exit(f"scene {args.scene} not found")
    flat = [(sc, sh) for sc in chosen for sh in sorted(sc.get("shots", []), key=lambda s: s.get("order", 0))]
    per = max(1, args.per_page)
    pages = (len(flat) + per - 1) // per
    if not 1 <= args.page <= pages:
        sys.exit(f"page {args.page} out of range 1..{pages}")
    part = flat[(args.page - 1) * per: args.page * per]
    print(f"INFO {len(flat)} cuts -> {pages} page(s) of {per}; this is page {args.page}.", file=sys.stderr)
    cols = 4 if per > 6 else 3
    rows = (len(part) + cols - 1) // cols

    char_ids, world_ids, obj_ids = [], [], []
    for sc, sh in part:
        char_ids += [c for c in sh.get("characters", []) if c not in char_ids]
        obj_ids += [o for o in sh.get("objects", []) if o not in obj_ids]
        if sc.get("world_id") and sc["world_id"] not in world_ids:
            world_ids.append(sc["world_id"])
    refs, labels = [], {}
    for n, cid in enumerate(char_ids[:2], 1):
        for p in all_refs(ents.get(cid, {}), base, 1):
            refs.append(f"character_image{n}={p}")
            labels[cid] = f"character_image{n}"
    for n, wid in enumerate(world_ids[:2], 1):
        for p in all_refs(ents.get(wid, {}), base, 1):
            refs.append(f"env_image{n}={p}")
            labels[wid] = f"env_image{n}"
    if obj_ids and len(refs) < 5:
        for p in all_refs(ents.get(obj_ids[0], {}), base, 1):
            refs.append(f"object_image1={p}")
            labels[obj_ids[0]] = "object_image1"

    def who(eid):
        e = ents.get(eid, {})
        tag = f" (= {labels[eid]})" if eid in labels else ""
        return f"- {e.get('name', eid)}{tag}: {e.get('anchor', '')}"

    panels = []
    for sc, sh in part:
        d = dialogue_text(sh, ents)
        panels.append(f"[{sh['id']}] scene '{sc.get('title', sc['id'])}' | {sh.get('camera', '')} | ~{round(sh.get('duration_ms', 0) / 1000)}s | "
                      f"{sh.get('action', '')}" + (f" | DIALOGUE: {d}" if d else "") + (f" | SFX: {sh['sfx']}" if sh.get("sfx") else ""))
    L = [
        f"Landscape 3:2 storyboard (conti) sheet on light paper, {cols} columns x {rows} rows of "
        f"{doc.get('story', {}).get('format', {}).get('aspect_ratio', '16:9')} cinematic frames, thin black borders, "
        f"small clean labels. Header: '{title} — STORYBOARD {args.page}/{pages}'.",
        "Each panel: the shot id in a small tag at top-left; under the panel two short lines: camera/lens + duration, then the action; "
        "dialogue as a quoted line in italics. A thin scene divider label where a new scene starts.",
        "Panels in this order, left to right, top to bottom:",
        *panels,
        "CHARACTERS (identical in every panel):",
        *[who(c) for c in char_ids],
        *[who(o) for o in obj_ids if o in labels],
        "LOCATIONS:",
        *[who(w) for w in world_ids],
        *[f"Spatial anchor ({sc['id']}): {sc['spatial_anchor']}" for sc in chosen if sc.get("spatial_anchor") and any(s is sc for s, _ in part)],
        f"Style of the frames: {style.get('anchor', '')}",
        "Frames are finished cinematic stills, not sketches. Text may be small; images matter most.",
    ]
    finish(L, style, refs, args.out)


def cut_line(i, shot):
    meta = [f"SHOT/CAMERA: {shot.get('camera', '')}".strip(),
            f"DURATION: ~{round(shot.get('duration_ms', 0) / 1000)}s"]
    if shot.get("lens"):
        meta.insert(0, f"LENS: {shot['lens']}")
    return f"Cut {i}: {shot.get('action', '')}. " + " | ".join(meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("scene", help="scene id (scene, storyboard), ALL (film-bible, storyboard, object), "
                                  "character id (character), object id/list (object) or world id (location)")
    ap.add_argument("--out")
    ap.add_argument("--layout", choices=["scene", "film-bible", "character", "object", "location", "storyboard"],
                    default="scene")
    ap.add_argument("--max-cuts", type=int, default=6)
    ap.add_argument("--per-page", type=int, default=12, help="storyboard: cuts per sheet")
    ap.add_argument("--page", type=int, default=1, help="storyboard: 1-based page number")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    story_path = Path(args.story).resolve()
    base = story_path.parent
    doc = json.loads(story_path.read_text(encoding="utf-8"))
    bible = doc.get("bible", {})
    ents = {e["id"]: e for g in ("characters", "objects", "worlds") for e in bible.get(g, [])}
    style = bible.get("style", {})
    scenes = sorted(doc.get("scenes", []), key=lambda s: s.get("order", 0))
    if args.layout in ("character", "object", "location"):
        return entity_sheets(args, doc, ents, style, base, scenes)
    if args.layout == "storyboard":
        return storyboard_sheet(args, doc, ents, style, base, scenes)
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

    if args.layout == "scene":
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
