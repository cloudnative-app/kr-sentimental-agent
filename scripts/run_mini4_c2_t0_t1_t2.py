#!/usr/bin/env python3
"""
Mini4 C2 T0/T1/T2: 같은 10샘플(seed 42)로 C2만 3조건 연속 실행.

- T0: 현재 (min_total=1.6, min_margin=0.8, min_target_conf=0.7, l3_conservative=true)
- T1: 완화 (min_total=1.0, min_margin=0.5, min_target_conf=0.6, l3_conservative=true)
- T2: 매우 완화 (min_total=0.6, min_margin=0.3, min_target_conf=0.55, l3_conservative=false)

목표: override_applied_rate 0 → T1>0 → T2 크게 증가 여부로 게이트(역치) 과다 원인 확정.
결과: results/<run_id>_proposed, override_gate_debug.jsonl, override_gate_debug_summary.json, structural_metrics.
항상 --run-id를 넘겨 config와 무관하게 출력 디렉터리가 t0/t1/t2(및 suffix)로만 결정되도록 함.

Usage:
  python scripts/run_mini4_c2_t0_t1_t2.py
  python scripts/run_mini4_c2_t0_t1_t2.py --run-id-suffix v2     # 아이디 분리 (experiment_mini4_validation_c2_t0_v2_proposed 등)
  python scripts/run_mini4_c2_t0_t1_t2.py --skip_run
  python scripts/run_mini4_c2_t0_t1_t2.py --skip_run --run-id-suffix v2
  python scripts/run_mini4_c2_t0_t1_t2.py --skip_regression     # 실험+체크리스트만, 회귀테스트 생략

PowerShell (아이디 분리 예시):
  .\scripts\run_mini4_c2_t0_t1_t2.ps1
  .\scripts\run_mini4_c2_t0_t1_t2.ps1 -RunIdSuffix v2
  .\scripts\run_mini4_c2_t0_t1_t2.ps1 -RunIdSuffix (Get-Date -Format "yyyyMMdd_HHmm")
  .\scripts\run_mini4_c2_t0_t1_t2.ps1 -SkipRun -RunIdSuffix v2
  .\scripts\run_mini4_c2_t0_t1_t2.ps1 -SkipRegression
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIGS = [
    ("t0", "experiments/configs/experiment_mini4_validation_c2_t0.yaml"),
    ("t1", "experiments/configs/experiment_mini4_validation_c2_t1.yaml"),
    ("t2", "experiments/configs/experiment_mini4_validation_c2_t2.yaml"),
]


def run_cmd(cmd: list[str], cwd: Path | None = None, env: dict | None = None, desc: str = "") -> bool:
    cwd = cwd or _PROJECT_ROOT
    print(f"[run] {desc or ' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd), shell=False, env=env)
    ok = r.returncode == 0
    if not ok:
        print(f"[FAIL] exit code {r.returncode}", file=sys.stderr)
    return ok


def main() -> int:
    print("Mini4 C2 T0/T1/T2 pipeline starting...")
    ap = argparse.ArgumentParser(description="Mini4 C2 T0/T1/T2 run + metrics + checklist + 02829 regression tests")
    ap.add_argument("--skip_run", action="store_true", help="Skip experiment run (only metrics + checklist + regression)")
    ap.add_argument("--run-id-suffix", type=str, default="", help="Suffix for run_id (e.g. 'v2' -> experiment_mini4_validation_c2_t0_v2_proposed). 아이디 겹치지 않게 할 때 사용.")
    ap.add_argument("--skip_regression", action="store_true", help="Skip 02829 regression tests after checklist")
    ap.add_argument("--out", default="reports/mini4_c2_t0_t1_t2_checklist.md", help="Checklist report path")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    results_dir = root / "results"
    suffix = (args.run_id_suffix or "").strip()
    suffix_part = f"_{suffix}" if suffix else ""
    run_dirs: list[tuple[str, str]] = []  # (label, run_id_proposed)

    if not args.skip_run:
        for label, config in CONFIGS:
            cfg_path = root / config
            if not cfg_path.exists():
                print(f"[FAIL] config not found: {cfg_path}", file=sys.stderr)
                return 1
            run_id_base = cfg_path.stem  # e.g. experiment_mini4_validation_c2_t0
            run_id_override = f"{run_id_base}{suffix_part}"
            run_id_mode = f"{run_id_override}_proposed"
            cmd = [
                sys.executable,
                "experiments/scripts/run_experiments.py",
                "--config", config,
                "--run-id", run_id_override,
            ]
            if not run_cmd(
                cmd,
                cwd=root,
                desc=f"run_experiments {label} ({config}) run_id={run_id_override}",
            ):
                return 1
            run_dirs.append((label, run_id_mode))
    else:
        run_dirs = [
            ("t0", f"experiment_mini4_validation_c2_t0{suffix_part}_proposed"),
            ("t1", f"experiment_mini4_validation_c2_t1{suffix_part}_proposed"),
            ("t2", f"experiment_mini4_validation_c2_t2{suffix_part}_proposed"),
        ]

    for label, run_id_mode in run_dirs:
        run_dir = results_dir / run_id_mode
        scorecards = run_dir / "scorecards.jsonl"
        if not scorecards.exists():
            print(f"[SKIP] {label}: no scorecards at {scorecards}", file=sys.stderr)
            continue
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
            desc=f"aggregator {label}",
        ):
            print(f"[WARN] aggregator failed for {label}, continuing.", file=sys.stderr)

    run_dir_by_label = {label: results_dir / run_id_mode for label, run_id_mode in run_dirs}
    t0_dir = run_dir_by_label.get("t0")
    t1_dir = run_dir_by_label.get("t1")
    t2_dir = run_dir_by_label.get("t2")
    if not t0_dir or not t1_dir or not t2_dir:
        print("[WARN] Missing one of t0/t1/t2 dirs; checklist may be partial.", file=sys.stderr)

    checklist_out = args.out
    if suffix and checklist_out == "reports/mini4_c2_t0_t1_t2_checklist.md":
        checklist_out = f"reports/mini4_c2_t0_t1_t2_checklist_{suffix}.md"
    if not run_cmd(
        [
            sys.executable,
            "scripts/checklist_override_gate_t0_t1_t2.py",
            "--t0_dir", str(t0_dir or results_dir / "experiment_mini4_validation_c2_t0_proposed"),
            "--t1_dir", str(t1_dir or results_dir / "experiment_mini4_validation_c2_t1_proposed"),
            "--t2_dir", str(t2_dir or results_dir / "experiment_mini4_validation_c2_t2_proposed"),
            "--out", checklist_out,
        ],
        cwd=root,
        desc="checklist_override_gate_t0_t1_t2",
    ):
        return 1

    if not args.skip_regression and t1_dir and t2_dir:
        env = os.environ.copy()
        env["REGRESSION_02829_RUN_DIR"] = str(t2_dir)
        env["REGRESSION_02829_T1_RUN_DIR"] = str(t1_dir)
        if not run_cmd(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_02829_regression.py",
                "-v",
                "--tb=short",
            ],
            cwd=root,
            env=env,
            desc="pytest 02829 regression (T2 + T1 L3 block)",
        ):
            print("[FAIL] 02829 regression tests failed.", file=sys.stderr)
            return 1
        print("[OK] 02829 regression tests passed.")
    elif args.skip_regression:
        print("[SKIP] Regression tests (--skip_regression).")

    out_path = root / checklist_out
    if out_path.exists():
        print(f"\n[OK] Checklist report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
