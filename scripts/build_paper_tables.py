#!/usr/bin/env python3
"""
Build IP&M-style paper Tables 1–4 from seed-level aggregated metrics.

Each row corresponds to one seed. Mean and SD are computed across seeds per condition.
Use after aggregate_seed_metrics has been run for each condition (C1, C2_silent, C2, C2_eval).

Usage:
  python scripts/build_paper_tables.py --base_run_id beta_n50 --report md --out reports/paper_tables.md
  python scripts/build_paper_tables.py --base_run_id finalexperiment_n50_seed1 --report md --out reports/paper_tables.md

Metric mapping (structural_metrics.csv fields):
  Table 1 (RQ1): unsupported_polarity_rate, severe_polarity_error_L3_rate, risk_resolution_rate
  Table 2 (RQ2): polarity_conflict_rate, tuple_agreement_rate, parse_generate_failure_rate (invalid_rate)
  Table 3: tuple_f1_s2_explicit_only
  Table 4: tuple_f1_s2_implicit_only (implicit_subset_F1), implicit_invalid_pred_rate (implicit_invalid_rate)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Condition display name -> run_id suffix (base_run_id + suffix)
CONDITION_SUFFIXES = {
    "C1": "_c1",
    "C2_silent": "_c3",  # C3 = C2_silent
    "C2": "_c2",
    "C2_eval": "_c2_eval_only",
}

# Table 1: Structural Error Control (RQ1)
TABLE1_METRICS = {
    "unsupported_polarity_rate": "unsupported_polarity_rate",
    "SeverePolarityErrorRate": "severe_polarity_error_L3_rate",
    "risk_resolution_rate": "risk_resolution_rate",
}

# Table 2: Inference Stability (RQ2)
TABLE2_METRICS = {
    "polarity_conflict_rate": "polarity_conflict_rate",
    "tuple_agreement_rate": "tuple_agreement_rate",
    "invalid_rate": "parse_generate_failure_rate",
}

# Table 3: Performance Constraint
TABLE3_METRICS = {
    "tuple_f1_s2": "tuple_f1_s2_explicit_only",
}

# Table 4: Implicit Subset
TABLE4_METRICS = {
    "implicit_subset_F1": "tuple_f1_s2_implicit_only",
    "implicit_invalid_rate": "implicit_invalid_pred_rate",
}

# Lower is better (for bold best)
LOWER_BETTER = {
    "unsupported_polarity_rate",
    "SeverePolarityErrorRate",
    "risk_resolution_rate",
    "polarity_conflict_rate",
    "invalid_rate",
    "implicit_invalid_rate",
}


def parse_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "")):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_csv_row(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def discover_seed_dirs(results_dir: Path, pattern: str) -> List[Path]:
    """Find dirs matching base_run_id__seed<N>_proposed."""
    if not results_dir.exists():
        return []
    # e.g. beta_n50_c1__seed42_proposed, beta_n50_c1__seed123_proposed
    escape = re.escape(pattern)
    regex = re.compile(rf"^{escape}__seed(\d+)_proposed$")
    dirs = []
    for d in results_dir.iterdir():
        if d.is_dir() and regex.match(d.name):
            dirs.append(d)
    return sorted(dirs, key=lambda x: int(re.search(r"__seed(\d+)_", x.name).group(1)))


def collect_per_seed_values(
    run_dirs: List[Path],
    csv_field: str,
) -> List[float]:
    """Extract csv_field from each run's structural_metrics.csv."""
    values = []
    for d in run_dirs:
        path = d / "derived" / "metrics" / "structural_metrics.csv"
        row = load_csv_row(path)
        if row is not None:
            v = parse_float(row.get(csv_field))
            if v is not None:
                values.append(v)
    return values


def mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n if n else 0
    std = variance ** 0.5
    return mean, std


def fmt_mean_sd(mean: float, std: float, bold: bool = False) -> str:
    if mean != mean:  # nan
        return "N/A"
    s = f"{mean:.4f} ({std:.4f})"
    return f"**{s}**" if bold else s


def compute_best_condition(
    condition_stats: Dict[str, Dict[str, Tuple[float, float]]],
    metrics: Dict[str, str],
    lower_better: set,
) -> Dict[str, str]:
    """Return best condition per metric key (display name)."""
    best: Dict[str, str] = {}
    for disp_key, csv_field in metrics.items():
        candidates = []
        for cond, stats in condition_stats.items():
            vals = stats.get(csv_field, (float("nan"), float("nan")))
            mean = vals[0]
            if mean == mean:  # not nan
                candidates.append((cond, mean))
        if not candidates:
            continue
        if disp_key in lower_better:
            best[disp_key] = min(candidates, key=lambda x: x[1])[0]
        else:
            best[disp_key] = max(candidates, key=lambda x: x[1])[0]
    return best


def build_table1(condition_stats: Dict[str, Dict], n_seeds: int) -> List[str]:
    lines = [
        "**Table 1. Structural Error Control (RQ1)**",
        "",
        "| Condition | unsupported_polarity_rate ↓ | SeverePolarityErrorRate ↓ | risk_resolution_rate ↑ |",
        "|-----------|----------------------------|---------------------------|------------------------|",
    ]
    best = compute_best_condition(
        condition_stats,
        TABLE1_METRICS,
        {"unsupported_polarity_rate", "SeverePolarityErrorRate", "risk_resolution_rate"},
    )
    for cond in ["C1", "C2_silent", "C2", "C2_eval"]:
        stats = condition_stats.get(cond, {})
        cells = [cond]
        for disp, csv_field in TABLE1_METRICS.items():
            mean, std = stats.get(csv_field, (float("nan"), float("nan")))
            bold = best.get(disp) == cond
            cells.append(fmt_mean_sd(mean, std, bold))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"*Values are mean (SD) over {n_seeds} seeds.*")
    return lines


