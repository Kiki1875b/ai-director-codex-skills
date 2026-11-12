# Story 문서 스키마

시간 단위는 모두 ms다. 주석은 필드의 허용 값이다.

```jsonc
{
  "story": {
    "id": "st_xxx", "title": "", "logline": "",
    "format": { "aspect_ratio": "16:9", "resolution": "1080p", "fps": 30 }   // format.aspect_ratio/resolution
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
          "chain_from": null,                         // 이전 샷 ID: 그 샷의 마지막 프레임을 첫 프레임으로 쓴다
          "keyframe_prompt": "", "video_prompt": "",
          "versions": [ { "id": "S1-1-v1", "kind": "video", "model": "", "prompt": "", "seed": null,
                          "media_url": "media/S1-1-v1.mp4", "status": "done", "notes": "" } ],
          "active_version_id": "S1-1-v1" }
      ] }
  ],
  "timeline": {
    "tracks": [                                              // id,type(video|audio|text|other),subtype(vo|bgm),order,muted,hidden,volume
      { "id": "tr_v1", "type": "video", "order": "a", "muted": false, "hidden": false, "volume": 1 },
      { "id": "tr_vo", "type": "audio", "subtype": "vo",  "order": "b", "volume": 1 },
      { "id": "tr_bgm","type": "audio", "subtype": "bgm", "order": "c", "volume": 0.35 },
      { "id": "tr_txt","type": "text", "order": "d" }
    ],
    "clips": [
      { "id": "cl_1", "kind": "shot", "track_id": "tr_v1", "shot_id": "S1-1",        // kind shot|resource
        "timeline_start_ms": 0, "source_in_ms": 0, "source_out_ms": 5000,           
        "version_id": "S1-1-v1",                                             // 샷을 나타내는 영상 클립은 shot_id + version_id 필수(export)
        "speed": 1, "media_url": "media/S1-1-v1.mp4", "media_kind": "video",         // speed 0.5–2, media_kind video|image
        "volume": 1, "muted": false, "enabled": true,                                // volume 0–3
        "transition_in": null },                                                     // {type,duration_ms≤5000,direction?}
      { "id": "cl_bgm", "kind": "resource", "track_id": "tr_bgm", "timeline_start_ms": 0,
        "source_in_ms": 0, "source_out_ms": 30000, "media_url": "audio/bgm.mp3", "media_kind": "audio" },
      { "id": "cl_cap1", "kind": "text", "track_id": "tr_txt", "timeline_start_ms": 500,
        "duration_ms": 2500, "text": "비가 그치지 않는 밤", "position": "bottom" }
    ]
  },
  "export": { "fps": 30, "width": 1920, "height": 1080, "sample_rate": 48000, "file_format": "mp4" }
}
```

## 규칙
- `transition_in.type`: `dissolve | fade | slide | wipe | clock_wipe | iris | zoom`. 기본 길이 500ms, 최대 5000ms. `direction`: `left|right|up|down|in|out`.
- 클립의 실제 길이는 `(source_out_ms - source_in_ms) / speed`다.
- `timeline_start_ms`가 기준이다. 트랜지션 클립은 `이전 클립 끝 - transition.duration_ms`에서 시작해야 한다. 겹치지 않으면 트랜지션이 무시되고 하드컷이 된다. 이전 클립 끝보다 뒤에서 시작하면 그 사이는 검은 화면이 된다.
- `media_kind`는 필수다(video, image, audio).
- 이미지 클립(`media_kind: image`)은 source_in/out을 표시 길이로 쓴다.
- export 제약: fps 1–60, 해상도 최대 3840×2160, sample_rate 16k–48k, 형식 mp4 또는 mov.
- `media_url`은 story.json 기준 상대경로나 절대경로다.
- `kind: text`는 자막 클립이다.

## 연출·촬영 설계

새로 설계하거나 시선·연결을 수정하는 범위에서 아래 기록을 사용한다. 기존 story.json의 마이그레이션이나 완료된 모든 샷의 재생성을 요구하지 않는다. `camera` 문자열, `start_state/end_state`, ID·버전·타임라인 필드는 그대로 유지한다.

