"""
Unit tests for Tuple (Aspect, Polarity) evaluation — gold_tuples / gold_triplets backward compat.
See docs/absa_tuple_eval.md.
"""

from __future__ import annotations

import pytest

from metrics.eval_tuple import (
    gold_implicit_polarities_from_tuples,
    gold_row_to_tuples,
    gold_tuple_set_from_record,
    normalize_polarity,
    precision_recall_f1_implicit_only,
    precision_recall_f1_tuple,
    pred_valid_polarities_from_tuples,
    tuple_from_sent,
    tuple_sets_match_with_empty_rule,
    tuples_from_list,
    tuples_to_pairs,
    tuples_to_ref_pairs,
)


def test_gold_row_to_tuples_new_format() -> None:
    """New gold_tuples format yields list of {aspect_ref, aspect_term, polarity}."""
    row = {
        "uid": "x1",
        "gold_tuples": [
            {"aspect_ref": "본품#다양성", "aspect_term": "마스크팩", "polarity": "positive"},
            {"aspect_ref": "가격", "aspect_term": "가격", "polarity": "neutral"},
        ],
    }
    out, _ = gold_row_to_tuples(row)
    assert len(out) == 2
    assert out[0]["aspect_ref"] == "본품#다양성"
    assert out[0]["aspect_term"] == "마스크팩"
    assert out[0]["polarity"] == "positive"
    assert out[1]["aspect_ref"] == "가격"
    assert out[1]["aspect_term"] == "가격"
    assert out[1]["polarity"] == "neutral"


def test_gold_row_to_tuples_legacy_format() -> None:
    """Legacy gold_triplets with opinion_term.term → aspect_term (backward compat)."""
    row = {
        "uid": "x2",
        "gold_triplets": [
            {"aspect_ref": "본품#다양성", "opinion_term": {"term": "마스크팩"}, "polarity": "positive"},
        ],
    }
    out, _ = gold_row_to_tuples(row)
    assert len(out) == 1
    assert out[0]["aspect_ref"] == "본품#다양성"
    assert out[0]["aspect_term"] == "마스크팩"
    assert out[0]["polarity"] == "positive"


def test_gold_tuple_set_same_for_both_formats() -> None:
    """Same gold content in gold_tuples vs gold_triplets yields same tuple set."""
    row_new = {
        "uid": "x",
        "gold_tuples": [{"aspect_ref": "a", "aspect_term": "b", "polarity": "positive"}],
    }
    row_legacy = {
        "uid": "x",
        "gold_triplets": [{"aspect_ref": "a", "opinion_term": {"term": "b"}, "polarity": "positive"}],
    }
    lst_new, _ = gold_row_to_tuples(row_new)
    lst_legacy, _ = gold_row_to_tuples(row_legacy)
    set_new = set(tuple(t[k] for k in ("aspect_ref", "aspect_term", "polarity")) for t in (lst_new or []))
    set_legacy = set(tuple(t[k] for k in ("aspect_ref", "aspect_term", "polarity")) for t in (lst_legacy or []))
    assert set_new == set_legacy
    assert set_new == {("a", "b", "positive")}


def test_gold_tuple_set_from_record_prefers_gold_tuples() -> None:
    """Scorecard with inputs.gold_tuples is used for F1."""
    record = {
        "inputs": {
            "gold_tuples": [{"aspect_ref": "r", "aspect_term": "t", "polarity": "negative"}],
        },
    }
    s = gold_tuple_set_from_record(record)
    assert s is not None
    assert len(s) == 1
    # EvalTuple is (aspect_ref, aspect_term, polarity) normalized
    t = next(iter(s))
    assert t[0] == "r"
    assert t[1] == "t"
    assert t[2] == "negative"


def test_tuple_from_sent_aspect_term() -> None:
    """Sentiment dict: aspect_term (or legacy opinion_term.term) is used as aspect surface form."""
    sent = {
        "aspect_term": {"term": "친절해요", "span": {"start": 0, "end": 3}},
        "polarity": "positive",
    }
    t = tuple_from_sent(sent)
    assert t[0] == ""
    assert t[1] == "친절해요"
    assert t[2] == "positive"


