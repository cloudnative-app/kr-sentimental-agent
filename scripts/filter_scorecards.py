"""
Filter scorecards.jsonl to a target split set (e.g., report_set only).

Usage:
  python scripts/filter_scorecards.py --scorecards path/to/scorecards.jsonl --splits valid --out report_only.jsonl
  # Or drive from config's data_roles.report_set
  python scripts/filter_scorecards.py --scorecards path/to/scorecards.jsonl --config experiments/configs/proposed.yaml
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Dict, Any, Set, Iterable, Optional
import statistics


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_report_splits(cfg_path: Path) -> Set[str]:
    import yaml

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    roles = cfg.get("data_roles") or {}
    report = roles.get("report_set") or ["valid"]
    return {s.lower() for s in report}


def _parse_list(arg: Optional[str]) -> Set[str]:
    if not arg:
        return set()
    return {s.strip().lower() for s in arg.split(",") if s.strip()}


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(0.95 * (len(sorted_vals) - 1))
    return sorted_vals[idx]


def _summary(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    flags = [r.get("runtime", {}).get("flags", {}) for r in rows]
    parse_failed = sum(1 for f in flags if f.get("parse_failed"))
    fallback = sum(1 for f in flags if f.get("fallback_used"))
    tokens = []
    costs = []
    for r in rows:
        rt = r.get("runtime", {})
        tin = rt.get("tokens_in") or 0
        tout = rt.get("tokens_out") or 0
        tokens.append((tin or 0) + (tout or 0))
        cost = rt.get("cost_usd")
        if cost is not None:
            costs.append(cost)
    n = len(rows) or 1
    return {
        "N": len(rows),
        "parse_failed_pct": round(100.0 * parse_failed / n, 2),
        "fallback_pct": round(100.0 * fallback / n, 2),
        "tokens_avg": round(statistics.mean(tokens) if tokens else 0.0, 2),
        "tokens_p95": round(_p95(tokens), 2),
        "cost_avg": round(statistics.mean(costs) if costs else 0.0, 4),
    }


def _compute_latency_stats(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute latency statistics from rows."""
    latencies = []
    for r in rows:
        rt = r.get("runtime", {})
        lat = rt.get("latency_ms")
        if lat is not None:
            latencies.append(lat)
    if not latencies:
        return {"latency_mean": 0.0, "latency_p50": 0.0, "latency_p95": 0.0}
    latencies.sort()
    n = len(latencies)
    return {
        "latency_mean": round(sum(latencies) / n, 2),
        "latency_p50": round(latencies[n // 2], 2),
        "latency_p95": round(_p95(latencies), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scorecards", required=True, help="Path to scorecards.jsonl")
    ap.add_argument("--splits", default=None, help="Comma-separated split names to keep (e.g., valid,test)")
    ap.add_argument("--config", default=None, help="Optional config YAML to read data_roles.report_set")
    ap.add_argument("--language", default=None, help="Comma-separated language codes to keep (e.g., en,ko)")
    ap.add_argument("--domain", default=None, help="Comma-separated domain_ids to keep")
    ap.add_argument("--runner", default=None, help="Comma-separated runner/mode names to keep (e.g., proposed,bl1)")
    ap.add_argument("--out", default=None, help="Optional output file path; default <scorecards>.<splits>.jsonl")
    ap.add_argument("--outdir", default=None, help="Output directory for filtered.jsonl, summary.json, summary.md")
    args = ap.parse_args()

    src = Path(args.scorecards)
    if args.config:
        keep = load_report_splits(Path(args.config))
    else:
        keep = {s.strip().lower() for s in args.splits.split(",")} if args.splits else {"valid"}
    keep_lang = _parse_list(args.language)
    keep_domain = _parse_list(args.domain)
    keep_runner = _parse_list(args.runner)

    rows = load_jsonl(src)
    filtered = []
    for r in rows:
        split = ((r.get("meta") or {}).get("split") or r.get("split") or "").lower()
        if split not in keep:
            continue
        lang = ((r.get("meta") or {}).get("language_code") or "unknown").lower()
        if keep_lang and lang not in keep_lang:
            continue
        domain = ((r.get("meta") or {}).get("domain_id") or "unknown").lower()
        if keep_domain and domain not in keep_domain:
            continue
        runner = ((r.get("meta") or {}).get("mode") or (r.get("runtime") or {}).get("runner_name") or "").lower()
        if keep_runner and runner not in keep_runner:
            continue
        filtered.append(r)

    # Build suffix for naming
    suffix_parts = []
    if keep:
        suffix_parts.append(",".join(sorted(keep)))
    if keep_lang:
        suffix_parts.append("lang=" + ",".join(sorted(keep_lang)))
    if keep_domain:
        suffix_parts.append("domain=" + ",".join(sorted(keep_domain)))
    if keep_runner:
        suffix_parts.append("runner=" + ",".join(sorted(keep_runner)))
    suffix = "." + ".".join(suffix_parts) if suffix_parts else ".filtered"

    # Determine output paths
    if args.outdir:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        out_path = outdir / "filtered_scorecards.jsonl"
        summary_json_path = outdir / "summary.json"
        summary_md_path = outdir / "summary.md"
    else:
        out_path = Path(args.out) if args.out else src.with_suffix(f"{suffix}.jsonl")
        summary_json_path = None
        summary_md_path = None

    # Write filtered JSONL
    write_jsonl(out_path, filtered)

    # Compute stats
    stats = _summary(filtered)
    latency_stats = _compute_latency_stats(filtered)
    full_stats = {**stats, **latency_stats}

    # Write summary files if outdir is specified
    if args.outdir:
        # summary.json
        summary_json_path.write_text(
            json.dumps(full_stats, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # summary.md
        filter_desc = []
        if keep:
            filter_desc.append(f"splits: {', '.join(sorted(keep))}")
        if keep_lang:
            filter_desc.append(f"language: {', '.join(sorted(keep_lang))}")
        if keep_domain:
            filter_desc.append(f"domain: {', '.join(sorted(keep_domain))}")
        if keep_runner:
            filter_desc.append(f"runner: {', '.join(sorted(keep_runner))}")

        md_lines = [
            "# Filter Summary",
            "",
            f"**Source**: `{src}`",
            f"**Filters**: {'; '.join(filter_desc) if filter_desc else 'none'}",
            f"**Kept**: {len(filtered)} / {len(rows)} rows",
            "",
            "## Statistics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| N | {full_stats['N']} |",
            f"| parse_failed_pct | {full_stats['parse_failed_pct']}% |",
            f"| fallback_pct | {full_stats['fallback_pct']}% |",
            f"| tokens_avg | {full_stats['tokens_avg']} |",
            f"| tokens_p95 | {full_stats['tokens_p95']} |",
            f"| cost_avg | {full_stats['cost_avg']} |",
            f"| latency_mean | {full_stats['latency_mean']} ms |",
            f"| latency_p50 | {full_stats['latency_p50']} ms |",
            f"| latency_p95 | {full_stats['latency_p95']} ms |",
        ]
        summary_md_path.write_text("\n".join(md_lines), encoding="utf-8")
        print(f"[done] filtered={out_path}, summary_json={summary_json_path}, summary_md={summary_md_path}")
    else:
        print(f"kept {len(filtered)}/{len(rows)} rows -> {out_path}")
        print(
            f"summary: N={stats['N']}, parse_failed%={stats['parse_failed_pct']}, "
            f"fallback%={stats['fallback_pct']}, tokens_avg={stats['tokens_avg']}, "
            f"tokens_p95={stats['tokens_p95']}, cost_avg={stats['cost_avg']}"
        )


if __name__ == "__main__":
    main()
