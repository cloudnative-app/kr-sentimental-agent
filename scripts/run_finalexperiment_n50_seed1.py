#!/usr/bin/env python3
"""
Finalexperiment n50 seed1: C1 / C2 / C3 / C2_eval_only 순차 실행.
T2(v2) 기본조건(finalexperiment): debate_override min_total=0.6, min_margin=0.3, min_target_conf=0.55, l3_conservative=false.
real n50 seed1 표본규칙·데이터 사용. run_pipeline(paper profile + with_metrics)로 실험 → 메트릭 → 페이퍼 프로파일 자동 순차 실행.

Usage:
  python scripts/run_finalexperiment_n50_seed1.py
  python scripts/run_finalexperiment_n50_seed1.py --conditions c1 c2
  python scripts/run_finalexperiment_n50_seed1.py --all
  python scripts/run_finalexperiment_n50_seed1.py --run-id-suffix v2
  python scripts/run_finalexperiment_n50_seed1.py --skip_dataset
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIGS = [
    ("c1", "experiments/configs/finalexperiment_n50_seed1_c1.yaml", "finalexperiment_n50_seed1_c1"),
    ("c2", "experiments/configs/finalexperiment_n50_seed1_c2.yaml", "finalexperiment_n50_seed1_c2"),
    ("c2_1", "experiments/configs/finalexperiment_n50_seed1_c2_1.yaml", "finalexperiment_n50_seed1_c2_1"),
    ("c3", "experiments/configs/finalexperiment_n50_seed1_c3.yaml", "finalexperiment_n50_seed1_c3"),
    ("c2_eval_only", "experiments/configs/finalexperiment_n50_seed1_c2_eval_only.yaml", "finalexperiment_n50_seed1_c2_eval_only"),
]


def run_cmd(cmd: list[str], cwd: Path | None = None, desc: str = "") -> bool:
    cwd = cwd or _PROJECT_ROOT
    print(f"[run] {desc or ' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(cwd), shell=False)
    ok = r.returncode == 0
    if not ok:
        print(f"[FAIL] exit code {r.returncode}", file=sys.stderr)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Finalexperiment n50 seed1: C1/C2/C3/C2_eval_only run_pipeline(paper + metrics) 순차 실행"
    )
    ap.add_argument(
        "--conditions",
        nargs="+",
        metavar="C",
        help="Run only these: c1 c2 c3 c2_eval_only (default: all)",
    )
    ap.add_argument("--all", action="store_true", help="Run all four (default when no --conditions)")
    ap.add_argument(
        "--run-id-suffix",
        type=str,
        default="",
        help="Suffix for run_id (e.g. v2 -> finalexperiment_n50_seed1_c1_v2). 아이디 겹치지 않게.",
    )
    ap.add_argument(
        "--skip_dataset",
        action="store_true",
        help="Skip dataset creation (real_n50_seed1 already exists)",
    )
    ap.add_argument(
        "--skip_summary",
        action="store_true",
        help="Skip build_memory_condition_summary after runs",
    )
    args = ap.parse_args()

    root = _PROJECT_ROOT
    suffix = (args.run_id_suffix or "").strip()
    suffix_part = f"_{suffix}" if suffix else ""

    if args.conditions:
        want = set(c.strip().lower().replace("-", "_") for c in args.conditions)
        configs = [(k, p, rid) for k, p, rid in CONFIGS if k in want]
        if len(configs) != len(want):
            unknown = want - {k for k, _, _ in configs}
            print(f"[FAIL] unknown condition(s): {unknown}. allowed: c1, c2, c2_1, c3, c2_eval_only", file=sys.stderr)
            return 1
    else:
        configs = list(CONFIGS)

    if not args.skip_dataset:
        if not run_cmd(
            [
                sys.executable,
                "scripts/make_real_n100_seed1_dataset.py",
                "--valid_size", "50",
                "--seed", "1",
                "--outdir", "experiments/configs/datasets/real_n50_seed1",
            ],
            cwd=root,
            desc="make_real_n100_seed1_dataset (real_n50_seed1)",
        ):
            return 1

    for label, config_rel, run_id_base in configs:
        config_path = root / config_rel
        if not config_path.exists():
            print(f"[FAIL] config not found: {config_path}", file=sys.stderr)
            return 1
        run_id = run_id_base + suffix_part
        if not run_cmd(
            [
                sys.executable,
                "scripts/run_pipeline.py",
                "--config", config_rel,
                "--run-id", run_id,
                "--mode", "proposed",
                "--profile", "paper",
                "--with_metrics",
                "--metrics_profile", "paper_main",
            ],
            cwd=root,
            desc=f"run_pipeline {label} ({config_rel}) run_id={run_id}",
        ):
            return 1

    if not args.skip_summary and configs:
        def _run_dir(base: str) -> str:
            return f"results/{base}{suffix_part}__seed1_proposed"
        run_dirs = []
        labels = {"c1": "C1", "c2": "C2", "c2_1": "C2_1", "c3": "C3", "c2_eval_only": "C2_eval_only"}
        for k, _, rid in CONFIGS:
            if any(c[0] == k for c in configs):
                run_dirs.append(f"{labels[k]}:{_run_dir(rid)}")
        if len(run_dirs) >= 2:
            summary_out = f"reports/finalexperiment_n50_seed1{suffix_part}_summary.md"
            if not run_cmd(
                [sys.executable, "scripts/build_memory_condition_summary.py", "--runs"] + run_dirs + ["--out", summary_out],
                cwd=root,
                desc="build_memory_condition_summary",
            ):
                print("[WARN] build_memory_condition_summary failed", file=sys.stderr)
            else:
                print(f"[OK] Summary: {summary_out}")

    print("\n[OK] Finalexperiment n50 seed1 pipeline done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
