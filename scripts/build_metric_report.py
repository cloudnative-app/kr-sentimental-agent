#!/usr/bin/env python3
"""
Metric Report HTML generator for ABSA runs.

Reads run_dir (manifest.json, scorecards.jsonl, derived/metrics/structural_metrics.csv)
and produces a single-page HTML report with:
  Header, Executive Summary (10 KPI cards + conclusion), RQ1/RQ3/RQ2, Efficiency/QA, Memory Growth, Appendix, KPI↔로그 필드 매핑.

Usage:
  python scripts/build_metric_report.py --run_dir results/real_mini_r1_proposed --out_dir reports/real_mini_r1_proposed
  python scripts/build_metric_report.py --run_dir results/real_mini_r1_proposed
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEBATE_THRESHOLDS_PATH = PROJECT_ROOT / "experiments" / "configs" / "debate_thresholds.json"

# Ensure project root is on path when run as script (e.g. python scripts/build_metric_report.py)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Tuple = (aspect_ref, aspect_term, polarity). Pipeline uses aspect_term only. See docs/absa_tuple_eval.md.
TupleAspectPolarity = Tuple[str, str, str]
SCHEMA_VERSION = "scorecard_v2"

# KPI list: Outcome (RQ) first (paper-claimable), then Process (validator-level diagnostic).
# Process metrics: "Validator-level diagnostic. Not an outcome metric."
# (label, struct_key, mg_key, tip)
KPI_LIST = [
    # Outcome (RQ)
    ("Severe Polarity Error (L3)", "severe_polarity_error_L3_rate", None, "Aspect matches gold, polarity mismatch only (L4/L5 excluded). Outcome (RQ)."),
    ("Polarity Conflict Rate", "polarity_conflict_rate", None, "Same-aspect polarity conflict after representative. Outcome (RQ)."),
    ("generalized F1@0.95", "generalized_f1_theta", None, "Neveditsin et al. variant (θ=0.95). Outcome (RQ). N/A if embedding not run."),
    ("Tuple Agreement Rate", "tuple_agreement_rate", None, "Final tuple sets identical across runs (n_trials≥2). Outcome (RQ2)."),
    ("Tuple F1 (Final)", "tuple_f1_s2", None, "Explicit-only tuple F1 (primary). Implicit cases = different inference task. Outcome (RQ)."),
    # Process (internal)
    ("Validator Clear Rate", "validator_clear_rate", None, "Validator-level diagnostic. Not an outcome metric. Stage1 structural risk → Stage2 cleared."),
    ("Validator Residual Risk Rate", "validator_residual_risk_rate", None, "Validator-level diagnostic. Not an outcome metric. Stage2 Validator risks>0."),
    ("Self-Consistency", "self_consistency_exact", None, "Trial별 final label agreement. N/A if single run."),
    ("Flip-flop Rate", "flip_flop_rate", None, "Trial 간 final 변경 빈도. variance proxy."),
    ("Override Applied Rate", "override_applied_rate", None, "Eligible 대비 applied 비율."),
    ("Override Success Rate", "override_success_rate", None, "Applied 중 risk 개선 비율."),
    ("Store Size", None, "store_size", "memory_growth_metrics.store_size. 메모리 off 시 N/A."),
    ("Retrieval Hit Rate@k", None, "retrieval_hit_k", "retrieval.hit 평균. 메모리 off 시 N/A."),
]

# KPI ↔ log field mapping (Task E). Outcome (RQ) vs Process.
KPI_FIELD_MAPPING = [
    ("Severe Polarity Error (L3)", "severe_polarity_error_L3_rate (aspect match, polarity mismatch)"),
    ("Polarity Conflict Rate", "polarity_conflict_rate (same-aspect after representative)"),
    ("generalized F1@0.95", "generalized_f1_theta (Neveditsin variant θ=0.95)"),
    ("Tuple Agreement Rate", "tuple_agreement_rate (n_trials≥2, final tuple sets equal)"),
    ("Tuple F1 (Final)", "tuple_f1_s2_explicit_only / tuple_f1_s2 (primary: explicit-only)"),
    ("Validator Clear Rate", "Process. validator_clear_rate (Validator-level diagnostic)"),
    ("Validator Residual Risk Rate", "Process. validator_residual_risk_rate (internal diagnostic)"),
    ("Self-Consistency", "self_consistency_exact (trial label agreement)"),
    ("Flip-flop Rate", "flip_flop_rate (variance proxy)"),
    ("Override Applied Rate", "override_applied_rate"),
    ("Override Success Rate", "override_success_rate"),
    ("Store Size", "memory_growth_metrics.store_size"),
    ("Retrieval Hit Rate@k", "memory_growth_metrics.retrieval_hit_k"),
]

from metrics.eval_tuple import (
    gold_tuple_set_from_record,
    precision_recall_f1_tuple,
    tuples_from_list,
    tuples_to_pairs,
    tuple_sets_match_with_empty_rule,
)


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_debate_thresholds() -> Dict[str, float]:
    defaults = {
        "coverage_warn": 0.4,
        "coverage_high": 0.25,
        "no_match_warn": 0.4,
        "no_match_high": 0.6,
        "neutral_warn": 0.4,
        "neutral_high": 0.6,
    }
    data = load_json(DEBATE_THRESHOLDS_PATH)
    if not data:
        return defaults
    out = dict(defaults)
    for k, v in data.items():
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_structural_metrics_csv(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def ensure_structural_metrics(run_dir: Path, derived_dir: Path, profile: str = "paper_main") -> Path:
    """Run structural_error_aggregator if structural_metrics.csv missing; return path to CSV."""
    metrics_dir = derived_dir / "metrics"
    csv_path = metrics_dir / "structural_metrics.csv"
    if csv_path.exists():
        return csv_path
    metrics_dir.mkdir(parents=True, exist_ok=True)
    scorecards = run_dir / "scorecards.jsonl"
    if not scorecards.exists():
        return csv_path
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "structural_error_aggregator.py"),
        "--input", str(scorecards),
        "--outdir", str(metrics_dir),
        "--profile", profile,
    ]
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    return csv_path


def ensure_transition_metrics(run_dir: Path, derived_dir: Path, profile: str = "paper_main") -> Path:
    """Run transition_aggregator on scorecards; write transition_summary.json + transition_table.csv. Return path to summary."""
    metrics_dir = derived_dir / "metrics"
    summary_path = metrics_dir / "transition_summary.json"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    scorecards = run_dir / "scorecards.jsonl"
    if not scorecards.exists():
        return summary_path
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "transition_aggregator.py"),
        "--input", str(scorecards),
        "--outdir", str(metrics_dir),
        "--profile", profile,
    ]
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
    return summary_path


def _rate(num: int, denom: int) -> float:
    return (num / denom) if denom else 0.0


def _pct(v: float) -> str:
    if v is None:
        return "N/A"
    return f"{float(v) * 100:.1f}%"


def _num(v: Any) -> str:
    if v is None or v == "":
        return "N/A"
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return f"{f:.4f}"
    except (TypeError, ValueError):
        return str(v)


# ---------- HF agree/disagree (same logic as structural_error_aggregator) ----------
def _norm_polarity(label: str) -> str:
    if not label:
        return "neu"
    key = (label or "").strip().lower()
    norm = {"positive": "pos", "pos": "pos", "negative": "neg", "neg": "neg", "neutral": "neu", "neu": "neu", "mixed": "neu"}
    return norm.get(key) or "neu"


def _get_hf_label(record: Dict[str, Any]) -> Optional[str]:
    hf = (record.get("aux_signals") or {}).get("hf") or {}
    return hf.get("label")


def _get_final_polarity(record: Dict[str, Any]) -> str:
    mod = record.get("moderator") or {}
    final = (mod.get("final_label") or (record.get("final_result") or {}).get("label") or "")
    return _norm_polarity(final)


def _hf_disagrees_with_final(record: Dict[str, Any]) -> bool:
    hf_label = _get_hf_label(record)
    if hf_label is None:
        return False
    return _norm_polarity(hf_label) != _get_final_polarity(record)


def _has_same_aspect_polarity_conflict(record: Dict[str, Any]) -> bool:
    """RQ1: 동일 aspect span 내 polarity 충돌 (final tuples에서 동일 aspect에 서로 다른 polarity)."""
    tuples = _extract_final_tuples(record)
    if not tuples:
        return False
    by_aspect: Dict[str, Set[str]] = {}
    for (_a, aspect_term, polarity) in tuples:
        t = (aspect_term or "").strip()
        if not t:
            continue
        if t not in by_aspect:
            by_aspect[t] = set()
        by_aspect[t].add((polarity or "").strip())
    return any(len(pols) >= 2 for pols in by_aspect.values())


def _has_polarity_conflict(record: Dict[str, Any]) -> bool:
    """RQ1: same-aspect polarity conflict only (align with structural_error_aggregator)."""
    return _has_same_aspect_polarity_conflict(record)


def _norm_txt(t: Optional[str]) -> str:
    if t is None:
        return ""
    t = (t or "").strip().lower()
    for p in ".,;:!?\"'`""''()[]{}":
        t = t.strip(p)
    return " ".join(t.split())


def _aspect_term_text(it: dict) -> str:
    """Get aspect surface-form text from item (aspect_term.term or string)."""
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return (it.get("opinion_term") or {}).get("term") or ""


def _tuples_from_list_of_dicts(items: Any) -> Set[TupleAspectPolarity]:
    """Convert list of {aspect_ref?, aspect_term, polarity} dicts to set. Pipeline uses aspect_term only (no aspect_ref)."""
    if not items or not isinstance(items, (list, tuple)):
        return set()
    out: Set[TupleAspectPolarity] = set()
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        a = (it.get("aspect_ref") or "").strip()
        t = _aspect_term_text(it)
        p = (it.get("polarity") or it.get("label") or "").strip()
        if a or t:
            out.add((a, t, p))
    return out


def _extract_final_tuples(record: Dict[str, Any]) -> Set[TupleAspectPolarity]:
    """Prefer final_result.final_tuples when present; else final_aspects or inputs.aspect_sentiments."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    final_tuples = final_result.get("final_tuples")
    if final_tuples and isinstance(final_tuples, list):
        out = _tuples_from_list_of_dicts(final_tuples)
        if out:
            return out
    final_aspects = final_result.get("final_aspects")
    if final_aspects:
        out = tuples_from_list(final_aspects)
        if out:
            return out
    sents = (record.get("inputs") or {}).get("aspect_sentiments")
    return tuples_from_list(sents) if sents else set()


