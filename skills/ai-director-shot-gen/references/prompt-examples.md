# 프롬프트 예시

창작 예시다. 바이블은 `<skills>/ai-director-consistency/references/bible-template.md`의 미나와 골목을 쓴다. 줄 순서와 LOOK 블록은 SKILL.md 2절, 근거는 `<skills>/ai-director-consistency/references/anti-slop.md`.

## S1-1: 우산을 펼치는 컷 (image2video)

**키프레임**
- 참조: `character_image1=refs/ch_mina_face_v1.png`, `character_image2=refs/ch_mina_front.png`, `env_image1=refs/wd_alley_wide_v1_darkA.png`, `object_image1=refs/ob_umbrella.png`
```
Landscape 16:9 single film frame.
Image roles: character_image1 = identity of the woman (face, hair, glasses) — match exactly. character_image2 = her costume only.
env_image1 = THE LOCATION: reproduce this exact alley, its look, colors and lighting. object_image1 = the umbrella.
Blocking and camera: she stands on the wet alley floor about 3 m from camera, on the right third, body turned three-quarters
to camera left, physically inside the space at the correct scale; medium shot at eye level, 40mm; a stack of plastic crates
out of focus in the left foreground.
Action: she has just stopped walking and looks up at the rain past the lens, the closed umbrella hanging from her left hand.
late-20s Korean woman, slim build, short straight black bob with blunt bangs, round thin silver glasses, small mole under left eye,
mustard-yellow vinyl raincoat over grey hoodie. Prop: transparent dome umbrella with glossy red J-handle, closed.
Location: narrow back alley in Euljiro, Seoul at night in light rain … (월드 앵커 원문)
LIGHTING: the cold white LED security lamp on the utility pole above and behind-left of her edges her hair and the top of the
raincoat; a fluorescent window on the second floor gives a soft key on the left side of her face. No other light.
LOOK (whole frame): photorealistic film still … (anti-slop.md 3절 원문)
negative: [style.negative]
```

**모션**
```
She raises the closed umbrella and pops it open overhead in one smooth motion; raindrops bead and slide on the clear dome;
slow push-in from medium to medium close-up; calm pace; steady thin rain crossing the lamp light.
Ends with the umbrella fully open, held in her right hand, her gaze turning to frame right.
```

## S1-2: 체인 컷 (앞 샷의 마지막 프레임에서 시작)

- 입력: `media/S1-1-v1_last.png`
- `start_state` = S1-1의 `end_state`
```
She steps forward toward frame right under the open umbrella; puddles splash softly at her boots;
camera tracks alongside at walking pace, static height. Ends with her pausing at a lit doorway.
```

## S2-1: 두 인물이 나오는 컷 (두 인물이 모두 들어간 키 + 첫·끝 키)

- 참조: `refs/ch_mina_face_v1.png`, `refs/ch_jun_face_v1.png`, `refs/wd_alley_wide_v1_darkA.png`
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
