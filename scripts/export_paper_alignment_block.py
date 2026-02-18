#!/usr/bin/env python3
"""
Post-hoc Alignment Block — paper_metrics에 붙일 블록 생성.

Block 1: Pre-decision summary (수동결정용)
Block 2: Post-decision alignment metrics (논문용)

Usage:
  python scripts/export_paper_alignment_block.py --posthoc-dir results/posthoc_alignment_v1 --confusion-summary-dir results/posthoc_confusion_v1 --out-md results/posthoc_alignment_v1/paper_alignment_block.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="Export paper alignment block")
    ap.add_argument("--posthoc-dir", type=Path, required=True, help="posthoc_alignment_eval output dir")
    ap.add_argument("--confusion-summary-dir", type=Path, default=None, help="posthoc_confusion_discovery output dir")
    ap.add_argument("--out-md", type=Path, default=None, help="Output md path (default: posthoc-dir/paper_alignment_block.md)")
    args = ap.parse_args()

    posthoc_dir = args.posthoc_dir.resolve()
    if not posthoc_dir.is_absolute():
        posthoc_dir = (PROJECT_ROOT / posthoc_dir).resolve()
    if not posthoc_dir.is_dir():
        print(f"[ERROR] Not a directory: {posthoc_dir}", file=sys.stderr)
        return 1

    out_md = args.out_md
    if out_md is None:
        out_md = posthoc_dir / "paper_alignment_block.md"
    else:
        out_md = out_md.resolve()
        if not out_md.is_absolute():
            out_md = (PROJECT_ROOT / out_md).resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    # Block 1: Pre-decision (from confusion discovery)
    conf_dir = args.confusion_summary_dir
    if conf_dir is not None:
        conf_dir = conf_dir.resolve()
        if not conf_dir.is_absolute():
            conf_dir = (PROJECT_ROOT / conf_dir).resolve()
        draft_path = conf_dir / "posthoc" / "confusion_groups_draft.json"
        if not draft_path.exists():
            draft_path = conf_dir / "confusion_groups_draft.json"
        if draft_path.exists():
            try:
                draft = json.loads(draft_path.read_text(encoding="utf-8"))
                total = draft.get("total_mismatches", 0)
                cov = draft.get("coverage_summary", {})
                elbow = draft.get("elbow_k")
                lines.append("## Post-hoc Construct Alignment (Pre-decision)\n")
                lines.append(f"**total_mismatches**: {total}\n")
                lines.append("| k | coverage |")
                lines.append("|---|----------|")
                for k in ["5", "10", "15", "20"]:
                    if k in cov:
                        lines.append(f"| {k} | {cov[k]:.4f} |")
                if elbow is not None:
                    lines.append(f"\n**Elbow candidate k**: {elbow}\n")
                lines.append("")
            except (json.JSONDecodeError, OSError):
                pass

    # Block 2: Post-decision alignment metrics
    summary_path = posthoc_dir / "posthoc_alignment_summary.json"
    if not summary_path.exists():
        print(f"[WARN] Missing: {summary_path}", file=sys.stderr)
        lines.append("## Post-hoc Construct Alignment (Post-decision)\n")
        lines.append("*No posthoc_alignment_summary.json found.*\n")
    else:
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            agg = summary.get("aggregated", {})
            lines.append("## Post-hoc Construct Alignment (Post-decision)\n")
            lines.append("| metric | mean ± std |")
            lines.append("|--------|------------|")
            for key in ["exact_ref_accuracy", "near_miss_rate", "exact_plus_near_rate",
                       "mean_taxonomy_similarity", "mean_taxonomy_distance",
                       "same_entity_rate", "same_attribute_rate"]:
                v = agg.get(key, {})
                m = v.get("mean")
                s = v.get("std", 0)
                if m is not None and m == m:
                    if s and s != 0:
                        lines.append(f"| {key} | {m:.4f} ± {s:.4f} |")
                    else:
                        lines.append(f"| {key} | {m:.4f} |")
            lines.append("")
        except (json.JSONDecodeError, OSError) as e:
            print(f"[WARN] Parse error: {e}", file=sys.stderr)

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] wrote: {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
