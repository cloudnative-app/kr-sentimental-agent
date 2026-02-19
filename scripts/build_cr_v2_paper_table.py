#!/usr/bin/env python3
"""
Build cr_v2_paper_table.md from aggregated CSV and paper metrics export.

Reads aggregated_mean_std.csv (M0, M1), per-seed structural_metrics for Δ 95% CI,
irr/irr_run_summary.json for IRR metrics, irr/irr_subset_summary.json for subset IRR,
outputs.jsonl for recheck rate. Outputs cr_v2_paper_table.md.

Usage:
  python scripts/build_cr_v2_paper_table.py --agg-m0 results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n100_m1_v4_aggregated/aggregated_mean_std.csv --run-dirs-m0 results/cr_v2_n100_m0_v4__seed42_proposed ... --run-dirs-m1 results/cr_v2_n100_m1_v4__seed42_proposed ... --out reports/cr_v2_paper_table.md
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from random import choices
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
N_BOOTSTRAP = 2000

# Table 1 — F1 Metrics (display_name, agg_metric_key)
TABLE1_ROWS = [
    ("Aspect-Term Sentiment F1 (ATSA-F1)", "tuple_f1_s2_otepol"),
    ("Aspect-Category Sentiment F1 (ACSA-F1)", "tuple_f1_s2_refpol"),
    ("#attribute f1", "tuple_f1_s2_attrpol"),
]

# Table 2 — Schema & Error Control (display_name, agg_metric_key, ideal_direction)
# ideal_direction: ↑/↓ or descriptive note
TABLE2_ROWS = [
    ("Schema Assignment Completeness", "ref_fill_rate_s2", "↑"),
    ("Schema Coverage", "ref_coverage_rate_s2", "↑"),
    ("Implicit Assignment Error Rate", "implicit_invalid_pred_rate", "↓"),
    ("Intra-Aspect Polarity Conflict Rate", "polarity_conflict_rate", "↓"),
    ("Error Correction Rate", "fix_rate", "proportion of incorrect assignments corrected"),
    ("Error Introduction Rate", "break_rate", "new errors introduced during refinement"),
    ("Net Correction Gain", "net_gain", "net positive correction"),
    ("recheck-trigger rate", "_recheck_rate", ""),
    ("memory retrieval rate (retrieved_k>0 기준)", "memory_used_rate", ""),
    ("memory_retrieval_mean_k", "memory_retrieval_mean_k", ""),
    ("Run-to-Run Output Agreement (Measurement IRR)", "meas_cohen_kappa_mean", "stability across seeds, *코헨 카파만 산출되는 중"),
    ("Inter-Reviewer Agreement (Action Level) (Action IRR)", "irr_cohen_kappa_mean", "reviewer decision consistency, *코헨 카파만 산출되는 중"),
    ("subset IRR (conflict)", "_subset_irr_conflict", ""),
    ("subset_n_conflict", "_subset_n_conflict", ""),
    ("subset IRR (implicit)", "_subset_irr_implicit", ""),
    ("subset_n_implicit", "_subset_n_implicit", ""),
    ("subset IRR (negation)", "_subset_irr_negation", ""),
    ("subset_n_negation", "_subset_n_negation", ""),
    ("seed variance", "_seed_variance", ""),
    ("CDA", "cda", ""),
    ("AAR Majority Rate", "aar_majority_rate", ""),
]

# Fallback keys when primary not in agg
KEY_FALLBACK = {
    "ref_fill_rate_s2": "ref_fill_rate",
    "ref_coverage_rate_s2": "ref_coverage_rate",
}

IRR_PROCESS_KEYS = {"mean_kappa": "irr_cohen_kappa_mean", "mean_fleiss": "irr_fleiss_kappa"}
IRR_MEASUREMENT_KEYS = {"mean_kappa_measurement": "meas_cohen_kappa_mean", "mean_fleiss_measurement": "meas_fleiss_kappa"}


def _load_agg(path: Path) -> dict[str, dict[str, str]]:
    out = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = (row.get("metric") or "").strip()
            if m:
                out[m] = {"mean": row.get("mean", ""), "std": row.get("std", "")}
    return out


def _load_per_seed_metrics(run_dirs: list[Path]) -> dict[str, dict[str, float]]:
    result = {}
    for d in run_dirs:
        d = d.resolve() if not d.is_absolute() else d
        if not d.is_dir():
            continue
        m = re.search(r"__seed(\d+)_", d.name)
        seed = m.group(1) if m else None
        if not seed:
            continue
        csv_path = d / "derived" / "metrics" / "structural_metrics.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        row = rows[0]
        out = {}
        for k, v in row.items():
            if k.startswith("_"):
                continue
            try:
                val = float(v) if v and str(v).strip() else float("nan")
                if val == val:
                    out[k] = val
            except (TypeError, ValueError):
                pass
        result[seed] = out
    return result


def _load_recheck_rate(run_dirs: list[Path]) -> tuple[float, float]:
    """Compute per-condition mean recheck_triggered_rate from outputs.jsonl."""
    rates_m0, rates_m1 = [], []
    for d in run_dirs:
        d = d.resolve() if not d.is_absolute() else d
        out_path = d / "outputs.jsonl"
        if not out_path.exists():
            continue
        n, n_with_recheck = 0, 0
        for line in out_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                c = (rec.get("meta") or {}).get("recheck_triggered_count", 0)
                n += 1
                if c > 0:
                    n_with_recheck += 1
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        rate = n_with_recheck / n if n else 0.0
        if "m0" in d.name.lower() or "m0" in str(d):
            rates_m0.append(rate)
        else:
            rates_m1.append(rate)
    # Infer from run_dir name: cr_v2_n100_m0_v4 -> m0, cr_v2_n100_m1_v4 -> m1
    def _infer(run_dirs: list[Path]) -> list[float]:
        rates = []
        for d in run_dirs:
            out_path = d / "outputs.jsonl"
            if not out_path.exists():
                continue
            n, n_with_recheck = 0, 0
            for line in out_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    c = (rec.get("meta") or {}).get("recheck_triggered_count", 0)
                    n += 1
                    if c > 0:
                        n_with_recheck += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            rates.append(n_with_recheck / n if n else 0.0)
        return rates
    return rates_m0, rates_m1


def _load_irr_from_run_dirs(run_dirs: list[Path]) -> dict[str, dict[str, str]]:
    irr_metrics = {}
    for irr_key, paper_name in {**IRR_PROCESS_KEYS, **IRR_MEASUREMENT_KEYS}.items():
        vals = []
        for d in run_dirs:
            d = d.resolve() if not d.is_absolute() else d
            irr_path = d / "irr" / "irr_run_summary.json"
            if irr_path.exists():
                try:
                    data = json.loads(irr_path.read_text(encoding="utf-8"))
                    v = data.get(irr_key)
                    if v is not None and v == v:
                        vals.append(float(v))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        if vals:
            m = mean(vals)
            s = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0.0
            irr_metrics[paper_name] = {"mean": f"{m:.4f}", "std": f"{s:.4f}"}
    return irr_metrics


def _load_subset_irr(run_dirs: list[Path]) -> dict[str, dict[str, float]]:
    """Aggregate irr_subset_summary.json across run_dirs. Returns {subset: {meas, irr, n}}."""
    by_subset: dict[str, list[dict]] = {}
    for d in run_dirs:
        d = d.resolve() if not d.is_absolute() else d
        p = d / "irr" / "irr_subset_summary.json"
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for name, sub in (data or {}).items():
                if isinstance(sub, dict):
                    by_subset.setdefault(name, []).append(sub)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    out = {}
    for name, subs in by_subset.items():
        meas = [s.get("meas_cohen_kappa_mean") for s in subs if s.get("meas_cohen_kappa_mean") is not None]
        irr = [s.get("irr_cohen_kappa_mean") for s in subs if s.get("irr_cohen_kappa_mean") is not None]
        ns = [s.get("n", 0) for s in subs if isinstance(s.get("n"), (int, float))]
        out[name] = {
            "meas": mean(meas) if meas else None,
            "irr": mean(irr) if irr else None,
            "n": int(round(mean(ns))) if ns else None,
        }
    return out


def _bootstrap_delta_ci(
    m0_per_seed: dict[str, dict[str, float]],
    m1_per_seed: dict[str, dict[str, float]],
    metric: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float] | None:
    common = sorted(set(m0_per_seed) & set(m1_per_seed))
    if len(common) < 2:
        return None
    deltas = []
    for s in common:
        v1 = m1_per_seed.get(s, {}).get(metric)
        v0 = m0_per_seed.get(s, {}).get(metric)
        if v1 is not None and v0 is not None and v1 == v1 and v0 == v0:
            deltas.append(float(v1) - float(v0))
    if len(deltas) < 2:
        return None
    mean_delta = mean(deltas)
    n = len(deltas)
    boot_means = [mean(choices(deltas, k=n)) for _ in range(n_bootstrap)]
    boot_means.sort()
    lower = boot_means[int(0.025 * n_bootstrap)]
    upper = boot_means[int(0.975 * n_bootstrap)]
    return (mean_delta, lower, upper)


def _fmt_mean_std(mean_val: str | float, std_val: str | float) -> str:
    if mean_val is None or mean_val == "" or str(mean_val).strip().upper() in ("N/A", "NA"):
        return ""
    if std_val is None or std_val == "" or str(std_val).strip().upper() in ("N/A", "NA"):
        try:
            return f"{float(mean_val):.4f}"
        except (TypeError, ValueError):
            return str(mean_val)
    try:
        m, s = float(mean_val), float(std_val)
        if m != m:
            return ""
        return f"{m:.4f} ± {s:.4f}"
    except (TypeError, ValueError):
        return str(mean_val)


def _fmt_ci(mean_delta: float, lower: float, upper: float) -> str:
    return f"[{lower:.4f}, {upper:.4f}]"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build cr_v2_paper_table.md from aggregated metrics")
    ap.add_argument("--agg-m0", type=Path, required=True, help="M0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m1", type=Path, required=True, help="M1 aggregated_mean_std.csv")
    ap.add_argument("--run-dirs-m0", nargs="*", type=Path, default=[], help="M0 seed run dirs (for Δ CI, recheck, subset IRR)")
    ap.add_argument("--run-dirs-m1", nargs="*", type=Path, default=[], help="M1 seed run dirs")
    ap.add_argument("--out", type=Path, default=Path("reports/cr_v2_paper_table.md"), help="Output md path")
    args = ap.parse_args()

    agg_m0 = _load_agg(args.agg_m0.resolve() if args.agg_m0.is_absolute() else (PROJECT_ROOT / args.agg_m0).resolve())
    agg_m1 = _load_agg(args.agg_m1.resolve() if args.agg_m1.is_absolute() else (PROJECT_ROOT / args.agg_m1).resolve())

    run_dirs_m0 = [d.resolve() if not d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_m0]
    run_dirs_m1 = [d.resolve() if not d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_m1]

    irr_m0 = _load_irr_from_run_dirs(run_dirs_m0)
    irr_m1 = _load_irr_from_run_dirs(run_dirs_m1)
    for k, v in irr_m0.items():
        agg_m0[k] = v
    for k, v in irr_m1.items():
        agg_m1[k] = v

    m0_per_seed = _load_per_seed_metrics(run_dirs_m0)
    m1_per_seed = _load_per_seed_metrics(run_dirs_m1)

    # Recheck rate from outputs.jsonl
    def _recheck_rates(run_dirs: list[Path]) -> list[float]:
        rates = []
        for d in run_dirs:
            p = d / "outputs.jsonl"
            if not p.exists():
                continue
            n, n_recheck = 0, 0
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    c = (rec.get("meta") or {}).get("recheck_triggered_count", 0)
                    n += 1
                    if c > 0:
                        n_recheck += 1
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            rates.append(n_recheck / n if n else 0.0)
        return rates

    recheck_m0 = _recheck_rates(run_dirs_m0)
    recheck_m1 = _recheck_rates(run_dirs_m1)
    recheck_m0_mean = mean(recheck_m0) if recheck_m0 else 0.0
    recheck_m1_mean = mean(recheck_m1) if recheck_m1 else 0.0
    recheck_m0_std = (sum((x - recheck_m0_mean) ** 2 for x in recheck_m0) / len(recheck_m0)) ** 0.5 if len(recheck_m0) > 1 else 0.0
    recheck_m1_std = (sum((x - recheck_m1_mean) ** 2 for x in recheck_m1) / len(recheck_m1)) ** 0.5 if len(recheck_m1) > 1 else 0.0
    agg_m0["_recheck_rate"] = {"mean": f"{recheck_m0_mean:.4f}", "std": f"{recheck_m0_std:.4f}"}
    agg_m1["_recheck_rate"] = {"mean": f"{recheck_m1_mean:.4f}", "std": f"{recheck_m1_std:.4f}"}

    subset_irr_m0 = _load_subset_irr(run_dirs_m0)
    subset_irr_m1 = _load_subset_irr(run_dirs_m1)

    def _get(agg: dict, key: str) -> tuple[str, str]:
        r = agg.get(key, {})
        if not r and key in KEY_FALLBACK:
            r = agg.get(KEY_FALLBACK[key], {})
        return r.get("mean", ""), r.get("std", "")

    def _delta(key: str) -> tuple[str, str]:
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        if (not m0_m or str(m0_m).strip() in ("", "N/A", "NA")) and (not m1_m or str(m1_m).strip() in ("", "N/A", "NA")):
            return "", ""
        try:
            d = float(m1_m or 0) - float(m0_m or 0)
        except (TypeError, ValueError):
            return "", ""
        ci = _bootstrap_delta_ci(m0_per_seed, m1_per_seed, key) if m0_per_seed and m1_per_seed else None
        ci_str = _fmt_ci(ci[0], ci[1], ci[2]) if ci else ""
        return f"{d:+.4f}" if isinstance(d, float) and d == d else "", ci_str

    def _seed_variance(per_seed: dict, key: str = "tuple_f1_s2_refpol") -> str:
        vals = []
        for row in per_seed.values():
            v = row.get(key)
            if v is not None and v == v:
                vals.append(float(v))
        if len(vals) < 2:
            return f"{vals[0]:.4f}" if vals else ""
        m = mean(vals)
        return f"{(sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5:.4f}"

    lines = []
    lines.append("# CR v2 Paper Table (M0 vs M1)")
    lines.append("")
    lines.append("## Table 1 — F1 Metrics")
    lines.append("")
    lines.append("| 구분 | M0 | M1 | Δ (M1−M0) | 95% CI |")
    lines.append("|------|-----|-----|-----------|--------|")
    for disp, key in TABLE1_ROWS:
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d, ci = _delta(key)
        m0_str = _fmt_mean_std(m0_m, m0_s) or ""
        m1_str = _fmt_mean_std(m1_m, m1_s) or ""
        lines.append(f"| {disp} | {m0_str} | {m1_str} | {d} | {ci} |")

    lines.append("")
    lines.append("## Table 2 — Schema & Error Control")
    lines.append("")
    lines.append("| Metric | M0 | M1 | Δ | ideal Direction |")
    lines.append("|--------|-----|-----|-----|-----------------|")
    for disp, key, direction in TABLE2_ROWS:
        if key == "_recheck_rate":
            m0_m, m0_s = _get(agg_m0, key)
            m1_m, m1_s = _get(agg_m1, key)
            d = f"{recheck_m1_mean - recheck_m0_mean:+.4f}" if recheck_m0 and recheck_m1 else ""
        elif key.startswith("_subset_irr_"):
            subset_name = key.replace("_subset_irr_", "")
            m0_sub = subset_irr_m0.get(subset_name, {})
            m1_sub = subset_irr_m1.get(subset_name, {})
            m0_val = m0_sub.get("meas") or m0_sub.get("irr")
            m1_val = m1_sub.get("meas") or m1_sub.get("irr")
            m0_m = f"{m0_val:.4f}" if m0_val is not None else ""
            m1_m = f"{m1_val:.4f}" if m1_val is not None else ""
            m0_s, m1_s = "", ""
            try:
                if m0_val is None and m1_val is None:
                    d = ""
                else:
                    d = f"{(m1_val or 0) - (m0_val or 0):+.4f}"
            except (TypeError, ValueError):
                d = ""
        elif key.startswith("_subset_n_"):
            subset_name = key.replace("_subset_n_", "")
            m0_sub = subset_irr_m0.get(subset_name, {})
            m1_sub = subset_irr_m1.get(subset_name, {})
            n0 = m0_sub.get("n")
            n1 = m1_sub.get("n")
            m0_m = str(n0) if n0 is not None else ""
            m1_m = str(n1) if n1 is not None else ""
            m0_s, m1_s = "", ""
            d = ""
        elif key == "_seed_variance":
            v0 = _seed_variance(m0_per_seed)
            v1 = _seed_variance(m1_per_seed)
            m0_m, m0_s = v0, ""
            m1_m, m1_s = v1, ""
            d = ""
        else:
            m0_m, m0_s = _get(agg_m0, key)
            m1_m, m1_s = _get(agg_m1, key)
            d, _ = _delta(key)
        if key.startswith("_subset_n_"):
            m0_str = m0_m or ""
            m1_str = m1_m or ""
        else:
            m0_str = _fmt_mean_std(m0_m, m0_s) or ""
            m1_str = _fmt_mean_std(m1_m, m1_s) or ""
        dir_str = direction or ""
        lines.append(f"| {disp} | {m0_str} | {m1_str} | {d} | {dir_str} |")

    lines.append("")
    lines.append("**Notes:**")
    lines.append("- CDA: n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)")
    lines.append("- aar_majority_rate: AAR majority agreement rate")
    lines.append("- memory retrieval rate: mean(retrieved_k > 0)")
    lines.append("")
    lines.append("## Appendix")
    lines.append("")
    lines.append("| 구분 | 내용 |")
    lines.append("|------|------|")
    lines.append("| A. Full seed-by-seed table | seed별 모든 핵심 메트릭, Δ per seed |")
    lines.append("| B. Bootstrap distribution plot | ΔF1 분포, net_gain 분포 |")
    lines.append("| C. Error case qualitative table | break 사례 상세, memory_retrieved 수, implicit/negation 태그 |")
    lines.append("| D. Memory usage diagnostics | retrieval_hit_rate, retrieval_k distribution histogram |")
    lines.append("| E. IRR subset table | conflict, implicit, negation subset별 Measurement IRR, Action IRR |")
    lines.append("| F. break subtype | implicit/negation/simple |")
    lines.append("| G. 절대건수 (event count) | break_count, implicit_invalid_count, conflict_count 등 |")

    out_path = args.out.resolve() if args.out.is_absolute() else (PROJECT_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
