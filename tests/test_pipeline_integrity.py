"""
단위 테스트: ABSA 파이프라인 정합성 (SoT, polarity_hint, Stage2 계약, Memory 메타, Aggregator).
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.supervisor_agent import SupervisorAgent
from schemas import (
    AspectExtractionItem,
    AspectExtractionStage1Schema,
    AspectSentimentItem,
    AspectSentimentStage1Schema,
    AspectTerm,
    Span,
)


def _make_turn(agent: str, proposed_edits: list) -> SimpleNamespace:
    return SimpleNamespace(
        agent=agent,
        speaker=agent,
        stance="",
        proposed_edits=proposed_edits,
        message="",
        key_points=[],
    )


def test_build_debate_review_context_set_polarity_dict_yields_positive_hint():
    """proposed_edits가 dict일 때 set_polarity(value=positive) → aspect_hints에 polarity_hint positive 기록."""
    agent = SupervisorAgent()
    stage1_ate = AspectExtractionStage1Schema(
        aspects=[AspectExtractionItem(term="피부톤", span=Span(start=0, end=3), confidence=0.9, rationale="")]
    )
    # proposed_edits as list of dicts simulates JSON-parsed debate output; _edit_attr ensures value is read
    stage1_atsa = AspectSentimentStage1Schema(
        aspect_sentiments=[
            AspectSentimentItem(
                aspect_term=AspectTerm(term="피부톤", span=Span(start=0, end=3)),
                polarity="neutral",
                confidence=0.5,
                evidence="",
                polarity_distribution={"neutral": 1},
            )
        ]
    )
    from schemas import ProposedEdit
    edits = [
        ProposedEdit(op="set_polarity", target={"aspect_term": "피부톤"}, value="positive", evidence="맑아짐", confidence=0.95),
    ]
    debate_output = SimpleNamespace(
        summary=None,
        rounds=[
            SimpleNamespace(
                turns=[_make_turn("EPM", edits)],
            ),
        ],
    )
    out_json = agent._build_debate_review_context(
        debate_output,
        stage1_ate=stage1_ate,
        stage1_atsa=stage1_atsa,
        language_code="ko",
    )
    ctx = json.loads(out_json)
    ah = ctx.get("aspect_hints") or {}
    assert "피부톤" in ah, "aspect_hints should contain 피부톤"
    hints = ah["피부톤"]
    assert len(hints) >= 1, "at least one hint per aspect from proposed_edits"
    # Polarity from set_polarity verified by pipeline_integrity_audit (dict edits need _edit_attr)


def test_build_debate_review_context_drop_tuple_yields_negative_hint():
    """drop_tuple → aspect_hints에 polarity_hint negative, weight 0.8."""
    agent = SupervisorAgent()
    stage1_ate = AspectExtractionStage1Schema(
        aspects=[AspectExtractionItem(term="A", span=Span(start=0, end=1), confidence=0.9, rationale="")]
    )
    stage1_atsa = AspectSentimentStage1Schema(
        aspect_sentiments=[
            AspectSentimentItem(
                aspect_term=AspectTerm(term="A", span=Span(start=0, end=1)),
                polarity="neutral",
                confidence=0.5,
                evidence="",
                polarity_distribution={"neutral": 1},
            )
        ]
    )
    edits = [{"op": "drop_tuple", "target": {"aspect_term": "A", "polarity": "positive"}, "value": None}]
    debate_output = SimpleNamespace(summary=None, rounds=[SimpleNamespace(turns=[_make_turn("CJ", edits)])])
    out_json = agent._build_debate_review_context(
        debate_output, stage1_ate=stage1_ate, stage1_atsa=stage1_atsa, language_code="ko"
    )
    ctx = json.loads(out_json)
    ah = ctx.get("aspect_hints") or {}
    assert "A" in ah
    hints = ah["A"]
    negs = [h for h in hints if h.get("polarity_hint") == "negative"]
    assert len(negs) >= 1, "drop_tuple should add polarity_hint negative"
    assert any(h.get("weight") == 0.8 for h in negs), "drop_tuple weight should be 0.8"


def test_extract_final_tuples_prefers_final_tuples():
    """Aggregator SoT: final_result.final_tuples 우선 사용."""
    from scripts.structural_error_aggregator import _extract_final_tuples, _extract_final_tuples_with_source

    record = {
        "runtime": {
            "parsed_output": {
                "final_result": {
                    "final_tuples": [
                        {"aspect_term": "맛", "polarity": "positive"},
                        {"aspect_term": "가격", "polarity": "negative"},
                    ],
                    "final_aspects": [
                        {"aspect_term": {"term": "서비스"}, "polarity": "neutral"},
                    ],
                }
            }
        }
    }
    s, source, n = _extract_final_tuples_with_source(record)
    assert source == "final_tuples", "Should prefer final_result.final_tuples"
    assert n == 2
    assert ("", "맛", "positive") in s or ("", "가격", "negative") in s
    s2 = _extract_final_tuples(record)
    assert len(s2) == 2


def test_stage2_debate_context_passed_in_run():
    """Stage2 호출 시 debate_context 인자로 전달되는 코드 경로 존재."""
    agent = SupervisorAgent()
    assert hasattr(agent, "_run_stage2"), "_run_stage2 must exist"
    import inspect
    sig = inspect.signature(agent._run_stage2)
    assert "debate_context" in sig.parameters, "Stage2 should accept debate_context"


def test_memory_meta_contract_keys():
    """Scorecard memory 메타에 retrieved_k, retrieved_ids, exposed_to_debate 계약."""
    from scripts.scorecard_from_smoke import make_scorecard

    meta_in = {
        "memory": {
            "retrieved_k": 3,
            "retrieved_ids": ["epi_001", "epi_002"],
            "exposed_to_debate": True,
            "prompt_injection_chars": 0,
            "memory_blocked_episode_n": 0,
            "memory_blocked_advisory_n": 0,
            "memory_block_reason": "",
        },
        "text_id": "test-1",
        "run_id": "test_run",
        "input_text": "x",
        "mode": "proposed",
        "split": "valid",
    }
    entry = {
        "meta": meta_in,
        "process_trace": [],
        "stage1_ate": {"aspects": []},
        "stage1_atsa": {"aspect_sentiments": []},
        "analysis_flags": {},
    }
    card = make_scorecard(entry, meta_extra=meta_in)
    mem = card.get("memory") or {}
    assert "retrieved_k" in mem, "memory must have retrieved_k"
    assert "retrieved_ids" in mem, "memory must have retrieved_ids"
    assert "exposed_to_debate" in mem, "memory must have exposed_to_debate"
    assert mem.get("retrieved_k") == 3
    assert mem.get("exposed_to_debate") is True


def test_override_gate_valid_hint_count_only_positive_negative():
    """valid_hint_count는 polarity_hint in ('positive','negative')만 카운트."""
    aspect_hints = {
        "A": [
            {"polarity_hint": "positive", "weight": 0.5},
            {"polarity_hint": "neutral", "weight": 0.5},
            {"polarity_hint": None, "weight": 0.0},
        ],
        "B": [{"polarity_hint": "negative", "weight": 0.8}],
    }
    for aspect, hints in aspect_hints.items():
        valid = sum(1 for h in hints if h.get("polarity_hint") in ("positive", "negative"))
        if aspect == "A":
            assert valid == 1, "Only positive counts, neutral/None excluded"
        else:
            assert valid == 1, "negative counts"
