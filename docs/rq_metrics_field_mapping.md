# RQ1~RQ3 메트릭 정렬 — 표 및 JSON 로그 필드 매핑

**논문/리포트 RQ 결론에는 Outcome (RQ) 지표만 사용.** Process 지표는 Validator 수준 진단용. See `docs/metrics_for_paper.md`.

- **공식 메트릭 정의·집계 공식**: `docs/official_metrics.md` (Official).

## Outcome (RQ) vs Process

| Category | Metric | Role |
|----------|--------|------|
| **Outcome (RQ)** | SeverePolarityErrorRate (L3), polarity_conflict_rate, generalized_f1@0.95, tuple_agreement_rate (RQ2), tuple_f1_s2 | 논문 주장용 |
| **Process** | risk_resolution_rate / validator_clear_rate, validator_residual_risk_rate | 진단 (Validator-level; not outcome) |

## RQ별 Primary / Secondary 지표

| RQ | Primary 지표 (Outcome) | Secondary / Process | 비고 |
|----|------------------------|---------------------|------|
| **RQ1** | severe_polarity_error_L3_rate, polarity_conflict_rate | tuple_f1_s2, generalized_f1_theta | Outcome만 논문용; risk_* 는 Process |
| **RQ2** | tuple_agreement_rate, stage_mismatch_rate | self_consistency_exact, flip_flop_rate, variance | n_trials≥2에서 tuple_agreement_rate 산출 |
| **RQ3** | (Outcome 지표로 RQ 결론) | override_applied_rate, override_success_rate, validator_clear_rate | Process: validator-level diagnostic only |

- **Process 지표**: risk_resolution_rate, validator_residual_risk_rate — "Validator-level diagnostic. Not an outcome metric."
- **RQ2**: tuple_agreement_rate = 동일 입력 N회 실행 시 최종 튜플 집합 완전 일치 비율. merged run에서만.
- **RQ3**: override_* 는 Process; 논문 RQ 문장은 Outcome 지표만으로 성립.

---

## JSON 로그 필드 매핑 (structural_metrics / scorecard)

### Outcome (RQ) — paper-claimable

| RQ | 지표명 | structural_metrics.csv 필드 | 비고 |
|----|--------|-----------------------------|------|
| RQ1 | Severe Polarity Error (L3) | severe_polarity_error_L3_rate | aspect match, polarity mismatch only |
| RQ1 | Polarity Conflict Rate | polarity_conflict_rate | same-aspect after representative |
| RQ1 | generalized F1@0.95 | generalized_f1_theta | Neveditsin variant (θ=0.95) |
| RQ1/RQ | Tuple F1 (Final) | tuple_f1_s2 | gold subset (aspect_term, polarity) |
| RQ2 | Tuple Agreement Rate | tuple_agreement_rate | n_trials≥2, final tuple sets equal |
| RQ2 | Stage Mismatch Rate | stage_mismatch_rate | RuleM or S1≠S2 |

### Process (Internal) — validator-level diagnostic

| 지표명 | structural_metrics.csv 필드 | 비고 |
|--------|-----------------------------|------|
| Validator Clear Rate (Risk Resolution) | validator_clear_rate | Not an outcome metric. |
| Validator Residual Risk Rate | validator_residual_risk_rate | Stage2 Validator risks>0 only. |
| Risk-Flagged Rate | risk_flagged_rate | 확장 정의. |
| Override Applied / Success | override_applied_rate, override_success_rate | Process. |

---

## 리포트 빌더 반영

- `scripts/build_metric_report.py`: Outcome (RQ) / Process Control 섹션 시각적 분리. Process 행에 tooltip "Validator-level diagnostic. Not an outcome metric."
- `scripts/structural_error_aggregator.py`: CANONICAL_METRIC_KEYS 순서 Outcome → Process. severe_polarity_error_L3_*, generalized_f1_theta, tuple_agreement_rate 산출. See `docs/metrics_for_paper.md`.
