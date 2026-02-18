"""
Derive per-sample scorecards from smoke_outputs.jsonl (or outputs.jsonl).
Outputs: scorecards.jsonl written to --out or alongside the smoke file.
Rule: results/<run_id>/scorecards.jsonl is reserved for run_experiments (original).
Smoke regeneration must use --out results/<run_id>/derived/scorecards/scorecards.smoke.jsonl
(or scorecards.smoke.gold.jsonl when using --gold) to avoid overwriting.
Adds meta.scorecard_source, meta.gold_injected, meta.gold_path, meta.outputs_sha256 for traceability.

Scorecard creation: run_experiments.py and this script both use make_scorecard(entry).
entry = one row of outputs.jsonl (parsed_output); meta.memory is copied to scorecard["memory"]
and scorecard["meta"]["memory"] for A2 (memory_debate_slot_present_for, memory_access_policy).

A2 검증 (재런 없이): 같은 outputs로 scorecard만 재생성 후 검증만 재실행
  python scripts/scorecard_from_smoke.py --smoke results/<run_id>/outputs.jsonl --out results/<run_id>/scorecards.jsonl
  python scripts/pipeline_integrity_verification.py --run_dir results/<run_id> --out reports/pipeline_integrity_verification_<run_id>.json
  → debate_persona_memory.pass true 확인
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure project root on path for structural_error_aggregator import
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Risk ID enum for validator normalization (canonical for S1/S2 comparison)
VALIDATOR_RISK_IDS = (
    "NEGATION_SCOPE", "CONTRAST_SCOPE", "POLARITY_MISMATCH", "EVIDENCE_GAP", "SPAN_MISMATCH", "OTHER",
)
PROPOSAL_ACTION_MAP = {"FLIP_POLARITY": "revise_polarity", "REVISE_SPAN": "revise_span", "DROP_ASPECT": "recheck_evidence"}

# Stoplist of obvious non-targets (ASCII-safe placeholders)
STOP_ASPECT_TERMS = {"ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "아", "야", "언제", "하지만", "그러나"}
# Allow short valid targets seen in contrast sets (can be augmented via CLI allowlist)
TARGET_ALLOWLIST = {"뷰", "AS", "as", "ui", "UI", "앱", "app"}

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_gold_by_uid(gold_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Load uid -> list of normalized gold dicts from a gold JSONL (uid, gold_tuples or gold_triplets).
    Same contract as run_experiments _load_eval_gold for scorecard gold injection."""
    try:
        from metrics.eval_tuple import gold_row_to_tuples
    except ImportError:
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not gold_path.exists():
        return out
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        uid = row.get("uid") or row.get("text_id") or row.get("id")
        if not uid:
            continue
        normalized, _ = gold_row_to_tuples(row)
        if normalized:
            out[str(uid)] = normalized
    return out

def _extract_call_meta(process_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    for tr in process_trace or []:
        notes = tr.get("notes")
        if not notes:
            continue
        try:
            meta = json.loads(notes)
            if isinstance(meta, dict):
                return meta
        except Exception:
            continue
    return {}


def _load_latency_gate_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "experiments" / "configs" / "latency_gate_config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _latency_gate_status(
    total_ms: Optional[int],
    profile: str,
    config: Dict[str, Any],
) -> Tuple[str, int]:
    """Return (gate_status, gate_threshold_ms). gate_status is PASS | WARN only (never FAIL)."""
    thresholds = config.get("latency_thresholds_ms") or {}
    threshold_ms = int(thresholds.get(profile, 30000))
    if total_ms is None:
        return "PASS", threshold_ms
    if total_ms <= threshold_ms:
        return "PASS", threshold_ms
    return "WARN", threshold_ms


def _normalize_risk_type(t: str) -> str:
    t_upper = (t or "").upper()
    for rid in VALIDATOR_RISK_IDS:
        if rid in t_upper or t_upper in rid:
            return rid
    if "NEGATION" in t_upper:
        return "NEGATION_SCOPE"
    if "CONTRAST" in t_upper:
        return "CONTRAST_SCOPE"
    return "OTHER"


