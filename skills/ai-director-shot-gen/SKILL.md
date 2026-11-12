---
name: ai-director-shot-gen
description: Use when turning a storyboard shot into generation jobs — choosing how to generate (Codex image keys and edits, LTX/Wan image2video with start/end keys, voice, music), writing keyframe and motion prompts, managing shot versions and the active version, and gating paid generations behind user approval. 한국어 트리거는 샷 생성, 컷별 프롬프트, 이미지투비디오, 레퍼런스 영상 생성, 다시 생성, 버전 관리, 영상 프롬프트 작성. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 샷 생성 (Shot Generation)

생성 결과는 샷의 **version**으로 붙는다. 이전 version은 지우지 않는다.

## 1. 방식 고르기

| 샷 성격 | 1단계 | 2단계 |
|---|---|---|
| 얼굴이 크게 나오는 인물 컷(클로즈업·미디엄) | 키프레임 + 끝 키(내장 image_gen) | LTX 첫·끝 키(`ltx_remote.py --end-image`) |
| 대사 컷(입이 보임) | 음성 확정 → 키·끝 키 | LTX 첫·끝 키 + `--audio` |
| 얼굴이 작고 공간을 지나는 큰 동작 | 키프레임 | 시작 1장 image2video (`model-capabilities.md`에서 모델 선택) |
| 인물 2명 이상 | 두 인물이 모두 들어간 키프레임(더티 싱글 포함) | 위 행의 얼굴 크기·동작 조건으로 고른다(인원수만으로 정하지 않음) |
| 정지 사진·그림 인서트 | 키프레임 | ffmpeg zoompan(사진 속이 움직이지 않게) |
| 움직일 것이 비·작은 광원뿐인 와이드 | 키프레임 | 작품이 합성으로 정한 효과는 합성. 그 밖에는 모델 표 확인(Wan은 비·작은 광원 실패 확인됨) |
| 인물이 없는 풍경 | 키프레임 | image2video (현재 래퍼는 `--image` 필수. text2video는 로컬 실행 경로 미확인) |
| 내레이션·대사 | 대사 확정 | 음성 생성(고정 voice_id) |
| 배경음악 | 무드·BPM·길이 결정 | 음악 생성 또는 라이선스 음원 (기본·실패 기록: `ai-director-edit/references/audio-generation.md`) |

모델별로 확인된 능력·실패·시간은 [model-capabilities.md](references/model-capabilities.md)에 있다. 표에 없는 조합은 미확인으로 다룬다.

## 2. 프롬프트 작성

**키프레임 생성 전 입력.** 새 컷이나 시선·연결을 바꾸는 컷은 `ai-director-scene-direction`의 scene.direction과 `ai-director-cinematography` 0·2-1절의 shot.staging/cut_link를 먼저 읽는다. 단독 컷 요청도 기존 앞뒤 컷이 있으면 그 연결을 포함한다. 시선 목표·높이·대화축·카메라·관객 관심점의 관계가 미확정이면 해당 키를 만들기 전에 블록아웃 설계를 보완한다. 이 단계의 계획 점검은 실제 영상 검수 pass가 아니다.

**키프레임(이미지)** 구조. 줄 순서를 지킨다(AI 슬롭 방지 근거는 `<skills>/ai-director-consistency/references/anti-slop.md`):
```
1. 형식: 작품 화면비의 문장(`ai-director/references/aspect-ratios.md`). 예: "Landscape 16:9 single film frame." / "Portrait 9:16 single film frame." / 2.39:1은 16:9 + 가운데 띠 구도 문장
2. Image roles: character_image1 = identity (face) — match exactly / character_image2 = costume only /
   env_image1 = THE LOCATION: reproduce this exact place, look, colors, lighting / object_image1 = <prop>
3. 블로킹·카메라: 인물이 공간 어디에(카메라에서 몇 m, 3분할 어느 쪽, 몸 방향) + 샷 크기/앵글/렌즈
   + "physically inside the space at the correct scale" + 전경 가림(어깨, 셔터 가장자리 등)
   + 시선 목표의 실제 위치·높이와 화면상 방향(shot.staging에서), 다음 컷으로 관심을 넘길 대상의 화면 위치
4. 한 행동: 컷의 시작 상태와 다음 행동이 읽히는 순간. 감정 단어 대신 자세·지정 목표를 향한 시선·손으로 쓴다
5. 앵커 원문: 캐릭터 / 오브젝트 / 월드 + 상태(젖음 등)
6. LIGHTING: 장면의 실제 광원마다 위치와 닿는 부위, 마지막에 "No other light."
7. LOOK 블록(anti-slop.md 3절 원문, 글자 그대로) + negative
```
- 참조: 얼굴 기준(`ref_images[0]`) → `character_image1`, 전신 의상 기준 → `character_image2`, 룩 확정 때 밝기 보정한 배경 기준 → `env_image1`. 옛 룩의 씬 시트는 넣지 않는다(질감이 옮는다). 5장 이내.
- `cinematic`, `melancholic`, `neon glow`, `teal-and-amber`, `wet reflections everywhere` 같은 분위기 단어를 쓰지 않는다.
- **룩 확정 게이트**(`ai-director-consistency` 1-1)를 통과하기 전에는 키프레임을 대량으로 만들지 않는다.
- **밤 실외 키·판**은 `<skills>/ai-director-consistency/references/anti-slop.md` 4-8을 따른다: 광원마다 빛이 닿는 범위와 그 밖의 어둠을 쓰고, 생성 뒤 도로 밝기를 선형 휘도로 재서 등 아래 대비 감쇠를 확인한다. 전체 노출만 낮추지 않는다.

