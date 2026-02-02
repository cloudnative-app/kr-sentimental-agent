#!/usr/bin/env python3
"""
런 디렉터리 검증 및 RUN SUMMARY 출력.

- manifest.json + outputs.jsonl + scorecards.jsonl 기반으로
  purpose, loaded_counts, processing_splits/count, outputs(total_lines, unique_uid, errors), artifacts 출력.
- --fail_fast 시: processing_splits == ['valid'], processing_count == valid_count, unique_uid == processing_count
  불일치면 즉시 exit 1 (덮어쓰기·중복·실패 누락 방지).

Usage:
  python scripts/run_summary.py --run_dir results/experiment_mini2__seed42_proposed
  python scripts/run_summary.py --run_dir results/experiment_mini2__seed42_proposed --fail_fast
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _uid_from_output(row: Dict[str, Any]) -> str | None:
    meta = row.get("meta") or {}
    return meta.get("uid") or meta.get("text_id") or row.get("uid")


def _is_error_row(row: Dict[str, Any]) -> bool:
    """True if parse_failed or generate_failed (placeholder/fallback)."""
    flags = row.get("analysis_flags") or {}
    if isinstance(flags, dict):
        if flags.get("parse_failed") or flags.get("generate_failed"):
            return True
    meta = row.get("meta") or {}
    if meta.get("parse_failed") or meta.get("generate_failed"):
        return True
    # scorecard-style entry
    fl = row.get("flags") or {}
    if fl.get("parse_failed") or fl.get("generate_failed"):
        return True
    return False


def collect_run_summary(run_dir: Path) -> Dict[str, Any]:
    run_dir = run_dir.resolve()
    manifest_path = run_dir / "manifest.json"
    outputs_path = run_dir / "outputs.jsonl"
    scorecards_path = run_dir / "scorecards.jsonl"

    manifest = _load_json(manifest_path)
    outputs_rows = _load_jsonl(outputs_path)
    scorecards_rows = _load_jsonl(scorecards_path)

    # From manifest
    purpose = (manifest or {}).get("purpose") or "unknown"
    mode = (manifest or {}).get("mode") or "unknown"
    backbone = (manifest or {}).get("backbone") or {}
    model = backbone.get("model") or "unknown"
    seed = backbone.get("seed")
    if seed is None and manifest:
        # Infer from run_id e.g. experiment_mini2__seed42_proposed
        run_id = manifest.get("run_id") or ""
        if "__seed" in run_id:
            try:
                tail = run_id.split("__seed")[-1]
                seed = int(tail.split("_")[0])
            except (ValueError, IndexError):
                pass
    dataset = (manifest or {}).get("dataset") or {}
    split_counts = dataset.get("split_counts") or {}
    train_c = split_counts.get("train")
    valid_c = split_counts.get("valid")
    test_c = split_counts.get("test")
    processing_splits = dataset.get("processing_splits")
    processing_count = dataset.get("processing_count")

    # From outputs
    total_lines = len(outputs_rows)
    uids: Set[str] = set()
    for row in outputs_rows:
        uid = _uid_from_output(row)
        if uid:
            uids.add(uid)
    unique_uid = len(uids)
    errors = sum(1 for row in outputs_rows if _is_error_row(row))

    # From scorecards: split=="valid" unique uid count (확정용)
    valid_uids: Set[str] = set()
    for row in scorecards_rows:
        meta = row.get("meta") or {}
        if (meta.get("split") or "").strip().lower() == "valid":
            uid = meta.get("text_id") or meta.get("uid") or row.get("uid")
            if uid:
                valid_uids.add(uid)
    valid_unique_uid = len(valid_uids)

    artifacts = []
    if outputs_path.exists():
        artifacts.append("outputs.jsonl")
    if scorecards_path.exists():
        artifacts.append("scorecards.jsonl")
    if manifest_path.exists():
        artifacts.append("manifest.json")

    return {
        "run_dir": str(run_dir),
        "purpose": purpose,
        "mode": mode,
        "model": model,
        "seed": seed,
        "loaded_counts": {"train": train_c, "valid": valid_c, "test": test_c},
        "processing_splits": processing_splits,
        "processing_count": processing_count,
        "total_lines": total_lines,
        "unique_uid": unique_uid,
        "errors": errors,
        "valid_unique_uid": valid_unique_uid,
        "artifacts": artifacts,
    }


def print_run_summary(summary: Dict[str, Any]) -> None:
    purpose = summary.get("purpose") or "unknown"
    mode = summary.get("mode") or "unknown"
    model = summary.get("model") or "unknown"
    seed = summary.get("seed")
    seed_str = str(seed) if seed is not None else "N/A"
    lc = summary.get("loaded_counts") or {}
    train_c = lc.get("train") if lc.get("train") is not None else "N/A"
    valid_c = lc.get("valid") if lc.get("valid") is not None else "N/A"
    test_c = lc.get("test") if lc.get("test") is not None else "N/A"
    splits = summary.get("processing_splits")
    proc_count = summary.get("processing_count")
    total_lines = summary.get("total_lines", 0)
    unique_uid = summary.get("unique_uid", 0)
    errors = summary.get("errors", 0)
    artifacts = summary.get("artifacts") or []

    print("[RUN SUMMARY]")
    print(f"purpose={purpose} | mode={mode} | model={model} | seed={seed_str}")
    print(f"loaded_counts: train={train_c} valid={valid_c} test={test_c}")
    print(f"processing: splits={splits} count={proc_count} (policy=P1 eval-only)")
    print(f"outputs: total_lines={total_lines} unique_uid={unique_uid} errors={errors}")
    if summary.get("valid_unique_uid") is not None:
        print(f"scorecards split=valid unique_uid={summary['valid_unique_uid']}")
    print(f"artifacts: {' '.join(artifacts)}")


def fail_fast_checks(summary: Dict[str, Any], run_dir: Path) -> List[str]:
    """Return list of failure reasons; empty if all pass."""
    failures: List[str] = []
    splits = summary.get("processing_splits")
    proc_count = summary.get("processing_count")
    valid_count = (summary.get("loaded_counts") or {}).get("valid")
    unique_uid = summary.get("unique_uid", 0)
    valid_unique = summary.get("valid_unique_uid")

    if splits is not None and splits != ["valid"]:
        failures.append(f"processing_splits == ['valid'] required; got {splits}")
    if proc_count is not None and valid_count is not None and proc_count != valid_count:
        failures.append(f"processing_count ({proc_count}) != manifest.split_counts.valid ({valid_count})")
    if proc_count is not None and unique_uid != proc_count:
        failures.append(f"outputs unique_uid ({unique_uid}) != processing_count ({proc_count})")
    if valid_unique is not None and proc_count is not None and valid_unique != proc_count:
        failures.append(f"scorecards split=valid unique_uid ({valid_unique}) != processing_count ({proc_count})")

    return failures


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run directory verification and RUN SUMMARY output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--run_dir", type=str, required=True, help="Path to results/<run_id>_<mode>")
    ap.add_argument("--fail_fast", action="store_true", help="Exit 1 if processing_splits/count or unique_uid checks fail")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = PROJECT_ROOT / run_dir

    if not run_dir.is_dir():
        print(f"[ERROR] Not a directory: {run_dir}", file=sys.stderr)
        return 1

    summary = collect_run_summary(run_dir)
    print_run_summary(summary)

    if args.fail_fast:
        failures = fail_fast_checks(summary, run_dir)
        if failures:
            print("\n[FAIL-FAST]", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
