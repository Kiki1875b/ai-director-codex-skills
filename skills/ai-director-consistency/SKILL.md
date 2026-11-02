---
name: ai-director-consistency
description: Use when an AI video needs the same character, outfit, prop, location and look across many shots — building a character/world/style bible with anchor sentences and reference sheets, keyframe-first generation, multi-reference video modes, last-frame chaining and a continuity ledger, plus drift review and fixes. 한국어 트리거는 캐릭터 일관성, 얼굴 고정, 같은 인물 유지, 연속성, 레퍼런스 시트, 바이블, 샷 간 이어짐. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 일관성 (Consistency)

OpenArt Director는 캐릭터, 오브젝트, 배경을 별도 자산으로 저장해 둔다. 자산 타입은 `director_character`, `director_object`, `director_background`이고, 월드는 `/api/world/{prompt,photo,pano}`로 만든다. 샷을 생성할 때 이 자산을 참조 입력으로 넣는다. 아래는 그 방식을 일반 도구로 재현하는 절차다. 결과는 story.json의 `bible`과 샷 필드에 기록한다.

## 0. OpenArt가 실제로 쓰는 장치 (로그인 후 클라이언트 코드에서 확인, 2026-11-02)

Director 에이전트 트래픽은 무료 계정에서 막혀 보지 못했다. 아래는 로그인 후 받은 JS 번들의 스키마, 기능 정의, 에이전트용 도구 설명에서 확인한 내용이다. 서버 안의 프롬프트는 보이지 않는다.

1. **캐릭터는 학습하지 않는다. 참조 이미지 묶음이다.**
   - `character:createCharacter`는 `{name, backgroundStory, imageUrls[], voice, flowType: image|upgrade|description|form}`를 받고, 비용은 0 크레딧이다.
   - 업로드 화면의 팁: "정면을 보는 전신 1명, 흰 배경이 영상에서 가장 일관성이 좋다."
   - 옛 방식(`createImageV1`: characterWeight 0.8, strictCharacterFeatures, steps, cfg)도 남아 있지만, 현재 경로는 참조 이미지를 생성 모델에 그대로 넘기는 방식이다.
2. **스마트샷(Smart Shot) = 프로덕션 시트 → 시트를 참조로 영상 생성.** Director는 이 폼을 `director-create` 범위에 그대로 넣어 쓴다.
   - 입력: `sceneDescription`(최대 5000자), `characterReferenceImageUrls`(최대 3), `environmentReferenceImageUrl`(1)
   - 1단계 `smart-shot:generate`
     - GPT Image 2(1536×1024)로 "production-doc sheet"와 "directing prompt"를 만든다.
     - 시트에는 인물, 배경, 샷 구성이 한 장에 담긴다. 한 번의 생성이므로 모든 칸의 인물이 같다.
     - 시트는 `smart-shot:revise`로 지시문 수정할 수 있다.
   - 2단계 `smart-shot:generate-video`
     - 시트와 참조를 Seedance 2(standard) 또는 2.5(high)의 element2video에 넣는다.
     - 기본값은 16:9, 480p, 20초다.
   - 참조 라벨은 `character_image1..3`, `env_image1`(또는 `Char1`, `Env1`)이다. 설명문 안의 `@이름`을 이 라벨로 바꿔서 보낸다. 규칙은 "인물·제품·배경마다 고유한 @label"이다.
3. **텍스트가 이미지 역할을 지정한다.**
   - 실제 기록: 사용자가 이전에 만든 이미지는 `nano-banana-2:image2image`에 `image_urls` 3장(label image1~3)을 넘겼고, 프롬프트가 "from the reference photo …"로 각 이미지를 가리켰다.
   - 번들의 예시 프롬프트: `[@Image 1] and [@Image 2] meet in a cafe`, `@imageA as character, @imageC as background`.
4. **에이전트용 도구 규칙** (에이전트가 읽는 도구 설명에 있는 문장 요지)
   - image-to-video는 이미지를 "절대 기준"으로 삼아 구도를 그대로 움직인다. 인물을 새 장면에 다시 배치하려면 text-to-video의 참조 경로(element2video)를 쓴다.
   - multi-view(3×3 9컷 앵글)는 장면 커버리지용이다. 캐릭터 시트나 정면·측면·후면 시트에는 쓰지 않는다. 그런 시트는 피사체 이미지를 참조로 넣은 text-to-image로 만든다.
   - 캐릭터의 새 앵글 1장은 camera-angle-control, 같은 그림 안의 부분 수정은 edit-image를 쓴다.
   - 영상 속 인물이 틀렸으면 replace-character나 face-swap을 쓴다.
