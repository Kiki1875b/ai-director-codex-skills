# 효과음·BGM 생성 기록 (도구 선택과 실패 사례)

근거: 「점등」(`stories/mystic-forest`) S1 사운드 작업, 2026-11-11. 사용자 판정은 `stories/mystic-forest/ledger.jsonl`, 진단 상세는 `stories/mystic-forest/reviews/sfx/sa3-root-cause-20261111.md`.
모든 수치와 판정은 원격 GPU(RTX 5070 12GB, 다른 프로그램이 약 2GB 사용)에서 측정했다. 다른 환경에서는 다시 확인한다.

## 1. 현재 기본값

| 용도 | 기본 | 실행 | 메모 |
|---|---|---|---|
| 효과음(생성) | Stable Audio 3 **Small-SFX**, ComfyUI 공식 템플릿 그대로(Qwen3.5 재작성 → T5Gemma → lcm 8스텝 cfg 1 simple) | `python .claude/skills/ai-director-shot-gen/scripts/sa3_template.py <out> stable_audio_3_small_sfx.safetensors <초> <시드> <이름> SFX "<짧은 아이디어>"` | 실제로 녹음할 수 있는 구체적 소리만 깨끗하다(아래 3절). 사용자 채택: 판타지 점등 `f5_spirit_med`(Medium)를 음높이만 바꿔 켜짐·꺼짐 전부에 씀 |
| 효과음(실제 녹음) | Sonniss GDC 번들(로열티 프리, 표기 불필요), Pixabay(공식 FAQ: 상업 무료·표기 불필요, 파일 재배포 금지) | `python .claude/skills/ai-director-edit/scripts/sound/sfx_fetch.py find "<정규식>"` → `get --story stories/<slug> "<member>"` (Sonniss) | 물·바람·발소리처럼 생성이 약한 소리는 실제 녹음이 우선 |
| BGM | **ACE-Step 1.5 2B turbo + ScragVAE 디코더** (둘 다 MIT) | `scripts/remote/ace_bgm.py` + job에 `"vae_decoder_dir": "C:/ai/acestep/checkpoints/vae_scrag"`, 실행은 `C:\ai\acestep\ace_run.ps1`(우선순위 낮음, UTF-8) | 사용자: "2B + ScragVAE 이 조합이 제일 깔끔하다" |
| 판정 | **사용자 귀** | 측정은 클리핑·빈 출력·끊김·대역 확인용 | Gemini·CLAP은 질감 판정에 못 쓴다(4절) |

그 밖의 도구(사용법은 각 파일 첫 줄):
- 생성: `ai-director-shot-gen/scripts/sa3_gen.py`(재작성 없이 프롬프트를 직접 넣음, base 체크포인트는 `SA3_STEPS=50 SA3_CFG=7`), `sa3_official.py`(공식 HF Space로 같은 시드 비교), `remote/moss_gen_server.py`(서버에서 실행하는 MOSS 생성, 3절 표의 결과 참고). 서버 주소는 env `COMFY_URL`이다.
- 측정·가공: `ai-director-edit/scripts/sound/`의 `sfx_measure.py`(길이·피크·클리핑·튐·바닥 잡음), `sfx_diff.py`(같은 시드 두 디코드의 상관·잔차), `sfx_offtail.py`(타격음을 떼고 잦아드는 꼬리만 남김), `gemini_listen.py`(Gemini 청취 판정, 결과는 측정으로 확인).

## 2. BGM 시도와 결과

