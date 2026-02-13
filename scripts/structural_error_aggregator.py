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
    polarity_conflict_rate_raw         (float) Same aspect_term with ≥2 polarities (no representative selection).
    polarity_conflict_rate             (float) RQ1: 동일 aspect span 내 polarity 충돌 (대표 선택 후).
    polarity_conflict_rate_after_rep    (float) Same as polarity_conflict_rate (대표 선택 후).
    N_pred_final_tuples / N_pred_final_aspects / N_pred_inputs_aspect_sentiments  (int) Rows where pred came from that source.
    final_pred_source_aspects_path_unused_flag  (bool) Info: True when N_pred_final_aspects=0 with n>0 (final_aspects 경로 미사용). Not a fail.
    N_pred_used                        (int) Total pred tuple count used in F1.
    stage_mismatch_rate                (float) RQ2: RuleM 적용 또는 stage1_label != stage2_label.
    negation_contrast_failure_rate      (float) validator NEGATION/CONTRAST risk count / N.
    guided_change_rate                 (float) stage_delta change_type=guided / all changes.
    unguided_drift_rate                (float) stage_delta change_type=unguided / N.
    validator_clear_rate               (float) Stage1 structural risk 대비 Stage2 해소 비율 (Validator 기준; 기존 risk_resolution_rate).
    validator_residual_risk_rate        (float) Stage2 Validator structural_risks > 0인 샘플 비율 (Validator S2만).
    outcome_residual_risk_rate         (float) 최종 출력에서 관찰되는 구조적 리스크 1건 이상인 샘플 비율 (통합).
    risk_resolution_rate               (float) Deprecated alias for validator_clear_rate.
    residual_risk_rate                 (float) Deprecated alias for validator_residual_risk_rate.
    risk_flagged_rate                  (float) Validator가 risk를 잡은 비율 (확장 정의: stage1 OR polarity_conflict 등 / N).
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

Evaluation unit (EVAL_MODE): Tuple extraction path is fixed per record (not config declaration).
  - gold: _extract_gold_tuples(record) → inputs.gold_tuples
  - stage1: _extract_stage1_tuples(record) → final_result.stage1_tuples | process_trace stage1 ATSA
  - final: _extract_final_tuples(record) → final_result.final_tuples | final_aspects | inputs.aspect_sentiments
  Use --log_tuple_sources PATH to write per-record source + N (stage1_tuple_source, final_tuple_source, gold_tuple_source).

Evaluation design notes (B1/B2 — definition/data, not bugs):
  - B1 (long gold span): When gold aspect_term is very long/specific (e.g. full product name) and pred is short,
    matches_*_vs_gold can be 0 by design; consider gold span refinement or auxiliary substring/token-overlap metrics.
  - B2 (implicit gold): When gold has aspect_term="" (implicit), exact (aspect_term, polarity) match is 0 unless
    pred also outputs ""; separate implicit_polarity_accuracy or generalized_f1@theta for implicit cases.
  Use --sanity_check to verify gold→gold F1=1 and final→final F1=1.
  Use --snapshot_eval_inputs PATH to save gold/stage1/final tuple sets (normalized) for first N samples as JSON (regression snapshot).
  structural_metrics.csv includes eval_semver and eval_policy_hash for metric continuity (reports can explain policy changes).

Triptych Table (human-readable per-sample table; separate from tuple source log):
  --export_triptych_table PATH   Write derived/tables/triptych_table.tsv (or .csv).
  --triptych_sample_n N          0 = all rows, N = first N only (default 0).
  --triptych_include_text 0|1     Include input text column (default 1).
  --triptych_include_debug 0|1    Include evidence/rationale etc. (default 0).
  --export_triptych_risk_details PATH  Optional: triptych_risk_details.jsonl for risk drilldown.

