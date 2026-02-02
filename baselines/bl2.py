from __future__ import annotations

from typing import Optional

from agents.prompts import load_prompt
from schemas.baselines import BL2OutputSchema
from tools.backbone_client import BackboneClient
from tools.llm_runner import StructuredResult, run_structured
from tools.prompt_spec import PromptSpec


def run_bl2_structured(
    *,
    backbone: BackboneClient,
    text: str,
    run_id: str,
    text_id: str,
    max_retries: int = 2,
    errors_path: Optional[str] = None,
    mode: str = "bl2",
    language_code: str = "unknown",
    domain_id: str = "unknown",
) -> StructuredResult[BL2OutputSchema]:
    """
    BL2 baseline: single structured prompt that emits BL2OutputSchema.
    """
    system_prompt = load_prompt("bl2")
    spec = PromptSpec(system=[system_prompt], user=text, language_code=language_code, domain_id=domain_id)
    return run_structured(
        backbone=backbone,
        system_prompt=system_prompt,
        user_text=text,
        schema=BL2OutputSchema,
        max_retries=max_retries,
        run_id=run_id,
        text_id=text_id,
        stage="BL2",
        mode=mode,
        errors_path=errors_path,
        prompt_spec=spec,
    )
