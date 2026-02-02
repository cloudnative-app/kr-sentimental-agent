from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProcessTrace(BaseModel):
    """Trace item capturing intermediate agent outputs."""

    stage: str = Field(default="", description="Stage identifier, e.g., stage1 or stage2.")
    agent: str = Field(default="", description="Agent name.")
    uid: Optional[str] = Field(default=None, description="Example uid for trace alignment.")
    case_type: Optional[str] = Field(default=None, description="Case type bucket propagated from dataset.")
    split: Optional[str] = Field(default=None, description="Dataset split.")
    language_code: Optional[str] = Field(default=None, description="Language code propagated from dataset.")
    domain_id: Optional[str] = Field(default=None, description="Domain identifier propagated from dataset.")
    input_hash: Optional[str] = Field(default=None, description="SHA256 of the input text for integrity checks.")
    input_text: str = Field(default="", description="Input text provided to the agent.")
    output: Dict[str, Any] = Field(default_factory=dict, description="Raw output dict.")
    call_metadata: Optional[Dict[str, Any]] = Field(default=None, description="LLM call metadata (model, tokens, latency, retries).")
    stage_status: Optional[str] = Field(default=None, description="Optional status marker per stage (e.g., not_applicable).")
    notes: Optional[str] = Field(default=None, description="Optional notes or repair info.")
