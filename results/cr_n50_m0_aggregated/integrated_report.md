# 시드별 집계 통합 보고서 — cr_n50_m0

- **시드 런 수**: 3
- **머지 scorecards**: `merged_scorecards.jsonl` (150 rows)
- **Episodic memory**: M0

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| cr_n50_m0__seed42_proposed | `results\cr_n50_m0__seed42_proposed` | `results\cr_n50_m0__seed42_proposed/derived/metrics/structural_metrics.csv` |
| cr_n50_m0__seed123_proposed | `results\cr_n50_m0__seed123_proposed` | `results\cr_n50_m0__seed123_proposed/derived/metrics/structural_metrics.csv` |
| cr_n50_m0__seed456_proposed | `results\cr_n50_m0__seed456_proposed` | `results\cr_n50_m0__seed456_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_agg_fallback_used | N_gold | N_gold_explicit | N_gold_explicit_pairs | N_gold_implicit | N_gold_implicit_pairs | N_gold_total | N_gold_total_pairs | N_pred_final_aspects | N_pred_final_tuples | N_pred_inputs_aspect_sentiments | N_pred_used |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cr_n50_m0__seed42_proposed | 0 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 50 | 0 | 142 |
| cr_n50_m0__seed123_proposed | 0 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 50 | 0 | 148 |
| cr_n50_m0__seed456_proposed | 0 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 50 | 0 | 141 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `cr_n50_m0_aggregated/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_agg_fallback_used | 0.0000 | 0.0000 |
| N_gold | 50.0000 | 0.0000 |
| N_gold_explicit | 27.0000 | 0.0000 |
| N_gold_explicit_pairs | 29.0000 | 0.0000 |
| N_gold_implicit | 25.0000 | 0.0000 |
| N_gold_implicit_pairs | 25.0000 | 0.0000 |
| N_gold_total | 50.0000 | 0.0000 |
| N_gold_total_pairs | 54.0000 | 0.0000 |
| N_pred_final_aspects | 0.0000 | 0.0000 |
| N_pred_final_tuples | 50.0000 | 0.0000 |
| N_pred_inputs_aspect_sentiments | 0.0000 | 0.0000 |
| N_pred_used | 143.6667 | 3.0912 |
| alignment_failure_rate | 0.6200 | 0.0163 |
| arb_intervention_rate | 1.0000 | 0.0000 |
| aspect_hallucination_rate | 0.6200 | 0.0163 |
| ... | (120 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `cr_n50_m0_aggregated/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 150 |
| profile_filter |  |
| eval_semver | 1.0 |
| eval_policy_hash | a64a7ec38e040a34 |
| severe_polarity_error_L3_count | 0 |
| severe_polarity_error_L3_rate | 0.0 |
| polarity_conflict_rate_raw | 0.0 |
| polarity_conflict_rate | 0.0 |
| polarity_conflict_rate_after_rep | 0.0 |
| generalized_f1_theta |  |
| generalized_precision_theta |  |
| generalized_recall_theta |  |
| tuple_agreement_rate | 0.18 |
| tuple_agreement_eligible | True |
| tuple_f1_s1 | 0.48753968253968255 |

## 5. 메트릭 리포트 (HTML)

- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
