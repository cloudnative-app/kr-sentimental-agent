# CR v2 Paper Table (M0 vs M1)

## Table 1 — F1 Metrics

| 구분 | M0 | M1 | Δ (M1−M0) | 95% CI |
|------|-----|-----|-----------|--------|
| Aspect-Term Sentiment F1 (ATSA-F1) | 0.7065 ± 0.0065 | 0.6974 ± 0.0037 | -0.0091 | [-0.0155, -0.0011] |
| Aspect-Category Sentiment F1 (ACSA-F1) | 0.4494 ± 0.0113 | 0.4611 ± 0.0046 | +0.0117 | [0.0017, 0.0258] |
| #attribute f1 | 0.6177 ± 0.0086 | 0.6248 ± 0.0037 | +0.0071 | [-0.0100, 0.0183] |

## Table 2 — Schema & Error Control

| Metric | M0 | M1 | Δ | ideal Direction |
|--------|-----|-----|-----|-----------------|
| Schema Assignment Completeness | 0.7615 ± 0.0162 | 0.7489 ± 0.0054 | -0.0126 | ↑ |
| Schema Coverage | 0.4955 ± 0.0127 | 0.5045 ± 0.0074 | +0.0090 | ↑ |
| Implicit Assignment Error Rate | 0.0347 ± 0.0098 | 0.0208 ± 0.0000 | -0.0139 | ↓ |
| Intra-Aspect Polarity Conflict Rate | 0.0333 ± 0.0047 | 0.0233 ± 0.0125 | -0.0100 | ↓ |
| Error Correction Rate | 0.0860 ± 0.0070 | 0.0887 ± 0.0060 | +0.0027 | proportion of incorrect assignments corrected |
| Error Introduction Rate | 0.0000 ± 0.0000 | 0.0115 ± 0.0163 | +0.0115 | new errors introduced during refinement |
| Net Correction Gain | 0.0633 ± 0.0047 | 0.0600 ± 0.0082 | -0.0033 | net positive correction |
| recheck-trigger rate | 0.4133 ± 0.0368 | 0.4100 ± 0.0216 | -0.0033 |  |
| memory retrieval rate (retrieved_k>0 기준) | 0.0000 ± 0.0000 | 0.9900 ± 0.0000 | +0.9900 |  |
| memory_retrieval_mean_k | 0.0000 ± 0.0000 | 1.5200 ± 0.0000 | +1.5200 |  |
| Run-to-Run Output Agreement (Measurement IRR) | 0.6028 ± 0.0387 | 0.5964 ± 0.0194 | -0.0064 | stability across seeds, *코헨 카파만 산출되는 중 |
| Inter-Reviewer Agreement (Action Level) (Action IRR) | 0.5750 ± 0.0345 | 0.5790 ± 0.0138 | +0.0040 | reviewer decision consistency, *코헨 카파만 산출되는 중 |
| subset IRR (conflict) | 0.4022 | 0.3447 | -0.0575 |  |
| subset_n_conflict | 27 | 24 |  |  |
| subset IRR (implicit) | 0.5859 | 0.5618 | -0.0241 |  |
| subset_n_implicit | 47 | 48 |  |  |
| subset IRR (negation) | 0.5509 | 0.6038 | +0.0530 |  |
| subset_n_negation | 22 | 22 |  |  |
| seed variance | 0.0113 | 0.0046 |  |  |
| CDA | 0.3136 ± 0.0435 | 0.3116 ± 0.0197 | -0.0020 |  |
| AAR Majority Rate | 0.9656 ± 0.0079 | 0.9632 ± 0.0078 | -0.0024 |  |

**Notes:**
- CDA: n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)
- aar_majority_rate: AAR majority agreement rate
- memory retrieval rate: mean(retrieved_k > 0)

## Appendix

| 구분 | 내용 |
|------|------|
| A. Full seed-by-seed table | seed별 모든 핵심 메트릭, Δ per seed |
| B. Bootstrap distribution plot | ΔF1 분포, net_gain 분포 |
| C. Error case qualitative table | break 사례 상세, memory_retrieved 수, implicit/negation 태그 |
| D. Memory usage diagnostics | retrieval_hit_rate, retrieval_k distribution histogram |
| E. IRR subset table | conflict, implicit, negation subset별 Measurement IRR, Action IRR |
| F. break subtype | implicit/negation/simple |
| G. 절대건수 (event count) | break_count, implicit_invalid_count, conflict_count 등 |