"""
Advisory injection gate for C2: inject memory only when at least one of (OR):
  - polarity_conflict_raw == 1  (same aspect with ≥2 polarities in stage1)
  - validator_s1_risk_ids not empty
  - alignment_failure_count >= 2
  - explicit_grounding_failure bucket (approximated at runtime)

Used by SupervisorAgent when merging DEBATE_CONTEXT__MEMORY into debate prompt.
Logic aligned with structural_error_aggregator risk_flagged / triptych columns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# Drop reason (must match scripts/scorecard_from_smoke and docs/metric_spec_rq1_grounding_v2.md)
DROP_REASON_ALIGNMENT_FAILURE = "alignment_failure"

# Same allowlist/stoplist as scorecard_from_smoke for alignment_failure counting
STOP_ASPECT_TERMS: Set[str] = {"ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "아", "야", "언제", "하지만", "그러나"}
TARGET_ALLOWLIST: Set[str] = {"뷰", "AS", "as", "ui", "UI", "앱", "app"}


def _safe_sub(text: str, span: Any) -> str:
    """Extract substring; span may be dict with start/end or Pydantic model."""
    try:
        if hasattr(span, "model_dump"):
            d = span.model_dump()
        else:
            d = span if isinstance(span, dict) else {}
        return text[int(d.get("start", 0)) : int(d.get("end", 0))]
    except Exception:
        return ""


def _aspects_to_dict_list(stage1_ate: Any) -> List[Dict[str, Any]]:
    """Convert stage1_ate.aspects to list of {term, span} dicts."""
    aspects = getattr(stage1_ate, "aspects", None) or []
    out: List[Dict[str, Any]] = []
    for a in aspects:
        term = getattr(a, "term", None) or (a.get("term", "") if isinstance(a, dict) else "")
        span = getattr(a, "span", None)
        if span is not None and hasattr(span, "model_dump"):
            span = span.model_dump()
        elif not isinstance(span, dict):
            span = {}
        out.append({"term": term, "span": span})
    return out


def _count_alignment_failure_drops(text: str, aspects: List[Dict[str, Any]]) -> int:
    """Count drops with drop_reason=alignment_failure. Same rules as scorecard_from_smoke build_filtered_aspects."""
    n = 0
    allow = TARGET_ALLOWLIST
    for a in aspects:
        term = (a.get("term") or "").strip()
        span = a.get("span") or {}
        span_txt = _safe_sub(text, span)
        span_ok = term == span_txt
        has_span = isinstance(span, dict) and "start" in span and "end" in span
        is_valid = (term in allow) or (
            (len(term) >= 2) and ((term not in STOP_ASPECT_TERMS) or (term in allow))
        )
        action = "keep" if (is_valid and span_ok) else "drop"
        if action == "drop" and has_span and term != span_txt:
            n += 1
    return n


def _has_polarity_conflict_raw_stage1(stage1_atsa: Any) -> bool:
    """Same aspect_term with ≥2 distinct polarities in stage1 aspect_sentiments."""
    sents = getattr(stage1_atsa, "aspect_sentiments", None) or []
    by_term: Dict[str, Set[str]] = {}
    for s in sents:
        at = getattr(s, "aspect_term", None)
        term = ""
        if at is not None:
            term = (getattr(at, "term", None) or (at.get("term", "") if isinstance(at, dict) else "")) or ""
        pol = (getattr(s, "polarity", None) or (s.get("polarity", "") if isinstance(s, dict) else "neutral")) or "neutral"
        by_term.setdefault(term.strip(), set()).add(pol)
    return any(len(pols) > 1 for pols in by_term.values())


def _validator_s1_risk_ids_not_empty(stage1_validator: Any) -> bool:
    """True if stage1 validator has at least one structural_risk."""
    risks = getattr(stage1_validator, "structural_risks", None) or []
    return len(risks) > 0


def _alignment_failure_count_ge_2(text: str, stage1_ate: Any) -> bool:
    """True if alignment_failure drop count >= 2."""
    aspects = _aspects_to_dict_list(stage1_ate)
    return _count_alignment_failure_drops(text, aspects) >= 2


def _is_explicit_grounding_failure_bucket(text: str, stage1_ate: Any, stage1_atsa: Any) -> bool:
    """Approximation: has explicit aspect(s) and all drops are alignment_failure (sample in explicit_failure bucket).
    At pipeline time we don't have sentiment_judgements; we use 'all dropped with alignment_failure' as proxy."""
    aspects = _aspects_to_dict_list(stage1_ate)
    if not aspects:
        return False
    n_align = _count_alignment_failure_drops(text, aspects)
    if n_align == 0:
        return False
    # All aspects dropped and every drop is alignment_failure => explicit alignment failed
    n_drops = 0
    allow = TARGET_ALLOWLIST
    for a in aspects:
        term = (a.get("term") or "").strip()
        span = a.get("span") or {}
        span_txt = _safe_sub(text, span)
        span_ok = term == span_txt
        has_span = isinstance(span, dict) and "start" in span and "end" in span
        is_valid = (term in allow) or (
            (len(term) >= 2) and ((term not in STOP_ASPECT_TERMS) or (term in allow))
        )
        if not (is_valid and span_ok):
            n_drops += 1
    return n_drops >= 1 and n_align == n_drops


