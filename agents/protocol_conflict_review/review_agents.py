"""Conflict-review protocol: Review agents (A, B, C) and Arbiter."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from schemas.protocol_conflict_review import ReviewOutputSchema
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec, DemoExample
from agents.prompts import load_prompt


def _split_system_user(prompt_content: str) -> tuple[str, str]:
    if "---USER---" in prompt_content:
        parts = prompt_content.split("---USER---", 1)
        return parts[0].strip(), parts[1].strip()
    return prompt_content.strip(), ""


def _run_review(
    backbone: BackboneClient,
    prompt_name: str,
    stage_name: str,
    text: str,
    candidates: List[Dict[str, Any]],
    conflict_flags: List[Dict[str, Any]],
    validator_risks: List[Dict[str, Any]],
    *,
    run_id: str,
    text_id: str,
    mode: str = "proposed",
    actions_a: Optional[List[Dict[str, Any]]] = None,
    actions_b: Optional[List[Dict[str, Any]]] = None,
    actions_c: Optional[List[Dict[str, Any]]] = None,
    memory_context: str = "",
) -> StructuredResult[ReviewOutputSchema]:
    raw = load_prompt(prompt_name)
    system, user_tmpl = _split_system_user(raw)
    candidates_json = json.dumps(candidates, ensure_ascii=False)
    conflict_flags_json = json.dumps(conflict_flags, ensure_ascii=False)
    validator_risks_json = json.dumps(validator_risks, ensure_ascii=False)
    kwargs: Dict[str, Any] = {
        "text": text,
        "candidates_json": candidates_json,
        "conflict_flags_json": conflict_flags_json,
        "validator_risks_json": validator_risks_json,
        "memory_context": memory_context or "",
    }
    if actions_a is not None:
        kwargs["actions_A_json"] = json.dumps(actions_a, ensure_ascii=False)
    if actions_b is not None:
        kwargs["actions_B_json"] = json.dumps(actions_b, ensure_ascii=False)
    if actions_c is not None:
        kwargs["actions_C_json"] = json.dumps(actions_c, ensure_ascii=False)
    user_text = user_tmpl
    for k, v in kwargs.items():
        user_text = user_text.replace("{" + k + "}", str(v))
    spec = PromptSpec(system=[system], user=user_text)
    return run_structured(
        backbone=backbone,
        system_prompt=system,
        user_text=user_text,
        schema=ReviewOutputSchema,
        max_retries=2,
        run_id=run_id,
        text_id=text_id,
        stage=stage_name,
        mode=mode,
        use_mock=(getattr(backbone, "provider", "mock") == "mock"),
        prompt_spec=spec,
    )


class ReviewAgentA:
    """Agent A (P-NEG) as reviewer."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
        self.backbone = backbone or BackboneClient()

    def run(
        self,
        text: str,
        candidates: List[Dict[str, Any]],
        conflict_flags: List[Dict[str, Any]],
        validator_risks: List[Dict[str, Any]],
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        memory_context: str = "",
    ) -> StructuredResult[ReviewOutputSchema]:
        return _run_review(
            self.backbone,
            "review_pneg_action",
            "ReviewAgentA",
            text,
            candidates,
            conflict_flags,
            validator_risks,
            run_id=run_id,
            text_id=text_id,
            mode=mode,
            memory_context=memory_context,
        )


class ReviewAgentB:
    """Agent B (P-IMP) as reviewer."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
        self.backbone = backbone or BackboneClient()

    def run(
        self,
        text: str,
        candidates: List[Dict[str, Any]],
        conflict_flags: List[Dict[str, Any]],
        validator_risks: List[Dict[str, Any]],
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        memory_context: str = "",
    ) -> StructuredResult[ReviewOutputSchema]:
        return _run_review(
            self.backbone,
            "review_pimp_action",
            "ReviewAgentB",
            text,
            candidates,
            conflict_flags,
            validator_risks,
            run_id=run_id,
            text_id=text_id,
            mode=mode,
            memory_context=memory_context,
        )


class ReviewAgentC:
    """Agent C (P-LIT) as reviewer."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
        self.backbone = backbone or BackboneClient()

    def run(
        self,
        text: str,
        candidates: List[Dict[str, Any]],
        conflict_flags: List[Dict[str, Any]],
        validator_risks: List[Dict[str, Any]],
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        memory_context: str = "",
    ) -> StructuredResult[ReviewOutputSchema]:
        return _run_review(
            self.backbone,
            "review_plit_action",
            "ReviewAgentC",
            text,
            candidates,
            conflict_flags,
            validator_risks,
            run_id=run_id,
            text_id=text_id,
            mode=mode,
            memory_context=memory_context,
        )


class ReviewAgentArbiter:
    """Arbiter: merge A/B/C actions into final list."""

    def __init__(self, backbone: Optional[BackboneClient] = None):
        self.backbone = backbone or BackboneClient()

    def run(
        self,
        text: str,
        candidates: List[Dict[str, Any]],
        conflict_flags: List[Dict[str, Any]],
        validator_risks: List[Dict[str, Any]],
        actions_a: List[Dict[str, Any]],
        actions_b: List[Dict[str, Any]],
        actions_c: List[Dict[str, Any]],
        *,
        run_id: str,
        text_id: str,
        mode: str = "proposed",
        memory_context: str = "",
    ) -> StructuredResult[ReviewOutputSchema]:
        return _run_review(
            self.backbone,
            "review_arbiter_action",
            "ReviewArbiter",
            text,
            candidates,
            conflict_flags,
            validator_risks,
            run_id=run_id,
            text_id=text_id,
            mode=mode,
            actions_a=actions_a,
            actions_b=actions_b,
            actions_c=actions_c,
            memory_context=memory_context,
        )
