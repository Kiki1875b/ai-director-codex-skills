---
name: ai-director
description: Use when the user wants to direct a multi-shot AI film, short drama, music video or long-form AI video end to end by chatting — story → character/world bible → storyboard (scenes and shots) → shot generation → timeline edit → export, with one Story document as the source of truth. 한국어 트리거는 AI 영화 감독, 디렉터 모드, 장편 AI 영상, 스토리보드부터 편집까지, 멀티샷 영상 제작, 오픈아트 디렉터처럼. Calls ai-director-writer for the screenplay, ai-director-consistency for character/background reference images and sheets, ai-director-shot-gen for scene production sheets, keyframes and clips, and ai-director-edit for the cut. Not for a single clip prompt (use ai-director-shot-gen) or a script only (use ai-director-writer).
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# AI Director (오케스트레이터)

채팅으로 받은 영화 아이디어를 **Story 문서 하나**로 관리한다. 그 문서를 단계별로 채워 완성 영상까지 만든다. 이 스킬은 OpenArt Suite Director의 공개 번들에서 관찰한 구조를 재구성한 것이다. 관찰한 구조는 다음과 같다.

- 에이전트 프로필 `director`
- Story → Scene → Shot → ShotVersion 계층
- tracks/clips 타임라인
- 이벤트 로그와 사용자 확인 게이트

OpenArt 서버의 실제 프롬프트는 공개되어 있지 않다. 그래서 `references/system-prompt.md`는 이 구조에 맞춰 새로 쓴 프롬프트다.

## 함께 쓰는 스킬

| 단계 | 스킬 |
|---|---|
| 장르 추천·전문 시나리오(로그라인→아웃라인→초고→리뷰) | `ai-director-writer` + `screenplay-reviewer` 에이전트 |
| 재미 중심 대본 | `ai-video-fun-writer` (있으면) |
| 캐릭터·월드·스타일 고정, 연속성 | `ai-director-consistency` |
| 샷별 생성 모드·프롬프트·버전 | `ai-director-shot-gen` |
| 타임라인 편집·자막·음향·렌더 | `ai-director-edit` |

## 핵심 원칙

1. **Story JSON이 유일한 진실 원천이다.** 대화 내용, 생성물, 편집 결정은 모두 이 파일에 반영한다. 형식은 [story-schema.md](references/story-schema.md)를 따른다. 기본 경로는 `stories/<slug>/story.json`이다.
2. **ID는 바꾸지 않는다.** scene, shot, clip ID는 한 번 만들면 유지한다. 샷을 다시 생성해도 새 version만 추가하고 `active_version_id`만 바꾼다.
3. **고칠 때는 범위를 최소로 잡는다.** 사용자가 `@S2-3`처럼 씬이나 샷을 지목하면 그 대상만 수정한다. 전체를 다시 만들지 않는다.
4. **유료·외부 호출 전에는 반드시 확인을 받는다** (`awaiting_user_input`). 생성할 샷 수, 모델, 예상 비용·시간을 보여주고 승인을 받는다. 게시는 절대 자동으로 하지 않는다.
5. **이미지를 먼저 만들고 영상으로 넘긴다.** 바이블(참조 시트)을 만들고, 키프레임 이미지를 만든 다음 image2video나 reference2video를 쓴다. 텍스트만으로 영상을 바로 만드는 방식은 연속성이 필요 없는 컷에만 쓴다.

## 작업 흐름

각 단계가 끝나면 story.json을 저장한다. 사용자에게는 짧은 진행 블록으로 알린다(아래 "출력 블록" 참고).

1. **Intake.** 소재, 길이, 화면비, 톤, 금지 요소, 쓸 수 있는 생성 도구를 확인한다. 빈칸은 기본값으로 채우고 한 줄로 밝힌다. 기본값: 16:9, 60초, 시네마틱 실사, 1~3명, 8~12샷. 생성 도구 기본값은 로컬 Codex(이미지 전용)와 ffmpeg 애니매틱이다(`ai-director-shot-gen` 4절). 영상 모델이 따로 있으면 사용자가 알려준다. 질문은 한 번에 하나만 하고, 막혀서 진행할 수 없을 때만 한다.
2. **Story (시나리오).** `ai-director-writer` 스킬을 불러 그 절차대로 진행한다(장르 추천 → 질문 → 로그라인~아웃라인 → 초고 → `screenplay-reviewer` 리뷰 → story.json 변환). writer가 scenes/shots와 새 바이블 항목까지 채운다. 사용자가 이미 대본을 줬으면 장르 추천과 질문을 건너뛰고 그 대본을 초고로 삼아 리뷰부터 한다. 병맛·브레인롯 숏폼이면 `ai-video-fun-writer`를 쓴다(없으면 writer의 코미디 플레이북).
3. **Bible (기준 이미지와 시트 계획).** `ai-director-consistency` 스킬을 불러 앵커를 확정하고, 필요한 이미지 목록을 아래 순서로 정한다. 이미 있는 이미지는 검수만 하고 재사용한다. **새 이미지는 5단계 승인 뒤 6-1에서 만든다**(사용자가 이 단계에서 먼저 만들어 달라고 하면 그 이미지만 승인받고 만든다).
   1. 캐릭터마다 **정면 전신, 흰 배경 기준 사진** 1장(`refs/<id>_front.png`). 이미 있으면 건너뛴다.
   2. 캐릭터 시트 1장: 기준 사진을 `character_image1`로 넣고 턴어라운드·클로즈업·표정·의상 디테일(`refs/<id>_sheet_v1.png`).
   3. 월드마다 **배경 기준 이미지**: 사람 없는 와이드 1장 + 주요 각도 1~2장(`refs/<id>_wide.png`). 중요 소품은 3방향 제품 컷 1장.
   4. 결과를 view_image로 보고 앵커와 비교 검수한 뒤 `ref_images`에 등록한다(정체성 기준은 `ref_images[0]`).