**키프레임 절차 (필수, 2026-11-08 사용자 결정).** 키를 만들 때마다 [references/keyframe-procedure.md](references/keyframe-procedure.md)를 처음부터 따른다. 순서만 적으면:
0 장소를 Blender로 먼저 설계(세트 없는 장소의 키는 만들지 않음) → 1 실제 광원만 켠 조명 가이드 렌더, 인물 밝은 면 한 줄 → 2 가이드를 `LIGHTING GUIDE`로 넣고 원판에서 한 번만 편집, 요구를 프롬프트/그림/보정으로 나눔, 후보 3~4장, `precheck_key.py` 사전 점검 → 3 키마다 새 `keyframe-reviewer`로 채점(만든 쪽이 통과시키지 않음) → 4 가장 작은 수단으로 고치기, **최대 3회** → 5 PASS이고 절차를 지킨 키만 사용자에게. 최종 판정은 사용자다(루트 `CLAUDE.md` 5절).

**영상(모션)** 프롬프트는 키 생성 전에 확정한 `ai-director-cinematography`의 촬영 설계와 6절 `[camera]` 요약을 이어받는다. 샷 크기·렌즈·방향을 이 단계에서 임의로 바꾸지 않는다. 샷 연결(루트 `CLAUDE.md` 3절)과 생성 방식(이 문서 1·4절)은 실제 모델·작품 규칙에 맞춰 확인한다. 인물의 시선이 바뀌면 대상과 순서를 쓴다. 정체성 묘사는 참조 이미지가 맡으므로 프롬프트에는 **일어나는 일만** 쓴다. 형식은 모델별 레시피를 따른다: LTX(기본) [references/ltx.md](references/ltx.md), Wan [references/wan.md](references/wan.md).

규칙:
- 한 샷에는 행동 하나만 넣는다. 끝 상태는 story.json의 `end_state`와 같아야 한다.
- 카메라 용어는 하나로 고정한다. 예: `slow push-in`, `static`, `handheld follow`, `orbit left`.
- 피할 것과 대안:
  - 군중 증식 → 와이드를 따로 찍거나 실루엣으로 처리
  - 정밀한 손동작 → 결과 인서트로 대체
  - 화면 속 긴 글자 → 자막
  - 여러 명이 동시에 말하는 장면 → 컷을 나누고 음성은 나중에 입힘
- 프롬프트 언어는 쓰는 도구에 맞춘다. 영어가 무조건 낫다고 가정하지 않는다.

예시와 샷 표 작성법은 [prompt-examples.md](references/prompt-examples.md)에 있다.

## 3. 승인 게이트 (필수)

생성 요청을 보내기 전에 아래 표를 보여주고 승인을 받는다. Codex에서는 선택지 질문(번호 선택지 2~4개, 추천 표시, 답을 받을 때까지 멈춤)으로 묻는다.

```
[generation_starting]
| 대상 | 모드 | 모델 | 개수 | 예상 비용/시간 |
| refs: ch_mina 시트 | text2image | (도구) | 3 | 도구 문서 기준 |
| S1-1 | image→video | (도구) | 1 | … |
합계: N건 / 예상 X
```

