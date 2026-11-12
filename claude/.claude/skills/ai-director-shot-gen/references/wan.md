# Wan 2.2 레시피 (대체 수단)

LTX-2.5가 기본이다(`../SKILL.md` 4절). Wan은 사용자가 지정하거나 LTX로 안 되는 컷에만 쓴다. 아래 규칙은 Wan 2.2 I2V A14B Q4 GGUF + 4스텝 LoRA(motionfix) + NAG 조합에서 확인한 것이며 LTX에 그대로 옮기지 않는다. 확인된 능력·실패는 [model-capabilities.md](model-capabilities.md)의 Wan 절. 한 건에 15~25분이 걸린다.

**2. 모션 프롬프트** (`prompts/motion/<shot>.txt`, 영어)
- 키프레임은 "가장 잘 읽히는 순간"이라 이미 행동의 끝일 때가 많다. 프롬프트는 **그 순간 이후**에 이어지는 동작으로 쓴다(키에서 고개를 든 상태면 "고개를 든다"가 아니라 "손을 멈추고, 입구를 계속 보며 미소가 번진다"). 안 그러면 모델이 반대 방향(고개를 숙임)으로 움직인다.
- 속도: `slowly / gently / calmly / quietly / slow pulse` 금지. `normal real-time speed`, `natural everyday pace`를 넣고, 5초 안에 동작 단계 3~4개.
- 지킬 상태는 긍정 문장("dry matte wool"). 금지할 것(가방, 우산 등)은 `--negative`에 더한다(NAG가 켜져 있어 적용됨).
- 카메라는 하나만, 명시적으로(`Locked-off`, `Smooth steady push-in`).
- 박자 수만 늘리지 않는다. "무엇을 해서 어떤 상태로 끝나는지"를 동작 하나하나 구체적으로 쓴다. 막연하면 목적 없는 손동작이 생긴다(S2-5 v3).
- 키에 없는 소품을 집게 하지 않는다. 모델이 가까운 다른 소품을 그것으로 바꾼다(S2-5 v3 신문 → 수건). 화면 속 소품은 "stays untouched"로 고정한다.
- 화면 속 두 번째 인물에게도 작은 동작 하나(숨, 시선, 고개)를 준다. 지시가 없으면 조각상처럼 굳는다.
- 뜨거운 물건(주전자, 냄비)은 손잡이만 잡는다. 몸통을 감싸면 어색하다. 끝 키(`--end-image`)의 손 위치도 같이 확인한다(S2-8 v4).
- 화면 밖 상대와 대화하는 클로즈업은 모델이 상대를 지어 넣는다(S2-3 v1~v4b: 맨살 어깨, 흰 셔츠 남자). 프롬프트·부정 프롬프트로는 안 막힌다. **더티 싱글로 키를 만든다**: 시선 쪽 가장자리에 상대의 흐린 어깨·머리(바이블 의상)를 Codex로 넣고, 끝 키는 그 키에서 편집한다. 상대가 이미 화면에 있으면 새 사람을 만들지 않는다(S2-3 v5 해결).
- **첫·끝 키 방식의 끝 키는 반드시 시작 키에서 바로 편집한다.** 다른 키를 거쳐 만들면 소품 방향이 달라지고(S2-8 v5 주전자 입구 왼쪽↔오른쪽), 모델이 중간에 변형한다(입구 두 개). 시작 키에 이미 있는 상태(주전자가 버너 위)와 프롬프트가 어긋나지 않게 쓴다.
- 움직임이 거의 없는 정지 인서트에는 첫·끝 키에 같은 이미지를 넣지 않는다. 중간에 줌인했다 돌아온다(S2-4 v5, 최대 76px). 일반 I2V가 더 안정적이다.
- **얇은 물건 뒤집기(사진, 카드, 종이)**: 모델은 90도를 넘는 회전을 그리지 못한다. 중간 키를 넣어도 세운 순간 앞면 그림을 뒷면으로 바꿔치기한다(S3-2 v1~v3 실패, 사용자: "완전히 뒤집질 않는다"). **넘어가는 구간은 `scripts/flip_card.py`로 렌더링한다**: (1) AI FLF로 시작 → 세운 상태(중간 키)까지, (2) 그 마지막 프레임에서 카드만 지운 빈 판(Codex 결과를 카드 영역에만 마스크 합성, 손 픽셀은 원본)을 만들고 flip_card.py로 79°→180°를 가속 회전 렌더(앞면 텍스처는 시작 키, 뒷면은 축 쪽에 테이프가 오게), (3) 렌더 마지막 프레임 → 끝 키(손바닥)를 AI FLF로. 끝 키의 카드는 PIL로 렌더 결과와 같은 크기·위치에 붙여 만든다. 이음 프레임은 같은 원본에서 나와야 손이 튀지 않는다(구간 A를 중간에서 자르지 말고 빈 판을 만든 프레임까지 쓴다)(S3-2 v4).
- 정지 사진·그림 인서트의 푸시인은 AI로 만들지 않는다. 사진 속이 움직인다. 키에 ffmpeg zoompan(ease in-out)으로 만든다(S3-4).
- 절제된 감정(눈가가 굳음, 턱에 힘)을 동작으로 쓰지 않는다. 모델은 크게 인상 쓰는 얼굴로 과장한다(S3-6 v1·v2). 감정은 끝 키 표정에 맡기고, 프롬프트는 "face stays almost completely still" + 눈꺼풀·손가락 같은 작은 동작 하나만.
- **작은 광원(옷 속 빛, 구슬, 눈빛)은 모델에 맡기지 않는다.** 얼룩지고 위치가 움직인다(S2-4 v2~v4). 키에서 빛을 지우고(Codex 편집), 빛 없이 생성한 뒤 `scripts/glow_overlay.py`로 고정된 자리에 합성한다(`--x --y --radius --color --curve "t:세기,..."`).

