from __future__ import annotations

from typing import Dict, Optional

from baseline_wrappers.bl1_wrapper import run_bl1_wrapped
from baselines.bl2 import run_bl2_structured
from baselines.bl3 import run_bl3_stage1_only
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
from schemas.baselines import BL2OutputSchema
from schemas.agent_outputs import AspectSentimentStage1Schema, AspectSentimentStage2Schema
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample
from tools.llm_runner import run_structured, default_errors_path


class BaselineRunner:
    """
    Baseline modes:
      bl1: Free-text backbone call -> heuristic polarity -> wrap into FinalOutputSchema (stage2_executed=False).
      bl2: Single structured prompt -> BL2OutputSchema -> wrap into FinalOutputSchema (stage2_executed=False).
      bl3: Stage1 ATE/ATSA/Validator only -> moderator -> FinalOutputSchema (stage2_executed=False).
    """

    def __init__(self, mode: str, backbone: Optional[BackboneClient] = None, config: Optional[Dict] = None, run_id: str = "run"):
        if mode not in {"bl1", "bl2", "bl3"}:
            raise ValueError(f"Unsupported baseline mode '{mode}'")
        self.mode = mode
        self.backbone = backbone or BackboneClient()
        self.config = config or {}
        self.run_id = run_id
        self.max_retries = self.config.get("max_retries", 2)
        default_errors = default_errors_path(self.run_id, self.mode)
        self.errors_path = self.config.get("errors_path") or default_errors
        self.temperature = self.config.get("temperature", 0.0)

        if self.mode == "bl3":
            self.ate_agent = ATEAgent(self.backbone)
            self.atsa_agent = ATSAAgent(self.backbone)
            self.validator = ValidatorAgent(self.backbone)
            self.moderator = Moderator()

    # --------- Helpers ---------
    def _aggregate_label_from_sentiments(self, atsa_output: AspectSentimentStage1Schema | AspectSentimentStage2Schema) -> ATEOutput:
        sentiments = getattr(atsa_output, "aspect_sentiments", None) or []
        if not sentiments:
            return ATEOutput(label="neutral", confidence=0.0, rationale="No sentiments detected.")
        best = max(sentiments, key=lambda s: s.confidence)
        return ATEOutput(label=best.polarity, confidence=best.confidence, rationale=best.evidence or "")

    def _validator_summary(self, validator_output: object) -> ValidatorOutput:
        issues = []
        confidence = 0.0
        suggested = None
        if hasattr(validator_output, "structural_risks"):
            for risk in validator_output.structural_risks:
                issues.append(risk.description or risk.type or "")
        if hasattr(validator_output, "consistency_score"):
            confidence = getattr(validator_output, "consistency_score", 0.0) or 0.0
        return ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=suggested, issues=issues, confidence=confidence)

    def _build_flags(self, confidence: float) -> AnalysisFlags:
        return AnalysisFlags(
            correction_occurred=False,
            conflict_resolved=False,
            final_confidence_score=confidence,
            stage2_executed=False,
        )

    # --------- Modes ---------
    def _run_bl1(self, text: str, text_id: str, *, language_code: str = "unknown", domain_id: str = "unknown") -> FinalOutputSchema:
        _, fos = run_bl1_wrapped(
            backbone=self.backbone,
            text=text,
            text_id=text_id,
            run_id=self.run_id,
            max_retries=self.max_retries,
            errors_path=self.errors_path,
            temperature=self.temperature,
            language_code=language_code,
            domain_id=domain_id,
        )
        return fos

    def _run_bl2(self, text: str, text_id: str, *, language_code: str = "unknown", domain_id: str = "unknown") -> FinalOutputSchema:
        bl2_result = run_bl2_structured(
            backbone=self.backbone,
            text=text,
            run_id=self.run_id,
            text_id=text_id,
            max_retries=self.max_retries,
            errors_path=self.errors_path,
            mode="bl2",
            language_code=language_code,
            domain_id=domain_id,
        )
        bl2_output = bl2_result.model

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
            ProcessTrace(
                stage="baseline",
                agent="BL2",
                input_text=text,
                output=bl2_output.model_dump() if bl2_output else {"error": "parsing_failed"},
                notes=bl2_result.meta.to_notes_str(),
            )
        ]

        return FinalOutputSchema(
            meta={"mode": "bl2", "run_id": self.run_id, "text_id": text_id, "input_text": text},
            stage1_ate=ate,
            stage1_atsa=atsa,
            stage1_validator=validator,
            stage2_ate=None,
            stage2_atsa=None,
            stage2_validator=None,
            moderator=None,
            process_trace=trace,
            analysis_flags=self._build_flags(confidence=conf),
            final_result=final_result,
        )

    def _run_bl3(self, text: str, text_id: str, *, language_code: str = "unknown", domain_id: str = "unknown") -> FinalOutputSchema:
        return run_bl3_stage1_only(
            text=text,
            text_id=text_id,
            run_id=self.run_id,
            ate_agent=self.ate_agent,
            atsa_agent=self.atsa_agent,
            validator=self.validator,
            moderator=self.moderator,
            language_code=language_code,
            domain_id=domain_id,
        )

    # --------- Public ---------
    def run(self, example: InternalExample | str) -> FinalOutputSchema:
        if isinstance(example, str):
            example = InternalExample(uid="text", text=example)
        text = example.text
        text_id = getattr(example, "uid", "text") or "text"
        case_type = getattr(example, "case_type", None) or "unknown"
        split = getattr(example, "split", None) or "unknown"
        language_code = getattr(example, "language_code", None) or "unknown"
        domain_id = getattr(example, "domain_id", None) or "unknown"
        if self.mode == "bl1":
            result = self._run_bl1(text, text_id, language_code=language_code, domain_id=domain_id)
        if self.mode == "bl2":
            result = self._run_bl2(text, text_id, language_code=language_code, domain_id=domain_id)
        else:
            result = self._run_bl3(text, text_id, language_code=language_code, domain_id=domain_id)

        # Attach dataset context for traceability
        result.meta = {
            **(result.meta or {}),
            "case_type": case_type,
            "split": split,
            "uid": text_id,
            "language_code": language_code,
            "domain_id": domain_id,
        }
        for tr in getattr(result, "process_trace", []) or []:
            tr.case_type = case_type
            tr.split = split
            tr.uid = text_id
            tr.language_code = language_code
            tr.domain_id = domain_id
        return result
