---
name: ai-director-reference
description: Use when an AI film needs reference material collected before bible, look or camera design — camera technique references (tilt up/down, push-in, crane, tracking, framing), location references (photos, videos) and mood references (light, colour, brightness, texture, rhythm) — recorded with source and timecode in story.json references[], with contact sheets and measured brightness/palette/screen-motion evidence from ref_probe.py. 한국어 트리거는 레퍼런스 수집, 레퍼런스 영상, 레퍼런스 보드, 무드보드, 촬영 레퍼런스, 배경 레퍼런스, 분위기 레퍼런스, 틸트업 레퍼런스. Part of the ai-director skill set.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 레퍼런스 수집 (Reference board)

장면 연출(2-1)이 정해진 뒤, 바이블(3)·촬영 설계(4)·룩 확정(6-2) 전에 **무엇을 참고해서 무엇을 가져올지**를 기록한다. 이 스킬은 **수집, 출처 기록, 분석 증거**만 맡는다. **라이선스는 검사하지 않는다**(사용자 결정 2026-11-11). 결정은 다른 스킬이 한다.

| 측면 | `aspect` | 결정하는 스킬 | 연결 위치 |
|---|---|---|---|
| 구도·촬영 기법(틸트업·다운, 푸시인, 크레인, 트래킹, 프레이밍) | `camera` | `ai-director-cinematography` 0절 | `scene.reference_links`, `shot.reference_links` → `shot.staging`, `shot.success_criteria.camera` |
| 배경(장소 사진·영상) | `location` | `ai-director-consistency` 2-2 장소 핸드북 | `bible.worlds[].reference_links` |
| 분위기(빛, 색, 밝기, 질감, 리듬) | `mood` | `ai-director-consistency` 룩 인터뷰(anti-slop 0절) | `bible.style.reference_links`, 씬만 다르면 `scene.reference_links` |

형식·필드는 [reference-board.md](references/reference-board.md)에 있다. 원장은 story.json 최상위 `references[]` 하나다(별도 board.json을 만들지 않는다).

## 0. 언제 하고 언제 건너뛰나

- 이 단계는 **선택**이다. 측면마다 방향이 이미 확정돼 있으면(사용자가 정한 레퍼런스, 기존 작품 규칙) 건너뛰고 `references`에 남길 필요도 없다. 건너뛴 이유는 진행 블록에 한 줄로 쓴다.
- 사용자가 주는 레퍼런스는 Intake(1단계)부터 받는다. 받는 즉시 `status: candidate`로 원장에 넣는다.
- 개수는 **상한**이다: 씬마다 측면별 최대 3개. 특정 무빙이 중요한 샷만 샷 단위로 1~2개.
- 단일 컷 요청(`@S2-3`)이면 그 컷과 앞뒤 컷에 필요한 측면만 다룬다.

## 1. 수집 순서

**1~6번은 `reference-scout` 에이전트에 맡긴다**(검색·다운로드·측정 로그가 길어 메인 맥락을 많이 차지한다). 프롬프트에 작품 폴더, 대상 씬/샷, 측면별로 찾는 것, scene.direction·shot.staging·RULES.md, 사용자 자료, 결과 경로(`refs/board/scout_<target>_<날짜>.json`)를 준다. 에이전트는 story.json을 고치지 않고 측면별 후보 최대 3개를 references[] 형식으로 돌려준다. **7번(보드 보여 주기·고르기)과 원장 반영은 메인 세션이 한다.** 후보가 1~2개뿐이거나 사용자 자료만 정리하면 될 때는 직접 해도 된다.

1. **사용자 자료 먼저.** 사용자가 준 파일·링크·작품명을 `candidate`로 넣는다. 파일은 `stories/<slug>/refs/board/src/`에 복사해 `source.path`에 적고, 원래 위치는 `source.path_original`에 남긴다.
2. **부족한 측면만 검색으로 후보를 찾는다.** 절차와 출처는 [reference-board.md](references/reference-board.md) 2절. 측면마다 후보 2~3개. 쓸 만한 것은 파일로 받아 분석한다(YouTube 등 스트리밍 영상도 필요한 구간만 받는다). 받지 못해 재생으로 확인하지 못한 링크는 타임코드를 추측하지 않고 `in_ms/out_ms: null`, `observed: null`로 둔다.
3. **로컬 파일을 분석한다:**
   ```
   python <skills>/ai-director-reference/scripts/ref_probe.py <source.path>      --out stories/<slug>/refs/board/<ref_id> [--range IN_MS OUT_MS] [--crop x0,y0,x1,y1 | --no-crop]
   ```
   결과(`contact.jpg`, `palette.png`, `probe.json`, `report.md`)를 `evidence`에 적고, probe.json의 `media_sha256`을 `source.sha256`에 옮긴다(나중에 파일이 바뀌었는지 확인). 링크만 있고 파일이 없으면 접촉 시트·관찰을 **만들어 내지 않는다**(`evidence: null`, `observed: null`).
