import json
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from tools.llm_runner import run_structured, StructuredResult
from tools.backbone_client import BackboneClient


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


class SimpleSchema(BaseModel):
    foo: str = Field(default="x")
    bar: int = Field(..., description="required")


def test_llm_runner_retries_and_logs():
    tmpdir = Path(tempfile.mkdtemp())
    errors_path = tmpdir / "errors.jsonl"
    responses = ["not json", json.dumps({"foo": "ok"}), json.dumps({"foo": "ok", "bar": 3})]
    backbone = MockBackbone(responses)
    result = run_structured(
        backbone=backbone,
        system_prompt="{}",
        user_text="text",
        schema=SimpleSchema,
        max_retries=2,
        run_id="r1",
        text_id="t1",
        stage="s1",
        errors_path=str(errors_path),
    )
    # run_structured now returns StructuredResult
    assert isinstance(result, StructuredResult)
    assert isinstance(result.model, SimpleSchema)
    assert result.model.foo == "ok"
    assert result.model.bar == 3
    # errors.jsonl may exist with json_parse_error but not fallback_construct
    # since we eventually succeeded


def test_llm_runner_logs_failures():
    tmpdir = Path(tempfile.mkdtemp())
    errors_path = tmpdir / "errors.jsonl"
    backbone = MockBackbone(["bad"] * 3)
    result = run_structured(
        backbone=backbone,
        system_prompt="{}",
        user_text="text",
        schema=SimpleSchema,
        max_retries=1,
        run_id="r2",
        text_id="t2",
        stage="s2",
        errors_path=str(errors_path),
    )
    # run_structured now returns StructuredResult with fallback
    assert isinstance(result, StructuredResult)
    assert result.meta.fallback_construct_used is True
    assert errors_path.exists()
    data = [json.loads(line) for line in errors_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert data, "errors.jsonl should contain at least one entry"
    first = data[0]
    assert first["run_id"] == "r2"
    assert first["text_id"] == "t2"
    assert first["stage"] == "s2"
