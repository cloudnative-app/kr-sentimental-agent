# T1 메트릭 요약 보고서 (C2_t1 최종 시행)

**Run ID:** `experiment_mini4_validation_c2_t1_proposed`  
**실행 시각 (UTC):** 2026-02-10T04:51:35  
**설정:** `experiment_mini4_validation_c2_t1.yaml` · C2 (episodic memory) · debate override 활성 (L3 conservative)

---

## 1. 데이터 규모

| 항목 | 값 |
|------|-----|
| n (평가 샘플 수) | 10 |
| N_gold (gold 튜플 수) | 10 (explicit 3, implicit 7) |
| N_gold_total_pairs | 12 |
| N_pred_final_tuples | 10 |
| gold_available | True |

---

## 2. 결과 메트릭 (RQ)

| 메트릭 | 값 | 비고 |
|--------|-----|------|
| **severe_polarity_error_L3** | 1건 (10.0%) | L3 극성 오류 1건 |
| **polarity_conflict_rate** | 0.0% | raw / after_rep 동일 |
| **tuple_f1_s2** | 0.0000 | tuple_f1_s1·triplet_f1 동일 |
| **delta_f1** | 0.0000 | |
| **stage_mismatch_rate** | 10.0% | 1/10 |
| **rq1_one_hot_sum** | 1.0 | RQ1 관련 집계 |

*tuple_agreement / generalized_f1_theta 등은 이번 설정에서 미집계 (tuple_agreement_eligible=False).*

---

## 3. 검증·리스크

| 메트릭 | 값 |
|--------|-----|
| validator_clear_rate | 100% |
| validator_residual_risk_rate | 0% |
| outcome_residual_risk_rate | 0% |
| risk_resolution_rate | 100% |
| risk_flagged_rate | 50% |
| ignored_proposal_rate | 100% |

---

## 4. 구조·그라운딩

| 메트릭 | 값 |
|--------|-----|
| aspect_hallucination_rate | 90.0% |
| alignment_failure_rate | 90.0% |
| implicit_grounding_rate | 60.0% |
| explicit_grounding_rate | 30.0% |
| explicit_grounding_failure_rate | 10.0% |
| unsupported_polarity_rate | 0.0% |
| legacy_unsupported_polarity_rate | 90.0% |
| unguided_drift_rate | 10.0% |

---

## 5. Debate·Override

| 메트릭 | 값 |
|--------|-----|
| debate_mapping_coverage | 100% |
| debate_mapping_direct_rate | 90% |
| debate_mapping_fallback_rate | 10% |
| **debate_override_applied** | **3** (판단 적용 횟수) |
| debate_override_skipped_low_signal | 25 |
| debate_override_skipped_conflict | 0 |
| **override_applied_n** | **2** (실제 override 적용 샘플 수) |
| override_applied_rate | 20.0% |
| override_success_rate | 0.0% |
| override_applied_unsupported_polarity_rate | 100% (적용된 override 중) |

**Override 사유 분포**

| 사유 | 건수 |
|------|------|
| override_reason_conflict_blocked_n | 7 |
| override_reason_low_signal_n | 3 |
| override_reason_risk_resolved_n | 0 |
| override_reason_debate_action_n | 0 |
| override_reason_grounding_improved_n | 0 |

---

## 6. Override Gate 요약 (override_gate_debug_summary)

| 항목 | 값 |
|------|-----|
| 총 aspect 판단 수 (n_aspects) | 29 |
| 적용(decision_applied_n) | 3 |
| 스킵(decision_skip_n) | 26 |
| neutral_only 스킵 | 18 |
| **스킵 사유** | |
| neutral_only | 18 (62.1%) |
| low_signal | 7 (24.1%) |
| l3_conservative | 1 (3.5%) |
| total_dist | min=0, mean≈0.41, max=1.6 |
| threshold_near_rate (total) | 24.1% (7건이 min_total 근처) |

---

## 7. 메모리·주입

| 메트릭 | 값 |
|--------|-----|
| memory_used_rate | 100% |
| memory_used_changed_rate | 11.1% |
| injection_trigger_alignment_n | 5 |
| injection_trigger_explicit_grounding_failure_n | 4 |
| injection_trigger_conflict_n | 0 |
| injection_trigger_validator_n | 0 |

---

## 8. 요약

- **샘플:** mini4 valid 10건, gold 10튜플(12 pairs).
- **결과:** L3 극성 오류 1건(10%), polarity conflict 0%, tuple F1·delta_f1 0.
- **Override:** 29개 aspect 판단 중 3회 적용, 2건에 실제 override 적용(20%); 적용 건은 unsupported_polarity 100%. 스킵은 대부분 neutral_only(18)와 low_signal(7).
- **안전장치:** conflict blocked 7건으로 보수적 override 동작 확인. validator clear 100%, residual risk 0%.
- **그라운딩:** aspect hallucination·alignment failure 90%, legacy_unsupported_polarity 90%; explicit/implicit grounding률은 위 표와 동일.

이 문서는 `results/experiment_mini4_validation_c2_t1_proposed`의 `derived/metrics/structural_metrics_table.md`, `override_gate_debug_summary.json`, `manifest.json` 기준으로 작성됨.
