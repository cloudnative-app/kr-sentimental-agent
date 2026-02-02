from metrics.hard_subset import filter_hard_examples


def test_filter_hard_examples():
    data = [
        {"is_risk_detected": True, "risk_type": "type", "scope": "scope", "proposal": "fix"},
        {"is_risk_detected": True, "risk_type": "", "scope": "scope", "proposal": "fix"},
        {"is_risk_detected": False, "risk_type": "type", "scope": "scope", "proposal": "fix"},
    ]
    res = filter_hard_examples(data)
    assert len(res) == 1
    assert res[0]["proposal"] == "fix"
