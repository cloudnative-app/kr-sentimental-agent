# Drift 원인 분해 (stage1_to_final_changed=1)

unguided_drift가 “메모리 오염”인지, stage_delta 기록/모더레이터 선택 로직에 따른 측정치인지 분해하기 위해, **stage1_to_final_changed=1**인 샘플을 **원인 태그**로 4분할한다.

---

## 0. 메모리 플래그 3종 (retrieved / injected / used)

C3(silent)를 “검색은 하되 주입은 안 함”으로 의미 있게 쓰려면 한 개 플래그로는 부족하므로, 아래처럼 분리한다.

| 플래그 | 정의 | C1 | C2 | C3 |
|--------|------|----|----|-----|
| **memory_retrieved** | 검색 실행/성공 (retrieved_k>0 또는 len(retrieved_ids)>0) | 0 | 1 (대부분) | 1 (대부분) |
| **memory_injected** | 프롬프트에 실제 주입 (exposed_to_debate==True AND prompt_injection_chars>0) | 0 | 1 (게이팅 만족 시) | **0 (항상)** ← silent의 정체성 |
| **memory_used** | 분석/집계용; **memory_injected와 동일** | 0 | 1 when injected | 0 |

- **memory_retrieved** = 1 if (retrieved_k>0 or len(retrieved_ids)>0) else 0.
- **memory_injected** = 1 if (memory.exposed_to_debate==True AND memory.prompt_injection_chars>0) else 0.
- **memory_used** = memory_injected (동일 정의, 집계/표에서 “사용됨” 의미로 사용).

**C3 기대 패턴**: `memory_retrieved=1`, `memory_injected=0`, `memory_used=0`.

- `exposed_to_debate`만 True이고 주입이 0이면 (게이팅 차단) → memory_injected=0, memory_used=0.
- stage2 선택과 독립: 위 플래그는 **메모리 필드만** 기준으로 0/1.

---

## 1. 원인 태그 (4-way)

| 태그 | 설명 |
|------|------|
| **stage2_selected** | Stage2 선택으로 변경 (Moderator selected stage2). 변경은 모더레이터가 stage2를 선택했기 때문. |
| **same_stage_tuples_differ** | 동일 stage 선택인데 tuples 변경. 모더레이터는 stage1(또는 stage2_adopted_but_no_change)인데 pair set이 다름 → 정규화/중복/추출경로 차이. |
| **stage_delta_missing** | stage_delta 미기록 (B-type inconsistency). changed=1인데 stage_delta.changed=False. |
| **(C2 전용)** | 메모리 노출 여부에 따른 변화: C2 run에서 memory_used=1/0별 changed=1 개수는 **drift_cause_summary.md**에서 cross-tab. |

---

## 2. 판정 순서

1. **stage_delta_missing**: `stage1_to_final_changed=1` 이고 `stage_delta.changed` 가 False/0 이면 → B-type.
2. **stage2_selected**: 그 외 `moderator_selected_stage=="stage2"` 이고 `stage2_adopted_but_no_change` 가 아님 → Stage2 선택으로 변경.
3. **same_stage_tuples_differ**: 그 외 (stage1 선택이거나 stage2_adopted_but_no_change) → 동일 stage 선택인데 tuples만 다름.

---

## 3. 산출물

- **Triptych 테이블**: 행마다 `drift_cause_tag`, `stage2_adopted_but_no_change`, **memory_retrieved**, **memory_injected**, **memory_used** 컬럼.
- **derived/diagnostics/drift_cause_breakdown.tsv**: changed=1인 샘플만, text_id, drift_cause_tag, moderator_selected_stage, stage_delta_changed, stage2_adopted_but_no_change, guided_change, unguided_drift, **memory_retrieved**, memory_used, run_id.
- **derived/diagnostics/drift_cause_summary.md**: 태그별 count; **drift_cause_memory_used_changed_n** (injected 기반), **drift_cause_memory_retrieved_changed_n**; C2 run이면 memory_used=1/0별 changed=1 count.

