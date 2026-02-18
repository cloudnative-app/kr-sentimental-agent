#!/usr/bin/env python3
"""Diagnose OTE vs opinion flip: Stage1 raw aspect_terms, ref=term ratio, opinion-like terms."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

# Opinion-like patterns (Korean + English, evaluative adjectives/expressions)
OPINION_PATTERNS = re.compile(
    r"^(좋|나쁘|맛있|별로|대박|추천|최고|훌륭|완벽|최악|끔찍|terrible|delicious|"
    r"great|good|bad|awesome|amazing|excellent|poor|wonderful|horrible|"
    r"사랑스럽|편하|불편|깔끔|지저분|부드럽|딱딱|촉촉|건조|"
    r"만족|불만|감사|실망|기대|기대되|좋아|싫어|별로)$",
    re.I,
)
# Category/abstract terms (often from P-IMP)
CATEGORY_TERMS = {"quality", "performance", "price", "design", "size", "convenience", "value"}


def is_opinion_like(term: str) -> bool:
    t = (term or "").strip().lower()
    if not t or len(t) < 2:
        return False
    if OPINION_PATTERNS.match(t):
        return True
    # Short evaluative
    if t in ("좋아", "별로", "대박", "추천", "최고", "good", "bad", "great"):
        return True
    return False


def is_category_like(term: str) -> bool:
    t = (term or "").strip().lower()
    return t in CATEGORY_TERMS or "quality" in t or "performance" in t


def main():
    # Use merged_scorecards or single seed scorecards (v3 first to check ref==term with no-op)
    candidates = [
        Path("results/cr_n50_m0_v3__seed123_proposed/scorecards.jsonl"),
        Path("results/cr_n50_m1_v3__seed3_proposed/scorecards.jsonl"),
        Path("results/cr_n50_m0_v2_aggregated/merged_scorecards.jsonl"),
    ]
    sc_path = None
    for p in candidates:
        if p.exists():
            sc_path = p
            break
    if not sc_path:
        print("No scorecards found")
        return 1

    records = []
    with open(sc_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if len(records) >= 50:  # Sample 50
                break

    # Dedupe by text_id
    seen = set()
    unique = []
    for r in records:
        tid = (r.get("meta") or {}).get("text_id") or ""
        if tid and tid not in seen:
            seen.add(tid)
            unique.append(r)
    records = unique[:50]

    # Extract from runtime.parsed_output
    pneg_terms, pimp_terms, plit_terms = [], [], []
    ref_eq_term = 0
    total_final = 0
    opinion_like_count = 0
    category_count = 0
    empty_opinion_with_pol = 0

    for r in records:
        runtime = r.get("runtime") or {}
        parsed = runtime.get("parsed_output") or {}
        if isinstance(parsed, str):
            continue
        fr = parsed.get("final_result") or {}
        trace = parsed.get("process_trace") or []

        # Stage1 raw triplets from process_trace (P-NEG, P-IMP, P-LIT)
        for entry in trace:
            agent = entry.get("agent") or ""
            if agent not in ("P-NEG", "P-IMP", "P-LIT"):
                continue
            triplets = (entry.get("output") or {}).get("triplets") or []
            for t in triplets:
                term = (t.get("aspect_term") or "").strip() if isinstance(t.get("aspect_term"), str) else ""
                if isinstance(t.get("aspect_term"), dict):
                    term = (t.get("aspect_term") or {}).get("term") or ""
                if term:
                    if agent == "P-NEG":
                        pneg_terms.append(term)
                    elif agent == "P-IMP":
                        pimp_terms.append(term)
                    else:
                        plit_terms.append(term)
                    if is_opinion_like(term):
                        opinion_like_count += 1
                    if is_category_like(term):
                        category_count += 1
                ot = t.get("opinion_term")
                pol = (t.get("polarity") or "").strip().lower()
                if (not ot or (isinstance(ot, dict) and not ot.get("term"))) and pol in ("positive", "negative", "pos", "neg"):
                    empty_opinion_with_pol += 1

        # Final ref==term
        finals = fr.get("final_tuples") or []
        for t in finals:
            if not isinstance(t, dict):
                continue
            total_final += 1
            ref = (t.get("aspect_ref") or "").strip()
            term = (t.get("aspect_term") or "").strip()
            if ref and term and ref == term:
                ref_eq_term += 1

    n_triplets = len(pneg_terms) + len(pimp_terms) + len(plit_terms)
    lines = [
        "=" * 60,
        "OTE vs Opinion Flip Diagnostic Report",
        "=" * 60,
        f"Source: {sc_path}",
        f"Records: {len(records)}",
        "",
        "--- Check A: Stage1 aspect_term samples (20 per agent) ---",
        f"P-NEG: {pneg_terms[:20]}",
        f"P-IMP: {pimp_terms[:20]}",
        f"P-LIT: {plit_terms[:20]}",
        "",
        "--- Check 6: Data-based ratios ---",
        f"opinion-like aspect_term count: {opinion_like_count} / {n_triplets}",
        f"category-like (quality/performance) count: {category_count} / {n_triplets}",
        f"empty opinion_term with pos/neg polarity: {empty_opinion_with_pol}",
        f"final ref==term: {ref_eq_term} / {total_final}",
        "",
    ]
    out_path = Path("reports/ote_opinion_flip_diagnostic.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
