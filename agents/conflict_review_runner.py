"""Conflict-review protocol v1 runner: produces FinalOutputSchema from perspective + review flow."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from tools.data_tools import InternalExample
from tools.llm_runner import run_structured, StructuredResult
from tools.backbone_client import BackboneClient
from agents.prompts import load_prompt
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
from metrics.opinion_validation import (
    validate_aspect_ref,
    has_english_in_term,
    is_likely_opinion_word,
)


def _triplet_to_candidate(t: ASTETripletItem, tuple_id: str, origin_agent: str) -> Dict[str, Any]:
    aspect_term = (t.aspect_term or "").strip()
    aspect_ref = (t.aspect_ref or "").strip() if t.aspect_ref else ""
    conf = getattr(t, "confidence", 0.5) or 0.5

    invalid_ref_flag = bool(aspect_ref and not validate_aspect_ref(aspect_ref))
    invalid_language_flag = has_english_in_term(aspect_term)
    invalid_target_flag = is_likely_opinion_word(aspect_term)

    if invalid_ref_flag:
        conf = conf * 0.5
    if invalid_language_flag:
        conf = conf * 0.5
    if invalid_target_flag:
        conf = conf * 0.5

    return {
        "tuple_id": tuple_id,
        "aspect_term": t.aspect_term,
        "aspect_ref": t.aspect_ref,
        "polarity": t.polarity,
        "evidence": t.evidence,
        "span": t.span,
        "origin_agent": origin_agent,
        "confidence": conf,
        "invalid_ref_flag": invalid_ref_flag,
        "invalid_language_flag": invalid_language_flag,
        "invalid_target_flag": invalid_target_flag,
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


def _normalize_ote(s: str) -> str:
    """Normalize OTE for similarity: strip, lower, remove extra spaces/special chars."""
    s = (s or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _char_ngrams(s: str, n: int = 3) -> set:
    """Return set of character n-grams."""
    s = _normalize_ote(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def _ote_similarity(a: str, b: str, theta: float = 0.6) -> bool:
    """True if OTE similarity >= theta. Uses char 3-gram Jaccard or SequenceMatcher ratio."""
    na, nb = _normalize_ote(a), _normalize_ote(b)
    if not na or not nb:
        return False
    jaccard = 0.0
    ga, gb = _char_ngrams(na, 3), _char_ngrams(nb, 3)
    if ga or gb:
        jaccard = len(ga & gb) / len(ga | gb) if (ga | gb) else 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    return jaccard >= theta or ratio >= theta


def _detect_granularity_overlap(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    동일 polarity + 동일 attribute에서
    상위 ref(제품 전체#X)와 하위 ref(본품#X, 패키지·구성품#X)가 동시 존재하면 flag.
    """
    UPPER_ENTITIES = frozenset({"제품 전체"})

    attr_groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        ref = (c.get("aspect_ref") or "").strip()
        pol = c.get("polarity")
        if not ref or not pol or "#" not in ref:
            continue
        parts = ref.split("#", 1)
        entity = (parts[0] or "").strip()
        attr = (parts[1] or "").strip()
        attr_groups[(attr, pol)].append({
            "tuple_id": c.get("tuple_id"),
            "entity": entity,
            "ref": ref,
        })

    flags: List[Dict[str, Any]] = []
    for (attr, polarity), items in attr_groups.items():
        entities = {i["entity"] for i in items if i.get("entity")}
        has_upper = bool(entities & UPPER_ENTITIES)
        has_lower = bool(entities - UPPER_ENTITIES)

        if has_upper and has_lower:
            flags.append({
                "aspect_ref": "|".join(i["ref"] for i in items if i.get("ref")),
                "aspect_term": "",
                "tuple_ids": [i["tuple_id"] for i in items if i.get("tuple_id")],
                "conflict_type": "granularity_overlap_candidate",
            })
    return flags


