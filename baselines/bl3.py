from __future__ import annotations

from typing import List

from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from schemas import (
    AnalysisFlags,
    FinalOutputSchema,
    FinalResult,
    ProcessTrace,
    ATEOutput,
    ATSAOutput,
    ValidatorOutput,
)
from schemas.agent_outputs import AspectSentimentStage1Schema


def _aggregate_label_from_sentiments(atsa_output: AspectSentimentStage1Schema) -> ATEOutput:
    sentiments = getattr(atsa_output, "aspect_sentiments", None) or []
    if not sentiments:
        return ATEOutput(label="neutral", confidence=0.0, rationale="No sentiments detected.")
    best = max(sentiments, key=lambda s: s.confidence)
    pol = getattr(best, "polarity", None)
    rationale = best.evidence or ""
    if pol is None:
        rationale = (rationale + " [missing polarity]").strip()
        pol = "neutral"
    return ATEOutput(label=pol, confidence=best.confidence, rationale=rationale)


def _validator_summary(validator_output: object) -> ValidatorOutput:
    issues: List[str] = []
    confidence = 0.0
    suggested = None
    if hasattr(validator_output, "structural_risks"):
        for risk in validator_output.structural_risks:
            issues.append(risk.description or risk.type or "")
    if hasattr(validator_output, "consistency_score"):
        confidence = getattr(validator_output, "consistency_score", 0.0) or 0.0
    return ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=suggested, issues=issues, confidence=confidence)


def run_bl3_stage1_only(
    *,
    text: str,
    text_id: str,
    run_id: str,
    ate_agent: ATEAgent,
    atsa_agent: ATSAAgent,
    validator: ValidatorAgent,
    moderator: Moderator,
    language_code: str = "unknown",
    domain_id: str = "unknown",
) -> FinalOutputSchema:
    """
    BL3: run Stage1 only. Stage2 is marked not_applicable in process_trace and analysis_flags.
    """
    trace: List[ProcessTrace] = []

    ate_s1_result = ate_agent.run_stage1(text, run_id=run_id, text_id=text_id, mode="bl3", language_code=language_code, domain_id=domain_id)
    ate_s1 = ate_s1_result.model
    trace.append(ProcessTrace(stage="stage1", agent="ATE", input_text=text, output=ate_s1.model_dump(), notes=ate_s1_result.meta.to_notes_str()))

    atsa_s1_result = atsa_agent.run_stage1(text, run_id=run_id, text_id=text_id, mode="bl3", language_code=language_code, domain_id=domain_id)
    atsa_s1 = atsa_s1_result.model
    trace.append(ProcessTrace(stage="stage1", agent="ATSA", input_text=text, output=atsa_s1.model_dump(), notes=atsa_s1_result.meta.to_notes_str()))

    validator_s1_result = validator.run_stage1(text, run_id=run_id, text_id=text_id, mode="bl3", language_code=language_code, domain_id=domain_id)
    validator_s1 = validator_s1_result.model
    trace.append(ProcessTrace(stage="stage1", agent="Validator", input_text=text, output=validator_s1.model_dump(), notes=validator_s1_result.meta.to_notes_str()))

    # Explicit Stage2 status marker
    trace.append(
        ProcessTrace(
            stage="stage2",
            agent="status",
            input_text=text,
            output={"triplets": []},
            stage_status="not_applicable",
        )
    )

    agg_ate = _aggregate_label_from_sentiments(atsa_s1)
    stage1_atsa_out = ATSAOutput(target=None, label=agg_ate.label, confidence=agg_ate.confidence, rationale=agg_ate.rationale)
    validator_summary = _validator_summary(validator_s1)

    moderator_out = moderator.decide(
        stage1_ate=agg_ate,
        stage1_atsa=stage1_atsa_out,
        validator=validator_summary,
        stage2_ate=None,
        stage2_atsa=None,
    )
    trace.append(ProcessTrace(stage="moderator", agent="Moderator", input_text=text, output=moderator_out.model_dump()))

    flags = AnalysisFlags(
        correction_occurred=False,
        conflict_resolved=False,
        final_confidence_score=moderator_out.confidence,
        stage2_executed=False,
    )
    final_result = FinalResult(label=moderator_out.final_label, confidence=moderator_out.confidence, rationale=moderator_out.rationale)

    return FinalOutputSchema(
        meta={
            "mode": "bl3",
            "run_id": run_id,
            "text_id": text_id,
            "input_text": text,
            "language_code": language_code,
            "domain_id": domain_id,
        },
        stage1_ate=agg_ate,
        stage1_atsa=stage1_atsa_out,
        stage1_validator=validator_summary,
        stage2_ate=None,
        stage2_atsa=None,
        stage2_validator=None,
        moderator=moderator_out,
        process_trace=trace,
        analysis_flags=flags,
        final_result=final_result,
    )