**2-1. 얼굴 무너짐·표정 과장 방지 (인물 컷 필수, 2026-11-05 S3-6 v1→v3에서 확인)**

증상: 일반 I2V에서 시간이 갈수록 얼굴이 밀랍처럼 뭉개지고 머리카락이 엉키며, 감정 동작은 크게 찡그리는 얼굴로 과장된다.

| 순서 | 방법 | 효과 |
|---|---|---|
| ① | 시작·끝 키의 얼굴을 기준 얼굴(`refs/ch_<id>_face_v2.png` + 승인된 키 1장)을 `character_image1/2`로 넣어 Codex로 **다시 그린다**. 옛 키 → 새 키를 기준 사진 옆에 붙인 점검표로 **사용자 승인 후** 생성 | 얼굴 정체성 유지(가장 큼) |
| ② | 얼굴이 큰 클로즈업·미디엄은 첫·끝 키(`--end-image`, 루트 CLAUDE.md 2절). 얼굴이 작거나 없는 큰 동작·고정 와이드는 model-capabilities.md의 해당 방식으로 판단. 끝 키는 반드시 시작 키에서 편집. 다른 인물·배경이 바뀌면 시작 키 픽셀을 마스크 합성해 되돌린다(S3-9). 시작 키만 쓰면 `Locked-off`라고 써도 카메라가 밀릴 수 있다(S5T-1·2 v1) | 정체성과 카메라 유지 |
| ③ | 길이: 동작이 작은 클로즈업은 65프레임(4초) 이하 | 변형 누적 감소 |
| ④ | 프롬프트에 감정 동작("jaw tightens", "eyes go hard", "knowing smile")을 쓰지 않는다. 감정은 끝 키 표정에 맡기고 "his face stays almost completely still and relaxed; only his eyelids lower slightly once and his thumb moves once"처럼 작은 동작 하나만 | 찡그림 제거 |
| ⑤ | 부정 프롬프트에 `smile`을 넣지 않는다(NAG가 반대쪽인 찡그림으로 민다, S3-8 v2). 대신 `frown, grimace, wince, squint, wrinkled brow, exaggerated facial expressions, waxy skin, smeared face, identity change`. 긍정에 "relaxed, calm, neutral expression, eyebrows relaxed". 뜨거운 음료는 "warm" | 표정 과장 감소 |
| ⑥ | (후처리, 효과 작음) `scripts/refine_remote.py --src-pid <id> --steps 8 --start 6`: 모델의 16fps 프레임을 저노이즈로 다시 그리는 보정 패스. 머리카락이 약간 살아남 | 작음 |
| ⑦ | (후처리, 선명도만 올림·형태 흔들림은 못 고침, 기본 작업에서 제외) `scripts/seedvr2_remote.py in.mp4 out.mp4 --res 720 --swap 12`: SeedVR2 3B fp8 복원. 서버 노드 `seedvr2_videoupscaler`(requirements는 ComfyUI를 끈 상태에서 설치해야 함). `--res 1080`은 12GB에서 VAE 디코딩이 묶음당 10분(컷당 1시간 이상)이라 비권장. 720p는 4초 컷에 약 26분. 출력이 1프레임 많을 수 있어 원본 프레임 수로 자른다 | 머리카락 올·속눈썹·눈썹이 살아남(S3-6 v3_sv) |
| ⑧ | NAG를 낮춘다: `--nag 2.5 --nag-tau 1.5 --nag-alpha 0.15`(I2V 권장, 기본 5/2.5/0.25는 표정 과장). 프롬프트에 얼굴 특징을 한 줄로 묘사하고 "The face keeps exactly the same shape and features from the first frame to the last"를 넣는다. 부정에 `exaggerated facial expressions, face shape changing, face morphing between frames` | S3-6 v4: 찡그림 사라지고 표정 일정 |
| ⑨ | **얼굴 디테일러 (미디엄·와이드 컷 기본, 사용자 승인 2026-11-05)**: `scripts/face_detail.py --video <clip> --image <start key> --end-image <end key> --box x0,y0,x1,y1 --scale 2.48 --steps 8 --start 5 --prompt "<얼굴만 자세히 묘사, 'keeps exactly the same shape and features in every frame'>" --out <clip>fd.mp4`. 원인: Wan은 화면을 16×16px 칸으로 다뤄서 폭 50px 얼굴은 3칸뿐 → 디코더가 추측으로 채워 프레임마다 뭉개짐. 방법: 얼굴이 움직이는 범위를 박스로 잘라(1280×720 기준, 고정 카메라) 2.5배로 키워 저노이즈로 다시 그리고, 줄여서 가장자리를 섞어 붙인다(색 평균 맞춤). 박스는 첫·중간·끝 프레임을 잘라 얼굴이 다 들어가는지 먼저 확인. 인물이 둘이면 사람마다 따로 돌린다. 4~5초 컷에 약 9분 | S2-5 v5fd: 얼굴이 프레임 사이에 일정, 경계 안 보임. 사용자 "좋은데" |


