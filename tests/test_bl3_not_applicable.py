import json
import tempfile
from tools.backbone_client import BackboneClient
from baselines.bl3 import run_bl3_stage1_only
from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from schemas import FinalOutputSchema


class MockBackbone(BackboneClient):
    def __init__(self, responses):
        self.responses = responses
        self.idx = 0
        self.provider = "mock"  # Mark as mock to avoid RuntimeError on fallback
        self.model = "mock-model"

    def generate(self, messages, *, temperature=None, max_tokens=None, response_format="text", mode="", text_id=""):
        resp = self.responses[self.idx % len(self.responses)]
        self.idx += 1
        return resp


def test_bl3_marks_stage2_not_applicable():
    # Responses for: ATE stage1 (aspects), ATSA stage1 (sentiments), Validator stage1 (risks)
    responses = [
        json.dumps({"aspects": [{"term": "service", "span": {"start": 0, "end": 7}, "confidence": 0.7, "rationale": "ok"}]}),
        json.dumps(
            {
                "aspect_sentiments": [
                    {
                        "aspect_term": {"term": "great", "span": {"start": 15, "end": 20}},
                        "polarity": "positive",
                        "confidence": 0.8,
                        "evidence": "great service",
                        "polarity_distribution": {"pos": 0.8},
                        "is_implicit": False,
                    }
                ]
            }
        ),
        json.dumps({"structural_risks": [], "consistency_score": 0.5, "correction_proposals": []}),
    ]
    mock_backbone = MockBackbone(responses)

    ate = ATEAgent(mock_backbone)
    atsa = ATSAAgent(mock_backbone)
    validator = ValidatorAgent(mock_backbone)
    moderator = Moderator()

    result = run_bl3_stage1_only(
        text="great service",
        text_id="bl3case",
        run_id="bl3test",
        ate_agent=ate,
        atsa_agent=atsa,
        validator=validator,
        moderator=moderator,
    )
    validated = FinalOutputSchema.model_validate(result.model_dump())
    assert validated.analysis_flags.stage2_executed is False
    stage2_status = [t for t in validated.process_trace if t.stage == "stage2"]
    assert stage2_status, "stage2 status trace missing"
    assert stage2_status[0].stage_status == "not_applicable"
    assert stage2_status[0].output.get("triplets") == []
    assert validated.stage2_ate is None
    assert validated.stage2_atsa is None
    assert validated.stage2_validator is None
