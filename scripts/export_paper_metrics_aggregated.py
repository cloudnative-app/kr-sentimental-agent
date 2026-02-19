#!/usr/bin/env python3
"""
집계본 aggregated_mean_std.csv → paper_metrics_aggregated.md 생성.

mean/std 컬럼을 "mean ± std" 형식으로 합쳐서 논문용 마크다운 작성.

Optional: --run-dirs로 outputs.jsonl에서 conflict_detection_rate, review_nontrivial_action_rate,
arb_nonkeep_rate 직접 계산. --run-dirs와 동일 경로의 irr/irr_run_summary.json에서 IRR 메트릭 수집.

M0 vs M1 비교: --agg-path-m1, --run-dirs-m1 지정 시 paper_metrics_aggregated_comparison.md 생성.
Δ(M1−M0) 95%% CI는 seed-level bootstrap 2000회로 추정 (Table 1A, Construct Integrity, Table 1B).

Usage:
  python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv
  python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0__seed42_proposed ... --out-dir results/cr_n50_m0_paper
  python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_v5_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_n50_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0_v5__seed3_proposed ... --run-dirs-m1 results/cr_n50_m1_v5__seed3_proposed ... --out-dir results/cr_n50_v5_comparison_paper
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from random import choices
from statistics import mean, pstdev

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Seed-level bootstrap for Δ(M1−M0) 95% CI
N_BOOTSTRAP = 2000

# Paper Metric Realignment Freeze — 3-level hierarchy
# Table 1 — Surface Measurement (OTE–polarity)
PAPER_METRICS_TABLE_1 = [
    "tuple_f1_s1_otepol",
    "tuple_f1_s2_otepol",
    "delta_f1_otepol",
    "tuple_f1_explicit",
]

# Table 2 — Schema Projection (entity#attribute–polarity) + Construct Integrity
PAPER_METRICS_TABLE_2 = [
    "tuple_f1_s1_refpol",
    "tuple_f1_s2_refpol",
    "delta_f1_refpol",
    "ref_fill_rate_s2",
    "ref_coverage_rate_s2",
    "--- Construct Integrity (debug) ---",
    "ref_hash_preserved_fail_count",
    "attr_split_missing_hash_count",
    "pred_ref_empty_count",
]

# Table 3 — Error Control
# 3A Error Reduction
PAPER_METRICS_TABLE_3A = [
    "fix_rate_refpol",
    "break_rate_refpol",
    "break_rate_implicit_refpol",
    "break_rate_negation_refpol",
    "break_rate_simple_refpol",
    "net_gain_refpol",
    "cda",
]

# 3B Error Detection
PAPER_METRICS_TABLE_3B = [
    "conflict_detection_rate",
    "aar_majority_rate",
]

# 3C Stability
PAPER_METRICS_TABLE_3C = [
    "meas_fleiss_kappa",
    "meas_cohen_kappa_mean",
    "meas_perfect_agreement_rate",
    "meas_majority_agreement_rate",
    "--- Process IRR (aux) ---",
    "irr_fleiss_kappa",
    "irr_cohen_kappa_mean",
    "irr_perfect_agreement_rate",
    "irr_majority_agreement_rate",
]

# Appendix — attr-pol, invalid_*, implicit_* (diagnostics, not deleted)
PAPER_METRICS_APPENDIX = [
    "tuple_f1_s1_attrpol",
    "tuple_f1_s2_attrpol",
    "delta_f1_attrpol",
    "fix_rate_attrpol",
    "break_rate_attrpol",
    "net_gain_attrpol",
    "invalid_target_rate",
    "invalid_language_rate",
    "invalid_ref_rate",
    "implicit_invalid_pred_rate",
    "implicit_coverage_fail_rate",
    "implicit_null_fail_rate",
    "implicit_parse_fail_rate",
    "tuple_f1_s2_otepol_explicit_only",
    "polarity_conflict_rate",
    "N_agg_fallback_used",
]

# Notes (Paper Metric Realignment Freeze) — Table definition comments to avoid OTE vs entity#attribute vs attribute confusion
TABLE_NOTES = {
    "TABLE_1": (
        "**Note.** Table 1B (Surface Measurement): pair=(aspect_term, polarity), explicit-only 중심. "
        "OTE–polarity (micro-level ABSA unit). Key: tuples_to_pairs / match_by_aspect_ref=False."
    ),
    "TABLE_2": (
        "**Note.** Table 1A (Schema Projection): pair=(entity#attribute, polarity), taxonomy projection. "
        "aspect_ref (entity#attribute) is schema label space. Key: tuples_to_ref_pairs. "
        "Construct Integrity: ref_hash_preserved_fail_count=0, attr_split_missing_hash_count, ref_fill_rate_s2."
    ),
    "TABLE_1C": (
        "**Note.** Table 1C: pair=(attribute, polarity), entity marginalization diagnostic."
    ),
    "TABLE_3A": (
        "**Note.** Error Control = change in error state transition. "
        "fix_rate: S1 wrong → S2 right. break_rate: S1 right → S2 wrong. "
        "CDA = n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed). Gold-based."
    ),
    "TABLE_3B": (
        "**Note.** Table 2A: label=action (KEEP/DROP/FLIP…), 전략 합의. "
        "Error Detection: conflict_detection_rate, AAR = n(majority agreement) / total_tuples."
    ),
    "TABLE_3C": (
        "**Note.** Table 2B: label=decision (POS/NEG/NEU/DROP), 측정값 합의. "
        "Stability. Measurement IRR: final decision. Process IRR (aux): action labels."
    ),
    "APPENDIX": (
        "**Note.** Appendix: attr-pol diagnostics, invalid_* grounding, implicit_* metrics. "
        "Kept for reproducibility; not in main paper tables."
    ),
}

# Fallback: use non-suffixed keys when refpol not in agg
PAPER_METRICS_CORE_FALLBACK = {
    "tuple_f1_s1_refpol": "tuple_f1_s1",
    "tuple_f1_s2_refpol": "tuple_f1_s2",
    "delta_f1_refpol": "delta_f1",
    "fix_rate_refpol": "fix_rate",
    "break_rate_refpol": "break_rate",
    "break_rate_implicit_refpol": "break_rate_implicit",
    "break_rate_negation_refpol": "break_rate_negation",
    "break_rate_simple_refpol": "break_rate_simple",
    "net_gain_refpol": "net_gain",
    "tuple_f1_s1_otepol": "tuple_f1_s1",
    "tuple_f1_s2_otepol": "tuple_f1_s2",
    "delta_f1_otepol": "delta_f1",
}

# IRR JSON key → paper metric name
IRR_JSON_TO_PAPER = {
    "mean_fleiss": "irr_fleiss_kappa",
    "mean_kappa": "irr_cohen_kappa_mean",
    "mean_perfect_agreement": "irr_perfect_agreement_rate",
    "mean_majority_agreement": "irr_majority_agreement_rate",
    "mean_fleiss_measurement": "meas_fleiss_kappa",
    "mean_kappa_measurement": "meas_cohen_kappa_mean",
    "mean_perfect_agreement_measurement": "meas_perfect_agreement_rate",
    "mean_majority_agreement_measurement": "meas_majority_agreement_rate",
}

# Post-hoc Construct Alignment (optional; when semantic_alignment_metrics.json exists)
PAPER_METRICS_SEMANTIC_ALIGNMENT = [
    "exact_ref_accuracy",
    "near_miss_rate",
    "exact_plus_near_rate",
    "mean_taxonomy_similarity",
    "mean_taxonomy_distance",
]

# aggregator 컬럼 → paper 컬럼 (aggregated_mean_std에는 aggregator 이름으로 저장됨)
AGG_TO_PAPER = {
    "review_action_rate": "review_intervention_rate",
    "changed_samples_rate": "pre_to_post_change_rate",
}



def _extract_seed_from_run_dir(path: Path) -> str | None:
    """Extract seed from run dir name, e.g. cr_n50_m0_v5__seed3_proposed -> '3'."""
    name = path.name if isinstance(path, Path) else str(path)
    m = re.search(r"__seed(\d+)_", name)
    return m.group(1) if m else None


def _load_per_seed_structural_metrics(run_dirs: list[Path]) -> dict[str, dict[str, float]]:
    """Load per-seed metrics from derived/metrics/structural_metrics.csv. Returns {seed: {metric: value}}."""
    result: dict[str, dict[str, float]] = {}
    for d in run_dirs:
        seed = _extract_seed_from_run_dir(d)
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
        out: dict[str, float] = {}
        for k, v in row.items():
            if k.startswith("_"):
                continue
            try:
                val = float(v) if v and str(v).strip() else float("nan")
                if val == val:  # not nan
                    out[k] = val
            except (TypeError, ValueError):
                pass
        result[seed] = out
    return result


def _bootstrap_delta_ci(
    m0_per_seed: dict[str, dict[str, float]],
    m1_per_seed: dict[str, dict[str, float]],
    metrics: list[str],
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, tuple[float, float, float]]:
    """
    Seed-level bootstrap for Δ(M1−M0). Returns {metric: (mean_delta, lower_2.5, upper_97.5)}.
    """
    common_seeds = sorted(set(m0_per_seed) & set(m1_per_seed))
    if len(common_seeds) < 2:
        return {}

    # structural_metrics.csv uses same column names as paper metrics
    def _get_col(paper_name: str) -> str:
        return paper_name

    result: dict[str, tuple[float, float, float]] = {}
    for paper_metric in metrics:
        if paper_metric == "--- Construct Integrity ---":
            continue
        col = _get_col(paper_metric)
        deltas: list[float] = []
        for s in common_seeds:
            v1 = m1_per_seed.get(s, {}).get(col)
            v0 = m0_per_seed.get(s, {}).get(col)
            if v1 is not None and v0 is not None and v1 == v1 and v0 == v0:
                deltas.append(float(v1) - float(v0))
        if len(deltas) < 2:
            continue
        mean_delta = mean(deltas)
        n = len(deltas)
        boot_means: list[float] = []
        for _ in range(n_bootstrap):
            sample = choices(deltas, k=n)
            boot_means.append(mean(sample))
        boot_means.sort()
        lower = boot_means[int(0.025 * n_bootstrap)]
        upper = boot_means[int(0.975 * n_bootstrap)]
        result[paper_metric] = (mean_delta, lower, upper)
    return result


def _format_delta_ci(mean_delta: float, lower: float, upper: float) -> str:
    """Format as 'mean_delta [lower, upper]'."""
    return f"{mean_delta:.4f} [{lower:.4f}, {upper:.4f}]"


def _load_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def compute_cr_process_metrics_from_outputs(outputs_path: Path) -> dict[str, float]:
    """outputs.jsonl에서 CR process 메트릭 계산."""
    N = 0
    n_has_conflict = 0
    n_review_nontrivial = 0
    n_arb_nonkeep = 0
    n_pre_post_changed = 0

    for r in _load_jsonl(outputs_path):
        N += 1
        af = r.get("analysis_flags") or {}

        conflict_flags = af.get("conflict_flags") or []
        if len(conflict_flags) > 0:
            n_has_conflict += 1

        review_actions = af.get("review_actions") or []
        if any((a.get("action_type") or a.get("type") or "KEEP").strip().upper() != "KEEP" for a in review_actions):
            n_review_nontrivial += 1

        arb_actions = af.get("arb_actions") or []
        if any((a.get("action_type") or a.get("type") or "KEEP").strip().upper() != "KEEP" for a in arb_actions):
            n_arb_nonkeep += 1

        fr = r.get("final_result") or {}
        pre = fr.get("final_tuples_pre_review") or fr.get("stage1_tuples") or []
        post = fr.get("final_tuples_post_review") or fr.get("final_tuples") or []
        if pre != post:
            n_pre_post_changed += 1

    if N == 0:
        return {
            "conflict_detection_rate": float("nan"),
            "review_nontrivial_action_rate": float("nan"),
            "arb_nonkeep_rate": float("nan"),
            "pre_to_post_change_rate": float("nan"),
        }

    return {
        "conflict_detection_rate": n_has_conflict / N,
        "review_nontrivial_action_rate": n_review_nontrivial / N,
        "arb_nonkeep_rate": n_arb_nonkeep / N,
        "pre_to_post_change_rate": n_pre_post_changed / N,
    }


def summarize_across_seeds(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    m = mean(values)
    s = pstdev(values) if len(values) > 1 else 0.0
    return (m, s)


def format_mean_std(mean_val: str | float, std_val: str | float) -> str:
    """mean/std를 'mean ± std' 또는 'mean' 형식으로 포맷."""
    if mean_val is None or mean_val == "" or str(mean_val).strip().upper() in ("N/A", "NA"):
        return "N/A"
    if std_val is None or std_val == "" or str(std_val).strip().upper() in ("N/A", "NA"):
        try:
            return f"{float(mean_val):.4f}"
        except (TypeError, ValueError):
            return str(mean_val)
    try:
        m = float(mean_val)
        s = float(std_val)
        if m != m:  # NaN
            return "N/A"
        return f"{m:.4f} ± {s:.4f}"
    except (TypeError, ValueError):
        return str(mean_val)


def to_markdown_table(rows: list[dict], columns: list[str]) -> str:
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    for row in rows:
        vals = [str(row.get(c, "")) for c in columns]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export paper_metrics_aggregated.md from aggregated_mean_std.csv"
    )
    ap.add_argument(
        "--agg-path",
        type=Path,
        required=True,
        help="Path to aggregated_mean_std.csv",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: results/<base>_paper)",
    )
    ap.add_argument(
        "--results-root",
        type=Path,
        default=PROJECT_ROOT / "results",
        help="Results root (default: results/)",
    )
    ap.add_argument(
        "--run-dirs",
        nargs="*",
        type=Path,
        default=None,
        help="Seed별 run 디렉토리 (outputs.jsonl + irr/irr_run_summary.json 수집)",
    )
    ap.add_argument(
        "--irr-json",
        type=Path,
        default=None,
        help="IRR seed별 결과 JSON (optional). 형식: {\"42\": {...}, \"123\": {...}}",
    )
    ap.add_argument(
        "--agg-path-m1",
        type=Path,
        default=None,
        help="M1 aggregated_mean_std.csv (for M0 vs M1 comparison)",
    )
    ap.add_argument(
        "--run-dirs-m1",
        nargs="*",
        type=Path,
        default=None,
        help="M1 seed별 run 디렉토리 (Δ 95%% CI용 per-seed structural_metrics)",
    )
    args = ap.parse_args()

    agg_path = args.agg_path.resolve()
    if not agg_path.is_absolute():
        agg_path = (PROJECT_ROOT / agg_path).resolve()
    if not agg_path.exists():
        print(f"[ERROR] Missing: {agg_path}", file=sys.stderr)
        return 1

    out_dir = args.out_dir
    if out_dir is None:
        parent = agg_path.parent.name
        if parent.endswith("_aggregated"):
            base = parent[: -len("_aggregated")]
        else:
            base = parent
        out_dir = args.results_root / f"{base}_paper"
    out_dir = out_dir.resolve()
    if not out_dir.is_absolute():
        out_dir = (PROJECT_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # metric → {mean, std} from aggregated_mean_std.csv
    agg: dict[str, dict[str, str]] = {}
    with agg_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = row.get("metric", "").strip()
            if m:
                agg[m] = {"mean": row.get("mean", ""), "std": row.get("std", "")}

    paper_to_agg = {v: k for k, v in AGG_TO_PAPER.items()}

    # extra_metrics: outputs.jsonl + irr에서 계산한 것
    extra_metrics: dict[str, dict[str, str]] = {}

    if args.run_dirs:
        run_dirs = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs]
        run_dirs = [d for d in run_dirs if d.is_dir()]

        # Process metrics from outputs.jsonl
        proc_keys = ["conflict_detection_rate", "review_nontrivial_action_rate", "arb_nonkeep_rate"]
        per_seed: dict[str, list[float]] = {k: [] for k in proc_keys}
        for d in run_dirs:
            outputs_path = d / "outputs.jsonl"
            if outputs_path.exists():
                met = compute_cr_process_metrics_from_outputs(outputs_path)
                for k in proc_keys:
                    v = met.get(k)
                    if v is not None and v == v and v != float("inf") and v != float("-inf"):
                        per_seed[k].append(v)

        for k, vals in per_seed.items():
            if vals:
                m, s = summarize_across_seeds(vals)
                extra_metrics[k] = {"mean": str(m), "std": str(s)}

        # pre_to_post_change_rate는 agg에 changed_samples_rate로 있을 수 있음 — 유지

        # Semantic alignment from run_dir/derived/semantic_alignment/semantic_alignment_metrics.json
        sem_align_paths = [
            d / "derived" / "semantic_alignment" / "semantic_alignment_metrics.json"
            for d in run_dirs
        ]
        if any(p.exists() for p in sem_align_paths):
            for k in PAPER_METRICS_SEMANTIC_ALIGNMENT:
                vals: list[float] = []
                for p in sem_align_paths:
                    if not p.exists():
                        continue
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        v = data.get(k)
                        if v is not None and v == v and v != float("inf"):
                            vals.append(float(v))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass
                if vals:
                    m, s = summarize_across_seeds(vals)
                    extra_metrics[k] = {"mean": str(m), "std": str(s)}

        # IRR from run_dir/irr/irr_run_summary.json
        irr_keys = ["mean_fleiss", "mean_kappa", "mean_perfect_agreement", "mean_majority_agreement"]
        for irr_key, paper_name in IRR_JSON_TO_PAPER.items():
            vals: list[float] = []
            for d in run_dirs:
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
                m, s = summarize_across_seeds(vals)
                extra_metrics[paper_name] = {"mean": str(m), "std": str(s)}

    if args.irr_json and args.irr_json.exists():
        try:
            irr_data = json.loads(args.irr_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError) as e:
            print(f"[WARN] --irr-json parse failed: {e}", file=sys.stderr)
            irr_data = {}
        if isinstance(irr_data, dict):
            for irr_key, paper_name in IRR_JSON_TO_PAPER.items():
                vals: list[float] = []
                for seed, obj in irr_data.items():
                    if isinstance(obj, dict):
                        v = obj.get(irr_key) or obj.get(paper_name)
                    else:
                        v = None
                    if v is not None and v == v:
                        vals.append(float(v))
                if vals and paper_name not in extra_metrics:
                    m, s = summarize_across_seeds(vals)
                    extra_metrics[paper_name] = {"mean": str(m), "std": str(s)}

    def lookup(paper_name: str) -> tuple[str, str]:
        if paper_name in extra_metrics:
            r = extra_metrics[paper_name]
            return r.get("mean", ""), r.get("std", "")
        if paper_name in agg:
            r = agg[paper_name]
            return r.get("mean", ""), r.get("std", "")
        agg_name = paper_to_agg.get(paper_name)
        if agg_name and agg_name in agg:
            r = agg[agg_name]
            return r.get("mean", ""), r.get("std", "")
        fallback = PAPER_METRICS_CORE_FALLBACK.get(paper_name)
        if fallback and fallback in agg:
            r = agg[fallback]
            return r.get("mean", ""), r.get("std", "")
        return "", ""

    def build_section(metric_list: list[str]) -> list[dict]:
        rows = []
        for m in metric_list:
            if m.startswith("---"):
                rows.append({"metric": m, "value": ""})
                continue
            mean_val, std_val = lookup(m)
            val = format_mean_std(mean_val, std_val)
            rows.append({"metric": m, "value": val})
        return rows

    t1_rows = build_section(PAPER_METRICS_TABLE_1)
    t2_rows = build_section(PAPER_METRICS_TABLE_2)
    t3a_rows = build_section(PAPER_METRICS_TABLE_3A)
    t3b_rows = build_section(PAPER_METRICS_TABLE_3B)
    t3c_rows = build_section(PAPER_METRICS_TABLE_3C)
    appendix_rows = build_section(PAPER_METRICS_APPENDIX)

    md_lines = []
    md_lines.append("# Aggregated Paper Metrics\n")
    md_lines.append("## Table 1 — Surface Measurement (OTE–polarity)\n")
    md_lines.append(to_markdown_table(t1_rows, ["metric", "value"]))
    md_lines.append(f"\n{TABLE_NOTES['TABLE_1']}\n")

    md_lines.append("\n## Table 2 — Schema Projection (entity#attribute–polarity)\n")
    md_lines.append(to_markdown_table(t2_rows, ["metric", "value"]))
    md_lines.append(f"\n{TABLE_NOTES['TABLE_2']}\n")

    md_lines.append("\n## Table 3 — Process (fix/break)\n")
    md_lines.append("\n### 3A Error Reduction\n")
    md_lines.append(to_markdown_table(t3a_rows, ["metric", "value"]))
    md_lines.append(f"\n{TABLE_NOTES['TABLE_3A']}\n")

    md_lines.append("\n### 3B Error Detection\n")
    md_lines.append(to_markdown_table(t3b_rows, ["metric", "value"]))
    md_lines.append(f"\n{TABLE_NOTES['TABLE_3B']}\n")

    # Subset IRR (conflict, implicit, negation) — aggregate across run_dirs when multiple seeds
    subset_irr_rows: list[dict] = []
    if args.run_dirs:
        run_dirs = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs]
        by_subset: dict[str, list[dict]] = {}
        for d in run_dirs:
            subset_path = d / "irr" / "irr_subset_summary.json"
            if subset_path.exists():
                try:
                    data = json.loads(subset_path.read_text(encoding="utf-8"))
                    for subset_name, sub in (data or {}).items():
                        if isinstance(sub, dict) and sub.get("n", 0) > 0:
                            by_subset.setdefault(subset_name, []).append(sub)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        for subset_name, subs in by_subset.items():
            meas_vals = [v for s in subs for v in [s.get("meas_cohen_kappa_mean")] if v is not None and v == v]
            irr_vals = [v for s in subs for v in [s.get("irr_cohen_kappa_mean")] if v is not None and v == v]
            n_total = sum(s.get("n", 0) for s in subs)
            meas_mean = mean(meas_vals) if meas_vals else None
            irr_mean = mean(irr_vals) if irr_vals else None
            subset_irr_rows.append({
                "subset": subset_name,
                "n": n_total,
                "Measurement IRR": f"{meas_mean:.4f}" if meas_mean is not None and meas_mean == meas_mean else "N/A",
                "Action IRR": f"{irr_mean:.4f}" if irr_mean is not None and irr_mean == irr_mean else "N/A",
            })
    if subset_irr_rows:
        md_lines.append("\n## Subset IRR\n")
        md_lines.append(to_markdown_table(subset_irr_rows, ["subset", "n", "Measurement IRR", "Action IRR"]))
        md_lines.append("\n**Note.** Subset IRR: conflict cases, implicit cases, negation cases. Measurement IRR = final decision agreement. Action IRR = reviewer action agreement.\n")

    md_lines.append("\n## Overall IRR\n")
    md_lines.append(to_markdown_table(t3c_rows, ["metric", "value"]))
    md_lines.append(f"\n{TABLE_NOTES['TABLE_3C']}\n")

    appendix_has_data = any(r.get("value") != "N/A" for r in appendix_rows)
    if appendix_has_data:
        md_lines.append("\n## Appendix — Diagnostics\n")
        md_lines.append(to_markdown_table(appendix_rows, ["metric", "value"]))
        md_lines.append(f"\n{TABLE_NOTES['APPENDIX']}\n")

    # Post-hoc Construct Alignment (when semantic_alignment_metrics.json exists)
    sem_align_rows = build_section(PAPER_METRICS_SEMANTIC_ALIGNMENT)
    sem_align_has_data = any(r.get("value") != "N/A" for r in sem_align_rows)
    if sem_align_has_data:
        md_lines.append("\n## Post-hoc Construct Alignment\n")
        md_lines.append(to_markdown_table(sem_align_rows, ["metric", "value"]))

    out_md = out_dir / "paper_metrics_aggregated.md"
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[OK] wrote: {out_md}")

    # M0 vs M1 comparison with Δ 95% CI (seed-level bootstrap)
    if args.agg_path_m1 and args.agg_path_m1.exists() and args.run_dirs_m1:
        agg_path_m1 = args.agg_path_m1.resolve()
        if not agg_path_m1.is_absolute():
            agg_path_m1 = (PROJECT_ROOT / agg_path_m1).resolve()
        run_dirs_m0 = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in (args.run_dirs or [])]
        run_dirs_m0 = [d for d in run_dirs_m0 if d.is_dir()]
        run_dirs_m1 = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs_m1]
        run_dirs_m1 = [d for d in run_dirs_m1 if d.is_dir()]
        if run_dirs_m0 and run_dirs_m1:
            agg_m1: dict[str, dict[str, str]] = {}
            with agg_path_m1.open("r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    m = row.get("metric", "").strip()
                    if m:
                        agg_m1[m] = {"mean": row.get("mean", ""), "std": row.get("std", "")}
            # M1 semantic alignment from run_dirs_m1
            sem_m1_paths = [d / "derived" / "semantic_alignment" / "semantic_alignment_metrics.json" for d in run_dirs_m1]
            if any(p.exists() for p in sem_m1_paths):
                for k in PAPER_METRICS_SEMANTIC_ALIGNMENT:
                    vals: list[float] = []
                    for p in sem_m1_paths:
                        if not p.exists():
                            continue
                        try:
                            data = json.loads(p.read_text(encoding="utf-8"))
                            v = data.get(k)
                            if v is not None and v == v and v != float("inf"):
                                vals.append(float(v))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                    if vals:
                        m, s = summarize_across_seeds(vals)
                        agg_m1[k] = {"mean": str(m), "std": str(s)}
            m0_per_seed = _load_per_seed_structural_metrics(run_dirs_m0)
            m1_per_seed = _load_per_seed_structural_metrics(run_dirs_m1)
            metrics_1a_1b = [
                m for m in PAPER_METRICS_TABLE_1 + PAPER_METRICS_TABLE_2 + PAPER_METRICS_TABLE_3A + PAPER_METRICS_TABLE_3B
                if not m.startswith("---")
            ]
            delta_ci = _bootstrap_delta_ci(m0_per_seed, m1_per_seed, metrics_1a_1b)
            def lookup_m1(paper_name: str) -> tuple[str, str]:
                if paper_name in agg_m1:
                    r = agg_m1[paper_name]
                    return r.get("mean", ""), r.get("std", "")
                fn = PAPER_METRICS_CORE_FALLBACK.get(paper_name)
                if fn and fn in agg_m1:
                    r = agg_m1[fn]
                    return r.get("mean", ""), r.get("std", "")
                return "", ""
            comp_rows: list[dict] = []
            comp_metrics = (
                PAPER_METRICS_TABLE_1 + PAPER_METRICS_TABLE_2 + PAPER_METRICS_TABLE_3A + PAPER_METRICS_TABLE_3B
            )
            for m in comp_metrics:
                if m.startswith("---"):
                    comp_rows.append({"metric": m, "M0": "", "M1": "", "Δ (M1−M0)": "", "Δ 95% CI": ""})
                    continue
                m0_mean, m0_std = lookup(m)
                m1_mean, m1_std = lookup_m1(m)
                m0_val = format_mean_std(m0_mean, m0_std)
                m1_val = format_mean_std(m1_mean, m1_std)
                dci = delta_ci.get(m)
                if dci:
                    mean_d, lo, hi = dci
                    delta_str = f"{mean_d:.4f}"
                    ci_str = _format_delta_ci(mean_d, lo, hi)
                else:
                    delta_str = "N/A"
                    ci_str = "N/A"
                comp_rows.append({
                    "metric": m,
                    "M0": m0_val,
                    "M1": m1_val,
                    "Δ (M1−M0)": delta_str,
                    "Δ 95% CI": ci_str,
                })
            comp_md = []
            comp_md.append("# M0 vs M1 Comparison (Δ 95% CI, seed-level bootstrap n=2000)\n")
            comp_md.append("## Table 1 (Surface) + Table 2 (Projection) + Table 3A/3B (Error Control)\n")
            comp_md.append(to_markdown_table(comp_rows, ["metric", "M0", "M1", "Δ (M1−M0)", "Δ 95% CI"]))
            # Post-hoc Construct Alignment (M0 vs M1)
            sem_comp_rows: list[dict] = []
            for m in PAPER_METRICS_SEMANTIC_ALIGNMENT:
                m0_mean, m0_std = lookup(m)
                m1_mean, m1_std = lookup_m1(m)
                m0_val = format_mean_std(m0_mean, m0_std)
                m1_val = format_mean_std(m1_mean, m1_std)
                try:
                    d = float(m1_mean or 0) - float(m0_mean or 0) if m0_mean and m1_mean else float("nan")
                    delta_str = f"{d:.4f}" if d == d else "N/A"
                except (TypeError, ValueError):
                    delta_str = "N/A"
                sem_comp_rows.append({"metric": m, "M0": m0_val, "M1": m1_val, "Δ (M1−M0)": delta_str})
            if any(r.get("M0") != "N/A" or r.get("M1") != "N/A" for r in sem_comp_rows):
                comp_md.append("\n## Post-hoc Construct Alignment\n")
                comp_md.append(to_markdown_table(sem_comp_rows, ["metric", "M0", "M1", "Δ (M1−M0)"]))
            comp_path = out_dir / "paper_metrics_aggregated_comparison.md"
            comp_path.write_text("\n".join(comp_md), encoding="utf-8")
            print(f"[OK] wrote: {comp_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
