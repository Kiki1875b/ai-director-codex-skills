---
name: ai-director-consistency
description: Use when an AI video needs the same character, outfit, prop, location and look across many shots — building a character/world/style bible with anchor sentences and reference sheets, keyframe-first generation, multi-reference video modes, last-frame chaining and a continuity ledger, plus drift review and fixes. 한국어 트리거는 캐릭터 일관성, 얼굴 고정, 같은 인물 유지, 연속성, 레퍼런스 시트, 바이블, 샷 간 이어짐. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 일관성 (Consistency)

캐릭터, 오브젝트, 배경을 별도 자산(기준 이미지와 앵커 문장)으로 두고, 샷을 생성할 때 이 자산을 참조 입력으로 넣는다. 결과는 story.json의 `bible`과 샷 필드에 기록한다. 캐릭터는 학습하지 않고 참조 이미지 묶음으로 유지한다. 참조는 라벨(`character_image1..3`, `env_image1`, `object_image1`)을 붙여 넣고, 프롬프트에서 그 라벨로 각 이미지의 역할을 지정한다. 한 요청에서 서로 다른 이미지에는 서로 다른 라벨을 붙이고, 프롬프트의 라벨이 실제 첨부 순서와 맞는지 확인한다.

## 0. 기준 자산과 시트

### 시트 만들기 (권장 기본값)

1. 인물마다 **정면 전신, 흰 배경** 의상 기준 1장과 **얼굴 기준 사진**(배우 프로필 톤 머리·어깨) 1장을 확정한다. 전신만 있으면 얼굴이 작아 모델이 아이돌 얼굴을 지어낸다. `ref_images = [face, front, sheet]`, 키프레임에서는 `character_image1`=얼굴, `character_image2`=의상. 만드는 법은 [anti-slop.md](references/anti-slop.md) 2-1.
2. 씬마다 내장 image_gen(다중 참조)으로 **프로덕션 시트 1장**을 만든다.
   - 참조로 인물 기준 이미지(최대 3)와 배경 1장을 넣는다.
   - 프롬프트: "이 씬의 샷 N개를 패널로 나눈 스토리보드 시트, 각 패널에 샷 번호, 같은 인물과 같은 의상, 인물은 `character_image1`, 배경은 `env_image1`".
3. 시트를 바이블과 비교 검수한다. 틀린 패널은 시트 수정(edit)으로 고친다.
   - 시트 형식(섹션 구성)과 생성 명령은 [production-sheet.md](references/production-sheet.md)에 있다. 프롬프트는 `scripts/build_sheet_prompt.py <story.json> <scene>`으로 만든다. 영화 전체를 어두운 보드 한 장에 담으려면 `ALL --layout film-bible`을 쓴다. 캐릭터별·소품·장소·콘티 시트를 따로 뽑으려면 `--layout character|object|location|storyboard`를 쓴다(production-sheet.md의 '개별 시트 레이아웃').
4. 시트와 기준 이미지를 참조로 컷별 키프레임을 만들고, 그 키로 image2video를 생성한다(`ai-director-shot-gen` 1절).

## 1. 앵커 3종을 정의한다

모든 등장 요소(캐릭터, 오브젝트, 월드)는 아래 앵커를 갖는다.

| 앵커 | 내용 | 규칙 |
|---|---|---|
| **텍스트 앵커** | 바뀌지 않는 시각 특징 6~10개를 한 문장으로 쓴다. 나이대, 체형, 헤어, 얼굴 특징, 의상 색과 재질, 시그니처 소품 순서다 | 모든 프롬프트에 **글자 그대로** 붙인다. 동의어로 바꾸지 않는다. 감정, 행동, 조명은 넣지 않는다 |
| **시각 앵커** | 참조 시트 이미지 | 중립 배경과 균일한 조명에서 정면, 3/4, 측면, 전신, 표정 2~3개를 그린다. 월드는 와이드 1장과 주요 각도 2장 |
| **음성 앵커** | voice_id | 말하는 캐릭터만 정한다. 한 번 정하면 바꾸지 않는다 |

스타일도 앵커 하나로 고정한다. 매체/필름 룩, 렌즈 경향, 색 보정, 질감, 금지 요소를 담고 모든 프롬프트 끝에 붙인다. 의상이 바뀌는 이야기라면 `ch_mina@raincoat`, `ch_mina@dress`처럼 **변형을 별도 엔트리**로 만든다. 프롬프트로 "옷만 바꿔"라고 지시하지 않는다.

템플릿은 [bible-template.md](references/bible-template.md)에 있다.

**스타일 앵커에 `cinematic`, `melancholic`, `teal-and-amber`, `neon` 같은 분위기 단어를 쓰지 않는다.** 이런 단어가 과포화·사방 발광·화보 얼굴(AI 슬롭)의 주원인이다. 대신 실제 필름·렌즈·질감과 "빛은 장면의 실제 광원에서만"을 쓴다. 월드 앵커는 **실제 장소 핸드북**(실제 지명, 그 장소에 있는 사물과 광원, 없는 것)에서 쓴다. 승인된 location 레퍼런스가 있으면(`bible.worlds[].reference_links`, `ai-director-reference`) 그 take/avoid를 핸드북에 옮긴다. 레퍼런스 사진을 `env_image`로 넣어도 되지만 그 질감·색이 옮고(anti-slop 2-3), Blender 설계·블록아웃을 대신하지 않는다. 전체 처방은 [anti-slop.md](references/anti-slop.md).

