import pathlib


def test_no_direct_llm_clients():
    root = pathlib.Path(__file__).resolve().parents[1]
    banned = ("ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI")
    for path in root.rglob("*.py"):
        # Allow backbone_client to hold provider implementations
        if "venv" in path.parts:
            continue
        if path.name in {"backbone_client.py", "checklist_summary.py", "test_no_direct_llm_clients.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        for b in banned:
            assert b not in text, f"Direct LLM client '{b}' found in {path}"
