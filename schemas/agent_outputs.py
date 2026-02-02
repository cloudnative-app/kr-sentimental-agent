from __future__ import annotations

from typing import List, Optional, Dict, Any, Literal

from pydantic import BaseModel, Field


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


# ATSA
class OpinionTerm(BaseModel):
    term: str
    span: Span


class AspectSentimentItem(BaseModel):
    aspect_ref: str
    polarity: str = Field(default="neutral")
    opinion_term: Optional[OpinionTerm] = None
    evidence: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    polarity_distribution: Dict[str, float] = Field(default_factory=dict)
    is_implicit: bool = Field(default=False)


class SentimentReviewItem(BaseModel):
    aspect_ref: str
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


# Debate layer (cross-agent argumentation)
class DebatePersona(BaseModel):
    name: str = Field(default="")
    stance: str = Field(default="pro", description="pro|con|neutral")
    role: str = Field(default="", description="persona role description")
    style: str = Field(default="", description="tone/style guidance")
    goal: str = Field(default="", description="debate goal for this persona")


class DebateTurn(BaseModel):
    speaker: str = Field(default="", description="Persona name")
    stance: str = Field(default="pro", description="pro|con|neutral")
    planning: str = Field(default="", description="Plan before speaking")
    reflection: str = Field(default="", description="Self-check for logic/consistency")
    message: str = Field(default="", description="Final utterance delivered to the debate")
    key_points: List[str] = Field(default_factory=list, description="Atomic claims or rebuttals")


class DebateRound(BaseModel):
    round_index: int = Field(default=1, ge=1)
    turns: List[DebateTurn] = Field(default_factory=list)


class DebateSummary(BaseModel):
    winner: Optional[str] = Field(default=None, description="Winner persona name or None")
    consensus: Optional[str] = Field(default=None, description="Consensus statement if any")
    key_agreements: List[str] = Field(default_factory=list)
    key_disagreements: List[str] = Field(default_factory=list)
    rationale: str = Field(default="", description="Why this summary was chosen")


class DebateOutput(BaseModel):
    topic: str = Field(default="")
    personas: Dict[str, DebatePersona] = Field(default_factory=dict)
    rounds: List[DebateRound] = Field(default_factory=list)
    summary: DebateSummary = Field(default_factory=DebateSummary)