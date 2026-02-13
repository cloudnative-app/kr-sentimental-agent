from agents.specialized_agents.validator_agent import ValidatorAgent
from schemas import StructuralValidatorStage1Schema
from schemas.agent_outputs import StructuralRiskItem, CorrectionProposal, Span
from tools.llm_runner import StructuredResult, StructuredResultMeta


def _build_structured_result():
    model = StructuralValidatorStage1Schema(
        structural_risks=[
            StructuralRiskItem(type="NEGATION", scope=Span(start=0, end=2), severity="medium", description="hallucinated"),
            StructuralRiskItem(type="CONSISTENCY", scope=Span(start=0, end=1), severity="low", description="ok"),
        ],
        correction_proposals=[
            CorrectionProposal(target_aspect="서비스", proposal_type="FLIP_POLARITY", rationale="due to negation"),
            CorrectionProposal(target_aspect="서비스", proposal_type="KEEP", rationale="ok"),
        ],
    )
    return StructuredResult(model=model, meta=StructuredResultMeta())


def test_negation_gate_removes_negation_when_no_trigger():
    agent = ValidatorAgent()
    sr = _build_structured_result()

    gated = agent._apply_negation_gate("서비스가 매우 좋다", sr, language_code="ko")

    risk_types = {r.type for r in gated.model.structural_risks}
    prop_types = {p.proposal_type for p in gated.model.correction_proposals}

    assert "NEGATION" not in risk_types
    assert "FLIP_POLARITY" not in prop_types
    assert "negation_suppressed" in (gated.meta.error or "")


def test_negation_gate_keeps_negation_when_trigger_present():
    agent = ValidatorAgent()
    sr = _build_structured_result()

    gated = agent._apply_negation_gate("서비스가 좋지 않다", sr, language_code="ko")

    risk_types = {r.type for r in gated.model.structural_risks}
    prop_types = {p.proposal_type for p in gated.model.correction_proposals}

    assert "NEGATION" in risk_types
    assert "FLIP_POLARITY" in prop_types
