# 시드별 집계 통합 보고서 — betatest_c1

- **시드 런 수**: 2
- **머지 scorecards**: `merged_scorecards.jsonl` (100 rows)
- **Episodic memory**: C1 (off)

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| betatest_c1__seed42_proposed | `results\betatest_c1__seed42_proposed` | `results\betatest_c1__seed42_proposed/derived/metrics/structural_metrics.csv` |
| betatest_c1__seed123_proposed | `results\betatest_c1__seed123_proposed` | `results\betatest_c1__seed123_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_agg_fallback_used | N_gold | N_gold_explicit | N_gold_explicit_pairs | N_gold_implicit | N_gold_implicit_pairs | N_gold_total | N_gold_total_pairs | N_pred_final_aspects | N_pred_final_tuples | N_pred_inputs_aspect_sentiments | N_pred_used |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| betatest_c1__seed42_proposed | 2 | 50 | 35 | 35 | 16 | 16 | 50 | 51 | 0 | 48 | 2 | 120 |
| betatest_c1__seed123_proposed | 2 | 50 | 35 | 35 | 16 | 16 | 50 | 51 | 0 | 48 | 2 | 120 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `betatest_c1_aggregated/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_agg_fallback_used | 2.0000 | 0.0000 |
| N_gold | 50.0000 | 0.0000 |
| N_gold_explicit | 35.0000 | 0.0000 |
| N_gold_explicit_pairs | 35.0000 | 0.0000 |
| N_gold_implicit | 16.0000 | 0.0000 |
| N_gold_implicit_pairs | 16.0000 | 0.0000 |
| N_gold_total | 50.0000 | 0.0000 |
| N_gold_total_pairs | 51.0000 | 0.0000 |
| N_pred_final_aspects | 0.0000 | 0.0000 |
| N_pred_final_tuples | 48.0000 | 0.0000 |
| N_pred_inputs_aspect_sentiments | 2.0000 | 0.0000 |
| N_pred_used | 120.0000 | 0.0000 |
| alignment_failure_rate | 0.0600 | 0.0000 |
| aspect_hallucination_rate | 0.0600 | 0.0000 |
| break_rate | 0.0000 | 0.0000 |
| ... | (135 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `betatest_c1_aggregated/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 100 |
| profile_filter |  |
| eval_semver | 1.0 |
| eval_policy_hash | a64a7ec38e040a34 |
| severe_polarity_error_L3_count | 5 |
| severe_polarity_error_L3_rate | 0.05 |
| polarity_conflict_rate_raw | 0.0 |
| polarity_conflict_rate | 0.0 |
| polarity_conflict_rate_after_rep | 0.0 |
| generalized_f1_theta |  |
| generalized_precision_theta |  |
| generalized_recall_theta |  |
| tuple_agreement_rate | 0.62 |
| tuple_agreement_eligible | True |
| tuple_f1_s1 | 0.3814047619047619 |

## 5. 메트릭 리포트 (HTML)

- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
