#!/usr/bin/env python3
"""Arbiter action type frequency per tuple_id (cr_n50_m0 M0)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    results_dir = PROJECT_ROOT / "results"
    base_run_id = "cr_n50_m0"
    mode = "proposed"
    seeds = ["42", "123", "456"]

    # action_type -> count of tuple_ids affected
    by_type: Dict[str, int] = {}
    # action_type -> count of actions (one action can target multiple tuple_ids)
    by_action_count: Dict[str, int] = {}
    total_tuple_ids = 0
    total_actions = 0

    for seed in seeds:
        path = results_dir / f"{base_run_id}__seed{seed}_{mode}" / "outputs.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            actions = (rec.get("analysis_flags") or {}).get("arb_actions") or []
            for a in actions:
                atype = (a.get("action_type") or a.get("type") or "KEEP").strip().upper()
                ids = a.get("target_tuple_ids") or []
                n = len(ids)
                by_type[atype] = by_type.get(atype, 0) + n
                by_action_count[atype] = by_action_count.get(atype, 0) + 1
                total_tuple_ids += n
                total_actions += 1

    print("Arbiter action frequency (cr_n50_m0, seeds 42,123,456 aggregated)")
    print("=" * 60)
    print("\nPer tuple_id (action_type applies to N tuple_ids):")
    print("-" * 40)
    for atype in sorted(by_type.keys(), key=lambda x: -by_type[x]):
        c = by_type[atype]
        pct = 100 * c / total_tuple_ids if total_tuple_ids else 0
        print(f"  {atype:8} : {c:5} tuple_ids ({pct:.1f}%)")
    print(f"  {'TOTAL':8} : {total_tuple_ids:5} tuple_ids")
    print("\nPer action (one action may target multiple tuple_ids):")
    print("-" * 40)
    for atype in sorted(by_action_count.keys(), key=lambda x: -by_action_count[x]):
        c = by_action_count[atype]
        print(f"  {atype:8} : {c:5} actions")
    print(f"  {'TOTAL':8} : {total_actions:5} actions")


if __name__ == "__main__":
    main()
