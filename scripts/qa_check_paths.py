"""
Ensures errors.jsonl files are run-scoped: experiments/results/<bucket>/<run_id>/errors.jsonl
Fails if a top-level experiments/results/errors.jsonl exists or any errors.jsonl outside the scoped pattern.
"""

import sys
from pathlib import Path
import re

ROOT = Path("experiments/results")
PATTERN = re.compile(r"errors_(.+)\\.jsonl$")


def main():
    bad = []
    if (ROOT / "errors.jsonl").exists():
        bad.append(str(ROOT / "errors.jsonl"))
    for path in ROOT.rglob("errors_*.jsonl"):
        rel = path.relative_to(ROOT)
        parts = rel.parts
        # expect at least 3 parts: bucket/run_id/errors_<run_id>.jsonl
        if len(parts) < 3 or not PATTERN.match(parts[-1]):
            bad.append(str(path))
    if bad:
        print("Non-scoped errors files detected:")
        for b in bad:
            print(" -", b)
        sys.exit(1)
    print("qa_check_paths: PASS")


if __name__ == "__main__":
    main()