def _extract_stage1_tuples(record: Dict[str, Any]) -> Set[TupleAspectPolarity]:
    """Prefer final_result.stage1_tuples when present; else process_trace Stage1 ATSA aspect_sentiments."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    stage1_tuples = final_result.get("stage1_tuples")
    if stage1_tuples and isinstance(stage1_tuples, list):
        out = _tuples_from_list_of_dicts(stage1_tuples)
        if out:
            return out
    trace = (record.get("runtime") or {}).get("process_trace") or record.get("process_trace") or []
    for entry in trace:
        if (entry.get("stage") or "").lower() == "stage1" and (entry.get("agent") or "").lower() == "atsa":
            sents = (entry.get("output") or {}).get("aspect_sentiments")
            if sents:
                return tuples_from_list(sents)
    return _extract_final_tuples(record)


def _extract_gold_tuples(record: Dict[str, Any]) -> Optional[Set[TupleAspectPolarity]]:
    return gold_tuple_set_from_record(record)


def compute_stage2_correction_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """When gold tuples exist: FixRate, BreakRate, NetGain, CorrPrec, CIS, Tuple F1 S1/S2, ΔF1. Else N/A. See docs/absa_tuple_eval.md."""
    out: Dict[str, Any] = {
        "tuple_f1_s1": None, "tuple_f1_s2": None, "delta_f1": None,
        "triplet_f1_s1": None, "triplet_f1_s2": None,
        "fix_rate": None, "break_rate": None, "net_gain": None,
        "correction_precision": None, "conservative_improvement_score": None,
        "n_fix": 0, "n_break": 0, "n_still": 0, "n_keep": 0, "N_gold": 0,
    }
    rows_with_gold = [(r, _extract_gold_tuples(r)) for r in rows if _extract_gold_tuples(r) is not None]
    if not rows_with_gold:
        return out
    N = len(rows_with_gold)
    f1_s1_list: List[float] = []
    f1_s2_list: List[float] = []
    n_fix = n_break = n_still = n_keep = 0
    for record, gold in rows_with_gold:
        gold = gold or set()
        s1 = _extract_stage1_tuples(record)
        s2 = _extract_final_tuples(record)
        _, _, f1_1 = precision_recall_f1_tuple(gold, s1)
        _, _, f1_2 = precision_recall_f1_tuple(gold, s2)
        f1_s1_list.append(f1_1)
        f1_s2_list.append(f1_2)
        st1 = tuple_sets_match_with_empty_rule(gold, s1)
        st2 = tuple_sets_match_with_empty_rule(gold, s2)
        if not st1 and st2:
            n_fix += 1
        if st1 and not st2:
            n_break += 1
        if not st1 and not st2:
            n_still += 1
        if st1 and st2:
            n_keep += 1
    out["N_gold"] = N
    out["n_fix"] = n_fix
    out["n_break"] = n_break
    out["n_still"] = n_still
    out["n_keep"] = n_keep
    if f1_s1_list:
        out["tuple_f1_s1"] = sum(f1_s1_list) / len(f1_s1_list)
        out["triplet_f1_s1"] = out["tuple_f1_s1"]
    if f1_s2_list:
        out["tuple_f1_s2"] = sum(f1_s2_list) / len(f1_s2_list)
        out["triplet_f1_s2"] = out["tuple_f1_s2"]
    if f1_s1_list and f1_s2_list:
        out["delta_f1"] = out["tuple_f1_s2"] - out["tuple_f1_s1"]
    # FixRate = n_fix / (n_fix + n_still); BreakRate = n_break / (n_break + n_keep); NetGain = (n_fix - n_break) / N
    need_fix = n_fix + n_still
    out["fix_rate"] = _rate(n_fix, need_fix) if need_fix else None
    keep_break = n_break + n_keep
    out["break_rate"] = _rate(n_break, keep_break) if keep_break else None
    out["net_gain"] = (n_fix - n_break) / N if N else None
    change_denom = n_fix + n_break
    out["correction_precision"] = _rate(n_fix, change_denom) if change_denom else None
    # CIS = (n_fix - 2*n_break) / (n_fix + n_still), λ=2
    cis_denom = n_fix + n_still
    out["conservative_improvement_score"] = (n_fix - 2 * n_break) / cis_denom if cis_denom else None
    return out


def _count_stage1_risks(record: Dict[str, Any]) -> int:
    for vb in record.get("validator") or []:
        if (vb.get("stage") or "").lower() == "stage1":
            return len(vb.get("structural_risks") or [])
    return 0


def _count_stage2_risks(record: Dict[str, Any]) -> int:
    for vb in record.get("validator") or []:
        if (vb.get("stage") or "").lower() == "stage2":
            return len(vb.get("structural_risks") or [])
    return 0


def compute_subset_rates(rows: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Risk Resolution Rate, Stage2 Adoption Rate, Polarity Conflict Rate for a subset of rows."""
    N = len(rows)
    if N == 0:
        return {"risk_resolution_rate": None, "stage2_adoption_rate": None, "polarity_conflict_rate": None}
    risk_s1 = sum(_count_stage1_risks(r) for r in rows)
    risk_s2 = sum(_count_stage2_risks(r) for r in rows)
    resolved = max(0, risk_s1 - risk_s2)
    risk_resolution_rate = _rate(resolved, risk_s1) if risk_s1 else None
    stage2_count = sum(1 for r in rows if (r.get("moderator") or {}).get("selected_stage") == "stage2")
    stage2_adoption_rate = _rate(stage2_count, N)
    polarity_conflict_count = sum(1 for r in rows if _has_polarity_conflict(r))
    polarity_conflict_rate = _rate(polarity_conflict_count, N)
    return {
        "risk_resolution_rate": risk_resolution_rate,
        "stage2_adoption_rate": stage2_adoption_rate,
        "polarity_conflict_rate": polarity_conflict_rate,
    }


