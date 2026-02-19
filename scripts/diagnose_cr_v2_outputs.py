#!/usr/bin/env python3
"""
cr_v2_patch 산출물 진단: granularity_overlap_candidate, REDUNDANT_UPPER_REF, Rule3 DROP, 패키지·구성품.
Usage: python scripts/diagnose_cr_v2_outputs.py --run-dirs results/cr_v2_n100_m0_v1__seed42_proposed ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _get_analysis_flags(row: dict) -> dict:
    """analysis_flags from outputs (top-level) or scorecards (flags.analysis_flags)."""
    return (row.get("analysis_flags") or row.get("flags", {}).get("analysis_flags") or {})


def count_granularity_overlap(scorecards_path: Path) -> int:
    n = 0
    for line in scorecards_path.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            flags = _get_analysis_flags(row).get("conflict_flags") or []
            for f in flags:
                if (f.get("conflict_type") or "").strip() == "granularity_overlap_candidate":
                    n += 1
        except json.JSONDecodeError:
            continue
    return n


def count_redundant_upper_ref_drop(outputs_path: Path) -> int:
    """Review C에서 action_type=DROP, reason_code=REDUNDANT_UPPER_REF."""
    n = 0
    for line in outputs_path.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            actions = (row.get("analysis_flags") or {}).get("review_actions") or []
            for a in actions:
                actor = (a.get("actor") or "").strip().upper()
                if actor != "C":
                    continue
                atype = (a.get("action_type") or a.get("type") or "").strip().upper()
                reason = (a.get("reason_code") or "").strip().upper()
                if atype == "DROP" and reason == "REDUNDANT_UPPER_REF":
                    n += 1
        except json.JSONDecodeError:
            continue
    return n


def count_rule3_drop_selected(outputs_path: Path) -> int:
    """Arbiter가 1FLIP+1DROP+1KEEP 상황에서 DROP 선택한 케이스."""
    n = 0
    for line in outputs_path.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            arb_actions = (row.get("analysis_flags") or {}).get("arb_actions") or []
            review_actions = (row.get("analysis_flags") or {}).get("review_actions") or []
            # Group by tuple_id
            by_tid: Dict[str, List[Dict]] = {}
            for a in review_actions:
                for tid in a.get("target_tuple_ids") or []:
                    by_tid.setdefault(tid, []).append(a)
            for arb in arb_actions:
                tids = arb.get("target_tuple_ids") or []
                atype = (arb.get("action_type") or "").strip().upper()
                if atype != "DROP":
                    continue
                for tid in tids:
                    votes = by_tid.get(tid, [])
                    atypes = [(v.get("action_type") or v.get("type") or "KEEP").strip().upper() for v in votes]
                    atypes = [a if a != "MERGE" else "KEEP" for a in atypes]
                    if set(atypes) == {"FLIP", "DROP", "KEEP"}:
                        n += 1
                        break
        except json.JSONDecodeError:
            continue
    return n


def find_package_component_fp_fn(scorecards_path: Path) -> List[Dict[str, Any]]:
    """패키지/구성품 또는 패키지·구성품 관련 FP/FN 예시 1~2개."""
    examples = []
    for line in scorecards_path.read_text(encoding="utf-8", errors="replace").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            gold = (row.get("inputs") or {}).get("sentence_sentiment", {}).get("gold_tuples") or row.get("gold_tuples") or []
            pred = row.get("final_tuples") or row.get("stage2_tuples") or (row.get("final_result") or {}).get("final_tuples") or []
            text_id = row.get("meta", {}).get("text_id", "")
            for g in gold:
                ref = (g.get("aspect_ref") or "").strip()
                if "패키지" in ref or "구성품" in ref:
                    examples.append({
                        "text_id": text_id,
                        "gold_ref": ref,
                        "type": "gold_has_package",
                        "gold": g,
                    })
                    if len(examples) >= 2:
                        return examples
            for p in pred:
                ref = (p.get("aspect_ref") or "").strip()
                if "패키지" in ref or "구성품" in ref:
                    examples.append({
                        "text_id": text_id,
                        "pred_ref": ref,
                        "type": "pred_has_package",
                        "pred": p,
                    })
                    if len(examples) >= 2:
                        return examples
        except json.JSONDecodeError:
            continue
    return examples


def main():
    ap = argparse.ArgumentParser(description="cr_v2 output diagnostics")
    ap.add_argument("--run-dirs", required=True, help="Comma-separated run dirs")
    args = ap.parse_args()
    run_dirs = [PROJECT_ROOT / d.strip() for d in args.run_dirs.split(",")]
    run_dirs = [d for d in run_dirs if d.is_dir()]

    print("=== cr_v2_patch 산출물 진단 ===\n")
    total_gran = 0
    total_red = 0
    total_r3 = 0
    for rd in run_dirs:
        sc = rd / "scorecards.jsonl"
        out = rd / "outputs.jsonl"
        if not sc.exists():
            print(f"[SKIP] {rd.name}: no scorecards.jsonl")
            continue
        gran = count_granularity_overlap(sc)
        total_gran += gran
        red = count_redundant_upper_ref_drop(out) if out.exists() else 0
        total_red += red
        r3 = count_rule3_drop_selected(out) if out.exists() else 0
        total_r3 += r3
        print(f"{rd.name}: granularity_overlap_candidate={gran}, REDUNDANT_UPPER_REF DROP={red}, Rule3 DROP선택={r3}")

    print(f"\n총계: granularity_overlap_candidate={total_gran}, REDUNDANT_UPPER_REF DROP={total_red}, Rule3 DROP선택={total_r3}")

    if run_dirs:
        ex = find_package_component_fp_fn(run_dirs[0] / "scorecards.jsonl")
        print("\n패키지/구성품 관련 예시 (1~2):")
        for e in ex:
            print(json.dumps(e, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
