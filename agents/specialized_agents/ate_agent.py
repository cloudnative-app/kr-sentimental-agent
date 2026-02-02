from __future__ import annotations

import sys

from schemas import ATEOutput, AspectExtractionStage1Schema, AspectExtractionStage2Schema
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec, DemoExample
from agents.prompts import load_prompt


class ATEAgent:
    """Aspect-agnostic sentiment agent (ATE)."""

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
    ) -> StructuredResult[AspectExtractionStage1Schema]:
        system_prompt = load_prompt("ate_stage1")
        print(f"[ATE DEBUG] stage1 text_id={text_id}, prompt_len={len(system_prompt)}", file=sys.stderr)
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
            schema=AspectExtractionStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="ATE",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )
        print(f"[ATE DEBUG] stage1 raw_response={result.meta.raw_response[:200]}", file=sys.stderr)
        return result

    def run_stage2(
        self,
        text: str,
        stage1_output: AspectExtractionStage1Schema,
        validator_output: object,
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        demos: list[str] | None = None,
        language_code: str = "unknown",
        domain_id: str = "unknown",
    ) -> StructuredResult[AspectExtractionStage2Schema]:
        system_prompt = load_prompt("ate_stage2") + f"\n\nStage1 JSON:\n{stage1_output.model_dump_json()}\nValidator JSON:\n{getattr(validator_output, 'model_dump_json', lambda: '')()}"
        print(f"[ATE DEBUG] stage2 text_id={text_id}, prompt_len={len(system_prompt)}", file=sys.stderr)
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
            schema=AspectExtractionStage2Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="ATE_reanalysis",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )
        print(f"[ATE DEBUG] stage2 raw_response={result.meta.raw_response[:200]}", file=sys.stderr)
        return result

    # Compatibility
    def run(self, text: str, *, run_id: str, text_id: str, mode: str = "proposed", language_code: str = "unknown", domain_id: str = "unknown") -> StructuredResult[AspectExtractionStage1Schema]:
        return self.run_stage1(text, run_id=run_id, text_id=text_id, mode=mode, language_code=language_code, domain_id=domain_id)
