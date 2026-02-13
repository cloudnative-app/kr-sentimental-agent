"""Conflict-review protocol v1 runner: produces FinalOutputSchema from perspective + review flow."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from tools.data_tools import InternalExample
from schemas import FinalOutputSchema, FinalResult, ProcessTrace, AnalysisFlags
from schemas.protocol_conflict_review import (
    ASTETripletItem,
    PerspectiveASTEStage1Schema,
    ReviewActionItem,
    ReviewOutputSchema,
)
from agents.protocol_conflict_review import (
    PerspectiveAgentPneg,
    PerspectiveAgentPimp,
    PerspectiveAgentPlit,
    ReviewAgentA,
    ReviewAgentB,
    ReviewAgentC,
)
from tools.backbone_client import BackboneClient


def _triplet_to_candidate(t: ASTETripletItem, tuple_id: str, origin_agent: str) -> Dict[str, Any]:
    return {
        "tuple_id": tuple_id,
        "aspect_term": t.aspect_term,
        "aspect_ref": t.aspect_ref,
        "polarity": t.polarity,
        "evidence": t.evidence,
        "span": t.span,
        "origin_agent": origin_agent,
    }


def _cr_adapter_for_slot(candidates: List[Dict[str, Any]]) -> Any:
    """Adapter for EpisodicOrchestrator.get_slot_payload: stage1_ate with .aspects from candidates."""
    aspects = [SimpleNamespace(term=c.get("aspect_term") or c.get("aspect_ref") or "") for c in candidates]
    return SimpleNamespace(aspects=aspects)


def _format_memory_context(slot_dict: Dict[str, Any], slot_name: str = "DEBATE_CONTEXT__MEMORY") -> str:
    """Format slot_dict for Review prompt advisory injection."""
    bundle = (slot_dict.get(slot_name) if isinstance(slot_dict, dict) else None) or (
        list(slot_dict.values())[0] if slot_dict else {}
    )
    if not isinstance(bundle, dict):
        return ""
    retrieved = bundle.get("retrieved") or []
    if not bundle.get("memory_on") or not retrieved:
        return ""
    lines = ["Memory advisory (from similar past cases):"]
    for adv in retrieved:
        msg = adv.get("message", "")
        if msg:
            lines.append(f"- {msg}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _cr_adapters_for_append(
    candidates: List[Dict[str, Any]],
    final_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build legacy-form adapters for EpisodicOrchestrator.append_episode_if_needed (CR path)."""
    def _aspect(term: str) -> Any:
        return SimpleNamespace(term=term or "")

    def _sent(term: str, pol: str) -> Any:
        return SimpleNamespace(aspect_term=SimpleNamespace(term=term or ""), polarity=pol or "neutral")

    aspects1 = [_aspect(c.get("aspect_term") or c.get("aspect_ref")) for c in candidates]
    sents1 = [_sent(c.get("aspect_term") or c.get("aspect_ref"), c.get("polarity")) for c in candidates]
    aspects2 = [_aspect(c.get("aspect_term") or c.get("aspect_ref")) for c in final_candidates]
    sents2 = [_sent(c.get("aspect_term") or c.get("aspect_ref"), c.get("polarity")) for c in final_candidates]
    empty_risks = []
    empty_proposals = []
    stage1_validator = SimpleNamespace(structural_risks=empty_risks, correction_proposals=empty_proposals)
    stage2_validator = SimpleNamespace(structural_risks=empty_risks, correction_proposals=empty_proposals)
    return {
        "stage1_ate": SimpleNamespace(aspects=aspects1),
        "stage1_atsa": SimpleNamespace(aspect_sentiments=sents1, confidence=0.5),
        "stage1_validator": stage1_validator,
        "stage2_ate": SimpleNamespace(aspects=aspects2),
        "stage2_atsa": SimpleNamespace(aspect_sentiments=sents2, confidence=0.5),
        "stage2_validator": stage2_validator,
        "moderator_out": SimpleNamespace(),
    }


