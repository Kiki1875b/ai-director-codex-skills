---
name: ai-director-edit
description: Use when assembling generated shots into a finished AI video — building the tracks/clips timeline (video, VO, BGM, captions), trimming with source in/out, speed 0.5–2x, transitions (dissolve, fade, slide, wipe, clock_wipe, iris, zoom), audio levels, matching a target length, and rendering the timeline to mp4/mov with ffmpeg via render_timeline.py. 한국어 트리거는 영상 편집, 타임라인, 컷 이어붙이기, 트랜지션, 자막 넣기, 배경음악, 내레이션 합치기, 렌더, 내보내기. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 편집과 렌더 (Edit & Export)

OpenArt Director의 편집기는 tracks/clips 데이터 모델 위에서 돌아간다. 트랙 타입은 video/audio(vo|bgm)/text다. 클립은 `timeline_start_ms`, `source_in_ms`, `source_out_ms`, `speed`, `volume`, `transition_in`을 가진다. 이 스킬은 같은 모델을 story.json의 `timeline`에 쓰고, `scripts/render_timeline.py`로 ffmpeg 렌더를 한다. 스키마는 `ai-director/references/story-schema.md`를 따른다.

## 1. 러프컷 자동 조립

1. 트랙 4개를 만든다: `tr_v1`(video), `tr_vo`(audio/vo), `tr_bgm`(audio/bgm, volume 0.3~0.4), `tr_txt`(text).
2. 스토리 순서대로 각 샷의 active version을 `kind:"shot"` 클립으로 이어 붙인다.
   - 첫 클립의 `timeline_start_ms`는 0이다.
   - 다음 클립의 시작 = 이전 클립 시작 + `(source_out-source_in)/speed`
   - 트랜지션이 있으면 그 길이만큼 겹쳐서 앞당긴다.
3. 대사와 내레이션 음성은 해당 샷의 시작 시점에 맞춰 vo 클립으로 놓는다. 음성 클립이 샷보다 길면 샷을 늘리거나 대사를 줄인다.
4. 자막은 text 클립으로 넣는다. 한 줄은 약 16자 이내로 하고, 대사 길이에 맞춰 표시한다.
5. `validate_story.py --target-ms <목표>`로 길이를 확인한다.

## 2. 편집 원칙

- **기본은 하드컷이다.** 트랜지션은 의미가 있을 때만 쓴다.
  - dissolve: 시간 경과
  - fade: 시작과 끝
  - wipe/slide: 장소 이동이나 코믹한 전환
  - iris, clock_wipe, zoom: 장르적 연출
  - 길이는 기본 500ms, 최대 5000ms다.
- **군더더기 프레임을 자른다.** 생성 영상은 앞뒤 0.3~1초가 정적이거나 흐트러진 경우가 많다. source_in/out으로 잘라낸다.
- **속도를 조절한다.** 0.5~2배 범위다. 늘어지는 동작은 1.2~1.5배, 강조할 순간은 0.6~0.8배.
- **행동 중간에 컷하면 연결이 매끄럽다.** 체인 샷은 앞 샷의 끝과 다음 샷의 시작이 같은 동작이 되도록 트림한다.
- **음향.** VO가 있는 구간은 BGM을 0.2~0.35로 낮춘다. 클립 볼륨은 0~3 범위다. 효과음은 vo가 아닌 별도 audio 트랙에 둔다(subtype 없이).
- **길이를 맞춘다.** 늘어지는 샷 트림 → 속도 → 샷 삭제 순서로 줄인다. 재생성은 마지막 수단이다.

## 3. 요청 → 편집 연산

| 요청 | 연산 |
|---|---|
| "S2-3 빼줘" | 해당 클립 `enabled:false`. 뒤 클립들을 앞으로 당긴다 |
| "더 빠르게" | 각 클립 꼬리 트림, 길게 늘어지는 샷 speed 1.2 |
| "S1-2랑 S1-3 순서 바꿔" | 두 클립의 시작 시간을 맞바꾸고 이후 클립을 다시 계산한다 |
| "이전 버전으로" | shot.active_version_id와 clip.media_url을 되돌린다 |
| "음악 넣어줘" | bgm 클립을 0부터 영상 끝까지 놓는다 |
| "자막 크게" | 렌더 옵션 `--font-size` |

## 4. 렌더

```bash
python <skills>/ai-director-edit/scripts/render_timeline.py stories/<slug>/story.json -o stories/<slug>/export/final.mp4
# 옵션: --dry-run (ffmpeg 명령만 출력), --font <ttf>, --font-size 48, --preview (540p 빠른 미리보기)
```

렌더러 동작:
- video 트랙 중 order가 가장 앞선 트랙을 주 영상으로 쓴다.
- 클립마다 트림, 속도 조절, 스케일, 패드를 적용한다. 이미지 클립은 정지 화면으로 만든다.
- 클립 사이 빈 구간은 검은 화면으로 채운다.
- `transition_in`은 ffmpeg xfade로 매핑한다: dissolve/fade/slide*/wipe*/radial/circleopen/zoomin.
- 오디오는 영상 클립 원음, vo, bgm을 각 위치에 배치한 뒤 amix로 섞는다. 원음이 없는 영상은 무음으로 처리한다.
- text 클립은 drawtext로 자막을 입힌다. 기본 폰트는 Windows의 맑은 고딕이다.
- export 설정(fps, 해상도, 형식, sample_rate)을 따른다.

렌더 후 `ffprobe`로 길이와 스트림을 확인한다. 중간 프레임 몇 장을 추출해 view_image로 보고 자막과 트랜지션을 확인한 뒤에 완료를 보고한다.

```bash
ffmpeg -y -ss 3 -i export/final.mp4 -frames:v 1 export/check_3s.png
```

## 한계

- 여러 video 트랙의 겹침(PIP, 오버레이)은 렌더러가 처리하지 않는다. 주 트랙 하나만 렌더한다.
- 색 보정(LUT)과 키프레임 애니메이션은 지원하지 않는다. 필요하면 ffmpeg 필터를 직접 추가한다.
- xfade의 slide/wipe 방향은 `direction`으로 고른다. iris는 in/out만 반영한다.
