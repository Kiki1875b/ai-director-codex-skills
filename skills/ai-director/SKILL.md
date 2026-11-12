---
name: ai-director
description: Use when the user wants to direct a multi-shot AI film, short drama, music video or long-form AI video end to end by chatting — story → reference board → character/world bible → storyboard (scenes and shots) → shot generation → timeline edit → export, with one Story document as the source of truth. 한국어 트리거는 AI 영화 감독, 디렉터 모드, 장편 AI 영상, 스토리보드부터 편집까지, 멀티샷 영상 제작. Calls ai-director-writer for the screenplay, ai-director-reference for camera/location/mood references, ai-director-consistency for character/background reference images and sheets, ai-director-shot-gen for scene production sheets, keyframes and clips, and ai-director-edit for the cut. Not for a single clip prompt (use ai-director-shot-gen) or a script only (use ai-director-writer).
---

> **경로:** `<skills>` = 이 SKILL.md가 있는 폴더의 상위 폴더(Codex 스킬 폴더). 스킬 안에서 `scripts/…`, `references/…`라고만 쓴 경로는 그 스킬 폴더 기준이다. 작업 폴더는 영상 프로젝트 루트(`stories/`가 있는 곳)다.
>
> **선택지 질문:** 번호 붙은 선택지 2~4개를 보여주고 추천안에 "(추천)"을 붙이며, 자유 입력도 된다고 적는다. 질문한 뒤에는 턴을 끝내고, 답이 올 때까지 다음 단계로 넘어가지 않는다. 추천안으로 혼자 진행하지 않는다.

# AI Director (오케스트레이터)

채팅으로 받은 영화 아이디어를 **Story 문서 하나**(`stories/<slug>/story.json`)로 관리한다. 그 문서를 단계별로 채워 완성 영상까지 만든다.

- Story → Scene → Shot → ShotVersion 계층
- tracks/clips 타임라인
- 생성 전 사용자 확인 게이트

에이전트용 시스템 프롬프트는 `references/system-prompt.md`에 있다.

## 함께 쓰는 스킬

| 단계 | 스킬 |
|---|---|
| 장르 추천·전문 시나리오(로그라인→아웃라인→초고→리뷰) | `ai-director-writer` + `screenplay-reviewer` 에이전트 |
| 재미 중심 대본 | `ai-video-fun-writer` (있으면) |
| 장면 의도·감정 비트·배우 블로킹·시선 인계 | `ai-director-scene-direction` |
| 레퍼런스 수집(구도·촬영 기법, 배경, 분위기)·출처·측정 증거 | `ai-director-reference` |
| 캐릭터·월드·스타일 고정, 연속성 | `ai-director-consistency` |
| 키 생성 전 구도·카메라·시선 높이·관객 시선 연결·무빙 설계 | `ai-director-cinematography` |
| 샷별 생성 모드·프롬프트·버전 | `ai-director-shot-gen` |
| 타임라인 편집·자막·음향·렌더 | `ai-director-edit` |

## 핵심 원칙

1. **Story JSON이 유일한 진실 원천이다.** 대화 내용, 생성물, 편집 결정은 모두 이 파일에 반영한다. 형식은 [story-schema.md](references/story-schema.md)를 따른다. 기본 경로는 `stories/<slug>/story.json`이다.
2. **ID는 바꾸지 않는다.** scene, shot, clip ID는 한 번 만들면 유지한다. 샷을 다시 생성해도 새 version만 추가하고 `active_version_id`만 바꾼다.
3. **고칠 때는 범위를 최소로 잡는다.** 사용자가 `@S2-3`처럼 씬이나 샷을 지목하면 그 대상만 수정한다. 전체를 다시 만들지 않는다.
4. **유료·외부 호출 전에는 반드시 확인을 받는다** (`awaiting_user_input`). 생성할 샷 수, 모델, 예상 비용·시간을 보여주고 승인을 받는다. 게시는 절대 자동으로 하지 않는다.
5. **개선은 최대 3회다**(사용자 결정 2026-11-10). 키프레임, 영상, 음성, 시나리오, 편집 등 리뷰를 받아 고치는 모든 작업이 대상이다. 3회째에도 통과하지 못하면 더 고치지 않는다. 남은 문제와 사용자가 정할 것을 보고하고 지시를 받는다. 회차는 스스로 고칠 때만 센다. 사용자가 명시적으로 지시한 재생성·수정은 회차에 넣지 않는다(사용자 2026-11-10).
6. **이미지를 먼저 만들고 영상으로 넘긴다.** 바이블(참조 시트)을 만들고, 키프레임 이미지를 만든 다음 image2video를 쓴다. 기본은 LTX 첫·끝 키이고, 실제 선택은 얼굴 크기·동작·카메라 조건과 `ai-director-shot-gen` 1절 표, `model-capabilities.md`를 따른다.

