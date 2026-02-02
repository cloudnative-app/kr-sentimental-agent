#!/usr/bin/env python3
"""
Metric Report HTML generator for ABSA runs.

Reads run_dir (manifest.json, scorecards.jsonl, derived/metrics/structural_metrics.csv)
and produces a single-page HTML report with:
  Header, Executive Summary (6 KPI cards + conclusion), RQ1/RQ3/RQ2, Efficiency/QA, Appendix.

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

# Triplet = (aspect, opinion, polarity) normalized strings
Triplet = Tuple[str, str, str]
SCHEMA_VERSION = "scorecard_v2"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def _has_polarity_conflict(record: Dict[str, Any]) -> bool:
    mod = record.get("moderator") or {}
    if "RuleM" in (mod.get("applied_rules") or []):
        return True
    s1 = (record.get("stage1_ate") or {}).get("label") or ""
    s2_ate = record.get("stage2_ate")
    s2 = s2_ate.get("label") if isinstance(s2_ate, dict) else None
    if s2 is not None and s1 != s2:
        return True
    return False


def _norm_txt(t: Optional[str]) -> str:
    if t is None:
        return ""
    t = (t or "").strip().lower()
    for p in ".,;:!?\"'`""''()[]{}":
        t = t.strip(p)
    return " ".join(t.split())


def _triplet_from_sent(sent: Dict[str, Any]) -> Triplet:
    aspect = _norm_txt(sent.get("aspect_ref") or sent.get("term"))
    op = sent.get("opinion_term")
    opinion = _norm_txt(op.get("term") if isinstance(op, dict) else op)
    polarity = _norm_txt(sent.get("polarity") or sent.get("label"))
    return (aspect, opinion, polarity)


def _triplets_from_list(items: Any) -> Set[Triplet]:
    if not items or not isinstance(items, (list, tuple)):
        return set()
    return {_triplet_from_sent(it) for it in items if it and isinstance(it, dict)}


def _extract_final_triplets(record: Dict[str, Any]) -> Set[Triplet]:
    sents = (record.get("inputs") or {}).get("aspect_sentiments")
    return _triplets_from_list(sents) if sents else set()


def _extract_stage1_triplets(record: Dict[str, Any]) -> Set[Triplet]:
    trace = (record.get("runtime") or {}).get("process_trace") or record.get("process_trace") or []
    for entry in trace:
        if (entry.get("stage") or "").lower() == "stage1" and (entry.get("agent") or "").lower() == "atsa":
            sents = (entry.get("output") or {}).get("aspect_sentiments")
            if sents:
                return _triplets_from_list(sents)
    return _extract_final_triplets(record)


def _extract_gold_triplets(record: Dict[str, Any]) -> Optional[Set[Triplet]]:
    gold = record.get("gold_triplets") or (record.get("inputs") or {}).get("gold_triplets")
    if isinstance(gold, list) and gold:
        return _triplets_from_list(gold)
    return None


def _precision_recall_f1(pred: Set[Triplet], gold: Set[Triplet]) -> Tuple[float, float, float]:
    if not gold:
        return (0.0, 0.0, 0.0)
    pred = pred or set()
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


def compute_stage2_correction_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """When gold triplets exist: FixRate, BreakRate, NetGain, CorrPrec, CIS, Triplet F1 S1/S2, ΔF1. Else N/A."""
    out: Dict[str, Any] = {
        "triplet_f1_s1": None, "triplet_f1_s2": None, "delta_f1": None,
        "fix_rate": None, "break_rate": None, "net_gain": None,
        "correction_precision": None, "conservative_improvement_score": None,
        "n_fix": 0, "n_break": 0, "n_still": 0, "n_keep": 0, "N_gold": 0,
    }
    rows_with_gold = [(r, _extract_gold_triplets(r)) for r in rows if _extract_gold_triplets(r) is not None]
    if not rows_with_gold:
        return out
    N = len(rows_with_gold)
    f1_s1_list: List[float] = []
    f1_s2_list: List[float] = []
    n_fix = n_break = n_still = n_keep = 0
    for record, gold in rows_with_gold:
        gold = gold or set()
        s1 = _extract_stage1_triplets(record)
        s2 = _extract_final_triplets(record)
        _, _, f1_1 = _precision_recall_f1(s1, gold)
        _, _, f1_2 = _precision_recall_f1(s2, gold)
        f1_s1_list.append(f1_1)
        f1_s2_list.append(f1_2)
        st1 = s1 == gold
        st2 = s2 == gold
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
        out["triplet_f1_s1"] = sum(f1_s1_list) / len(f1_s1_list)
    if f1_s2_list:
        out["triplet_f1_s2"] = sum(f1_s2_list) / len(f1_s2_list)
    if f1_s1_list and f1_s2_list:
        out["delta_f1"] = out["triplet_f1_s2"] - out["triplet_f1_s1"]
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
    rr = _to_float(struct.get("risk_resolution_rate"))
    gcr = _to_float(struct.get("guided_change_rate"))
    udr = _to_float(struct.get("unguided_drift_rate"))
    stage2 = metrics.get("stage2_adoption_rate")
    pol_conf = _to_float(struct.get("polarity_conflict_rate"))
    n_gold = _to_float(struct.get("N_gold")) or 0
    f1_s1 = _to_float(struct.get("triplet_f1_s1"))
    f1_s2 = _to_float(struct.get("triplet_f1_s2"))
    delta_f1 = _to_float(struct.get("delta_f1"))

    line1 = f"본 Run은 샘플 수 N={n} 기준, 구조 품질 통과율(Structural PASS) {_pct(pass_rate) if pass_rate is not None else 'N/A'}, "
    line1 += f"극성 충돌률 {_pct(pol_conf) if pol_conf is not None else 'N/A'}, 위험 해소율 {_pct(rr) if rr is not None else 'N/A'}로 집계되었습니다."

    line2 = f"Stage2 채택률 {_pct(stage2) if stage2 is not None else 'N/A'}, "
    line2 += f"가이드 변경률 {_pct(gcr) if gcr is not None else 'N/A'}, 비가이드 드리프트 {_pct(udr) if udr is not None else 'N/A'}입니다."
    if n_gold and (f1_s1 is not None or f1_s2 is not None):
        line2 += f" 골드 N={int(n_gold)} 기준 Triplet F1(Stage1) {_pct(f1_s1) if f1_s1 is not None else 'N/A'}, F1(Stage2+Mod) {_pct(f1_s2) if f1_s2 is not None else 'N/A'}, ΔF1 {_num(delta_f1) if delta_f1 is not None else 'N/A'} (aspect-polarity F1)."

    line3 = "추가 검증이 필요하면 Appendix의 샘플별 상세를 참고하세요."
    return [line1, line2, line3]


def _to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
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
) -> None:
    run_id = manifest.get("run_id") or run_dir.name
    date_utc = (manifest.get("timestamp_utc") or "").replace("Z", " UTC")
    profile = manifest.get("purpose") or computed.get("profile") or "—"
    backbone = manifest.get("backbone") or {}
    provider = backbone.get("provider") or "—"
    model = backbone.get("model") or "—"
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

    # KPI values from struct_metrics + computed (Stage2 Adoption moved to RQ3 / appendix)
    structural_pass = computed.get("structural_pass_rate")
    pol_conf = _to_float(struct_metrics.get("polarity_conflict_rate"))
    risk_res = _to_float(struct_metrics.get("risk_resolution_rate"))
    risk_flagged = _to_float(struct_metrics.get("risk_flagged_rate"))
    guided = _to_float(struct_metrics.get("guided_change_rate"))
    unguided = _to_float(struct_metrics.get("unguided_drift_rate"))
    # F1 from struct_metrics (structural_metrics.csv) when gold present
    n_gold_kpi = _to_float(struct_metrics.get("N_gold")) or (stage2_correction.get("N_gold") or 0)
    triplet_f1_s2_kpi = _to_float(struct_metrics.get("triplet_f1_s2")) if n_gold_kpi else None
    if triplet_f1_s2_kpi is None and n_gold_kpi:
        triplet_f1_s2_kpi = _to_float(stage2_correction.get("triplet_f1_s2"))

    kpi_cards = [
        ("Structural PASS rate", structural_pass, 1.0),
        ("Polarity Conflict Rate", pol_conf if pol_conf is not None else 0, 1.0),
        ("Risk Resolution Rate", risk_res if risk_res is not None else 0, 1.0),
        ("Risk-Flagged Rate", risk_flagged if risk_flagged is not None else 0, 1.0),
        ("Guided Change Rate", guided if guided is not None else 0, 1.0),
        ("Unguided Drift Rate", unguided if unguided is not None else 0, 1.0),
    ]
    if n_gold_kpi and triplet_f1_s2_kpi is not None:
        kpi_cards.append(("Triplet F1 (Stage2+Mod)", triplet_f1_s2_kpi, 1.0))

    kpi_html = ""
    for label, val, max_v in kpi_cards:
        v = val if val is not None else 0
        kpi_html += f'<div class="kpi-card"><div class="kpi-title">{label}</div><div class="kpi-value">{_pct(v) if 0 <= v <= 1 else _num(v)}</div></div>'

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

    # Overall: prefer struct_metrics so Overall column is never N/A when CSV has values (e.g. risk_resolution_rate when risk_s1=0 from scorecards)
    hf_split_table = '<table class="data-table"><thead><tr><th>Metric</th><th>Overall</th><th>HF-agree</th><th>HF-disagree</th></tr></thead><tbody>'
    for metric_key, metric_name in [
        ("risk_resolution_rate", "Risk Resolution Rate"),
        ("stage2_adoption_rate", "Stage2 Adoption Rate"),
        ("polarity_conflict_rate", "Polarity Conflict Rate"),
    ]:
        o = overall_rates.get(metric_key)
        if o is None:
            o = _to_float(struct_metrics.get(metric_key))
        a = hf_agree_rates.get(metric_key) if hf_agree_rates else None
        d = hf_disagree_rates.get(metric_key) if hf_disagree_rates else None
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

    # RQ3: Risk decomposition, Stage1 vs Stage2, Table 2 (ΔF1 / FixRate / BreakRate / NetGain when gold), Rule A~D
    risk_flagged_r = _to_float(struct_metrics.get("risk_flagged_rate"))
    risk_affected = _to_float(struct_metrics.get("risk_affected_change_rate"))
    risk_res_with_ch = _to_float(struct_metrics.get("risk_resolved_with_change_rate"))
    risk_res_without_ch = _to_float(struct_metrics.get("risk_resolved_without_change_rate"))
    ignored_prop = _to_float(struct_metrics.get("ignored_proposal_rate"))
    rq3_risk_decomp = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq3_risk_decomp += f"<tr><td>Risk-Flagged Rate</td><td>{_pct(risk_flagged_r)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Affected Change Rate</td><td>{_pct(risk_affected)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Resolved-with-Change (rate)</td><td>{_pct(risk_res_with_ch)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Risk-Resolved-without-Change (rate)</td><td>{_pct(risk_res_without_ch)}</td></tr>"
    rq3_risk_decomp += f"<tr><td>Ignored Proposal Rate</td><td>{_pct(ignored_prop)}</td></tr>"
    rq3_risk_decomp += "</tbody></table>"

    rq3_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq3_table += f"<tr><td>Risk Resolution Rate</td><td>{_pct(risk_res)}</td></tr>"
    rq3_table += f"<tr><td>Guided Change Rate</td><td>{_pct(guided)}</td></tr>"
    rq3_table += f"<tr><td>Unguided Drift Rate</td><td>{_pct(unguided)}</td></tr>"
    stage2_adopt = computed.get("stage2_adoption_rate")
    rq3_table += f"<tr><td>Stage2 Adoption Rate</td><td>{_pct(stage2_adopt) if stage2_adopt is not None else 'N/A'}</td></tr>"
    rq3_table += "</tbody></table>"

    # Table 2 (RQ1+RQ3): Triplet F1, ΔF1, FixRate, BreakRate, NetGain (when gold)
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
        t2_f1_s1 = _first(struct_metrics.get("triplet_f1_s1"), stage2_correction.get("triplet_f1_s1"))
        t2_f1_s2 = _first(struct_metrics.get("triplet_f1_s2"), stage2_correction.get("triplet_f1_s2"))
        t2_delta = _first(struct_metrics.get("delta_f1"), stage2_correction.get("delta_f1"))
        t2_fix = _first(struct_metrics.get("fix_rate"), stage2_correction.get("fix_rate"))
        t2_break = _first(struct_metrics.get("break_rate"), stage2_correction.get("break_rate"))
        t2_net = _first(struct_metrics.get("net_gain"), stage2_correction.get("net_gain"))
        n_gold_display = int(n_gold_struct) if n_gold_struct else (n_gold_corr or 0)
        table2_html = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
        table2_html += f"<tr><td>N (with gold)</td><td>{n_gold_display}</td></tr>"
        table2_html += f"<tr><td>Triplet F1 (Stage1)</td><td>{_num(t2_f1_s1)}</td></tr>"
        table2_html += f"<tr><td>Triplet F1 (Stage2+Moderator)</td><td>{_num(t2_f1_s2)}</td></tr>"
        table2_html += f"<tr><td>ΔF1 (S2−S1)</td><td>{_num(t2_delta)}</td></tr>"
        table2_html += f"<tr><td>Fix Rate ↑</td><td>{_pct(t2_fix) if t2_fix is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Break Rate ↓</td><td>{_pct(t2_break) if t2_break is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Net Gain ↑</td><td>{_num(t2_net) if t2_net is not None else 'N/A'}</td></tr>"
        corr_prec = stage2_correction.get("correction_precision")
        cis = stage2_correction.get("conservative_improvement_score")
        table2_html += f"<tr><td>Correction Precision</td><td>{_pct(corr_prec) if corr_prec is not None else 'N/A'}</td></tr>"
        table2_html += f"<tr><td>Conservative Improvement Score (λ=2)</td><td>{_num(cis) if cis is not None else 'N/A'}</td></tr>"
        table2_html += "</tbody></table>"
        table2_html += "<p class=\"header-meta\">F1 is aspect-polarity F1 (match on aspect+polarity; evaluation-only). Values from structural_metrics.csv when available.</p>"
    else:
        table2_html = "<p class=\"header-meta\">Gold triplets not present; Table 2 (ΔF1, Fix Rate, Break Rate, Net Gain) requires labeled data.</p>"

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
        transition_table_html = "<p class=\"header-meta\">Correctness snapshot not present in scorecards; transition table requires label experiment (correctness or triplet_correctness).</p>"
        transition_note = ""

    rule_counts = computed.get("rule_counts") or {}
    rule_table = "<table class=\"data-table\"><thead><tr><th>Rule</th><th>Count</th></tr></thead><tbody>"
    for rule in ["RuleA", "RuleB", "RuleM", "RuleD"]:
        rule_table += f"<tr><td>{rule}</td><td>{rule_counts.get(rule, 0)}</td></tr>"
    rule_table += "</tbody></table>"

    # RQ2: self_consistency, risk_set_consistency; interpret with Break Rate when gold available
    self_cons = _to_float(struct_metrics.get("self_consistency_exact"))
    risk_cons = _to_float(struct_metrics.get("risk_set_consistency"))
    break_rate_val = (_to_float(struct_metrics.get("break_rate")) or stage2_correction.get("break_rate")) if has_gold else None
    rq2_table = "<table class=\"data-table\"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>"
    rq2_table += f"<tr><td>Self-consistency (exact)</td><td>{_pct(self_cons) if self_cons is not None else 'N/A'}</td></tr>"
    rq2_table += f"<tr><td>Risk-set consistency</td><td>{_pct(risk_cons) if risk_cons is not None else 'N/A'}</td></tr>"
    rq2_table += "</tbody></table>"
    rq2_note = ""
    if break_rate_val is not None:
        rq2_note = "<p class=\"header-meta\">Interpret stability together with Break Rate (Stage2): stable but wrong vs. unstable but correcting.</p>"

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
.kpi-card { background: var(--card); padding: 0.75rem; border-radius: 6px; }
.kpi-title { font-size: 0.75rem; color: var(--muted); }
.kpi-value { font-size: 1.25rem; font-weight: 600; color: var(--green); }
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
  <span><strong>Schema</strong> {SCHEMA_VERSION}</span>
</div>
</header>

<section class="section" id="executive">
<h2>Executive Summary</h2>
<div class="kpi-grid">
{kpi_html}
</div>
<div class="conclusion">
  <p><strong>이 Run의 결론</strong></p>
  <p>{conclusion_lines[0]}</p>
  <p>{conclusion_lines[1]}</p>
  <p>{conclusion_lines[2]}</p>
</div>
<p class="header-meta">{hf_sentence}</p>
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
<h3>Table 2: Triplet F1, ΔF1, Fix Rate, Break Rate, Net Gain (gold required)</h3>
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
<p class="header-meta">{env_note}</p>
</section>
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

    build_html(run_dir, manifest, scorecards, struct_metrics, computed, stage2_correction, transition_summary, out_path, top_n=args.top_n)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
