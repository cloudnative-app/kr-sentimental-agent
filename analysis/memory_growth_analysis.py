#!/usr/bin/env python3
"""
Memory Growth Curve aggregation — post-hoc analysis of episodic memory utilization.

This script analyzes within-run episodic memory utilization dynamics.
It does NOT measure model learning or parameter updates.
All metrics are derived from post-hoc case traces.

Purpose: Observe accumulation, usage, and effect of episodic memory over time
within a run. Primary metrics: risk/usage/stability; optional auxiliary: accuracy/F1
when present in trace or merged from scorecards. Input: CaseTrace JSONL only.

Usage:
  python analysis/memory_growth_analysis.py --trace results/<run_id>/traces.jsonl --window 50 --out results/<run_id>/memory_growth_metrics.jsonl
  python analysis/memory_growth_analysis.py --trace traces.jsonl --window 50 --memory_mode on --out memory_growth_metrics.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# 1) Input: flat format (required fields) or nested CaseTraceV1_1 → normalize
# -----------------------------------------------------------------------------

REQUIRED_FLAT_KEYS = (
    "case_id",
    "sample_index",
    "memory_mode",
    "advisories_present",
    "override_applied",
)


def _is_nested_case_trace(obj: Dict[str, Any]) -> bool:
    return "run_meta" in obj and "risk" in obj and isinstance(obj.get("risk"), dict)


def _condition_to_memory_mode(condition: str) -> str:
    m = {"C1": "off", "C2": "on", "C2_silent": "silent"}
    return m.get(condition, condition)


def normalize_to_flat(line_index: int, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert one JSONL record to flat format for aggregation.
    Accepts: (1) user-specified flat format, (2) nested CaseTraceV1_1.
    """
    if _is_nested_case_trace(raw):
        run_meta = raw.get("run_meta") or {}
        condition = run_meta.get("condition") or ""
        memory_mode = run_meta.get("memory_mode") or _condition_to_memory_mode(condition)
        risk = raw.get("risk") or {}
        override = raw.get("override") or {}
        memory_bundle = raw.get("memory_bundle") or {}
        retrieved = memory_bundle.get("retrieved") or []
        advisories_present = bool(retrieved)
        advisories_ids = [
            a.get("advisory_id") or a.get("id", "")
            for a in retrieved
            if isinstance(a, dict)
        ]
        return {
            "case_id": raw.get("case_id") or "",
            "sample_index": raw.get("sample_index") if raw.get("sample_index") is not None else line_index,
            "memory_mode": memory_mode,
            "store_size_after": raw.get("store_size_after"),
            "advisories_present": advisories_present,
            "advisories_ids": advisories_ids,
            "retrieval_k_returned": len(retrieved),
            "override_applied": bool(override.get("applied", False)),
            "risk_before": {
                "flagged": risk.get("flagged", False),
                "residual": risk.get("residual", False),
                "severity": float(risk.get("severity_before", 0.0)),
            },
            "risk_after": {
                "flagged": risk.get("flagged", False),
                "residual": risk.get("residual", False),
                "severity": float(risk.get("severity_after", 0.0)),
            },
            "accepted_changes": override.get("accepted_changes") or [],
            "rejected_changes": override.get("rejected_changes") or [],
        }
    # Assume flat format or minimal trace (e.g. run_experiments _build_case_trace: uid, stages, final_result, no run_meta)
    flat = dict(raw)
    if "case_id" not in flat:
        flat["case_id"] = flat.get("uid") or ""
    if "sample_index" not in flat:
        flat["sample_index"] = line_index
    if "memory_mode" not in flat:
        flat["memory_mode"] = _condition_to_memory_mode((flat.get("run_meta") or {}).get("condition", "")) if flat.get("run_meta") else "off"
    if "advisories_present" not in flat:
        flat["advisories_present"] = False
    if "override_applied" not in flat:
        flat["override_applied"] = False
    # Ensure risk_before/risk_after have severity for flat format (may use severity_before/severity_after at top level)
    if "risk_before" not in flat and ("severity_before" in flat or "risk" in flat):
        r = flat.get("risk") or {}
        flat["risk_before"] = {"flagged": r.get("flagged"), "residual": r.get("residual"), "severity": float(r.get("severity_before", 0.0))}
    if "risk_after" not in flat and ("severity_after" in flat or "risk" in flat):
        r = flat.get("risk") or {}
        flat["risk_after"] = {"flagged": r.get("flagged"), "residual": r.get("residual"), "severity": float(r.get("severity_after", 0.0))}
    if "risk_before" not in flat:
        flat["risk_before"] = {"flagged": False, "residual": False, "severity": float(flat.get("severity_before", 0.0))}
    if "risk_after" not in flat:
        flat["risk_after"] = {"flagged": False, "residual": False, "severity": float(flat.get("severity_after", 0.0))}
    if "advisories_ids" not in flat:
        flat["advisories_ids"] = []
    if "retrieval_k_returned" not in flat:
        flat["retrieval_k_returned"] = 0
    if "accepted_changes" not in flat:
        flat["accepted_changes"] = []
    if "rejected_changes" not in flat:
        flat["rejected_changes"] = []
    return flat