승인 범위를 넘는 재시도나 추가 생성은 다시 묻는다. 게시나 업로드는 절대 자동으로 하지 않는다.

## 4. 실행과 기록

### 기본 생성 도구: Codex 내장 image_gen

이미지는 Codex 내장 `image_gen` 도구로 만든다(GPT Image 계열, 참조 이미지 여러 장 가능). OpenArt Smart Shot이 시트를 만드는 구조와 같다. **영상 생성은 없다.**

| 작업 | 실행 |
|---|---|
| 참조 시트, 키프레임, 씬 프로덕션 시트, 이미지 수정 | 내장 `image_gen` (아래 절차) |
| 영상 (video 모델이 없을 때) | `<skills>/ai-director-shot-gen/scripts/animate_still.py`로 키프레임에 카메라 무브를 준 애니매틱 |
| 체인용 마지막 프레임 | ffmpeg (`ai-director-consistency` 3절) |
| 밤 장면 노출 낮추기(룩 확정·렌더) | `<skills>/ai-director-shot-gen/scripts/night_exposure.py` (광원 하이라이트 유지, `--compare`로 단계 비교) |

**image_gen 호출 절차** — 일관성은 앵커 원문에 달려 있으므로 프롬프트를 확정한 뒤 **한 글자도 바꾸지 않고** 보낸다.
1. 참조 이미지를 라벨과 함께 정한다: `character_image1..3`, `env_image1`, 소품 `object_image1`. 이번 작업에서 처음 다루는 이미지는 `view_image`로 한 번 확인한다.
2. 프롬프트 파일 `stories/<slug>/prompts/<이름>.txt`를 먼저 쓴다. 맨 앞 줄은 라벨 범례다: `Reference images: image 1 = character_image1; image 2 = env_image1.` 본문에서는 라벨로 각 이미지를 가리키고, 바이블 앵커는 원문 그대로 넣는다.
3. 그 파일 내용을 **그대로** `image_gen`의 `prompt`로 보낸다. 번역·요약·보강·재구성하지 않는다. 내장 imagegen 스킬의 프롬프트 보강(prompt augmentation)이나 공용 프롬프트 스키마를 이 작업에 적용하지 않는다. `referenced_image_paths`에는 범례와 **같은 순서**로 절대경로를 넣는다. 새 이미지면 참조를 생략한다. `transparent_background`는 배경 제거가 필요할 때만 true.
4. 결과 파일을 `stories/<slug>/...` 목표 경로로 **복사**한다. 기존 파일을 덮어쓰지 않고 `-v2`처럼 새 버전 이름을 쓴다.
   - 경로는 도구 결과에 나온 것을 쓴다.
   - 결과에 경로가 없으면 `$CODEX_HOME/generated_images`(Codex 홈 아래)에서 이번 호출 뒤에 생긴 PNG를 찾는다. 정확히 한 장이면 `view_image`로 확인하고 복사한다. 0장이거나 여러 장이면 추측하지 않고 실패로 기록한다.
5. 도구가 실패하면 version에 `status:"failed"`, 거절이면 `status:"refused"`와 사유를 기록하고, 다시 시도할지 사용자에게 묻는다.

`<skills>/ai-director-consistency/scripts/build_sheet_prompt.py`가 출력하는 `--ref "label=path"` 목록은 1~3단계의 라벨과 경로로 그대로 쓴다(앞에서부터 image 1, 2, …).

```bash
python "<skills>/ai-director-shot-gen/scripts/animate_still.py" \
  stories/<slug>/media/S1-1-key-v1.png stories/<slug>/media/S1-1-v1.mp4 --dur 5 --move push-in
```

- 이미지는 한 장에 수십 초~몇 분이 걸린다. image_gen은 한 번에 하나씩 호출하고 결과를 확인한 뒤 다음으로 넘어간다. 애니매틱(ffmpeg)은 서로 독립된 샷끼리 병렬로 돌려도 된다.
- 시드와 해상도 옵션이 없다. 화면비와 구도는 프롬프트에 쓴다(예: "Landscape 16:9 frame").
- 비용은 사용자의 Codex(ChatGPT) 사용량에서 나간다. 3절 승인 표의 "모델"에는 `codex image_gen`, 비용 칸에는 "Codex 사용량 N회"로 적는다.
- 참조는 5장 이내로 넣는다.
- 애니매틱 클립은 version의 `model`을 `ffmpeg-zoompan`으로, `mode`를 `image2video`로 적고 `notes`에 "animatic"이라고 남긴다. 나중에 영상 모델이 생기면 같은 키프레임으로 새 version을 만든다.
- `--move`는 샷의 `camera`에 맞춘다: push-in / pull-out / pan-left·right·up·down / static.
- 키프레임 화면비가 출력과 다르면 경고가 나온다. 키프레임을 출력 화면비로 다시 만들거나 `--fit pad|blur`를 쓴다(기본 crop은 가장자리를 잘라낸다).