## 1-1. 룩 확정 게이트 (키프레임 대량 생성 전 필수)

**먼저 룩 인터뷰를 한다**(작품마다, [anti-slop.md](references/anti-slop.md) 0절. 사전 질문 1·2·6·7번은 ai-director 2-2 레퍼런스 단계에서 이미 했으면 다시 묻지 않는다): 레퍼런스, 사실감↔화사함, 얼굴 톤, 밝기, 색 룩·LUT, 장소 실재감, 금지 룩. 아래 기본값은 답이 없을 때만 쓴다.

바이블 기준 이미지가 준비되면 키프레임을 돌리기 전에 **스타일 프레임 2장**(가장 어두운 씬, 가장 따뜻한/밝은 씬)을 만들어 사용자 승인을 받는다.
- 참조는 얼굴·의상·배경·소품만 넣고 옛 룩의 시트는 넣지 않는다.
- 밝기는 `ai-director-shot-gen/scripts/night_exposure.py --compare 0.9,1.5`로 단계 비교를 보여주고 고르게 한다(로컬, 무료).
- 피드백은 하나씩 온다(얼굴 → 톤 → 광원·배우 위치 → 장소 → 밝기). 지적된 것만 바꿔 1~2장으로 다시 보여준다.
- 승인되면 `bible.style`에 `anchor`, `negative`, `look_frames`, `grade`를 기록하고 이전 앵커는 `notes`에 남긴다.
절차와 LOOK 블록 원문은 [anti-slop.md](references/anti-slop.md) 3~4절.

## 2. 키프레임을 먼저 만든다

텍스트만으로 영상을 만들면 샷마다 얼굴과 의상이 달라진다. 순서는 아래와 같다.

키 생성 전에는 `ai-director-scene-direction`의 장면 비트와 `ai-director-cinematography` 0·2-1절의 시선·카메라·관객 관심점 설계를 읽는다. 같은 인물·장소라는 사실만으로 앞뒤 컷의 시선 연결이 맞지는 않는다. 단독 키가 통과해도 인접 키는 `ai-director-cinematography/references/eyeline-continuity.md`로 따로 점검한다.

1. **참조 시트 생성.** text2image로 만든다. 마음에 드는 1장을 고르고 나머지 각도는 image2image로 만든다.
2. **샷 키프레임.** image2image나 다중 참조 이미지 모델로 만든다. 등장 요소의 참조 시트를 넣고, 프롬프트에는 앵커, 장소, 한 행동, 구도, 조명, 스타일을 쓴다.
3. **키프레임을 바이블과 비교 검수한다.** 영상보다 이미지가 싸고 빠르므로 여기서 걸러낸다.
4. **image2video.** 영상 프롬프트에는 정체성을 다시 쓰지 않고 **움직임만** 쓴다.

## 3. 상황별 일관성 장치

| 상황 | 방식 | 방법 |
|---|---|---|
| 인물 1명, 일반 컷 | image2video | 승인된 키프레임을 첫 프레임으로 쓴다 |
| 인물 여러 명이나 소품이 중요한 컷 | 모두 들어간 키프레임 + `ai-director-shot-gen` 1절 조건별 선택 | 인물별 기준·소품·배경을 참조로 넣어 모두 들어간 키를 만든다. 끝 키가 필요한 방식이면 그 시작 키에서 편집한다 |
| 같은 동작이 이어지는 컷 | 체인 | 이전 샷의 **마지막 프레임**을 다음 샷의 첫 프레임으로 쓴다. `chain_from`에 기록한다 |
| 얼굴, 소품 일부만 틀림 | 후처리 | 얼굴 디테일러, 영역 합성, VACE 영역 마스크 등으로 그 부분만 고친다(`ai-director-shot-gen`) |
| 대사 컷 | 음성 + image2video | 정해진 voice_id로 음성을 먼저 만들고, 그 음성을 넣어 생성한다(루트 CLAUDE.md 2절) |

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
4. 부분 편집·후처리로 그 부분만 수정
5. 모델 교체

프롬프트에 형용사를 계속 덧붙이는 방식은 효과가 거의 없다. 실패한 시도는 version에 `notes`로 남긴다.

## 하지 말 것

- 앵커 문장을 샷마다 다르게 다시 쓰지 않는다.
- 한 컷에 같은 인물을 여러 번 등장시키지 않는다. 증식 위험이 있다.
- 읽혀야 하는 글자를 생성 화면 안에 넣지 않는다. 자막으로 처리한다.
- 모델별 참조 장수 제한이나 가격을 추측으로 단정하지 않는다. 쓰는 도구의 문서를 확인한다.
- 룩 확정(1-1) 전에 키프레임을 대량으로 만들지 않는다.
- AI 느낌을 후처리(채도↓, 그레인, 블랙 리프트)로 지우려 하지 않는다. 입력(앵커·기준 이미지)을 고친다.
- 사실감을 위해 얼굴에 잡티·점·다크서클을 과하게 넣지 않는다. 장르 주인공은 매력적이어야 한다("못생김"으로 거절된 사례).
