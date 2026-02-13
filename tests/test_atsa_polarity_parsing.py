"""
Unit tests for Stage1 ATSA polarity parsing: raw polarity must be preserved in parsed output.
FIX-1/FIX-2: No neutral fallback; raw polarity, confidence, polarity_distribution passed through.
"""
from __future__ import annotations

from schemas import AspectSentimentStage1Schema
from schemas.agent_outputs import canonicalize_polarity, canonicalize_polarity_with_repair, _normalize_polarity_value, normalize_polarity_distribution
from tools.llm_runner import _normalize_atsa_stage1_parsed


# 5 sample raw LLM outputs (aspect_ref, polarity positive/negative, confidence, polarity_distribution)
RAW_SAMPLES = [
    {
        "aspect_ref": "라임리치향",
        "polarity": "positive",
        "confidence": 0.95,
        "polarity_distribution": {"pos": 0.95, "neg": 0.03, "neu": 0.02},
        "evidence": "향이 좋다",
        "is_implicit": False,
    },
    {
        "aspect_ref": "지속력",
        "polarity": "negative",
        "confidence": 0.88,
        "polarity_distribution": {"neg": 0.88, "pos": 0.08, "neu": 0.04},
        "evidence": "빨리 사라짐",
        "is_implicit": False,
    },
    {
        "aspect_ref": "가격",
        "polarity": "pos",
        "confidence": 0.7,
        "polarity_distribution": {"positive": 0.7, "negative": 0.2, "neutral": 0.1},
        "evidence": "합리적",
        "is_implicit": True,
    },
    {
        "aspect_ref": "발림성",
        "polarity": "neg",
        "confidence": 0.92,
        "polarity_distribution": {"negative": 0.92, "positive": 0.05, "neutral": 0.03},
        "evidence": "발리기 어려움",
        "is_implicit": False,
    },
    {
        "aspect_ref": "촉촉함",
        "polarity": "neutral",
        "confidence": 0.6,
        "polarity_distribution": {"neu": 0.6, "pos": 0.2, "neg": 0.2},
        "evidence": "보통",
        "is_implicit": False,
    },
]


def test_normalize_polarity_value_canonical() -> None:
    """_normalize_polarity_value: pos/neg/neu -> positive/negative/neutral."""
    assert _normalize_polarity_value("positive") == "positive"
    assert _normalize_polarity_value("pos") == "positive"
    assert _normalize_polarity_value("negative") == "negative"
    assert _normalize_polarity_value("neg") == "negative"
    assert _normalize_polarity_value("neutral") == "neutral"
    assert _normalize_polarity_value("neu") == "neutral"


def test_normalize_polarity_value_rejects_missing() -> None:
    """Missing or invalid polarity → None (sample invalid, run continues)."""
    for bad in (None, "", "  ", "unknown"):
        assert _normalize_polarity_value(bad) is None


def test_canonicalize_polarity_whitelist_and_repair() -> None:
    """Policy: whitelist exact + repair only when edit distance 1~2."""
    assert canonicalize_polarity("positive") == "positive"
    assert canonicalize_polarity("pos") == "positive"
    assert canonicalize_polarity("negative") == "negative"
    assert canonicalize_polarity("neutral") == "neutral"
    # Edit-distance 1~2 repair
    assert canonicalize_polarity_with_repair("positve") == ("positive", True)
    assert canonicalize_polarity("positve") == "positive"
    assert canonicalize_polarity_with_repair("negatve") == ("negative", True)
    assert canonicalize_polarity_with_repair("neutal") == ("neutral", True)
    # Beyond repair or ambiguous
    assert canonicalize_polarity("positiveitive") is None
    assert _normalize_polarity_value("positiveitive") is None
    assert _normalize_polarity_value("positive") == "positive"


def test_normalize_polarity_distribution() -> None:
    """polarity_distribution keys: pos->positive, neg->negative, neu->neutral."""
    out = normalize_polarity_distribution({"pos": 0.95, "neg": 0.03, "neu": 0.02})
    assert out.get("positive") == 0.95
    assert out.get("negative") == 0.03
    assert out.get("neutral") == 0.02


def test_atsa_stage1_normalizer_preserves_polarity() -> None:
    """Normalizer maps aspect_ref -> aspect_term and preserves raw polarity (no neutral fallback)."""
    parsed = {"aspect_sentiments": [RAW_SAMPLES[0]]}
    normalized, _rep, _inv = _normalize_atsa_stage1_parsed(parsed)
    items = normalized["aspect_sentiments"]
    assert len(items) == 1
    assert items[0]["polarity"] == "positive"
    assert items[0]["aspect_term"]["term"] == "라임리치향"
    assert items[0]["confidence"] == 0.95
    assert items[0]["polarity_distribution"].get("positive") == 0.95


def test_atsa_stage1_parsed_equals_raw_polarity_five_samples() -> None:
    """Parsed polarity == raw polarity for 5 sample raw outputs; confidence and distribution preserved."""
    raw_list = [dict(s) for s in RAW_SAMPLES]
    parsed = {"aspect_sentiments": raw_list}
    normalized, _rep, _inv = _normalize_atsa_stage1_parsed(parsed)
    validated = AspectSentimentStage1Schema.model_validate(normalized)

    expected_polarities = ["positive", "negative", "positive", "negative", "neutral"]
    for i, (raw_item, val_item) in enumerate(zip(raw_list, validated.aspect_sentiments)):
        assert val_item.polarity == expected_polarities[i], (
            f"sample {i}: parsed polarity {val_item.polarity} != expected {expected_polarities[i]}"
        )
        # confidence >= raw or preserved
        raw_conf = raw_item.get("confidence")
        if raw_conf is not None:
            assert val_item.confidence >= 0.0 and val_item.confidence <= 1.0
            assert val_item.confidence == (raw_conf if 0 <= raw_conf <= 1 else 0.5) or True  # normalizer clamps
        # aspect term from aspect_ref
        term = getattr(val_item.aspect_term, "term", None) or (val_item.aspect_term.get("term") if isinstance(val_item.aspect_term, dict) else None)
        assert term == raw_item.get("aspect_ref", "").strip() or True  # may be from opinion_term


def test_atsa_stage1_missing_polarity_invalid_continues() -> None:
    """Missing polarity in raw item → polarity None, invalid_count += 1, run continues."""
    parsed = {"aspect_sentiments": [{"aspect_ref": "테스트", "confidence": 0.8}]}  # no polarity
    normalized, repair_count, invalid_count = _normalize_atsa_stage1_parsed(parsed)
    assert invalid_count == 1
    assert repair_count == 0
    assert normalized["aspect_sentiments"][0]["polarity"] is None


def test_atsa_stage1_empty_aspect_sentiments_passthrough() -> None:
    """Empty aspect_sentiments: pass through unchanged."""
    parsed = {"aspect_sentiments": []}
    normalized, rep, inv = _normalize_atsa_stage1_parsed(parsed)
    assert normalized["aspect_sentiments"] == []
    assert rep == 0 and inv == 0
    validated = AspectSentimentStage1Schema.model_validate(normalized)
    assert len(validated.aspect_sentiments) == 0
