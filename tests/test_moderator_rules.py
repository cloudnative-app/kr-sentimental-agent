from schemas import ATEOutput, ATSAOutput, ValidatorOutput, Span
from agents.specialized_agents import Moderator
import math


def make_span(start, end):
    return Span(start=start, end=end)


def test_iou_79_no_alignment():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 10))
    s2_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s2_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(2, 11))  # IoU ~0.79
    val = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert math.isclose(res.confidence, 0.6, rel_tol=1e-6)


def test_iou_80_alignment():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 10))
    s2_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s2_atsa = ATSAOutput(label="pos", confidence=0.8, rationale="", span=make_span(1, 9))  # IoU 0.8
    val = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert math.isclose(res.confidence, (0.6 + 0.8) / 2, rel_tol=1e-6)


def test_iou_81_alignment():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.5, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.7, rationale="", span=make_span(0, 10))
    s2_ate = ATEOutput(label="pos", confidence=0.5, rationale="")
    s2_atsa = ATSAOutput(label="pos", confidence=0.9, rationale="", span=make_span(1, 9))
    val = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert math.isclose(res.confidence, (0.5 + 0.9) / 2, rel_tol=1e-6)


def test_stage2_drop_0_19_allows_stage2():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 5))
    s2_ate = ATEOutput(label="neg", confidence=0.41, rationale="")  # drop 0.19
    s2_atsa = ATSAOutput(label="neg", confidence=0.5, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert res.final_label == "neg"


def test_stage2_drop_0_2_keeps_stage1():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.65, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 5))
    s2_ate = ATEOutput(label="neg", confidence=0.45, rationale="")  # drop 0.20
    s2_atsa = ATSAOutput(label="neg", confidence=0.5, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert res.final_label == "pos"


def test_stage2_drop_0_21_keeps_stage1():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.7, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 5))
    s2_ate = ATEOutput(label="neg", confidence=0.49, rationale="")  # drop 0.21
    s2_atsa = ATSAOutput(label="neg", confidence=0.5, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert res.final_label == "pos"


def test_validator_veto_negation():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.7, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 5))
    s2_ate = ATEOutput(label="pos", confidence=0.75, rationale="")
    s2_atsa = ATSAOutput(label="pos", confidence=0.65, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label="neg", issues=["NEGATION scope"], confidence=0.9)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert res.final_label == "neg"


def test_validator_veto_irony():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.7, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.6, rationale="", span=make_span(0, 5))
    s2_ate = ATEOutput(label="pos", confidence=0.75, rationale="")
    s2_atsa = ATSAOutput(label="pos", confidence=0.65, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label="neg", issues=["irony detected"], confidence=0.8)
    res = mod.decide(s1_ate, s1_atsa, val, s2_ate, s2_atsa)
    assert res.final_label == "neg"


def test_conf_diff_0_09_prefers_ate():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.62, rationale="")
    s1_atsa = ATSAOutput(label="neg", confidence=0.53, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val)
    assert res.final_label == "pos"


def test_conf_diff_0_1_prefers_higher():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s1_atsa = ATSAOutput(label="neg", confidence=0.7, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val)
    assert res.final_label == "neg"


def test_conf_diff_0_11_prefers_higher():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.6, rationale="")
    s1_atsa = ATSAOutput(label="neg", confidence=0.71, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=False, agrees_with_atsa=False, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val)
    assert res.final_label == "neg"


def test_default_rule_no_change():
    mod = Moderator()
    s1_ate = ATEOutput(label="pos", confidence=0.55, rationale="")
    s1_atsa = ATSAOutput(label="pos", confidence=0.5, rationale="", span=make_span(0, 5))
    val = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=[], confidence=0.5)
    res = mod.decide(s1_ate, s1_atsa, val)
    assert res.final_label == "pos"
