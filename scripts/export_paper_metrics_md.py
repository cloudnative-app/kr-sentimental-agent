#!/usr/bin/env python3
"""
논문용 메트릭만 추려 paper_metrics.md, paper_metrics.csv 생성.

우선순위: structural_metrics.csv (aggregator 산출) → 없으면 outputs.jsonl에서 CR process만 계산.

Usage:
  python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0 --mode proposed
  python scripts/export_paper_metrics_md.py --run-glob "results/cr_n50_m0__seed*_proposed" --out-dir results/cr_n50_m0_paper
  python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0 --mode proposed --no-csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 논문용 컬럼 세트 (권장 고정)
PAPER_METRICS_CORE = [
    "tuple_f1_s1", "tuple_f1_s2", "delta_f1",
    "fix_rate", "break_rate", "net_gain",
    "implicit_invalid_pred_rate",
    "polarity_conflict_rate",
    "N_agg_fallback_used",
]

# Table 2. Reliability / Stability (RQ2) — IRR 또는 기존
PAPER_METRICS_RQ2_IRR = [
    "irr_fleiss_kappa",
    "irr_cohen_kappa_mean",
    "irr_perfect_agreement_rate",
    "irr_majority_agreement_rate",
]
PAPER_METRICS_RQ2_OPTIONAL = [
    "tuple_agreement_rate",
    "polarity_conflict_rate_repeat",
]
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

# aggregator 컬럼 → paper 컬럼 매핑 (없는 컬럼은 outputs에서 계산)
AGG_TO_PAPER = {
    "review_action_rate": "review_nontrivial_action_rate",
    "changed_samples_rate": "pre_to_post_change_rate",
}


def _get(d: dict, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _read_jsonl(p: Path) -> list[dict]:
    rows = []
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _normalize_actions(actions: list) -> list:
    if not isinstance(actions, list):
        return []
    norm = []
    for a in actions:
        if not isinstance(a, dict):
            continue
        t = (a.get("type") or a.get("action_type") or "").upper()
        tup = a.get("tuple_id")
        payload = {k: a.get(k) for k in ["tuple_ids", "polarity", "risk_type"] if k in a}
        norm.append((t, tup, json.dumps(payload, sort_keys=True)))
    return sorted(norm)


def compute_cr_process_from_outputs(outputs_path: Path) -> dict:
    """outputs.jsonl에서 CR process 4개만 계산. (conflict/pre_to_post + review_nontrivial/arb_nonkeep)"""
    recs = _read_jsonl(outputs_path)
    n = len(recs) if recs else 1

    conflict = 0
    review_nontrivial = 0
    arb_nonkeep = 0
    changed = 0

    for r in recs:
        conflicts = _get(r, "analysis_flags.conflict_flags") or []
        if len(conflicts) > 0:
            conflict += 1

        review_actions = _get(r, "analysis_flags.review_actions") or []
        if any((a.get("type") or a.get("action_type") or "KEEP").strip().upper() != "KEEP" for a in review_actions):
            review_nontrivial += 1

        arb_actions = _get(r, "analysis_flags.arb_actions") or []
        if any((a.get("type") or a.get("action_type") or "KEEP").strip().upper() != "KEEP" for a in arb_actions):
            arb_nonkeep += 1

        pre = _get(r, "final_result.final_tuples_pre_review") or []
        post = _get(r, "final_result.final_tuples_post_review") or _get(r, "final_result.final_tuples") or []
        if pre != post:
            changed += 1

    return {
        "conflict_detection_rate": conflict / n,
        "pre_to_post_change_rate": changed / n,
        "review_nontrivial_action_rate": review_nontrivial / n,
        "arb_nonkeep_rate": arb_nonkeep / n,
    }


def _format_val(v, float_fmt: str = "{:.4f}") -> str:
    if v is None or (isinstance(v, float) and (v != v or v == float("inf") or v == float("-inf"))):
        return "N/A"
    if isinstance(v, float):
        return float_fmt.format(v)
    return str(v)


def to_markdown_table(rows: list[dict], columns: list[str], float_fmt: str = "{:.4f}") -> str:
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
    for row in rows:
        vals = [_format_val(row.get(c), float_fmt) for c in columns]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Export paper metrics from structural_metrics.csv or outputs.jsonl"
    )
    ap.add_argument(
        "--base-run-id",
        type=str,
        help="Base run ID (e.g. cr_n50_m0). Inferred run dirs: results/<base>__seed*_<mode>",
    )
    ap.add_argument(
        "--run-glob",
        type=str,
        help="Glob pattern for run dirs (e.g. results/cr_n50_m0__seed*_proposed). Overrides --base-run-id.",
    )
    ap.add_argument(
        "--mode",
        type=str,
        default="proposed",
        help="Run mode suffix (default: proposed)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output dir (default: results/<base_run_id>_paper)",
    )
    ap.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not write paper_metrics.csv",
    )
    ap.add_argument(
        "--results-root",
        type=Path,
        default=PROJECT_ROOT / "results",
        help="Results root (default: results/)",
    )
    args = ap.parse_args()

    if args.run_glob:
        run_dirs = sorted(glob.glob(str(args.run_glob)))
    elif args.base_run_id:
        pattern = str(args.results_root / f"{args.base_run_id}__seed*_{args.mode}")
        run_dirs = sorted(glob.glob(pattern))
        base_run_id = args.base_run_id
    else:
        print("[ERROR] Provide --base-run-id or --run-glob", file=sys.stderr)
        return 1

    if not run_dirs:
        print(f"[ERROR] No run dirs matched", file=sys.stderr)
        return 1

    if not args.base_run_id and args.run_glob:
        # Infer base from first dir, e.g. cr_n50_m0__seed42_proposed -> cr_n50_m0
        first_name = Path(run_dirs[0]).name
        if "__seed" in first_name:
            base_run_id = first_name.split("__seed")[0]
        else:
            base_run_id = first_name.replace(f"_{args.mode}", "")
    elif args.base_run_id:
        base_run_id = args.base_run_id
    else:
        base_run_id = "run"

    out_dir = args.out_dir or (args.results_root / f"{base_run_id}_paper")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_cols = PAPER_METRICS_CORE + PAPER_METRICS_RQ2_IRR + PAPER_METRICS_RQ2_OPTIONAL + PAPER_METRICS_PROCESS
    rows = []

    for rd in run_dirs:
        rd = Path(rd)
        seed_name = rd.name
        metrics_csv = rd / "derived" / "metrics" / "structural_metrics.csv"
        outputs_path = rd / "outputs.jsonl"

        row: dict = {"run": seed_name}

        if metrics_csv.exists():
            with metrics_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                recs = list(reader)
            rec = recs[0].copy() if recs else {}

            for k in PAPER_METRICS_CORE + PAPER_METRICS_RQ2_IRR + PAPER_METRICS_RQ2_OPTIONAL:
                v = rec.get(k)
                if v is not None and v != "":
                    try:
                        row[k] = float(v)
                    except (TypeError, ValueError):
                        row[k] = v
                else:
                    row[k] = None

            # IRR: irr/irr_run_summary.json에서 로드
            irr_path = (rd.resolve() if not rd.is_absolute() else rd) / "irr" / "irr_run_summary.json"
            if irr_path.exists():
                try:
                    irr_data = json.loads(irr_path.read_text(encoding="utf-8"))
                    for irr_key, paper_name in IRR_JSON_TO_PAPER.items():
                        v = irr_data.get(irr_key)
                        if v is not None and v == v:
                            row[paper_name] = float(v)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

            # Process: pre_to_post_change_rate는 aggregator changed_samples_rate와 동일
            csv_pre_post = rec.get("pre_to_post_change_rate") or rec.get("changed_samples_rate")
            if csv_pre_post is not None and csv_pre_post != "":
                try:
                    row["pre_to_post_change_rate"] = float(csv_pre_post)
                except (TypeError, ValueError):
                    row["pre_to_post_change_rate"] = None
            else:
                row["pre_to_post_change_rate"] = None

            # conflict_detection_rate, review_nontrivial_action_rate, arb_nonkeep_rate: outputs에서만 계산
            if outputs_path.exists():
                proc = compute_cr_process_from_outputs(outputs_path)
                row["conflict_detection_rate"] = proc.get("conflict_detection_rate")
                row["review_nontrivial_action_rate"] = proc.get("review_nontrivial_action_rate")
                row["arb_nonkeep_rate"] = proc.get("arb_nonkeep_rate")
                if row.get("pre_to_post_change_rate") is None:
                    row["pre_to_post_change_rate"] = proc.get("pre_to_post_change_rate")
            else:
                row["conflict_detection_rate"] = None
                row["review_nontrivial_action_rate"] = None
                row["arb_nonkeep_rate"] = None

        else:
            # CSV 없으면 outputs에서 process만 계산
            if not outputs_path.exists():
                print(f"[WARN] Missing CSV and outputs: {rd}", file=sys.stderr)
                for k in all_cols:
                    row[k] = None
            else:
                proc = compute_cr_process_from_outputs(outputs_path)
                for k in PAPER_METRICS_CORE + PAPER_METRICS_RQ2_IRR + PAPER_METRICS_RQ2_OPTIONAL:
                    row[k] = None
                for k, v in proc.items():
                    row[k] = v
                irr_path = (rd.resolve() if not rd.is_absolute() else rd) / "irr" / "irr_run_summary.json"
                if irr_path.exists():
                    try:
                        irr_data = json.loads(irr_path.read_text(encoding="utf-8"))
                        for irr_key, paper_name in IRR_JSON_TO_PAPER.items():
                            v = irr_data.get(irr_key)
                            if v is not None and v == v:
                                row[paper_name] = float(v)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        pass

        rows.append(row)

    # 마크다운 섹션
    core_cols = ["run"] + [c for c in PAPER_METRICS_CORE if c in (rows[0] if rows else {})]
    rq2_irr_cols = ["run"] + [c for c in PAPER_METRICS_RQ2_IRR if c in (rows[0] if rows else {})]
    rq2_opt_cols = ["run"] + [c for c in PAPER_METRICS_RQ2_OPTIONAL if c in (rows[0] if rows else {})]
    proc_cols = ["run"] + [c for c in PAPER_METRICS_PROCESS if c in (rows[0] if rows else {})]

    md = []
    md.append("# Paper Metrics Export\n")
    md.append("## Table 1. Overall Outcome (RQ1)\n")
    md.append(to_markdown_table(rows, core_cols))

    rq2_irr_has_data = any(r.get(c) is not None for r in rows for c in PAPER_METRICS_RQ2_IRR if c in rq2_irr_cols)
    if rq2_irr_has_data:
        md.append("\n## Table 2. Reliability / Stability (RQ2)\n")
        md.append(to_markdown_table(rows, rq2_irr_cols))

    rq2_opt_has_data = any(r.get(c) is not None for r in rows for c in PAPER_METRICS_RQ2_OPTIONAL if c in rq2_opt_cols)
    if rq2_opt_has_data:
        md.append("\n## RQ2 Stability Metrics (Repeat, Optional)\n")
        md.append(to_markdown_table(rows, rq2_opt_cols))

    md.append("\n## Table 3. Process Evidence (CR)\n")
    md.append(to_markdown_table(rows, proc_cols))

    # validator/risk 계열 제외 권고 (CR은 0 → N/A로 오해 방지)
    md.append("\n---\n")
    md.append("*Note: validator/risk 계열(validator_clear_rate 등)은 CR에서 0 반환. 논문 표에서는 제외 권장.*\n")

    out_md = out_dir / "paper_metrics.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"[OK] wrote: {out_md}")

    if not args.no_csv:
        out_csv = out_dir / "paper_metrics.csv"
        csv_cols = ["run"] + [c for c in all_cols if c in (rows[0] if rows else {})]
        with out_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=csv_cols, restval="", extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: ("" if v is None else v) for k, v in r.items() if k in csv_cols})
        print(f"[OK] wrote: {out_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
