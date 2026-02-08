# 시드별 집계 통합 보고서 — experiment_mini2

- **시드 런 수**: 2
- **머지 scorecards**: `merged_scorecards.jsonl` (122 rows)

## 1. 시드별 런 디렉터리

| Seed / Run | 결과 디렉터리 | 메트릭 CSV |
|------------|----------------|------------|
| experiment_mini2__seed42_proposed | `results\experiment_mini2__seed42_proposed` | `results\experiment_mini2__seed42_proposed/derived/metrics/structural_metrics.csv` |
| experiment_mini2__seed123_proposed | `results\experiment_mini2__seed123_proposed` | `results\experiment_mini2__seed123_proposed/derived/metrics/structural_metrics.csv` |

## 2. 시드별 구조 오류 메트릭 (요약)

| _seed | N_gold | aspect_hallucination_rate | break_rate | conditional_improvement_gain_hf_agree | conditional_improvement_gain_hf_disagree | debate_fail_fallback_used_rate | debate_fail_neutral_stance_rate | debate_fail_no_aspects_rate | debate_fail_no_match_rate | debate_mapping_coverage | debate_mapping_direct_rate | debate_mapping_fallback_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| experiment_mini2__seed42_proposed | 61 | 0.75409836 |  |  |  | 0.05191256 | 0.00546448 | 0.03278688 | 0.0 | 0.96174863 | 0.90983606 | 0.05191256 |
| experiment_mini2__seed123_proposed | 61 | 0.73770491 |  |  |  | 0.07103825 | 0.00546448 | 0.03278688 | 0.0 | 0.96174863 | 0.89071038 | 0.07103825 |

## 3. 평균 ± 표준편차 (시드 간)

- **파일**: `experiment_mini2_aggregated/aggregated_mean_std.csv`, `aggregated_mean_std.md`

| Metric | Mean | Std |
|--------|------|-----|
| N_gold | 61.0000 | 0.0000 |
| aspect_hallucination_rate | 0.7459 | 0.0082 |
| debate_fail_fallback_used_rate | 0.0615 | 0.0096 |
| debate_fail_neutral_stance_rate | 0.0055 | 0.0000 |
| debate_fail_no_aspects_rate | 0.0328 | 0.0000 |
| debate_fail_no_match_rate | 0.0000 | 0.0000 |
| debate_mapping_coverage | 0.9617 | 0.0000 |
| debate_mapping_direct_rate | 0.9003 | 0.0096 |
| debate_mapping_fallback_rate | 0.0615 | 0.0096 |
| debate_mapping_none_rate | 0.0383 | 0.0000 |
| debate_override_applied | 17.0000 | 1.0000 |
| debate_override_skipped_already_confident | 4.0000 | 1.0000 |
| debate_override_skipped_already_confident_rate | 0.0252 | 0.0061 |
| debate_override_skipped_conflict | 130.5000 | 0.5000 |
| debate_override_skipped_low_signal | 7.0000 | 2.0000 |
| ... | (44 metrics total) | |

## 4. 머지 메트릭 (self_consistency 등)

- **디렉터리**: `experiment_mini2_aggregated/merged_metrics/`
- **파일**: structural_metrics.csv, structural_metrics_table.md

| Metric | Value |
|--------|-------|
| n | 122 |
| aspect_hallucination_rate | 0.7459016393442623 |
| unsupported_polarity_rate | 0.8934426229508197 |
| polarity_conflict_rate | 0.16393442622950818 |
| negation_contrast_failure_rate | 0.08196721311475409 |
| guided_change_rate | 0.35 |
| unguided_drift_rate | 0.10655737704918032 |
| risk_resolution_rate | 1.0 |
| risk_flagged_rate | 0.09836065573770492 |
| risk_affected_change_rate | 0.08333333333333333 |
| risk_resolved_with_change_rate | 0.05 |
| risk_resolved_without_change_rate | 0.10784313725490197 |
| ignored_proposal_rate | 0.9166666666666666 |
| residual_risk_severity_sum | 0.0 |
| parse_generate_failure_rate | 0.0 |

## 5. 메트릭 리포트 (HTML)

- 머지 런: `reports/<merged_run_name>/metric_report.html` (아래 스크립트로 생성됨)
- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)
