from __future__ import annotations

from schemas import ATSAOutput, AspectSentimentStage1Schema, AspectSentimentStage2Schema
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec, DemoExample
from agents.prompts import load_prompt


class ATSAAgent:
    """Aspect/target-specific sentiment agent (ATSA)."""

    def __init__(self, backbone: BackboneClient | None = None):
        self.backbone = backbone or BackboneClient()

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
    ) -> StructuredResult[AspectSentimentStage1Schema]:
        system_prompt = load_prompt("atsa_stage1")
        spec = PromptSpec(
            system=[system_prompt],
            user=text,
            demos=[DemoExample(text=d) for d in (demos or [])],
            language_code=language_code,
            domain_id=domain_id,
        )
        return run_structured(
            backbone=self.backbone,
            system_prompt=system_prompt,
            user_text=text,
            schema=AspectSentimentStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="ATSA",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )

    def run_stage2(
        self,
        text: str,
        stage1_output: AspectSentimentStage1Schema,
        validator_output: object,
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        demos: list[str] | None = None,
        language_code: str = "unknown",
        domain_id: str = "unknown",
        extra_context: str | None = None,
    ) -> StructuredResult[AspectSentimentStage2Schema]:
        extra_instruction = "\nInstruction: Output aspect_term (term + span) for the aspect surface form from the sentence; use ATE term/span when applicable."
        system_prompt = (
            load_prompt("atsa_stage2")
            + extra_instruction
            + f"\n\nStage1 JSON:\n{stage1_output.model_dump_json()}\nValidator JSON:\n{getattr(validator_output, 'model_dump_json', lambda: '')()}"
        )
        if extra_context:
            system_prompt += f"\n\nDebate Review Context JSON:\n{extra_context}"
        spec = PromptSpec(
            system=[system_prompt],
            user=text,
            demos=[DemoExample(text=d) for d in (demos or [])],
            language_code=language_code,
            domain_id=domain_id,
        )
        return run_structured(
            backbone=self.backbone,
            system_prompt=system_prompt,
            user_text=text,
            schema=AspectSentimentStage2Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="ATSA_reanalysis",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )

    def run(self, text: str, *, run_id: str, text_id: str, mode: str = "proposed", language_code: str = "unknown", domain_id: str = "unknown") -> StructuredResult[AspectSentimentStage1Schema]:
        return self.run_stage1(text, run_id=run_id, text_id=text_id, mode=mode, language_code=language_code, domain_id=domain_id)
