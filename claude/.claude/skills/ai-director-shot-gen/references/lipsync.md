# 립싱크 후처리 (LatentSync, 레거시)

**기본이 아니다.** 사용자가 요청할 때만 쓴다(사용자 2026-11-10 "LatentSync는 못쓰겠다").
**2026-11-11 사용자 지시로 서버의 `C:\ai\latentsync`를 삭제했다.** 다시 쓰려면 아래 설치 스크립트로 새로 설치한다. 기본은 음성을 넣어 LTX로 생성하고 편집에서 음성 위치만 옮기는 방식이다(`../SKILL.md` LTX 절).
아래 후처리 스크립트는 `../scripts/lipsync_legacy/`에 참고용으로 보관한다(설명은 그 폴더의 `README.md`). 입력 준비(컷 구간 영상 + 컷 타임라인 대사 WAV)는 `lipsync_prep.py --story stories/<slug> <컷 id...>`.

**2-2. 립싱크 (기존 영상 유지, 후처리만. 사용자 승인 2026-11-09 S3-5 "너무 좋다") — 2026-11-10부터 기본 아님, 사용자가 요청할 때만** (기본은 `../SKILL.md` LTX 절: 음성을 넣어 생성하고 편집에서 음성 위치만 맞춤)

다시 생성하지 않는다. 기존 컷 + 대사 WAV(컷 타임라인에 놓고 앞뒤 무음, 음악·효과음 없음)로 입만 바꾼다. 유료 서비스는 쓰지 않는다(사용자: 돈은 최대한 안 씀).

| 순서 | 방법 |
|---|---|
| ① | 서버 `C:\ai\latentsync`(LatentSync 1.6, 코드 Apache-2.0·가중치 OpenRAIL++, InsightFace 대신 MediaPipe): `latentsync_run.py --video shot.mp4 --audio voice_on_shot.wav --out out.mp4 --ckpt C:\ai\latentsync\checkpoints16\latentsync_unet.pt --config configs/unet/stage2_512.yaml --cfg 1.75 --lowmem --max-vram 6.5 --throttle 0.5`. 4.2GB, 5초 컷 약 9.5분. 설치 `scripts/remote/install_latentsync.ps1` + `latentsync_dl16.py` |
| ② | `python .claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/lipsync_post.py --orig shot --synced out_noaudio.mp4 --out final.mp4`: 입 주변만 모델 결과, 볼·턱은 원본(피부 일렁임 제거). 기본으로 입 안쪽 밝기 보정(`--mouth-gamma 0.58`)과 입술 경계 선명화(원본 입술 윤곽 기울기에 자동 맞춤)를 한다 |
| ②-1 | `.claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/speech_only.py --orig --synced --audio --out`: 대사 구간(±0.12초)만 립싱크 프레임, 나머지는 원본 입. **적용 전후 `lipsync_eval.py` sync를 비교해 떨어지면 쓰지 않는다**(원본 입이 쉼 동안 움직이는 컷: S6-4 0.60→0.26, S2-3 0.80→0.50) |
| ②-3 | 얼굴이 작거나 어두워 인식이 안 되면 얼굴 주변을 잘라 2~3배로 키워 립싱크하고 `.claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/paste_crop.py`로 입만 붙인다(S3-7 12/97 → 97/97). 고개를 숙인 각도 자체가 문제면 키워도 안 된다(S4-7) |
| ②-2 | 대사 없는 컷에서 입이 벌어지면 `.claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/mouth_hold.py --start 0`으로 다문 입 고정 |
| ③ | `.claude/skills/ai-director-shot-gen/scripts/lipsync_legacy/lipsync_eval.py --orig --audio --ref <기준 결과> <후보들>`: 시간 차, 소리 일치, 기준과 입 움직임 일치, 입 벌림, 가로 입 모양, 치아, 선명도, 떨림, 입술 경계 하얗게 뜸(halo)을 기준 범위로 판정 |

실패에서 배운 것(되풀이 금지):
- 음성을 앞당기지 않는다. 입-소리 상관의 시간 차는 잘 맞은 결과(sync-3)도 +4프레임이다(S3-5 v2의 0.2초 당김은 오판).
- guidance: 1.5는 입 모양이 작고(가로 0.5배), 1.6에서 2.25 이상은 오므릴 때 입술 경계가 하얗게 뜬다(halo 0.17). 1.6은 1.75.
- 참조 얼굴을 입 벌린 편집 이미지로 바꾸면 입속이 검게 샌다(v3_ref). 쓰지 않는다.
- 얼굴 검출은 첫 프레임 얼굴을 끝까지 추적한다(가장 큰 얼굴을 매번 고르면 배경을 얼굴로 잡아 입이 떨림, S3-5 v1).
- 남은 한계: 크게 벌릴 때 치아가 뭉개진다(기준의 0.1배). 클로즈업에서만 보인다.
- 모델은 벌린 입 안쪽을 거의 검게 칠한다(사용자 지적 "입 안 공간이 너무 검어보여", 2026-11-09). 어두운 10%/볼 밝기 0.07 → 기준 0.19. ②의 입속 보정을 끄지 않는다.
- 모델은 얼굴을 512px로 다시 그려 입술 경계가 원본보다 흐려진다(사용자 지적 "입술 경계가 흐릿해지는게 문제", S4-5). ②의 입술 선명화를 끄지 않는다. 선명도는 입 주변 전체가 아니라 입술 윤곽에서 잰다.
- 대사 사이·뒤에도 모델이 입을 다시 그려 오므린 입이 남는다(S4-5). ②-1로 대사 구간만 쓴다.
- 옆모습·고개 숙인 컷은 얼굴 인식이 안 되어 립싱크가 안 된다(S3-7 12/97, S4-7 3/96 프레임, 잘라 키워도 실패). 대사를 입이 안 보이는 컷으로 옮긴다.
- 검수 기준은 `ai-director-consistency/references/video-rubric.md` 9번(립싱크 컷 입 확대 검사).
- 게임 등 다른 프로그램과 같이 쓸 때는 `--max-vram`(메모리 부족으로 상대가 꺼지는 것 방지)과 `--throttle`(끊김 완화)을 함께 건다.