Usage:
  python scripts/structural_error_aggregator.py --input results/my_run/scorecards.jsonl --outdir results/metrics --profile paper_main
  python scripts/structural_error_aggregator.py --input results/scorecards.jsonl --outdir results/metrics --log_tuple_sources results/tuple_source_log.tsv --log_sample_n 10
  python scripts/structural_error_aggregator.py --input results/scorecards.jsonl --sanity_check
  python scripts/structural_error_aggregator.py --input path/to/scorecards.jsonl --export_triptych_table derived/tables/triptych_table.tsv --triptych_sample_n 0 --triptych_include_text 1 --triptych_include_debug 0 --export_triptych_risk_details derived/tables/triptych_risk_details.jsonl
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Ensure project root is on path when run as script (e.g. python scripts/structural_error_aggregator.py)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from metrics.eval_tuple import (
    final_aspects_from_final_tuples,
    gold_implicit_polarities_from_tuples,
    gold_tuple_set_from_record,
    normalize_for_eval,
    normalize_polarity,
    precision_recall_f1_implicit_only,
    precision_recall_f1_tuple,
    pred_valid_polarities_from_tuples,
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


def _split_gold_explicit_implicit(
    gold: Set[Tuple[str, str, str]],
) -> Tuple[Set[Tuple[str, str, str]], Set[Tuple[str, str, str]]]:
    """Split gold into explicit (aspect_term non-empty after norm) and implicit (aspect_term empty)."""
    explicit: Set[Tuple[str, str, str]] = set()
    implicit: Set[Tuple[str, str, str]] = set()
    for (a, t, p) in gold:
        tn = normalize_for_eval((t or "").strip())
        if tn:
            explicit.add((a, t, p))
        else:
            implicit.add((a, t, p))
    return explicit, implicit


def _record_has_forbidden_neutral_fallback(record: Dict[str, Any]) -> bool:
    """True if any final tuple item has missing/empty polarity (evaluator would use neutral default → forbidden fallback)."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    for lst_key in ("final_tuples", "final_aspects"):
        lst = final_result.get(lst_key)
        if not isinstance(lst, list):
            continue
        for it in lst:
            if not it or not isinstance(it, dict):
                continue
            p = (it.get("polarity") or it.get("label") or "").strip()
            if not p:
                return True
    return False


def _record_parse_failed(record: Dict[str, Any]) -> bool:
    """True if record has parse_failed, generate_failed, or ATSA/parse error in runtime/trace."""
    flags = record.get("flags") or (record.get("runtime") or {}).get("flags") or {}
    if flags.get("parse_failed") or flags.get("generate_failed"):
        return True
    runtime = record.get("runtime") or {}
    if (runtime.get("error") or "").strip():
        return True
    trace = _get_process_trace(record)
    for entry in trace or []:
        notes = entry.get("notes") or ""
        if isinstance(notes, str) and ("atsa_parse" in notes or "json_parse" in notes):
            return True
    return False


def _aspect_term_text(it: dict) -> str:
    """Get aspect surface-form text from item (aspect_term.term or string)."""
    at = it.get("aspect_term")
    if isinstance(at, dict) and at.get("term") is not None:
        return (at.get("term") or "").strip()
    if isinstance(at, str):
        return at.strip()
    return ((it.get("opinion_term") or {}).get("term") or "").strip()


def _tuples_from_list_of_dicts(items: Any) -> Set[Tuple[str, str, str]]:
    """Convert list of {aspect_ref?, aspect_term, polarity} dicts to set of EvalTuple.
    Pipeline uses aspect_term only. Polarity/term normalized for eval (normalize_polarity, normalize_for_eval)."""
    if not items or not isinstance(items, (list, tuple)):
        return set()
    out: Set[Tuple[str, str, str]] = set()
    for it in items:
        if not it or not isinstance(it, dict):
            continue
        a = normalize_for_eval((it.get("aspect_ref") or "").strip())
        t = _aspect_term_text(it)
        t = normalize_for_eval(t) if t else ""
        p = normalize_polarity(it.get("polarity") or it.get("label"))
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


# Canonical source names for tuple extraction (eval path logging)
FINAL_SOURCE_FINAL_TUPLES = "final_tuples"
FINAL_SOURCE_FINAL_ASPECTS = "final_aspects"
FINAL_SOURCE_INPUTS_ASPECT_SENTIMENTS = "inputs.aspect_sentiments"
STAGE1_SOURCE_STAGE1_TUPLES = "stage1_tuples"
STAGE1_SOURCE_TRACE_ATSA = "trace_atsa"
STAGE1_SOURCE_FALLBACK_FINAL = "final_tuples"
GOLD_SOURCE_INPUTS = "inputs.gold_tuples"


def _extract_final_tuples_with_source(record: Dict[str, Any]) -> Tuple[Set[Tuple[str, str, str]], str, int]:
    """
    CONTRACT-AGG-1: When final_result.final_tuples exists and is non-empty, use it only (no other source).
    Fallback only when final_tuples is empty or missing → final_aspects, then inputs. On fallback: log + caller counts.
    """
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    text_id = (record.get("meta") or {}).get("text_id") or (record.get("runtime") or {}).get("uid") or ""

    # CONTRACT-AGG-1: final_tuples present and non-empty → use only; do not use final_aspects/inputs
    final_tuples = final_result.get("final_tuples")
    if final_tuples and isinstance(final_tuples, list) and len(final_tuples) > 0:
        out = tuples_from_list(final_tuples)
        if out:
            return (out, FINAL_SOURCE_FINAL_TUPLES, len(out))

    # Fallback: final_tuples empty or missing
    final_aspects = final_result.get("final_aspects")
    if final_aspects and len(final_aspects) > 0:
        out = tuples_from_list(final_aspects)
        if out:
            logger.warning(
                "AGG_FALLBACK_USED",
                extra={"text_id": text_id, "source": FINAL_SOURCE_FINAL_ASPECTS, "reason": "final_tuples_empty_or_missing"},
            )
            return (out, FINAL_SOURCE_FINAL_ASPECTS, len(out))
    inputs = record.get("inputs") or {}
    sents = inputs.get("aspect_sentiments")
    if sents:
        out = tuples_from_list(sents)
        out = {(a, t, p) for (a, t, p) in out if (t or "").strip()}
        if out:
            logger.warning(
                "AGG_FALLBACK_USED",
                extra={"text_id": text_id, "source": FINAL_SOURCE_INPUTS_ASPECT_SENTIMENTS, "reason": "final_tuples_and_final_aspects_empty_or_missing"},
            )
            return (out, FINAL_SOURCE_INPUTS_ASPECT_SENTIMENTS, len(out))
    return (set(), FINAL_SOURCE_INPUTS_ASPECT_SENTIMENTS, 0)


def _extract_final_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    """Prefer final_result.final_tuples when present; else final_aspects or inputs.aspect_sentiments."""
    s, _, _ = _extract_final_tuples_with_source(record)
    return s


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


def _extract_stage1_tuples_with_source(record: Dict[str, Any]) -> Tuple[Set[Tuple[str, str, str]], str, int]:
    """Return (tuple_set, source_name, n). source_name: stage1_tuples | trace_atsa | final_tuples (fallback)."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    stage1_tuples = final_result.get("stage1_tuples")
    if stage1_tuples and isinstance(stage1_tuples, list):
        out = _tuples_from_list_of_dicts(stage1_tuples)
        if out:
            return (out, STAGE1_SOURCE_STAGE1_TUPLES, len(out))
    trace = _get_process_trace(record)
    for entry in trace:
        if (entry.get("stage") or "").lower() == "stage1" and (entry.get("agent") or "").lower() == "atsa":
            sents = (entry.get("output") or {}).get("aspect_sentiments")
            if sents:
                out = tuples_from_list(sents)
                return (out, STAGE1_SOURCE_TRACE_ATSA, len(out))
    s, src, n = _extract_final_tuples_with_source(record)
    return (s, STAGE1_SOURCE_FALLBACK_FINAL, n)


def _extract_stage1_tuples(record: Dict[str, Any]) -> Set[Tuple[str, str, str]]:
    """Prefer final_result.stage1_tuples when present; else process_trace Stage1 ATSA aspect_sentiments."""
    s, _, _ = _extract_stage1_tuples_with_source(record)
    return s


def _gold_tuple_source(record: Dict[str, Any]) -> str:
    """Which gold source was used: inputs.gold_tuples (or top-level gold_tuples)."""
    inputs = record.get("inputs") or {}
    if inputs.get("gold_tuples"):
        return GOLD_SOURCE_INPUTS
    if record.get("gold_tuples"):
        return "gold_tuples"
    return "gold_triplets" if record.get("gold_triplets") or (inputs.get("gold_triplets")) else ""


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
    """When gold tuples exist: tuple_f1_s1, tuple_f1_s2, delta_f1, fix_rate, break_rate, net_gain, N_gold.
    Gold denominator split: N_gold_total, N_gold_explicit, N_gold_implicit (definition).
    F1 split: tuple_f1_s2_overall (reference), tuple_f1_s2_explicit_only (primary quality metric).
    N_pred_*: rows where pred came from that source; N_pred_used: total pred tuple count used in F1.
    gold_available = (N_gold_total_pairs > 0); N_gold_* and N_pred_* are always computed (not gated).
    F1 matches on (aspect_term, polarity) only. Rows without gold excluded. See docs/absa_tuple_eval.md."""
    out: Dict[str, Any] = {
        "tuple_f1_s1": None, "tuple_f1_s2": None, "tuple_f1_s2_overall": None, "tuple_f1_s2_explicit_only": None,
        "tuple_f1_s2_implicit_only": None,
        "tuple_f1_s2_raw": None, "tuple_f1_s2_after_rep": None,
        "delta_f1": None,
        "triplet_f1_s1": None, "triplet_f1_s2": None,
        "fix_rate": None, "break_rate": None, "net_gain": None,
        "N_gold": 0, "N_gold_total": 0, "N_gold_explicit": 0, "N_gold_implicit": 0,
        "gold_available": False,
        "N_pred_final_tuples": 0, "N_pred_final_aspects": 0, "N_pred_inputs_aspect_sentiments": 0,
        "N_pred_used": 0,
        "N_agg_fallback_used": 0,  # CONTRACT-AGG-1: rows where final_tuples was empty/missing and we used final_aspects or inputs
        "implicit_gold_sample_n": 0, "implicit_invalid_sample_n": 0,
        "implicit_invalid_pred_rate": None,
    }
    # Always: gold pair counts and pred counts from all rows (not gated)
    n_gold_total_pairs = 0
    n_gold_explicit_pairs = 0
    n_gold_implicit_pairs = 0
    n_pred_final_tuples = n_pred_final_aspects = n_pred_inputs = 0
    n_pred_used_total = 0
    n_agg_fallback_used = 0
    for r in rows:
        gold = _extract_gold_tuples(r)
        if gold is not None and len(gold) > 0:
            ge, gi = _split_gold_explicit_implicit(gold)
            n_gold_total_pairs += len(gold)
            n_gold_explicit_pairs += len(ge)
            n_gold_implicit_pairs += len(gi)
        s2, pred_source, pred_n = _extract_final_tuples_with_source(r)
        if pred_source == FINAL_SOURCE_FINAL_TUPLES:
            n_pred_final_tuples += 1
        elif pred_source == FINAL_SOURCE_FINAL_ASPECTS:
            n_pred_final_aspects += 1
            n_agg_fallback_used += 1
        else:
            n_pred_inputs += 1
            n_agg_fallback_used += 1
        n_pred_used_total += pred_n if s2 else 0
    out["N_gold_total_pairs"] = n_gold_total_pairs
    out["N_gold_explicit_pairs"] = n_gold_explicit_pairs
    out["N_gold_implicit_pairs"] = n_gold_implicit_pairs
    out["N_pred_final_tuples"] = n_pred_final_tuples
    out["N_pred_final_aspects"] = n_pred_final_aspects
    out["N_pred_inputs_aspect_sentiments"] = n_pred_inputs
    out["N_pred_used"] = n_pred_used_total
    out["N_agg_fallback_used"] = n_agg_fallback_used
    gold_available = n_gold_total_pairs > 0
    out["gold_available"] = gold_available
    if not gold_available:
        out["N_gold"] = 0
        out["N_gold_total"] = 0
        out["N_gold_explicit"] = 0
        out["N_gold_implicit"] = 0
        print("[aggregator] gold_available=False, skipping F1 (no gold pairs in scorecards).", file=sys.stderr)
        return out

    rows_with_gold = [(r, _extract_gold_tuples(r)) for r in rows if _extract_gold_tuples(r) is not None and len(_extract_gold_tuples(r)) > 0]
    if not rows_with_gold:
        out["N_gold"] = 0
        out["N_gold_total"] = 0
        out["N_gold_explicit"] = 0
        out["N_gold_implicit"] = 0
        return out
    N = len(rows_with_gold)
    out["N_gold"] = N
    out["N_gold_total"] = N

    n_gold_explicit = 0
    n_gold_implicit = 0
    f1_s1_list: List[float] = []
    f1_s2_list: List[float] = []
    f1_s2_raw_list: List[float] = []
    f1_s2_after_rep_list: List[float] = []
    f1_s2_explicit_only_list: List[float] = []
    f1_s2_implicit_only_list: List[float] = []
    n_fix = n_break = n_still = n_keep = 0
    n_implicit_gold_samples = 0
    n_implicit_invalid_samples = 0
    for record, gold in rows_with_gold:
        gold = gold or set()
        gold_explicit, gold_implicit = _split_gold_explicit_implicit(gold)
        if gold_explicit:
            n_gold_explicit += 1
        if gold_implicit:
            n_gold_implicit += 1

        s1 = _extract_stage1_tuples(record)
        s2 = _extract_final_tuples(record)
        s2_after_rep = select_representative_tuples(record)
        _, _, f1_1 = precision_recall_f1_tuple(gold, s1)
        _, _, f1_2 = precision_recall_f1_tuple(gold, s2)
        _, _, f1_2_ar = precision_recall_f1_tuple(gold, s2_after_rep)
        f1_s1_list.append(f1_1)
        f1_s2_list.append(f1_2)
        f1_s2_raw_list.append(f1_2)
        f1_s2_after_rep_list.append(f1_2_ar)
        if gold_explicit:
            _, _, f1_2_explicit = precision_recall_f1_tuple(gold_explicit, s2)
            f1_s2_explicit_only_list.append(f1_2_explicit)

        # Implicit-only F1 and invalid rate (sample-level)
        gold_implicit_pols = gold_implicit_polarities_from_tuples(gold)
        pred_valid_pols, _ = pred_valid_polarities_from_tuples(s2)
        if gold_implicit_pols:
            n_implicit_gold_samples += 1
            _, _, f1_implicit = precision_recall_f1_implicit_only(gold_implicit_pols, pred_valid_pols)
            f1_s2_implicit_only_list.append(f1_implicit)
            parse_fail = _record_parse_failed(record)
            forbidden_fallback = _record_has_forbidden_neutral_fallback(record)
            invalid_implicit = len(pred_valid_pols) == 0 or parse_fail or forbidden_fallback
            if invalid_implicit:
                n_implicit_invalid_samples += 1

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
        out["tuple_f1_s2_overall"] = out["tuple_f1_s2"]
    if f1_s2_explicit_only_list:
        out["tuple_f1_s2_explicit_only"] = sum(f1_s2_explicit_only_list) / len(f1_s2_explicit_only_list)
    if f1_s2_implicit_only_list:
        out["tuple_f1_s2_implicit_only"] = sum(f1_s2_implicit_only_list) / len(f1_s2_implicit_only_list)
    if f1_s2_raw_list:
        out["tuple_f1_s2_raw"] = sum(f1_s2_raw_list) / len(f1_s2_raw_list)
    if f1_s2_after_rep_list:
        out["tuple_f1_s2_after_rep"] = sum(f1_s2_after_rep_list) / len(f1_s2_after_rep_list)
    if f1_s1_list and f1_s2_list:
        out["delta_f1"] = (out["tuple_f1_s2"] or 0.0) - (out["tuple_f1_s1"] or 0.0)
    need_fix = n_fix + n_still
    out["fix_rate"] = _rate(n_fix, need_fix) if need_fix else None
    keep_break = n_break + n_keep
    out["break_rate"] = _rate(n_break, keep_break) if keep_break else None
    out["net_gain"] = (n_fix - n_break) / N if N else None
    out["implicit_gold_sample_n"] = n_implicit_gold_samples
    out["implicit_invalid_sample_n"] = n_implicit_invalid_samples
    out["implicit_invalid_pred_rate"] = _rate(n_implicit_invalid_samples, n_implicit_gold_samples) if n_implicit_gold_samples else 0.0
    out["N_gold_explicit"] = n_gold_explicit
    out["N_gold_implicit"] = n_gold_implicit
    out["N_gold_total_pairs"] = n_gold_total_pairs
    out["N_gold_explicit_pairs"] = n_gold_explicit_pairs
    out["N_gold_implicit_pairs"] = n_gold_implicit_pairs
    out["N_pred_final_tuples"] = n_pred_final_tuples
    out["N_pred_final_aspects"] = n_pred_final_aspects
    out["N_pred_inputs_aspect_sentiments"] = n_pred_inputs
    out["N_pred_used"] = n_pred_used_total
    out["N_agg_fallback_used"] = n_agg_fallback_used
    return out


def count_severe_polarity_error_L3(record: Dict[str, Any]) -> int:
    """L3: aspect boundary matches gold, polarity only mismatch (conservative; L4/L5 excluded).
    Returns number of (gold aspect_term, pred polarity) pairs where aspect matches but polarity differs."""
    gold = _extract_gold_tuples(record)
    if not gold:
        return 0
    final = _extract_final_tuples(record)
    gold_by_term: Dict[str, str] = {}
    for (_a, term, pol) in gold:
        t = normalize_for_eval((term or "").strip())
        if t != "" or (_a or "").strip():
            gold_by_term[t] = normalize_polarity(pol)
    count = 0
    for (_a, term_f, pol_f) in final:
        tn = normalize_for_eval((term_f or "").strip())
        if tn not in gold_by_term:
            continue
        if normalize_polarity(pol_f) != gold_by_term[tn]:
            count += 1
    return count


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
    """Input span에 매칭되지 않는 aspect 비율 소스: ate_score filtered drop or ate.hallucination_flag. (Stage1 raw; legacy.)"""
    ate = record.get("ate") or record.get("ate_score") or {}
    flags = record.get("flags") or {}
    if record.get("ate", {}).get("hallucination_flag") is True:
        return True
    filtered = (record.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
    drops = [f for f in filtered if f.get("action") == "drop"]
    return len(drops) > 0 and len(filtered) > 0


def has_hallucinated_aspect_final(record: Dict[str, Any]) -> bool:
    """PJ1/Action2: Final(patched_stage2 or final) 기준 — any final aspect term not a substring of input_text."""
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    meta = parsed.get("meta") or record.get("meta") or {}
    input_text = (meta.get("input_text") or "").strip()
    final_result = parsed.get("final_result") or {}
    final_tuples = final_result.get("final_tuples")
    if final_tuples and isinstance(final_tuples, list):
        for it in final_tuples:
            if not it or not isinstance(it, dict):
                continue
            term = (_aspect_term_text(it) or "").strip()
            if not term:
                continue
            if term not in input_text:
                return True
    final_aspects = final_result.get("final_aspects") or []
    for it in final_aspects:
        if not isinstance(it, dict):
            continue
        term = _aspect_term_text(it.get("aspect_term") or it) if isinstance(it.get("aspect_term"), dict) else (it.get("term") or "").strip()
        if not term:
            continue
        if term not in input_text:
            return True
    return False


def count_hallucination_types_final(record: Dict[str, Any]) -> Dict[str, bool]:
    """PJ1/Action2: Final 기준 — drop_reason from final_tuples if present; else alignment_failure = has_hallucinated_aspect_final."""
    out = {
        DROP_REASON_ALIGNMENT_FAILURE: False,
        DROP_REASON_FILTER_REJECTION: False,
        DROP_REASON_SEMANTIC_HALLUCINATION: False,
    }
    if has_hallucinated_aspect_final(record):
        out[DROP_REASON_ALIGNMENT_FAILURE] = True
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    final_tuples = final_result.get("final_tuples") or []
    for it in final_tuples or []:
        if not isinstance(it, dict):
            continue
        reason = (it.get("drop_reason") or "").strip()
        if reason == DROP_REASON_ALIGNMENT_FAILURE:
            out[DROP_REASON_ALIGNMENT_FAILURE] = True
        elif reason == DROP_REASON_FILTER_REJECTION:
            out[DROP_REASON_FILTER_REJECTION] = True
        elif reason == DROP_REASON_SEMANTIC_HALLUCINATION:
            out[DROP_REASON_SEMANTIC_HALLUCINATION] = True
    return out


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


def has_polarity_conflict_raw(record: Dict[str, Any]) -> bool:
    """Conflict without representative selection: same aspect_term with ≥2 distinct polarities (raw final tuples)."""
    raw = _get_final_tuples_raw(record)
    if not raw:
        return False
    by_aspect: Dict[str, Set[str]] = {}
    for it in raw:
        key = (it.get("aspect_term_norm") or "").strip()
        pol = it.get("polarity_norm") or "neutral"
        by_aspect.setdefault(key, set()).add(pol)
    return any(len(pols) > 1 for pols in by_aspect.values())


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


def has_same_aspect_polarity_conflict(record: Dict[str, Any]) -> bool:
    """Same-aspect polarity conflict (after representative selection). Alias for has_polarity_conflict_after_representative."""
    return has_polarity_conflict_after_representative(record)


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
    """(has_guided_change, has_unguided_drift).
    CR: guided_by_review counts as guided; unguided = change_type=unguided only."""
    delta = record.get("stage_delta") or {}
    changed = delta.get("changed", False)
    change_type = (delta.get("change_type") or "none").lower()
    guided = changed and change_type in ("guided", "guided_by_review")
    unguided = changed and change_type == "unguided"
    return guided, unguided


def _cr_has_review_actions(record: Dict[str, Any]) -> bool:
    """True if analysis_flags.review_actions has ≥1 item (CR protocol)."""
    parsed = (record.get("runtime") or {}).get("parsed_output") or {}
    actions = (parsed.get("analysis_flags") or {}).get("review_actions") or []
    return bool(actions)


def _cr_has_arb_intervention(record: Dict[str, Any]) -> bool:
    """True if analysis_flags.arb_actions has ≥1 item (CR protocol)."""
    parsed = (record.get("runtime") or {}).get("parsed_output") or {}
    actions = (parsed.get("analysis_flags") or {}).get("arb_actions") or []
    return bool(actions)


def _cr_is_guided_by_review(record: Dict[str, Any]) -> bool:
    """True if change_type=guided_by_review (CR protocol)."""
    ct = (record.get("stage_delta") or {}).get("change_type") or ""
    return ct == "guided_by_review"


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


def outcome_residual_risk(record: Dict[str, Any]) -> bool:
    """True if the final output has any observable structural quality risk (outcome-based).
    Union of: Validator S2 risk, polarity conflict after representative, unsupported polarity, negation/contrast risks.
    Does not include process-only flags (e.g. alignment_failure>=2, explicit_failure)."""
    if count_stage2_risks(record) > 0:
        return True
    if has_polarity_conflict_after_representative(record):
        return True
    if rq1_grounding_bucket(record) == RQ1_BUCKET_UNSUPPORTED:
        return True
    if count_negation_contrast_risks(record) > 0:
        return True
    return False


def stage1_risk_severity(record: Dict[str, Any]) -> float:
    """Stage1 structural_risks severity 가중합: high=3, mid=2, low=1 (risk_before_sum per sample)."""
    weight = {"high": 3.0, "mid": 2.0, "low": 1.0}
    total = 0.0
    for stage_block in record.get("validator") or []:
        if (stage_block.get("stage") or "").lower() != "stage1":
            continue
        for r in (stage_block.get("structural_risks") or []):
            total += weight.get((r.get("severity") or "mid").lower(), 2.0)
    return total


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


def aggregate_single_run(
    rows: List[Dict[str, Any]],
    profile_filter: Optional[str] = None,
    override_gate_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Aggregate metrics over a list of scorecards (single run or already filtered)."""
    if profile_filter:
        rows = [r for r in rows if (r.get("profile") or r.get("meta", {}).get("profile")) == profile_filter]
    N = len(rows)
    if N == 0:
        return {"n": 0}

    # Action2/PJ1: hallucination and alignment from final (patched_stage2 or final), not stage1 raw
    hallucinated = sum(1 for r in rows if has_hallucinated_aspect_final(r))
    n_align_fail = sum(1 for r in rows if count_hallucination_types_final(r).get(DROP_REASON_ALIGNMENT_FAILURE))
    n_filter_rej = sum(1 for r in rows if count_hallucination_types_final(r).get(DROP_REASON_FILTER_REJECTION))
    n_semantic_hal = sum(1 for r in rows if count_hallucination_types_final(r).get(DROP_REASON_SEMANTIC_HALLUCINATION))
    unsupported = sum(1 for r in rows if has_unsupported_polarity(r))
    # RQ1 one-hot grounding buckets (exactly one per sample)
    n_implicit = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_IMPLICIT)
    n_explicit = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_EXPLICIT)
    n_explicit_failure = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_EXPLICIT_FAILURE)
    n_unsupported_rq1 = sum(1 for r in rows if rq1_grounding_bucket(r) == RQ1_BUCKET_UNSUPPORTED)
    polarity_conflict_raw = sum(1 for r in rows if has_polarity_conflict_raw(r))
    polarity_conflict = sum(1 for r in rows if has_polarity_conflict_after_representative(r))
    stage_mismatch = sum(1 for r in rows if has_stage_mismatch(r))
    negation_contrast_risks = sum(count_negation_contrast_risks(r) for r in rows)
    guided_changes = sum(1 for r in rows if stage_delta_guided_unguided(r)[0])
    unguided_drifts = sum(1 for r in rows if stage_delta_guided_unguided(r)[1])
    all_changes = sum(1 for r in rows if (r.get("stage_delta") or {}).get("changed", False))
    # CR process metrics (conflict_review_v1)
    n_review_action = sum(1 for r in rows if _cr_has_review_actions(r))
    n_arb_intervention = sum(1 for r in rows if _cr_has_arb_intervention(r))
    n_guided_by_review = sum(1 for r in rows if _cr_is_guided_by_review(r))
    # Action3: "변화가 있었을 때만" 안정성 지표 — changed_samples_rate, changed_and_improved_rate, changed_and_degraded_rate
    n_changed_improved = sum(
        1 for r in rows
        if (r.get("stage_delta") or {}).get("changed") and _row_delta_f1(r) is not None and _row_delta_f1(r) > 0
    )
    n_changed_degraded = sum(
        1 for r in rows
        if (r.get("stage_delta") or {}).get("changed") and _row_delta_f1(r) is not None and _row_delta_f1(r) < 0
    )
    changed_samples_rate = _rate(all_changes, N)
    changed_and_improved_rate = _rate(n_changed_improved, all_changes) if all_changes else None
    changed_and_degraded_rate = _rate(n_changed_degraded, all_changes) if all_changes else None
    risk_s1 = sum(count_stage1_risks(r) for r in rows)
    risk_s2 = sum(count_stage2_risks(r) for r in rows)
    resolved = risk_s1 - risk_s2  # simplified: residual risk count decrease
    residual_sev = sum(residual_risk_severity(r) for r in rows)
    risk_before_sev_sum = sum(stage1_risk_severity(r) for r in rows)
    risk_after_sev_sum = sum(residual_risk_severity(r) for r in rows)
    risk_delta_sev_sum = sum(residual_risk_severity(r) - stage1_risk_severity(r) for r in rows)
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
    # RQ1: validator_residual_risk_rate = 샘플 중 Stage2 Validator risk가 남아 있는 비율 (Validator 기준만)
    n_residual_risk = sum(1 for r in rows if count_stage2_risks(r) > 0)
    validator_residual_risk_rate = _rate(n_residual_risk, N)

    # Outcome 기준: 최종 출력에서 관찰되는 구조적 리스크 1건 이상이면 True
    n_outcome_residual = sum(1 for r in rows if outcome_residual_risk(r))
    outcome_residual_risk_rate = _rate(n_outcome_residual, N)

    # RQ3 extended: validator_clear_rate (denom = stage1_structural_risk True, num = resolved by stage2; Validator 기준)
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
    validator_clear_rate = _rate(n_resolved_structural, n_stage1_structural_risk) if n_stage1_structural_risk else 0.0
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
    # Skip reason granularity (Discussion: why conflict skip?)
    skip_reasons_agg: Dict[str, int] = {"action_ambiguity": 0, "L3_conservative": 0, "implicit_soft_only": 0, "low_confidence": 0, "contradictory_memory": 0}
    for r in rows:
        reasons = (r.get("meta") or {}).get("debate_override_skip_reasons") or {}
        if isinstance(reasons, dict):
            for k in list(skip_reasons_agg.keys()):
                skip_reasons_agg[k] += int(reasons.get(k) or 0)

    # Override subset metrics: applied vs skipped_conflict (include Stage2 adoption decision override_applied bool)
    def _row_override_applied(r: Dict[str, Any]) -> bool:
        o = _get_override_stats(r)
        return o.get("override_applied") is True or int(o.get("applied") or 0) > 0
    rows_applied = [r for r in rows if _row_override_applied(r)]
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
    # Stage2 adoption override_reason counts (for debugging / paper)
    override_reason_counts: Dict[str, int] = {"risk_resolved": 0, "debate_action": 0, "grounding_improved": 0, "conflict_blocked": 0, "low_signal": 0, "ev_below_threshold": 0}
    for r in rows:
        o = _get_override_stats(r)
        reason = (o.get("override_reason") or "").strip()
        if reason in override_reason_counts:
            override_reason_counts[reason] += 1
    # Override outcome decomposition: applied+adopted, applied+ev_rejected, applied+adopted+degraded
    n_applied_and_adopted = sum(1 for r in rows if _get_override_stats(r).get("override_effect_applied") is True)
    n_ev_rejected = sum(
        1 for r in rows
        if _row_override_applied(r)
        and (r.get("meta") or {}).get("adopt_decision") == "not_adopted"
        and (r.get("meta") or {}).get("adopt_reason") == "ev_below_threshold"
    )
    n_override_harm = sum(
        1 for r in rows
        if _get_override_stats(r).get("override_effect_applied") is True
        and (r.get("stage_delta") or {}).get("changed")
        and _row_delta_f1(r) is not None
        and _row_delta_f1(r) < 0
    )
    override_applied_and_adopted_rate = _rate(n_applied_and_adopted, N)
    override_applied_but_ev_rejected_rate = _rate(n_ev_rejected, N)
    override_harm_rate = _rate(n_override_harm, n_applied_and_adopted) if n_applied_and_adopted else None
    # C: memory gate coverage — memory_used_rate (retrieved>0 AND exposed_to_debate), injection_trigger_reason_counts, memory_used_changed_rate
    n_retrieved_and_exposed = 0
    n_injected = 0
    n_injected_and_changed = 0
    injection_trigger_counts: Dict[str, int] = {"conflict": 0, "validator": 0, "alignment": 0, "explicit_grounding_failure": 0}
    for r in rows:
        mem = r.get("memory") or (r.get("meta") or {}).get("memory") or {}
        retrieved_n = int(mem.get("retrieved_k") or 0) or len(mem.get("retrieved_ids") or [])
        exposed = bool(mem.get("exposed_to_debate", False))
        inj_chars = int(mem.get("prompt_injection_chars") or 0)
        if retrieved_n > 0 and exposed:
            n_retrieved_and_exposed += 1
        if exposed and inj_chars > 0:
            n_injected += 1
            changed = bool((r.get("stage_delta") or {}).get("changed", False))
            if changed:
                n_injected_and_changed += 1
            reason = (mem.get("injection_trigger_reason") or "").strip().lower()
            if reason in injection_trigger_counts:
                injection_trigger_counts[reason] += 1
    memory_used_rate = _rate(n_retrieved_and_exposed, N)
    memory_used_changed_rate = _rate(n_injected_and_changed, n_injected) if n_injected else None
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
        "polarity_conflict_rate_raw": _rate(polarity_conflict_raw, aspect_conflict_denom),
        "polarity_conflict_rate": _rate(polarity_conflict, aspect_conflict_denom),
        "polarity_conflict_rate_after_rep": _rate(polarity_conflict, aspect_conflict_denom),
        "stage_mismatch_rate": _rate(stage_mismatch, N),
        "negation_contrast_failure_rate": _rate(negation_contrast_risks, N) if N else 0.0,
        "guided_change_rate": _rate(guided_changes, all_changes) if all_changes else 0.0,
        "unguided_drift_rate": _rate(unguided_drifts, N),
        "changed_samples_rate": changed_samples_rate,
        "pre_to_post_change_rate": changed_samples_rate,
        "review_action_rate": _rate(n_review_action, N),
        "arb_intervention_rate": _rate(n_arb_intervention, N),
        "guided_by_review_rate": _rate(n_guided_by_review, all_changes) if all_changes else 0.0,
        "changed_and_improved_rate": changed_and_improved_rate,
        "changed_and_degraded_rate": changed_and_degraded_rate,
        "validator_clear_rate": validator_clear_rate,
        "validator_residual_risk_rate": validator_residual_risk_rate,
        "outcome_residual_risk_rate": outcome_residual_risk_rate,
        "risk_resolution_rate_legacy": risk_resolution_rate_legacy,
        "risk_flagged_rate": risk_flagged_rate,
        # Deprecated aliases (same values); use validator_* / outcome_* for clarity.
        "risk_resolution_rate": validator_clear_rate,
        "residual_risk_rate": validator_residual_risk_rate,
        "risk_affected_change_rate": risk_affected_change_rate,
        "risk_resolved_with_change_rate": risk_resolved_with_change_rate,
        "risk_resolved_without_change_rate": risk_resolved_without_change_rate,
        "ignored_proposal_rate": ignored_proposal_rate,
        "residual_risk_severity_sum": residual_sev,
        "risk_before_sum": risk_before_sev_sum,
        "risk_after_sum": risk_after_sev_sum,
        "risk_delta_sum": risk_delta_sev_sum,
        "risk_before_sum_mean": risk_before_sev_sum / N if N else 0.0,
        "risk_after_sum_mean": risk_after_sev_sum / N if N else 0.0,
        "risk_delta_sum_mean": risk_delta_sev_sum / N if N else 0.0,
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
        "override_skipped_conflict_action_ambiguity": skip_reasons_agg.get("action_ambiguity", 0),
        "override_skipped_conflict_L3_conservative": skip_reasons_agg.get("L3_conservative", 0),
        "override_skipped_conflict_implicit_soft_only": skip_reasons_agg.get("implicit_soft_only", 0),
        "override_skipped_conflict_low_confidence": skip_reasons_agg.get("low_confidence", 0),
        "override_skipped_conflict_contradictory_memory": skip_reasons_agg.get("contradictory_memory", 0),
        "memory_used_rate": memory_used_rate,
        "memory_used_changed_rate": memory_used_changed_rate,
        "injection_trigger_conflict_n": injection_trigger_counts.get("conflict", 0),
        "injection_trigger_validator_n": injection_trigger_counts.get("validator", 0),
        "injection_trigger_alignment_n": injection_trigger_counts.get("alignment", 0),
        "injection_trigger_explicit_grounding_failure_n": injection_trigger_counts.get("explicit_grounding_failure", 0),
        "override_reason_risk_resolved_n": override_reason_counts.get("risk_resolved", 0),
        "override_reason_debate_action_n": override_reason_counts.get("debate_action", 0),
        "override_reason_grounding_improved_n": override_reason_counts.get("grounding_improved", 0),
        "override_reason_conflict_blocked_n": override_reason_counts.get("conflict_blocked", 0),
        "override_reason_low_signal_n": override_reason_counts.get("low_signal", 0),
        "override_reason_ev_below_threshold_n": override_reason_counts.get("ev_below_threshold", 0),
        "override_applied_and_adopted_rate": override_applied_and_adopted_rate,
        "override_applied_but_ev_rejected_rate": override_applied_but_ev_rejected_rate,
        "override_harm_rate": override_harm_rate,
    }
    if override_gate_summary is not None:
        if "override_hint_invalid_total" in override_gate_summary:
            out["override_hint_invalid_total"] = override_gate_summary["override_hint_invalid_total"]
        if override_gate_summary.get("override_hint_invalid_rate") is not None:
            out["override_hint_invalid_rate"] = override_gate_summary["override_hint_invalid_rate"]
        if "override_hint_repair_total" in override_gate_summary:
            out["override_hint_repair_total"] = override_gate_summary["override_hint_repair_total"]
    # Polarity typo policy: polarity_repair_rate, polarity_invalid_rate (whitelist/repair 1~2 vs invalid)
    polarity_repair_n = sum(int((r.get("meta") or {}).get("polarity_repair_count", 0) or 0) for r in rows)
    polarity_invalid_n = sum(int((r.get("meta") or {}).get("polarity_invalid_count", 0) or 0) for r in rows)
    if override_gate_summary is not None:
        polarity_repair_n += int(override_gate_summary.get("override_hint_repair_total", 0) or 0)
        polarity_invalid_n += int(override_gate_summary.get("override_hint_invalid_total", 0) or 0)
    denom = polarity_repair_n + polarity_invalid_n
    out["polarity_repair_n"] = polarity_repair_n
    out["polarity_invalid_n"] = polarity_invalid_n
    out["polarity_repair_rate"] = _rate(polarity_repair_n, denom) if denom else None
    out["polarity_invalid_rate"] = _rate(polarity_invalid_n, denom) if denom else None
    # Gold-based F1 / correction metrics (for aggregate_seed_metrics mean±std)
    correction = compute_stage2_correction_metrics(rows)
    for k in (
        "tuple_f1_s1", "tuple_f1_s2", "tuple_f1_s2_overall", "tuple_f1_s2_explicit_only", "tuple_f1_s2_implicit_only",
        "tuple_f1_s2_raw", "tuple_f1_s2_after_rep",
        "triplet_f1_s1", "triplet_f1_s2", "delta_f1",
        "fix_rate", "break_rate", "net_gain",
        "N_gold", "N_gold_total", "N_gold_explicit", "N_gold_implicit",
        "N_gold_total_pairs", "N_gold_explicit_pairs", "N_gold_implicit_pairs", "gold_available",
        "N_pred_final_tuples", "N_pred_final_aspects", "N_pred_inputs_aspect_sentiments", "N_pred_used",
        "N_agg_fallback_used",
        "implicit_gold_sample_n", "implicit_invalid_sample_n", "implicit_invalid_pred_rate",
    ):
        if k in correction:
            out[k] = correction[k]
    # Outcome (RQ): Severe Polarity Error L3 — aspect match, polarity mismatch only
    rows_with_gold_list = [r for r in rows if _extract_gold_tuples(r) is not None]
    N_gold = len(rows_with_gold_list)
    severe_L3_count = sum(count_severe_polarity_error_L3(r) for r in rows_with_gold_list)
    out["severe_polarity_error_L3_count"] = severe_L3_count
    out["severe_polarity_error_L3_rate"] = _rate(severe_L3_count, N_gold) if N_gold else None
    # Outcome (RQ): generalized_f1@θ=0.95 (Neveditsin et al. variant; requires embedding+Hungarian — stub)
    out["generalized_f1_theta"] = None
    out["generalized_precision_theta"] = None
    out["generalized_recall_theta"] = None
    # tuple_agreement_rate only in merged (n_trials >= 2); single run leaves None / False
    if "tuple_agreement_rate" not in out:
        out["tuple_agreement_rate"] = None
        out["tuple_agreement_eligible"] = False
    # Metric continuity: eval_semver / eval_policy_hash so reports can explain policy changes
    out["eval_semver"] = _eval_semver()
    out["eval_policy_hash"] = _eval_policy_hash()
    # Drift cause decomposition (stage1_to_final_changed=1 → 4-way tag counts)
    _, drift_summary = _collect_drift_cause_rows(rows)
    n_changed_drift = drift_summary.get("n_changed") or 0
    by_tag = drift_summary.get("by_tag") or {}
    out["drift_cause_n_changed"] = n_changed_drift
    out["drift_cause_stage2_selected_n"] = by_tag.get(DRIFT_CAUSE_STAGE2_SELECTED, 0)
    out["drift_cause_same_stage_tuples_differ_n"] = by_tag.get(DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER, 0)
    out["drift_cause_stage_delta_missing_n"] = by_tag.get(DRIFT_CAUSE_STAGE_DELTA_MISSING, 0)
    out["drift_cause_stage2_selected_rate"] = _rate(by_tag.get(DRIFT_CAUSE_STAGE2_SELECTED, 0), N) if N else None
    out["drift_cause_same_stage_tuples_differ_rate"] = _rate(by_tag.get(DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER, 0), N) if N else None
    out["drift_cause_stage_delta_missing_rate"] = _rate(by_tag.get(DRIFT_CAUSE_STAGE_DELTA_MISSING, 0), N) if N else None
    out["drift_cause_memory_used_changed_n"] = drift_summary.get("memory_used_changed")
    out["drift_cause_memory_unused_changed_n"] = drift_summary.get("memory_unused_changed")
    out["drift_cause_memory_retrieved_changed_n"] = drift_summary.get("memory_retrieved_changed")
    # P3/P4: one pass over triptych rows for drift_any, drift_conflict_relevant, stage2_selected stats
    n_drift_any = 0
    n_drift_conflict_relevant = 0
    n_stage2_selected = 0
    n_stage2_selected_and_pairs_changed = 0
    sum_delta_pairs_given_stage2 = 0
    for r in rows:
        row = _triptych_row(r, include_text=False, include_debug=False)
        if int(row.get("drift_any_change") or 0) == 1:
            n_drift_any += 1
        if int(row.get("drift_conflict_relevant_change") or 0) == 1:
            n_drift_conflict_relevant += 1
        mod_stage = (row.get("moderator_selected_stage") or "").strip().lower()
        changed = int(row.get("stage1_to_final_changed") or 0)
        delta_pairs = int(row.get("delta_pairs_count") or 0)
        if mod_stage == "stage2":
            n_stage2_selected += 1
            sum_delta_pairs_given_stage2 += delta_pairs
            if changed == 1:
                n_stage2_selected_and_pairs_changed += 1
    out["drift_any_change_n"] = n_drift_any
    out["drift_conflict_relevant_change_n"] = n_drift_conflict_relevant
    out["drift_any_change_rate"] = _rate(n_drift_any, N) if N else None
    out["drift_conflict_relevant_change_rate"] = _rate(n_drift_conflict_relevant, N) if N else None
    out["n_stage2_selected"] = n_stage2_selected
    out["n_stage2_selected_and_pairs_changed"] = n_stage2_selected_and_pairs_changed
    out["mean_delta_pairs_count_given_stage2_selected"] = (sum_delta_pairs_given_stage2 / n_stage2_selected) if n_stage2_selected else None
    return out


# Canonical metric keys: Outcome (RQ) first, then Process, then debug/diagnostic.
# Outcome (RQ): paper-claimable only. Process: validator-level diagnostic, not outcome.
CANONICAL_METRIC_KEYS = [
    "n", "profile_filter",
    "eval_semver", "eval_policy_hash",
    # Outcome (RQ) — structural_risk_definition.md / metrics_for_paper.md
    "severe_polarity_error_L3_count", "severe_polarity_error_L3_rate",
    "polarity_conflict_rate_raw", "polarity_conflict_rate", "polarity_conflict_rate_after_rep",
    "generalized_f1_theta", "generalized_precision_theta", "generalized_recall_theta",
    "tuple_agreement_rate", "tuple_agreement_eligible",
    "tuple_f1_s1", "tuple_f1_s2", "tuple_f1_s2_overall", "tuple_f1_s2_explicit_only", "tuple_f1_s2_implicit_only",
    "tuple_f1_s2_raw", "tuple_f1_s2_after_rep",
    "implicit_gold_sample_n", "implicit_invalid_sample_n", "implicit_invalid_pred_rate",
    "triplet_f1_s1", "triplet_f1_s2", "delta_f1", "fix_rate", "break_rate", "net_gain",
    "N_gold", "N_gold_total", "N_gold_explicit", "N_gold_implicit",
    "N_gold_total_pairs", "N_gold_explicit_pairs", "N_gold_implicit_pairs", "gold_available",
    "N_pred_final_tuples", "N_pred_final_aspects", "N_pred_inputs_aspect_sentiments", "N_pred_used",
    "final_pred_source_aspects_path_unused_flag",  # Info: True when N_pred_final_aspects==0 with n>0 (final_aspects 경로 미사용)
    "N_agg_fallback_used",
    "stage_mismatch_rate",
    # Process Control (Internal) — validator-level diagnostic; not interpreted as outcome
    "validator_clear_rate", "validator_residual_risk_rate", "outcome_residual_risk_rate",
    "risk_resolution_rate", "risk_resolution_rate_legacy", "risk_flagged_rate", "residual_risk_rate", "risk_affected_change_rate",
    "risk_resolved_with_change_rate", "risk_resolved_without_change_rate", "ignored_proposal_rate",
    "residual_risk_severity_sum",
    "risk_before_sum", "risk_after_sum", "risk_delta_sum",
    "risk_before_sum_mean", "risk_after_sum_mean", "risk_delta_sum_mean",
    # Other
    "aspect_hallucination_rate", "alignment_failure_rate", "filter_rejection_rate", "semantic_hallucination_rate",
    "implicit_grounding_rate", "explicit_grounding_rate", "explicit_grounding_failure_rate", "unsupported_polarity_rate",
    "legacy_unsupported_polarity_rate",
    "negation_contrast_failure_rate", "guided_change_rate", "unguided_drift_rate",
    "changed_samples_rate", "changed_and_improved_rate", "changed_and_degraded_rate",
    "pre_to_post_change_rate", "review_action_rate", "arb_intervention_rate", "guided_by_review_rate",
    "drift_cause_n_changed", "drift_cause_stage2_selected_n", "drift_cause_same_stage_tuples_differ_n", "drift_cause_stage_delta_missing_n",
    "drift_cause_stage2_selected_rate", "drift_cause_same_stage_tuples_differ_rate", "drift_cause_stage_delta_missing_rate",
    "drift_cause_memory_used_changed_n", "drift_cause_memory_unused_changed_n", "drift_cause_memory_retrieved_changed_n",
    "drift_any_change_n", "drift_conflict_relevant_change_n", "drift_any_change_rate", "drift_conflict_relevant_change_rate",
    "n_stage2_selected", "n_stage2_selected_and_pairs_changed", "mean_delta_pairs_count_given_stage2_selected",
    "parse_generate_failure_rate",
    "hf_polarity_disagreement_rate", "hf_disagreement_coverage_of_structural_risks",
    "conditional_improvement_gain_hf_disagree", "conditional_improvement_gain_hf_agree",
    "debate_mapping_coverage", "debate_mapping_direct_rate", "debate_mapping_fallback_rate", "debate_mapping_none_rate",
    "debate_fail_no_aspects_rate", "debate_fail_no_match_rate", "debate_fail_neutral_stance_rate", "debate_fail_fallback_used_rate",
    "debate_override_applied", "debate_override_skipped_low_signal", "debate_override_skipped_conflict",
    "debate_override_skipped_already_confident", "debate_override_skipped_already_confident_rate",
    "override_applied_n", "override_applied_rate", "override_success_rate", "override_applied_delta_f1_mean", "override_applied_unsupported_polarity_rate", "override_applied_negation_contrast_failure_rate",
    "override_applied_and_adopted_rate", "override_applied_but_ev_rejected_rate", "override_harm_rate",
    "override_hint_invalid_total", "override_hint_repair_total", "override_hint_invalid_rate",
    "polarity_repair_n", "polarity_invalid_n", "polarity_repair_rate", "polarity_invalid_rate",
    "override_skipped_conflict_n", "override_skipped_conflict_delta_f1_mean", "override_skipped_conflict_unsupported_polarity_rate", "override_skipped_conflict_negation_contrast_failure_rate",
    "override_skipped_conflict_action_ambiguity", "override_skipped_conflict_L3_conservative", "override_skipped_conflict_implicit_soft_only",
    "override_skipped_conflict_low_confidence",     "override_skipped_conflict_contradictory_memory",
    "override_reason_risk_resolved_n", "override_reason_debate_action_n", "override_reason_grounding_improved_n",
    "override_reason_conflict_blocked_n", "override_reason_low_signal_n", "override_reason_ev_below_threshold_n",
    "memory_used_rate", "memory_used_changed_rate",
    "injection_trigger_conflict_n", "injection_trigger_validator_n", "injection_trigger_alignment_n", "injection_trigger_explicit_grounding_failure_n",
    "self_consistency_exact", "self_consistency_eligible", "n_trials",
    "risk_set_consistency", "flip_flop_rate", "variance",
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


def aggregate_merged(
    rows: List[Dict[str, Any]],
    profile_filter: Optional[str] = None,
    override_gate_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """When rows are merged (multi-run per case): add self_consistency, risk_set_consistency. Single run: exact=null, eligible=False, n_trials=1."""
    single = aggregate_single_run(rows, profile_filter, override_gate_summary)
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
        single["tuple_agreement_rate"] = None
        single["tuple_agreement_eligible"] = False
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
        single["tuple_agreement_rate"] = None
        single["tuple_agreement_eligible"] = False
        single["variance"] = None
        single["flip_flop_rate"] = None
        return single

    agree_label = 0
    agree_risk = 0
    agree_tuple = 0
    for cid in case_ids:
        group = by_case[cid]
        if len(group) < 2:
            agree_label += 1
            agree_risk += 1
            agree_tuple += 1
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
        # RQ2 Outcome: tuple_agreement_rate — final tuple sets identical across runs
        tuple_sets = [frozenset(_extract_final_tuples(r)) for r in group]
        if len(set(tuple_sets)) == 1:
            agree_tuple += 1
    single["self_consistency_exact"] = _rate(agree_label, len(case_ids))
    single["self_consistency_eligible"] = True
    single["n_trials"] = max_trials
    single["risk_set_consistency"] = _rate(agree_risk, len(case_ids))
    single["tuple_agreement_rate"] = _rate(agree_tuple, len(case_ids))
    single["tuple_agreement_eligible"] = True
    # RQ2: variance = 1 - self_consistency (label variation across runs); flip_flop_rate = disagreement rate proxy
    single["variance"] = 1.0 - single["self_consistency_exact"] if single.get("self_consistency_exact") is not None else None
    single["flip_flop_rate"] = single["variance"]
    return single


def write_tuple_source_log(rows: List[Dict[str, Any]], out_path: Path, sample_n: int = 10) -> None:
    """Per-record tuple extraction path (eval path fixed): stage1_tuple_source, final_tuple_source, gold_tuple_source + N."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    take = len(rows) if sample_n <= 0 else min(sample_n, len(rows))
    lines = ["text_id\tstage1_tuple_source\tN_stage1\tfinal_tuple_source\tN_final\tgold_tuple_source\tN_gold"]
    for r in rows[:take]:
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("case_id") or r.get("text_id") or ""
        _, s1_src, n_s1 = _extract_stage1_tuples_with_source(r)
        _, s2_src, n_s2 = _extract_final_tuples_with_source(r)
        gold = _extract_gold_tuples(r)
        gold_src = _gold_tuple_source(r) if gold is not None else ""
        n_gold = len(gold) if gold else 0
        lines.append(f"{text_id}\t{s1_src}\t{n_s1}\t{s2_src}\t{n_s2}\t{gold_src}\t{n_gold}")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote tuple source log: {out_path} (n={take})")


def compute_tuple_source_coverage(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate tuple source over all rows: final==inputs.aspect_sentiments, stage1==trace_atsa, gold missing."""
    n = len(rows)
    if n == 0:
        return {"n_total": 0, "final_fallback_aspect_sentiments_rate": None, "stage1_fallback_trace_atsa_rate": None, "gold_missing_rate": None}
    n_final_fallback = 0
    n_stage1_trace = 0
    n_gold_missing = 0
    for r in rows:
        _, s1_src, _ = _extract_stage1_tuples_with_source(r)
        _, s2_src, _ = _extract_final_tuples_with_source(r)
        gold = _extract_gold_tuples(r)
        gold_src = _gold_tuple_source(r) if gold is not None else ""
        if s2_src == FINAL_SOURCE_INPUTS_ASPECT_SENTIMENTS:
            n_final_fallback += 1
        if s1_src == STAGE1_SOURCE_TRACE_ATSA:
            n_stage1_trace += 1
        if not gold_src or gold is None:
            n_gold_missing += 1
    return {
        "n_total": n,
        "final_fallback_aspect_sentiments_rate": _rate(n_final_fallback, n),
        "stage1_fallback_trace_atsa_rate": _rate(n_stage1_trace, n),
        "gold_missing_rate": _rate(n_gold_missing, n),
        "final_fallback_aspect_sentiments_count": n_final_fallback,
        "stage1_fallback_trace_atsa_count": n_stage1_trace,
        "gold_missing_count": n_gold_missing,
    }


def write_tuple_source_coverage_csv(rows: List[Dict[str, Any]], out_path: Path, run_id: str = "run") -> None:
    """Write run-level tuple source coverage to derived/diagnostics/tuple_source_coverage.csv."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cov = compute_tuple_source_coverage(rows)
    row = {"run_id": run_id, **cov}
    fieldnames = [
        "run_id", "n_total",
        "final_fallback_aspect_sentiments_rate", "stage1_fallback_trace_atsa_rate", "gold_missing_rate",
        "final_fallback_aspect_sentiments_count", "stage1_fallback_trace_atsa_count", "gold_missing_count",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerow(row)
    print(f"Wrote tuple source coverage: {out_path}")


def _collect_inconsistency_flags(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Triptych/scorecard contradictions: delta_pairs!=0 but changed=0; changed=1 but stage_delta.changed=0; stage2 but no guided/unguided."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        row = _triptych_row(r, include_text=False, include_debug=False)
        text_id = row.get("text_id") or ""
        delta_pairs = row.get("delta_pairs_count") or 0
        changed = row.get("stage1_to_final_changed") or 0
        guided = row.get("guided_change") or 0
        unguided = row.get("unguided_drift") or 0
        mod_stage = (row.get("moderator_selected_stage") or "").strip().lower()
        stage_delta = r.get("stage_delta") or {}
        delta_changed = stage_delta.get("changed")

        risk_res = int(row.get("risk_resolution") or 0)
        s2_structural = int(row.get("stage2_structural_risk") or 0)
        stage2_adopted_but_no_change = bool(stage_delta.get("stage2_adopted_but_no_change"))
        flag_a = False  # delta_pairs != 0 but stage1_to_final_changed == 0
        flag_b = False  # stage1_to_final_changed == 1 but stage_delta.changed == 0 (pairs-based SSOT should remove this)
        flag_c = False  # stage2 but guided==0 and unguided==0, and NOT stage2_adopted_but_no_change (defined case)
        flag_d = False  # risk_resolution==1 but stage2_structural_risk==1 (definition: resolution => S2 clear)
        if delta_pairs != 0 and changed == 0:
            flag_a = True
        if changed == 1 and (delta_changed is False or delta_changed == 0 or delta_changed == "0"):
            flag_b = True
        if mod_stage == "stage2" and guided == 0 and unguided == 0 and not stage2_adopted_but_no_change:
            flag_c = True
        if risk_res == 1 and s2_structural == 1:
            flag_d = True
        if not (flag_a or flag_b or flag_c or flag_d):
            continue
        out.append({
            "text_id": text_id,
            "flag_delta_nonzero_changed_zero": 1 if flag_a else 0,
            "flag_changed_one_delta_zero": 1 if flag_b else 0,
            "flag_stage2_no_guided_unguided": 1 if flag_c else 0,
            "flag_risk_resolution_but_stage2_risk": 1 if flag_d else 0,
            "delta_pairs_count": delta_pairs,
            "stage1_to_final_changed": changed,
            "stage_delta_changed": delta_changed,
            "guided_change": guided,
            "unguided_drift": unguided,
            "moderator_selected_stage": row.get("moderator_selected_stage") or "",
            "risk_resolution": risk_res,
            "stage2_structural_risk": s2_structural,
        })
    return out


def write_inconsistency_flags_tsv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Write derived/diagnostics/inconsistency_flags.tsv: rows where changed/guided logic contradicts."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    flagged = _collect_inconsistency_flags(rows)
    fieldnames = [
        "text_id", "flag_delta_nonzero_changed_zero", "flag_changed_one_delta_zero", "flag_stage2_no_guided_unguided", "flag_risk_resolution_but_stage2_risk",
        "delta_pairs_count", "stage1_to_final_changed", "stage_delta_changed", "guided_change", "unguided_drift", "moderator_selected_stage",
        "risk_resolution", "stage2_structural_risk",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(flagged)
    print(f"Wrote inconsistency flags: {out_path} (n={len(flagged)})")


def _collect_drift_cause_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    For each sample with stage1_to_final_changed=1, attach drift_cause_tag, memory_used (=injected), memory_retrieved.
    Returns (list of rows with changed=1 for TSV, summary dict with counts by tag, memory_used, memory_retrieved).
    """
    breakdown: List[Dict[str, Any]] = []
    tag_counts: Dict[str, int] = {}
    memory_used_changed: int = 0
    memory_unused_changed: int = 0
    memory_retrieved_changed: int = 0
    run_id_for_c2 = (rows[0].get("meta") or {}).get("run_id") or rows[0].get("run_id") or "" if rows else ""
    for r in rows:
        row = _triptych_row(r, include_text=False, include_debug=False)
        changed = int(row.get("stage1_to_final_changed") or 0)
        if changed != 1:
            continue
        text_id = row.get("text_id") or ""
        tag = (row.get("drift_cause_tag") or "").strip()
        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        memory_used = int(row.get("memory_used") or 0)
        memory_retrieved = int(row.get("memory_retrieved") or 0)
        if memory_used:
            memory_used_changed += 1
        else:
            memory_unused_changed += 1
        if memory_retrieved:
            memory_retrieved_changed += 1
        breakdown.append({
            "text_id": text_id,
            "drift_cause_tag": tag,
            "moderator_selected_stage": row.get("moderator_selected_stage") or "",
            "stage_delta_changed": row.get("stage1_to_final_changed_from_delta"),
            "stage2_adopted_but_no_change": row.get("stage2_adopted_but_no_change") or 0,
            "guided_change": row.get("guided_change") or 0,
            "unguided_drift": row.get("unguided_drift") or 0,
            "memory_retrieved": memory_retrieved,
            "memory_used": memory_used,
            "run_id": (r.get("meta") or {}).get("run_id") or r.get("run_id") or "",
        })
    summary = {
        "n_changed": len(breakdown),
        "by_tag": dict(tag_counts),
        "memory_used_changed": memory_used_changed,
        "memory_unused_changed": memory_unused_changed,
        "memory_retrieved_changed": memory_retrieved_changed,
        "is_c2_run": "c2" in run_id_for_c2.lower(),
    }
    return breakdown, summary


def write_drift_cause_breakdown_tsv(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Write derived/diagnostics/drift_cause_breakdown.tsv: one row per sample with stage1_to_final_changed=1."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    breakdown, _ = _collect_drift_cause_rows(rows)
    fieldnames = [
        "text_id", "drift_cause_tag", "moderator_selected_stage", "stage_delta_changed",
        "stage2_adopted_but_no_change", "guided_change", "unguided_drift", "memory_retrieved", "memory_used", "run_id",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(breakdown)
    print(f"Wrote drift cause breakdown: {out_path} (n={len(breakdown)} samples with changed=1)")


def write_drift_cause_summary_md(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Write derived/diagnostics/drift_cause_summary.md: counts by drift_cause_tag; C2 memory_used cross-tab."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _, summary = _collect_drift_cause_rows(rows)
    n_changed = summary["n_changed"]
    by_tag = summary.get("by_tag") or {}
    mem_used = summary.get("memory_used_changed") or 0
    mem_unused = summary.get("memory_unused_changed") or 0
    mem_retrieved = summary.get("memory_retrieved_changed") or 0
    is_c2 = summary.get("is_c2_run", False)
    lines = [
        "# Drift cause decomposition (stage1_to_final_changed=1)",
        "",
        "| drift_cause_tag | 설명 | count |",
        "|-----------------|------|-------|",
        f"| **{DRIFT_CAUSE_STAGE2_SELECTED}** | Stage2 선택으로 변경 (Moderator selected stage2) | {by_tag.get(DRIFT_CAUSE_STAGE2_SELECTED, 0)} |",
        f"| **{DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER}** | 동일 stage 선택인데 tuples 변경 (정규화/중복/추출경로 차이) | {by_tag.get(DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER, 0)} |",
        f"| **{DRIFT_CAUSE_STAGE_DELTA_MISSING}** | stage_delta 미기록 (B-type inconsistency) | {by_tag.get(DRIFT_CAUSE_STAGE_DELTA_MISSING, 0)} |",
        "",
        f"**Total samples with changed=1**: {n_changed}",
        "",
        "## Memory (retrieved vs injected)",
        "",
        "| metric | 설명 | count (changed=1) |",
        "|--------|------|------------------|",
        f"| drift_cause_memory_used_changed_n (==injected) | changed=1 이면서 memory_injected=1 | {mem_used} |",
        f"| drift_cause_memory_retrieved_changed_n | changed=1 이면서 memory_retrieved=1 (C3에서 크면: 검색은 하는데 주입 없이 stage2 변화) | {mem_retrieved} |",
        "",
    ]
    if is_c2:
        lines.extend([
            "## 메모리 주입 여부 (C2 run, changed=1)",
            "",
            "| memory_used (=injected) | count |",
            "|------------------------|-------|",
            f"| 1 (injected) | {mem_used} |",
            f"| 0 (not injected) | {mem_unused} |",
            "",
        ])
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote drift cause summary: {out_path}")


def _percentile(sorted_list: List[float], p: float) -> float:
    """p in [0,100]. Returns value at percentile (linear interpolation)."""
    if not sorted_list:
        return 0.0
    n = len(sorted_list)
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    if lo == hi:
        return float(sorted_list[lo])
    return float(sorted_list[lo]) + (idx - lo) * (float(sorted_list[hi]) - float(sorted_list[lo]))


def compute_memory_usage_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """C2 memory usage: retrieved_n p50/p90, used rate, used&changed=0 rate, used&risk_resolution=0 rate."""
    n = len(rows)
    if n == 0:
        return {
            "n_total": 0,
            "retrieved_n_p50": None, "retrieved_n_p90": None,
            "memory_used_rate": None,
            "memory_used_but_changed_zero_rate": None,
            "memory_used_but_risk_resolution_zero_rate": None,
        }
    retrieved_list: List[int] = []
    n_used = 0
    n_used_changed_zero = 0
    n_used_risk_zero = 0
    for r in rows:
        row = _triptych_row(r, include_text=False, include_debug=False)
        retrieved_list.append(int(row.get("memory_retrieved_n") or 0))
        used = int(row.get("memory_used") or 0)
        changed = int(row.get("stage1_to_final_changed") or 0)
        risk_res = int(row.get("risk_resolution") or 0)
        if used:
            n_used += 1
            if changed == 0:
                n_used_changed_zero += 1
            if risk_res == 0:
                n_used_risk_zero += 1
    retrieved_list.sort()
    return {
        "n_total": n,
        "retrieved_n_p50": _percentile([float(x) for x in retrieved_list], 50),
        "retrieved_n_p90": _percentile([float(x) for x in retrieved_list], 90),
        "memory_used_rate": _rate(n_used, n),
        "memory_used_but_changed_zero_rate": _rate(n_used_changed_zero, n_used) if n_used else None,
        "memory_used_but_risk_resolution_zero_rate": _rate(n_used_risk_zero, n_used) if n_used else None,
        "memory_used_count": n_used,
        "memory_used_changed_zero_count": n_used_changed_zero,
        "memory_used_risk_resolution_zero_count": n_used_risk_zero,
    }


def write_memory_usage_summary_csv(rows: List[Dict[str, Any]], out_path: Path, run_id: str = "run") -> None:
    """Write derived/diagnostics/memory_usage_summary.csv: C2 retrieval/usage stats."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = compute_memory_usage_summary(rows)
    row = {"run_id": run_id, **summary}
    fieldnames = [
        "run_id", "n_total",
        "retrieved_n_p50", "retrieved_n_p90",
        "memory_used_rate", "memory_used_but_changed_zero_rate", "memory_used_but_risk_resolution_zero_rate",
        "memory_used_count", "memory_used_changed_zero_count", "memory_used_risk_resolution_zero_count",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerow(row)
    print(f"Wrote memory usage summary: {out_path}")


# ---------- Triptych Table (per-sample human-readable table; read-only from scorecards) ----------
def _pairs_to_display_str(pairs: Set[Tuple[str, str]]) -> str:
    """(aspect_term_norm, polarity_norm) set → 'term|pol;term|pol' for TSV/CSV."""
    if not pairs:
        return ""
    return ";".join(sorted(f"{t}|{p}" for (t, p) in pairs))


def _validator_risk_ids_by_stage(record: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """(s1_risk_ids, s2_risk_ids) from validator blocks. Short ids e.g. NEGATION, CONTRAST."""
    s1_ids: List[str] = []
    s2_ids: List[str] = []
    for stage_block in record.get("validator") or []:
        stage = (stage_block.get("stage") or "").lower()
        risks = stage_block.get("structural_risks") or []
        ids = [(r.get("risk_id") or "").strip() or "UNKNOWN" for r in risks]
        if stage == "stage1":
            s1_ids = ids
        elif stage == "stage2":
            s2_ids = ids
    return s1_ids, s2_ids


def _moderator_selected_stage(record: Dict[str, Any]) -> str:
    """Moderator selected stage: moderator.selected_stage or derived from stage_delta.changed."""
    mod = record.get("moderator") or {}
    if mod.get("selected_stage"):
        return str(mod.get("selected_stage")).strip()
    delta = record.get("stage_delta") or {}
    return "stage2" if delta.get("changed") else "stage1"


def _moderator_rules_short(record: Dict[str, Any]) -> str:
    """Short applied_rules e.g. RuleM or A,B."""
    mod = record.get("moderator") or {}
    rules = mod.get("applied_rules") or []
    if not rules:
        return ""
    return ",".join(str(r).strip() for r in rules[:5])


# Drift cause tags for stage1_to_final_changed=1 (4-way decomposition)
DRIFT_CAUSE_STAGE2_SELECTED = "stage2_selected"           # Stage2 선택으로 변경 (Moderator selected stage2)
DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER = "same_stage_tuples_differ"  # 동일 stage 선택인데 tuples 변경 (정규화/중복/추출경로 차이)
DRIFT_CAUSE_STAGE_DELTA_MISSING = "stage_delta_missing"   # stage_delta 미기록 (B-type inconsistency)
DRIFT_CAUSE_MEMORY_EXPOSED_C2 = "memory_exposed_c2"       # 메모리 노출 여부에 따른 변화 (C2 only; cross-tab dimension)


def _drift_cause_tag(
    stage1_to_final_changed: bool,
    mod_stage: str,
    stage_delta_changed: bool,
    stage2_adopted_but_no_change: bool,
) -> str:
    """
    원인 태그 (stage1_to_final_changed=1인 샘플만 의미 있음).
    Returns one of: stage2_selected, same_stage_tuples_differ, stage_delta_missing, or "" when changed=0.
    """
    if not stage1_to_final_changed:
        return ""
    mod = (mod_stage or "").strip().lower()
    # 1) B-type: changed=1 but stage_delta.changed=False
    if stage_delta_changed is False or stage_delta_changed == 0 or stage_delta_changed == "0":
        return DRIFT_CAUSE_STAGE_DELTA_MISSING
    # 2) Stage2 선택으로 변경
    if mod == "stage2" and not stage2_adopted_but_no_change:
        return DRIFT_CAUSE_STAGE2_SELECTED
    # 3) 동일 stage 선택인데 tuples 변경 (stage1 선택이거나 stage2_adopted_but_no_change)
    return DRIFT_CAUSE_SAME_STAGE_TUPLES_DIFFER


def _triptych_row(
    record: Dict[str, Any],
    include_text: bool = True,
    include_debug: bool = False,
) -> Dict[str, Any]:
    """Build one row for the Triptych table (read-only from scorecard). Uses _extract_*_with_source and tuples_to_pairs."""
    meta = record.get("meta") or {}
    inputs = record.get("inputs") or {}
    text_id = meta.get("text_id") or meta.get("case_id") or record.get("text_id") or ""
    uid = meta.get("uid") or ""
    profile = (record.get("profile") or meta.get("profile") or "").strip()

    s1_tuples, s1_src, n_s1 = _extract_stage1_tuples_with_source(record)
    s2_tuples, s2_src, n_s2 = _extract_final_tuples_with_source(record)
    gold_tuples = _extract_gold_tuples(record)
    gold_src = _gold_tuple_source(record) if gold_tuples is not None else ""

    s1_pairs = tuples_to_pairs(s1_tuples) if s1_tuples else set()
    s2_pairs = tuples_to_pairs(s2_tuples) if s2_tuples else set()
    s2_after_rep = select_representative_tuples(record)
    s2_pairs_after_rep = tuples_to_pairs(s2_after_rep) if s2_after_rep else set()
    gold_pairs = tuples_to_pairs(gold_tuples) if gold_tuples else set()

    # Gold type: explicit (all gold pairs have non-empty term) vs implicit (at least one empty term)
    gold_explicit, gold_implicit = _split_gold_explicit_implicit(gold_tuples) if gold_tuples else (set(), set())
    gold_type = "implicit" if gold_implicit else ("explicit" if gold_tuples else "")
    f1_eval_note = "not evaluated for explicit F1" if gold_implicit else ""

    # Comparison (matches on pairs)
    n_gold = len(gold_pairs)
    match_s1_gold = len(s1_pairs & gold_pairs) if gold_pairs is not None else 0
    match_final_gold = len(s2_pairs & gold_pairs) if gold_pairs is not None else 0
    new_correct_in_final = len((gold_pairs & s2_pairs) - s1_pairs) if gold_pairs is not None else 0
    new_wrong_in_final = len(s2_pairs - gold_pairs) if gold_pairs is not None else len(s2_pairs)

    delta_pairs_count = n_s2 - n_s1
    # A1: changed is canonical from pairs set comparison (not label/delta); delta is for reference
    stage1_to_final_changed = s1_pairs != s2_pairs
    stage_delta = record.get("stage_delta") or {}
    stage1_to_final_changed_from_delta = bool(stage_delta.get("changed", False))
    stage2_adopted_but_no_change = bool(stage_delta.get("stage2_adopted_but_no_change"))
    mod_stage = _moderator_selected_stage(record)
    drift_cause_tag = _drift_cause_tag(
        stage1_to_final_changed,
        mod_stage,
        stage_delta.get("changed"),
        stage2_adopted_but_no_change,
    )
    guided_change, unguided_drift = stage_delta_guided_unguided(record)
    # A2 fallback: when pairs changed but stage_delta had no change_type (e.g. old scorecards), infer unguided
    if stage1_to_final_changed and not guided_change and not unguided_drift:
        unguided_drift = True

    s1_structural = record.get("stage1_structural_risk")
    if s1_structural is None:
        s1_structural = has_stage1_structural_risk(record)
    s2_structural = record.get("stage2_structural_risk")
    if s2_structural is None:
        s2_structural = has_stage2_structural_risk(record)
    risk_resolution = bool(s1_structural and not s2_structural)

    episodic_memory_effect = (
        stage1_to_final_changed and guided_change and risk_resolution
    )

    s1_risk_ids, s2_risk_ids = _validator_risk_ids_by_stage(record)
    validator_s1_risk_ids = ";".join(s1_risk_ids) if s1_risk_ids else ""
    validator_s2_risk_ids = ";".join(s2_risk_ids) if s2_risk_ids else ""

    # Memory observation columns (C2/C3: retrieval vs injection)
    mem = record.get("memory") or {}
    run_id = (record.get("meta") or {}).get("run_id") or record.get("run_id") or ""
    memory_retrieved_n = int(mem.get("retrieved_k") or 0) or len(mem.get("retrieved_ids") or [])
    memory_injected_chars = int(mem.get("prompt_injection_chars") or 0)
    memory_exposed_to_debate = bool(mem.get("exposed_to_debate", False))
    # memory_retrieved = 검색 실행/성공 (C2:1, C3:1, C1:0)
    memory_retrieved = 1 if memory_retrieved_n > 0 else 0
    # memory_injected = 프롬프트에 실제 주입 (C2:1 when gating ok, C3:0 always, C1:0)
    memory_injected = 1 if (memory_exposed_to_debate and memory_injected_chars > 0) else 0
    # memory_used = 분석/집계용, injected와 동일 (C3: memory_retrieved=1, memory_injected=0, memory_used=0)
    memory_used = memory_injected
    memory_enabled = 1 if ("c2" in run_id.lower() or "c3" in run_id.lower() or memory_retrieved_n > 0) else 0
    retrieved_ids = mem.get("retrieved_ids") or []
    memory_ids_or_hash = ";".join(str(x) for x in retrieved_ids[:3]) if retrieved_ids else ""
    # OPFB: Scorecard/Triptych 필수 로그 3개 (왜 drift가 줄었는지 보이게)
    memory_blocked_episode_n = int(mem.get("memory_blocked_episode_n", 0) or 0)
    memory_blocked_advisory_n = int(mem.get("memory_blocked_advisory_n", 0) or 0)
    memory_block_reason = (mem.get("memory_block_reason") or "") if isinstance(mem.get("memory_block_reason"), str) else ""

    row: Dict[str, Any] = {
        "text_id": text_id,
        "uid": uid or "",
        "profile": profile,
        "gold_type": gold_type,
        "f1_eval_note": f1_eval_note,
        "stage1_tuple_source": s1_src,
        "stage1_n_pairs": n_s1,
        "stage1_pairs": _pairs_to_display_str(s1_pairs),
        "final_tuple_source": s2_src,
        "final_n_pairs": n_s2,
        "final_pairs": _pairs_to_display_str(s2_pairs),
        "final_n_pairs_raw": n_s2,
        "final_pairs_raw": _pairs_to_display_str(s2_pairs),
        "final_n_pairs_after_rep": len(s2_pairs_after_rep),
        "final_pairs_after_rep": _pairs_to_display_str(s2_pairs_after_rep),
        "gold_tuple_source": gold_src,
        "gold_n_pairs": n_gold,
        "gold_pairs": _pairs_to_display_str(gold_pairs) if gold_pairs is not None else "",
        "gold_n_explicit_pairs": len(gold_explicit) if gold_tuples else 0,
        "gold_n_implicit_pairs": len(gold_implicit) if gold_tuples else 0,
        "gold_audit_verdict": gold_type,
        "delta_pairs_count": delta_pairs_count,
        "stage1_to_final_changed": 1 if stage1_to_final_changed else 0,
        "stage1_to_final_changed_from_delta": 1 if stage1_to_final_changed_from_delta else 0,
        "drift_any_change": 1 if stage1_to_final_changed else 0,
        "drift_conflict_relevant_change": 1 if (stage1_to_final_changed and (has_polarity_conflict_raw(record) or s1_structural or (gold_pairs is not None and (new_correct_in_final > 0 or (isinstance(new_wrong_in_final, (int, float)) and new_wrong_in_final > 0))))) else 0,
        "guided_change": 1 if guided_change else 0,
        "unguided_drift": 1 if unguided_drift else 0,
        "matches_stage1_vs_gold": match_s1_gold if gold_pairs is not None else "",
        "matches_final_vs_gold": match_final_gold if gold_pairs is not None else "",
        "new_correct_in_final": new_correct_in_final if gold_pairs is not None else "",
        "new_wrong_in_final": new_wrong_in_final,
        "risk_flagged": 1 if is_risk_flagged(record) else 0,
        "stage1_structural_risk": 1 if s1_structural else 0,
        "stage2_structural_risk": 1 if s2_structural else 0,
        "risk_resolution": 1 if risk_resolution else 0,
        "polarity_conflict_raw": 1 if has_polarity_conflict_raw(record) else 0,
        "polarity_conflict_after_rep": 1 if has_polarity_conflict_after_representative(record) else 0,
        "stage_mismatch": 1 if has_stage_mismatch(record) else 0,
        "unsupported_polarity": 1 if has_unsupported_polarity(record) else 0,
        "aspect_hallucination": 1 if has_hallucinated_aspect(record) else 0,
        "alignment_failure_count": count_alignment_failure_drops(record),
        "validator_s1_risk_ids": validator_s1_risk_ids,
        "validator_s2_risk_ids": validator_s2_risk_ids,
        "moderator_selected_stage": mod_stage,
        "moderator_rules": _moderator_rules_short(record),
        "drift_cause_tag": drift_cause_tag,
        "stage2_adopted_but_no_change": 1 if stage2_adopted_but_no_change else 0,
        "episodic_memory_effect": 1 if episodic_memory_effect else 0,
        "memory_enabled": memory_enabled,
        "memory_retrieved": memory_retrieved,
        "memory_injected": memory_injected,
        "memory_exposed_to_debate": 1 if memory_exposed_to_debate else 0,
        "memory_retrieved_n": memory_retrieved_n,
        "memory_used": memory_used,
        "memory_injected_chars": memory_injected_chars,
        "memory_ids_or_hash": memory_ids_or_hash,
        "memory_blocked_episode_n": memory_blocked_episode_n,
        "memory_blocked_advisory_n": memory_blocked_advisory_n,
        "memory_block_reason": memory_block_reason,
        "risk_before_sum": stage1_risk_severity(record),
        "risk_after_sum": residual_risk_severity(record),
        "risk_delta_sum": residual_risk_severity(record) - stage1_risk_severity(record),
    }
    if include_text:
        row["text"] = (inputs.get("text") or meta.get("input_text") or "").strip().replace("\n", " ").replace("\t", " ")
    if include_debug:
        row["rq1_bucket"] = rq1_grounding_bucket(record)
        row["evidence_rationale"] = str((record.get("atsa") or record.get("atsa_score") or {}).get("evidence") or "")[:200]
    return row


def write_triptych_table(
    rows: List[Dict[str, Any]],
    out_path: Path,
    sample_n: int = 0,
    include_text: bool = True,
    include_debug: bool = False,
    use_csv: bool = False,
) -> None:
    """Write per-sample Triptych table (TSV default, or CSV). sample_n=0 means all rows."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    take = len(rows) if sample_n <= 0 else min(sample_n, len(rows))
    subset = rows[:take]

    dict_rows = [_triptych_row(r, include_text=include_text, include_debug=include_debug) for r in subset]
    if not dict_rows:
        out_path.write_text("", encoding="utf-8")
        print(f"Wrote empty Triptych table: {out_path}")
        return

    # Rule check: one row where gold_pairs contains |positive → confirm N_gold and matches_final_vs_gold inclusion
    for i, row in enumerate(dict_rows):
        gp = (row.get("gold_pairs") or "")
        if "|positive" in gp:
            text_id = row.get("text_id") or ""
            gold_n = row.get("gold_n_pairs") or 0
            match_final = row.get("matches_final_vs_gold")
            in_n_gold = "yes (row has gold, so counted in N_gold)"
            in_matches = "yes (matches_final_vs_gold computed for this row; value={})".format(match_final)
            print(
                "[triptych rule check] Row with |positive in gold_pairs: text_id={!r} gold_pairs={!r} gold_n_pairs={} "
                "matches_final_vs_gold={}. Included in N_gold: {}. Included in matches_final_vs_gold calc: {}.".format(
                    text_id, gp, gold_n, match_final, in_n_gold, in_matches
                )
            )
            break

    fieldnames = list(dict_rows[0].keys())
    delimiter = "," if use_csv else "\t"
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(dict_rows)
    print(f"Wrote Triptych table: {out_path} (n={len(dict_rows)}, {'CSV' if use_csv else 'TSV'})")


def write_triptych_risk_details(
    rows: List[Dict[str, Any]],
    out_path: Path,
    sample_n: int = 0,
) -> None:
    """Write risk drilldown JSONL: validator raw risks, debate override stats, ate_debug filtered top-k per text_id."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    take = len(rows) if sample_n <= 0 else min(sample_n, len(rows))
    subset = rows[:take]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        for r in subset:
            meta = r.get("meta") or {}
            text_id = meta.get("text_id") or meta.get("case_id") or r.get("text_id") or ""
            s1_ids, s2_ids = _validator_risk_ids_by_stage(r)
            validator_raw = []
            for stage_block in (r.get("validator") or []):
                validator_raw.append({
                    "stage": stage_block.get("stage"),
                    "structural_risks": stage_block.get("structural_risks") or [],
                })
            override = _get_override_stats(r)
            filtered = (r.get("inputs") or {}).get("ate_debug", {}).get("filtered", [])
            drop_reasons = [x.get("drop_reason") for x in filtered if x.get("action") == "drop"]
            obj = {
                "text_id": text_id,
                "validator_s1_risk_ids": s1_ids,
                "validator_s2_risk_ids": s2_ids,
                "validator_raw": validator_raw,
                "debate_override_stats": override,
                "ate_debug_filtered_drop_reasons_top10": drop_reasons[:10],
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"Wrote Triptych risk details: {out_path} (n={len(subset)})")


# ---------- Eval policy continuity (metric continuity note) ----------
EVAL_POLICY_STRING = (
    "normalize_polarity;normalize_for_eval;match_empty_aspect_by_polarity_only=True;"
    "gold=gold_tuples;stage1=stage1_tuples|trace_atsa;final=final_tuples|final_aspects|inputs.aspect_sentiments"
)


def _eval_policy_hash() -> str:
    """Hash of current eval policy (gold empty handling, normalization, extract path). For metric continuity."""
    return hashlib.sha256(EVAL_POLICY_STRING.encode("utf-8")).hexdigest()[:16]


def _eval_semver() -> str:
    """Eval policy version; set EVAL_SEMVER env to override (e.g. when gold empty policy changes)."""
    return os.environ.get("EVAL_SEMVER", "1.0").strip() or "1.0"


def write_snapshot_eval_inputs(rows: List[Dict[str, Any]], out_path: Path, sample_n: int = 5) -> None:
    """Regression snapshot: first N samples — gold/stage1/final tuple sets (normalized) as JSON for before/after comparison."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _tuples_to_json_list(tuples_set: Set[Tuple[str, str, str]]) -> List[Dict[str, str]]:
        """Normalized (aspect_term, polarity) pairs for JSON; aspect_ref omitted for comparison."""
        pairs = tuples_to_pairs(tuples_set)
        return [{"aspect_term": t, "polarity": p} for (t, p) in sorted(pairs)]

    payload: List[Dict[str, Any]] = []
    for r in rows[:sample_n]:
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("case_id") or r.get("text_id") or ""
        gold = _extract_gold_tuples(r)
        s1 = _extract_stage1_tuples(r)
        s2 = _extract_final_tuples(r)
        payload.append({
            "text_id": text_id,
            "gold_tuples": _tuples_to_json_list(gold) if gold else [],
            "stage1_tuples": _tuples_to_json_list(s1) if s1 else [],
            "final_tuples": _tuples_to_json_list(s2) if s2 else [],
        })
    obj = {
        "eval_policy_hash": _eval_policy_hash(),
        "eval_semver": _eval_semver(),
        "sample_n": len(payload),
        "samples": payload,
    }
    out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote snapshot_eval_inputs: {out_path} (n={len(payload)})")


def run_sanity_checks(rows: List[Dict[str, Any]]) -> bool:
    """Sanity check: gold→gold F1=1, stage1→stage1 F1=1, final→final F1=1. Returns True if all pass."""
    for i, r in enumerate(rows):
        gold = _extract_gold_tuples(r)
        if gold is not None:
            # gold→gold: both sides use aspect_term (match_by_aspect_ref=False). Else gold has (a,t) with both set → ref_fallback picks a → key mismatch → F1=0.
            _, _, f1 = precision_recall_f1_tuple(gold, gold, match_by_aspect_ref=False)
            if abs(f1 - 1.0) > 1e-6:
                print(f"Sanity check FAIL: row {i} gold→gold F1={f1} (expected 1.0)")
                return False
        stage1 = _extract_stage1_tuples(r)
        if stage1:
            _, _, f1 = precision_recall_f1_tuple(stage1, stage1)
            if abs(f1 - 1.0) > 1e-6:
                print(f"Sanity check FAIL: row {i} stage1→stage1 F1={f1} (expected 1.0)")
                return False
        final = _extract_final_tuples(r)
        if final:
            _, _, f1 = precision_recall_f1_tuple(final, final)
            if abs(f1 - 1.0) > 1e-6:
                print(f"Sanity check FAIL: row {i} final→final F1={f1} (expected 1.0)")
                return False
    print("Sanity check passed: gold→gold, stage1→stage1, and final→final F1=1.")
    return True


def main():
    ap = argparse.ArgumentParser(description="Aggregate structural errors from merged_scorecards.jsonl")
    ap.add_argument("--input", required=True, help="Path to merged_scorecards.jsonl (or scorecards.jsonl)")
    ap.add_argument("--outdir", default="results/metrics", help="Output directory for CSV")
    ap.add_argument("--profile", choices=["smoke", "regression", "paper_main"], default=None, help="Filter by profile")
    ap.add_argument("--traces", default=None, help="Optional traces.jsonl for proposal_id linkage")
    ap.add_argument("--log_tuple_sources", default=None, help="Write tuple extraction path log (stage1/final/gold source + N) for first N samples")
    ap.add_argument("--log_sample_n", type=int, default=10, help="Number of samples for tuple source log (default 10)")
    ap.add_argument("--sanity_check", action="store_true", help="Run sanity check: gold→gold F1=1, final→final F1=1")
    ap.add_argument("--snapshot_eval_inputs", default=None, help="Regression snapshot: save gold/stage1/final tuple sets (normalized) for first N samples as JSON")
    ap.add_argument("--snapshot_sample_n", type=int, default=5, help="Number of samples for snapshot_eval_inputs (default 5)")
    ap.add_argument("--export_triptych_table", default=None, help="Write per-sample Triptych table (TSV or CSV); path .csv → CSV, else TSV")
    ap.add_argument("--triptych_sample_n", type=int, default=0, help="Triptych: 0=all, N=first N samples (default 0)")
    ap.add_argument("--triptych_include_text", type=int, default=1, choices=[0, 1], help="Triptych: include input text column (default 1)")
    ap.add_argument("--triptych_include_debug", type=int, default=0, choices=[0, 1], help="Triptych: include evidence/rationale etc. (default 0)")
    ap.add_argument("--export_triptych_risk_details", default=None, help="Optional: write triptych_risk_details.jsonl for risk drilldown")
    ap.add_argument("--diagnostics_dir", default=None, help="Run B1 sanity check (fail-fast), then write tuple_source_coverage.csv and inconsistency_flags.tsv here")
    ap.add_argument("--verbose", action="store_true", help="Log INFO-level messages (e.g. final_pred_source_aspects_path_unused_flag)")
    args = ap.parse_args()

    path = Path(args.input)
    rows = load_jsonl(path)
    if not rows:
        print(f"No records in {path}")
        return

    # B1) Sanity check (fail-fast): gold→gold F1=1, final→final F1=1. Fail => 채점 로직/정규화/추출 경로 충돌.
    if args.sanity_check or args.diagnostics_dir:
        if not run_sanity_checks(rows):
            print("Sanity check FAIL: scoring/normalization/extraction path conflict. Aborting.")
            sys.exit(1)

    if args.log_tuple_sources:
        write_tuple_source_log(rows, Path(args.log_tuple_sources), args.log_sample_n)

    # B2) Tuple source coverage audit; B3) changed/guided inconsistency flags; C2) memory usage summary
    if args.diagnostics_dir:
        diag_dir = Path(args.diagnostics_dir)
        run_id = path.resolve().parent.name or "run"
        write_tuple_source_coverage_csv(rows, diag_dir / "tuple_source_coverage.csv", run_id=run_id)
        write_inconsistency_flags_tsv(rows, diag_dir / "inconsistency_flags.tsv")
        write_drift_cause_breakdown_tsv(rows, diag_dir / "drift_cause_breakdown.tsv")
        write_drift_cause_summary_md(rows, diag_dir / "drift_cause_summary.md")
        write_memory_usage_summary_csv(rows, diag_dir / "memory_usage_summary.csv", run_id=run_id)

    if args.snapshot_eval_inputs:
        write_snapshot_eval_inputs(rows, Path(args.snapshot_eval_inputs), args.snapshot_sample_n)

    if args.export_triptych_table:
        triptych_path = Path(args.export_triptych_table)
        use_csv = triptych_path.suffix.lower() == ".csv"
        write_triptych_table(
            rows,
            triptych_path,
            sample_n=args.triptych_sample_n,
            include_text=bool(args.triptych_include_text),
            include_debug=bool(args.triptych_include_debug),
            use_csv=use_csv,
        )
    if args.export_triptych_risk_details:
        write_triptych_risk_details(rows, Path(args.export_triptych_risk_details), sample_n=args.triptych_sample_n)

    profile_filter = args.profile
    if profile_filter == "paper_main":
        profile_filter = "paper_main"
    override_gate_summary = None
    summary_path = path.resolve().parent / "override_gate_debug_summary.json"
    if summary_path.exists():
        try:
            override_gate_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    metrics = aggregate_merged(rows, profile_filter, override_gate_summary)
    if metrics.get("n", 0) == 0 and profile_filter:
        metrics = aggregate_single_run(rows, None)
        metrics["profile_filter"] = profile_filter or "all"
        if metrics.get("n", 0) > 0:
            metrics["self_consistency_exact"] = None
            metrics["self_consistency_eligible"] = False
            metrics["n_trials"] = 1
    metrics = _ensure_canonical_metrics(metrics)

    # N_pred_final_aspects == 0 with n > 0: final_aspects 경로 미사용 (Info flag, not fail)
    if metrics.get("N_pred_final_aspects", 0) == 0 and metrics.get("n", 0) > 0:
        metrics["final_pred_source_aspects_path_unused_flag"] = True
        if args.verbose:
            print(
                "[aggregator] INFO: final_pred_source_aspects_path_unused_flag=True (N_pred_final_aspects=0 with n>0, final_aspects 경로 미사용)",
                file=sys.stderr,
            )
    else:
        metrics["final_pred_source_aspects_path_unused_flag"] = False

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
    # Outcome (RQ) vs Process (internal diagnostic) — paper-claimable vs validator-level only
    _md_section_before_key: Dict[str, str] = {
        "severe_polarity_error_L3_count": "**Outcome Metrics (RQ)**",
        "validator_clear_rate": "**Process Control Metrics (Internal)**",
        "drift_cause_n_changed": "**Drift cause (stage1_to_final_changed=1)**",
        "drift_any_change_n": "**Drift (any vs conflict-relevant)**",
        "n_stage2_selected": "**Stage2 selection / pairs change**",
    }
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
    ]
    seen = set()
    for k in fieldnames:
        if k not in metrics:
            continue
        if k in _md_section_before_key and k not in seen:
            lines.append(f"| {_md_section_before_key[k]} | |")
            seen.add(k)
        v = metrics[k]
        if v is None:
            v = "N/A"
        elif isinstance(v, float):
            v = f"{v:.4f}"
        lines.append(f"| {k} | {v} |")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {md_path}")

    # final_pred_source_aspects_path_unused_flag는 Info flag (exit 없음)


if __name__ == "__main__":
    main()
