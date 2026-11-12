# AI 슬롭 방지와 룩 확정

키프레임이 "AI처럼" 보이는 원인은 대부분 **입력**(스타일 앵커, 참조 이미지)에 있다. 후처리로는 거의 고쳐지지 않는다. 이 문서는 「마지막 손님」(stories/male-gumiho, 2026-11-03)에서 검증한 순서와 웹 조사 결과(끝의 출처)를 정리한 것이다.

## 0. 룩 인터뷰 (작품마다, 기준 이미지를 만들기 전에)

룩은 작품마다 사용자와 정한다. 이 문서의 기본값(중간 톤, 배우 프로필 얼굴, SL Blue)은 답이 없을 때만 쓴다. 질문은 선택지 질문으로 한 번에 1~4개, 선택지마다 추천 표시. 막연한 단어보다 **비교 이미지**로 묻는 편이 정확하다(사용자 답은 대개 "이건 너무…", "못생김", "너무 밝아"처럼 이미지에 대한 반응으로 온다).

| # | 묻는 것 | 선택지 예 | 기록 위치 |
|---|---|---|---|
| 1 | 레퍼런스 작품·장면 (분위기만, 설정은 빌리지 않음) | 사용자가 말한 작품 / 장르 기본 | `references[]` + `bible.style.reference_links`(`ai-director-reference`), 요약은 `bible.style.notes` |
| 2 | 사실감 ↔ 화사함 | 리얼(다큐 질감) / 중간 / 화사(드라마 광고 톤) | `style.anchor` |
| 3 | 주인공 얼굴 톤 | 배우 프로필(매력+피부 결) / 더 화사 / 더 생활감 | 얼굴 기준 프롬프트 |
| 4 | 밝기 (밤·실내) | 원본 / -1 stop / -1.7 stop (`night_exposure.py --compare`) | `style.grade` |
| 5 | 색 룩·LUT | 장르 레퍼런스 그레이드 / SL Blue(기본) / 따뜻한 텅스텐 / 흑백·탈색 등 | `style.grade`, `style.lut` |
| 6 | 장소의 실재감 | 실제 지명 기반 / 가상의 장소 / 사용자 사진 | `script/08-env-handbook.md` |
| 7 | 금지할 룩 | 청록·주황, 네온, 보케, 과한 비 … | `style.negative` |

순서:
1. 1·2·6·7은 기준 이미지 전에, ai-director 2-2 레퍼런스 단계에서 묻는다(답이 앵커와 핸드북이 된다). 1번은 mood 레퍼런스 승인으로, 6번은 location 레퍼런스 승인으로 답할 수 있다. 작품 프레임을 생성 참조로 넣으면 그 질감이 옮으니(2-3), 분위기만 빌릴 때는 측정값과 take/avoid 문장으로 옮기는 편이 낫다.
2. 3은 얼굴 기준 사진 2안을 만들어 보여주며 묻는다.
3. 4·5는 스타일 프레임과 그 LOG→LUT 결과를 보여주며 묻는다(`ai-director-edit` 5절). 장르 레퍼런스 그레이드를 웹에서 찾아보고, 근거가 부족하면 그렇다고 말하고 SL Blue를 기본으로 제안한다.
4. 답은 `bible.style`(anchor, negative, grade, lut, look_frames, notes)에 남긴다. 다음 작품에서 그대로 재사용하지 않고 다시 묻는다(직전 작품 값을 추천 기본값으로 제시하는 것은 좋다).

## 1. 흔한 AI 티와 원인

| 티 | 원인 | 처방 |
|---|---|---|
| 청록·주황 과포화, 사방에서 빛남 | 스타일 앵커에 `cinematic`, `teal-and-amber`, `neon`, `melancholic` 같은 막연한 분위기 단어 | 3절 LOOK 블록으로 교체. 색은 "실제 광원이 내는 색"으로만 쓴다 |
| 출처 없는 조명, 모든 인물에 림라이트 | 광원을 지정하지 않음 | 월드마다 실제 광원 1~3개를 이름과 위치로 적고 "no other light"라고 쓴다 |
| 아이돌 얼굴, 플라스틱 피부 | 기준 사진이 **전신**이라 얼굴이 작아 모델이 얼굴을 지어냄 | 2-1 얼굴 기준 사진(배우 프로필 톤)을 `ref_images[0]`로 둔다 |
| 장소가 게임/사이버펑크 배경 같음 | "비 오는 아시아 골목" 같은 일반형 장소 앵커와, 그걸로 만든 배경 기준 | 2-2 실제 장소 핸드북으로 배경 기준을 다시 만든다 |
| 모든 표면이 젖어 반짝, 보케·빗줄기 과다 | 앵커에 `wet asphalt reflecting…`을 매 컷 반복 | 반사·비는 "빛을 지날 때만 보인다"로 제한 |
| 정중앙·정면 구도 | 기본값 | "off-center, foreground depth"와 인물 위치(3분할)를 샷마다 적는다 |
| 화보 포즈 연기 | 행동을 "말한다/본다"로만 씀 | 자세, 시선(렌즈 옆), 손 동작처럼 **행동**으로 쓴다 |
| 너무 밝은 밤 | 생성 모델은 노출을 올리는 경향 | 4절 로컬 노출 보정으로 기준 이미지를 낮추고 그걸 참조로 넣는다 |