5. **광고 파이프라인도 같은 패턴이다.** LLM이 구조화 출력으로 `characterSheets`(사진이 있는 인물마다 시트 프롬프트 1개)와 `productSheetPrompt`, `videoPrompts`를 만든다. 그다음 GPT Image로 시트를 만들고, Seedance 2.5 element2video로 영상을 만든다.

**요약:** OpenArt의 일관성은 다음 세 가지로 이루어진다.
- 참조 이미지를 정면 전신, 흰 배경으로 받는다.
- 한 장의 시트 안에서 인물과 장면을 동시에 그린다.
- 시트와 참조를 라벨로 묶어 참조형 영상 모델에 넣는다.

텍스트 앵커는 보조 수단이다. 아래 절차는 이 방식을 다른 도구로 재현하는 방법이다.

### 시트 방식 재현 (권장 기본값)

1. 인물마다 **정면 전신, 흰 배경** 기준 이미지 1장을 확정한다(`ref_images[0]`).
2. 씬마다 다중 참조 이미지 모델(GPT Image, Nano Banana 등)로 **프로덕션 시트 1장**을 만든다.
   - 참조로 인물 기준 이미지(최대 3)와 배경 1장을 넣는다.
   - 프롬프트: "이 씬의 샷 N개를 패널로 나눈 스토리보드 시트, 각 패널에 샷 번호, 같은 인물과 같은 의상, 인물은 `character_image1`, 배경은 `env_image1`".
3. 시트를 바이블과 비교 검수한다. 틀린 패널은 시트 수정(edit)으로 고친다.
   - 시트 형식(섹션 구성, 실제 데모 값)과 생성 명령은 [production-sheet.md](references/production-sheet.md)에 있다. 프롬프트는 `scripts/build_sheet_prompt.py <story.json> <scene>`으로 만든다. 영화 전체를 어두운 보드 한 장에 담으려면 `ALL --layout film-bible`을 쓴다.
4. 시트와 인물 기준 이미지를 참조형 영상 모델(element2video / reference2video)에 넣고, 샷별 움직임 프롬프트로 생성한다.
   - 특정 패널 구도를 그대로 써야 하면 그 패널을 잘라 image2video의 첫 프레임으로 쓴다.

## 1. 앵커 3종을 정의한다

모든 등장 요소(캐릭터, 오브젝트, 월드)는 아래 앵커를 갖는다.

| 앵커 | 내용 | 규칙 |
|---|---|---|
| **텍스트 앵커** | 바뀌지 않는 시각 특징 6~10개를 한 문장으로 쓴다. 나이대, 체형, 헤어, 얼굴 특징, 의상 색과 재질, 시그니처 소품 순서다 | 모든 프롬프트에 **글자 그대로** 붙인다. 동의어로 바꾸지 않는다. 감정, 행동, 조명은 넣지 않는다 |
| **시각 앵커** | 참조 시트 이미지 | 중립 배경과 균일한 조명에서 정면, 3/4, 측면, 전신, 표정 2~3개를 그린다. 월드는 와이드 1장과 주요 각도 2장 |
| **음성 앵커** | voice_id | 말하는 캐릭터만 정한다. 한 번 정하면 바꾸지 않는다 |

스타일도 앵커 하나로 고정한다. 매체/필름 룩, 렌즈 경향, 색 보정, 질감, 금지 요소를 담고 모든 프롬프트 끝에 붙인다. 의상이 바뀌는 이야기라면 `ch_mina@raincoat`, `ch_mina@dress`처럼 **변형을 별도 엔트리**로 만든다. 프롬프트로 "옷만 바꿔"라고 지시하지 않는다.

템플릿은 [bible-template.md](references/bible-template.md)에 있다.

## 2. 키프레임을 먼저 만든다

텍스트만으로 영상을 만들면 샷마다 얼굴과 의상이 달라진다. 순서는 아래와 같다.

