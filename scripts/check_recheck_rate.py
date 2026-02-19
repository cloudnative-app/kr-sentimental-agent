#!/usr/bin/env python3
"""Compute recheck_triggered_rate from outputs.jsonl (CR v2 targeted re-check)."""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description="Compute recheck_triggered_rate from outputs.jsonl")
    ap.add_argument("--input", type=Path, required=True, help="outputs.jsonl path")
    args = ap.parse_args()
    n = 0
    total_recheck = 0
    n_with_recheck = 0
    with args.input.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            meta = rec.get("meta") or {}
            c = meta.get("recheck_triggered_count", 0)
            n += 1
            total_recheck += c
            if c > 0:
                n_with_recheck += 1
    rate_samples = n_with_recheck / n if n else 0.0
    print(f"N={n} | recheck_triggered_count (total)={total_recheck} | samples_with_recheck={n_with_recheck} | recheck_triggered_rate={rate_samples:.4f}")


if __name__ == "__main__":
    main()
