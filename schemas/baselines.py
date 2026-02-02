from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .agent_outputs import Span


class BL2Aspect(BaseModel):
    term: str = Field(default="")
    polarity: str = Field(default="neutral")
    evidence: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="")
    span: Optional[Span] = None


class BL2OutputSchema(BaseModel):
    aspects: List[BL2Aspect] = Field(default_factory=list)


# BL1 structured output uses the same schema as BL2 after parsing the free-form text.
BL1OutputSchema = BL2OutputSchema
