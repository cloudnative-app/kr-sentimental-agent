#!/usr/bin/env python3
"""
C3 vs C2_eval 통계 검정: store_write 영향 (seed-level paired test, SD 비교).

1) Mean 차이: paired t-test (Wilcoxon signed-rank as robust alternative)
2) SD 차이: 시드 간 분산 비교 (Levene test). 
   참고: seed 내부 분산(여러 run/seed)은 n_trials=1이라 산출 불가 → 시드 간 SD 비교로 대체.

Usage:
  python scripts/c3_vs_c2_eval_statistical_test.py --base_run_id beta_n50 --out reports/c3_vs_c2_eval_statistics.md
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

METRICS = [
    "tuple_f1_s2_explicit_only",
    "severe_polarity_error_L3_rate",
    "unsupported_polarity_rate",
    "risk_resolution_rate",
    "tuple_f1_s2_implicit_only",
    "implicit_invalid_pred_rate",
    "polarity_conflict_rate",
    "parse_generate_failure_rate",
]


def parse_float(v: Any) -> Optional[float]:
    if v is None or v == "" or (isinstance(v, str) and v.strip().upper() in ("N/A", "NA", "")):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_seed_values(
    results_dir: Path,
    pattern: str,
    seeds: List[int],
    metrics: List[str],
) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {m: [] for m in metrics}
    for s in seeds:
        p = results_dir / f"{pattern}__seed{s}_proposed" / "derived" / "metrics" / "structural_metrics.csv"
        if not p.exists():
            continue
        with p.open(encoding="utf-8") as f:
            row = next(csv.DictReader(f))
        for m in metrics:
            v = parse_float(row.get(m))
            if v is not None:
                out[m].append(v)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="C3 vs C2_eval statistical tests")
    ap.add_argument("--base_run_id", type=str, default="beta_n50")
    ap.add_argument("--seeds", type=str, default="42,123,456")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
    results_dir = PROJECT_ROOT / "results"
    c3_pattern = args.base_run_id + "_c3"
    c2_eval_pattern = args.base_run_id + "_c2_eval_only"

    c3 = load_seed_values(results_dir, c3_pattern, seeds, METRICS)
    c2_eval = load_seed_values(results_dir, c2_eval_pattern, seeds, METRICS)

    # Ensure same length per metric
    for m in METRICS:
        nc = len(c3[m])
        ne = len(c2_eval[m])
        if nc != ne or nc == 0:
            c3[m] = c3[m][: min(nc, ne)]
            c2_eval[m] = c2_eval[m][: min(nc, ne)]

    try:
        from scipy import stats
    except ImportError:
        print("[WARN] scipy not installed. Run: pip install scipy")
        stats = None

    lines = [
        "# C3 vs C2_eval 통계 검정 결과",
        "",
        f"**Base run**: {args.base_run_id}  |  **Seeds**: {seeds}  |  **n_pairs**: {len(seeds)}",
        "",
        "---",
        "",
        "## 1. Mean 차이 (Paired t-test)",
        "",
        "같은 seed에서 C3 vs C2_eval 비교. **paired t-test** (ttest_rel) 사용.",
        "",
        "| Metric | C3 mean (SD) | C2_eval mean (SD) | Mean diff | t | p-value | 해석 |",
        "|--------|--------------|-------------------|-----------|---|---------|------|",
    ]

    for m in METRICS:
        a = np.array(c3[m])
        b = np.array(c2_eval[m])
        if len(a) < 2:
            lines.append(f"| {m} | — | — | — | — | — | n<2 |")
            continue
        diff = a - b
        mean_diff = np.mean(diff)
        c3_mean, c3_std = np.mean(a), np.std(a, ddof=0)  # population SD (matches paper_tables)
        c2_mean, c2_std = np.mean(b), np.std(b, ddof=0)

        if stats:
            t_stat, p_val = stats.ttest_rel(a, b)
            higher_better = {"tuple_f1_s2_explicit_only", "tuple_f1_s2_implicit_only", "risk_resolution_rate"}
            lower_better = {"severe_polarity_error_L3_rate", "unsupported_polarity_rate", "implicit_invalid_pred_rate", "polarity_conflict_rate", "parse_generate_failure_rate"}
            if p_val < 0.05:
                interp = "**p<.05** store_write 영향 유의"
            elif (mean_diff > 0 and m in higher_better) or (mean_diff < 0 and m in lower_better):
                interp = "p≥.05, exploratory: C3 유리"
            elif (mean_diff < 0 and m in higher_better) or (mean_diff > 0 and m in lower_better):
                interp = "p≥.05, exploratory: C2_eval 유리"
            else:
                interp = "p≥.05"
            lines.append(
                f"| {m} | {c3_mean:.4f} ({c3_std:.4f}) | {c2_mean:.4f} ({c2_std:.4f}) | {mean_diff:+.4f} | {t_stat:.3f} | {p_val:.4f} | {interp} |"
            )
        else:
            lines.append(f"| {m} | {c3_mean:.4f} ({c3_std:.4f}) | {c2_mean:.4f} ({c2_std:.4f}) | {mean_diff:+.4f} | — | — | (scipy 필요) |")

    lines.extend([
        "",
        "---",
        "",
        "## 2. SD 차이 (시드 간 분산 비교)",
        "",
        "각 조건에서 시드 간 표준편차. **Levene test**로 분산 동질성 검정.",
        "",
        "| Metric | C3 SD | C2_eval SD | Levene stat | p-value | 해석 |",
        "|--------|------|------------|-------------|---------|------|",
    ])

    for m in METRICS:
        a = np.array(c3[m])
        b = np.array(c2_eval[m])
        if len(a) < 2 or len(b) < 2:
            lines.append(f"| {m} | {np.std(a):.4f} | {np.std(b):.4f} | — | — | n<2 |")
            continue
        sd_c3 = np.std(a, ddof=0)
        sd_c2 = np.std(b, ddof=0)
        if stats:
            lev_stat, lev_p = stats.levene(a, b)
            interp = "**p<.05** 분산 유의적 차이" if lev_p < 0.05 else "p≥.05"
            lines.append(f"| {m} | {sd_c3:.4f} | {sd_c2:.4f} | {lev_stat:.3f} | {lev_p:.4f} | {interp} |")
        else:
            lines.append(f"| {m} | {sd_c3:.4f} | {sd_c2:.4f} | — | — | (scipy 필요) |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Wilcoxon signed-rank (robust 대안)",
        "",
        "paired t-test의 비모수 대안.",
        "",
        "| Metric | Mean diff | W stat | p-value |",
        "|--------|-----------|--------|---------|",
    ])

    for m in METRICS:
        a = np.array(c3[m])
        b = np.array(c2_eval[m])
        if len(a) < 2:
            lines.append(f"| {m} | — | — | — |")
            continue
        diff = a - b
        mean_diff = np.mean(diff)
        if stats:
            try:
                w_stat, w_p = stats.wilcoxon(a, b)
                lines.append(f"| {m} | {mean_diff:+.4f} | {w_stat:.1f} | {w_p:.4f} |")
            except Exception:
                lines.append(f"| {m} | {mean_diff:+.4f} | — | (zero diff) |")
        else:
            lines.append(f"| {m} | {mean_diff:+.4f} | — | — |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. 참고",
        "",
        "- **store_write**: C3=true (episodic store에 저장), C2_eval=false (저장 안 함).",
        "- **n=3** (seeds 42, 123, 456) → 검정력 제한. exploratory 해석 권장.",
        "- **seed 내부 분산**: n_trials=1이라 run-level repeated measure 없음 → 시드 간 SD 비교로 대체.",
    ])

    out_path = Path(args.out) if args.out else PROJECT_ROOT / "reports" / f"c3_vs_c2_eval_statistics_{args.base_run_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")


if __name__ == "__main__":
    main()