| 시도 | 설정 | 측정 | 판정 |
|---|---|---|---|
| SA3 Medium(증류) | 공식 템플릿 Music, 8스텝 cfg 1 | 4~8kHz -56dB(실제 녹음 -28dB). 클리핑 없음 | 사용자 "먹먹하고 깔끔하지 못함". Gemini: "4~5kHz 위가 잘림" |
| SA3 Medium **base** | 공식 base 템플릿 50스텝 cfg 7 | 8~16kHz는 늘었지만 4~8kHz보다 커짐(잡음 모양) | Gemini: 쉬익 잡음·금속성 끽끽·물속 소리. 사용 안 함 |
| ACE-Step 1.5 2B turbo(원래 디코더) | 8스텝 shift 3, LM 1.7B thinking | SA3보다 4~8kHz 10~30dB 밝음 | 사용 가능, 아래 둘보다 덜 깔끔 |
| **2B + ScragVAE** | 같은 잠재값을 디코더만 교체해 비교 | 상관 0.995, 고음 +1~2.5dB | 사용자 "확실히 더 낫다" → **채택** |
| ACE-Step 1.5 XL turbo(4B) | int8_weight_only, DiT CPU 오프로딩, VRAM 상한 0.75 → OOM 없음 | 2~4kHz는 밝으나 12kHz 위가 8~12kHz보다 큼(잡음 의심), 클리핑 5~22샘플 | 사용자: 2B+ScragVAE가 더 깔끔. 서버에서 삭제 |

ACE-Step 주의:
- **같은 시드로 다시 돌려도 다른 곡이 나온다**(LM 계획 단계, 재생성 상관 0.02). 디코더 비교나 나중에 다시 디코딩하려면 생성할 때 잠재값을 저장한다: `scripts/remote/ace_decoder_ab.py`(같은 잠재값 → 원래 디코더 A / 다른 디코더 B, `_latents.npy`).
- 지정 길이보다 2~5초 일찍 끝나고 끝이 30dB 가까이 뚝 떨어진다. 필요한 길이보다 9초쯤 길게 주문하고(31초 영상 → 40초) 끝은 편집에서 페이드한다.
- 공식표의 50스텝 SFT는 turbo보다 품질 등급이 낮다("High" vs "Very High"). 스텝을 늘리는 것은 개선책이 아니다.

## 3. 효과음 시도와 결과

| 시도 | 결과 |
|---|---|
| SA3를 **50스텝 cfg 7**로(증류 체크포인트) | 찌그러짐. Small-SFX는 전체가 +3dB 직류로 포화 → 증류 체크포인트는 8스텝 cfg 1만 쓴다 |
| SA3 Medium, 직접 쓴 프롬프트(공식 템플릿의 Qwen 재작성 생략) | 사용자 "다 이상하고 깨져 있음"(약 60개 탈락) |
| **공식 템플릿 그대로(Qwen 재작성) + Small-SFX** | 사용자 "훨씬 좋아졌다". 단 낮고 따뜻한 소리(예: 등불 웅웅)는 1kHz 위 -41dB로 먹먹 → 시드·EQ로 안 풀림 |
| cfg 1.2 + 부정 프롬프트("clipping, distortion, …, muffled") | 다른 소리가 되지만 고음은 늘지 않음(-41 → -43dB). cfg 1에서는 부정 프롬프트가 계산되지 않는다 |
| 정밀도(확산 fp32, VAE fp32 `--fp32-vae`, 텍스트 인코더 `--fp32-text-enc`) | VAE bf16과 fp32 차이가 신호보다 -19~-24dB로 측정됐지만 사용자 "같다" → 들리는 원인 아님 |
| HF 공식 Space(공식 구현, pingpong 샘플러) | ComfyUI보다 "낫긴 한데 부족". 익명 ZeroGPU 한도가 3회 만에 소진 |
| 추상적 프롬프트("magical shimmer", "fairy sparkles") | 고음이 촘촘한 반짝임 계열은 금속성·사각거림이 남는다(가설: 잠재 압축 복원 오차가 2kHz 위, 특히 12kHz 위에서 큼). 구체적 물체(유리 풍경, 싱잉볼, 유리잔 테두리)는 깨끗 |
| 물방울·숨결·바람 | 물방울만 Gemini 통과, 사용자 "물방울로 안 들림". 숨결은 사람 한숨, 바람은 잡음 → 실제 녹음으로 |
| 꺼짐 소리 | 생성한 "잦아드는 소리"는 앞에 타격음이 붙음. 채택: 켜짐 소리를 짧게 잘라 깜빡임 시점에 놓고 점점 작게, 마지막만 -3반음 |
| MOSS-SoundEffect v2.0 (Apache-2.0) | 공식 로더가 DiT·VAE를 fp32로 올려 9.5GB 상한에서도 OOM(12GB 공유 카드). bf16 변환 시험은 안 함. 서버에 `C:\ai\moss_sfx` 설치만 남음 |

