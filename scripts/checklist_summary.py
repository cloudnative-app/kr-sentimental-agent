import json
from pathlib import Path


def status(label: str, state: str, note: str = ""):
    print(f"{label}: {state}" + (f" ({note})" if note else ""))


def main():
    repo = Path(__file__).resolve().parents[1]

    # Item 1: no direct LLM clients outside backbone_client.py
    banned = ("ChatOpenAI", "ChatAnthropic", "ChatGoogleGenerativeAI")
    bad_hits = []
    for path in repo.rglob("*.py"):
        if "venv" in path.parts:
            continue
        if path.name in {"backbone_client.py", "checklist_summary.py", "test_no_direct_llm_clients.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non-utf8 files
            continue
        for b in banned:
            if b in text:
                bad_hits.append(str(path))
    status("LLM client single entry", "PASS" if not bad_hits else "FAIL", ", ".join(bad_hits))

    # Item 2: smoke outputs exist (any mode)
    smoke_base = repo / "experiments" / "results"
    mode_hits = []
    for mode in ["proposed", "bl1", "bl2", "bl3"]:
        path = smoke_base / mode / "smoke_outputs.jsonl"
        if path.exists():
            mode_hits.append(mode)
    if mode_hits:
        status("Smoke outputs", "PASS", f"modes: {','.join(mode_hits)}")
    else:
        status("Smoke outputs", "SKIP", "run scripts/schema_validation_test.py --mode all")

    # Item 3: errors log presence
    errors_root = repo / "experiments" / "results"
    error_logs = sorted(str(p) for p in errors_root.rglob("errors.jsonl")) if errors_root.exists() else []
    status("Errors log", "PASS" if error_logs else "SKIP", ", ".join(error_logs) or str(errors_root / "errors.jsonl"))

    # Item 4: hard subset filter exists
    hard_file = repo / "metrics" / "hard_subset.py"
    status("Hard subset filter", "PASS" if hard_file.exists() else "FAIL")

    # Item 5: schema contract test file
    contract_test = repo / "tests" / "test_schema_contract.py"
    status("Schema contract test", "PASS" if contract_test.exists() else "FAIL")


if __name__ == "__main__":
    main()
