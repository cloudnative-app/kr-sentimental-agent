"""Tests for conflict_review granularity_overlap_candidate detection."""

from __future__ import annotations

import pytest

from agents.conflict_review_runner import _detect_granularity_overlap, _compute_conflict_flags


def test_detect_granularity_overlap_upper_and_lower() -> None:
    """Same attr+pol with 제품 전체 + 본품 -> granularity_overlap_candidate."""
    cands = [
        {"tuple_id": "t0", "aspect_ref": "제품 전체#일반", "polarity": "positive"},
        {"tuple_id": "t1", "aspect_ref": "본품#일반", "polarity": "positive"},
    ]
    flags = _detect_granularity_overlap(cands)
    assert len(flags) >= 1
    g = [f for f in flags if f.get("conflict_type") == "granularity_overlap_candidate"]
    assert len(g) == 1
    assert set(g[0]["tuple_ids"]) == {"t0", "t1"}


def test_compute_conflict_flags_includes_granularity() -> None:
    """_compute_conflict_flags extends with granularity_overlap_candidate."""
    cands = [
        {"tuple_id": "t0", "aspect_ref": "제품 전체#일반", "polarity": "positive"},
        {"tuple_id": "t1", "aspect_ref": "본품#일반", "polarity": "positive"},
    ]
    all_flags = _compute_conflict_flags(cands)
    g = [f for f in all_flags if f.get("conflict_type") == "granularity_overlap_candidate"]
    assert len(g) >= 1
