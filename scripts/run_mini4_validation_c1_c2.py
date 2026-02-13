#!/usr/bin/env python3
"""
Mini4 validation: C1 / C2 / C3 / C2_eval_only 중 선택해 순차 실행, 메트릭 생성, 체크리스트 검토.

지원 조건: c1, c2, c3, c2_eval_only
- C1: no memory
- C2: debate + memory (주입)
- C3: retrieval-only (주입 없음, v1_1 C2_silent)
- C2_eval_only: retrieval + 주입 마스킹, store 미저장 (v1_2)

Usage:
  python scripts/run_mini4_validation_c1_c2.py --conditions c1 c2
  python scripts/run_mini4_validation_c1_c2.py --all
  python scripts/run_mini4_validation_c1_c2.py --conditions c1 c2 c3 c2_eval_only
  python scripts/run_mini4_validation_c1_c2.py --skip_run --conditions c1 c2 c3 c2_eval_only
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONDITION_CONFIGS: dict[str, str] = {
    "c1": "experiments/configs/experiment_mini4_validation_c1.yaml",
    "c2": "experiments/configs/experiment_mini4_validation_c2.yaml",
    "c3": "experiments/configs/experiment_mini4_validation_c3.yaml",
    "c2_eval_only": "experiments/configs/experiment_mini4_validation_c2_eval_only.yaml",
}

# run_id_mode = config stem + _proposed
def _config_stem_to_run_id(stem: str) -> str:
    return stem + "_proposed"


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
        description="Mini4 validation: C1/C2/C3/C2_eval_only run + metrics + checklist"
    )
    ap.add_argument(
        "--conditions",
        nargs="+",
        metavar="C",
        help="Run only these conditions: c1 c2 c3 c2_eval_only (space-separated)",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Run all four: c1, c2, c3, c2_eval_only",
    )
    ap.add_argument("--out", default="reports/mini4_validation_checklist.md", help="Checklist report path")
    ap.add_argument("--skip_run", action="store_true", help="Skip experiment run (only metrics + checklist)")
    args = ap.parse_args()

    root = _PROJECT_ROOT

    if args.all:
        condition_keys = ["c1", "c2", "c3", "c2_eval_only"]
    elif args.conditions:
        condition_keys = [c.strip().lower().replace("-", "_") for c in args.conditions]
        for c in condition_keys:
            if c not in CONDITION_CONFIGS:
                print(f"[FAIL] unknown condition: {c}. allowed: {list(CONDITION_CONFIGS.keys())}", file=sys.stderr)
                return 1
    else:
        condition_keys = ["c1", "c2"]

    configs = [(k, CONDITION_CONFIGS[k]) for k in condition_keys]
    run_dirs: list[tuple[str, str]] = []  # (label, run_id_proposed)

    if not args.skip_run:
        for label, config in configs:
            cfg_path = root / config
            if not cfg_path.exists():
                print(f"[FAIL] config not found: {cfg_path}", file=sys.stderr)
                return 1
            if not run_cmd(
                [sys.executable, "experiments/scripts/run_experiments.py", "--config", config],
                cwd=root,
                desc=f"run_experiments {label} ({config})",
            ):
                return 1
            run_id_mode = _config_stem_to_run_id(cfg_path.stem)
            run_dirs.append((label, run_id_mode))
    else:
        run_dirs = [(label, _config_stem_to_run_id(Path(config).stem)) for label, config in configs]

    results_dir = root / "results"
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
            desc=f"aggregator + triptych {label}",
        ):
            print(f"[WARN] aggregator failed for {label}, continuing.", file=sys.stderr)

    # Checklist: C1/C2 필수; C3, C2_eval_only는 있으면 전달
    run_dir_by_label = {label: results_dir / run_id_mode for label, run_id_mode in run_dirs}
    c1_dir = run_dir_by_label.get("c1") or (results_dir / run_dirs[0][1] if run_dirs else results_dir)
    c2_dir = run_dir_by_label.get("c2") or c1_dir
    c3_dir = run_dir_by_label.get("c3") if run_dir_by_label.get("c3") and run_dir_by_label["c3"].exists() else None
    c2_eval_dir = run_dir_by_label.get("c2_eval_only") if run_dir_by_label.get("c2_eval_only") and run_dir_by_label["c2_eval_only"].exists() else None

    cmd_review = [
        sys.executable,
        "scripts/validation_checklist_review.py",
        "--c1_dir", str(c1_dir),
        "--c2_dir", str(c2_dir),
        "--out", args.out,
    ]
    if c3_dir and c3_dir.exists():
        cmd_review.extend(["--c3_dir", str(c3_dir)])
    if c2_eval_dir and c2_eval_dir.exists():
        cmd_review.extend(["--c2_eval_only_dir", str(c2_eval_dir)])

    if not run_cmd(cmd_review, cwd=root, desc="validation_checklist_review"):
        return 1

    out_path = root / args.out
    if out_path.exists():
        print(f"\n[OK] Checklist report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