def _get_severity_before(case: Dict[str, Any]) -> float:
    rb = case.get("risk_before")
    if isinstance(rb, dict) and "severity" in rb:
        return float(rb["severity"])
    return 0.0


def _get_severity_after(case: Dict[str, Any]) -> float:
    ra = case.get("risk_after")
    if isinstance(ra, dict) and "severity" in ra:
        return float(ra["severity"])
    return 0.0


def _get_store_size_after(case: Dict[str, Any]) -> Optional[int]:
    v = case.get("store_size_after")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# 2) Derived variables per case
# -----------------------------------------------------------------------------


def compute_delta_risk(case: Dict[str, Any]) -> float:
    return _get_severity_after(case) - _get_severity_before(case)


def is_followed(case: Dict[str, Any]) -> bool:
    return bool(case.get("advisories_present")) and bool(case.get("override_applied"))


def is_ignored(case: Dict[str, Any]) -> bool:
    return bool(case.get("advisories_present")) and not bool(case.get("override_applied"))


# -----------------------------------------------------------------------------
# 3) Load, sort, filter
# -----------------------------------------------------------------------------


def load_and_normalize(trace_path: Path) -> List[Dict[str, Any]]:
    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")
    cases: List[Dict[str, Any]] = []
    text = trace_path.read_text(encoding="utf-8-sig")
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON at line {i + 1}: {e}") from e
        flat = normalize_to_flat(i, raw)
        for key in REQUIRED_FLAT_KEYS:
            if key not in flat:
                raise ValueError(f"Missing required field '{key}' at line {i + 1} (after normalization)")
        cases.append(flat)
    return cases


