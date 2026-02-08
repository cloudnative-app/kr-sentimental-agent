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
    aspect_hallucination_rate          (float) ate.hallucination_flag or filtered drop (any drop).
    alignment_failure_rate             (float) Samples with >=1 drop_reason=alignment_failure.
    filter_rejection_rate              (float) Samples with >=1 drop_reason=filter_rejection.
    semantic_hallucination_rate        (float) Samples with >=1 drop_reason=semantic_hallucination.
    implicit_grounding_rate            (float) RQ1 one-hot: implicit grounded.
    explicit_grounding_rate            (float) RQ1 one-hot: explicit grounded.
    explicit_grounding_failure_rate    (float) RQ1 one-hot: explicit grounding failure.
    unsupported_polarity_rate          (float) RQ1 one-hot: unsupported polarity (one-hot sum == 1.0).
    legacy_unsupported_polarity_rate   (float) Legacy: atsa opinion_grounded/evidence issues.
    polarity_conflict_rate             (float) RQ1: 동일 aspect span 내 polarity 충돌 (final tuples 기준).
    stage_mismatch_rate                (float) RQ2: RuleM 적용 또는 stage1_label != stage2_label.
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
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root is on path when run as script (e.g. python scripts/structural_error_aggregator.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import (
    gold_tuple_set_from_record,
    normalize_for_eval,
    normalize_polarity,
    precision_recall_f1_tuple,
    tuple_from_sent,
    tuples_from_list,
    tuples_to_pairs,
    tuple_sets_match_with_empty_rule,
)


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


# ---------- Tuple (Aspect, Polarity) F1 — see docs/absa_tuple_eval.md ----------
# Tuple = (aspect_ref, aspect_term, polarity). Pipeline uses aspect_term (AspectTerm: term, span) only.


def _extract_gold_tuples(record: Dict[str, Any]) -> Optional[Set[Tuple[str, str, str]]]:
    """Gold as set of (aspect_ref, aspect_term, polarity). Accepts gold_tuples or gold_triplets (backward compat)."""
    return gold_tuple_set_from_record(record)


def _aspect_term_text(it: dict) -> str:
    """Get aspect surface-form text from item (aspect_term.term or string)."""
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return ((it.get("opinion_term") or {}).get("term") or "").strip()


def _tuples_from_list_of_dicts(items: Any) -> Set[Tuple[str, str, str]]:
    """Convert list of {aspect_ref?, aspect_term, polarity} dicts to set of EvalTuple. Pipeline uses aspect_term only."""
    if not items or not isinstance(items, (list, tuple)):
        return set()
    out: Set[Tuple[str, str, str]] = set()
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        a = (it.get("aspect_ref") or "").strip()
        t = _aspect_term_text(it)
        p = (it.get("polarity") or it.get("label") or "").strip()
        if a or t:
            out.add((a, t, p))
    return out


def _get_process_trace(record: Dict[str, Any]) -> list:
    """Get process_trace from runtime or runtime.parsed_output (scorecard stores it inside parsed_output)."""
    runtime = record.get("runtime") or {}
    trace = runtime.get("process_trace") or record.get("process_trace") or []
    if not trace and isinstance(runtime.get("parsed_output"), dict):
        trace = runtime["parsed_output"].get("process_trace") or []
    return trace if isinstance(trace, list) else []


def _extract_final_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
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
    inputs = record.get("inputs") or {}
    sents = inputs.get("aspect_sentiments")
    if sents:
        return tuples_from_list(sents)
    return set()


def _get_first_final_tuple(record: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    """First final tuple in pipeline order (for RQ1 selected tuple). Returns (aspect_ref_norm, aspect_term_norm, polarity_norm)."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    final_tuples = final_result.get("final_tuples")
    if final_tuples and isinstance(final_tuples, list):
        for it in final_tuples:
            if not it or not isinstance(it, dict):
                continue
            a = (it.get("aspect_ref") or "").strip()
            t = "" if it.get("is_implicit") else (_aspect_term_text(it) or "").strip()
            p = (it.get("polarity") or it.get("label") or "").strip()
            if a or t or it.get("is_implicit"):
                return (normalize_for_eval(a), normalize_for_eval(t) if t else "", normalize_polarity(p))
    final_aspects = final_result.get("final_aspects")
    if final_aspects and isinstance(final_aspects, list):
        for it in final_aspects:
            if it and isinstance(it, dict):
                tup = tuple_from_sent(it)
                if tup[0] or tup[1] or (tup[2] and tup[2].strip()):
                    return tup
    inputs = record.get("inputs") or {}
    sents = inputs.get("aspect_sentiments")
    if sents and isinstance(sents, list):
        for it in sents:
            if it and isinstance(it, dict):
                tup = tuple_from_sent(it)
                if tup[0] or tup[1] or (tup[2] and tup[2].strip()):
                    return tup
    return None


def _extract_stage1_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    """Prefer final_result.stage1_tuples when present; else process_trace Stage1 ATSA aspect_sentiments."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    stage1_tuples = final_result.get("stage1_tuples")
    if stage1_tuples and isinstance(stage1_tuples, list):
        out = _tuples_from_list_of_dicts(stage1_tuples)
        if out:
            return out
    trace = _get_process_trace(record)
    for entry in trace:
        if (entry.get("stage") or "").lower() == "stage1" and (entry.get("agent") or "").lower() == "atsa":
            sents = (entry.get("output") or {}).get("aspect_sentiments")
            if sents:
                return tuples_from_list(sents)
    return _extract_final_tuples(record)


def _row_delta_f1(record: Dict[str, Any]) -> Optional[float]:
    """Per-row delta_f1 (S2−S1 F1) when gold exists; None otherwise. For override subset metrics."""
    gold = _extract_gold_tuples(record)
    if not gold:
        return None
    s1 = _extract_stage1_tuples(record)
    s2 = _extract_final_tuples(record)
    _, _, f1_1 = precision_recall_f1_tuple(gold, s1)
    _, _, f1_2 = precision_recall_f1_tuple(gold, s2)
    return f1_2 - f1_1


def _get_override_stats(record: Dict[str, Any]) -> Dict[str, int]:
    """Override stats for this row (debate.override_stats or meta.debate_override_stats)."""
    override = (record.get("debate") or {}).get("override_stats") or (record.get("meta") or {}).get("debate_override_stats") or {}
    return override if isinstance(override, dict) else {}


def compute_stage2_correction_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """When gold tuples exist: tuple_f1_s1, tuple_f1_s2, delta_f1, fix_rate, break_rate, net_gain, N_gold. Else N/A.
    F1 matches on (aspect_term, polarity) only. Rows without gold excluded. See docs/absa_tuple_eval.md.
    Fallback: when no row has gold, set N_gold = len(rows) and gold_available = False so denominator is meaningful."""
    out: Dict[str, Any] = {
        "tuple_f1_s1": None, "tuple_f1_s2": None, "delta_f1": None,
        "triplet_f1_s1": None, "triplet_f1_s2": None,  # deprecated alias
        "fix_rate": None, "break_rate": None, "net_gain": None, "N_gold": 0,
        "gold_available": True,
    }
    rows_with_gold = [(r, _extract_gold_tuples(r)) for r in rows if _extract_gold_tuples(r) is not None]
    if not rows_with_gold:
        out["N_gold"] = len(rows)
        out["gold_available"] = False
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
    if f1_s1_list:
        out["tuple_f1_s1"] = sum(f1_s1_list) / len(f1_s1_list)
        out["triplet_f1_s1"] = out["tuple_f1_s1"]
    if f1_s2_list:
        out["tuple_f1_s2"] = sum(f1_s2_list) / len(f1_s2_list)
        out["triplet_f1_s2"] = out["tuple_f1_s2"]
    if f1_s1_list and f1_s2_list:
        out["delta_f1"] = (out["tuple_f1_s2"] or 0.0) - (out["tuple_f1_s1"] or 0.0)
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


# ATE drop_reason taxonomy (must match scorecard_from_smoke; see docs/metric_spec_rq1_grounding_v2.md)
DROP_REASON_ALIGNMENT_FAILURE = "alignment_failure"
DROP_REASON_FILTER_REJECTION = "filter_rejection"
DROP_REASON_SEMANTIC_HALLUCINATION = "semantic_hallucination"


def count_hallucination_types(record: Dict[str, Any]) -> Dict[str, bool]:
    """Per-sample: True iff sample has >=1 drop with that drop_reason. Keys: alignment_failure, filter_rejection, semantic_hallucination."""
    out = {
        DROP_REASON_ALIGNMENT_FAILURE: False,
        DROP_REASON_FILTER_REJECTION: False,
        DROP_REASON_SEMANTIC_HALLUCINATION: False,
    }
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    for f in filtered:
        if f.get("action") != "drop":
            continue
        reason = (f.get("drop_reason") or "").strip()
        if reason == DROP_REASON_ALIGNMENT_FAILURE:
            out[DROP_REASON_ALIGNMENT_FAILURE] = True
        elif reason == DROP_REASON_FILTER_REJECTION:
            out[DROP_REASON_FILTER_REJECTION] = True
        elif reason == DROP_REASON_SEMANTIC_HALLUCINATION:
            out[DROP_REASON_SEMANTIC_HALLUCINATION] = True
    return out


def has_hallucinated_aspect(record: Dict[str, Any]) -> bool:
    """Input span에 매칭되지 않는 aspect 비율 소스: ate_score filtered drop or ate.hallucination_flag."""
    ate = record.get("ate") or record.get("ate_score") or {}
    flags = record.get("flags") or {}
    if record.get("ate", {}).get("hallucination_flag") is True:
        return True
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    drops = [f for f in filtered if f.get("action") == "drop"]
    return len(drops) > 0 and len(filtered) > 0


def _judgement_fail_for_unsupported(j: Dict[str, Any]) -> bool:
    """Single judgement fails for unsupported iff: opinion_grounded=False or issues other than only 'unknown/insufficient'."""
    if j.get("opinion_grounded") is False:
        return True
    issues = j.get("issues") or []
    if not issues:
        return False
    if all(x == "unknown/insufficient" for x in issues):
        return False  # evidence/span 없음만 → unsupported로 강제하지 않음
    return True


def has_unsupported_polarity(record: Dict[str, Any]) -> bool:
    """Sample unsupported iff: all judgements fail, OR any judgement for a final-tuple aspect fails.
    Relaxed: 'unknown/insufficient' only is not counted as fail.
    Join key: normalize_for_eval(aspect_term) for both final_tuples and judgement.aspect_term."""
    atsa = record.get("atsa") or record.get("atsa_score") or {}
    judgements = atsa.get("sentiment_judgements") or []
    if not judgements:
        return False
    final_tuples = _extract_final_tuples(record)
    final_terms_norm = {normalize_for_eval((aspect_term or "").strip()) for (_, aspect_term, _) in final_tuples if (aspect_term or "").strip()}
    all_fail = all(_judgement_fail_for_unsupported(j) for j in judgements)
    selected_fail = False
    if final_terms_norm:
        for j in judgements:
            term_norm = normalize_for_eval((j.get("aspect_term") or "").strip())
            if term_norm in final_terms_norm and _judgement_fail_for_unsupported(j):
                selected_fail = True
                break
    return all_fail or selected_fail


# RQ1 one-hot bucket labels (see docs/metric_spec_rq1_grounding_v2.md)
RQ1_BUCKET_IMPLICIT = "implicit"
RQ1_BUCKET_EXPLICIT = "explicit"
RQ1_BUCKET_EXPLICIT_FAILURE = "explicit_failure"
RQ1_BUCKET_UNSUPPORTED = "unsupported"


def _is_implicit_fallback_eligible(record: Dict[str, Any], final_label: str, first: Optional[Tuple[str, str, str]]) -> bool:
    """True if sample would be explicit_failure but is eligible for implicit (doc-level polarity valid + candidate).
    See docs/implicit_fallback_review_and_plan.md."""
    pol = (final_label or (first[2] if first else "") or "").strip()
    if not pol or normalize_polarity(pol) not in ("positive", "negative", "neutral", "mixed"):
        return False
    inputs = record.get("inputs") or {}
    if inputs.get("implicit_grounding_candidate") is True:
        return True
    filtered = (inputs.get("ate_debug") or {}).get("filtered") or []
    drops = [f for f in filtered if f.get("action") == "drop"]
    if not drops:
        return False
    all_dropped = len(drops) == len(filtered)
    all_align_fail = all((f.get("drop_reason") or "").strip() == DROP_REASON_ALIGNMENT_FAILURE for f in drops)
    return bool(all_dropped and all_align_fail)


def get_selected_judgement(record: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    """Resolve selected tuple then its matching sentiment_judgement. Returns (judgement, idx) or (None, None)."""
    first = _get_first_final_tuple(record)
    atsa = record.get("atsa") or record.get("atsa_score") or {}
    judgements = atsa.get("sentiment_judgements") or []
    if not first:
        # No final tuple: if single judgement (sentence-level), use it
        if len(judgements) == 1:
            return judgements[0], 0
        return None, None
    _aspect_ref, selected_term_norm, _polarity = first
    if selected_term_norm == "":
        # Implicit: first judgement with empty aspect_term, or first if only one
        for idx, j in enumerate(judgements):
            term_norm = normalize_for_eval((j.get("aspect_term") or "").strip())
            if term_norm == "":
                return j, idx
        if len(judgements) == 1:
            return judgements[0], 0
        return None, None
    for idx, j in enumerate(judgements):
        term_norm = normalize_for_eval((j.get("aspect_term") or "").strip())
        if term_norm == selected_term_norm:
            return j, idx
    return None, None


def rq1_grounding_bucket(record: Dict[str, Any]) -> str:
    """One-hot RQ1 grounding bucket: implicit | explicit | explicit_failure | unsupported. Exactly one per sample."""
    first = _get_first_final_tuple(record)
    mod = record.get("moderator") or {}
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or record.get("final_result") or {}
    final_label = (mod.get("final_label") or final_result.get("label") or "").strip()
    judgement, _ = get_selected_judgement(record)

    # 1) Implicit grounded: selected aspect empty or explicit implicit, and polarity exists (normal category)
    if first:
        _a, selected_term_norm, pol = first
        if selected_term_norm == "":
            if pol and normalize_polarity(pol) in ("positive", "negative", "neutral", "mixed"):
                return RQ1_BUCKET_IMPLICIT
            return RQ1_BUCKET_UNSUPPORTED
    else:
        if final_label and normalize_polarity(final_label) in ("positive", "negative", "neutral", "mixed"):
            return RQ1_BUCKET_IMPLICIT
        return RQ1_BUCKET_UNSUPPORTED

    # 2) Explicit: selected_term != "", opinion_grounded==True, issues empty or "unknown/insufficient" only
    if judgement is None:
        return RQ1_BUCKET_UNSUPPORTED
    if judgement.get("opinion_grounded") is True:
        issues = judgement.get("issues") or []
        if not issues or all(x == "unknown/insufficient" for x in issues):
            return RQ1_BUCKET_EXPLICIT

    # 3) Explicit grounding failure: selected_term != "", judgement failed (opinion_grounded==False or mismatch)
    #    Implicit fallback: if candidate and doc polarity valid, reclassify explicit_failure → implicit
    if judgement.get("opinion_grounded") is False or any("opinion_not_grounded" in str(x) or "mismatch" in str(x).lower() for x in (judgement.get("issues") or [])):
        if _is_implicit_fallback_eligible(record, final_label, first):
            return RQ1_BUCKET_IMPLICIT
        return RQ1_BUCKET_EXPLICIT_FAILURE

    # 4) Unsupported polarity (근거 부재/비논리/불가능)
    return RQ1_BUCKET_UNSUPPORTED


def _get_final_tuples_raw(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Final tuples as list of dicts with aspect_term, polarity, grounding?, confidence?, drop_reason? for representative selection."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    final_tuples = final_result.get("final_tuples")
    if final_tuples and isinstance(final_tuples, list):
        out: List[Dict[str, Any]] = []
        for it in final_tuples:
            if not it or not isinstance(it, dict):
                continue
            t = _aspect_term_text(it)
            p = (it.get("polarity") or it.get("label") or "").strip()
            if not t and not it.get("is_implicit"):
                continue
            out.append({
                "aspect_term_norm": normalize_for_eval(t) if t else "",
                "polarity_norm": normalize_polarity(p),
                "grounding": (it.get("grounding") or "implicit").strip().lower(),
                "confidence": float(it.get("confidence") or 0),
                "drop_reason": (it.get("drop_reason") or "").strip(),
            })
        if out:
            return out
    final_aspects = final_result.get("final_aspects")
    if final_aspects and isinstance(final_aspects, list):
        out = []
        for it in final_aspects:
            if not it or not isinstance(it, dict):
                continue
            t = _aspect_term_text(it)
            p = (it.get("polarity") or it.get("label") or "").strip()
            out.append({
                "aspect_term_norm": normalize_for_eval(t) if t else "",
                "polarity_norm": normalize_polarity(p),
                "grounding": "implicit",
                "confidence": 0.0,
                "drop_reason": "",
            })
        return out
    # Fallback: from set of tuples (no meta)
    tuples = _extract_final_tuples(record)
    return [
        {"aspect_term_norm": normalize_for_eval((t or "").strip()), "polarity_norm": normalize_polarity(p), "grounding": "implicit", "confidence": 0.0, "drop_reason": ""}
        for (_, t, p) in tuples if (t or "").strip()
    ]


def select_representative_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    """One tuple per aspect_norm: (aspect_ref_placeholder, aspect_term_norm, polarity_norm).
    Sort key: explicit > implicit, then confidence desc, then no drop_reason. Returns set of (a, t, p)."""
    raw = _get_final_tuples_raw(record)
    if not raw:
        return set()
    by_aspect: Dict[str, List[Dict[str, Any]]] = {}
    for it in raw:
        key = (it.get("aspect_term_norm") or "").strip() or ""
        if key not in by_aspect:
            by_aspect[key] = []
        by_aspect[key].append(it)
    out: Set[Tuple[str, str, str]] = set()
    for _aspect_norm, items in by_aspect.items():
        if not items:
            continue
        # Sort: explicit first, then confidence desc, then no drop_reason
        def _key(x: Dict[str, Any]) -> Tuple[bool, float, bool]:
            g = (x.get("grounding") or "implicit").strip().lower()
            c = float(x.get("confidence") or 0)
            dr = (x.get("drop_reason") or "").strip()
            return (g == "explicit", c, not bool(dr))

        items_sorted = sorted(items, key=_key, reverse=True)
        first = items_sorted[0]
        a = ""
        t = _aspect_norm
        p = first.get("polarity_norm") or "neutral"
        out.add((a, t, p))
    return out


def has_polarity_conflict_after_representative(record: Dict[str, Any]) -> bool:
    """RQ2 정규화: 대표 tuple 선택 후에도 상충 극성이 남을 경우만 conflict.
    Per aspect: select representative (explicit > implicit, confidence, no drop_reason); conflict iff ≥2 distinct polarities."""
    raw = _get_final_tuples_raw(record)
    if not raw:
        return False
    by_aspect: Dict[str, List[Dict[str, Any]]] = {}
    for it in raw:
        key = (it.get("aspect_term_norm") or "").strip() or ""
        if key not in by_aspect:
            by_aspect[key] = []
        by_aspect[key].append(it)
    def _key(x: Dict[str, Any]) -> Tuple[bool, float, bool]:
        g = (x.get("grounding") or "implicit").strip().lower()
        c = float(x.get("confidence") or 0)
        dr = (x.get("drop_reason") or "").strip()
        return (g == "explicit", c, not bool(dr))

    for _aspect_norm, items in by_aspect.items():
        if len(items) < 2:
            continue
        items_sorted = sorted(items, key=_key, reverse=True)
        rep_pol = items_sorted[0].get("polarity_norm") or "neutral"
        if any((it.get("polarity_norm") or "neutral") != rep_pol for it in items_sorted[1:]):
            return True
    return False


def has_stage_mismatch(record: Dict[str, Any]) -> bool:
    """RQ2: Stage1 vs Stage2 문서급 레이블 불일치 또는 RuleM 적용 (flip-flop/variance 지표)."""
    mod = record.get("moderator") or {}
    if "RuleM" in (mod.get("applied_rules") or []):
        return True
    stage1_label = (record.get("stage1_ate") or {}).get("label") or ""
    stage2_ate = record.get("stage2_ate") or {}
    stage2_label = stage2_ate.get("label") if isinstance(stage2_ate, dict) else None
    if stage2_label is not None and stage1_label != stage2_label:
        return True
    return False


def has_polarity_conflict(record: Dict[str, Any]) -> bool:
    """Legacy alias: same-aspect polarity conflict only (RQ1). Use has_same_aspect_polarity_conflict."""
    return has_same_aspect_polarity_conflict(record)


def count_negation_contrast_risks(record: Dict[str, Any]) -> int:
    """validator.structural_risks 중 NEGATION_SCOPE, CONTRAST_SCOPE."""
    count = 0
    for stage_block in record.get("validator") or []:
        for r in (stage_block.get("structural_risks") or []):
            rid = (r.get("risk_id") or "").upper()
            if "NEGATION" in rid or "CONTRAST" in rid:
                count += 1
    return count


def count_negation_contrast_risks_stage1(record: Dict[str, Any]) -> int:
    """Stage1 validator blocks only: NEGATION_SCOPE, CONTRAST_SCOPE count."""
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() != "stage1":
            continue
        n = 0
        for r in (stage_block.get("structural_risks") or []):
            rid = (r.get("risk_id") or "").upper()
            if "NEGATION" in rid or "CONTRAST" in rid:
                n += 1
        return n
    return 0


def count_negation_contrast_risks_stage2(record: Dict[str, Any]) -> int:
    """Stage2 validator blocks only: NEGATION_SCOPE, CONTRAST_SCOPE count."""
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() != "stage2":
            continue
        n = 0
        for r in (stage_block.get("structural_risks") or []):
            rid = (r.get("risk_id") or "").upper()
            if "NEGATION" in rid or "CONTRAST" in rid:
                n += 1
        return n
    return 0


def has_stage1_structural_risk(record: Dict[str, Any]) -> bool:
    """Extended stage1 structural risk (RQ3 denominator).
    True if any: validator stage1 risk > 0, polarity_conflict, negation/contrast in stage1,
    alignment_failure_count >= 2, explicit_grounding_failure."""
    if count_stage1_risks(record) > 0:
        return True
    if has_polarity_conflict_after_representative(record):
        return True
    if count_negation_contrast_risks_stage1(record) > 0:
        return True
    if count_alignment_failure_drops(record) >= 2:
        return True
    if rq1_grounding_bucket(record) == RQ1_BUCKET_EXPLICIT_FAILURE:
        return True
    return False


def has_stage2_structural_risk(record: Dict[str, Any]) -> bool:
    """Stage2 structural risk: only conditions that have a stage2 analogue (validator s2, negation/contrast s2).
    Excludes polarity_conflict, alignment_failure, explicit_failure so that 'resolved' can be > 0 when
    stage1_structural_risk was driven by those (they have no post-stage2 resolution in pipeline)."""
    if count_stage2_risks(record) > 0:
        return True
    if count_negation_contrast_risks_stage2(record) > 0:
        return True
    return False


def count_alignment_failure_drops(record: Dict[str, Any]) -> int:
    """Number of ATE drops with drop_reason=alignment_failure (for risk_flagged: alignment_failure >= 2)."""
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    return sum(1 for f in filtered if f.get("action") == "drop" and (f.get("drop_reason") or "").strip() == DROP_REASON_ALIGNMENT_FAILURE)


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


def is_risk_flagged(record: Dict[str, Any]) -> bool:
    """RQ3 denominator: True if sample is risk-flagged (OR).
    Validator stage1 risk, OR negation/contrast scope, OR polarity conflict (after representative), OR alignment_failure >= 2."""
    if count_stage1_risks(record) > 0:
        return True
    if count_negation_contrast_risks(record) > 0:
        return True
    if has_polarity_conflict_after_representative(record):
        return True
    if count_alignment_failure_drops(record) >= 2:
        return True
    return False


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
    # ATE drop decomposition (sample-level: >=1 drop with that reason)
    n_align_fail = sum(1 for r in rows if count_hallucination_types(r).get(DROP_REASON_ALIGNMENT_FAILURE))
    n_filter_rej = sum(1 for r in rows if count_hallucination_types(r).get(DROP_REASON_FILTER_REJECTION))
    n_semantic_hal = sum(1 for r in rows if count_hallucination_types(r).get(DROP_REASON_SEMANTIC_HALLUCINATION))
    unsupported = sum(1 for r in rows if has_unsupported_polarity(r))
    # RQ1 one-hot grounding buckets (exactly one per sample)
    n_implicit = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_IMPLICIT)
    n_explicit = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_EXPLICIT)
    n_explicit_failure = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_EXPLICIT_FAILURE)
    n_unsupported_rq1 = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_UNSUPPORTED)
    polarity_conflict = sum(1 for r in rows if has_polarity_conflict_after_representative(r))
    stage_mismatch = sum(1 for r in rows if has_stage_mismatch(r))
    negation_contrast_risks = sum(count_negation_contrast_risks(r) for r in rows)
    guided_changes = sum(1 for r in rows if stage_delta_guided_unguided(r)[0])
    unguided_drifts = sum(1 for r in rows if stage_delta_guided_unguided(r)[1])
    all_changes = sum(1 for r in rows if (r.get("stage_delta") or {}).get("changed", False))
    risk_s1 = sum(count_stage1_risks(r) for r in rows)
    risk_s2 = sum(count_stage2_risks(r) for r in rows)
    resolved = risk_s1 - risk_s2  # simplified: residual risk count decrease
    residual_sev = sum(residual_risk_severity(r) for r in rows)
    parse_gen_fail = sum(1 for r in rows if parse_generate_failed(r))

    # Risk decomposition: risk-flagged (extended: validator OR negation/contrast OR polarity_conflict OR align_fail>=2), risk-affected change, resolved with/without change, ignored proposal
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
        rf = is_risk_flagged(r)
        if rf:
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
    # RQ1: residual_risk_rate = 샘플 중 Stage2에 risk가 남아 있는 비율
    n_residual_risk = sum(1 for r in rows if count_stage2_risks(r) > 0)
    residual_risk_rate = _rate(n_residual_risk, N)

    # RQ3 extended: risk_resolution_rate (denom = stage1_structural_risk True, num = resolved by stage2)
    n_stage1_structural_risk = 0
    n_resolved_structural = 0
    for r in rows:
        s1_risk = r.get("stage1_structural_risk")
        if s1_risk is None:
            s1_risk = has_stage1_structural_risk(r)
        s2_risk = r.get("stage2_structural_risk")
        if s2_risk is None:
            s2_risk = has_stage2_structural_risk(r)
        if s1_risk:
            n_stage1_structural_risk += 1
            if not s2_risk:
                n_resolved_structural += 1
    risk_resolution_rate = _rate(n_resolved_structural, n_stage1_structural_risk) if n_stage1_structural_risk else 0.0
    risk_resolution_rate_legacy = _rate(max(0, resolved), risk_s1) if risk_s1 else 0.0

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
    debate_override_skipped_already_confident = 0
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
        override = _get_override_stats(r)
        debate_override_applied += int(override.get("applied") or 0)
        debate_override_skipped_low += int(override.get("skipped_low_signal") or 0)
        debate_override_skipped_conflict += int(override.get("skipped_conflict") or 0)
        debate_override_skipped_already_confident += int(override.get("skipped_already_confident") or 0)

    # Override subset metrics: applied vs skipped_conflict
    rows_applied = [r for r in rows if int(_get_override_stats(r).get("applied") or 0) > 0]
    rows_conflict = [r for r in rows if int(_get_override_stats(r).get("skipped_conflict") or 0) > 0]
    n_applied = len(rows_applied)
    n_conflict = len(rows_conflict)
    override_applied_delta_f1_mean = None
    override_applied_unsupported_rate = _rate(sum(1 for r in rows_applied if has_unsupported_polarity(r)), n_applied) if n_applied else None
    override_applied_negation_contrast_rate = _rate(sum(count_negation_contrast_risks(r) for r in rows_applied), n_applied) if n_applied else None
    if rows_applied:
        delta_f1_vals = [_row_delta_f1(r) for r in rows_applied]
        delta_f1_vals = [v for v in delta_f1_vals if v is not None]
        if delta_f1_vals:
            override_applied_delta_f1_mean = sum(delta_f1_vals) / len(delta_f1_vals)
    override_conflict_delta_f1_mean = None
    override_conflict_unsupported_rate = _rate(sum(1 for r in rows_conflict if has_unsupported_polarity(r)), n_conflict) if n_conflict else None
    override_conflict_negation_contrast_rate = _rate(sum(count_negation_contrast_risks(r) for r in rows_conflict), n_conflict) if n_conflict else None
    if rows_conflict:
        delta_f1_vals = [_row_delta_f1(r) for r in rows_conflict]
        delta_f1_vals = [v for v in delta_f1_vals if v is not None]
        if delta_f1_vals:
            override_conflict_delta_f1_mean = sum(delta_f1_vals) / len(delta_f1_vals)

    total_override_events = (
        debate_override_applied + debate_override_skipped_low + debate_override_skipped_conflict + debate_override_skipped_already_confident
    )
    debate_override_skipped_already_confident_rate = (
        _rate(debate_override_skipped_already_confident, total_override_events) if total_override_events else None
    )
    # RQ3: override_applied_rate = 적용된 샘플 비율; override_success_rate = 적용된 케이스 중 risk 개선 비율(정답 아님, risk 감소+안전)
    override_applied_rate = _rate(n_applied, N)
    n_applied_success = sum(1 for r in rows_applied if count_stage1_risks(r) > 0 and count_stage2_risks(r) < count_stage1_risks(r)) if rows_applied else 0
    override_success_rate = _rate(n_applied_success, n_applied) if n_applied else None

    out = {
        "n": N,
        "aspect_hallucination_rate": _rate(hallucinated, N),
        "alignment_failure_rate": _rate(n_align_fail, N),
        "filter_rejection_rate": _rate(n_filter_rej, N),
        "semantic_hallucination_rate": _rate(n_semantic_hal, N),
        "implicit_grounding_rate": _rate(n_implicit, N),
        "explicit_grounding_rate": _rate(n_explicit, N),
        "explicit_grounding_failure_rate": _rate(n_explicit_failure, N),
        "unsupported_polarity_rate": _rate(n_unsupported_rq1, N),
        "legacy_unsupported_polarity_rate": _rate(unsupported, N),
        "rq1_one_hot_sum": (
            _rate(n_implicit, N) + _rate(n_explicit, N) + _rate(n_explicit_failure, N) + _rate(n_unsupported_rq1, N)
        ),
        "polarity_conflict_rate": _rate(polarity_conflict, aspect_conflict_denom),
        "stage_mismatch_rate": _rate(stage_mismatch, N),
        "negation_contrast_failure_rate": _rate(negation_contrast_risks, N) if N else 0.0,
        "guided_change_rate": _rate(guided_changes, all_changes) if all_changes else 0.0,
        "unguided_drift_rate": _rate(unguided_drifts, N),
        "risk_resolution_rate": risk_resolution_rate,
        "risk_resolution_rate_legacy": risk_resolution_rate_legacy,
        "risk_flagged_rate": risk_flagged_rate,
        "residual_risk_rate": residual_risk_rate,
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
        "debate_override_skipped_already_confident": debate_override_skipped_already_confident,
        "debate_override_skipped_already_confident_rate": debate_override_skipped_already_confident_rate,
        "override_applied_n": n_applied,
        "override_applied_rate": override_applied_rate,
        "override_success_rate": override_success_rate,
        "override_applied_delta_f1_mean": override_applied_delta_f1_mean,
        "override_applied_unsupported_polarity_rate": override_applied_unsupported_rate,
        "override_applied_negation_contrast_failure_rate": override_applied_negation_contrast_rate,
        "override_skipped_conflict_n": n_conflict,
        "override_skipped_conflict_delta_f1_mean": override_conflict_delta_f1_mean,
        "override_skipped_conflict_unsupported_polarity_rate": override_conflict_unsupported_rate,
        "override_skipped_conflict_negation_contrast_failure_rate": override_conflict_negation_contrast_rate,
    }
    # Gold-based F1 / correction metrics (for aggregate_seed_metrics mean±std)
    correction = compute_stage2_correction_metrics(rows)
    for k in ("tuple_f1_s1", "tuple_f1_s2", "triplet_f1_s1", "triplet_f1_s2", "delta_f1", "fix_rate", "break_rate", "net_gain", "N_gold", "gold_available"):
        if k in correction:
            out[k] = correction[k]
    return out


