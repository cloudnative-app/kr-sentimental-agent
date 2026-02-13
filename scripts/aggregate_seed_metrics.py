#!/usr/bin/env python3
"""
N개 시드 실행 후 결과 머징·평균±표준편차·통합 보고서를 한 번에 자동 생성.

- 시드별 scorecards.jsonl을 이어붙여 merged_scorecards.jsonl 생성
- structural_error_aggregator로 머지 메트릭 생성
- 시드별 structural_metrics.csv를 수집해 평균·표준편차 계산
- 통합 보고서(integrated_report.md) 및 (선택) merged metric_report.html 생성

Usage:
  python scripts/aggregate_seed_metrics.py --base_run_id experiment_mini --mode proposed --seeds 42,123,456,789,101 --outdir results/experiment_mini_aggregated --metrics_profile paper_main
  python scripts/aggregate_seed_metrics.py --run_dirs results/experiment_mini__seed42_proposed,results/experiment_mini__seed123_proposed --outdir results/experiment_mini_aggregated --with_metric_report
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Metrics that should always appear in aggregated_mean_std (even when all values are N/A).
REPORT_METRICS_ALWAYS = [
    "n", "N_gold",
    "tuple_f1_s1", "tuple_f1_s2", "triplet_f1_s1", "triplet_f1_s2", "delta_f1",
    "fix_rate", "break_rate", "net_gain",
]


def load_csv_row(path: Path) -> Optional[Dict[str, Any]]:
    """Load first data row of structural_metrics.csv."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def parse_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "")):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def collect_per_seed_metrics(run_dirs: List[Path], metrics_path: str = "derived/metrics/structural_metrics.csv") -> List[Dict[str, Any]]:
    """Collect one row per run_dir from <run_dir>/derived/metrics/structural_metrics.csv."""
    rows = []
    for d in run_dirs:
        path = d / metrics_path if not Path(metrics_path).is_absolute() else Path(metrics_path)
        path = d / "derived" / "metrics" / "structural_metrics.csv" if not (d / metrics_path).exists() else d / metrics_path
        if not path.exists():
            path = d / "derived" / "metrics" / "structural_metrics.csv"
        r = load_csv_row(path)
        if r is not None:
            r["_run_dir"] = str(d)
            r["_seed"] = d.name
            rows.append(r)
    return rows


def compute_mean_std(per_seed_rows: List[Dict[str, Any]]) -> tuple[Dict[str, str], Dict[str, str], List[str]]:
    """
    Compute mean and std for numeric columns across per_seed_rows.
    Returns (mean_dict, std_dict, numeric_columns).
    """
    if not per_seed_rows:
        return {}, {}, []

    all_keys = set()
    for r in per_seed_rows:
        all_keys.update(k for k in r if not k.startswith("_"))

    numeric_cols = []
    for col in sorted(all_keys):
        values = [parse_float(r.get(col)) for r in per_seed_rows]
        values = [v for v in values if v is not None]
        if len(values) >= 1:
            numeric_cols.append(col)

    # Always include F1 and key metrics in report when column exists (even if all values N/A)
    cols_for_report = sorted(set(numeric_cols) | (set(REPORT_METRICS_ALWAYS) & all_keys))

    mean_dict: Dict[str, str] = {}
    std_dict: Dict[str, str] = {}

    for col in cols_for_report:
        values = [parse_float(r.get(col)) for r in per_seed_rows]
        values = [v for v in values if v is not None]
        if not values:
            mean_dict[col] = "N/A"
            std_dict[col] = "N/A"
            continue
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n if n else 0
        std = variance ** 0.5
        mean_dict[col] = f"{mean:.4f}"
        std_dict[col] = f"{std:.4f}"

    return mean_dict, std_dict, cols_for_report


