#!/usr/bin/env python3
"""
Post-hoc Confusion Discovery — gold vs pred 혼동 패턴 후보 자동 생성.

입력: run-dirs의 scorecards.jsonl
출력: results/<analysis_run>/posthoc/
  - confusion_pairs_ranked.csv
  - confusion_coverage_curve.png
  - confusion_delta_gain_curve.png
  - confusion_candidates_review.md
  - confusion_groups_draft.json

Usage:
  python scripts/posthoc_confusion_discovery.py --run-dirs results/cr_n50_m0_v5__seed3_proposed ... --out-dir results/posthoc_confusion_v1 --min-freq 2 --top-k 100
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from metrics.eval_tuple import gold_tuple_set_from_record, tuples_from_list, tuples_to_ref_pairs
from schemas.taxonomy import parse_ref


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


def _norm_ref(ref: str) -> str:
    return (ref or "").strip()


def _is_sibling(ref1: str, ref2: str) -> bool:
    """Same entity, different attribute."""
    p1 = parse_ref(ref1)
    p2 = parse_ref(ref2)
    if not p1 or not p2:
        return False
    return p1[0] == p2[0] and p1[1] != p2[1]


def _string_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def collect_mismatch_pairs(run_dirs: list[Path]) -> list[tuple[str, str]]:
    """Collect (gold_ref, pred_ref) where gold_ref != pred_ref, same polarity."""
    pairs: list[tuple[str, str]] = []
    for run_dir in run_dirs:
        sc_path = run_dir / "scorecards.jsonl"
        if not sc_path.exists():
            continue
        for line in sc_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            gold = _extract_gold_tuples(rec)
            if gold is None or not gold:
                continue
            final = _extract_final_tuples(rec)
            gold_pairs, _ = tuples_to_ref_pairs(gold)
            pred_pairs, _ = tuples_to_ref_pairs(final)
            pred_by_pol: dict[str, set[str]] = {}
            for ref, pol in pred_pairs:
                pred_by_pol.setdefault(pol, set()).add(_norm_ref(ref))
            for ref_g, pol_g in gold_pairs:
                rg = _norm_ref(ref_g)
                pred_refs = pred_by_pol.get(pol_g, set())
                for ref_p in pred_refs:
                    if rg != ref_p:
                        pairs.append((rg, ref_p))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Post-hoc Confusion Discovery")
    ap.add_argument("--run-dirs", nargs="+", type=Path, required=True, help="Run directories with scorecards.jsonl")
    ap.add_argument("--out-dir", type=Path, required=True, help="Output directory (e.g. results/posthoc_confusion_v1)")
    ap.add_argument("--min-freq", type=int, default=3, help="Minimum frequency for pair (pilot: 2)")
    ap.add_argument("--top-k", type=int, default=100, help="Top k pairs to output")
    ap.add_argument("--string-sim-th", type=float, default=0.7, help="String similarity threshold")
    args = ap.parse_args()

    run_dirs = [d.resolve() if d.is_absolute() else (PROJECT_ROOT / d).resolve() for d in args.run_dirs]
    run_dirs = [d for d in run_dirs if d.is_dir()]
    if not run_dirs:
        print("[ERROR] No valid run directories", file=sys.stderr)
        return 1

    out_dir = args.out_dir.resolve()
    if not out_dir.is_absolute():
        out_dir = (PROJECT_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    posthoc_dir = out_dir / "posthoc"
    posthoc_dir.mkdir(parents=True, exist_ok=True)

    pairs = collect_mismatch_pairs(run_dirs)
    if not pairs:
        print("[WARN] No mismatch pairs found", file=sys.stderr)
        # Write empty outputs
        (posthoc_dir / "confusion_pairs_ranked.csv").write_text(
            "rank,gold_ref,pred_ref,pair_key,freq,freq_rate,sources,sibling_flag,string_sim,accept,notes\n",
            encoding="utf-8",
        )
        (posthoc_dir / "confusion_groups_draft.json").write_text(
            json.dumps({"confusion_groups": [], "near_miss_pairs": [], "accept": False}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return 0

    # pair_key = tuple(sorted([g, p])) for dedup
    pair_counter: Counter[tuple[str, str]] = Counter()
    for g, p in pairs:
        key = tuple(sorted([g, p]))
        pair_counter[key] += 1

    total_mismatches = sum(pair_counter.values())
    rows: list[dict[str, Any]] = []
    for (r1, r2), freq in pair_counter.most_common(args.top_k):
        gold_ref, pred_ref = (r1, r2) if r1 < r2 else (r2, r1)
        pair_key = f"{gold_ref}|{pred_ref}"
        freq_rate = freq / total_mismatches if total_mismatches else 0
        sibling = 1 if _is_sibling(gold_ref, pred_ref) else 0
        sim = _string_sim(gold_ref, pred_ref)
        str_tag = 1 if sim >= args.string_sim_th else 0
        score = 0
        if freq >= args.min_freq:
            score += 2
        if sibling:
            score += 1
        if str_tag:
            score += 1
        sources = f"{freq}/{sibling}/{str_tag}"
        rows.append({
            "gold_ref": gold_ref,
            "pred_ref": pred_ref,
            "pair_key": pair_key,
            "freq": freq,
            "freq_rate": round(freq_rate, 6),
            "sources": sources,
            "sibling_flag": sibling,
            "string_sim": round(sim, 4),
            "score": score,
            "recommended": score >= 2,
        })

    # CSV
    csv_path = posthoc_dir / "confusion_pairs_ranked.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["rank", "gold_ref", "pred_ref", "pair_key", "freq", "freq_rate", "sources", "sibling_flag", "string_sim", "accept", "notes"],
        )
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({
                "rank": i,
                "gold_ref": r["gold_ref"],
                "pred_ref": r["pred_ref"],
                "pair_key": r["pair_key"],
                "freq": r["freq"],
                "freq_rate": r["freq_rate"],
                "sources": r["sources"],
                "sibling_flag": r["sibling_flag"],
                "string_sim": r["string_sim"],
                "accept": "",
                "notes": "",
            })
    print(f"[OK] wrote: {csv_path}")

    # Coverage curve data
    cum_freq = 0
    coverage_vals: list[float] = []
    delta_vals: list[float] = []
    prev_cov = 0.0
    for r in rows:
        cum_freq += r["freq"]
        cov = cum_freq / total_mismatches if total_mismatches else 0
        coverage_vals.append(cov)
        delta_vals.append(cov - prev_cov)
        prev_cov = cov

    # Plots (matplotlib only)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        k_vals = list(range(1, len(rows) + 1))
        ax.plot(k_vals, coverage_vals, "b-", linewidth=2, label="coverage(k)")
        ax.set_xlabel("k (top pairs)")
        ax.set_ylabel("coverage")
        ax.set_title("Confusion Coverage Curve")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(posthoc_dir / "confusion_coverage_curve.png", dpi=150)
        plt.close()
        print(f"[OK] wrote: {posthoc_dir / 'confusion_coverage_curve.png'}")

        fig2, ax2 = plt.subplots(figsize=(8, 5))
        ax2.plot(k_vals, delta_vals, "g-", linewidth=2, label="delta(k)")
        ax2.set_xlabel("k (top pairs)")
        ax2.set_ylabel("delta gain")
        ax2.set_title("Confusion Delta Gain Curve")
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(posthoc_dir / "confusion_delta_gain_curve.png", dpi=150)
        plt.close()
        print(f"[OK] wrote: {posthoc_dir / 'confusion_delta_gain_curve.png'}")
    except ImportError:
        print("[WARN] matplotlib not found, skipping plots", file=sys.stderr)

    # Elbow: first k where delta < threshold (e.g. 0.01)
    elbow_k = None
    for i, d in enumerate(delta_vals):
        if i > 0 and d < 0.01:
            elbow_k = i + 1
            break

    # Review MD
    md_lines = [
        "# Confusion Candidates Review",
        "",
        f"**total_mismatches**: {total_mismatches}",
        f"**min_freq**: {args.min_freq}, **top_k**: {args.top_k}",
        "",
        "## Coverage summary",
        "",
        "| k | coverage |",
        "|---|----------|",
    ]
    for ki in [5, 10, 15, 20]:
        if ki <= len(rows):
            md_lines.append(f"| {ki} | {coverage_vals[ki-1]:.4f} |")
    if elbow_k:
        md_lines.append("")
        md_lines.append(f"**Elbow candidate k**: {elbow_k} (delta < 0.01)")
    md_lines.append("")
    md_lines.append("## Top candidates (score >= 2 recommended)")
    md_lines.append("")
    md_lines.append("| rank | gold_ref | pred_ref | freq | sibling | string_sim | recommended |")
    md_lines.append("|------|----------|----------|------|---------|------------|-------------|")
    for i, r in enumerate(rows[:30], 1):
        rec = "Y" if r["recommended"] else ""
        md_lines.append(f"| {i} | {r['gold_ref']} | {r['pred_ref']} | {r['freq']} | {r['sibling_flag']} | {r['string_sim']:.2f} | {rec} |")
    review_path = posthoc_dir / "confusion_candidates_review.md"
    review_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[OK] wrote: {review_path}")

    # Draft JSON (pair format for research review)
    draft = {
        "accept": False,
        "total_mismatches": total_mismatches,
        "coverage_summary": {str(k): coverage_vals[k - 1] for k in [5, 10, 15, 20] if k <= len(rows)},
        "elbow_k": elbow_k,
        "candidates": [
            {
                "gold_ref": r["gold_ref"],
                "pred_ref": r["pred_ref"],
                "freq": r["freq"],
                "sibling_flag": r["sibling_flag"],
                "string_sim": r["string_sim"],
                "score": r["score"],
                "recommended": r["recommended"],
                "accept": False,
                "reason": "",
            }
            for r in rows
        ],
        "confusion_groups": [],
        "near_miss_pairs": [],
    }
    draft_path = posthoc_dir / "confusion_groups_draft.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] wrote: {draft_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