| 위치 | 필드 | 내용 |
|---|---|---|
| Scene | `direction.viewpoint` | 관객이 따라갈 인물/관찰 위치와 이유 |
| Scene | `direction.dramatic_turn` | 장면 전후에 바뀌는 관계·정보 |
| Scene | `direction.beats[]` | 각 `{action, audience_learns, shot_ids}`. 관찰 가능한 사건과 관객에게 공개할 정보 |
| Shot | `staging.status` | `planned` 또는 `observed`. 설계 추정과 실제 관찰을 구분 |
| Shot | `staging.axis` | 인물·목표의 축과 카메라가 있는 쪽. 축이 바뀌면 재정향 근거 |
| Shot | `staging.camera` | `{position_m, look_at_m, lens_mm}`. 세트와 같은 좌표계. position_m/look_at_m은 `[x,y,z]` |
| Shot | `staging.blocking` | 인물·소품의 위치, 서기/앉기, 몸 방향, 눈높이·소품 높이 |
| Shot | `staging.gaze[]` | 각 `{actor_id, phase, target, target_point_m, screen_direction, height_relation}`. phase는 start/end 또는 비트 이름. 대상의 어느 부분인지와 실제 높이를 명시 |
| Shot | `staging.attention.entry/exit` | 각각 `{target, frame_xy}`. 컷 처음/끝에서 관객이 읽을 대상과 정규화 화면 위치 |
| Shot | `cut_link` | `{from_shot_id, relation, handoff, intentional_break, reorientation}`. 첫 컷은 from_shot_id가 null. 그 외에는 앞 컷 ID |

relation은 예를 들어 continuous/reaction/insert/ellipsis/scene-change/intentional-break/scene-opening으로 쓴다. handoff는 앞 컷의 관심을 다음 컷 대상으로 넘기는 눈·손·행동·공간 단서다. `intentional_break: true`이면 단절의 이유를 handoff에, 새 방향/시간/장소를 읽게 할 단서를 reorientation에 적는다. 도약을 없애는 것이 목적은 아니다.

좌표를 모르면 `null`과 미확정 사유를 남긴다. 생성에 필요한 인물·목표·카메라 관계를 블록아웃에서 확정한 뒤 해당 키를 만든다. frame_xy는 영상/이미지 전체 좌상단 `[0,0]`, 우하단 `[1,1]`; 표시는 추정/관찰 여부와 함께 한다. 좌표만으로 실제 시선이나 자연스러움이 입증되지는 않는다.

예시는 `<skills>/ai-director-scene-direction/references/shot-design.md`, 앞뒤 컷 검사 절차는 `<skills>/ai-director-cinematography/references/eyeline-continuity.md`에 있다. 상세 리뷰는 작품의 리뷰 파일에 쓰고 `notes` 또는 기존 `review.evidence`로 연결한다. **현재 validate_story.py는 이 설계 필드의 완성도·시선 의미를 검사하지 않는다.** 계획 검토는 실제 영상의 pass/playback 검수를 대신하지 않는다.

## 레퍼런스 (선택, `ai-director-reference`)

| 위치 | 필드 | 내용 |
|---|---|---|
| 최상위 | `references[]` | 레퍼런스 원장. 각 `{id, aspect[camera|location|mood], kind(video|image|link), source{title, credit, url, path, path_original, in_ms, out_ms, sha256}, derived[], evidence, observed{by: agent|user, mode, date, notes}|null, status(candidate|approved|rejected), note}` |
| `bible.style`, `bible.worlds[]`, Scene, Shot | `reference_links[]` | 각 `{ref_id, aspect, take, avoid, stale}`. 그 범위에 무엇을 가져오고(take) 무엇을 빼는지(avoid) |

형식과 수집 절차는 `<skills>/ai-director-reference/references/reference-board.md`. validate_story.py가 ID·연결·aspect·구간·observed 형식, `approved`인데 `observed` 없음, 링크 전용인데 증거 있음을 검사한다. 라이선스는 검사하지 않는다(사용자 결정 2026-11-11). 레퍼런스 수치는 영상 pass 근거가 아니다.

