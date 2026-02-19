# Targeted Re-check Prompt (CR_V2)

You are performing a targeted re-check for conflict review.
You MUST output exactly one ReviewActionItem for the given tuple_id(s).

## Input
- original_text: the review text
- conflict_type: the conflict type for this tuple (if any)
- candidate_tuples: list of tuple objects with:
  - tuple_id
  - aspect_ref
  - aspect_term
  - polarity
  - evidence (may be null)
  - confidence (optional)
- prior_votes: actions from A/B/C (may be incomplete)

## Your task
Choose ONE action among: KEEP, DROP, FLIP, MERGE, FLAG.

### Hard constraints (format)
1) target_tuple_ids MUST be non-empty.
2) If action_type == FLIP: new_value MUST include {"polarity": "<positive|negative|neutral>"}.
3) If action_type == MERGE: new_value MUST include {"normalized_ref": "<valid_aspect_ref>"}.
4) If you cannot provide required fields, do NOT output FLIP/MERGE. Use FLAG with reason_code="FORMAT_INCOMPLETE".

### Decision guidance (do not over-generate)
- Prefer DROP when reason is structural redundancy and conflict_type indicates granularity overlap:
  - If conflict_type == "granularity_overlap_candidate" and an upper-level ref ("제품 전체#X") is redundant with a lower-level ref of same polarity, choose DROP with reason_code="REDUNDANT_UPPER_REF".
- Prefer FLIP only when polarity evidence is clear (negation/contrast scope etc.):
  - If negation/contrast is explicitly present and affects sentiment direction, FLIP with reason_code in {"NEGATION_SCOPE","CONTRAST_CLAUSE"}.
- Prefer MERGE only when ref normalization is unambiguous (e.g., duplicate refs or mapping within allowed taxonomy):
  - Use reason_code "SPAN_OVERLAP_MERGE" or "DUPLICATE_TUPLE" when applicable.
- If uncertainty remains:
  - Use FLAG. For granularity overlap use reason_code="REDUNDANT_REF_UNCERTAIN"; otherwise "TIE_UNRESOLVED" or "POLARITY_UNCERTAIN".

## Output schema
Return JSON matching:
{"review_actions":[{"action_type":"...","target_tuple_ids":["..."],"new_value":{...},"reason_code":"...","actor":"ARB"}]}

---USER---

original_text:
{text}

conflict_type:
{conflict_type}

candidate_tuples:
{candidate_tuples_json}

prior_votes:
{prior_votes_json}

Task:
Output exactly one ReviewActionItem. Ensure target_tuple_ids is non-empty. For FLIP include new_value.polarity; for MERGE include new_value.normalized_ref. Otherwise use FLAG with FORMAT_INCOMPLETE.
