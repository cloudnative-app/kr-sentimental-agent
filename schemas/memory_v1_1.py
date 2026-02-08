"""
Memory v1.1 schemas — EpisodicMemoryEntry, Advisory, AdvisoryBundle, CaseTrace.
공통: raw_text/gold/CoT 저장 금지. schema_version "1.1" 고정.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ---------- EpisodicMemoryEntry v1.1 ----------
class InputSignatureV1_1(BaseModel):
    language: str = Field(..., description="ko | en | other")
    detected_structure: List[str] = Field(..., description="negation, contrast, irony, none")
    contrast_marker: Optional[str] = None
    has_negation: Optional[bool] = None
    num_aspects: int = Field(..., ge=0)
    length_bucket: str = Field(..., description="short | medium | long")


class CaseSummaryV1_1(BaseModel):
    target_aspect_type: str = ""
    symptom: str = ""
    rationale_summary: str = Field(..., max_length=500)


class StageSnapshotV1_1(BaseModel):
    aspects_norm: List[str] = Field(default_factory=list)
    polarities: Dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class RiskVectorV1_1(BaseModel):
    severity_sum: float = Field(0.0, ge=0.0)
    tags: List[str] = Field(default_factory=list)


class CorrectionV1_1(BaseModel):
    corrective_principle: str = Field(..., max_length=400)
    applicable_conditions: List[str] = Field(..., min_length=1)
    principle_id: Optional[str] = None
    anti_pattern: Optional[str] = Field(None, max_length=200)


class EvaluationV1_1(BaseModel):
    risk_before: RiskVectorV1_1
    risk_after: RiskVectorV1_1
    override_applied: bool = False
    override_success: bool = False
    override_harm: bool = False


class ProvenanceV1_1(BaseModel):
    created_from_split: str = ""
    used_in_eval: bool = False
    timestamp: str = ""
    version: str = ""
    has_gold: bool = False


class StageSnapshotPairV1_1(BaseModel):
    stage1: StageSnapshotV1_1
    final: StageSnapshotV1_1


class EpisodicMemoryEntryV1_1(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    episode_id: str = Field(..., pattern=r"^epi_[0-9]{6,}$")
    episode_type: str = Field(..., pattern="^(success|harm|neutral)$")
    error_category: List[str] = Field(..., min_length=1)
    input_signature: InputSignatureV1_1
    case_summary: CaseSummaryV1_1
    stage_snapshot: StageSnapshotPairV1_1
    correction: CorrectionV1_1
    evaluation: EvaluationV1_1
    provenance: ProvenanceV1_1

    def model_dump_for_store(self) -> Dict[str, Any]:
        """Export for store; must not contain raw_text."""
        return self.model_dump(exclude_none=False)


# ---------- Advisory v1.1 ----------
# Anchor: evidence에는 consistency/variance/n(stats) 중심. mode_decision 노출 금지.
# Successful/Failed: evidence에는 risk_before_tags, risk_after_tags, principle_id. accuracy/gold 문구 금지.
class EvidenceV1_1(BaseModel):
    source_episode_ids: List[str] = Field(default_factory=list)
    risk_tags: List[str] = Field(default_factory=list)
    principle_id: str = ""
    risk_before_tags: List[str] = Field(default_factory=list, description="Successful/Failed용; gold/accuracy 없음")
    risk_after_tags: List[str] = Field(default_factory=list, description="Successful/Failed용; gold/accuracy 없음")
    stats: Optional[Dict[str, Any]] = Field(default=None, description="Anchor용: historical_count, consistency_score, variance 만")


class AdvisoryConstraintsV1_1(BaseModel):
    no_label_hint: Literal[True] = True
    no_forcing: Literal[True] = True
    no_confidence_boost: Literal[True] = True


class AdvisoryV1_1(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    advisory_id: str = Field(..., pattern=r"^adv_[0-9]{6,}$")
    advisory_type: str = Field(
        ...,
        pattern="^(successful_override|failed_override_warning|consistency_anchor)$",
    )
    message: str = Field(..., max_length=800)
    strength: str = Field(..., pattern="^(weak|moderate|strong)$")
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    evidence: EvidenceV1_1
    constraints: AdvisoryConstraintsV1_1 = Field(default_factory=AdvisoryConstraintsV1_1)


# ---------- Retrieval v1.1 (CaseTrace 최소 필드: decision.correct 없이 follow/ignored 판정) ----------
class RetrievalV1_1(BaseModel):
    k: int = Field(0, ge=0, description="requested top-k")
    hit: bool = False
    returned_ids: List[str] = Field(default_factory=list, description="advisory_id list returned")


# ---------- AdvisoryBundle v1.1 (DEBATE_CONTEXT__MEMORY slot) ----------
class AdvisoryBundleMetaV1_1(BaseModel):
    memory_mode: str = Field(..., pattern="^(off|on|silent)$")
    topk: int = Field(0, ge=0, le=3)
    masked_injection: bool = False
    retrieval_executed: bool = False


class AdvisoryBundleV1_1(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    memory_on: bool = False
    retrieved: List[AdvisoryV1_1] = Field(default_factory=list, max_length=3)
    warnings: List[str] = Field(default_factory=list, max_length=5)
    meta: AdvisoryBundleMetaV1_1


# ---------- CaseTrace v1.1 (실험 로그/분석용) ----------
class RunMetaV1_1(BaseModel):
    run_id: str = ""
    condition: str = Field(..., pattern="^(C1|C2|C2_silent)$")
    seed: int = 0
    timestamp: str = ""
    memory_mode: Optional[str] = Field(None, description="off|on|silent; token/round 동일성 점검용")


class DebateLogEntryV1_1(BaseModel):
    round: int = Field(..., ge=1)
    speaker: str = ""
    stance: str = Field(..., pattern="^(pro|con|neutral)$")
    message: str = Field(..., max_length=600)
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class RiskV1_1(BaseModel):
    flagged: bool = False
    residual: bool = False
    severity_before: float = Field(0.0, ge=0.0)
    severity_after: float = Field(0.0, ge=0.0)
    tags_before: List[str] = Field(default_factory=list)
    tags_after: List[str] = Field(default_factory=list)


class OverrideChangeV1_1(BaseModel):
    change_id: str = ""
    reasoning: str = Field(..., max_length=400)


class OverrideV1_1(BaseModel):
    eligible: bool = False
    applied: bool = False
    success: bool = False
    harm: bool = False
    accepted_changes: List[OverrideChangeV1_1] = Field(default_factory=list)
    rejected_changes: List[OverrideChangeV1_1] = Field(default_factory=list)


class RiskTagMappingV1_1(BaseModel):
    risk_tag: str = ""
    principle_id: str = ""


class CoverageV1_1(BaseModel):
    risk_tag_to_principle_mapped: List[RiskTagMappingV1_1] = Field(default_factory=list)
    mapping_coverage_hit: bool = False


class CaseTraceV1_1(BaseModel):
    """RQ1~RQ3 계산용 최소 증거. 원문/CoT/골드 직접 저장 금지. memory_mode, risk_before/after, retrieval, advisories_present, accepted/rejected(reasoning 필수)."""
    schema_version: Literal["1.1"] = "1.1"
    run_meta: RunMetaV1_1
    case_id: str = ""
    sample_index: Optional[int] = Field(None, description="Sample processing order (0-based); for memory growth analysis")
    input_signature: InputSignatureV1_1
    stage1_output: StageSnapshotV1_1
    debate_log: List[DebateLogEntryV1_1] = Field(default_factory=list)
    memory_bundle: AdvisoryBundleV1_1
    retrieval: Optional[RetrievalV1_1] = Field(None, description="k, hit, returned_ids[]; MemoryImpactAnalysis용")
    final_output: StageSnapshotV1_1
    risk: RiskV1_1
    override: OverrideV1_1
    coverage: CoverageV1_1
