from __future__ import annotations

import textwrap
from typing import Tuple

from schemas import BL2OutputSchema
from tools.llm_runner import run_structured, StructuredResultMeta
from tools.backbone_client import BackboneClient
from agents.prompts import load_prompt
from tools.prompt_spec import PromptSpec


def _load_bl1_system_prompt() -> str:
    """Load BL1 system prompt from agents/prompts/bl1.md; fall back to built-in."""
    try:
        return load_prompt("bl1")
    except FileNotFoundError:
        return DEFAULT_BL1_SYSTEM_PROMPT

DEFAULT_BL1_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are BL1 Free-form Sentiment Writer.
    Perform aspect-based sentiment analysis on the given text.
    Write a concise analysis of sentiment and aspects in free text. Be descriptive; structure is not required in this step.
    """
).strip()

# Resolve system prompt at import so BL1 can run even if prompt file is missing.
BL1_SYSTEM_PROMPT = _load_bl1_system_prompt()

BL1_PARSE_PROMPT = textwrap.dedent(
    """
    You are a parser. Convert the given free-form analysis into JSON matching the schema:
    - aspects: list of items with fields {{term: string, polarity: positive|negative|neutral, evidence: string, confidence: float, rationale: string, span: {{"start": int, "end": int}} or null}}

    Output MUST be valid JSON only. Do not omit keys; use null/""/[] for unknowns. Spans use character indices on the original user text.

    Free-form analysis to parse:
    {raw_text}
    """
).strip()


def run_bl1_to_bl2(
    backbone: BackboneClient,
    text: str,
    *,
    run_id: str,
    text_id: str,
    max_retries: int,
    errors_path: str,
    temperature: float | None = None,
    language_code: str = "unknown",
    domain_id: str = "unknown",
) -> Tuple[str, BL2OutputSchema, StructuredResultMeta]:
    """
    BL1 pipeline:
      1) Generate free-form analysis.
      2) Parse the analysis into BL2OutputSchema using run_structured (with repair).
    Returns (raw_text, parsed_model, parse_metadata).
    """
    raw_text = backbone.generate(
        [
            {"role": "system", "content": BL1_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=temperature,
        response_format="text",
        mode="bl1",
        text_id=text_id,
    )

    parse_prompt = BL1_PARSE_PROMPT.format(raw_text=raw_text)
    spec = PromptSpec(system=[parse_prompt], user=text, language_code=language_code, domain_id=domain_id)
    parsed_result = run_structured(
        backbone=backbone,
        system_prompt=parse_prompt,
        user_text=text,
        schema=BL2OutputSchema,
        max_retries=max_retries,
        run_id=run_id,
        text_id=text_id,
        stage="BL1_parse",
        mode="bl1",
        errors_path=errors_path,
        prompt_spec=spec,
    )
    parsed = parsed_result.model if parsed_result else BL2OutputSchema.model_construct()
    meta = parsed_result.meta if parsed_result else StructuredResultMeta()
    return raw_text, parsed, meta
