#!/usr/bin/env python3
"""
C2 T0 1회 런 + polarity/final_tuples 체크리스트 파이프라인.

1. C2 T0 실험 1회 실행 (experiment_mini4_validation_c2_t0.yaml, 10샘플 seed 42)
2. structural_error_aggregator 실행 (override_gate_debug, structural_metrics)
3. checklist_polarity_final_tuples.py 실행 → reports/<run_id>_polarity_checklist.md

Usage:
  python scripts/run_c2_t0_and_checklist.py
  python scripts/run_c2_t0_and_checklist.py --skip_run   # 실험 생략, 기존 결과에 대해 2·3만 실행
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG = "experiments/configs/experiment_mini4_validation_c2_t0.yaml"
RUN_ID_PROPOSED = "experiment_mini4_validation_c2_t0_proposed"


def run_cmd(cmd: list[str], cwd: Path | None = None, desc: str = "") -> bool:
    cwd = cwd or _PROJECT_ROOT
    print(f"[run] {desc or ' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd), shell=False)
    ok = r.returncode == 0
    if not ok:
        print(f"[FAIL] exit code {r.returncode}", file=sys.stderr)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="C2 T0 1회 런 + polarity/final_tuples 체크리스트")
    ap.add_argument("--skip_run", action="store_true", help="실험 생략, 기존 결과에 대해 aggregator + checklist만 실행")
    ap.add_argument("--checklist_out", type=str, default="", help="체크리스트 출력 경로 (기본: reports/<run_id>_polarity_checklist.md)")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    results_dir = root / "results"
    run_dir = results_dir / RUN_ID_PROPOSED

    if not args.skip_run:
        cfg_path = root / CONFIG
        if not cfg_path.exists():
            print(f"[FAIL] config not found: {cfg_path}", file=sys.stderr)
            return 1
        if not run_cmd(
            [sys.executable, "experiments/scripts/run_experiments.py", "--config", CONFIG],
            cwd=root,
            desc=f"run_experiments C2 T0 ({CONFIG})",
        ):
            return 1

    scorecards = run_dir / "scorecards.jsonl"
    if not scorecards.exists():
        print(f"[FAIL] no scorecards at {scorecards}", file=sys.stderr)
        return 1

    outdir = run_dir / "derived" / "metrics"
    triptych_path = run_dir / "derived" / "tables" / "triptych_table.tsv"
    triptych_path.parent.mkdir(parents=True, exist_ok=True)
    if not run_cmd(
        [
            sys.executable,
            "scripts/structural_error_aggregator.py",
            "--input", str(scorecards),
            "--outdir", str(outdir),
            "--export_triptych_table", str(triptych_path),
            "--triptych_sample_n", "0",
            "--triptych_include_text", "1",
        ],
        cwd=root,
        desc="structural_error_aggregator",
    ):
        print("[WARN] aggregator failed, continuing with checklist.", file=sys.stderr)

    checklist_args = [
        sys.executable,
        "scripts/checklist_polarity_final_tuples.py",
        "--run_dir", str(run_dir),
    ]
    if args.checklist_out:
        checklist_args.extend(["--out", args.checklist_out])
    if not run_cmd(checklist_args, cwd=root, desc="checklist_polarity_final_tuples"):
        return 1

    out_path = root / (args.checklist_out or f"reports/{RUN_ID_PROPOSED}_polarity_checklist.md")
    if out_path.exists():
        print(f"\n[OK] Checklist report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
