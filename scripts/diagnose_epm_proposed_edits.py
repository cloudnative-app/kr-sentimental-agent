#!/usr/bin/env python3
"""
EPM proposed_edits가 비어 있는 케이스 점검: debate 단계 raw_response vs 파싱 결과.

- traces.jsonl 또는 scorecards(process_trace)에서 debate/EPM 턴을 찾음
- output.proposed_edits 길이 vs raw_response에 "set_polarity" 포함 여부로
  "실제로 빈 응답" vs "파서 누락" 구분

Usage:
  python scripts/diagnose_epm_proposed_edits.py --run_dir results/experiment_mini4_validation_c2_t0_proposed
  python scripts/diagnose_epm_proposed_edits.py --traces results/experiment_mini4_validation_c2_t0_proposed/traces.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _get_stages(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """stages from traces or process_trace from scorecard."""
    stages = row.get("stages")
    if stages:
        return stages
    runtime = row.get("runtime") or {}
    parsed = runtime.get("parsed_output")
    if isinstance(parsed, dict):
        return parsed.get("process_trace") or []
    return row.get("process_trace") or []


def main() -> int:
    ap = argparse.ArgumentParser(description="EPM proposed_edits empty: raw vs parser")
    ap.add_argument("--run_dir", type=str, default="", help="e.g. results/experiment_mini4_validation_c2_t0_proposed")
    ap.add_argument("--traces", type=str, default="", help="path to traces.jsonl (overrides run_dir)")
    ap.add_argument("--scorecards", type=str, default="", help="path to scorecards.jsonl (overrides run_dir)")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    if args.traces:
        traces_path = root / args.traces
        if not traces_path.is_absolute():
            traces_path = Path(args.traces)
        rows = _load_jsonl(traces_path)
    elif args.scorecards:
        sc_path = root / args.scorecards
        if not sc_path.is_absolute():
            sc_path = Path(args.scorecards)
        rows = _load_jsonl(sc_path)
    elif args.run_dir:
        run_dir = root / args.run_dir
        if not run_dir.is_dir():
            run_dir = Path(args.run_dir)
        traces_path = run_dir / "traces.jsonl"
        if traces_path.exists():
            rows = _load_jsonl(traces_path)
        else:
            rows = _load_jsonl(run_dir / "scorecards.jsonl")
    else:
        print("Provide --run_dir or --traces or --scorecards", file=sys.stderr)
        return 1

    empty_but_raw_has = 0
    empty_and_raw_empty = 0
    non_empty = 0
    lines: List[str] = []

    for i, row in enumerate(rows):
        uid = row.get("uid") or (row.get("meta") or {}).get("text_id") or f"row{i}"
        stages = _get_stages(row)
        for s in stages:
            if (s.get("stage") or "").lower() != "debate" or (s.get("agent") or "").upper() != "EPM":
                continue
            out = s.get("output") or {}
            edits = out.get("proposed_edits") or []
            raw = (s.get("call_metadata") or {}).get("raw_response") or ""
            raw_has_set_polarity = "set_polarity" in raw or '"op":' in raw and "polarity" in raw
            n_edits = len(edits)
            if n_edits == 0:
                if raw_has_set_polarity:
                    empty_but_raw_has += 1
                    lines.append(f"  [parser?] uid={uid} EPM proposed_edits=0 but raw_response contains set_polarity/patch")
                else:
                    empty_and_raw_empty += 1
                    lines.append(f"  [agent] uid={uid} EPM proposed_edits=0, raw has no set_polarity (EPM gave no edits)")
            else:
                non_empty += 1
                lines.append(f"  uid={uid} EPM proposed_edits={n_edits} (ok)")
            break
        else:
            lines.append(f"  uid={uid} no debate/EPM turn in trace")

    print("EPM proposed_edits diagnostic")
    print("  non_empty:", non_empty)
    print("  empty_but_raw_has_set_polarity (parser suspect):", empty_but_raw_has)
    print("  empty_and_raw_empty (agent gave no edits):", empty_and_raw_empty)
    for line in lines[:20]:
        print(line)
    if len(lines) > 20:
        print("  ...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
