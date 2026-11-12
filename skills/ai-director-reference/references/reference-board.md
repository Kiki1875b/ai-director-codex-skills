# 레퍼런스 원장 형식과 수집 절차

라이선스는 검사하지 않는다(사용자 결정 2026-11-11). 출처는 다시 찾고 크레딧을 넣기 위해 적는다.

## 1. story.json 필드

### 최상위 `references[]`

```jsonc
"references": [
  { "id": "R01",                                   // 한 번 만들면 바꾸지 않는다. R + 숫자
    "aspect": ["camera"],                          // camera | location | mood 중 1개 이상
    "kind": "video",                               // video | image | link (link = 파일 없음)
    "source": {
      "title": "작품/페이지 제목", "credit": "감독·촬영·사진가",
      "url": "https://...",                        // 있으면
      "path": "refs/board/src/R01.mp4",            // 로컬 사본(story.json 기준). link면 null
      "path_original": "D:/내자료/clip.mp4",        // 사용자가 준 원래 위치(선택)
      "in_ms": 12000, "out_ms": 16500,              // 볼 구간. 둘 다 숫자로 함께, in < out. 재생으로 확인 못 했으면 둘 다 null
      "sha256": "…"                                 // ref_probe.py probe.json 의 media_sha256 (파일이 바뀌었는지 확인)
    },
    "derived": ["refs/board/R01/frame_0004.png"],  // 이 원본에서 만든 크롭·추출 프레임·보정본(선택)
    "evidence": { "dir": "refs/board/R01", "probe": "refs/board/R01/probe.json",
                  "contact_sheet": "refs/board/R01/contact.jpg" },   // 분석 안 했으면 null
    "observed": { "by": "agent", "mode": "dense_frames", "interval_s": 0.25, "range_ms": [12000, 16500], "date": "2026-11-11",
                  "notes": "0:12–0:16 발끝→얼굴 tilt up, 카메라 높이 허리, 끝 MCU. ref_probe: 화면 내용 y +31%" },
                                                   // by: agent | user. mode: contact_sheet | dense_frames(interval_s, range_ms 필수)
                                                   //   | playback(실제 실시간 재생만) | user_viewing(by: user). 못 봤으면 null
                                                   // 촬영 기법은 dense_frames(구간 전체, ≤0.25초)·playback·user_viewing 으로만 확정한다
    "status": "approved",                          // candidate | approved | rejected
    "note": "" }
]
```

### 범위별 `reference_links[]`

`bible.style`, `bible.worlds[]`, `scenes[]`, `scenes[].shots[]` 에 둔다.

```jsonc
"reference_links": [
  { "ref_id": "R01", "aspect": "camera",
    "take": "발끝에서 얼굴까지 4초 tilt up, 끝 MCU, 카메라 허리 높이",
    "avoid": "핸드헬드 흔들림",
    "stale": false }                               // 레퍼런스가 바뀌어 재검토가 필요하면 true
]
```

- `aspect`는 그 레퍼런스의 `aspect` 목록 안에 있어야 한다.
- `take`는 비우지 않는다. 측정·관찰 가능한 문장으로 쓴다.
- `rejected` 레퍼런스는 연결하지 않는다.

## 2. 검증기가 보는 것

`validate_story.py`는 ID 중복, 없는 ref_id 연결, aspect·kind·status 값, 구간(숫자, 함께, in < out), observed 형식·mode, `approved`인데 `observed` 없음, 링크 전용인데 `evidence` 있음을 검사한다. 라이선스·권한은 검사하지 않는다(예전 `rights` 필드가 남아 있어도 무시한다).

## 3. 레퍼런스를 실제로 찾아오는 절차

1. **찾을 것을 문장으로 정한다.** 측면 + 기법 + 피사체 + 샷 크기. 예: camera "tilt up, 바닥/제단에서 높은 천장까지, 와이드", location "을지로 뒷골목 셔터 상가 밤", mood "백색 보안등 하나, 어두운 골목".
2. **출처.** 쓸 만하면 어디서든 가져온다.
   - camera: ① 사용자 자료 ② 영화·드라마·광고의 해당 장면(YouTube 등 클립) ③ Wikimedia Commons·Pexels·Pixabay 영상 ④ 촬영 해설(ASC, StudioBinder 등)의 예시 장면. 해설 글의 설명은 `note`에 근거로 남긴다.
   - location: ① 사용자 사진 ② 실제 장소 사진(Commons 지명 카테고리, 스톡, 여행·블로그 사진) ③ 지도·로드뷰 화면 캡처.
   - mood: ① 사용자 자료 ② 작품 장면·스틸 ③ 스톡 이미지·영상.
