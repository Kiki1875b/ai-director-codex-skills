---
name: ai-director-shot-gen
description: Use when turning a storyboard shot into generation jobs — choosing how to generate (Codex image keys and edits, LTX/Wan image2video with start/end keys, voice, music), writing keyframe and motion prompts, managing shot versions and the active version, and gating paid generations behind user approval. 한국어 트리거는 샷 생성, 컷별 프롬프트, 이미지투비디오, 레퍼런스 영상 생성, 다시 생성, 버전 관리, 영상 프롬프트 작성. Part of the ai-director skill set.
---

# 샷 생성 (Shot Generation)

생성 결과는 샷의 **version**으로 붙는다. 이전 version은 지우지 않는다.

## 1. 방식 고르기

| 샷 성격 | 1단계 | 2단계 |
|---|---|---|
| 얼굴이 크게 나오는 인물 컷(클로즈업·미디엄) | 키프레임 + 끝 키(`codex_image.py`) | LTX 첫·끝 키(`ltx_remote.py --end-image`) |
| 대사 컷(입이 보임) | 음성 확정 → 키·끝 키 | LTX 첫·끝 키 + `--audio` |
| 얼굴이 작고 공간을 지나는 큰 동작 | 키프레임 | 시작 1장 image2video (`model-capabilities.md`에서 모델 선택) |
| 인물 2명 이상 | 두 인물이 모두 들어간 키프레임(더티 싱글 포함) | 위 행의 얼굴 크기·동작 조건으로 고른다(인원수만으로 정하지 않음) |
| 정지 사진·그림 인서트 | 키프레임 | ffmpeg zoompan(사진 속이 움직이지 않게) |
| 움직일 것이 비·작은 광원뿐인 와이드 | 키프레임 | 작품이 합성으로 정한 효과는 합성. 그 밖에는 모델 표 확인(Wan은 비·작은 광원 실패 확인됨) |
| 인물이 없는 풍경 | 키프레임 | image2video (현재 래퍼는 `--image` 필수. text2video는 로컬 실행 경로 미확인) |
| 내레이션·대사 | 대사 확정 | 음성 생성(고정 voice_id) |
| 배경음악 | 무드·BPM·길이 결정 | 음악 생성 또는 라이선스 음원 (기본·실패 기록: `ai-director-edit/references/audio-generation.md`) |

모델별로 확인된 능력·실패·시간은 [model-capabilities.md](references/model-capabilities.md)에 있다. 표에 없는 조합은 미확인으로 다룬다.

## 2. 프롬프트 작성

**키프레임 생성 전 입력.** 새 컷이나 시선·연결을 바꾸는 컷은 `ai-director-scene-direction`의 scene.direction과 `ai-director-cinematography` 0·2-1절의 shot.staging/cut_link를 먼저 읽는다. 단독 컷 요청도 기존 앞뒤 컷이 있으면 그 연결을 포함한다. 시선 목표·높이·대화축·카메라·관객 관심점의 관계가 미확정이면 해당 키를 만들기 전에 블록아웃 설계를 보완한다. 이 단계의 계획 점검은 실제 영상 검수 pass가 아니다.

**키프레임(이미지)** 구조. 줄 순서를 지킨다(AI 슬롭 방지 근거는 `ai-director-consistency/references/anti-slop.md`):
```
1. 형식: 작품 화면비의 문장(`ai-director/references/aspect-ratios.md`). 예: "Landscape 16:9 single film frame." / "Portrait 9:16 single film frame." / 2.39:1은 16:9 + 가운데 띠 구도 문장
2. Image roles: character_image1 = identity (face) — match exactly / character_image2 = costume only /
   env_image1 = THE LOCATION: reproduce this exact place, look, colors, lighting / object_image1 = <prop>
3. 블로킹·카메라: 인물이 공간 어디에(카메라에서 몇 m, 3분할 어느 쪽, 몸 방향) + 샷 크기/앵글/렌즈
   + "physically inside the space at the correct scale" + 전경 가림(어깨, 셔터 가장자리 등)
   + 시선 목표의 실제 위치·높이와 화면상 방향(shot.staging에서), 다음 컷으로 관심을 넘길 대상의 화면 위치
4. 한 행동: 컷의 시작 상태와 다음 행동이 읽히는 순간. 감정 단어 대신 자세·지정 목표를 향한 시선·손으로 쓴다
5. 앵커 원문: 캐릭터 / 오브젝트 / 월드 + 상태(젖음 등)
6. LIGHTING: 장면의 실제 광원마다 위치와 닿는 부위, 마지막에 "No other light."
7. LOOK 블록(anti-slop.md 3절 원문, 글자 그대로) + negative
```
- 참조: 얼굴 기준(`ref_images[0]`) → `character_image1`, 전신 의상 기준 → `character_image2`, 룩 확정 때 밝기 보정한 배경 기준 → `env_image1`. 옛 룩의 씬 시트는 넣지 않는다(질감이 옮는다). 5장 이내.
- `cinematic`, `melancholic`, `neon glow`, `teal-and-amber`, `wet reflections everywhere` 같은 분위기 단어를 쓰지 않는다.
- **룩 확정 게이트**(`ai-director-consistency` 1-1)를 통과하기 전에는 키프레임을 대량으로 만들지 않는다.
- **밤 실외 키·판**은 `ai-director-consistency/references/anti-slop.md` 4-8을 따른다: 광원마다 빛이 닿는 범위와 그 밖의 어둠을 쓰고, 생성 뒤 도로 밝기를 선형 휘도로 재서 등 아래 대비 감쇠를 확인한다. 전체 노출만 낮추지 않는다.

