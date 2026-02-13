"""Conflict-review protocol: Stage1 perspective agents (P-NEG, P-IMP, P-LIT)."""

from __future__ import annotations

from typing import Optional

from schemas.protocol_conflict_review import PerspectiveASTEStage1Schema
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec, DemoExample
from agents.prompts import load_prompt


def _split_system_user(prompt_content: str) -> tuple[str, str]:
    """Split prompt by ---USER--- into system and user template."""
    if "---USER---" in prompt_content:
        parts = prompt_content.split("---USER---", 1)
        return parts[0].strip(), parts[1].strip()
    return prompt_content.strip(), "{text}"


class PerspectiveAgentPneg:
    """Agent A (P-NEG): negation/contrast specialist."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
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
    ) -> StructuredResult[PerspectiveASTEStage1Schema]:
        raw = load_prompt("perspective_pneg_stage1")
        system, user_tmpl = _split_system_user(raw)
        user_text = user_tmpl.replace("{text}", text)
        spec = PromptSpec(system=[system], user=user_text, demos=[DemoExample(text=d) for d in (demos or [])], language_code=language_code, domain_id=domain_id)
        return run_structured(
            backbone=self.backbone,
            system_prompt=system,
            user_text=user_text,
            schema=PerspectiveASTEStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="PerspectivePneg",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )


class PerspectiveAgentPimp:
    """Agent B (P-IMP): implicit aspect specialist."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
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
    ) -> StructuredResult[PerspectiveASTEStage1Schema]:
        raw = load_prompt("perspective_pimp_stage1")
        system, user_tmpl = _split_system_user(raw)
        user_text = user_tmpl.replace("{text}", text)
        spec = PromptSpec(system=[system], user=user_text, demos=[DemoExample(text=d) for d in (demos or [])], language_code=language_code, domain_id=domain_id)
        return run_structured(
            backbone=self.backbone,
            system_prompt=system,
            user_text=user_text,
            schema=PerspectiveASTEStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="PerspectivePimp",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )


class PerspectiveAgentPlit:
    """Agent C (P-LIT): literal/explicit evidence specialist."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
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
    ) -> StructuredResult[PerspectiveASTEStage1Schema]:
        raw = load_prompt("perspective_plit_stage1")
        system, user_tmpl = _split_system_user(raw)
        user_text = user_tmpl.replace("{text}", text)
        spec = PromptSpec(system=[system], user=user_text, demos=[DemoExample(text=d) for d in (demos or [])], language_code=language_code, domain_id=domain_id)
        return run_structured(
            backbone=self.backbone,
            system_prompt=system,
            user_text=user_text,
            schema=PerspectiveASTEStage1Schema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="PerspectivePlit",
            mode=mode,
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=spec,
        )
