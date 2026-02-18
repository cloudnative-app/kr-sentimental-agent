"""
Normalization SSOT: Tier1+Tier2 strict only.

Policy (P2):
- Tier1+Tier2(strict): gold / LLM parsing / eval 전 경로에 공통 적용
- Tier3(flexible/edit-distance): 기본 OFF, ablation에서만 ON

이 모듈은 평가·골드·집계에 사용하는 정규화만 제공.
canonicalize_polarity_with_repair(edit-distance)는 파싱 복구용으로만 사용, 이 모듈에서 호출하지 않음.
"""

from __future__ import annotations

import re
from typing import Optional

# Tier1+Tier2: whitelist only, no edit-distance
_POLARITY_MAP = {
    "pos": "positive",
    "positive": "positive",
    "neg": "negative",
    "negative": "negative",
    "neu": "neutral",
    "neutral": "neutral",
    "mixed": "mixed",
}


def canonical_normalize_text(s: Optional[str]) -> str:
    """
    Tier1+Tier2: strip, lower, collapse whitespace, remove leading/trailing punct.
    null/None -> "".
    """
    if s is None:
        return ""
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(".,;:!?\"'`""''()[]{}")
    return t


def normalize_polarity_strict(
    s: Optional[str],
    default_missing: Optional[str] = "neutral",
) -> Optional[str]:
    """
    Tier1+Tier2: pos->positive, neg->negative, neu->neutral.
    Whitelist only; no edit-distance repair.
    """
    if s is None or (isinstance(s, str) and not s.strip()):
        return default_missing
    key = (s or "").strip().lower()
    if key in _POLARITY_MAP:
        return _POLARITY_MAP[key]
    if key in ("positive", "negative", "neutral", "mixed"):
        return key
    return default_missing
