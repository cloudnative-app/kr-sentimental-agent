#!/usr/bin/env python3
"""
CR-M0 vs CR-M1 vs CR-M2 (n=50, seeds 3) 순차 실행 파이프라인.

1. run_pipeline (M0, M1, M2) — mode proposed, profile paper, with_metrics, with_aggregate
2. compute_irr — 각 시드 run별 outputs.jsonl → irr/
3. export_paper_metrics_md — 시드별 paper_metrics.md, paper_metrics.csv
4. export_paper_metrics_aggregated — aggregated_mean_std.csv → paper_metrics_aggregated.md

Usage:
  python scripts/run_cr_m0_m1_m2_pipeline.py
  python scripts/run_cr_m0_m1_m2_pipeline.py --skip-pipeline
  python scripts/run_cr_m0_m1_m2_pipeline.py --conditions m0 m1
"""
from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS = PROJECT_ROOT / "results"

CONFIGS = [
    ("M0", "experiments/configs/cr_n50_m0.yaml", "cr_n50_m0"),
    ("M1", "experiments/configs/cr_n50_m1.yaml", "cr_n50_m1"),
    ("M2", "experiments/configs/cr_n50_m2.yaml", "cr_n50_m2"),
]


def run_cmd(cmd: list[str], cwd: Path | None = None, desc: str = "") -> bool:
    cwd = cwd or PROJECT_ROOT
    print(f"\n[run] {desc or ' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd), shell=False)
    ok = r.returncode == 0
    if not ok:
        print(f"[FAIL] exit code {r.returncode}", file=sys.stderr)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="CR-M0 vs CR-M1 vs CR-M2 pipeline: run_pipeline → compute_irr → export_paper_metrics",
    )
    ap.add_argument(
        "--conditions",
        nargs="+",
        metavar="C",
        choices=["m0", "m1", "m2"],
        help="Run only these: m0 m1 m2 (default: all)",
    )
    ap.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Skip run_pipeline (data already exists)",
    )
    ap.add_argument(
        "--skip-irr",
        action="store_true",
        help="Skip compute_irr",
    )
    ap.add_argument(
        "--skip-paper-metrics",
        action="store_true",
        help="Skip export_paper_metrics_md and export_paper_metrics_aggregated",
    )
    args = ap.parse_args()

    if args.conditions:
        want = set(c.strip().lower() for c in args.conditions)
        configs = [(k, p, rid) for k, p, rid in CONFIGS if k.lower() in want]
        if len(configs) != len(want):
            unknown = want - {k.lower() for k, _, _ in CONFIGS}
            print(f"[FAIL] unknown: {unknown}. allowed: m0, m1, m2", file=sys.stderr)
            return 1
    else:
        configs = list(CONFIGS)

    # Step 1: run_pipeline
    if not args.skip_pipeline:
        for label, config_rel, run_id in configs:
            config_path = PROJECT_ROOT / config_rel
            if not config_path.exists():
                print(f"[FAIL] config not found: {config_path}", file=sys.stderr)
                return 1
            if not run_cmd(
                [
                    sys.executable,
                    "scripts/run_pipeline.py",
                    "--config", config_rel,
                    "--run-id", run_id,
                    "--mode", "proposed",
                    "--profile", "paper",
                    "--with_metrics",
                    "--with_aggregate",
                ],
                cwd=PROJECT_ROOT,
                desc=f"run_pipeline {label} ({config_rel}) run_id={run_id}",
            ):
                return 1

    # Step 2: compute_irr (per seed run)
    if not args.skip_irr:
        for label, _, run_id in configs:
            pattern = str(RESULTS / f"{run_id}__seed*_proposed")
            run_dirs = sorted(glob.glob(pattern))
            for run_dir in run_dirs:
                rd = Path(run_dir)
                outputs = rd / "outputs.jsonl"
                if not outputs.exists():
                    print(f"[WARN] skipping IRR (no outputs): {rd.name}", file=sys.stderr)
                    continue
                outdir = rd / "irr"
                scorecards = rd / "scorecards.jsonl"
                cmd = [
                    sys.executable,
                    "scripts/compute_irr.py",
                    "--input", str(outputs),
                    "--outdir", str(outdir),
                ]
                if scorecards.exists():
                    cmd.extend(["--scorecards", str(scorecards)])
                if not run_cmd(
                    cmd,
                    cwd=PROJECT_ROOT,
                    desc=f"compute_irr {rd.name}",
                ):
                    print(f"[WARN] compute_irr failed for {rd.name}", file=sys.stderr)

    # Step 3 & 4: export_paper_metrics_md, export_paper_metrics_aggregated
    if not args.skip_paper_metrics:
        for label, _, run_id in configs:
            if not run_cmd(
                [
                    sys.executable,
                    "scripts/export_paper_metrics_md.py",
                    "--base-run-id", run_id,
                    "--mode", "proposed",
                ],
                cwd=PROJECT_ROOT,
                desc=f"export_paper_metrics_md {run_id}",
            ):
                print(f"[WARN] export_paper_metrics_md failed for {run_id}", file=sys.stderr)

            agg_path = RESULTS / f"{run_id}_aggregated" / "aggregated_mean_std.csv"
            if agg_path.exists():
                pattern = str(RESULTS / f"{run_id}__seed*_proposed")
                run_dirs = sorted(glob.glob(pattern))
                cmd = [
                    sys.executable,
                    "scripts/export_paper_metrics_aggregated.py",
                    "--agg-path", str(agg_path),
                ]
                if run_dirs:
                    cmd.extend(["--run-dirs"] + run_dirs)
                if not run_cmd(
                    cmd,
                    cwd=PROJECT_ROOT,
                    desc=f"export_paper_metrics_aggregated {run_id}",
                ):
                    print(f"[WARN] export_paper_metrics_aggregated failed for {run_id}", file=sys.stderr)
            else:
                print(f"[WARN] aggregated_mean_std.csv not found: {agg_path}", file=sys.stderr)

    print("\n[OK] CR-M0/M1/M2 pipeline done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
