# 프로덕션 시트 (OpenArt Smart Shot 형식)

OpenArt Smart Shot 공개 데모 영상에서 확인한 시트 구성을 정리한 것이다(데모 이미지는 포함하지 않는다). 데모 흐름은 아래와 같다.

- 입력: 흰 배경 정면 전신 인물 사진 1장과 배경 사진 1장
- 출력: 시트 1장
- 그 시트를 따르는 컷 영상 3개

시트는 GPT Image 2로 만든 1536×1024 가로형 1장이다. 데모 영상은 정사각형이어서 시트 오른쪽 끝이 일부 잘려 보인다. 그 부분은 추정으로 표시했다.

## 레이아웃

```
┌ 헤더 ─────────────────────────────────────────────────────────────┐
│ SHARED CHOICES / <시퀀스 제목> │ CUT COUNT: N │ COLOR PALETTE: 이름 5개 + 색 견본 5칸 │ ENVIRONMENT FINGERPRINT: 랜드마크 3~4개 │
├──────────────────────────────────────────────────────────────────┤
│ SPATIAL ANCHOR (EXPLICIT): 지형과 방위 고정 문장 + "Every storyboard cut must honor this same geography and lighting continuity." │
├ 1 CHARACTER REFERENCE ─────────────────────┬ 2 ENVIRONMENT / SET DESIGN ┤
│ 전신 FRONT · SIDE · BACK │ FACE CLOSE-UP    │ 대표 와이드 1장                  │
│                          │ SIDE CLOSE-UP    ├──────────────────────────────┤
│ COSTUME DETAILS: 의상·소품 아이템별 컷 + 이름 │ FLOOR PLAN / TERRAIN BLOCKING   │
│ PALETTE MATCH: 색 견본 5칸                   │ MAP (TOP-DOWN): 지형, 동선 점선,  │
│                                              │ 컷별 카메라 아이콘과 번호         │
├ 3 STORYBOARD (N CUTS) ────────────────────────────────────────────┤
│ [Cut 1] [Cut 2] [Cut 3] [Cut 4]  컷마다 이미지 + 아래 메타 2줄:       │
│  LENS · SHOT · DURATION / MOVEMENT · CAMERA POSITION / 설명 1~2문장   │
├ 4 LIGHTING + MOOD + STYLE NOTES ──────────────────────────────────┤
│ 조명 레퍼런스 썸네일 4개(이름 + 한 줄 설명) │ MOOD KEYWORDS 5개 │ LENS + CAMERA 규칙 목록 │
└──────────────────────────────────────────────────────────────────┘
```

## 데모 시트 실제 값 (요지)

- **헤더**
  - 제목: WILD WEST HORSEBACK SEQUENCE
  - CUT COUNT: 4
  - 팔레트: sun-bleached blue, red bandana crimson, sandstone orange, warm tan, ivory haze
- **공간 앵커**
  - 거대한 평정 메사는 서쪽 지평선에 고정한다.
  - 쌍둥이 뷰트는 먼 중앙에 둔다.
  - 층진 절벽 선반은 동쪽 전경에 둔다.
  - 트레일은 남서쪽 전경에서 북동쪽으로 뻗는다.
  - 모든 컷이 이 지리와 조명 연속성을 지킨다.
- **1. 캐릭터 레퍼런스**
  - 정면, 측면, 후면 전신
  - 얼굴 정면 클로즈업과 측면 클로즈업
  - 의상 디테일: straw hat, bandana, denim shirt, leather chaps, leather belt, black boots
  - 팔레트 매치
- **2. 환경**
  - 메사 와이드 1장
  - 탑다운 지형 블로킹 맵: WEST MESA, VALLEY FLOOR, 동선 점선, `Cut 1 (STATIC)` 카메라 아이콘
- **3. 스토리보드 (컷마다 렌즈, 숏, 길이, 움직임, 카메라 위치)**
  - Cut 1: 40mm Anamorphic, Wide Establishing, ~4s, Static, 라이더 남서쪽 높은 위치
  - Cut 2: 50mm Anamorphic, Medium-Wide, ~3s, 트레일과 평행하게 트래킹, 라이더 남쪽 낮은 위치
  - Cut 3: 75mm Anamorphic, Medium Side Profile, Static, 라이더 동쪽
  - Cut 4: 데모 영상에서 잘려 보이지 않음
- **4. 조명과 무드**
  - 조명 레퍼런스: HARD MIDDAY SUN, WARM SIDE LIGHT + DUST HAZE, SOFT BOUNCE / DESERT REFLECTION, RIM GLOW (SUNSET-ADJACENT)
  - MOOD KEYWORDS: expansive, stoic, sun-baked, heroic solitude, frontier realism
  - LENS + CAMERA: Anamorphic, Moderate…, Wide sky…, Shallow…, Natural…, Choose… (뒷부분은 잘림)

## 이 시트가 일관성을 만드는 이유

| 섹션 | 고정하는 것 | 영상 모델이 쓰는 방식 |
|---|---|---|
| 1 캐릭터 레퍼런스 | 얼굴, 3방향 체형, 의상 아이템 | 모든 컷에서 같은 인물로 그린다 |
| 팔레트, PALETTE MATCH | 색 | 컷 사이 색감이 튀지 않는다 |
| 공간 앵커, 탑다운 맵 | 방위, 랜드마크 위치, 동선 | 컷마다 배경 배치와 이동 방향이 같다(180도 규칙) |
| 3 스토리보드 메타 | 컷별 구도, 렌즈, 카메라 움직임 | 컷별 영상 프롬프트의 근거가 된다 |
| 4 조명/무드 | 빛의 방향, 질감, 톤 | 스타일 앵커 역할을 한다 |

story.json과의 대응:
- 1번 섹션 = `bible.characters[]`, `bible.objects[]`
- 2번 섹션 = `bible.worlds[]`와 씬의 `spatial_anchor`
- 3번 섹션 = `scene.shots[]`
- 4번 섹션 = `bible.style`과 씬의 `lighting`

## 만드는 법 (로컬 Codex)

```bash
python <skills>/ai-director-consistency/scripts/build_sheet_prompt.py stories/<slug>/story.json S1 \
  --out stories/<slug>/prompts/S1-sheet.txt      # 프롬프트 파일을 쓰고 --ref 인자를 출력한다
# 그다음 이 프롬프트와 출력된 --ref 목록(라벨=경로)으로 내장 image_gen을 호출하고
# (ai-director-shot-gen 4절), 결과를 stories/<slug>/media/S1-sheet-v1.png로 복사한다
```

- 컷 수는 4~6개로 둔다. 컷이 많으면 패널이 작아져 디테일이 무너진다.
- 시트의 작은 글자는 틀려도 된다. 사람과 모델이 구조를 읽는 용도다. 검수는 1번 섹션(얼굴, 의상), 공간 배치, 각 컷의 구도로 한다.
- 틀린 부분은 시트 전체를 다시 만들지 않는다. 내장 image_gen에 시트를 참조로 넣고 수정 지시만 쓴다.
- 영상 단계:
  - 영상 모델이 있으면 시트와 인물 기준 이미지를 참조로 넣고, 컷 메타(렌즈, 움직임, 길이)를 그대로 영상 프롬프트로 쓴다.
  - 영상 모델이 없으면 각 컷 패널을 출력 화면비로 다시 그려 키프레임으로 쓴다. 이때 시트를 참조 이미지로 넣고 "Cut N을 16:9 단독 프레임으로"라고 지시한다. 그다음 `animate_still.py`로 움직임을 준다.
