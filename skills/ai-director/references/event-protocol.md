# 에이전트 이벤트 프로토콜

OpenArt는 세션마다 이벤트 로그 `{seq, kind, payload}`를 저장한다. 이 로그를 WebSocket(`/api/auth/ws-token`으로 토큰 발급)으로 UI에 실시간으로 보낸다. 앱을 직접 만들 때 그대로 쓸 수 있는 최소 집합은 아래와 같다.

| kind | 누가 | payload 예 | 의미 |
|---|---|---|---|
| `user_message` | 사용자 | `{text, mentions:[{type:"shot",id}], attachments}` | 턴 시작 |
| `assistant_text` | 에이전트 | `{text}` | 짧은 설명 |
| `block` | 에이전트 | `{type:"scene"\|"shot"\|"character"\|"reference"\|"voice"\|"music"\|"handoff", data}` | 카드 렌더링 [관찰: 블록 타입명] |
| `generation_starting` | 에이전트 | `{jobs:[{target:"S1-1", mode, model}]}` | 생성 예고 [관찰] |
| `generation_submitted` | 서버 | `{job_id, target, history_id}` | 비동기 작업 등록 [관찰] |
| `generation_summary` | 에이전트 | `{done:[version_id], failed:[{target, reason}]}` | 결과 요약 [관찰] |
| `story_patch` | 서버 | JSON Patch | 스토리보드와 타임라인 동기화 |
| `awaiting_user_input` | 에이전트 | `{question, options:[...]}` | 턴 정지, 승인 대기 [관찰] |
| `transient_user_gate` | 에이전트 | `{reason:"credits"\|"login"}` | 일시 게이트 [관찰] |
| `done` / `stopped` / `error` | 서버 | `{message_id}` | 턴 종료 [관찰] |

## 상태 판정 (OpenArt 클라이언트 로직 요약)
- 마지막 `awaiting_user_input` 뒤에 `user_message`, `done`, `stopped`, `error`가 없으면 "입력 대기"다.
- 재실행(rerun) 같은 사용자 메시지는 새 턴으로 세지 않는다. `non_turn_action`으로 분류한다.
- 생성 작업은 history ID로 추적한다. 취소는 `/api/history/:id/cancel`, 결과는 ShotVersion으로 붙인다.

## 이 세션(Codex)에서의 대응
UI가 없으므로 블록을 채팅 섹션으로 출력한다. `awaiting_user_input`은 **선택지 질문**으로 대신한다: 번호 붙은 선택지 2~4개(추천에 "(추천)" 표시, 자유 입력 가능하다고 명시)를 보여주고, 답을 받을 때까지 다음 단계로 넘어가지 않는다. `story_patch`는 story.json 파일 편집으로 대신한다.
