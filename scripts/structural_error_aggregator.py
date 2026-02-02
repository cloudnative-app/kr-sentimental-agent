"""
Aggregate structural errors and paper metrics from scorecards (single-run or merged).

=== INPUT ===
  --input PATH (required)
      Scorecards JSONL. Either:
      - Single run: <run_dir>/scorecards.jsonl (one row per sample).
      - Merged runs: merged_scorecards.jsonl (multiple rows per text_id for self_consistency).
  --outdir PATH (default: results/metrics)
      Directory to write structural_metrics.csv and structural_metrics_table.md.
  --profile {smoke|regression|paper_main} (optional)
      Filter rows by scorecard field "profile" (or meta.profile) before aggregating.
  --traces PATH (optional)
      Reserved for future use (proposal_id ↔ stage2 linkage). Currently unused.

  Input row schema (per line): scorecard object with at least:
    run_id, profile (or meta.profile), ate/ate_score, atsa/atsa_score, validator,
    moderator, stage_delta, flags, meta.text_id (or meta.case_id, meta.uid for grouping).
    Optional: aux_signals.hf (for HF metrics), inputs.ate_debug.filtered.

=== OUTPUT ===
  <outdir>/structural_metrics.csv
      Single row of aggregated metrics (column names below).
  <outdir>/structural_metrics_table.md
      Markdown table of the same metrics (float as 4-decimal, None as "N/A").

  Output columns (metrics):
    n                                  (int)   Sample count after profile filter.
    aspect_hallucination_rate          (float) ate.hallucination_flag or filtered drop.
    unsupported_polarity_rate          (float) atsa opinion_grounded / evidence issues.
    polarity_conflict_rate             (float) moderator RuleM or stage1 vs stage2 label conflict.
    negation_contrast_failure_rate      (float) validator NEGATION/CONTRAST risk count / N.
    guided_change_rate                 (float) stage_delta change_type=guided / all changes.
    unguided_drift_rate                (float) stage_delta change_type=unguided / N.
    risk_resolution_rate               (float) (stage1_risks - stage2_risks) / stage1_risks.
    risk_flagged_rate                  (float) Validator가 risk를 잡은 비율 (samples with ≥1 stage1 risk / N).
    risk_affected_change_rate          (float) risk-flagged 중 Stage2 변경 발생 비율.
    risk_resolved_with_change_rate     (float) 변경 발생 샘플 중 risk 해소 비율.
    risk_resolved_without_change_rate  (float) 변경 없음 샘플 중 risk 해소 비율.
    ignored_proposal_rate              (float) risk 있었는데 변경 없음 비율 (risk-flagged 대비).
    residual_risk_severity_sum         (float) Sum of severity weights (stage2 risks).
    parse_generate_failure_rate        (float) flags.parse_failed or generate_failed.
    hf_polarity_disagreement_rate      (float|N/A) HF_Polarity_Disagreement_Rate: 외부 기준 대비 이탈도. N/A if no aux_signals.hf.
    hf_disagreement_coverage_of_structural_risks (float|N/A) HF_Disagreement_Coverage_of_Structural_Risks. N/A if no HF.
    (Report text: "HF-based polarity agreement is used as an external reference signal, not as a correctness criterion.")
    conditional_improvement_gain_hf_disagree    (N/A) Requires gold; not computed.
    conditional_improvement_gain_hf_agree        (N/A) Requires gold; not computed.
    self_consistency_exact             (float) Same final label across runs (merged); 1.0 if single run.
    risk_set_consistency               (float) Same validator risk_set across runs; 1.0 if single run.
    profile_filter                     (str, optional) Present if profile filter yielded 0 rows and fallback to all.

Usage:
  python scripts/structural_error_aggregator.py --input results/my_run/scorecards.jsonl --outdir results/metrics --profile paper_main
  python scripts/structural_error_aggregator.py --input results/scorecards_3runs.jsonl --outdir results/metrics --profile paper_main
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _n(r: Optional[float]) -> float:
    return r if r is not None else 0.0


def _rate(num: int, denom: int) -> float:
    return (num / denom) if denom else 0.0


# ---------- Triplet / gold-based F1 (for structural_metrics.csv so aggregate_seed_metrics can include F1) ----------
Triplet = Tuple[str, str, str]


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


def _triplets_from_list(items: Any) -> set:
    if not items or not isinstance(items, (list, tuple)):
        return set()
    return {_triplet_from_sent(it) for it in items if it and isinstance(it, dict)}


def _gold_triplets_with_span_variants(gold_list: List[Dict[str, Any]]) -> set:
    """
    Build gold set with canonical triplets plus span-based variants for matching.
    When annotation uses categorical aspect_ref (e.g. '제품 전체#편의성') and opinion_term.term
    as the surface span, we add (opinion_term.term, opinion_term.term, polarity) so that
    model predictions using span-based aspect_ref can match. Evaluation-only; no leakage.
    """
    out: set = set()
    for it in gold_list or []:
        if not it or not isinstance(it, dict):
            continue
        out.add(_triplet_from_sent(it))
        op = it.get("opinion_term")
        op_term = _norm_txt(op.get("term") if isinstance(op, dict) else op)
        aspect_canon = _norm_txt(it.get("aspect_ref") or it.get("term"))
        polarity = _norm_txt(it.get("polarity") or it.get("label"))
        if op_term and aspect_canon != op_term:
            out.add((op_term, op_term, polarity))
    return out


def _extract_gold_triplets(record: Dict[str, Any]) -> Optional[set]:
    gold = record.get("gold_triplets") or (record.get("inputs") or {}).get("gold_triplets")
    if isinstance(gold, list) and gold:
        return _gold_triplets_with_span_variants(gold)
    return None


def _get_process_trace(record: Dict[str, Any]) -> list:
    """Get process_trace from runtime or runtime.parsed_output (scorecard stores it inside parsed_output)."""
    runtime = record.get("runtime") or {}
    trace = runtime.get("process_trace") or record.get("process_trace") or []
    if not trace and isinstance(runtime.get("parsed_output"), dict):
        trace = runtime["parsed_output"].get("process_trace") or []
    return trace if isinstance(trace, list) else []


def _extract_final_triplets(record: Dict[str, Any]) -> set:
    """Prefer Stage2+Moderator final_aspects (parsed_output.final_result), then inputs.aspect_sentiments (Stage1)."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_aspects = (parsed.get("final_result") or {}).get("final_aspects")
    if final_aspects:
        out = _triplets_from_list(final_aspects)
        if out:
            return out
    inputs = record.get("inputs") or {}
    sents = inputs.get("aspect_sentiments")
    if sents:
        return _triplets_from_list(sents)
    return set()


