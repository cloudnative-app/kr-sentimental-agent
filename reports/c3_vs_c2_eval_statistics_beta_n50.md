# C3 vs C2_eval 통계 검정 결과

**Base run**: beta_n50  |  **Seeds**: [42, 123, 456]  |  **n_pairs**: 3

---

## 1. Mean 차이 (Paired t-test)

같은 seed에서 C3 vs C2_eval 비교. **paired t-test** (ttest_rel) 사용.

| Metric | C3 mean (SD) | C2_eval mean (SD) | Mean diff | t | p-value | 해석 |
|--------|--------------|-------------------|-----------|---|---------|------|
| tuple_f1_s2_explicit_only | 0.3833 (0.0552) | 0.4208 (0.0110) | -0.0375 | -0.929 | 0.4511 | p≥.05, exploratory: C2_eval 유리 |
| severe_polarity_error_L3_rate | 0.0733 (0.0094) | 0.0667 (0.0094) | +0.0067 | 1.000 | 0.4226 | p≥.05, exploratory: C2_eval 유리 |
| unsupported_polarity_rate | 0.0000 (0.0000) | 0.0000 (0.0000) | +0.0000 | nan | nan | p≥.05 |
| risk_resolution_rate | 1.0000 (0.0000) | 1.0000 (0.0000) | +0.0000 | nan | nan | p≥.05 |
| tuple_f1_s2_implicit_only | 0.7667 (0.0340) | 0.7956 (0.0314) | -0.0289 | -0.679 | 0.5674 | p≥.05, exploratory: C2_eval 유리 |
| implicit_invalid_pred_rate | 0.0667 (0.0189) | 0.0533 (0.0189) | +0.0133 | 1.000 | 0.4226 | p≥.05, exploratory: C2_eval 유리 |
| polarity_conflict_rate | 0.0000 (0.0000) | 0.0000 (0.0000) | +0.0000 | nan | nan | p≥.05 |
| parse_generate_failure_rate | 0.0000 (0.0000) | 0.0000 (0.0000) | +0.0000 | nan | nan | p≥.05 |

---

## 2. SD 차이 (시드 간 분산 비교)

각 조건에서 시드 간 표준편차. **Levene test**로 분산 동질성 검정.

| Metric | C3 SD | C2_eval SD | Levene stat | p-value | 해석 |
|--------|------|------------|-------------|---------|------|
| tuple_f1_s2_explicit_only | 0.0552 | 0.0110 | 2.046 | 0.2258 | p≥.05 |
| severe_polarity_error_L3_rate | 0.0094 | 0.0094 | 0.000 | 1.0000 | p≥.05 |
| unsupported_polarity_rate | 0.0000 | 0.0000 | nan | nan | p≥.05 |
| risk_resolution_rate | 0.0000 | 0.0000 | nan | nan | p≥.05 |
| tuple_f1_s2_implicit_only | 0.0340 | 0.0314 | 0.025 | 0.8831 | p≥.05 |
| implicit_invalid_pred_rate | 0.0189 | 0.0189 | 0.000 | 1.0000 | p≥.05 |
| polarity_conflict_rate | 0.0000 | 0.0000 | nan | nan | p≥.05 |
| parse_generate_failure_rate | 0.0000 | 0.0000 | nan | nan | p≥.05 |

---

## 3. Wilcoxon signed-rank (robust 대안)

paired t-test의 비모수 대안.

| Metric | Mean diff | W stat | p-value |
|--------|-----------|--------|---------|
| tuple_f1_s2_explicit_only | -0.0375 | 1.0 | 0.5000 |
| severe_polarity_error_L3_rate | +0.0067 | 0.0 | 0.3173 |
| unsupported_polarity_rate | +0.0000 | — | (zero diff) |
| risk_resolution_rate | +0.0000 | — | (zero diff) |
| tuple_f1_s2_implicit_only | -0.0289 | 2.0 | 0.7500 |
| implicit_invalid_pred_rate | +0.0133 | 0.0 | 0.3173 |
| polarity_conflict_rate | +0.0000 | — | (zero diff) |
| parse_generate_failure_rate | +0.0000 | — | (zero diff) |

---

## 4. 참고

- **store_write**: C3=true (episodic store에 저장), C2_eval=false (저장 안 함).
- **n=3** (seeds 42, 123, 456) → 검정력 제한. exploratory 해석 권장.
- **seed 내부 분산**: n_trials=1이라 run-level repeated measure 없음 → 시드 간 SD 비교로 대체.