보조 사실: RIFE 보간 프레임은 원본 프레임보다 선명도가 약 4%만 낮다(뭉개짐의 원인이 아님). 뭉개짐의 주원인은 4스텝 증류 + Q4 양자화다. NAG는 `--nag-alpha --nag-tau`로 조절 가능(기본 0.25/2.5, I2V는 더 낮게 권장).
- 표정 연기 자체가 필요한 컷(대사·감정 클로즈업)의 다음 후보: LivePortrait로 실제 연기 영상의 표정을 옮겨 입히기(미설치, 사용자 결정 대기).

**3. 기본 실행 (Wan 대체 수단을 쓸 때)**
```bash
# 한 컷
python .claude/skills/ai-director-shot-gen/scripts/wan_remote.py   --image stories/<slug>/media/S2-1-key-v9.png --prompt-file stories/<slug>/prompts/motion/S2-1.txt   --out stories/<slug>/media/video/S2-1-vid-v2.mp4 --frames 81 --seed 2101 --nag 5 --rife
# 여러 컷: 대기열에 몰아 넣지 않는다(사용자 결정 2026-11-05). 한 컷을 run_in_background로 돌리고,
# 끝나면 검수·보고한 뒤 다음 컷을 넣는다. 앞 컷에서 배운 것을 다음 프롬프트에 반영할 수 있고, 서버가 재부팅돼도 잃는 게 한 컷뿐이다.
# queue_shots.sh(한 번에 대기열 등록)는 사용자가 명시적으로 요청할 때만 쓴다.
```
- 기본값: Wan 2.2 I2V A14B Q4_K_M GGUF 고/저노이즈, **`--lora motionfix`**(slow-mo fix 4스텝 쌍; 구 `lightx2v`는 슬로모션), 4스텝 CFG 1 shift 5, 1280×720, NAG 5, RIFE x3 → 24fps. 기본 부정에 `slow motion`이 들어 있다.
- 프레임: 3초 이하 컷은 65(4초), 그 외 81(5초). 7초 이상은 반복·드리프트가 생긴다.
- **속도**: 배속은 컷마다 사용자가 지정한 컷에만 적용한다(일괄 적용 금지, 사용자 2026-11-05). 예: S2-3만 2배속. 방법은 `--fetch <id> --rife --speed N`, 서버 기록이 없으면 24fps 원본에서 N프레임마다 1장. 구 LoRA 클립의 기준은 2배속이었다. motionfix 클립은 컷마다 그 체감에 맞춰 `--speed`(1, 1.5, 2…)를 고른다. 서버에 48fps 간격 프레임이 남으므로 다시 생성하지 않고 `--fetch <prompt_id> --rife --speed 2`로 다시 내보낼 수 있다.
- **색**: LOG→LUT는 현재 끔(2026-11-04). 원본(`<shot>-vid-vN.mp4`)이 결과물이다. 나중에 켜려면 `--lut stories/<slug>/luts/sl_blue.cube`(→ `_graded.mp4`).
- `--motion-amp`(PainterI2V) 금지: 밤 장면 밝기가 하얗게 뜬다.

