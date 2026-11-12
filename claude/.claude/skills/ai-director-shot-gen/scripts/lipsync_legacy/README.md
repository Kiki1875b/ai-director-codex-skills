# 립싱크 후처리 스크립트 (레거시, 참고용)

**지금은 쓰지 않는다.** 2026-11-10부터 립싱크는 기본이 아니고(사용자 "LatentSync는 못쓰겠다"), 2026-11-11 사용자 지시로 서버의 LatentSync(`C:\ai\latentsync`)를 삭제했다. 대사 컷은 음성을 넣어 LTX로 생성하고 편집에서 음성 위치만 옮긴다(`../../SKILL.md` LTX 절, 프로젝트 `CLAUDE.md` 2절).

사용자가 립싱크를 다시 요청할 때와, 「마지막 손님」(`stories/male-gumiho`)에서 무엇을 시도했고 왜 버렸는지 확인할 때를 위해 남긴다. 절차와 실패 사례는 `../../references/lipsync.md`에 있다. LatentSync를 다시 쓰려면 `../remote/install_latentsync.ps1`로 새로 설치한다.

| 파일 | 하는 일 |
|---|---|
| `lipsync_prep.py --story stories/<slug> <컷 id...>` | 컷의 사용 구간 영상과, 그 컷에 걸친 대사를 컷 타임라인에 놓은 WAV를 만든다(`<story>/media/video/_lipsync/in/`) |
| `lipsync_post.py` | 입 주변만 모델 결과를 쓰고 볼·턱은 원본으로 되돌린다. 입 안쪽 밝기 보정, 입술 경계 선명화 |
| `speech_only.py` | 대사가 나오는 구간에만 립싱크 프레임을 쓴다 |
| `mouth_hold.py` | 대사가 끝난 뒤 입을 다문 프레임 하나로 고정한다 |
| `paste_crop.py` | 잘라 키워 립싱크한 얼굴 크롭의 입을 원래 크기 컷에 붙인다 |
| `sv_mouth_composite.py` | SeedVR2로 복원한 얼굴 크롭의 아래 얼굴만 붙인다. 마스크 함수는 `../remote/latentsync_run.py`에서 읽는다 |
| `procedural_mouth.py` | 모델 없이 아래 입술과 턱을 음성에 맞춰 움직인다 |
| `lipsync_eval.py` | 립싱크 결과를 원본과 기준 결과(sync.so 등)에 대어 시간 차·일치·입 벌림·선명도·떨림·halo를 잰다 |

각 파일의 첫 줄 docstring에 사용법이 있다. `lipsync_prep.py` 말고는 경로를 인자로만 받는다.