## 2. 기준 이미지 다시 잡기

### 2-1. 얼굴 기준 사진 (인물마다 1장, `refs/<id>_face_v*.png`)
- 전신 정면(의상 기준)과 **따로** 머리·어깨 사진을 만든다. 의상 기준 전신을 `character_image1`로 넣고 같은 사람으로 만든다.
- 톤은 **"에이전시용 배우 프로필 사진"**이다. 매력적이지만 피부 결이 보이고, 아주 옅은 메이크업, 부드러운 창가 키 라이트, 회색 배경, 시선은 렌즈 옆.
- **과보정 주의:** "보정 없는 캐스팅 테스트 사진, 잡티·점·다크서클"까지 가면 사용자가 "못생겼다"고 느낀다(실제 v1에서 거절됨). 장르(로맨스·판타지)에 맞게 주인공은 매력적이어야 한다. 잡티 대신 "natural fine skin texture, not airbrushed"로 쓴다.
- 금지어: `idol-style beauty filter`, `glossy plastic skin`, `strong rim light`, `heavy retouching`.
- 바이블: `ref_images = [face, front, sheet]`. 키프레임 생성 시 `character_image1`=얼굴(정체성), `character_image2`=전신(의상).

### 2-2. 실제 장소 핸드북 → 배경 기준 (`script/08-env-handbook.md`)
- 실제 지명을 하나 고른다(예: 을지로·종로3가 뒷골목, 광장시장 뒤편). 그 장소에 실제로 있는 사물을 목록으로 적는다: 건물 높이와 재질, 셔터 색, 길가 잡동사니, 전봇대와 전선 양, 바닥 재질, **실제 광원**(보안등 색, 창문 불빛, 천막).
- 없는 것도 적는다: "네온 없음", "전선 다발 아님", "바닥 전체가 거울 아님".
- 배경 기준은 **참조 없이** 새로 만든다(옛 AI 배경을 참조로 넣으면 그 질감이 그대로 남는다). 프롬프트 첫 줄: "Photorealistic real photograph, an empty location scouting plate … no people … not stylized, not cyberpunk, not a game environment".
- 배경 기준에 **"Lighting note for actors"**를 넣는다: 인물이 서는 자리에 어떤 빛이 어디서 오는지. 이게 없으면 모델이 얼굴 조명을 임의로 정해 정면 스튜디오 조명이 된다.
- 역방향 등 추가 각도는 새 와이드를 `env_image1`로 넣어 같은 건물·소품을 유지한다.
- 폐기한 기준은 바이블 `notes`에 사유와 함께 남기고 `ref_images`에서 뺀다.

### 2-3. 옛 룩의 시트
- 씬 프로덕션 시트·캐릭터 시트가 옛 룩이면 키프레임 참조로 넣지 않는다(질감이 옮는다). 블로킹은 프롬프트에 글로 쓴다. 꼭 넣어야 하면 역할을 "blocking/layout only, ignore its rendering style"로 지정한다.

## 3. 프롬프트 규칙 (GPT Image 계열 기준)

OpenAI 공식 가이드 요지: `photorealistic`을 명시, "honest and unposed… no glamorization, no heavy retouching", "Avoid cinematic lighting, dramatic color grading, or stylized composition", 참조 이미지마다 번호와 역할을 적는다.

**이미지 역할 줄** (프롬프트 2번째 줄):
```
Image roles: character_image1 = identity (face, hair) — match exactly. character_image2 = costume only.
env_image1 = THE LOCATION: reproduce this exact place, its look, colors and lighting. object_image1 = <prop>.
```

