"""
CR v2 validation: taxonomy, language, opinion→aspect.
Closed-set aspect_ref, Korean-only aspect_term, opinion-word exclusion.
SSOT: schemas.taxonomy
"""

from __future__ import annotations

import re

from schemas.taxonomy import ALLOWED_REFS

# Backward compat alias
VALID_ASPECT_REF: frozenset[str] = ALLOWED_REFS


def validate_aspect_ref(ref: str) -> bool:
    """Return True if aspect_ref is in the closed-set taxonomy (ALLOWED_REFS)."""
    if not ref or not isinstance(ref, str):
        return False
    return ref.strip() in ALLOWED_REFS


def has_english_in_term(term: str) -> bool:
    """Return True if aspect_term contains Latin letters (A-Za-z)."""
    if not term or not isinstance(term, str):
        return False
    return bool(re.search(r"[A-Za-z]", term))


# Evaluative expressions that should NOT be used as aspect_term (opinion words, not targets)
_OPINION_LEXICON: frozenset[str] = frozenset({
    "좋아", "나쁘다", "부드러움", "최고", "bad", "excellent", "good", "great",
    "worst", "best", "맛있다", "맛없다", "예쁘다", "추하다", "편하다", "불편하다",
    "만족", "불만", "훌륭", "형편", "훌륭하다", "별로", "괜찮", "괜찮다",
    "좋다", "나쁘다", "훌륭함", "최악", "훌륭", "별로다",
})

_OPINION_SUFFIXES: tuple[str, ...] = (
    "좋아", "나쁘다", "부드러움", "최고", "맛있다", "맛없다", "예쁘다",
    "편하다", "불편하다", "훌륭하다", "괜찮다", "별로다",
)


def is_likely_opinion_word(term: str) -> bool:
    """
    Return True if term appears to be an opinion/evaluative expression rather than an aspect target.
    Used for invalid_target_flag logging; does not remove triplets.
    """
    if not term or not isinstance(term, str):
        return False
    t = term.strip().lower()
    if not t:
        return False
    if t in _OPINION_LEXICON:
        return True
    for suf in _OPINION_SUFFIXES:
        if t.endswith(suf) or t == suf:
            return True
    return False
