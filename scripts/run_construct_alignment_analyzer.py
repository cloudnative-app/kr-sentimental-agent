#!/usr/bin/env python3
"""
Post-hoc Construct Alignment Analyzer.

Reads scorecards.jsonl, computes taxonomy-aware semantic alignment metrics.
No pipeline/aggregator modification. Deterministic only.

Input: results/<run>/scorecards.jsonl
Output: results/<run>/derived/semantic_alignment/semantic_alignment_metrics.json

Usage:
  python scripts/run_construct_alignment_analyzer.py --run-dir results/cr_n50_m0_v5__seed3_proposed
  python scripts/run_construct_alignment_analyzer.py --run-dir results/cr_n50_m0_v5__seed3_proposed --ensure-taxonomy-tree
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.construct_alignment.alignment_utils import (
    build_taxonomy_tree,
    is_near_miss,
    load_confusion_groups,
    taxonomy_distance,
    wu_palmer_similarity,
)
from metrics.eval_tuple import (
    gold_tuple_set_from_record,
    tuples_from_list,
    tuples_to_ref_pairs,
)


def _extract_final_tuples(record: dict[str, Any]) -> set[tuple[str, str, str]]:
    """Extract final_tuples from scorecard. Handles runtime.parsed_output and top-level final_result."""
    fr = record.get("final_result") or {}
    if not fr:
        runtime = record.get("runtime") or {}
        parsed = runtime.get("parsed_output") or {}
        fr = parsed.get("final_result") or {}
    lst = fr.get("final_tuples")
    if lst and isinstance(lst, list):
        return tuples_from_list(lst)
    return set()


def _extract_gold_tuples(record: dict[str, Any]) -> set[tuple[str, str, str]] | None:
    """Extract gold tuples. Returns None if no gold."""
    return gold_tuple_set_from_record(record)


def _compute_sample_metrics(
    gold_pairs: set[tuple[str, str]],
    pred_pairs: set[tuple[str, str]],
    confusion_cfg: dict[str, Any],
) -> dict[str, Any]:
    """
    For each gold (ref, pol), find best matching pred (ref, pol) with same polarity.
    Returns exact_match, near_miss, taxonomy_similarity.
    """
    if not gold_pairs:
        return {
            "exact_match": False,
            "near_miss": False,
            "taxonomy_similarity": float("nan"),
            "n_gold": 0,
            "n_matched_exact": 0,
            "n_matched_near": 0,
        }
    pred_by_pol: dict[str, set[str]] = {}
    for ref, pol in pred_pairs:
        pred_by_pol.setdefault(pol, set()).add(ref)

    n_exact = 0
    n_near = 0
    sims: list[float] = []

    for ref_g, pol_g in gold_pairs:
        pred_refs = pred_by_pol.get(pol_g, set())
        best_sim = 0.0
        best_is_exact = False
        best_is_near = False
        best_ref_p: str | None = None

        for ref_p in pred_refs:
            if ref_g == ref_p:
                best_sim = 1.0
                best_is_exact = True
                best_is_near = False
                best_ref_p = ref_p
                break
            sim = wu_palmer_similarity(ref_g, ref_p)
            if sim > best_sim:
                best_sim = sim
                best_ref_p = ref_p
                best_is_near = is_near_miss(ref_g, ref_p, confusion_cfg)

        if best_is_exact:
            n_exact += 1
        elif best_is_near and best_ref_p:
            n_near += 1
        sims.append(best_sim)

    n_gold = len(gold_pairs)
    exact_match = n_exact == n_gold
    near_miss = not exact_match and n_exact + n_near > 0
    mean_sim = sum(sims) / len(sims) if sims else float("nan")

    return {
        "exact_match": exact_match,
        "near_miss": near_miss,
        "taxonomy_similarity": mean_sim,
        "n_gold": n_gold,
        "n_matched_exact": n_exact,
        "n_matched_near": n_near,
    }


def run_analyzer(run_dir: Path, ensure_taxonomy_tree: bool = False) -> dict[str, Any]:
    """Run construct alignment analyzer on scorecards. Returns metrics dict."""
    scorecards_path = run_dir / "scorecards.jsonl"
    if not scorecards_path.exists():
        return {"error": f"Missing: {scorecards_path}"}

    confusion_cfg = load_confusion_groups()

    if ensure_taxonomy_tree:
        tree_path = PROJECT_ROOT / "analysis" / "construct_alignment" / "taxonomy_tree.json"
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        tree = build_taxonomy_tree()
        tree_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")

    records: list[dict] = []
    for line in scorecards_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    per_sample: list[dict] = []
    n_exact = 0
    n_near = 0
    n_exact_or_near = 0
    sims: list[float] = []
    dists: list[float] = []

    for rec in records:
        gold = _extract_gold_tuples(rec)
        if gold is None or len(gold) == 0:
            continue
        final = _extract_final_tuples(rec)
        gold_pairs, _ = tuples_to_ref_pairs(gold)
        pred_pairs, _ = tuples_to_ref_pairs(final)
        if not gold_pairs:
            continue

        sm = _compute_sample_metrics(gold_pairs, pred_pairs, confusion_cfg)
        text_id = (rec.get("meta") or {}).get("text_id") or (rec.get("runtime") or {}).get("uid") or ""
        per_sample.append({
            "text_id": text_id,
            **sm,
        })

        if sm["exact_match"]:
            n_exact += 1
            n_exact_or_near += 1
        elif sm["near_miss"]:
            n_near += 1
            n_exact_or_near += 1

        s = sm.get("taxonomy_similarity")
        if s is not None and s == s and s != float("inf"):
            sims.append(float(s))
            dists.append(1.0 - float(s))

    n_with_gold = len(per_sample)
    exact_ref_accuracy = n_exact / n_with_gold if n_with_gold else float("nan")
    near_miss_rate = n_near / n_with_gold if n_with_gold else float("nan")
    exact_plus_near_rate = n_exact_or_near / n_with_gold if n_with_gold else float("nan")
    mean_taxonomy_similarity = sum(sims) / len(sims) if sims else float("nan")
    mean_taxonomy_distance = sum(dists) / len(dists) if dists else float("nan")

    return {
        "run_id": (records[0].get("meta") or {}).get("run_id", str(run_dir.name)) if records else str(run_dir.name),
        "n_with_gold": n_with_gold,
        "exact_ref_accuracy": exact_ref_accuracy,
        "near_miss_rate": near_miss_rate,
        "exact_plus_near_rate": exact_plus_near_rate,
        "mean_taxonomy_similarity": mean_taxonomy_similarity,
        "mean_taxonomy_distance": mean_taxonomy_distance,
        "per_sample": per_sample,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc Construct Alignment Analyzer")
    ap.add_argument("--run-dir", type=Path, required=True, help="Run directory (e.g. results/cr_n50_m0_v5__seed3_proposed)")
    ap.add_argument("--ensure-taxonomy-tree", action="store_true", help="Write analysis/construct_alignment/taxonomy_tree.json")
    args = ap.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_absolute():
        run_dir = (PROJECT_ROOT / run_dir).resolve()
    if not run_dir.is_dir():
        print(f"[ERROR] Not a directory: {run_dir}", file=sys.stderr)
        return 1

    metrics = run_analyzer(run_dir, ensure_taxonomy_tree=args.ensure_taxonomy_tree)
    if "error" in metrics:
        print(f"[ERROR] {metrics['error']}", file=sys.stderr)
        return 1

    out_dir = run_dir / "derived" / "semantic_alignment"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "semantic_alignment_metrics.json"

    # Serialize; avoid inf in JSON
    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, float):
            if obj != obj:
                return None
            if obj == float("inf") or obj == float("-inf"):
                return None
            return round(obj, 6)
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(x) for x in obj]
        return obj

    to_write = _sanitize(metrics)
    out_path.write_text(json.dumps(to_write, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