**키프레임 절차 (필수, 2026-11-08 사용자 결정).** 키를 만들 때마다 [references/keyframe-procedure.md](references/keyframe-procedure.md)를 처음부터 따른다. 순서만 적으면:
0 장소를 Blender로 먼저 설계(세트 없는 장소의 키는 만들지 않음) → 1 실제 광원만 켠 조명 가이드 렌더, 인물 밝은 면 한 줄 → 2 가이드를 `LIGHTING GUIDE`로 넣고 원판에서 한 번만 편집, 요구를 프롬프트/그림/보정으로 나눔, 후보 3~4장, `precheck_key.py` 사전 점검 → 3 키마다 새 `keyframe-reviewer`로 채점(만든 쪽이 통과시키지 않음) → 4 가장 작은 수단으로 고치기, **최대 3회** → 5 PASS이고 절차를 지킨 키만 사용자에게. 최종 판정은 사용자다(루트 `CLAUDE.md` 5절).

**영상(모션)** 프롬프트는 키 생성 전에 확정한 `ai-director-cinematography`의 촬영 설계와 6절 `[camera]` 요약을 이어받는다. 샷 크기·렌즈·방향을 이 단계에서 임의로 바꾸지 않는다. 샷 연결(루트 `CLAUDE.md` 3절)과 생성 방식(이 문서 1·4절)은 실제 모델·작품 규칙에 맞춰 확인한다. 인물의 시선이 바뀌면 대상과 순서를 쓴다. 정체성 묘사는 참조 이미지가 맡으므로 프롬프트에는 **일어나는 일만** 쓴다. 형식은 모델별 레시피를 따른다: LTX(기본) [references/ltx.md](references/ltx.md), Wan [references/wan.md](references/wan.md).

규칙:
- 한 샷에는 행동 하나만 넣는다. 끝 상태는 story.json의 `end_state`와 같아야 한다.
- 카메라 용어는 하나로 고정한다. 예: `slow push-in`, `static`, `handheld follow`, `orbit left`.
- 피할 것과 대안:
  - 군중 증식 → 와이드를 따로 찍거나 실루엣으로 처리
  - 정밀한 손동작 → 결과 인서트로 대체
  - 화면 속 긴 글자 → 자막
  - 여러 명이 동시에 말하는 장면 → 컷을 나누고 음성은 나중에 입힘
- 프롬프트 언어는 쓰는 도구에 맞춘다. 영어가 무조건 낫다고 가정하지 않는다.

예시와 샷 표 작성법은 [prompt-examples.md](references/prompt-examples.md)에 있다.

## 3. 승인 게이트 (필수)

생성 요청을 보내기 전에 아래 표를 보여주고 승인을 받는다. Claude Code에서는 AskUserQuestion을 쓴다.

```
[generation_starting]
| 대상 | 모드 | 모델 | 개수 | 예상 비용/시간 |
| refs: ch_mina 시트 | text2image | (도구) | 3 | 도구 문서 기준 |
| S1-1 | image→video | (도구) | 1 | … |
합계: N건 / 예상 X
```

승인 범위를 넘는 재시도나 추가 생성은 다시 묻는다. 게시나 업로드는 절대 자동으로 하지 않는다.

