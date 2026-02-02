import json

from schemas import FinalOutputSchema, AnalysisFlags, FinalResult, ProcessTrace
from metrics.contract import (
    get_run_mode,
    get_correction_occurred,
    get_conflict_resolved,
    get_final_confidence_score,
    has_risk_detected,
    get_stage2_status,
)


def _make_payload(mode: str, risk: bool = False, stage2_status=None, flags=None):
    flags = flags or AnalysisFlags(
        correction_occurred=False,
        conflict_resolved=False,
        final_confidence_score=0.5,
        stage2_executed=mode == "proposed",
    )
    traces = []
    if risk:
        traces.append(ProcessTrace(stage="stage1", agent="Validator", input_text="t", output={"is_risk_detected": True}))
    if stage2_status:
        traces.append(
            ProcessTrace(stage="stage2", agent="status", input_text="t", output={"triplets": []}, stage_status=stage2_status)
        )
    payload = FinalOutputSchema(meta={"mode": mode}, process_trace=traces, analysis_flags=flags, final_result=FinalResult()).model_dump()
    return payload


def test_contract_fields_proposed():
    payload = _make_payload("proposed", risk=True)
    assert get_run_mode(payload) == "proposed"
    assert get_correction_occurred(payload) is False
    assert get_conflict_resolved(payload) is False
    assert has_risk_detected(payload) is True
    assert get_final_confidence_score(payload) == 0.5
    assert get_stage2_status(payload) is None


def test_contract_fields_bl1_bl2_bl3_modes():
    flags = AnalysisFlags(final_confidence_score=0.5, stage2_executed=False)
    bl1 = _make_payload("bl1", risk=False, stage2_status=None, flags=flags)
    bl2 = _make_payload("bl2", risk=True, stage2_status=None, flags=flags)
    bl3 = _make_payload("bl3", risk=False, stage2_status="not_applicable", flags=flags)

    assert get_run_mode(bl1) == "bl1"
    assert has_risk_detected(bl1) is False
    assert get_run_mode(bl2) == "bl2"
    assert has_risk_detected(bl2) is True
    assert get_run_mode(bl3) == "bl3"
    assert get_stage2_status(bl3) == "not_applicable"
    assert get_final_confidence_score(bl3) == 0.5
