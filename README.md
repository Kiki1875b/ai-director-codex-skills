# AI Director — Codex & Claude Code Skills

채팅으로 짧은 AI 영화를 만드는 스킬 묶음입니다. [Codex](https://github.com/openai/codex)용(`skills/`)과 [Claude Code](https://claude.com/claude-code)용(`claude/`) 두 버전이 있습니다. 원본은 Claude Code 버전이고, Codex 버전은 `port_to_codex.py`로 변환한 결과입니다. 시나리오 → 캐릭터·배경 시트 → 씬 프로덕션 시트 → 키프레임 → 애니매틱 → 편집·렌더까지, `story.json` 문서 하나를 기준으로 진행합니다.

OpenArt Director·Smart Shot의 공개 클라이언트 동작(참조 이미지 묶음, 씬 단위 프로덕션 시트, 라벨 붙은 참조)을 관찰해 같은 흐름을 일반 도구로 재구성했습니다. OpenArt의 코드, 서버 프롬프트, 이미지는 포함하지 않습니다.

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `ai-director` | 전체 진행. 시나리오 → 레퍼런스 → 바이블 → 연출·촬영 설계 → 승인 → 생성 → 검수 → 편집 → 내보내기 |
| `ai-director-writer` | 장르 추천 → 핵심 질문 → 로그라인·시놉시스·비트시트·아웃라인 → 초고 → **별도 컨텍스트 리뷰어** 채점(최대 3회) → `story.json` 변환 |
| `ai-director-reference` | 촬영 기법·장소·분위기 레퍼런스를 출처·타임코드와 측정 증거(접촉 시트, 밝기, 팔레트, 화면 움직임)로 기록 |
| `ai-director-scene-direction` | 장면 관점, 감정 비트, 배우 블로킹, 시선 인계, 씬 단위 검수 |
| `ai-director-cinematography` | 키 생성 전 구도·카메라·시선 높이·관객 시선 연결·무빙 설계 |
| `ai-director-consistency` | 캐릭터·배경·스타일 바이블, 기준 사진, 시트, 연속성 장부, 키·영상 검수 루브릭 |
| `ai-director-shot-gen` | 생성 방식 선택, 키프레임 절차(Blender 세트 → 생성 → 채점), LTX/Wan 영상, 효과음(Stable Audio 3), 승인 게이트, 버전 관리 |
| `ai-director-edit` | 타임라인(트랙·클립), 트림·속도·트랜지션·자막, 사운드 믹스·BGM(ACE-Step), LOG→LUT, ffmpeg 렌더 |

## 요구 사항

- Codex CLI (내장 `image_gen` 도구 사용 가능, 하위 에이전트 기능 권장)
- Python 3.10+
- ffmpeg / ffprobe (애니매틱과 렌더)
- 한글 자막 렌더: 한글 TTF 폰트(Windows 기본값 `malgun.ttf`, 다른 OS는 `--font`로 지정)

## 설치

`skills/` 아래 여덟 폴더를 Codex 스킬 폴더(`$CODEX_HOME/skills`, 기본 `~/.codex/skills`)에 복사합니다.

```bash
git clone https://github.com/Kiki1875b/ai-director-codex-skills.git
cp -r ai-director-codex-skills/skills/* "${CODEX_HOME:-$HOME/.codex}/skills/"
```

PowerShell:

```powershell
git clone https://github.com/Kiki1875b/ai-director-codex-skills.git
$dst = if ($env:CODEX_HOME) { "$env:CODEX_HOME\skills" } else { "$HOME\.codex\skills" }
Copy-Item -Recurse -Force ai-director-codex-skills\skills\* $dst
```

Codex를 다시 시작하면 스킬이 보입니다.

## 사용

영상 프로젝트 폴더(작업물이 `stories/<slug>/`에 쌓입니다)에서 Codex를 열고:

```
$ai-director 구미호가 나오는 60초 단편 영화 만들어줘
$ai-director-writer 단편 영화 시나리오 써줘
$ai-director-consistency stories/<slug>/refs/hero_front.png 로 캐릭터 시트 만들어줘
```

이름 없이 "AI 영화 만들어줘", "시나리오 써줘", "캐릭터 시트" 같은 말로도 트리거됩니다.

### 흐름

```
아이디어
  └─ ai-director-writer ── 리뷰어(별도 컨텍스트)      시나리오, story.json
        └─ ai-director ─┬─ ai-director-consistency    기준 사진, 캐릭터·배경 시트
                        ├─ ai-director-shot-gen       씬 시트 → 키프레임 → 애니매틱
                        └─ ai-director-edit           타임라인 → mp4
```

- 돈(사용량)이 드는 생성 전에는 항상 개수와 비용을 표로 보여주고 승인을 받습니다.
- 선택이 필요한 지점에서는 번호 선택지를 보여주고 답을 기다립니다.

### 스크립트

| 스크립트 | 용도 |
|---|---|
| `ai-director/scripts/validate_story.py` | story.json 검사(참조, 연속성 필드, 타임라인, 목표 길이) |
| `ai-director-consistency/scripts/build_sheet_prompt.py` | 씬 → 프로덕션 시트 프롬프트(`smart-shot` / `film-bible`)와 참조 라벨 목록 |
| `ai-director-shot-gen/scripts/animate_still.py` | 키프레임 → 카메라 무브 애니매틱(push-in, pan 등) |
| `ai-director-edit/scripts/render_timeline.py` | 타임라인 → mp4/mov (트랜지션, 오디오 믹스, 자막) |

## Claude Code 버전 (`claude/`)

`claude/`는 영상 프로젝트 루트에 그대로 놓는 구조입니다.

| 경로 | 내용 |
|---|---|
| `claude/.claude/skills/` | 위 8개 스킬 원본 |
| `claude/.claude/agents/` | 별도 컨텍스트 리뷰어·스카우트: `screenplay-reviewer`, `keyframe-reviewer`, `video-reviewer`, `scene-reviewer`, `reference-scout` |
| `claude/.claude/hooks/require_skill.py` + `settings.json` | 생성·편집 스크립트를 해당 스킬 호출 없이 실행하면 막는 PreToolUse 훅 |
| `claude/CLAUDE.md` | 프로젝트 지침(반복된 실수를 막는 체크리스트, 진행 규칙) |

```bash
git clone https://github.com/Kiki1875b/ai-director-codex-skills.git
cp -r ai-director-codex-skills/claude/.claude ai-director-codex-skills/claude/CLAUDE.md <영상 프로젝트 루트>/
```

훅은 Claude Code를 다시 시작하거나 `/hooks`를 한 번 열면 적용됩니다.

### 원격 GPU 설정

영상·효과음 스크립트(`ltx_remote.py`, `wan_remote.py`, `sa3_template.py` 등)는 ComfyUI 서버 주소를 환경 변수 `COMFY_URL`로 받습니다(기본 `http://127.0.0.1:8188`). 문서 속 `<GPU_HOST_TAILSCALE_IP>`, ssh 별칭 `gpu-host`, 사용자 `gpu-user`는 자리표시자이니 자기 환경으로 바꿔 쓰세요. ComfyUI를 공인 인터넷에 열지 말고 Tailscale 같은 사설망으로만 접속하세요.

## 한계

- 영상 생성(LTX/Wan)과 효과음·BGM은 별도 GPU의 ComfyUI 서버가 필요합니다. 서버가 없으면 영상은 키프레임에 카메라 무브를 준 **애니매틱**입니다.
- `image_gen`은 시드·해상도 지정이 없습니다. 일관성은 참조 이미지와 시트, 앵커 원문 유지로 맞춥니다.
- 리뷰어 점수는 작법 기준 평가이며 흥행 예측이 아닙니다. 독창성 확인도 기계적 대조가 아닙니다.