1. **참조 시트 생성.** text2image로 만든다. 마음에 드는 1장을 고르고 나머지 각도는 image2image로 만든다.
2. **샷 키프레임.** image2image나 다중 참조 이미지 모델로 만든다. 등장 요소의 참조 시트를 넣고, 프롬프트에는 앵커, 장소, 한 행동, 구도, 조명, 스타일을 쓴다.
3. **키프레임을 바이블과 비교 검수한다.** 영상보다 이미지가 싸고 빠르므로 여기서 걸러낸다.
4. **image2video.** 영상 프롬프트에는 정체성을 다시 쓰지 않고 **움직임만** 쓴다.

## 3. 모드별 일관성 장치

| 상황 | 모드 | 방법 |
|---|---|---|
| 인물 1명, 일반 컷 | image2video | 승인된 키프레임을 첫 프레임으로 쓴다 |
| 인물 여러 명이나 소품이 중요한 컷 | reference2video / element2video | 참조 이미지 여러 장(인물별 시트, 소품, 배경)을 넣는다. 번들에 `gemini-omni-flash:reference2video`, `byte-plus-seedance-2-5:element2video` 같은 모드가 있다 |
| 같은 동작이 이어지는 컷 | 체인 | 이전 샷의 **마지막 프레임**을 다음 샷의 첫 프레임으로 쓴다. `chain_from`에 기록한다 |
| 롱테이크 | extend | 같은 영상을 이어서 늘린다. 번들에 `:extendVideo`가 있다 |
| 얼굴, 소품 일부만 틀림 | modify | 해당 부분만 수정한다(`:modifyVideo` / `:modify-video`). 전체를 다시 만들지 않는다 |
| 대사 립싱크 | lipsync / avatar | 정해진 voice_id로 음성을 먼저 만들고 입을 맞춘다 |

마지막 프레임 추출:
```bash
ffmpeg -y -sseof -0.1 -i media/S1-1-v1.mp4 -frames:v 1 -update 1 media/S1-1-v1_last.png
```
체인을 이을 때 다음 샷의 start_state는 이 프레임에 보이는 상태와 같아야 한다.

## 4. 연속성 장부

샷마다 `start_state`와 `end_state`에 아래 항목을 적는다. 다음 샷의 start_state는 앞 샷의 end_state와 같아야 한다. 시간이나 장소가 바뀌는 의도적 컷이면 summary에 그렇다고 명시한다.

- 의상과 상태(젖음, 찢어짐 등), 손에 든 것과 어느 손인지
- 화면상 위치와 시선 방향. 180도 규칙을 지키고, 인물 A는 왼쪽, B는 오른쪽처럼 씬 안에서 고정한다
- 조명 방향, 시간대, 날씨
- 소품 상태(열림/닫힘, 양, 파손)

`validate_story.py`는 상태 필드가 빠진 곳을 경고한다.

## 5. 드리프트 검수와 수정

새 version마다 바이블 시트와 나란히 놓고 확인한다(이미지면 view_image로 직접 본다).

1. 얼굴, 헤어, 체형
2. 의상 색과 재질
3. 시그니처 소품
4. 화면 방향과 위치
5. 스타일과 색감
6. 손, 글자, 군중 같은 아티팩트

고칠 때는 작은 수단부터 쓴다.

1. 같은 설정으로 다시 생성
2. 프롬프트에서 충돌하는 형용사 제거. 앵커와 다른 묘사가 섞이면 드리프트가 생긴다
3. 참조를 강화한다. 더 가까운 각도의 시트를 쓰거나, 참조 장수를 늘리거나, 키프레임을 다시 만든다
4. modify로 부분 수정
5. 모델 교체

프롬프트에 형용사를 계속 덧붙이는 방식은 효과가 거의 없다. 실패한 시도는 version에 `notes`로 남긴다.

## 하지 말 것

- 앵커 문장을 샷마다 다르게 다시 쓰지 않는다.
- 한 컷에 같은 인물을 여러 번 등장시키지 않는다. 증식 위험이 있다.
- 읽혀야 하는 글자를 생성 화면 안에 넣지 않는다. 자막으로 처리한다.
- 모델별 참조 장수 제한이나 가격을 추측으로 단정하지 않는다. 쓰는 도구의 문서를 확인한다.
