#!/usr/bin/env python3
"""
Break root cause analysis for CR v2: S1✓S2✗ 샘플 추출, 액션 유형별 기여도, implicit/explicit F1, changed∧improved/degraded.

Usage:
  python scripts/break_root_cause_analysis.py --scorecards results/cr_n50_m2_v2__seed42_proposed/scorecards.jsonl --output reports/cr_break_root_cause_report.md
  python scripts/break_root_cause_analysis.py --scorecards results/cr_n50_m2_v2_aggregated/merged_scorecards.jsonl --output reports/cr_break_root_cause_merged.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from metrics.eval_tuple import (
    gold_implicit_polarities_from_tuples,
    gold_tuple_set_from_record,
    normalize_for_eval,
    normalize_polarity,
    precision_recall_f1_implicit_only,
    precision_recall_f1_tuple,
    pred_valid_polarities_from_tuples,
    tuple_sets_match_with_empty_rule,
)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _get_runtime(record: Dict[str, Any]) -> Dict[str, Any]:
    """Scorecard: inputs.runtime; fallback: record.runtime."""
    return record.get("runtime") or (record.get("inputs") or {}).get("runtime") or {}


def _extract_stage1_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    runtime = _get_runtime(record)
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    fr = parsed.get("final_result") or {}
    stage1 = fr.get("stage1_tuples")
    if stage1 and isinstance(stage1, list):
        return _tuples_from_list(stage1)
    trace = parsed.get("process_trace") or record.get("process_trace") or []
    for e in trace:
        if (e.get("stage") or "").lower() == "stage1" and (e.get("agent") or "").lower() == "atsa":
            sents = (e.get("output") or {}).get("aspect_sentiments")
            if sents:
                return _tuples_from_list(sents)
    return set()


def _extract_final_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    runtime = _get_runtime(record)
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    fr = parsed.get("final_result") or {}
    final = fr.get("final_tuples") or fr.get("final_aspects")
    if final and isinstance(final, list):
        return _tuples_from_list(final)
    return set()


def _tuples_from_list(items: Any) -> Set[Tuple[str, str, str]]:
    out: Set[Tuple[str, str, str]] = set()
    if not items or not isinstance(items, (list, tuple)):
        return out
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        a = normalize_for_eval((it.get("aspect_ref") or "").strip())
        t = _aspect_term_text(it)
        t = normalize_for_eval(t) if t else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
        if a or t or (p and p.strip()):
            out.add((a, t, p))
    return out


def _aspect_term_text(it: dict) -> str:
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return ""


def _get_arb_actions(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime = _get_runtime(record)
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    flags = parsed.get("analysis_flags") or record.get("flags") or {}
    if isinstance(flags, dict) and "analysis_flags" in flags:
        flags = flags["analysis_flags"]
    arb = flags.get("arb_actions") or []
    return arb if isinstance(arb, list) else []


def _get_review_actions(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime = _get_runtime(record)
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    flags = parsed.get("analysis_flags") or record.get("flags") or {}
    if isinstance(flags, dict) and "analysis_flags" in flags:
        flags = flags["analysis_flags"]
    ra = flags.get("review_actions") or []
    return ra if isinstance(ra, list) else []


def _action_type(a: Dict[str, Any]) -> str:
    t = (a.get("action_type") or a.get("type") or "KEEP").strip().upper()
    if t in ("FLIP_POS", "FLIP_NEG", "FLIP"):
        return "FLIP"
    return t


def _classify_break_cause(
    record: Dict[str, Any],
    gold: Set[Tuple[str, str, str]],
    s1: Set[Tuple[str, str, str]],
    s2: Set[Tuple[str, str, str]],
) -> str:
    """Classify break cause: DROP, MERGE, polarity_change, representative_selection."""
    arb = _get_arb_actions(record)
    action_types = [_action_type(a) for a in arb]
    has_drop = "DROP" in action_types
    has_merge = "MERGE" in action_types
    has_flip = "FLIP" in action_types

    gold_pairs = {(normalize_for_eval(t or a), normalize_polarity(p)) for (a, t, p) in gold}
    s1_pairs = {(normalize_for_eval(t or a), normalize_polarity(p)) for (a, t, p) in s1}
    s2_pairs = {(normalize_for_eval(t or a), normalize_polarity(p)) for (a, t, p) in s2}

    n_s1 = len(s1)
    n_s2 = len(s2)
    n_gold = len(gold)

    if has_drop and n_s2 < n_s1:
        return "DROP"
    if has_merge and n_s2 < n_s1:
        return "MERGE"
    if has_flip:
        s1_pols = {(normalize_for_eval(t or a), p) for (a, t, p) in s1}
        s2_pols = {(normalize_for_eval(t or a), p) for (a, t, p) in s2}
        for (term, pol) in gold_pairs:
            s1_has = any(p == pol and (normalize_for_eval(t or a) == term) for (a, t, p) in s1)
            s2_has = any(p == pol and (normalize_for_eval(t or a) == term) for (a, t, p) in s2)
            if s1_has and not s2_has:
                return "polarity_change"
    if n_s1 > n_gold or n_s2 < n_s1:
        if not has_drop and not has_merge and not has_flip:
            return "representative_selection"
    if has_drop:
        return "DROP"
    if has_merge:
        return "MERGE"
    if has_flip:
        return "polarity_change"
    return "representative_selection"


def run_analysis(scorecards_path: Path) -> Dict[str, Any]:
    rows = _load_jsonl(scorecards_path)
    rows_with_gold = [
        (r, gold_tuple_set_from_record(r))
        for r in rows
        if gold_tuple_set_from_record(r) is not None and len(gold_tuple_set_from_record(r) or set()) > 0
    ]
    rows_with_gold = [(r, g) for r, g in rows_with_gold if g]

    break_samples: List[Dict[str, Any]] = []
    action_break_counts: Dict[str, int] = {"DROP": 0, "MERGE": 0, "FLIP": 0, "other": 0}
    n_fix = n_break = n_keep = n_still = 0
    changed_improved = 0
    changed_degraded = 0
    changed_total = 0

    f1_s1_explicit_list: List[float] = []
    f1_s1_implicit_list: List[float] = []
    f1_s2_explicit_list: List[float] = []
    f1_s2_implicit_list: List[float] = []

    for record, gold in rows_with_gold:
        gold = gold or set()
        s1 = _extract_stage1_tuples(record)
        s2 = _extract_final_tuples(record)
        st1 = tuple_sets_match_with_empty_rule(gold, s1)
        st2 = tuple_sets_match_with_empty_rule(gold, s2)

        if not st1 and st2:
            n_fix += 1
        elif st1 and not st2:
            n_break += 1
            cause = _classify_break_cause(record, gold, s1, s2)
            text_id = (record.get("meta") or {}).get("text_id") or (record.get("runtime") or {}).get("uid") or ""
            input_text = (record.get("meta") or {}).get("input_text") or ""
            arb = _get_arb_actions(record)
            action_types = [_action_type(a) for a in arb]
            break_samples.append({
                "text_id": text_id,
                "input_text": input_text[:80] + "..." if len(input_text) > 80 else input_text,
                "cause": cause,
                "arb_actions": action_types,
                "gold_n": len(gold),
                "s1_n": len(s1),
                "s2_n": len(s2),
            })
            if cause == "DROP":
                action_break_counts["DROP"] += 1
            elif cause == "MERGE":
                action_break_counts["MERGE"] += 1
            elif cause == "polarity_change":
                action_break_counts["FLIP"] += 1
            else:
                action_break_counts["other"] += 1
        elif st1 and st2:
            n_keep += 1
        else:
            n_still += 1

        changed = st1 != st2
        if changed:
            changed_total += 1
            if not st1 and st2:
                changed_improved += 1
            elif st1 and not st2:
                changed_degraded += 1

        gold_explicit, gold_implicit = _split_gold(gold)
        if gold_explicit:
            _, _, f1_s1_ex = precision_recall_f1_tuple(gold_explicit, s1)
            _, _, f1_s2_ex = precision_recall_f1_tuple(gold_explicit, s2)
            f1_s1_explicit_list.append(f1_s1_ex)
            f1_s2_explicit_list.append(f1_s2_ex)
        if gold_implicit:
            gold_impl_pols = gold_implicit_polarities_from_tuples(gold)
            pred_s1, _ = pred_valid_polarities_from_tuples(s1)
            pred_s2, _ = pred_valid_polarities_from_tuples(s2)
            _, _, f1_s1_im = precision_recall_f1_implicit_only(gold_impl_pols, pred_s1)
            _, _, f1_s2_im = precision_recall_f1_implicit_only(gold_impl_pols, pred_s2)
            f1_s1_implicit_list.append(f1_s1_im)
            f1_s2_implicit_list.append(f1_s2_im)

    n_total = len(rows_with_gold)
    break_rate = n_break / (n_break + n_keep) if (n_break + n_keep) > 0 else 0
    total_breaks = action_break_counts["DROP"] + action_break_counts["MERGE"] + action_break_counts["FLIP"] + action_break_counts["other"]
    drop_pct = 100 * action_break_counts["DROP"] / total_breaks if total_breaks > 0 else 0
    merge_pct = 100 * action_break_counts["MERGE"] / total_breaks if total_breaks > 0 else 0
    flip_pct = 100 * action_break_counts["FLIP"] / total_breaks if total_breaks > 0 else 0
    other_pct = 100 * action_break_counts["other"] / total_breaks if total_breaks > 0 else 0

    return {
        "n_total": n_total,
        "n_break": n_break,
        "n_fix": n_fix,
        "n_keep": n_keep,
        "n_still": n_still,
        "break_rate": break_rate,
        "break_samples": break_samples[:20],
        "action_break_counts": action_break_counts,
        "drop_break_pct": drop_pct,
        "merge_break_pct": merge_pct,
        "flip_break_pct": flip_pct,
        "other_break_pct": other_pct,
        "changed_improved": changed_improved,
        "changed_degraded": changed_degraded,
        "changed_total": changed_total,
        "changed_improved_rate": changed_improved / changed_total if changed_total > 0 else 0,
        "changed_degraded_rate": changed_degraded / changed_total if changed_total > 0 else 0,
        "f1_s1_explicit": sum(f1_s1_explicit_list) / len(f1_s1_explicit_list) if f1_s1_explicit_list else None,
        "f1_s2_explicit": sum(f1_s2_explicit_list) / len(f1_s2_explicit_list) if f1_s2_explicit_list else None,
        "f1_s1_implicit": sum(f1_s1_implicit_list) / len(f1_s1_implicit_list) if f1_s1_implicit_list else None,
        "f1_s2_implicit": sum(f1_s2_implicit_list) / len(f1_s2_implicit_list) if f1_s2_implicit_list else None,
    }


def _split_gold(gold: Set[Tuple[str, str, str]]) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str, str]]]:
    explicit, implicit = set(), set()
    for (a, t, p) in gold:
        tn = normalize_for_eval((t or "").strip())
        if tn:
            explicit.add((a, t, p))
        else:
            implicit.add((a, t, p))
    return explicit, implicit


def write_report(result: Dict[str, Any], out_path: Path, source: str = "") -> None:
    lines = [
        "# CR Break Root Cause Analysis Report",
        "",
        f"**Source**: {source}",
        "",
        "---",
        "",
        "## 1. S1✓ S2✗ 샘플 20개 추출 및 원인 분류",
        "",
    ]
    for i, s in enumerate(result["break_samples"], 1):
        lines.append(f"### {i}. {s['text_id']}")
        lines.append("")
        lines.append(f"- **input_text**: {s['input_text']}")
        cause_display = "대표선택" if s["cause"] == "representative_selection" else s["cause"]
        lines.append(f"- **원인**: **{cause_display}**")
        lines.append(f"- **arb_actions**: {s['arb_actions']}")
        lines.append(f"- gold_n={s['gold_n']}, s1_n={s['s1_n']}, s2_n={s['s2_n']}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 2. 액션 유형별 break 기여도",
        "",
        "| 액션 | break 건수 | 비율 (%) |",
        "|------|------------|----------|",
        f"| DROP | {result['action_break_counts']['DROP']} | {result['drop_break_pct']:.1f}% |",
        f"| MERGE | {result['action_break_counts']['MERGE']} | {result['merge_break_pct']:.1f}% |",
        f"| FLIP (polarity 변경) | {result['action_break_counts']['FLIP']} | {result['flip_break_pct']:.1f}% |",
        f"| 기타 (대표선택 등) | {result['action_break_counts']['other']} | {result['other_break_pct']:.1f}% |",
        "",
        "---",
        "",
        "## 3. Implicit vs Explicit F1",
        "",
        "| 구분 | S1 F1 | S2 F1 | Δ |",
        "|------|-------|-------|---|",
    ])
    ex_s1 = result.get("f1_s1_explicit")
    ex_s2 = result.get("f1_s2_explicit")
    im_s1 = result.get("f1_s1_implicit")
    im_s2 = result.get("f1_s2_implicit")
    if ex_s1 is not None and ex_s2 is not None:
        delta_ex = ex_s2 - ex_s1
        lines.append(f"| explicit | {ex_s1:.4f} | {ex_s2:.4f} | {delta_ex:+.4f} |")
    else:
        lines.append("| explicit | N/A | N/A | N/A |")
    if im_s1 is not None and im_s2 is not None:
        delta_im = im_s2 - im_s1
        lines.append(f"| implicit | {im_s1:.4f} | {im_s2:.4f} | {delta_im:+.4f} |")
    else:
        lines.append("| implicit | N/A | N/A | N/A |")
    lines.append("")
    if im_s1 is not None and im_s2 is not None and ex_s1 is not None and ex_s2 is not None:
        delta_im = im_s2 - im_s1
        delta_ex = ex_s2 - ex_s1
        if delta_im < delta_ex - 0.05:
            lines.append("**해석**: implicit F1 하락이 explicit보다 큼 → ReviewC가 implicit을 과도하게 깎고 있을 가능성")
        else:
            lines.append("**해석**: explicit/implicit 하락 패턴 확인")
    lines.extend([
        "",
        "---",
        "",
        "## 4. Review action과 correctness 관계",
        "",
        "| 구분 | 건수 | 비율 (changed 대비) |",
        "|------|------|---------------------|",
        f"| changed ∧ improved | {result['changed_improved']} | {100*result['changed_improved_rate']:.1f}% |",
        f"| changed ∧ degraded | {result['changed_degraded']} | {100*result['changed_degraded_rate']:.1f}% |",
        "",
        f"**changed 총계**: {result['changed_total']} (전체 {result['n_total']} 중)",
        "",
        "---",
        "",
        "## 5. 요약",
        "",
        f"- **break_rate**: {result['break_rate']:.2%} (n_break={result['n_break']}, n_keep={result['n_keep']})",
        f"- **break 원인 1순위**: DROP {result['drop_break_pct']:.1f}%, MERGE {result['merge_break_pct']:.1f}%, FLIP {result['flip_break_pct']:.1f}%",
        f"- **changed∧degraded**: {100*result['changed_degraded_rate']:.1f}% (변경된 샘플 중)",
        "",
    ])
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Break root cause analysis for CR v2")
    ap.add_argument("--scorecards", type=Path, required=True, help="Scorecards JSONL path")
    ap.add_argument("--output", type=Path, required=True, help="Output report path")
    args = ap.parse_args()
    sc_path = args.scorecards.resolve()
    if not sc_path.is_absolute():
        sc_path = (PROJECT_ROOT / sc_path).resolve()
    if not sc_path.exists():
        print(f"[ERROR] Not found: {sc_path}", file=sys.stderr)
        return 1
    out_path = args.output.resolve()
    if not out_path.is_absolute():
        out_path = (PROJECT_ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_analysis(sc_path)
    write_report(result, out_path, source=str(sc_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
