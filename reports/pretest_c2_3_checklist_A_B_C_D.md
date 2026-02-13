# Pretest C2_3 결과 체크리스트 (A–D, A2, Override unsupported)

**Run**: `pretest_c2_3__seed1_proposed` (n=50, C2, override T1)  
**검증 산출물**: `reports/pipeline_integrity_verification_pretest_c2_3.json`, `results/.../derived/metrics/structural_metrics_table.md`, `override_gate_debug_summary.json`

---

## A. 메모리 접근 제어

| 항목 | 결과 | 비고 |
|------|------|------|
| **A1** EPM/TAN prompt에 DEBATE_CONTEXT__MEMORY 완전히 없음 | ✅ 추정 충족 | 검증 스크립트는 scorecard 메타만 검사. trace 상 EPM/TAN에는 메모리 미주입 정책(cj_only)과 일치. |
| **A2** 메타 전달 수정 확인 (memory_debate_slot_present_for, cj_only) | ❌ **실패** | `debate_persona_memory.pass: false`, violations 50건. |
| **A3** Stage2 리뷰 컨텍스트에 STAGE2_REVIEW_CONTEXT__MEMORY 존재 | ✅ **통과** | `stage2_memory_injection.pass: true`, violations 0. |

### A2 상세 (c2_2에서 잡히지 않았던 검증)

- **검증 조건**: `exposed_to_debate` 이고 `prompt_injection_chars > 0` 인 샘플에서 `memory_debate_slot_present_for == ["cj"]`, `memory_access_policy.debate == "cj_only"` 기대.
- **현상**: 모든 50건에서 `memory_debate_slot_present_for: null`, `memory_access_policy.debate: null` 로 기록됨.
- **원인**: 검증 스크립트는 **scorecard의 `meta.memory` 또는 top-level `memory`** 를 참조하는데, 실제 값은 **`parsed_output.meta.memory`** (runtime) 안에만 있음.  
  - 샘플 scorecard에서 `parsed_output.meta.memory` 에는 `memory_debate_slot_present_for: ["cj"]`, `memory_access_policy: { debate: "cj_only" }` 가 존재함.
- **결론**: **메타 전달 수정 미적용**. 파이프라인에서 scorecard/메타를 쓸 때 `meta.memory`(또는 검증이 보는 경로)에 `memory_debate_slot_present_for`, `memory_access_policy` 를 복사해야 A2 검증 통과.

### A2 수정 적용 (scripts/scorecard_from_smoke.py · make_scorecard)

- **적용 위치**: `make_scorecard()` — **run_experiments.py**와 **scorecard_from_smoke.py** 모두 이 함수를 호출하므로, 실험 런과 스모크 재생성 시 동일하게 적용됨.
- **구조**: `mem = meta_in.get("memory") or {}` (이미 있으면 그대로 재사용) → `scorecard["memory"]`에 A2 필드 2개 포함해 메모리 블록 구성 → `scorecard["meta"]["memory"] = dict(scorecard["memory"])` 로 **(a) row["memory"] (b) row["meta"]["memory"]** 둘 다 동일 블록 반영.
- **재런 없이 A2 검증**: 같은 outputs로 scorecard만 재생성 후 검증만 재실행.
  ```bash
  python scripts/scorecard_from_smoke.py --smoke results/pretest_c2_3__seed1_proposed/outputs.jsonl --out results/pretest_c2_3__seed1_proposed/scorecards.jsonl
  python scripts/pipeline_integrity_verification.py --run_dir results/pretest_c2_3__seed1_proposed --out reports/pipeline_integrity_verification_pretest_c2_3.json
  ```
  → `debate_persona_memory.pass: true` 확인.

---

## B. 조건 의미 유지

| 항목 | 결과 | 비고 |
|------|------|------|
| C2_silent / C2_eval_only | N/A | 본 런은 **C2 단일 조건**. C2_silent·C2_eval_only 미사용. |
| C2: retrieval_executed + prompt 노출 | ✅ | memory_samples 상 retrieval·exposed·prompt_injection_chars 등 정상. |