def _compute_conflict_flags(
    candidates: List[Dict[str, Any]],
    conflict_mode: str = "primary_secondary",
    semantic_conflict_enabled: bool = False,
) -> List[Dict[str, Any]]:
    """
    Detect conflicts. Primary: same aspect_ref with different polarity (ref-pol mismatch).
    Secondary: same aspect_term with different polarity (when ref empty or mode=primary_secondary).
    Semantic (optional): same ref + opposite polarity + similar OTE → semantic_conflict_candidate.
    conflict_mode: "primary" (ref only) | "primary_secondary" (ref + term for empty-ref tuples)
    """
    flags: List[Dict[str, Any]] = []

    # Primary: group by aspect_ref (non-empty)
    by_ref: Dict[str, List[Dict[str, Any]]] = {}
    no_ref: List[Dict[str, Any]] = []
    for c in candidates:
        ref = (c.get("aspect_ref") or "").strip()
        if ref:
            by_ref.setdefault(ref, []).append(c)
        else:
            no_ref.append(c)

    for ref, items in by_ref.items():
        pols = {i.get("polarity") for i in items if i.get("polarity")}
        if len(pols) > 1:
            flags.append({
                "aspect_ref": ref,
                "aspect_term": items[0].get("aspect_term") or ref,
                "tuple_ids": [i.get("tuple_id") for i in items],
                "conflict_type": "ref_polarity_mismatch",
            })
            # Semantic conflict candidate: same ref, opposite polarity, similar OTE
            if semantic_conflict_enabled:
                for i, c1 in enumerate(items):
                    for c2 in items[i + 1 :]:
                        p1, p2 = c1.get("polarity"), c2.get("polarity")
                        if p1 and p2 and p1 != p2:
                            t1 = (c1.get("aspect_term") or "").strip()
                            t2 = (c2.get("aspect_term") or "").strip()
                            if t1 and t2 and t1 != t2 and _ote_similarity(t1, t2):
                                flags.append({
                                    "aspect_ref": ref,
                                    "aspect_term": f"{t1}|{t2}",
                                    "tuple_ids": [c1.get("tuple_id"), c2.get("tuple_id")],
                                    "conflict_type": "semantic_conflict_candidate",
                                })
                                break

    # Secondary: term-level for tuples with empty ref (when primary_secondary)
    if conflict_mode == "primary_secondary" and no_ref:
        by_term: Dict[str, List[Dict[str, Any]]] = {}
        for c in no_ref:
            term = (c.get("aspect_term") or "").strip()
            if not term:
                continue
            by_term.setdefault(term, []).append(c)
        for term, items in by_term.items():
            pols = {i.get("polarity") for i in items if i.get("polarity")}
            if len(pols) > 1:
                flags.append({
                    "aspect_ref": "",
                    "aspect_term": term,
                    "tuple_ids": [i.get("tuple_id") for i in items],
                    "conflict_type": "term_polarity_mismatch",
                })

    flags.extend(_detect_granularity_overlap(candidates))
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
# DROP justified: when 1 FLIP + 1 DROP + 1 KEEP, prefer DROP if reason in this set.
_DROP_JUSTIFIED = frozenset({"WEAK_EVIDENCE", "REDUNDANT_UPPER_REF"})
# Facet priority: conflict_type/reason -> preferred actor (C = P-LIT). ARB excluded from minority checks.
_FACET_PRIORITY: Dict[str, str] = {
    "granularity_overlap_candidate": "C",
    "REDUNDANT_UPPER_REF": "C",
}


def _is_incomplete_revise(action_item: Any) -> tuple[bool, str]:
    """
    Check if FLIP/MERGE action is incomplete (missing required fields).
    Returns (True, "FORMAT_INCOMPLETE") if incomplete, else (False, "").
    """
    if not action_item or not isinstance(action_item, dict):
        return (False, "")
    atype = (action_item.get("action_type") or action_item.get("type") or "KEEP").strip().upper()
    if atype not in {"FLIP", "MERGE"}:
        return (False, "")
    tids = action_item.get("target_tuple_ids") or []
    if not tids:
        return (True, "FORMAT_INCOMPLETE")
    nv = action_item.get("new_value") or {}
    if atype == "FLIP":
        if not (isinstance(nv, dict) and (nv.get("polarity") or "").strip()):
            return (True, "FORMAT_INCOMPLETE")
    elif atype == "MERGE":
        if not (isinstance(nv, dict) and (nv.get("normalized_ref") or "").strip()):
            return (True, "FORMAT_INCOMPLETE")
    return (False, "")


