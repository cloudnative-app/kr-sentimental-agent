"""
5-line diagnostic for one scorecard sample: selected tuple, selected judgement idx,
RQ1 bucket, and drop_reason counts (alignment_failure, filter_rejection, semantic_hallucination).
See docs/smoke_check_rq1_grounding_v2.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.structural_error_aggregator import (
    DROP_REASON_ALIGNMENT_FAILURE,
    DROP_REASON_FILTER_REJECTION,
    DROP_REASON_SEMANTIC_HALLUCINATION,
    get_selected_judgement,
    load_jsonl,
    rq1_grounding_bucket,
)

# Private helper used for selected tuple display
from scripts.structural_error_aggregator import _get_first_final_tuple  # noqa: F401


def main() -> None:
    ap = argparse.ArgumentParser(description="5-line RQ1 grounding diagnostic for one scorecard sample")
    ap.add_argument("--input", required=True, help="Path to scorecards.jsonl")
    ap.add_argument("--index", type=int, default=0, help="Sample index (0-based)")
    args = ap.parse_args()
    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        print("No records")
        return
    idx = max(0, min(args.index, len(rows) - 1))
    record = rows[idx]

    meta = record.get("meta") or {}
    text_id = meta.get("text_id") or meta.get("uid") or meta.get("case_id") or f"index_{idx}"
    first = _get_first_final_tuple(record)
    selected_tuple_str = "None"
    if first:
        _a, term_norm, pol = first
        selected_tuple_str = f"(aspect_term_norm={repr(term_norm)}, polarity={repr(pol)})"
    judgement, j_idx = get_selected_judgement(record)
    selected_judgement_idx = j_idx if j_idx is not None else "None"
    bucket = rq1_grounding_bucket(record)
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    n_align = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_ALIGNMENT_FAILURE)
    n_filter = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_FILTER_REJECTION)
    n_semantic = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_SEMANTIC_HALLUCINATION)

    print(f"text_id: {text_id}")
    print(f"selected_tuple: {selected_tuple_str}")
    print(f"selected_judgement_idx: {selected_judgement_idx}")
    print(f"rq1_bucket: {bucket}")
    print(f"drop_reason_counts: alignment_failure={n_align}, filter_rejection={n_filter}, semantic_hallucination={n_semantic}")


if __name__ == "__main__":
    main()
