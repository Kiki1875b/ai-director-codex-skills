# 프롬프트 예시

창작 예시다. 바이블은 `ai-director-consistency/references/bible-template.md`의 미나와 골목을 쓴다.

## S1-1: 우산을 펼치는 컷 (image2video)

**키프레임**
```
late-20s Korean woman, slim build, short straight black bob with blunt bangs, round thin silver glasses, small mole under left eye, mustard-yellow vinyl raincoat over grey hoodie,
holding a transparent dome umbrella with glossy red J-handle, closed, in her left hand,
narrow Seoul back alley at night, wet asphalt reflecting pink and cyan neon, stacked AC units, light rain,
she looks up at the rain, medium shot, eye level, 35mm,
neon rim light from frame right, cinematic live-action, 35mm anamorphic, shallow depth of field, teal-and-amber grade, light film grain
negative: on-screen text, watermark, extra fingers, duplicated people
```

**모션**
```
She raises the closed umbrella and pops it open overhead in one smooth motion; raindrops bead and slide on the clear dome;
slow push-in from medium to medium close-up; calm pace; steady rain and neon flicker in the background.
Ends with the umbrella fully open, held in her right hand, her gaze turning to frame right.
```

## S1-2: 체인 컷 (앞 샷의 마지막 프레임에서 시작)

- 입력: `media/S1-1-v1_last.png`
- `start_state` = S1-1의 `end_state`
```
She steps forward toward frame right under the open umbrella; puddles splash softly at her boots;
camera tracks alongside at walking pace, static height. Ends with her pausing at a lit doorway.
```

## S2-1: 두 인물이 나오는 컷 (reference2video)

- 참조: `refs/ch_mina_front.png`, `refs/ch_jun_front.png`, `refs/wd_alley_wide.png`
```
Mina (yellow raincoat, left side of frame) hands the red-handled umbrella to Jun (right side of frame); Jun hesitates, then takes it;
static two-shot, eye level; light rain; ends with Jun holding the umbrella, Mina's hands empty.
```
화면 방향을 프롬프트에 명시한다(미나는 왼쪽, 준은 오른쪽). 씬이 끝날 때까지 이 배치를 바꾸지 않는다.

## 스토리보드 표 형식 (사용자에게 보여줄 때)

| 샷 | 길이 | 행동 | 카메라 | 등장 | 시작 → 끝 상태 | 모드 | 대사/소리 |
|---|---|---|---|---|---|---|---|
| S1-1 | 5s | 우산을 편다 | MS, push-in | 미나 | 접힘·왼손 → 펼침·오른손 | img→vid | 빗소리 |
| S1-2 | 4s | 문 앞까지 걷는다 | tracking | 미나 | 펼침 → 문 앞 정지 | chain | 발소리 |