def compute_from_scorecards(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    N = len(rows)
    if N == 0:
        return {"n": 0}

    # Structural PASS: summary.quality_pass
    pass_count = sum(1 for r in rows if (r.get("summary") or {}).get("quality_pass") is True)
    structural_pass_rate = _rate(pass_count, N)

    # Stage2 Adoption: moderator.selected_stage == "stage2"
    stage2_count = sum(1 for r in rows if (r.get("moderator") or {}).get("selected_stage") == "stage2")
    stage2_adoption_rate = _rate(stage2_count, N)

    # Rule A/B/M/D breakdown (applied_rules)
    rule_counter: Counter = Counter()
    for r in rows:
        rules = (r.get("moderator") or {}).get("applied_rules") or []
        for rule in rules:
            rule_counter[rule] += 1

    # risk_id frequency (validator.structural_risks)
    risk_counter: Counter = Counter()
    for r in rows:
        for stage_block in r.get("validator") or []:
            for risk in stage_block.get("structural_risks") or []:
                rid = (risk.get("risk_id") or risk.get("type") or "").strip()
                if rid:
                    risk_counter[rid] += 1

    # risk resolution: stage1 risks vs stage2 risks (resolved = s1 - s2)
    risk_resolved_count = 0
    risk_s1_total = 0
    for r in rows:
        validator = r.get("validator") or []
        s1_risks = 0
        s2_risks = 0
        for vb in validator:
            stage = (vb.get("stage") or "").lower()
            n_risk = len(vb.get("structural_risks") or [])
            if stage == "stage1":
                s1_risks = n_risk
            elif stage == "stage2":
                s2_risks = n_risk
        if s1_risks > 0:
            risk_s1_total += s1_risks
            if s2_risks < s1_risks:
                risk_resolved_count += 1  # at least one resolved for this sample

    # Latencies for p50/p95
    latencies: List[float] = []
    gate_status_counter: Counter = Counter()
    parse_fail = 0
    gen_fail = 0
    fallback = 0
    for r in rows:
        meta = r.get("meta") or {}
        lat = meta.get("latency_ms")
        if lat is not None:
            try:
                latencies.append(float(lat))
            except (TypeError, ValueError):
                pass
        lat_block = r.get("latency") or {}
        gate = lat_block.get("gate_status") or ""
        if gate:
            gate_status_counter[gate] += 1
        fl = r.get("flags") or {}
        if fl.get("parse_failed"):
            parse_fail += 1
        if fl.get("generate_failed"):
            gen_fail += 1
        if fl.get("fallback_used"):
            fallback += 1

    latencies.sort()
    n_lat = len(latencies)
    latency_p50 = latencies[n_lat // 2] if n_lat else None
    latency_p95 = latencies[int(n_lat * 0.95)] if n_lat and n_lat >= 2 else (latencies[-1] if latencies else None)

    return {
        "n": N,
        "structural_pass_rate": structural_pass_rate,
        "stage2_adoption_rate": stage2_adoption_rate,
        "rule_counts": dict(rule_counter),
        "risk_id_counts": dict(risk_counter),
        "risk_resolved_samples": risk_resolved_count,
        "risk_s1_total": risk_s1_total,
        "latency_p50_ms": latency_p50,
        "latency_p95_ms": latency_p95,
        "latencies": latencies,
        "gate_status": dict(gate_status_counter),
        "parse_failure_count": parse_fail,
        "generate_failure_count": gen_fail,
        "fallback_used_count": fallback,
        "parse_failure_rate": _rate(parse_fail, N),
        "generate_failure_rate": _rate(gen_fail, N),
        "fallback_used_rate": _rate(fallback, N),
    }


def generate_conclusion_3lines(metrics: Dict[str, Any], struct: Dict[str, Any]) -> List[str]:
    """Auto-generate 3-line conclusion from KPIs."""
    n = metrics.get("n") or struct.get("n") or 0
    if n == 0:
        return ["No samples in this run.", "", ""]

    pass_rate = metrics.get("structural_pass_rate")
    rr = _to_float(struct.get("validator_clear_rate")) or _to_float(struct.get("risk_resolution_rate"))
    gcr = _to_float(struct.get("guided_change_rate"))
    udr = _to_float(struct.get("unguided_drift_rate"))
    stage2 = metrics.get("stage2_adoption_rate")
    pol_conf = _to_float(struct.get("polarity_conflict_rate"))
    n_gold = _to_float(struct.get("N_gold")) or 0
    f1_s1 = _to_float(struct.get("tuple_f1_s1")) or _to_float(struct.get("triplet_f1_s1"))
    f1_s2 = _to_float(struct.get("tuple_f1_s2")) or _to_float(struct.get("triplet_f1_s2"))
    delta_f1 = _to_float(struct.get("delta_f1"))

    line1 = f"본 Run은 샘플 수 N={n} 기준, 구조 품질 통과율(Structural PASS) {_pct(pass_rate) if pass_rate is not None else 'N/A'}, "
    line1 += f"극성 충돌률 {_pct(pol_conf) if pol_conf is not None else 'N/A'}, 위험 해소율 {_pct(rr) if rr is not None else 'N/A'}로 집계되었습니다."

    line2 = f"Stage2 채택률 {_pct(stage2) if stage2 is not None else 'N/A'}, "
    line2 += f"가이드 변경률 {_pct(gcr) if gcr is not None else 'N/A'}, 비가이드 드리프트 {_pct(udr) if udr is not None else 'N/A'}입니다."
    if n_gold and (f1_s1 is not None or f1_s2 is not None):
        line2 += f" 골드 N={int(n_gold)} 기준 Tuple F1(Stage1) {_pct(f1_s1) if f1_s1 is not None else 'N/A'}, F1(Stage2+Mod) {_pct(f1_s2) if f1_s2 is not None else 'N/A'}, ΔF1 {_num(delta_f1) if delta_f1 is not None else 'N/A'} (Tuple Aspect,Polarity)."

    line3 = "추가 검증이 필요하면 Appendix의 샘플별 상세를 참고하세요."
    return [line1, line2, line3]


def _to_float(v: Any) -> Optional[float]:
    """Normalize to scalar float. Handles None, (mean, std) tuple, or string."""
    if v is None or v == "":
        return None
    # (mean, std) or [mean, std]: use first element as scalar
    if isinstance(v, (list, tuple)) and len(v) >= 1:
        return _to_float(v[0])
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_html(
    run_dir: Path,
    manifest: Dict[str, Any],
    scorecards: List[Dict[str, Any]],
    struct_metrics: Dict[str, Any],
    computed: Dict[str, Any],
    stage2_correction: Dict[str, Any],
    transition_summary: Dict[str, Any],
    out_path: Path,
    top_n: int = 15,
    memory_growth_rows: Optional[List[Dict[str, Any]]] = None,
    memory_growth_plot_path: Optional[Path] = None,
    memory_off: bool = False,
) -> None:
    run_id = manifest.get("run_id") or run_dir.name
    date_utc = (manifest.get("timestamp_utc") or "").replace("Z", " UTC")
    profile = manifest.get("purpose") or computed.get("profile") or "—"
    backbone = manifest.get("backbone") or {}
    provider = backbone.get("provider") or "—"
    model = backbone.get("model") or "—"
    episodic_memory = manifest.get("episodic_memory")
    memory_label = "—"
    if isinstance(episodic_memory, dict):
        cond = episodic_memory.get("condition") or ""
        memory_label = f"{cond} (on)" if cond == "C2" else (f"{cond} (off)" if cond == "C1" else (f"{cond} (silent)" if cond == "C2_silent" else cond or "—"))
    elif episodic_memory is not None:
        memory_label = str(episodic_memory)
    dataset = "—"
    ds = manifest.get("dataset") or {}
    paths = ds.get("paths") or ds.get("resolved_paths") or {}
    train_file = paths.get("train_file") or ""
    if train_file:
        dataset = Path(train_file).name
    n = computed.get("n") or struct_metrics.get("n") or 0
    cfg_hash = (manifest.get("cfg_hash") or "")[:16]
    prompt_versions = manifest.get("prompt_versions") or {}
    prompt_hash = (list(prompt_versions.values())[0][:12]) if prompt_versions else "—"

    conclusion_lines = generate_conclusion_3lines(computed, struct_metrics)

    # KPI: cards from KPI_LIST (struct_metrics + memory_growth last row). Prefer new keys; fallback to deprecated.
    memory_growth_last = (memory_growth_rows or [])[-1] if memory_growth_rows else {}
    kpi_cards: List[Tuple[str, Optional[float], Optional[float], str]] = []
    _struct_fallback = {
        "validator_residual_risk_rate": "residual_risk_rate",
        "validator_clear_rate": "risk_resolution_rate",
        "severe_polarity_error_L3_rate": None,
        "generalized_f1_theta": None,
        "tuple_agreement_rate": None,
    }
    for label, struct_key, mg_key, tip in KPI_LIST:
        val: Optional[float] = None
        max_v: Optional[float] = 1.0
        if struct_key:
            val = _to_float(struct_metrics.get(struct_key))
            if val is None and struct_key in _struct_fallback and _struct_fallback[struct_key]:
                val = _to_float(struct_metrics.get(_struct_fallback[struct_key]))
            # Primary F1: explicit-only (implicit is a different inference task)
            if struct_key == "tuple_f1_s2":
                val = (_to_float(struct_metrics.get("tuple_f1_s2_explicit_only"))
                    or _to_float(struct_metrics.get("tuple_f1_s2"))
                    or _to_float(struct_metrics.get("triplet_f1_s2"))
                    or _to_float(stage2_correction.get("tuple_f1_s2_explicit_only"))
                    or _to_float(stage2_correction.get("tuple_f1_s2"))
                    or _to_float(stage2_correction.get("triplet_f1_s2")))
        if mg_key and val is None:
            raw = memory_growth_last.get(mg_key)
            if raw is not None:
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    val = None
            if mg_key == "store_size":
                max_v = None
        kpi_cards.append((label, val, max_v, tip))

    # Debate warn box (not KPI cards): load for suggestions only
    debate_cov_kpi = _to_float(struct_metrics.get("debate_mapping_coverage"))
    debate_fail_no_match_kpi = _to_float(struct_metrics.get("debate_fail_no_match_rate"))
    debate_fail_neutral_kpi = _to_float(struct_metrics.get("debate_fail_neutral_stance_rate"))
    thresholds = load_debate_thresholds()

    def _kpi_class_and_tip(label: str, value: Optional[float], tip: str) -> Tuple[str, str]:
        if value is None:
            return "kpi-neutral", tip or "N/A"
        if label == "Severe Polarity Error (L3)":
            return ("kpi-warn", tip) if (value and value > 0.2) else ("kpi-ok", tip)
        if label == "Polarity Conflict Rate":
            return ("kpi-warn", tip) if (value and value > 0.3) else ("kpi-ok", tip)
        if label == "generalized F1@0.95":
            return ("kpi-warn", tip) if (value is not None and value < 0.7) else ("kpi-ok", tip)
        if label == "Tuple Agreement Rate":
            return ("kpi-warn", tip) if (value is not None and value < 0.8) else ("kpi-ok", tip)
        if label == "Validator Residual Risk Rate":
            return ("kpi-warn", tip) if (value and value > 0.3) else ("kpi-ok", tip)
        if label == "Validator Clear Rate":
            return ("kpi-warn", tip) if (value is not None and value < 0.3) else ("kpi-ok", tip)
        if label == "Override Success Rate":
            return ("kpi-warn", tip) if (value is not None and value < 0.5) else ("kpi-ok", tip)
        if label == "Tuple F1 (Final)" and value is not None:
            return ("kpi-warn", tip) if value < 0.7 else ("kpi-ok", tip)
        return "kpi-ok", tip or "정상 범위"

    kpi_html = ""
    for label, val, max_v, tip in kpi_cards:
        v = val if val is not None else 0
        cls, tooltip = _kpi_class_and_tip(label, val, tip)
        disp = _num(v) if max_v is None else (_pct(v) if 0 <= v <= 1 else _num(v))
        if val is None:
            disp = "—"
        kpi_html += (
            f'<div class="kpi-card {cls}" title="{tooltip}" data-kpi-title="{label}" data-kpi-tip="{tooltip}">'
            f'<div class="kpi-title">{label}</div>'
            f'<div class="kpi-value">{disp}</div>'
            f"</div>"
        )

    def _warn_level(flag: bool) -> str:
        return "HIGH" if flag else "LOW"

    def _suggestions() -> List[str]:
        tips: List[str] = []
        if debate_cov_kpi is not None and debate_cov_kpi < thresholds["coverage_warn"]:
            tips.append("Coverage↑: 토론 프롬프트에 aspect_terms 명시, synonym_hints 확장, aspect_token_regex 점검")
        if debate_fail_no_match_kpi is not None and debate_fail_no_match_kpi > thresholds["no_match_warn"]:
            tips.append("No-match↓: aspect_synonyms 보강, 토론 발언에 aspect_term 명시 유도")
        if debate_fail_neutral_kpi is not None and debate_fail_neutral_kpi > thresholds["neutral_warn"]:
            tips.append("Neutral↓: persona stance 강화, critic/empath 발언 지침 강화")
        return tips

    debate_warn = ""
    if debate_cov_kpi is not None and debate_cov_kpi < thresholds["coverage_warn"]:
        lvl = _warn_level(debate_cov_kpi < thresholds["coverage_high"])
        debate_warn += f"<p class=\"header-meta\">[WARN/{lvl}] Debate mapping coverage is low; review debate prompts or synonym hints.</p>"
    if debate_fail_no_match_kpi is not None and debate_fail_no_match_kpi > thresholds["no_match_warn"]:
        lvl = _warn_level(debate_fail_no_match_kpi > thresholds["no_match_high"])
        debate_warn += f"<p class=\"header-meta\">[WARN/{lvl}] Debate mapping no_match rate is high; consider expanding aspect synonyms.</p>"
    if debate_fail_neutral_kpi is not None and debate_fail_neutral_kpi > thresholds["neutral_warn"]:
        lvl = _warn_level(debate_fail_neutral_kpi > thresholds["neutral_high"])
        debate_warn += f"<p class=\"header-meta\">[WARN/{lvl}] Debate mapping neutral_stance rate is high; consider sharper persona stance.</p>"
    if debate_warn:
        tips = _suggestions()
        tips_html = ""
        if tips:
            tips_html = "<ul>" + "".join(f"<li>{t}</li>" for t in tips) + "</ul>"
        debate_warn = f"<div class=\"warn-box\">{debate_warn}{tips_html}</div>"
    already_confident_rate = _to_float(struct_metrics.get("debate_override_skipped_already_confident_rate"))
    if already_confident_rate is not None and already_confident_rate > 0.5:
        debate_warn += (
            '<div class="header-meta" style="background:#fff3cd;border:1px solid #f0ad4e;padding:8px;margin:8px 0;border-radius:4px;">'
            "<strong>해석:</strong> override가 적게 적용된 주된 이유가 ‘이미 확신 충분’(min_target_conf)일 수 있습니다. "
            "Skipped (Already Confident) 비율이 0.5 초과이면, 적용된 케이스만 보는 조건부 지표를 참고하세요."
            "</div>"
        )

    # HF: external reference only (not correctness criterion). HF-agree/disagree for Appendix / error analysis only.
    hf_sentence = "HF-based polarity agreement is used as an external reference signal, not as a correctness criterion."
    hf_agree_rows = [r for r in scorecards if _get_hf_label(r) is not None and not _hf_disagrees_with_final(r)]
    hf_disagree_rows = [r for r in scorecards if _get_hf_label(r) is not None and _hf_disagrees_with_final(r)]
    overall_rates = compute_subset_rates(scorecards)
    hf_agree_rates = compute_subset_rates(hf_agree_rows) if hf_agree_rows else {}
    hf_disagree_rates = compute_subset_rates(hf_disagree_rows) if hf_disagree_rows else {}

    def _fmt_rate(v: Any) -> str:
        if v is None:
            return "N/A"
        f = float(v)
        if 0 <= f <= 1:
            return _pct(f)
        return f"{f:.2f}"

    # HF metrics from struct_metrics (structural_metrics.csv) — prefer aggregator output so HTML matches CSV
    hf_polarity_rate = _to_float(struct_metrics.get("hf_polarity_disagreement_rate"))
    hf_coverage_rate = _to_float(struct_metrics.get("hf_disagreement_coverage_of_structural_risks"))
    cond_gain_disagree = _to_float(struct_metrics.get("conditional_improvement_gain_hf_disagree"))
    cond_gain_agree = _to_float(struct_metrics.get("conditional_improvement_gain_hf_agree"))
    hf_metrics_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    hf_metrics_table += f"<tr><td>HF Polarity Disagreement Rate</td><td>{_pct(hf_polarity_rate) if hf_polarity_rate is not None else 'N/A'}</td></tr>"
    hf_metrics_table += f"<tr><td>HF Disagreement Coverage of Structural Risks</td><td>{_pct(hf_coverage_rate) if hf_coverage_rate is not None else 'N/A'}</td></tr>"
    hf_metrics_table += f"<tr><td>Conditional Improvement Gain (HF-disagree)</td><td>{_num(cond_gain_disagree) if cond_gain_disagree is not None else 'N/A'}</td></tr>"
    hf_metrics_table += f"<tr><td>Conditional Improvement Gain (HF-agree)</td><td>{_num(cond_gain_agree) if cond_gain_agree is not None else 'N/A'}</td></tr>"
    hf_metrics_table += "</tbody></table>"
    hf_metrics_note = "<p class=\"header-meta\">Above: values from structural_metrics.csv (structural_error_aggregator). HF is an external reference signal, not a correctness criterion.</p>"

    # Overall: prefer struct_metrics so Overall column is never N/A when CSV has values
    hf_split_table = '<table class="data-table"><thead><tr><th>Metric</th><th>Overall</th><th>HF-agree</th><th>HF-disagree</th></tr></thead><tbody>'
    _overall_metric_keys = [
        ("validator_clear_rate", "Validator Clear Rate (Risk Resolution)"),
        ("stage2_adoption_rate", "Stage2 Adoption Rate"),
        ("polarity_conflict_rate", "Polarity Conflict Rate (same-aspect only)"),
        ("stage_mismatch_rate", "Stage Mismatch Rate (RQ2: RuleM / S1≠S2)"),
    ]
    for metric_key, metric_name in _overall_metric_keys:
        o = overall_rates.get(metric_key)
        if o is None and metric_key == "validator_clear_rate":
            o = overall_rates.get("risk_resolution_rate")
        if o is None:
            o = _to_float(struct_metrics.get(metric_key))
        if o is None and metric_key == "validator_clear_rate":
            o = _to_float(struct_metrics.get("risk_resolution_rate"))
        a = hf_agree_rates.get(metric_key) if hf_agree_rates else None
        if a is None and metric_key == "validator_clear_rate":
            a = hf_agree_rates.get("risk_resolution_rate") if hf_agree_rates else None
        d = hf_disagree_rates.get(metric_key) if hf_disagree_rates else None
        if d is None and metric_key == "validator_clear_rate":
            d = hf_disagree_rates.get("risk_resolution_rate") if hf_disagree_rates else None
        hf_split_table += f'<tr><td>{metric_name}</td><td>{_fmt_rate(o)}</td><td>{_fmt_rate(a)}</td><td>{_fmt_rate(d)}</td></tr>'
    hf_split_table += "</tbody></table>"
    if not (hf_agree_rows or hf_disagree_rows):
        hf_appendix_note = "<p class=\"header-meta\">HF-agree / HF-disagree: N/A (aux_signals.hf not present in this run). Overall uses structural_metrics.csv when available. To populate HF columns, enable pipeline aux_hf and provide HF checkpoint.</p>"
    else:
        hf_appendix_note = f"<p class=\"header-meta\">HF-agree n={len(hf_agree_rows)}, HF-disagree n={len(hf_disagree_rows)}. For error analysis / drill-down only.</p>"

    # RQ1: risk_id top table, unsupported/hallucination (from struct)
    risk_counts = computed.get("risk_id_counts") or {}
    risk_rows = sorted(risk_counts.items(), key=lambda x: -x[1])[:15]
    rq1_risk_table = "<table class=\"data-table\"><thead><tr><th>risk_id</th><th>count</th></tr></thead><tbody>"
    for rid, cnt in risk_rows:
        rq1_risk_table += f"<tr><td>{rid}</td><td>{cnt}</td></tr>"
    rq1_risk_table += "</tbody></table>"

    hard_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    hard_table += f"<tr><td>Aspect Hallucination Rate</td><td>{_pct(_to_float(struct_metrics.get('aspect_hallucination_rate')))}</td></tr>"
    hard_table += f"<tr><td>Unsupported Polarity Rate</td><td>{_pct(_to_float(struct_metrics.get('unsupported_polarity_rate')))}</td></tr>"
    hard_table += "</tbody></table>"

    # Outcome (RQ) vs Process (internal) — paper-claimable only vs validator-level diagnostic
    severe_L3_r = _to_float(struct_metrics.get("severe_polarity_error_L3_rate"))
    pol_conf_raw_r = _to_float(struct_metrics.get("polarity_conflict_rate_raw"))
    pol_conf_r = _to_float(struct_metrics.get("polarity_conflict_rate"))
    pol_conf_after_rep_r = _to_float(struct_metrics.get("polarity_conflict_rate_after_rep"))
    gen_f1_theta = _to_float(struct_metrics.get("generalized_f1_theta"))
    tuple_agree_r = _to_float(struct_metrics.get("tuple_agreement_rate"))
    validator_residual_r = _to_float(struct_metrics.get("validator_residual_risk_rate")) or _to_float(struct_metrics.get("residual_risk_rate"))
    outcome_residual_r = _to_float(struct_metrics.get("outcome_residual_risk_rate"))
    risk_flagged_r = _to_float(struct_metrics.get("risk_flagged_rate"))
    risk_affected = _to_float(struct_metrics.get("risk_affected_change_rate"))
    risk_res_with_ch = _to_float(struct_metrics.get("risk_resolved_with_change_rate"))
    risk_res_without_ch = _to_float(struct_metrics.get("risk_resolved_without_change_rate"))
    ignored_prop = _to_float(struct_metrics.get("ignored_proposal_rate"))
    rq3_risk_decomp = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq3_risk_decomp += "<tr><td colspan=\"2\"><strong>Outcome Metrics (RQ)</strong> — paper-claimable</td></tr>"
    rq3_risk_decomp += f"<tr><td>Severe Polarity Error (L3) Rate</td><td>{_pct(severe_L3_r) if severe_L3_r is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Polarity Conflict Rate (raw)</td><td>{_pct(pol_conf_raw_r) if pol_conf_raw_r is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Polarity Conflict Rate (after representative)</td><td>{_pct(pol_conf_r if pol_conf_r is not None else pol_conf_after_rep_r) if (pol_conf_r is not None or pol_conf_after_rep_r is not None) else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>generalized F1@0.95</td><td>{_pct(gen_f1_theta) if gen_f1_theta is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Tuple Agreement Rate (RQ2)</td><td>{_pct(tuple_agree_r) if tuple_agree_r is not None else 'N/A'}</td></tr>"
    stage_mismatch_r = _to_float(struct_metrics.get("stage_mismatch_rate"))
    rq3_risk_decomp += f"<tr><td>Stage Mismatch Rate (RQ2)</td><td>{_pct(stage_mismatch_r) if stage_mismatch_r is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += "<tr><td colspan=\"2\"><strong>Process Control Metrics (Internal)</strong> — Validator-level diagnostic; not an outcome metric</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Flagged Rate</td><td>{_pct(risk_flagged_r)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Validator Residual Risk Rate</td><td>{_pct(validator_residual_r) if validator_residual_r is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Outcome Residual Risk Rate (internal)</td><td>{_pct(outcome_residual_r) if outcome_residual_r is not None else 'N/A'}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Affected Change Rate</td><td>{_pct(risk_affected)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Resolved-with-Change (rate)</td><td>{_pct(risk_res_with_ch)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Resolved-without-Change (rate)</td><td>{_pct(risk_res_without_ch)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Ignored Proposal Rate</td><td>{_pct(ignored_prop)}</td></tr>"
    rq3_risk_decomp += "</tbody></table>"

    validator_clear_r = _to_float(struct_metrics.get("validator_clear_rate")) or _to_float(struct_metrics.get("risk_resolution_rate"))
    guided = _to_float(struct_metrics.get("guided_change_rate"))
    unguided = _to_float(struct_metrics.get("unguided_drift_rate"))
    stage2_adopt = _to_float(computed.get("stage2_adoption_rate"))
    rq3_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq3_table += f"<tr><td title=\"Validator-level diagnostic. Not an outcome metric.\">Validator Clear Rate (Risk Resolution)</td><td>{_pct(validator_clear_r) if validator_clear_r is not None else 'N/A'}</td></tr>"
    rq3_table += f"<tr><td>Guided Change Rate</td><td>{_pct(guided) if guided is not None else 'N/A'}</td></tr>"
    rq3_table += f"<tr><td>Unguided Drift Rate</td><td>{_pct(unguided) if unguided is not None else 'N/A'}</td></tr>"
    rq3_table += f"<tr><td>Stage2 Adoption Rate</td><td>{_pct(stage2_adopt) if stage2_adopt is not None else 'N/A'}</td></tr>"
    rq3_table += "</tbody></table>"
    # CR (conflict_review_v1) process metrics
    protocol_mode = (scorecards[0].get("meta") or {}).get("protocol_mode") if scorecards else ""
    if not protocol_mode and manifest:
        pipeline = manifest.get("pipeline") or {}
        protocol_mode = pipeline.get("protocol_mode") or ""
    if not protocol_mode and manifest:
        try:
            import json as _json
            cfg = _json.loads(manifest.get("cfg_canonical") or "{}")
            protocol_mode = (cfg.get("pipeline") or {}).get("protocol_mode") or ""
        except Exception:
            pass
    cr_table = ""
    if (protocol_mode or "").strip() == "conflict_review_v1":
        pre_post = _to_float(struct_metrics.get("pre_to_post_change_rate"))
        review_action = _to_float(struct_metrics.get("review_action_rate"))
        arb_intervention = _to_float(struct_metrics.get("arb_intervention_rate"))
        guided_by_review = _to_float(struct_metrics.get("guided_by_review_rate"))
        cr_table = "<h4>Conflict-Review (CR) Process Metrics</h4><table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
        cr_table += f"<tr><td>Pre-to-Post Change Rate</td><td>{_pct(pre_post) if pre_post is not None else 'N/A'}</td></tr>"
        cr_table += f"<tr><td>Review Action Rate</td><td>{_pct(review_action) if review_action is not None else 'N/A'}</td></tr>"
        cr_table += f"<tr><td>Arb Intervention Rate</td><td>{_pct(arb_intervention) if arb_intervention is not None else 'N/A'}</td></tr>"
        cr_table += f"<tr><td>Guided-by-Review Rate</td><td>{_pct(guided_by_review) if guided_by_review is not None else 'N/A'}</td></tr>"
        cr_table += "</tbody></table>"
    rq3_note = (
        "<p class=\"header-meta\">N/A: 키 결측 또는 미계산(구버전 results 등). "
        "Validator 기준(validator_clear_rate, validator_residual_risk_rate) vs Outcome 기준(outcome_residual_risk_rate) 구분: docs/structural_risk_definition.md. "
        "RQ3(validator_clear_rate, guided_change_rate, unguided_drift_rate)는 단일 run에서도 계산 가능.</p>"
    )
    eval_semver = struct_metrics.get("eval_semver")
    eval_policy_hash = struct_metrics.get("eval_policy_hash")
    if eval_semver or eval_policy_hash:
        metric_continuity_note = (
            "<p class=\"header-meta\"><strong>Metric continuity:</strong> "
            f"eval_semver={eval_semver or 'N/A'}, eval_policy_hash={eval_policy_hash or 'N/A'}. "
            "이 값이 바뀌면 gold empty 처리·정규화·추출 경로 등 평가 정책이 변경된 run입니다. "
            "EVAL_SEMVER 환경 변수로 버전을 올리면 리포트에 자동 반영됩니다.</p>"
        )
    else:
        metric_continuity_note = ""

    debate_cov = _to_float(struct_metrics.get("debate_mapping_coverage"))
    debate_direct = _to_float(struct_metrics.get("debate_mapping_direct_rate"))
    debate_fallback = _to_float(struct_metrics.get("debate_mapping_fallback_rate"))
    debate_none = _to_float(struct_metrics.get("debate_mapping_none_rate"))
    debate_fail_no_aspects = _to_float(struct_metrics.get("debate_fail_no_aspects_rate"))
    debate_fail_no_match = _to_float(struct_metrics.get("debate_fail_no_match_rate"))
    debate_fail_neutral = _to_float(struct_metrics.get("debate_fail_neutral_stance_rate"))
    debate_fail_fallback = _to_float(struct_metrics.get("debate_fail_fallback_used_rate"))
    debate_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    debate_table += f"<tr><td>Debate Mapping Coverage</td><td>{_pct(debate_cov) if debate_cov is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Mapping Direct Rate</td><td>{_pct(debate_direct) if debate_direct is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Mapping Fallback Rate</td><td>{_pct(debate_fallback) if debate_fallback is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Mapping None Rate</td><td>{_pct(debate_none) if debate_none is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Fail (no_aspects)</td><td>{_pct(debate_fail_no_aspects) if debate_fail_no_aspects is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Fail (no_match)</td><td>{_pct(debate_fail_no_match) if debate_fail_no_match is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Fail (neutral_stance)</td><td>{_pct(debate_fail_neutral) if debate_fail_neutral is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Debate Fail (fallback_used)</td><td>{_pct(debate_fail_fallback) if debate_fail_fallback is not None else 'N/A'}</td></tr>"
    debate_override_applied = _num(struct_metrics.get("debate_override_applied"))
    debate_override_low = _num(struct_metrics.get("debate_override_skipped_low_signal"))
    debate_override_conflict = _num(struct_metrics.get("debate_override_skipped_conflict"))
    debate_override_already_confident = _num(struct_metrics.get("debate_override_skipped_already_confident"))
    debate_override_already_confident_rate = _to_float(struct_metrics.get("debate_override_skipped_already_confident_rate"))
    debate_table += f"<tr><td>Debate Override Applied (count)</td><td>{debate_override_applied}</td></tr>"
    debate_table += f"<tr><td>Debate Override Skipped Low Signal (count)</td><td>{debate_override_low}</td></tr>"
    debate_table += f"<tr><td>Debate Override Skipped Conflict (count)</td><td>{debate_override_conflict}</td></tr>"
    debate_table += f"<tr><td>Debate Override Skipped Already Confident (count)</td><td>{debate_override_already_confident}</td></tr>"
    debate_table += f"<tr><td>Debate Override Skipped Already Confident (rate)</td><td>{_pct(debate_override_already_confident_rate) if debate_override_already_confident_rate is not None else 'N/A'}</td></tr>"
    override_applied_rate = _to_float(struct_metrics.get("override_applied_rate"))
    override_success_rate = _to_float(struct_metrics.get("override_success_rate"))
    debate_table += f"<tr><td>Override Applied Rate (RQ3)</td><td>{_pct(override_applied_rate) if override_applied_rate is not None else 'N/A'}</td></tr>"
    debate_table += f"<tr><td>Override Success Rate (RQ3, risk 개선·안전)</td><td>{_pct(override_success_rate) if override_success_rate is not None else 'N/A'}</td></tr>"
    debate_table += "</tbody></table>"
    debate_thresholds_note = (
        f"<p class=\"header-meta\">Thresholds: coverage_warn={thresholds['coverage_warn']}, "
        f"no_match_warn={thresholds['no_match_warn']}, neutral_warn={thresholds['neutral_warn']}.</p>"
    )

    # Override conditional effects: Applied vs Skipped (Conflict) subset
    n_app = int(struct_metrics.get("override_applied_n") or 0)
    n_conf = int(struct_metrics.get("override_skipped_conflict_n") or 0)
    delta_app = _to_float(struct_metrics.get("override_applied_delta_f1_mean"))
    delta_conf = _to_float(struct_metrics.get("override_skipped_conflict_delta_f1_mean"))
    unsup_app = _to_float(struct_metrics.get("override_applied_unsupported_polarity_rate"))
    unsup_conf = _to_float(struct_metrics.get("override_skipped_conflict_unsupported_polarity_rate"))
    neg_app = _to_float(struct_metrics.get("override_applied_negation_contrast_failure_rate"))
    neg_conf = _to_float(struct_metrics.get("override_skipped_conflict_negation_contrast_failure_rate"))
    override_conditional_table = (
        "<table class=\"data-table\"><thead><tr><th>Subset</th><th>n</th><th>ΔF1 (mean)</th><th>Unsupported Polarity</th><th>Negation/Contrast Fail</th></tr></thead><tbody>"
        f"<tr><td>Override Applied</td><td>{n_app}</td><td>{_num(delta_app) if delta_app is not None else 'N/A'}</td><td>{_pct(unsup_app) if unsup_app is not None else 'N/A'}</td><td>{_pct(neg_app) if neg_app is not None else 'N/A'}</td></tr>"
        f"<tr><td>Skipped (Conflict)</td><td>{n_conf}</td><td>{_num(delta_conf) if delta_conf is not None else 'N/A'}</td><td>{_pct(unsup_conf) if unsup_conf is not None else 'N/A'}</td><td>{_pct(neg_conf) if neg_conf is not None else 'N/A'}</td></tr>"
        "</tbody></table>"
    )
    override_conditional_note = (
        "<p class=\"header-meta\">Applied에서 ΔF1이 플러스이고 오류율이 낮으면: override는 유익. "
        "Conflict subset에서 오류율이 높으면: 토론 신호가 갈리는 문장(대조/부정)에선 보수적 스킵이 합리적.</p>"
    )
    # Skip reason granularity (Discussion: why conflict skip?)
    skip_action_ambiguity = _num(struct_metrics.get("override_skipped_conflict_action_ambiguity"))
    skip_L3_conservative = _num(struct_metrics.get("override_skipped_conflict_L3_conservative"))
    skip_implicit_soft = _num(struct_metrics.get("override_skipped_conflict_implicit_soft_only"))
    skip_low_conf = _num(struct_metrics.get("override_skipped_conflict_low_confidence"))
    skip_contradictory = _num(struct_metrics.get("override_skipped_conflict_contradictory_memory"))
    override_conditional_table += (
        "<p class=\"header-meta\"><strong>Skipped conflict reasons (counts):</strong> "
        f"action_ambiguity={skip_action_ambiguity}, L3_conservative={skip_L3_conservative}, "
        f"implicit_soft_only={skip_implicit_soft}, low_confidence={skip_low_conf}, contradictory_memory={skip_contradictory}</p>"
    )

    # Table 2 (RQ1+RQ3): Tuple F1, ΔF1, FixRate, BreakRate, NetGain (when gold)
    # Mean tuple counts from final_result (stage1_tuples, stage2_tuples, final_tuples) — recorded by supervisor.
    mean_stage1_tuples_n = mean_stage2_tuples_n = mean_final_tuples_n = None
    if scorecards:
        s1_lens = []
        s2_lens = []
        fin_lens = []
        for r in scorecards:
            fr = (r.get("runtime") or {}).get("parsed_output") or {}
            fr = fr.get("final_result") if isinstance(fr, dict) else {}
            if not isinstance(fr, dict):
                fr = {}
            s1 = fr.get("stage1_tuples")
            s2 = fr.get("stage2_tuples")
            fin = fr.get("final_tuples")
            if isinstance(s1, list):
                s1_lens.append(len(s1))
            if isinstance(s2, list):
                s2_lens.append(len(s2))
            if isinstance(fin, list):
                fin_lens.append(len(fin))
        mean_stage1_tuples_n = sum(s1_lens) / len(s1_lens) if s1_lens else None
        mean_stage2_tuples_n = sum(s2_lens) / len(s2_lens) if s2_lens else None
        mean_final_tuples_n = sum(fin_lens) / len(fin_lens) if fin_lens else None

    # Prefer struct_metrics (from structural_metrics.csv / structural_error_aggregator) for F1 so HTML matches CSV (aspect-polarity F1, process_trace/final_aspects).
    n_gold_struct = _to_float(struct_metrics.get("N_gold")) or 0
    n_gold_corr = (stage2_correction.get("N_gold") or 0)
    has_gold = n_gold_struct > 0 or n_gold_corr > 0
    table2_html = ""
    if has_gold:
        def _first(v1, v2):
            if v1 is not None and v1 != "":
                return _to_float(v1)
            return v2
        t2_f1_s1 = _first(struct_metrics.get("tuple_f1_s1"), _first(struct_metrics.get("triplet_f1_s1"), stage2_correction.get("tuple_f1_s1") or stage2_correction.get("triplet_f1_s1")))
        t2_f1_s2 = _first(struct_metrics.get("tuple_f1_s2"), _first(struct_metrics.get("triplet_f1_s2"), stage2_correction.get("tuple_f1_s2") or stage2_correction.get("triplet_f1_s2")))
        t2_f1_s2_explicit = _first(struct_metrics.get("tuple_f1_s2_explicit_only"), None)
        t2_f1_s2_overall = _first(struct_metrics.get("tuple_f1_s2_overall"), t2_f1_s2)
        t2_delta = _first(struct_metrics.get("delta_f1"), stage2_correction.get("delta_f1"))
        t2_fix = _first(struct_metrics.get("fix_rate"), stage2_correction.get("fix_rate"))
        t2_break = _first(struct_metrics.get("break_rate"), stage2_correction.get("break_rate"))
        t2_net = _first(struct_metrics.get("net_gain"), stage2_correction.get("net_gain"))
        n_gold_display = int(n_gold_struct) if n_gold_struct else (n_gold_corr or 0)
        n_gold_total = _to_float(struct_metrics.get("N_gold_total")) or n_gold_display
        n_gold_explicit = _to_float(struct_metrics.get("N_gold_explicit"))
        n_gold_implicit = _to_float(struct_metrics.get("N_gold_implicit"))
        table2_html = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
        table2_html += f"<tr><td>N (with gold)</td><td>{int(n_gold_total) if n_gold_total else n_gold_display}</td></tr>"
        if n_gold_explicit is not None or n_gold_implicit is not None:
            table2_html += f"<tr><td>N_gold_explicit</td><td>{int(n_gold_explicit) if n_gold_explicit is not None else 'N/A'}</td></tr>"
            table2_html += f"<tr><td>N_gold_implicit</td><td>{int(n_gold_implicit) if n_gold_implicit is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Stage1 tuples (mean/sample)</td><td>{_num(mean_stage1_tuples_n) if mean_stage1_tuples_n is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Stage2 tuples (mean/sample)</td><td>{_num(mean_stage2_tuples_n) if mean_stage2_tuples_n is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Final tuples (mean/sample)</td><td>{_num(mean_final_tuples_n) if mean_final_tuples_n is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Tuple F1 (Stage1)</td><td>{_num(t2_f1_s1)}</td></tr>"
        if t2_f1_s2_explicit is not None:
            table2_html += f"<tr><td>Tuple F1 (Stage2+Moderator, explicit-only) <em>primary</em></td><td>{_num(t2_f1_s2_explicit)}</td></tr>"
            table2_html += f"<tr><td>Tuple F1 (Stage2+Moderator, overall)</td><td>{_num(t2_f1_s2_overall)}</td></tr>"
        else:
            table2_html += f"<tr><td>Tuple F1 (Stage2+Moderator)</td><td>{_num(t2_f1_s2)}</td></tr>"
        table2_html += f"<tr><td>ΔF1 (S2−S1)</td><td>{_num(t2_delta)}</td></tr>"
        table2_html += f"<tr><td>Fix Rate ↑</td><td>{_pct(t2_fix) if t2_fix is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Break Rate ↓</td><td>{_pct(t2_break) if t2_break is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Net Gain ↑</td><td>{_num(t2_net) if t2_net is not None else 'N/A'}</td></tr>"
        t2_f1_s2_implicit = _first(struct_metrics.get("tuple_f1_s2_implicit_only"), stage2_correction.get("tuple_f1_s2_implicit_only"))
        t2_implicit_invalid_r = _first(struct_metrics.get("implicit_invalid_pred_rate"), stage2_correction.get("implicit_invalid_pred_rate"))
        n_implicit_gold = _to_float(struct_metrics.get("implicit_gold_sample_n")) or _to_float(stage2_correction.get("implicit_gold_sample_n"))
        n_implicit_invalid = _to_float(struct_metrics.get("implicit_invalid_sample_n")) or _to_float(stage2_correction.get("implicit_invalid_sample_n"))
        table2_html += f"<tr><td>Tuple F1 (Stage2+Moderator, implicit-only)</td><td>{_num(t2_f1_s2_implicit) if t2_f1_s2_implicit is not None else ('N/A' if n_implicit_gold == 0 else '0')}</td></tr>"
        table2_html += f"<tr><td>Implicit invalid pred rate</td><td>{_pct(t2_implicit_invalid_r) if t2_implicit_invalid_r is not None else ('N/A' if n_implicit_gold == 0 else '0')}</td></tr>"
        table2_html += f"<tr><td>Implicit gold sample n</td><td>{int(n_implicit_gold) if n_implicit_gold is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Implicit invalid sample n</td><td>{int(n_implicit_invalid) if n_implicit_invalid is not None else 'N/A'}</td></tr>"
        corr_prec = stage2_correction.get("correction_precision")
        cis = stage2_correction.get("conservative_improvement_score")
        table2_html += f"<tr><td>Correction Precision</td><td>{_pct(corr_prec) if corr_prec is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Conservative Improvement Score (λ=2)</td><td>{_num(cis) if cis is not None else 'N/A'}</td></tr>"
        table2_html += "</tbody></table>"
        table2_html += "<p class=\"header-meta\">F1 matches on (aspect_term, polarity) only. Gold-present samples only. Primary: explicit-only tuple F1 (implicit cases are a different inference task). Values from structural_metrics.csv when available.</p>"
    else:
        # When no gold: still report the 3 tuple counts (from final_result) if available.
        if mean_stage1_tuples_n is not None or mean_stage2_tuples_n is not None or mean_final_tuples_n is not None:
            table2_html = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
            table2_html += f"<tr><td>Stage1 tuples (mean/sample)</td><td>{_num(mean_stage1_tuples_n) if mean_stage1_tuples_n is not None else 'N/A'}</td></tr>"
            table2_html += f"<tr><td>Stage2 tuples (mean/sample)</td><td>{_num(mean_stage2_tuples_n) if mean_stage2_tuples_n is not None else 'N/A'}</td></tr>"
            table2_html += f"<tr><td>Final tuples (mean/sample)</td><td>{_num(mean_final_tuples_n) if mean_final_tuples_n is not None else 'N/A'}</td></tr>"
            table2_html += "</tbody></table>"
            table2_html += "<p class=\"header-meta\">Gold tuples not present; F1/Fix Rate/Break Rate require labeled data. Above: tuple counts from final_result (supervisor).</p>"
        else:
            table2_html = "<p class=\"header-meta\">Gold tuples not present; Table 2 (ΔF1, Fix Rate, Break Rate, Net Gain) requires labeled data.</p>"

    # Transition table (Fix / Keep / Break / Still Wrong) from correctness snapshot (transition_aggregator)
    n_trans = transition_summary.get("n_total") or 0
    if n_trans > 0:
        transition_table_html = "<table class=\"data-table\"><thead><tr><th>구분</th><th>의미</th><th>카운트</th><th>rate</th></tr></thead><tbody>"
        transition_table_html += f"<tr><td><strong>Fix</strong></td><td>S1 오답 → S2 정답</td><td>{transition_summary.get('n_fix', 0)}</td><td>{_pct(transition_summary.get('fix_rate'))}</td></tr>"
        transition_table_html += f"<tr><td><strong>Keep</strong></td><td>S1 정답 → S2 정답 유지</td><td>{transition_summary.get('n_keep', 0)}</td><td>{_pct(transition_summary.get('keep_rate'))}</td></tr>"
        transition_table_html += f"<tr><td><strong>Break</strong></td><td>S1 정답 → S2 오답(망침)</td><td>{transition_summary.get('n_break', 0)}</td><td>{_pct(transition_summary.get('break_rate'))}</td></tr>"
        transition_table_html += f"<tr><td><strong>Still Wrong</strong></td><td>S1 오답 → S2 오답 유지</td><td>{transition_summary.get('n_still', 0)}</td><td>{_pct(transition_summary.get('still_wrong_rate'))}</td></tr>"
        transition_table_html += "</tbody></table>"
        transition_note = f"<p class=\"header-meta\">Correctness snapshot (label experiment): n_total={n_trans}.</p>"
    else:
        transition_table_html = "<p class=\"header-meta\">Correctness snapshot not present in scorecards; transition table requires label experiment (correctness or tuple_correctness).</p>"
        transition_note = ""

    rule_counts = computed.get("rule_counts") or {}
    rule_table = "<table class=\"data-table\"><thead><tr><th>Rule</th><th>Count</th></tr></thead><tbody>"
    for rule in ["RuleA", "RuleB", "RuleM", "RuleD"]:
        rule_table += f"<tr><td>{rule}</td><td>{rule_counts.get(rule, 0)}</td></tr>"
    rule_table += "</tbody></table>"

    # RQ2: self_consistency, flip_flop_rate, variance; interpret with Break Rate when gold available
    self_cons = _to_float(struct_metrics.get("self_consistency_exact"))
    self_cons_eligible = struct_metrics.get("self_consistency_eligible")
    n_trials = struct_metrics.get("n_trials")
    risk_cons = _to_float(struct_metrics.get("risk_set_consistency"))
    flip_flop = _to_float(struct_metrics.get("flip_flop_rate"))
    variance = _to_float(struct_metrics.get("variance"))
    break_rate_val = (_to_float(struct_metrics.get("break_rate")) or stage2_correction.get("break_rate")) if has_gold else None
    rq2_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq2_table += f"<tr><td>Self-consistency (exact)</td><td>{_pct(self_cons) if self_cons is not None else 'N/A'}</td></tr>"
    rq2_table += f"<tr><td>Self-consistency eligible</td><td>{'Yes' if self_cons_eligible is True else ('No' if self_cons_eligible is False else 'N/A')}</td></tr>"
    rq2_table += f"<tr><td>n_trials</td><td>{n_trials if n_trials is not None else 'N/A'}</td></tr>"
    rq2_table += f"<tr><td>Risk-set consistency</td><td>{_pct(risk_cons) if risk_cons is not None else 'N/A'}</td></tr>"
    rq2_table += f"<tr><td>Flip-flop rate (RQ2)</td><td>{_pct(flip_flop) if flip_flop is not None else 'N/A'}</td></tr>"
    rq2_table += f"<tr><td>Variance (RQ2)</td><td>{_pct(variance) if variance is not None else 'N/A'}</td></tr>"
    rq2_table += "</tbody></table>"
    rq2_note = "<p class=\"header-meta\">N/A: Self-consistency·n_trials·eligible은 다중 trial(n_trials≥2)일 때만 값 있음; 단일 run이면 N/A.</p>"
    if break_rate_val is not None:
        rq2_note += "<p class=\"header-meta\">Interpret stability together with Break Rate (Stage2): stable but wrong vs. unstable but correcting.</p>"

    # Efficiency
    lat_p50 = computed.get("latency_p50_ms")
    lat_p95 = computed.get("latency_p95_ms")
    gate_status = computed.get("gate_status") or {}
    eff_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    eff_table += f"<tr><td>Latency p50 (ms)</td><td>{_num(lat_p50)}</td></tr>"
    eff_table += f"<tr><td>Latency p95 (ms)</td><td>{_num(lat_p95)}</td></tr>"
    gate_str = ", ".join(f"{k}: {v}" for k, v in (gate_status or {}).items()) or "—"
    eff_table += f"<tr><td>Gate status</td><td>{gate_str}</td></tr>"
    eff_table += f"<tr><td>Parse failure rate</td><td>{_pct(computed.get('parse_failure_rate'))}</td></tr>"
    eff_table += f"<tr><td>Generate failure rate</td><td>{_pct(computed.get('generate_failure_rate'))}</td></tr>"
    eff_table += f"<tr><td>Fallback used rate</td><td>{_pct(computed.get('fallback_used_rate'))}</td></tr>"
    eff_table += "</tbody></table>"

    # Memory Growth: memory off → accumulation/usage/effect N/A; RQ metrics (F1, accuracy) always shown when rows exist
    memory_growth_rows = memory_growth_rows or []
    CANONICAL_MG_KEYS = (
        "window_end_sample", "window_size", "memory_mode",
        "store_size", "store_new_entry_rate", "advisory_presence_rate", "follow_rate",
        "mean_delta_risk_followed", "mean_delta_risk_ignored", "harm_rate_followed", "harm_rate_ignored",
        "retrieval_hit_k", "mean_tuple_f1_s2", "accuracy_rate",
    )

    def _mg_cell(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    if memory_off and not memory_growth_rows:
        memory_growth_html = (
            "<p class=\"header-meta\">Memory growth (accumulation/usage/effect): N/A (episodic memory off).</p>"
            "<p class=\"header-meta\">To include RQ metrics (F1, accuracy) in this section, run "
            "<code>analysis/memory_growth_analysis.py --trace &lt;run_dir&gt;/traces.jsonl --scorecards &lt;run_dir&gt;/scorecards.jsonl --out &lt;run_dir&gt;/memory_growth_metrics.jsonl</code>.</p>"
        )
    elif not memory_growth_rows:
        memory_growth_html = "<p class=\"header-meta\">Memory growth metrics not available (run <code>analysis/memory_growth_analysis.py</code> with traces.jsonl and optionally --scorecards, then <code>analysis/plot_memory_growth.py</code>).</p>"
    else:
        last = memory_growth_rows[-1]
        mg_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value (last window)</th></tr></thead><tbody>"
        for key in CANONICAL_MG_KEYS:
            v = last.get(key)
            mg_table += f"<tr><td>{key}</td><td>{_mg_cell(v)}</td></tr>"
        mg_table += "</tbody></table>"
        if memory_off:
            memory_growth_html = "<p class=\"header-meta\">Memory growth (accumulation/usage/effect): N/A (episodic memory off). RQ metrics below from scorecards.</p>" + mg_table
            if memory_growth_plot_path and memory_growth_plot_path.exists():
                memory_growth_html += f'<p class="header-meta">Window-based curves (F1/accuracy when available).</p><img src="{memory_growth_plot_path.name}" alt="Memory growth plot" style="max-width:100%; height:auto;" />'
        else:
            memory_growth_html = mg_table
            if memory_growth_plot_path and memory_growth_plot_path.exists():
                memory_growth_html += f'<p class="header-meta">Window-based curves (store_size, Δ risk followed vs ignored, optional F1/accuracy).</p><img src="{memory_growth_plot_path.name}" alt="Memory growth plot" style="max-width:100%; height:auto;" />'
            else:
                memory_growth_html += "<p class=\"header-meta\">Plot not generated (run <code>analysis/plot_memory_growth.py --metrics &lt;run_dir&gt;/memory_growth_metrics.jsonl --out_dir &lt;report_dir&gt;</code>).</p>"

    # Appendix: top cases (collapsible)
    top_cases = scorecards[:top_n]
    rows_html = []
    for i, card in enumerate(top_cases):
        meta = card.get("meta") or {}
        text_id = meta.get("text_id") or meta.get("uid") or f"#{i+1}"
        text_preview = (meta.get("input_text") or "")[:60] + ("…" if len(meta.get("input_text") or "") > 60 else "")
        mod = card.get("moderator") or {}
        final_label = mod.get("final_label") or "—"
        selected = mod.get("selected_stage") or "—"
        lat = meta.get("latency_ms")
        lat_str = f"{lat} ms" if lat is not None else "—"
        rows_html.append(
            f"<tr><td>{text_id}</td><td>{text_preview}</td><td>{final_label}</td><td>{selected}</td><td>{lat_str}</td></tr>"
        )
    appendix_table = "<table class=\"data-table\"><thead><tr><th>text_id</th><th>input (preview)</th><th>final_label</th><th>selected_stage</th><th>latency</th></tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"

    kpi_mapping_table = "<table class=\"data-table\"><thead><tr><th>KPI</th><th>로그/집계 필드</th></tr></thead><tbody>"
    for kpi_name, log_field in KPI_FIELD_MAPPING:
        kpi_mapping_table += f"<tr><td>{kpi_name}</td><td>{log_field}</td></tr>"
    kpi_mapping_table += "</tbody></table>"

    env_note = f"config_hash (short): {cfg_hash}, prompt_hash (short): {prompt_hash}, schema: {SCHEMA_VERSION}"

    css = """
:root { --bg: #0f1419; --card: #1a2332; --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --green: #3fb950; --orange: #d29922; }
* { box-sizing: border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 1rem 2rem; line-height: 1.5; }
h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
.header-meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
.header-meta span { margin-right: 1rem; }
.section { margin-bottom: 2rem; }
.section h2 { font-size: 1.2rem; color: var(--accent); border-bottom: 1px solid var(--card); padding-bottom: 0.25rem; margin-bottom: 0.75rem; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.kpi-card { background: var(--card); padding: 0.75rem; border-radius: 6px; border-left: 3px solid transparent; }
.kpi-card.kpi-ok { border-left-color: var(--green); }
.kpi-card.kpi-warn { border-left-color: var(--orange); }
.kpi-card.kpi-neutral { border-left-color: var(--muted); }
.kpi-title { font-size: 0.75rem; color: var(--muted); }
.kpi-value { font-size: 1.25rem; font-weight: 600; color: var(--green); }
.kpi-card.kpi-warn .kpi-value { color: var(--orange); }
.kpi-card.kpi-neutral .kpi-value { color: var(--muted); }
.kpi-legend { display: flex; gap: 1rem; font-size: 0.85rem; color: var(--muted); margin-bottom: 0.75rem; }
.legend-item { display: inline-flex; align-items: center; gap: 0.4rem; }
.legend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.legend-swatch.ok { background: var(--green); }
.legend-swatch.warn { background: var(--orange); }
.legend-swatch.neutral { background: var(--muted); }
.warn-box { border-left: 3px solid var(--orange); background: #1f1a12; padding: 0.5rem 0.75rem; border-radius: 6px; }
.warn-box .header-meta { margin: 0.25rem 0; }
.warn-box ul { margin: 0.25rem 0 0.25rem 1rem; padding: 0; }
.conclusion { background: var(--card); padding: 1rem; border-radius: 6px; margin-top: 0.5rem; }
.conclusion p { margin: 0.25rem 0; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.data-table th, .data-table td { text-align: left; padding: 0.4rem 0.6rem; border: 1px solid var(--card); }
.data-table th { background: var(--card); color: var(--muted); }
.bar-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }
.bar-label { min-width: 180px; font-size: 0.9rem; }
.bar-track { flex: 1; height: 12px; background: var(--card); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--accent); border-radius: 4px; }
.bar-value { min-width: 4rem; font-size: 0.9rem; color: var(--muted); }
.details-summary { cursor: pointer; padding: 0.5rem; background: var(--card); border-radius: 4px; margin-bottom: 0.5rem; }
.details-content { padding: 0.5rem 0; }
.modal { display: none; position: fixed; inset: 0; background: rgba(0, 0, 0, 0.6); align-items: center; justify-content: center; }
.modal.active { display: flex; }
.modal-content { background: var(--card); padding: 1rem; border-radius: 8px; min-width: 280px; max-width: 520px; }
.modal-title { font-weight: 600; margin-bottom: 0.5rem; }
.modal-close { margin-top: 0.75rem; }
"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metric Report — {run_id}</title>
<style>{css}</style>
</head>
<body>
<header>
<h1>Metric Report</h1>
<div class="header-meta">
  <span><strong>Run ID</strong> {run_id}</span>
  <span><strong>Date</strong> {date_utc}</span>
  <span><strong>Profile</strong> {profile}</span>
  <span><strong>Provider/Model</strong> {provider} / {model}</span>
  <span><strong>Dataset</strong> {dataset}</span>
  <span><strong>N</strong> {n}</span>
  <span><strong>Episodic memory</strong> {memory_label}</span>
  <span><strong>Schema</strong> {SCHEMA_VERSION}</span>
</div>
</header>

<section class="section" id="executive">
<h2>Executive Summary</h2>
<div class="kpi-grid">
{kpi_html}
</div>
<div class="kpi-legend">
  <span class="legend-item"><span class="legend-swatch ok"></span> 정상</span>
  <span class="legend-item"><span class="legend-swatch warn"></span> 경고</span>
  <span class="legend-item"><span class="legend-swatch neutral"></span> N/A</span>
</div>
<div class="conclusion">
  <p><strong>이 Run의 결론</strong></p>
  <p>{conclusion_lines[0]}</p>
  <p>{conclusion_lines[1]}</p>
  <p>{conclusion_lines[2]}</p>
</div>
<p class="header-meta">{hf_sentence}</p>
{debate_warn}
</section>

<section class="section" id="rq1">
<h2>RQ1: Structural Quality</h2>
<h3>risk_id 빈도 (Top)</h3>
{rq1_risk_table}
<h3>Hard subset / Unsupported polarity · Hallucinated aspect</h3>
{hard_table}
</section>

<section class="section" id="rq3">
<h2>RQ3: CBL Effectiveness</h2>
<h3>Risk decomposition</h3>
{rq3_risk_decomp}
<h3>Stage1 vs Stage2 요약</h3>
{rq3_table}
{rq3_note}
{cr_table}
{metric_continuity_note}
<h3>Debate mapping metrics</h3>
{debate_table}
{debate_thresholds_note}
<h3>Override Conditional Effects (Applied vs Skipped-Conflict)</h3>
{override_conditional_table}
{override_conditional_note}
<h3>Table 2: Tuple F1, ΔF1, Fix Rate, Break Rate, Net Gain (gold required)</h3>
{table2_html}
<h3>Transition table (correctness snapshot)</h3>
{transition_table_html}
{transition_note}
<h3>Adoption/Reject breakdown (Rule A~D)</h3>
{rule_table}
</section>

<section class="section" id="rq2">
<h2>RQ2: Reliability & Stability</h2>
{rq2_table}
{rq2_note}
</section>

<section class="section" id="efficiency">
<h2>Efficiency / QA</h2>
{eff_table}
</section>

<section class="section" id="memory-growth">
<h2>Memory Growth (episodic memory)</h2>
{memory_growth_html}
</section>

<section class="section" id="appendix">
<h2>Appendix</h2>
<h3>HF metrics (from structural_metrics.csv)</h3>
<p class="header-meta">{hf_sentence}</p>
{hf_metrics_table}
{hf_metrics_note}
<h3>Error analysis: HF facet (Overall / HF-agree / HF-disagree)</h3>
{hf_split_table}
{hf_appendix_note}
<details class="details-summary">
<summary>Top cases ({len(top_cases)}개) — 접기/펼치기</summary>
<div class="details-content">{appendix_table}</div>
</details>
<h3>KPI ↔ 로그 필드 매핑</h3>
<p class="header-meta">리뷰어가 숫자 출처를 추적할 수 있도록 KPI와 로그/집계 필드 대응표.</p>
{kpi_mapping_table}
<p class="header-meta">{env_note}</p>
</section>
<div id="kpi-modal" class="modal" role="dialog" aria-modal="true">
  <div class="modal-content">
    <div class="modal-title" id="kpi-modal-title">KPI</div>
    <div id="kpi-modal-body">설명</div>
    <button class="modal-close" id="kpi-modal-close">닫기</button>
  </div>
</div>
<script>
  const modal = document.getElementById("kpi-modal");
  const modalTitle = document.getElementById("kpi-modal-title");
  const modalBody = document.getElementById("kpi-modal-body");
  const closeBtn = document.getElementById("kpi-modal-close");
  document.querySelectorAll(".kpi-card").forEach((card) => {{
    card.addEventListener("click", () => {{
      modalTitle.textContent = card.dataset.kpiTitle || "KPI";
      modalBody.textContent = card.dataset.kpiTip || "설명 없음";
      modal.classList.add("active");
    }});
  }});
  closeBtn.addEventListener("click", () => modal.classList.remove("active"));
  modal.addEventListener("click", (e) => {{
    if (e.target === modal) modal.classList.remove("active");
  }});
</script>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build metric report HTML from run_dir")
    ap.add_argument("--run_dir", required=True, help="Run directory (e.g. results/real_mini_r1_proposed)")
    ap.add_argument("--out_dir", default=None, help="Output directory (default: reports/<run_dir.name>)")
    ap.add_argument("--metrics_profile", default="paper_main", help="Profile for structural_error_aggregator if run")
    ap.add_argument("--top_n", type=int, default=15, help="Number of top cases in appendix")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = PROJECT_ROOT / run_dir
    if not run_dir.exists():
        print(f"[ERROR] run_dir not found: {run_dir}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "reports" / run_dir.name
    out_path = out_dir / "metric_report.html"

    manifest_path = run_dir / "manifest.json"
    manifest = load_json(manifest_path)
    if not manifest:
        print(f"[WARN] manifest.json not found or empty in {run_dir}", file=sys.stderr)

    scorecards_path = run_dir / "scorecards.jsonl"
    scorecards = load_jsonl(scorecards_path)
    if not scorecards:
        print(f"[WARN] scorecards.jsonl not found or empty in {run_dir}", file=sys.stderr)

    derived_dir = run_dir / "derived"
    csv_path = ensure_structural_metrics(run_dir, derived_dir, args.metrics_profile)
    struct_metrics = load_structural_metrics_csv(csv_path)
    ensure_transition_metrics(run_dir, derived_dir, args.metrics_profile)
    transition_summary_path = derived_dir / "metrics" / "transition_summary.json"
    transition_summary = load_json(transition_summary_path) if transition_summary_path.exists() else {}

    computed = compute_from_scorecards(scorecards)
    computed["profile"] = (manifest.get("purpose") or "").strip() or (scorecards[0].get("profile") if scorecards else "")
    stage2_correction = compute_stage2_correction_metrics(scorecards)
    n_gold = stage2_correction.get("N_gold") or 0
    print(f"Metric report: run_dir={run_dir.name}, scorecards={len(scorecards)}, rows_with_gold={n_gold}")

    # Memory growth: load metrics; if missing, run memory_growth_analysis from traces+scorecards so RQ metrics (F1, accuracy) are always available
    episodic_memory = manifest.get("episodic_memory")
    memory_off = not episodic_memory or (isinstance(episodic_memory, dict) and (episodic_memory.get("condition") == "C1"))
    memory_growth_rows: List[Dict[str, Any]] = []
    memory_growth_plot_path: Optional[Path] = None
    metrics_path = run_dir / "memory_growth_metrics.jsonl"
    if not metrics_path.exists():
        metrics_path = run_dir / "derived" / "memory_growth_metrics.jsonl"
    if not metrics_path.exists() and (run_dir / "traces.jsonl").exists() and scorecards_path.exists() and scorecards:
        window = min(50, max(1, len(scorecards)))
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "analysis" / "memory_growth_analysis.py"),
                    "--trace",
                    str(run_dir / "traces.jsonl"),
                    "--scorecards",
                    str(scorecards_path),
                    "--window",
                    str(window),
                    "--out",
                    str(run_dir / "memory_growth_metrics.jsonl"),
                ],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                metrics_path = run_dir / "memory_growth_metrics.jsonl"
            else:
                print(f"[WARN] memory_growth_analysis failed: {r.stderr[:300] if r.stderr else r.returncode}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] memory_growth_analysis failed: {e}", file=sys.stderr)
    if metrics_path.exists():
        memory_growth_rows = load_jsonl(metrics_path)
    if memory_growth_rows and metrics_path.exists():
        try:
            r = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "analysis" / "plot_memory_growth.py"),
                    "--metrics",
                    str(metrics_path),
                    "--out_dir",
                    str(out_path.parent),
                ],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode == 0:
                memory_growth_plot_path = out_path.parent / "memory_growth_plot.png"
        except Exception as e:
            print(f"[WARN] plot_memory_growth failed: {e}", file=sys.stderr)

    build_html(
        run_dir,
        manifest,
        scorecards,
        struct_metrics,
        computed,
        stage2_correction,
        transition_summary,
        out_path,
        top_n=args.top_n,
        memory_growth_rows=memory_growth_rows,
        memory_growth_plot_path=memory_growth_plot_path,
        memory_off=memory_off,
    )
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
