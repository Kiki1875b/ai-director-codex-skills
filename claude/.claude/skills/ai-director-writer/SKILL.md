---
name: ai-director-writer
description: Use when the user wants a professional screenplay or scenario for an AI film — recommends genres first, asks a few key questions, then writes in stages (logline → synopsis → beat sheet → step outline → screenplay draft), has a separate screenplay-reviewer agent score it, revises, and exports scenes/shots into story.json for ai-director. Handles shorts (≤3 min) and short films (3–20 min). 한국어 트리거는 시나리오 써줘, 각본, 대본 작성, 시나리오 에이전트, 장르 추천, 스토리 짜줘, 단편 영화 시나리오, 숏폼 드라마 대본. Not for gag/brainrot shorts (ai-video-fun-writer) or shot prompts (ai-director-shot-gen).
---

# 시나리오 작가 (Writer)

전문 시나리오를 단계별로 쓴다. 결과는 `stories/<slug>/script/` 아래 파일과 `story.json`에 남겨 `ai-director`의 스토리보드·생성 단계로 넘긴다. 한 번에 대본까지 쓰지 않는다. 단계마다 결과를 저장하고, 다음 단계는 앞 단계의 확정 결과만 입력으로 받는다.

## 읽을 파일

| 언제 | 파일 |
|---|---|
| 항상 | [craft-rules.md](references/craft-rules.md): 구조, 장면, 인물, 대사 원칙과 길이별 템플릿, 제작 제약 |
| 장르 추천과 집필 | [genres.md](references/genres.md): 고른 장르 항목만 읽는다 |
| 각 단계 실행 | [stage-prompts.md](references/stage-prompts.md): 단계별 지시문과 출력 스키마 |
| 초고 | [format-ko.md](references/format-ko.md): 한국 시나리오 표기법 |
| 리뷰 | [review-rubric.md](references/review-rubric.md): 리뷰 에이전트 채점표 |
| story.json 변환 | `.claude/skills/ai-director/references/story-schema.md` |

## 0. Intake

1. **프로젝트 정하기.** `stories/` 아래 폴더를 나열한다.
   - 사용자가 말한 소재와 맞는 폴더가 있으면(예: "구미호" → `stories/gumiho`) 그 폴더를 쓸지 새로 만들지 AskUserQuestion으로 묻는다.
   - 새로 만들면 slug는 영문 소문자와 하이픈(예: `gumiho-temple`)으로 정하고 한 줄로 알린다.
   - story.json이 없으면 `ai-director/examples/sample-story.json`과 같은 구조로 새로 만든다. `scenes`는 `[]`, `timeline`은 `{"tracks": [], "clips": []}`, `bible.style.anchor`는 장르 톤으로 초안을 쓴다.
2. **기존 자료 읽기.** 바이블의 캐릭터·월드·스타일은 **반드시 쓰는 재료**다. 외형은 앵커와 충돌하게 쓰지 않는다.
   - `ref_images`의 이미지(기준 사진, 캐릭터 시트)를 Read로 직접 본다. 텍스트 앵커에 없는 시각 정보를 `script/00-brief.md`의 "시각 메모"에 적는다: 표정 범위, 시그니처 소품, 실루엣, 색, 눈에 띄는 특징(예: 분노하면 눈이 금빛으로 빛남). 장르 카드의 훅과 장면 설계에 이 메모를 활용한다.
   - 시트에 있는 것만 쓸 수 있다고 가정하지 않는다. 시트에 없는 의상·소품이 필요하면 바이블 변형 엔트리로 추가할 항목으로 적는다.
3. **빈칸은 기본값.** 용도·플랫폼, 관객·등급, 금지 요소. 기본값: 15세 관람가, 주요 인물 1~3명. 길이는 1단계에서 장르와 함께 묻는다. **화면비는 기본값으로 채우지 않고 9:16 / 16:9 / 2.39:1 중 사용자에게 묻는다**(장면 구성과 인물 배치가 화면비에 따라 달라지므로 대본 전에 정한다).
4. 정한 화면비는 `ai-director/references/aspect-ratios.md` 표대로 `story.format.aspect_ratio`와 `export`(width/height/fit)에 함께 적는다.

## 1. 장르 추천

`genres.md`, 바이블, 플랫폼을 보고 **서로 다른 방향의 카드 3~4개**를 만든다. 최신 유행이 중요하면 웹 검색으로 현재 인기 장르·소재를 확인하고 출처와 날짜를 적는다.

```
[A] 장르 / 하위 장르 — 한 줄 로그라인
훅: 숏폼은 첫 5초 화면, 단편은 첫 장면
왜 맞는지: 자산·길이·플랫폼과의 적합성
톤 레퍼런스: 작품 2개 (분위기 설명용. 설정·전개·결말을 빌리지 않는다)
제작 난이도: 인물 N · 장소 N · 액션 비중 낮음/중간/높음
```

AskUserQuestion 한 번에 두 질문을 묻는다: **카드 선택**(카드 이름을 선택지로), **길이**(숏폼 60~180초 / 단편 3~20분, 기본값을 추천으로 표시). 사용자가 섞거나 새 방향을 말하면(Other) 그대로 따른다.

## 2. 핵심 질문

품질을 바꾸는 것만, 한 번에 하나씩, 추천 기본값을 붙여 AskUserQuestion으로 묻는다. 최대 4개다.

1. 주인공이 원하는 것과 그것을 막는 것
2. 결말의 감정(통쾌 / 씁쓸 / 반전 / 여운)
3. 꼭 넣고 싶은 장면이나 이미지 하나
4. 피할 것(소재, 수위, 클리셰)

"알아서"라고 하면 질문을 멈추고 기본값으로 진행한다. 답은 `script/00-brief.md`에 저장한다(장르, 길이, 플랫폼, 등급, 답, 금지 요소).