**블로킹과 카메라:** 인물이 공간 어디에(카메라에서 몇 m, 3분할 어느 쪽) 서는지, 몸 방향, 샷 크기, 렌즈. "physically inside the space at the correct scale"을 넣으면 합성처럼 떠 보이는 문제가 줄어든다.

**조명 줄:** 광원마다 위치와 닿는 부위를 쓴다. 예:
```
LIGHTING: the cold white security lamp is high above and slightly front-left: it lights the top of his head,
cheekbones and nose from above, soft shadows in the eye sockets. The bead adds only a faint blue glow on his palm.
The distant tent gives a faint warm edge on his right side. No other light.
```
"구슬 빛만 얼굴을 비춘다"처럼 아주 약한 광원 하나로 얼굴을 밝히라는 지시는 잘 안 듣는다. 얼굴 키는 장소의 실제 광원(가로등, 전구)에 맡기고 마법 광원은 보조로 둔다.

**LOOK 블록** (모든 키프레임 끝에 글자 그대로):
```
LOOK (whole frame): photorealistic film still from a <genre> feature film shot on a real location on Kodak Vision3 500T
35mm film with a spherical lens; natural fine film grain, gentle lens softness, no digital over-sharpening. Real textures:
natural skin with fine texture, worn and used materials. Color: natural and restrained, moderate saturation, no
teal-and-orange grade. Light comes only from the practical sources described; faces are lit by those sources (no
invisible studio fill). Blacks deep but not crushed. Off-center composition with some foreground depth. Avoid rim light
on everything, bokeh balls, light rays, HDR, glossy shine, plastic skin, beauty filter. No readable text, no subtitles.
```
- 톤은 사용자와 정한다. 이번 작품은 "중간"(기존의 화사함과 리얼한 칙칙함 사이)이 채택됐다. 너무 어둡고 탁하게 가면 거절된다.

## 4. 룩 확정 게이트 (키프레임 대량 생성 전에 필수)

1. 가장 어두운 씬 1장 + 가장 밝은/따뜻한 씬 1장의 **스타일 프레임**을 만든다(`media/style-<scene>-vN.png`). 참조는 얼굴·전신·새 배경·소품만.
2. 기존 컷(있으면)과 나란히 놓은 비교 이미지를 만들어 보여준다.
3. 밝기는 로컬로 조정해 고르게 한다(Codex 불필요):
   ```bash
   python <skills>/ai-director-shot-gen/scripts/night_exposure.py refs/wd_alley_wide_v3.png --stops 0.9 --gamma 1.15
   # → refs/wd_alley_wide_v3_darkA.png  (광원 주변 하이라이트는 유지)
   ```
   여러 단계(`--stops 0.9`, `1.5`)를 나란히 보여주고 고르게 한다. 고른 값으로 만든 배경 기준을 키프레임 참조로 쓰고, 렌더 때 같은 값을 다시 건다.
4. 승인되면 `bible.style`에 `anchor`(새 LOOK 요지), `negative`, `look_frames`, `grade`, 이전 앵커는 `notes`에 남긴다. 그다음에 키프레임을 만든다.

사용자 피드백은 보통 한 번에 하나씩 온다(얼굴 → 톤 → 광원·배우 위치 → 장소 → 밝기). 한 번에 다 고치려 하지 말고 지적된 것만 바꿔 1~2장으로 다시 보여준다.

## 4-1. 전신 비율 (다등신 방지)
- GPT Image 계열은 전신 컷에서 인물을 패션 일러스트처럼 늘린다(머리 작고 다리·코트 길게). 「마지막 손님」에서 "28등신 같아", "여전히 다등신"으로 세 번 거절됐다.
- 원인: 의상 기준 전신 사진(화보 비율)과 앵커의 `tall lean build`. 처방:
  1. 와이드·미디엄·투샷처럼 몸이 다 나오는 컷에는 **전신 사진을 참조로 넣지 않는다**(얼굴 기준만).
  2. 앵커를 "average build, 178 cm, normal natural shoulders"처럼 쓴다.
  3. 프롬프트에 BODY PROPORTIONS 줄: 약 7.3등신(남), 7등신(여), 머리 크기 정상, 어깨 약 2.3 머리 폭, 코트는 무릎 바로 아래, 주변 사물 크기(셔터 2.5m, 실외기 70cm, 의자 45cm, 바 90cm).
  4. 그래도 길면 재생성 대신 **부분 수정**: 그 이미지를 `image_1`로 넣고 "인물 비율만 바꾸고 나머지 100% 유지", 머리 +7%, 키 -5%처럼 **작은 단계**로. 한 번에 크게(+15%/-10%) 고치면 과하다는 반응이 온다. 단계별 결과를 확대 비교 이미지로 보여주고 고르게 한다.

