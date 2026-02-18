#!/usr/bin/env python3
"""
CR 브랜치 ref-pol 관련 진단:
1. Stage1 aspect_ref 채움 비율
2. Stage2 polarity flip이 ref-pol에 반영되는 케이스 수
3. Stage1 vs Stage2 ref-pol pair difference count
4. Gold 대비 ref coverage rate
5. 구조통제: term level vs ref level

Usage:
  python scripts/diagnose_cr_refpol_metrics.py --input results/cr_n50_m0_v4_aggregated/merged_scorecards.jsonl --out reports/cr_refpol_diagnostic_report.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import normalize_for_eval, normalize_polarity, tuples_to_ref_pairs


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _get_parsed_output(record: Dict[str, Any]) -> Dict[str, Any]:
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    return parsed


def _extract_stage1_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Raw stage1_tuples from final_result."""
    parsed = _get_parsed_output(record)
    fr = parsed.get("final_result") or {}
    s1 = fr.get("stage1_tuples")
    if s1 and isinstance(s1, list):
        return s1
    return []


def _extract_final_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Raw final_tuples from final_result."""
    parsed = _get_parsed_output(record)
    fr = parsed.get("final_result") or {}
    s2 = fr.get("final_tuples")
    if s2 and isinstance(s2, list):
        return s2
    return []


def _extract_gold_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gold tuples from inputs."""
    inputs = record.get("inputs") or {}
    gt = inputs.get("gold_tuples")
    if gt and isinstance(gt, list):
        return gt
    gt = inputs.get("gold_triplets")
    if gt and isinstance(gt, list):
        return gt
    return []


def _tuple_to_tuple_set(items: List[Dict[str, Any]]) -> Set[Tuple[str, str, str]]:
    """Convert list of dicts to EvalTuple set (aspect_ref, aspect_term, polarity)."""
    out: Set[Tuple[str, str, str]] = set()
    for it in items or []:
        if not it or not isinstance(it, dict):
            continue
        a = normalize_for_eval((it.get("aspect_ref") or it.get("term") or "").strip())
        t = it.get("aspect_term")
        if isinstance(t, dict):
            t = (t.get("term") or "").strip()
        elif isinstance(t, str):
            t = t.strip()
        else:
            t = (it.get("opinion_term") or {}).get("term", "") if isinstance(it.get("opinion_term"), dict) else ""
        t = normalize_for_eval(t) if t else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
        if a or t:
            out.add((a, t, p))
    return out


