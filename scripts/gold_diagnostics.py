"""
A1) Gold profile statistics (run-level): gold_empty_aspect_rate, gold_long_term_rate,
    gold_brand_like_rate, gold_taxonomy_like_rate → derived/diagnostics/gold_profile.csv
A2) Definition-mismatch samples: matches_final_vs_gold==0 & gold_n_pairs>0 & final_n_pairs>0,
    tagged (a) empty (b) long (c) taxonomy → derived/diagnostics/definition_mismatch_samples.tsv (min 50).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import gold_tuples_from_record

# Default long-term threshold (chars)
GOLD_LONG_TERM_K = 15

# Regex: brand-like = hashtag or Latin/digits (해시태그/영문+숫자/모델명)
RE_BRAND_LIKE = re.compile(r"#\w+|[A-Za-z0-9]{2,}")

# Regex: taxonomy-like = "본품#품질" style (word#word)
RE_TAXONOMY_LIKE = re.compile(r".+#.+")

# Gold aspect_term from item (raw string for length/pattern)
def _gold_aspect_term_raw(item: Dict[str, Any]) -> str:
    if item.get("aspect_term") == "":
        return ""
    raw = item.get("aspect_term") or (item.get("opinion_term") or {}).get("term")
    if raw is not None:
        return (raw or "").strip() if isinstance(raw, str) else str(raw).strip()
    return (item.get("aspect_ref") or item.get("term") or "").strip()


def _is_gold_empty(term: str) -> bool:
    return (term or "").strip() == ""


def _is_gold_long(term: str, k: int = GOLD_LONG_TERM_K) -> bool:
    return len((term or "").strip()) >= k


def _is_gold_brand_like(term: str) -> bool:
    if not (term or "").strip():
        return False
    return bool(RE_BRAND_LIKE.search(term))


def _is_gold_taxonomy_like(term: str) -> bool:
    if not (term or "").strip():
        return False
    return bool(RE_TAXONOMY_LIKE.search(term))


def compute_gold_profile(rows: List[Dict[str, Any]], long_term_k: int = GOLD_LONG_TERM_K) -> Dict[str, Any]:
    """Run-level stats from inputs.gold_tuples: rates of empty, long, brand_like, taxonomy_like."""
    n_total = 0
    n_empty = 0
    n_long = 0
    n_brand = 0
    n_taxonomy = 0
    for record in rows:
        lst, _ = gold_tuples_from_record(record)
        if not lst:
            continue
        for item in lst:
            term = _gold_aspect_term_raw(item)
            n_total += 1
            if _is_gold_empty(term):
                n_empty += 1
            if _is_gold_long(term, long_term_k):
                n_long += 1
            if _is_gold_brand_like(term):
                n_brand += 1
            if _is_gold_taxonomy_like(term):
                n_taxonomy += 1
    return {
        "n_gold_pairs": n_total,
        "gold_empty_aspect_rate": (n_empty / n_total) if n_total else None,
        "gold_long_term_rate": (n_long / n_total) if n_total else None,
        "gold_brand_like_rate": (n_brand / n_total) if n_total else None,
        "gold_taxonomy_like_rate": (n_taxonomy / n_total) if n_total else None,
        "gold_empty_aspect_count": n_empty,
        "gold_long_term_count": n_long,
        "gold_brand_like_count": n_brand,
        "gold_taxonomy_like_count": n_taxonomy,
    }


def write_gold_profile_csv(profile: Dict[str, Any], run_id: str, out_path: Path) -> None:
    """Write one row: run_id + profile keys."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    row = {"run_id": run_id, **{k: v for k, v in profile.items() if v is not None}}
    fieldnames = ["run_id", "n_gold_pairs", "gold_empty_aspect_rate", "gold_long_term_rate", "gold_brand_like_rate", "gold_taxonomy_like_rate"]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerow(row)
    print(f"Wrote gold profile: {out_path}")