4. **출처를 적는다.** 제목·만든 사람·URL을 `source`에 남긴다. 권리 확인용이 아니라 나중에 다시 찾고, 크레딧을 넣고 싶을 때 쓰기 위해서다.
5. **직접 본다.** 접촉 시트를 view_image로 보고, 영상은 가능하면 구간을 재생(촘촘한 프레임 추출 포함)해 확인한다. 본 내용만 `observed.notes`에 적고 어떻게 봤는지를 `observed.mode`에 남긴다: `contact_sheet`(접촉 시트만), `dense_frames`(촘촘한 정지 프레임, `interval_s`와 `range_ms`를 함께 기록), `playback`(실제 실시간 재생을 관찰한 경우만), `user_viewing`(사용자가 보고 고름, `by: user`). 촘촘한 프레임을 본 것은 재생 관찰이 아니므로 `playback`으로 적지 않는다. **촬영 기법(틸트업 등)은 `dense_frames`(사용 구간 전체, 간격 0.25초 이하)·`playback`·`user_viewing`으로만 확정한다.** 단, 촘촘한 프레임으로도 틸트와 페데스탈·크레인(수직 이동), 팬과 트럭처럼 구별되지 않는 경우는 후보로 남긴다(dense_frames가 기법 판정의 정확성을 보증하지 않는다). 접촉 시트만 봤으면 무빙은 후보로 남긴다. 레퍼런스 관찰 기록은 생성 영상 검수의 재생 근거로 쓰지 않는다. 사용자 시청 확인은 취향 승인의 근거이지 도구 측정이 아니다.
6. **가져올 것/가져오지 않을 것을 문장으로 쓴다.** 연결(`reference_links[]`)마다 `take`(측정·관찰 가능한 문장)와 `avoid`를 쓴다. 예:
   - camera: `take: "인물 발끝에서 시작해 4초 동안 얼굴 높이까지 tilt up, 끝 구도 MCU, 카메라 높이 허리"`, `avoid: "핸드헬드 흔들림, 렌즈 플레어"`
   - location: `take: "2층 이하 상가, 회색 셔터, 머리 위 전선 3~4가닥, 바닥 마른 아스팔트"`, `avoid: "네온 간판, 젖은 거울 바닥"`
   - mood: `take: "평균 휘도 약 30(ref_probe), 광원은 위쪽 백색 보안등 하나, 그림자 쪽 채도 낮음"`, `avoid: "청록·주황 그레이드"`
   분위기 단어(cinematic, moody)로만 쓰지 않는다(`<skills>/ai-director-consistency/references/anti-slop.md`).
7. **보드를 보여 주고 고르게 한다.** 측면별로 접촉 시트(또는 링크·타임코드)와 take/avoid를 표로 보여 주고 선택지 질문으로 고르게 한다. 고른 것만 `approved`, 버린 것은 `rejected`(이유를 `note`에). 최종 확인은 Gate 1(계획 승인)에 같이 넣는다.

## 2. 넘겨주기

- **camera** → cinematography 0절: 승인된 take를 `shot.staging`(카메라 높이·렌즈·무빙)으로 옮기고, 생성 전에 `shot.success_criteria.camera`에 관찰 가능한 문장으로 쓴다(예: "0~4초 동안 화면 내용이 위에서 아래로 흘러 tilt up으로 읽힌다, 끝에서 얼굴이 화면 위 1/3"). 모델이 해낼 수 있는 무빙인지는 cinematography 4·5절과 `model-capabilities.md`로 판단한다.
- **location** → consistency 2-2: 핸드북의 "있는 사물/실제 광원/없는 것"에 take/avoid를 옮긴다. 장소 사진은 `env_image`로 넣어도 된다. 넣어도 **Blender 설계·블록아웃·조명 가이드를 대체하지 않는다**(루트 `CLAUDE.md` 0절).
- **mood** → 룩 인터뷰(anti-slop 0절 1번): 승인된 mood 레퍼런스가 1번 답이다. 측정값(휘도·대비·지배색)은 스타일 프레임 비교(6-2)의 기준 후보로 `bible.style.notes`에 적는다. 리듬(컷 길이, 동작 비트, 정적 구간)은 도구가 재지 않으므로 직접 보고 `observed.notes`에 적는다.
- 레퍼런스 프레임을 생성 참조로 직접 넣을 수 있다. 단 그 그림의 질감·색·사물이 그대로 옮는다(anti-slop 2-3). 구도·무빙만 빌리려면 참조로 넣지 말고 take 문장으로 옮기는 편이 결과가 낫다. 넣을 때는 프롬프트에 역할을 적는다(예: "layout/camera only, ignore its rendering style").