def test_tuples_from_list_final_aspects() -> None:
    """final_aspects list (aspect_term or legacy opinion_term, polarity) → set of EvalTuple."""
    items = [
        {"aspect_term": {"term": "저렴", "span": {"start": 0, "end": 2}}, "polarity": "positive"},
        {"aspect_term": {"term": "맛", "span": {"start": 0, "end": 1}}, "polarity": "negative"},
    ]
    s = tuples_from_list(items)
    assert len(s) == 2
    by_term = {t[1]: t for t in s}
    assert "저렴" in by_term
    assert by_term["저렴"][2] == "positive"
    assert "맛" in by_term
    assert by_term["맛"][2] == "negative"


def test_gold_aspect_term_empty_preserved() -> None:
    """Gold with aspect_term=\"\" keeps \"\"; do not fill with aspect_ref."""
    row = {
        "uid": "x",
        "gold_tuples": [{"aspect_ref": "본품#품질", "aspect_term": "", "polarity": "positive"}],
    }
    out, _ = gold_row_to_tuples(row)
    assert len(out) == 1
    assert out[0]["aspect_term"] == ""
    assert out[0]["aspect_ref"] == "본품#품질"
    assert out[0]["polarity"] == "positive"


def test_tuple_from_sent_implicit() -> None:
    """When is_implicit is True, aspect_term is \"\" (암시적 관점)."""
    sent = {"aspect_term": {"term": "추측", "span": {"start": 0, "end": 2}}, "polarity": "positive", "is_implicit": True}
    t = tuple_from_sent(sent)
    assert t is not None
    assert t[1] == ""
    assert t[2] == "positive"


def test_tuples_from_list_includes_empty_aspect_term() -> None:
    """aspect_term=\"\" tuples are included for F1 (\"\", polarity) pairing."""
    items = [{"aspect_term": {"term": "", "span": {"start": 0, "end": 0}}, "polarity": "positive"}]
    s = tuples_from_list(items)
    assert len(s) == 1
    t = next(iter(s))
    assert t[1] == ""
    assert t[2] == "positive"
    pairs = tuples_to_pairs(s)
    assert ("", "positive") in pairs


def test_normalize_polarity() -> None:
    """Polarity normalized: pos→positive, neg→negative, neu→neutral. Missing with default_missing=None → None."""
    assert normalize_polarity("pos") == "positive"
    assert normalize_polarity("positive") == "positive"
    assert normalize_polarity("neg") == "negative"
    assert normalize_polarity("negative") == "negative"
    assert normalize_polarity("neu") == "neutral"
    assert normalize_polarity("neutral") == "neutral"
    assert normalize_polarity(None) == "neutral"
    assert normalize_polarity(None, default_missing=None) is None
    assert normalize_polarity("", default_missing=None) is None


def test_precision_recall_f1_empty_aspect_polarity_only() -> None:
    """When gold aspect_term is "", match by polarity only (1:1). Uses term-based for implicit matching."""
    # Gold: one implicit (aspect_term="", polarity=positive)
    gold = tuples_from_list([{"aspect_ref": "본품#품질", "aspect_term": "", "polarity": "positive"}])
    # Pred: one concrete (aspect_term=피부톤, polarity=positive)
    pred = tuples_from_list([{"aspect_term": {"term": "피부톤", "span": {"start": 0, "end": 3}}, "polarity": "positive"}])
    prec, rec, f1 = precision_recall_f1_tuple(
        gold, pred, match_empty_aspect_by_polarity_only=True, match_by_aspect_ref=False
    )
    assert prec == 1.0
    assert rec == 1.0
    assert f1 == 1.0
    assert tuple_sets_match_with_empty_rule(gold, pred, match_by_aspect_ref=False) is True


def test_precision_recall_f1_empty_aspect_strict_no_match() -> None:
    """When match_empty_aspect_by_polarity_only=False, gold ("", p) does not match pred (t, p)."""
    gold = tuples_from_list([{"aspect_ref": "본품#품질", "aspect_term": "", "polarity": "positive"}])
    pred = tuples_from_list([{"aspect_term": {"term": "피부톤", "span": {"start": 0, "end": 3}}, "polarity": "positive"}])
    prec, rec, f1 = precision_recall_f1_tuple(
        gold, pred, match_empty_aspect_by_polarity_only=False, match_by_aspect_ref=False
    )
    assert f1 == 0.0
    assert tuple_sets_match_with_empty_rule(gold, pred, match_empty_aspect_by_polarity_only=False, match_by_aspect_ref=False) is False


