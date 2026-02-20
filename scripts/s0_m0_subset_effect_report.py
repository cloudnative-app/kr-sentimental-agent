#!/usr/bin/env python3
"""
S0 vs M0 subset effect report: implicit vs explicit, negation, multi-aspect, conflict_flag.
Uses triptych tables (per-sample) and NEGATION_PATTERNS from compute_irr.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

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


def load_triptych(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def load_m0_conflict_flags() -> dict[str, bool]:
    """Load has_conflict per text_id from M0 outputs (seed42)."""
    out = {}
    path = PROJECT / "results" / "cr_v2_n601_m0_v1__seed42_proposed" / "outputs.jsonl"
    if not path.exists():
        return out
    import json
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
        out[text_id] = bool(cf and len(cf) > 0)
    return out


def micro_f1_pair_level(rows: list[dict], match_key: str = "matches_final_vs_gold", gold_key: str = "gold_n_pairs", final_key: str = "final_n_pairs") -> tuple[float, int, int, int, int, int]:
    """
    Pair-level micro F1 (동일 집계 방식: precision_recall_f1_from_pairs).
    TP=matches, FN=gold-matches, FP=final-matches. F1=2*P*R/(P+R).
    Returns (f1, n_samples, n_pairs, tp, fp, fn).
    """
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


def main():
    s0_path = PROJECT / "results" / "cr_v2_n601_s0_v1__seed42_proposed" / "derived_subset" / "triptych.csv"
    m0_path = PROJECT / "results" / "cr_v2_n601_m0_v1__seed42_proposed" / "derived_subset" / "triptych.csv"
    if not s0_path.exists() or not m0_path.exists():
        print("Run structural_error_aggregator with --export_triptych_table first.")
        return 1

    s0_rows = load_triptych(s0_path)
    m0_rows = load_triptych(m0_path)
    m0_conflict = load_m0_conflict_flags()

    # Add has_negation, has_conflict
    for r in s0_rows:
        r["has_negation"] = _has_negation(r.get("text") or "")
        r["has_conflict"] = False  # S0 single agent
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
        if subset == "non_negation":
            return [r for r in rows if not r.get("has_negation")]
        if subset == "single_aspect":
            return [r for r in rows if int(r.get("gold_n_pairs") or 0) == 1]
        if subset == "multi_aspect":
            return [r for r in rows if int(r.get("gold_n_pairs") or 0) > 1]
        if subset == "conflict":
            return [r for r in rows if r.get("has_conflict")]
        if subset == "no_conflict":
            return [r for r in rows if not r.get("has_conflict")]
        return rows

    # Overall pair-level micro F1 (전체 dataset)
    f1_s0_all, n_s0, pairs_s0, tp_s0, fp_s0, fn_s0 = micro_f1_pair_level(s0_rows)
    f1_m0_all, n_m0, pairs_m0, tp_m0, fp_m0, fn_m0 = micro_f1_pair_level(m0_rows)

    report = []
    report.append("# S0 vs M0 subset effect report (seed 42, n=601)")
    report.append("")
    report.append("**집계 방식**: pair-level micro F1 (TP=matches, FN=gold−matches, FP=final−matches, F1=2PR/(P+R)). Subset은 동일 방식으로 TP/FP/FN 합산 후 F1 계산. Partition subset(implicit+explicit)은 weighted recompute로 전체와 일치 검증.")
    report.append("")
    report.append("## 0. Overall pair-level micro F1")
    report.append("")
    report.append("| Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |")
    report.append("|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|")
    report.append(f"| S0 | {n_s0} | {pairs_s0} | {tp_s0} | {fp_s0} | {fn_s0} | {f1_s0_all:.4f} | — |")
    report.append(f"| M0 | {n_m0} | {pairs_m0} | {tp_m0} | {fp_m0} | {fn_m0} | {f1_m0_all:.4f} | **{f1_m0_all - f1_s0_all:+.4f}** |")
    report.append("")
    report.append("## 1. Implicit vs Explicit")
    report.append("")
    report.append("| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |")
    report.append("|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|")

    def _run_subset_pair(sub_s0: list, sub_m0: list, label: str) -> tuple[int, int, int, int, int, int]:
        f1_s0, n_s0, pairs_s0, tp_s0, fp_s0, fn_s0 = micro_f1_pair_level(sub_s0)
        f1_m0, n_m0, pairs_m0, tp_m0, fp_m0, fn_m0 = micro_f1_pair_level(sub_m0)
        report.append(f"| {label} | S0 | {n_s0} | {pairs_s0} | {tp_s0} | {fp_s0} | {fn_s0} | {f1_s0:.4f} | — |")
        report.append(f"| | M0 | {n_m0} | {pairs_m0} | {tp_m0} | {fp_m0} | {fn_m0} | {f1_m0:.4f} | **{f1_m0 - f1_s0:+.4f}** |")
        return tp_s0, fp_s0, fn_s0, tp_m0, fp_m0, fn_m0

    # 1. Implicit vs Explicit (partition)
    tp_i_s0, fp_i_s0, fn_i_s0, tp_i_m0, fp_i_m0, fn_i_m0 = _run_subset_pair(
        by_subset(s0_rows, "implicit"), by_subset(m0_rows, "implicit"), "Implicit (gold aspect_term empty)")
    tp_e_s0, fp_e_s0, fn_e_s0, tp_e_m0, fp_e_m0, fn_e_m0 = _run_subset_pair(
        by_subset(s0_rows, "explicit"), by_subset(m0_rows, "explicit"), "Explicit")

    # Weighted recompute: implicit+explicit = all (partition)
    tp_s0_re, fp_s0_re, fn_s0_re = tp_i_s0 + tp_e_s0, fp_i_s0 + fp_e_s0, fn_i_s0 + fn_e_s0
    tp_m0_re, fp_m0_re, fn_m0_re = tp_i_m0 + tp_e_m0, fp_i_m0 + fp_e_m0, fn_i_m0 + fn_e_m0
    def _weighted_f1(tp, fp, fn):
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    f1_s0_re = _weighted_f1(tp_s0_re, fp_s0_re, fn_s0_re)
    f1_m0_re = _weighted_f1(tp_m0_re, fp_m0_re, fn_m0_re)
    report.append("")
    report.append(f"*Weighted recompute (implicit+explicit → all): S0 F1={f1_s0_re:.4f} (vs overall {f1_s0_all:.4f}), M0 F1={f1_m0_re:.4f} (vs overall {f1_m0_all:.4f})*")
    report.append("")

    report.append("## 2. Negation/Contrast 포함 vs 미포함")
    report.append("")
    report.append("| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |")
    report.append("|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|")

    _run_subset_pair(by_subset(s0_rows, "negation"), by_subset(m0_rows, "negation"), "Negation/Contrast 포함 (lexical cue)")
    _run_subset_pair(by_subset(s0_rows, "non_negation"), by_subset(m0_rows, "non_negation"), "Negation 미포함")
    # Weighted recompute for negation partition
    neg_s0 = by_subset(s0_rows, "negation")
    neg_m0 = by_subset(m0_rows, "negation")
    nneg_s0 = by_subset(s0_rows, "non_negation")
    nneg_m0 = by_subset(m0_rows, "non_negation")
    _, _, _, tp_neg_s0, fp_neg_s0, fn_neg_s0 = micro_f1_pair_level(neg_s0)
    _, _, _, tp_neg_m0, fp_neg_m0, fn_neg_m0 = micro_f1_pair_level(neg_m0)
    _, _, _, tp_nneg_s0, fp_nneg_s0, fn_nneg_s0 = micro_f1_pair_level(nneg_s0)
    _, _, _, tp_nneg_m0, fp_nneg_m0, fn_nneg_m0 = micro_f1_pair_level(nneg_m0)
    f1_neg_re_s0 = _weighted_f1(tp_neg_s0 + tp_nneg_s0, fp_neg_s0 + fp_nneg_s0, fn_neg_s0 + fn_nneg_s0)
    f1_neg_re_m0 = _weighted_f1(tp_neg_m0 + tp_nneg_m0, fp_neg_m0 + fp_nneg_m0, fn_neg_m0 + fn_nneg_m0)
    report.append("")
    report.append(f"*Weighted recompute (negation+non_negation → all): S0 F1={f1_neg_re_s0:.4f}, M0 F1={f1_neg_re_m0:.4f}*")

    report.append("")
    report.append("## 3. Multi-aspect vs Single-aspect")
    report.append("")
    report.append("| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |")
    report.append("|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|")

    sa_s0, sa_m0 = by_subset(s0_rows, "single_aspect"), by_subset(m0_rows, "single_aspect")
    ma_s0, ma_m0 = by_subset(s0_rows, "multi_aspect"), by_subset(m0_rows, "multi_aspect")
    _run_subset_pair(sa_s0, sa_m0, "Single-aspect (gold_n_pairs=1)")
    _run_subset_pair(ma_s0, ma_m0, "Multi-aspect (gold_n_pairs>1)")
    _, _, _, tp_sa_s0, fp_sa_s0, fn_sa_s0 = micro_f1_pair_level(sa_s0)
    _, _, _, tp_sa_m0, fp_sa_m0, fn_sa_m0 = micro_f1_pair_level(sa_m0)
    _, _, _, tp_ma_s0, fp_ma_s0, fn_ma_s0 = micro_f1_pair_level(ma_s0)
    _, _, _, tp_ma_m0, fp_ma_m0, fn_ma_m0 = micro_f1_pair_level(ma_m0)
    f1_sa_re_s0 = _weighted_f1(tp_sa_s0 + tp_ma_s0, fp_sa_s0 + fp_ma_s0, fn_sa_s0 + fn_ma_s0)
    f1_sa_re_m0 = _weighted_f1(tp_sa_m0 + tp_ma_m0, fp_sa_m0 + fp_ma_m0, fn_sa_m0 + fn_ma_m0)
    report.append("")
    report.append(f"*Weighted recompute (single+multi_aspect → all): S0 F1={f1_sa_re_s0:.4f}, M0 F1={f1_sa_re_m0:.4f}*")

    report.append("")
    report.append("## 4. Conflict_flag 발생 vs 비발생 (M0 only, S0 비교 불가)")
    report.append("")
    report.append("*S0는 단일 에이전트이므로 conflict_flag 없음. M0만 집계.*")
    report.append("")
    report.append("| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) |")
    report.append("|--------|-----------|-----------|---------|-----|-----|-----|-----------------|")

    for sub, label in [("conflict", "Conflict 발생"), ("no_conflict", "Conflict 비발생")]:
        m0_sub = by_subset(m0_rows, sub)
        f1_m0, n_m0, pairs_m0, tp_m0, fp_m0, fn_m0 = micro_f1_pair_level(m0_sub)
        report.append(f"| {label} | M0 | {n_m0} | {pairs_m0} | {tp_m0} | {fp_m0} | {fn_m0} | {f1_m0:.4f} |")

    # S0 for no_conflict (same samples as M0 no_conflict)
    m0_no_cf = by_subset(m0_rows, "no_conflict")
    m0_no_cf_ids = {r.get("text_id") for r in m0_no_cf}
    s0_no_cf = [r for r in s0_rows if r.get("text_id") in m0_no_cf_ids]
    f1_s0_nc, _, _, _, _, _ = micro_f1_pair_level(s0_no_cf)
    f1_m0_nc, _, _, _, _, _ = micro_f1_pair_level(m0_no_cf)
    report.append("")
    report.append("*동일 샘플(no_conflict)에 대해 S0 vs M0: S0 F1={:.4f}, M0 F1={:.4f}, Δ={:+.4f}*".format(
        f1_s0_nc, f1_m0_nc, f1_m0_nc - f1_s0_nc))

    out_path = PROJECT / "reports" / "cr_v2_n601_s0_m0_subset_effect_report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
