"""
Unit tests for build_metric_report: key-missing safety, _to_float, RQ3 table with empty struct_metrics.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

# Run from project root; scripts are not a package, so load by path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_metric_report as bmr


def test_to_float_handles_none_and_empty():
    assert bmr._to_float(None) is None
    assert bmr._to_float("") is None


def test_to_float_handles_tuple_takes_first():
    """(mean, std) or list: use first element as scalar."""
    assert bmr._to_float((0.5, 0.1)) == 0.5
    assert bmr._to_float([0.25, 0.05]) == 0.25


def test_to_float_scalar_and_string():
    assert bmr._to_float(0.42) == 0.42
    assert bmr._to_float("0.99") == 0.99


def test_build_html_with_empty_struct_metrics_succeeds():
    """Input struct_metrics={} (dummy/legacy run): HTML is generated and RQ3 cells show N/A."""
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / "metric_report.html"
        run_dir = Path(tmp)  # can be same; build_html only needs run_dir.name
        build_html = bmr.build_html
        build_html(
            run_dir=run_dir,
            manifest={"run_id": "test_run"},
            scorecards=[],
            struct_metrics={},  # key-missing: no risk_resolution_rate, guided_change_rate, unguided_drift_rate
            computed={"n": 0},
            stage2_correction={},
            transition_summary={},
            out_path=out_path,
            top_n=5,
            memory_growth_rows=None,
            memory_growth_plot_path=None,
            memory_off=True,
        )
        assert out_path.exists()
        html = out_path.read_text(encoding="utf-8")
        # RQ3 table: Risk Resolution Rate, Guided Change Rate, Unguided Drift Rate → N/A
        assert "Validator Clear Rate" in html or "Outcome Residual Risk Rate" in html
        assert "Guided Change Rate" in html
        assert "Unguided Drift Rate" in html
        # All three cells should show N/A when struct_metrics is empty
        assert html.count("N/A") >= 3
        # RQ3 note about N/A meaning
        assert "RQ3" in html and "단일 run" in html


def test_csv_report_terminology_consistent():
    """CSV key validator_clear_rate vs report label 'Validator Clear Rate': same concept (no conflict)."""
    # structural_metrics.csv uses validator_clear_rate (and deprecated risk_resolution_rate); HTML uses "Validator Clear Rate".
    kpi_row = next(r for r in bmr.KPI_LIST if r[1] == "validator_clear_rate")
    assert kpi_row[0] == "Validator Clear Rate"
