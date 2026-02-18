#!/usr/bin/env python3
"""Show stage-wise results (s1, final, gold) for first N unique text_ids from merged scorecards."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metrics.eval_tuple import (
    gold_tuple_set_from_record,
    normalize_for_eval,
    normalize_polarity,
    tuples_to_pairs,
)
from scripts.structural_error_aggregator import (
    _extract_final_tuples,
    _extract_stage1_tuples,
)


def _extract_gold(record: dict) -> set:
    gold = gold_tuple_set_from_record(record)
    return gold if gold else set()


def _format_tuple(ref: str, term: str, pol: str) -> str:
    ref_s = f"ref={ref!r}" if ref else "ref=''"
    return f"({ref_s}, term={term!r}, pol={pol!r})"


def main():
    scorecard_path = Path("results/cr_n50_m0_v2_aggregated/merged_scorecards.jsonl")
    if not scorecard_path.exists():
        print(f"Not found: {scorecard_path}")
        return 1

    records = []
    seen = set()
    with open(scorecard_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            tid = (r.get("meta") or {}).get("text_id") or (r.get("runtime") or {}).get("uid") or ""
            if tid and tid not in seen:
                seen.add(tid)
                records.append(r)
                if len(records) >= 10:
                    break

    def _fmt_tuples(tuples_set):
        if not tuples_set:
            return []
        return sorted([(a, t, p) for (a, t, p) in tuples_set])

    def _fmt_pairs(pairs_set):
        if not pairs_set:
            return []
        return sorted([(t, p) for t, p in pairs_set])

    lines = [
        "# CR v2 M0 스테이지별 결과 샘플 (10건)",
        "",
        "튜플 = (aspect_ref, aspect_term, polarity). pairs = (aspect_term, polarity) — P0 평가 키.",
        "",
    ]

    for i, r in enumerate(records, 1):
        meta = r.get("meta") or {}
        tid = meta.get("text_id") or (r.get("runtime") or {}).get("uid") or ""
        text = meta.get("input_text") or ""

        gold = _extract_gold(r)
        s1 = _extract_stage1_tuples(r)
        s2 = _extract_final_tuples(r)

        s1_pairs = tuples_to_pairs(s1) if s1 else set()
        s2_pairs = tuples_to_pairs(s2) if s2 else set()

        delta = r.get("stage_delta") or {}
        changed = delta.get("changed", False)

        gold_list = _fmt_tuples(gold)
        s1_list = _fmt_tuples(s1)
        s1_pairs_list = _fmt_pairs(s1_pairs)
        s2_list = _fmt_tuples(s2)
        s2_pairs_list = _fmt_pairs(s2_pairs)

        lines.append(f"## {i}. {tid}")
        lines.append("")
        lines.append(f"**input_text**: {text}")
        lines.append("")
        lines.append("| 구분 | 내용 |")
        lines.append("|------|------|")
        lines.append("| **gold** (ref, term, pol) | " + ("; ".join([f"({a!r},{t!r},{p!r})" for a,t,p in gold_list]) if gold_list else "-") + " |")
        lines.append("| **s1_tuples** (ref, term, pol) | " + ("; ".join([f"({a!r},{t!r},{p!r})" for a,t,p in s1_list]) if s1_list else "-") + " |")
        lines.append("| **s1_pairs** (term, pol) | " + ("; ".join([f"({t!r},{p!r})" for t,p in s1_pairs_list]) if s1_pairs_list else "-") + " |")
        lines.append("| **final_tuples** (ref, term, pol) | " + ("; ".join([f"({a!r},{t!r},{p!r})" for a,t,p in s2_list]) if s2_list else "-") + " |")
        lines.append("| **final_pairs** (term, pol) | " + ("; ".join([f"({t!r},{p!r})" for t,p in s2_pairs_list]) if s2_pairs_list else "-") + " |")
        lines.append("| **stage_delta.changed** | " + str(changed) + " |")
        lines.append("")

    out_path = Path("reports/cr_v2_m0_stage_results_10_sample.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