## 검수 필드 (모두 선택)
- Shot `success_criteria`: 생성 **전에** 쓰는 관찰 가능한 문장. `{"start": "", "progress": "", "complete": "", "continuity": "", "identity": "", "camera": ""}` (시작 상태 / 진행 / 완료 / 소품·손 연속성 / 얼굴·의상 / 카메라).
- ShotVersion `job_id`: 서버 prompt id. 결과를 다시 받아올 때 쓴다.
- ShotVersion `review`: 활성 버전의 검수 기록. 파일·트림 범위와 묶어서 저장한다.
```jsonc
"review": { "status": "pending",            // pending|pass|revise|hold
            "scope": ["frames", "metrics", "playback"],   // 실제로 확인한 범위만 적는다
            "defects": [ { "t0": 2.10, "t1": 2.45, "observation": "", "impact": "", "action": "" } ],   // 초 단위
            "evidence": ["review/S1-1-v1/contact.png"],
            "media_sha1": "", "range_ms": [0, 5000],   // 검수한 파일 해시와 사용 구간(source_in/out)
            "reviewer": "", "date": "2026-11-08" }
```
**export 단계의 pass 기록(필수 필드).** `status: "pass"`만으로는 통과하지 못한다. 모두 있어야 하고, 하나라도 없거나 형식이 틀리면 필드 이름을 담은 오류가 난다.
```jsonc
"review": { "status": "pass",
            "media_sha1": "<파일 sha1, 비어 있으면 안 됨, 실제 파일과 같아야 함>",
            "range_ms": [0, 5000],                       // 정수 [in, out], in < out. 검수한 source 구간
            "scope": ["frames", "metrics", "playback"],   // "playback" 필수
            "reviewer": "video-reviewer",
            "playback_by": "user",                        // "user" 또는 "model:<이름>" - 실제로 재생해서 본 주체
            "date": "2026-11-08",
            "criteria": { "start": "met", "progress": "met", "complete": "met" } }   // shot.success_criteria의 값이 있는 키마다 "met" (unverified/not_met이면 차단)
```
- export에서는 shot에 `success_criteria`가 없으면 오류다(planning/generation/edit는 경고).
- 기록이 있다는 것이 시청 사실을 보장하지는 않는다. `playback_by`로 누가 봤는지를 구분해 남긴다.
- **타임라인 클립 연결(export).** 영상 클립이 샷을 나타내면 `shot_id`와 `version_id`가 필수다(`shot_id`만 있으면 오류). `version_id`는 샷의 `active_version_id`와 같아야 하고, 클립 `media_url`은 그 버전의 `media_url`과 같은 경로(정규화 후)여야 하며, 파일이 있어야 한다. 파일이 없으면 건너뛰지 않고 오류다.
- `shot_id`가 없는 영상 클립(자유 resource)은 클립 자신의 `review` 객체를 가져야 하며 위와 같은 pass 필드를 요구한다(`criteria`는 비어 있지 않고 모두 `"met"`).
- **사용 구간.** 클립의 `[source_in_ms, source_out_ms]`가 `review.range_ms` 안에 있어야 한다. 벗어나면 `used range … outside reviewed range …, re-review` 오류. 핵심 행동이 잘리는지는 사람의 판단이므로, `range_ms`를 넓히려면 샷 전체를 다시 검수해야 한다.
- **편집점 검수.** `timeline.edit_point_reviews`에 메인 비디오 트랙의 연속한 활성 영상 클립 쌍마다 pass 기록이 있어야 한다. 현재 컷과 정확히 같아야 하므로 트림·속도·전환·버전·파일·인접 클립이 바뀌면 무효가 되고 `edit point <a>→<b> not reviewed for the current cut` 오류가 난다.
```jsonc
"edit_point_reviews": [ {
  "a": { "clip_id": "cl_1", "version_id": "S1-1-v1", "media_sha1": "…", "source_in_ms": 0, "source_out_ms": 5000, "speed": 1 },
  "b": { "clip_id": "cl_2", "version_id": "S1-2-v1", "media_sha1": "…", "source_in_ms": 0, "source_out_ms": 4000, "speed": 1 },
  "transition": { "type": "dissolve", "duration_ms": 500 },   // b 클립의 transition_in(type, duration_ms). 없으면 null
  "status": "pass",   // pass|revise|hold (pass만 인정)
  "reviewer": "video-reviewer", "playback_by": "user", "date": "2026-11-08" } ]
```

## 검증 단계 (`validate_story.py --stage`)
단계는 누적된다. 기본값은 `planning`.

| 단계 | 추가 검사 |
|---|---|
| planning | 기존 검사 + 장면 `world_id`는 bible.worlds의 id여야 함, `chain_from` 자기 참조·순환 금지, `active_version_id`는 해당 샷 versions 안의 id (오류) |
| generation | 버전이 있는데 `active_version_id`가 없으면 경고, 활성 버전 status `failed`면 오류, `success_criteria` 없으면 경고 |
| edit | 활성 버전이 `kind: video`가 아니거나 `media_url` 파일이 없으면 오류 (story.json 폴더 기준), 활성 영상 버전의 `review.status`가 `pass`가 아니면 경고 |
| export | 모든 샷의 활성 영상 버전이 위 pass 기록 필드를 모두 갖춰야 함(sha1은 필수이며 파일과 다르면 오류), `success_criteria` 없으면 오류, 클립의 `version_id`·`media_url`·파일 존재, 사용 구간 ⊂ `range_ms`, 연속 클립마다 일치하는 pass `edit_point_reviews`, 자유 영상 클립의 자체 `review`, 클립 `source_out_ms`가 미디어 길이를 넘으면 오류(ffprobe 없으면 경고 후 건너뜀), `--target-ms` 대비 ±10% 밖이면 오류 |

겹침 규칙(타임라인이 있는 모든 단계): 같은 비디오 트랙에서 클립 B가 앞 클립 A의 끝보다 먼저 시작하면 겹침 길이는 `B.transition_in.duration_ms`와 같아야 한다(±1ms). 다르면 오류(`overlap X ms does not match transition Y ms`). 빈 구간(gap)은 허용하며 경고만 낸다. `render_timeline.py`도 같은 규칙을 쓰고, 어긋나면 클립을 밀지 않고 렌더를 거부한다.