def _normalize_validator_stage(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build list of { stage, structural_risks, proposals } from process_trace (Validator outputs)."""
    out: List[Dict[str, Any]] = []
    trace = entry.get("process_trace") or []
    for tr in trace:
        if (tr.get("agent") or "").lower() != "validator":
            continue
        stage = "stage2" if "stage2" in (tr.get("stage") or "").lower() or "reanalysis" in (tr.get("stage") or "").lower() else "stage1"
        raw = tr.get("output") or {}
        risks = []
        for r in raw.get("structural_risks") or []:
            scope = r.get("scope") or {}
            if isinstance(scope, dict):
                span = [int(scope.get("start", 0)), int(scope.get("end", 0))]
            else:
                span = [0, 0]
            sev = (r.get("severity") or "mid").lower()
            if sev not in ("low", "mid", "high"):
                sev = "mid"
            risks.append({
                "risk_id": _normalize_risk_type(r.get("type") or r.get("risk_id") or ""),
                "severity": sev,
                "span": span,
                "description": (r.get("description") or "")[:500],
            })
        proposals = []
        for p in raw.get("correction_proposals") or []:
            prop_type = (p.get("proposal_type") or p.get("action") or "").upper()
            action = PROPOSAL_ACTION_MAP.get(prop_type, "other")
            target = "ATSA" if "POLARITY" in prop_type or "SENTIMENT" in prop_type else "ATE"
            proposals.append({
                "target": target,
                "action": action,
                "reason": (p.get("rationale") or p.get("reason") or "")[:500],
            })
        out.append({"stage": stage, "structural_risks": risks, "proposals": proposals})
    if not out and (entry.get("stage1_validator") or entry.get("stage2_validator")):
        out.append({"stage": "stage1", "structural_risks": [], "proposals": []})
    return out


def _build_stage_delta(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build stage_delta: changed (SSOT pairs-based), pairs_changed, label_changed, change_type, optional hashes/counts.
    SSOT: stage_delta.changed = (s1_pairs != final_pairs) or (stage1_label != final_label). Same extract/normalize as aggregator.
    When changed=0 and selected_stage=stage2: stage2_adopted_but_no_change=1. When changed=1 and no guided → unguided."""
    meta = entry.get("meta") or {}
    correction_log = meta.get("correction_applied_log") or []
    override_stats = (entry.get("debate") or {}).get("override_stats") or meta.get("debate_override_stats") or {}
    override_applied_count = int(override_stats.get("applied") or 0)
    override_applied_bool = override_stats.get("override_applied") is True  # Stage2 adoption decision (per-sample)
    stage1_label = (entry.get("stage1_ate") or {}).get("label") or ""
    stage2_label = (entry.get("stage2_ate") or {}).get("label") if entry.get("stage2_ate") else None
    label_changed = stage2_label is not None and stage2_label != stage1_label

    # SSOT: pairs-based changed (same extract/normalize as aggregator/triptych)
    pairs_changed = False
    n_s1_pairs = 0
    n_final_pairs = 0
    try:
        from scripts.structural_error_aggregator import _extract_stage1_tuples, _extract_final_tuples
        from metrics.eval_tuple import tuples_to_pairs
        wrap = {"runtime": {"parsed_output": entry}}
        s1 = _extract_stage1_tuples(wrap)
        s2 = _extract_final_tuples(wrap)
        s1_pairs = tuples_to_pairs(s1) if s1 else set()
        s2_pairs = tuples_to_pairs(s2) if s2 else set()
        pairs_changed = s1_pairs != s2_pairs
        n_s1_pairs = len(s1_pairs)
        n_final_pairs = len(s2_pairs)
    except Exception:
        pass
    changed = pairs_changed or label_changed

    moderator = entry.get("moderator") or {}
    selected_stage = (moderator.get("selected_stage") or "").strip().lower()
    stage2_adopted = selected_stage == "stage2"

    base = {
        "changed": changed,
        "pairs_changed": pairs_changed,
        "label_changed": label_changed,
        "n_s1_pairs": n_s1_pairs,
        "n_final_pairs": n_final_pairs,
        "related_proposal_ids": [str(i) for i in range(len(correction_log))] if correction_log else [],
    }
    if override_stats.get("override_candidate") is not None:
        base["override_candidate"] = bool(override_stats.get("override_candidate"))
    if override_stats.get("override_applied") is not None:
        base["override_applied"] = bool(override_stats.get("override_applied"))
    if override_stats.get("override_reason"):
        base["override_reason"] = str(override_stats.get("override_reason"))
    if stage2_adopted and not changed:
        base["stage2_adopted_but_no_change"] = True

    if not changed:
        base["change_type"] = "none"
        return base

    # CR (conflict_review_v1): guided_by_review when changed and (review_actions or arb_actions) exist
    protocol_mode = (meta.get("protocol_mode") or "").strip()
    if protocol_mode == "conflict_review_v1":
        analysis_flags = entry.get("analysis_flags") or {}
        review_actions = analysis_flags.get("review_actions") or []
        arb_actions = analysis_flags.get("arb_actions") or []
        has_actions = bool(review_actions or arb_actions)
        base["change_type"] = "guided_by_review" if has_actions else "unguided"
        return base

    # guided: correction_log applied, or Stage2 adoption (override_applied), or legacy debate override count
    guided = (
        any(log.get("applied") for log in correction_log if isinstance(log, dict))
        or override_applied_bool
        or (override_applied_count > 0)
    )
    base["change_type"] = "guided" if guided else "unguided"
    return base

def safe_sub(text: str, span: Dict[str, int]) -> str:
    try:
        return text[span["start"] : span["end"]]
    except Exception:
        return ""

# Drop reason taxonomy for ATE filtered aspects (see docs/metric_spec_rq1_grounding_v2.md)
DROP_REASON_ALIGNMENT_FAILURE = "alignment_failure"
DROP_REASON_FILTER_REJECTION = "filter_rejection"
DROP_REASON_SEMANTIC_HALLUCINATION = "semantic_hallucination"

# Implicit grounding candidate trigger reasons (see docs/implicit_fallback_review_and_plan.md)
IMPLICIT_TRIGGER_NO_ASPECT = "no_aspect"
IMPLICIT_TRIGGER_EXPLICIT_ALIGNMENT_FAILED = "explicit_alignment_failed"


def build_filtered_aspects(text: str, aspects: List[Dict[str, Any]], extra_allow: Set[str] | None = None):
    raw = []
    filtered = []
    allow = TARGET_ALLOWLIST | (extra_allow or set())
    for a in aspects:
        term = a.get("term", "")
        span = a.get("span", {})
        raw.append({"term": term, "span": span})
        span_txt = safe_sub(text, span)
        span_ok = term == span_txt
        has_span = isinstance(span, dict) and "start" in span and "end" in span
        # Allowlist terms bypass minimum length/stop checks
        is_valid = (term in allow) or ((len(term) >= 2) and ((term not in STOP_ASPECT_TERMS) or (term in allow)))
        action = "keep" if (is_valid and span_ok) else "drop"
        drop_reason = None
        if action == "drop":
            if has_span and term != span_txt:
                drop_reason = DROP_REASON_ALIGNMENT_FAILURE
            elif not is_valid:
                drop_reason = DROP_REASON_FILTER_REJECTION
            else:
                # span missing or out-of-range / out-of-text
                drop_reason = DROP_REASON_SEMANTIC_HALLUCINATION
        item = {"term": term, "span": span, "action": action, "drop_reason": drop_reason}
        if span_txt is not None:
            item["span_text"] = span_txt
        filtered.append(item)
    kept_terms = [f["term"] for f in filtered if f["action"] == "keep"]
    dropped_terms = [f["term"] for f in filtered if f["action"] == "drop"]
    return raw, filtered, kept_terms, dropped_terms

def ate_score(filtered):
    keeps = [f for f in filtered if f["action"] == "keep"]
    drops = [f for f in filtered if f["action"] == "drop"]
    hallucination_flag = len(drops) > 0 and len(filtered) > 0  # canonical: hallucinated aspect
    if not keeps:
        return {
            "aspect_judgements": [],
            "missing_aspects": [],
            "valid_aspect_rate": None,
            "span_ok_rate": None,
            "hallucination_flag": hallucination_flag,
        }
    return {
        "aspect_judgements": [{"term": f["term"], "span_ok": True, "is_valid_target": True, "reason": ""} for f in keeps],
        "missing_aspects": [],
        "valid_aspect_rate": 1.0,
        "span_ok_rate": 1.0,
        "hallucination_flag": hallucination_flag,
    }

def atsa_score(text: str, kept_terms: List[str], sentiments: List[Dict[str, Any]]):
    if not sentiments:
        return {
            "sentiment_judgements": [],
            "mean_attribution_score": 0.0,
            "opinion_grounded_rate": 0.0,
            "evidence_relevance_score": 0.0,
            "evidence_flags": [],
        }
    def _term_text(sent: dict) -> str:
        at = sent.get("aspect_term")
        if isinstance(at, dict) and at.get("term") is not None:
            return (at.get("term") or "").strip()
        if isinstance(at, str):
            return at.strip()
        return ((sent.get("opinion_term") or {}).get("term") or "").strip()

    judgements = []
    for s in sentiments:
        ref = _term_text(s)
        attr = 1.0 if ref in kept_terms else 0.0
        op = s.get("aspect_term") or s.get("opinion_term") or {}
        ev = s.get("evidence") or ""
        opinion_grounded = False
        opinion_grounded_reason = ""
        # Option B: aspect_term이 str이면 span 검증 생략 → issues 만들지 않음
        if isinstance(op, str):
            opinion_grounded = True
            opinion_grounded_reason = ""
        elif isinstance(op, dict) and "span" in op:
            op_span = op.get("span", {})
            op_term = op.get("term", "")
            if op_span and op_term:
                extracted_text = safe_sub(text, op_span)
                opinion_grounded = extracted_text == op_term
                if not opinion_grounded:
                    opinion_grounded_reason = f"span_text='{extracted_text}' != aspect_term='{op_term}'"
            else:
                opinion_grounded_reason = f"missing span or term: span={op_span}, term={op_term}"
        else:
            # aspect_term이 dict가 아니거나 span 없음 → str 허용 완화: issues 만들지 않음
            opinion_grounded = True
            opinion_grounded_reason = ""
        evidence_relevant = bool(ev and ev in text)
        issues = []
        if not opinion_grounded:
            issues.append(f"opinion_not_grounded: {opinion_grounded_reason}")
        # evidence/span 없을 때는 unknown/insufficient로만 (aggregator에서 unsupported로 강제하지 않음)
        if not evidence_relevant:
            issues.append("unknown/insufficient")
        judgements.append(
            {
                "aspect_term": ref,
                "attribution_score": attr,
                "opinion_grounded": opinion_grounded,
                "opinion_grounded_reason": opinion_grounded_reason if not opinion_grounded else "",
                "evidence_relevant": evidence_relevant,
                "issues": issues,
                "suggested_fix": {"polarity": s.get("polarity"), "aspect_term": None, "evidence": ev if evidence_relevant else None},
            }
        )
    n = len(judgements)
    evidence_flags = [j.get("issues") or [] for j in judgements if j.get("issues")]
    return {
        "sentiment_judgements": judgements,
        "mean_attribution_score": sum(j["attribution_score"] for j in judgements) / n if n else 0.0,
        "opinion_grounded_rate": sum(1 for j in judgements if j["opinion_grounded"]) / n if n else 0.0,
        "evidence_relevance_score": sum(1 for j in judgements if j["evidence_relevant"]) / n if n else 0.0,
        "evidence_flags": evidence_flags,
    }

def _heuristic_has_target(text: str) -> bool:
    t = (text or "").strip()
    if len(t) <= 1:
        return False
    if t in STOP_ASPECT_TERMS:
        return False
    return (" " in t) or (len(t) >= 4)

def stage_policy_score(text: str, raw_aspects, kept_terms, sentence_sentiment):
    if len(raw_aspects) > 0:
        targetless_expected = False
    else:
        targetless_expected = not _heuristic_has_target(text)
    targetless_applied = targetless_expected and bool(sentence_sentiment)
    targetless_ok = targetless_expected == targetless_applied
    return {
        "targetless_policy_applied": targetless_applied,
        "targetless_expected": targetless_expected,
        "targetless_ok": targetless_ok,
        "notes": [],
        "action_items": [] if targetless_ok else ["Ensure sentence_sentiment is present when no aspects kept."],
    }

def build_sentence_sentiment(text: str, entry: Dict[str, Any]):
    label = entry.get("final_result", {}).get("label", "neutral")
    conf = entry.get("final_result", {}).get("confidence", 0.0)
    return {
        "polarity": label,
        "evidence": {"text": text, "span": {"start": 0, "end": len(text)}},
        "confidence": conf,
        "reason": "fallback to final_result",
    }

def make_scorecard(
    entry: Dict[str, Any],
    extra_allow: Set[str] | None = None,
    meta_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = entry.get("meta", {}).get("input_text", "")
    meta_in = entry.get("meta", {}) or {}
    run_id = meta_in.get("run_id", "")
    text_id = meta_in.get("text_id", "")
    mode = meta_in.get("mode", "")
    case_type = meta_in.get("case_type") or entry.get("case_type")
    split = meta_in.get("split") or entry.get("split")
    manifest_path = meta_in.get("manifest_path") or entry.get("manifest_path")
    cfg_hash = meta_in.get("cfg_hash") or entry.get("cfg_hash")
    call_meta = _extract_call_meta(entry.get("process_trace", []))
    error_str = call_meta.get("error")
    generate_failed = bool(error_str and error_str.startswith("generate_failed"))
    parse_failed = bool(error_str and ("json_parse" in error_str or "schema_validation" in error_str))
    raw_output_val = None if (generate_failed or parse_failed) else (call_meta.get("raw_response") or None)
    runtime = {
        "uid": text_id,
        "split": split,
        "runner_name": mode,
        "backbone_model_id": meta_in.get("backbone_model_id"),
        "raw_output": raw_output_val,
        "parsed_output": None if (generate_failed or parse_failed) else entry,
        "flags": {
            "analysis_flags": entry.get("analysis_flags"),
            "error": error_str,
            "fallback_used": call_meta.get("fallback_construct_used"),
            "generate_failed": generate_failed,
            "parse_failed": parse_failed,
            "usage_parse_failed": call_meta.get("usage_parse_failed", False),
        },
        "tokens_in": call_meta.get("tokens_in"),
        "tokens_out": call_meta.get("tokens_out"),
        "cost_usd": call_meta.get("cost_usd"),
        "latency_ms": meta_in.get("latency_ms"),
        "retries": call_meta.get("retries"),
        "prompt_hash": call_meta.get("prompt_hash") or meta_in.get("prompt_hash"),
        "demo_uids": meta_in.get("demo_uids") or [],
        "demo_k": meta_in.get("demo_k"),
        "demo_seed": meta_in.get("demo_seed"),
    }
    debate_ctx = meta_in.get("debate_review_context") or {}
    debate_override_stats = meta_in.get("debate_override_stats") or {}
    debate_override_skip_reasons = meta_in.get("debate_override_skip_reasons") or {}
    mapping_stats = debate_ctx.get("mapping_stats") or {}
    mapping_fail_reasons = debate_ctx.get("mapping_fail_reasons") or {}
    total_maps = sum(int(v) for v in mapping_stats.values()) if mapping_stats else 0
    direct = int(mapping_stats.get("direct") or 0)
    fallback = int(mapping_stats.get("fallback") or 0)
    coverage = (direct + fallback) / total_maps if total_maps > 0 else None

    stage1_ate = entry.get("stage1_ate", {}) or {}
    stage1_atsa = entry.get("stage1_atsa", {}) or {}

    if not stage1_ate.get("aspects") and entry.get("process_trace"):
        for tr in entry["process_trace"]:
            if tr.get("stage") == "stage1" and tr.get("agent") == "ATE":
                stage1_ate = {**stage1_ate, "aspects": tr.get("output", {}).get("aspects", [])}
                break
    if not stage1_atsa.get("aspect_sentiments") and entry.get("process_trace"):
        for tr in entry["process_trace"]:
            if tr.get("stage") == "stage1" and tr.get("agent") == "ATSA":
                out = tr.get("output", {}) or {}
                aspect_sents = out.get("aspect_sentiments") or out.get("sentiments") or out.get("items") or out.get("results")
                if isinstance(aspect_sents, list):
                    stage1_atsa = {**stage1_atsa, "aspect_sentiments": aspect_sents}
                break

    aspects = stage1_ate.get("aspects") or []
    raw_aspects, filtered, kept_terms, dropped_terms = build_filtered_aspects(text, aspects, extra_allow)
    sentiments = stage1_atsa.get("aspect_sentiments") or []

    sentence_sentiment = None
    if not kept_terms:
        sentence_sentiment = build_sentence_sentiment(text, entry)

    ate = ate_score(filtered)
    atsa = atsa_score(text, kept_terms, sentiments)
    policy = stage_policy_score(text, raw_aspects, kept_terms, sentence_sentiment)

    # Implicit grounding candidate for RQ1 fallback (explicit_failure → implicit when doc polarity valid)
    implicit_grounding_candidate = False
    implicit_trigger_reason = ""
    if not kept_terms:
        implicit_grounding_candidate = True
        implicit_trigger_reason = IMPLICIT_TRIGGER_NO_ASPECT
    else:
        drops = [f for f in filtered if f.get("action") == "drop"]
        if drops and len(drops) == len(filtered):
            if all((f.get("drop_reason") or "").strip() == DROP_REASON_ALIGNMENT_FAILURE for f in drops):
                implicit_grounding_candidate = True
                implicit_trigger_reason = IMPLICIT_TRIGGER_EXPLICIT_ALIGNMENT_FAILED

    quality_pass = True
    fail_reasons = []
    if policy["targetless_expected"]:
        if not sentence_sentiment:
            quality_pass = False
            fail_reasons.append("targetless_missing_sentence_sentiment")
    else:
        thr = 0.5
        if ate["valid_aspect_rate"] is None or ate["valid_aspect_rate"] < thr:
            quality_pass = False
            fail_reasons.append("low_valid_aspect_rate")
        if atsa["opinion_grounded_rate"] is None or atsa["opinion_grounded_rate"] < thr:
            quality_pass = False
            fail_reasons.append("low_opinion_grounded_rate")
        if atsa["evidence_relevance_score"] is None or atsa["evidence_relevance_score"] < thr:
            quality_pass = False
            fail_reasons.append("low_evidence_relevance_score")

    profile = meta_in.get("profile") or "regression"
    latency_config = _load_latency_gate_config()
    total_ms = meta_in.get("latency_ms")
    gate_status, gate_threshold_ms = _latency_gate_status(total_ms, profile, latency_config)
    latency_block = {
        "total_ms": total_ms,
        "gate_threshold_ms": gate_threshold_ms,
        "gate_status": gate_status,
        "profile": profile,
    }
    validator_stages = _normalize_validator_stage(entry)
    moderator_block = entry.get("moderator")
    if isinstance(moderator_block, dict):
        moderator_block = {k: v for k, v in moderator_block.items()}
    else:
        moderator_block = {}
    # Use entry.stage_delta from pipeline if present (avoid recompute drift vs run_experiments); else compute
    stage_delta = entry.get("stage_delta")
    if not isinstance(stage_delta, dict) or not stage_delta:
        stage_delta = _build_stage_delta(entry)
    flags_block = {
        "parse_failed": runtime.get("flags", {}).get("parse_failed", False),
        "generate_failed": runtime.get("flags", {}).get("generate_failed", False),
        "fallback_used": bool(runtime.get("flags", {}).get("fallback_used")),
    }

    stage1_ate_payload = entry.get("stage1_ate")
    stage2_ate_payload = entry.get("stage2_ate")
    if isinstance(stage1_ate_payload, dict):
        stage1_ate_payload = {k: v for k, v in stage1_ate_payload.items()}
    else:
        stage1_ate_payload = {}
    if isinstance(stage2_ate_payload, dict):
        stage2_ate_payload = {k: v for k, v in stage2_ate_payload.items()}
    else:
        stage2_ate_payload = {}

    aux_signals = entry.get("aux_signals") or {}
    if not isinstance(aux_signals, dict):
        aux_signals = {}

    scorecard = {
        "run_id": run_id,
        "profile": profile,
        "aux_signals": aux_signals,
        "meta": {
            "run_id": run_id,
            "text_id": text_id,
            "mode": mode,
            "input_text": text,
            "case_type": case_type,
            "split": split,
            "manifest_path": manifest_path,
            "cfg_hash": cfg_hash,
            "profile": profile,
            "protocol_mode": meta_in.get("protocol_mode"),
            "debate_mapping_stats": mapping_stats,
            "debate_mapping_coverage": coverage,
            "debate_mapping_fail_reasons": mapping_fail_reasons,
            "debate_override_stats": debate_override_stats,
            "debate_override_skip_reasons": debate_override_skip_reasons,
        },
        "debate": {
            "mapping_stats": mapping_stats,
            "mapping_coverage": coverage,
            "mapping_fail_reasons": mapping_fail_reasons,
            "override_stats": debate_override_stats,
        },
        "ate": ate,
        "atsa": atsa,
        "validator": validator_stages,
        "moderator": moderator_block,
        "stage_delta": stage_delta,
        "latency": latency_block,
        "flags": flags_block,
        "stage1_ate": stage1_ate_payload,
        "stage2_ate": stage2_ate_payload,
        "inputs": {
            "ate_debug": {"raw": raw_aspects, "filtered": filtered},
            "filtered_aspects": filtered,
            "aspect_sentiments": sentiments,
            "sentence_sentiment": sentence_sentiment,
            "implicit_grounding_candidate": implicit_grounding_candidate,
            "implicit_trigger_reason": implicit_trigger_reason,
        },
        "ate_score": ate,
        "atsa_score": atsa,
        "stage_policy_score": policy,
        "summary": {
            "quality_pass": quality_pass,
            "fail_reasons": fail_reasons,
            "pass_reason_breakdown": fail_reasons,  # why fail (same as fail_reasons for traceability)
        },
        "runtime": runtime,
    }
    # C2/C3 memory verification: retrieved_k, retrieved_ids, exposed_to_debate, prompt_injection_chars; OPFB 블록 로그 3개
    # Source: parsed_output.meta.memory (entry = pipeline output row; run_experiments와 본 스크립트 모두 make_scorecard 사용 → 동일 경로)
    # mem: 이미 있으면 그대로 재사용 (supervisor가 meta.memory에 기록한 값)
    mem = (meta_in.get("memory") or {}) if isinstance(meta_in.get("memory"), dict) else {}
    scorecard["memory"] = {
        "retrieved_k": mem.get("retrieved_k", 0),
        "retrieved_ids": mem.get("retrieved_ids") if isinstance(mem.get("retrieved_ids"), list) else [],
        "exposed_to_debate": bool(mem.get("exposed_to_debate", False)),
        "prompt_injection_chars": int(mem.get("prompt_injection_chars", 0)),
        "injection_trigger_reason": (mem.get("injection_trigger_reason") or "") if isinstance(mem.get("injection_trigger_reason"), str) else "",
        "memory_blocked_episode_n": int(mem.get("memory_blocked_episode_n", 0)),
        "memory_blocked_advisory_n": int(mem.get("memory_blocked_advisory_n", 0)),
        "memory_block_reason": (mem.get("memory_block_reason") or "") if isinstance(mem.get("memory_block_reason"), str) else "",
        "memory_debate_slot_present_for": mem.get("memory_debate_slot_present_for"),
        "memory_access_policy": mem.get("memory_access_policy"),
    }
    # A2: 검증 스크립트가 (a) row["memory"] 또는 (b) row["meta"]["memory"] 를 보므로 둘 다 동일 블록으로 채움
    scorecard["meta"]["memory"] = dict(scorecard["memory"])
    # Polarity typo policy: aggregator가 polarity_repair_rate, polarity_invalid_rate 산출용으로 row.meta에서 합산
    scorecard["meta"]["polarity_repair_count"] = int(meta_in.get("polarity_repair_count", 0) or 0)
    scorecard["meta"]["polarity_invalid_count"] = int(meta_in.get("polarity_invalid_count", 0) or 0)
    # CR v2 invalid_flag 로그: Appendix 전용
    scorecard["meta"]["invalid_ref_count"] = int(meta_in.get("invalid_ref_count", 0) or 0)
    scorecard["meta"]["invalid_language_count"] = int(meta_in.get("invalid_language_count", 0) or 0)
    scorecard["meta"]["invalid_target_count"] = int(meta_in.get("invalid_target_count", 0) or 0)
    if meta_extra:
        scorecard.setdefault("meta", {}).update(meta_extra)
    # RQ3 extended stage1/stage2 structural risk (for risk_resolution_rate denominator)
    try:
        from scripts.structural_error_aggregator import has_stage1_structural_risk, has_stage2_structural_risk
        scorecard["stage1_structural_risk"] = has_stage1_structural_risk(scorecard)
        scorecard["stage2_structural_risk"] = has_stage2_structural_risk(scorecard)
    except Exception:
        # Leave keys unset so aggregator recomputes from record
        pass
    return scorecard

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=str, default="experiments/results/proposed/smoke_outputs.jsonl")
    ap.add_argument(
        "--gold",
        type=str,
        default=None,
        help="Optional path to gold JSONL (uid, gold_tuples). Merges gold into scorecards by uid/text_id for N_gold > 0.",
    )
    ap.add_argument(
        "--aspect_allowlist",
        type=str,
        default=None,
        help="Optional path to JSON/YAML/CSV file listing aspect terms to force-allow (experiment-scoped).",
    )
    ap.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output path for scorecards. If unset, writes to <smoke_dir>/scorecards.jsonl. "
        "To avoid overwriting run result, use e.g. results/<run_id>/derived/scorecards/scorecards.smoke.gold.jsonl",
    )
    args = ap.parse_args()
    smoke_path = Path(args.smoke)
    smoke_path = smoke_path.resolve() if smoke_path.exists() else smoke_path
    uid_to_gold: Dict[str, List[Dict[str, Any]]] = {}
    if args.gold:
        gold_path = Path(args.gold)
        if not gold_path.is_absolute():
            gold_path = (_PROJECT_ROOT / gold_path).resolve()
        uid_to_gold = load_gold_by_uid(gold_path)
        if uid_to_gold:
            print(f"Gold: loaded gold_tuples for {len(uid_to_gold)} uids from {gold_path}")
    if args.out:
        cards_path = Path(args.out)
        cards_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        # Avoid overwriting run result: if smoke is results/<run_id>/outputs.jsonl, write to derived/scorecards
        if smoke_path.name == "outputs.jsonl" and "results" in smoke_path.parts:
            out_dir = smoke_path.parent / "derived" / "scorecards"
            out_dir.mkdir(parents=True, exist_ok=True)
            cards_path = out_dir / ("scorecards.smoke.gold.jsonl" if (args.gold and uid_to_gold) else "scorecards.smoke.jsonl")
        else:
            cards_path = smoke_path.parent / "scorecards.jsonl"

    allow_terms: Set[str] = set()
    if args.aspect_allowlist:
        allow_path = Path(args.aspect_allowlist)
        if allow_path.exists():
            try:
                suffix = allow_path.suffix.lower()
                if suffix in {".json", ".jsonl"}:
                    data = json.loads(allow_path.read_text(encoding="utf-8-sig"))
                    allow_terms = {str(x) for x in data} if isinstance(data, list) else set()
                elif suffix in {".yaml", ".yml"}:
                    import yaml  # type: ignore

                    data = yaml.safe_load(allow_path.read_text(encoding="utf-8-sig"))
                    allow_terms = {str(x) for x in data} if isinstance(data, list) else set()
                else:
                    # Treat as CSV/TSV/line-delimited
                    tokens: Set[str] = set()
                    for line in allow_path.read_text(encoding="utf-8-sig").splitlines():
                        for tok in line.replace(",", " ").replace("\t", " ").split():
                            if tok:
                                tokens.add(tok.strip())
                    allow_terms = tokens
            except Exception as e:
                print(f"[warn] failed to load allowlist {allow_path}: {e}")

    data = load_jsonl(smoke_path)
    gold_path_resolved = None
    if args.gold:
        gold_path_resolved = Path(args.gold)
        if not gold_path_resolved.is_absolute():
            gold_path_resolved = (_PROJECT_ROOT / gold_path_resolved).resolve()
    with cards_path.open("w", encoding="utf-8", newline="\n") as f:
        for entry in data:
            uid = (entry.get("meta") or {}).get("text_id") or entry.get("text_id") or entry.get("uid") or ""
            gold_injected = bool(uid_to_gold and uid in uid_to_gold)
            meta_extra = {
                "scorecard_source": "scorecard_from_smoke",
                "gold_injected": gold_injected,
                "gold_path": str(gold_path_resolved) if gold_path_resolved else None,
                "outputs_sha256": hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            }
            card = make_scorecard(entry, extra_allow=allow_terms, meta_extra=meta_extra)
            if gold_injected:
                card.setdefault("inputs", {})["gold_tuples"] = uid_to_gold[uid]
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    print(f"wrote {cards_path} ({len(data)} records)")

if __name__ == "__main__":
    main()
