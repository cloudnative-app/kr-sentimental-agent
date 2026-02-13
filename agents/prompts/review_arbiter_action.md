# Arbiter Policy (Deterministic — implemented in code)

**Note**: The Arbiter is deterministic voting logic in `conflict_review_runner.py`.
No A>B>C authority order. Prefer minimal intervention.

---

## Aggregation Rule (No authority order)

For each tuple_id:

1. If ≥2 reviewers propose DROP → DROP
2. If ≥2 reviewers propose KEEP → KEEP
3. If ≥2 reviewers propose FLIP → FLIP (structural consistency)
4. If only 1 reviewer proposes FLIP (1 FLIP + 1 DROP + 1 KEEP):
   - If FLIP has structural reason (NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT) → FLIP
   - If inference/evidence weak → KEEP + FLAG
5. If tie (1 KEEP, 1 DROP, 1 FLAG):
   - Default to KEEP + FLAG (minimal intervention)

Never apply A>B>C authority order.
Prefer minimal intervention.

---

## Arbiter Action Space

{KEEP, DROP, FLIP, FLAG}

(MERGE moved to Finalize step.)

---

## Implementation

```python
actions_by_tuple = group_by_tuple_id(review_actions)

for tid, acts in actions_by_tuple.items():
    votes = [norm(a["action_type"]) for a in acts]  # MERGE → KEEP

    if majority(votes) >= 2:
        final_action = majority_vote(votes)
        if final_action == "FLIP" and set(votes) == {"FLIP","DROP","KEEP"}:
            # 1 FLIP + 1 DROP + 1 KEEP: check reason_code
            if flip has structural reason (NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT):
                final_action = "FLIP"
            else:
                final_action = "FLAG"
                reason_code = "POLARITY_UNCERTAIN"
    else:
        final_action = "FLAG"
        reason_code = "POLARITY_UNCERTAIN"

    output.append(...)
```

**Finalize** (after Arbiter):

```python
for tuples with same aspect_term:
    unify aspect_ref
```
