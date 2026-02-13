from __future__ import annotations

from typing import List, Optional, Dict, Any, Literal, Tuple

from pydantic import BaseModel, Field, field_validator


class Span(BaseModel):
    """Standard span/risk_scope representation."""

    start: int = Field(ge=0, description="Start index inclusive.")
    end: int = Field(ge=0, description="End index exclusive.")


# ATE (Aspect Extraction)
class AspectExtractionItem(BaseModel):
    term: str = Field(default="", description="텍스트 그대로의 속성 명")
    span: Span
    normalized: Optional[str] = Field(default=None, description="정규화된 표현")
    syntactic_head: Optional[str] = Field(default=None, description="지배소(핵심 서술어)")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", description="추출 근거")


class AspectExtractionReviewItem(BaseModel):
    term: str
    action: str = Field(default="keep", description="keep|revise_span|remove")
    revised_span: Optional[Span] = None
    reason: str = Field(default="", description="Validator 지적 반영")
    provenance: Optional[str] = Field(default=None, description="source:<speaker>/<stance>")


class AspectExtractionStage1Schema(BaseModel):
    aspects: List[AspectExtractionItem] = Field(default_factory=list)


class AspectExtractionStage2Schema(BaseModel):
    aspect_review: List[AspectExtractionReviewItem] = Field(default_factory=list)


# ATSA — 문장 내 관점 표면형(term + span)
class AspectTerm(BaseModel):
    """문장 내 관점 표면형: term(텍스트) + span(문자 구간)."""
    term: str = Field(default="", description="문장 내 관점 표면형 텍스트")
    span: Span = Field(default_factory=lambda: Span(start=0, end=0), description="문장 내 문자 구간")


# Canonical polarity values; raw LLM may use pos/neg/neu.
POLARITY_VALID = frozenset({"positive", "negative", "neutral"})
# Targets for edit-distance repair (only these; whitelist is pos/neg/neu + these)
POLARITY_CANONICAL_TARGETS = ("positive", "negative", "neutral")

# Whitelist: exact match only (no repair)
POLARITY_WHITELIST = frozenset({"pos", "neg", "neu", "positive", "negative", "neutral"})


