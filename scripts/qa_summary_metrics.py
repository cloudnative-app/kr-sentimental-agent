"""
Summarize smoke_outputs.jsonl into JSON metrics per run_id.
- anchoring_success_rate: mapped / (mapped + dropped) from stage2_validator.issues
- stage2_intervention_rate: fraction with any stage2 review entries
- moderator_rule_distribution: counts of RuleA-D mentions in moderator rationale
- fallback_rate and error taxonomy: from run-scoped errors.jsonl if present
"""

import json
import sys
from collections import Counter
from pathlib import Path

SMOKE_PATH = Path("experiments/results/proposed/smoke_outputs.jsonl")


def load_smoke(path: Path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_errors(run_id: str):
    path = Path(f"experiments/results/proposed/{run_id}/errors.jsonl")
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    if not SMOKE_PATH.exists():
        print(f"missing {SMOKE_PATH}", file=sys.stderr)
        sys.exit(1)

    records = list(load_smoke(SMOKE_PATH))
    if not records:
        print("no records", file=sys.stderr)
        sys.exit(1)

    run_id = records[0].get("meta", {}).get("run_id", "unknown")

    # anchoring
    mapped = dropped = 0
    intervention = 0
    rule_counts = Counter()
    for obj in records:
        issues = obj.get("stage2_validator", {}).get("issues", []) or []
        for iss in issues:
            if "mapped_aspect_term" in iss:
                mapped += 1
            if "dropped_unanchored_aspect_term" in iss:
                dropped += 1
        trace = obj.get("process_trace", [])
        has_review = any(t.get("stage") == "stage2" and ((t.get("agent") == "ATE" and t.get("output", {}).get("aspect_review")) or (t.get("agent") == "ATSA" and t.get("output", {}).get("sentiment_review"))) for t in trace)
        if has_review:
            intervention += 1
        rationale = obj.get("moderator", {}).get("rationale", "") or ""
        for tag in ("RuleA", "RuleB", "RuleC", "RuleD"):
            if tag in rationale:
                rule_counts[tag] += 1

    anchor_total = mapped + dropped
    anchoring_success_rate = (mapped / anchor_total) if anchor_total else None
    stage2_intervention_rate = intervention / len(records)

    # errors
    errors = load_errors(run_id)
    err_counts = Counter(e.get("type", "unknown") for e in errors)
    fallback_total = err_counts.get("fallback_construct", 0)
    fallback_rate = fallback_total / len(records) if records else 0.0

    summary = {
        "run_id": run_id,
        "num_records": len(records),
        "anchoring_success_rate": anchoring_success_rate,
        "stage2_intervention_rate": stage2_intervention_rate,
        "moderator_rule_distribution": dict(rule_counts),
        "fallback_rate": fallback_rate,
        "error_taxonomy": dict(err_counts),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
