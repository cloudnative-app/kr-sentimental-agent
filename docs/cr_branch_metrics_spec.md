# CR 브랜치 메트릭 명세

Conflict Review v1 (CR) 프로토콜에서 생성되는 메트릭, 산출 공식, 집계 데이터 플로우를 정리합니다.

---

## 0. Paper Metrics 3-Level 구조 (Paper Metric Realignment Freeze)

| Level | 정의 | Paper Table |
|-------|------|-------------|
| **Level 1: Surface** | OTE–polarity (micro-level ABSA unit). | Table 1 |
| **Level 2: Projection** | entity#attribute–polarity mapping into taxonomy. aspect_ref = entity#attribute. | Table 2 |
| **Level 3: Error Control** | change in error state transition. 3A Error Reduction, 3B Error Detection, 3C Stability. | Table 3A/B/C |

**용어**: aspect_ref → entity#attribute (표기 병기). ref-pol → entity#attribute–polarity. ote-pol → OTE–polarity.

**CDA** = n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed). Gold-based.  
**AAR** = n(majority agreement in review actions) / total_tuples.

---

**변경 이력 (주요)**:
- [CHG] Conflict 정의 ref-level 정렬: polarity_conflict_rate → aspect_ref 기준 그룹핑
- [CHG] Ref 메트릭 stage2 기준 추가: ref_fill_rate_s2, ref_valid_rate_s2, ref_coverage_rate_s2
- [CHG] implicit_invalid 세분화: implicit_coverage_fail_rate, implicit_null_fail_rate, implicit_parse_fail_rate

---

## 1. 데이터 플로우 개요

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  1. 추론 (Conflict Review Runner)                                                │
│     P-NEG / P-IMP / P-LIT → merge candidates → ReviewA/B/C → Arbiter              │
│     → FinalOutputSchema(stage1_tuples, final_tuples, final_tuples_pre_review,     │
│        final_tuples_post_review, analysis_flags.review_actions, arb_actions)     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  2. outputs.jsonl (런 단위)                                                       │
│     각 행: FinalOutputSchema.model_dump()                                         │
│     runtime.parsed_output = entry (scorecard 생성 시 wrap)                        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  3. scorecards.jsonl (런 단위)                                                    │
│     make_scorecard(entry) → run_experiments / scorecard_from_smoke               │
│     - stage_delta: _extract_stage1_tuples, _extract_final_tuples로 pairs 비교    │
│     - CR: change_type = guided_by_review | unguided (review_actions|arb_actions) │
│     - runtime.parsed_output = entry (aggregator 입력용 wrap)                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  4. structural_error_aggregator.py                                                │
│     입력: scorecards.jsonl (+ optional override_gate_debug_summary.json)           │
│     출력: structural_metrics.csv, structural_metrics_table.md                     │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  5. build_metric_report.py → metric_report.html                                  │
│     structural_metrics.csv + scorecards 기반 추가 시각화                          │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. CR 튜플 소스 정의 (SSOT)

| 구분 | 필드 | CR 의미 | aggregator 추출 |
|------|------|---------|-----------------|
| **stage1** | `final_result.stage1_tuples` | pre_review (P-NEG/P-IMP/P-LIT merge 후 candidates) | `_extract_stage1_tuples` |
| **final** | `final_result.final_tuples` | post_review (Arbiter 적용 후 final_candidates) | `_extract_final_tuples` |
| **pre_review** | `final_result.final_tuples_pre_review` | stage1_tuples와 동일 | (참조용) |
| **post_review** | `final_result.final_tuples_post_review` | final_tuples와 동일 | (참조용) |

- **추출 우선순위**: `final_result.stage1_tuples` → process_trace Stage1 ATSA → final_tuples fallback  
- **추출 우선순위**: `final_result.final_tuples` → final_aspects → inputs.aspect_sentiments (fallback)

---

## 3. Outcome 메트릭 (RQ)

### 3.1 Tuple F1 계열 (ref-pol, CR v2 주평가)

| 메트릭 | 공식 | 소스 |
|--------|------|------|
| **tuple_f1_s1** / **tuple_f1_s1_refpol** | `mean(F1(gold, stage1_tuples))` | pre_review vs gold |
| **tuple_f1_s2** / **tuple_f1_s2_refpol** | `mean(F1(gold, final_tuples))` | post_review vs gold |
| **delta_f1** / **delta_f1_refpol** | `tuple_f1_s2 - tuple_f1_s1` | S2−S1 개선량 |
| **triplet_f1_s1 / triplet_f1_s2** | tuple_f1과 동일 | 호환용 별칭 |

