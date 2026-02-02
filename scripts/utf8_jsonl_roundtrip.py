"""
Quick UTF-8 JSONL round-trip sanity check, focused on Windows newline handling.
Run with: python scripts/utf8_jsonl_roundtrip.py
"""

import json
import tempfile
from pathlib import Path


def run_roundtrip() -> None:
    sample = {"text_id": "utf8_check", "raw_response": "한글 응답"}

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "utf8_check.jsonl"

        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        with open(path, "r", encoding="utf-8") as f:
            parsed = [json.loads(line) for line in f if line.strip()]

        assert parsed and parsed[0]["raw_response"] == sample["raw_response"], "Round-trip mismatch for UTF-8 text"

        raw_bytes = path.read_bytes()
        assert raw_bytes.endswith(b"\n"), "File must end with newline"
        assert b"\r\n" not in raw_bytes, "Newlines should be '\\n' only when newline='\\n'"

    print("UTF-8 JSONL round-trip succeeded on this platform.")


if __name__ == "__main__":
    run_roundtrip()
