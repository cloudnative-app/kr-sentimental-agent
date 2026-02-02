from __future__ import annotations

"""
Metric input contract for FinalOutputSchema consumers.

Expected fields (payload is FinalOutputSchema.model_dump()):
- meta.mode | meta.run_mode: str in {"proposed","bl1","bl2","bl3"} (used to identify baseline vs proposed)
- process_trace: list of ProcessTrace dicts. Validator-related outputs may include:
    * output.is_risk_detected: bool (preferred)
    * output.validator_intervention.is_risk_detected: bool (fallback)
    * output.structural_risks: list (non-empty implies risk detected)
    * process_trace items may include stage_status, e.g., "not_applicable" for stage2 in BL3.
- analysis_flags:
    * correction_occurred: bool
    * conflict_resolved: bool
    * final_confidence_score: float
    * stage2_executed: bool

All metrics should read ONLY these fields; missing/None defaults to safe fallbacks.
"""

from typing import Any, Dict, List, Optional


def _get_process_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    traces = payload.get("process_trace", [])
    return traces if isinstance(traces, list) else []


def get_run_mode(payload: Dict[str, Any]) -> str:
    meta = payload.get("meta") or {}
    return (meta.get("run_mode") or meta.get("mode") or "proposed").lower()


def get_correction_occurred(payload: Dict[str, Any]) -> bool:
    flags = payload.get("analysis_flags") or {}
    return bool(flags.get("correction_occurred", False))


def get_conflict_resolved(payload: Dict[str, Any]) -> bool:
    flags = payload.get("analysis_flags") or {}
    return bool(flags.get("conflict_resolved", False))


def get_final_confidence_score(payload: Dict[str, Any]) -> float:
    flags = payload.get("analysis_flags") or {}
    try:
        return float(flags.get("final_confidence_score", 0.0))
    except Exception:
        return 0.0


def has_risk_detected(payload: Dict[str, Any]) -> bool:
    """
    True if any validator trace reports risk.
    Preferred: output.is_risk_detected == True
    Fallback: output.validator_intervention.is_risk_detected == True
              or structural_risks list is non-empty
    """
    for trace in _get_process_trace(payload):
        out = trace.get("output", {}) or {}
        if out.get("is_risk_detected") is True:
            return True
        vi = out.get("validator_intervention") or {}
        if isinstance(vi, dict) and vi.get("is_risk_detected") is True:
            return True
        risks = out.get("structural_risks") or []
        if isinstance(risks, list) and len(risks) > 0:
            return True
    return False


def get_stage2_status(payload: Dict[str, Any]) -> Optional[str]:
    """Return stage_status for any stage2 trace if present (e.g., 'not_applicable')."""
    for trace in _get_process_trace(payload):
        if trace.get("stage") == "stage2":
            if trace.get("stage_status"):
                return trace["stage_status"]
    return None
