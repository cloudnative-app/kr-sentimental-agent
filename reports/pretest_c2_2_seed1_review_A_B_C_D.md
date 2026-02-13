# pretest_c2_2__seed1_proposed 검토 보고서 (A–D)

**Run dir**: `results/pretest_c2_2__seed1_proposed`  
**검증 산출**: `reports/pipeline_integrity_verification_pretest_c2_2.json`, `derived/metrics/structural_metrics_table.md`

---

## A. 메모리 접근 제어

### A1. EPM / TAN prompt에 DEBATE_CONTEXT__MEMORY 완전히 없음

- **검증 방법**: trace에는 프롬프트 원문이 저장되지 않음. 토큰 수로 간접 추론.
- **결과**: EPM prompt_len≈891, TAN≈934, CJ≈1404 (동일 샘플 기준). CJ만 토큰이 크게 많음 → 메모리 블록은 CJ 쪽에만 주입된 것으로 추정 가능.
- **한계**: 프롬프트 텍스트에 `DEBATE_CONTEXT__MEMORY` 문자열 부재는 trace만으로는 확인 불가. 코드상으로는 debate 시 EPM/TAN에는 메모리 슬롯을 넣지 않고 CJ에만 넣는 정책(cj_only)으로 구현되어 있음.

### A2. CJ prompt에만 존재 (gate 통과 샘플)

- **pipeline_integrity_verification**: `debate_persona_memory.pass` = **false**. 37건 violation (memory_debate_slot_present_for / memory_access_policy.debate가 **null**).
- **원인**: 검증 스크립트는 `row.meta.memory`를 참조하는데, scorecard에 기록되는 **top-level meta.memory**에는 `memory_debate_slot_present_for`, `memory_access_policy`가 **포함되지 않음**.
- **실제 데이터**: scorecard의 **parsed_output.meta.memory**에는 해당 필드가 있음.  
  예: 첫 번째 샘플(nikluge-sa-2022-train-02669)에서  
  `memory_debate_slot_present_for: ["cj"]`, `memory_access_policy: {"debate": "cj_only"}`.
- **결론**: 정책상 CJ-only는 **구현·데이터 상 만족**하나, 검증 스크립트가 참조하는 **meta.memory**가 불완전해 자동 검증은 실패로 나옴.  
  → scorecard 작성 시 `parsed_output.meta.memory`를 그대로 `row.meta.memory`에 넣거나, 검증 시 `parsed_output.meta.memory`를 우선 사용하도록 수정 권장.

### A3. Stage2 리뷰 컨텍스트에 STAGE2_REVIEW_CONTEXT__MEMORY 존재 여부

- **pipeline_integrity_verification**: `stage2_memory_injection.pass` = **true**, violations = [].
- **결과**: stage2_memory_injected=True인 샘플에서 리뷰 컨텍스트에 `STAGE2_REVIEW_CONTEXT__MEMORY` 키가 존재함.
- **추가 확인**: scorecard `debate_review_context` 안에 `STAGE2_REVIEW_CONTEXT__MEMORY` (schema_version, memory_on, retrieved, meta 등) 포함됨.

**A 종합**:  
- A1: 코드/토큰 수 기준 추정 충족, trace만으로는 문구 수준 검증 불가.  
- A2: 동작은 CJ-only이나, 검증은 meta 직렬화 불일치로 실패.  
- A3: **통과.**

---

## B. 조건 의미 유지

- **대상**: B는 **C2_silent / C2_eval_only** 조건에 대한 항목(retrieval_executed=True·프롬프트 노출 없음, eval_only는 store_write=False).
- **이번 런**: pretest_c2_2는 **일반 C2** (store_write=True, retrieval + gate에 따라 debate/CJ·Stage2에 메모리 노출).
- **결론**: **B는 이 런에 해당 없음 (N/A).** C2_silent / C2_eval_only 전용 런으로 동일 체크 필요.

---

## C. 저장 정책

- **기대**: store_write=True인데 **stored / skipped가 섞여 나와야 함**. 전부 저장 or 전부 스킵이면 실패.
- **pipeline_integrity_verification**: `selective_storage_mix.pass` = **true**.  
  `store_decision_counts`: **skipped=40, stored=10**.
- **결론**: **통과.** stored와 skipped가 혼재되어 있음.

---

## D. 메트릭 무결성

### D1. tuple_f1_s1 / s2 값 NaN, 0 고정, 폭주 없음

- **structural_metrics_table.md**:
  - tuple_f1_s1: **0.4313**
  - tuple_f1_s2: **0.5440**
  - tuple_f1_s2_explicit_only: 0.4790, tuple_f1_s2_implicit_only: 0.7778
- **결과**: NaN 없음, 0으로만 고정된 값 없음, 비이상적 폭주 없음. **통과.**

### D2. implicit_invalid_pred_rate 계산 정상

- implicit_gold_sample_n: **24**
- implicit_invalid_sample_n: **1**
- implicit_invalid_pred_rate: **0.0417** (= 1/24).
- **결과**: 비율 계산 정상. **통과.**

### D3. delta_f1가 의미 없는 상수로 수렴하지 않음

- delta_f1: **0.1127** (tuple_f1_s2 − tuple_f1_s1).
- fix_rate 0.1250, break_rate 0.1000, net_gain 0.0800 등과 조합해 Stage2 효과가 있는 값.
- **결과**: **통과.**

**D 종합**: **모두 통과.**

---

## 요약 표

| 항목 | 결과 | 비고 |
|------|------|------|
| A1 EPM/TAN에 MEMORY 없음 | △ 추정 충족 | trace만으로 문구 검증 불가 |
| A2 CJ에만 (gate 통과 시) | △ 구현 충족, 검증 실패 | meta.memory 직렬화 불일치 |
| A3 Stage2에 STAGE2_REVIEW_CONTEXT__MEMORY | ✅ 통과 | |
| B C2_silent / C2_eval_only | N/A | 이 런은 C2 |
| C stored/skipped 혼재 | ✅ 통과 | skipped=40, stored=10 |
| D1 tuple_f1_s1/s2 무결성 | ✅ 통과 | |
| D2 implicit_invalid_pred_rate | ✅ 통과 | |
| D3 delta_f1 의미 있음 | ✅ 통과 | |

---

## 권장 조치

1. **A2**: scorecard를 쓸 때 `parsed_output.meta.memory` 전체를 `row.meta.memory`에 반영하거나, pipeline_integrity_verification에서 `row.runtime.parsed_output.meta.memory`(또는 동일 소스)를 우선 사용하도록 변경하여 debate_persona_memory 검증이 통과하도록 할 것.
2. **B**: C2_silent / C2_eval_only 전용 런으로 retrieval_executed·프롬프트 노출·store_write 여부를 동일 방식으로 검토할 것.