## 3. 생성 뒤 비교 (실험)

같은 스크립트로 생성 영상을 레퍼런스 옆에 잴 수 있다.
```
python <skills>/ai-director-reference/scripts/ref_probe.py <레퍼런스> --range IN OUT --out <dir> \
  --compare stories/<slug>/media/<shot>-v<n>.mp4 --compare-range <사용 구간>
```
나란히 놓은 표만 나오고 판정은 없다. **수치 유사도는 영상 PASS 근거가 아니다.** 영상 합격은 `video-reviewer`가 `success_criteria.camera`를 기준으로 재생 검수해서 정한다(루트 `CLAUDE.md` 0-1절). 화면비·크롭·구간·재생 속도가 다르면 수치를 그대로 비교하지 않는다.

## 4. ref_probe.py가 재는 것과 한계

- **분위기:** Rec.709 Y 휘도(평균, p5/p50/p95, 대비), HSV 채도 평균, 지배색 k개(비율). 색 관리 없이 BT.709로 가정한다. 색온도는 재지 않는다. 휘도는 감마가 적용된 화면 값이라 물리적 광량이 아니고, 영상 합격 임계값으로 옮기지 않는다.
- **화면 움직임(영상):** 컷 사이 구간마다 0.5초 간격 프레임 쌍의 사분면 위상상관(1px 미만 보간)으로 화면 내용의 이동(px, 화면 대비 %)과 확대 근사(`scale_change`)를 누적한다. 이름은 후보로만 낸다: "화면 내용이 아래로 → tilt up 또는 pedestal/crane up 후보". 틸트와 페데스탈, 팬과 트럭, 돌리와 줌은 화면 이동만으로 구별할 수 없다. 사람이 영상을 보고 정한다.
- 순이동(`image_translation_frac`)과 총 이동(`path_length_frac`)·방향 바뀜(`direction_changes`)을 따로 낸다. 갔다 돌아온 무빙은 순이동이 0이어도 static으로 표시하지 않고 "왕복·흔들림 후보"로 낸다. 측정 간격(`--step-s`, 기본 0.5초)보다 짧은 흔들림은 못 잡는다. 무효 쌍을 평균 속도로 채운 값은 `estimated_fill_s`로, 유효 쌍만의 값은 `observed_translation_frac`로 구분된다.
- `scale_change`는 실제 배율이 아니라 근사 지표다(합성 테스트에서 실제 1.29배를 1.19로 잼).
- `unknown`: 상관 피크가 약하거나(저텍스처·어두움·가림), 사분면끼리 이동이 맞지 않거나(피사체가 화면을 채움, 회전), 신뢰 쌍이 60% 미만인 구간. 컷 전환에서는 구간을 나눈다.
- 레터박스는 자동 감지하되 어두운 장면을 띠로 오인할 수 있다. 검출 영역은 `conditions.analysis_crop`에 남고, `--crop`/`--no-crop`으로 고친다.
- 측정 조건(구간, 원본·분석 해상도, 크롭, 화면비, 색공간 가정, 재생 속도 1.0·보정 없음)은 `probe.json conditions`에 모두 남는다.
- 테스트: `python <skills>/ai-director-reference/scripts/tests/test_ref_probe.py`(합성 틸트·팬·푸시인·느린 무빙·왕복·레터박스·수동 크롭 범위·컷·무늬 없는 화면).

## 5. 바뀌면

- 승인된 레퍼런스를 바꾸거나 빼면 그것을 연결한 bible/scene/shot을 목록으로 보여 주고 "재검토 필요"로 표시한다(`reference_links[].stale: true`). **자동으로 다시 생성하지 않는다.**
- 개선 3회 한도는 스스로 고칠 때만 센다. 사용자가 레퍼런스를 고르거나 바꾸라고 한 것은 세지 않는다.

## 완료 전 점검

- `python <skills>/ai-director/scripts/validate_story.py stories/<slug>/story.json`에 references 관련 오류가 없다(ID 중복, 없는 ref_id 연결, aspect 값, 구간, `approved`인데 `observed` 없음, 링크 전용인데 증거 있음).
- 링크만 있는 레퍼런스에 접촉 시트·관찰이 지어져 있지 않다.
- 승인된 camera 레퍼런스가 있는 샷은 `success_criteria.camera`가 생성 전에 쓰여 있다.