## 4. 검수 도구의 한계

- **Gemini 3 Flash**(무료 등급, Pro는 무료 한도 0): 사용자가 탈락시킨 소리 4개를 통과시켰고, "1초에서 끊김"·"클리핑" 지적이 측정과 맞지 않았다. 브리프에 측정값을 넣으면 그대로 따라 말한다. 쓰려면 측정값 없이 묻고, 지적은 측정으로 확인한다(`sound-rubric.md` 9절).
- **CLAP**(`laion/larger_clap_general`, Apache-2.0, 평가 전용): 실제 녹음 6개 중 5개를 맞혔지만 사용자가 "물방울로 안 들린다"고 한 것도 물방울로 판정했다. 소리 종류는 보지만 질감은 못 본다.
- 클리핑 0개·끝 페이드 정상이어도 깨져 들릴 수 있다. 질감은 사용자 청취로만 판정한다. 스피커 의심이 나오면 실제 녹음 1개 + 생성물 + 저역 제거본을 같은 크기로 들려 가른다(이번: 스피커 아님).

## 5. 라이선스로 제외한 모델 (HF 원본 저장소 표기, 2026-11-11 확인)

| 모델 | 라이선스 |
|---|---|
| AudioLDM / AudioLDM 2 (`cvssp/*` 6종) | CC-BY-NC-SA 4.0 |
| Meta AudioGen (`facebook/audiogen-medium`) | CC-BY-NC 4.0 (코드 audiocraft는 MIT) |
| MMAudio, ControlFoley, Sony Woosh, MusicGen | 가중치 CC-BY-NC |
| Foley-Omni | MIT 표기지만 MMAudio VAE·보코더·Synchformer 가중치 포함 |
| HunyuanVideo-Foley | 약관에서 한국·EU·영국 제외 |
| YuE2 | CC-BY-NC 4.0 (YuE v1 가중치 4종은 Apache-2.0, 저사양 포크 YuEGP는 라이선스 표시 없음) |
| LTX-2.3 Foley V2A LoRA | LTX-2 커뮤니티 라이선스, 단 학습 데이터 일부(FoleyBench) CC BY-NC-SA. 22B dev 원본 필요, 2.5 미검증 |
| Google Lyria | 곡당 약 $0.04~0.08(2차 자료), 상업 조건 원문 미확인 |

## 6. 원격 GPU 운용

- 공유 12GB 카드에서는 VRAM 상한(`torch.cuda.set_per_process_memory_fraction`)과 우선순위 BelowNormal로 돌린다. 상한을 넘으면 다른 프로그램 대신 우리 작업이 OOM으로 멈춘다.
- 생성 전 ComfyUI가 잡은 VRAM을 `POST /free {"unload_models":true,"free_memory":true}`로 비운다.
- Windows 원격 Python은 `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`이 없으면 로그의 이모지에서 cp949 오류로 죽는다(ACE-Step).
- 서버로 job 파일을 올릴 때 작품별 이름을 쓴다(`<slug>_bgm_vN.json`). 같은 이름으로 다른 작품의 job을 덮어쓴 적이 있다.
- 2026-11-11 서버 정리: LatentSync 폴더, ACE XL turbo, ComfyUI `input`·`output\aid` 삭제. 추가 설치: SA3(`medium`, `medium_base`, `small_sfx`), `qwen3.5_2b_bf16`, ScragVAE, MOSS 가상환경, CLAP.

## 7. 믹스에 BGM을 넣을 때

- 음악을 깔면 효과음의 여유가 줄어든다(점등 +5.5 → +1.5dB). 음악을 넣은 뒤 효과음과 배경(앰비언스+음악)의 차이를 다시 재고 올린다.
- 음악은 숲 소리보다 5~7dB 아래(「점등」 개울 ref -40, 음악 ref -43), 대사 구간 -10dB 덕킹(attack 0.3, release 1.2).
