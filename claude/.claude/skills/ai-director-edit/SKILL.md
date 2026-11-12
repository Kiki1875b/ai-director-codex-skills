---
name: ai-director-edit
description: Use when assembling generated shots into a finished AI video — building the tracks/clips timeline (video, VO, BGM, captions), trimming with source in/out, speed 0.5–2x, transitions (dissolve, fade, slide, wipe, clock_wipe, iris, zoom), audio levels, matching a target length, and rendering the timeline to mp4/mov with ffmpeg via render_timeline.py. 한국어 트리거는 영상 편집, 타임라인, 컷 이어붙이기, 트랜지션, 자막 넣기, 배경음악, 내레이션 합치기, 렌더, 내보내기. Part of the ai-director skill set.
---

# 편집과 렌더 (Edit & Export)

편집은 tracks/clips 데이터 모델 위에서 한다. 트랙 타입은 video/audio(vo|bgm)/text다. 클립은 `timeline_start_ms`, `source_in_ms`, `source_out_ms`, `speed`, `volume`, `transition_in`을 가진다. 이 모델을 story.json의 `timeline`에 쓰고, `scripts/render_timeline.py`로 ffmpeg 렌더를 한다. 스키마는 `ai-director/references/story-schema.md`를 따른다.

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

- **시선·관심의 연결.** 해당 scene.direction과 shot.staging/cut_link를 읽고, 실제 사용 구간에서 앞 컷의 관심점과 다음 컷의 대상을 대조한다. 인물의 목표·눈높이·축과 관객이 대상을 찾는 단서를 따로 본다. 절차는 `ai-director-cinematography/references/eyeline-continuity.md`. 이미 영상이 잠겼다면 결함 위치와 허용된 조치만 보고하며 트림·순서·대사 위치를 자동 변경하지 않는다. 확정된 정적·하드컷은 유지한다.
- **기본은 하드컷이다.** 트랜지션은 의미가 있을 때만 쓴다.
  - dissolve: 시간 경과
  - fade: 시작과 끝
  - wipe/slide: 장소 이동이나 코믹한 전환
  - iris, clock_wipe, zoom: 장르적 연출
  - 길이는 기본 500ms, 최대 5000ms다.
- **군더더기 프레임을 자른다.** 생성 영상은 앞뒤 0.3~1초가 정적이거나 흐트러진 경우가 많다. source_in/out으로 잘라낸다.
- **속도를 조절한다.** 0.5~2배 범위다. 늘어지는 동작은 1.2~1.5배, 강조할 순간은 0.6~0.8배.
- **행동 중간에 컷하면 연결이 매끄럽다.** 체인 샷은 앞 샷의 끝과 다음 샷의 시작이 같은 동작이 되도록 트림한다.
- **음향.** VO가 있는 구간은 BGM을 0.2~0.35로 낮춘다. 클립 볼륨은 0~3 범위다. 효과음은 vo가 아닌 별도 audio 트랙에 둔다(subtype 없이). 믹스를 보내기 전에 `references/sound-rubric.md`로 검수한다: 효과음이 들리는지, 동작과 맞는지, 끊김, 배경음 변화 시점, 대사 공간감, 대사와 입, 음악, 최종 음량.
- **효과음·BGM을 생성할 때**는 `references/audio-generation.md`를 먼저 읽는다: 현재 기본(효과음 SA3 Small-SFX 공식 템플릿 또는 실제 녹음, BGM ACE-Step 1.5 2B + ScragVAE), 시도한 방법과 결과, 라이선스로 제외한 모델, 공유 GPU 운용. 소리의 질감은 사용자 청취로 판정한다.
- **사운드 도구는 `scripts/sound/`에 있다.** 큐 시트(`stories/<slug>/edit/sound_cues_vN.json`)로 스템과 믹스를 만드는 것은 `python .claude/skills/ai-director-edit/scripts/sound/sound_mix.py stories/<slug>/edit/sound_cues_vN.json [--story stories/<slug>] [--outdir DIR] [--video export/a.mp4 --out export/a_sound.mp4]`다(기본 출력 `stories/<slug>/edit/mix/`, 상대 경로는 작품 폴더 기준). 레벨·꼬리·검사는 `fx_levels.py`, `cue_tails.py`, `sound_audit.py`, `audit_sync.py`, `mouth_sync.py`(`references/sound-rubric.md`), 대사 음성 고르기·후처리는 `voice_pick.py`, `voice_post.py`, 효과음 구하기·측정은 `sfx_fetch.py`, `sfx_measure.py` 등(`references/audio-generation.md`).
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
python .claude/skills/ai-director-edit/scripts/render_timeline.py stories/<slug>/story.json -o stories/<slug>/export/final.mp4
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

