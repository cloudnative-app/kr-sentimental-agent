"""
Test that real runs (use_mock=0, provider != 'mock') fail with RuntimeError
when fallback_construct is triggered.
"""
import json
import tempfile
from pathlib import Path

from schemas import ATEOutput
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured


class FakeRealBackboneClient(BackboneClient):
    """
    Simulates a real provider that always fails.
    provider is set to 'openai' (non-mock) to trigger fatal fallback behavior.
    """

    def __init__(self):
        self.provider = "openai"  # Non-mock provider
        self.model = "gpt-3.5-turbo"

    def generate(self, messages, *, temperature=None, max_tokens=None, response_format="text", mode="", text_id=""):
        # Always return invalid JSON to trigger fallback
        return "this is not valid json"


class FakeMockBackboneClient(BackboneClient):
    """
    Simulates a mock provider that fails but should NOT raise RuntimeError.
    provider is set to 'mock' to allow fallback without error.
    """

    def __init__(self):
        self.provider = "mock"
        self.model = "mock-model"

    def generate(self, messages, *, temperature=None, max_tokens=None, response_format="text", mode="", text_id=""):
        # Always return invalid JSON to trigger fallback
        return "this is not valid json"


def test_realrun_fallback_raises_runtime_error():
    """
    When provider is not 'mock' and fallback_construct is triggered,
    run_structured must raise RuntimeError.
    """
    backbone = FakeRealBackboneClient()

    with tempfile.TemporaryDirectory() as td:
        errors_file = Path(td) / "errors.jsonl"

        runtime_error_raised = False
        error_message = ""
        try:
            run_structured(
                backbone=backbone,
                system_prompt="Return valid JSON",
                user_text="sample text",
                schema=ATEOutput,
                max_retries=1,
                run_id="test_realrun",
                text_id="test_text_001",
                stage="test_stage",
                errors_path=str(errors_file),
            )
        except RuntimeError as e:
            runtime_error_raised = True
            error_message = str(e)

        # Must raise RuntimeError
        assert runtime_error_raised, "RuntimeError should be raised for real run fallback"

        # Check error message contains expected info
        assert "fatal_fallback_realrun" in error_message
        assert "openai" in error_message
        assert "test_stage" in error_message

        # Check errors.jsonl contains fatal_fallback_realrun entry
        assert errors_file.exists()
        with open(errors_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        fatal_entries = [e for e in lines if e.get("type") == "fatal_fallback_realrun"]
        assert len(fatal_entries) >= 1
        assert fatal_entries[0]["provider"] == "openai"
        assert fatal_entries[0]["stage"] == "test_stage"


def test_mock_fallback_does_not_raise():
    """
    When provider is 'mock', fallback_construct should NOT raise RuntimeError.
    This allows mock tests to complete even with invalid responses.
    """
    backbone = FakeMockBackboneClient()

    with tempfile.TemporaryDirectory() as td:
        errors_file = Path(td) / "errors.jsonl"

        # Should NOT raise - mock provider allows fallback
        result = run_structured(
            backbone=backbone,
            system_prompt="Return valid JSON",
            user_text="sample text",
            schema=ATEOutput,
            max_retries=1,
            run_id="test_mock",
            text_id="test_text_002",
            stage="test_stage",
            errors_path=str(errors_file),
        )

        # Should return a fallback model
        assert result.meta.fallback_construct_used is True
        assert result.model is not None

        # errors.jsonl should have fallback_construct but NOT fatal_fallback_realrun
        assert errors_file.exists()
        with open(errors_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        fallback_entries = [e for e in lines if e.get("type") == "fallback_construct"]
        fatal_entries = [e for e in lines if e.get("type") == "fatal_fallback_realrun"]

        assert len(fallback_entries) >= 1
        assert len(fatal_entries) == 0


def test_realrun_exception_raises_runtime_error():
    """
    When provider is not 'mock' and generate() raises an exception repeatedly,
    run_structured must raise RuntimeError.
    """

    class ExceptionBackbone(BackboneClient):
        def __init__(self):
            self.provider = "anthropic"  # Non-mock provider
            self.model = "claude-3"

        def generate(self, messages, **kwargs):
            raise ConnectionError("Simulated API failure")

    backbone = ExceptionBackbone()

    with tempfile.TemporaryDirectory() as td:
        errors_file = Path(td) / "errors.jsonl"

        runtime_error_raised = False
        error_message = ""
        try:
            run_structured(
                backbone=backbone,
                system_prompt="Return valid JSON",
                user_text="sample text",
                schema=ATEOutput,
                max_retries=2,
                run_id="test_exception",
                text_id="test_text_003",
                stage="exception_stage",
                errors_path=str(errors_file),
            )
        except RuntimeError as e:
            runtime_error_raised = True
            error_message = str(e)

        # Must raise RuntimeError
        assert runtime_error_raised, "RuntimeError should be raised for real run exception"
        assert "fatal_fallback_realrun" in error_message
        assert "anthropic" in error_message

        # Check errors.jsonl
        assert errors_file.exists()
        with open(errors_file, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        fatal_entries = [e for e in lines if e.get("type") == "fatal_fallback_realrun"]
        assert len(fatal_entries) >= 1
