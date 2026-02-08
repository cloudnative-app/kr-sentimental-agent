"""
Run RQ1 grounding diagnostic for all scorecard samples and write a result md.
Usage:
  python scripts/run_rq1_diagnosis_and_md.py --run_dir results/mini4_proposed_2__seed42_proposed --out_md docs/mini4_proposed_2_rq1_grounding_diagnosis.md
  python scripts/run_rq1_diagnosis_and_md.py --run_dir results/experiment_mini4_b1_4__seed42_proposed --out_md docs/mini4_b1_4_rq1_grounding_diagnosis.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.structural_error_aggregator import (
    DROP_REASON_ALIGNMENT_FAILURE,
    DROP_REASON_FILTER_REJECTION,
    DROP_REASON_SEMANTIC_HALLUCINATION,
    get_selected_judgement,
    load_jsonl,
    rq1_grounding_bucket,
    _get_first_final_tuple,
)


def diagnostic_row(record: dict, idx: int) -> dict:
    meta = record.get("meta") or {}
    text_id = meta.get("text_id") or meta.get("uid") or meta.get("case_id") or f"index_{idx}"
    first = _get_first_final_tuple(record)
    selected_tuple_str = "None"
    if first:
        _a, term_norm, pol = first
        selected_tuple_str = f"(aspect_term_norm={repr(term_norm)}, polarity={repr(pol)})"
    judgement, j_idx = get_selected_judgement(record)
    selected_judgement_idx = j_idx if j_idx is not None else "None"
    bucket = rq1_grounding_bucket(record)
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    n_align = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_ALIGNMENT_FAILURE)
    n_filter = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_FILTER_REJECTION)
    n_semantic = sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_SEMANTIC_HALLUCINATION)
    return {
        "index": idx,
        "text_id": text_id,
        "selected_tuple": selected_tuple_str,
        "selected_judgement_idx": selected_judgement_idx,
        "rq1_bucket": bucket,
        "n_align": n_align,
        "n_filter": n_filter,
        "n_semantic": n_semantic,
    }


def read_metrics_table(md_path: Path) -> list[tuple[str, str]]:
    """Parse structural_metrics_table.md into list of (metric_name, value)."""
    if not md_path.exists():
        return []
    rows = []
    for line in md_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|$", line)
        if m and m.group(1).strip() != "Metric":
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Run RQ1 diagnostic for all samples and write result md")
    ap.add_argument("--run_dir", required=True, help="Run directory (contains scorecards.jsonl, derived/metrics/)")
    ap.add_argument("--out_md", required=True, help="Output md path (e.g. docs/run_rq1_grounding_diagnosis.md)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    out_md = Path(args.out_md)

    scorecards_path = run_dir / "scorecards.jsonl"
    if not scorecards_path.exists():
        print(f"Missing {scorecards_path}", file=sys.stderr)
        sys.exit(1)
    rows = load_jsonl(scorecards_path)
    if not rows:
        print("No scorecards", file=sys.stderr)
        sys.exit(1)

    run_name = run_dir.name
    N = len(rows)
    diag_rows = [diagnostic_row(record, idx) for idx, record in enumerate(rows)]

    metrics_path = run_dir / "derived" / "metrics" / "structural_metrics_table.md"
    metrics_rows = read_metrics_table(metrics_path)

    try:
        scorecards_rel = scorecards_path.relative_to(_PROJECT_ROOT)
    except ValueError:
        scorecards_rel = scorecards_path
    scorecards_str = str(scorecards_rel).replace("\\", "/")

    lines = [
        f"# {run_name} RQ1 Grounding v2 진단 보고",
        "",
        "## 1. 실행 개요",
        "",
        f"- **Run**: `{run_name}`",
        f"- **Scorecards**: `{scorecards_str}`",
        f"- **진단 스크립트**: `scripts/diagnose_rq1_grounding_sample.py --input <scorecards> --index <i>`",
        f"- **샘플 수**: N = {N}",
        "",
        "## 2. Run 단위 메트릭 (structural_metrics)",
        "",
        "| 구분 | 메트릭 | 값 |",
        "|------|--------|-----|",
    ]
    for name, val in metrics_rows:
        if name in ("n", "aspect_hallucination_rate", "alignment_failure_rate", "filter_rejection_rate", "semantic_hallucination_rate",
                    "implicit_grounding_rate", "explicit_grounding_rate", "explicit_grounding_failure_rate", "unsupported_polarity_rate",
                    "rq1_one_hot_sum", "legacy_unsupported_polarity_rate"):
            lines.append(f"| | {name} | {val} |")
    lines.extend(["", "## 3. 샘플별 5줄 진단 (index 0 ~ {})".format(N - 1), ""])
    lines.append("| index | text_id | selected_judgement_idx | rq1_bucket | drop_reason (align / filter / semantic) |")
    lines.append("|-------|---------|------------------------|------------|----------------------------------------|")
    for d in diag_rows:
        bucket = d["rq1_bucket"]
        if bucket not in ("implicit", "explicit", "explicit_failure", "unsupported"):
            bucket = bucket
        lines.append("| {} | {} | {} | **{}** | {} / {} / {} |".format(
            d["index"], d["text_id"], d["selected_judgement_idx"], d["rq1_bucket"],
            d["n_align"], d["n_filter"], d["n_semantic"]))
    lines.extend([
        "",
        "- **selected_tuple**: 각 샘플은 (aspect_term_norm, polarity) 1개로 대표됨.",
        "- **drop_reason**: alignment_failure / filter_rejection / semantic_hallucination 개수.",
        "",
    ])

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_md} (N={N})")


if __name__ == "__main__":
    main()