def _extract_stage1_triplets(record: Dict[str, Any]) -> set:
    trace = _get_process_trace(record)
    for entry in trace:
        if (entry.get("stage") or "").lower() == "stage1" and (entry.get("agent") or "").lower() == "atsa":
            sents = (entry.get("output") or {}).get("aspect_sentiments")
            if sents:
                return _triplets_from_list(sents)
    return _extract_final_triplets(record)


def _triplets_to_ap_pairs(triplets: set) -> set:
    """(aspect, opinion, polarity) -> {(aspect, polarity)} for aspect-polarity F1 (evaluation-only)."""
    return {(a, p) for (a, o, p) in (triplets or set())}

def _precision_recall_f1(pred: set, gold: set) -> Tuple[float, float, float]:
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


def _precision_recall_f1_ap(pred_triplets: set, gold_triplets: set) -> Tuple[float, float, float]:
    """
    Aspect-polarity F1: match on (aspect, polarity) only so categorical gold and span-based pred
    are comparable. Evaluation-only; no leakage.
    """
    gold_ap = _triplets_to_ap_pairs(gold_triplets)
    pred_ap = _triplets_to_ap_pairs(pred_triplets)
    if not gold_ap:
        return (0.0, 0.0, 0.0)
    pred_ap = pred_ap or set()
    tp = len(pred_ap & gold_ap)
    fp = len(pred_ap - gold_ap)
    fn = len(gold_ap - pred_ap)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
    return (prec, rec, f1)


