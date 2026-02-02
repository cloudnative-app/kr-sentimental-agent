#!/usr/bin/env python3
"""
Run debate override ablation:
 - proposed (override ON)
 - abl_no_debate_override (override OFF)
Then build structural metrics + HTML report for each.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, help="Base run_id (suffixes will be added).")
    ap.add_argument("--mode", default="proposed", help="Run mode (default: proposed).")
    ap.add_argument("--profile", default="smoke", help="Profile for metrics (smoke|regression|paper_main).")
    ap.add_argument("--config", default="experiments/configs/test_small.yaml", help="Config for override ON run.")
    ap.add_argument(
        "--ablation-config",
        default="experiments/configs/abl_no_debate_override.yaml",
        help="Config for override OFF run.",
    )
    args = ap.parse_args()

    runs = [
        ("override_on", args.config),
        ("override_off", args.ablation_config),
    ]

    for suffix, cfg in runs:
        run_id = f"{args.run_id}_{suffix}"
        run_cmd(
            [
                sys.executable,
                "experiments/scripts/run_experiments.py",
                "--config",
                cfg,
                "--run-id",
                run_id,
                "--mode",
                args.mode,
            ]
        )
        run_dir = Path("results") / f"{run_id}_{args.mode}"
        run_cmd(
            [
                sys.executable,
                "scripts/structural_error_aggregator.py",
                "--input",
                str(run_dir / "scorecards.jsonl"),
                "--outdir",
                str(run_dir / "derived" / "metrics"),
                "--profile",
                args.profile,
            ]
        )
        run_cmd(
            [
                sys.executable,
                "scripts/build_metric_report.py",
                "--run_dir",
                str(run_dir),
                "--metrics_profile",
                args.profile,
            ]
        )

    print(f"[done] ablation runs created under results/ and reports/ (base run_id={args.run_id})")


if __name__ == "__main__":
    main()
