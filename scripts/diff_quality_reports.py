"""
Generate a simple mock-vs-real quality diff report in markdown.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

KEY_METRICS = [
    "pass_rate",
    "valid_target_rate",
    "opinion_grounded_rate",
    "evidence_relevance_score",
    "contrast_sentence_rate",
    "contrast_aspect_coverage_rate",
    "contrast_polarity_split_rate",
]


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(buckets: Dict[str, Any], name: str, bucket: str = "proposed"):
    try:
        val = buckets[bucket][name]
    except Exception:
        return None
    if isinstance(val, list) and val:
        return val[0]
    return val


def _fmt_pairs(lst: Any, k: int = 5) -> str:
    if not lst:
        return "N/A"
    parts = []
    for item in lst[:k]:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            parts.append(f"{item[0]} ({item[1]})")
        else:
            parts.append(str(item))
    return ", ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock_report", required=True)
    ap.add_argument("--real_report", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    mock = _load(Path(args.mock_report))
    real = _load(Path(args.real_report))
    mb = mock.get("buckets", {})
    rb = real.get("buckets", {})

    lines: List[str] = ["# Quality Diff: mock vs real", ""]
    lines.append("| metric | mock | real |")
    lines.append("| --- | --- | --- |")
    for key in KEY_METRICS:
        mv = _metric(mb, key)
        rv = _metric(rb, key)
        mv_s = "N/A" if mv is None else f"{mv:.3f}" if isinstance(mv, (int, float)) else str(mv)
        rv_s = "N/A" if rv is None else f"{rv:.3f}" if isinstance(rv, (int, float)) else str(rv)
        lines.append(f"| {key} | {mv_s} | {rv_s} |")

    lines.append("")
    lines.append("## Top drops / fails")
    lines.append(f"- mock drop_top: {_fmt_pairs(mb.get('proposed', {}).get('drop_top'))}")
    lines.append(f"- real drop_top: {_fmt_pairs(rb.get('proposed', {}).get('drop_top'))}")
    lines.append(f"- mock fail_top: {_fmt_pairs(mb.get('proposed', {}).get('fail_top'))}")
    lines.append(f"- real fail_top: {_fmt_pairs(rb.get('proposed', {}).get('fail_top'))}")

    # Triage if real worse on contrast coverage or polarity split
    cov_mock = _metric(mb, "contrast_aspect_coverage_rate") or 0
    cov_real = _metric(rb, "contrast_aspect_coverage_rate") or 0
    split_mock = _metric(mb, "contrast_polarity_split_rate") or 0
    split_real = _metric(rb, "contrast_polarity_split_rate") or 0
    drop_real = _metric(rb, "drop_top") or []
    drop_mock = _metric(mb, "drop_top") or []
    other_not_target_real = next((c for c in drop_real if isinstance(c, list) and c and c[0] == "other_not_target"), None)
    other_not_target_mock = next((c for c in drop_mock if isinstance(c, list) and c and c[0] == "other_not_target"), None)
    if cov_real < cov_mock or split_real < split_mock or (other_not_target_real and (not other_not_target_mock or other_not_target_real[1] > other_not_target_mock[1])):
        lines.append("")
        lines.append("## Triage checklist")
        lines.append("- Verify provider credentials and quotas (run provider_dry_run).")
        lines.append("- Inspect ATE aspects on contrast sentences for missing second target.")
        lines.append("- Check ATSA grounding/polarity per aspect; re-run with small n if needed.")
        lines.append("- If 'other_not_target' increases, review aspect allowlist or taxonomy for this experiment.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
