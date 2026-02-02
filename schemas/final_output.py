from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .agent_outputs import ATEOutput, ATSAOutput, ModeratorOutput, ValidatorOutput, DebateOutput
from .metric_trace import ProcessTrace


class AnalysisFlags(BaseModel):
    correction_occurred: bool = Field(default=False, description="Stage2 corrected Stage1 polarity.")
    conflict_resolved: bool = Field(default=False, description="Conflicts were resolved into a single decision.")
    final_confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Representative confidence.")
    stage2_executed: bool = Field(
        default=True,
        description="Whether Stage2 was actually executed (baselines set this to False).",
    )


class FinalResult(BaseModel):
    label: str = Field(default="neutral", min_length=1, description="Final polarity label (sentence-level aggregate).")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score.")
    rationale: str = Field(default="", description="Summary rationale for the final decision.")
    final_aspects: List[Dict[str, Any]] = Field(default_factory=list, description="Final aspect_sentiments list (ABSA output).")


class FinalOutputSchema(BaseModel):
    """
    Canonical output structure. meta/process_trace/analysis_flags/final_result are always present (never None).
    If upstream data is missing, defaults provide empty dict/list/neutral values so model_dump() is stable.
    """

    model_config = {"validate_default": True}

    meta: Dict[str, Any] = Field(default_factory=dict, description="Request/trace metadata.")
    stage1_ate: Optional[ATEOutput] = None
    stage1_atsa: Optional[ATSAOutput] = None
    stage1_validator: Optional[ValidatorOutput] = None
    stage2_ate: Optional[ATEOutput] = None
    stage2_atsa: Optional[ATSAOutput] = None
    stage2_validator: Optional[ValidatorOutput] = None
    moderator: Optional[ModeratorOutput] = None
    debate: Optional[DebateOutput] = None
    process_trace: List[ProcessTrace] = Field(default_factory=list, description="Stage1/Validator/Stage2/Moderator traces.")
    analysis_flags: AnalysisFlags = Field(default_factory=AnalysisFlags, description="Always populated; empty defaults allowed.")
    final_result: FinalResult = Field(default_factory=FinalResult, description="Always populated; neutral defaults allowed.")