렌더 전:
- **통과 기록은 사용자 판정으로 채운다.** 사용자가 재생해 보고 컷을 통과시키면 `python .claude/skills/ai-director/scripts/ledger.py pass stories/<slug> --shot <id>`(버전을 바꿀 때 `--version <vid> --activate`), 러프컷의 연결을 통과시키면 `ledger.py cut-pass stories/<slug> --all`. version.review(파일 지문, 사용 구간, scope playback, reviewer/playback_by user, criteria)와 timeline.edit_point_reviews를 검증기와 같은 계산으로 쓰므로, 손으로 필드를 채우지 않는다. 이후 파일·트림·속도·전환이 바뀌면 검증기가 그 컷/편집점만 다시 묻는다(2026-11-11 「점등」 S1 사본 시험: 오류 52 → 0, 트림 100ms 변경 → 편집점 2곳만 오류).
- `validate_story.py --stage edit`(편집 중), 내보내기 직전에는 `--stage export`를 통과해야 한다. `render_timeline.py`가 최종 렌더 전에 export 검증을 자동으로 돌리고 실패하면 렌더하지 않는다(타임라인이 실제로 쓰는 샷만 검사, 폐기 샷 제외). `--preview`는 경고만 낸다. 사용자가 검증 미통과 상태의 렌더를 요청했을 때만 `--allow-unvalidated "<사유>"`를 쓰고, 사유는 장부(`ledger.jsonl`)에 남는다. 같은 트랙에서 겹치는 클립은 겹친 길이가 `transition_in.duration_ms`와 같아야 하고, 아니면 검사기와 렌더러가 거부한다.
- **편집점 재검수:** 트림·순서를 바꾼 이음매마다 `video-reviewer`가 실제 사용 구간으로 다시 본다(`review_video.py <clip> --range IN OUT --prev <앞 클립> --prev-range IN OUT --next <뒤 클립> --next-range IN OUT`, 범위는 ms): 손에 든 것, 행동 단계, 인물의 시선 목표·높이·축, 관객 관심점의 인계, 이동 방향, 밝기, 움직이는 부위의 속도. 실제 컷 경계와 speed/전환을 적용한 연결도 재생으로 확인한다. 구간만 바뀌었으면 편집점만 다시 보고, 파일이 바뀌면 샷 검수부터 다시 한다(`ai-director-consistency/references/video-rubric.md` 6절).

렌더 후 `ffprobe`로 길이와 스트림을 확인한다. 중간 프레임 몇 장을 추출해 Read로 보고 자막과 트랜지션을 확인한 뒤에 완료를 보고한다.

```bash
ffmpeg -y -ss 3 -i export/final.mp4 -frames:v 1 export/check_3s.png
```

## 5. LOG 원본과 LUT 룩

생성물은 바로 쓰지 않고 **LOG 원본 → LUT** 순서로 룩을 입힌다(카메라 원본을 그레이딩하는 실제 후반 흐름과 같다). `scripts/log_lut.py`:

```bash
python .claude/skills/ai-director-edit/scripts/log_lut.py make-lut --look sl-blue stories/<slug>/luts/sl_blue.cube
python .claude/skills/ai-director-edit/scripts/log_lut.py to-log media/S1-1-key-v2.png media/log/S1-1-key-v2_log.png
python .claude/skills/ai-director-edit/scripts/log_lut.py apply media/log/S1-1-key-v2_log.png luts/sl_blue.cube media/graded/S1-1-key-v2_slblue.png
# 영상 클립도 같은 .cube: ffmpeg -i clip_log.mp4 -vf "lut3d=file='luts/sl_blue.cube':interp=tetrahedral" out.mp4
```
- LOG 원본(`media/log/`)은 보관용이라 사용자에게 제출하지 않는다. 보여주는 건 LUT를 입힌 결과(`media/graded/`)와 그걸로 만든 콘티다.
- **어떤 룩을 쓸지는 작품마다 사용자 인터뷰로 정한다**(`ai-director-consistency/references/anti-slop.md` 0절의 4·5번). 스타일 프레임의 LOG→LUT 결과를 2~3안 나란히 보여주고 고르게 한다.
- 룩은 장르에 맞는 레퍼런스 그레이드(컬러리스트 인터뷰, 공개 LUT)가 확보되면 그걸 근거로 새 look을 `LOOKS`에 추가한다. **자료가 없거나 부족하면 `sl-blue`를 기본값으로 쓴다**(S-Log3→709, 스틸 블루 그림자, 피부·텅스텐은 따뜻하게 유지, 채도 약간↓). 「마지막 손님」에서 사용자 승인.
- 결정은 `bible.style.grade`와 `bible.style.lut`에 기록한다.
- 렌더러는 아직 LUT를 자동으로 걸지 않는다. 클립을 미리 LUT 처리해 media_url로 쓰거나, 렌더 후 ffmpeg lut3d를 한 번 더 건다.

## 한계

- 여러 video 트랙의 겹침(PIP, 오버레이)은 렌더러가 처리하지 않는다. 주 트랙 하나만 렌더한다.
- 색 보정(LUT)과 키프레임 애니메이션은 지원하지 않는다. 필요하면 ffmpeg 필터를 직접 추가한다.
- xfade의 slide/wipe 방향은 `direction`으로 고른다. iris는 in/out만 반영한다.
