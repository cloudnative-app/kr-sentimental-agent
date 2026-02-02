"""
Tests for integrity features:
1. Run purpose flag inference
2. Split overlap detection
3. Demo hash-based leakage prevention
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Set

import pytest


# ---------- Test run purpose inference ----------


def test_infer_run_purpose_from_config():
    """Test that run_purpose is read from config when present."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "scripts"))
    from run_experiments import _infer_run_purpose

    cfg_smoke = {"run_purpose": "smoke"}
    cfg_paper = {"run_purpose": "paper"}
    cfg_sanity = {"run_purpose": "sanity"}
    cfg_dev = {"run_purpose": "dev"}
    cfg_invalid = {"run_purpose": "invalid"}
    cfg_empty = {}

    assert _infer_run_purpose(cfg_smoke, "some/path.yaml") == "smoke"
    assert _infer_run_purpose(cfg_paper, "some/path.yaml") == "paper"
    assert _infer_run_purpose(cfg_sanity, "some/path.yaml") == "sanity"
    assert _infer_run_purpose(cfg_dev, "some/path.yaml") == "dev"
    # Invalid values fall through to path inference
    assert _infer_run_purpose(cfg_invalid, "experiments/configs/smoke_test.yaml") == "smoke"
    assert _infer_run_purpose(cfg_empty, "experiments/configs/default.yaml") == "dev"


def test_infer_run_purpose_from_path():
    """Test that run_purpose is inferred from config path when not in config."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "scripts"))
    from run_experiments import _infer_run_purpose

    cfg_empty = {}

    assert _infer_run_purpose(cfg_empty, "experiments/configs/smoke_xlang.yaml") == "smoke"
    assert _infer_run_purpose(cfg_empty, "experiments/configs/span_sanity.yaml") == "sanity"
    assert _infer_run_purpose(cfg_empty, "experiments/configs/default.yaml") == "dev"
    assert _infer_run_purpose(cfg_empty, "experiments/configs/proposed.yaml") == "dev"


# ---------- Test split overlap detection ----------


def test_compute_split_overlap_no_overlap():
    """Test that no overlap is detected when splits are distinct."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_run_snapshot import _compute_split_overlap

    # Create mock scorecards with distinct input_hashes
    scorecards = [
        {"meta": {"split": "train", "input_hash": "hash_train_1"}},
        {"meta": {"split": "train", "input_hash": "hash_train_2"}},
        {"meta": {"split": "valid", "input_hash": "hash_valid_1"}},
        {"meta": {"split": "valid", "input_hash": "hash_valid_2"}},
        {"meta": {"split": "test", "input_hash": "hash_test_1"}},
    ]
    traces = []

    result = _compute_split_overlap(scorecards, traces)

    assert result["split_overlap_any_rate"] == 0.0
    assert result["split_overlap_pairs"]["train_valid"] == 0.0
    assert result["split_overlap_pairs"]["train_test"] == 0.0
    assert result["split_overlap_pairs"]["valid_test"] == 0.0
    assert result["notes"] is None


def test_compute_split_overlap_with_overlap():
    """Test that overlap is detected when splits share hashes."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_run_snapshot import _compute_split_overlap

    # Create mock scorecards with overlapping input_hashes
    scorecards = [
        {"meta": {"split": "train", "input_hash": "hash_shared"}},
        {"meta": {"split": "train", "input_hash": "hash_train_2"}},
        {"meta": {"split": "valid", "input_hash": "hash_shared"}},  # overlaps with train
        {"meta": {"split": "valid", "input_hash": "hash_valid_2"}},
        {"meta": {"split": "test", "input_hash": "hash_test_1"}},
    ]
    traces = []

    result = _compute_split_overlap(scorecards, traces)

    assert result["split_overlap_any_rate"] > 0.0
    assert result["split_overlap_pairs"]["train_valid"] > 0.0
    assert result["notes"] is not None
    assert "train-valid" in result["notes"]


def test_compute_split_overlap_all_same():
    """Test that 100% overlap is detected when all splits are identical."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from build_run_snapshot import _compute_split_overlap

    # Create mock scorecards where all splits have same hashes
    scorecards = [
        {"meta": {"split": "train", "input_hash": "hash_1"}},
        {"meta": {"split": "train", "input_hash": "hash_2"}},
        {"meta": {"split": "valid", "input_hash": "hash_1"}},
        {"meta": {"split": "valid", "input_hash": "hash_2"}},
        {"meta": {"split": "test", "input_hash": "hash_1"}},
        {"meta": {"split": "test", "input_hash": "hash_2"}},
    ]
    traces = []

    result = _compute_split_overlap(scorecards, traces)

    # All pairs should have 100% overlap
    assert result["split_overlap_any_rate"] == 1.0
    assert result["split_overlap_pairs"]["train_valid"] == 1.0
    assert result["split_overlap_pairs"]["train_test"] == 1.0
    assert result["split_overlap_pairs"]["valid_test"] == 1.0


# ---------- Test demo hash-based leakage prevention ----------


