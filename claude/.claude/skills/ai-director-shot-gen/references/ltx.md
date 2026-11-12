# LTX-2.5 모션 프롬프트 레시피 (기본 영상 모델)

`ltx_remote.py`로 만드는 컷의 모션 프롬프트(`prompts/motion/<shot>-ltx.txt`, 영어) 작성법이다. 설정값(첫·끝 키, cfg, 중간 guide, 음성)은 `../SKILL.md` LTX 절, 확인된 능력과 실패는 [model-capabilities.md](model-capabilities.md)에 있다. Wan용 처방(`normal real-time speed`, 느린 부사 금지, NAG 부정어)은 [wan.md](wan.md)에만 적용한다.

출처: [LTX 프롬프팅 가이드](https://docs.ltx.io/open-source-model/usage-guides/prompting-guide), [LTX image-to-video 가이드](https://docs.ltx.io/open-source-model/usage-guides/image-to-video) (2026-11-10 확인).

## 공식 권장을 적용한 작성법

각 항목의 근거 종류를 표시한다. **[공식]** 위 공식 문서의 권장, **[프로젝트]** 이 프로젝트가 고른 방식, **[로컬]** 이 프로젝트의 코드·관찰. 권장은 기본값이지 자동 FAIL 기준이 아니다.

1. **한 문단, 현재형, 대략 4~8문장.** [공식] ("a single flowing paragraph", "present tense verbs", "roughly 4–8 descriptive sentences") 조각을 `+`로 잇지 않는다. 문장 수는 대략적인 기본값이고, 대사가 있거나 동작이 복잡하면 늘거나 줄 수 있다.
2. **일어나는 일 중심으로 쓴다.** [공식] ("the model already knows what the scene looks like from your image") 시작 키가 이미 보여 주는 얼굴·의상·장소는 다시 묘사하지 않는 것을 기본으로 한다. [프로젝트]
3. **처음부터 끝까지 자연스러운 순서로 쓰고, 동작 서술의 끝에서 움직임이 끝난 모습을 분명히 쓴다.** [공식] ("Write the core action as a natural sequence that flows from beginning to end", "Describing how subjects appear after the movement helps the model complete the motion accurately") 끝 모습은 story.json `end_state`와 같게 쓴다. [프로젝트] 소리 설명은 그 뒤에 따로 붙여도 된다.
4. **클로즈업은 더 자세히 쓰되, 외형이 아니라 미세 동작을 쓴다.** [공식] "close-ups need more detail than wide shots"를 2번과 함께 적용한 것이다. 눈길이 옮겨 가는 곳, 눈꺼풀, 숨, 입술이 닫힌 상태, 머리카락의 흔들림 같은 것이다. [프로젝트]
5. **속도·리듬은 `Lingering shot`, `Continuous shot`, `Sudden stop` 같은 말로 쓴다.** 이 표현들은 공식 목록에 있다. [공식] 같은 목록의 `Slow motion`, `Time-lapse`, `Rapid cuts`를 쓰지 않는 것은 슬로모션을 피하는 이 프로젝트의 선택이다. 모델이 그 표현을 못 쓴다는 뜻은 아니다. [프로젝트]
6. **첫 프레임에서 시작하는 컷은 한 테이크로 쓴다.** [공식] ("prefer a single continuous take unless you intentionally describe a cut away from that opening image") 이 프로젝트는 컷 단위로 만들고 연결은 편집에서 하므로 의도된 컷 전환도 쓰지 않는다. [프로젝트]
7. **소리는 동작과 구분해 분명히 쓴다.** [공식] 음성을 넣지 않는 컷은 들려야 할 소리만 긍정문으로 쓴다(예: `Only the sound of the stream and the forest ambience is heard.`). [프로젝트] 이 프로젝트 설정은 audio_cfg가 1로 고정이라 소리 쪽 부정어는 작동하지 않는다(코드 확인). [로컬] 모델이 목소리를 만들면 입이 그 소리에 맞춰 움직일 수 있어서다. 결과물의 소리는 어차피 편집에서 정한다. 이렇게 쓰면 원치 않는 목소리가 사라지는지는 아직 확인하지 않았다(아래 관찰 실패 참조).

기존 규칙 중 그대로 유지하는 것: 원하는 상태는 긍정문으로 쓰고, 금지할 것은 부정어(`--negative`)로 넣는다(cfg 2에서 작동, `../SKILL.md`). 빛은 한 컷에 한 가지 논리로 둔다("one coherent light logic per shot").

## 예시 (구조만, 내용은 컷에 맞춘다)

```
She keeps her palm resting on the moss as her eyes move from the stone to the water's edge. Her breath lifts her shoulders once and settles. A few strands of silver hair stir in the air near her temple while her lips stay softly closed. The camera holds still in a lingering shot. By the end she is looking at the water, her hand still on the moss, her face calm and still. Only the sound of the stream and the forest ambience is heard.
```

## 확정되지 않은 것 (규칙이 아님, 비교해서 정한다)

- **CFG**: 공식 distilled 설정은 CFG 1이다. 이 프로젝트는 부정어를 작동시키려고 2를 쓴다(S3-5 v1→v2에서 미소 사라짐). 2는 생성 시간이 약 2배다. 같은 컷·같은 시드로 1 / 1.5 / 2를 비교해 부정어 효과와 시간을 함께 기록한다.
- **첫·끝 키 단계 수**: 공식 첫·끝 키 템플릿은 업스케일 없는 1단계다. 지금 기본값은 2단계(업스케일)다. 같은 키·시드로 비교한다(CONSENSUS G 파일럿).
- **초 단위 구간 지정**(예: "1.2초부터 3.5초까지"): 공식 문법이 없다("Write the beats you want into the prompt"만 있음). 시험 전에는 비트 순서로만 쓴다.
- **감정 표현**: 공식 가이드는 "Express emotion through physical cues, not abstract labels"라고 한다. 지금 규칙(루트 CLAUDE.md 2절, 표정 기본 무표정·감정 동작 금지)은 Wan에서 나온 것이다. 바꿀지는 사용자 결정 변경 제안 U2이며, **감정이 필요한 LTX 컷이 생기면 현행 방식과 몸의 단서 방식을 비교한 뒤 정한다**(사용자 2026-11-10). 그 전에는 현행 규칙을 따른다.

## 관찰된 실패 (LTX, 표본이 적음)

- 작은 빛의 위치를 말로 지정해도 따르지 않았다. 빛 중심이 손바닥 약 50px 앞에 생겼다(mystic-forest S1-1W v5~v7, 1계열). 위치가 정확해야 하면 합성한다.
- 동작 설명에 속삭임(whisper)을 넣었더니 모델 소리에 사람 목소리가 생겼다(S1-1W v3). v4에서 문장을 뺐지만 목소리가 사라졌는지는 기록이 없다.
- 같은 시드에서는 큰 동작 결함(0.85초 눈 감김)이 설정을 바꿔도 남았다. 시드를 바꾼다(S3-5).