def _levenshtein(a: str, b: str) -> int:
    """Levenshtein distance between two strings (for typo repair within 1~2)."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    n, m = len(a), len(b)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i]
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[m]


def canonicalize_polarity_with_repair(s: str | None) -> Tuple[Optional[str], bool]:
    """
    Map raw polarity to canonical (positive/negative/neutral). Returns (canonical, was_repaired).

    Strict typo policy:
    - Whitelist: pos/neg/neu, positive/negative/neutral (exact, case-insensitive) → (canon, False).
    - Repair: edit distance 1 or 2 to exactly one of positive/negative/neutral → (canon, True).
    - Otherwise → (None, False) (invalid; do not repair).
    """
    if s is None or (isinstance(s, str) and not s.strip()):
        return (None, False)
    raw = (s if isinstance(s, str) else str(s)).strip().lower()
    if raw in ("pos", "positive"):
        return ("positive", False)
    if raw in ("neg", "negative"):
        return ("negative", False)
    if raw in ("neu", "neutral"):
        return ("neutral", False)
    if raw in POLARITY_VALID:
        return (raw, False)
    # Edit-distance 1~2 repair: only if unique minimum in [1, 2]
    best_target: Optional[str] = None
    best_d = 10
    for t in POLARITY_CANONICAL_TARGETS:
        d = _levenshtein(raw, t)
        if 1 <= d <= 2 and d < best_d:
            best_d = d
            best_target = t
        elif 1 <= d <= 2 and d == best_d:
            best_target = None  # tie → ambiguous, do not repair
    if best_target is not None:
        return (best_target, True)
    return (None, False)


def canonicalize_polarity(s: str | None) -> Optional[str]:
    """
    Map raw polarity to canonical (positive/negative/neutral). Returns None if unmappable.

    Policy: whitelist exact + repair only when edit distance 1~2 (see canonicalize_polarity_with_repair).
    Use for override gate (invalid dropped and counted) and ATSA (invalid → None, run continues).
    """
    canon, _ = canonicalize_polarity_with_repair(s)
    return canon


def _normalize_polarity_value(v: str | None) -> Optional[str]:
    """
    Same policy as canonicalize_polarity_with_repair. Invalid/missing → None (no raise).
    ATSA: invalid polarity → sample marked invalid, run continues (no retry/abort).
    """
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    canon, _ = canonicalize_polarity_with_repair(v)
    return canon


def normalize_polarity_distribution(raw: Dict[str, float] | None) -> Dict[str, float]:
    """Normalize polarity_distribution keys: pos->positive, neg->negative, neu->neutral."""
    if not raw:
        return {}
    out: Dict[str, float] = {}
    for k, val in raw.items():
        key = (k or "").strip().lower()
        if key in ("pos", "positive"):
            out["positive"] = out.get("positive", 0) + float(val)
        elif key in ("neg", "negative"):
            out["negative"] = out.get("negative", 0) + float(val)
        elif key in ("neu", "neutral"):
            out["neutral"] = out.get("neutral", 0) + float(val)
        elif key in POLARITY_VALID:
            out[k] = out.get(k, 0) + float(val)
    return out


class AspectSentimentItem(BaseModel):
    """
    neutral ≠ missing: polarity=None means missing; use polarity=\"neutral\" only when text has no explicit pos/neg.
    Backfill/placeholder should set is_backfilled=True and neutral_reason so eval can separate.
    """
    aspect_term: Optional[AspectTerm] = Field(default=None, description="문장 내 관점 표면형(term+span). 암시적이면 None.")
    polarity: Optional[str] = Field(default=None, description="positive/negative/neutral. None = missing (do not treat as neutral).")
    evidence: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    polarity_distribution: Dict[str, float] = Field(default_factory=dict)
    is_implicit: bool = Field(default=False)
    is_backfilled: bool = Field(default=False, description="True when sentiment was filled for missing ATSA (ATE-only aspect).")
    neutral_reason: Optional[str] = Field(default=None, description="When polarity=neutral, reason e.g. missing_atsa_for_aspect, backfill_no_opinion.")

    @field_validator("polarity", mode="before")
    @classmethod
    def _polarity_canonical(cls, v: Any) -> Optional[str]:
        """Allow None (missing/invalid); whitelist or edit-distance 1~2 repair when present. Invalid → None, run continues."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return _normalize_polarity_value(v)


class SentimentReviewItem(BaseModel):
    aspect_term: str = Field(default="", description="대상 감성 항목 식별용 관점 표면형(term 텍스트)")
    action: str = Field(default="maintain")
    revised_polarity: Optional[str] = None
    reason: str = Field(default="")
    provenance: Optional[str] = Field(default=None, description="source:<speaker>/<stance>")


class AspectSentimentStage1Schema(BaseModel):
    aspect_sentiments: List[AspectSentimentItem] = Field(default_factory=list)


class AspectSentimentStage2Schema(BaseModel):
    sentiment_review: List[SentimentReviewItem] = Field(default_factory=list)


# Validator
class StructuralRiskItem(BaseModel):
    type: str = Field(default="")
    scope: Span
    severity: str = Field(default="")
    description: str = Field(default="")


class CorrectionProposal(BaseModel):
    target_aspect: str = Field(default="")
    proposal_type: str = Field(default="")
    rationale: str = Field(default="")


class StructuralValidatorStage1Schema(BaseModel):
    structural_risks: List[StructuralRiskItem] = Field(default_factory=list)
    consistency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    correction_proposals: List[CorrectionProposal] = Field(default_factory=list)


class StructuralValidatorStage2Schema(BaseModel):
    final_validation: Dict[str, Any] = Field(default_factory=dict)


# Normalized validator output (same schema for stage1/stage2; for scorecard/metrics)
VALIDATOR_RISK_IDS = (
    "NEGATION_SCOPE",
    "CONTRAST_SCOPE",
    "POLARITY_MISMATCH",
    "EVIDENCE_GAP",
    "SPAN_MISMATCH",
    "OTHER",
)


