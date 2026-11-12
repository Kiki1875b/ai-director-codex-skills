"""PreToolUse(Bash) hook: a generation/edit script may run only after its ai-director skill was invoked in this session.

Why: the user had to point out several times that generation started without the skill's procedure (memory
use-ai-director-skills). Converting skills to agents would not fix that; this hook does.
How: if the Bash command runs one of the scripts below, look in the session transcript for a Skill call with the
required skill name ("skill":"<name>"). Missing -> deny with a message telling which skill to invoke first.
Any other command, or an unreadable payload/transcript, is allowed (the hook must never block normal work).
"""
import json
import re
import sys

RULES = [
    (re.compile(r"\b(ltx_remote|wan_remote|codex_image|rerun_workflow|animate_still)\.py\b"), "ai-director-shot-gen"),
    (re.compile(r"\b(sa3_template|sa3_gen|sa3_official|ace_bgm|ace_decoder_ab|sound_mix|render_timeline|moss_gen_server)\.py\b"), "ai-director-edit"),
]


def skill_invoked(transcript_path, skill):
    needles = (f'"skill":"{skill}"', f'"skill": "{skill}"', f'"skill":"projectSettings:{skill}"')
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"Skill"' in line and any(n in line for n in needles):
                    return True
    except OSError:
        return True  # cannot check -> do not block
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    need = [skill for rx, skill in RULES if rx.search(cmd)]
    if not need:
        return 0
    path = data.get("transcript_path")
    if not path:
        return 0
    missing = sorted({s for s in need if not skill_invoked(path, s)})
    if not missing:
        return 0
    names = ", ".join(missing)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"이 스크립트는 {names} 스킬 절차를 따라야 한다. 먼저 Skill 도구로 {names}를 호출하고 "
            f"그 절차(승인 게이트, GPU 한 작업, 검수 기준)를 확인한 뒤 다시 실행한다. (.claude/hooks/require_skill.py)")}},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