# Canonical metric keys so CSV/report always have same columns (even when n=0 or fallback).
CANONICAL_METRIC_KEYS = [
    "n", "profile_filter",
    "aspect_hallucination_rate", "alignment_failure_rate", "filter_rejection_rate", "semantic_hallucination_rate",
    "implicit_grounding_rate", "explicit_grounding_rate", "explicit_grounding_failure_rate", "unsupported_polarity_rate",
    "legacy_unsupported_polarity_rate", "polarity_conflict_rate",
    "negation_contrast_failure_rate", "guided_change_rate", "unguided_drift_rate",
    "risk_resolution_rate", "risk_resolution_rate_legacy", "risk_flagged_rate", "residual_risk_rate", "risk_affected_change_rate",
    "risk_resolved_with_change_rate", "risk_resolved_without_change_rate", "ignored_proposal_rate",
    "residual_risk_severity_sum", "parse_generate_failure_rate",
    "hf_polarity_disagreement_rate", "hf_disagreement_coverage_of_structural_risks",
    "conditional_improvement_gain_hf_disagree", "conditional_improvement_gain_hf_agree",
    "debate_mapping_coverage", "debate_mapping_direct_rate", "debate_mapping_fallback_rate", "debate_mapping_none_rate",
    "debate_fail_no_aspects_rate", "debate_fail_no_match_rate", "debate_fail_neutral_stance_rate", "debate_fail_fallback_used_rate",
    "debate_override_applied", "debate_override_skipped_low_signal", "debate_override_skipped_conflict",
    "debate_override_skipped_already_confident", "debate_override_skipped_already_confident_rate",
    "override_applied_n", "override_applied_rate", "override_success_rate", "override_applied_delta_f1_mean", "override_applied_unsupported_polarity_rate", "override_applied_negation_contrast_failure_rate",
    "override_skipped_conflict_n", "override_skipped_conflict_delta_f1_mean", "override_skipped_conflict_unsupported_polarity_rate", "override_skipped_conflict_negation_contrast_failure_rate",
    "tuple_f1_s1", "tuple_f1_s2", "triplet_f1_s1", "triplet_f1_s2", "delta_f1", "fix_rate", "break_rate", "net_gain", "N_gold", "gold_available",
    "self_consistency_exact", "self_consistency_eligible", "n_trials",
    "risk_set_consistency", "flip_flop_rate", "variance",
    "stage_mismatch_rate",  # RQ2: RuleM or stage1_label != stage2_label
]