## 작업 흐름

각 단계가 끝나면 story.json을 저장한다. 사용자에게는 짧은 진행 블록으로 알린다(아래 "출력 블록" 참고).

1. **Intake.** 소재, 길이, 화면비, 톤, 금지 요소, 쓸 수 있는 생성 도구를 확인한다. **화면비는 기본값으로 채우지 않고 반드시 사용자에게 묻는다**: 9:16(세로) / 16:9(가로) / 2.39:1(시네마스코프) 중 선택(선택지 질문). 정한 값은 [aspect-ratios.md](references/aspect-ratios.md) 표대로 `story.format`, `export`, 키 프롬프트, 영상 생성 크기, 검수 크기에 적용한다. 나머지 빈칸은 기본값으로 채우고 한 줄로 밝힌다. 기본값: 60초, 시네마틱 실사, 1~3명, 8~12샷. 생성 도구 기본값은 로컬 Codex(이미지 전용)이고, 영상은 사용자의 원격 GPU ComfyUI가 있으면 LTX-2.5(`ltx_remote.py`, 기본값이 사용자 확정 설정, 2026-11-10)이고 Wan 2.2(`wan_remote.py`)는 대체 수단, 서버가 없으면 ffmpeg 애니매틱이다(`ai-director-shot-gen` 4절). 영상 모델이 따로 있으면 사용자가 알려준다. 사용자가 레퍼런스(영상·사진·링크·작품명)를 주면 이때 받아 `references[]`에 `candidate`로 넣는다(`ai-director-reference` 1절). 질문은 한 번에 하나만 하고, 막혀서 진행할 수 없을 때만 한다.
2. **Story (시나리오).** `ai-director-writer` 스킬을 불러 그 절차대로 진행한다(장르 추천 → 질문 → 로그라인~아웃라인 → 초고 → `screenplay-reviewer` 리뷰 → story.json 변환). writer가 scenes/shots와 새 바이블 항목까지 채운다. 사용자가 이미 대본을 줬으면 장르 추천과 질문을 건너뛰고 그 대본을 초고로 삼아 리뷰부터 한다. 병맛·브레인롯 숏폼이면 `ai-video-fun-writer`를 쓴다(없으면 writer의 코미디 플레이북).
2-1. **Scene direction.** `ai-director-scene-direction`으로 해당 장면의 관점·관계/정보 변화·행동 비트를 `scene.direction`에 기록한다. 인물이 누구의 어느 지점을 언제 보는지와 반응 순서를 정한다. 기존 대본과 확정 연출은 유지하며, 씬을 수정하는 요청은 해당 범위와 인접 컷만 다룬다.
2-2. **Reference board (선택).** `ai-director-reference`로 세 측면의 레퍼런스를 모은다: **구도·촬영 기법**(틸트업·다운, 푸시인, 크레인 등 → 4단계), **배경**(장소 사진·영상 → 3단계 장소 핸드북), **분위기**(빛·색·밝기·질감·리듬 → 룩 인터뷰). 원장은 story.json `references[]`, 적용은 범위별 `reference_links[]`(take/avoid)다. 측면별 씬당 최대 3개이고, 방향이 이미 정해진 측면은 건너뛴다. 출처·타임코드를 기록하고, 받은 파일을 `ref_probe.py`로 분석한다(링크만 있으면 증거를 만들지 않는다). 라이선스는 검사하지 않는다(사용자 결정 2026-11-11). 룩 인터뷰의 사전 질문(anti-slop 0절 1·2·6·7번)도 이 단계에서 한다. 사용자가 측면별로 고르고, 최종 확인은 5단계 Gate 1에 넣는다.
3. **Bible (기준 이미지와 시트 계획).** `ai-director-consistency` 스킬을 불러 앵커를 확정하고, 필요한 이미지 목록을 아래 순서로 정한다. 이미 있는 이미지는 검수만 하고 재사용한다. **새 이미지는 5단계 승인 뒤 6-1에서 만든다**(사용자가 이 단계에서 먼저 만들어 달라고 하면 그 이미지만 승인받고 만든다).
   1. 캐릭터마다 **정면 전신, 흰 배경 의상 기준** 1장(`refs/<id>_front.png`)과 **얼굴 기준 사진**(배우 프로필 톤 머리·어깨, `refs/<id>_face_v1.png`) 1장. 전신만 있으면 모델이 아이돌 얼굴을 지어낸다.
   2. 캐릭터 시트 1장: 기준 사진을 `character_image1`로 넣고 턴어라운드·클로즈업·표정·의상 디테일(`refs/<id>_sheet_v1.png`).
   3. 월드마다 **실제 장소 핸드북**(`script/08-env-handbook.md`: 실제 지명, 있는 사물, 실제 광원, 없는 것)을 쓰고(승인된 location 레퍼런스의 take/avoid를 옮긴다), 그걸로 **배경 기준 이미지**를 만든다: 사람 없는 와이드 1장 + 주요 각도 1~2장(`refs/<id>_wide.png`), 인물 자리의 빛을 적은 "Lighting note for actors" 포함. 중요 소품은 3방향 제품 컷 1장.
   4. 결과를 view_image로 보고 앵커와 비교 검수한 뒤 `ref_images`에 등록한다(정체성 기준은 `ref_images[0]` = 얼굴 기준).
   5. 스타일 앵커는 분위기 단어(cinematic, melancholic, teal-and-amber, neon) 없이 실제 필름·질감·광원 규칙으로 쓴다(`<skills>/ai-director-consistency/references/anti-slop.md`).