---

## C. 저장 정책

| 항목 | 결과 | 비고 |
|------|------|------|
| store_write=True인데 stored/skipped 혼합 | ✅ **통과** | `selective_storage_mix.pass: true`, stored=7, skipped=43. |

---

## D. 메트릭 무결성

| 항목 | 결과 | 비고 |
|------|------|------|
| tuple_f1_s1 / s2 NaN·0 고정·폭주 없음 | ✅ | tuple_f1_s1=0.4013, tuple_f1_s2=0.4993. |
| implicit_invalid_pred_rate 계산 정상 | ✅ | 0.0417 (implicit_gold_sample_n=24, implicit_invalid_sample_n=1). |
| delta_f1 의미 있는 값 | ✅ | delta_f1=0.0980, fix_rate=0.075, break_rate=0.100, net_gain=0.04. |

---

## Override 관련 ("unsupported 1.0" 원인 및 현황)

### 요약

- **Override**: ON (T1 프로파일). `override_applied_n=5`, `override_applied_rate=0.10`.
- **override_applied_unsupported_polarity_rate**: **0.80** (c2_2의 1.0에서 개선, but 아직 80%).
- **원인**: `override_applied_unsupported_polarity_rate` 는 **override가 적용된 샘플** 중 `has_unsupported_polarity(record)==True` 인 비율.  
  `has_unsupported_polarity` 는 RQ1 그라운딩 기준(최종 tuple aspect에 대한 judgement 실패 등)으로 “unsupported” 판정.  
  즉, **polarity 오타/캐노니컬 문제가 아니라**, override를 탄 샘플들이 **evidence/grounding 관점에서 unsupported로 분류**되고 있음.
- **관련 지표**:
  - override_applied_and_adopted_rate: 0.08 (4/50)
  - override_reason_ev_below_threshold_n: 5 (EV 부족으로 미채택)
  - override_hint_invalid_total: 4, override_hint_invalid_rate: 0.1538 (힌트 polarity invalid는 별도 집계)
- **Override OFF**: 사용하지 않음. OFF로 두면 override_applied_n=0, unsupported rate 산출 불가.

### 결론 (Override)

- **Unsupported 1.0 → 0.8**: polarity canonicalization 및 invalid hint 제거로 **일부 개선**되었으나, **0.8은 RQ1 “unsupported polarity” 정의**(그라운딩/evidence 실패)에 따른 것.
- **0.0으로 만들려면**: override가 적용된 샘플에 대해 (1) opinion_grounded/evidence 판정이 통과하거나, (2) unsupported 정의를 조정(또는 override 적용 구간만 다른 메트릭으로 분리)해야 함.  
  현재 구조에서는 **override ON 유지**, unsupported는 “override 적용 구간의 RQ1 unsupported 비율”로 해석하는 것이 타당.

---

## 종합

| 구분 | 결과 |
|------|------|
| **A** | A1/A3 통과. **A2 실패** (메타 전달 미적용: scorecard meta.memory에 memory_debate_slot_present_for·memory_access_policy 미전달). |
| **B** | N/A (C2 단일). |
| **C** | 통과 (stored/skipped 혼합). |
| **D** | 통과 (tuple_f1, delta_f1, implicit_invalid_pred_rate 정상). |
| **Override unsupported** | 1.0 → 0.8로 개선. 원인: RQ1 unsupported(그라운딩) 비율. Override OFF 아님. |

### 권장

1. **A2**: scorecard 작성 시 `parsed_output.meta.memory` 의 `memory_debate_slot_present_for`, `memory_access_policy` 를 scorecard의 `meta.memory`(또는 검증 스크립트가 읽는 경로)에 복사하는 메타 전달 수정 적용.
2. **Override**: T1 유지. unsupported 0.8은 “override 적용 샘플 내 RQ1 unsupported 비율”로 기록하고, 필요 시 override_applied 구간만 별도 분석.