def ensure_structural_metrics(run_dir: Path, profile: str = "paper_main") -> bool:
    """Run structural_error_aggregator if structural_metrics.csv missing."""
    metrics_dir = run_dir / "derived" / "metrics"
    csv_path = metrics_dir / "structural_metrics.csv"
    if csv_path.exists():
        return True
    scorecards = run_dir / "scorecards.jsonl"
    if not scorecards.exists():
        return False
    metrics_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "structural_error_aggregator.py"),
        "--input", str(scorecards),
        "--outdir", str(metrics_dir),
        "--profile", profile,
    ]
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return r.returncode == 0 and csv_path.exists()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Merge seed runs, compute mean±std, generate integrated report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--base_run_id", type=str, help="Base run ID (e.g. experiment_mini)")
    g.add_argument("--run_dirs", type=str, help="Comma-separated run dirs (e.g. results/exp__seed42_proposed,results/exp__seed123_proposed)")

    ap.add_argument("--mode", type=str, default="proposed", help="Run mode (default: proposed)")
    ap.add_argument("--seeds", type=str, help="Comma-separated seeds (e.g. 42,123,456). Required if --base_run_id.")
    ap.add_argument("--outdir", type=str, default=None, help="Output directory (default: results/<base_run_id>_aggregated)")
    ap.add_argument("--metrics_profile", type=str, default="paper_main", choices=["smoke", "regression", "paper_main"])
    ap.add_argument("--with_metric_report", action="store_true", help="Run build_metric_report for merged run (HTML)")
    ap.add_argument("--ensure_per_seed_metrics", action="store_true", help="Run structural_error_aggregator for each seed if CSV missing")

    args = ap.parse_args()

    if args.base_run_id:
        if not args.seeds:
            ap.error("--seeds required when using --base_run_id")
        seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
        results_dir = PROJECT_ROOT / "results"
        run_dirs = [results_dir / f"{args.base_run_id}__seed{s}_{args.mode}" for s in seeds]
        run_dirs = [d for d in run_dirs if d.is_dir()]
        base_run_id = args.base_run_id
    else:
        run_dirs = [Path(p.strip()).resolve() if (p.strip().startswith("/") or (len(p.strip()) > 1 and p.strip()[1] == ":")) else PROJECT_ROOT / p.strip() for p in args.run_dirs.split(",")]
        run_dirs = [d if d.is_absolute() else PROJECT_ROOT / d for d in run_dirs]
        run_dirs = [d for d in run_dirs if d.is_dir()]
        if run_dirs and "__seed" in run_dirs[0].name:
            base_run_id = run_dirs[0].name.split("__seed")[0].rstrip("_")
        else:
            base_run_id = run_dirs[0].name.rsplit("_", 1)[0] if run_dirs else "merged"

    if not run_dirs:
        print("[ERROR] No run directories found.")
        sys.exit(1)

    outdir = Path(args.outdir) if args.outdir else PROJECT_ROOT / "results" / f"{base_run_id}_aggregated"
    outdir = outdir if outdir.is_absolute() else PROJECT_ROOT / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    # Ensure per-seed structural_metrics.csv exist
    if args.ensure_per_seed_metrics:
        for d in run_dirs:
            if not (d / "derived" / "metrics" / "structural_metrics.csv").exists():
                print(f"[aggregate] Ensuring metrics for {d.name}...")
                ensure_structural_metrics(d, args.metrics_profile)

    # 1) Merge scorecards
    merged_path = outdir / "merged_scorecards.jsonl"
    lines = []
    for d in run_dirs:
        sc = d / "scorecards.jsonl"
        if not sc.exists():
            print(f"[WARN] Missing {sc}")
            continue
        lines.extend(sc.read_text(encoding="utf-8", errors="replace").strip().splitlines())
    merged_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {merged_path} ({len(lines)} lines)")

    # 2) Merged metrics (structural_error_aggregator on merged scorecards)
    merged_metrics_dir = outdir / "merged_metrics"
    merged_metrics_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "structural_error_aggregator.py"),
        "--input", str(merged_path),
        "--outdir", str(merged_metrics_dir),
        "--profile", args.metrics_profile,
    ]
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[WARN] structural_error_aggregator failed: {r.stderr[:500]}")
    else:
        print(f"[OK] Merged metrics -> {merged_metrics_dir}")

    # 3) Per-seed metrics -> mean ± std
    per_seed = collect_per_seed_metrics(run_dirs)
    if not per_seed:
        print("[WARN] No per-seed structural_metrics.csv found; skipping mean±std.")
    else:
        mean_dict, std_dict, numeric_cols = compute_mean_std(per_seed)

        # aggregated_mean_std.csv (one row: metric, mean, std)
        mean_std_path = outdir / "aggregated_mean_std.csv"
        with mean_std_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "mean", "std"])
            for col in numeric_cols:
                w.writerow([col, mean_dict.get(col, "N/A"), std_dict.get(col, "N/A")])
        print(f"[OK] Wrote {mean_std_path}")

        # aggregated_mean_std.md
        md_lines = [
            "| Metric | Mean | Std |",
            "|--------|------|-----|",
        ]
        for col in numeric_cols:
            md_lines.append(f"| {col} | {mean_dict.get(col, 'N/A')} | {std_dict.get(col, 'N/A')} |")
        (outdir / "aggregated_mean_std.md").write_text("\n".join(md_lines), encoding="utf-8")
        print(f"[OK] Wrote {outdir / 'aggregated_mean_std.md'}")

    # 4) Integrated report (markdown)
    report_path = outdir / "integrated_report.md"
    memory_note = ""
    first_manifest_path = run_dirs[0] / "manifest.json" if run_dirs else None
    if first_manifest_path and first_manifest_path.exists():
        try:
            import json
            m = json.loads(first_manifest_path.read_text(encoding="utf-8"))
            em = m.get("episodic_memory")
            if isinstance(em, dict):
                c = em.get("condition") or ""
                memory_note = f"- **Episodic memory**: {c} (on)" if c == "C2" else (f"- **Episodic memory**: {c} (off)" if c == "C1" else (f"- **Episodic memory**: {c} (silent)" if c == "C2_silent" else f"- **Episodic memory**: {c}"))
            elif em is not None:
                memory_note = f"- **Episodic memory**: {em}"
        except Exception:
            pass
    report_lines = [
        f"# 시드별 집계 통합 보고서 — {base_run_id}",
        "",
        f"- **시드 런 수**: {len(run_dirs)}",
        f"- **머지 scorecards**: `{merged_path.name}` ({len(lines)} rows)",
        *([memory_note, ""] if memory_note else []),
        "## 1. 시드별 런 디렉터리",
        "",
        "| Seed / Run | 결과 디렉터리 | 메트릭 CSV |",
        "|------------|----------------|------------|",
    ]
    for d in run_dirs:
        rel = d.relative_to(PROJECT_ROOT) if PROJECT_ROOT in d.parents else d
        csv_rel = f"{rel}/derived/metrics/structural_metrics.csv"
        report_lines.append(f"| {d.name} | `{rel}` | `{csv_rel}` |")

    report_lines.extend([
        "",
        "## 2. 시드별 구조 오류 메트릭 (요약)",
        "",
    ])
    if per_seed:
        # Use first row keys (excluding _run_dir, _seed) for header
        sample = per_seed[0]
        cols = [k for k in sorted(sample.keys()) if not k.startswith("_")][:12]
        report_lines.append("| " + " | ".join(["_seed"] + cols) + " |")
        report_lines.append("|" + "---|" * (len(cols) + 1))
        for row in per_seed:
            vals = [str(row.get("_seed", ""))] + [str(row.get(c, ""))[:10] for c in cols]
            report_lines.append("| " + " | ".join(vals) + " |")
    else:
        report_lines.append("(per-seed CSV 없음)")

    report_lines.extend([
        "",
        "## 3. 평균 ± 표준편차 (시드 간)",
        "",
        f"- **파일**: `{outdir.name}/aggregated_mean_std.csv`, `aggregated_mean_std.md`",
        "",
    ])
    if per_seed and numeric_cols:
        report_lines.append("| Metric | Mean | Std |")
        report_lines.append("|--------|------|-----|")
        for col in numeric_cols[:15]:
            report_lines.append(f"| {col} | {mean_dict.get(col, 'N/A')} | {std_dict.get(col, 'N/A')} |")
        if len(numeric_cols) > 15:
            report_lines.append(f"| ... | ({len(numeric_cols)} metrics total) | |")

    report_lines.extend([
        "",
        "## 4. 머지 메트릭 (self_consistency 등)",
        "",
        f"- **디렉터리**: `{outdir.name}/merged_metrics/`",
        f"- **파일**: structural_metrics.csv, structural_metrics_table.md",
        "",
    ])
    merged_csv = merged_metrics_dir / "structural_metrics.csv"
    if merged_csv.exists():
        row = load_csv_row(merged_csv)
        if row:
            report_lines.append("| Metric | Value |")
            report_lines.append("|--------|-------|")
            for k, v in list(row.items())[:15]:
                report_lines.append(f"| {k} | {v} |")

    merged_run_dirname = f"merged_run_{base_run_id}"
    report_lines.extend([
        "",
        "## 5. 메트릭 리포트 (HTML)",
        "",
    ])
    if args.with_metric_report:
        report_lines.append(f"- 머지 런: `reports/{merged_run_dirname}/metric_report.html` (아래 스크립트로 생성됨)")
    report_lines.append("- 시드별: `reports/<run_id>__seed<N>_<mode>/metric_report.html` (run_pipeline --with_metrics 또는 build_metric_report로 생성)")
    report_lines.append("")
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"[OK] Wrote {report_path}")

    # 5) Optional: build_metric_report for merged run (dir name includes base_run_id to avoid overwrite across runs)
    if args.with_metric_report and merged_path.exists():
        merged_run_dir = outdir / merged_run_dirname
        merged_run_dir.mkdir(parents=True, exist_ok=True)
        # Copy merged scorecards and merged metrics so build_metric_report finds them
        import shutil
        dest_sc = merged_run_dir / "scorecards.jsonl"
        if not dest_sc.exists() or dest_sc.stat().st_size != merged_path.stat().st_size:
            shutil.copy2(merged_path, dest_sc)
        dest_derived = merged_run_dir / "derived" / "metrics"
        dest_derived.mkdir(parents=True, exist_ok=True)
        for f in ("structural_metrics.csv", "structural_metrics_table.md"):
            src = merged_metrics_dir / f
            if src.exists():
                shutil.copy2(src, dest_derived / f)
        # Copy manifest from first seed for run_id etc.
        first_manifest = run_dirs[0] / "manifest.json"
        if first_manifest.exists():
            manifest = first_manifest.read_text(encoding="utf-8").replace(run_dirs[0].name, merged_run_dir.name)
            (merged_run_dir / "manifest.json").write_text(manifest, encoding="utf-8")
        reports_out = PROJECT_ROOT / "reports" / merged_run_dir.name
        reports_out.mkdir(parents=True, exist_ok=True)
        cmd_mr = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_metric_report.py"),
            "--run_dir", str(merged_run_dir),
            "--out_dir", str(reports_out),
            "--metrics_profile", args.metrics_profile,
        ]
        r2 = subprocess.run(cmd_mr, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if r2.returncode == 0:
            print(f"[OK] Merged metric_report.html -> {reports_out / 'metric_report.html'}")
        else:
            print(f"[WARN] build_metric_report failed: {r2.stderr[:300]}")

    print("")
    print(f"Output directory: {outdir}")
    print(f"Integrated report: {report_path}")


if __name__ == "__main__":
    main()
