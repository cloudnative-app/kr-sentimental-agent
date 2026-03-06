#!/usr/bin/env python3
"""
Export A table: run_summary.csv (condition × seed).

Input: structural_metrics.csv from each run.
Output: analysis_exports/run_summary.csv

Usage:
  python scripts/export_run_summary.py --run_dirs results/final_260306_s0__seed42_proposed,results/final_260306_s0__seed123_proposed
  python scripts/export_run_summary.py --base_run_id final_260306_s0 --seeds 42,123,456,789,1024 --mode proposed
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "")):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def infer_condition_from_run_dir(run_dir_name: str) -> str:
    """Infer S0/M0/M1/M0+nt/S0+Budget from run dir name (e.g. final_260306_s0__seed42_proposed)."""
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
    """Extract seed from run dir name (e.g. final_260306_s0__seed42_proposed -> 42)."""
    m = re.search(r"__seed(\d+)", run_dir_name)
    return m.group(1) if m else None


def load_structural_metrics(path: Path) -> Optional[Dict[str, Any]]:
    """Load first data row of structural_metrics.csv."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


# Required columns for run_summary
REQUIRED_COLS = [
    "condition", "seed", "macro_f1", "micro_f1", "schema_validity_rate",
    "conflict_rate", "fix_rate", "break_rate",
]
OPTIONAL_COLS = ["negative_f1", "neutral_f1", "seed_variance"]

# structural_metrics.csv -> run_summary column mapping
COL_MAP = {
    "macro_f1": "tuple_f1_s2_refpol",
    "micro_f1": "tuple_f1_s2_refpol_micro",
    "schema_validity_rate": "invalid_ref_rate",  # 1 - invalid_ref_rate
    "conflict_rate": "polarity_conflict_rate_after_rep",
    "fix_rate": "fix_rate_refpol",
    "break_rate": "break_rate_refpol",
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Export run_summary.csv (A table)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run_dirs", type=str, help="Comma-separated run dirs")
    g.add_argument("--base_run_id", type=str, help="Base run ID (e.g. final_260306_s0)")
    ap.add_argument("--seeds", type=str, help="Comma-separated seeds (required with --base_run_id)")
    ap.add_argument("--mode", type=str, default="proposed")
    ap.add_argument("--outdir", type=str, default=None, help="Output dir (default: analysis_exports)")
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
    out_path = outdir / "run_summary.csv"

    rows: List[Dict[str, Any]] = []
    for d in run_dirs:
        metrics_path = d / "derived" / "metrics" / "structural_metrics.csv"
        sm = load_structural_metrics(metrics_path)
        if sm is None:
            print(f"[WARN] Missing {metrics_path}")
            continue

        condition = infer_condition_from_run_dir(d.name)
        seed = parse_seed_from_run_dir(d.name) or ""

        row: Dict[str, Any] = {
            "condition": condition,
            "seed": seed,
        }

        # macro_f1, micro_f1
        macro_src = sm.get("tuple_f1_s2_refpol")
        micro_src = sm.get("tuple_f1_s2_refpol_micro")
        row["macro_f1"] = parse_float(macro_src) if macro_src not in (None, "", "N/A") else None
        row["micro_f1"] = parse_float(micro_src) if micro_src not in (None, "", "N/A") else None

        # schema_validity_rate = 1 - invalid_ref_rate
        inv_rate = parse_float(sm.get("invalid_ref_rate"))
        row["schema_validity_rate"] = (1.0 - inv_rate) if inv_rate is not None else None

        # conflict_rate, fix_rate, break_rate
        row["conflict_rate"] = parse_float(sm.get("polarity_conflict_rate_after_rep"))
        row["fix_rate"] = parse_float(sm.get("fix_rate_refpol"))
        row["break_rate"] = parse_float(sm.get("break_rate_refpol"))

        # Optional
        row["negative_f1"] = parse_float(sm.get("tuple_f1_s2_negative"))  # if exists
        row["neutral_f1"] = parse_float(sm.get("tuple_f1_s2_neutral"))  # if exists
        row["seed_variance"] = None  # from aggregated_mean_std if available

        rows.append(row)

    fieldnames = ["condition", "seed", "macro_f1", "micro_f1", "schema_validity_rate",
                  "conflict_rate", "fix_rate", "break_rate", "negative_f1", "neutral_f1", "seed_variance"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    print(f"[OK] Wrote {out_path} (n={len(rows)})")


if __name__ == "__main__":
    main()
