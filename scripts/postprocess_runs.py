"""
Postprocess merged scorecards (multi-run) to derive root-cause labels, stability metrics, and a concise report.

Expected input: scorecards_3runs.jsonl (or similar) produced by run_mini_suite.py
Each record should contain meta.run, meta.case_id, meta.case_type, final_result.label, summary.quality_pass, etc.

Outputs (written alongside the merged file unless --outdir is provided):
  - scorecards_with_root.jsonl : per-record diagnostics with PASS/FAIL + root_cause + failure_stage + fix_location
  - stability_metrics.json      : per-case and per-case_type stability (pass_rate_mean, pass_rate_worst, flip rates)
  - pretest_report.md           : human-friendly summary (stability table + top failure_stage/fix_location)

Heuristics for root cause:
  - PASS -> root_cause = "none", failure_stage = "none", fix_location = "none"
  - If low_valid_aspect_rate:
        * if any filtered_aspects drop_reason == other_not_target -> root_cause="other_not_target", failure_stage="ATE", fix_location="target_filter/allowlist"
        * else -> root_cause="span_error", failure_stage="ATE", fix_location="ATE_span_rule"
  - If low_opinion_grounded_rate or low_evidence_relevance_score -> root_cause="grounding", failure_stage="ATSA", fix_location="ATSA_evidence/prompt"
  - If targetless_missing_sentence_sentiment -> root_cause="targetless_policy", failure_stage="policy", fix_location="sentence_sentiment_logic"
  - Fallback -> root_cause="unknown", failure_stage="unknown", fix_location="tbd"
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def infer_root(record: Dict[str, Any]) -> Tuple[str, str, str]:
    summary = record.get("summary", {}) or {}
    fail_reasons = summary.get("fail_reasons", []) or []
    if not fail_reasons:
        return "none", "none", "none"

    inputs = record.get("inputs", {}) or {}
    filtered = inputs.get("filtered_aspects") or []
    drops = [f for f in filtered if f.get("action") == "drop"]

    if "low_valid_aspect_rate" in fail_reasons:
        if any(d.get("drop_reason") == "other_not_target" for d in drops):
            return "other_not_target", "ATE", "target_filter/allowlist"
        return "span_error", "ATE", "ATE_span_rule"

    if ("low_opinion_grounded_rate" in fail_reasons) or ("low_evidence_relevance_score" in fail_reasons):
        return "grounding", "ATSA", "ATSA_evidence/prompt"

    if "targetless_missing_sentence_sentiment" in fail_reasons:
        return "targetless_policy", "policy", "sentence_sentiment_logic"

    return "unknown", "unknown", "tbd"


def add_root_labels(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        root, stage, fix = infer_root(r)
        diag = {
            "root_cause": root,
            "failure_stage": stage,
            "fix_location": fix,
        }
        r_out = {**r, "diagnostics": diag}
        out.append(r_out)
    return out


def stability(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_case: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cid = r.get("meta", {}).get("case_id")
        if cid is None:
            continue
        by_case[cid].append(r)

    case_metrics = {}
    flip_flags = []
    pass_flip_flags = []
    type_buckets: Dict[str, List[str]] = defaultdict(list)  # maps case_type -> list of case_ids

    for cid, items in by_case.items():
        items = sorted(items, key=lambda x: x.get("meta", {}).get("run", 0))
        labels = [x.get("final_result", {}).get("label") for x in items]
        passes = [1 if (x.get("summary", {}).get("quality_pass", False)) else 0 for x in items]

        pass_rate_mean = sum(passes) / len(passes)
        pass_rate_worst = min(passes)
        flip = int(len(set(labels)) > 1)
        pass_flip = int(len(set(passes)) > 1)

        case_metrics[cid] = {
            "case_type": items[0].get("meta", {}).get("case_type"),
            "pass_rate_mean": pass_rate_mean,
            "pass_rate_worst": pass_rate_worst,
            "label_flip": flip,
            "pass_flip": pass_flip,
        }
        flip_flags.append(flip)
        pass_flip_flags.append(pass_flip)
        ctype = items[0].get("meta", {}).get("case_type") or "unknown"
        type_buckets[ctype].append(cid)

    # aggregate by case_type
    type_metrics = {}
    for ctype, cids in type_buckets.items():
        vals = [case_metrics[c] for c in cids]
        type_metrics[ctype] = {
            "n_cases": len(cids),
            "pass_rate_mean": sum(v["pass_rate_mean"] for v in vals) / len(vals),
            "pass_rate_worst": sum(v["pass_rate_worst"] for v in vals) / len(vals),
            "label_flip_rate": sum(v["label_flip"] for v in vals) / len(vals),
            "pass_flip_rate": sum(v["pass_flip"] for v in vals) / len(vals),
        }

    overall = {
        "n_cases": len(case_metrics),
        "label_flip_rate": sum(flip_flags) / len(flip_flags) if flip_flags else 0.0,
        "pass_flip_rate": sum(pass_flip_flags) / len(pass_flip_flags) if pass_flip_flags else 0.0,
    }

    return {
        "overall": overall,
        "by_case": case_metrics,
        "by_case_type": type_metrics,
    }


def make_report(metrics: Dict[str, Any], rows: List[Dict[str, Any]]) -> str:
    # Top failure_stage / fix_location among failed records
    failed = [r for r in rows if not r.get("summary", {}).get("quality_pass", False)]
    stage_ctr = Counter(r.get("diagnostics", {}).get("failure_stage", "unknown") for r in failed)
    fix_ctr = Counter(r.get("diagnostics", {}).get("fix_location", "tbd") for r in failed)
    top_stage = stage_ctr.most_common(1)[0] if stage_ctr else ("none", 0)
    top_fix = fix_ctr.most_common(1)[0] if fix_ctr else ("none", 0)

    lines = []
    lines.append("# Pretest Report")
    lines.append("## Stability (overall)")
    lines.append(f"- label_flip_rate: {metrics['overall']['label_flip_rate']:.3f}")
    lines.append(f"- pass_flip_rate: {metrics['overall']['pass_flip_rate']:.3f}")
    lines.append("")
    lines.append("## Stability by case_type")
    lines.append("| case_type | n_cases | pass_mean | pass_worst | label_flip_rate | pass_flip_rate |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for ctype, m in metrics["by_case_type"].items():
        lines.append(
            f"| {ctype} | {m['n_cases']} | {m['pass_rate_mean']:.3f} | {m['pass_rate_worst']:.3f} | "
            f"{m['label_flip_rate']:.3f} | {m['pass_flip_rate']:.3f} |"
        )
    lines.append("")
    lines.append("## Top failure_stage / fix_location (failed only)")
    lines.append(f"- failure_stage top1: {top_stage[0]} ({top_stage[1]})")
    lines.append(f"- fix_location  top1: {top_fix[0]} ({top_fix[1]})")
    lines.append("")
    lines.append("## Go / No-Go heuristic")
    # Simple heuristic: if overall pass_flip_rate < 0.1 and label_flip_rate < 0.1 -> GO else NEEDS_FIX
    go = (metrics["overall"]["pass_flip_rate"] < 0.1) and (metrics["overall"]["label_flip_rate"] < 0.1)
    decision = "GO" if go else "NEEDS_FIX"
    lines.append(f"- decision: **{decision}**")
    if not go:
        lines.append(f"- focus on: failure_stage={top_stage[0]}, fix_location={top_fix[0]}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--merged", required=True, help="Path to merged scorecards (e.g., scorecards_3runs.jsonl)")
    ap.add_argument("--outdir", default=None, help="Output directory; default same as merged file parent")
    args = ap.parse_args()

    merged_path = Path(args.merged)
    outdir = Path(args.outdir) if args.outdir else merged_path.parent
    rows = load_jsonl(merged_path)

    rows_with_root = add_root_labels(rows)
    diag_path = outdir / "scorecards_with_root.jsonl"
    write_jsonl(diag_path, rows_with_root)

    metrics = stability(rows_with_root)
    metrics_path = outdir / "stability_metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    report_md = make_report(metrics, rows_with_root)
    report_path = outdir / "pretest_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    print(f"[done] diagnostics={diag_path}, metrics={metrics_path}, report={report_path}")


if __name__ == "__main__":
    main()