## 3. 단계별 집필

각 단계 결과를 `stories/<slug>/script/`에 저장하고, 사용자에게는 짧은 요약을 보여준다. "자동 진행" 단계도 요약 한두 줄은 보여주고 멈추지 않고 넘어간다.

| 단계 | 파일 | 확인 |
|---|---|---|
| 3-1 로그라인 3안 → 1안 | `01-logline.md` | 사용자 선택 |
| 3-2 시놉시스, 인물표, 주제 | `02-synopsis.md` | 자동 진행 |
| 3-3 비트시트 | `03-beats.json` | 자동 진행 |
| 3-4 스텝 아웃라인 | `04-outline.json` | **사용자 승인** — 구조가 여기서 확정된다 |
| 3-5 초고 | `05-draft-v1.md` | 리뷰로 넘김 |

"2막만 다시", "결말 바꿔"라고 하면 해당 단계부터 다시 쓰고 그 뒤 단계만 갱신한다. 3-4 이전으로 돌아가면 아웃라인 승인을 다시 받는다.

## 4. 리뷰와 수정 (쓴 쪽이 스스로 승인하지 않는다)

리뷰 n은 `05-draft-vn.md`를 평가해 `review-vn.md`에 쓴다. **리뷰는 최대 3회**(초고 v1~v3)다.

호출: Agent 도구, `subagent_type: "screenplay-reviewer"`. 프롬프트에 아래를 모두 넣는다.
- 초고 `script/05-draft-vn.md`, 아웃라인 `script/04-outline.json`, 비트시트 `script/03-beats.json`, 브리프 `script/00-brief.md`, `story.json` 경로
- 장르, 목표 길이(초), 플랫폼, 등급, 사용자 요구, 금지 요소
- 이전 리뷰 경로(n>1이면 `review-v{n-1}.md`), 이번 리뷰를 쓸 경로 `script/review-vn.md`

판정별 처리:
- **PASS** → 5단계.
- **REVISE** → 지시마다 리뷰어가 붙인 범위를 본다.
  - `국소`: 해당 위치만 고쳐 `05-draft-v{n+1}.md`를 쓰고 다시 리뷰한다(stage-prompts.md 수정 지시문).
  - `구조`: 3-4로 돌아가 아웃라인을 고치고, 바뀐 씬 표를 보여주고 사용자 재승인을 받은 뒤 초고를 다시 쓴다. 리뷰 횟수는 이어서 센다.
- **BLOCK**(표절 의심, 등급·금지 요소 위반) → 즉시 멈추고 사유를 보여주고 AskUserQuestion으로 방향(해당 요소 교체 / 장르·로그라인 재선택 / 중단)을 묻는다.
- 3회 리뷰 후에도 PASS가 아니면 마지막 버전을 최종 후보로 삼고, 남은 지적을 목록으로 보여주고 그대로 갈지 사용자에게 묻는다.

점수를 흥행·수상 가능성처럼 말하지 않는다. 독창성 확인은 리뷰어의 판단이며 기계적 대조가 아니라고 보고서에 적는다.

## 5. 최종본과 story.json 변환

1. **최종본 확인.** `06-final.md`를 만든다. `(가치: …)`와 `[수정: …]` 주석은 지운다. 사용자에게 전문 링크와 한 단락 요약을 보여주고 확정을 받는다.
2. **기존 장면 보호.** story.json에 `scenes`가 이미 있으면 덮어쓰지 않는다. 바뀌는 씬·샷 목록과 그중 `versions`가 있는 샷 수를 보여주고 승인을 받는다. 바뀌지 않는 샷은 `id`, `versions`, `active_version_id`를 그대로 둔다.
3. **씬 하나씩 변환.** stage-prompts.md 5절 그대로, 씬 하나를 변환해 저장하고 다음 씬으로 넘어간다. 샷은 **반드시 해당 씬 객체 안의 `shots[]`**에 넣는다(최상위 `shots`는 무시된다).
4. **바이블 갱신.** 새 인물·소품·장소는 `bible.characters/objects/worlds`에 앵커 문장과 함께 추가하고 `ref_images`는 `[]`로 둔다. 씬의 `world_id`는 반드시 `bible.worlds`에 있어야 한다.
5. `story.title`, `story.logline`을 채운다.
6. 검사:
   ```bash
   python .claude/skills/ai-director/scripts/validate_story.py stories/<slug>/story.json --target-ms <목표 길이 ms>
   ```
   타임라인이 아직 없으면 검증기가 **샷 `duration_ms` 합계**를 목표의 ±10%와 비교한다. 오류가 있으면 고치고 다시 검사한다.
7. 편집 단계로 넘길 메모를 `script/07-handoff.md`에 쓴다: 말하는 인물별 목소리 성격(voice 배정 후보), BGM 무드와 템포, 꼭 필요한 효과음.
8. 다음 단계 안내: `ref_images`가 빈 항목 → `ai-director-consistency`, 시트·키프레임 → `ai-director-shot-gen`.

## 원칙

- 작품 대사·장면을 베끼지 않는다. 레퍼런스는 톤 설명에만 쓴다. `genres.md`의 비틀기 예시도 그대로 쓰지 말고 같은 원리로 새로 만든다.
- AI 영상 제약은 시나리오 단계에서 지킨다(craft-rules.md 7절).
- 생성·게시는 이 스킬에서 하지 않는다.
- 병맛·브레인롯 숏폼 요청이면 `ai-video-fun-writer` 스킬을 쓴다. 이 프로젝트에 설치되어 있지 않으면(`.claude/skills/`에 없음) 사용자에게 알리고 이 스킬의 코미디 플레이북으로 진행한다.