def test_demo_sampler_forbid_hashes():
    """Test that DemoSampler excludes demos by text hash."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.demo_sampler import DemoSampler, _compute_text_hash
    from data.datasets.loader import InternalExample

    # Create demo pool
    demo_pool = [
        InternalExample(uid="demo1", text="This is demo text 1", split="train"),
        InternalExample(uid="demo2", text="This is demo text 2", split="train"),
        InternalExample(uid="demo3", text="This is demo text 3", split="train"),
    ]

    # Create forbid hashes (hash of text that matches demo2)
    forbid_hashes = {_compute_text_hash("This is demo text 2")}

    sampler = DemoSampler(demo_pool)
    result = sampler.sample_with_stats(k=3, seed=42, forbid_hashes=forbid_hashes)

    # Should have excluded demo2
    assert result.removed_by_hash == 1
    assert len(result.demos) == 2
    demo_uids = {d.uid for d in result.demos}
    assert "demo2" not in demo_uids


def test_demo_sampler_forbid_uids_and_hashes():
    """Test that DemoSampler excludes by both UID and hash."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.demo_sampler import DemoSampler, _compute_text_hash
    from data.datasets.loader import InternalExample

    demo_pool = [
        InternalExample(uid="demo1", text="Text A", split="train"),
        InternalExample(uid="demo2", text="Text B", split="train"),
        InternalExample(uid="demo3", text="Text C", split="train"),
    ]

    forbid_uids = {"demo1"}
    forbid_hashes = {_compute_text_hash("Text B")}

    sampler = DemoSampler(demo_pool)
    result = sampler.sample_with_stats(
        k=3, seed=42, forbid_uids=forbid_uids, forbid_hashes=forbid_hashes
    )

    assert result.removed_by_uid == 1
    assert result.removed_by_hash == 1
    assert result.total_excluded == 2
    assert len(result.demos) == 1
    assert result.demos[0].uid == "demo3"


def test_compute_eval_hashes():
    """Test compute_eval_hashes utility function."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.demo_sampler import compute_eval_hashes, _compute_text_hash
    from data.datasets.loader import InternalExample

    examples = [
        InternalExample(uid="1", text="Train text", split="train"),
        InternalExample(uid="2", text="Valid text", split="valid"),
        InternalExample(uid="3", text="Test text", split="test"),
        InternalExample(uid="4", text="Another valid", split="valid"),
    ]

    # Get hashes for valid and test splits
    hashes = compute_eval_hashes(examples, {"valid", "test"})

    assert len(hashes) == 3
    assert _compute_text_hash("Valid text") in hashes
    assert _compute_text_hash("Test text") in hashes
    assert _compute_text_hash("Another valid") in hashes
    assert _compute_text_hash("Train text") not in hashes


# ---------- Test split files tracking ----------


def test_compute_split_files():
    """Test _compute_split_files detects when all splits use same file."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "experiments" / "scripts"))
    from run_experiments import _compute_split_files

    # Different files
    data_cfg_different = {
        "input_format": "csv",
        "train_file": "data/train.csv",
        "valid_file": "data/valid.csv",
        "test_file": "data/test.csv",
    }
    resolved_paths_different = {}

    result = _compute_split_files(data_cfg_different, resolved_paths_different)
    assert result["all_same"] is False

    # Same file for all splits (smoke/debug scenario)
    data_cfg_same = {
        "input_format": "csv",
        "train_file": "data/same.csv",
        "valid_file": "data/same.csv",
        "test_file": "data/same.csv",
    }

    result = _compute_split_files(data_cfg_same, {})
    assert result["all_same"] is True


# ---------- Test report_sources / blind_sources (sources-based roles) ----------


def test_schema_paper_requires_report_sources_and_blind_sources():
    """Paper run must have report_sources and blind_sources explicit."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from schemas.experiment_config_schema import validate_experiment_config

    # Paper without report_sources -> fail
    cfg_missing_sources = {
        "run_purpose": "paper",
        "data_roles": {"demo_pool": ["train"], "report_set": ["valid"], "blind_set": ["test"]},
    }
    try:
        validate_experiment_config(cfg_missing_sources)
        assert False, "expected validation error for missing report_sources"
    except Exception as e:
        assert "report_sources" in str(e).lower() or "blind_sources" in str(e).lower()

    # Paper with report_sources and blind_sources -> pass (and demo_pool disjoint from eval)
    cfg_ok = {
        "run_purpose": "paper",
        "data_roles": {
            "demo_pool": ["train"],
            "report_set": ["valid"],
            "blind_set": ["test"],
            "report_sources": ["valid_file"],
            "blind_sources": ["test_file"],
        },
    }
    validate_experiment_config(cfg_ok)


def test_check_experiment_config_eval_splits_from_sources():
    """Eval splits are derived from report_sources/blind_sources when present."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from check_experiment_config import _eval_splits_from_roles

    roles_sources = {"report_sources": ["valid_file", "test_file"], "blind_sources": ["test_file"]}
    splits = _eval_splits_from_roles(roles_sources)
    assert splits == {"valid", "test"}

    roles_set = {"report_set": ["valid"], "blind_set": ["test"]}
    splits_fallback = _eval_splits_from_roles(roles_set)
    assert splits_fallback == {"valid", "test"}


def test_intentional_failure_demo_overlap_with_eval():
    """Config with demo_pool overlapping report_sources must fail (leakage guard)."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from schemas.experiment_config_schema import validate_experiment_config

    # demo_pool contains "valid", report_sources=["valid_file"] -> eval includes "valid" -> overlap
    cfg_overlap = {
        "run_purpose": "paper",
        "data_roles": {
            "demo_pool": ["train", "valid"],
            "report_sources": ["valid_file"],
            "blind_sources": ["test_file"],
        },
    }
    try:
        validate_experiment_config(cfg_overlap)
        assert False, "expected validation error for demo/eval overlap"
    except Exception as e:
        assert "overlap" in str(e).lower() or "intersect" in str(e).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