def run_diagnostic(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all diagnostic metrics."""
    n_total = len(rows)
    total_s1_tuples = 0
    s1_ref_filled = 0
    s1_ref_empty = 0
    total_s2_tuples = 0
    s2_ref_filled = 0
    s2_ref_empty = 0
    total_gold_tuples = 0
    gold_ref_filled = 0
    gold_ref_empty = 0

    polarity_flip_refpol_n = 0  # same ref, different polarity in s1 vs s2
    delta_pairs_sum = 0
    delta_pairs_symmetric_sum = 0
    n_changed = 0

    gold_refs_covered_by_pred_s1 = 0
    gold_refs_total = 0
    n_has_gold = 0

    for record in rows:
        s1_raw = _extract_stage1_tuples_raw(record)
        s2_raw = _extract_final_tuples_raw(record)
        gold_raw = _extract_gold_tuples_raw(record)

        s1_tuples = _tuple_to_tuple_set(s1_raw)
        s2_tuples = _tuple_to_tuple_set(s2_raw)
        gold_tuples = _tuple_to_tuple_set(gold_raw)

        # 1. Stage1 aspect_ref 채움
        for t in s1_raw:
            if not t or not isinstance(t, dict):
                continue
            ref = (t.get("aspect_ref") or "").strip()
            total_s1_tuples += 1
            if ref:
                s1_ref_filled += 1
            else:
                s1_ref_empty += 1

        for t in s2_raw:
            if not t or not isinstance(t, dict):
                continue
            ref = (t.get("aspect_ref") or "").strip()
            total_s2_tuples += 1
            if ref:
                s2_ref_filled += 1
            else:
                s2_ref_empty += 1

        for t in gold_raw:
            if not t or not isinstance(t, dict):
                continue
            ref = (t.get("aspect_ref") or t.get("term") or "").strip()
            total_gold_tuples += 1
            if ref:
                gold_ref_filled += 1
            else:
                gold_ref_empty += 1

        # 2. ref-pol pairs
        s1_pairs, s1_invalid = tuples_to_ref_pairs(s1_tuples)
        s2_pairs, s2_invalid = tuples_to_ref_pairs(s2_tuples)
        gold_pairs, _ = tuples_to_ref_pairs(gold_tuples)

        # 3. Polarity flip: same ref, different polarity
        s1_by_ref: Dict[str, str] = {r: p for (r, p) in s1_pairs}
        s2_by_ref: Dict[str, str] = {r: p for (r, p) in s2_pairs}
        common_refs = set(s1_by_ref.keys()) & set(s2_by_ref.keys())
        flip_count = sum(1 for r in common_refs if s1_by_ref[r] != s2_by_ref[r])
        if flip_count > 0:
            polarity_flip_refpol_n += 1

        # 4. Stage1 vs Stage2 pair difference
        n_s1 = len(s1_pairs)
        n_s2 = len(s2_pairs)
        delta_pairs_sum += abs(n_s2 - n_s1)
        symmetric = len(s1_pairs ^ s2_pairs)  # symmetric difference
        delta_pairs_symmetric_sum += symmetric
        if s1_pairs != s2_pairs:
            n_changed += 1

        # 5. Gold ref coverage
        if gold_pairs:
            n_has_gold += 1
            gold_refs = set(r for (r, _) in gold_pairs)
            gold_refs_total += len(gold_refs)
            pred_refs_s1 = set(r for (r, _) in s1_pairs)
            covered = len(gold_refs & pred_refs_s1)
            gold_refs_covered_by_pred_s1 += covered

    # Rates
    s1_ref_fill_rate = s1_ref_filled / total_s1_tuples if total_s1_tuples else None
    s2_ref_fill_rate = s2_ref_filled / total_s2_tuples if total_s2_tuples else None
    gold_ref_fill_rate = gold_ref_filled / total_gold_tuples if total_gold_tuples else None

    gold_ref_coverage_rate = gold_refs_covered_by_pred_s1 / gold_refs_total if gold_refs_total else None

    return {
        "n_samples": n_total,
        "stage1_aspect_ref_filled": s1_ref_filled,
        "stage1_aspect_ref_empty": s1_ref_empty,
        "stage1_total_tuples": total_s1_tuples,
        "stage1_ref_fill_rate": s1_ref_fill_rate,
        "stage2_aspect_ref_filled": s2_ref_filled,
        "stage2_aspect_ref_empty": s2_ref_empty,
        "stage2_total_tuples": total_s2_tuples,
        "stage2_ref_fill_rate": s2_ref_fill_rate,
        "gold_aspect_ref_filled": gold_ref_filled,
        "gold_aspect_ref_empty": gold_ref_empty,
        "gold_total_tuples": total_gold_tuples,
        "gold_ref_fill_rate": gold_ref_fill_rate,
        "polarity_flip_refpol_sample_n": polarity_flip_refpol_n,
        "polarity_flip_refpol_sample_rate": polarity_flip_refpol_n / n_total if n_total else None,
        "delta_pairs_count_mean": delta_pairs_sum / n_total if n_total else None,
        "delta_pairs_symmetric_mean": delta_pairs_symmetric_sum / n_total if n_total else None,
        "stage1_to_final_changed_n": n_changed,
        "stage1_to_final_changed_rate": n_changed / n_total if n_total else None,
        "gold_refs_total": gold_refs_total,
        "gold_refs_covered_by_pred_s1": gold_refs_covered_by_pred_s1,
        "gold_ref_coverage_rate": gold_ref_coverage_rate,
        "n_samples_with_gold": n_has_gold,
    }


def main():
    ap = argparse.ArgumentParser(description="CR ref-pol diagnostic")
    ap.add_argument("--input", required=True, type=Path, help="merged_scorecards.jsonl or scorecards.jsonl")
    ap.add_argument("--out", type=Path, help="Output report path")
    args = ap.parse_args()

    rows = load_jsonl(args.input)
    if not rows:
        print(f"[ERROR] No rows in {args.input}", file=sys.stderr)
        sys.exit(1)

    result = run_diagnostic(rows)

    lines = [
        "# CR ref-pol 진단 보고서",
        "",
        f"**입력**: {args.input}",
        f"**샘플 수**: {result['n_samples']}",
        "",
        "---",
        "",
        "## 1. Stage1 aspect_ref 채움 비율",
        "",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| Stage1 총 튜플 수 | {result['stage1_total_tuples']} |",
        f"| aspect_ref 채움 | {result['stage1_aspect_ref_filled']} |",
        f"| aspect_ref 비움 | {result['stage1_aspect_ref_empty']} |",
        f"| **채움 비율** | {(result['stage1_ref_fill_rate']*100):.1f}% |" if result['stage1_ref_fill_rate'] is not None else "| **채움 비율** | N/A |",
        "",
        "---",
        "",
        "## 2. Stage2 polarity flip이 ref-pol에 반영되는 케이스 수",
        "",
        "동일 aspect_ref에 대해 Stage1과 Final에서 polarity가 다른 샘플 수:",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| polarity flip 샘플 수 | {result['polarity_flip_refpol_sample_n']} |",
        f"| polarity flip 샘플 비율 | {(result['polarity_flip_refpol_sample_rate']*100):.1f}% |" if result['polarity_flip_refpol_sample_rate'] is not None else "| polarity flip 샘플 비율 | N/A |",
        "",
        "---",
        "",
        "## 3. Stage1 vs Stage2 ref-pol pair difference count",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| changed 샘플 수 (s1_pairs ≠ s2_pairs) | {result['stage1_to_final_changed_n']} |",
        f"| changed 샘플 비율 | {(result['stage1_to_final_changed_rate']*100):.1f}% |" if result['stage1_to_final_changed_rate'] is not None else "| changed 샘플 비율 | N/A |",
        f"| delta_pairs 평균 (|n_s2 - n_s1|) | {result['delta_pairs_count_mean']:.2f}" if result['delta_pairs_count_mean'] is not None else "| delta_pairs 평균 | N/A |",
        f"| symmetric difference 평균 (|s1^s2|) | {result['delta_pairs_symmetric_mean']:.2f}" if result['delta_pairs_symmetric_mean'] is not None else "| symmetric difference 평균 | N/A |",
        "",
        "---",
        "",
        "## 4. Gold 대비 ref coverage rate",
        "",
        "Gold의 (aspect_ref, polarity) 쌍 중, Stage1 pred가 동일 ref를 가진 gold pair를 커버하는 비율:",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| Gold 총 ref 수 (unique) | {result['gold_refs_total']} |",
        f"| Stage1 pred가 커버한 gold ref 수 | {result['gold_refs_covered_by_pred_s1']} |",
        f"| **Gold ref coverage rate** | {(result['gold_ref_coverage_rate']*100):.1f}% |" if result['gold_ref_coverage_rate'] is not None else "| **Gold ref coverage rate** | N/A |",
        "",
        "---",
        "",
        "## 5. 구조통제: term level vs ref level",
        "",
        "**CR v2 브랜치**:",
        "",
        "- **stage_delta.changed** SSOT: `s1_pairs != s2_pairs` (tuples_to_ref_pairs 사용)",
        "- **s1_pairs, s2_pairs**: (aspect_ref, polarity) 쌍 — **ref level**",
        "- **평가 단위**: GoldUnit = (aspect_ref, polarity). match_by_aspect_ref=True (기본값)",
        "- **결론**: 현재 구조통제는 **ref level** (ref-pol pairs). term level이 아님.",
        "",
        "---",
        "",
        "## 6. Gold aspect_ref 채움",
        "",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| Gold 총 튜플 수 | {result['gold_total_tuples']} |",
        f"| Gold aspect_ref 채움 | {result['gold_aspect_ref_filled']} |",
        f"| Gold aspect_ref 비움 | {result['gold_aspect_ref_empty']} |",
        f"| Gold ref 채움 비율 | {(result['gold_ref_fill_rate']*100):.1f}% |" if result['gold_ref_fill_rate'] is not None else "| Gold ref 채움 비율 | N/A |",
        "",
    ]

    report = "\n".join(lines)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"[OK] Wrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