def _compute_conflict_flags(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect conflicts: same aspect_term with different polarity."""
    by_term: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        term = (c.get("aspect_term") or "").strip() or (c.get("aspect_ref") or "").strip()
        if not term:
            continue
        by_term.setdefault(term, []).append(c)
    flags = []
    for term, items in by_term.items():
        pols = {i.get("polarity") for i in items if i.get("polarity")}
        if len(pols) > 1:
            flags.append({"aspect_term": term, "tuple_ids": [i.get("tuple_id") for i in items], "conflict_type": "polarity_mismatch"})
    return flags


def _group_actions_by_tuple(
    actions_a: List[Dict[str, Any]],
    actions_b: List[Dict[str, Any]],
    actions_c: List[Dict[str, Any]],
    all_tuple_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Map each tuple_id to {A: action_dict, B: action_dict, C: action_dict}. Default KEEP if no action."""
    result: Dict[str, Dict[str, Any]] = {tid: {"A": None, "B": None, "C": None} for tid in all_tuple_ids}

    for act, key in [(actions_a, "A"), (actions_b, "B"), (actions_c, "C")]:
        for a in act or []:
            atype = (a.get("action_type") or a.get("type") or "KEEP").strip().upper()
            ids = a.get("target_tuple_ids") or []
            action_dict = {
                "action_type": atype,
                "new_value": a.get("new_value") or {},
                "reason_code": (a.get("reason_code") or "").strip(),
            }
            for tid in ids:
                if tid in result:
                    result[tid][key] = action_dict

    return result


# Structural reason codes: when only 1 reviewer proposes FLIP, adopt if structural.
_STRUCTURAL_REASON_CODES = frozenset({"NEGATION_SCOPE", "CONTRAST_CLAUSE", "STRUCTURAL_INCONSISTENT"})


def _arbiter_vote(
    actions_by_tuple: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Deterministic Arbiter: No A>B>C authority. Aggregation by majority and reason_code.

    Rule 1: ≥2 identical → adopt.
    Rule 2: All disagree → KEEP + FLAG.
    Rule 3: 1 FLIP + 1 DROP + 1 KEEP: if FLIP has structural reason_code → FLIP; else FLAG.
    Rule 4: Arbiter does NOT output MERGE (moved to Finalize).
    """
    from collections import Counter

    output: List[Dict[str, Any]] = []
    for tid, acts in actions_by_tuple.items():
        votes_raw = [acts.get("A"), acts.get("B"), acts.get("C")]
        votes = [_norm_atype(v) if v else "KEEP" for v in votes_raw]
        votes_adopted = [v if v != "MERGE" else "KEEP" for v in votes]

        cnt = Counter(votes_adopted)
        most_common = cnt.most_common(1)[0] if cnt else ("KEEP", 0)
        majority_action, majority_count = most_common[0], most_common[1]

        add_flag = False
        if majority_count >= 2:
            final_action = majority_action
        else:
            # No majority: check for single FLIP with structural reason (Rule 3)
            if set(votes_adopted) == {"FLIP", "DROP", "KEEP"}:
                flip_action = next((v for v in votes_raw if v and _norm_atype(v) == "FLIP"), None)
                reason = (flip_action.get("reason_code") or "").strip().upper() if flip_action else ""
                if reason and reason in _STRUCTURAL_REASON_CODES:
                    final_action = "FLIP"
                    add_flag = False
                else:
                    final_action = "FLAG"
                    add_flag = True
            else:
                final_action = "FLAG"
                add_flag = True  # Rule 2: all disagree → FLAG

        out: Dict[str, Any] = {
            "action_type": final_action,
            "target_tuple_ids": [tid],
            "actor": "ARB",
            "reason_code": "POLARITY_UNCERTAIN" if add_flag else "",
        }
        if final_action == "FLIP":
            for v in votes_raw:
                if v and _norm_atype(v) == "FLIP" and v.get("new_value"):
                    out["new_value"] = v.get("new_value")
                    break
        output.append(out)

    return output


def _norm_atype(v: Any) -> str:
    if not v or not isinstance(v, dict):
        return "KEEP"
    t = (v.get("action_type") or v.get("type") or "KEEP").strip().upper()
    return t if t else "KEEP"


def _apply_review_actions(
    candidates: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply DROP/FLIP/KEEP/FLAG. FLAG = KEEP (no drop/flip). MERGE handled in _finalize_normalize_ref."""
    id_to_cand = {c.get("tuple_id"): dict(c) for c in candidates if c.get("tuple_id")}
    to_drop = set()
    for a in actions:
        atype = (a.get("action_type") or "").strip().upper()
        ids = a.get("target_tuple_ids") or []
        if atype == "DROP":
            to_drop.update(ids)
        elif atype == "FLIP":
            new_val = a.get("new_value") or {}
            pol = new_val.get("polarity")
            if pol:
                for tid in ids:
                    if tid in id_to_cand:
                        id_to_cand[tid]["polarity"] = pol
        # MERGE: no longer applied here; see _finalize_normalize_ref
    return [c for tid, c in id_to_cand.items() if tid not in to_drop]


def _finalize_normalize_ref(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic normalization: unify aspect_ref for tuples with same aspect_term."""
    by_term: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        term = (c.get("aspect_term") or "").strip() or (c.get("aspect_ref") or "").strip()
        key = term or "___empty"
        by_term.setdefault(key, []).append(c)

    result = []
    for term, items in by_term.items():
        canonical_ref = (items[0].get("aspect_term") or items[0].get("aspect_ref") or "").strip()
        for c in items:
            out = dict(c)
            out["aspect_ref"] = canonical_ref
            result.append(out)
    return result


def run_conflict_review_v1(
    example: InternalExample,
    backbone: BackboneClient,
    run_id: str,
    *,
    language_code: str = "unknown",
    domain_id: str = "unknown",
    demos: Optional[List[str]] = None,
    episodic_orchestrator: Optional[Any] = None,
    episodic_config: Optional[Dict[str, Any]] = None,
) -> FinalOutputSchema:
    text = example.text
    text_id = getattr(example, "uid", "text") or "text"
    trace: List[ProcessTrace] = []
    demos = demos or []

    # Stage1: P-NEG, P-IMP, P-LIT
    pneg = PerspectiveAgentPneg(backbone)
    pimp = PerspectiveAgentPimp(backbone)
    plit = PerspectiveAgentPlit(backbone)
    r_neg = pneg.run_stage1(text, run_id=run_id, text_id=text_id, demos=demos, language_code=language_code, domain_id=domain_id)
    r_imp = pimp.run_stage1(text, run_id=run_id, text_id=text_id, demos=demos, language_code=language_code, domain_id=domain_id)
    r_lit = plit.run_stage1(text, run_id=run_id, text_id=text_id, demos=demos, language_code=language_code, domain_id=domain_id)

    for name, res in [("P-NEG", r_neg), ("P-IMP", r_imp), ("P-LIT", r_lit)]:
        trace.append(ProcessTrace(stage="stage1", agent=name, input_text=text, output=res.model.model_dump(), notes=res.meta.to_notes_str()))

    # Merge triplets with tuple_id
    candidates: List[Dict[str, Any]] = []
    idx = 0
    for label, res in [("A", r_neg), ("B", r_imp), ("C", r_lit)]:
        for t in getattr(res.model, "triplets", []) or []:
            tid = f"t{idx}"
            idx += 1
            candidates.append(_triplet_to_candidate(t, tid, label))
    conflict_flags = _compute_conflict_flags(candidates)
    validator_risks: List[Dict[str, Any]] = []

    # Episodic memory: retrieve 1x before Review (M0/M1/M2)
    memory_context = ""
    meta_memory: Dict[str, Any] = {
        "mode": "M0",
        "retrieved_k": 0,
        "write_enabled": False,
        "store_id": "",
        "retrieval_stage": "review_only",
    }
    slot_dict: Optional[Dict[str, Any]] = None
    if episodic_orchestrator and episodic_config:
        condition = (episodic_config.get("condition") or "M0").strip()
        meta_memory["mode"] = condition
        adapter_ate = _cr_adapter_for_slot(candidates)
        slot_dict, memory_mode, memory_meta = episodic_orchestrator.get_slot_payload_for_current_sample(
            text, adapter_ate, None, None, language_code=language_code
        )
        meta_memory["retrieved_k"] = memory_meta.get("retrieved_k", 0)
        meta_memory["write_enabled"] = condition == "M2"
        meta_memory["store_id"] = str(getattr(episodic_orchestrator._store, "path", ""))
        slot_name = getattr(episodic_orchestrator, "_slot_name", "DEBATE_CONTEXT__MEMORY")
        memory_context = _format_memory_context(slot_dict or {}, slot_name)

    # Review: A, B, C, Arbiter (deterministic voting)
    ra, rb, rc = ReviewAgentA(backbone), ReviewAgentB(backbone), ReviewAgentC(backbone)
    res_a = ra.run(text, candidates, conflict_flags, validator_risks, run_id=run_id, text_id=text_id, memory_context=memory_context)
    res_b = rb.run(text, candidates, conflict_flags, validator_risks, run_id=run_id, text_id=text_id, memory_context=memory_context)
    res_c = rc.run(text, candidates, conflict_flags, validator_risks, run_id=run_id, text_id=text_id, memory_context=memory_context)
    actions_a = [a.model_dump() for a in (res_a.model.review_actions or [])]
    actions_b = [a.model_dump() for a in (res_b.model.review_actions or [])]
    actions_c = [a.model_dump() for a in (res_c.model.review_actions or [])]

    # Deterministic Arbiter: Majority First, FLIP restricted, no MERGE
    all_tids = [c.get("tuple_id") for c in candidates if c.get("tuple_id")]
    actions_by_tuple = _group_actions_by_tuple(actions_a, actions_b, actions_c, all_tids)
    arb_actions_list = _arbiter_vote(actions_by_tuple)
    arb_output = ReviewOutputSchema(review_actions=[ReviewActionItem(**a) for a in arb_actions_list])
    res_arb = SimpleNamespace(model=arb_output, meta=SimpleNamespace(to_notes_str=lambda: "deterministic_vote"))

    for name, res in [("ReviewA", res_a), ("ReviewB", res_b), ("ReviewC", res_c), ("Arbiter", res_arb)]:
        trace.append(ProcessTrace(stage="review", agent=name, input_text=text, output=res.model.model_dump(), notes=res.meta.to_notes_str()))

    final_candidates = _apply_review_actions(candidates, arb_actions_list)
    final_candidates = _finalize_normalize_ref(final_candidates)

    # M2: append episode to store (if episodic_orchestrator and condition M2)
    if episodic_orchestrator and episodic_config:
        condition = (episodic_config.get("condition") or "M0").strip()
        if condition == "M2":
            adapters = _cr_adapters_for_append(candidates, final_candidates)
            conflict_resolved = bool(conflict_flags and arb_actions_list)
            moderator_summary = {"conflict_resolved": conflict_resolved}
            if conflict_resolved:
                moderator_summary["outcome_delta"] = {"conflict_resolved": True}
            episodic_orchestrator.append_episode_if_needed(
                text,
                text_id,
                adapters["stage1_ate"],
                adapters["stage1_atsa"],
                adapters["stage1_validator"],
                adapters["stage2_ate"],
                adapters["stage2_atsa"],
                adapters["stage2_validator"],
                adapters["moderator_out"],
                language_code=language_code,
                split=getattr(example, "split", "unknown"),
                moderator_summary=moderator_summary,
            )

    # Build FinalResult
    def _tup(d: Dict[str, Any]) -> Dict[str, str]:
        return {
            "aspect_ref": (d.get("aspect_ref") or ""),
            "aspect_term": (d.get("aspect_term") or ""),
            "polarity": (d.get("polarity") or "neutral"),
        }
    stage1_tuples = [_tup(c) for c in candidates]
    final_tuples = [_tup(c) for c in final_candidates]
    final_aspects = [
        {
            "aspect_term": {"term": c.get("aspect_term") or "", "span": c.get("span") or {"start": 0, "end": 0}},
            "polarity": c.get("polarity") or "neutral",
            "evidence": c.get("evidence") or "",
        }
        for c in final_candidates
    ]
    label = "neutral"
    if final_tuples:
        pols = [t.get("polarity") for t in final_tuples if t.get("polarity")]
        if all(p in ("positive", "pos") for p in pols):
            label = "positive"
        elif all(p in ("negative", "neg") for p in pols):
            label = "negative"
        elif len(set(pols)) > 1:
            label = "mixed"

    # SSOT: stage1_perspective_aste (A/B/C triplets)
    stage1_perspective_aste = {
        "P_NEG": {
            "agent_name": "P-NEG",
            "n_triplets": len(getattr(r_neg.model, "triplets", []) or []),
            "triplets": [t.model_dump() if hasattr(t, "model_dump") else t for t in (getattr(r_neg.model, "triplets", []) or [])],
        },
        "P_IMP": {
            "agent_name": "P-IMP",
            "n_triplets": len(getattr(r_imp.model, "triplets", []) or []),
            "triplets": [t.model_dump() if hasattr(t, "model_dump") else t for t in (getattr(r_imp.model, "triplets", []) or [])],
        },
        "P_LIT": {
            "agent_name": "P-LIT",
            "n_triplets": len(getattr(r_lit.model, "triplets", []) or []),
            "triplets": [t.model_dump() if hasattr(t, "model_dump") else t for t in (getattr(r_lit.model, "triplets", []) or [])],
        },
    }

    final_result = FinalResult(
        label=label,
        confidence=0.7,
        rationale="Conflict-review protocol v1",
        final_aspects=final_aspects,
        stage1_tuples=stage1_tuples,
        stage2_tuples=final_tuples,
        final_tuples=final_tuples,
        final_tuples_pre_review=stage1_tuples,
        final_tuples_post_review=final_tuples,
    )
    meta = {
        "input_text": text,
        "run_id": run_id,
        "text_id": text_id,
        "mode": "proposed",
        "protocol_mode": "conflict_review_v1",
        "case_type": getattr(example, "case_type", "unknown"),
        "split": getattr(example, "split", "unknown"),
        "language_code": language_code,
        "domain_id": domain_id,
        "stage1_perspective_aste": stage1_perspective_aste,
        "memory": meta_memory,
    }
    analysis_flags = AnalysisFlags(
        stage2_executed=True,
        review_actions=actions_a + actions_b + actions_c,
        arb_actions=arb_actions_list,
        conflict_flags=conflict_flags,
    )
    return FinalOutputSchema(
        meta=meta,
        process_trace=trace,
        analysis_flags=analysis_flags,
        final_result=final_result,
    )
