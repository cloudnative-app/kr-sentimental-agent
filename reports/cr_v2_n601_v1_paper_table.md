# CR v2 Paper Table (M0 vs M1)

## Table 1 — F1 Metrics

| 구분 | M0 | M1 | Δ (M1−M0) | 95% CI |
|------|-----|-----|-----------|--------|
| Aspect-Term Sentiment F1 (ATSA-F1) | 0.6717 ± 0.0037 | 0.6719 ± 0.0056 | +0.0002 | [-0.0052, 0.0079] |
| Aspect-Category Sentiment F1 (ACSA-F1) | 0.4932 ± 0.0057 | 0.4893 ± 0.0138 | -0.0039 | [-0.0258, 0.0203] |
| #attribute f1 | 0.6417 ± 0.0083 | 0.6480 ± 0.0068 | +0.0063 | [-0.0067, 0.0212] |

## Table 2 — Schema & Error Control

| Metric | M0 | M1 | Δ | ideal Direction |
|--------|-----|-----|-----|-----------------|
| Schema Assignment Completeness | 0.7441 ± 0.0047 | 0.7359 ± 0.0017 | -0.0082 | ↑ |
| Schema Coverage | 0.5445 ± 0.0059 | 0.5419 ± 0.0122 | -0.0026 | ↑ |
| Implicit Assignment Error Rate | 0.0078 ± 0.0016 | 0.0100 ± 0.0027 | +0.0022 | ↓ |
| Intra-Aspect Polarity Conflict Rate | 0.0471 ± 0.0028 | 0.0455 ± 0.0039 | -0.0016 | ↓ |
| Error Correction Rate | 0.0694 ± 0.0059 | 0.0645 ± 0.0027 | -0.0049 | proportion of incorrect assignments corrected |
| Error Introduction Rate | 0.0049 ± 0.0001 | 0.0119 ± 0.0049 | +0.0070 | new errors introduced during refinement |
| Net Correction Gain | 0.0444 ± 0.0039 | 0.0394 ± 0.0028 | -0.0050 | net positive correction |
| recheck-trigger rate | 0.3705 ± 0.0039 | 0.3705 ± 0.0100 | +0.0000 |  |
| memory retrieval rate (retrieved_k>0 기준) | 0.0000 ± 0.0000 | 0.9983 ± 0.0000 | +0.9983 |  |
| memory_retrieval_mean_k | 0.0000 ± 0.0000 | 2.7399 ± 0.0078 | +2.7399 |  |
| Run-to-Run Output Agreement (Measurement IRR) | 0.6132 ± 0.0087 | 0.6029 ± 0.0100 | -0.0103 | stability across seeds, *코헨 카파만 산출되는 중 |
| Inter-Reviewer Agreement (Action Level) (Action IRR) | 0.5869 ± 0.0079 | 0.5743 ± 0.0124 | -0.0126 | reviewer decision consistency, *코헨 카파만 산출되는 중 |
| subset IRR (conflict) | 0.4251 | 0.4242 | -0.0009 |  |
| subset_n_conflict | 130 | 138 |  |  |
| subset IRR (implicit) | 0.6085 | 0.5918 | -0.0167 |  |
| subset_n_implicit | 297 | 297 |  |  |
| subset IRR (negation) | 0.6211 | 0.5865 | -0.0346 |  |
| subset_n_negation | 117 | 117 |  |  |
| seed variance | 0.0057 | 0.0138 |  |  |
| CDA | 0.3186 ± 0.0420 | 0.2817 ± 0.0223 | -0.0369 |  |
| AAR Majority Rate | 0.9584 ± 0.0015 | 0.9615 ± 0.0021 | +0.0031 |  |

**Notes:**
- CDA: n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)
- aar_majority_rate: AAR majority agreement rate
- memory retrieval rate: mean(retrieved_k > 0)

## Fleiss' κ IRR (별도 보고)

| 구분 | M0 | M1 | Δ |
|------|-----|-----|-----|
| Action IRR (Fleiss' κ) | -0.190 ± 0.010 | -0.164 ± 0.014 | +0.026 |
| Measurement IRR (Fleiss' κ) | -0.043 ± 0.008 | -0.030 ± 0.011 | +0.013 |

*Fleiss' κ는 3명 rater(A/B/C) 전체 일치도. Cohen's κ는 pairwise 평균. n601 v1 시드 42,123,456 기준.*

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