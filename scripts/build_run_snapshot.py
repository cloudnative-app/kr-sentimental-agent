"""
ops-only run snapshot generator.

Reads existing artifacts in a run directory and produces lightweight ops summaries
that work even without gold labels. No changes to inference/pipeline.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------- IO helpers ----------

def load_json(path: Path) -> Optional[Dict]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def save_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(path: Path, rows: List[Dict]):
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        if not rows:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ---------- Stats helpers ----------

def safe_mean(lst: List[Optional[float]]) -> Optional[float]:
    vals = [x for x in lst if x is not None and not math.isnan(x)]
    return statistics.mean(vals) if vals else None


def percentile(lst: List[Optional[float]], p: float) -> Optional[float]:
    vals = sorted([x for x in lst if x is not None and not math.isnan(x)])
    if not vals:
        return None
    k = (len(vals) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return vals[int(k)]
    return vals[f] * (c - k) + vals[c] * (k - f)


# ---------- Split overlap helpers ----------


def _compute_split_overlap(scorecards: List[Dict], traces: List[Dict]) -> Dict[str, Any]:
    """
    Compute exact overlap between train/valid/test splits using input_hash.
    Returns overlap rates and notes.
    """
    # Collect input_hashes by split
    hashes_by_split: Dict[str, set] = {"train": set(), "valid": set(), "test": set()}

    # Prefer scorecards for input_hash, fall back to traces
    for row in scorecards:
        meta = row.get("meta") or {}
        split = meta.get("split") or row.get("split")
        # Try to get input_hash from meta or compute from text
        input_hash = meta.get("input_hash")
        if not input_hash:
            # Try traces for this uid
            uid = meta.get("text_id") or meta.get("uid") or row.get("uid")
            for tr in traces:
                if tr.get("uid") == uid:
                    input_hash = tr.get("input_hash")
                    break
        if not input_hash:
            # Last resort: hash the input_preview if available
            preview = meta.get("input_text") or row.get("text")
            if preview and isinstance(preview, str):
                import hashlib
                # Normalize whitespace for consistent hashing
                normalized = " ".join(preview.split())
                input_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        if split in hashes_by_split and input_hash:
            hashes_by_split[split].add(input_hash)

    train_hashes = hashes_by_split.get("train", set())
    valid_hashes = hashes_by_split.get("valid", set())
    test_hashes = hashes_by_split.get("test", set())

    def overlap_rate(set_a: set, set_b: set) -> float:
        if not set_a and not set_b:
            return 0.0
        union_size = len(set_a | set_b)
        if union_size == 0:
            return 0.0
        return len(set_a & set_b) / union_size

    train_valid_overlap = overlap_rate(train_hashes, valid_hashes)
    train_test_overlap = overlap_rate(train_hashes, test_hashes)
    valid_test_overlap = overlap_rate(valid_hashes, test_hashes)

    # Any overlap rate
    any_rate = max(train_valid_overlap, train_test_overlap, valid_test_overlap)

    notes = []
    if train_valid_overlap > 0:
        notes.append(f"train-valid overlap: {train_valid_overlap:.2%}")
    if train_test_overlap > 0:
        notes.append(f"train-test overlap: {train_test_overlap:.2%}")
    if valid_test_overlap > 0:
        notes.append(f"valid-test overlap: {valid_test_overlap:.2%}")

    return {
        "split_overlap_pairs": {
            "train_valid": train_valid_overlap,
            "train_test": train_test_overlap,
            "valid_test": valid_test_overlap,
        },
        "split_overlap_any_rate": any_rate,
        "notes": "; ".join(notes) if notes else None,
        "split_hash_counts": {
            "train": len(train_hashes),
            "valid": len(valid_hashes),
            "test": len(test_hashes),
        },
    }


# ---------- Core processing ----------


def build_snapshot(run_dir: Path, out_dir: Path, text_preview_chars: int, raw_preview_chars: int, top_k: int):
    manifest_path = run_dir / "manifest.json"
    score_path = run_dir / "scorecards.jsonl"
    trace_path = run_dir / "traces.jsonl"
    smoke_path = run_dir / "smoke_outputs.jsonl"

    manifest = load_json(manifest_path) or {}
    scorecards = load_jsonl(score_path)
    traces = load_jsonl(trace_path)
    smokes = load_jsonl(smoke_path)

    run_id = manifest.get("run_id") or run_dir.name
    timestamp = manifest.get("timestamp_utc")
    cfg_hash = manifest.get("cfg_hash")
    backbone = (manifest.get("backbone") or {}).get("model")
    prompt_hashes = list((manifest.get("prompt_versions") or {}).values())
    purpose = manifest.get("purpose") or "unknown"

    # Compute split overlap integrity check
    split_overlap = _compute_split_overlap(scorecards, traces)

    # Artifact presence
    def fsize(p: Path):
        return p.stat().st_size if p.exists() else None

    artifacts_presence = {
        "manifest": manifest_path.exists(),
        "scorecards": score_path.exists(),
        "traces": trace_path.exists(),
        "smoke_outputs": smoke_path.exists(),
        "manifest_bytes": fsize(manifest_path),
        "scorecards_bytes": fsize(score_path),
        "traces_bytes": fsize(trace_path),
        "smoke_outputs_bytes": fsize(smoke_path),
    }

    # Aggregates
    rows = scorecards
    n_total = len(rows)
    by_split = {}
    by_case_type = {}

    def inc(d, key):
        if key is None:
            return
        d[key] = d.get(key, 0) + 1

    for r in rows:
        meta = r.get("meta") or {}
        inc(by_split, meta.get("split"))
        inc(by_case_type, meta.get("case_type"))

    # Reliability
    def rate(key):
        flags = [(r.get("flags") or {}).get(key) for r in rows]
        flags = [bool(x) for x in flags if x is not None]
        if not flags:
            return None
        return sum(flags) / len(flags)

    def agg_numeric(getter):
        vals = []
        for r in rows:
            val = getter(r)
            if val is not None:
                vals.append(val)
        return vals

    # empty_output detection
    empty_output_flags = []
    aspects_counts = []
    for r in rows:
        parsed = (r.get("runtime") or {}).get("parsed_output") or {}
        aspects = parsed.get("stage1_aspects") or parsed.get("stage2_aspects") or parsed.get("final_aspects") or []
        if isinstance(aspects, list):
            aspects_counts.append(len(aspects))
            empty_output_flags.append(len(aspects) == 0)

    reliability = {
        "generate_failed_rate": rate("generate_failed"),
        "parse_failed_rate": rate("parse_failed"),
        "fallback_used_rate": rate("fallback_used"),
        "empty_output_rate": (sum(empty_output_flags) / len(empty_output_flags)) if empty_output_flags else None,
        "avg_aspect_count": safe_mean(aspects_counts) if aspects_counts else None,
    }

    tokens_in = agg_numeric(lambda r: (r.get("runtime") or {}).get("tokens_in"))
    tokens_out = agg_numeric(lambda r: (r.get("runtime") or {}).get("tokens_out"))
    costs = agg_numeric(lambda r: (r.get("runtime") or {}).get("cost_usd"))
    latencies = agg_numeric(lambda r: (r.get("meta") or {}).get("latency_ms"))
    retries = agg_numeric(lambda r: (r.get("runtime") or {}).get("retries"))

    usage = {
        "tokens_in_total": sum(tokens_in) if tokens_in else None,
        "tokens_out_total": sum(tokens_out) if tokens_out else None,
        "cost_usd_total": sum(costs) if costs else None,
        "latency_ms_mean": safe_mean(latencies),
        "latency_ms_p50": percentile(latencies, 0.5),
        "latency_ms_p95": percentile(latencies, 0.95),
        "retries_mean": safe_mean(retries),
    }

    # ops_table rows
    def collect_ops_rows():
        by_key = {}
        for r in rows:
            meta = r.get("meta") or {}
            key = (meta.get("runner_name") or meta.get("mode") or manifest.get("mode"), meta.get("backbone_model_id"), meta.get("split"))
            if key not in by_key:
                by_key[key] = {
                    "runner_name": key[0],
                    "backbone_model_id": key[1],
                    "split": key[2],
                    "n": 0,
                    "parse_failed": [],
                    "generate_failed": [],
                    "fallback_used": [],
                    "tokens_in": [],
                    "tokens_out": [],
                    "cost_usd": [],
                    "latency_ms": [],
                    "retries": [],
                }
            bucket = by_key[key]
            bucket["n"] += 1
            flags = r.get("flags") or {}
            bucket["parse_failed"].append(bool(flags.get("parse_failed")))
            bucket["generate_failed"].append(bool(flags.get("generate_failed")))
            bucket["fallback_used"].append(bool(flags.get("fallback_used")))
            rt = r.get("runtime") or {}
            bucket["tokens_in"].append(rt.get("tokens_in"))
            bucket["tokens_out"].append(rt.get("tokens_out"))
            bucket["cost_usd"].append(rt.get("cost_usd"))
            bucket["latency_ms"].append((r.get("meta") or {}).get("latency_ms"))
            bucket["retries"].append(rt.get("retries"))

        rows_out = []
        for _, b in by_key.items():
            rows_out.append(
                {
                    "runner_name": b["runner_name"],
                    "backbone_model_id": b["backbone_model_id"],
                    "split": b["split"],
                    "n": b["n"],
                    "parse_failed_rate": safe_mean(b["parse_failed"]),
                    "generate_failed_rate": safe_mean(b["generate_failed"]),
                    "fallback_used_rate": safe_mean(b["fallback_used"]),
                    "tokens_in_mean": safe_mean(b["tokens_in"]),
                    "tokens_out_mean": safe_mean(b["tokens_out"]),
                    "cost_usd_sum": sum([x for x in b["cost_usd"] if x is not None]) if b["cost_usd"] else None,
                    "latency_ms_p50": percentile(b["latency_ms"], 0.5),
                    "latency_ms_p95": percentile(b["latency_ms"], 0.95),
                    "retries_mean": safe_mean(b["retries"]),
                }
            )
        return rows_out

    ops_table = collect_ops_rows()

    # top issues
    def severity(row):
        flags = row.get("flags") or {}
        sev = (
            (3 if flags.get("generate_failed") else 0)
            + (2 if flags.get("parse_failed") else 0)
            + (1 if flags.get("fallback_used") else 0)
        )
        # empty_output bonus
        parsed = (row.get("runtime") or {}).get("parsed_output") or {}
        aspects = parsed.get("stage1_aspects") or parsed.get("stage2_aspects") or []
        empty = isinstance(aspects, list) and len(aspects) == 0
        if empty:
            sev += 1
        return sev

    def preview_text(uid):
        # try smoke_outputs for shorter input
        for s in smokes:
            sm_uid = (s.get("meta") or {}).get("text_id") or s.get("uid")
            if sm_uid == uid:
                txt = (s.get("meta") or {}).get("input_text") or s.get("text")
                if txt:
                    return txt[:text_preview_chars]
        return None

    top_rows = []
    for r in rows:
        uid = (r.get("meta") or {}).get("text_id") or r.get("uid")
        flags = r.get("flags") or {}
        sev = severity(r)
        rt = r.get("runtime") or {}
        meta = r.get("meta") or {}
        raw_out = (rt.get("raw_output") or "")[:raw_preview_chars]
        top_rows.append(
            {
                "uid": uid,
                "split": meta.get("split"),
                "case_type": meta.get("case_type"),
                "runner_name": meta.get("runner_name") or meta.get("mode") or manifest.get("mode"),
                "backbone_model_id": meta.get("backbone_model_id"),
                "tokens_in": rt.get("tokens_in"),
                "tokens_out": rt.get("tokens_out"),
                "cost_usd": rt.get("cost_usd"),
                "latency_ms": meta.get("latency_ms"),
                "retries": rt.get("retries"),
                "flags": json.dumps(flags, ensure_ascii=False),
                "text_preview": preview_text(uid),
                "raw_output_preview": raw_out,
                "_severity": sev,
            }
        )

    top_rows = sorted(top_rows, key=lambda x: (-(x["_severity"] or 0), -(x["latency_ms"] or -1)))
    top_rows = top_rows[:top_k]
    for r in top_rows:
        r.pop("_severity", None)

    # run snapshot dict
    snapshot = {
        "run_id": run_id,
        "timestamp_utc": timestamp,
        "cfg_hash": cfg_hash,
        "backbone_model_id": backbone,
        "prompt_hashes": prompt_hashes,
        "purpose": purpose,
        "artifacts": artifacts_presence,
        "volume": {"total_rows": n_total, "rows_by_split": by_split, "rows_by_case_type": by_case_type},
        "reliability": reliability,
        "usage": usage,
        "integrity": {
            "split_overlap_pairs": split_overlap.get("split_overlap_pairs", {}),
            "split_overlap_any_rate": split_overlap.get("split_overlap_any_rate", 0.0),
            "split_overlap_notes": split_overlap.get("notes"),
            "split_hash_counts": split_overlap.get("split_hash_counts", {}),
        },
    }

    # render markdown
    lines = []
    lines.append(f"# Run Snapshot: {run_id}")
    lines.append("")

    # Show prominent warning if split overlap detected or purpose is smoke/sanity
    overlap_any = split_overlap.get("split_overlap_any_rate", 0.0)
    if overlap_any > 0:
        lines.append("> **WARNING: SPLIT OVERLAP DETECTED**")
        lines.append(f"> Overlap rate: {overlap_any:.2%}")
        if split_overlap.get("notes"):
            lines.append(f"> Details: {split_overlap.get('notes')}")
        if purpose == "sanity":
            lines.append("> This is a SANITY run (integrity suite). Overlap is expected if split files are identical.")
        else:
            lines.append("> This run may not provide valid generalization metrics.")
        lines.append("")
    if purpose in ("smoke", "sanity"):
        lines.append(f"> **NOTE: This is a {purpose.upper()} run. Do not use for paper reporting.**")
        lines.append("")

    lines.append("## Artifacts")
    lines.append(f"- manifest: {artifacts_presence['manifest']} ({artifacts_presence['manifest_bytes']} bytes)")
    lines.append(f"- scorecards: {artifacts_presence['scorecards']} ({artifacts_presence['scorecards_bytes']} bytes)")
    lines.append(f"- traces: {artifacts_presence['traces']} ({artifacts_presence['traces_bytes']} bytes)")
    lines.append(f"- smoke_outputs: {artifacts_presence['smoke_outputs']} ({artifacts_presence['smoke_outputs_bytes']} bytes)")
    lines.append("")
    lines.append("## Identity")
    lines.append(f"- run_id: {run_id}")
    lines.append(f"- timestamp_utc: {timestamp}")
    lines.append(f"- cfg_hash: {cfg_hash}")
    lines.append(f"- backbone_model_id: {backbone}")
    lines.append(f"- prompt_hash_count: {len(prompt_hashes)}")
    lines.append(f"- purpose: {purpose}")
    lines.append("")
    lines.append("## Volume")
    lines.append(f"- total rows: {n_total}")
    lines.append(f"- by split: {by_split}")
    lines.append(f"- by case_type: {by_case_type}")
    lines.append("")
    lines.append("## Integrity")
    lines.append(f"- split_overlap_any_rate: {overlap_any:.4f}")
    lines.append(f"- split_overlap_pairs: {split_overlap.get('split_overlap_pairs', {})}")
    if split_overlap.get("notes"):
        lines.append(f"- notes: {split_overlap.get('notes')}")
    lines.append("")
    lines.append("## Reliability")
    for k, v in reliability.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Usage")
    for k, v in usage.items():
        lines.append(f"- {k}: {v}")

    # outputs
    save_text(out_dir / "run_snapshot.md", "\n".join(lines))
    save_json(out_dir / "run_snapshot.json", snapshot)
    save_csv(out_dir / "ops_table.csv", ops_table)
    save_csv(out_dir / "top_issues.csv", top_rows)


# ---------- CLI ----------


def parse_args():
    p = argparse.ArgumentParser(description="Build ops-only run snapshot.")
    p.add_argument("--run_dir", required=True, help="Run directory containing artifacts.")
    p.add_argument("--out_dir", help="Output directory (default: <run_dir>/ops_outputs)")
    p.add_argument("--text_preview_chars", type=int, default=80)
    p.add_argument("--raw_preview_chars", type=int, default=200)
    p.add_argument("--top_k", type=int, default=20)
    return p.parse_args()


def main():
    args = parse_args()
    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir / "ops_outputs"
    build_snapshot(run_dir, out_dir, args.text_preview_chars, args.raw_preview_chars, args.top_k)


if __name__ == "__main__":
    main()

