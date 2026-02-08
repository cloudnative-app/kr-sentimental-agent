"""
SignatureBuilder — raw text → input_signature (구조 태그/길이/언어 등).
원문 저장 금지: input_signature만 반환.
"""

from __future__ import annotations

import re
from typing import List

from schemas.memory_v1_1 import InputSignatureV1_1


def _length_bucket(text: str) -> str:
    n = len(text.strip())
    if n < 50:
        return "short"
    if n < 200:
        return "medium"
    return "long"


def _detect_structure(text: str, language: str = "ko") -> List[str]:
    """간단한 구조 표지: negation, contrast, irony, none."""
    detected: List[str] = []
    t = text.lower().strip()
    # negation
    neg_patterns = ["안 ", "못 ", "없", "않", "not ", "n't ", "never ", "no "]
    if any(p in t for p in neg_patterns):
        detected.append("negation")
    # contrast (간단)
    contrast_patterns = ["하지만", "그런데", "반면", "but ", "however", "although"]
    if any(p in t for p in contrast_patterns):
        detected.append("contrast")
    if not detected:
        detected.append("none")
    return detected


def build_input_signature(
    raw_text: str,
    *,
    language: str = "ko",
    num_aspects: int = 0,
) -> InputSignatureV1_1:
    """
    raw text → input_signature. 원문은 저장하지 않고 시그니처만 반환.
    """
    detected_structure = _detect_structure(raw_text, language)
    length_bucket = _length_bucket(raw_text)
    has_negation = "negation" in detected_structure
    return InputSignatureV1_1(
        language=language,
        detected_structure=detected_structure,
        contrast_marker=None,
        has_negation=has_negation,
        num_aspects=num_aspects,
        length_bucket=length_bucket,
    )


class SignatureBuilder:
    """raw text → input_signature. 원문 저장 금지."""

    def build(
        self,
        raw_text: str,
        *,
        language: str = "ko",
        num_aspects: int = 0,
    ) -> InputSignatureV1_1:
        return build_input_signature(raw_text, language=language, num_aspects=num_aspects)
