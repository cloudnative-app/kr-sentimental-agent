#!/usr/bin/env python3
"""
Ghost change & structural consistency diagnostic.

Checks:
1. Ghost change: stage_delta.changed=False (or s1_pairs==s2_pairs) but f1_s1 != f1_s2_raw
2. s1_pairs vs s2_pairs set equality for changed=False samples
3. break_rate (tuple_sets_match) vs F1 (precision_recall_f1) criteria consistency

Usage:
  python scripts/ghost_change_diagnostic.py --scorecards results/cr_n50_m0_v2_aggregated/merged_scorecards.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from metrics.eval_tuple import (
    normalize_for_eval,
    normalize_polarity,
    precision_recall_f1_tuple,
    tuple_sets_match_with_empty_rule,
    tuples_to_ref_pairs,
)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
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
    return record.get("runtime") or (record.get("inputs") or {}).get("runtime") or {}


def _aspect_term_text(it: dict) -> str:
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return ((it.get("opinion_term") or {}).get("term") or "").strip()


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


def _extract_gold_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    from metrics.eval_tuple import gold_tuple_set_from_record
    return gold_tuple_set_from_record(record) or set()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecards", required=True, help="Path to merged_scorecards.jsonl")
    ap.add_argument("--max-ghost", type=int, default=20, help="Max ghost change samples to print")
    args = ap.parse_args()
    path = Path(args.scorecards)
    if not path.exists():
        print(f"Not found: {path}")
        sys.exit(1)

    rows = _load_jsonl(path)
    # Dedupe by text_id (take first per text_id for merged)
    seen: Dict[str, Dict] = {}
    for r in rows:
        tid = (r.get("meta") or {}).get("text_id") or (r.get("runtime") or {}).get("uid") or ""
        if tid and tid not in seen:
            seen[tid] = r
    records = list(seen.values()) if seen else rows

    n_gold = 0
    n_changed_delta = 0
    n_changed_pairs = 0
    ghost_changes: List[Dict[str, Any]] = []
    pairs_equal_f1_diff: List[Dict[str, Any]] = []
    break_match_f1_inconsistent: List[Dict[str, Any]] = []

    for r in records:
        gold = _extract_gold_tuples(r)
        if not gold:
            continue
        n_gold += 1

        s1 = _extract_stage1_tuples(r)
        s2 = _extract_final_tuples(r)

        s1_pairs, _ = tuples_to_ref_pairs(s1) if s1 else (set(), 0)
        s2_pairs, _ = tuples_to_ref_pairs(s2) if s2 else (set(), 0)

        stage_delta = r.get("stage_delta") or {}
        changed_delta = bool(stage_delta.get("changed", False))
        changed_pairs = s1_pairs != s2_pairs

        if changed_delta:
            n_changed_delta += 1
        if changed_pairs:
            n_changed_pairs += 1

        _, _, f1_s1 = precision_recall_f1_tuple(gold, s1)
        _, _, f1_s2 = precision_recall_f1_tuple(gold, s2)

        st1 = tuple_sets_match_with_empty_rule(gold, s1)
        st2 = tuple_sets_match_with_empty_rule(gold, s2)
        is_break = st1 and not st2

        # 1) Ghost change: changed=False (delta) but F1 differs
        if not changed_delta and abs(f1_s1 - f1_s2) > 1e-6:
            ghost_changes.append({
                "text_id": (r.get("meta") or {}).get("text_id", ""),
                "changed_delta": changed_delta,
                "changed_pairs": changed_pairs,
                "f1_s1": f1_s1,
                "f1_s2": f1_s2,
                "delta_f1": f1_s2 - f1_s1,
                "s1_pairs_eq_s2": s1_pairs == s2_pairs,
                "n_s1": len(s1_pairs),
                "n_s2": len(s2_pairs),
            })

        # 2) Pairs equal (tuples_to_ref_pairs) but F1 differs
        if s1_pairs == s2_pairs and abs(f1_s1 - f1_s2) > 1e-6:
            pairs_equal_f1_diff.append({
                "text_id": (r.get("meta") or {}).get("text_id", ""),
                "f1_s1": f1_s1,
                "f1_s2": f1_s2,
            })

        # 3) break vs F1: st1 and not st2 (break) - check if F1 dropped
        if is_break:
            break_match_f1_inconsistent.append({
                "text_id": (r.get("meta") or {}).get("text_id", ""),
                "f1_s1": f1_s1,
                "f1_s2": f1_s2,
                "st1": st1,
                "st2": st2,
            })

    # Report
    print("=" * 60)
    print("GHOST CHANGE & STRUCTURAL CONSISTENCY DIAGNOSTIC")
    print("=" * 60)
    print(f"Input: {path}")
    print(f"N with gold: {n_gold}")
    print(f"N changed (stage_delta.changed): {n_changed_delta}")
    print(f"N changed (s1_pairs != s2_pairs): {n_changed_pairs}")
    print()

    print("1. GHOST CHANGE (changed_delta=False but f1_s1 != f1_s2_raw)")
    print("-" * 50)
    if not ghost_changes:
        print("  None found.")
    else:
        print(f"  Total: {len(ghost_changes)}")
        for g in ghost_changes[: args.max_ghost]:
            print(f"  - {g['text_id']}: f1_s1={g['f1_s1']:.4f} f1_s2={g['f1_s2']:.4f} delta={g['delta_f1']:+.4f}")
            print(f"    s1_pairs==s2_pairs: {g['s1_pairs_eq_s2']}")
    print()

    print("2. PAIRS EQUAL (tuples_to_pairs) BUT F1 DIFFERS")
    print("-" * 50)
    if not pairs_equal_f1_diff:
        print("  None found. (pairs equal => F1 same, as expected)")
    else:
        print(f"  Total: {len(pairs_equal_f1_diff)}  <-- CRITICAL: normalization path mismatch")
        for p in pairs_equal_f1_diff[: args.max_ghost]:
            print(f"  - {p['text_id']}: f1_s1={p['f1_s1']:.4f} f1_s2={p['f1_s2']:.4f} s1_ref==s2_ref: {p['s1_pairs_ref_eq_s2_ref']}")
    print()

    print("3. BREAK_RATE vs F1 CRITERIA")
    print("-" * 50)
    print("  break_rate: tuple_sets_match_with_empty_rule(gold, pred) -> prec=1 and rec=1")
    print("  F1: precision_recall_f1_tuple(gold, pred) -> same normalize_for_eval, normalize_polarity")
    print("  Both use match_by_aspect_ref=True (CR v2 ref-level), match_empty_aspect_by_polarity_only=True")
    print(f"  N break samples: {len(break_match_f1_inconsistent)}")
    if break_match_f1_inconsistent:
        for b in break_match_f1_inconsistent[:5]:
            print(f"  - {b['text_id']}: f1_s1={b['f1_s1']:.4f} f1_s2={b['f1_s2']:.4f}")
    print()

    # Summary for report
    summary = {
        "n_gold": n_gold,
        "n_changed_delta": n_changed_delta,
        "n_changed_pairs": n_changed_pairs,
        "ghost_change_n": len(ghost_changes),
        "pairs_equal_f1_diff_n": len(pairs_equal_f1_diff),
        "break_n": len(break_match_f1_inconsistent),
    }
    print("SUMMARY (for report)")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
