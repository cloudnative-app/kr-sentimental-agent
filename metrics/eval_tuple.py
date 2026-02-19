"""
ABSA evaluation Tuple (Aspect, Polarity) contract.

- Tuple = (aspect_ref, aspect_term, polarity). aspect_term = 문장 내 관점 표면형(surface form).
- CR v2: 주평가 키 = (aspect_ref, polarity). match_by_aspect_ref=True (default).
- 보조평가: (aspect_term, polarity) explicit-only — tuples_to_pairs.
- Gold: gold_tuples (preferred) or gold_triplets with backward compat (opinion_term.term → aspect_term).
- Samples without gold are excluded from tuple F1. See docs/evaluation_cr_v2.md, docs/absa_tuple_eval.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Tuple = (aspect_ref, aspect_term, polarity). aspect_ref only for gold/taxonomy; pipeline uses aspect_term only.
EvalTuple = Tuple[str, str, str]
# Pair used for F1 matching: (aspect_term, polarity) only.
EvalPair = Tuple[str, str]


# Polarity normalization: short form -> canonical (evaluation only)
_POLARITY_MAP = {
    "pos": "positive",
    "positive": "positive",
    "neg": "negative",
    "negative": "negative",
    "neu": "neutral",
    "neutral": "neutral",
    "mixed": "mixed",
}


def normalize_polarity(s: Optional[str], default_missing: Optional[str] = "neutral") -> Optional[str]:
    """
    Normalize polarity to canonical form: pos->positive, neg->negative, neu->neutral.
    When default_missing is None, missing/empty polarity returns None (neutral ≠ missing).
    When default_missing="neutral" (default), missing returns "neutral" (backward compat).
    """
    if s is None or (isinstance(s, str) and not s.strip()):
        return default_missing
    key = (s or "").strip().lower()
    if key in _POLARITY_MAP:
        return _POLARITY_MAP[key]
    if key in ("positive", "negative", "neutral", "mixed"):
        return key
    return default_missing


def normalize_for_eval(s: Optional[str]) -> str:
    """Normalize string for matching: strip, lower, collapse whitespace, remove leading/trailing punct. null/None -> "".
    Use for aspect_term only. For aspect_ref use normalize_ref_for_eval (preserves #)."""
    if s is None:
        return ""
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(".,;:!?\"'`""''()[]{}")
    return t


def normalize_ref_for_eval(ref: Optional[str]) -> str:
    """Normalize aspect_ref for matching: strip, collapse whitespace, # 좌우 공백 제거.
    IMPORTANT: # is never removed or altered.
    Gold is never filtered by allowlist; this is surface-only normalization.
    Entity canonicalize: 패키지/구성품 → 패키지·구성품 (gold 호환)."""
    if ref is None:
        return ""
    s = str(ref)
    s = s.replace("패키지/구성품", "패키지·구성품")
    s = s.strip()
    s = " ".join(s.split())  # whitespace collapse
    if "#" in s:
        left, right = s.split("#", 1)
        s = left.strip() + "#" + right.strip()
    if __debug__ and ref and "#" in str(ref).strip():
        assert "#" in s, "normalize_ref_for_eval: # must be preserved"
    return s


def _aspect_term_text(sent: Dict[str, Any]) -> str:
    """Extract aspect surface-form text from a sentiment dict (pipeline aspect_term or legacy opinion_term)."""
    at = sent.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    op = sent.get("opinion_term")
    if isinstance(op, dict) and op.get("term") is not None:
        return (op.get("term") or "").strip()
    return ""


def tuple_from_sent(
    sent: Dict[str, Any],
    default_missing_polarity: Optional[str] = "neutral",
) -> Optional[EvalTuple]:
    """
    Build (aspect_ref, aspect_term, polarity) from a sentiment/aspect dict.
    When default_missing_polarity is None and polarity is missing, returns None (neutral ≠ missing).
    """
    if sent.get("is_implicit") is True:
        aspect_term = ""
    else:
        aspect_term_raw = _aspect_term_text(sent)
        aspect_term = normalize_for_eval(aspect_term_raw) if aspect_term_raw else ""
    raw_ref = sent.get("aspect_ref") or sent.get("term")
    aspect_ref = normalize_ref_for_eval(raw_ref or "")
    polarity = normalize_polarity(sent.get("polarity") or sent.get("label"), default_missing=default_missing_polarity)
    if polarity is None:
        return None
    return (aspect_ref, aspect_term, polarity)


def tuples_from_list(
    items: Any,
    default_missing_polarity: Optional[str] = "neutral",
) -> Set[EvalTuple]:
    """Convert list of sentiment dicts to set of EvalTuple. When default_missing_polarity is None, items with missing polarity are skipped."""
    if not items or not isinstance(items, (list, tuple)):
        return set()
    out: Set[EvalTuple] = set()
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        t = tuple_from_sent(it, default_missing_polarity=default_missing_polarity)
        if t is None:
            continue
        if t[0] or t[1] or (t[2] and t[2].strip()):
            out.add(t)
    return out


def tuples_from_list_for_eval(
    items: Any,
    default_missing_polarity: Optional[str] = None,
) -> Tuple[Set[EvalTuple], int]:
    """
    Build EvalTuple set for evaluation; do not treat missing polarity as neutral.
    When default_missing_polarity is None, items with missing polarity are excluded and counted as invalid.
    Returns (tuple_set, invalid_polarity_count).
    """
    if not items or not isinstance(items, (list, tuple)):
        return (set(), 0)
    out: Set[EvalTuple] = set()
    invalid = 0
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        t = tuple_from_sent(it, default_missing_polarity=default_missing_polarity)
        if t is None:
            invalid += 1
            continue
        if t[0] or t[1] or (t[2] and t[2].strip()):
            out.add(t)
    return (out, invalid)


def tuples_to_list_of_dicts(tuples_set: Set[EvalTuple]) -> List[Dict[str, str]]:
    """Serialize set of EvalTuple to list of dicts for JSON/schema (aspect_ref, aspect_term, polarity)."""
    if not tuples_set:
        return []
    return [{"aspect_ref": a, "aspect_term": t, "polarity": p} for (a, t, p) in tuples_set]


def final_aspects_from_final_tuples(final_tuples: Any) -> List[Dict[str, Any]]:
    """Reconstruct final_aspects from final_tuples when missing/empty in scorecards.
    Returns unique list of aspect-sentiment dicts (aspect_ref, aspect_term, polarity, is_implicit)
    compatible with tuple_from_sent. Uniqueness by (aspect_ref or aspect_term, polarity)."""
    if not final_tuples or not isinstance(final_tuples, (list, tuple)):
        return []
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for it in final_tuples:
        if not it or not isinstance(it, dict):
            continue
        a_raw = (it.get("aspect_ref") or "").strip()
        t_raw = _aspect_term_text(it)
        if not t_raw and a_raw:
            t_raw = a_raw
        a = normalize_ref_for_eval(a_raw)
        t = normalize_for_eval(t_raw) if t_raw else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
        is_impl = it.get("is_implicit", False) or (not (t_raw or a_raw))
        key = (a or t, p)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "aspect_ref": a_raw or a,
            "aspect_term": "" if is_impl else (t_raw or ""),
            "polarity": p,
            "is_implicit": is_impl,
        })
    return out


