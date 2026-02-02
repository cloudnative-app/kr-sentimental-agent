import json
import tempfile
from pathlib import Path

from agents.supervisor_agent import SupervisorAgent
from schemas import ATEOutput, FinalOutputSchema
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample


class MockBackboneClient(BackboneClient):
    """Backbone that returns a predefined sequence of responses."""

    def __init__(self, responses):
        self.responses = responses
        self.idx = 0
        self.provider = "mock"  # Mark as mock to avoid RuntimeError on fallback
        self.model = "mock-model"

    def generate(self, messages, *, temperature=None, max_tokens=None, response_format="text", mode="", text_id=""):
        resp = self.responses[self.idx % len(self.responses)]
        self.idx += 1
        return resp


def test_supervisor_always_runs_stage2_with_repair():
    # Sequence: bad JSON -> missing field -> valid JSON
    responses = [
        "not json",
        json.dumps({"confidence": 0.4, "rationale": "missing label"}),
        json.dumps({"label": "neutral", "confidence": 0.9, "rationale": "ok"}),
    ]
    mock_backbone = MockBackboneClient(responses)

    # Patch run_structured to log errors to tmp and reuse across agents.
    import tools.llm_runner as runner

    orig_run_structured = runner.run_structured

    with tempfile.TemporaryDirectory() as td:
        errors_file = Path(td) / "errors.jsonl"

        def patched_run_structured(*args, **kwargs):
            kwargs.setdefault("errors_path", str(errors_file))
            return orig_run_structured(*args, **kwargs)

        # Manual patching
        runner.run_structured = patched_run_structured
        import agents.specialized_agents.ate_agent as ate_mod
        import agents.specialized_agents.atsa_agent as atsa_mod
        import agents.specialized_agents.validator_agent as val_mod

        ate_mod.run_structured = patched_run_structured
        atsa_mod.run_structured = patched_run_structured
        val_mod.run_structured = patched_run_structured

        supervisor = SupervisorAgent(backbone=mock_backbone, run_id="test_run")
        example = InternalExample(uid="ex1", text="sample text for schema contract")
        result = supervisor.run(example)

        validated = FinalOutputSchema.model_validate(result.model_dump())

        stages = {t.stage for t in validated.process_trace}
        assert "stage2" in stages
        stage2_agents = {t.agent for t in validated.process_trace if t.stage == "stage2"}
        assert {"ATE", "ATSA", "Validator"}.issubset(stage2_agents)
        assert validated.analysis_flags.stage2_executed is True

        # Force a failure to ensure errors.jsonl is populated
        fail_backbone = MockBackboneClient(["still bad"])
        _ = patched_run_structured(
            backbone=fail_backbone,
            system_prompt="{}",
            user_text="text",
            schema=ATEOutput,
            max_retries=1,
            run_id="fail",
            text_id="failtext",
            stage="test",
            errors_path=str(errors_file),
        )

        assert errors_file.exists()
        with open(errors_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) >= 1



def test_bl1_baseline_wraps_final_output():
    backbone = MockBackboneClient(
        [
            "raw positive about service",  # free-form BL1 text
            json.dumps(
                {
                    "aspects": [
                        {
                            "term": "service",
                            "polarity": "positive",
                            "evidence": "great service",
                            "confidence": 0.8,
                            "rationale": "mentions great",
                            "span": {"start": 0, "end": 7},
                        }
                    ]
                }
            ),
        ]
    )
    from agents.baseline_runner import BaselineRunner

    runner = BaselineRunner(mode="bl1", backbone=backbone, run_id="bltest")
    result = runner.run(InternalExample(uid="b1", text="this is a good sample"))
    validated = FinalOutputSchema.model_validate(result.model_dump())
    assert validated.meta.get("mode") == "bl1"
    assert validated.analysis_flags.stage2_executed is False
    assert validated.analysis_flags.correction_occurred is False
    assert validated.stage1_ate.label in {"positive", "neutral", "negative"}


def test_resolve_run_mode_priority():
    from evaluation.baselines import resolve_run_mode

    assert resolve_run_mode("cli", "env", "cfg") == "cli"
    assert resolve_run_mode(None, "env", "cfg") == "env"
    assert resolve_run_mode(None, None, "cfg") == "cfg"
    assert resolve_run_mode(None, None, None) == "proposed"