def _run_recheck(
    backbone: BackboneClient,
    text: str,
    text_id: str,
    run_id: str,
    mode: str,
    tid: str,
    conflict_type: str,
    candidate_tuples: List[Dict[str, Any]],
    prior_votes: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Run targeted re-check for one tuple. Returns single action dict (actor=ARB) or None on failure.
    """
    raw = load_prompt("review_recheck_action")
    if "---USER---" in raw:
        system_part, user_tmpl = raw.split("---USER---", 1)
        system_part = system_part.strip()
        user_tmpl = user_tmpl.strip()
    else:
        system_part = raw.strip()
        user_tmpl = ""
    candidate_tuples_json = json.dumps(candidate_tuples, ensure_ascii=False)
    prior_votes_json = json.dumps(prior_votes, ensure_ascii=False)
    user_text = user_tmpl.replace("{text}", text)
    user_text = user_text.replace("{conflict_type}", conflict_type)
    user_text = user_text.replace("{candidate_tuples_json}", candidate_tuples_json)
    user_text = user_text.replace("{prior_votes_json}", prior_votes_json)
    try:
        res = run_structured(
            backbone=backbone,
            system_prompt=system_part,
            user_text=user_text,
            schema=ReviewOutputSchema,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="ReviewRecheck",
            mode=mode,
            use_mock=(getattr(backbone, "provider", "mock") == "mock"),
        )
        actions = res.model.review_actions or []
        if not actions:
            return None
        a = actions[0]
        out = {
            "action_type": (a.action_type or "KEEP").strip().upper(),
            "target_tuple_ids": list(a.target_tuple_ids or [tid]),
            "new_value": (a.new_value or {}) if isinstance(a.new_value, dict) else {},
            "reason_code": (a.reason_code or "").strip(),
            "actor": "ARB",
        }
        if out["action_type"] == "MERGE":
            out["action_type"] = "KEEP"
        return out
    except Exception:
        return None


def _arbiter_vote(
    actions_by_tuple: Dict[str, Dict[str, Any]],
    conflict_flags: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic Arbiter: No A>B>C authority. Aggregation by majority and reason_code.

    Rule 1: ≥2 identical → adopt; unless minority actor matches _FACET_PRIORITY → FLAG (FACET_MINORITY_SIGNAL).
    Rule 2: All disagree → KEEP + FLAG; granularity tie → REDUNDANT_REF_UNCERTAIN.
    Rule 3: 1 FLIP + 1 DROP + 1 KEEP: FLIP structural → FLIP; DROP justified → DROP; else FLAG.
    Rule 4: Arbiter does NOT output MERGE (moved to Finalize).
    """
    from collections import Counter

    tid_to_conflict: Dict[str, str] = {}
    for f in conflict_flags or []:
        for tid in f.get("tuple_ids", []):
            tid_to_conflict[tid] = (f.get("conflict_type") or "").strip()

    output: List[Dict[str, Any]] = []
    emitted_tids: set = set()
    for tid, acts in actions_by_tuple.items():
        arb_recheck = acts.get("ARB")
        if arb_recheck:
            tids_in_action = arb_recheck.get("target_tuple_ids") or [tid]
            if emitted_tids & set(tids_in_action):
                continue
            emitted_tids.update(tids_in_action)
            out = {
                "action_type": (arb_recheck.get("action_type") or "KEEP").strip().upper(),
                "target_tuple_ids": tids_in_action,
                "actor": "ARB",
                "reason_code": (arb_recheck.get("reason_code") or "").strip(),
            }
            if out["action_type"] == "FLIP" and arb_recheck.get("new_value"):
                out["new_value"] = arb_recheck.get("new_value")
            output.append(out)
            continue

        votes_raw = [acts.get("A"), acts.get("B"), acts.get("C")]
        actor_keys = ["A", "B", "C"]
        votes = [_norm_atype(v) if v else "KEEP" for v in votes_raw]
        votes_adopted = [v if v != "MERGE" else "KEEP" for v in votes]

        cnt = Counter(votes_adopted)
        most_common = cnt.most_common(1)[0] if cnt else ("KEEP", 0)
        majority_action, majority_count = most_common[0], most_common[1]

        # Minority: actor whose vote differs from majority
        minority_actors: List[str] = []
        minority_actions: List[Dict[str, Any]] = []
        for i, (k, v) in enumerate(zip(actor_keys, votes_raw)):
            atype = votes_adopted[i] if i < len(votes_adopted) else "KEEP"
            if atype != majority_action and v:
                minority_actors.append(k)
                minority_actions.append(v)

        conflict_type = tid_to_conflict.get(tid, "")
        preferred = _FACET_PRIORITY.get(conflict_type)

        add_flag = False
        flag_reason = "POLARITY_UNCERTAIN"

        if majority_count >= 2:
            # Rule 1: facet-weighted minority protection
            if preferred and minority_actors and preferred in minority_actors:
                final_action = "FLAG"
                add_flag = True
                flag_reason = "FACET_MINORITY_SIGNAL"
            else:
                final_action = majority_action
        else:
            # No majority
            if set(votes_adopted) == {"FLIP", "DROP", "KEEP"}:
                # Rule 3
                flip_action = next((v for v in votes_raw if v and _norm_atype(v) == "FLIP"), None)
                drop_action = next((v for v in votes_raw if v and _norm_atype(v) == "DROP"), None)
                flip_reason = (flip_action.get("reason_code") or "").strip().upper() if flip_action else ""
                drop_reason = (drop_action.get("reason_code") or "").strip().upper() if drop_action else ""

                if flip_reason and flip_reason in _STRUCTURAL_REASON_CODES:
                    final_action = "FLIP"
                    add_flag = False
                elif drop_reason and drop_reason in _DROP_JUSTIFIED:
                    final_action = "DROP"
                    add_flag = False
                else:
                    final_action = "FLAG"
                    add_flag = True
                    if conflict_type == "granularity_overlap_candidate":
                        flag_reason = "REDUNDANT_REF_UNCERTAIN"
                    else:
                        flag_reason = "TIE_UNRESOLVED"
            else:
                # Rule 2: all disagree
                final_action = "FLAG"
                add_flag = True
                if conflict_type == "granularity_overlap_candidate":
                    flag_reason = "REDUNDANT_REF_UNCERTAIN"
                else:
                    flag_reason = "POLARITY_UNCERTAIN"

        out: Dict[str, Any] = {
            "action_type": final_action,
            "target_tuple_ids": [tid],
            "actor": "ARB",
            "reason_code": flag_reason if add_flag else "",
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
    """P1: No-op. aspect_ref를 덮어쓰지 않음. 원본 보존(SSOT). 평가는 term-only이므로 ref 변경이 F1에 영향 없음."""
    return list(candidates)


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
    conflict_mode: str = "primary_secondary",
    semantic_conflict_enabled: bool = False,
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
    invalid_ref_count = invalid_language_count = invalid_target_count = 0
    idx = 0
    for label, res in [("A", r_neg), ("B", r_imp), ("C", r_lit)]:
        for t in getattr(res.model, "triplets", []) or []:
            tid = f"t{idx}"
            idx += 1
            c = _triplet_to_candidate(t, tid, label)
            if c.get("invalid_ref_flag"):
                invalid_ref_count += 1
            if c.get("invalid_language_flag"):
                invalid_language_count += 1
            if c.get("invalid_target_flag"):
                invalid_target_count += 1
            candidates.append(c)
    conflict_flags = _compute_conflict_flags(
        candidates,
        conflict_mode=conflict_mode,
        semantic_conflict_enabled=semantic_conflict_enabled,
    )
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
        meta_memory["write_enabled"] = getattr(episodic_orchestrator, "_flags", {}).get("store_write", False)
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

    tid_to_conflict: Dict[str, str] = {}
    for f in conflict_flags or []:
        for tid in f.get("tuple_ids", []):
            tid_to_conflict[tid] = (f.get("conflict_type") or "").strip()

    recheck_count = 0
    recheck_done_for_conflict: set = set()
    for tid in all_tids:
        acts = actions_by_tuple.get(tid, {})
        need_recheck = False
        for v in [acts.get("A"), acts.get("B"), acts.get("C")]:
            if v and _is_incomplete_revise(v)[0]:
                need_recheck = True
                break
        if not need_recheck:
            conflict_type = tid_to_conflict.get(tid, "")
            if conflict_type == "granularity_overlap_candidate":
                votes_raw = [acts.get("A"), acts.get("B"), acts.get("C")]
                votes = [_norm_atype(v) if v else "KEEP" for v in votes_raw]
                votes_adopted = [v if v != "MERGE" else "KEEP" for v in votes]
                cnt = Counter(votes_adopted)
                majority_count = cnt.most_common(1)[0][1] if cnt else 0
                if majority_count < 2:
                    need_recheck = True
        if need_recheck:
            flag = next((f for f in (conflict_flags or []) if tid in (f.get("tuple_ids") or [])), None)
            tuple_ids_in_conflict = tuple(sorted(flag.get("tuple_ids") or [tid])) if flag else (tid,)
            conflict_key = tuple_ids_in_conflict
            if conflict_key in recheck_done_for_conflict:
                continue
            conflict_type = tid_to_conflict.get(tid, "")
            candidate_tuples = [c for c in candidates if c.get("tuple_id") in tuple_ids_in_conflict]
            prior_votes = {"A": acts.get("A"), "B": acts.get("B"), "C": acts.get("C")}
            arb_action = _run_recheck(
                backbone, text, text_id, run_id, "proposed",
                tid, conflict_type, candidate_tuples, prior_votes,
            )
            if arb_action:
                recheck_done_for_conflict.add(conflict_key)
                recheck_count += 1
                for t in tuple_ids_in_conflict:
                    if t in actions_by_tuple:
                        actions_by_tuple[t]["ARB"] = arb_action

    arb_actions_list = _arbiter_vote(actions_by_tuple, conflict_flags)
    arb_output = ReviewOutputSchema(review_actions=[ReviewActionItem(**a) for a in arb_actions_list])
    res_arb = SimpleNamespace(model=arb_output, meta=SimpleNamespace(to_notes_str=lambda: "deterministic_vote"))

    for name, res in [("ReviewA", res_a), ("ReviewB", res_b), ("ReviewC", res_c), ("Arbiter", res_arb)]:
        trace.append(ProcessTrace(stage="review", agent=name, input_text=text, output=res.model.model_dump(), notes=res.meta.to_notes_str()))

    final_candidates = _apply_review_actions(candidates, arb_actions_list)
    final_candidates = _finalize_normalize_ref(final_candidates)

    # M1/M2: append episode to store when store_write enabled
    if episodic_orchestrator and episodic_config:
        store_write = getattr(episodic_orchestrator, "_flags", {}).get("store_write", False)
        if store_write:
            adapters = _cr_adapters_for_append(candidates, final_candidates)
            conflict_resolved = bool(conflict_flags and arb_actions_list)
            moderator_summary = {"conflict_resolved": conflict_resolved}
            if conflict_resolved:
                moderator_summary["outcome_delta"] = {"conflict_resolved": True}
            # arbiter_reason_code, facet_dissent for EvaluationV1_1
            arb_reasons = [a.get("reason_code") or "" for a in arb_actions_list if (a.get("reason_code") or "").strip()]
            moderator_summary["arbiter_reason_code"] = arb_reasons[0] if arb_reasons else ""
            facet_dissent_list: List[Dict[str, Any]] = []
            for a in arb_actions_list:
                tids = a.get("target_tuple_ids") or []
                final_atype = (a.get("action_type") or "").strip().upper()
                for tid in tids:
                    acts = actions_by_tuple.get(tid, {})
                    votes_raw = [acts.get("A"), acts.get("B"), acts.get("C")]
                    actor_keys = ["A", "B", "C"]
                    for i, (k, v) in enumerate(zip(actor_keys, votes_raw)):
                        if not v:
                            continue
                        atype = (v.get("action_type") or v.get("type") or "KEEP").strip().upper()
                        if atype == "MERGE":
                            atype = "KEEP"
                        if atype != final_atype:
                            facet_dissent_list.append({
                                "actor": k,
                                "action_type": atype,
                                "reason_code": (v.get("reason_code") or "").strip(),
                            })
            moderator_summary["facet_dissent"] = facet_dissent_list
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
        "recheck_triggered_count": recheck_count,
        "case_type": getattr(example, "case_type", "unknown"),
        "split": getattr(example, "split", "unknown"),
        "language_code": language_code,
        "domain_id": domain_id,
        "stage1_perspective_aste": stage1_perspective_aste,
        "memory": meta_memory,
        "invalid_ref_count": invalid_ref_count,
        "invalid_language_count": invalid_language_count,
        "invalid_target_count": invalid_target_count,
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
