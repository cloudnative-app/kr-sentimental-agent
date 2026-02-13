# Paper Tables — beta_n50

*n_seeds = 3*

**Table 1. Structural Error Control (RQ1)**

| Condition | unsupported_polarity_rate ↓ | SeverePolarityErrorRate ↓ | risk_resolution_rate ↑ |
|-----------|----------------------------|---------------------------|------------------------|
| C1 | **0.0000 (0.0000)** | 0.0867 (0.0189) | **1.0000 (0.0000)** |
| C2_silent | 0.0000 (0.0000) | 0.0733 (0.0094) | 1.0000 (0.0000) |
| C2 | 0.0000 (0.0000) | 0.0733 (0.0094) | 1.0000 (0.0000) |
| C2_eval | 0.0000 (0.0000) | **0.0667 (0.0094)** | 1.0000 (0.0000) |

*Values are mean (SD) over 3 seeds.*

---

**Table 2. Inference Stability (RQ2)**

| Condition | polarity_conflict_rate ↓ | tuple_agreement_rate ↑ | invalid_rate ↓ |
|-----------|-------------------------|------------------------|----------------|
| C1 | **0.0000 (0.0000)** | N/A | **0.0000 (0.0000)** |
| C2_silent | 0.0000 (0.0000) | N/A | 0.0000 (0.0000) |
| C2 | 0.0000 (0.0000) | N/A | 0.0000 (0.0000) |
| C2_eval | 0.0000 (0.0000) | N/A | 0.0000 (0.0000) |

*Values are mean (SD) over 3 seeds; metrics are computed per seed using repeated runs and then averaged.*

---

**Table 3. Performance Constraint (Explicit-only F1)**

| Condition | tuple_f1_s2 |
|-----------|-------------|
| C1 | 0.4110 (0.0148) |
| C2_silent | 0.3833 (0.0552) |
| C2 | 0.3945 (0.0276) |
| C2_eval | **0.4208 (0.0110)** |

*Values are mean (SD) over 3 seeds.*

---

**Table 4. Implicit Subset Analysis**

| Condition | implicit_subset_F1 ↑ | implicit_invalid_rate ↓ |
|-----------|---------------------|--------------------------|
| C1 | 0.7800 (0.0144) | 0.0533 (0.0189) |
| C2_silent | 0.7667 (0.0340) | 0.0667 (0.0189) |
| C2 | **0.7978 (0.0245)** | **0.0400 (0.0000)** |
| C2_eval | 0.7956 (0.0314) | 0.0533 (0.0189) |

*Implicit subset metrics are computed at seed level and averaged. Values are mean (SD) over 3 seeds.*