## 4. 실행과 기록

### 기본 생성 도구: 로컬 Codex CLI

이 프로젝트의 생성 도구는 로컬 Codex(`codex exec`)다. Codex 안의 `image_gen` 도구는 GPT Image 계열이며 참조 이미지를 여러 장 받는다. **이 도구는 이미지 전용**이다. 영상은 아래 LTX(기본)·Wan(대체) 경로로 만든다.

| 작업 | 실행 |
|---|---|
| 참조 시트, 키프레임, 씬 프로덕션 시트, 이미지 수정 | `scripts/codex_image.py` |
| 애니매틱 (영상 모델을 쓰지 않을 때, 모션 합격본이 아님) | `scripts/animate_still.py`로 키프레임에 카메라 무브를 준 애니매틱 |
| 체인용 마지막 프레임 | ffmpeg (`ai-director-consistency` 3절) |
| 밤 장면 노출 낮추기(룩 확정·렌더) | `scripts/night_exposure.py` (광원 하이라이트 유지, `--compare`로 단계 비교) |

```bash
# 참조를 라벨과 함께 넣는다. 라벨 범례가 프롬프트 앞에 자동으로 붙는다.
python .claude/skills/ai-director-shot-gen/scripts/codex_image.py \
  --prompt-file stories/<slug>/prompts/S1-1-key.txt \
  --ref character_image1=stories/<slug>/refs/ch_mina_front.png \
  --ref env_image1=stories/<slug>/refs/wd_alley_wide.png \
  --out stories/<slug>/media/S1-1-key-v1.png

python .claude/skills/ai-director-shot-gen/scripts/animate_still.py \
  stories/<slug>/media/S1-1-key-v1.png stories/<slug>/media/S1-1-v1.mp4 --dur 5 --move push-in
```

- 1장에 수십 초~몇 분이 걸린다. 여러 장은 Bash `run_in_background`로 돌린다. 동시 실행은 2~3개까지로 한다.
- 시드와 해상도 옵션이 없다. 화면비와 구도는 프롬프트에 쓴다(예: "Landscape 16:9 frame").
- 비용은 사용자의 Codex(ChatGPT) 사용량에서 나간다. 3절 승인 표의 "모델"에는 `codex image_gen`, 비용 칸에는 "Codex 사용량 N회"로 적는다.
- 참조는 5장 이내로 넣는다. 라벨은 `ai-director-consistency` 0절과 같이 `character_image1..3`, `env_image1`, 소품은 `object_image1`을 쓴다.
- 애니매틱 클립은 version의 `model`을 `ffmpeg-zoompan`으로, `mode`를 `image2video`로 적고 `notes`에 "animatic"이라고 남긴다. 나중에 영상 모델이 생기면 같은 키프레임으로 새 version을 만든다.
- `--move`는 샷의 `camera`에 맞춘다: push-in / pull-out / pan-left·right·up·down / static.
- 키프레임 화면비가 출력과 다르면 경고가 나온다. 키프레임을 출력 화면비로 다시 만들거나 `--fit pad|blur`를 쓴다(기본 crop은 가장자리를 잘라낸다).
- `codex_image.py`는 결과를 확실히 특정하지 못하면 추측하지 않고 실패한다(Codex가 ERROR를 내거나 새 PNG가 여러 장인 경우). 실패한 샷은 version에 `status:"failed"`로 기록하고 다시 묻는다.
  - 병렬 실행 중 결과 경로가 돌아오지 않으면 `codex_image.py`는 추측하지 않고 `HOLD`로 멈추며 후보 PNG 목록을 출력한다(다른 job이 이미 가져간 PNG는 제외). 이미지는 만들어졌으므로 재생성하지 말고, 후보를 Read로 열어 맞는 것을 `--out`으로 복사한다. 같은 라벨을 서로 다른 이미지에 붙이면 생성 전에 거부한다.

### 영상 생성 기본: LTX-2.5 — 사용자 결정 2026-11-10

원격 GPU 서버(아래)에서 `scripts/ltx_remote.py`로 만든다. **기본값은 S3-5 v4의 키·cfg·중간 guide·음성 설정 + v7의 2단계 업스케일**이라 옵션 없이 쓰면 된다. 시간은 당시 측정값으로 v4(1단계) 약 6분, v7(2단계) 약 5분, 첫 로딩 포함 약 7.5분이다(보장값 아님).

