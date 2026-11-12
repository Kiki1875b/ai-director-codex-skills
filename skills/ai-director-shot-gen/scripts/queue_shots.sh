#!/bin/bash
# Queue many shots on the remote ComfyUI at once (the server runs them one by one).
#   bash queue_shots.sh stories/<slug> <queue-file> <version> <first-seed> [extra wan_remote args...]
# queue-file lines: "<shot-id> <keyframe path relative to the story dir> <frames> [extra negative: rest of the line]"
#   prompt = prompts/motion/<shot-id>.txt, output = media/video/<shot-id>-vid-<version>.mp4, log in media/video/_src/
set -u
story="$1"; queue="$2"; ver="$3"; seed="$4"; shift 4
here="$(cd "$(dirname "$0")" && pwd)"
cd "$story"
mkdir -p media/video/_src
while read -r shot key frames neg; do
  [ -z "${shot:-}" ] && continue
  extra=()
  if [ -n "${neg:-}" ]; then extra=(--negative-extra "$neg"); fi
  python "$here/wan_remote.py" --image "$key" --prompt-file "prompts/motion/$shot.txt" \
    --out "media/video/$shot-vid-$ver.mp4" --frames "$frames" --seed "$seed" --nag 5 --rife --allow-queue \
    "${extra[@]}" "$@" > "media/video/_src/$shot-vid-$ver.log" 2>&1 &
  seed=$((seed + 1)); sleep 6
done < "$queue"
wait
grep -h prompt_id media/video/_src/*-vid-"$ver".log