def tuples_to_pairs(tuples_set: Set[EvalTuple]) -> Set[EvalPair]:
    """Convert EvalTuple set to (aspect_term, polarity) pairs for F1. aspect_ref is ignored. Polarity normalized.
    Used for explicit-only surface-level (SurfaceUnit) auxiliary evaluation."""
    if not tuples_set:
        return set()
    return {(normalize_for_eval(t), normalize_polarity(p)) for (_, t, p) in tuples_set}


def tuples_to_ref_pairs(tuples_set: Set[EvalTuple]) -> Tuple[Set[EvalPair], int]:
    """
    Convert EvalTuple set to (aspect_ref, polarity) pairs for ref-level F1 (CR v2 primary evaluation).
    Skips tuples with empty aspect_ref; returns (pairs, invalid_ref_count).
    Gold typically has aspect_ref; pred with empty ref is excluded.
    """
    if not tuples_set:
        return (set(), 0)
    pairs: Set[EvalPair] = set()
    invalid_ref_count = 0
    for (a, _, p) in tuples_set:
        ref = normalize_ref_for_eval(a) if a else ""
        if ref == "":
            invalid_ref_count += 1
            continue
        pairs.add((ref, normalize_polarity(p)))
    return (pairs, invalid_ref_count)


def tuples_to_attr_pairs(
    tuples_set: Set[EvalTuple],
    debug_counters: Optional[Dict[str, int]] = None,
) -> Tuple[Set[EvalPair], int]:
    """
    Convert EvalTuple set to (attribute, polarity) pairs for attr-level F1 (Table 1C diagnostic).
    Uses entity#attribute → attribute only via split("#", 1). Skips tuples with empty/invalid aspect_ref.
    Returns (pairs, invalid_ref_count).
    Gold is never filtered by allowlist; invalid_ref_count is diagnostic only.
    """
    if not tuples_set:
        return (set(), 0)
    counters = debug_counters if debug_counters is not None else {}
    pairs: Set[EvalPair] = set()
    invalid_ref_count = 0
    for (a, _, p) in tuples_set:
        ref = normalize_ref_for_eval(a or "")
        if not ref:
            invalid_ref_count += 1
            continue
        if "#" not in ref:
            counters["attr_split_missing_hash"] = counters.get("attr_split_missing_hash", 0) + 1
            invalid_ref_count += 1
            continue
        parts = ref.split("#", 1)
        attr = parts[1].strip() if len(parts) == 2 else ""
        if not attr:
            invalid_ref_count += 1
            continue
        pairs.add((normalize_for_eval(attr), normalize_polarity(p)))
    return (pairs, invalid_ref_count)


