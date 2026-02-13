#!/usr/bin/env python3
"""
집계본 aggregated_mean_std.csv → paper_metrics_aggregated.md 생성.

mean/std 컬럼을 "mean ± std" 형식으로 합쳐서 논문용 마크다운 작성.

Optional: --run-dirs로 outputs.jsonl에서 conflict_detection_rate, review_nontrivial_action_rate,
arb_nonkeep_rate 직접 계산. --run-dirs와 동일 경로의 irr/irr_run_summary.json에서 IRR 메트릭 수집.

Usage:
  python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv
  python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0__seed42_proposed results/cr_n50_m0__seed123_proposed results/cr_n50_m0__seed456_proposed --out-dir results/cr_n50_m0_paper
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean, pstdev

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Table 1. Overall Outcome (RQ1)
PAPER_METRICS_CORE = [
    "tuple_f1_s1",
    "tuple_f1_s2",
    "delta_f1",
    "fix_rate",
    "break_rate",
    "net_gain",
    "implicit_invalid_pred_rate",
    "polarity_conflict_rate",
    "N_agg_fallback_used",
]

# Table 2. Reliability / Stability (RQ2) — IRR
PAPER_METRICS_RQ2_IRR = [
    "irr_fleiss_kappa",
    "irr_cohen_kappa_mean",
    "irr_perfect_agreement_rate",
    "irr_majority_agreement_rate",
]

# IRR JSON key → paper metric name
IRR_JSON_TO_PAPER = {
    "mean_fleiss": "irr_fleiss_kappa",
    "mean_kappa": "irr_cohen_kappa_mean",
    "mean_perfect_agreement": "irr_perfect_agreement_rate",
    "mean_majority_agreement": "irr_majority_agreement_rate",
}

# Table 3. Process Evidence (CR)
PAPER_METRICS_PROCESS = [
    "conflict_detection_rate",
    "pre_to_post_change_rate",
    "review_nontrivial_action_rate",
    "arb_nonkeep_rate",
]

# aggregator 컬럼 → paper 컬럼 (aggregated_mean_std에는 aggregator 이름으로 저장됨)
AGG_TO_PAPER = {
    "review_action_rate": "review_intervention_rate",
    "changed_samples_rate": "pre_to_post_change_rate",
}


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
        return "", ""

    def build_section(metric_list: list[str]) -> list[dict]:
        rows = []
        for m in metric_list:
            mean_val, std_val = lookup(m)
            val = format_mean_std(mean_val, std_val)
            rows.append({"metric": m, "value": val})
        return rows

    core_rows = build_section(PAPER_METRICS_CORE)
    rq2_irr_rows = build_section(PAPER_METRICS_RQ2_IRR)
    proc_rows = build_section(PAPER_METRICS_PROCESS)

    md_lines = []
    md_lines.append("# Aggregated Paper Metrics\n")
    md_lines.append("## Table 1. Overall Outcome (RQ1)\n")
    md_lines.append(to_markdown_table(core_rows, ["metric", "value"]))

    rq2_has_data = any(r.get("value") != "N/A" for r in rq2_irr_rows)
    if rq2_has_data:
        md_lines.append("\n## Table 2. Reliability / Stability (RQ2)\n")
        md_lines.append(to_markdown_table(rq2_irr_rows, ["metric", "value"]))

    md_lines.append("\n## Table 3. Process Evidence (CR)\n")
    md_lines.append(to_markdown_table(proc_rows, ["metric", "value"]))

    out_md = out_dir / "paper_metrics_aggregated.md"
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[OK] wrote: {out_md}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
