# RQ1~RQ3 메트릭 정렬 — 표 및 JSON 로그 필드 매핑

## RQ별 Primary / Secondary 지표

| RQ | Primary 지표 | Secondary 지표 | 비고 |
|----|----------------|-----------------|------|
| **RQ1** | risk_flagged_rate | residual_risk_rate, risk_resolution_rate | risk/residual/conflict 중심; 정답 기준 아님 |
| **RQ2** | self_consistency_exact | flip_flop_rate, variance, risk_set_consistency | 반복추론 agreement/variance; merged run에서 계산 |
| **RQ3** | override_applied_rate, override_success_rate | debate_mapping_coverage (mapping_coverage) | override_success = risk 개선 & 안전(정답 아님); applied/skipped + coverage |

- **override_success_rate**: "정답"이 아니라 "risk 감소 + 안전"으로 계산 (적용된 케이스 중 risk_before > risk_after 비율).
- **RQ1**: risk_flagged_rate, residual_risk_rate, risk_resolution_rate 는 structural_metrics.csv / scorecard 에서 계산.
- **RQ2**: self_consistency, flip_flop_rate, variance 는 merged_scorecards 기반으로만 유의미 (단일 run 시 1.0 / 0 / 0).
- **RQ3**: mapping_coverage = debate_mapping_coverage (토론 발언→관점 매핑 커버리지).

---

## JSON 로그 필드 매핑 (structural_metrics / scorecard)

| RQ | 지표명 | structural_metrics.csv 필드 | scorecard / CaseTrace 필드 |
|----|--------|-----------------------------|----------------------------|
| RQ1 | Risk-Flagged Rate | risk_flagged_rate | validator.structural_risks (stage1) 존재 여부 |
| RQ1 | Residual Risk Rate | residual_risk_rate | validator.structural_risks (stage2) 존재 여부 |
| RQ1 | Risk Resolution Rate | risk_resolution_rate | (stage1_risks - stage2_risks) / stage1_risks |
| RQ2 | Self-Consistency | self_consistency_exact | merged: 동일 case_id의 final_result.label 일치 비율 |
| RQ2 | Flip-Flop Rate | flip_flop_rate | merged: label 변동 비율 (variance와 동일) |
| RQ2 | Variance | variance | 1 - self_consistency_exact |
| RQ3 | Override Applied Rate | override_applied_rate | debate.override_stats.applied / N |
| RQ3 | Override Success Rate | override_success_rate | 적용 케이스 중 risk 개선 비율 (정답 아님) |
| RQ3 | Mapping Coverage | debate_mapping_coverage | debate.mapping_stats (direct+fallback)/total |

---

## 리포트 빌더 반영

- `scripts/build_metric_report.py`: RQ1/RQ2/RQ3 섹션에서 위 Primary 지표를 우선 표시.
- `scripts/structural_error_aggregator.py`: residual_risk_rate, override_applied_rate, override_success_rate, flip_flop_rate, variance 출력 및 CANONICAL_METRIC_KEYS에 포함.