# Trigger reason labels for injection_trigger_reason_counts (C2 gate coverage)
INJECTION_REASON_CONFLICT = "conflict"
INJECTION_REASON_VALIDATOR = "validator"
INJECTION_REASON_ALIGNMENT = "alignment"
INJECTION_REASON_EXPLICIT_GROUNDING = "explicit_grounding_failure"
INJECTION_REASON_NEUTRAL_ONLY = "neutral_only"

# Debate gate (conservative) = existing should_inject_advisory_with_reason.
# Stage2 gate (relaxed) = should_inject_memory_for_stage2_with_reason.


def _alignment_failure_count_ge_1(text: str, stage1_ate: Any) -> bool:
    """True if alignment_failure drop count >= 1 (relaxed for Stage2)."""
    aspects = _aspects_to_dict_list(stage1_ate)
    return _count_alignment_failure_drops(text, aspects) >= 1


def _is_neutral_only_stage1(stage1_atsa: Any) -> bool:
    """True if Stage1 aspect_sentiments are almost all neutral (0 or 1 non-neutral)."""
    sents = getattr(stage1_atsa, "aspect_sentiments", None) or []
    if not sents:
        return False
    non_neutral = 0
    for s in sents:
        pol = (getattr(s, "polarity", None) or (s.get("polarity", "") if isinstance(s, dict) else "")) or ""
        pol = (pol or "").strip().lower()
        if pol not in ("neutral", "neu", ""):
            non_neutral += 1
    return non_neutral <= 1


def should_inject_memory_for_debate_with_reason(
    text: str,
    stage1_ate: Any,
    stage1_atsa: Any,
    stage1_validator: Any,
) -> tuple[bool, Optional[str]]:
    """Debate gate (conservative). Same as should_inject_advisory_with_reason."""
    return should_inject_advisory_with_reason(text, stage1_ate, stage1_atsa, stage1_validator)


def should_inject_memory_for_stage2_with_reason(
    text: str,
    stage1_ate: Any,
    stage1_atsa: Any,
    stage1_validator: Any,
) -> tuple[bool, Optional[str]]:
    """
    Stage2 gate (relaxed). True if any of (OR):
      validator_s1_risk, polarity_conflict_raw, alignment_failure >= 1,
      neutral_only (Stage1 almost all neutral), explicit_grounding_failure.
    """
    if _validator_s1_risk_ids_not_empty(stage1_validator):
        return True, INJECTION_REASON_VALIDATOR
    if _has_polarity_conflict_raw_stage1(stage1_atsa):
        return True, INJECTION_REASON_CONFLICT
    if _alignment_failure_count_ge_1(text, stage1_ate):
        return True, INJECTION_REASON_ALIGNMENT
    if _is_neutral_only_stage1(stage1_atsa):
        return True, INJECTION_REASON_NEUTRAL_ONLY
    if _is_explicit_grounding_failure_bucket(text, stage1_ate, stage1_atsa):
        return True, INJECTION_REASON_EXPLICIT_GROUNDING
    return False, None


def should_inject_advisory(
    text: str,
    stage1_ate: Any,
    stage1_atsa: Any,
    stage1_validator: Any,
) -> bool:
    """
    True iff at least one of (OR):
      - polarity_conflict_raw == 1
      - validator_s1_risk_ids not empty
      - alignment_failure_count >= 2
      - explicit_grounding_failure bucket (approximated)
    """
    _, reason = should_inject_advisory_with_reason(text, stage1_ate, stage1_atsa, stage1_validator)
    return reason is not None


def should_inject_advisory_with_reason(
    text: str,
    stage1_ate: Any,
    stage1_atsa: Any,
    stage1_validator: Any,
) -> tuple[bool, Optional[str]]:
    """
    Returns (should_inject, trigger_reason). reason is one of conflict/validator/alignment/explicit_grounding_failure.
    """
    if _has_polarity_conflict_raw_stage1(stage1_atsa):
        return True, INJECTION_REASON_CONFLICT
    if _validator_s1_risk_ids_not_empty(stage1_validator):
        return True, INJECTION_REASON_VALIDATOR
    if _alignment_failure_count_ge_2(text, stage1_ate):
        return True, INJECTION_REASON_ALIGNMENT
    if _is_explicit_grounding_failure_bucket(text, stage1_ate, stage1_atsa):
        return True, INJECTION_REASON_EXPLICIT_GROUNDING
    return False, None
