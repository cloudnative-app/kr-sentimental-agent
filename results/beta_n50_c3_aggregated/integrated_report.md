# 시드별 집계 통합 보고서 — beta_n50_c3

- **시드 런 수**: 3
- **머지 scorecards**: `merged_scorecards.jsonl` (150 rows)
- **Episodic memory**: C2_silent (silent)

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| beta_n50_c3__seed42_proposed | `results\beta_n50_c3__seed42_proposed` | `results\beta_n50_c3__seed42_proposed/derived/metrics/structural_metrics.csv` |
| beta_n50_c3__seed123_proposed | `results\beta_n50_c3__seed123_proposed` | `results\beta_n50_c3__seed123_proposed/derived/metrics/structural_metrics.csv` |
| beta_n50_c3__seed456_proposed | `results\beta_n50_c3__seed456_proposed` | `results\beta_n50_c3__seed456_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_agg_fallback_used | N_gold | N_gold_explicit | N_gold_explicit_pairs | N_gold_implicit | N_gold_implicit_pairs | N_gold_total | N_gold_total_pairs | N_pred_final_aspects | N_pred_final_tuples | N_pred_inputs_aspect_sentiments | N_pred_used |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| beta_n50_c3__seed42_proposed | 2 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 48 | 2 | 113 |
| beta_n50_c3__seed123_proposed | 2 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 48 | 2 | 115 |
| beta_n50_c3__seed456_proposed | 1 | 50 | 27 | 29 | 25 | 25 | 50 | 54 | 0 | 49 | 1 | 119 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `beta_n50_c3_aggregated/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_agg_fallback_used | 1.6667 | 0.4714 |
| N_gold | 50.0000 | 0.0000 |
| N_gold_explicit | 27.0000 | 0.0000 |
| N_gold_explicit_pairs | 29.0000 | 0.0000 |
| N_gold_implicit | 25.0000 | 0.0000 |
| N_gold_implicit_pairs | 25.0000 | 0.0000 |
| N_gold_total | 50.0000 | 0.0000 |
| N_gold_total_pairs | 54.0000 | 0.0000 |
| N_pred_final_aspects | 0.0000 | 0.0000 |
| N_pred_final_tuples | 48.3333 | 0.4714 |
| N_pred_inputs_aspect_sentiments | 1.6667 | 0.4714 |
| N_pred_used | 115.6667 | 2.4944 |
| alignment_failure_rate | 0.0200 | 0.0000 |
| aspect_hallucination_rate | 0.0200 | 0.0000 |
| break_rate | 0.0000 | 0.0000 |
| ... | (138 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `beta_n50_c3_aggregated/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 150 |
| profile_filter |  |
| eval_semver | 1.0 |
| eval_policy_hash | a64a7ec38e040a34 |
| severe_polarity_error_L3_count | 11 |
| severe_polarity_error_L3_rate | 0.07333333333333333 |
| polarity_conflict_rate_raw | 0.0 |
| polarity_conflict_rate | 0.0 |
| polarity_conflict_rate_after_rep | 0.0 |
| generalized_f1_theta |  |
| generalized_precision_theta |  |
| generalized_recall_theta |  |
| tuple_agreement_rate | 0.46 |
| tuple_agreement_eligible | True |
| tuple_f1_s1 | 0.40415873015873016 |

## 5. 메트릭 리포트 (HTML)

- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
