#!/usr/bin/env python3
"""
Memory Growth Curve visualization — plots from memory_growth_metrics.jsonl.

Uses matplotlib (and seaborn if available). Generates figures for:
- store_size / coverage over window_end_sample
- mean_delta_risk_followed vs mean_delta_risk_ignored over time
- optional: mean_tuple_f1_s2, accuracy_rate when present

Usage:
  python analysis/plot_memory_growth.py --metrics results/<run_id>/memory_growth_metrics.jsonl --out results/<run_id>/memory_growth_plot.png
  python analysis/plot_memory_growth.py --metrics memory_growth_metrics.jsonl --out_dir reports/<run_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None

try:
    import seaborn as sns
    sns.set_theme(style="whitegrid", font_scale=1.0)
except ImportError:
    sns = None


def load_metrics(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def plot_memory_growth(rows: List[Dict[str, Any]], out_path: Path, title: str = "Memory Growth") -> None:
    """Always produce 3 panels: (1) store_size, (2) retrieval_hit_rate@k, (3) mean_delta_risk followed vs ignored. N/A when silent/off."""
    if not rows or plt is None:
        return
    x = [r.get("window_end_sample") for r in rows]
    if not x:
        return

    n_plots = 3
    fig, axes = plt.subplots(n_plots, 1, figsize=(10, 4 * n_plots), sharex=True)

    # 1) store_size curve
    ax = axes[0]
    store_vals = [_safe_float(r.get("store_size")) for r in rows]
    if any(v is not None for v in store_vals):
        y = [v if v is not None else float("nan") for v in store_vals]
        ax.plot(x, y, color="#2ecc71", marker="o", markersize=3, label="store_size")
        ax.set_ylabel("store_size")
        ax.set_title("Store size (accumulation)")
        ax.legend(loc="upper left")
    else:
        ax.text(0.5, 0.5, "N/A (e.g. memory off/silent)", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Store size (accumulation)")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("window_end_sample")

    # 2) retrieval_hit_rate@k curve
    ax = axes[1]
    retrieval_vals = [_safe_float(r.get("retrieval_hit_k")) for r in rows]
    if any(v is not None for v in retrieval_vals):
        y = [v if v is not None else float("nan") for v in retrieval_vals]
        ax.plot(x, y, color="#9b59b6", marker="o", markersize=3, label="retrieval_hit_k")
        ax.set_ylabel("retrieval_hit_k")
        ax.set_title("Retrieval Hit Rate@k")
        ax.legend(loc="upper left")
    else:
        ax.text(0.5, 0.5, "N/A (e.g. memory off/silent)", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Retrieval Hit Rate@k")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("window_end_sample")

    # 3) mean_delta_risk_followed vs mean_delta_risk_ignored
    ax = axes[2]
    dr_f = [_safe_float(r.get("mean_delta_risk_followed")) for r in rows]
    dr_i = [_safe_float(r.get("mean_delta_risk_ignored")) for r in rows]
    if any(v is not None for v in dr_f) or any(v is not None for v in dr_i):
        yf = [v if v is not None else float("nan") for v in dr_f]
        yi = [v if v is not None else float("nan") for v in dr_i]
        ax.plot(x, yf, color="#3498db", marker="s", markersize=3, label="mean_delta_risk (followed)")
        ax.plot(x, yi, color="#e74c3c", marker="^", markersize=3, label="mean_delta_risk (ignored)")
        ax.axhline(0, color="gray", linestyle="--", alpha=0.5)
        ax.set_ylabel("Δ risk")
        ax.set_title("Effect: Δ risk (followed vs ignored)")
        ax.legend(loc="best")
    else:
        ax.text(0.5, 0.5, "N/A (e.g. memory off/silent)", ha="center", va="center", transform=ax.transAxes)
        ax.set_title("Effect: Δ risk (followed vs ignored)")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("window_end_sample")

    fig.suptitle(title, fontsize=12, y=1.02)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot memory growth metrics from JSONL")
    p.add_argument("--metrics", required=True, type=Path, help="Path to memory_growth_metrics.jsonl")
    p.add_argument("--out", type=Path, default=None, help="Output image path (default: same dir as metrics, memory_growth_plot.png)")
    p.add_argument("--out_dir", type=Path, default=None, help="Output directory (overrides --out dir)")
    p.add_argument("--title", default="Memory Growth", help="Plot title")
    args = p.parse_args()

    if plt is None:
        print("matplotlib is required; install with: pip install matplotlib", file=sys.stderr)
        sys.exit(1)

    rows = load_metrics(args.metrics)
    if not rows:
        print("No rows in metrics file; skipping plot.", file=sys.stderr)
        sys.exit(0)

    out_path = args.out
    if out_path is None:
        if args.out_dir is not None:
            out_path = args.out_dir / "memory_growth_plot.png"
        else:
            out_path = args.metrics.parent / "memory_growth_plot.png"
    elif args.out_dir is not None:
        out_path = args.out_dir / (out_path.name if out_path.name else "memory_growth_plot.png")
    plot_memory_growth(rows, out_path, title=args.title)


if __name__ == "__main__":
    main()
