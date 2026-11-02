---
name: ai-director-shot-gen
description: Use when turning a storyboard shot into generation jobs — choosing the mode (text2image, image2image, text2video, image2video, reference2video/element2video, extend, modify, voice, music), writing keyframe and motion prompts, managing shot versions and the active version, and gating paid generations behind user approval. 한국어 트리거는 샷 생성, 컷별 프롬프트, 이미지투비디오, 레퍼런스 영상 생성, 다시 생성, 버전 관리, 영상 프롬프트 작성. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 샷 생성 (Shot Generation)

OpenArt는 생성 기능을 `모델:모드` 형식의 ID로 부른다. 예: `gpt-image-2:text2image`, `gemini-omni-flash:image2video`, `byte-plus-seedance-2-5:extendVideo`. 생성은 비동기 작업(history ID)으로 돌고, 끝나면 샷의 **version**으로 붙는다. 이 스킬은 그 흐름을 쓰는 도구에 상관없이 재현한다.

## 1. 모드 고르기

| 샷 성격 | 1단계 | 2단계 |
|---|---|---|
| 바이블 인물이 나오는 일반 컷 | image2image(참조 시트) → 키프레임 | image2video |
| 인물 2명 이상, 또는 소품과 배경이 모두 중요한 컷 | 키프레임(선택) | reference2video / element2video (참조 여러 장) |
| 앞 샷에서 동작이 이어지는 컷 | 앞 샷 마지막 프레임 추출 | image2video (첫 프레임으로 사용) |
| 롱테이크, 길이 연장 | — | extend |
| 일부만 틀린 기존 영상 | — | modify (수정 지시만) |
| 인물이 없는 풍경, 인서트, 추상 이미지 | — | text2video도 허용 |
| 내레이션, 대사 | 대사 확정 | 음성 생성(고정 voice_id) → 필요하면 lipsync |
| 배경음악 | 무드, BPM, 길이 결정 | 음악 생성 또는 라이선스 음원 |

어떤 모델과 모드를 쓸 수 있는지는 사용자가 가진 도구로 정한다. 쓸 수 있는 모델, 샷 최대 길이, 가격은 그 도구의 현재 문서에서 읽는다. 기억이나 추측으로 단정하지 않는다.

## 2. 프롬프트 작성

**키프레임(이미지)** 구조:
```
[캐릭터 앵커 원문] + [오브젝트 앵커] + [월드 앵커] +
[한 행동: 가장 잘 읽히는 순간에서 멈춘 상태] + [샷 크기/앵글/렌즈] + [조명/시간대] + [스타일 앵커]
negative: [style.negative]
```

**영상(모션)** 구조. 정체성 묘사는 참조 이미지가 맡으므로 프롬프트에는 **움직임만** 쓴다.
```
[무엇이 어떻게 움직이는지: 시작 상태 → 끝 상태] + [카메라 움직임] + [속도/리듬] +
[환경 움직임: 비, 연기, 천] + [소리 단서(오디오를 지원하는 모델만)]
```

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

### 그 밖의 도구

- 다른 로컬 도구(ComfyUI, 로컬 SD 등)나 API가 있으면 실행하고, 결과를 `stories/<slug>/media/`에 저장한다.
- 생성 도구가 없으면 샷별 프롬프트 패키지(키프레임 프롬프트, 영상 프롬프트, 참조 이미지 목록, 설정)를 출력한다. 사용자가 생성해서 `media/`에 넣으면 그 파일을 version으로 등록한다.
- version 레코드는 아래 형식이다.
  ```json
  {"id":"S1-1-v2","kind":"video","model":"…","mode":"image2video","prompt":"…","seed":null,
   "inputs":["media/S1-1-key-v1.png"],"media_url":"media/S1-1-v2.mp4","status":"done","notes":"v1은 우산 손이 바뀜"}
  ```
- 검수를 통과한 version은 `active_version_id`로 지정한다. 그 샷의 타임라인 클립에서는 `media_url`만 갈아끼우고 클립 ID와 위치는 유지한다. 새 영상 길이가 다르면 source_out_ms를 조정한다.
- 실패나 거절은 `status:"failed"`와 사유를 남긴다. 같은 실패를 반복하지 않도록 다음 시도의 변경점을 notes에 적는다.

## 5. 다시 생성할 때

사용자가 "@S2-3 다시"라고 하면 순서는 아래와 같다.

1. 무엇이 문제인지 한 줄로 확인한다(정체성, 동작, 카메라, 아티팩트).
2. `ai-director-consistency` 5절의 수정 순서에 따라 가장 작은 수단을 고른다.
3. 새 version을 만든다. 이전 version은 삭제하지 않는다. 사용자가 이전 버전으로 되돌릴 수 있어야 한다.
