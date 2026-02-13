# Memory policy v1.2 — OPFB 및 조건 정의

목표: drift/충돌을 줄이면서 **advisory-only** 원칙을 유지하고, 논문 방어 가능한 ablation 1개를 추가한다.

---

## 1. OPFB 규칙 (한 줄)

**동일 aspect_term_norm에 대해 “해당 polarity로 갔다가 실패/리스크 악화” 기록이 retrieved episode에 있으면, 그 polarity로 바꾸는 조언을 생성하지 않거나 BLOCKED로 태깅한다.**

---

## 2. 조건 정의 (C1 / C2 / C3 / C2_eval_only)

| 조건 | retrieval_execute | injection_mask | store_write | 설명 |
|------|------------------|----------------|-------------|------|
| **C1** | false | true | false | 메모리 OFF. 슬롯 비움. |
| **C2** | true | false | true | Retrieval + debate에 advisory 주입 + 저장. |
| **C3** (C2_silent) | true | true | true | Retrieval만 수행, 주입 마스킹(비용/지연 유지). 저장함. |
| **C2_eval_only** | true | true | false (권장) | C3와 동일하게 주입 마스킹. 평가 전용(저장 안 함 권장, 로그 오염 감소). |

- **retrieval_execute**: store load + retriever 실행 여부  
- **injection_mask**: true면 slot의 retrieved를 비워 debate에 주입하지 않음  
- **store_write**: 샘플 끝 에피소드 append 여부  
- **C2_eval_only**: 이미 있는 C3(silent)와 거의 동일하게 두고, 이름/목적만 분리(평가 전용 ablation).

---

## 3. “메모리는 결정을 강제하지 않는다” 유지

메모리는 **의사결정을 강제하지 않는다**. OPFB는 “위험한 조언을 프롬프트에 올리지 않거나 BLOCKED로 태깅”하는 수준이며, 최종 선택은 모더레이터/파이프라인에 둔다.

---

## 4. 관련 구현·설정

| 항목 | 위치 |
|------|------|
| 조건 플래그 (v1.2) | `experiments/configs/conditions_memory_v1_2.yaml` |
| OPFB (위험 조언 필터링/블록) | `memory/advisory_builder.py` |
| Scorecard/Triptych 로그 | `memory_blocked_episode_n`, `memory_blocked_advisory_n`, `memory_block_reason` |
