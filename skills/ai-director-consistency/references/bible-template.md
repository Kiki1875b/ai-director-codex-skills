# 바이블 템플릿

```jsonc
"bible": {
  "style": {
    "anchor": "cinematic live-action, 35mm anamorphic, shallow depth of field, teal-and-amber grade, light film grain",
    "palette": ["#0F2A3A", "#E8A33D", "#C9D6DF"],
    "negative": "on-screen text, watermark, extra fingers, duplicated people"
  },
  "characters": [
    {
      "id": "ch_mina",
      "name": "미나",
      "anchor": "late-20s Korean woman, slim build, short straight black bob with blunt bangs, round thin silver glasses, small mole under left eye, mustard-yellow vinyl raincoat over grey hoodie",
      "variants": { "dress": "ch_mina@dress" },
      "ref_images": ["refs/ch_mina_front.png", "refs/ch_mina_34.png", "refs/ch_mina_side.png"],
      "voice": { "provider": "", "voice_id": "", "notes": "낮고 건조한 톤" }
    }
  ],
  "objects": [
    { "id": "ob_umbrella", "anchor": "transparent dome umbrella with glossy red J-handle", "ref_images": [] }
  ],
  "worlds": [
    { "id": "wd_alley", "anchor": "narrow Seoul back alley at night, wet asphalt reflecting pink and cyan neon, stacked AC units, light rain", "ref_images": ["refs/wd_alley_wide.png"] }
  ]
}
```

## 참조 시트 생성 프롬프트 형식

- 캐릭터: `character reference sheet, [anchor], front view, three-quarter view, side view, full body, neutral expression, plain light-grey background, even studio lighting, [style anchor]`
- 표정 시트: `[anchor], head-and-shoulders, expressions: neutral / surprised / smiling, plain background, [style anchor]`
- 오브젝트: `product-style reference of [anchor], three angles, plain background, even lighting`
- 월드: `[anchor], wide establishing shot, no people, [style anchor]`

시트 이미지는 `refs/` 아래 저장하고 `ref_images`에 상대경로로 기록한다.
