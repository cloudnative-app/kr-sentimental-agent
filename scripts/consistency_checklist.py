#!/usr/bin/env python3
"""
One-command consistency checklist (GO/NO-GO) for a run.

Checks:
1. source: meta.scorecard_source in scorecards (run_experiments | scorecard_from_smoke)
2. gold: if gold_injected==true anywhere, at least one row has inputs.gold_tuples
3. tuple path: N_pred_* from structural_metrics.csv (warn if fallback dominates)
4. sanity: gold→gold F1=1, final→final F1=1 (via aggregator run_sanity_checks)
5. inconsistency_flags == 0 (read derived/diagnostics/inconsistency_flags.tsv)
6. triptych: top n rows present (path + optional peek)

Usage:
  python scripts/consistency_checklist.py --run_dir results/experiment_real_n100_seed1_c1_1__seed1_proposed
  python scripts/consistency_checklist.py --run_dir results/... --triptych_n 5
"""
from __future__ import annotations

import argparse
import csv
import sys
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_jsonl(path: Path) -> list:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="One-command consistency checklist (GO/NO-GO)")
    ap.add_argument("--run_dir", required=True, help="Run directory (e.g. results/experiment_real_n100_seed1_c1_1__seed1_proposed)")
    ap.add_argument("--scorecards", default=None, help="Override scorecards path (default: run_dir/scorecards.jsonl)")
    ap.add_argument("--triptych_n", type=int, default=3, help="Number of triptych rows to print (default 3)")
    ap.add_argument("--expect_source", default=None, help="Expected meta.scorecard_source (run_experiments | scorecard_from_smoke)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = (_PROJECT_ROOT / run_dir).resolve()
    if not run_dir.exists():
        print(f"[NO-GO] run_dir not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    scorecards_path = Path(args.scorecards) if args.scorecards else run_dir / "scorecards.jsonl"
    if not scorecards_path.is_absolute():
        scorecards_path = run_dir / scorecards_path.name if args.scorecards else run_dir / "scorecards.jsonl"
    if not scorecards_path.exists():
        print(f"[NO-GO] scorecards not found: {scorecards_path}", file=sys.stderr)
        sys.exit(1)

    rows = load_jsonl(scorecards_path)
    if not rows:
        print("[NO-GO] scorecards empty", file=sys.stderr)
        sys.exit(1)

    failed = []
    # 1) source
    sources = [str((r.get("meta") or {}).get("scorecard_source") or "").strip() for r in rows]
    uniq = set(s for s in sources if s)
    if not uniq:
        failed.append("source: meta.scorecard_source missing in all rows")
    elif args.expect_source and uniq != {args.expect_source}:
        failed.append(f"source: expected {args.expect_source}, got {uniq}")
    else:
        print(f"[OK] source: {uniq}")

    # 2) gold
    any_injected = any((r.get("meta") or {}).get("gold_injected") for r in rows)
    with_gold = sum(1 for r in rows if (r.get("inputs") or {}).get("gold_tuples"))
    if any_injected and with_gold == 0:
        failed.append("gold: gold_injected true but no row has inputs.gold_tuples")
    else:
        print(f"[OK] gold: gold_injected present in rows={any_injected}, rows with inputs.gold_tuples={with_gold}")

    # 3) tuple path (from structural_metrics.csv if present)
    metrics_path = run_dir / "derived" / "metrics" / "structural_metrics.csv"
    if metrics_path.exists():
        with metrics_path.open("r", encoding="utf-8") as f:
            r = next(csv.DictReader(f), None)
        if r:
            n_ft = int(r.get("N_pred_final_tuples") or 0)
            n_fa = int(r.get("N_pred_final_aspects") or 0)
            n_in = int(r.get("N_pred_inputs_aspect_sentiments") or 0)
            n_used = int(r.get("N_pred_used") or 0)
            print(f"[OK] tuple path: N_pred_final_tuples={n_ft}, N_pred_final_aspects={n_fa}, N_pred_inputs={n_in}, N_pred_used={n_used}")
            if n_used and n_ft == 0 and n_fa == 0 and n_in > 0:
                print("      [WARN] fallback (inputs.aspect_sentiments) used for all pred tuples", file=sys.stderr)
    else:
        print("[--] tuple path: structural_metrics.csv not found (run aggregator first)")

    # 4) sanity (run aggregator sanity check in-process)
    try:
        from scripts.structural_error_aggregator import run_sanity_checks
        if not run_sanity_checks(rows):
            failed.append("sanity: gold→gold or final→final F1 != 1")
        else:
            print("[OK] sanity: gold→gold, stage1→stage1, final→final F1=1")
    except Exception as e:
        failed.append(f"sanity: run_sanity_checks failed: {e}")

    # 5) inconsistency_flags
    flags_path = run_dir / "derived" / "diagnostics" / "inconsistency_flags.tsv"
    if flags_path.exists():
        with flags_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            flag_rows = list(reader)
        n_flags = len(flag_rows)
        if n_flags > 0:
            failed.append(f"inconsistency_flags: {n_flags} rows (expect 0)")
            bc = sum(1 for r in flag_rows if r.get("flag_changed_one_delta_zero") == "1" or r.get("flag_stage2_no_guided_unguided") == "1")
            if bc:
                print(f"      [WARN] B/C type flags: {bc}", file=sys.stderr)
        else:
            print("[OK] inconsistency_flags: 0")
    else:
        print("[--] inconsistency_flags: file not found (run aggregator with --diagnostics_dir)")

    # 6) triptych top n
    triptych_path = run_dir / "derived" / "tables" / "triptych_table.tsv"
    if not triptych_path.exists():
        triptych_path = run_dir / "derived" / "tables" / "triptych_table.csv"
    if triptych_path.exists():
        with triptych_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="," if triptych_path.suffix.lower() == ".csv" else "\t")
            tri_rows = list(reader)
        print(f"[OK] triptych: {len(tri_rows)} rows at {triptych_path}")
        n_show = min(args.triptych_n, len(tri_rows))
        for i in range(n_show):
            r = tri_rows[i]
            tid = r.get("text_id") or ""
            s1 = r.get("stage1_n_pairs") or ""
            fn = r.get("final_n_pairs") or ""
            gn = r.get("gold_n_pairs") or ""
            mf = r.get("matches_final_vs_gold") or ""
            print(f"      row{i+1}: text_id={tid[:40]}... stage1_n={s1} final_n={fn} gold_n={gn} matches_final_vs_gold={mf}")
    else:
        print("[--] triptych: table not found (run aggregator with --export_triptych_table)")

    # GO/NO-GO
    print("")
    if failed:
        print("NO-GO:", "; ".join(failed), file=sys.stderr)
        sys.exit(1)
    print("GO: all required checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
