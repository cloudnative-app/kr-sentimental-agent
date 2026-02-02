#!/usr/bin/env python
"""
HTML report builder for run artifacts.

Usage:
  python scripts/build_html_report.py --run_dir results/<run_id>_<mode> --out_dir reports/<run_id>_<mode> --profile ops
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


# ---------------- I/O helpers ----------------
def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------- Selection helpers ----------------
def pick_primary_ops_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {}
    for r in rows:
        if str(r.get("split", "")).lower() == "valid":
            return r
    return rows[0]


def pick_first(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return rows[0] if rows else {}


# ---------------- Metric extraction ----------------
def _get_from_dict_path(obj: Dict[str, Any], dot_path: str) -> Any:
    cur: Any = obj
    for part in dot_path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _to_number(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not math.isnan(v):
        return float(v)
    try:
        s = str(v).strip()
        if s == "" or s.lower() == "nan":
            return None
        return float(s)
    except Exception:
        return None


def extract_metric(metric_path: str, ctx: Dict[str, Any]) -> Any:
    if metric_path.startswith("ops."):
        return pick_primary_ops_row(ctx.get("ops_table", [])) .get(metric_path[4:])
    if metric_path.startswith("paper3."):
        return ctx.get("paper3_row", {}).get(metric_path[7:])
    if metric_path.startswith("paper4."):
        return ctx.get("paper4_row", {}).get(metric_path[7:])
    if metric_path.startswith("snapshot."):
        return _get_from_dict_path(ctx.get("snapshot", {}), metric_path[9:])
    if metric_path.startswith("derived."):
        return ctx.get("derived", {}).get(metric_path[8:])
    return None


# ---------------- Derived metrics ----------------
def compute_empty_output_rate(top_issues: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> Optional[float]:
    total_rows = _to_number(_get_from_dict_path(snapshot, "volume.total_rows")) or len(top_issues)
    if not total_rows:
        return None

    empty = 0
    for row in top_issues:
        flags_val = row.get("flags") or row.get("analysis_flags") or ""
        flags = {}
        if isinstance(flags_val, str):
            try:
                flags = json.loads(flags_val)
            except Exception:
                flags = {}
        elif isinstance(flags_val, dict):
            flags = flags_val

        if flags.get("empty_output") is True:
            empty += 1
            continue

        gen_failed = flags.get("generate_failed") or False
        parse_failed = flags.get("parse_failed") or False
        if gen_failed or parse_failed:
            continue  # unknown; do not mark empty

        preview = row.get("raw_output_preview") or row.get("parsed_output_preview") or ""
        if isinstance(preview, str) and preview.strip() in {"", "[]", "{}", "null", "None"}:
            empty += 1

    return empty / total_rows if total_rows else None


# ---------------- Threshold evaluation ----------------
def _match(cond: Dict[str, Any], value: float) -> bool:
    if "between" in cond:
        lo, hi = cond["between"]
        return lo <= value <= hi
    if "lte" in cond:
        return value <= cond["lte"]
    if "lt" in cond:
        return value < cond["lt"]
    if "gte" in cond:
        return value >= cond["gte"]
    if "gt" in cond:
        return value > cond["gt"]
    return False


def eval_verdict(value: Any, thresholds: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    num = _to_number(value)
    if num is None:
        return "N/A", "value missing"
    # Evaluate in pass -> warn -> fail order so strict pass ceilings win
    if thresholds.get("pass") and _match(thresholds["pass"], num):
        return "PASS", f"pass @{num}"
    if thresholds.get("warn") and _match(thresholds["warn"], num):
        return "WARN", f"warn @{num}"
    if thresholds.get("fail") and _match(thresholds["fail"], num):
        return "FAIL", f"fail @{num}"
    return "WARN", f"no rule matched @{num}"


# ---------------- Gate building ----------------
def _latency_never_fail() -> bool:
    """If latency_gate_config says latency never fails, return True (smoke/regression/paper_main)."""
    cfg_path = Path(__file__).resolve().parent.parent / "experiments" / "configs" / "latency_gate_config.yaml"
    if not cfg_path.exists() or not yaml:
        return True
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return bool(cfg.get("overall_policy", {}).get("latency_never_fail", True))
    except Exception:
        return True


def build_gate_rows(profile: str, rules: Dict[str, Any], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    gates = []
    profile_cfg = rules["profiles"][profile]
    latency_never_fail = _latency_never_fail()
    for gate_name in profile_cfg.get("gates", []):
        rule = rules["rules"][gate_name]
        val = extract_metric(rule["metric_path"], ctx)
        verdict, reason = eval_verdict(val, rule.get("thresholds", {}))
        if gate_name == "latency_ms_p95" and verdict == "FAIL" and latency_never_fail:
            verdict, reason = "WARN", f"warn @{val} (latency gate: never fail)"
        gates.append(
            {
                "gate": gate_name,
                "value": val,
                "verdict": verdict,
                "thresholds": rule.get("thresholds", {}),
                "meaning": rule.get("meaning", ""),
                "criterion": rule.get("criterion", ""),
                "reason": reason,
            }
        )
    return gates


def overall_verdict(gates: List[Dict[str, Any]], policy: Dict[str, Any]) -> str:
    verdicts = [g["verdict"] for g in gates if g["verdict"] != "N/A"]
    if any(v in policy.get("fail_if_any_gate_is", []) for v in verdicts):
        return "FAIL"
    if any(v in policy.get("warn_if_any_gate_is", []) for v in verdicts):
        return "WARN"
    return "PASS"


# ---------------- Rendering ----------------
def _fmt_thresholds(th: Dict[str, Any]) -> str:
    parts = []
    for k in ("fail", "warn", "pass"):
        if k in th:
            parts.append(f"{k}: {th[k]}")
    return "; ".join(parts)


def _html_table(rows: List[Dict[str, Any]], columns: List[Tuple[str, str]]) -> str:
    if not rows:
        return "<p><em>No data</em></p>"
    head = "".join(f"<th>{title}</th>" for _, title in columns)
    body_parts = []
    for r in rows:
        tds = "".join(f"<td>{'' if r.get(key) is None else r.get(key)}</td>" for key, _ in columns)
        body_parts.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_parts)}</tbody></table>"


def render_html(report: Dict[str, Any]) -> str:
    gates_table = _html_table(
        report["gates"],
        [
            ("gate", "Gate"),
            ("value", "Value"),
            ("verdict", "Verdict"),
            ("threshold_str", "Thresholds"),
            ("meaning", "Meaning"),
            ("criterion", "Criterion"),
        ],
    )

    css = """
    body { font-family: Arial, sans-serif; margin: 24px; }
    h1, h2 { margin-bottom: 6px; }
    .badge { padding: 6px 10px; border-radius: 6px; color: white; display: inline-block; }
    .PASS { background: #2e8b57; }
    .WARN { background: #f0ad4e; }
    .FAIL { background: #d9534f; }
    .NA { background: #777; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0; }
    th, td { border: 1px solid #ddd; padding: 6px; font-size: 13px; vertical-align: top; }
    th { background: #f5f5f5; }
    details { margin: 10px 0; }
    .warning-banner { background: #fff3cd; border: 2px solid #f0ad4e; padding: 12px; margin: 12px 0; border-radius: 6px; }
    .error-banner { background: #f8d7da; border: 2px solid #d9534f; padding: 12px; margin: 12px 0; border-radius: 6px; }
    """

    def badge(v: str) -> str:
        cls = "NA" if v == "N/A" else v
        return f'<span class="badge {cls}">{v}</span>'

    parts = [
        "<!doctype html><html><head>",
        "<meta charset='utf-8'>",
        f"<title>Run Report - {report['header'].get('run_id','')}</title>",
        f"<style>{css}</style>",
        "</head><body>",
        f"<h1>Run Report: {report['header'].get('run_id','')}</h1>",
    ]

    # Add warning banner for smoke/sanity runs
    purpose = report['header'].get('purpose', 'unknown')
    if purpose in ('smoke', 'sanity'):
        parts.append(f"""
        <div class="warning-banner">
            <strong>⚠️ {purpose.upper()} RUN - DO NOT USE FOR PAPER REPORTING</strong><br>
            This run has purpose="{purpose}" and should not be used for final paper metrics.
        </div>
        """)

    # Add error banner for split overlap
    split_overlap_rate = report['header'].get('split_overlap_any_rate', 0.0)
    if split_overlap_rate and split_overlap_rate > 0:
        overlap_msg = "Train/valid/test splits contain duplicate texts. Generalization metrics are unreliable."
        if purpose == "sanity":
            overlap_msg = "This is a SANITY run (integrity suite). Overlap is expected if split files are identical."
        parts.append(f"""
        <div class="error-banner">
            <strong>🛑 SPLIT OVERLAP DETECTED</strong><br>
            Overlap rate: {split_overlap_rate:.2%}<br>
            {overlap_msg}
        </div>
        """)

    parts.extend([
        "<div>",
        f"<strong>Timestamp:</strong> {report['header'].get('timestamp_utc','N/A')} &nbsp; ",
        f"<strong>cfg_hash:</strong> {report['header'].get('cfg_hash','N/A')} &nbsp; ",
        f"<strong>backbone:</strong> {report['header'].get('backbone_model_id','N/A')} &nbsp; ",
        f"<strong>purpose:</strong> {purpose}",
        "</div>",
        f"<h2>Overall Verdict {badge(report['overall'])}</h2>",
        gates_table,
    ])

    parts.append("<details><summary>Ops table</summary>")
    parts.append(report["ops_table_html"])
    parts.append("</details>")

    parts.append("<details><summary>Top issues</summary>")
    parts.append(report["top_issues_html"])
    parts.append("</details>")

    if report.get("paper3_html"):
        parts.append("<details open><summary>Paper Table 3 (main results)</summary>")
        parts.append(report["paper3_html"])
        parts.append("</details>")
    if report.get("paper4_html"):
        parts.append("<details open><summary>Paper Table 4 (failure breakdown)</summary>")
        parts.append(report["paper4_html"])
        parts.append("</details>")

    parts.append("</body></html>")
    return "".join(parts)


# ---------------- Main assembly ----------------
def build_report(run_dir: Path, out_dir: Path, profile: str, rules_path: Path, strict: bool = False) -> Path:
    if not rules_path.exists():
        raise SystemExit(f"rules file not found: {rules_path}")
    if rules_path.suffix == ".json":
        rules = load_json(rules_path)
    else:
        if yaml is None:
            raise SystemExit("pyyaml not installed; install or supply JSON rules.")
        rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))

    if profile not in rules.get("profiles", {}):
        raise SystemExit(f"profile '{profile}' not defined in rules")

    # Load artifacts
    snapshot = load_json(run_dir / "ops_outputs" / "run_snapshot.json")
    ops_table = load_csv(run_dir / "ops_outputs" / "ops_table.csv")
    top_issues = load_csv(run_dir / "ops_outputs" / "top_issues.csv")
    paper3 = load_csv(run_dir / "paper_outputs" / "paper_table_3_main_results.csv")
    paper4 = load_csv(run_dir / "paper_outputs" / "paper_table_4_failure_breakdown.csv")

    # Optional fallback: paper -> ops when artifacts missing
    if profile == "paper" and (not paper3 or not paper4) and not strict:
        profile = "ops"

    required = rules["profiles"][profile].get("required_artifacts", [])
    missing = [a for a in required if not (run_dir / a).exists()]
    if missing and strict:
        raise SystemExit(f"Missing required artifacts for profile '{profile}': {missing}")

    derived = {
        "empty_output_rate": compute_empty_output_rate(top_issues, snapshot),
    }

    ctx = {
        "snapshot": snapshot,
        "ops_table": ops_table,
        "paper3_row": pick_first(paper3),
        "paper4_row": pick_first(paper4),
        "derived": derived,
    }

    gates = build_gate_rows(profile, rules, ctx)
    for g in gates:
        g["threshold_str"] = _fmt_thresholds(g.get("thresholds", {}))

    overall = overall_verdict(gates, rules.get("overall_policy", {}))

    # Get purpose and integrity info from snapshot
    purpose = snapshot.get("purpose", "unknown")
    integrity = snapshot.get("integrity") or {}
    split_overlap_any_rate = integrity.get("split_overlap_any_rate", 0.0)

    # For paper profile with split overlap, upgrade overall verdict to at least WARN
    if profile == "paper" and split_overlap_any_rate and split_overlap_any_rate > 0:
        if overall == "PASS":
            overall = "WARN"
        if strict:
            overall = "FAIL"

    report_dict = {
        "header": {
            "run_id": snapshot.get("run_id") or run_dir.name,
            "timestamp_utc": snapshot.get("timestamp_utc") or snapshot.get("timestamp"),
            "cfg_hash": snapshot.get("cfg_hash") or _get_from_dict_path(snapshot, "config.cfg_hash"),
            "backbone_model_id": snapshot.get("backbone_model_id") or _get_from_dict_path(snapshot, "backbone.model"),
            "purpose": purpose,
            "split_overlap_any_rate": split_overlap_any_rate,
        },
        "overall": overall,
        "gates": gates,
        "ops_table_html": _html_table(ops_table, [(k, k) for k in (ops_table[0].keys() if ops_table else [])]),
        "top_issues_html": _html_table(top_issues, [(k, k) for k in (top_issues[0].keys() if top_issues else [])]),
        "paper3_html": _html_table(paper3, [(k, k) for k in (paper3[0].keys() if paper3 else [])]) if paper3 else "",
        "paper4_html": _html_table(paper4, [(k, k) for k in (paper4[0].keys() if paper4 else [])]) if paper4 else "",
    }

    ensure_dir(out_dir)
    out_path = out_dir / "index.html"
    out_path.write_text(render_html(report_dict), encoding="utf-8")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", required=True, help="results/<run_id>_<mode>")
    ap.add_argument("--out_dir", required=True, help="reports/<run_id>_<mode>")
    ap.add_argument("--profile", choices=["ops", "paper"], default="ops")
    ap.add_argument("--rules", default=None, help="Rules file path (default: auto-select based on profile)")
    ap.add_argument("--strict", action="store_true", help="missing required artifacts -> fatal")
    ap.add_argument("--open", action="store_true", help="print output path only")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir)
    
    # Auto-select rules file based on profile if not specified
    if args.rules:
        rules_path = Path(args.rules)
    else:
        if args.profile == "paper":
            rules_path = Path("scripts/paper_rules.yaml")
        else:
            rules_path = Path("scripts/ops_rules.yaml")

    out_path = build_report(run_dir, out_dir, args.profile, rules_path, strict=args.strict)
    print(out_path)


if __name__ == "__main__":
    main()
