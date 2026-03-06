#!/usr/bin/env python3
"""
Export C table: transition_metrics.csv (stage1→final per sample).

Input: triptych.csv from each run.
Output: analysis_exports/transition_metrics.csv

Calculation:
  stage1_tp = matches_stage1_vs_gold
  stage1_fp = stage1_n_pairs - stage1_tp
  stage1_fn = gold_n_pairs - stage1_tp
  final_tp = matches_final_vs_gold
  final_fp = final_n_pairs - final_tp
  final_fn = gold_n_pairs - final_tp
  fix_count = fix_flag, break_count = break_flag

Usage:
  python scripts/export_transition_metrics.py --run_dirs results/...
  python scripts/export_transition_metrics.py --base_run_id final_260306_s0 --seeds 42,123,456,789,1024 --mode proposed
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v)) if isinstance(v, (int, float)) else int(v)
    except (TypeError, ValueError):
        return 0


def infer_condition_from_run_dir(run_dir_name: str) -> str:
    base = run_dir_name.split("__seed")[0].lower() if "__seed" in run_dir_name else run_dir_name.lower()
    if "_s0_bg" in base or "s0_budget" in base or "_s0_bg_" in base:
        return "S0+Budget"
    if "_m0_nt" in base or "m0_nt" in base or "m0+nt" in base:
        return "M0+nt"
    if "_s0_" in base or base.startswith("s0_"):
        return "S0"
    if "_m1_" in base or base.startswith("m1_"):
        return "M1"
    if "_m0_" in base or base.startswith("m0_"):
        return "M0"
    return base or "unknown"


def parse_seed_from_run_dir(run_dir_name: str) -> Optional[str]:
    m = re.search(r"__seed(\d+)", run_dir_name)
    return m.group(1) if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Export transition_metrics.csv (C table)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run_dirs", type=str, help="Comma-separated run dirs")
    g.add_argument("--base_run_id", type=str, help="Base run ID")
    ap.add_argument("--seeds", type=str, help="Comma-separated seeds (required with --base_run_id)")
    ap.add_argument("--mode", type=str, default="proposed")
    ap.add_argument("--outdir", type=str, default=None)
    args = ap.parse_args()

    results_dir = PROJECT_ROOT / "results"
    if args.run_dirs:
        run_dirs = [
            Path(p.strip()).resolve() if (p.strip().startswith("/") or (len(p.strip()) > 1 and p.strip()[1] == ":"))
            else PROJECT_ROOT / p.strip()
            for p in args.run_dirs.split(",")
        ]
        run_dirs = [d if d.is_absolute() else PROJECT_ROOT / d for d in run_dirs]
        run_dirs = [d for d in run_dirs if d.is_dir()]
    else:
        seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
        run_dirs = [results_dir / f"{args.base_run_id}__seed{s}_{args.mode}" for s in seeds]
        run_dirs = [d for d in run_dirs if d.is_dir()]

    if not run_dirs:
        print("[ERROR] No run directories found.")
        sys.exit(1)

    outdir = Path(args.outdir) if args.outdir else PROJECT_ROOT / "analysis_exports"
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "transition_metrics.csv"

    fieldnames = [
        "condition", "seed", "sample_id",
        "stage1_tp", "stage1_fp", "stage1_fn",
        "final_tp", "final_fp", "final_fn",
        "fix_count", "break_count",
        "stage1_conflict_flag", "final_conflict_flag",
        "stage1_schema_valid_flag", "final_schema_valid_flag",
    ]
    all_rows: List[Dict[str, Any]] = []

    for d in run_dirs:
        triptych_path = d / "derived_subset" / "triptych.csv"
        if not triptych_path.exists():
            print(f"[WARN] Missing {triptych_path}")
            continue

        condition = infer_condition_from_run_dir(d.name)
        seed = parse_seed_from_run_dir(d.name) or ""

        with triptych_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                gold_n = parse_int(r.get("gold_n_pairs"))
                stage1_tp = parse_int(r.get("matches_stage1_vs_gold"))
                stage1_n = parse_int(r.get("stage1_n_pairs"))
                final_tp = parse_int(r.get("matches_final_vs_gold"))
                final_n = parse_int(r.get("final_n_pairs"))

                stage1_fp = max(0, stage1_n - stage1_tp)
                stage1_fn = max(0, gold_n - stage1_tp)
                final_fp = max(0, final_n - final_tp)
                final_fn = max(0, gold_n - final_tp)

                fix_count = parse_int(r.get("fix_flag"))
                break_count = parse_int(r.get("break_flag"))

                stage1_conflict = parse_int(r.get("polarity_conflict_raw"))
                final_conflict = parse_int(r.get("polarity_conflict_after_rep") or r.get("polarity_conflict_raw"))

                stage1_schema = r.get("stage1_schema_valid_flag")
                final_schema = r.get("final_schema_valid_flag")
                stage1_schema_valid_flag = parse_int(stage1_schema) if stage1_schema not in (None, "") else 1
                final_schema_valid_flag = parse_int(final_schema) if final_schema not in (None, "") else 1

                sample_id = r.get("text_id") or r.get("uid") or ""

                all_rows.append({
                    "condition": condition,
                    "seed": seed,
                    "sample_id": sample_id,
                    "stage1_tp": stage1_tp,
                    "stage1_fp": stage1_fp,
                    "stage1_fn": stage1_fn,
                    "final_tp": final_tp,
                    "final_fp": final_fp,
                    "final_fn": final_fn,
                    "fix_count": fix_count,
                    "break_count": break_count,
                    "stage1_conflict_flag": stage1_conflict,
                    "final_conflict_flag": final_conflict,
                    "stage1_schema_valid_flag": stage1_schema_valid_flag,
                    "final_schema_valid_flag": final_schema_valid_flag,
                })

    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(all_rows)

    print(f"[OK] Wrote {out_path} (n={len(all_rows)})")


if __name__ == "__main__":
    main()