# ---------- Implicit-only F1 and valid/invalid polarity (tuple_f1_s2_implicit_only, implicit_invalid_pred_rate) ----------


def test_implicit_gold_one_pred_valid_one_f1_one() -> None:
    """Implicit gold 1, pred polarity valid 1 → implicit F1 = 1.0, invalid count 0."""
    gold = {("", "", "positive")}  # (aspect_ref, aspect_term, polarity) with aspect_term=""
    pred = {("", "", "positive")}
    g_pols = gold_implicit_polarities_from_tuples(gold)
    p_pols, invalid = pred_valid_polarities_from_tuples(pred)
    assert g_pols == ["positive"]
    assert p_pols == ["positive"]
    assert invalid == 0
    _, _, f1 = precision_recall_f1_implicit_only(g_pols, p_pols)
    assert f1 == 1.0


def test_implicit_gold_one_pred_missing_polarity_invalid() -> None:
    """Implicit gold 1, pred polarity missing → valid=0, invalid=1; implicit F1 uses empty pred set."""
    gold = {("", "", "positive")}
    pred = {("", "", "")}  # empty polarity
    g_pols = gold_implicit_polarities_from_tuples(gold)
    p_pols, invalid = pred_valid_polarities_from_tuples(pred)
    assert g_pols == ["positive"]
    assert p_pols == []
    assert invalid == 1
    _, _, f1 = precision_recall_f1_implicit_only(g_pols, p_pols)
    assert f1 == 0.0


def test_implicit_f1_set_based() -> None:
    """Implicit-only F1 is set-based: gold {pos, neg}, pred {pos} → TP=1, FP=0, FN=1, rec=0.5, prec=1, F1=2/3."""
    gold_pols = ["positive", "negative"]
    pred_pols = ["positive"]
    prec, rec, f1 = precision_recall_f1_implicit_only(gold_pols, pred_pols)
    assert prec == 1.0
    assert rec == 0.5
    assert abs(f1 - 2.0 / 3.0) < 1e-6


def test_tuples_to_ref_pairs_skips_empty_ref() -> None:
    """Ref-based pairs: (aspect_ref, polarity); tuples with empty aspect_ref are excluded."""
    gold = {("제품 전체#일반", "아이립밤", "positive"), ("", "맛", "negative")}
    pairs, invalid = tuples_to_ref_pairs(gold)
    assert invalid == 1
    assert ("제품 전체#일반", "positive") in pairs
    assert ("", "negative") not in pairs  # empty ref skipped


def test_precision_recall_f1_ref_based_match() -> None:
    """CR v2: when both gold and pred have aspect_ref, match on (aspect_ref, polarity)."""
    gold = {("제품 전체#일반", "아이립밤", "positive")}
    pred = {("제품 전체#일반", "아이립밤", "positive")}
    prec, rec, f1 = precision_recall_f1_tuple(gold, pred, match_by_aspect_ref=True)
    assert prec == 1.0
    assert rec == 1.0
    assert f1 == 1.0


def test_normalize_ref_for_eval_preserves_hash() -> None:
    """normalize_ref_for_eval preserves # and strips # left/right spaces."""
    from metrics.eval_tuple import normalize_ref_for_eval
    assert normalize_ref_for_eval("제품 전체 # 품질") == "제품 전체#품질"
    assert normalize_ref_for_eval("본품#다양성") == "본품#다양성"
    gold = tuples_from_list([{"aspect_ref": "제품 전체#품질", "aspect_term": "포장", "polarity": "positive"}])
    pred = tuples_from_list([{"aspect_ref": "제품 전체#품질", "aspect_term": "포장", "polarity": "positive"}])
    prec, rec, f1 = precision_recall_f1_tuple(gold, pred, match_by_aspect_ref=True)
    assert prec == 1.0
    assert rec == 1.0
    assert f1 == 1.0


def test_pred_valid_polarities_rejects_unknown() -> None:
    """Pred with polarity unknown/missing → valid list empty or partial, invalid count increased."""
    pred_unknown = {("", "x", "unknown")}
    p_pols, inv = pred_valid_polarities_from_tuples(pred_unknown)
    assert p_pols == []
    assert inv == 1
    pred_mixed = {("", "a", "positive"), ("", "b", "")}
    p_pols2, inv2 = pred_valid_polarities_from_tuples(pred_mixed)
    assert p_pols2 == ["positive"]
    assert inv2 == 1
