import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def categorize(error: str) -> str:
    err_lower = error.lower()
    if "429" in err_lower or "rate" in err_lower:
        return "429_rate_limit"
    if "timeout" in err_lower or "timed out" in err_lower:
        return "timeout"
    if "jsondecodeerror" in err_lower or "parse" in err_lower:
        return "parse_json"
    if "validationerror" in err_lower or "validate" in err_lower:
        return "schema_validation"
    return "other"


def load_errors(path: Path):
    counts = Counter()
    text_ids = defaultdict(list)
    if not path.exists():
        return counts, text_ids
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        error_msg = str(obj.get("error", ""))
        cat = categorize(error_msg)
        counts[cat] += 1
        text_ids[cat].append(obj.get("text_id", "unknown"))
    return counts, text_ids


def main():
    parser = argparse.ArgumentParser(description="Summarize errors.jsonl and suggest repro samples.")
    parser.add_argument("--errors", type=str, default="experiments/results/errors.jsonl", help="Path to errors.jsonl")
    parser.add_argument("--top", type=int, default=3, help="Top N text_ids per category")
    args = parser.parse_args()

    counts, text_ids = load_errors(Path(args.errors))
    total = sum(counts.values())
    if total == 0:
        print("No errors found.")
        return

    print(f"Total errors: {total}")
    for cat, cnt in counts.most_common():
        sample_ids = text_ids[cat][: args.top]
        print(f"- {cat}: {cnt} (sample text_id={sample_ids})")


if __name__ == "__main__":
    main()
