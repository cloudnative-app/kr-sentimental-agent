"""
Export gold pairs vs pred pairs (eval key) per sample for F1 audit.
Uses same extraction as structural_error_aggregator; gold = (aspect_term, polarity), pred = (aspect_ref or aspect_term, polarity).
Output: Markdown table to --out (default: gold_pred_pairs_table.md in same dir as --input).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import (
    tuples_to_pairs,
    tuples_to_pairs_ref_fallback,
    precision_recall_f1_tuple,
)
from scripts.structural_error_aggregator import (
    load_jsonl,
    _extract_gold_tuples,
    _extract_final_tuples,
    _extract_stage1_tuples,
    _tuples_from_list_of_dicts,
)


def _fmt_pairs(pairs: set, sep: str = "; ") -> str:
    if not pairs:
        return ""
    return sep.join(f"({t!r}, {p})" for (t, p) in sorted(pairs))


def _extract_stage2_tuples(record: dict) -> set:
    """Stage2 tuples from final_result.stage2_tuples (same key space as final)."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    fr = parsed.get("final_result") or {}
    stage2 = fr.get("stage2_tuples")
    if stage2 and isinstance(stage2, list):
        return _tuples_from_list_of_dicts(stage2)
    return set()


def _trunc(s: str, max_len: int = 80) -> str:
    return s[: max_len - 3] + "..." if len(s) > max_len else s


def _debate_info(record: dict) -> str:
    """Short debate info: adopt_decision, adopt_reason, gate_decision, override_applied, sentence_polarity."""
    meta = record.get("meta") or {}
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output")
    if isinstance(parsed, dict) and parsed.get("meta"):
        pmeta = parsed.get("meta") or {}
        meta = {**meta, **pmeta}
    summary = meta.get("debate_summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    parts = []
    adopt = (meta.get("adopt_decision") or "").strip()
    if adopt:
        parts.append(f"adopt={adopt}")
    reason = (meta.get("adopt_reason") or "").strip()
    if reason:
        parts.append(f"reason={reason[:20]}" + ("..." if len(reason) > 20 else ""))
    gate = (meta.get("gate_decision") or "").strip()
    if gate:
        parts.append(f"gate={gate}")
    ov = meta.get("override_applied")
    if ov is not None:
        parts.append(f"override={ov}")
    sent_pol = (summary.get("sentence_polarity") or "").strip()
    if sent_pol:
        parts.append(f"sent_pol={sent_pol}")
    return "; ".join(parts) if parts else ""


def main() -> None:
    ap = argparse.ArgumentParser(description="Export gold vs pred pairs table for F1 audit")
    ap.add_argument("--input", required=True, help="Scorecards JSONL path")
    ap.add_argument("--out", default=None, help="Output Markdown path (default: same dir as input, gold_pred_pairs_table.md)")
    ap.add_argument("--max-rows", type=int, default=0, help="Max rows to show (0 = all)")
    args = ap.parse_args()

    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        print("No records", file=sys.stderr)
        return

    out_path = Path(args.out) if args.out else path.parent / "gold_pred_pairs_table.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Gold pairs vs Pred pairs (F1 eval key) + Stage pairs + Debate info",
        "",
        "Gold pair key = (aspect_term, polarity). Stage/Pred pair key = (aspect_ref or aspect_term, polarity).",
        "",
        "**Columns**: gold_pairs = gold (term, pol); stage1_pairs = final_result.stage1_tuples; stage2_pairs = final_result.stage2_tuples; pred_pairs = final (final_aspects/final_tuples); matched = gold ∩ pred; debate = adopt_decision; adopt_reason; gate_decision; override_applied; sent_pol (from meta).",
        "",
        "| # | text_id | gold_pairs | stage1_pairs | stage2_pairs | pred_pairs (final) | matched | F1 | debate |",
        "|---|--------|------------|---------------|---------------|---------------------|---------|-----|--------|",
    ]

    n_show = len(rows) if args.max_rows <= 0 else min(args.max_rows, len(rows))
    for i, record in enumerate(rows[:n_show]):
        text_id = (record.get("meta") or {}).get("text_id") or (record.get("runtime") or {}).get("uid") or record.get("uid") or record.get("text_id") or f"row_{i}"

        gold_tuples = _extract_gold_tuples(record)
        stage1_tuples = _extract_stage1_tuples(record)
        stage2_tuples = _extract_stage2_tuples(record)
        pred_tuples = _extract_final_tuples(record)

        if not gold_tuples:
            gold_pairs: set = set()
        else:
            gold_pairs = tuples_to_pairs(gold_tuples)
        stage1_pairs = tuples_to_pairs_ref_fallback(stage1_tuples) if stage1_tuples else set()
        stage2_pairs = tuples_to_pairs_ref_fallback(stage2_tuples) if stage2_tuples else set()
        pred_pairs = tuples_to_pairs_ref_fallback(pred_tuples) if pred_tuples else set()

        matched = gold_pairs & pred_pairs
        _, _, f1 = precision_recall_f1_tuple(gold_tuples or set(), pred_tuples or set())
        f1_str = f"{f1:.4f}" if f1 is not None else "N/A"

        gold_str = _fmt_pairs(gold_pairs)
        s1_str = _fmt_pairs(stage1_pairs)
        s2_str = _fmt_pairs(stage2_pairs)
        pred_str = _fmt_pairs(pred_pairs)
        matched_str = _fmt_pairs(matched)
        debate_str = _debate_info(record)
        # Truncate long cells (no pipe inside cells)
        gold_str = _trunc(gold_str, 80)
        s1_str = _trunc(s1_str, 80)
        s2_str = _trunc(s2_str, 80)
        pred_str = _trunc(pred_str, 80)
        matched_str = _trunc(matched_str, 40)
        debate_str = _trunc(debate_str, 60)

        lines.append(f"| {i+1} | {text_id} | {gold_str} | {s1_str} | {s2_str} | {pred_str} | {matched_str} | {f1_str} | {debate_str} |")

    if args.max_rows > 0 and len(rows) > args.max_rows:
        lines.append(f"| ... | ({len(rows) - args.max_rows} more rows) | | | | | | | |")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