**F1 산출**: `metrics.eval_tuple.precision_recall_f1_tuple(gold, pred, match_by_aspect_ref=True)`  
- **매칭 단위**: (aspect_ref, polarity) 쌍 — ref-pol (CR v2 주평가)  
- **tuples_to_ref_pairs**: aspect_ref가 비어 있으면 제외  
- 정규화: `normalize_for_eval`, `normalize_polarity`  
- 상세: `docs/evaluation_cr_v2.md`, `docs/data_flow_tuple_triplet_pair_definitions.md`

### 3.2 Tuple F1 세분화

| 메트릭 | 공식 | 용도 |
|--------|------|------|
| **tuple_f1_s2_explicit_only** | explicit gold만 사용한 F1 (ref-pol) | primary quality metric |
| **tuple_f1_s2_implicit_only** | implicit gold만 사용한 F1 | 참고용 |
| **tuple_f1_s2_overall** | 전체 gold 기준 F1 | 참고용 |
| **tuple_f1_s2_raw** | 대표 선택 전 F1 | 참고용 |
| **tuple_f1_s2_after_rep** | 대표 선택 후 F1 | 참고용 |
| **tuple_f1_explicit** | explicit-only (aspect_term, polarity) F1 | Appendix, Grounding 진단 |

### 3.2.1 비교 골드 vs Pre튜플 정리

| 구분 | 정의 | 소스 |
|------|------|------|
| **비교 골드** | | |
| gold (전체) | `inputs.gold_tuples` 정규화 | `_extract_gold_tuples` |
| gold_explicit | aspect_term non-empty 튜플만 | `_split_gold_explicit_implicit` |
| gold_implicit | aspect_term empty 튜플만 | `_split_gold_explicit_implicit` |
| gold_implicit_polarities | implicit gold의 polarity 리스트 | `gold_implicit_polarities_from_tuples` |
| **Pre튜플 (Pred)** | | |
| stage1_tuples | pre-review (P-NEG/P-IMP/P-LIT merge 후) | `final_result.stage1_tuples` |
| final_tuples | post-review (Arbiter 적용 후) | `final_result.final_tuples` |
| final_tuples (raw) | 대표 선택 전 | 동일 |
| final_tuples (after_rep) | 대표 선택 후 | `select_representative_tuples` |
| pred_explicit_only | aspect_term non-empty 튜플만 | `_pred_explicit_only` |
| pred_valid_polarities | polarity ∈ {pos, neg, neu}만 | `pred_valid_polarities_from_tuples` |

**메트릭별 비교 조합**

| 메트릭 | 비교 골드 | Pre튜플 | Pair 단위 |
|--------|-----------|---------|-----------|
| tuple_f1_s1 | gold | stage1_tuples | (aspect_ref, polarity) |
| tuple_f1_s2 | gold | final_tuples | (aspect_ref, polarity) |
| tuple_f1_s2_explicit_only | gold_explicit | final_tuples | (aspect_ref, polarity) |
| tuple_f1_s2_implicit_only | gold_implicit_polarities | pred_valid_polarities | polarity만 |
| tuple_f1_s2_overall | gold | final_tuples | (aspect_ref, polarity) |
| tuple_f1_s2_raw | gold | final_tuples (raw) | (aspect_ref, polarity) |
| tuple_f1_s2_after_rep | gold | final_tuples (after_rep) | (aspect_ref, polarity) |
| tuple_f1_explicit | gold_explicit | pred_explicit_only | (aspect_term, polarity) |

### 3.3 교정률 (fix / break / net_gain)

| 메트릭 | 공식 |
|--------|------|
| **fix_rate** | `n_fix / (n_fix + n_still)` — S1×gold 불일치 → S2 일치 |
| **break_rate** | `n_break / (n_break + n_keep)` — S1×gold 일치 → S2 불일치 |
| **net_gain** | `(n_fix - n_break) / N` |

- `tuple_sets_match_with_empty_rule(gold, s1/s2)` 기준으로 일치 여부 판단

### 3.4 Polarity Conflict

