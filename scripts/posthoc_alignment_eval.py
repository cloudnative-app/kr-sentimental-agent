#!/usr/bin/env python3
"""
Post-hoc Alignment Eval — confusion_groups 적용한 alignment metric 계산.

입력: run-dirs, evaluation/confusion_groups.json (연구자 확정본)
출력: results/<analysis_run>/posthoc_alignment_metrics.csv (seed별 + aggregated)
      results/<analysis_run>/posthoc_alignment_summary.json

Usage:
  python scripts/posthoc_alignment_eval.py --run-dirs results/cr_n50_m0_v5__seed3_proposed ... --confusion-groups evaluation/confusion_groups.json --out-dir results/posthoc_alignment_v1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.construct_alignment.alignment_utils import is_near_miss, wu_palmer_similarity
from metrics.eval_tuple import gold_tuple_set_from_record, tuples_from_list, tuples_to_ref_pairs
from schemas.taxonomy import get_attribute, get_entity


def _extract_final_tuples(record: dict[str, Any]) -> set[tuple[str, str, str]]:
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
    return gold_tuple_set_from_record(record)


def _compute_sample_metrics(
    gold_pairs: set[tuple[str, str]],
    pred_pairs: set[tuple[str, str]],
    confusion_cfg: dict[str, Any],
) -> dict[str, Any]:
    if not gold_pairs:
        return {
            "exact_match": False,
            "near_miss": False,
            "taxonomy_similarity": float("nan"),
            "n_gold": 0,
            "n_matched_exact": 0,
            "n_matched_near": 0,
            "same_entity_count": 0,
            "same_attribute_count": 0,
        }
    pred_by_pol: dict[str, set[str]] = {}
    for ref, pol in pred_pairs:
        pred_by_pol.setdefault(pol, set()).add(ref)

    n_exact = 0
    n_near = 0
    sims: list[float] = []
    same_entity = 0
    same_attr = 0

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

        if best_ref_p:
            e_g, e_p = get_entity(ref_g), get_entity(ref_p)
            a_g, a_p = get_attribute(ref_g), get_attribute(ref_p)
            if e_g and e_p and e_g == e_p:
                same_entity += 1
            if a_g and a_p and a_g == a_p:
                same_attr += 1

    n_gold = len(gold_pairs)
    exact_match = n_exact == n_gold
    near_miss = not exact_match and n_exact + n_near > 0
    mean_sim = sum(sims) / len(sims) if sims else float("nan")
    same_entity_rate = same_entity / n_gold if n_gold else float("nan")
    same_attribute_rate = same_attr / n_gold if n_gold else float("nan")

    return {
        "exact_match": exact_match,
        "near_miss": near_miss,
        "taxonomy_similarity": mean_sim,
        "n_gold": n_gold,
        "n_matched_exact": n_exact,
        "n_matched_near": n_near,
        "same_entity_count": same_entity,
        "same_attribute_count": same_attr,
        "same_entity_rate": same_entity_rate,
        "same_attribute_rate": same_attribute_rate,
    }


def run_eval(run_dir: Path, confusion_cfg: dict[str, Any]) -> dict[str, Any] | None:
    sc_path = run_dir / "scorecards.jsonl"
    if not sc_path.exists():
        return None
    records = []
    for line in sc_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    per_sample = []
    n_exact = 0
    n_near = 0
    n_exact_or_near = 0
    sims: list[float] = []
    dists: list[float] = []
    se_rates: list[float] = []
    sa_rates: list[float] = []

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
        per_sample.append({"text_id": text_id, **sm})

        if sm["exact_match"]:
            n_exact += 1
            n_exact_or_near += 1
        elif sm["near_miss"]:
            n_near += 1
            n_exact_or_near += 1

        s = sm.get("taxonomy_similarity")
        if s is not None and s == s:
            sims.append(float(s))
            dists.append(1.0 - float(s))
        if sm.get("same_entity_rate") == sm.get("same_entity_rate"):
            se_rates.append(sm["same_entity_rate"])
        if sm.get("same_attribute_rate") == sm.get("same_attribute_rate"):
            sa_rates.append(sm["same_attribute_rate"])

    n_with_gold = len(per_sample)
    return {
        "run_id": run_dir.name,
        "n_with_gold": n_with_gold,
        "exact_ref_accuracy": n_exact / n_with_gold if n_with_gold else float("nan"),
        "near_miss_rate": n_near / n_with_gold if n_with_gold else float("nan"),
        "exact_plus_near_rate": n_exact_or_near / n_with_gold if n_with_gold else float("nan"),
        "mean_taxonomy_similarity": mean(sims) if sims else float("nan"),
        "mean_taxonomy_distance": mean(dists) if dists else float("nan"),
        "same_entity_rate": mean(se_rates) if se_rates else float("nan"),
        "same_attribute_rate": mean(sa_rates) if sa_rates else float("nan"),
        "per_sample": per_sample,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc Alignment Eval")
    ap.add_argument("--run-dirs", nargs="+", type=Path, required=True)
    ap.add_argument("--confusion-groups", type=Path, default=None, help="evaluation/confusion_groups.json")
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()

    run_dirs = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs]
    run_dirs = [d for d in run_dirs if d.is_dir()]

    cg_path = args.confusion_groups
    if cg_path is None:
        cg_path = PROJECT_ROOT / "evaluation" / "confusion_groups.json"
    elif not cg_path.is_absolute():
        cg_path = (PROJECT_ROOT / cg_path).resolve()

    confusion_cfg: dict[str, Any] = {"confusion_groups": [], "near_miss_pairs": []}
    if cg_path.exists():
        try:
            data = json.loads(cg_path.read_text(encoding="utf-8"))
            confusion_cfg["confusion_groups"] = data.get("confusion_groups", [])
            confusion_cfg["near_miss_pairs"] = data.get("near_miss_pairs", [])
        except (json.JSONDecodeError, OSError):
            pass

    out_dir = args.out_dir.resolve()
    if not out_dir.is_absolute():
        out_dir = (PROJECT_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    seed_results: list[dict[str, Any]] = []
    for d in run_dirs:
        res = run_eval(d, confusion_cfg)
        if res:
            seed_results.append(res)

    if not seed_results:
        print("[WARN] No valid results", file=sys.stderr)
        return 1

    # CSV
    import csv
    csv_path = out_dir / "posthoc_alignment_metrics.csv"
    cols = ["run_id", "n_with_gold", "exact_ref_accuracy", "near_miss_rate", "exact_plus_near_rate",
            "mean_taxonomy_similarity", "mean_taxonomy_distance", "same_entity_rate", "same_attribute_rate"]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in seed_results:
            row = {k: r.get(k, "") for k in cols}
            for k in ["exact_ref_accuracy", "near_miss_rate", "exact_plus_near_rate",
                      "mean_taxonomy_similarity", "mean_taxonomy_distance", "same_entity_rate", "same_attribute_rate"]:
                v = row.get(k)
                if isinstance(v, float) and v == v:
                    row[k] = round(v, 6)
            w.writerow(row)
    print(f"[OK] wrote: {csv_path}")

    # Aggregated
    def _agg(key: str) -> tuple[float, float]:
        vals = [r.get(key) for r in seed_results if isinstance(r.get(key), (int, float)) and r[key] == r[key]]
        if not vals:
            return float("nan"), float("nan")
        return mean(vals), pstdev(vals) if len(vals) > 1 else 0.0

    agg = {
        "n_seeds": len(seed_results),
        "exact_ref_accuracy": _agg("exact_ref_accuracy"),
        "near_miss_rate": _agg("near_miss_rate"),
        "exact_plus_near_rate": _agg("exact_plus_near_rate"),
        "mean_taxonomy_similarity": _agg("mean_taxonomy_similarity"),
        "mean_taxonomy_distance": _agg("mean_taxonomy_distance"),
        "same_entity_rate": _agg("same_entity_rate"),
        "same_attribute_rate": _agg("same_attribute_rate"),
    }

    summary = {
        "confusion_groups_path": str(cg_path),
        "run_dirs": [str(d) for d in run_dirs],
        "seed_results": [{k: v for k, v in r.items() if k != "per_sample"} for r in seed_results],
        "aggregated": {k: {"mean": v[0], "std": v[1]} for k, v in agg.items() if isinstance(v, tuple)},
    }
    summary_path = out_dir / "posthoc_alignment_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
