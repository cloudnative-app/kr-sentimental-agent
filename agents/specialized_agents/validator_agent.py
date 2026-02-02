from __future__ import annotations

from typing import Iterable

from schemas import (
    ATEOutput,
    ATSAOutput,
    StructuralValidatorStage1Schema,
    StructuralValidatorStage2Schema,
    ValidatorOutput,
)
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec, DemoExample
from agents.prompts import load_prompt


class ValidatorAgent:
    """Consistency checker between ATE and ATSA outputs."""

    NEGATION_TRIGGERS: tuple[str, ...] = (
        "안",
        "못",
        "않",
        "없",
        "아니",
        "지 않",
        "지못",
        "지 못",
        "지않",
        "별로 안",
        "전혀 안",
    )

    def __init__(self, backbone: BackboneClient | None = None):
        self.backbone = backbone or BackboneClient()

    @classmethod
    def _contains_negation_trigger(cls, text: str, *, language_code: str = "unknown", triggers: Iterable[str] | None = None) -> bool:
        from tools.pattern_loader import load_patterns

        haystack = text.lower()
        if triggers is None:
            patterns, _, _ = load_patterns(language_code)
            triggers = patterns.get("negation_triggers") or cls.NEGATION_TRIGGERS
        for trig in triggers:
            if trig and str(trig).lower() in haystack:
                return True
        return False

    def _apply_negation_gate(self, text: str, result: StructuredResult[StructuralValidatorStage1Schema], *, language_code: str) -> StructuredResult[StructuralValidatorStage1Schema]:
        """
        If input text lacks negation triggers, drop NEGATION structural risks
        and FLIP_POLARITY proposals to avoid hallucinated negation flags.
        """
        has_trigger = self._contains_negation_trigger(text, language_code=language_code)
        if has_trigger:
            return result

        # Filter structural_risks
        risks = getattr(result.model, "structural_risks", [])
        filtered_risks = [r for r in risks if getattr(r, "type", "").upper() != "NEGATION"]
        result.model.structural_risks = filtered_risks

        # Filter correction_proposals
        proposals = getattr(result.model, "correction_proposals", [])
        filtered_props = [p for p in proposals if getattr(p, "proposal_type", "").upper() != "FLIP_POLARITY"]
        result.model.correction_proposals = filtered_props

        # Optional: record suppression in meta.error for transparency
        note = "negation_suppressed"
        result.meta.error = f"{result.meta.error};{note}" if result.meta.error else note
        return result

    def run_stage1(
        self,
        text: str,
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        demos: list[str] | None = None,
        language_code: str = "unknown",
        domain_id: str = "unknown",
    ) -> StructuredResult[StructuralValidatorStage1Schema]:
        system_prompt = load_prompt("validator_stage1")
        spec = PromptSpec(
            system=[system_prompt],
            user=text,
            demos=[DemoExample(text=d) for d in (demos or [])],
            language_code=language_code,
            domain_id=domain_id,
        )
        result = run_structured(
            backbone=self.backbone,
            system_prompt=system_prompt,
            user_text=text,
            schema=StructuralValidatorStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="Validator",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )
        return self._apply_negation_gate(text, result, language_code=language_code)

    def run_stage2(
        self,
        text: str,
        stage1_output: StructuralValidatorStage1Schema,
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        demos: list[str] | None = None,
        language_code: str = "unknown",
        domain_id: str = "unknown",
    ) -> StructuredResult[StructuralValidatorStage2Schema]:
        prompt = load_prompt("validator_stage2") + f"\n\nStage1 JSON:\n{stage1_output.model_dump_json()}"
        spec = PromptSpec(
            system=[prompt],
            user=text,
            demos=[DemoExample(text=d) for d in (demos or [])],
            language_code=language_code,
            domain_id=domain_id,
        )
        return run_structured(
            backbone=self.backbone,
            system_prompt=prompt,
            user_text=text,
            schema=StructuralValidatorStage2Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="Validator_reanalysis",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )

    # Compatibility with previous interface
    def run(self, text: str, ate: ATEOutput = None, atsa: ATSAOutput = None, *, run_id: str, text_id: str, run_mode: str = "stage1", mode: str = "proposed", language_code: str = "unknown", domain_id: str = "unknown"):
        if run_mode == "stage2":
            if ate is None or atsa is None:
                raise ValueError("Stage2 requires stage1 outputs for context.")
            # For stage2 compatibility, wrap stage1 validator as empty
            return self.run_stage2(
                text,
                self.run_stage1(text, run_id=run_id, text_id=text_id, mode=mode, language_code=language_code, domain_id=domain_id).model,
                run_id=run_id,
                text_id=text_id,
                mode=mode,
                language_code=language_code,
                domain_id=domain_id,
            )
        return self.run_stage1(text, run_id=run_id, text_id=text_id, mode=mode, language_code=language_code, domain_id=domain_id)