`structural_error_aggregator.py --diagnostics_dir ...` 실행 시 위 TSV/MD가 함께 생성된다.

---

## 4. Triptych 검증 열 (P2)

게이팅 적용 런(c2_2)에서 “주입 차단이 실제로 발생했는지” 샘플 단위 확인용. Triptych에 다음 열이 있음:

- **memory_retrieved**, **memory_injected**, **memory_used** (used = injected)
- **memory_exposed_to_debate**, **memory_injected_chars** (prompt_injection_chars), **memory_retrieved_n** (retrieved_k)
- **moderator_selected_stage**, **stage1_pairs**, **final_pairs** (stage2_pairs는 final과 동일 소스)

검증: `exposed_to_debate=0` 또는 `prompt_injection_chars=0`인 행은 반드시 **memory_injected=0, memory_used=0**. memory_used=1이면 플래그 정의/기록 오류.

---

## 5. Drift 2분할 (P3)

- **drift_any_change**: `stage1_pairs != final_pairs` (기존 stage1_to_final_changed와 동일).
- **drift_conflict_relevant_change**: 바뀐 것 중 **중요한 바뀜**만 — polarity_conflict_raw 또는 stage1_structural_risk 또는 gold fix/break (new_correct_in_final>0 or new_wrong_in_final>0).

메트릭: `drift_any_change_n/rate`, `drift_conflict_relevant_change_n/rate`.

---

## 6. Stage2 선택 시 pairs 변경 분해 (P4)

- **n_stage2_selected**: moderator_selected_stage=stage2인 샘플 수.
- **n_stage2_selected_and_pairs_changed**: stage2 선택이고 stage1_to_final_changed=1인 샘플 수.
- **mean_delta_pairs_count_given_stage2_selected**: stage2 선택인 행만으로 delta_pairs_count 평균.

stage2 수정이 “+positive 추가” 등 특정 패턴인지 유형화하면, 대표 선택/정규화 vs stage2 수정 폭 제한 중 다음 액션 선택에 활용.

---

## 7. C3 실행으로 원인 분리 (P5)

C2만 보면 memory_injected와 stage2 선택이 결합돼 인과 주장이 흔들리므로, **C3(C2_silent)를 반드시 돌려** 원인 분리를 강제한다.

- C3: retrieval 수행, injection_mask=True (주입 0) → **memory_retrieved=1**, **memory_injected=0**, **memory_used=0**.
- C3에서 **stage2_selected가 높으면** → 메모리 주입 때문이 아니라 **stage2 정책** 때문.
- C3에서 **stage2_selected가 낮아지면** → 메모리 주입이 stage2 선택을 자극한다는 방향 해석 가능.

실행: `.\scripts\run_real_n100_c2_c3.ps1` (C2 → C3 순차, run-id c2_2, c3_2) 또는 C3만 `experiment_real_n100_seed1_c3.yaml` 로 20개라도 실행.

---

## 7.1. Drift 원인 집계: used vs retrieved (C3 해석)

표 포맷을 그대로 쓰면 다음처럼 해석할 수 있다.

- **drift_cause_memory_used_changed_n** (injected 기반): changed=1 이면서 memory_injected=1인 샘플 수. **C3에서는 0에 가까워야 정상** (주입 없음).
- **drift_cause_memory_retrieved_changed_n**: changed=1 이면서 memory_retrieved=1인 샘플 수 (주입 여부 무관).  
  **C3에서 이 값이 크면** → “검색(시간/비용)은 드는데, 주입은 안 해도 stage2가 바뀐다/바뀌지 않는다”를 **분리해서** 말할 수 있음 (다음 작업 시행용).

---

## 8. 관련

- B-type inconsistency: `flag_changed_one_delta_zero` (inconsistency_flags.tsv).
- stage_delta SSOT: `docs/stage_delta_ssot_checklist.md`.
- RQ 메트릭: `docs/rq_metrics_field_mapping.md`, guided_change_rate / unguided_drift_rate.
