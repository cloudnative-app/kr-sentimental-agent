"""
CI/QA smoke output checks.
Fails (exit 1) on:
 - missing required top-level keys
 - stage2 outputs not review-only (aspect_sentiments/aspects under stage2)
 - stage2 reviews present but aggregated stage2_ate.confidence == 0
"""

import json
import sys
from pathlib import Path

SMOKE_PATH = Path("experiments/results/proposed/smoke_outputs.jsonl")

REQUIRED_KEYS = {
    "stage1_ate",
    "stage1_atsa",
    "stage1_validator",
    "stage2_ate",
    "stage2_atsa",
    "stage2_validator",
    "moderator",
    "process_trace",
}


def load_lines(path: Path):
    if not path.exists():
        print(f"missing file: {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            yield line_no, json.loads(line)


def check_required_keys(lines):
    errors = []
    for ln, obj in lines:
        miss = REQUIRED_KEYS - obj.keys()
        if miss:
            errors.append(f"line {ln}: missing keys {sorted(miss)}")
    if errors:
        print("Required key failures:")
        for e in errors:
            print(" -", e)
        sys.exit(1)


def check_semantic_nonempty(lines, min_nonempty: int = 1):
    nonempty = 0
    for _, obj in lines:
        if obj.get("stage1_ate", {}).get("label") or obj.get("stage1_ate", {}).get("confidence", 0) > 0:
            pass
        aspects = obj.get("stage1_ate", {}).get("aspects") or []
        sentiments = obj.get("stage1_atsa", {}).get("aspect_sentiments") or []
        if aspects or sentiments:
            nonempty += 1
    if nonempty < min_nonempty:
        print(f"Semantic content failure: only {nonempty} lines with aspects/sentiments, expected >= {min_nonempty}")
        sys.exit(1)


def check_stage2_review_only(lines):
    errors = []
    for ln, obj in lines:
        for trace in obj.get("process_trace", []):
            if trace.get("stage") != "stage2":
                continue
            out = trace.get("output", {})
            agent = trace.get("agent", "")
            if agent == "ATSA" and "aspect_sentiments" in out:
                errors.append(f"line {ln}: stage2 ATSA output contains aspect_sentiments")
            if agent == "ATE" and "aspects" in out:
                errors.append(f"line {ln}: stage2 ATE output contains aspects")
    if errors:
        print("Stage2 review-only failures:")
        for e in errors:
            print(" -", e)
        sys.exit(1)


def check_confidence_after_review(lines):
    errors = []
    for ln, obj in lines:
        reviews = []
        for trace in obj.get("process_trace", []):
            if trace.get("stage") != "stage2":
                continue
            out = trace.get("output", {})
            if trace.get("agent") == "ATSA":
                reviews.extend(out.get("sentiment_review", []))
            if trace.get("agent") == "ATE":
                reviews.extend(out.get("aspect_review", []))
        if reviews and obj.get("stage2_ate", {}).get("confidence", 0) == 0:
            errors.append(f"line {ln}: review exists but stage2_ate.confidence == 0")
    if errors:
        print("Stage2 confidence failures:")
        for e in errors:
            print(" -", e)
        sys.exit(1)


def main():
    lines = list(load_lines(SMOKE_PATH))
    check_required_keys(lines)
    check_semantic_nonempty(lines, min_nonempty=1)
    check_stage2_review_only(lines)
    check_confidence_after_review(lines)
    print("qa_check_smoke: PASS")


if __name__ == "__main__":
    main()