def build_table2(condition_stats: Dict[str, Dict], n_seeds: int) -> List[str]:
    lines = [
        "**Table 2. Inference Stability (RQ2)**",
        "",
        "| Condition | polarity_conflict_rate ↓ | tuple_agreement_rate ↑ | invalid_rate ↓ |",
        "|-----------|-------------------------|------------------------|----------------|",
    ]
    best = compute_best_condition(
        condition_stats,
        TABLE2_METRICS,
        {"polarity_conflict_rate", "invalid_rate"},
    )
    for cond in ["C1", "C2_silent", "C2", "C2_eval"]:
        stats = condition_stats.get(cond, {})
        cells = [cond]
        for disp, csv_field in TABLE2_METRICS.items():
            mean, std = stats.get(csv_field, (float("nan"), float("nan")))
            bold = best.get(disp) == cond
            cells.append(fmt_mean_sd(mean, std, bold))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        f"*Values are mean (SD) over {n_seeds} seeds; metrics are computed per seed using repeated runs and then averaged.*"
    )
    return lines


def build_table3(condition_stats: Dict[str, Dict], n_seeds: int) -> List[str]:
    lines = [
        "**Table 3. Performance Constraint (Explicit-only F1)**",
        "",
        "| Condition | tuple_f1_s2 |",
        "|-----------|-------------|",
    ]
    best = compute_best_condition(
        condition_stats,
        TABLE3_METRICS,
        set(),
    )
    for cond in ["C1", "C2_silent", "C2", "C2_eval"]:
        stats = condition_stats.get(cond, {})
        csv_field = TABLE3_METRICS["tuple_f1_s2"]
        mean, std = stats.get(csv_field, (float("nan"), float("nan")))
        bold = best.get("tuple_f1_s2") == cond
        cells = [cond, fmt_mean_sd(mean, std, bold)]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(f"*Values are mean (SD) over {n_seeds} seeds.*")
    return lines


def build_table4(condition_stats: Dict[str, Dict], n_seeds: int) -> List[str]:
    lines = [
        "**Table 4. Implicit Subset Analysis**",
        "",
        "| Condition | implicit_subset_F1 ↑ | implicit_invalid_rate ↓ |",
        "|-----------|---------------------|--------------------------|",
    ]
    best = compute_best_condition(
        condition_stats,
        TABLE4_METRICS,
        {"implicit_invalid_rate"},
    )
    for cond in ["C1", "C2_silent", "C2", "C2_eval"]:
        stats = condition_stats.get(cond, {})
        cells = [cond]
        for disp, csv_field in TABLE4_METRICS.items():
            mean, std = stats.get(csv_field, (float("nan"), float("nan")))
            bold = best.get(disp) == cond
            cells.append(fmt_mean_sd(mean, std, bold))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        f"*Implicit subset metrics are computed at seed level and averaged. Values are mean (SD) over {n_seeds} seeds.*"
    )
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build IP&M-style paper Tables 1–4 from seed-level aggregated metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--base_run_id",
        type=str,
        required=True,
        help="Base run ID (e.g. beta_n50, finalexperiment_n50_seed1). Conditions: _c1, _c2, _c3, _c2_eval_only",
    )
    ap.add_argument(
        "--results_dir",
        type=str,
        default=None,
        help="Results directory (default: PROJECT_ROOT/results)",
    )
    ap.add_argument(
        "--report",
        type=str,
        choices=["md"],
        default="md",
        help="Output format (default: md)",
    )
    ap.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file (default: reports/paper_tables_<base_run_id>.md)",
    )
    ap.add_argument(
        "--conditions",
        type=str,
        default="C1,C2_silent,C2,C2_eval",
        help="Comma-separated conditions (default: C1,C2_silent,C2,C2_eval)",
    )
    args = ap.parse_args()

    results_dir = Path(args.results_dir) if args.results_dir else PROJECT_ROOT / "results"
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]

    condition_stats: Dict[str, Dict[str, Tuple[float, float]]] = {}
    n_seeds = 0

    all_metrics = {}
    for m in [TABLE1_METRICS, TABLE2_METRICS, TABLE3_METRICS, TABLE4_METRICS]:
        all_metrics.update(m)

    for cond in conditions:
        suffix = CONDITION_SUFFIXES.get(cond)
        if not suffix:
            print(f"[WARN] Unknown condition: {cond}, skipping.", file=sys.stderr)
            continue
        pattern = args.base_run_id + suffix
        run_dirs = discover_seed_dirs(results_dir, pattern)
        if not run_dirs:
            print(f"[WARN] No seed dirs found for {cond} (pattern: {pattern})", file=sys.stderr)
            condition_stats[cond] = {}
            continue
        if n_seeds == 0:
            n_seeds = len(run_dirs)
        stats = {}
        for disp, csv_field in all_metrics.items():
            values = collect_per_seed_values(run_dirs, csv_field)
            if values:
                stats[csv_field] = mean_std(values)
            else:
                stats[csv_field] = (float("nan"), float("nan"))
        condition_stats[cond] = stats

    if n_seeds == 0:
        print("[ERROR] No seed directories found for any condition.", file=sys.stderr)
        sys.exit(1)

    lines = [
        f"# Paper Tables — {args.base_run_id}",
        "",
        f"*n_seeds = {n_seeds}*",
        "",
    ]
    lines.extend(build_table1(condition_stats, n_seeds))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(build_table2(condition_stats, n_seeds))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(build_table3(condition_stats, n_seeds))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(build_table4(condition_stats, n_seeds))

    out_path = Path(args.out) if args.out else PROJECT_ROOT / "reports" / f"paper_tables_{args.base_run_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")


if __name__ == "__main__":
    main()