4. **Storyboard / 촬영 설계.** `ai-director-cinematography` 0·2-1절을 **키프레임 생성 전에** 적용한다. 승인된 camera 레퍼런스가 있는 샷은 그 take를 `shot.staging`과 `shot.success_criteria.camera`로 옮긴다. 장소 블록아웃을 바탕으로 인물·목표 높이, 대화축, 카메라 위치/높이, 구도, 시선 대상, 관객 관심점 입구/출구를 `shot.staging`에, 앞 컷과의 연결은 `shot.cut_link`에 기록한다. writer가 만든 씬과 샷을 점검·보완한다. 샷마다 아래 항목이 채워져 있어야 한다.
   - 주요 행동 하나
   - 카메라
   - 길이
   - 등장 ID
   - start_state / end_state
   - 대사, 효과음
   - 생성 모드
   - 해당 장면의 연출 비트와 시선/관객 관심점 인계
   - `scripts/validate_story.py`로 검사한다.
4-1. **연속 콘티 계획 점검.** 인접 컷을 순서대로 놓고 인물 시선(목표·높이·축)과 관객 시선(관심점·다음 대상을 찾는 단서)을 따로 확인한다. 아직 없는 키/영상은 미확정으로 적고, 배치가 해결되지 않은 컷의 생성은 보류한다. 생성 후에는 계획 키 대신 실제 사용 프레임·구간으로 다시 검수한다(`ai-director-cinematography/references/eyeline-continuity.md`). 계획 점검은 영상 pass가 아니다.
5. **Gate 1 (계획 승인).** 스토리보드 표, 바이블 요약, 생성 예산을 보여주고 승인을 기다린다.
5-1. 승인 표에는 2-2단계 레퍼런스 보드(측면별 승인 목록), 3단계 이미지(얼굴·의상 기준·캐릭터 시트·배경), 스타일 프레임 2장, 씬 시트, 키프레임, 영상 개수를 모두 넣는다.
6. **Generate.** `ai-director-shot-gen`으로 아래 순서로 만든다.
   1. 3단계 기준 이미지·시트(아직 없으면)
   2. **룩 확정 게이트**: 룩 인터뷰의 사전 질문(레퍼런스, 사실감↔화사함, 장소 실재감, 금지 룩)은 2-2에서 끝냈다. 여기서는 남은 질문(얼굴 톤, 밝기, 색 룩·LUT — `<skills>/ai-director-consistency/references/anti-slop.md` 0절)을 이미지로 보여 주며 묻는다. 승인된 mood 레퍼런스의 측정값(휘도·대비·지배색)은 비교 기준 후보로만 쓴다. 그다음 가장 어두운 씬과 가장 따뜻한 씬의 스타일 프레임 2장을 만들어 기존 컷과 비교해 보여주고, `night_exposure.py --compare`로 밝기를 고르게 한 뒤 승인받는다(`ai-director-consistency` 1-1). **승인 전에는 키프레임을 대량으로 만들지 않는다.** 피드백은 하나씩 온다(얼굴 → 톤 → 광원·배우 위치 → 장소 → 밝기). 지적된 것만 고쳐 1~2장씩 다시 보여준다.
   3. **씬 프로덕션 시트**: 씬마다 `<skills>/ai-director-consistency/scripts/build_sheet_prompt.py <story.json> <scene>`으로 프롬프트를 만들고, 출력된 `--ref`(character_image·env_image) 목록을 참조로 내장 image_gen을 호출한다(`media/<scene>-sheet-v1.png`). 검수 후 틀린 부분만 시트를 참조로 넣어 수정한다.
   4. **키프레임**: 4단계의 연출·촬영 설계와 앞뒤 연결을 입력으로, 얼굴·의상 기준, 밝기 보정한 배경 기준, 소품을 참조로 넣어 컷별 단독 프레임을 작품 화면비로 만든다(`references/aspect-ratios.md`)(프롬프트 줄 순서와 LOOK 블록은 `ai-director-shot-gen` 2절). 시트가 옛 룩이면 참조로 넣지 않는다. 처음 3장을 앞뒤 구도와 함께 보고 문제가 없을 때 나머지를 돌린다. 단독 이미지 PASS와 컷 연결 검수를 구분한다.
   5. **영상**: `ai-director-shot-gen` 1절 표로 방식을 고른다(기본 LTX 첫·끝 키). 영상 모델을 쓰지 않으면 `animate_still.py` 애니매틱. 결과는 shot.versions에 기록한다. 이미지(image_gen)는 한 번에 하나씩 만들고, 애니매틱은 서로 독립된 샷끼리 병렬로 돌려도 된다. 체인 샷(앞 샷의 마지막 프레임을 이어받는 샷)은 순서대로 만든다.
