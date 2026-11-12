# 바이블 템플릿

```jsonc
"bible": {
  "style": {
    // 분위기 단어(cinematic, melancholic, teal-and-amber, neon) 대신 실제 필름·렌즈·질감·광원 규칙을 쓴다. anti-slop.md 3절
    "anchor": "photorealistic film still from a Korean drama feature shot on a real location on Kodak Vision3 500T 35mm film with a spherical lens; natural fine film grain, gentle lens softness; real textures (natural skin with fine texture, worn and used materials); natural restrained color, moderate saturation; light only from the practical sources in the scene, faces lit by those sources; blacks deep but not crushed; off-center composition with foreground depth",
    "palette": ["#101418", "#D9A35B", "#C9D3D6"],
    "negative": "on-screen text, readable signage, watermark, extra fingers, duplicated people, teal-and-orange grade, oversaturation, rim light on everything, bokeh balls, light rays, HDR, glossy shine, plastic skin, beauty filter, cyberpunk",
    "look_frames": ["media/style-S1-v1.png", "media/style-S3-v1.png"],  // 룩 확정 게이트에서 승인된 스타일 프레임
    "grade": "야외 밤 -0.9 stop / gamma 1.15 (night_exposure.py)",
    "notes": "이전 앵커와 변경 사유"
  },
  "characters": [
    {
      "id": "ch_mina",
      "name": "미나",
      "anchor": "late-20s Korean woman, slim build, short straight black bob with blunt bangs, round thin silver glasses, small mole under left eye, mustard-yellow vinyl raincoat over grey hoodie",
      "variants": { "dress": "ch_mina@dress" },
      // [0]=얼굴 기준(배우 프로필 톤 머리·어깨) [1]=정면 전신(의상) [2]=시트
      "ref_images": ["refs/ch_mina_face_v1.png", "refs/ch_mina_front.png", "refs/ch_mina_sheet_v1.png"],
      "voice": { "provider": "", "voice_id": "", "notes": "낮고 건조한 톤" }
    }
  ],
  "objects": [
    { "id": "ob_umbrella", "anchor": "transparent dome umbrella with glossy red J-handle", "ref_images": [] }
  ],
  "worlds": [
    {
      "id": "wd_alley",
      // 실제 장소 핸드북(script/08-env-handbook.md)에서: 실제 지명, 있는 사물, 실제 광원, 없는 것
      "anchor": "narrow back alley in Euljiro, Seoul at night in light rain: worn 3-story tiled buildings, faded green rolling shutters, stacked plastic crates, an AC outdoor unit, a utility pole with a cold white LED security lamp, patched asphalt with a drain grate and a few puddles; no neon",
      "ref_images": ["refs/wd_alley_wide_v1_darkA.png", "refs/wd_alley_wide_v1.png"],
      "notes": "폐기한 기준과 사유"
    }
  ]
}
```

## 참조 이미지 생성 프롬프트 형식

- 얼굴 기준: `Photorealistic real photograph: a professional profile photo of a Korean film actor/actress, the same person as character_image1, head and shoulders, plain warm-grey backdrop. Keep from character_image1: [hair, costume, face shape]. [장르 주인공다운 매력 한 줄]. Clear healthy skin with natural fine texture (not airbrushed, not plastic), very light film makeup, eyes looking just beside the lens. Large soft key light from camera left. No heavy retouching, no glossy plastic skin, no idol-style beauty filter, no strong rim light. Portrait 4:5. No text.`
- 의상 기준(정면 전신): `[anchor], full body front view, standing straight, plain white background, even light`
- 캐릭터 시트: `character reference sheet, [anchor], front view, three-quarter view, side view, full body, neutral expression, plain light-grey background, even studio lighting, [style anchor]`
- 오브젝트: `product-style reference of [anchor], three angles, plain background, even lighting`
- 월드(참조 없이 새로): `Photorealistic real photograph, an empty location scouting plate taken at night by a film crew on Kodak Vision3 500T, no people. Real, specific, ordinary and slightly messy — not stylized, not cyberpunk, not a game environment. No readable text. Place: [핸드북 묘사]. Light — only real sources: [광원 목록]. Lighting note for actors: [인물 자리의 빛].`

시트 이미지는 `refs/` 아래 저장하고 `ref_images`에 상대경로로 기록한다.
