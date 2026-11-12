# 연출·촬영 인계 기록 예

기록은 `story.json`의 해당 scene/shot에 둔다. 아래는 한 장면의 일부이며 독립적인 story.json이 아니다. 필드 정의 원본은 `<skills>/ai-director/references/story-schema.md`의 "연출·촬영 설계"다.

장면 의도: 서 있는 A가 앉은 B에게 컵을 내밀어 화해를 제안한다. 새 대사는 만들지 않는다. 아래 좌표는 **설계 예**이며 실제 작품의 측정값이 아니다. 기존 세트가 있으면 실제 좌표로 대체한다.

```json
{
  "direction": {
    "viewpoint": "A가 내밀기 어려워하는 순간을 따라간다",
    "dramatic_turn": "컵을 숨기던 A가 B에게 먼저 내민다",
    "beats": [
      {"action": "A가 B를 보다 컵으로 시선을 내린다", "audience_learns": "A가 말을 대신할 행동을 선택한다", "shot_ids": ["S1-1"]},
      {"action": "A가 컵을 B에게 민다", "audience_learns": "컵을 상대에게 내미는 제안임이 드러난다", "shot_ids": ["S1-2"]},
      {"action": "B가 컵에서 A의 눈으로 시선을 올린다", "audience_learns": "B가 제안을 알아차렸다", "shot_ids": ["S1-3"]}
    ]
  },
  "shots": [
    {
      "id": "S1-1",
      "camera": "CU 85mm, camera south of the A-B axis, locked-off",
      "start_state": "서 있는 A가 앉은 B의 눈을 본다",
      "end_state": "A가 아래의 컵으로 시선을 옮기고 손을 움직이기 시작한다",
      "staging": {
        "status": "planned",
        "axis": "A(-0.8,0)–B(0.8,0); 카메라는 y<0 쪽",
        "camera": {"position_m": [0.8, -1.2, 1.5], "look_at_m": [-0.8, 0, 1.6], "lens_mm": 85},
        "blocking": "A는 서 있음, 눈높이 1.65m. B는 앉음, 눈높이 1.15m. 컵은 A 앞 테이블 위",
        "gaze": [
          {"actor_id": "ch_a", "phase": "start", "target": "ch_b의 눈", "target_point_m": [0.8, 0, 1.15], "screen_direction": "right-down", "height_relation": "상대가 낮음"},
          {"actor_id": "ch_a", "phase": "end", "target": "컵", "target_point_m": [-0.5, 0, 0.8], "screen_direction": "down", "height_relation": "눈보다 낮음"}
        ],
        "attention": {
          "entry": {"target": "A의 눈", "frame_xy": [0.55, 0.35]},
          "exit": {"target": "A가 내려다보는 방향의 손", "frame_xy": [0.5, 0.65]}
        }
      },
      "cut_link": {"from_shot_id": null, "relation": "scene-opening", "handoff": "A의 얼굴에서 시선이 손 쪽으로 내려감", "intentional_break": false, "reorientation": "A와 B의 배치는 직전 공간 설정으로 확인"},
      "success_criteria": {"continuity": "A가 B의 눈을 내려다보다 컵 쪽으로 시선을 내린다. 다음 컷의 컵은 내려간 시선 방향에서 읽힌다"}
    }
  ]
}
```

S1-2의 `attention.entry`를 컵의 계획된 위치로 정하고, S1-1의 손/시선 출구에서 그 컵을 찾는 단서를 `cut_link.handoff`에 적는다. S1-3에서는 컵을 내려다보다 A를 올려다보는 사건과 그 높이를 기록한다. 위치를 맞췄다는 이유만으로 연결 합격을 주지 않는다.

| 편집점 | 인물의 시선 | 관객 관심점의 연결 | 상태 / 다음 조치 |
|---|---|---|---|
| S1-1 → S1-2 | A의 눈이 상대→컵으로 내려감 | 내려가는 시선/손→컵 인서트 | 계획 점검. 키 생성 뒤 화면 위치 재확인 |
| S1-2 → S1-3 | B는 컵을 먼저 보고 A의 눈을 올려다봄 | 도착한 컵→B가 알아차리는 얼굴 | 계획 점검. 실제 영상·사용 구간 없으므로 재생 판정은 hold |

`status`는 `planned` 또는 `observed`다. 좌표가 없으면 `null`과 미확정 사유를 남긴다. 시선 연결에 필요한 배치가 미확정이면 해당 키 생성을 보류하고 블록아웃부터 완성한다. 화면 위치는 이미지/영상 전체의 좌상단 (0,0), 우하단 (1,1) 기준이며 계획 추정과 실제 관찰을 혼동하지 않는다. 화면 좌우 방향은 카메라 투영에 따라 달라지므로 월드 좌표의 부호를 그대로 복사하지 않는다.
