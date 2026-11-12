---
name: ai-director-scene-direction
description: Use when an AI film needs scene direction, actor blocking, emotional beats or a clear visual point of view before shot generation, or when adjacent shots feel disconnected. 한국어 트리거는 연출 감독, 장면 연출, 배우 동선, 감정선, 시선 연결, 씬 연결. Not for screenplay-only requests or model settings alone.
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# 장면 연출 감독

장면에서 관객이 **누구를 따라 무엇을 알아차리는지**를 정하고, 인물의 행동과 시선으로 보여준다. `ai-director`는 진행·승인을 관리하고, 이 스킬은 장면의 의도·비트·블로킹을, `ai-director-cinematography`는 그 의도를 보여줄 카메라와 구도를 맡는다.

## 시작할 때

작품 `RULES.md`, 확정 대본, 해당 scene과 앞뒤 scene/shot, 세트 평면도·기존 카메라, 승인된 키를 읽는다. 이미 영상이 있으면 실제 타임라인의 사용 구간도 확인한다. 작업 대상 밖의 대본·ID·버전은 유지한다.

| 요청 | 범위 |
|---|---|
| 새 장면·키프레임 설계 | 아래 연출 설계 → 촬영 설계 → 연속 콘티 점검 후 shot-gen |
| 기존 컷의 시선·연결 수정 | 문제가 있는 컷과 바로 앞뒤 컷부터 진단 |
| 영상이 잠긴 작업 | 현재 영상과 대사 위치 안에서 진단. 허용 범위를 넘는 트림·순서·구도·재생성은 제안으로만 분리 |

## 1. 장면의 의도와 비트

`scene.direction`에 다음을 기록한다. 대본에 없는 사연·감정·동작을 사실처럼 보태지 않는다.

- `viewpoint`: 관객이 따라갈 인물/관찰자와 그 이유.
- `dramatic_turn`: 장면 전후의 관계·정보 변화 한 문장.
- `beats`: 관찰 가능한 사건 순서. 각 비트에 `action`, `audience_learns`, `shot_ids`를 적는다.

예: **A가 컵을 숨기고 있음 → 컵을 내밂 → B가 컵을 보고 A를 다시 봄.** 관객이 컵을 처음 알아차려야 하는 컷을 지정한다. 같은 정보를 반복하는 컷은 필요성을 설명하고, 컷을 추가하기 전에 기존 컷의 길이·구성으로 전달 가능한지 검토한다. 실제 삭제·재배치는 사용자 범위를 따른다.

## 2. 인물 배치와 시선의 사건 순서

관련 샷의 `shot.staging` 초안을 만든다. 필드와 예시는 [shot-design.md](references/shot-design.md), 스키마 원본은 `ai-director/references/story-schema.md`의 연출 확장이다.

1. 인물·소품 위치, 서기/앉기, 몸 방향, 실제 눈높이와 대화축을 정한다. 기존 세트와 카메라가 있으면 그 좌표를 사용한다. 없으면 블록아웃에서 확정할 설계안과 미확정 사항을 구분한다.
2. 인물마다 **언제, 누구의 어느 부분을 보는지**를 정한다. 상대의 눈, 컵, 출입구는 서로 다른 목표다. 시선 전환이 있으면 시작→전환 계기→끝을 적고 `start_state`/`end_state`와 맞춘다.
3. 행동 시작·접촉·완료·반응 중 어느 순간에 컷을 넘길지 정한다. 모든 컷을 행동이 끝난 포즈로 시작하지 않는다. 기존 키가 이미 완료 상태면 그 이후 행동을 설계하거나 수정안을 제안한다.
4. 화면 밖 상대의 위치·높이도 지정한다. 배우의 눈은 실제 목표를 향하고, 카메라를 응시하는 연출은 의도가 있을 때만 쓴다.

확정된 대본의 미스터리·의도적 시선 회피는 보존한다. 그 경우 실제 바라보는 목표와 관객이 받아들일 의미를 별도로 쓴다.

## 3. 키프레임 전에 촬영 설계로 넘긴다

`ai-director-cinematography` **0절과 2-1절**을 적용해 `shot.staging`을 완성한다. 샷 크기·렌즈·카메라 위치/높이·축의 어느 쪽인지, 화면 속 인물 배치, 시선 목표·높이, 관객 관심점의 입구/출구를 함께 정한다. 불명확한 공간을 프롬프트의 "자연스럽게"로 대신하지 않는다.

연속 컷마다 `shot.cut_link`에 앞 컷 ID, 연결 종류, 관심을 넘기는 단서, 의도적 단절 여부와 재정향 단서를 적는다. **인물의 시선 일치와 관객의 관심 이동은 별도 항목**이다. 관심점이 멀리 이동해도 발견·충격이 목적이면 그 이유와 대상을 찾게 하는 단서를 기록한다.

## 4. 연속 콘티로 확인하고 인계한다

키 생성 전에는 비트와 공간·시선 설계가 서로 맞는지 계획으로 점검한다. 키가 생기면 앞 컷의 계획된 끝 구도와 다음 컷의 시작 구도를 순서대로 본다. 실제 영상이 생기면 계획용 키를 사용 구간의 실제 끝·시작 프레임으로 대체한다.

- 공유 검수 절차: `ai-director-cinematography/references/eyeline-continuity.md`.
- 키의 정체성·빛·배치: 기존 `keyframe-reviewer`에 연출/촬영 기록과 인접 키를 함께 준다.
- 실제 연결의 움직임: 기존 `video-reviewer`에 두 영상과 정확한 source in/out·speed를 준다. 프레임만 본 결과를 재생 합격으로 쓰지 않는다.
- shot-gen에는 해당 scene/shot 기록, 기준 이미지, 앞뒤 연결과 관찰 가능한 `success_criteria`를 넘긴다. 실제 시선 행동은 start/progress/complete에, 시선·관심점 연결은 continuity에 쓴다.

## 5. 씬이 완성되면 씬 전체를 검수한다

컷이 아니라 **씬** 단위다. 씬의 모든 컷이 타임라인 렌더 트랙에 활성 버전으로 놓이면(또는 씬 안의 컷을 바꾸면) 실행한다.

1. `python <skills>/ai-director-edit/scripts/render_timeline.py stories/<slug>/story.json --preview -o stories/<slug>/export/<scene>-preview.mp4`로 현재 타임라인을 렌더한다.
2. `scene-reviewer` 에이전트에 story.json, 씬 ID, 렌더 경로, 리뷰 경로(`stories/<slug>/reviews/<scene>-scene-v<n>.md`)를 준다. 에이전트는 `scripts/scene_evidence.py`로 컷 목록·길이·편집점·소리 크기를 뽑고 [scene-rubric.md](references/scene-rubric.md)의 이야기·배치·화면·빛·편집·소리 항목을 채점한다.
3. 판정과 "시청 확인" 질문을 렌더와 함께 사용자에게 보여 준다. 정지 프레임으로 못 보는 감정·리듬·소리는 사용자 시청으로 확정한다. 사용자 판정은 루트 CLAUDE.md 5절대로 장부에 기록한다(`--shot <scene>`).
4. 고칠 때는 `[편집]`부터. 재생성은 승인 후. 자체 수정은 최대 3회.

산출물은 story.json의 관련 scene/shot 변경과 **장면 의도 한 줄 + 앞뒤 컷 연결표**다. 상세 리뷰는 작품 `script/` 또는 기존 리뷰 경로에 저장하고 Story에서 경로를 참조한다. 계획 기록은 영상 검수 pass를 대신하지 않는다. 이미지·영상 생성은 이 스킬에서 자동 실행하지 않는다.
