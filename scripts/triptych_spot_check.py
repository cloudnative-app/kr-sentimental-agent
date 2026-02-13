"""
Triptych 10-sample spot check: 5 categories × 2 rows each for human review.
Categories:
  1. gold_type=implicit
  2. gold_type=explicit & matches_final_vs_gold > 0 (hit)
  3. gold_type=explicit & matches_final_vs_gold == 0 (miss)
  4. stage1_to_final_changed=1
  5. risk_flagged=1
Output: TSV with selected rows (or print to stdout).
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List

def load_tsv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def _num(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0

def select_spot_rows(rows: List[Dict[str, Any]], per_category: int = 2) -> List[Dict[str, Any]]:
    """Select up to per_category rows from each of 5 categories. Order: first match in table order."""
    out: List[Dict[str, Any]] = []
    seen_text_ids: set = set()
    def take(candidates: List[Dict[str, Any]], label: str) -> None:
        n = 0
        for r in candidates:
            if n >= per_category:
                break
            tid = r.get("text_id") or ""
            if tid in seen_text_ids:
                continue
            seen_text_ids.add(tid)
            r_copy = dict(r)
            r_copy["_spot_category"] = label
            out.append(r_copy)
            n += 1

    # 1. gold_type=implicit
    take([r for r in rows if (r.get("gold_type") or "").strip().lower() == "implicit"], "implicit")
    # 2. explicit & matches_final_vs_gold > 0
    take([r for r in rows if (r.get("gold_type") or "").strip().lower() == "explicit" and _num(r.get("matches_final_vs_gold")) > 0], "explicit_hit")
    # 3. explicit & matches_final_vs_gold == 0
    take([r for r in rows if (r.get("gold_type") or "").strip().lower() == "explicit" and _num(r.get("matches_final_vs_gold")) == 0], "explicit_miss")
    # 4. stage1_to_final_changed=1
    take([r for r in rows if _num(r.get("stage1_to_final_changed")) == 1], "changed")
    # 5. risk_flagged=1
    take([r for r in rows if _num(r.get("risk_flagged")) == 1], "risk_flagged")
    return out

def main() -> None:
    ap = argparse.ArgumentParser(description="Triptych 10-sample spot check (5 categories × 2 rows)")
    ap.add_argument("triptych_tsv", help="Path to triptych_table.tsv")
    ap.add_argument("-o", "--output", default=None, help="Output TSV path (default: stdout)")
    ap.add_argument("-n", "--per_category", type=int, default=2, help="Rows per category (default 2)")
    args = ap.parse_args()

    path = Path(args.triptych_tsv)
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        sys.exit(1)
    rows = load_tsv(path)
    selected = select_spot_rows(rows, per_category=args.per_category)
    if not selected:
        print("No rows selected.", file=sys.stderr)
        sys.exit(0)
    fieldnames = ["_spot_category"] + [k for k in selected[0].keys() if k != "_spot_category"]
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", restval="", extrasaction="ignore")
            w.writeheader()
            w.writerows(selected)
        print(f"Wrote spot check: {out_path} (n={len(selected)})")
    else:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames, delimiter="\t", restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(selected)

if __name__ == "__main__":
    main()
