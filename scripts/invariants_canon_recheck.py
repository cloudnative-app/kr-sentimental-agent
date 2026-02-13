#!/usr/bin/env python3
"""
불변식 S1/S2 정규화 기준(canon_pair set) 재검증.
S1: debate_summary.final_tuples vs final_result.final_tuples → canon_pair set 비교로 fail 재계산.
S2: final_tuples vs final_aspects → canon_pair set 비교로 재계산.
산출: reports/invariants_canon_recheck_c2_t1.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import normalize_for_eval, normalize_polarity


def _aspect_term_text(it: dict) -> str:
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return (it.get("opinion_term") or {}).get("term", "") or ""


def _list_to_canon_pairs(items: List[Dict]) -> Set[Tuple[str, str]]:
    """(aspect_term_norm, polarity_norm) set. aspect_ref 무시."""
    out: Set[Tuple[str, str]] = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        t = _aspect_term_text(it)
        t_norm = normalize_for_eval(t) if t else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
        if t_norm or p:
            out.add((t_norm, p))
    return out


def _final_aspects_to_canon_pairs(final_aspects: List[Dict]) -> Set[Tuple[str, str]]:
    out: Set[Tuple[str, str]] = set()
    for it in final_aspects or []:
        if not isinstance(it, dict):
            continue
        term = it.get("aspect_term")
        t = term.get("term", "") if isinstance(term, dict) else (term or "")
        t_norm = normalize_for_eval(t) if t else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
        if t_norm or p:
            out.add((t_norm, p))
    return out


def load_jsonl(p: Path) -> List[Dict[str, Any]]:
    out = []
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", type=str, default=None)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else (_PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t1_proposed")
    out_path = Path(args.out) if args.out else (_PROJECT_ROOT / "reports" / "invariants_canon_recheck_c2_t1.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scorecards = load_jsonl(run_dir / "scorecards.jsonl")
    result = {
        "run_id": str(run_dir.name),
        "canon_definition": "(aspect_term_norm, polarity_norm) via normalize_for_eval + normalize_polarity; aspect_ref ignored",
        "invariant_s1_canon_fail": [],
        "invariant_s2_canon_fail": [],
        "invariant_s1_canon_fail_n": 0,
        "invariant_s2_canon_fail_n": 0,
        "interpretation": "If fail_n drops to ~0: 비교 스크립트/표현 문제. If fail_n unchanged: 진짜 동기화/생성 순서 문제.",
    }

    for i, row in enumerate(scorecards):
        text_id = (row.get("meta") or {}).get("text_id") or row.get("runtime", {}).get("uid") or ("row_%s" % i)
        runtime = row.get("runtime") or row
        parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else row
        if isinstance(parsed, dict):
            meta = parsed.get("meta") or {}
            fr = parsed.get("final_result") or {}
        else:
            meta = row.get("meta") or {}
            fr = (runtime.get("parsed_output") or {}).get("final_result") if isinstance(runtime.get("parsed_output"), dict) else {}
        debate_summary = (parsed.get("debate_summary") if isinstance(parsed, dict) and isinstance(parsed.get("debate_summary"), dict) else None) or (meta.get("debate_summary") if isinstance(meta.get("debate_summary"), dict) else {})

        # S1: debate_summary.final_tuples vs final_result.final_tuples (canon_pair)
        ds_tuples = debate_summary.get("final_tuples") if debate_summary else []
        fr_tuples = fr.get("final_tuples") or []
        if isinstance(ds_tuples, list) and ds_tuples:
            canon_ds = _list_to_canon_pairs(ds_tuples)
            canon_fr = _list_to_canon_pairs(fr_tuples)
            if canon_ds != canon_fr:
                result["invariant_s1_canon_fail"].append({
                    "text_id": text_id,
                    "debate_summary_canon_n": len(canon_ds),
                    "final_result_canon_n": len(canon_fr),
                    "symdiff": len(canon_ds ^ canon_fr),
                    "only_in_ds": list(canon_ds - canon_fr),
                    "only_in_fr": list(canon_fr - canon_ds),
                })

        # S2: final_tuples vs final_aspects (canon_pair)
        final_aspects = fr.get("final_aspects") or []
        canon_ft = _list_to_canon_pairs(fr_tuples)
        canon_fa = _final_aspects_to_canon_pairs(final_aspects)
        if canon_ft and canon_fa and canon_ft != canon_fa:
            result["invariant_s2_canon_fail"].append({
                "text_id": text_id,
                "final_tuples_canon_n": len(canon_ft),
                "final_aspects_canon_n": len(canon_fa),
                "symdiff": len(canon_ft ^ canon_fa),
                "only_in_ft": list(canon_ft - canon_fa),
                "only_in_fa": list(canon_fa - canon_ft),
            })

    result["invariant_s1_canon_fail_n"] = len(result["invariant_s1_canon_fail"])
    result["invariant_s2_canon_fail_n"] = len(result["invariant_s2_canon_fail"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("Wrote %s (S1 canon fail=%s, S2 canon fail=%s)" % (out_path, result["invariant_s1_canon_fail_n"], result["invariant_s2_canon_fail_n"]))


if __name__ == "__main__":
    main()
