# 시드별 집계 통합 보고서 — experiment_mini3_2

- **시드 런 수**: 2
- **머지 scorecards**: `merged_scorecards.jsonl` (60 rows)

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| experiment_mini3_2__seed42_proposed | `results\experiment_mini3_2__seed42_proposed` | `results\experiment_mini3_2__seed42_proposed/derived/metrics/structural_metrics.csv` |
| experiment_mini3_2__seed123_proposed | `results\experiment_mini3_2__seed123_proposed` | `results\experiment_mini3_2__seed123_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_gold | aspect_hallucination_rate | break_rate | conditional_improvement_gain_hf_agree | conditional_improvement_gain_hf_disagree | debate_fail_fallback_used_rate | debate_fail_neutral_stance_rate | debate_fail_no_aspects_rate | debate_fail_no_match_rate | debate_mapping_coverage | debate_mapping_direct_rate | debate_mapping_fallback_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| experiment_mini3_2__seed42_proposed | 30 | 0.66666666 |  |  |  | 0.01111111 | 0.0 | 0.03333333 | 0.0 | 0.96666666 | 0.95555555 | 0.01111111 |
| experiment_mini3_2__seed123_proposed | 30 | 0.7 |  |  |  | 0.0 | 0.00555555 | 0.03333333 | 0.0 | 0.96111111 | 0.96111111 | 0.0 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `experiment_mini3_2_aggregated/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_gold | 30.0000 | 0.0000 |
| aspect_hallucination_rate | 0.6833 | 0.0167 |
| debate_fail_fallback_used_rate | 0.0056 | 0.0056 |
| debate_fail_neutral_stance_rate | 0.0028 | 0.0028 |
| debate_fail_no_aspects_rate | 0.0333 | 0.0000 |
| debate_fail_no_match_rate | 0.0000 | 0.0000 |
| debate_mapping_coverage | 0.9639 | 0.0028 |
| debate_mapping_direct_rate | 0.9583 | 0.0028 |
| debate_mapping_fallback_rate | 0.0056 | 0.0056 |
| debate_mapping_none_rate | 0.0361 | 0.0028 |
| debate_override_applied | 8.5000 | 4.5000 |
| debate_override_skipped_already_confident | 4.0000 | 1.0000 |
| debate_override_skipped_already_confident_rate | 0.0479 | 0.0138 |
| debate_override_skipped_conflict | 67.0000 | 8.0000 |
| debate_override_skipped_low_signal | 5.0000 | 1.0000 |
| ... | (46 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `experiment_mini3_2_aggregated/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 60 |
| aspect_hallucination_rate | 0.6833333333333333 |
| unsupported_polarity_rate | 0.8833333333333333 |
| polarity_conflict_rate | 0.25 |
| negation_contrast_failure_rate | 0.06666666666666667 |
| guided_change_rate | 0.4 |
| unguided_drift_rate | 0.15 |
| risk_resolution_rate | 1.0 |
| risk_flagged_rate | 0.06666666666666667 |
| risk_affected_change_rate | 0.0 |
| risk_resolved_with_change_rate | 0.0 |
| risk_resolved_without_change_rate | 0.08888888888888889 |
| ignored_proposal_rate | 1.0 |
| residual_risk_severity_sum | 0.0 |
| parse_generate_failure_rate | 0.0 |

## 5. 메트릭 리포트 (HTML)

- 머지 런: `reports/merged_run_experiment_mini3_2/metric_report.html` (아래 스크립트로 생성됨)
- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
