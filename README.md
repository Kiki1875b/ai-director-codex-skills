# AI Director — Codex Skills

채팅으로 짧은 AI 영화를 만드는 [Codex](https://github.com/openai/codex) 스킬 묶음입니다. 시나리오 → 캐릭터·배경 시트 → 씬 프로덕션 시트 → 키프레임 → 애니매틱 → 편집·렌더까지, `story.json` 문서 하나를 기준으로 진행합니다.

OpenArt Director·Smart Shot의 공개 클라이언트 동작(참조 이미지 묶음, 씬 단위 프로덕션 시트, 라벨 붙은 참조)을 관찰해 같은 흐름을 일반 도구로 재구성했습니다. OpenArt의 코드, 서버 프롬프트, 이미지는 포함하지 않습니다.

## 스킬

| 스킬 | 하는 일 |
|---|---|
| `ai-director` | 전체 진행. 시나리오 → 바이블 → 스토리보드 → 승인 → 생성 → 검수 → 편집 → 내보내기. 아래 스킬을 단계마다 부른다 |
| `ai-director-writer` | 장르 추천 → 핵심 질문 → 로그라인·시놉시스·비트시트·아웃라인 → 초고 → **별도 컨텍스트 리뷰어** 채점(최대 3회) → `story.json` 변환. 숏폼(≤3분)·단편(3~20분) |
| `ai-director-consistency` | 캐릭터·배경·스타일 바이블(텍스트 앵커), 정면 전신 기준 사진, 캐릭터 시트, 씬 프로덕션 시트(Smart Shot 형식), 연속성 장부, 드리프트 검수 |
| `ai-director-shot-gen` | 생성 모드 선택, 키프레임·움직임 프롬프트, 승인 게이트, 내장 `image_gen` 호출 규칙, 애니매틱, 버전 관리 |
| `ai-director-edit` | 타임라인(트랙·클립), 트림·속도·트랜지션·자막·음향, ffmpeg 렌더 |

## 요구 사항

- Codex CLI (내장 `image_gen` 도구 사용 가능, 하위 에이전트 기능 권장)
- Python 3.10+
- ffmpeg / ffprobe (애니매틱과 렌더)
- 한글 자막 렌더: 한글 TTF 폰트(Windows 기본값 `malgun.ttf`, 다른 OS는 `--font`로 지정)

## 설치

`skills/` 아래 다섯 폴더를 Codex 스킬 폴더(`$CODEX_HOME/skills`, 기본 `~/.codex/skills`)에 복사합니다.

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

## 한계

- Codex에는 영상 생성 모델이 없습니다. 영상은 키프레임에 카메라 무브를 준 **애니매틱**입니다. 영상 모델 API를 쓸 수 있으면 같은 키프레임과 시트를 참조로 넣어 교체하면 됩니다.
- `image_gen`은 시드·해상도 지정이 없습니다. 일관성은 참조 이미지와 시트, 앵커 원문 유지로 맞춥니다.
- 리뷰어 점수는 작법 기준 평가이며 흥행 예측이 아닙니다. 독창성 확인도 기계적 대조가 아닙니다.
