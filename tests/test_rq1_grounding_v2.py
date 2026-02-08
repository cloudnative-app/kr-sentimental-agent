"""Tests for RQ1 Grounding v2: drop_reason taxonomy and RQ1 one-hot invariants. See docs/metric_spec_rq1_grounding_v2.md."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.scorecard_from_smoke import (
    DROP_REASON_ALIGNMENT_FAILURE,
    DROP_REASON_FILTER_REJECTION,
    DROP_REASON_SEMANTIC_HALLUCINATION,
    build_filtered_aspects,
)
from scripts.structural_error_aggregator import (
    DROP_REASON_ALIGNMENT_FAILURE as AGG_ALIGNMENT_FAILURE,
    DROP_REASON_FILTER_REJECTION as AGG_FILTER_REJECTION,
    DROP_REASON_SEMANTIC_HALLUCINATION as AGG_SEMANTIC_HALLUCINATION,
    aggregate_single_run,
    count_hallucination_types,
    load_jsonl,
    rq1_grounding_bucket,
    RQ1_BUCKET_IMPLICIT,
    RQ1_BUCKET_EXPLICIT,
    RQ1_BUCKET_EXPLICIT_FAILURE,
    RQ1_BUCKET_UNSUPPORTED,
)


def test_drop_reason_alignment_failure():
    """Span exists and term != span_text -> alignment_failure."""
    text = "ab good"
    aspects = [{"term": "xy", "span": {"start": 0, "end": 2}}]  # span_text "ab" != term "xy"
    raw, filtered, _, _ = build_filtered_aspects(text, aspects)
    assert len(filtered) == 1
    assert filtered[0]["action"] == "drop"
    assert filtered[0]["drop_reason"] == DROP_REASON_ALIGNMENT_FAILURE
    assert filtered[0].get("span_text") == "ab"


def test_drop_reason_filter_rejection():
    """Invalid target (stoplist/short) -> filter_rejection."""
    text = "아 좋아요"  # "아" is in STOP_ASPECT_TERMS
    aspects = [{"term": "아", "span": {"start": 0, "end": 1}}]
    raw, filtered, _, _ = build_filtered_aspects(text, aspects)
    assert len(filtered) == 1
    assert filtered[0]["action"] == "drop"
    assert filtered[0]["drop_reason"] == DROP_REASON_FILTER_REJECTION


def test_drop_reason_semantic_hallucination():
    """No valid span (missing or out-of-range) -> semantic_hallucination."""
    text = "good taste"
    aspects = [{"term": "taste", "span": {}}]  # no start/end -> has_span False, span_txt ""
    raw, filtered, _, _ = build_filtered_aspects(text, aspects)
    assert len(filtered) == 1
    assert filtered[0]["action"] == "drop"
    assert filtered[0]["drop_reason"] == DROP_REASON_SEMANTIC_HALLUCINATION


def test_count_hallucination_types():
    """count_hallucination_types returns booleans for each drop_reason present."""
    record = {
        "inputs": {
            "ate_debug": {
                "filtered": [
                    {"action": "drop", "drop_reason": AGG_ALIGNMENT_FAILURE},
                    {"action": "keep", "drop_reason": None},
                    {"action": "drop", "drop_reason": AGG_FILTER_REJECTION},
                ]
            }
        }
    }
    out = count_hallucination_types(record)
    assert out[AGG_ALIGNMENT_FAILURE] is True
    assert out[AGG_FILTER_REJECTION] is True
    assert out[AGG_SEMANTIC_HALLUCINATION] is False


def test_rq1_bucket_one_of_four():
    """rq1_grounding_bucket returns exactly one of the four buckets."""
    buckets = {RQ1_BUCKET_IMPLICIT, RQ1_BUCKET_EXPLICIT, RQ1_BUCKET_EXPLICIT_FAILURE, RQ1_BUCKET_UNSUPPORTED}
    record = {
        "runtime": {"parsed_output": {"final_result": {"final_tuples": [{"aspect_term": "맛", "polarity": "positive"}]}}},
        "ate": {},
        "atsa": {
            "sentiment_judgements": [
                {"aspect_term": "맛", "opinion_grounded": True, "issues": []},
            ]
        },
        "moderator": {},
    }
    b = rq1_grounding_bucket(record)
    assert b in buckets


def test_aggregate_rq1_one_hot_sum_near_one():
    """After aggregation, rq1_one_hot_sum should be ~1.0 (one-hot invariant)."""
    import tempfile
    scorecard = {
        "profile": "smoke",
        "meta": {"text_id": "t1", "profile": "smoke"},
        "ate": {"hallucination_flag": False},
        "ate_score": {},
        "atsa": {"sentiment_judgements": [{"aspect_term": "taste", "opinion_grounded": True, "issues": []}]},
        "inputs": {"ate_debug": {"filtered": [{"action": "keep", "drop_reason": None}]}},
        "runtime": {
            "parsed_output": {
                "final_result": {
                    "final_tuples": [{"aspect_term": {"term": "taste"}, "polarity": "positive"}],
                }
            }
        },
        "moderator": {},
        "validator": [],
        "stage_delta": {"changed": False, "change_type": "none"},
        "flags": {},
    }
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scorecards.jsonl"
        path.write_text(json.dumps(scorecard) + "\n", encoding="utf-8")
        rows = load_jsonl(path)
    metrics = aggregate_single_run(rows)
    one_hot_sum = metrics.get("rq1_one_hot_sum")
    assert one_hot_sum is not None
    assert abs(one_hot_sum - 1.0) < 0.001
