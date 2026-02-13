#!/usr/bin/env python3
"""
Triptych 테이블 생성 및 극성충돌(polarity_conflict) 집계.

1. structural_error_aggregator에 --export_triptych_table로 triptych_table.tsv 생성
2. triptych 행별 polarity_conflict_raw, polarity_conflict_after_rep 카운트

Usage:
  python scripts/generate_triptych_and_count_conflicts.py --run_dir results/beta_n50_c1__seed42_proposed
  python scripts/generate_triptych_and_count_conflicts.py --run_dirs results/beta_n50_c1__seed42_proposed,results/beta_n50_c2__seed42_proposed --out reports/triptych_polarity_conflict_counts.md
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def generate_triptych(run_dir: Path, profile: str = "paper_main") -> bool:
    """Run structural_error_aggregator with triptych export."""
    scorecards = run_dir / "scorecards.jsonl"
    outdir = run_dir / "derived" / "metrics"
    triptych_path = run_dir / "derived" / "tables" / "triptych_table.tsv"
    triptych_path.parent.mkdir(parents=True, exist_ok=True)

    if not scorecards.exists():
        print(f"[WARN] Missing {scorecards}", file=sys.stderr)
        return False

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "structural_error_aggregator.py"),
        "--input", str(scorecards),
        "--outdir", str(outdir),
        "--profile", profile,
        "--export_triptych_table", str(triptych_path),
        "--triptych_sample_n", "0",
        "--triptych_include_text", "1",
    ]
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"[WARN] aggregator failed: {r.stderr[:500]}", file=sys.stderr)
        return False
    return triptych_path.exists()


def count_polarity_conflict(triptych_path: Path) -> Tuple[int, int, int]:
    """
    Count polarity_conflict_raw=1 and polarity_conflict_after_rep=1 from triptych TSV.
    Returns (n_rows, n_polarity_conflict_raw, n_polarity_conflict_after_rep).
    """
    if not triptych_path.exists():
        return 0, 0, 0
    with triptych_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)
    n_raw = sum(1 for r in rows if r.get("polarity_conflict_raw") == "1")
    n_rep = sum(1 for r in rows if r.get("polarity_conflict_after_rep") == "1")
    return len(rows), n_raw, n_rep


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate triptych and count polarity conflicts")
    ap.add_argument("--run_dir", type=str, help="Single run directory")
    ap.add_argument("--run_dirs", type=str, help="Comma-separated run directories")
    ap.add_argument("--out", type=str, default=None, help="Output report path (optional)")
    ap.add_argument("--profile", type=str, default="paper_main")
    ap.add_argument("--no_generate", action="store_true", help="Skip triptych generation, only count if exists")
    args = ap.parse_args()

    if args.run_dir:
        run_dirs = [Path(args.run_dir).resolve()]
    elif args.run_dirs:
        run_dirs = [Path(p.strip()).resolve() for p in args.run_dirs.split(",") if p.strip()]
    else:
        ap.error("--run_dir or --run_dirs required")

    results: List[Tuple[str, int, int, int]] = []

    for run_dir in run_dirs:
        if not run_dir.is_dir():
            print(f"[WARN] Not a directory: {run_dir}", file=sys.stderr)
            continue
        triptych_path = run_dir / "derived" / "tables" / "triptych_table.tsv"

        if not args.no_generate:
            ok = generate_triptych(run_dir, args.profile)
            if not ok:
                print(f"[WARN] Triptych generation failed for {run_dir.name}", file=sys.stderr)
                results.append((run_dir.name, 0, 0, 0))
                continue

        n_rows, n_raw, n_rep = count_polarity_conflict(triptych_path)
        results.append((run_dir.name, n_rows, n_raw, n_rep))
        print(f"{run_dir.name}: n={n_rows}, polarity_conflict_raw={n_raw}, polarity_conflict_after_rep={n_rep}")

    if args.out and results:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Triptych 극성충돌 집계",
            "",
            "| Run | n_rows | polarity_conflict_raw | polarity_conflict_after_rep |",
            "|-----|--------|----------------------|-----------------------------|",
        ]
        for name, n_rows, n_raw, n_rep in results:
            lines.append(f"| {name} | {n_rows} | {n_raw} | {n_rep} |")
        lines.extend([
            "",
            "- **polarity_conflict_raw**: 동일 aspect에 ≥2 극성 (대표 선택 전)",
            "- **polarity_conflict_after_rep**: 대표 선택 후에도 극성충돌 남은 샘플 수",
        ])
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n[OK] Wrote {out_path}")


if __name__ == "__main__":
    main()