class ValidatorStructuralRiskItem(BaseModel):
    """Single structural risk; risk_id is fixed enum for S1/S2 comparison."""
    risk_id: str = Field(default="OTHER", description="Fixed enum for aggregation.")
    severity: Literal["low", "mid", "high"] = Field(default="mid")
    span: List[int] = Field(default_factory=lambda: [0, 0], description="[start, end]")
    description: str = Field(default="")


class ValidatorProposalItem(BaseModel):
    """Single correction proposal; target and action for metrics."""
    target: Literal["ATE", "ATSA"] = Field(default="ATSA")
    action: Literal["revise_span", "revise_polarity", "recheck_evidence", "other"] = Field(default="other")
    reason: str = Field(default="")


class ValidatorStageOutput(BaseModel):
    """Unified validator output per stage (stage1 or stage2) for scorecard."""
    stage: Literal["stage1", "stage2"] = Field(default="stage1")
    structural_risks: List[ValidatorStructuralRiskItem] = Field(default_factory=list)
    proposals: List[ValidatorProposalItem] = Field(default_factory=list)


class ATEOutput(BaseModel):
    """Aspect-independent (document-level) sentiment."""

    label: str = Field(default="neutral", min_length=1, description="Polarity label.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1.")
    rationale: str = Field(default="", description="Brief reasoning.")
    risk_scope: Optional[Span] = Field(default=None, description="Optional risk scope span.")


class ATSAOutput(BaseModel):
    """Aspect/target-aware sentiment."""

    target: Optional[str] = Field(default=None, description="Detected target/aspect if any.")
    label: str = Field(default="neutral", min_length=1, description="Polarity label for the target.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0-1.")
    rationale: str = Field(default="", description="Brief reasoning.")
    span: Optional[Span] = Field(default=None, description="Span of the target if known.")
    risk_scope: Optional[Span] = Field(default=None, description="Optional risk scope span.")


class ValidatorOutput(BaseModel):
    """Cross-check between ATE/ATSA predictions."""

    agrees_with_ate: bool = Field(default=True, description="Does validator agree with ATE?")
    agrees_with_atsa: bool = Field(default=True, description="Does validator agree with ATSA?")
    suggested_label: Optional[str] = Field(default=None, description="Suggested corrected label if disagreement.")
    issues: List[str] = Field(default_factory=list, description="List of detected issues.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Validator confidence.")


class ArbiterFlags(BaseModel):
    """Why Stage2 was/wasn't selected; for metrics aggregation."""
    stage2_rejected_due_to_confidence: bool = Field(default=False)
    validator_override_applied: bool = Field(default=False)
    confidence_margin_used: float = Field(default=0.0, ge=0.0, le=1.0)
    # S0/S3: Rule E and Rule B vs E order logging
    rule_e_fired: bool = Field(default=False, description="True when Rule E actually changed final_label.")
    rule_e_block_reason: Optional[str] = Field(default=None, description="Why Rule E did not apply (e.g. confidence_too_high, label_unchanged).")
    rule_b_applied: bool = Field(default=False, description="True when Rule B was evaluated (stage2 preference).")
    rule_e_attempted_after_b: bool = Field(default=False, description="True when Rule E was evaluated after Rule B (order log).")


class ModeratorOutput(BaseModel):
    """Rule-based moderator decision."""

    final_label: str = Field(default="neutral", min_length=1, description="Moderator-selected final label.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Moderator confidence.")
    rationale: str = Field(default="", description="Why this final label was chosen.")
    # Extended for metrics: which stage was selected and which rules fired
    selected_stage: Literal["stage1", "stage2"] = Field(default="stage2", description="Which stage output was used.")
    applied_rules: List[str] = Field(default_factory=list, description="e.g. ['RuleA', 'RuleC'].")
    decision_reason: str = Field(default="", description="Alias/summary of rationale for aggregation.")
    arbiter_flags: ArbiterFlags = Field(default_factory=ArbiterFlags)