def compute_stage2_correction_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """When gold triplets exist: triplet_f1_s1, triplet_f1_s2, delta_f1, fix_rate, break_rate, net_gain, N_gold. Else N/A.
    F1 is aspect-polarity F1 (match on (aspect, polarity) only; evaluation-only, no leakage)."""
    out: Dict[str, Any] = {
        "triplet_f1_s1": None, "triplet_f1_s2": None, "delta_f1": None,
        "fix_rate": None, "break_rate": None, "net_gain": None, "N_gold": 0,
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
        _, _, f1_1 = _precision_recall_f1_ap(s1, gold)
        _, _, f1_2 = _precision_recall_f1_ap(s2, gold)
        f1_s1_list.append(f1_1)
        f1_s2_list.append(f1_2)
        gold_ap = _triplets_to_ap_pairs(gold)
        st1 = _triplets_to_ap_pairs(s1) == gold_ap
        st2 = _triplets_to_ap_pairs(s2) == gold_ap
        if not st1 and st2:
            n_fix += 1
        if st1 and not st2:
            n_break += 1
        if not st1 and not st2:
            n_still += 1
        if st1 and st2:
            n_keep += 1
    if f1_s1_list:
        out["triplet_f1_s1"] = sum(f1_s1_list) / len(f1_s1_list)
    if f1_s2_list:
        out["triplet_f1_s2"] = sum(f1_s2_list) / len(f1_s2_list)
    if f1_s1_list and f1_s2_list:
        out["delta_f1"] = (out["triplet_f1_s2"] or 0.0) - (out["triplet_f1_s1"] or 0.0)
    need_fix = n_fix + n_still
    out["fix_rate"] = _rate(n_fix, need_fix) if need_fix else None
    keep_break = n_break + n_keep
    out["break_rate"] = _rate(n_break, keep_break) if keep_break else None
    out["net_gain"] = (n_fix - n_break) / N if N else None
    out["N_gold"] = N
    return out


# ---------- Canonical sources (Task 3) ----------
# Hallucinated aspect: ate vs input span match -> ate.hallucination_flag or derived from ate_score
# Unsupported polarity: atsa.evidence_flags / sentiment_judgements issues
# Polarity conflict: aggregator.conflict_flags / stage1 vs stage2 label conflict
# Negation/contrast: validator.structural_risks (risk_id NEGATION_SCOPE, CONTRAST_SCOPE)
# Stage1↔2 change: stage_delta
# Self-consistency / risk-set: merged_scorecards (multiple runs per case)


def has_hallucinated_aspect(record: Dict[str, Any]) -> bool:
    """Input span에 매칭되지 않는 aspect 비율 소스: ate_score filtered drop or ate.hallucination_flag."""
    ate = record.get("ate") or record.get("ate_score") or {}
    flags = record.get("flags") or {}
    if record.get("ate", {}).get("hallucination_flag") is True:
        return True
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    drops = [f for f in filtered if f.get("action") == "drop"]
    return len(drops) > 0 and len(filtered) > 0


def has_unsupported_polarity(record: Dict[str, Any]) -> bool:
    """evidence 없거나 aspect와 비정합인 polarity: atsa_score sentiment_judgements issues."""
    atsa = record.get("atsa") or record.get("atsa_score") or {}
    judgements = atsa.get("sentiment_judgements") or []
    for j in judgements:
        if j.get("issues") or not j.get("opinion_grounded", True) or not j.get("evidence_relevant", True):
            return True
    return False


def has_polarity_conflict(record: Dict[str, Any]) -> bool:
    """동일 aspect 상충 polarity: moderator RuleM or stage1 vs stage2 label conflict."""
    mod = record.get("moderator") or {}
    if "RuleM" in (mod.get("applied_rules") or []):
        return True
    stage1_label = (record.get("stage1_ate") or {}).get("label") or ""
    stage2_ate = record.get("stage2_ate") or {}
    stage2_label = stage2_ate.get("label") if isinstance(stage2_ate, dict) else None
    if stage2_label is not None and stage1_label != stage2_label:
        return True
    return False


def count_negation_contrast_risks(record: Dict[str, Any]) -> int:
    """validator.structural_risks 중 NEGATION_SCOPE, CONTRAST_SCOPE."""
    count = 0
    for stage_block in record.get("validator") or []:
        for r in (stage_block.get("structural_risks") or []):
            rid = (r.get("risk_id") or "").upper()
            if "NEGATION" in rid or "CONTRAST" in rid:
                count += 1
    return count


def stage_delta_guided_unguided(record: Dict[str, Any]) -> Tuple[bool, bool]:
    """(has_guided_change, has_unguided_drift)."""
    delta = record.get("stage_delta") or {}
    changed = delta.get("changed", False)
    change_type = (delta.get("change_type") or "none").lower()
    guided = changed and change_type == "guided"
    unguided = changed and change_type == "unguided"
    return guided, unguided


def count_stage1_risks(record: Dict[str, Any]) -> int:
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() == "stage1":
            return len(stage_block.get("structural_risks") or [])
    return 0


def count_stage2_risks(record: Dict[str, Any]) -> int:
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() == "stage2":
            return len(stage_block.get("structural_risks") or [])
    return 0


def residual_risk_severity(record: Dict[str, Any]) -> float:
    """Stage2 (final) structural_risks severity 가중합: high=3, mid=2, low=1."""
    weight = {"high": 3.0, "mid": 2.0, "low": 1.0}
    total = 0.0
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() != "stage2":
            continue
        for r in (stage_block.get("structural_risks") or []):
            total += weight.get((r.get("severity") or "mid").lower(), 2.0)
    return total


def parse_generate_failed(record: Dict[str, Any]) -> bool:
    flags = record.get("flags") or {}
    return bool(flags.get("parse_failed") or flags.get("generate_failed"))


# ---------- HF aux signal metrics (append-only; no impact on Validator/Moderator) ----------
def _norm_polarity(label: str) -> str:
    """Normalize to pos/neg/neu for HF–LLM comparison."""
    if not label:
        return "neu"
    key = (label or "").strip().lower()
    norm = {"positive": "pos", "pos": "pos", "negative": "neg", "neg": "neg", "neutral": "neu", "neu": "neu", "mixed": "neu"}
    return norm.get(key) or "neu"


def get_final_polarity(record: Dict[str, Any]) -> str:
    """Final polarity (moderator.final_label or final_result.label) normalized pos/neg/neu."""
    mod = record.get("moderator") or {}
    final = (mod.get("final_label") or (record.get("final_result") or {}).get("label") or "")
    return _norm_polarity(final)


def get_hf_label(record: Dict[str, Any]) -> Optional[str]:
    """HF label from aux_signals.hf if present."""
    hf = (record.get("aux_signals") or {}).get("hf") or {}
    return hf.get("label")


def hf_disagrees_with_final(record: Dict[str, Any]) -> bool:
    """HF label ≠ final polarity (for HF–LLM Polarity Disagreement Rate)."""
    hf_label = get_hf_label(record)
    if hf_label is None:
        return False
    final = get_final_polarity(record)
    return _norm_polarity(hf_label) != final


def has_validator_risk(record: Dict[str, Any]) -> bool:
    """Validator structural_risks 존재 여부."""
    return count_stage1_risks(record) > 0 or count_stage2_risks(record) > 0


def hf_disagreement_coverage_of_structural_risks(record: Dict[str, Any]) -> Optional[bool]:
    """Among samples with Validator risk: HF disagrees with final? (None if no HF or no risk)."""
    if not has_validator_risk(record):
        return None
    hf_label = get_hf_label(record)
    if hf_label is None:
        return None
    return hf_disagrees_with_final(record)


def aggregate_single_run(rows: List[Dict[str, Any]], profile_filter: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate metrics over a list of scorecards (single run or already filtered)."""
    if profile_filter:
        rows = [r for r in rows if (r.get("profile") or r.get("meta", {}).get("profile")) == profile_filter]
    N = len(rows)
    if N == 0:
        return {"n": 0}

    hallucinated = sum(1 for r in rows if has_hallucinated_aspect(r))
    unsupported = sum(1 for r in rows if has_unsupported_polarity(r))
    polarity_conflict = sum(1 for r in rows if has_polarity_conflict(r))
    negation_contrast_risks = sum(count_negation_contrast_risks(r) for r in rows)
    guided_changes = sum(1 for r in rows if stage_delta_guided_unguided(r)[0])
    unguided_drifts = sum(1 for r in rows if stage_delta_guided_unguided(r)[1])
    all_changes = sum(1 for r in rows if (r.get("stage_delta") or {}).get("changed", False))
    risk_s1 = sum(count_stage1_risks(r) for r in rows)
    risk_s2 = sum(count_stage2_risks(r) for r in rows)
    resolved = risk_s1 - risk_s2  # simplified: residual risk count decrease
    residual_sev = sum(residual_risk_severity(r) for r in rows)
    parse_gen_fail = sum(1 for r in rows if parse_generate_failed(r))

    # Risk decomposition: risk-flagged, risk-affected change, resolved with/without change, ignored proposal
    n_risk_flagged = 0
    n_risk_affected_change = 0  # risk-flagged and stage_delta.changed
    n_with_change = 0
    n_resolved_with_change = 0
    n_without_change = 0
    n_resolved_without_change = 0
    n_ignored_proposal = 0  # risk-flagged and not changed
    for r in rows:
        s1 = count_stage1_risks(r)
        s2 = count_stage2_risks(r)
        changed = (r.get("stage_delta") or {}).get("changed", False)
        is_resolved = s1 > 0 and s2 < s1
        if s1 > 0:
            n_risk_flagged += 1
            if changed:
                n_risk_affected_change += 1
            else:
                n_ignored_proposal += 1
        if changed:
            n_with_change += 1
            if is_resolved:
                n_resolved_with_change += 1
        else:
            n_without_change += 1
            if is_resolved:
                n_resolved_without_change += 1
    risk_flagged_rate = _rate(n_risk_flagged, N)
    risk_affected_change_rate = _rate(n_risk_affected_change, n_risk_flagged) if n_risk_flagged else 0.0
    risk_resolved_with_change_rate = _rate(n_resolved_with_change, n_with_change) if n_with_change else 0.0
    risk_resolved_without_change_rate = _rate(n_resolved_without_change, n_without_change) if n_without_change else 0.0
    ignored_proposal_rate = _rate(n_ignored_proposal, n_risk_flagged) if n_risk_flagged else 0.0

    aspect_total = N  # per-sample; for conflict rate denominator use N or count aspects
    aspect_conflict_denom = max(N, 1)

    # HF aux metrics: external reference signal only (not a correctness criterion)
    rows_with_hf = [r for r in rows if get_hf_label(r) is not None]
    n_with_hf = len(rows_with_hf)
    hf_disagree_count = sum(1 for r in rows_with_hf if hf_disagrees_with_final(r))
    hf_polarity_disagreement_rate = _rate(hf_disagree_count, n_with_hf) if n_with_hf else None

    rows_with_risk = [r for r in rows if has_validator_risk(r)]
    risk_hf_vals = [hf_disagreement_coverage_of_structural_risks(r) for r in rows_with_risk]
    risk_hf_vals = [x for x in risk_hf_vals if x is not None]
    hf_disagreement_coverage_of_structural_risks_rate = _rate(sum(1 for x in risk_hf_vals if x), len(risk_hf_vals)) if risk_hf_vals else None

    # Conditional Improvement Gain (ΔTriplet F1 | HF-disagree / HF-agree): requires gold; placeholder when no gold
    conditional_improvement_gain_hf_disagree = None  # requires gold/triplet F1
    conditional_improvement_gain_hf_agree = None  # requires gold/triplet F1

    debate_coverages: List[float] = []
    debate_direct_rates: List[float] = []
    debate_fallback_rates: List[float] = []
    debate_none_rates: List[float] = []
    debate_total_rebuttals = 0
    debate_fail_counts = {"no_aspects": 0, "no_match": 0, "neutral_stance": 0, "fallback_used": 0}
    debate_override_applied = 0
    debate_override_skipped_low = 0
    debate_override_skipped_conflict = 0
    for r in rows:
        debate = r.get("debate") or {}
        mapping_stats = debate.get("mapping_stats") or (r.get("meta") or {}).get("debate_mapping_stats") or {}
        total = sum(int(v) for v in mapping_stats.values()) if mapping_stats else 0
        if total > 0:
            direct = int(mapping_stats.get("direct") or 0)
            fallback = int(mapping_stats.get("fallback") or 0)
            none = int(mapping_stats.get("none") or 0)
            debate_coverages.append((direct + fallback) / total)
            debate_direct_rates.append(direct / total)
            debate_fallback_rates.append(fallback / total)
            debate_none_rates.append(none / total)
            debate_total_rebuttals += total
            fail = debate.get("mapping_fail_reasons") or (r.get("meta") or {}).get("debate_mapping_fail_reasons") or {}
            for key in list(debate_fail_counts.keys()):
                debate_fail_counts[key] += int(fail.get(key) or 0)
        override = debate.get("override_stats") or (r.get("meta") or {}).get("debate_override_stats") or {}
        debate_override_applied += int(override.get("applied") or 0)
        debate_override_skipped_low += int(override.get("skipped_low_signal") or 0)
        debate_override_skipped_conflict += int(override.get("skipped_conflict") or 0)

    out = {
        "n": N,
        "aspect_hallucination_rate": _rate(hallucinated, N),
        "unsupported_polarity_rate": _rate(unsupported, N),
        "polarity_conflict_rate": _rate(polarity_conflict, aspect_conflict_denom),
        "negation_contrast_failure_rate": _rate(negation_contrast_risks, N) if N else 0.0,
        "guided_change_rate": _rate(guided_changes, all_changes) if all_changes else 0.0,
        "unguided_drift_rate": _rate(unguided_drifts, N),
        "risk_resolution_rate": _rate(max(0, resolved), risk_s1) if risk_s1 else 0.0,
        "risk_flagged_rate": risk_flagged_rate,
        "risk_affected_change_rate": risk_affected_change_rate,
        "risk_resolved_with_change_rate": risk_resolved_with_change_rate,
        "risk_resolved_without_change_rate": risk_resolved_without_change_rate,
        "ignored_proposal_rate": ignored_proposal_rate,
        "residual_risk_severity_sum": residual_sev,
        "parse_generate_failure_rate": _rate(parse_gen_fail, N),
        "hf_polarity_disagreement_rate": hf_polarity_disagreement_rate,
        "hf_disagreement_coverage_of_structural_risks": hf_disagreement_coverage_of_structural_risks_rate,
        "conditional_improvement_gain_hf_disagree": conditional_improvement_gain_hf_disagree,
        "conditional_improvement_gain_hf_agree": conditional_improvement_gain_hf_agree,
        "debate_mapping_coverage": sum(debate_coverages) / len(debate_coverages) if debate_coverages else None,
        "debate_mapping_direct_rate": sum(debate_direct_rates) / len(debate_direct_rates) if debate_direct_rates else None,
        "debate_mapping_fallback_rate": sum(debate_fallback_rates) / len(debate_fallback_rates) if debate_fallback_rates else None,
        "debate_mapping_none_rate": sum(debate_none_rates) / len(debate_none_rates) if debate_none_rates else None,
        "debate_fail_no_aspects_rate": _rate(debate_fail_counts["no_aspects"], debate_total_rebuttals) if debate_total_rebuttals else None,
        "debate_fail_no_match_rate": _rate(debate_fail_counts["no_match"], debate_total_rebuttals) if debate_total_rebuttals else None,
        "debate_fail_neutral_stance_rate": _rate(debate_fail_counts["neutral_stance"], debate_total_rebuttals) if debate_total_rebuttals else None,
        "debate_fail_fallback_used_rate": _rate(debate_fail_counts["fallback_used"], debate_total_rebuttals) if debate_total_rebuttals else None,
        "debate_override_applied": debate_override_applied,
        "debate_override_skipped_low_signal": debate_override_skipped_low,
        "debate_override_skipped_conflict": debate_override_skipped_conflict,
    }
    # Gold-based F1 / correction metrics (for aggregate_seed_metrics mean±std)
    correction = compute_stage2_correction_metrics(rows)
    for k in ("triplet_f1_s1", "triplet_f1_s2", "delta_f1", "fix_rate", "break_rate", "net_gain", "N_gold"):
        out[k] = correction.get(k)
    return out


def aggregate_merged(rows: List[Dict[str, Any]], profile_filter: Optional[str] = None) -> Dict[str, Any]:
    """When rows are merged (multi-run per case): add self_consistency, risk_set_consistency."""
    single = aggregate_single_run(rows, profile_filter)
    if single.get("n", 0) == 0:
        return single

    # Group by case_id (or text_id) for multi-run consistency
    by_case: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        meta = r.get("meta") or {}
        cid = meta.get("case_id") or meta.get("text_id") or meta.get("uid") or ""
        if not cid:
            continue
        if cid not in by_case:
            by_case[cid] = []
        by_case[cid].append(r)

    case_ids = [c for c in by_case.keys() if c]
    if not case_ids:
        single["self_consistency_exact"] = 0.0
        single["risk_set_consistency"] = 0.0
        return single

    agree_label = 0
    agree_risk = 0
    for cid in case_ids:
        group = by_case[cid]
        if len(group) < 2:
            agree_label += 1
            agree_risk += 1
            continue
        labels = [str((r.get("final_result") or {}).get("label", (r.get("meta") or {}).get("label", ""))) for r in group]
        if len(set(labels)) == 1:
            agree_label += 1
        def risk_set(r: Dict[str, Any]) -> Tuple[str, ...]:
            ids = []
            for s in (r.get("validator") or []):
                for v in (s.get("structural_risks") or []):
                    ids.append(v.get("risk_id") or "")
            return tuple(sorted(ids))
        risk_sets = [risk_set(r) for r in group]
        if len(set(risk_sets)) == 1:
            agree_risk += 1
    single["self_consistency_exact"] = _rate(agree_label, len(case_ids))
    single["risk_set_consistency"] = _rate(agree_risk, len(case_ids))
    return single


def main():
    ap = argparse.ArgumentParser(description="Aggregate structural errors from merged_scorecards.jsonl")
    ap.add_argument("--input", required=True, help="Path to merged_scorecards.jsonl (or scorecards.jsonl)")
    ap.add_argument("--outdir", default="results/metrics", help="Output directory for CSV")
    ap.add_argument("--profile", choices=["smoke", "regression", "paper_main"], default=None, help="Filter by profile")
    ap.add_argument("--traces", default=None, help="Optional traces.jsonl for proposal_id linkage")
    args = ap.parse_args()

    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        print(f"No records in {path}")
        return

    profile_filter = args.profile
    if profile_filter == "paper_main":
        profile_filter = "paper_main"
    metrics = aggregate_merged(rows, profile_filter)
    if metrics.get("n", 0) == 0 and profile_filter:
        metrics = aggregate_single_run(rows, None)
        metrics["profile_filter"] = profile_filter or "all"

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "structural_metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(metrics.keys()))
        w.writeheader()
        w.writerow(metrics)
    print(f"Wrote {csv_path}")

    md_path = outdir / "structural_metrics_table.md"
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
    ]
    for k, v in metrics.items():
        if v is None:
            v = "N/A"
        elif isinstance(v, float):
            v = f"{v:.4f}"
        lines.append(f"| {k} | {v} |")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
