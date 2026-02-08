# Validation Requirements Before Claiming Improvement (RQ3)

Before stating that **advisory memory improves structural risk control** (RQ3), the following three validations must be satisfied.

---

## 1) Differential Effect

- **risk_resolution_rate** (validator-only or extended definition) must **differ** between:
  - **Memory OFF (C1)** and **Memory ON (C2)**
- Under **identical data and seed** (e.g. same `real_n100_seed1` dataset, same `experiment.repeat.seeds`).
- If C1 and C2 yield the same risk_resolution_rate, the metric does not support a claim of improvement from memory.

---

## 2) Change-Coupled Resolution

- **risk_resolved_with_change_rate** must be **> 0**.
- This confirms that resolution is **not a definitional artifact** (e.g. not solely from samples that had no stage2 change).
- If risk_resolved_with_change_rate = 0, report as **metric definability improvement** only, not performance improvement.

---

## 3) Stability Check

- **polarity_conflict_rate** and other stability metrics must **not increase** in the Memory ON (C2) condition compared to Memory OFF (C1).
- If memory ON increases polarity_conflict_rate or degrades stability, do not claim performance improvement.

---

## Reporting Rule

| Outcome | Report as |
|--------|-----------|
| All three validations pass | **Performance improvement** (advisory memory improves structural risk control). |
| Any validation fails | **Metric definability improvement** only (e.g. extended risk_resolution_rate is now measurable), not performance improvement. |

---

## References

- RQ3: Does explicit_failure ↓ → risk_resolution_rate ↑? (see `docs/rq2_rq3_implicit_explicit_failure_diagnosis.md`)
- Extended risk_resolution_rate: stage1_structural_risk denominator, stage2 resolution; legacy = validator-only (see `scripts/structural_error_aggregator.py`, `docs/rq_metrics_field_mapping.md`)