## 4-2. 광원 거리와 방향
- 모델은 장면의 광원이 어디 있든 인물을 "바로 위나 앞에서" 비추는 경향이 있다. 사용자 지적: "광원은 더 뒤에 있는데 마치 바로 옆 위에 있는 듯함".
- 프롬프트에 광원과 인물의 **상대 위치와 거리**를 적고, 그에 따른 결과(역광이면 카메라 쪽 면은 그늘, 윤곽광, 그림자가 카메라 쪽으로)를 함께 쓴다.
- 이미 구도가 좋은 컷이면 재생성하지 말고 "조명만 바꾸고 나머지 100% 유지" 부분 수정으로 고친다(S1-5 v4에서 한 번에 통과).

## 4-3. 실내 세트: 설계서 → 3D 블록아웃 → 빈 판(plate) → 인물 삽입
이미지 모델은 치수를 계산하지 못한다. "60 cm 틈"이라고 써도 폭을 지어내고, 시트 한 장에 도면과 사진을 함께 그리게 하면 둘이 서로 맞지 않는다(「마지막 손님」 포장마차에서 시선 방향, 바 끝, 입구 위치가 다섯 번 어긋남). 반복해서 나오는 실내 세트는 아래 순서로 만든다.
1. **설계서** `script/NN-<set>-spec.md`: 크기와 방위(앞/뒤/좌/우의 정의), 구역, 입구, 카메라 방향 규칙(어느 카메라에서 입구가 화면 어느 쪽인지), **소품 목록**(ID, 모양·재질·색, 크기·수량, 위치, 씬별 상태)과 넣지 않는 것. 생활감 소품(테이프, 전선, 봉지, 장갑, 단말기, 전표)도 여기 적는다.
2. **소품 시트**: 목록대로 제품 사진 격자를 만든다. 중요한 소품(예: 사진 소품)은 따로 만든 이미지를 그 칸에 직접 합성한다. 소품 이미지 안에 다른 그림이 들어 있으면 그것까지 복제되므로 확인한다(사진 속 기둥의 풍경 사진 사례).
3. **Blender 블록아웃**: `scripts/set_blockout_example.py`를 본떠 설계서 치수로 박스 모형을 만든다. Workbench 객체색 렌더, 위에서 본 평면 렌더로 도면과 대조한다. 공간이 좁으면 실제 촬영처럼 한쪽 벽을 걷어 내고(wild wall) 밖에서 찍는다. 마네킹 머리에 코 블록을 달아 시선 방향을 고정한다.
4. **빈 판 실사화**: 블록아웃 렌더를 `image_1`로 넣고 "형태와 배치는 100% 그대로, 렌더만 사진으로", 블록아웃 색이 각각 무엇인지, 생활감 소품, 전구 하나의 감쇠(구석은 디테일이 묻힘)를 적는다. 어긋난 부분은 블록아웃을 `image_2`로 함께 넣은 부분 수정으로 고친다.
5. **인물 컷**: 블록아웃에서 바로 인물 컷을 만들면 모델이 장소 참조 쪽 구조를 따라가 다시 틀어진다. **구조가 맞는 빈 판에 인물만 넣는 편집**(나머지 100% 유지)을 하고, 샷 크기는 로컬에서 잘라 맞춘다. 이렇게 S2-1에서 시선·바·틈을 한 번에 지켰다.

## 4-4. 질감 패스 (procedural grunge 제거)
- "낡음·생활감"을 요구하면 모델은 모든 표면에 같은 무늬(갈라진 페인트, 망치 자국, 녹)를 고르게 칠한다. 사용자 지적: "전반적인 질감".
- 구도가 확정된 뒤 **질감만 바꾸는 편집 패스**를 한 번 한다. 재질마다 실제 모습(사출 플라스틱은 매끈한 광택에 긁힘 몇 개, 스테인리스는 결 방향 헤어라인·지문·작은 찌그러짐, 오래된 나무는 결과 손 닿는 모서리만 닳음), 금지 무늬(크랙클, 갈라짐, 망치 자국), "마모는 손 닿고 물 떨어지는 곳에만, 대부분은 그냥 쓰던 깨끗함", 흰 물건은 따뜻한 흰색(주황 아님)을 적는다.
- 같은 세트를 계속 쓸 거면 빈 판(plate)에도 질감 패스를 걸어 두고 그 위에 인물을 넣는다.

