#!/usr/bin/env python3
"""
CR v1 메트릭 진단: conflict_detection_rate, pre_conflict vs no_conflict, IRR, Stage1 variance.

Usage:
  python scripts/diagnose_cr_metrics.py --base-run-id cr_n50_m0 --mode proposed --seeds 42,123,456
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get(d: dict, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _read_jsonl(p: Path) -> List[dict]:
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


def main() -> int:
    ap = argparse.ArgumentParser(description="CR v1 metrics diagnostic")
    ap.add_argument("--base-run-id", type=str, default="cr_n50_m0")
    ap.add_argument("--mode", type=str, default="proposed")
    ap.add_argument("--seeds", type=str, default="42,123,456")
    args = ap.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    results_dir = PROJECT_ROOT / "results"

    lines: List[str] = []
    lines.append("# CR v1 Metrics Diagnostic Report")
    lines.append("")
    lines.append(f"**Run**: {args.base_run_id} | seeds: {seeds}")
    lines.append("")

    # 1) conflict_detection_rate raw (from outputs.jsonl)
    lines.append("## 1. conflict_detection_rate (raw from outputs.jsonl)")
    lines.append("")
    lines.append("**정의**: `analysis_flags.conflict_flags` 비어있지 않은 샘플 비율 (Merge 시점, pre-review)")
    lines.append("**export_paper_metrics_aggregated에서 N/A**: aggregated_mean_std.csv는 structural_error_aggregator 산출만 포함. aggregator는 conflict_detection_rate를 계산하지 않음. outputs.jsonl에서 별도 계산 필요.")
    lines.append("")

    all_conflict_counts: Dict[str, List[int]] = {}
    conflict_rates = []
    for seed in seeds:
        out_path = results_dir / f"{args.base_run_id}__seed{seed}_{args.mode}" / "outputs.jsonl"
        recs = _read_jsonl(out_path)
        n = len(recs)
        conflict_n = 0
        conflict_per_sample = []
        for r in recs:
            cf = _get(r, "analysis_flags.conflict_flags") or []
            if cf:
                conflict_n += 1
            conflict_per_sample.append(len(cf))
        rate = conflict_n / n if n else 0
        conflict_rates.append(rate)
        all_conflict_counts[seed] = conflict_per_sample
        lines.append(f"- **seed {seed}**: {conflict_n}/{n} = {rate:.4f} ({conflict_n} samples with ≥1 conflict_flag)")
    if conflict_rates:
        avg = sum(conflict_rates) / len(conflict_rates)
        lines.append(f"- **평균 (seeds)**: {avg:.4f}")
    lines.append("")

    # 2) pre_conflict vs no_conflict 비교
    lines.append("## 2. pre_conflict vs no_conflict 비교")
    lines.append("")
    lines.append("| seed | pre_conflict (n) | no_conflict (n) | pre_conflict % |")
    lines.append("|------|------------------|----------------|----------------|")
    for seed in seeds:
        out_path = results_dir / f"{args.base_run_id}__seed{seed}_{args.mode}" / "outputs.jsonl"
        recs = _read_jsonl(out_path)
        pre = sum(1 for r in recs if (_get(r, "analysis_flags.conflict_flags") or []))
        no = len(recs) - pre
        pct = 100 * pre / len(recs) if recs else 0
        lines.append(f"| {seed} | {pre} | {no} | {pct:.1f}% |")
    lines.append("")

    # 3) IRR
    lines.append("## 3. IRR (Inter-Rater Reliability)")
    lines.append("")
    irr_dir = results_dir / f"{args.base_run_id}__seed{seeds[0]}_{args.mode}" / "irr"
    if not (irr_dir / "irr_run_summary.json").exists():
        lines.append("IRR not computed. Run: `python scripts/compute_irr.py --input results/<run>/outputs.jsonl --outdir results/<run>/irr/`")
    else:
        for seed in seeds:
            summary_path = results_dir / f"{args.base_run_id}__seed{seed}_{args.mode}" / "irr" / "irr_run_summary.json"
            if summary_path.exists():
                data = json.loads(summary_path.read_text(encoding="utf-8"))
                k = data.get("mean_kappa")
                f = data.get("mean_fleiss")
                p = data.get("mean_perfect_agreement")
                def _fmt(v):
                    if v is None or (isinstance(v, float) and (v != v or v in (float("inf"), float("-inf")))):
                        return "N/A"
                    return f"{float(v):.4f}"
                lines.append(f"**seed {seed}**:")
                lines.append(f"- Mean Cohen's κ (A-B, A-C, B-C): {_fmt(k)}")
                lines.append(f"- Fleiss' κ: {_fmt(f)}")
                lines.append(f"- Perfect agreement: {_fmt(p)}")
                lines.append(f"- conflict vs no_conflict: {data.get('conflict_vs_no_conflict', {})}")
                lines.append("")
    lines.append("")

    # 4) Stage1 baseline seed variance
    lines.append("## 4. Stage1 baseline seed variance (tuple_f1_s1)")
    lines.append("")
    lines.append("| seed | tuple_f1_s1 | triplet_f1_s1 |")
    lines.append("|------|-------------|---------------|")
    f1_s1_values = []
    for seed in seeds:
        csv_path = results_dir / f"{args.base_run_id}__seed{seed}_{args.mode}" / "derived" / "metrics" / "structural_metrics.csv"
        if not csv_path.exists():
            lines.append(f"| {seed} | (missing) | (missing) |")
            continue
        with csv_path.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        r = rows[0] if rows else {}
        tf1 = r.get("tuple_f1_s1", "N/A")
        trf1 = r.get("triplet_f1_s1", "N/A")
        try:
            f1_s1_values.append(float(tf1))
        except (TypeError, ValueError):
            pass
        lines.append(f"| {seed} | {tf1} | {trf1} |")
    if len(f1_s1_values) >= 2:
        mean_f1 = sum(f1_s1_values) / len(f1_s1_values)
        var_f1 = sum((x - mean_f1) ** 2 for x in f1_s1_values) / len(f1_s1_values)
        std_f1 = var_f1 ** 0.5
        lines.append("")
        lines.append(f"tuple_f1_s1: mean={mean_f1:.4f}, std={std_f1:.4f}")
    lines.append("")

    # 5) polarity_conflict_rate = 0 해석
    lines.append("## 5. polarity_conflict_rate = 0.0000 해석")
    lines.append("")
    lines.append("**에이전트 vs 어그리게이터 차이**:")
    lines.append("- **conflict_flags** (Merge 시점): P-NEG/P-IMP/P-LIT 합친 후 동일 aspect_term에 서로 다른 polarity → **pre-review**")
    lines.append("- **polarity_conflict_rate** (structural_error_aggregator): **final_tuples (post-review)** 기준. Arbiter 적용 후 동일 aspect에 polarity 충돌 남은 샘플 비율")
    lines.append("- **해석**: 0.0 = Arbiter가 충돌을 해소한 후 최종 결과에는 남은 충돌이 없음 (설계상 의도된 동작)")
    lines.append("")
    lines.append("**어그리게이터는 최종 결과(final_tuples)를 봄** — `_get_final_tuples_raw(record)` → `has_polarity_conflict_raw`, `has_polarity_conflict_after_representative`")
    lines.append("")

    # 6) review_intervention_rate & arb_intervention_rate 공식
    lines.append("## 6. review_intervention_rate, arb_intervention_rate 공식")
    lines.append("")
    lines.append("### review_intervention_rate (aggregator: review_action_rate)")
    lines.append("- **공식**: `n_review_action / N`")
    lines.append("- **정의**: `_cr_has_review_actions(r)` = `analysis_flags.review_actions`에 ≥1개 항목이 있는 샘플")
    lines.append("- **주의**: review_actions는 **A/B/C 각각의 합** (Arbiter 합의 전). CR 프로토콜상 A/B/C가 모두 출력하므로 **항목 ≥1**이면 True")
    lines.append("")
    lines.append("### arb_intervention_rate (aggregator)")
    lines.append("- **공식**: `n_arb_intervention / N`")
    lines.append("- **정의**: `_cr_has_arb_intervention(r)` = `analysis_flags.arb_actions`에 ≥1개 항목이 있는 샘플")
    lines.append("- **CR 설계**: Arbiter는 항상 A/B/C actions를 합쳐서 최종 arb_actions를 출력. **액션이 있으면** (KEEP 포함) arb_actions 리스트에 ≥1개")
    lines.append("- **1.0 = 모든 샘플에서 Arbiter가 최소 1개 액션 출력** — 설계상 튜플이 있으면 Arbiter가 각 tuple_id에 대해 KEEP/FLIP/DROP 등 처리")
    lines.append("")

    # 7) Sample-level action counts
    lines.append("## 7. Sample-level action counts (seed 42)")
    lines.append("")
    out_path = results_dir / f"{args.base_run_id}__seed42_{args.mode}" / "outputs.jsonl"
    recs = _read_jsonl(out_path)
    n_has_review = sum(1 for r in recs if (_get(r, "analysis_flags.review_actions") or []))
    n_has_arb = sum(1 for r in recs if (_get(r, "analysis_flags.arb_actions") or []))
    n_has_conflict = sum(1 for r in recs if (_get(r, "analysis_flags.conflict_flags") or []))
    lines.append(f"- n_review_actions ≥ 1: {n_has_review}/{len(recs)}")
    lines.append(f"- n_arb_actions ≥ 1: {n_has_arb}/{len(recs)}")
    lines.append(f"- n_conflict_flags ≥ 1: {n_has_conflict}/{len(recs)}")
    lines.append("")
    # action type distribution
    action_types: Dict[str, int] = {}
    for r in recs:
        for a in _get(r, "analysis_flags.arb_actions") or []:
            t = (a.get("action_type") or a.get("type") or "KEEP").strip().upper()
            action_types[t] = action_types.get(t, 0) + 1
    lines.append("Arbiter action_type distribution (all samples):")
    for t, c in sorted(action_types.items(), key=lambda x: -x[1]):
        lines.append(f"- {t}: {c}")
    lines.append("")

    # Write report
    out_path = results_dir / f"{args.base_run_id}_diagnostic_report.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
