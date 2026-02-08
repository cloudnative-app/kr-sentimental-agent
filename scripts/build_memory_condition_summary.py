"""
Build C1/C2/C3 memory condition summary table.

Reads structural_metrics.csv and scorecards.jsonl from each run dir and outputs
a single table with: condition, n, unsupported_polarity_rate, implicit_grounding_rate,
explicit_grounding_failure_rate, polarity_conflict_rate, risk_resolution_rate,
memory_prompt_injection_chars_mean (C3 truly silent 증명).

Usage:
  python scripts/build_memory_condition_summary.py --runs C1:results/run_c1 C2:results/run_c2 C3:results/run_c3
  python scripts/build_memory_condition_summary.py --runs C1:results/exp_c1 C2:results/exp_c2 C3:results/exp_c3 --out reports/memory_condition_summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_structural_metrics(csv_path: Path) -> Optional[Dict[str, Any]]:
    """Load single-row structural_metrics.csv; return dict of column -> value."""
    if not csv_path.exists():
        return None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return None
    row = rows[0]
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if v == "" or v is None:
            out[k] = None
            continue
        try:
            out[k] = float(v)
        except ValueError:
            out[k] = v
    out["n"] = int(out.get("n", 0))
    return out


def mean_prompt_injection_chars(scorecards_path: Path) -> Optional[float]:
    """Mean memory.prompt_injection_chars across scorecards; None if no file or no memory block."""
    if not scorecards_path.exists():
        return None
    chars: List[int] = []
    for line in scorecards_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            card = json.loads(line)
        except json.JSONDecodeError:
            continue
        mem = card.get("memory") if isinstance(card.get("memory"), dict) else {}
        c = mem.get("prompt_injection_chars")
        if c is not None:
            chars.append(int(c))
    if not chars:
        return None
    return sum(chars) / len(chars)


def build_summary_row(
    condition: str,
    run_dir: Path,
    root: Optional[Path] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    """
    Return (metrics_dict, mean_prompt_injection_chars) for the run.
    metrics_dict has: n, unsupported_polarity_rate, implicit_grounding_rate,
    explicit_grounding_failure_rate, polarity_conflict_rate, risk_resolution_rate.
    """
    root = root or _project_root()
    base = (root / run_dir).resolve() if not run_dir.is_absolute() else run_dir
    metrics_path = base / "derived" / "metrics" / "structural_metrics.csv"
    scorecards_path = base / "scorecards.jsonl"
    metrics = load_structural_metrics(metrics_path)
    mean_chars = mean_prompt_injection_chars(scorecards_path)
    return (metrics, mean_chars)


def format_rate(v: Any) -> str:
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return str(v)


def build_table(
    runs: List[Tuple[str, Path]],
    root: Optional[Path] = None,
) -> str:
    """Build markdown table string."""
    root = root or _project_root()
    cols = [
        "condition",
        "n",
        "unsupported_polarity_rate",
        "implicit_grounding_rate",
        "explicit_grounding_failure_rate",
        "polarity_conflict_rate",
        "risk_resolution_rate",
        "memory_prompt_injection_chars_mean",
    ]
    lines: List[str] = []
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines.append(header)
    lines.append(sep)
    for condition, run_dir in runs:
        metrics, mean_chars = build_summary_row(condition, run_dir, root=root)
        if metrics is None:
            row_vals = [condition, "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", format_rate(mean_chars)]
        else:
            row_vals = [
                condition,
                str(metrics.get("n", "N/A")),
                format_rate(metrics.get("unsupported_polarity_rate")),
                format_rate(metrics.get("implicit_grounding_rate")),
                format_rate(metrics.get("explicit_grounding_failure_rate")),
                format_rate(metrics.get("polarity_conflict_rate")),
                format_rate(metrics.get("risk_resolution_rate")),
                format_rate(mean_chars),
            ]
        lines.append("| " + " | ".join(row_vals) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build C1/C2/C3 memory condition summary table")
    ap.add_argument(
        "--runs",
        type=str,
        nargs="+",
        required=True,
        help="Pairs CONDITION:DIR e.g. C1:results/exp_c1 C2:results/exp_c2 C3:results/exp_c3",
    )
    ap.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path for markdown table (default: stdout)",
    )
    ap.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root for resolving relative run dirs",
    )
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else _project_root()
    runs: List[Tuple[str, Path]] = []
    for pair in args.runs:
        if ":" not in pair:
            runs.append((pair, Path(pair)))
            continue
        label, dir_path = pair.split(":", 1)
        runs.append((label.strip(), Path(dir_path.strip())))
    table = build_table(runs, root=root)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(table, encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print(table)


if __name__ == "__main__":
    main()