def sort_by_sample_index(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(cases, key=lambda c: (c.get("sample_index"), c.get("case_id", "")))


def filter_by_memory_mode(
    cases: List[Dict[str, Any]],
    memory_mode: Optional[str],
) -> List[Dict[str, Any]]:
    if not memory_mode or memory_mode == "all":
        return cases
    return [c for c in cases if (c.get("memory_mode") or "").lower() == memory_mode.lower()]


def _merge_scorecards_auxiliary(cases: List[Dict[str, Any]], scorecards_path: Path) -> None:
    """Merge optional tuple_f1_s2 and correct from scorecards by index (first trace = first scorecard). In-place."""
    if not scorecards_path.exists():
        return
    try:
        from metrics.eval_tuple import gold_tuple_set_from_record, tuples_from_list, tuples_to_pairs
    except ImportError:
        return
    lines = scorecards_path.read_text(encoding="utf-8-sig").strip().splitlines()
    scorecards: List[Dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            scorecards.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(scorecards) != len(cases):
        return
    for i, sc in enumerate(scorecards):
        if i >= len(cases):
            break
        gold = gold_tuple_set_from_record(sc)
        if gold is not None:
            runtime = sc.get("runtime") or {}
            parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
            fr = parsed.get("final_result") or {}
            final_tuples = fr.get("final_tuples")
            pred = tuples_from_list(final_tuples) if isinstance(final_tuples, list) else set()
            _, _, f1 = _precision_recall_f1_set(pred, gold)
            cases[i]["tuple_f1_s2"] = f1
        meta = sc.get("meta") or {}
        if "correctness" in meta or "tuple_correctness" in meta:
            correct = meta.get("correctness") if "correctness" in meta else meta.get("tuple_correctness")
            cases[i]["correct"] = bool(correct)


def _precision_recall_f1_set(pred: set, gold: set) -> Tuple[float, float, float]:
    """F1 on (aspect_term, polarity) pairs; expects sets of (aspect_ref, aspect_term, polarity) tuples."""
    try:
        from metrics.eval_tuple import tuples_to_pairs
    except ImportError:
        return (0.0, 0.0, 0.0)
    gold_pairs = tuples_to_pairs(gold)
    pred_pairs = tuples_to_pairs(pred) if pred else set()
    tp = len(pred_pairs & gold_pairs)
    fp = len(pred_pairs - gold_pairs)
    fn = len(gold_pairs - pred_pairs)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


# -----------------------------------------------------------------------------
# 4) Window-based aggregation
# -----------------------------------------------------------------------------


def sliding_windows(
    cases: List[Dict[str, Any]],
    window_size: int,
) -> List[Tuple[int, List[Dict[str, Any]]]]:
    """Yield (window_end_sample_index, list of cases in window). window_end = last sample_index in window."""
    if not cases or window_size <= 0:
        return []
    out: List[Tuple[int, List[Dict[str, Any]]]] = []
    for end in range(window_size - 1, len(cases)):
        start = end - window_size + 1
        window_cases = cases[start : end + 1]
        if not window_cases:
            continue
        window_end_sample = window_cases[-1].get("sample_index", end)
        out.append((window_end_sample, window_cases))
    return out


def _safe_mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _rate(n: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return n / total


def aggregate_window(
    window_end_sample: int,
    window_size: int,
    window_cases: List[Dict[str, Any]],
    memory_mode: str,
) -> Dict[str, Any]:
    """Compute all required metrics for one window."""
    n = len(window_cases)

    # A. Accumulation: store_size(t) = last case's store_size_after in window
    store_size = _get_store_size_after(window_cases[-1]) if window_cases else None
    store_sizes_ordered = [_get_store_size_after(c) for c in window_cases]
    store_new_entry_count = 0
    prev_s = None
    for s in store_sizes_ordered:
        if prev_s is not None and s is not None and s > prev_s:
            store_new_entry_count += 1
        if s is not None:
            prev_s = s
    store_new_entry_rate = _rate(store_new_entry_count, n) if n else None
    # principle_coverage: optional; flat format may not include principle_id per advisory
    principle_coverage: Optional[int] = None

    # B. Usage
    advisory_present_count = sum(1 for c in window_cases if c.get("advisories_present"))
    advisory_presence_rate = _rate(advisory_present_count, n) if n else None
    retrieval_ks = [c.get("retrieval_k_returned") for c in window_cases if c.get("retrieval_k_returned") is not None]
    retrieval_hit_k = _safe_mean([float(k) for k in retrieval_ks]) if retrieval_ks else None
    follow_count = sum(1 for c in window_cases if is_followed(c))
    follow_rate = _rate(follow_count, advisory_present_count) if advisory_present_count else None

    # C. Effect
    followed_cases = [c for c in window_cases if is_followed(c)]
    ignored_cases = [c for c in window_cases if is_ignored(c)]
    deltas_followed = [compute_delta_risk(c) for c in followed_cases]
    deltas_ignored = [compute_delta_risk(c) for c in ignored_cases]
    mean_delta_risk_followed = _safe_mean(deltas_followed)
    mean_delta_risk_ignored = _safe_mean(deltas_ignored)
    harm_rate_followed = _rate(sum(1 for d in deltas_followed if d > 0), len(deltas_followed)) if deltas_followed else None
    harm_rate_ignored = _rate(sum(1 for d in deltas_ignored if d > 0), len(deltas_ignored)) if deltas_ignored else None

    # D. Auxiliary (optional): accuracy / F1 when present in case
    f1_vals = [float(c["tuple_f1_s2"]) for c in window_cases if c.get("tuple_f1_s2") is not None]
    mean_tuple_f1_s2 = _safe_mean(f1_vals) if f1_vals else None
    correct_vals = [c for c in window_cases if c.get("correct") is not None]
    accuracy_rate = _rate(sum(1 for c in correct_vals if c.get("correct")), len(correct_vals)) if correct_vals else None

    # Canonical output: RQ metrics (F1, accuracy) always present; memory-growth fields null when memory off
    row: Dict[str, Any] = {
        "window_end_sample": window_end_sample,
        "window_size": window_size,
        "memory_mode": memory_mode,
        "store_size": store_size,
        "store_new_entry_rate": store_new_entry_rate,
        "advisory_presence_rate": advisory_presence_rate,
        "follow_rate": follow_rate,
        "mean_delta_risk_followed": mean_delta_risk_followed,
        "mean_delta_risk_ignored": mean_delta_risk_ignored,
        "harm_rate_followed": harm_rate_followed,
        "harm_rate_ignored": harm_rate_ignored,
        "retrieval_hit_k": retrieval_hit_k,
        "mean_tuple_f1_s2": mean_tuple_f1_s2,
        "accuracy_rate": accuracy_rate,
    }
    if principle_coverage is not None:
        row["principle_coverage"] = principle_coverage
    return row


# -----------------------------------------------------------------------------
# 5) CLI and main
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Memory Growth Curve aggregation from CaseTrace JSONL. "
        "Analyzes episodic memory accumulation, usage, and effect over time (no accuracy/F1)."
    )
    p.add_argument("--trace", required=True, type=Path, help="Path to traces.jsonl")
    p.add_argument("--window", type=int, default=50, help="Sliding window size (default: 50)")
    p.add_argument(
        "--memory_mode",
        default="all",
        choices=["all", "off", "on", "silent"],
        help="Filter by memory_mode (default: all)",
    )
    p.add_argument("--out", required=True, type=Path, help="Output JSONL path (memory_growth_metrics.jsonl)")
    p.add_argument(
        "--scorecards",
        type=Path,
        default=None,
        help="Optional scorecards.jsonl to merge tuple_f1_s2/correct by sample order (auxiliary metrics)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        cases = load_and_normalize(args.trace)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    cases = sort_by_sample_index(cases)
    cases = filter_by_memory_mode(cases, args.memory_mode if args.memory_mode != "all" else None)
    if args.scorecards:
        _merge_scorecards_auxiliary(cases, args.scorecards)
    if not cases:
        print("No cases after filter; writing empty output.", file=sys.stderr)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("", encoding="utf-8")
        return
    filter_all = args.memory_mode == "all"
    windows = sliding_windows(cases, args.window)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as f:
        for window_end_sample, window_cases in windows:
            mode = (window_cases[0].get("memory_mode", "all") if window_cases else "all") if filter_all else args.memory_mode
            row = aggregate_window(window_end_sample, args.window, window_cases, mode)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(windows)} window rows to {args.out}")


if __name__ == "__main__":
    main()
