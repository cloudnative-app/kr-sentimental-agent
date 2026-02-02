from __future__ import annotations

from typing import Tuple

from baselines.bl1 import run_bl1_to_bl2
from schemas import FinalOutputSchema, ATEOutput, ATSAOutput, ValidatorOutput, FinalResult, AnalysisFlags
from schemas.baselines import BL2OutputSchema
from tools.backbone_client import BackboneClient
from schemas.metric_trace import ProcessTrace


def run_bl1_wrapped(
    backbone: BackboneClient,
    text: str,
    text_id: str,
    *,
    run_id: str,
    max_retries: int,
    errors_path: str,
    temperature: float | None = None,
    language_code: str = "unknown",
    domain_id: str = "unknown",
) -> Tuple[str, FinalOutputSchema]:
    """
    Run BL1 free-text + parse into BL2 schema, then wrap into FinalOutputSchema.
    """
    raw_text, bl2_output, parse_meta = run_bl1_to_bl2(
        backbone=backbone,
        text=text,
        run_id=run_id,
        text_id=text_id,
        max_retries=max_retries,
        errors_path=errors_path,
        temperature=temperature,
        language_code=language_code,
        domain_id=domain_id,
    )

    aspects = bl2_output.aspects if bl2_output else []
    if aspects:
        best = max(aspects, key=lambda a: a.confidence)
        label = best.polarity
        conf = best.confidence
        rationale = best.evidence or best.rationale
    else:
        label, conf, rationale = "neutral", 0.0, "No aspects parsed."

    ate = ATEOutput(label=label, confidence=conf, rationale=rationale)
    atsa = ATSAOutput(
        target=aspects[0].term if aspects else None,
        label=label,
        confidence=conf,
        rationale=rationale,
        span=aspects[0].span if aspects and aspects[0].span else None,
    )
    validator = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, confidence=conf)

    final_result = FinalResult(label=label, confidence=conf, rationale=rationale)
    trace = [
        ProcessTrace(stage="baseline_raw", agent="BL1", input_text=text, output={"raw_text": raw_text}),
        ProcessTrace(
            stage="baseline_parse",
            agent="BL1_parser",
            input_text=text,
            output=bl2_output.model_dump() if isinstance(bl2_output, BL2OutputSchema) else {"error": "parsing_failed"},
            notes=parse_meta.to_notes_str(),
        ),
    ]

    flags = AnalysisFlags(
        correction_occurred=False,
        conflict_resolved=False,
        final_confidence_score=conf,
        stage2_executed=False,
    )

    fos = FinalOutputSchema(
        meta={"mode": "bl1", "run_id": run_id, "text_id": text_id, "input_text": text},
        stage1_ate=ate,
        stage1_atsa=atsa,
        stage1_validator=validator,
        stage2_ate=None,
        stage2_atsa=None,
        stage2_validator=None,
        moderator=None,
        process_trace=trace,
        analysis_flags=flags,
        final_result=final_result,
    )
    return raw_text, fos
