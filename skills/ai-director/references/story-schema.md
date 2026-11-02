# Story 문서 스키마

OpenArt 번들의 zod 스키마에서 관찰한 필드는 **굵게** 표시했다. 나머지는 로컬 제작용으로 추가한 필드다. 시간 단위는 모두 ms다.

```jsonc
{
  "story": {
    "id": "st_xxx", "title": "", "logline": "",
    "format": { "aspect_ratio": "16:9", "resolution": "1080p", "fps": 30 }   // **format.aspect_ratio/resolution**
  },
  "bible": {
    "style":   { "anchor": "35mm film look, teal-orange grade, soft haze", "palette": ["#..."], "negative": "text, watermark" },
    "characters": [ { "id": "ch_mina", "name": "미나", "anchor": "late-20s Korean woman, short black bob, round silver glasses, mustard raincoat",
                      "ref_images": ["refs/ch_mina_sheet.png"], "voice": { "provider": "elevenlabs", "voice_id": "" } } ],
    "objects":    [ { "id": "ob_umbrella", "anchor": "transparent bubble umbrella with red handle", "ref_images": [] } ],
    "worlds":     [ { "id": "wd_alley", "anchor": "narrow Seoul alley at night, wet asphalt, neon signs", "ref_images": [] } ]
  },
  "scenes": [
    { "id": "S1", "order": 1, "title": "", "world_id": "wd_alley", "summary": "",
      "spatial_anchor": "", "lighting": "",          // 시트 생성용: 방위·랜드마크·동선, 조명 방향·시간대
      "shots": [
        { "id": "S1-1", "order": 1, "duration_ms": 5000,
          "action": "미나가 우산을 펼친다", "camera": "MS, eye level, slow push-in",
          "characters": ["ch_mina"], "objects": ["ob_umbrella"],
          "start_state": "우산 접힘, 왼손", "end_state": "우산 펼침, 오른손, 화면 오른쪽을 봄",
          "dialogue": [ { "character": "ch_mina", "text": "" } ], "sfx": "빗소리",
          "mode": "image2video",                      // text2video|image2video|reference2video|element2video|extend|modify
          "chain_from": null,                         // 이전 샷 ID: 그 샷의 마지막 프레임을 첫 프레임으로 쓴다
          "keyframe_prompt": "", "video_prompt": "",
          "versions": [ { "id": "S1-1-v1", "kind": "video", "model": "", "prompt": "", "seed": null,
                          "media_url": "media/S1-1-v1.mp4", "status": "done", "notes": "" } ],
          "active_version_id": "S1-1-v1" }
      ] }
  ],
  "timeline": {
    "tracks": [                                              // **id,type(video|audio|text|other),subtype(vo|bgm),order,muted,hidden,volume**
      { "id": "tr_v1", "type": "video", "order": "a", "muted": false, "hidden": false, "volume": 1 },
      { "id": "tr_vo", "type": "audio", "subtype": "vo",  "order": "b", "volume": 1 },
      { "id": "tr_bgm","type": "audio", "subtype": "bgm", "order": "c", "volume": 0.35 },
      { "id": "tr_txt","type": "text", "order": "d" }
    ],
    "clips": [
      { "id": "cl_1", "kind": "shot", "track_id": "tr_v1", "shot_id": "S1-1",        // **kind shot|resource**
        "timeline_start_ms": 0, "source_in_ms": 0, "source_out_ms": 5000,           // **필드명 그대로**
        "speed": 1, "media_url": "media/S1-1-v1.mp4", "media_kind": "video",         // **speed 0.5–2, media_kind video|image**
        "volume": 1, "muted": false, "enabled": true,                                // **volume 0–3**
        "transition_in": null },                                                     // **{type,duration_ms≤5000,direction?}**
      { "id": "cl_bgm", "kind": "resource", "track_id": "tr_bgm", "timeline_start_ms": 0,
        "source_in_ms": 0, "source_out_ms": 30000, "media_url": "audio/bgm.mp3", "media_kind": "audio" },
      { "id": "cl_cap1", "kind": "text", "track_id": "tr_txt", "timeline_start_ms": 500,
        "duration_ms": 2500, "text": "비가 그치지 않는 밤", "position": "bottom" }
    ]
  },
  "export": { "fps": 30, "width": 1920, "height": 1080, "sample_rate": 48000, "file_format": "mp4" }  // **export 스키마**
}
```

## 규칙 (OpenArt 제약을 그대로 따름)
- `transition_in.type`: `dissolve | fade | slide | wipe | clock_wipe | iris | zoom`. 기본 길이 500ms, 최대 5000ms. `direction`: `left|right|up|down|in|out`.
- 클립의 실제 길이는 `(source_out_ms - source_in_ms) / speed`다.
- `timeline_start_ms`가 기준이다. 트랜지션 클립은 `이전 클립 끝 - transition.duration_ms`에서 시작해야 한다. 겹치지 않으면 트랜지션이 무시되고 하드컷이 된다. 이전 클립 끝보다 뒤에서 시작하면 그 사이는 검은 화면이 된다.
- `media_kind`는 필수다(video, image, audio).
- 이미지 클립(`media_kind: image`)은 source_in/out을 표시 길이로 쓴다.
- export 제약: fps 1–60, 해상도 최대 3840×2160, sample_rate 16k–48k, 형식 mp4 또는 mov.
- OpenArt는 `media_url`에 https만 허용한다. 로컬 렌더에서는 story.json 기준 상대경로나 절대경로를 허용한다.
- `kind: text`는 로컬 확장이다. OpenArt에도 text 트랙은 있지만 텍스트 클립 스키마는 관찰하지 못했다.