| 메트릭 | 공식 | 정의 |
|--------|------|------|
| **polarity_conflict_rate_raw** | `n(동일 aspect_term에 ≥2 극성) / N` | 대표 선택 없음 |
| **polarity_conflict_rate** | `n(대표 선택 후에도 상충 극성) / N` | has_polarity_conflict_after_representative |
| **polarity_conflict_rate_after_rep** | polarity_conflict_rate와 동일 | 별칭 |

**대표 선택**: explicit > implicit, confidence, drop_reason 없음 순으로 1개 선택 후, 동일 aspect에 ≥2 극성 남으면 conflict

### 3.5 Implicit 관련

| 메트릭 | 공식 |
|--------|------|
| **implicit_invalid_sample_n** | implicit gold 샘플 중, pred_valid_polars=0 또는 parse_fail 또는 forbidden_neutral_fallback |
| **implicit_invalid_pred_rate** | `implicit_invalid_sample_n / implicit_gold_sample_n` |
| **implicit_coverage_fail_rate** | [CHG] `n(len(pred_valid_pols)==0) / implicit_gold_sample_n` |
| **implicit_null_fail_rate** | [CHG] `n(forbidden_neutral_fallback) / implicit_gold_sample_n` |
| **implicit_parse_fail_rate** | [CHG] `n(parse_fail) / implicit_gold_sample_n` |

**[CHG] implicit_invalid 세분화**: coverage_fail / null_fail / parse_fail 분리. implicit_invalid_pred_rate ≈ coverage + null + parse (합, 중복 포함 가능).

### 3.6 Grounding 진단 (Appendix)

| 메트릭 | 공식 | 용도 |
|--------|------|------|
| **invalid_ref_rate** | `invalid_ref_count_total / total_stage1_triplets` | taxonomy 미준수 비율 |
| **invalid_language_rate** | `invalid_language_count_total / total_stage1_triplets` | aspect_term 영어 포함 비율 |
| **invalid_target_rate** | `invalid_target_count_total / total_stage1_triplets` | opinion→aspect 오염 비율 |

- candidate 단계 검증: `invalid_ref_flag`, `invalid_language_flag`, `invalid_target_flag` — `metrics.opinion_validation`, `agents.conflict_review_runner`

### 3.7 Ref Validity (Construct) — [CHG] stage2 기준 추가

| 메트릭 | 공식 | 기준 |
|--------|------|------|
| **ref_fill_rate** | `n_pred_with_ref / n_pred_total_ref` | stage1 (기존) |
| **ref_valid_rate** | `n_pred_valid_ref / n_pred_with_ref` | stage1 (기존) |
| **ref_coverage_rate** | `gold_refs_covered / gold_refs_total` | stage1 (기존) |
| **ref_fill_rate_s2** | [CHG] `n_pred_with_ref_s2 / n_pred_total_ref_s2` | **stage2** (final_tuples) |
| **ref_valid_rate_s2** | [CHG] `n_pred_valid_ref_s2 / n_pred_with_ref_s2` | **stage2** |
| **ref_coverage_rate_s2** | [CHG] `gold_refs_covered_s2 / gold_refs_total` | **stage2** |

---

## 4. Process 메트릭 (CR 전용)

### 4.1 Pre/Post 변경

| 메트릭 | 공식 | 소스 |
|--------|------|------|
| **pre_to_post_change_rate** | `n(changed) / N` | stage_delta.changed |
| **changed_samples_rate** | 동일 | 동일 |
| **changed_and_improved_rate** | `n(changed ∧ delta_f1>0) / N` | |
| **changed_and_degraded_rate** | `n(changed ∧ delta_f1<0) / N` | |

**stage_delta.changed** (SSOT):  
`(s1_pairs != final_pairs) or (stage1_label != final_label)`  
- `s1_pairs, _ = tuples_to_ref_pairs(_extract_stage1_tuples(record))` (CR v2 ref-pol)
- `final_pairs, _ = tuples_to_ref_pairs(_extract_final_tuples(record))`  
- scorecard_from_smoke와 aggregator가 동일 함수 사용

### 4.2 Review / Arbiter 개입

| 메트릭 | 공식 | 소스 |
|--------|------|------|
| **review_action_rate** | `n(review_actions ≥ 1) / N` | analysis_flags.review_actions |
| **arb_intervention_rate** | `n(arb_actions ≥ 1) / N` | analysis_flags.arb_actions |
| **guided_by_review_rate** | `n(change_type=guided_by_review) / all_changes` | stage_delta.change_type |