def tag_gold_pairs_display(gold_pairs_str: str, long_term_k: int = GOLD_LONG_TERM_K) -> Tuple[bool, bool, bool]:
    """From display string 'term|pol;term|pol' return (has_empty, has_long, has_taxonomy)."""
    has_empty = False
    has_long = False
    has_taxonomy = False
    if not gold_pairs_str or not isinstance(gold_pairs_str, str):
        return has_empty, has_long, has_taxonomy
    for part in (gold_pairs_str or "").split(";"):
        part = part.strip()
        if "|" not in part:
            continue
        term, _ = part.split("|", 1)
        term = (term or "").strip()
        if term == "":
            has_empty = True
        if len(term) >= long_term_k:
            has_long = True
        if RE_TAXONOMY_LIKE.search(term):
            has_taxonomy = True
        if RE_BRAND_LIKE.search(term):
            pass  # optional: add has_brand if needed for TSV
    return has_empty, has_long, has_taxonomy


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Gold diagnostics: profile CSV + definition-mismatch samples TSV")
    ap.add_argument("--input", required=True, help="scorecards.jsonl")
    ap.add_argument("--run_dir", default=None, help="Run directory; diagnostics go to run_dir/derived/diagnostics/")
    ap.add_argument("--outdir", default=None, help="Override diagnostics output directory (default: run_dir/derived/diagnostics)")
    ap.add_argument("--long_term_k", type=int, default=GOLD_LONG_TERM_K, help="Long term length threshold (default 15)")
    ap.add_argument("--min_mismatch", type=int, default=50, help="Minimum number of definition-mismatch samples to output (default 50)")
    args = ap.parse_args()

    # Resolve diagnostics dir
    if args.outdir:
        diag_dir = Path(args.outdir)
    elif args.run_dir:
        diag_dir = Path(args.run_dir) / "derived" / "diagnostics"
    else:
        diag_dir = Path(args.input).resolve().parent / "derived" / "diagnostics"
    run_id = Path(args.input).resolve().parent.name or "run"

    rows = load_jsonl(Path(args.input))
    if not rows:
        print(f"No records in {args.input}")
        return

    # A1: Gold profile
    profile = compute_gold_profile(rows, long_term_k=args.long_term_k)
    gold_profile_path = diag_dir / "gold_profile.csv"
    write_gold_profile_csv(profile, run_id, gold_profile_path)

    # A2: Definition-mismatch samples (need triptych-like rows)
    try:
        from scripts.structural_error_aggregator import _triptych_row
    except ImportError:
        from structural_error_aggregator import _triptych_row
    triptych_rows: List[Dict[str, Any]] = [_triptych_row(r, include_text=True, include_debug=False) for r in rows]
    def _match_final_zero(r: Dict[str, Any]) -> bool:
        v = r.get("matches_final_vs_gold")
        return v == 0 or v == "0" or v == "" or (isinstance(v, (int, float)) and v == 0)

    mismatch = [
        r
        for r in triptych_rows
        if _match_final_zero(r) and (r.get("gold_n_pairs") or 0) > 0 and (r.get("final_n_pairs") or 0) > 0
    ]
    # Tag each: (a) empty (b) long (c) taxonomy
    for r in mismatch:
        gp = (r.get("gold_pairs") or "")
        has_empty, has_long, has_taxonomy = tag_gold_pairs_display(gp, args.long_term_k)
        r["tag_empty_aspect"] = 1 if has_empty else 0
        r["tag_long_term"] = 1 if has_long else 0
        r["tag_taxonomy_like"] = 1 if has_taxonomy else 0
        parts = []
        if has_empty:
            parts.append("empty")
        if has_long:
            parts.append("long")
        if has_taxonomy:
            parts.append("taxonomy")
        r["tag_summary"] = ";".join(parts) if parts else ""
    # Output all mismatch rows (at least min_mismatch requested; we output all we have)
    out_mismatch = mismatch
    out_path = diag_dir / "definition_mismatch_samples.tsv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not out_mismatch:
        # Write header only
        fieldnames = [
            "text_id", "gold_type", "f1_eval_note", "gold_pairs", "gold_n_pairs", "final_n_pairs",
            "matches_final_vs_gold", "tag_empty_aspect", "tag_long_term", "tag_taxonomy_like", "tag_summary", "text",
        ]
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", restval="", extrasaction="ignore")
            w.writeheader()
        print(f"Wrote definition-mismatch samples: {out_path} (n=0, no matching rows)")
    else:
        fieldnames = list(out_mismatch[0].keys())
        keep = ["text_id", "gold_type", "f1_eval_note", "gold_pairs", "gold_n_pairs", "final_n_pairs", "matches_final_vs_gold", "tag_empty_aspect", "tag_long_term", "tag_taxonomy_like", "tag_summary", "text"]
        for k in list(out_mismatch[0].keys()):
            if k not in keep:
                keep.append(k)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keep, delimiter="\t", restval="", extrasaction="ignore")
            w.writeheader()
            w.writerows(out_mismatch)
        print(f"Wrote definition-mismatch samples: {out_path} (n={len(out_mismatch)})")


if __name__ == "__main__":
    main()
