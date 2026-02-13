#!/usr/bin/env python3
"""
파이프라인 정합성 검증: E2E 레코드 수, SoT 불변식 S1/S2/S3, override gate 힌트→점수/neutral_only 분해,
memory 주입/차단, scorecards↔triptych↔structural_metrics pred 일치.

Invariant 재정의 (Action 1):
- S1, S2: FAIL → EXPECTED (debate≠final, final_tuples≠final_aspects는 허용/기대).
- S3만 진짜 FAIL:
  - IF debate_summary.final_tuples ≠ final_result.final_tuples THEN ev_decision == reject AND ev_reason ∈ {low_ev, conflict, no_evidence, memory_contradiction}.
  - ∀ tuple ∈ final_tuples: tuple.aspect_ref(또는 term) ∈ final_aspects.
산출: reports/pipeline_integrity_verification_result.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _norm_t(t: str) -> str:
    return (t or "").strip().lower().replace(" ", "")


def _tuple_set_from_list(items: List[Dict]) -> Set[Tuple[str, str, str]]:
    out = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        ref = (it.get("aspect_ref") or "").strip()
        term = (it.get("aspect_term") or "")
        if isinstance(term, dict):
            term = (term.get("term") or "").strip()
        else:
            term = (term or "").strip()
        pol = (it.get("polarity") or it.get("label") or "").strip().lower()
        if pol in ("pos", "positive"): pol = "positive"
        elif pol in ("neg", "negative"): pol = "negative"
        elif pol in ("neu", "neutral"): pol = "neutral"
        key = (_norm_t(ref), _norm_t(term), pol)
        if key[0] or key[1] or key[2]:
            out.add(key)
    return out


def load_jsonl(p: Path) -> List[Dict[str, Any]]:
    out = []
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def load_json(p: Path) -> Optional[Dict]:
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_dir", type=str, default=None)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    run_dir = Path(args.run_dir) if args.run_dir else _PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t0_proposed"
    out_path = Path(args.out) if args.out else _PROJECT_ROOT / "reports" / "pipeline_integrity_verification_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    scorecards = load_jsonl(run_dir / "scorecards.jsonl")
    outputs = load_jsonl(run_dir / "outputs.jsonl")
    traces = load_jsonl(run_dir / "traces.jsonl")
    override_debug = load_jsonl(run_dir / "override_gate_debug.jsonl")
    override_summary = load_json(run_dir / "override_gate_debug_summary.json")
    manifest = load_json(run_dir / "manifest.json") or {}
    triptych_path = run_dir / "derived" / "tables" / "triptych_table.tsv"
    structural_path = run_dir / "derived" / "metrics" / "structural_metrics.csv"

    expected_n = int(manifest.get("dataset", {}).get("processing_count") or 10)
    result = {
        "run_id": str(run_dir.name),
        "expected_count": expected_n,
        "e2e_record_count": {
            "outputs": len(outputs),
            "scorecards": len(scorecards),
            "traces": len(traces),
            "pass": len(outputs) == expected_n and len(scorecards) == expected_n and len(traces) == expected_n,
        },
        "invariant_s1_expected": [],
        "invariant_s2_expected": [],
        "aggregator_source_fallback": [],
        "invariant_s3_fail": [],
        "invariant_pj1_aspect_not_substring": [],
        "override_applied_hint_evidence": [],
        "neutral_only_breakdown": [],
        "neutral_only_and_source_final_tuples": [],  # CONTRACT-AGG: all polarities neutral and source=final_tuples (track for SoT)
        "memory_samples": [],
        "metrics_pred_consistency": {"pass": None, "mismatches": []},
        "debate_persona_memory": {"pass": None, "violations": []},
        "stage2_memory_injection": {"pass": None, "violations": []},
        "selective_storage_mix": {"pass": None, "store_decision_counts": {}, "note": ""},
    }

    if result["e2e_record_count"]["outputs"] != expected_n:
        result["e2e_record_count"]["note"] = (
            "manifest processing_count=%s, no config limit to %s; run may have been interrupted."
            % (expected_n, result["e2e_record_count"]["outputs"])
        )

    try:
        from scripts.structural_error_aggregator import (
            _extract_final_tuples_with_source,
            _extract_final_tuples,
            _tuples_from_list_of_dicts,
            FINAL_SOURCE_FINAL_TUPLES,
            FINAL_SOURCE_FINAL_ASPECTS,
        )
        from metrics.eval_tuple import tuples_to_pairs, normalize_for_eval, normalize_polarity
        _aggregator_available = True
    except Exception:
        _extract_final_tuples_with_source = None
        _extract_final_tuples = None
        tuples_to_pairs = None
        _aggregator_available = False

    for i, row in enumerate(scorecards):
        text_id = (row.get("meta") or {}).get("text_id") or row.get("runtime", {}).get("uid") or ("row_%s" % i)
        runtime = row.get("runtime") or row
        parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else row
        if isinstance(parsed, dict):
            meta = parsed.get("meta") or {}
            fr = parsed.get("final_result") or {}
        else:
            meta = row.get("meta") or {}
            fr = (runtime.get("parsed_output") or {}).get("final_result") if isinstance(runtime.get("parsed_output"), dict) else {}
        debate_summary = meta.get("debate_summary") or (parsed.get("debate_summary") if isinstance(parsed, dict) else {})

        # S1 (EXPECTED): debate_summary.final_tuples ≠ final_result.final_tuples — 허용/기대
        ds_tuples = debate_summary.get("final_tuples") if isinstance(debate_summary, dict) else []
        fr_tuples = fr.get("final_tuples") or []
        debate_final_mismatch = False
        if ds_tuples and isinstance(ds_tuples, list):
            set_ds = _tuple_set_from_list(ds_tuples)
            set_fr = _tuple_set_from_list(fr_tuples)
            if set_ds != set_fr:
                debate_final_mismatch = True
                result["invariant_s1_expected"].append({
                    "text_id": text_id,
                    "debate_summary_n": len(set_ds),
                    "final_result_n": len(set_fr),
                    "symdiff": len(set_ds ^ set_fr),
                })

        # S2 (EXPECTED): final_tuples ↔ final_aspects 불일치 — 허용/기대
        final_aspects = fr.get("final_aspects") or []
        set_ft = _tuple_set_from_list(fr_tuples)
        set_fa = set()
        final_aspect_terms: Set[str] = set()
        for it in final_aspects:
            if isinstance(it, dict):
                term = it.get("aspect_term")
                t = (term.get("term", "") if isinstance(term, dict) else (term or "")).strip()
                pol = (it.get("polarity") or "").strip().lower()
                set_fa.add((_norm_t(""), _norm_t(t), pol or "neutral"))
                if t:
                    final_aspect_terms.add(_norm_t(t))
        if set_ft and set_fa and set_ft != set_fa:
            result["invariant_s2_expected"].append({"text_id": text_id, "final_tuples_n": len(set_ft), "final_aspects_n": len(set_fa)})

        # S3 (FAIL only): (1) debate≠final → ev_decision==reject AND ev_reason ∈ {low_ev, conflict, no_evidence, memory_contradiction}; (2) ∀ tuple: aspect_ref ∈ final_aspects
        EV_REASON_ALLOWED = {"low_ev", "conflict", "no_evidence", "memory_contradiction"}
        ADOPT_REASON_TO_EV = {
            "ev_below_threshold": "low_ev", "low_signal": "low_ev", "l3_conservative": "conflict",
            "conflict_blocked": "conflict", "action_ambiguity": "conflict", "implicit_soft_only": "conflict",
            "no_evidence_span": "no_evidence", "evidence_span_not_in_text": "no_evidence", "evidence_span_missing_trigger": "no_evidence",
            "contradictory_memory": "memory_contradiction", "max_one_override_per_sample": "low_ev",
        }
        adopt_decision = (meta.get("adopt_decision") or "").strip().lower()
        adopt_reason = (meta.get("adopt_reason") or "").strip().lower().replace("-", "_")
        ev_decision_reject = adopt_decision == "not_adopted"
        ev_reason_canon = ADOPT_REASON_TO_EV.get(adopt_reason) or (adopt_reason if adopt_reason in EV_REASON_ALLOWED else None)
        ev_ok = ev_decision_reject and (ev_reason_canon in EV_REASON_ALLOWED if ev_reason_canon else False)
        if debate_final_mismatch and not ev_ok:
            result["invariant_s3_fail"].append({
                "text_id": text_id,
                "reason": "ev_decision_or_reason_violation",
                "debate_final_mismatch": True,
                "ev_decision_reject": ev_decision_reject,
                "ev_reason_raw": adopt_reason,
                "ev_reason_canon": ev_reason_canon,
            })
        violating_refs: List[str] = []
        for it in (fr_tuples or []):
            if not isinstance(it, dict):
                continue
            ref = (it.get("aspect_ref") or "").strip()
            term = it.get("aspect_term")
            t = (term.get("term", "") if isinstance(term, dict) else (term or "")).strip()
            key = _norm_t(ref) or _norm_t(t)
            if not key:
                continue
            in_fa = key in final_aspect_terms
            if not in_fa:
                violating_refs.append(key)
        if violating_refs:
            result["invariant_s3_fail"].append({
                "text_id": text_id,
                "reason": "tuple_aspect_ref_not_in_final_aspects",
                "aspect_ref_or_terms": violating_refs,
            })

        # Aggregator source (informational, not fail)
        if _extract_final_tuples_with_source:
            tuple_set, src, n = _extract_final_tuples_with_source(row)
            if src != FINAL_SOURCE_FINAL_TUPLES:
                result["aggregator_source_fallback"].append({"text_id": text_id, "source": src})
            # CONTRACT-AGG: neutral-only & source=final_tuples 별도 집계 (SoT 추적)
            if src == FINAL_SOURCE_FINAL_TUPLES and tuple_set and n > 0:
                polarities = {p for (_, _, p) in tuple_set}
                if polarities <= {"neutral"}:
                    result["neutral_only_and_source_final_tuples"].append({
                        "text_id": text_id,
                        "n_tuples": n,
                        "source": src,
                    })

        # PJ1: Stage1 ATE invariant — every aspect term must be a substring of input text
        input_text = (meta.get("input_text") or "").strip()
        stage1_aspects = meta.get("stage1_aspects") or []
        for asp in stage1_aspects:
            if not isinstance(asp, dict):
                continue
            term = (asp.get("term") or "").strip()
            if not term:
                continue
            if term not in input_text:
                result["invariant_pj1_aspect_not_substring"].append({"text_id": text_id, "term": term, "rejection_reason": "aspect_not_substring"})

        # Memory: sample list
        mem = (row.get("meta") or {}).get("memory") or row.get("memory") or {}
        if isinstance(mem, dict) and (mem.get("retrieved_k") or mem.get("retrieved_ids")):
            result["memory_samples"].append({
                "text_id": text_id,
                "retrieved_k": mem.get("retrieved_k"),
                "exposed_to_debate": mem.get("exposed_to_debate"),
                "prompt_injection_chars": mem.get("prompt_injection_chars"),
                "advisory_injection_gated": mem.get("advisory_injection_gated"),
                "memory_block_reason": (mem.get("memory_block_reason") or "")[:80],
            })
        # G1: Debate persona memory — C2 + debate gate passed → slot present for CJ only
        if isinstance(mem, dict) and mem.get("exposed_to_debate") and (mem.get("prompt_injection_chars") or 0) > 0:
            slot_present = mem.get("memory_debate_slot_present_for")
            policy_debate = (mem.get("memory_access_policy") or {}).get("debate")
            if slot_present != ["cj"] or policy_debate != "cj_only":
                result["debate_persona_memory"]["violations"].append({
                    "text_id": text_id,
                    "memory_debate_slot_present_for": slot_present,
                    "memory_access_policy.debate": policy_debate,
                })
        # G2: Stage2 memory — when stage2_memory_injected=True, review context must contain STAGE2_REVIEW_CONTEXT__MEMORY
        if isinstance(mem, dict) and mem.get("stage2_memory_injected"):
            review_ctx = meta.get("debate_review_context")
            if not isinstance(review_ctx, dict) or "STAGE2_REVIEW_CONTEXT__MEMORY" not in review_ctx:
                result["stage2_memory_injection"]["violations"].append({
                    "text_id": text_id,
                    "stage2_memory_injected": True,
                    "has_stage2_key": isinstance(review_ctx, dict) and "STAGE2_REVIEW_CONTEXT__MEMORY" in review_ctx,
                })
        # G3: Selective storage — collect store_decision for post-loop check
        store_decision = meta.get("store_decision")
        if store_decision is not None:
            result["selective_storage_mix"].setdefault("_decisions", [])
            result["selective_storage_mix"]["_decisions"].append(store_decision)

    # Override: applied 케이스에서 hint→점수 증거 (override_gate_debug에 decision APPLY 없으면 summary 기준으로 applied된 aspect 추정)
    applied_records = [r for r in override_debug if (r.get("decision") == "APPLY" or r.get("override_action"))]
    for r in applied_records:
        result["override_applied_hint_evidence"].append({
            "text_id": r.get("text_id"),
            "aspect_term": r.get("aspect_term"),
            "valid_hint_count": r.get("valid_hint_count"),
            "pos_score": r.get("pos_score"),
            "neg_score": r.get("neg_score"),
            "total": r.get("total"),
            "margin": r.get("margin"),
        })
    neutral_only_records = [r for r in override_debug if r.get("skip_reason") == "neutral_only"]
    for r in neutral_only_records[:15]:
        result["neutral_only_breakdown"].append({
            "text_id": r.get("text_id"),
            "aspect_term": r.get("aspect_term"),
            "valid_hint_count": r.get("valid_hint_count"),
            "pos_score": r.get("pos_score"),
            "neg_score": r.get("neg_score"),
            "note": "hint_absent" if (r.get("valid_hint_count") or 0) == 0 else "hint_reduced_to_neutral",
        })
    if len(neutral_only_records) > 15:
        result["neutral_only_breakdown"].append({"_truncated": True, "total_neutral_only": len(neutral_only_records)})

    # Metrics: scorecards final vs triptych final_pairs vs structural_metrics n
    triptych_rows = []
    if triptych_path.exists():
        with open(triptych_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if lines:
            header = lines[0].split("\t")
            for line in lines[1:]:
                cols = line.split("\t")
                row = dict(zip(header, cols)) if len(cols) >= len(header) else {}
                triptych_rows.append(row)
    sc_by_id = {(s.get("meta") or {}).get("text_id") or (s.get("runtime") or {}).get("uid"): s for s in scorecards}
    mismatches = []
    for tr in triptych_rows:
        tid = tr.get("text_id")
        t_final = (tr.get("final_pairs") or "").strip()
        sc = sc_by_id.get(tid)
        if not sc:
            continue
        if _aggregator_available and _extract_final_tuples is not None and tuples_to_pairs is not None:
            sc_tuples = _extract_final_tuples(sc)
            sc_pairs = tuples_to_pairs(sc_tuples) if sc_tuples else set()
            t_pairs = set()
            for part in (t_final or "").split(";"):
                part = part.strip()
                if "|" in part:
                    t, p = part.split("|", 1)
                    t_pairs.add((normalize_for_eval(t.strip()), normalize_polarity(p.strip())))
            sc_final = ";".join(sorted(f"{t}|{p}" for (t, p) in sc_pairs))
            if sc_pairs != t_pairs:
                mismatches.append({"text_id": tid, "scorecard_pairs": sc_final[:200], "triptych_pairs": t_final[:200]})
        else:
            fr = (sc.get("runtime") or {}).get("parsed_output") or sc
            fr = fr.get("final_result") if isinstance(fr, dict) else {}
            ft = fr.get("final_tuples") or []
            parts = []
            for it in ft:
                if isinstance(it, dict):
                    t = it.get("aspect_term") or (it.get("aspect_term") if isinstance(it.get("aspect_term"), dict) else "")
                    if isinstance(t, dict):
                        t = t.get("term", "")
                    p = it.get("polarity") or it.get("label", "")
                    parts.append("%s|%s" % (t, p))
            sc_final = ";".join(sorted(parts))
            if _norm_t(sc_final) != _norm_t(t_final.replace(";", "").replace("|", "")):
                mismatches.append({"text_id": tid, "scorecard_pairs": sc_final[:100], "triptych_pairs": t_final[:100]})
    result["metrics_pred_consistency"]["pass"] = len(mismatches) == 0
    result["metrics_pred_consistency"]["mismatches"] = mismatches
    result["metrics_pred_consistency"]["scorecards_n"] = len(scorecards)
    result["metrics_pred_consistency"]["triptych_n"] = len(triptych_rows)

    # G1/G2: set pass from violations
    result["debate_persona_memory"]["pass"] = len(result["debate_persona_memory"]["violations"]) == 0
    result["stage2_memory_injection"]["pass"] = len(result["stage2_memory_injection"]["violations"]) == 0

    # G3: Selective storage — when store_write=True (any store_decision present), both stored and skipped must occur
    decisions = result["selective_storage_mix"].pop("_decisions", [])
    if decisions:
        from collections import Counter
        counts = Counter(decisions)
        result["selective_storage_mix"]["store_decision_counts"] = dict(counts)
        has_stored = "stored" in counts
        has_skipped = "skipped" in counts
        result["selective_storage_mix"]["pass"] = has_stored and has_skipped
        if not result["selective_storage_mix"]["pass"]:
            result["selective_storage_mix"]["note"] = "store_write=True run must have both stored and skipped (no 100% store)."
    else:
        result["selective_storage_mix"]["pass"] = None
        result["selective_storage_mix"]["note"] = "No store_decision in meta (C1 or C2_eval_only)."

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("Wrote %s" % out_path)


if __name__ == "__main__":
    main()
