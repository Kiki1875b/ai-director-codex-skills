# 단계별 지시문과 출력 스키마

각 단계는 아래 **공통 머리말**을 먼저 따른다. `{…}`는 실제 값으로 채운다. 결과는 스키마 그대로 저장한다. 단계 사이에서 앞 단계의 확정 결과 외의 아이디어를 몰래 바꾸지 않는다.

## 공통 머리말 (시스템 역할)

```
너는 극영화와 숏폼 드라마를 쓰는 전문 시나리오 작가다.
장르: {genre} / 길이: {length} / 플랫폼: {platform} / 관객·등급: {audience}
반드시 쓸 자산(바이블): {bible_summary}   ← 외형 묘사는 앵커와 충돌하지 않게
사용자 요구: {answers}   피할 것: {avoid}
원칙: craft-rules.md 1~6절. 제작 제약: craft-rules.md 7절.
장르 플레이북: {genre_playbook_section}
오픈아트식 유형 지시(라이브 액션 단편일 때): "광고·트레일러·UGC가 아니라 실사 단편이다.
실제 공간, 동기 있는 조명, 믿을 수 있는 연기, 분명한 극적 척추를 쓰고 영화 문법을 유지한다."
```

마지막 줄은 OpenArt Director 퀵스타트의 `[Type: LIVE_ACTION_FEATURE_OR_SHORT]` 지시를 옮긴 것이다. 그쪽 입력 항목은 `[Short Film is about]`, `[Visual Style]`, `[Video duration]`, 예고편형은 `[Plot Script]`, `[Film Genre]`이다. 이 스킬의 Intake와 질문이 같은 항목을 채운다.

## 3-1 로그라인

```
서로 다른 방향의 로그라인 3개를 써라. 각 로그라인은 한 문장이며
[결함 있는 주인공]이 [촉발 사건] 때문에 [대가가 걸린 목표]를 위해 [강한 적대 세력]과 맞선다 를 담는다.
각 안에 극적 질문 한 줄, 훅(숏폼은 첫 5초 화면, 단편은 첫 장면) 한 줄, 주제 한 문장을 붙인다.
각 안마다 "독창성 점검" 한 줄: 톤 레퍼런스나 널리 알려진 작품과 겹치는 고유 설정(이름, 세계 규칙,
핵심 반전, 결말)이 있는지 쓰고, 있으면 바꾼다.
```
출력(`01-logline.md`): 안 A/B/C, 각 4줄. 사용자가 고른 안에 `✔`.

## 3-2 시놉시스와 인물표

```
고른 로그라인으로 시놉시스를 써라. 숏폼은 150~250자, 단편은 600~1000자.
결말까지 모두 쓴다(숨기지 않는다). 그다음 인물표를 쓴다.
```
출력(`02-synopsis.md`):
```
## 시놉시스
## 인물
- 이름 (bible id 또는 new) — 원하는 것 / 필요한 것 / 두려움 / 습관 하나 / 첫 등장 행동
## 주제
```

## 3-3 비트시트

```
craft-rules.md 2절의 길이별 템플릿으로 비트를 나눠라.
각 비트에 실제 사건, 가치 변화, 초(秒) 배분을 적어라. 합계는 {length_s}초.
도입에서 심을 것(setup)과 회수할 곳(payoff)을 짝지어라.
```
출력(`03-beats.json`):
```json
{"length_s": 90,
 "beats": [{"name": "훅", "event": "", "value_shift": "평온→불안", "seconds": [0, 5]}],
 "setups": [{"setup": "", "beat": "훅", "payoff": "", "payoff_beat": "보상"}]}
```

## 3-4 스텝 아웃라인 (사용자 승인 지점)

```
비트를 장면으로 바꿔라. 장면마다 장소·시간을 정하고 목표→갈등→결과, 가치 변화를 적어라.
가치가 바뀌지 않는 장면은 만들지 마라. 장소는 재사용하라. 제작 제약을 지켜라.
```
출력(`04-outline.json`):
```json
{"scenes": [{"id": "S1", "heading": "S#1. 폐사찰 법당 (밤)", "world_id": "wd_temple",
  "characters": ["ch_gumiho"], "goal": "", "conflict": "", "outcome": "",
  "value_before": "", "value_after": "", "spatial_anchor": "", "lighting": "",
  "est_seconds": 15, "beats": ["훅", "설정"]}]}
```
사용자에게는 씬 표(헤딩 / 한 줄 요약 / 가치 변화 / 초)만 보여주고 선택지 질문으로 승인·수정을 묻는다.

## 3-5 초고

```
승인된 아웃라인으로 시나리오를 써라. 형식은 format-ko.md.
지문은 현재형, 보이는 것과 들리는 것만. 감정 단어 대신 행동.
대사는 서브텍스트. 숏폼은 한 줄 15자 안팎.
각 장면 끝에 (가치: A → B · 추정 N초) 주석을 남긴다(최종본에서는 지운다).
추정 초는 대사 글자 수(한국어 약 5~6자/초)와 지문 행동 수(행동 하나 2~4초)로 계산한다.
단편(180초 초과)은 시퀀스 단위로 나눠 쓰고, 시퀀스마다 저장한 뒤 다음으로 넘어간다.
```
출력: `05-draft-v1.md`.

## 수정 (리뷰 후)

```
리뷰 {review_path}의 수정 지시 중 범위가 '국소'인 항목만 고쳐라. 지적 위치 밖은 바꾸지 마라.
'구조' 항목은 여기서 고치지 않는다(SKILL.md 4단계: 아웃라인으로 돌아간다).
고친 곳마다 [수정: 항목명] 주석을 남겨 다음 리뷰가 확인할 수 있게 하라.
```
출력: `05-draft-v{n+1}.md`.

## 5 story.json 변환

```
최종 시나리오를 컷으로 나눠라. 컷 하나 = 주요 행동 하나, 3~10초.
shot 필드: id, order, duration_ms, action, camera(숏 크기, 앵글, 움직임), characters, objects,
start_state, end_state(다음 컷 start_state와 이어지게), dialogue[{character, text}], sfx, mode, chain_from.
scene 필드: id, order, title, world_id, summary, spatial_anchor, lighting, shots[].
shots는 반드시 해당 scene 객체 안에 넣는다. 최상위 shots 배열을 만들지 않는다.
shot id는 "<scene id>-<번호>"(예: S1-1). 기존 샷이 있으면 그 id를 유지한다.
새 샷은 그 씬에서 아직 쓰지 않은 다음 번호를 쓰고(사이에 끼워도 S1-5처럼), 순서는 order로 정한다.
mode: 인물 1명 → image2video, 인물 2명 이상이나 소품이 중요 → reference2video,
      인물 없는 인서트·풍경 → text2video. mode 값은 이 셋과 element2video, extend, modify만 쓴다.
chain_from: 앞 컷과 동작이 이어지면 직전 샷 id, 아니면 null. (chain_from은 mode 값이 아니다)
dialogue.character는 바이블 id(예: ch_gumiho)로 쓴다. 내레이션은 {"character": "narrator", "text": ""}로
쓰고 바이블에 없어도 된다. narrator는 dialogue에만 쓰고 shot.characters에는 넣지 않는다. 대사 줄 앞 이름을 id로 바꾸는 표를 변환 전에 만든다.
world_id는 bible.worlds에 있는 id여야 한다. 없으면 먼저 worlds에 추가한다.
```