```bash
python .claude/skills/ai-director-shot-gen/scripts/ltx_remote.py --image stories/<slug>/media/<shot>-key-vN.png \
  --end-image stories/<slug>/media/<shot>-end-key-vN.png [--audio stories/<slug>/export/<shot>_dialogue.wav] \
  --prompt-file stories/<slug>/prompts/motion/<shot>-ltx.txt --out stories/<slug>/media/video/<shot>-ltx-v1.mp4 --seed <n>
```

| 기본값 | 내용 | 근거(S3-5 v1~v6, `story.json` version notes) |
|---|---|---|
| 모델 | LTX-2.5 22B distilled `UD-Q3_K_XL` GGUF + Gemma4-12B-with-proj int8, 8스텝 | 12GB에 맞는 크기 중 품질 최상(unsloth LPIPS 표) |
| 키 | 시작 키 frame 0 + 끝 키 frame -1, strength 0.7 | 처음·끝이 키와 일치(차이 4.7/5.5) |
| `--video-cfg 2.0` | 부정 프롬프트가 실제로 작동. 1이면 부정어 무시 | v1(cfg 1): 끝 미소·렌즈 응시 → v2(cfg 2): 미소 사라짐 |
| 기본 부정어 | 미소, 카메라 응시, 정면 얼굴, 고개 젖힘, 눈 감기, 입 과장 등 (`NEG`) | v2·v3 |
| `--mid-guides auto` | 시작 키를 24프레임마다 strength 0.25로(끝 2초 전까지; 121f → 24·48·72) | v4: 얼굴 3/4 유지, sync 0.53→0.63, 입 변화폭 1.56→0.58. 0.4(v5)는 입이 줄어 sync 0.53 |
| `--audio-gain -10` | 모델에 넣는 음성만 -10dB. 결과물의 소리는 편집에서 원본 음성으로 넣는다 | v3 |
| 2단계 업스케일 (기본, `--no-upscale`로 끔) | 640×352에서 8스텝 → x2 latent 업스케일러 → 키를 다시 넣고 3스텝(공식 i2v 템플릿). 서버 `--reserve-vram 2` 필수: 없으면 VRAM이 공유 메모리로 넘쳐 39분 뒤에도 1단계에서 멈춤 | v7: 5분, sync 0.67, 입 변화폭 1.00. 선명도는 그대로(얼굴 25 vs v4 27). 3.6초 시선이 v4와 달라짐 |
| 쓰지 않는 것 | `--modality`(A/V 결합): 입이 커지고 sync가 떨어짐(v6 0.47). NAG: LTX 어텐션에 안 걸림 | v6, 코드 확인 |

- **대사 컷**: 음성을 `--audio`로 넣어 그 음성에 맞춰 생성하고, 영상의 입은 그대로 쓴다. **후처리 립싱크(LatentSync)는 기본에서 뺐다**(사용자 2026-11-10 "LatentSync는 못쓰겠다": LTX 위에 입히면 입이 흐려지고 입속이 회색). 입과 소리가 어긋나면 편집에서 **음성 위치만** 옮긴다. 수치(lag)로 정하지 않고 몇 프레임씩 옮긴 버전(예 -4·-2·0·+2)을 만들어 사용자가 보고 고른다.
- 프롬프트에는 부정문("never smiling")을 쓰지 않고 원하는 상태를 긍정문으로 쓴다. 금지할 것은 부정어로 넣는다(cfg 2에서 작동).
- 출력 크기는 작품 화면비를 따른다(9:16은 `--width 704 --height 1280`, 16:9·2.39:1은 기본 1280×704, 2.39는 편집에서 자름 — `ai-director/references/aspect-ratios.md`). 16:9에서 720 컷과 섞을 때는 위아래 8px씩 채우거나 잘라 맞춘다(키를 가운데 기준으로 잘라 만들기 때문에 구도가 맞는다).
- 소리 없는 컷은 `--audio`를 빼면 모델이 소리를 만든다. 결과물의 소리는 쓰지 않고 편집에서 정한다.
- 남은 한계(S3-5): 선명도가 Wan 합격본의 약 1/3(얼굴 라플라시안 70 vs 192), 같은 시드에서는 큰 동작(0.85초 눈 감김)이 설정을 바꿔도 남는다 → 시드를 바꾼다. 모델 로딩 때 RAM 31GB를 넘어 페이지파일을 쓴다(커밋 약 67/91GB).
- **모션 프롬프트는 [references/ltx.md](references/ltx.md)를 따른다.** Wan용 규칙(NAG, RIFE, motionfix, 배속, `normal real-time speed`)은 LTX에 옮기지 않는다.