def tuples_to_pairs_ref_fallback(tuples_set: Set[EvalTuple]) -> Set[EvalPair]:
    """Convert to (aspect_ref or aspect_term, polarity) pairs. When aspect_ref is present, use it for matching (avoids term normalization mismatch)."""
    if not tuples_set:
        return set()
    out: Set[EvalPair] = set()
    for (a, t, p) in tuples_set:
        key = normalize_ref_for_eval(a) if a else normalize_for_eval(t or "")
        out.add((key, normalize_polarity(p)))
    return out


def precision_recall_f1_tuple(
    gold_tuples: Set[EvalTuple],
    pred_tuples: Set[EvalTuple],
    match_empty_aspect_by_polarity_only: bool = True,
    match_by_aspect_ref: bool = True,
) -> Tuple[float, float, float]:
    """
    Tuple F1. CR v2: primary evaluation uses (aspect_ref, polarity) — match_by_aspect_ref=True (default).
    When match_by_aspect_ref is True: gold and pred use tuples_to_ref_pairs; tuples with empty aspect_ref are excluded.
    When match_by_aspect_ref is False: (aspect_term, polarity) pairs; aspect_ref ignored.
    When match_empty_aspect_by_polarity_only is True (term mode only): gold pairs with aspect=="" match any pred with same polarity (one-to-one).

    POLICY: Gold is never filtered by allowlist (ALLOWED_REFS). invalid_ref_count applies to pred only (diagnostic).
    """
    if not gold_tuples:
        return (0.0, 0.0, 0.0)
    pred_tuples = pred_tuples or set()
    if match_by_aspect_ref:
        gold_pairs, _ = tuples_to_ref_pairs(gold_tuples)
        pred_pairs, _ = tuples_to_ref_pairs(pred_tuples)
    else:
        gold_pairs = tuples_to_pairs(gold_tuples)
        pred_pairs = tuples_to_pairs(pred_tuples)

    if not match_empty_aspect_by_polarity_only:
        tp = len(pred_pairs & gold_pairs)
        fp = len(pred_pairs - gold_pairs)
        fn = len(gold_pairs - pred_pairs)
    else:
        exact_gold = {(t, p) for (t, p) in gold_pairs if t != ""}
        polarity_only_gold = [p for (t, p) in gold_pairs if t == ""]
        tp_exact = len(pred_pairs & exact_gold)
        matched_pred = pred_pairs & exact_gold
        remaining_pred = pred_pairs - matched_pred
        tp_polarity = 0
        for p in polarity_only_gold:
            for pair in list(remaining_pred):
                if pair[1] == p:
                    remaining_pred = remaining_pred - {pair}
                    tp_polarity += 1
                    break
        tp = tp_exact + tp_polarity
        fp = len(pred_pairs) - tp
        fn = len(gold_pairs) - tp

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


