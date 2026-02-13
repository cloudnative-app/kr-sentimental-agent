"""Protocol conflict_review_v1: Perspective-specific ASTE + Review actions schema."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Span(BaseModel):
    """Standard span representation."""

    start: int = Field(ge=0, description="Start index inclusive.")
    end: int = Field(ge=0, description="End index exclusive.")


class ASTETripletItem(BaseModel):
    """Single aspect-sentiment triplet from perspective agent (P-NEG/P-IMP/P-LIT)."""

    aspect_term: str = Field(default="", description="Required aspect surface form.")
    aspect_ref: Optional[str] = Field(default=None, description="Optional normalized aspect ref.")
    polarity: str = Field(default="neutral", description="positive|negative|neutral|mixed")
    opinion_term: Optional[str] = Field(default=None)
    evidence: Optional[str] = Field(default=None)
    span: Optional[Dict[str, int]] = Field(default=None, description="Optional {start, end}.")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rationale: Optional[str] = Field(default=None)

    @field_validator("span", mode="before")
    @classmethod
    def normalize_span(cls, v: Any) -> Any:
        """
        Fail-soft span normalization:
        - dict -> keep (validated)
        - (list|tuple)[2] -> dict
        - str -> parse if "start,end" / "start-end" / "start:.. end:.." else None
        - others -> None (무해화)
        - invalid ranges -> None
        """
        if v is None:
            return None

        # dict-like
        if isinstance(v, dict):
            start = v.get("start")
            end = v.get("end")
            try:
                start_i = int(start)
                end_i = int(end)
            except (TypeError, ValueError):
                return None
            if start_i < 0 or end_i < 0 or start_i > end_i:
                return None
            return {"start": start_i, "end": end_i}

        # list/tuple (start, end)
        if isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                start_i = int(v[0])
                end_i = int(v[1])
            except (TypeError, ValueError):
                return None
            if start_i < 0 or end_i < 0 or start_i > end_i:
                return None
            return {"start": start_i, "end": end_i}

        # string patterns
        if isinstance(v, str):
            s = v.strip()
            # pattern: "12,18" or "12-18" or "12~18"
            m = re.match(r"^\s*(\d+)\s*[,~-]\s*(\d+)\s*$", s)
            if m:
                start_i = int(m.group(1))
                end_i = int(m.group(2))
                if start_i < 0 or end_i < 0 or start_i > end_i:
                    return None
                return {"start": start_i, "end": end_i}
            # pattern: "start:12 end:18" (loose)
            m2 = re.search(r"start\s*[:=]\s*(\d+)", s, re.IGNORECASE)
            m3 = re.search(r"end\s*[:=]\s*(\d+)", s, re.IGNORECASE)
            if m2 and m3:
                start_i = int(m2.group(1))
                end_i = int(m3.group(1))
                if start_i < 0 or end_i < 0 or start_i > end_i:
                    return None
                return {"start": start_i, "end": end_i}
            # unknown / garbled string -> None (무해화)
            return None

        # any other type -> None
        return None


class PerspectiveASTEStage1Schema(BaseModel):
    """Stage1 output schema for P-NEG, P-IMP, P-LIT agents."""

    triplets: List[ASTETripletItem] = Field(default_factory=list)


# Review action types
REVIEW_ACTION_TYPES = frozenset({"DROP", "MERGE", "FLIP", "KEEP", "FLAG"})
REASON_CODES = frozenset({
    "NEGATION_SCOPE",
    "CONTRAST_CLAUSE",
    "IMPLICIT_ASPECT",
    "ASPECT_REF_MISMATCH",
    "SPAN_OVERLAP_MERGE",
    "DUPLICATE_TUPLE",
    "WEAK_EVIDENCE",
    "POLARITY_UNCERTAIN",
    "FORMAT_INCOMPLETE",
    "KEEP_BEST_SUPPORTED",
    # Extended (validation consistency)
    "WEAK_INFERENCE",
    "EXPLICIT_NOT_REQUIRED",
    "STRUCTURAL_INCONSISTENT",
})


class ReviewActionItem(BaseModel):
    """Single review action from Agent A/B/C or Arbiter."""

    action_type: str = Field(default="KEEP", description="DROP|MERGE|FLIP|KEEP|FLAG")
    target_tuple_ids: List[str] = Field(default_factory=list)
    new_value: Optional[Dict[str, Any]] = Field(default=None)
    reason_code: str = Field(default="")
    actor: str = Field(default="", description="A|B|C|ARB")


class ReviewOutputSchema(BaseModel):
    """Review output: merged actions from A/B/C or Arbiter final."""

    review_actions: List[ReviewActionItem] = Field(default_factory=list)
