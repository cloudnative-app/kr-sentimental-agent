#!/usr/bin/env python3
"""
ref-level 산출물(Gold vs Pred) 비교 예시 N개 출력.

Usage:
  python scripts/show_refpol_examples.py --input results/cr_n50_m0_v4__seed3_proposed/scorecards.jsonl --n 10 --out reports/refpol_examples_10.md
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
    parsed = _get_parsed_output(record)
    fr = parsed.get("final_result") or {}
    s1 = fr.get("stage1_tuples")
    return s1 if (s1 and isinstance(s1, list)) else []


def _extract_final_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    parsed = _get_parsed_output(record)
    fr = parsed.get("final_result") or {}
    s2 = fr.get("final_tuples")
    return s2 if (s2 and isinstance(s2, list)) else []


def _extract_gold_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    inputs = record.get("inputs") or {}
    gt = inputs.get("gold_tuples") or inputs.get("gold_triplets")
    return gt if (gt and isinstance(gt, list)) else []


def _tuple_to_tuple_set(items: List[Dict[str, Any]]) -> Set[Tuple[str, str, str]]:
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


def _pairs_to_str(pairs: Set[Tuple[str, str]]) -> str:
    if not pairs:
        return "(없음)"
    return "; ".join(f"({r}, {p})" for (r, p) in sorted(pairs))


def main():
    ap = argparse.ArgumentParser(description="ref-pol Gold vs Pred 예시")
    ap.add_argument("--input", required=True, type=Path, help="scorecards.jsonl")
    ap.add_argument("--n", type=int, default=10, help="예시 개수")
    ap.add_argument("--out", type=Path, help="Output markdown path")
    ap.add_argument("--wrong-only", action="store_true", help="오답만 (FN>0 또는 FP>0인 샘플)")
    args = ap.parse_args()

    rows = load_jsonl(args.input)
    if not rows:
        print(f"[ERROR] No rows in {args.input}", file=sys.stderr)
        sys.exit(1)

    # Filter rows with gold
    rows_with_gold = []
    for r in rows:
        gold_raw = _extract_gold_tuples_raw(r)
        if gold_raw:
            rows_with_gold.append(r)
    if not rows_with_gold:
        print("[ERROR] No rows with gold_tuples", file=sys.stderr)
        sys.exit(1)

    if args.wrong_only:
        wrong_rows = []
        for r in rows_with_gold:
            gold_raw = _extract_gold_tuples_raw(r)
            s2_raw = _extract_final_tuples_raw(r)
            gold_tuples = _tuple_to_tuple_set(gold_raw)
            s2_tuples = _tuple_to_tuple_set(s2_raw)
            gold_pairs, _ = tuples_to_ref_pairs(gold_tuples)
            s2_pairs, _ = tuples_to_ref_pairs(s2_tuples)
            fn = len(gold_pairs - s2_pairs)
            fp = len(s2_pairs - gold_pairs)
            if fn > 0 or fp > 0:
                wrong_rows.append(r)
        rows_with_gold = wrong_rows

    take = min(args.n, len(rows_with_gold))
    selected = rows_with_gold[:take]

    title = "ref-level 산출물 Gold vs Pred 오답 예시" if args.wrong_only else "ref-level 산출물 Gold vs Pred 예시"
    lines = [
        f"# {title}",
        "",
        f"**입력**: {args.input}",
        f"**예시 수**: {take}" + (" (오답만)" if args.wrong_only else ""),
        "",
        "---",
        "",
    ]

    for i, record in enumerate(selected, 1):
        meta = record.get("meta") or {}
        inputs = record.get("inputs") or {}
        text_id = meta.get("text_id") or meta.get("uid") or meta.get("case_id") or f"sample_{i}"
        text = (inputs.get("text") or meta.get("input_text") or "").strip()
        text_preview = (text[:80] + "…") if len(text) > 80 else text

        gold_raw = _extract_gold_tuples_raw(record)
        s1_raw = _extract_stage1_tuples_raw(record)
        s2_raw = _extract_final_tuples_raw(record)

        gold_tuples = _tuple_to_tuple_set(gold_raw)
        s1_tuples = _tuple_to_tuple_set(s1_raw)
        s2_tuples = _tuple_to_tuple_set(s2_raw)

        gold_pairs, _ = tuples_to_ref_pairs(gold_tuples)
        s1_pairs, _ = tuples_to_ref_pairs(s1_tuples)
        s2_pairs, _ = tuples_to_ref_pairs(s2_tuples)

        tp = len(gold_pairs & s2_pairs)
        fp = len(s2_pairs - gold_pairs)
        fn = len(gold_pairs - s2_pairs)

        lines.extend([
            f"## 예시 {i}: {text_id}",
            "",
            f"**텍스트**: {text_preview}",
            "",
            "| 구분 | (aspect_ref, polarity) 쌍 |",
            "|------|---------------------------|",
            f"| **Gold** | {_pairs_to_str(gold_pairs)} |",
            f"| **Stage1 Pred** | {_pairs_to_str(s1_pairs)} |",
            f"| **Final Pred** | {_pairs_to_str(s2_pairs)} |",
            "",
            "| 비교 | 값 |",
            "|------|-----|",
            f"| Gold ∩ Pred (TP) | {tp} |",
            f"| Pred - Gold (FP) | {fp} |",
            f"| Gold - Pred (FN) | {fn} |",
            "",
        ])

    report = "\n".join(lines)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"[OK] Wrote {args.out}", file=sys.stderr)
    else:
        print(report)


if __name__ == "__main__":
    main()