## 4-5. 컷 연속성: 직전 컷을 바탕으로
- 인물 컷의 편집 바탕은 **그 시점의 직전 통과 컷**이다. 이전 단계의 빈 판이나 앞 장면 컷을 쓰면 이미 들어온 인물·놓인 소품이 빠진다(S2-8에서 연과 잔이 사라짐).
- 프롬프트에 "이 컷에 있어야 할 사람·소품과 각자의 시선"을 매번 적는다. 앉아 있는 사람도 상대를 보는지 명시한다.
- 역방향 컷(반대편 카메라)은 좌우가 뒤집혀야 한다(180도 규칙). 생성 결과가 정방향 배치면 좌우 반전으로 바로잡을 수 있다(S2-6).

## 4-6. 표정 편집은 얼굴을 바꾼다
- 표정·시선을 크게 바꾸는 편집을 하면 모델이 얼굴을 새로 그려 다른 사람이 된다(S3-10에서 두 번 "다른 사람 같다"). 얼굴 기준 사진을 함께 넣어도 막지 못했다.
- 표정은 **이미 통과한 같은 각도 컷 위에서, 바꿀 부위만(예: 입꼬리) 아주 작게** 고친다. "얼굴을 다시 그리지 말 것, 나머지 100% 동일"을 명시한다. 대본에 없는 시선 변화는 넣지 않는다.
- 결과는 원본과 얼굴만 잘라 나란히 비교해서 보여준다.
- **얼굴 보존 합성(가장 확실):** 통과 컷을 바탕으로 얼굴 외 부분(손·소품·하단)만 편집한 뒤, 원본의 얼굴·머리 영역을 부드러운 마스크로 다시 덮는다. 조명 색이 바뀌는 컷(예: 푸른 마법광)은 생성 모델로 다시 그리지 말고 로컬 색 보정(그라디언트 틴트)으로 입힌다. S4-6에서 "다른 사람 같음" → 이 방식으로 한 번에 통과.

## 4-7. 연쇄 편집 금지 (화질 붕괴)
- Codex 편집은 매번 이미지 전체를 다시 그린다. 같은 와이드를 컷마다 이어 편집하면 디테일이 계속 깎인다. 실측(라플라시안 분산, 같은 영역): 빈 판 152 → 6회 후 95 → 11회 후 29. 사용자 지적 "사진이 전반적으로 뭉개짐".
- 규칙: 인물 컷은 **깨끗한 빈 판에서 1회 편집**으로 만든다(사람·소품을 한 번에). 추가 수정은 결과에서 **바뀐 부위만 마스크로 가져와** 나머지는 이전 픽셀을 유지한다. 와이드를 잘라 확대하지 않는다.
- 이어지는 소품(사진 등)은 확정된 컷의 같은 위치 픽셀을 원근 변환으로 옮겨 붙인다.
- 보내기 전에 선명도 수치를 원판과 비교하고, 손·소품·접촉부를 100% 크기로 잘라 확인한다(손이 컵을 관통한 것을 놓친 사례).

## 4-8. 밤 실외 광원: 거리를 밝히지 않는다
사용자 지적(S5-2, 2026-11-07): "거리가 너무 밝다." 전체를 어둡게 해도 거리가 빛나 보이면 노출이 아니라 **빛의 분포**가 틀린 것이다. 어두운 장면은 프레임 전체를 낮추지 않고 **빛이 닿는 면적을 줄여서** 만든다.

**실제 값(참고용).** 한국 주택가 보안등은 평균 3~5 lux 수준으로 인용되고, KS A 3701의 저밀도 주거지역은 평균 4 lux·최소 1 lux로 정리된다(논문 인용값, 원문 미확인). 미국 지자체 기준의 주거지 골목은 약 3~4 lux, 균제도 약 6:1이다. 즉 실제 골목은 원래 얼룩지고 어둡다. 등 사이가 고르게 밝으면 틀린 것이다.

**등 하나의 감쇠(계산값).** 바닥 조도는 `(h/√(h²+d²))³`을 따른다. 높이 h 3.55m 등 기준으로, 등 바로 아래 대비:

