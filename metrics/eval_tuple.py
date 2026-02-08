"""
ABSA evaluation Tuple (Aspect, Polarity) contract.

- Tuple = (aspect_ref, aspect_term, polarity). aspect_term = 문장 내 관점 표면형(surface form).
  Pipeline ATSA output uses aspect_term (AspectTerm: term, span) only; aspect_ref is not used in pipeline.
- Gold: gold_tuples (preferred) or gold_triplets with backward compat (opinion_term.term → aspect_term).
- Scoring (F1): match on (aspect_term, polarity) only; aspect_ref is ignored.
  Samples without gold are excluded from tuple F1. See docs/absa_tuple_eval.md.
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


def normalize_polarity(s: Optional[str]) -> str:
    """Normalize polarity to canonical form: pos->positive, neg->negative, neu->neutral."""
    if s is None or (isinstance(s, str) and not s.strip()):
        return "neutral"
    key = (s or "").strip().lower()
    return _POLARITY_MAP.get(key, key if key in ("positive", "negative", "neutral", "mixed") else "neutral")


def normalize_for_eval(s: Optional[str]) -> str:
    """Normalize string for matching: strip, lower, collapse whitespace, remove leading/trailing punct. null/None -> ""."""
    if s is None:
        return ""
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(".,;:!?\"'`""''()[]{}")
    return t


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


def tuple_from_sent(sent: Dict[str, Any]) -> EvalTuple:
    """
    Build (aspect_ref, aspect_term, polarity) from a sentiment/aspect dict.
    aspect_term: from aspect_term (AspectTerm.term or string) or legacy opinion_term.term; no fallback to aspect_ref.
    If is_implicit is True, aspect_term is "" (암시적 관점).
    aspect_ref: only from gold/taxonomy (sent.get("aspect_ref")); pipeline output has no aspect_ref.
    polarity: normalized via normalize_polarity (pos->positive, etc.).
    """
    if sent.get("is_implicit") is True:
        aspect_term = ""
    else:
        aspect_term_raw = _aspect_term_text(sent)
        aspect_term = normalize_for_eval(aspect_term_raw) if aspect_term_raw else ""
    aspect_ref = normalize_for_eval(sent.get("aspect_ref") or sent.get("term"))
    polarity = normalize_polarity(sent.get("polarity") or sent.get("label"))
    return (aspect_ref, aspect_term, polarity)


def tuples_from_list(items: Any) -> Set[EvalTuple]:
    """Convert list of sentiment dicts to set of EvalTuple. Includes aspect_term=\"\" tuples (암시적) for F1 (\"\", polarity) pairing."""
    if not items or not isinstance(items, (list, tuple)):
        return set()
    out: Set[EvalTuple] = set()
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        t = tuple_from_sent(it)
        if t[0] or t[1] or (t[2] and t[2].strip()):
            out.add(t)
    return out


def tuples_to_list_of_dicts(tuples_set: Set[EvalTuple]) -> List[Dict[str, str]]:
    """Serialize set of EvalTuple to list of dicts for JSON/schema (aspect_ref, aspect_term, polarity)."""
    if not tuples_set:
        return []
    return [{"aspect_ref": a, "aspect_term": t, "polarity": p} for (a, t, p) in tuples_set]


def tuples_to_pairs(tuples_set: Set[EvalTuple]) -> Set[EvalPair]:
    """Convert EvalTuple set to (aspect_term, polarity) pairs for F1. aspect_ref is ignored. Polarity normalized."""
    if not tuples_set:
        return set()
    return {(normalize_for_eval(t), normalize_polarity(p)) for (_, t, p) in tuples_set}


def precision_recall_f1_tuple(
    gold_tuples: Set[EvalTuple],
    pred_tuples: Set[EvalTuple],
    match_empty_aspect_by_polarity_only: bool = True,
) -> Tuple[float, float, float]:
    """
    Tuple F1: match on (aspect_term, polarity).
    When match_empty_aspect_by_polarity_only is True (default), gold pairs with
    aspect_term=="" match any pred pair with the same polarity (one-to-one).
    """
    if not gold_tuples:
        return (0.0, 0.0, 0.0)
    pred_tuples = pred_tuples or set()
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


def tuple_sets_match_with_empty_rule(
    gold_tuples: Set[EvalTuple],
    pred_tuples: Set[EvalTuple],
    match_empty_aspect_by_polarity_only: bool = True,
) -> bool:
    """True when pred exactly covers gold under the same F1 rule (prec=1, rec=1)."""
    if not gold_tuples:
        return len(pred_tuples or set()) == 0
    prec, rec, _ = precision_recall_f1_tuple(
        gold_tuples, pred_tuples or set(), match_empty_aspect_by_polarity_only
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


def gold_row_to_tuples(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Normalize a gold row to list of dicts with aspect_ref, aspect_term, polarity.
    Accepts gold_tuples (preferred) or gold_triplets (backward compat: opinion_term.term → aspect_term).
    When aspect_term is explicitly "" in source (암시적 관점), keep ""; do not fill with aspect_ref.
    """
    gold_tuples = row.get("gold_tuples")
    if isinstance(gold_tuples, list) and gold_tuples:
        out_gt: List[Dict[str, Any]] = []
        for t in gold_tuples:
            if isinstance(t, dict):
                out_gt.append({
                    "aspect_ref": (t.get("aspect_ref") or t.get("term") or "").strip(),
                    "aspect_term": _gold_aspect_term(t),
                    "polarity": normalize_polarity(t.get("polarity") or t.get("label") or "neutral"),
                })
        return out_gt if out_gt else []

    gold_triplets = row.get("gold_triplets")
    if not isinstance(gold_triplets, list) or not gold_triplets:
        return []

    out: List[Dict[str, Any]] = []
    for it in gold_triplets or []:
        if not it or not isinstance(it, dict):
            continue
        aspect_ref = (it.get("aspect_ref") or it.get("term") or "").strip()
        polarity = normalize_polarity(it.get("polarity") or it.get("label") or "neutral")
        aspect_term = _gold_aspect_term(it)
        out.append({"aspect_ref": aspect_ref, "aspect_term": aspect_term, "polarity": polarity})
    return out


def gold_tuples_from_record(record: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Get normalized gold list from scorecard/inputs. Prefer gold_tuples; fallback gold_triplets.
    Returns list of {aspect_ref, aspect_term, polarity} or None if no gold.
    """
    inputs = record.get("inputs") or {}
    row = {
        "gold_tuples": record.get("gold_tuples") or inputs.get("gold_tuples"),
        "gold_triplets": record.get("gold_triplets") or inputs.get("gold_triplets"),
    }
    if not row["gold_tuples"] and not row["gold_triplets"]:
        return None
    lst = gold_row_to_tuples(row)
    return lst if lst else None


def gold_tuple_set_from_record(record: Dict[str, Any]) -> Optional[Set[EvalTuple]]:
    """Gold as set of EvalTuple for F1. None if no gold."""
    lst = gold_tuples_from_record(record)
    if not lst:
        return None
    return tuples_from_list(lst)