# Valid polarity set for implicit / invalid-rate SSOT (positive, negative, neutral only).
VALID_POLARITIES = frozenset({"positive", "negative", "neutral"})


def _canon_polarity_for_valid(p: Optional[str]) -> Optional[str]:
    """Normalize polarity; return None if missing/empty/unknown (invalid for pred validity)."""
    if p is None or (isinstance(p, str) and not p.strip()):
        return None
    key = (p or "").strip().lower()
    if key in _POLARITY_MAP:
        out = _POLARITY_MAP[key]
        return out if out in VALID_POLARITIES else None
    if key in VALID_POLARITIES:
        return key
    return None


def gold_implicit_polarities_from_tuples(gold_tuples: Set[EvalTuple]) -> List[str]:
    """Extract polarities from gold tuples where aspect_term is empty (implicit gold). Polarity normalized to {positive, negative, neutral}."""
    out: List[str] = []
    for (_a, term, pol) in gold_tuples or set():
        if normalize_for_eval((term or "").strip()) != "":
            continue
        p = normalize_polarity(pol, default_missing=None)
        if p is not None and p in VALID_POLARITIES:
            out.append(p)
    return out


def pred_valid_polarities_from_tuples(pred_tuples: Set[EvalTuple]) -> Tuple[List[str], int]:
    """From pred tuples, collect polarities that are valid (in {positive, negative, neutral}). Returns (valid_polarities, invalid_count)."""
    valid: List[str] = []
    invalid = 0
    for (_a, _t, pol) in pred_tuples or set():
        p = _canon_polarity_for_valid(pol)
        if p is not None:
            valid.append(p)
        else:
            invalid += 1
    return (valid, invalid)