# Debate layer (EPM/TAN/CJ annotation correctors — patch-only, no pro/con battle)
class ProposedEdit(BaseModel):
    """Single patch operation: set_polarity, set_aspect_ref, merge_tuples, drop_tuple, confirm_tuple, etc. S2: target should use aspect_ref for mapping."""
    op: str = Field(default="", description="set_polarity | set_aspect_ref | merge_tuples | drop_tuple | confirm_tuple")
    target: Dict[str, Any] = Field(default_factory=dict, description="Must include aspect_ref (Stage1 term key for mapping). Optional aspect_term, polarity. e.g. {aspect_ref: str, aspect_term?: str, polarity?: str}")
    value: Optional[str] = Field(default=None, description="e.g. polarity or aspect_ref value")
    evidence: Optional[str] = Field(default=None, description="text span or citation for EPM")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DebatePersona(BaseModel):
    """EPM / TAN / CJ: role and goal only. stance/style deprecated (no pro/con)."""
    name: str = Field(default="", description="agent display name (e.g. EPM, TAN, CJ)")
    role: str = Field(default="", description="Evidence–Polarity Mapper | Target–Aspect Normalizer | Consistency Judge")
    goal: str = Field(default="", description="annotation corrector goal for this agent")
    stance: str = Field(default="", description="deprecated; unused (no pro/con)")
    style: str = Field(default="", description="optional; unused in patch-only flow")


class DebateTurn(BaseModel):
    """EPM/TAN output: agent + proposed_edits only. Legacy speaker/message kept for backward compat."""
    agent: str = Field(default="", description="EPM | TAN | CJ")
    proposed_edits: List[ProposedEdit] = Field(default_factory=list, description="patch actions only")
    speaker: str = Field(default="", description="legacy; use agent")
    stance: str = Field(default="", description="legacy; unused")
    planning: str = Field(default="", description="optional")
    reflection: str = Field(default="", description="optional")
    message: str = Field(default="", description="optional; prefer proposed_edits")
    key_points: List[str] = Field(default_factory=list, description="optional")


class DebateRound(BaseModel):
    round_index: int = Field(default=1, ge=1)
    turns: List[DebateTurn] = Field(default_factory=list)


class DebateSummary(BaseModel):
    """CJ output: final_patch + final_tuples + unresolved_conflicts. winner/consensus deprecated. S1: sentence-level conclusion/evidence."""
    final_patch: List[Dict[str, Any]] = Field(default_factory=list, description="drop_tuple, confirm_tuple, etc. Stage2-ready.")
    final_tuples: List[Dict[str, Any]] = Field(default_factory=list, description="single consistent set; each item {aspect_ref, aspect_term?, polarity} for mapping_direct_rate.")
    unresolved_conflicts: List[str] = Field(default_factory=list, description="empty when converged")
    # S1: sentence-level conclusion and evidence spans (Rule E can use these instead of inferring from tuples only)
    sentence_polarity: Optional[str] = Field(default=None, description="Sentence-level overall polarity from Judge (positive/negative/neutral/mixed).")
    sentence_evidence_spans: List[str] = Field(default_factory=list, description="1+ exact substrings from the source text that support the conclusion.")
    aspect_evidence: Optional[Dict[str, str]] = Field(default=None, description="Optional map aspect_ref -> evidence span substring.")
    winner: Optional[str] = Field(default=None, description="deprecated; unused")
    consensus: Optional[str] = Field(default=None, description="deprecated; use final_tuples")
    key_agreements: List[str] = Field(default_factory=list, description="deprecated")
    key_disagreements: List[str] = Field(default_factory=list, description="deprecated")
    rationale: str = Field(default="", description="optional CJ rationale")


class DebateOutput(BaseModel):
    topic: str = Field(default="")
    personas: Dict[str, DebatePersona] = Field(default_factory=dict)
    rounds: List[DebateRound] = Field(default_factory=list)
    summary: DebateSummary = Field(default_factory=DebateSummary)