4. **Storyboard.** writer가 만든 씬과 샷을 점검·보완한다. 샷마다 아래 항목이 채워져 있어야 한다.
   - 주요 행동 하나
   - 카메라
   - 길이
   - 등장 ID
   - start_state / end_state
   - 대사, 효과음
   - 생성 모드
   - `scripts/validate_story.py`로 검사한다.
5. **Gate 1 (계획 승인).** 스토리보드 표, 바이블 요약, 생성 예산을 보여주고 승인을 기다린다.
5-1. 승인 표에는 3단계 이미지(기준 사진·캐릭터 시트·배경), 씬 시트, 키프레임, 영상 개수를 모두 넣는다.
6. **Generate.** `ai-director-shot-gen`으로 아래 순서로 만든다.
   1. 3단계 기준 이미지·시트(아직 없으면)
   2. **씬 프로덕션 시트**: 씬마다 `<skills>/ai-director-consistency/scripts/build_sheet_prompt.py <story.json> <scene>`으로 프롬프트를 만들고, 출력된 `--ref`(character_image·env_image) 목록을 참조로 내장 image_gen을 호출한다(`media/<scene>-sheet-v1.png`). 검수 후 틀린 부분만 시트를 참조로 넣어 수정한다.
   3. **키프레임**: 시트와 기준 사진을 참조로 넣어 컷별 16:9 단독 프레임을 만든다.
   4. **영상**: 영상 모델이 있으면 시트+참조로 reference2video, 없으면 `animate_still.py` 애니매틱. 결과는 shot.versions에 기록한다. 이미지(image_gen)는 한 번에 하나씩 만들고, 애니매틱은 서로 독립된 샷끼리 병렬로 돌려도 된다. 체인 샷(앞 샷의 마지막 프레임을 이어받는 샷)은 순서대로 만든다.
7. **Review.** 버전마다 바이블 대비 드리프트, 연속성, 행동 완결 여부를 점검한다. 실패한 샷만 다시 만들거나 modify로 고친다.
8. **Edit.** `ai-director-edit`으로 타임라인을 만든다. 클립 배치, 트림, 트랜지션, VO와 BGM, 자막이 이 단계다.
9. **Gate 2 (러프컷 확인)** 후 **Export.** `render_timeline.py`로 mp4를 만들고 경로를 보고한다.

## 사용자 요청 → 동작

| 요청 | 동작 |
|---|---|
| "처음부터 만들어줘" | 1→9 전체 |
| "@S1-2 더 극적으로" | 해당 샷의 프롬프트와 카메라를 수정하고 새 version을 만든다. 타임라인 클립은 유지한다 |
| "주인공 옷 바꿔" | 바이블을 수정한 뒤, 영향받는 샷 목록과 재생성 비용을 보여주고 확인받는다 |
| "더 빨리 / 30초로" | 편집으로 해결한다(트림, 속도, 샷 삭제). 재생성이 필요한지는 마지막에 판단한다 |
| "음악 넣어줘" | bgm 트랙을 추가하고, VO가 있으면 볼륨을 낮춘다 |
| "내보내줘" | 검증 후 렌더한다 |

## 출력 블록

채팅 응답은 OpenArt의 블록 타입을 본뜬 짧은 섹션으로 쓴다.

- `[scene]` / `[shot]`: 표 한 줄씩
- `[character]`: 앵커 문자열과 참조 이미지 경로
- `[generation_starting]`: 무엇을 어떤 모드로 몇 개 만드는지
- `[generation_summary]`: 성공/실패 수와 새 version ID
- `[awaiting_user_input]`: 선택지 2~4개

프로토콜 상세는 [event-protocol.md](references/event-protocol.md)에 있다.

## 시스템 프롬프트

다른 LLM이나 앱에 이 감독 에이전트를 심을 때는 [system-prompt.md](references/system-prompt.md)를 그대로 쓴다. 이 세션에서 직접 감독할 때도 같은 규칙을 따른다.

## 완료 전 점검

- `python <skills>/ai-director/scripts/validate_story.py stories/<slug>/story.json` 결과에 오류가 없어야 한다.
- 모든 활성 샷에 `active_version_id`가 있어야 한다.
- 타임라인 총 길이가 목표 길이와 맞아야 한다.
- 렌더 파일이 존재하고 ffprobe로 길이를 확인했어야 한다.
- 비용이 드는 호출은 모두 승인받은 범위 안이어야 한다.