**검수와 기록** (정지 프레임 중심 검수를 시간축 검수로 바꿈, 2026-11-08)
- 생성 **전에** shot `success_criteria`(시작·진행·완료·연속성·정체성·카메라)를 관찰 가능한 문장으로 적는다. 방식 선택은 [model-capabilities.md](references/model-capabilities.md)를 본다.
- 생성 **뒤에** 리뷰어(새 컨텍스트 하위 에이전트 또는 별도 `codex exec` 세션, 지시문은 `<skills>/ai-director-consistency/references/video-reviewer.md` 전문)가 `<skills>/ai-director-consistency/references/video-rubric.md`로 검수한다: `review_video.py`로 0.5초 간격 접촉 시트·얼굴 스트립·움직임/밝기/이음매 후보를 만들고, 후보 구간을 촘촘히 다시 보고, 시간대별 결함과 판정(pass/revise/hold)을 version `review`에 남긴다. 만든 쪽이 스스로 합격시키지 않는다.
- 영상도 개선(재생성·후처리 수정)은 **최대 3회**다. 3회째에도 pass가 아니면 멈추고 사용자에게 보고한다. 사용자가 명시적으로 지시한 재생성(예: "시드 바꿔 재생성", "프롬프트 정리해서 넣어봐")은 회차에 넣지 않는다(사용자 2026-11-10).
- 정지 프레임과 수치만으로 동작을 합격시키지 않는다. 움직임의 자연스러움은 사용자가 재생으로 본 판정이 있어야 pass다. 그 전에는 사용자에게 "검수 후보: 미확인 항목 …"으로 보낸다.
- 결과는 story.json version(`kind:"video"`, `status`, `notes`에 설정과 문제, `review`에 검수 결과)에 기록한다. 실패는 `failed`, 대체는 `superseded`.
- 애니매틱 클립도 같은 절차로 검수한다. 카메라 무브만 있으므로 `success_criteria`는 카메라·정체성·연속성 중심으로 쓴다.
- 사용자에게는 한 컷씩 보낸다.

### 그 밖의 도구

- 다른 로컬 도구(ComfyUI, 로컬 SD 등)나 API가 있으면 실행하고, 결과를 `stories/<slug>/media/`에 저장한다.
- 생성 도구가 없으면 샷별 프롬프트 패키지(키프레임 프롬프트, 영상 프롬프트, 참조 이미지 목록, 설정)를 출력한다. 사용자가 생성해서 `media/`에 넣으면 그 파일을 version으로 등록한다.
- version 레코드는 아래 형식이다.
  ```json
  {"id":"S1-1-v2","kind":"video","model":"…","mode":"image2video","prompt":"…","seed":null,
   "inputs":["media/S1-1-key-v1.png"],"media_url":"media/S1-1-v2.mp4","status":"done","notes":"v1은 우산 손이 바뀜"}
  ```
- `review.status`가 `pass`인 version만 `active_version_id`로 지정한다(`validate_story.py --stage export`가 막는다). 그 샷의 타임라인 클립에서는 `media_url`만 갈아끼우고 클립 ID와 위치는 유지한다. 새 영상 길이가 다르면 source_out_ms를 조정한다.
- 실패나 거절은 `status:"failed"`와 사유를 남긴다. 같은 실패를 반복하지 않도록 다음 시도의 변경점을 notes에 적는다.

## 5. 다시 생성할 때

사용자가 "@S2-3 다시"라고 하면 순서는 아래와 같다.

1. 무엇이 문제인지 한 줄로 확인한다(정체성, 동작, 카메라, 아티팩트).
2. `ai-director-consistency` 5절의 수정 순서에 따라 가장 작은 수단을 고른다.
3. 새 version을 만든다. 이전 version은 삭제하지 않는다. 사용자가 이전 버전으로 되돌릴 수 있어야 한다.
