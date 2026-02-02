"""
Derive per-sample scorecards from smoke_outputs.jsonl.
Outputs: scorecards.jsonl written alongside the smoke file.
Adds ATE debug info (raw candidates + filtered decisions) for easier diagnosis.
Extended: run_id, profile, ate, atsa, validator, moderator, stage_delta, latency, flags.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
    """Build stage_delta: changed, change_type (guided|unguided|none), related_proposal_ids."""
    flags = entry.get("analysis_flags") or {}
    correction_log = (entry.get("meta") or {}).get("correction_applied_log") or []
    stage1_label = (entry.get("stage1_ate") or {}).get("label") or ""
    stage2_label = (entry.get("stage2_ate") or {}).get("label") if entry.get("stage2_ate") else None
    changed = bool(flags.get("correction_occurred") or (stage2_label is not None and stage2_label != stage1_label))
    related_ids = [str(i) for i in range(len(correction_log))] if correction_log else []
    if not changed:
        return {"changed": False, "change_type": "none", "related_proposal_ids": []}
    guided = any(log.get("applied") for log in correction_log if isinstance(log, dict))
    change_type = "guided" if guided else "unguided"
    return {"changed": True, "change_type": change_type, "related_proposal_ids": related_ids}

def safe_sub(text: str, span: Dict[str, int]) -> str:
    try:
        return text[span["start"] : span["end"]]
    except Exception:
        return ""

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
        # Allowlist terms bypass minimum length/stop checks
        is_valid = (term in allow) or ((len(term) >= 2) and ((term not in STOP_ASPECT_TERMS) or (term in allow)))
        action = "keep" if (is_valid and span_ok) else "drop"
        drop_reason = None if action == "keep" else "other_not_target"
        filtered.append({"term": term, "span": span, "action": action, "drop_reason": drop_reason})
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
    judgements = []
    for s in sentiments:
        ref = s.get("aspect_ref", "")
        attr = 1.0 if ref in kept_terms else 0.0
        op = s.get("opinion_term") or {}
        ev = s.get("evidence") or ""
        opinion_grounded = False
        opinion_grounded_reason = ""
        if isinstance(op, dict) and "span" in op:
            op_span = op.get("span", {})
            op_term = op.get("term", "")
            if op_span and op_term:
                extracted_text = safe_sub(text, op_span)
                opinion_grounded = extracted_text == op_term
                if not opinion_grounded:
                    opinion_grounded_reason = f"span_text='{extracted_text}' != opinion_term='{op_term}'"
            else:
                opinion_grounded_reason = f"missing span or term: span={op_span}, term={op_term}"
        else:
            opinion_grounded_reason = "opinion_term missing or not dict"
        evidence_relevant = ev in text
        issues = []
        if not opinion_grounded:
            issues.append(f"opinion_not_grounded: {opinion_grounded_reason}")
        judgements.append(
            {
                "aspect_ref": ref,
                "attribution_score": attr,
                "opinion_grounded": opinion_grounded,
                "opinion_grounded_reason": opinion_grounded_reason if not opinion_grounded else "",
                "evidence_relevant": evidence_relevant,
                "issues": issues,
                "suggested_fix": {"polarity": s.get("polarity"), "opinion_term": None, "evidence": ev if evidence_relevant else None},
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

def make_scorecard(entry: Dict[str, Any], extra_allow: Set[str] | None = None) -> Dict[str, Any]:
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
        },
        "ate_score": ate,
        "atsa_score": atsa,
        "stage_policy_score": policy,
        "summary": {"quality_pass": quality_pass, "fail_reasons": fail_reasons},
        "runtime": runtime,
    }
    return scorecard

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=str, default="experiments/results/proposed/smoke_outputs.jsonl")
    ap.add_argument(
        "--aspect_allowlist",
        type=str,
        default=None,
        help="Optional path to JSON/YAML/CSV file listing aspect terms to force-allow (experiment-scoped).",
    )
    args = ap.parse_args()
    smoke_path = Path(args.smoke)
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
    with cards_path.open("w", encoding="utf-8", newline="\n") as f:
        for entry in data:
            card = make_scorecard(entry, extra_allow=allow_terms)
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
    print(f"wrote {cards_path} ({len(data)} records)")

if __name__ == "__main__":
    main()
