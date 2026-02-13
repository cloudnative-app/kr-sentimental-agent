"""
Export Stage1 ATSA raw output and parsed JSON for 3~5 samples (as-is).
Reads scorecards; writes derived/metrics/stage1_atsa_raw_parsed_samples.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_jsonl(path: Path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def get_trace(record: dict) -> list:
    parsed = (record.get("runtime") or {}).get("parsed_output")
    if isinstance(parsed, dict):
        return parsed.get("process_trace") or []
    return record.get("process_trace") or []


def find_stage1_atsa(record: dict) -> dict | None:
    for tr in get_trace(record):
        if (tr.get("stage") or "").lower() == "stage1" and (tr.get("agent") or "").upper() == "ATSA":
            return tr
    return None


def main() -> None:
    path = _PROJECT_ROOT / "results" / "finalexperiment_n50_seed1_c2_1__seed1_proposed" / "scorecards.jsonl"
    if not path.exists():
        print(f"Not found: {path}", file=sys.stderr)
        return
    rows = load_jsonl(path)
    n = min(5, len(rows))

    out_dir = path.parent / "derived" / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "stage1_atsa_raw_parsed_samples.md"

    lines = [
        "# Stage1 ATSA raw output (3~5 samples, as-is)",
        "",
        "Raw = LLM raw response string. Parsed = schema-parsed output (aspect_sentiments).",
        "",
    ]

    for i in range(n):
        rec = rows[i]
        text_id = (rec.get("meta") or {}).get("text_id") or (rec.get("runtime") or {}).get("uid") or f"row_{i+1}"
        atsa = find_stage1_atsa(rec)
        if not atsa:
            lines.append(f"## Sample {i+1} ({text_id})")
            lines.append("No Stage1 ATSA entry.")
            lines.append("")
            continue

        raw = (atsa.get("call_metadata") or {}).get("raw_response")
        if not raw and atsa.get("notes"):
            try:
                notes = json.loads(atsa["notes"]) if isinstance(atsa["notes"], str) else atsa["notes"]
                raw = (notes or {}).get("raw_response") or (notes or {}).get("raw_response")
            except Exception:
                raw = atsa.get("notes") if isinstance(atsa.get("notes"), str) else None
        parsed = atsa.get("output") or {}

        lines.append(f"## Sample {i+1} ({text_id})")
        lines.append("")
        lines.append("### Raw output (as-is)")
        lines.append("```")
        lines.append(raw if raw else "(none)")
        lines.append("```")
        lines.append("")
        lines.append("### Parsed JSON")
        lines.append("```json")
        lines.append(json.dumps(parsed, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