### 원격 GPU 서버

사용자 PC(RTX 5070 12GB, Tailscale `<GPU_HOST_TAILSCALE_IP>`, ssh 별칭 `gpu-host`, 사용자 `gpu-user`)의 ComfyUI에서 만든다. 사용자 자신의 GPU라 유료 호출이 아니지만 시간이 걸리므로(LTX 약 6분, Wan 15~25분) 몇 건을 거는지와 예상 시간을 알린다.

**1. 컷 단위로 만든다.** 컷끼리 잇는 원테이크(first-last-frame 체인)는 기본 제작 방식으로 쓰지 않는다(사용자 결정 2026-11-04). 연결은 편집에서 일반 컷으로 한다. **한 컷 안의 얼굴·카메라 유지를 위한 끝 키는 컷 간 전환과 다른 용도**다. `--end-image` 선택은 최신 루트 `CLAUDE.md` 2절과 [model-capabilities.md](references/model-capabilities.md)를 따른다. 얼굴이 큰 클로즈업·미디엄은 첫·끝 키를 쓰고, 얼굴이 작고 공간을 지나는 큰 동작은 시작 1장이 적합할 수 있다. 키 사이 시차가 안 맞는 카메라 이동은 촬영 설계를 조정한다.

### 영상 생성 대체: Wan 2.2

사용자가 지정하거나 LTX로 안 되는 컷에만 쓴다. 모션 프롬프트, 얼굴 무너짐 방지, 실행, 속도 조절은 [references/wan.md](references/wan.md)에 있다. 후처리 립싱크(사용자 요청 시만)는 [references/lipsync.md](references/lipsync.md).

**진행 확인과 서버 관리**
- 진행 막대: `python .claude/skills/ai-director-shot-gen/scripts/comfy_progress.py`(5초마다 갱신, `--once`는 한 번만) — 현재 작업 단계·%·남은 시간과 대기열 완료 수·전체 남은 시간. 사용자가 "진행상황"을 물으면 `--once` 결과를 보여준다.
- 진행(브라우저): `http://<GPU_HOST_TAILSCALE_IP>:8188` 대기열(스크립트가 client_id 없이 보내 모든 탭에 진행이 뜬다). 지금 그래프는 서버 `C:\ai\workflows\current_job_api.json`(캔버스에 끌어다 놓기).
- 대기열 보기/비우기: `GET /queue`, `POST /queue {"clear":true}`, 실행 중 중단 `POST /interrupt`. 로컬 대기 프로세스(실행한 `ltx_remote.py`/`wan_remote.py`)도 함께 끈다.
- 재시작: `scp scripts/remote/restart_comfy.ps1 gpu-host:C:/ai/` 후 `ssh gpu-host "powershell -ExecutionPolicy Bypass -File C:\ai\restart_comfy.ps1"`. ComfyUI는 작업 스케줄러 `ComfyUI-Remote`(로그인 시 자동 실행, `C:\ai\start_comfy.bat`)로 돈다. 재시작하면 서버 대기열이 사라지므로 다시 건다.
- Tailscale 주소 접속이 끊기고 `127.0.0.1`만 열려 있으면 재시작한다.
- 사용자가 5070에서 게임을 같이 하면: `start_comfy.bat`에 `--reserve-vram 4`(게임용 4GB 확보). 대신 생성이 2배 이상 느려진다. 게임이 끝나면 LTX 기본값인 `--reserve-vram 2`로 되돌리고 재시작한다(옵션을 빼면 2단계 생성이 멈출 수 있다, S3-5 v7). 시작 명령에 같은 옵션이 중복되지 않았는지 확인한다. 사용자가 게임 중이면 자동으로 재시작하지 않는다.
- 대기 시간은 `--timeout`(기본 6시간)에 포함된다. 대기 프로세스가 죽었으면 `--fetch <prompt_id>`.

