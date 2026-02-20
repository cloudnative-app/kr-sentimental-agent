#!/usr/bin/env python3
"""
Build CR v2 Paper Table v2 — layered format (Surface, Schema, Process, Stochastic).

Output format:
  5.1 Surface Layer: ATSA-F1
  5.2 Schema Layer: Constraint Stability (RQ1) — error rates, schema metrics, ACSA-F1, #attribute f1
  5.3 Process Layer: Correction Stability (RQ2) — fix/break/net_gain
  5.4 Stochastic Stability: seed variance, Measurement IRR (Cohen + Fleiss), CDA, AAR

With --agg-s0: adds S0 column and Δ_refinement (M0−S0) for multi-agent refinement effect.

Usage:
  python scripts/build_cr_v2_paper_table_v2.py --agg-m0 ... --agg-m1 ... --run-dirs-m0 ... --run-dirs-m1 ... --out reports/cr_v2_n601_v1_paper_table_v2.md
  python scripts/build_cr_v2_paper_table_v2.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --run-dirs-s0 ... --run-dirs-m0 ... --run-dirs-m1 ... --out reports/cr_v2_n601_v1_paper_table_v2.md
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

KEY_FALLBACK = {
    "ref_fill_rate_s2": "ref_fill_rate",
    "ref_coverage_rate_s2": "ref_coverage_rate",
}

IRR_KEYS = {
    "mean_kappa_measurement": "meas_cohen_kappa_mean",
    "mean_fleiss_measurement": "meas_fleiss_kappa",
}


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


def _load_irr_from_run_dirs(run_dirs: list[Path]) -> dict[str, dict[str, str]]:
    irr_metrics = {}
    for irr_key, paper_name in IRR_KEYS.items():
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


def _bootstrap_delta_ci(
    m0_per_seed: dict[str, dict[str, float]],
    m1_per_seed: dict[str, dict[str, float]],
    metric: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float] | None:
    """Bootstrap 95% CI for M1−M0 delta."""
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


def _bootstrap_delta_ci_refinement(
    s0_per_seed: dict[str, dict[str, float]],
    m0_per_seed: dict[str, dict[str, float]],
    metric: str,
    n_bootstrap: int = N_BOOTSTRAP,
) -> tuple[float, float, float] | None:
    """Bootstrap 95% CI for Δ_refinement = M0−S0."""
    common = sorted(set(s0_per_seed) & set(m0_per_seed))
    if len(common) < 2:
        return None
    deltas = []
    for s in common:
        v0 = m0_per_seed.get(s, {}).get(metric)
        vs = s0_per_seed.get(s, {}).get(metric)
        if v0 is not None and vs is not None and v0 == v0 and vs == vs:
            deltas.append(float(v0) - float(vs))
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Build CR v2 Paper Table v2 (layered format)")
    ap.add_argument("--agg-s0", type=Path, default=None, help="S0 aggregated_mean_std.csv (optional, for Δ_refinement)")
    ap.add_argument("--agg-m0", type=Path, required=True, help="M0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m1", type=Path, required=True, help="M1 aggregated_mean_std.csv")
    ap.add_argument("--run-dirs-s0", nargs="*", type=Path, default=[], help="S0 seed run dirs (for Δ_refinement CI)")
    ap.add_argument("--run-dirs-m0", nargs="*", type=Path, default=[], help="M0 seed run dirs")
    ap.add_argument("--run-dirs-m1", nargs="*", type=Path, default=[], help="M1 seed run dirs")
    ap.add_argument("--out", type=Path, default=Path("reports/cr_v2_paper_table_v2.md"), help="Output md path")
    args = ap.parse_args()

    agg_m0 = _load_agg(args.agg_m0.resolve() if args.agg_m0.is_absolute() else (PROJECT_ROOT / args.agg_m0).resolve())
    agg_m1 = _load_agg(args.agg_m1.resolve() if args.agg_m1.is_absolute() else (PROJECT_ROOT / args.agg_m1).resolve())
    agg_s0: dict | None = None
    if args.agg_s0:
        p = args.agg_s0.resolve() if args.agg_s0.is_absolute() else (PROJECT_ROOT / args.agg_s0).resolve()
        if p.exists():
            agg_s0 = _load_agg(p)

    run_dirs_m0 = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_m0]
    run_dirs_m1 = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_m1]
    run_dirs_s0 = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_s0]

    irr_m0 = _load_irr_from_run_dirs(run_dirs_m0)
    irr_m1 = _load_irr_from_run_dirs(run_dirs_m1)
    for k, v in irr_m0.items():
        agg_m0[k] = v
    for k, v in irr_m1.items():
        agg_m1[k] = v

    m0_per_seed = _load_per_seed_metrics(run_dirs_m0)
    m1_per_seed = _load_per_seed_metrics(run_dirs_m1)
    s0_per_seed = _load_per_seed_metrics(run_dirs_s0) if run_dirs_s0 else {}

    has_s0 = agg_s0 is not None and bool(agg_s0)

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

    def _delta_refinement(key: str) -> tuple[str, str]:
        """Δ_refinement = M0 − S0."""
        if not has_s0 or not agg_s0:
            return "", ""
        s0_m, s0_s = _get(agg_s0, key)
        m0_m, m0_s = _get(agg_m0, key)
        if not s0_m or str(s0_m).strip() in ("", "N/A", "NA"):
            return "", ""  # S0 has no value for this metric (e.g. IRR)
        if not m0_m or str(m0_m).strip() in ("", "N/A", "NA"):
            return "", ""
        try:
            d = float(m0_m) - float(s0_m)
        except (TypeError, ValueError):
            return "", ""
        ci = _bootstrap_delta_ci_refinement(s0_per_seed, m0_per_seed, key) if s0_per_seed and m0_per_seed else None
        ci_str = _fmt_ci(ci[0], ci[1], ci[2]) if ci else ""
        return f"{d:+.4f}" if isinstance(d, float) and d == d else "", ci_str

    def _row(key: str) -> tuple[str, str, str, str]:
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d, ci = _delta(key)
        return _fmt_mean_std(m0_m, m0_s) or "", _fmt_mean_std(m1_m, m1_s) or "", d, ci

    def _row_s0(key: str) -> tuple[str, str, str, str, str]:
        """Returns (s0, m0, m1, d_refinement, d_m1_m0)."""
        s0_m, s0_s = _get(agg_s0 or {}, key)
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d_ref, ci_ref = _delta_refinement(key)
        d, ci = _delta(key)
        return (
            _fmt_mean_std(s0_m, s0_s) or "",
            _fmt_mean_std(m0_m, m0_s) or "",
            _fmt_mean_std(m1_m, m1_s) or "",
            d_ref,
            d,
        )

    def _row_dir(key: str, direction: str) -> tuple[str, str, str, str]:
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d, _ = _delta(key)
        return _fmt_mean_std(m0_m, m0_s) or "", _fmt_mean_std(m1_m, m1_s) or "", d, direction

    def _row_dir_s0(key: str, direction: str) -> tuple[str, str, str, str, str]:
        s0_m, s0_s = _get(agg_s0 or {}, key)
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d_ref, _ = _delta_refinement(key)
        d, _ = _delta(key)
        return (
            _fmt_mean_std(s0_m, s0_s) or "",
            _fmt_mean_std(m0_m, m0_s) or "",
            _fmt_mean_std(m1_m, m1_s) or "",
            d_ref,
            d,
        )

    lines = []
    if has_s0:
        lines.append("# CR v2 Paper Table v2 (S0 | M0 | M1 | Δ_refinement | Δ)")
    else:
        lines.append("# CR v2 Paper Table v2 (M0 vs M1)")
    lines.append("")

    # 5.1 Surface Layer
    lines.append("## 5.1 Surface Layer: Extraction Performance Control")
    lines.append("")
    if has_s0:
        lines.append("| Layer | Metric | S0 | M0 | M1 | Δ_refinement (M0−S0) | Δ (M1−M0) | 95% CI |")
        lines.append("|-------|--------|-----|-----|-----|----------------------|------------|--------|")
        s0, m0, m1, d_ref, d = _row_s0("tuple_f1_s2_otepol")
        ci = _delta("tuple_f1_s2_otepol")[1]
        lines.append(f"| Surface | ATSA-F1 | {s0} | {m0} | {m1} | {d_ref} | {d} | {ci} |")
    else:
        lines.append("| Layer | Metric | M0 | M1 | Δ | 95% CI |")
        lines.append("|-------|--------|-----|-----|-----|--------|")
        m0, m1, d, ci = _row("tuple_f1_s2_otepol")
        lines.append(f"| Surface | ATSA-F1 | {m0} | {m1} | {d} | {ci} |")
    lines.append("")

    # 5.2 Schema Layer: Constraint Stability (RQ1)
    lines.append("## 5.2 Schema Layer: Constraint Stability (RQ1)")
    lines.append("")
    if has_s0:
        lines.append("| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|---------------|-----|-----------|")
        for disp, key, direction in [
            ("Implicit Assignment Error Rate", "implicit_invalid_pred_rate", "↓"),
            ("Intra-Aspect Polarity Conflict Rate", "polarity_conflict_rate", "↓"),
            ("Schema Assignment Completeness", "ref_fill_rate_s2", "↑"),
            ("Schema Coverage", "ref_coverage_rate_s2", "↑"),
        ]:
            s0, m0, m1, d_ref, d = _row_dir_s0(key, direction)
            lines.append(f"| {disp} | {s0} | {m0} | {m1} | {d_ref} | {d} | {direction} |")
    else:
        lines.append("| Metric | M0 | M1 | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|-----------|")
        for disp, key, direction in [
            ("Implicit Assignment Error Rate", "implicit_invalid_pred_rate", "↓"),
            ("Intra-Aspect Polarity Conflict Rate", "polarity_conflict_rate", "↓"),
            ("Schema Assignment Completeness", "ref_fill_rate_s2", "↑"),
            ("Schema Coverage", "ref_coverage_rate_s2", "↑"),
        ]:
            m0, m1, d, _ = _row_dir(key, direction)
            lines.append(f"| {disp} | {m0} | {m1} | {d} | {direction} |")
    lines.append("")
    if has_s0:
        lines.append("| Layer | Metric | S0 | M0 | M1 | Δ_refinement | Δ | 95% CI |")
        lines.append("|-------|--------|-----|-----|-----|---------------|-----|--------|")
        s0, m0, m1, d_ref, d = _row_s0("tuple_f1_s2_refpol")
        ci = _delta("tuple_f1_s2_refpol")[1]
        lines.append(f"| Schema | ACSA-F1 | {s0} | {m0} | {m1} | {d_ref} | {d} | {ci} |")
        s0, m0, m1, d_ref, d = _row_s0("tuple_f1_s2_attrpol")
        ci = _delta("tuple_f1_s2_attrpol")[1]
        lines.append(f"| Schema | #attribute f1 | {s0} | {m0} | {m1} | {d_ref} | {d} | {ci} |")
    else:
        lines.append("| Layer | Metric | M0 | M1 | Δ | 95% CI |")
        lines.append("|-------|--------|-----|-----|-----|--------|")
        m0, m1, d, ci = _row("tuple_f1_s2_refpol")
        lines.append(f"| Schema | ACSA-F1 | {m0} | {m1} | {d} | {ci} |")
        m0, m1, d, ci = _row("tuple_f1_s2_attrpol")
        lines.append(f"| Schema | #attribute f1 | {m0} | {m1} | {d} | {ci} |")
    lines.append("")

    # 5.3 Process Layer: Correction Stability (RQ2) — S0 has no Stage2, fix/break/net_gain = 0/NA
    lines.append("## 5.3 Process Layer: Correction Stability (RQ2)")
    lines.append("")
    if has_s0:
        lines.append("| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|---------------|-----|-----------|")
        for disp, key, direction in [
            ("Error Correction Rate", "fix_rate", "↑"),
            ("Error Introduction Rate", "break_rate", "↓"),
            ("Net Correction Gain", "net_gain", "↑"),
        ]:
            s0, m0, m1, d_ref, d = _row_dir_s0(key, direction)
            lines.append(f"| {disp} | {s0} | {m0} | {m1} | {d_ref} | {d} | {direction} |")
    else:
        lines.append("| Metric | M0 | M1 | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|-----------|")
        for disp, key, direction in [
            ("Error Correction Rate", "fix_rate", "↑"),
            ("Error Introduction Rate", "break_rate", "↓"),
            ("Net Correction Gain", "net_gain", "↑"),
        ]:
            m0, m1, d, _ = _row_dir(key, direction)
            lines.append(f"| {disp} | {m0} | {m1} | {d} | {direction} |")
    lines.append("")

    # 5.4 Stochastic Stability
    lines.append("## 5.4 Stochastic Stability: Run-to-Run Reproducibility")
    lines.append("")
    if has_s0:
        sv_s0 = _seed_variance(s0_per_seed) if s0_per_seed else ""
        lines.append("| Metric | S0 | M0 | M1 | Δ_refinement | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|---------------|-----|-----------|")
        sv0 = _seed_variance(m0_per_seed)
        sv1 = _seed_variance(m1_per_seed)
        try:
            sv_ref = f"{float(sv0) - float(sv_s0):+.4f}" if sv_s0 and sv0 else ""
            sv_d = f"{float(sv1) - float(sv0):+.4f}"
        except (TypeError, ValueError):
            sv_ref, sv_d = "", ""
        lines.append(f"| seed variance (ACSA-F1) | {sv_s0} | {sv0} | {sv1} | {sv_ref} | {sv_d} | ↓ |")
        for label, key in [
            ("Run-to-Run Output Agreement (Measurement IRR, Cohen's κ)", "meas_cohen_kappa_mean"),
            ("Run-to-Run Output Agreement (Measurement IRR, Fleiss' κ)", "meas_fleiss_kappa"),
        ]:
            s0, m0, m1, d_ref, d = _row_dir_s0(key, "↑")
            lines.append(f"| {label} | {s0} | {m0} | {m1} | {d_ref} | {d} | ↑ |")
        s0, m0, m1, d_ref, d = _row_dir_s0("cda", "")
        lines.append(f"| CDA | {s0} | {m0} | {m1} | {d_ref} | {d} | |")
        s0, m0, m1, d_ref, d = _row_dir_s0("aar_majority_rate", "")
        lines.append(f"| aar_majority_rate | {s0} | {m0} | {m1} | {d_ref} | {d} | |")
    else:
        lines.append("| Metric | M0 | M1 | Δ | Direction |")
        lines.append("|--------|-----|-----|-----|-----------|")
        sv0 = _seed_variance(m0_per_seed)
        sv1 = _seed_variance(m1_per_seed)
        try:
            sv_d = f"{float(sv1) - float(sv0):+.4f}"
        except (TypeError, ValueError):
            sv_d = ""
        lines.append(f"| seed variance (ACSA-F1) | {sv0} | {sv1} | {sv_d} | ↓ |")
        for label, key in [
            ("Run-to-Run Output Agreement (Measurement IRR, Cohen's κ)", "meas_cohen_kappa_mean"),
            ("Run-to-Run Output Agreement (Measurement IRR, Fleiss' κ)", "meas_fleiss_kappa"),
        ]:
            m0, m1, d, _ = _row_dir(key, "↑")
            lines.append(f"| {label} | {m0} | {m1} | {d} | ↑ |")
        m0, m1, d, _ = _row_dir("cda", "")
        lines.append(f"| CDA | {m0} | {m1} | {d} | |")
        m0, m1, d, _ = _row_dir("aar_majority_rate", "")
        lines.append(f"| aar_majority_rate | {m0} | {m1} | {d} | |")
    lines.append("")

    lines.append("**Notes:**")
    lines.append("- CDA: n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)")
    lines.append("- aar_majority_rate: AAR majority agreement rate")
    lines.append("- seed variance: std of tuple_f1_s2_refpol (ACSA-F1) across seeds")
    if has_s0:
        lines.append("- Δ_refinement = M0 − S0: multi-agent refinement effect (Review+Arbiter)")
        lines.append("- S0: single-pass baseline (no review, no arbiter, no memory); fix/break/net_gain = 0")

    out_path = args.out.resolve() if args.out.is_absolute() else (PROJECT_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
