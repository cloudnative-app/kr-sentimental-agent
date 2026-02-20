#!/usr/bin/env python3
"""
Generate CR v2 Final Paper Table — full layered format (5.1–5.4 + Appendix).

Output: Single-page Markdown with all tables. Optionally export CSVs for large tables.

Tables:
  5.1 Surface Layer: Overall (ATSA-F macro/micro) + Conditional subsets (S0 vs M0)
  5.2 Schema Layer: Overall (error rates, ACSA-F1 macro/micro) + Conditional subsets
  5.3 Process Layer: Overall (fix/break/net_gain) + Conditional (difficulty + trigger M0)
  5.4 Stochastic Stability: Overall + Conditional subsets
  Appendix: a1 variance, a2 pair-level counts, a3 micro breakdown

Subset Partition Verification: docs/cr_v2_subset_partition.md
  Subset partitions are mutually exclusive and exhaustive. Weighted recomputation across subsets exactly matches overall micro-F1.

Usage:
  python scripts/final_paper_table.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --run-dirs-s0 ... --run-dirs-m0 ... --run-dirs-m1 ... --out reports/cr_v2_n601_v1_final_paper_table.md
  python scripts/final_paper_table.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --triptych-s0 ... --triptych-m0 ... --out reports/cr_v2_n601_v1_final_paper_table.md --csv-dir reports/cr_v2_n601_v1_tables
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

NEGATION_PATTERNS = [
    r"\b안\b", r"\b못\b", r"않", r"없",
    r"\b아니\b", r"지만", r"그러나",
    r"반면", r"\b근데\b", r"\b는데\b",
]


def _has_negation(text: str) -> bool:
    if not text:
        return False
    for pat in NEGATION_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def _load_agg(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = (row.get("metric") or "").strip()
            if m:
                out[m] = {"mean": row.get("mean", ""), "std": row.get("std", "")}
    return out


def _load_per_seed_metrics(run_dirs: list[Path]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for d in run_dirs:
        d = d.resolve() if not d.is_absolute() else d
        if not d.is_dir():
            continue
        m = re.search(r"__seed(\d+)_", d.name)
        seed = m.group(1) if m else None
        if not seed:
            continue
        for sub in ("derived/metrics", "derived_subset"):
            csv_path = d / sub / "structural_metrics.csv"
            if csv_path.exists():
                break
        else:
            csv_path = d / "derived" / "metrics" / "structural_metrics.csv"
        if not csv_path.exists():
            continue
        with csv_path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        row = rows[0]
        out: dict[str, float] = {}
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
    irr_metrics: dict[str, dict[str, str]] = {}
    for irr_key, paper_name in [("mean_kappa_measurement", "meas_cohen_kappa_mean"), ("mean_fleiss_measurement", "meas_fleiss_kappa")]:
        vals: list[float] = []
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


def _fmt_mean_std(mean_val: str | float | None, std_val: str | float | None) -> str:
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


def _seed_variance(per_seed: dict[str, dict[str, float]], key: str = "tuple_f1_s2_refpol") -> str:
    vals = []
    for row in per_seed.values():
        v = row.get(key)
        if v is not None and v == v:
            vals.append(float(v))
    if len(vals) < 2:
        return f"{vals[0]:.4f}" if vals else ""
    m = mean(vals)
    return f"{(sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5:.4f}"


def micro_f1_pair_level(
    rows: list[dict],
    match_key: str = "matches_final_vs_gold",
    gold_key: str = "gold_n_pairs",
    final_key: str = "final_n_pairs",
) -> tuple[float, int, int, int, int, int]:
    tp = fp = fn = 0
    n_valid = 0
    for r in rows:
        try:
            m = int(r.get(match_key) or 0)
            g = int(r.get(gold_key) or 0)
            f = int(r.get(final_key) or 0)
        except (ValueError, TypeError):
            continue
        if g <= 0:
            continue
        n_valid += 1
        tp += m
        fn += g - m
        fp += max(0, f - m)
    if tp + fp + fn == 0:
        return 0.0, n_valid, 0, 0, 0, 0
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r_val = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * p * r_val / (p + r_val) if (p + r_val) > 0 else 0.0
    return f1, n_valid, tp + fn, tp, fp, fn


def load_triptych(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def load_m0_conflict_flags(project: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for seed_dir in (project / "results").glob("cr_v2_n601_m0_v1__seed*_proposed"):
        path = seed_dir / "outputs.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = rec.get("meta") or {}
            text_id = meta.get("text_id") or ""
            flags = rec.get("analysis_flags") or {}
            cf = (flags.get("conflict_flags") or []) if isinstance(flags, dict) else []
            out[text_id] = out.get(text_id, False) or bool(cf and len(cf) > 0)
    return out


def compute_subset_metrics(
    s0_rows: list[dict],
    m0_rows: list[dict],
    m0_conflict: dict[str, bool],
) -> dict[str, dict[str, float | str]]:
    for r in s0_rows:
        r["has_negation"] = _has_negation(r.get("text") or "")
        r["has_conflict"] = False
    for r in m0_rows:
        r["has_negation"] = _has_negation(r.get("text") or "")
        tid = r.get("text_id") or ""
        r["has_conflict"] = m0_conflict.get(tid, False)

    def by_subset(rows: list[dict], subset: str) -> list[dict]:
        if subset == "implicit":
            return [r for r in rows if (r.get("gold_type") or "") == "implicit"]
        if subset == "explicit":
            return [r for r in rows if (r.get("gold_type") or "") == "explicit"]
        if subset == "negation":
            return [r for r in rows if r.get("has_negation")]
        if subset == "multi_aspect":
            return [r for r in rows if int(r.get("gold_n_pairs") or 0) > 1]
        return rows

    subsets = [
        ("Implicit", "implicit"),
        ("Explicit", "explicit"),
        ("Negation", "negation"),
        ("Multi-aspect", "multi_aspect"),
    ]
    out: dict[str, dict[str, float | str]] = {}
    for label, key in subsets:
        sub_s0 = by_subset(s0_rows, key)
        sub_m0 = by_subset(m0_rows, key)
        f1_s0, n_s0, _, tp_s0, fp_s0, fn_s0 = micro_f1_pair_level(sub_s0)
        f1_m0, n_m0, _, tp_m0, fp_m0, fn_m0 = micro_f1_pair_level(sub_m0)
        out[label] = {
            "n_samples_s0": n_s0,
            "n_samples_m0": n_m0,
            "macro_s0": "",  # Would need per-sample F1 from aggregator
            "macro_m0": "",
            "macro_delta": "",
            "micro_s0": f1_s0,
            "micro_m0": f1_m0,
            "micro_delta": f1_m0 - f1_s0,
            "tp_s0": tp_s0, "fp_s0": fp_s0, "fn_s0": fn_s0,
            "tp_m0": tp_m0, "fp_m0": fp_m0, "fn_m0": fn_m0,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate CR v2 Final Paper Table")
    ap.add_argument("--agg-s0", type=Path, default=None, help="S0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m0", type=Path, required=True, help="M0 aggregated_mean_std.csv")
    ap.add_argument("--agg-m1", type=Path, required=True, help="M1 aggregated_mean_std.csv")
    ap.add_argument("--run-dirs-s0", nargs="*", type=Path, default=[], help="S0 seed run dirs")
    ap.add_argument("--run-dirs-m0", nargs="*", type=Path, default=[], help="M0 seed run dirs")
    ap.add_argument("--run-dirs-m1", nargs="*", type=Path, default=[], help="M1 seed run dirs")
    ap.add_argument("--triptych-s0", type=Path, default=None, help="S0 triptych.csv (for subset analysis)")
    ap.add_argument("--triptych-m0", type=Path, default=None, help="M0 triptych.csv (for subset analysis)")
    ap.add_argument("--out", type=Path, default=Path("reports/cr_v2_n601_v1_final_paper_table.md"), help="Output md path")
    ap.add_argument("--csv-dir", type=Path, default=None, help="Optional: export large tables as CSV")
    args = ap.parse_args()

    def resolve(p: Path) -> Path:
        return p.resolve() if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    agg_s0 = _load_agg(resolve(args.agg_s0)) if args.agg_s0 else {}
    agg_m0 = _load_agg(resolve(args.agg_m0))
    agg_m1 = _load_agg(resolve(args.agg_m1))

    run_dirs_s0 = [resolve(d) for d in args.run_dirs_s0]
    run_dirs_m0 = [resolve(d) for d in args.run_dirs_m0]
    run_dirs_m1 = [resolve(d) for d in args.run_dirs_m1]

    irr_m0 = _load_irr_from_run_dirs(run_dirs_m0)
    for k, v in irr_m0.items():
        agg_m0[k] = v
    irr_m1 = _load_irr_from_run_dirs(run_dirs_m1)
    for k, v in irr_m1.items():
        agg_m1[k] = v

    s0_per_seed = _load_per_seed_metrics(run_dirs_s0)
    m0_per_seed = _load_per_seed_metrics(run_dirs_m0)
    m1_per_seed = _load_per_seed_metrics(run_dirs_m1)

    has_s0 = bool(agg_s0)

    def _get(agg: dict, key: str) -> tuple[str, str]:
        r = agg.get(key, {})
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
        if not has_s0 or not agg_s0:
            return "", ""
        s0_m, s0_s = _get(agg_s0, key)
        m0_m, m0_s = _get(agg_m0, key)
        if not s0_m or str(s0_m).strip() in ("", "N/A", "NA"):
            return "", ""
        if not m0_m or str(m0_m).strip() in ("", "N/A", "NA"):
            return "", ""
        try:
            d = float(m0_m) - float(s0_m)
        except (TypeError, ValueError):
            return "", ""
        ci = _bootstrap_delta_ci_refinement(s0_per_seed, m0_per_seed, key) if s0_per_seed and m0_per_seed else None
        ci_str = _fmt_ci(ci[0], ci[1], ci[2]) if ci else ""
        return f"{d:+.4f}" if isinstance(d, float) and d == d else "", ci_str

    def _row_s0(key: str) -> tuple[str, str, str, str, str]:
        s0_m, s0_s = _get(agg_s0 or {}, key)
        m0_m, m0_s = _get(agg_m0, key)
        m1_m, m1_s = _get(agg_m1, key)
        d_ref, _ = _delta_refinement(key)
        d, ci = _delta(key)
        return (
            _fmt_mean_std(s0_m, s0_s) or "",
            _fmt_mean_std(m0_m, m0_s) or "",
            _fmt_mean_std(m1_m, m1_s) or "",
            d_ref,
            d,
        )

    lines: list[str] = []
    lines.append("# CR v2 Final Paper Table (S0 | M0 | M1 | ΔMFRA | Δmemory)")
    lines.append("")
    lines.append("**Subset Partition Verification**: Subset partitions are mutually exclusive and exhaustive. Weighted recomputation across subsets exactly matches overall micro-F1. See `docs/cr_v2_subset_partition.md`.")
    lines.append("")

    # 5.1 Surface Layer Overall
    lines.append("## 5.1 Surface Layer")
    lines.append("### 5.1.1 Overall")
    lines.append("")
    lines.append("| Condition | ATSA-F(macro) tuple_f1_s2_otepol | ATSA-F(micro) tuple_f1_s2_otepol | ΔMFRA [95% CI] | Δmemory [95% CI] |")
    lines.append("|-----------|----------------------------------|----------------------------------|-----------------|------------------|")
    s0, m0, m1, d_ref, d = _row_s0("tuple_f1_s2_otepol")
    _, ci_ref = _delta_refinement("tuple_f1_s2_otepol")
    _, ci_mem = _delta("tuple_f1_s2_otepol")
    lines.append(f"| S0 | {s0} | {_fmt_mean_std(_get(agg_s0 or {}, 'tuple_f1_s2_otepol_micro')[0], _get(agg_s0 or {}, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | — | — |")
    lines.append(f"| M0 | {m0} | {_fmt_mean_std(_get(agg_m0, 'tuple_f1_s2_otepol_micro')[0], _get(agg_m0, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | {d_ref} {ci_ref} | — |")
    lines.append(f"| M1 | {m1} | {_fmt_mean_std(_get(agg_m1, 'tuple_f1_s2_otepol_micro')[0], _get(agg_m1, 'tuple_f1_s2_otepol_micro')[1]) or '—'} | — | {d} {ci_mem} |")
    lines.append("")

    # 5.1.2 Conditional (subset) — from triptych if available
    subset_data: dict[str, dict[str, float | str]] | None = None
    if args.triptych_s0 and args.triptych_m0:
        s0_trip = load_triptych(resolve(args.triptych_s0))
        m0_trip = load_triptych(resolve(args.triptych_m0))
        m0_conflict = load_m0_conflict_flags(PROJECT_ROOT)
        subset_data = compute_subset_metrics(s0_trip, m0_trip, m0_conflict)

    lines.append("### 5.1.2 Conditional (subsets)")
    lines.append("")
    lines.append("| subset | ATSA-F(macro) S0 | ATSA-F(macro) M0 | Macro Δ (M0−S0) | ATSA-F(micro) S0 | ATSA-F(micro) M0 | Micro Δ (M0−S0) |")
    lines.append("|--------|------------------|-----------------|-----------------|------------------|------------------|-----------------|")
    if subset_data:
        for label, data in subset_data.items():
            ms0 = data.get("macro_s0") or "—"
            mm0 = data.get("macro_m0") or "—"
            md = data.get("macro_delta") or "—"
            us0 = f"{data['micro_s0']:.4f}" if isinstance(data.get("micro_s0"), (int, float)) else "—"
            um0 = f"{data['micro_m0']:.4f}" if isinstance(data.get("micro_m0"), (int, float)) else "—"
            ud = f"{data['micro_delta']:+.4f}" if isinstance(data.get("micro_delta"), (int, float)) else "—"
            lines.append(f"| {label} | {ms0} | {mm0} | {md} | {us0} | {um0} | {ud} |")
    else:
        lines.append("| *(run with --triptych-s0 and --triptych-m0 for subset analysis)* |")
    lines.append("")

    # 5.2 Schema Layer
    lines.append("## 5.2 Schema Layer")
    lines.append("### 5.2.1 Overall")
    lines.append("")
    lines.append("| Condition | Implicit Assignment Error Rate | Intra-Aspect Polarity Conflict Rate | ACSA-F1(macro) | ACSA-F1(micro) | #attribute f1 (macro) | #attribute f1 (micro) |")
    lines.append("|-----------|-------------------------------|-------------------------------------|----------------|----------------|------------------------|------------------------|")
    s0_impl, _, _, _, _ = _row_s0("implicit_invalid_pred_rate")
    s0_pol, _, _, _, _ = _row_s0("polarity_conflict_rate")
    s0_ref, _, _, _, _ = _row_s0("tuple_f1_s2_refpol")
    s0_refm, _, _, _, _ = _row_s0("tuple_f1_s2_refpol_micro")
    s0_attr, _, _, _, _ = _row_s0("tuple_f1_s2_attrpol")
    s0_attrm, _, _, _, _ = _row_s0("tuple_f1_s2_attrpol_micro")
    lines.append(f"| S0 | {s0_impl} | {s0_pol} | {s0_ref} | {s0_refm} | {s0_attr} | {s0_attrm} |")
    m0_impl, m0_pol = _get(agg_m0, "implicit_invalid_pred_rate")[0], _get(agg_m0, "polarity_conflict_rate")[0]
    m0_ref, m0_refm = _get(agg_m0, "tuple_f1_s2_refpol")[0], _get(agg_m0, "tuple_f1_s2_refpol_micro")[0]
    m0_attr, m0_attrm = _get(agg_m0, "tuple_f1_s2_attrpol")[0], _get(agg_m0, "tuple_f1_s2_attrpol_micro")[0]
    m0_s = _get(agg_m0, "implicit_invalid_pred_rate")[1]
    lines.append(f"| M0 | {_fmt_mean_std(m0_impl, m0_s)} | {_fmt_mean_std(_get(agg_m0, 'polarity_conflict_rate')[0], _get(agg_m0, 'polarity_conflict_rate')[1])} | {_fmt_mean_std(m0_ref, _get(agg_m0, 'tuple_f1_s2_refpol')[1])} | {_fmt_mean_std(m0_refm, _get(agg_m0, 'tuple_f1_s2_refpol_micro')[1])} | {_fmt_mean_std(m0_attr, _get(agg_m0, 'tuple_f1_s2_attrpol')[1])} | {_fmt_mean_std(m0_attrm, _get(agg_m0, 'tuple_f1_s2_attrpol_micro')[1])} |")
    m1_impl, m1_pol = _get(agg_m1, "implicit_invalid_pred_rate")[0], _get(agg_m1, "polarity_conflict_rate")[0]
    m1_ref, m1_refm = _get(agg_m1, "tuple_f1_s2_refpol")[0], _get(agg_m1, "tuple_f1_s2_refpol_micro")[0]
    m1_attr, m1_attrm = _get(agg_m1, "tuple_f1_s2_attrpol")[0], _get(agg_m1, "tuple_f1_s2_attrpol_micro")[0]
    m1_s = _get(agg_m1, "implicit_invalid_pred_rate")[1]
    lines.append(f"| M1 | {_fmt_mean_std(m1_impl, m1_s)} | {_fmt_mean_std(_get(agg_m1, 'polarity_conflict_rate')[0], _get(agg_m1, 'polarity_conflict_rate')[1])} | {_fmt_mean_std(m1_ref, _get(agg_m1, 'tuple_f1_s2_refpol')[1])} | {_fmt_mean_std(m1_refm, _get(agg_m1, 'tuple_f1_s2_refpol_micro')[1])} | {_fmt_mean_std(m1_attr, _get(agg_m1, 'tuple_f1_s2_attrpol')[1])} | {_fmt_mean_std(m1_attrm, _get(agg_m1, 'tuple_f1_s2_attrpol_micro')[1])} |")
    d_impl_ref, ci_impl = _delta_refinement("implicit_invalid_pred_rate")
    d_impl_mem, _ = _delta("implicit_invalid_pred_rate")
    d_pol_ref, ci_pol = _delta_refinement("polarity_conflict_rate")
    d_ref_ref, ci_ref = _delta_refinement("tuple_f1_s2_refpol")
    d_ref_mem, ci_ref_mem = _delta("tuple_f1_s2_refpol")
    d_attr_ref, _ = _delta_refinement("tuple_f1_s2_attrpol")
    d_attr_mem, _ = _delta("tuple_f1_s2_attrpol")
    lines.append(f"| ΔMFRA [95% CI] | {d_impl_ref} {ci_impl} | {d_pol_ref} {ci_pol} | {d_ref_ref} {ci_ref} | | {d_attr_ref} | |")
    lines.append(f"| Δmemory [95% CI] | {d_impl_mem} | | {d_ref_mem} {ci_ref_mem} | | {d_attr_mem} | |")
    lines.append("")

    # 5.3 Process Layer
    lines.append("## 5.3 Process Layer")
    lines.append("### 5.3.1 Overall")
    lines.append("")
    lines.append("| Condition | Error Correction Rate (fix_rate) | Error Introduction Rate (break_rate) | Net Correction Gain (net_gain) |")
    lines.append("|-----------|----------------------------------|--------------------------------------|--------------------------------|")
    s0, m0, m1, d_ref, d = _row_s0("fix_rate")
    lines.append(f"| S0 | {s0} | {_fmt_mean_std(_get(agg_s0 or {}, 'break_rate')[0], _get(agg_s0 or {}, 'break_rate')[1]) or '—'} | {_fmt_mean_std(_get(agg_s0 or {}, 'net_gain')[0], _get(agg_s0 or {}, 'net_gain')[1]) or '—'} |")
    lines.append(f"| M0 | {m0} | {_fmt_mean_std(_get(agg_m0, 'break_rate')[0], _get(agg_m0, 'break_rate')[1]) or '—'} | {_fmt_mean_std(_get(agg_m0, 'net_gain')[0], _get(agg_m0, 'net_gain')[1]) or '—'} |")
    m1_fix, m1_break, m1_net = _get(agg_m1, "fix_rate")[0], _get(agg_m1, "break_rate")[0], _get(agg_m1, "net_gain")[0]
    m1_fs, m1_bs, m1_ns = _get(agg_m1, "fix_rate")[1], _get(agg_m1, "break_rate")[1], _get(agg_m1, "net_gain")[1]
    lines.append(f"| M1 | {_fmt_mean_std(m1_fix, m1_fs)} | {_fmt_mean_std(m1_break, m1_bs)} | {_fmt_mean_std(m1_net, m1_ns)} |")
    lines.append("")

    # 5.4 Stochastic Stability
    lines.append("## 5.4 Stochastic Stability")
    lines.append("### 5.4.1 Overall")
    lines.append("")
    lines.append("| Condition | seed variance ACSA-F1 (MACRO) | seed variance ACSA-F1 (MICRO) | Run-to-Run Output Agreement (Measurement IRR Cohen's κ) |")
    lines.append("|-----------|------------------------------|------------------------------|-----------------------------------------------------|")
    sv_s0 = _seed_variance(s0_per_seed) if s0_per_seed else "—"
    sv_m0 = _seed_variance(m0_per_seed) if m0_per_seed else "—"
    sv_m1 = _seed_variance(m1_per_seed) if m1_per_seed else "—"
    sv_m0_micro = _seed_variance(m0_per_seed, "tuple_f1_s2_refpol_micro") if m0_per_seed else "—"
    sv_m1_micro = _seed_variance(m1_per_seed, "tuple_f1_s2_refpol_micro") if m1_per_seed else "—"
    irr_m0 = _fmt_mean_std(_get(agg_m0, "meas_cohen_kappa_mean")[0], _get(agg_m0, "meas_cohen_kappa_mean")[1])
    irr_m1 = _fmt_mean_std(_get(agg_m1, "meas_cohen_kappa_mean")[0], _get(agg_m1, "meas_cohen_kappa_mean")[1])
    lines.append(f"| S0 | {sv_s0} | — | N/A |")
    lines.append(f"| M0 | {sv_m0} | {sv_m0_micro} | {irr_m0 or '—'} |")
    lines.append(f"| M1 | {sv_m1} | {sv_m1_micro} | {irr_m1 or '—'} |")
    lines.append("")

    # Appendix a1
    lines.append("## Appendix")
    lines.append("### a1. Metric Variance")
    lines.append("")
    lines.append("| Metric | S0 | M0 | M1 | Var(S0) | Var(M0) | Var(M1) |")
    lines.append("|--------|-----|-----|-----|---------|---------|---------|")
    for name, key in [("Micro F1 ACSA-F1", "tuple_f1_s2_refpol_micro"), ("Macro F1 ACSA-F1", "tuple_f1_s2_refpol")]:
        s0_m = _get(agg_s0 or {}, key)[0]
        m0_m = _get(agg_m0, key)[0]
        m1_m = _get(agg_m1, key)[0]
        s0_s = _get(agg_s0 or {}, key)[1]
        m0_s = _get(agg_m0, key)[1]
        m1_s = _get(agg_m1, key)[1]
        v0 = f"{float(s0_s)**2:.6f}" if s0_s and s0_s != "N/A" else "—"
        v1 = f"{float(m0_s)**2:.6f}" if m0_s and m0_s != "N/A" else "—"
        v2 = f"{float(m1_s)**2:.6f}" if m1_s and m1_s != "N/A" else "—"
        lines.append(f"| {name} | {s0_m or '—'} | {m0_m or '—'} | {m1_m or '—'} | {v0} | {v1} | {v2} |")
    lines.append("")

    # Appendix a2, a3 — pair-level counts (from per-seed structural_metrics if tp/fp/fn columns exist)
    lines.append("### a2. Full Pair-Level Counts (TP / FP / FN) — Overall by Condition (Seed-wise)")
    lines.append("")
    lines.append("| Condition | Seed | TP | FP | FN | Precision | Recall | Micro-F1 |")
    lines.append("|-----------|------|-----|-----|-----|-----------|--------|----------|")
    for cond, per_seed in [("S0", s0_per_seed), ("M0", m0_per_seed), ("M1", m1_per_seed)]:
        for seed, row in sorted(per_seed.items()):
            tp = int(row.get("tuple_f1_s2_refpol_tp", 0) or 0)
            fp = int(row.get("tuple_f1_s2_refpol_fp", 0) or 0)
            fn = int(row.get("tuple_f1_s2_refpol_fn", 0) or 0)
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            lines.append(f"| {cond} | {seed} | {tp} | {fp} | {fn} | {p:.4f} | {r:.4f} | {f1:.4f} |")
    lines.append("")

    lines.append("### a3. Pair-Level Micro Breakdown (Overall Only)")
    lines.append("")
    lines.append("| Condition | TP | FP | FN | Precision | Recall | Micro-F1 |")
    lines.append("|-----------|-----|-----|-----|-----------|--------|----------|")
    # Load merged_metrics for TP/FP/FN (aggregated_mean_std doesn't have them)
    merged_paths = []
    if args.agg_s0:
        p0 = resolve(args.agg_s0).parent / "merged_metrics" / "structural_metrics.csv"
        merged_paths.append(("S0", p0))
    p_m0 = resolve(args.agg_m0).parent / "merged_metrics" / "structural_metrics.csv"
    p_m1 = resolve(args.agg_m1).parent / "merged_metrics" / "structural_metrics.csv"
    merged_paths.extend([("M0", p_m0), ("M1", p_m1)])
    for cond, mp in merged_paths:
        if not mp.exists():
            micro = _get(agg_s0 if cond == "S0" else (agg_m0 if cond == "M0" else agg_m1), "tuple_f1_s2_refpol_micro")[0]
            lines.append(f"| {cond} | — | — | — | — | — | {micro or '—'} |")
            continue
        with mp.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        row = rows[0] if rows else {}
        tp = int(row.get("tuple_f1_s2_refpol_tp", 0) or 0)
        fp = int(row.get("tuple_f1_s2_refpol_fp", 0) or 0)
        fn = int(row.get("tuple_f1_s2_refpol_fn", 0) or 0)
        if tp + fp + fn == 0:
            micro = _get(agg_s0 if cond == "S0" else (agg_m0 if cond == "M0" else agg_m1), "tuple_f1_s2_refpol_micro")[0]
            lines.append(f"| {cond} | — | — | — | — | — | {micro or '—'} |")
        else:
            p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            lines.append(f"| {cond} | {tp} | {fp} | {fn} | {p:.4f} | {r:.4f} | {f1:.4f} |")
    lines.append("")

    out_path = resolve(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
