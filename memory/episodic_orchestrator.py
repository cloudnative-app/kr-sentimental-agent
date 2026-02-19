"""
EpisodicOrchestrator — 샘플마다 할 일: 토론 전 slot 주입, 샘플 후 에피소드 저장.
파이프라인에서 호출하는 진입점만 노출하여 수정 최소화.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from memory.memory_store import MemoryStore
from memory.signature_builder import SignatureBuilder
from memory.retriever import Retriever
from memory.advisory_builder import AdvisoryBuilder
from memory.injection_controller import InjectionController
from schemas.memory_v1_1 import (
    CaseSummaryV1_1,
    CorrectionV1_1,
    EpisodicMemoryEntryV1_1,
    EvaluationV1_1,
    InputSignatureV1_1,
    OutcomeDeltaV1_1,
    ProvenanceV1_1,
    RiskVectorV1_1,
    StageSnapshotV1_1,
    StageSnapshotPairV1_1,
)

# 조건 YAML 기본 경로 (프로젝트 루트 기준)
DEFAULT_CONDITIONS_PATH = Path(__file__).resolve().parent.parent / "experiments" / "configs" / "conditions_memory_v1_1.yaml"


def _load_conditions(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or DEFAULT_CONDITIONS_PATH
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        import yaml
        return yaml.safe_load(f) or {}


def _condition_flags(conditions_cfg: Dict[str, Any], condition: str) -> Dict[str, Any]:
    cond = (conditions_cfg.get("conditions") or {}).get(condition) or {}
    em = cond.get("episodic_memory") or {}
    return {
        "retrieval_execute": em.get("retrieval_execute", False),
        "injection_mask": em.get("injection_mask", True),
        "store_write": em.get("store_write", False),
    }


class EpisodicOrchestrator:
    """
    샘플마다: (1) 토론 전 — DEBATE_CONTEXT__MEMORY 슬롯 생성 후 debate_context에 병합,
              (2) 샘플 끝 — store_write 시 에피소드 1건 구성 후 append.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        config: { "condition": "C1"|"C2"|"C2_silent"|"C2_eval_only", optional "store_path", "topk", "slot_name", "conditions_path" }
        """
        self.condition = (config.get("condition") or "C1").strip()
        if self.condition not in ("C1", "C2", "C2_silent", "C2_eval_only", "M0", "M1", "M2"):
            self.condition = "C1"
        cond_path = config.get("conditions_path")
        conditions_cfg = _load_conditions(Path(cond_path) if cond_path else None)
        self._flags = _condition_flags(conditions_cfg, self.condition)
        g = conditions_cfg.get("global") or {}
        g_em = g.get("episodic_memory") or {}
        store_cfg = g_em.get("store") or {}
        retrieval_cfg = g_em.get("retrieval") or {}
        io_cfg = g.get("io") or {}
        store_path = config.get("store_path") or store_cfg.get("path") or "memory/episodic_store.jsonl"
        topk = config.get("topk") or retrieval_cfg.get("topk") or 3
        slot_name = config.get("slot_name") or io_cfg.get("slot_memory_name") or "DEBATE_CONTEXT__MEMORY"
        self._store = MemoryStore(
            store_path,
            forbid_raw_text=store_cfg.get("forbid_raw_text", True),
            keep_last_n=store_cfg.get("prune", {}).get("keep_last_n", 5000),
            prune_enabled=store_cfg.get("prune", {}).get("enabled", True),
            prune_strategy=store_cfg.get("prune", {}).get("strategy", "fifo"),
        )
        self._signature_builder = SignatureBuilder()
        self._retriever = Retriever(
            mode=retrieval_cfg.get("mode", "signature_lexical"),
            topk=topk,
            require_same_language=True,
            require_structure_overlap=True,
        )
        self._advisory_builder = AdvisoryBuilder()
        self._injection = InjectionController(slot_memory_name=slot_name, topk=topk)
        self._slot_name = slot_name
        self._episode_counter = 0
        self._selective_storage_recent_n = int(
            store_cfg.get("selective_storage_recent_n") or g_em.get("selective_storage_recent_n") or 200
        )

    def get_slot_payload_for_current_sample(
        self,
        text: str,
        stage1_ate: Any,
        stage1_atsa: Any,
        stage1_validator: Any,
        language_code: str = "unknown",
    ) -> Tuple[Optional[Dict[str, Any]], str, Dict[str, Any]]:
        """
        토론 전 호출. (slot_dict, memory_mode, memory_meta) 반환.
        memory_meta: retrieved_k, retrieved_ids, exposed_to_debate (C2만 True).
        C3(retrieval-only): retrieval은 수행(비용/지연 유지)하되 debate prompt에는 넣지 않음.
        C2_silent: retrieval_execute=True, injection_mask=True → slot은 생성하나 supervisor에서 context에 미병합.
        """
        retrieval_execute = self._flags.get("retrieval_execute", False)
        injection_mask = self._flags.get("injection_mask", True)
        num_aspects = len(getattr(stage1_ate, "aspects", []) or [])
        query_sig = self._signature_builder.build(text, language=language_code, num_aspects=num_aspects)
        advisories = []
        retrieved: List[Dict[str, Any]] = []
        blocked_stats: Dict[str, Any] = {}
        if retrieval_execute:
            store_entries = self._store.load()
            retrieved = self._retriever.retrieve(store_entries, query_sig, query_lexical=None)
            if not injection_mask:
                advisories, blocked_stats = self._advisory_builder.build_from_episodes(retrieved)
        slot_json = self._injection.build_slot_payload(self.condition, advisories if not injection_mask else [])
        slot_dict = json.loads(slot_json)
        memory_mode = "off" if self.condition == "C1" else ("on" if self.condition == "C2" else "silent")
        # C2만 debate prompt에 memory 노출; C1/C2_silent/C2_eval_only는 노출 안 함
        exposed_to_debate = self.condition == "C2"
        memory_meta: Dict[str, Any] = {
            "retrieved_k": len(retrieved),
            "retrieved_ids": [e.get("episode_id") or "" for e in retrieved if e.get("episode_id")],
            "exposed_to_debate": exposed_to_debate,
        }
        # OPFB: Scorecard/Triptych용 블록 로그 3개
        memory_meta["memory_blocked_episode_n"] = blocked_stats.get("memory_blocked_episode_n", 0)
        memory_meta["memory_blocked_advisory_n"] = blocked_stats.get("memory_blocked_advisory_n", 0)
        memory_meta["memory_block_reason"] = blocked_stats.get("memory_block_reason") or ""
        return (slot_dict, memory_mode, memory_meta)

    def append_episode_if_needed(
        self,
        text: str,
        text_id: str,
        stage1_ate: Any,
        stage1_atsa: Any,
        stage1_validator: Any,
        stage2_ate: Any,
        stage2_atsa: Any,
        stage2_validator: Any,
        moderator_out: Any,
        language_code: str = "unknown",
        split: str = "unknown",
        moderator_summary: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Optional[str], List[str]]:
        """샘플 끝 호출. store_write일 때만 에피소드 1건 구성 후 selective gate 통과 시 append.
        moderator_summary: optional { action_taken, outcome_delta, override_applied, override_success, override_harm } for risk→action mapping.
        Returns: (store_decision, store_skip_reason, store_reason_tags).
        """
        if not self._flags.get("store_write", False):
            return ("skipped", "store_write_disabled", [])
        self._episode_counter += 1
        episode_id = f"epi_{self._episode_counter:06d}"
        num_aspects = len(getattr(stage1_ate, "aspects", []) or [])
        input_sig = self._signature_builder.build(text, language=language_code, num_aspects=num_aspects)
        risks1 = getattr(stage1_validator, "structural_risks", []) or []
        proposals1 = getattr(stage1_validator, "correction_proposals", []) or []
        aspects1 = getattr(stage1_ate, "aspects", []) or []
        sents1 = getattr(stage1_atsa, "aspect_sentiments", []) or []
        aspects_final = getattr(stage2_ate, "aspects", []) or []
        sents_final = getattr(stage2_atsa, "aspect_sentiments", []) or []
        symptom = (risks1[0].description if risks1 else "") or "none"
        rationale = (proposals1[0].rationale if proposals1 else "")[:500] or "No correction"
        case_summary = CaseSummaryV1_1(
            target_aspect_type=(aspects1[0].term if aspects1 else "") or "",
            symptom=symptom,
            rationale_summary=rationale,
        )
        polarities1 = {}
        for s in sents1:
            t = (getattr(s.aspect_term, "term", None) if getattr(s, "aspect_term", None) else None) or ""
            if t:
                polarities1[t] = getattr(s, "polarity", "neutral") or "neutral"
        polarities_final = {}
        for s in sents_final:
            t = (getattr(s.aspect_term, "term", None) if getattr(s, "aspect_term", None) else None) or ""
            if t:
                polarities_final[t] = getattr(s, "polarity", "neutral") or "neutral"
        conf1 = getattr(stage1_atsa, "confidence", 0.5) or 0.5
        conf_final = getattr(stage2_atsa, "confidence", 0.5) or 0.5
        stage_snapshot = StageSnapshotPairV1_1(
            stage1=StageSnapshotV1_1(
                aspects_norm=[getattr(a, "term", "") or "" for a in aspects1],
                polarities=polarities1,
                confidence=conf1,
            ),
            final=StageSnapshotV1_1(
                aspects_norm=[getattr(a, "term", "") or "" for a in aspects_final],
                polarities=polarities_final,
                confidence=conf_final,
            ),
        )
        corrective = (proposals1[0].rationale if proposals1 else "")[:400] or "No correction"
        correction = CorrectionV1_1(
            corrective_principle=corrective,
            applicable_conditions=[corrective] if corrective != "No correction" else ["none"],
        )
        # severity weight: high=3, mid=2, low=1 (align with structural_error_aggregator.residual_risk_severity)
        _sev_weight = {"high": 3.0, "mid": 2.0, "low": 1.0}
        def _severity_sum(risks: list) -> float:
            total = 0.0
            for r in risks:
                sev = (getattr(r, "severity", None) or (r.get("severity") if isinstance(r, dict) else None) or "mid")
                total += _sev_weight.get((str(sev)).lower(), 2.0)
            return total
        tags1 = [getattr(r, "type", "") or (r.get("type", "") if isinstance(r, dict) else "") for r in risks1]
        risk_before = RiskVectorV1_1(severity_sum=_severity_sum(risks1), tags=tags1)
        risks2 = getattr(stage2_validator, "structural_risks", []) or []
        if isinstance(stage2_validator, dict):
            risks2 = stage2_validator.get("structural_risks") or []
        tags2 = [getattr(r, "type", "") or (r.get("type", "") if isinstance(r, dict) else "") for r in risks2]
        risk_after = RiskVectorV1_1(severity_sum=_severity_sum(risks2), tags=tags2)
        ms = moderator_summary or {}
        evaluation = EvaluationV1_1(
            risk_before=risk_before,
            risk_after=risk_after,
            override_applied=bool(ms.get("override_applied", False)),
            override_success=bool(ms.get("override_success", False)),
            override_harm=bool(ms.get("override_harm", False)),
            arbiter_reason_code=(ms.get("arbiter_reason_code") or "").strip(),
            facet_dissent=ms.get("facet_dissent") or [],
        )
        provenance = ProvenanceV1_1(
            created_from_split=split or "",
            used_in_eval=False,
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.1",
            has_gold=False,
        )
        episode_type = "harm" if len(risks1) > 0 else "success"
        error_cats = list(set(tags1)) if tags1 else ["none"]
        # Risk type for content-strengthened memory: L3 (structural polarity), conflict, implicit
        risk_type_val: Optional[str] = None
        l3_tags = {"NEGATION_SCOPE", "CONTRAST_SCOPE", "POLARITY_MISMATCH", "NEGATION", "CONTRAST", "IRONY"}
        if any((getattr(r, "type", "") or "").upper().replace(" ", "_") in l3_tags for r in risks1):
            risk_type_val = "L3"
        elif len(set(polarities1.values()) - {"neutral", "unknown"}) > 1 and len(polarities1) >= 2:
            risk_type_val = "conflict"
        elif "implicit_opinion" in error_cats or any(getattr(s, "is_implicit", False) for s in sents1):
            risk_type_val = "implicit"
        action_taken_val = ms.get("action_taken")
        outcome_delta_val: Optional[OutcomeDeltaV1_1] = None
        if ms.get("outcome_delta"):
            od = ms["outcome_delta"]
            outcome_delta_val = OutcomeDeltaV1_1(
                delta_f1=od.get("delta_f1"),
                conflict_resolved=od.get("conflict_resolved"),
            )
        entry = EpisodicMemoryEntryV1_1(
            schema_version="1.1",
            episode_id=episode_id,
            episode_type=episode_type,
            error_category=error_cats,
            input_signature=input_sig,
            case_summary=case_summary,
            stage_snapshot=stage_snapshot,
            correction=correction,
            evaluation=evaluation,
            provenance=provenance,
            risk_type=risk_type_val,
            action_taken=action_taken_val,
            outcome_delta=outcome_delta_val,
        )
        # Selective storage gate: store only on failure_asset, utility, or novelty
        reason_tags: List[str] = []
        failure_asset = risk_type_val in ("L3", "conflict") or (risk_before.severity_sum >= 3.0)
        utility = evaluation.override_applied and (
            evaluation.override_success or evaluation.override_harm or outcome_delta_val is not None
        )
        store_entries = self._store.load()
        recent = store_entries[-self._selective_storage_recent_n:] if len(store_entries) > self._selective_storage_recent_n else store_entries

        def _fp(ent: Dict[str, Any]) -> Tuple[Any, ...]:
            sig = ent.get("input_signature") or {}
            ev = ent.get("evaluation") or {}
            rb = ev.get("risk_before") or {}
            cs = ent.get("case_summary") or {}
            return (
                sig.get("language", ""),
                tuple(sorted(sig.get("detected_structure") or [])),
                tuple(sorted(rb.get("tags") or [])),
                cs.get("symptom", ""),
            )

        current_fp = (
            input_sig.language,
            tuple(sorted(input_sig.detected_structure or [])),
            tuple(sorted(risk_before.tags or [])),
            case_summary.symptom or "",
        )
        recent_fps = {_fp(e) for e in recent}
        novelty = current_fp not in recent_fps
        if failure_asset:
            reason_tags.append("failure_asset")
        if utility:
            reason_tags.append("utility")
        if novelty:
            reason_tags.append("novelty")
        if reason_tags:
            self._store.append(entry)
            return ("stored", None, reason_tags)
        return ("skipped", "no_gate_passed", [])