3. **검색 방법.** 일반 웹 검색은 설명 글이 주로 나오므로, 파일이 필요하면 **소스 사이트 안에서 바로 찾는다**.
   - Wikimedia Commons API(키 없음):
     `https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=<검색어>%20filetype:video&srnamespace=6&format=json`
     → 후보 제목으로 `action=query&titles=File:<제목>&prop=imageinfo&iiprop=url|size|extmetadata` 를 호출해 `url`, `Artist`, `descriptionurl`을 받는다. 제목의 기법명은 틀릴 수 있다(예: "pan up"이라고 올라온 tilt up).
   - 영화 장면: "<작품명> <장면> scene" 또는 "<기법> shot example"로 검색해 클립 URL과 장면 시각을 찾는다.
   - Pexels·Pixabay: 자산 페이지의 다운로드 링크를 쓴다.
4. **파일 확보.** `stories/<slug>/refs/board/src/<id>.<ext>`에 받는다. User-Agent는 일반 이름(예: `ref-collector/0.1`)을 쓰고 개인 정보는 넣지 않는다.
   - 직접 파일 URL: `curl -L -A "ref-collector/0.1" -o stories/<slug>/refs/board/src/<id>.<ext> <url>`
   - YouTube 등 스트리밍: 필요한 구간만 받는다.
     `yt-dlp --download-sections "*00:12-00:20" -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 -o stories/<slug>/refs/board/src/<id>.mp4 <url>`
     받은 파일의 0초 = 원본의 `--download-sections` 시작 시각이다. `source.in_ms/out_ms`에는 **원본 시각**을 적고, 받은 구간을 `note`에 적는다(예: "src = 원본 12.0–20.0s").
5. **구간 정하기.** 전체를 `ref_probe.py`로 한 번 잰 뒤 접촉 시트·`pairs`(시각별 이동)로 쓸 구간을 고르고, 그 구간을 `--range`로 다시 잰다. 구간은 촘촘한 프레임(예: `ffmpeg -t 8 -i <파일> -vf "fps=4,scale=240:-2,tile=8x4" -frames:v 1 dense.jpg`)으로 직접 확인한 뒤 `in_ms/out_ms`에 적는다. 원본 시각 기준이다.
6. **원장·연결.** 위 1절 형식으로 넣고, 연결 문장(take/avoid)은 측정값과 본 내용으로만 쓴다.

### 실제 수행 예 (2026-11-11, camera)

- 검색: Commons API `srsearch=pan up filetype:video` → `File:Basilique Saint-Nazaire de Carcassonne - pan up from altar.webm` (1920×1080, 44.9초).
- 받기: `curl -L`로 원본 webm(43MB).
- 측정(전체): 화면 내용 y +310%(위로 계속 올라감), 가로 왕복 흔들림 후보(총 29%, 순 +8%) → 구간 0–8초 다시 측정: y +51%, x +4%, 확대 0.997.
- 확인(dense_frames, 0.25초 간격 32장, 0–8초): 제단 → 스테인드글라스로 일정하게 tilt up, 가로로 약한 흔들림(핸드헬드). 이름은 "pan up"이지만 실제는 tilt up이다.
- 원장 항목:
```json
{ "id": "R01", "aspect": ["camera"], "kind": "video",
  "source": { "title": "Basilique Saint-Nazaire de Carcassonne - pan up from altar",
              "credit": "Joe Mabel (CC BY-SA 3.0)",
              "url": "https://commons.wikimedia.org/wiki/File:Basilique_Saint-Nazaire_de_Carcassonne_-_pan_up_from_altar.webm",
              "path": "refs/board/src/R01.webm", "in_ms": 0, "out_ms": 8000 },
  "evidence": { "dir": "refs/board/R01_0-8s", "probe": "refs/board/R01_0-8s/probe.json" },
  "observed": { "by": "agent", "mode": "dense_frames", "interval_s": 0.25, "range_ms": [0, 8000], "date": "2026-11-11",
                "notes": "0-8s 제단에서 스테인드글라스까지 일정한 tilt up, 약한 가로 흔들림. ref_probe y +51%/8s" },
  "status": "candidate" }
```
- 연결 예: `{"ref_id": "R01", "aspect": "camera", "take": "8초 동안 바닥 높이에서 창 높이까지 일정한 속도로 tilt up, 화면 높이의 약 절반이 지나감", "avoid": "가로 흔들림(락오프 헤드로)"}`

## 4. 보드 보여 주기 (채팅)

```
[reference] S2 | camera
  R01 tilt up 발끝→얼굴 (사용자 파일, 0:12–0:16) | ref_probe: 화면 내용 y +31%, 신뢰 100% | 후보: tilt up 또는 pedestal up
     take: … / avoid: …
  R02 (링크만, 미시청) https://… 0:40–0:45 | 증거 없음
[reference] wd_market | location …
[reference] style | mood …
[awaiting_user_input] 측면별로 고를 레퍼런스
```
