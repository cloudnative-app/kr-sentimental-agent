# CR v2 Paper Table v2 (S0 | M0 | M1 | Δ_refinement | Δ)

## 5.1 Surface Layer: Extraction Performance Control

| Layer | Metric | S0 | M0 | M1 | Δ_refinement (M0−S0) | Δ (M1−M0) | 95% CI |
|-------|--------|-----|-----|-----|----------------------|------------|--------|
| Surface | ATSA-F1 | 0.5824 ± 0.0022 | 0.6717 ± 0.0037 | 0.6719 ± 0.0056 | +0.0893 | +0.0002 | [-0.0052, 0.0079] |

## 5.2 Schema Layer: Constraint Stability (RQ1)

| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |
|--------|-----|-----|-----|---------------|-----|-----------|
| Implicit Assignment Error Rate | 0.2018 ± 0.0042 | 0.0078 ± 0.0016 | 0.0100 ± 0.0027 | -0.1940 | +0.0022 | ↓ |
| Intra-Aspect Polarity Conflict Rate | 0.0155 ± 0.0044 | 0.0471 ± 0.0028 | 0.0455 ± 0.0039 | +0.0316 | -0.0016 | ↓ |
| Schema Assignment Completeness | 0.9250 ± 0.0006 | 0.7441 ± 0.0047 | 0.7359 ± 0.0017 | -0.1809 | -0.0082 | ↑ |
| Schema Coverage | 0.4240 ± 0.0020 | 0.5445 ± 0.0059 | 0.5419 ± 0.0122 | +0.1205 | -0.0026 | ↑ |

| Layer | Metric | S0 | M0 | M1 | Δ_refinement | Δ | 95% CI |
|-------|--------|-----|-----|-----|---------------|-----|--------|
| Schema | ACSA-F1 | 0.4015 ± 0.0028 | 0.4932 ± 0.0057 | 0.4893 ± 0.0138 | +0.0917 | -0.0039 | [-0.0258, 0.0203] |
| Schema | #attribute f1 | 0.5437 ± 0.0030 | 0.6417 ± 0.0083 | 0.6480 ± 0.0068 | +0.0980 | +0.0063 | [-0.0067, 0.0212] |

## 5.3 Process Layer: Correction Stability (RQ2)

| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |
|--------|-----|-----|-----|---------------|-----|-----------|
| Error Correction Rate | 0.0000 ± 0.0000 | 0.0694 ± 0.0059 | 0.0645 ± 0.0027 | +0.0694 | -0.0049 | ↑ |
| Error Introduction Rate | 0.0000 ± 0.0000 | 0.0049 ± 0.0001 | 0.0119 ± 0.0049 | +0.0049 | +0.0070 | ↓ |
| Net Correction Gain | 0.0000 ± 0.0000 | 0.0444 ± 0.0039 | 0.0394 ± 0.0028 | +0.0444 | -0.0050 | ↑ |

## 5.4 Stochastic Stability: Run-to-Run Reproducibility

| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |
|--------|-----|-----|-----|---------------|-----|-----------|
| seed variance (ACSA-F1) | 0.0028 | 0.0057 | 0.0138 | +0.0029 | +0.0081 | ↓ |
| Run-to-Run Output Agreement (Measurement IRR, Cohen's κ) |  | 0.6132 ± 0.0087 | 0.6029 ± 0.0100 |  | -0.0103 | ↑ |
| Run-to-Run Output Agreement (Measurement IRR, Fleiss' κ) |  | -0.0429 ± 0.0082 | -0.0303 ± 0.0113 |  | +0.0126 | ↑ |
| CDA |  | 0.3186 ± 0.0420 | 0.2817 ± 0.0223 |  | -0.0369 | |
| aar_majority_rate | 1.0000 ± 0.0000 | 0.9584 ± 0.0015 | 0.9615 ± 0.0021 | -0.0416 | +0.0031 | |

**Notes:**
- CDA: n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)
- aar_majority_rate: AAR majority agreement rate
- seed variance: std of tuple_f1_s2_refpol (ACSA-F1) across seeds
- Δ_refinement = M0 − S0: multi-agent refinement effect (Review+Arbiter)
- S0: single-pass baseline (no review, no arbiter, no memory); fix/break/net_gain = 0