"""
Lightweight test runner to satisfy `python -m pytest -q` without external dependency.
Discovers tests/test_*.py and runs callables starting with `test_`.
"""

import importlib.util
import sys
from pathlib import Path
import traceback


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
        return mod
    raise ImportError(f"Cannot load {path}")


def main():
    failures = 0
    for path in sorted(Path("tests").glob("test_*.py")):
        mod = load_module(path)
        for name in dir(mod):
            if not name.startswith("test_"):
                continue
            func = getattr(mod, name)
            if callable(func):
                try:
                    func()
                except Exception:
                    failures += 1
                    print(f"FAIL: {path.name}::{name}")
                    traceback.print_exc()
    if failures:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
