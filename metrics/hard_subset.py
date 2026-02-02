from __future__ import annotations

from typing import List, Dict

from metrics.contract import has_risk_detected


def filter_hard_examples(examples: List[Dict]) -> List[Dict]:
    """
    Return examples where risk was detected.
    Compatibility: if risk_type/scope/proposal exist, require them to be non-empty;
    otherwise include the example if any validator risk is detected.
    """
    hard = []
    for ex in examples:
        # Backward compat: allow top-level is_risk_detected
        root_flag = ex.get("is_risk_detected")
        detected = has_risk_detected(ex) or (root_flag is True)
        if not detected:
            continue
        # Optional stricter fields
        if {"risk_type", "scope", "proposal"}.issubset(ex.keys()):
            if ex.get("risk_type") and ex.get("scope") and ex.get("proposal"):
                hard.append(ex)
        else:
            hard.append(ex)
    return hard
