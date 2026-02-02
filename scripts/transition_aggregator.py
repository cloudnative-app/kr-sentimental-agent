#!/usr/bin/env python3
"""
Aggregate S1→S2 correctness transitions from scorecards (with correctness snapshot).

=== INPUT ===
  --input PATH (required)
      Scorecards JSONL (merged_scorecards.jsonl or scorecards.jsonl).
      Rows must include "correctness" or "triplet_correctness" (label experiments only).
  --outdir PATH (default: results/metrics)
      Directory to write transition_summary.json and transition_table.csv.
  --profile {smoke|regression|paper_main} (optional)
      Filter rows by scorecard field "profile" (or meta.profile) before aggregating.

  Correctness source (one of):
    - correctness.stage1.is_correct, correctness.stage2.is_correct (sample-level)
    - triplet_correctness: sample-level C1/C2 = all(t.stage1_correct), all(t.stage2_correct)

=== OUTPUT ===
  <outdir>/transition_summary.json
      { n_fix, n_keep, n_break, n_still, n_total, fix_rate, keep_rate, break_rate, still_wrong_rate }
  <outdir>/transition_table.csv
      Rows: Fix, Keep, Break, Still Wrong (count, rate).

  Transition logic:
    Fix         = S1 오답 → S2 정답   : C1=0, C2=1  → n_fix
    Keep        = S1 정답 → S2 정답 유지 : C1=1, C2=1  → n_keep
    Break       = S1 정답 → S2 오답(망침) : C1=1, C2=0  → n_break
    Still Wrong = S1 오답 → S2 오답 유지 : C1=0, C2=0  → n_still

Usage:
  python scripts/transition_aggregator.py --input results/my_run/scorecards.jsonl --outdir results/my_run/derived/metrics --profile paper_main
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def get_sample_correctness(record: Dict[str, Any]) -> Optional[Tuple[bool, bool]]:
    """
    Return (C1, C2) for sample: stage1 correct, stage2 correct.
    Returns None if correctness/triplet_correctness not present.
    """
    # 1) Sample-level correctness block
    correctness = record.get("correctness")
    if isinstance(correctness, dict):
        s1 = correctness.get("stage1")
        s2 = correctness.get("stage2")
        if isinstance(s1, dict) and isinstance(s2, dict):
            c1 = s1.get("is_correct")
            c2 = s2.get("is_correct")
            if c1 is not None and c2 is not None:
                return (bool(c1), bool(c2))

    # 2) Derive from triplet_correctness: sample correct iff all triplets correct
    triplets = record.get("triplet_correctness")
    if isinstance(triplets, list) and len(triplets) > 0:
        c1_all = all(
            bool(t.get("stage1_correct", False)) for t in triplets if isinstance(t, dict)
        )
        c2_all = all(
            bool(t.get("stage2_correct", False)) for t in triplets if isinstance(t, dict)
        )
        return (c1_all, c2_all)

    return None


def aggregate_transitions(
    rows: List[Dict[str, Any]],
    profile_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute n_fix, n_keep, n_break, n_still and rates."""
    if profile_filter:
        rows = [r for r in rows if (r.get("profile") or (r.get("meta") or {}).get("profile")) == profile_filter]

    n_fix = n_keep = n_break = n_still = 0
    for r in rows:
        pair = get_sample_correctness(r)
        if pair is None:
            continue
        c1, c2 = pair
        if not c1 and c2:
            n_fix += 1
        elif c1 and c2:
            n_keep += 1
        elif c1 and not c2:
            n_break += 1
        else:
            n_still += 1

    n_total = n_fix + n_keep + n_break + n_still
    if n_total == 0:
        return {
            "n_fix": 0,
            "n_keep": 0,
            "n_break": 0,
            "n_still": 0,
            "n_total": 0,
            "n_skipped": len(rows) - n_total,
            "fix_rate": None,
            "keep_rate": None,
            "break_rate": None,
            "still_wrong_rate": None,
        }

    def rate(num: int, denom: int) -> float:
        return (num / denom) if denom else 0.0

    return {
        "n_fix": n_fix,
        "n_keep": n_keep,
        "n_break": n_break,
        "n_still": n_still,
        "n_total": n_total,
        "n_skipped": len(rows) - n_total,
        "fix_rate": rate(n_fix, n_total),
        "keep_rate": rate(n_keep, n_total),
        "break_rate": rate(n_break, n_total),
        "still_wrong_rate": rate(n_still, n_total),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Aggregate S1→S2 correctness transitions from scorecards")
    ap.add_argument("--input", required=True, help="Path to scorecards.jsonl (or merged_scorecards.jsonl)")
    ap.add_argument("--outdir", default="results/metrics", help="Output directory for transition_summary.json and transition_table.csv")
    ap.add_argument("--profile", choices=["smoke", "regression", "paper_main"], default=None, help="Filter by profile")
    args = ap.parse_args()

    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        print(f"No records in {path}")
        return

    summary = aggregate_transitions(rows, args.profile)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # transition_summary.json
    summary_path = outdir / "transition_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Wrote {summary_path}")

    # transition_table.csv: transition_type, meaning, count, rate
    table_path = outdir / "transition_table.csv"
    table_rows = [
        ("Fix", "S1 오답 → S2 정답", summary["n_fix"], summary.get("fix_rate")),
        ("Keep", "S1 정답 → S2 정답 유지", summary["n_keep"], summary.get("keep_rate")),
        ("Break", "S1 정답 → S2 오답(망침)", summary["n_break"], summary.get("break_rate")),
        ("Still Wrong", "S1 오답 → S2 오답 유지", summary["n_still"], summary.get("still_wrong_rate")),
    ]
    with table_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["transition_type", "meaning", "count", "rate"])
        for row in table_rows:
            rate_val = row[3] if row[3] is not None else ""
            w.writerow([row[0], row[1], row[2], rate_val])
    print(f"Wrote {table_path}")


if __name__ == "__main__":
    main()