7. **Review.** 버전마다 바이블 대비 드리프트, 연속성, 행동 완결 여부를 점검하고 인접 컷의 실제 사용 구간에서 인물 시선과 관객 관심 이동을 별도로 검수한다. 실패한 샷만 다시 만들거나 부분 편집·후처리로 고친다. 잠긴 영상에서는 결함과 허용된 조치만 보고하고, 트림·순서·대사 위치를 자동 변경하지 않는다. 의도된 하드컷·정적은 유지한다.
8. **Edit.** `ai-director-edit`으로 타임라인을 만든다. 클립 배치, 트림, 트랜지션, VO와 BGM, 자막이 이 단계다.
8-1. **씬 검수 (씬 하나가 완성될 때마다).** 한 씬의 모든 컷이 렌더 트랙에 활성 버전으로 놓이면 `render_timeline.py --preview`로 렌더하고 `scene-reviewer` 에이전트로 그 씬을 검수한다(`ai-director-scene-direction` 5절, 기준표 `references/scene-rubric.md`). 컷 단위 검수(7단계)를 대신하지 않는다. 고칠 때는 편집부터, 재생성은 승인 후. 결과(판정, 시청 확인 질문)를 사용자에게 렌더와 함께 보여 준다. 씬 안의 컷을 바꾸면 그 씬을 다시 검수한다.
9. **Gate 2 (러프컷 확인)** 후 **Export.** `render_timeline.py`로 mp4를 만들고 경로를 보고한다.

## 사용자 요청 → 동작

| 요청 | 동작 |
|---|---|
| "처음부터 만들어줘" | 1→9 전체 |
| "@S1-2 더 극적으로" | 해당 샷의 프롬프트와 카메라를 수정하고 새 version을 만든다. 타임라인 클립은 유지한다 |
| "주인공 옷 바꿔" | 바이블을 수정한 뒤, 영향받는 샷 목록과 재생성 비용을 보여주고 확인받는다 |
| "더 빨리 / 30초로" | 편집으로 해결한다(트림, 속도, 샷 삭제). 재생성이 필요한지는 마지막에 판단한다 |
| "S2 틸트업 레퍼런스 찾아줘" / "이 영상 분위기로" | `ai-director-reference`로 해당 측면·범위만 후보를 모으고 원장에 넣는다. 승인 전에는 바이블·촬영 설계를 바꾸지 않는다 |
| "음악 넣어줘" | bgm 트랙을 추가하고, VO가 있으면 볼륨을 낮춘다 |
| "내보내줘" | 검증 후 렌더한다 |

## 출력 블록

채팅 응답은 아래 짧은 섹션으로 쓴다.

- `[scene]` / `[shot]`: 표 한 줄씩
- `[character]`: 앵커 문자열과 참조 이미지 경로
- `[generation_starting]`: 무엇을 어떤 모드로 몇 개 만드는지
- `[generation_summary]`: 성공/실패 수와 새 version ID
- `[awaiting_user_input]`: 선택지 2~4개


## 시스템 프롬프트

다른 LLM이나 앱에 이 감독 에이전트를 심을 때는 [system-prompt.md](references/system-prompt.md)를 그대로 쓴다. 이 세션에서 직접 감독할 때도 같은 규칙을 따른다.

## 완료 전 점검

- `python <skills>/ai-director/scripts/validate_story.py stories/<slug>/story.json` 결과에 오류가 없어야 한다.
- 모든 활성 샷에 `active_version_id`가 있어야 한다.
- 모든 씬에 최신 씬 검수(`stories/<slug>/reviews/<scene>-scene-v<n>.md`)가 있고, 그 뒤로 씬 안의 컷이 바뀌지 않았어야 한다.
- 타임라인 총 길이가 목표 길이와 맞아야 한다.
- 렌더 파일이 존재하고 ffprobe로 길이를 확인했어야 한다.
- 비용이 드는 호출은 모두 승인받은 범위 안이어야 한다.