**CR change_type 규칙** (scorecard_from_smoke):  
- `changed` and (review_actions or arb_actions) 존재 → `guided_by_review`  
- 그 외 changed → `unguided`

### 4.3 Validator / Risk (CR에서 validator 없음)

| 메트릭 | 공식 | CR 특성 |
|--------|------|---------|
| **validator_clear_rate** | `n(S1 risk ∧ ¬S2 risk) / n(S1 risk)` | validator 없음 → 0 |
| **risk_resolution_rate** | validator_clear_rate 별칭 | 동일 |
| **validator_residual_risk_rate** | `n(S2 risk > 0) / N` | 0 |
| **outcome_residual_risk_rate** | 최종 출력 구조적 리스크 1건 이상 / N | - |
| **negation_contrast_failure_rate** | `n(NEGATION/CONTRAST risk) / N` | validator 없음 → 0 |

---

## 5. N_pred 소스 카운트

| 메트릭 | 의미 |
|--------|------|
| **N_pred_final_tuples** | final_result.final_tuples 사용 행 수 |
| **N_pred_final_aspects** | final_aspects fallback 사용 행 수 |
| **N_pred_inputs_aspect_sentiments** | inputs.aspect_sentiments fallback 사용 행 수 |
| **N_pred_used** | F1 계산에 사용된 pred tuple 총 개수 |
| **N_agg_fallback_used** | final_tuples 비어있어 fallback 사용한 행 수 |

---

## 6. Override Gate (CR에서 비활성화)

CR 설정: `enable_debate: false`, `enable_debate_override: false`  
→ override_gate_debug.jsonl, override_gate_debug_summary.json 미생성  
→ aggregator는 override_gate_summary=None으로 처리, override_* 메트릭 N/A 또는 0

---

## 7. IRR (Inter-Rater Reliability)

| 구분 | unit | label | raters | 의미 |
|------|------|-------|--------|------|
| **Process IRR** | tuple_id | KEEP/DROP/FLIP_*/MERGE/OTHER | Review A/B/C | 교정행위 전략 합의도 |
| **Measurement IRR** | tuple_id | POS/NEG/NEU/DROP | Review A/B/C | 교정 이후 측정값(polarity) 합의도 |

- **산출**: `scripts/compute_irr.py` → `irr/irr_run_summary.json`
- **Measurement 매핑**: KEEP→원 polarity, FLIP_POS→POS, FLIP_NEG→NEG, DROP→DROP, **MERGE/OTHER→DROP**
- **Paper export**: Table 2A (Process), Table 2B (Measurement) — `export_paper_metrics_aggregated.py`
- 상세: `docs/evaluation_cr_v2.md`

---

## 8. 산출물 경로

| 단계 | 경로 | 설명 |
|------|------|------|
| 추론 | `results/<run_id>__seed<N>_proposed/outputs.jsonl` | FinalOutputSchema |
| scorecard | `results/<run_id>__seed<N>_proposed/scorecards.jsonl` | make_scorecard 출력 |
| 메트릭 | `results/<run_id>__seed<N>_proposed/derived/metrics/structural_metrics.csv` | aggregator 출력 |
| 메트릭 MD | `.../derived/metrics/structural_metrics_table.md` | 동일 |
| IRR | `.../irr/irr_sample_level.csv`, `irr_run_summary.json` | Process + Measurement IRR |
| 리포트 | `reports/<run_id>__seed<N>_proposed/metric_report.html` | build_metric_report |
| 집계 | `results/<run_id>_aggregated/aggregated_mean_std.csv` | aggregate_seed_metrics |
| Paper | `results/<run_id>_paper/paper_metrics_aggregated.md` | export_paper_metrics_aggregated |

---

## 9. 참고 문서

- `docs/evaluation_cr_v2.md` — CR v2 평가 정의 (ref-pol, IRR, ΔF1 해석)
- `docs/data_flow_tuple_triplet_pair_definitions.md` — GoldUnit/SurfaceUnit/EvalTuple 정의
- `docs/protocol_conflict_review_vs_legacy_comparison.md` — CR vs Legacy 메트릭 정합성
- `docs/stage_delta_ssot_checklist.md` — stage_delta SSOT 및 pairs 기반 changed
- `docs/schema_scorecard_trace.md` — scorecard 스키마
- `scripts/structural_error_aggregator.py` — 집계 구현 (docstring 포함)