**검수와 기록** (정지 프레임 중심 검수를 시간축 검수로 바꿈, 2026-11-08)
- 생성 **전에** shot `success_criteria`(시작·진행·완료·연속성·정체성·카메라)를 관찰 가능한 문장으로 적는다. 방식 선택은 [model-capabilities.md](references/model-capabilities.md)를 본다.
- 생성 **뒤에** `video-reviewer` 에이전트가 `ai-director-consistency/references/video-rubric.md`로 검수한다: `review_video.py`로 0.5초 간격 접촉 시트·얼굴 스트립·움직임/밝기/이음매 후보를 만들고, 후보 구간을 촘촘히 다시 보고, 시간대별 결함과 판정(pass/revise/hold)을 version `review`에 남긴다. 만든 쪽이 스스로 합격시키지 않는다.
- 영상도 개선(재생성·후처리 수정)은 **최대 3회**다. 3회째에도 pass가 아니면 멈추고 사용자에게 보고한다. 사용자가 명시적으로 지시한 재생성(예: "시드 바꿔 재생성", "프롬프트 정리해서 넣어봐")은 회차에 넣지 않는다(사용자 2026-11-10).
- 정지 프레임과 수치만으로 동작을 합격시키지 않는다. 움직임의 자연스러움은 사용자가 재생으로 본 판정이 있어야 pass다. 그 전에는 사용자에게 "검수 후보: 미확인 항목 …"으로 보낸다.
- 서버 작업 ID를 version `job_id`에 남긴다. 생성 스크립트(`ltx_remote.py`, `wan_remote.py`, `codex_image.py`, `rerun_workflow.py`)는 작업마다 `stories/<slug>/ledger.jsonl`에 자동으로 기록한다. 컷별 비용은 `python .claude/skills/ai-director/scripts/ledger.py summary stories/<slug>`.
- GPU 한 작업 원칙은 스크립트가 지킨다: 서버에 실행 중이거나 대기 중인 작업이 있으면 보내지 않는다. 여러 건을 한 번에 넣는 것은 사용자가 요청했을 때만 `--allow-queue`(`queue_shots.sh`가 사용).
- 결과는 story.json version(`kind:"video"`, `status`, `notes`에 설정과 문제)에 기록한다. 실패는 `failed`(사용자가 지우라 하면 파일 삭제, 기록은 남김), 대체는 `superseded`.
- 사용자에게는 한 컷씩 보낸다(파일 경로를 알리고 지원되는 전달 수단을 쓴다).
- 끝나면 `python .claude/skills/ai-director-edit/scripts/tidy_video.py stories/<slug>`: 최종본만 `media/video/`, 원본·16fps·그래프·로그는 `_src/`, failed·superseded는 `_rejected/`.
- 서버 처음 세팅(Wan 대체 수단용 노드·LoRA): `scripts/remote/install_nodes.ps1`(PainterI2V, ComfyUI-NAG, Frame-Interpolation), `download_motionfix_lora.ps1`, `register_comfy_task.ps1`.

### 그 밖의 도구

- 다른 로컬 도구(ComfyUI, 로컬 SD 등)나 API가 있으면 실행하고, 결과를 `stories/<slug>/media/`에 저장한다.
- 생성 도구가 없으면 샷별 프롬프트 패키지(키프레임 프롬프트, 영상 프롬프트, 참조 이미지 목록, 설정)를 출력한다. 사용자가 생성해서 `media/`에 넣으면 그 파일을 version으로 등록한다.
- version 레코드는 아래 형식이다.
  ```json
  {"id":"S1-1-v2","kind":"video","model":"…","mode":"image2video","prompt":"…","seed":null,
   "inputs":["media/S1-1-key-v1.png"],"media_url":"media/S1-1-v2.mp4","status":"done","notes":"v1은 우산 손이 바뀜"}
  ```
- `review.status`가 `pass`인 version만 `active_version_id`로 지정한다(`validate_story.py --stage export`가 막는다). 그 샷의 타임라인 클립에서는 `media_url`만 갈아끼우고 클립 ID와 위치는 유지한다. 새 영상 길이가 다르면 source_out_ms를 조정한다.
- 실패나 거절은 `status:"failed"`와 사유를 남긴다. 같은 실패를 반복하지 않도록 다음 시도의 변경점을 notes에 적는다.

## 5. 다시 생성할 때

사용자가 "@S2-3 다시"라고 하면 순서는 아래와 같다.

1. 무엇이 문제인지 한 줄로 확인한다(정체성, 동작, 카메라, 아티팩트).
2. `ai-director-consistency` 5절의 수정 순서에 따라 가장 작은 수단을 고른다.
3. 새 version을 만든다. 이전 version은 삭제하지 않는다. 사용자가 이전 버전으로 되돌릴 수 있어야 한다.