def _canonical_skeleton() -> Dict[str, Any]:
    """Skeleton so CSV/report have all columns when n=0 or partial metrics."""
    return {k: (0 if k == "n" else None) for k in CANONICAL_METRIC_KEYS}


def _ensure_canonical_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all canonical keys exist (fill missing with skeleton); keep existing values."""
    skeleton = _canonical_skeleton()
    out = dict(metrics)
    for k in CANONICAL_METRIC_KEYS:
        if k not in out:
            out[k] = skeleton[k]
    return out


def aggregate_merged(rows: List[Dict[str, Any]], profile_filter: Optional[str] = None) -> Dict[str, Any]:
    """When rows are merged (multi-run per case): add self_consistency, risk_set_consistency. Single run: exact=null, eligible=False, n_trials=1."""
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
        single["self_consistency_exact"] = None
        single["self_consistency_eligible"] = False
        single["n_trials"] = 1
        single["risk_set_consistency"] = None
        single["variance"] = None
        single["flip_flop_rate"] = None
        return single

    max_trials = max(len(by_case[cid]) for cid in case_ids)
    if max_trials < 2:
        # Single run: do not report "full consistency"; report no information
        single["self_consistency_exact"] = None
        single["self_consistency_eligible"] = False
        single["n_trials"] = 1
        single["risk_set_consistency"] = None
        single["variance"] = None
        single["flip_flop_rate"] = None
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
    single["self_consistency_eligible"] = True
    single["n_trials"] = max_trials
    single["risk_set_consistency"] = _rate(agree_risk, len(case_ids))
    # RQ2: variance = 1 - self_consistency (label variation across runs); flip_flop_rate = disagreement rate proxy
    single["variance"] = 1.0 - single["self_consistency_exact"] if single.get("self_consistency_exact") is not None else None
    single["flip_flop_rate"] = single["variance"]
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
        if metrics.get("n", 0) > 0:
            metrics["self_consistency_exact"] = None
            metrics["self_consistency_eligible"] = False
            metrics["n_trials"] = 1
    metrics = _ensure_canonical_metrics(metrics)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "structural_metrics.csv"
    fieldnames = CANONICAL_METRIC_KEYS + [k for k in metrics if k not in CANONICAL_METRIC_KEYS]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        row = {k: ("" if metrics.get(k) is None else metrics.get(k)) for k in fieldnames}
        w.writerow(row)
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
