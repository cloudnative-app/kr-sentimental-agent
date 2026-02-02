#!/usr/bin/env python3
"""
E2E 실험 결과 통합: 스냅샷·논문 테이블·HTML 리포트·메트릭을 한 번에 생성.

사용 패턴:
  (1) 단일 런 통합: run_experiments 후 산출물·레포트·메트릭까지 일원화
  (2) N회 반복 런: merged_scorecards.jsonl 기준으로 메트릭만 생성 (self-consistency 등)

Usage:
  # 단일 런 (스냅샷 + paper 테이블 + HTML + 메트릭)
  python scripts/experiment_results_integrate.py --run_dir results/my_run_proposed --with_metrics

  # N회 반복 merged scorecards → 메트릭
  python scripts/experiment_results_integrate.py --merged_scorecards results/my_run_proposed/scorecards_3runs.jsonl --outdir results/metrics --profile paper_main
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd: list[str], step: str) -> bool:
    print(f"\n[STEP] {step}")
    print(" ".join(cmd))
    r = subprocess.run(cmd, cwd=PROJECT_ROOT, check=False)
    if r.returncode != 0:
        print(f"[FAIL] {step} exit code {r.returncode}")
        return False
    print(f"[OK]   {step}")
    return True


def main():
    ap = argparse.ArgumentParser(
        description="E2E experiment results integration: snapshot + paper tables + HTML report + metrics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run_dir", type=str, help="Single run directory (e.g. results/my_run_proposed)")
    g.add_argument(
        "--merged_scorecards",
        type=str,
        help="Path to merged scorecards (e.g. scorecards_3runs.jsonl) for N-run metrics only",
    )

    ap.add_argument(
        "--with_metrics",
        action="store_true",
        help="[--run_dir only] Run structural_error_aggregator on run scorecards",
    )
    ap.add_argument(
        "--metrics_profile",
        default="paper_main",
        choices=["smoke", "regression", "paper_main"],
        help="Profile for structural_error_aggregator",
    )
    ap.add_argument(
        "--outdir",
        type=str,
        default="results/metrics",
        help="[--merged_scorecards only] Output directory for metrics CSV/MD",
    )
    ap.add_argument(
        "--profile",
        default="paper_main",
        choices=["smoke", "regression", "paper_main"],
        help="[--merged_scorecards only] Same as metrics_profile",
    )
    ap.add_argument("--force_paper_tables", action="store_true", help="Pass --force to build_paper_tables")
    ap.add_argument("--report_profile", default="ops", choices=["ops", "paper"], help="HTML report profile when using --run_dir")

    args = ap.parse_args()
    py = sys.executable

    if args.merged_scorecards:
        # N-run: metrics only from merged scorecards
        merged = Path(args.merged_scorecards)
        if not merged.exists():
            print(f"[ERROR] Not found: {merged}")
            sys.exit(1)
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            py, "scripts/structural_error_aggregator.py",
            "--input", str(merged),
            "--outdir", str(outdir),
            "--profile", args.profile,
        ]
        if not run_cmd(cmd, "structural_error_aggregator"):
            sys.exit(1)
        print(f"\nMetrics written to: {outdir}")
        sys.exit(0)

    # Single run: snapshot + paper tables + HTML + optional metrics
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"[ERROR] Not a directory: {run_dir}")
        sys.exit(1)

    reports_dir = PROJECT_ROOT / "reports" / run_dir.name
    derived_dir = run_dir / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)

    # 1) Build run snapshot
    if not run_cmd(
        [py, "scripts/build_run_snapshot.py", "--run_dir", str(run_dir)],
        "build_run_snapshot",
    ):
        print("[WARN] build_run_snapshot failed, continuing...")

    # 2) Paper tables (if paper_outputs desired; check purpose in manifest)
    try:
        with open(run_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        purpose = (manifest.get("purpose") or "dev").lower()
    except Exception:
        purpose = "dev"

    if purpose in ("paper", "dev"):
        cmd_pt = [py, "scripts/build_paper_tables.py", "--run_dir", str(run_dir)]
        if args.force_paper_tables:
            cmd_pt.append("--force")
        rc = subprocess.run(cmd_pt, cwd=PROJECT_ROOT).returncode
        if rc == 0:
            print("[OK]   build_paper_tables")
        elif rc == 2:
            print("[SKIP] build_paper_tables (purpose smoke/sanity; use --force_paper_tables to override)")
        else:
            print("[WARN] build_paper_tables failed")

    # 3) HTML report
    report_profile = "paper" if purpose == "paper" else args.report_profile
    if not run_cmd(
        [
            py, "scripts/build_html_report.py",
            "--run_dir", str(run_dir),
            "--out_dir", str(reports_dir),
            "--profile", report_profile,
        ],
        "build_html_report",
    ):
        print("[WARN] build_html_report failed")

    # 4) Optional: structural_error_aggregator on run scorecards
    if args.with_metrics:
        scorecards = run_dir / "scorecards.jsonl"
        metrics_out = derived_dir / "metrics"
        metrics_out.mkdir(parents=True, exist_ok=True)
        if scorecards.exists():
            if not run_cmd(
                [
                    py, "scripts/structural_error_aggregator.py",
                    "--input", str(scorecards),
                    "--outdir", str(metrics_out),
                    "--profile", args.metrics_profile,
                ],
                "structural_error_aggregator",
            ):
                print("[WARN] structural_error_aggregator failed")
        else:
            print(f"[SKIP] structural_error_aggregator: {scorecards} not found")

    print(f"\nRun dir:   {run_dir}")
    print(f"Reports:   {reports_dir}")
    print(f"Derived:   {derived_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()