| 등에서 바닥까지 수평 거리 | 2m | 3.5m | 5m | 7m | 10m |
|---|---|---|---|---|---|
| 밝기 | -0.6 stop | -1.5 stop | -2.4 stop | -3.4 stop | -4.7 stop |

**판·키 검수(수치로 잰다).** 도로 영역의 선형 휘도를 등 바로 아래와 비교해 위 표에서 1 stop 이상 밝으면 고친다. 측정은 감마를 풀고(`(값/255)^2.2`) 영역 평균으로 한다.

**흔한 원인과 처방.**
| 원인 | 처방 |
|---|---|
| 모델이 어두운 부분을 고르게 채움. 조명을 안 쓰면 임의로 빛을 넣는다 | 광원마다 닿는 범위를 쓰고 그 밖을 명시: "pool of light about 7 m across under the lamp; beyond it the pavement falls to near black" |
| 젖은 바닥 하이라이트가 넓게 번짐 | 반사는 광원 아래와 천막 앞에만. "pavement is matte dark except where it crosses the lamp pool" |
| Blender 가이드 바닥이 번들거리면 등 아래 웅덩이가 어둡게 나와 도로 밝기가 평평해짐(S5-2 측정: roughness 0.25는 앞쪽 69.8·중간 62.9, 0.85는 앞쪽 69.6·중간 139.8) | 가이드 바닥은 무광(roughness 0.8 이상)으로 렌더한다. 물웅덩이 반사는 판에서 살린다 |
| 전체 노출만 내림 | 벽과 하늘만 뭉개지고 거리는 상대적으로 밝게 남는다. 바닥은 위 감쇠로 **따로** 낮춘다 |
| 화면에 보이는 도로가 대부분 웅덩이 안에 있음(S5-2 카메라 A: 프레임 아래쪽 도로도 등에서 2~4m) | 감쇠만으로는 안 어두워진다. 등 자체의 밝기(웅덩이 최고값)를 낮춘다 |

**지키는 것.** 어둠은 구도의 일부지만 인물 얼굴은 읽혀야 한다. 사용자가 "너무 어둡고 탁함"도 거절했으므로(3절), 등 아래 웅덩이와 천막 앞의 빛은 살려 두고 그 사이만 내린다.

출처: [koreascience 보안등·도로조명 논문 검색(조도 수치가 어느 논문의 것인지 미확인)](https://www.koreascience.kr/article/JAKO201447633877331.pdf), [Kannapolis 가로등 기준](https://kannapolisnc.gov/Portals/0/Kannapolis/Departments/Engineering/Documents/Land%20Development%20Standards%20Manual/Street%20Lighting%20Standards.pdf), [Mohave County 도로조명 지침](https://www.mohave.gov/departments/public-works/documents/roadway-lighting-design-directive/), [PetaPixel 가로등 야간 촬영](https://petapixel.com/2021/07/26/how-to-use-street-lights-to-improve-your-night-street-photography), [Morphic Low Key Lighting](https://morphic.com/es/ai-glossary/Low-Key-Lighting), [Artlist AI 조명 프롬프트](https://artlist.io/blog/ai-lighting-prompts/).

## 5. 하지 말 것
- 후처리(채도↓, 그레인, 하레이션, 블랙 리프트)로 슬롭을 지우려 하지 않는다. 시험 결과 화면만 뿌옇게 되고 AI 티는 남았다. 필름 그레인은 렌더 마지막에 아주 약하게만.
- 기존 AI 이미지를 "질감만 바꿔" 리터치하는 것으로 끝내지 않는다. 구도·조명·장소의 문제는 남는다.
- 키프레임 45장을 룩 확정 전에 돌리지 않는다.

## 출처 (2026-11 조사)
- OpenAI, GPT Image prompting guide: https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide
- flick.art, 5 fixes for AI slop: https://flick.art/blog/how-to-make-realistic-ai-videos
- magicshot, 12 tells: https://magicshot.ai/blog/why-your-ai-images-still-look-fake-12-tells-and-how-to-kill-them
- arcloop, avoid AI slop in video: https://arcloop.ai/handbook/en-US/how-to-avoid-ai-slop-in-ai-videos
- Bottle Rocket, invisible AI integration: https://www.bottlerocketcontent.com/ai-video-filmmaking-workflow-invisible-integration/
- Curious Refuge, professional AI film: https://curiousrefuge.com/blog/how-to-create-an-ai-film