def precision_recall_f1_implicit_only(
    gold_implicit_polarities: List[str],
    pred_valid_polarities: List[str],
) -> Tuple[float, float, float]:
    """
    Implicit-only F1: match by polarity only (no aspect). Set-based.
    gold_implicit_polarities / pred_valid_polarities: list of polarities in {positive, negative, neutral}.
    """
    gold_set = set(gold_implicit_polarities) if gold_implicit_polarities else set()
    pred_set = set(pred_valid_polarities) if pred_valid_polarities else set()
    if not gold_set:
        return (0.0, 0.0, 0.0)
    tp = len(pred_set & gold_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


def precision_recall_f1_from_pairs(
    gold_pairs: Set[EvalPair],
    pred_pairs: Set[EvalPair],
) -> Tuple[float, float, float]:
    """F1 from (aspect, polarity) pair sets. Used for attr-pol and custom pair-level eval."""
    if not gold_pairs:
        return (0.0, 0.0, 0.0)
    pred_pairs = pred_pairs or set()
    tp = len(pred_pairs & gold_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


def pair_sets_match(gold_pairs: Set[EvalPair], pred_pairs: Set[EvalPair]) -> bool:
    """True when pred exactly covers gold (prec=1, rec=1)."""
    if not gold_pairs:
        return len(pred_pairs or set()) == 0
    prec, rec, _ = precision_recall_f1_from_pairs(gold_pairs, pred_pairs or set())
    return prec == 1.0 and rec == 1.0


def tuple_sets_match_with_empty_rule(
    gold_tuples: Set[EvalTuple],
    pred_tuples: Set[EvalTuple],
    match_empty_aspect_by_polarity_only: bool = True,
    match_by_aspect_ref: bool = True,
) -> bool:
    """True when pred exactly covers gold under the same F1 rule (prec=1, rec=1)."""
    if not gold_tuples:
        return len(pred_tuples or set()) == 0
    prec, rec, _ = precision_recall_f1_tuple(
        gold_tuples, pred_tuples or set(),
        match_empty_aspect_by_polarity_only=match_empty_aspect_by_polarity_only,
        match_by_aspect_ref=match_by_aspect_ref,
    )
    return prec == 1.0 and rec == 1.0


def _gold_aspect_term(t: Dict[str, Any]) -> str:
    """Gold aspect_term: keep "" when explicitly empty (암시적); do not fill with aspect_ref."""
    if "aspect_term" in t and t.get("aspect_term") == "":
        return ""
    raw = t.get("aspect_term") or (t.get("opinion_term") or {}).get("term")
    if raw is not None:
        return (raw or "").strip() if isinstance(raw, str) else str(raw).strip()
    return (t.get("aspect_ref") or t.get("term") or "").strip()


def gold_row_to_tuples(
    row: Dict[str, Any],
    default_missing_polarity: Optional[str] = "neutral",
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Normalize a gold row to list of dicts with aspect_ref, aspect_term, polarity.
    Accepts gold_tuples (preferred) or gold_triplets (backward compat).
    When default_missing_polarity is None and any tuple has missing polarity, returns (list, True) for eval_excluded.
    Otherwise returns (list, False).
    """
    def _one(t: Dict[str, Any]) -> Optional[str]:
        return normalize_polarity(t.get("polarity") or t.get("label"), default_missing=default_missing_polarity)

    gold_tuples = row.get("gold_tuples")
    if isinstance(gold_tuples, list) and gold_tuples:
        out_gt: List[Dict[str, Any]] = []
        has_missing = False
        for t in gold_tuples:
            if isinstance(t, dict):
                p = _one(t)
                if p is None:
                    has_missing = True
                    continue
                out_gt.append({
                    "aspect_ref": (t.get("aspect_ref") or t.get("term") or "").strip(),
                    "aspect_term": _gold_aspect_term(t),
                    "polarity": p,
                })
        return (out_gt if out_gt else [], has_missing)

    gold_triplets = row.get("gold_triplets")
    if not isinstance(gold_triplets, list) or not gold_triplets:
        return ([], False)

    out: List[Dict[str, Any]] = []
    has_missing = False
    for it in gold_triplets or []:
        if not it or not isinstance(it, dict):
            continue
        p = _one(it)
        if p is None:
            has_missing = True
            continue
        aspect_ref = (it.get("aspect_ref") or it.get("term") or "").strip()
        aspect_term = _gold_aspect_term(it)
        out.append({"aspect_ref": aspect_ref, "aspect_term": aspect_term, "polarity": p})
    return (out, has_missing)


def gold_tuples_from_record(
    record: Dict[str, Any],
    default_missing_polarity: Optional[str] = "neutral",
) -> Tuple[Optional[List[Dict[str, Any]]], bool]:
    """
    Get normalized gold list from scorecard/inputs. Prefer gold_tuples; fallback gold_triplets.
    Returns (list, eval_excluded). When default_missing_polarity is None and any gold tuple has missing polarity, eval_excluded=True (sample should be excluded from F1).
    """
    inputs = record.get("inputs") or {}
    row = {
        "gold_tuples": record.get("gold_tuples") or inputs.get("gold_tuples"),
        "gold_triplets": record.get("gold_triplets") or inputs.get("gold_triplets"),
    }
    if not row["gold_tuples"] and not row["gold_triplets"]:
        return (None, False)
    lst, has_missing = gold_row_to_tuples(row, default_missing_polarity=default_missing_polarity)
    if has_missing and default_missing_polarity is None:
        return (None, True)  # eval_excluded
    return (lst if lst else None, has_missing)


def gold_tuple_set_from_record(
    record: Dict[str, Any],
    default_missing_polarity: Optional[str] = "neutral",
) -> Optional[Set[EvalTuple]]:
    """Gold as set of EvalTuple for F1. None if no gold or eval_excluded (missing polarity when default_missing_polarity is None)."""
    lst, eval_excluded = gold_tuples_from_record(record, default_missing_polarity=default_missing_polarity)
    if lst is None or eval_excluded:
        return None
    return tuples_from_list(lst, default_missing_polarity=default_missing_polarity)
