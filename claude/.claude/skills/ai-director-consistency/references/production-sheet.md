# 씬 프로덕션 시트

씬 하나의 인물·배경·샷 구성을 한 장에 담는 시트다. 한 번에 생성해 칸 사이의 인물·공간·룩을 맞추도록 유도하지만 보장은 아니므로 패널별로 검수한다. Codex image로 3:2 가로형 1장을 목표로 만들고, 실제 크기는 생성 뒤 확인한다. 프롬프트는 `scripts/build_sheet_prompt.py <story.json> <scene> --layout scene`으로 만든다.

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

## 이 시트가 일관성을 만드는 이유

| 섹션 | 고정하는 것 | 키·영상 단계에서 쓰는 방식 |
|---|---|---|
| 1 캐릭터 레퍼런스 | 얼굴, 3방향 체형, 의상 아이템 | 컷 키를 그릴 때 같은 인물의 기준으로 쓴다 |
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
python .claude/skills/ai-director-consistency/scripts/build_sheet_prompt.py stories/<slug>/story.json S1 \
  --out stories/<slug>/prompts/S1-sheet.txt      # 프롬프트 파일을 쓰고 --ref 인자를 출력한다
python .claude/skills/ai-director-shot-gen/scripts/codex_image.py --prompt-file stories/<slug>/prompts/S1-sheet.txt \
  <출력된 --ref 인자들> --out stories/<slug>/media/S1-sheet-v1.png
```

- 컷 수는 4~6개로 둔다. 컷이 많으면 패널이 작아져 디테일이 무너진다.
- 시트의 작은 글자는 틀려도 된다. 사람과 모델이 구조를 읽는 용도다. 검수는 1번 섹션(얼굴, 의상), 공간 배치, 각 컷의 구도로 한다.
- 틀린 부분은 시트 전체를 다시 만들지 않는다. `codex_image.py`에 시트를 `--ref`로 넣고 수정 지시만 쓴다.
- 영상 단계: 시트는 영상 모델에 직접 넣지 않는다. 시트를 `--ref`로 넣어 컷 패널을 작품 화면비의 단독 키프레임으로 다시 그리고, 승인된 키(와 필요한 끝 키)를 영상 도구에 넣는다(`ai-director-shot-gen` 1절). 컷 메타(렌즈, 움직임, 길이)는 영상 프롬프트의 근거로 쓴다. 영상 모델을 쓰지 않으면 그 키로 `animate_still.py` 애니매틱을 만든다(모션 합격본이 아님).

## 개별 시트 레이아웃 (character / object / location / storyboard)

씬 시트(`--layout scene`)는 인물·배경·콘티를 한 장에 묶는다. 항목별로 따로 보고 싶거나 참조 품질을 높이려면 아래 레이아웃을 쓴다. 모두 story.json만 읽는다.

| 레이아웃 | 대상 인자 | 내용 | 참조 라벨 | 권장 저장 경로 |
|---|---|---|---|---|
| `character` | 캐릭터 id | 턴어라운드 4방향, 얼굴 2컷, 표정 4개(그 인물 단독 CU/MCU/ECU 샷의 action), 상태 변형(`notes`), 의상 디테일, 대표 소품 2개 | `character_image1` | `refs/<id>_sheet_vN.png` |
| `object` | 소품 id, 쉼표 목록, `ALL` | 소품마다 가로 띠 1개: 정면·측면·윗면, 손 윤곽 대비 크기, 디테일 매크로, 상태 띠. 참조는 3개까지 | `object_image1..3` | `refs/ob_<..>_sheet_vN.png` |
| `location` | 월드 id | 사람 없음. 히어로 와이드, 실제 컷이 쓰는 카메라(wide/two-shot)에서 본 앵글 3개, 평면도, 씬별 조명 변형, 재질 띠 | `env_image1..2` | `refs/<id>_sheet_vN.png` |
| `storyboard` | 씬 id 또는 `ALL` | 콘티. 16:9 프레임 격자(`--per-page`, 기본 12컷 = 4×3), 패널마다 샷 id·카메라·길이·행동·대사. `--page N`으로 쪽 선택 | 인물 2, 배경 2, 소품 1 | `media/conti-pN-vN.png` |

```bash
S=.claude/skills/ai-director-consistency/scripts/build_sheet_prompt.py
python $S stories/<slug>/story.json ch_mina --layout character --out stories/<slug>/prompts/ch_mina-charsheet.txt
python $S stories/<slug>/story.json ALL --layout object --out stories/<slug>/prompts/props-sheet.txt
python $S stories/<slug>/story.json wd_alley --layout location --out stories/<slug>/prompts/wd_alley-locsheet.txt
python $S stories/<slug>/story.json ALL --layout storyboard --page 1 --out stories/<slug>/prompts/conti-p1.txt   # 쪽 수는 stderr INFO에 나온다
```

- 출력된 `refs:` 줄을 그대로 `codex_image.py`에 붙인다. Windows에서는 `PYTHONIOENCODING=utf-8`을 켜야 한글 경로가 깨지지 않는다.
- 콘티 시트는 검토·공유용이다. 키프레임의 참조로는 씬 시트(`--layout scene`)나 개별 기준 이미지를 쓴다. 패널이 작아 얼굴 디테일이 약하다.
- 위치 시트의 앵글은 shot.camera에 `wide`나 `two-shot`이 들어간 컷에서 최대 3개를 뽑는다. 없으면 모델이 앵글을 고른다.