**3-1. 속도 조절** (Wan + 4스텝 LoRA는 기본적으로 슬로모션처럼 보인다. 아래를 순서대로 쓴다)
| 단계 | 방법 | 언제 |
|---|---|---|
| 생성 전 ① 프롬프트 | 느린 부사 금지, `normal real-time speed`, 5초에 동작 3~4단계, 부정 `slow motion`(NAG) | 항상 |
| 생성 전 ② LoRA | `--lora motionfix`(기본). 구 `lightx2v` 쌍은 쓰지 않는다 | 항상 |
| 생성 시 ③ 배속 굽기 | `--rife --speed N`: RIFE x3로 48fps 간격 프레임을 만든 뒤 `2N`장마다 1장을 골라 24fps로 저장. N은 1, 1.5, 2, 2.5, 3 | 체감 기준이 정해졌을 때 |
| 생성 후 ④ 다시 내보내기 | `--fetch <prompt_id> --image <키> --prompt x --out <새 이름> --rife --speed N` — 서버에 남은 프레임으로 몇 초 만에 다른 배속본을 만든다(재생성 없음) | 배속을 바꿔 보고 싶을 때 |
| 생성 후 ⑤ 기존 파일 | `ffmpeg -i in.mp4 -vf "setpts=PTS/N,fps=24" -c:v libx264 -crf 14 -pix_fmt yuv420p out.mp4` | 서버 프레임이 없을 때 |
| 길이 유지 | 배속 N이면 원본이 N배 길어야 같은 길이가 된다. 81f(5초)×2배속 = 2.5초. 5초를 원하면 161f가 필요하지만 학습 길이(81f)의 2배라 반복·드리프트·메모리 위험 → 먼저 ①②로 5초 안의 동작을 빠르게 하고, 모자란 컷만 프레임을 늘린다 | 콘티 길이와 안 맞을 때 |

**체감 속도 정하기**: 같은 클립을 1.5 / 1.75 / 2배속으로 만들어(④ 또는 ⑤) 사용자에게 보여주고 고르게 한다. 이 프로젝트는 "구 LoRA 클립의 2배속"으로 정했다(story.json `format.video_motion_speed`). 새 설정(①②) 클립은 그 기준본과 나란히 보고 컷마다 N을 정한다 — 2를 그대로 곱하지 않는다. 최종 배속은 편집 타임라인의 clip speed(0.5–2x)로도 바꿀 수 있다.
