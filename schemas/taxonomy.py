"""
NIKLuge ABSA Taxonomy v1 — SSOT (Single Source of Truth).

Entity/Attribute 정의 및 허용 조합. docs/taxonomy_nikluge_v1.md 참고.
"""

from __future__ import annotations

import re

# Entity (개체)
ALLOWED_ENTITIES: frozenset[str] = frozenset({
    "제품 전체",
    "본품",
    "패키지·구성품",
    "브랜드",
})

# Attribute (속성)
ALLOWED_ATTRIBUTES: frozenset[str] = frozenset({
    "일반", "가격", "디자인", "품질", "편의성", "다양성", "인지도",
})


# 허용 (entity, attribute) 조합
ALLOWED_REF_PAIRS: frozenset[tuple[str, str]] = frozenset({

    # 제품 전체 (7)
    ("제품 전체", "품질"),
    ("제품 전체", "편의성"),
    ("제품 전체", "디자인"),
    ("제품 전체", "일반"),
    ("제품 전체", "가격"),
    ("제품 전체", "인지도"),
    ("제품 전체", "다양성"),

    # 본품 (7)
    ("본품", "일반"),
    ("본품", "다양성"),
    ("본품", "품질"),
    ("본품", "인지도"),
    ("본품", "편의성"),
    ("본품", "디자인"),
    ("본품", "가격"),

    # 패키지·구성품 (6)
    ("패키지·구성품", "디자인"),
    ("패키지·구성품", "가격"),
    ("패키지·구성품", "다양성"),
    ("패키지·구성품", "일반"),
    ("패키지·구성품", "편의성"),
    ("패키지·구성품", "품질"),

    # 브랜드 (5)
    ("브랜드", "인지도"),
    ("브랜드", "일반"),
    ("브랜드", "디자인"),
    ("브랜드", "품질"),
    ("브랜드", "가격"),
})

# 허용 aspect_ref 문자열 (entity#attribute). 패키지/구성품 포함 = gold 호환 (정규화 단계에서 /↔· 동일시하지 않음)
_EXTRA_GOLD_COMPAT_REFS: frozenset[str] = frozenset({
    "패키지/구성품#디자인", "패키지/구성품#가격", "패키지/구성품#다양성",
    "패키지/구성품#일반", "패키지/구성품#편의성", "패키지/구성품#품질",
})
ALLOWED_REFS: frozenset[str] = frozenset(
    f"{entity}#{attribute}"
    for entity, attribute in ALLOWED_REF_PAIRS
) | _EXTRA_GOLD_COMPAT_REFS

def normalize_entity(s: str) -> str:
    """Normalize entity string: strip, / → ·, collapse whitespace. Eval-only."""
    if not s or not isinstance(s, str):
        return ""
    t = (s or "").strip().replace("/", "·")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_ref_canonical(ref: str) -> str:
    """
    Canonicalize aspect_ref for eval matching: / → ·, strip, collapse whitespace.
    Applies to whole ref (entity#attribute). Eval-only; no gold leakage.
    """
    if not ref or not isinstance(ref, str):
        return ""
    t = (ref or "").strip().replace("/", "·")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_ref(ref: str) -> tuple[str, str] | None:
    """Parse entity#attribute into (entity, attribute). Returns None if invalid format."""
    if not ref or "#" not in ref:
        return None
    parts = ref.split("#", 1)
    if len(parts) != 2:
        return None
    return (parts[0].strip(), parts[1].strip())


def is_valid_ref(ref: str) -> bool:
    """Return True if aspect_ref is in ALLOWED_REFS."""
    if not ref or not isinstance(ref, str):
        return False
    return ref.strip() in ALLOWED_REFS


def get_attribute(ref: str) -> str | None:
    """Extract attribute from entity#attribute. Returns None if invalid."""
    parsed = parse_ref(ref)
    return parsed[1] if parsed else None


def get_entity(ref: str) -> str | None:
    """Extract entity from entity#attribute. Returns None if invalid."""
    parsed = parse_ref(ref)
    return parsed[0] if parsed else None
