# 시드별 집계 통합 보고서 — experiment_real_n100_seed1_c1_1

- **시드 런 수**: 2
- **머지 scorecards**: `merged_scorecards.jsonl` (200 rows)
- **Episodic memory**: C1 (off)

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| experiment_real_n100_seed1_c1_1__seed1_proposed | `results\experiment_real_n100_seed1_c1_1__seed1_proposed` | `results\experiment_real_n100_seed1_c1_1__seed1_proposed/derived/metrics/structural_metrics.csv` |
| experiment_real_n100_seed1_c2_1__seed1_proposed | `results\experiment_real_n100_seed1_c2_1__seed1_proposed` | `results\experiment_real_n100_seed1_c2_1__seed1_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_gold | N_gold_explicit | N_gold_explicit_pairs | N_gold_implicit | N_gold_implicit_pairs | N_gold_total | N_gold_total_pairs | N_pred_final_aspects | N_pred_final_tuples | N_pred_inputs_aspect_sentiments | N_pred_used | alignment_failure_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| experiment_real_n100_seed1_c1_1__seed1_proposed | 100 | 0 |  | 0 |  | 100 |  | 0 | 0 | 0 | 0 | 0.75 |
| experiment_real_n100_seed1_c2_1__seed1_proposed | 100 | 0 |  | 0 |  | 100 |  | 0 | 0 | 0 | 0 | 0.75 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `real_n100_c1_1_c2_1_merged/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_gold | 100.0000 | 0.0000 |
| N_gold_explicit | 0.0000 | 0.0000 |
| N_gold_implicit | 0.0000 | 0.0000 |
| N_gold_total | 100.0000 | 0.0000 |
| N_pred_final_aspects | 0.0000 | 0.0000 |
| N_pred_final_tuples | 0.0000 | 0.0000 |
| N_pred_inputs_aspect_sentiments | 0.0000 | 0.0000 |
| N_pred_used | 0.0000 | 0.0000 |
| alignment_failure_rate | 0.7500 | 0.0000 |
| aspect_hallucination_rate | 0.7500 | 0.0000 |
| break_rate | N/A | N/A |
| debate_fail_fallback_used_rate | 0.0150 | 0.0033 |
| debate_fail_neutral_stance_rate | 0.0083 | 0.0017 |
| debate_fail_no_aspects_rate | 0.0450 | 0.0050 |
| debate_fail_no_match_rate | 0.0000 | 0.0000 |
| ... | (76 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `real_n100_c1_1_c2_1_merged/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 200 |
| profile_filter |  |
| eval_semver | 1.0 |
| eval_policy_hash | a64a7ec38e040a34 |
| severe_polarity_error_L3_count | 0 |
| severe_polarity_error_L3_rate |  |
| polarity_conflict_rate_raw | 0.86 |
| polarity_conflict_rate | 0.86 |
| polarity_conflict_rate_after_rep | 0.86 |
| generalized_f1_theta |  |
| generalized_precision_theta |  |
| generalized_recall_theta |  |
| tuple_agreement_rate | 0.43 |
| tuple_agreement_eligible | True |
| tuple_f1_s1 |  |

## 5. 메트릭 리포트 (HTML)

- 머지 런: `reports/merged_run_experiment_real_n100_seed1_c1_1/metric_report.html` (아래 스크립트로 생성됨)
- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
