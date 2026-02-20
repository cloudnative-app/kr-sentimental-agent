from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import re

from schemas import (
    AnalysisFlags,
    FinalOutputSchema,
    FinalResult,
    ProcessTrace,
    AspectExtractionStage1Schema,
    AspectExtractionStage2Schema,
    AspectExtractionItem,
    AspectSentimentStage1Schema,
    AspectSentimentStage2Schema,
    AspectSentimentItem,
    AspectTerm,
    Span,
    StructuralValidatorStage1Schema,
    StructuralValidatorStage2Schema,
    StructuralRiskItem,
    ATEOutput,
    ATSAOutput,
    ValidatorOutput,
    canonicalize_polarity,
    canonicalize_polarity_with_repair,
)
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample
from tools.llm_runner import StructuredResult, _log_error, default_errors_path
from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from agents.debate_orchestrator import DebateOrchestrator
from tools.pattern_loader import load_patterns
from memory.episodic_orchestrator import EpisodicOrchestrator
from memory.advisory_injection_gate import (
    should_inject_advisory_with_reason,
    should_inject_memory_for_stage2_with_reason,
)
from pathlib import Path
from metrics.eval_tuple import tuples_from_list, tuples_to_list_of_dicts


class PolarityContractViolation(Exception):
    """CONTRACT-SUP-1: final_tuples polarity must be in {positive, negative, neutral}; no silent fallback."""

    def __init__(self, text_id: str, aspect: str, actual_polarity: Any, message: str = ""):
        self.text_id = text_id
        self.aspect = aspect
        self.actual_polarity = actual_polarity
        super().__init__(f"[CONTRACT-SUP-1] text_id={text_id} aspect={aspect} polarity={actual_polarity!r} {message}".strip())


def _assert_final_tuples_polarity_contract(
    final_tuples: List[Dict[str, Any]],
    text_id: str,
) -> None:
    """
    CONTRACT-SUP-1: Every final_tuple polarity must be in {positive, negative, neutral}.
    No silent fallback (raw positive → neutral). Raises PolarityContractViolation on violation.
    """
    VALID = {"positive", "negative", "neutral"}
    for t in final_tuples or []:
        if not isinstance(t, dict):
            continue
        pol = t.get("polarity") or t.get("label")
        aspect = (t.get("aspect_term") or t.get("aspect_ref") or "")
        if isinstance(aspect, dict):
            aspect = aspect.get("term") or aspect.get("aspect_ref") or ""
        aspect = (aspect or "").strip() or "(implicit)"
        if pol is None or (isinstance(pol, str) and not pol.strip()):
            raise PolarityContractViolation(
                text_id, aspect, pol,
                "missing polarity (neutral ≠ missing)",
            )
        p = (pol if isinstance(pol, str) else str(pol)).strip().lower()
        if p in ("pos", "positive"):
            p = "positive"
        elif p in ("neg", "negative"):
            p = "negative"
        elif p in ("neu", "neutral"):
            p = "neutral"
        if p not in VALID:
            raise PolarityContractViolation(
                text_id, aspect, pol,
                f"polarity not in {VALID}",
            )


class SupervisorAgent:
    """
    ABSA flow (Stage2 always on):
      Stage1: ATE + ATSA (independent) + Validator
      Stage2: ATE + ATSA + Validator (re-analysis, always executed)
      Moderator: aggregate to final result
    """

    def __init__(
        self,
        backbone: Optional[BackboneClient] = None,
        config: Optional[Dict] = None,
        ate_agent: Optional[ATEAgent] = None,
        atsa_agent: Optional[ATSAAgent] = None,
        validator: Optional[ValidatorAgent] = None,
        moderator: Optional[Moderator] = None,
        run_id: str | None = None,
    ):
        self.backbone = backbone or BackboneClient()
        self.config = config or {}
        self.protocol_mode = (self.config.get("protocol_mode") or "legacy").strip().lower()
        self.enable_stage2 = self.config.get("enable_stage2", True)
        self.enable_validator = self.config.get("enable_validator", True)
        self.enable_moderator = self.config.get("enable_moderator", True)
        self.enable_debate = self.config.get("enable_debate", True)
        self.enable_debate_override = self.config.get("enable_debate_override", True)
        self.debate_override_cfg, self._override_profile_id, self._override_cfg_source = self._load_debate_override_cfg(
            self.config.get("debate_override"), self.config.get("override_profile")
        )
        # C2 ablation: cap memory injection chars (0 = no inject, 300/600/1000 = max chars)
        self.memory_prompt_injection_chars_cap = self.config.get("memory_prompt_injection_chars_cap")
        self.run_id = run_id or "run"
        self.ate_agent = ate_agent or ATEAgent(self.backbone)
        self.atsa_agent = atsa_agent or ATSAAgent(self.backbone)
        self.validator = validator or ValidatorAgent(self.backbone)
        self.moderator = moderator or Moderator()
        self.debate = DebateOrchestrator(self.backbone, config=self.config.get("debate"))
        self._pattern_cache: dict[str, dict] = {}
        self._override_stats: dict = {
            "applied": 0,
            "skipped_low_signal": 0,
            "skipped_neutral_only": 0,
            "skipped_conflict": 0,
            "skipped_already_confident": 0,
            "override_candidate": False,
            "override_applied": False,
            "override_effect_applied": False,
            "override_reason": "low_signal",
            "override_hint_invalid_total": 0,
            "override_hint_repair_total": 0,
            "skipped_conflict_reasons": {
                "action_ambiguity": 0,
                "L3_conservative": 0,
                "implicit_soft_only": 0,
                "low_confidence": 0,
                "contradictory_memory": 0,
            },
        }
        episodic_cfg = self.config.get("episodic_memory")
        self._episodic_orchestrator: Optional[EpisodicOrchestrator] = EpisodicOrchestrator(episodic_cfg) if episodic_cfg else None
        self._override_gate_records: List[Dict[str, Any]] = []
        self._override_sample_outcomes: Dict[str, Dict[str, Any]] = {}
        self._override_sample_idx = -1
        self._last_override_run_id: Optional[str] = None

    @staticmethod
    def _term_str(sent: AspectSentimentItem) -> str:
        """Return the aspect surface-form term string from an AspectSentimentItem."""
        return (sent.aspect_term.term if sent.aspect_term else "") or ""

    def _patterns(self, language_code: str) -> dict:
        lang = (language_code or "unknown").lower()
        if lang not in self._pattern_cache:
            patterns, _, _ = load_patterns(lang)
            self._pattern_cache[lang] = patterns or {}
        return self._pattern_cache.get(lang, {})

    def _run_stage1(
        self,
        text: str,
        trace: list[ProcessTrace],
        text_id: str,
        demos: list[str] | None = None,
        *,
        language_code: str = "unknown",
        domain_id: str = "unknown",
    ) -> Dict[str, object]:
        ate_result = self.ate_agent.run_stage1(
            text,
            run_id=self.run_id,
            text_id=text_id,
            mode="proposed",
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
        )
        # Post-process ATE aspects: strip topic particles, enforce contrast rule, PJ1 substring enforcement
        ate_aspects = getattr(ate_result.model, "aspects", [])
        ate_aspects = self._clean_aspects(text, ate_aspects, language_code=language_code, )
        ate_aspects = self._enforce_contrast_min_aspects(text, ate_aspects, language_code=language_code)
        ate_aspects, ate_dropped_substring = self._enforce_substring_aspects(text, ate_aspects)
        ate_result.model.aspects = ate_aspects
        if ate_dropped_substring:
            for item in ate_dropped_substring:
                item["rejection_reason"] = "aspect_not_substring"
            trace.append(ProcessTrace(stage="stage1_ate", agent="ATE", input_text=text, output={"dropped_substring": ate_dropped_substring}, notes="PJ1: dropped aspects whose term is not a substring of text"))

        trace.append(ProcessTrace(
            stage="stage1", agent="ATE", input_text=text,
            output=ate_result.model.model_dump(),
            notes=ate_result.meta.to_notes_str()
        ))

        atsa_result = self.atsa_agent.run_stage1(
            text,
            run_id=self.run_id,
            text_id=text_id,
            mode="proposed",
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
        )
        # Ensure sentiments align to aspects; backfill missing aspect sentiments neutrally. PJ1: drop sentiments for dropped aspects.
        atsa_sents = getattr(atsa_result.model, "aspect_sentiments", [])
        atsa_sents = self._backfill_sentiments(text, ate_aspects, atsa_sents)
        kept_terms = {a.term for a in ate_aspects if a.term}
        atsa_sents = [s for s in atsa_sents if self._term_str(s) in kept_terms]
        atsa_result.model.aspect_sentiments = atsa_sents

        trace.append(ProcessTrace(
            stage="stage1", agent="ATSA", input_text=text,
            output=atsa_result.model.model_dump(),
            notes=atsa_result.meta.to_notes_str()
        ))

        if self.enable_validator:
            validator_result = self.validator.run_stage1(
                text,
                run_id=self.run_id,
                text_id=text_id,
                mode="proposed",
                demos=demos,
                language_code=language_code,
                domain_id=domain_id,
            )
            # Inject missing-second-aspect risk when contrast detected
            if self._has_contrast(text, language_code=language_code) and len(ate_aspects) < 2:
                validator_result.model.structural_risks.append(
                    StructuralRiskItem(
                        type="MISSING_SECOND_ASPECT",
                        scope={"start": 0, "end": len(text)},
                        severity="high",
                        description="Contrastive connective detected but only one aspect extracted.",
                    )
                )
            trace.append(ProcessTrace(
                stage="stage1", agent="Validator", input_text=text,
                output=validator_result.model.model_dump(),
                notes=validator_result.meta.to_notes_str()
            ))
            validator_model = validator_result.model
        else:
            validator_model = StructuralValidatorStage1Schema()
            trace.append(ProcessTrace(
                stage="stage1", agent="Validator", input_text=text,
                output=validator_model.model_dump(),
                notes="validator_disabled"
            ))
        return {"ate": ate_result.model, "atsa": atsa_result.model, "atsa_result": atsa_result, "validator": validator_model}

    def _run_stage2(
        self,
        text: str,
        trace: list[ProcessTrace],
        text_id: str,
        demos: list[str] | None = None,
        *,
        language_code: str = "unknown",
        domain_id: str = "unknown",
        debate_context: str | None = None,
    ) -> Dict[str, object]:
        if not self.enable_stage2:
            return {"ate": self.stage1_outputs["ate"], "atsa": self.stage1_outputs["atsa"], "validator": self.stage1_outputs["validator"]}
        # Stage2 uses Stage1 context + validator feedback
        # Note: structural validator stage1 result is reused for reanalysis
        errors_path = default_errors_path(self.run_id, "proposed", "stage2")
        ate2_result = self.ate_agent.run_stage2(
            text,
            self.stage1_outputs["ate"],
            self.stage1_outputs["validator"],
            run_id=self.run_id,
            text_id=text_id,
            mode="proposed",
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
            extra_context=debate_context,
        )
        if self.debate_review_context:
            self._inject_review_provenance(
                reviews=getattr(ate2_result.model, "aspect_review", []),
                key_field="term",
                debate_review_context=self.debate_review_context,
            )
        self._enforce_stage2_review_only(
            agent="ATE",
            text_id=text_id,
            errors_path=errors_path,
            payload=ate2_result.model.model_dump(),
            forbid_keys=["aspects"],
        )
        trace.append(ProcessTrace(
            stage="stage2", agent="ATE", input_text=text,
            output=ate2_result.model.model_dump(),
            notes=ate2_result.meta.to_notes_str()
        ))

        atsa2_result = self.atsa_agent.run_stage2(
            text,
            self.stage1_outputs["atsa"],
            self.stage1_outputs["validator"],
            run_id=self.run_id,
            text_id=text_id,
            mode="proposed",
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
            extra_context=debate_context,
        )
        if self.debate_review_context:
            self._inject_review_provenance(
                reviews=getattr(atsa2_result.model, "sentiment_review", []),
                key_field="aspect_term",
                debate_review_context=self.debate_review_context,
            )
        self._enforce_stage2_review_only(
            agent="ATSA",
            text_id=text_id,
            errors_path=errors_path,
            payload=atsa2_result.model.model_dump(),
            forbid_keys=["aspect_sentiments"],
        )
        trace.append(ProcessTrace(
            stage="stage2", agent="ATSA", input_text=text,
            output=atsa2_result.model.model_dump(),
            notes=atsa2_result.meta.to_notes_str()
        ))

        validator2_result = self.validator.run_stage2(
            text,
            self.stage1_outputs["validator"],
            run_id=self.run_id,
            text_id=text_id,
            mode="proposed",
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
            extra_context=debate_context,
        )
        trace.append(ProcessTrace(
            stage="stage2", agent="Validator", input_text=text,
            output=validator2_result.model.model_dump(),
            notes=validator2_result.meta.to_notes_str()
        ))
        return {"ate": ate2_result.model, "atsa": atsa2_result.model, "validator": validator2_result.model}

    def run(self, example: InternalExample | str) -> FinalOutputSchema:
        if isinstance(example, str):
            example = InternalExample(uid="text", text=example)
        # Per-sample override stats so each scorecard row has its own counts
        self._override_stats = {
            "applied": 0,
            "skipped_low_signal": 0,
            "skipped_neutral_only": 0,
            "skipped_conflict": 0,
            "skipped_already_confident": 0,
            "skipped_no_evidence_span": 0,
            "skipped_evidence_span_not_in_text": 0,
            "skipped_evidence_span_missing_trigger": 0,
            "skipped_max_one_override_per_sample": 0,
            "ev_score": None,
            "ev_adopted": False,
            "ev_components": {},
            "override_candidate": False,
            "override_applied": False,
            "override_effect_applied": False,
            "override_reason": "low_signal",
            "skipped_conflict_reasons": {
                "action_ambiguity": 0,
                "L3_conservative": 0,
                "implicit_soft_only": 0,
                "low_confidence": 0,
                "contradictory_memory": 0,
            },
        }
        self._last_memory_meta = None
        text = example.text
        text_id = getattr(example, "uid", "text") or "text"
        if getattr(self, "_last_override_run_id", None) != self.run_id:
            self._override_gate_records = []
            self._override_sample_outcomes = {}
            self._override_sample_idx = -1
            self._last_override_run_id = self.run_id
        self._override_sample_idx += 1
        self._current_text_id = text_id
        self._current_sample_idx = self._override_sample_idx
        case_type = getattr(example, "case_type", None) or "unknown"
        split = getattr(example, "split", None) or "unknown"
        language_code = getattr(example, "language_code", None) or "unknown"
        domain_id = getattr(example, "domain_id", None) or "unknown"
        demos = []
        if getattr(example, "metadata", None):
            demos = list(getattr(example, "metadata").get("demo_texts") or [])
        trace: list[ProcessTrace] = []

        if self.protocol_mode == "conflict_review_v1":
            from agents.conflict_review_runner import run_conflict_review_v1
            pipeline_cfg = self.config.get("pipeline") or self.config
            conflict_mode = (pipeline_cfg.get("conflict_mode") or "primary_secondary").strip()
            semantic_conflict = bool(pipeline_cfg.get("semantic_conflict_enabled", False))
            enable_review = pipeline_cfg.get("enable_review", True)
            enable_memory = pipeline_cfg.get("enable_memory", True)
            stage1_mode = (pipeline_cfg.get("stage1_mode") or "multi_facet").strip()
            conflict_flags_mode = pipeline_cfg.get("conflict_flags_mode")
            compute_conflict_flags = pipeline_cfg.get("compute_conflict_flags", True)
            episodic_orch = self._episodic_orchestrator if enable_memory else None
            episodic_cfg = self.config.get("episodic_memory") if enable_memory else None
            return run_conflict_review_v1(
                example,
                self.backbone,
                self.run_id,
                language_code=language_code,
                domain_id=domain_id,
                demos=demos,
                episodic_orchestrator=episodic_orch,
                episodic_config=episodic_cfg,
                conflict_mode=conflict_mode,
                semantic_conflict_enabled=semantic_conflict,
                enable_review=enable_review,
                enable_memory=enable_memory,
                stage1_mode=stage1_mode,
                conflict_flags_mode=conflict_flags_mode,
                compute_conflict_flags=compute_conflict_flags,
            )

        stage1 = self._run_stage1(
            text,
            trace,
            text_id,
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
        )
        self.stage1_outputs = stage1

        debate_output = None
        debate_context_json = None
        self.debate_review_context = None
        self._last_slot_dict = None
        if self.enable_debate:
            debate_context = self._build_debate_context(
                text=text,
                stage1_ate=stage1["ate"],
                stage1_atsa=stage1["atsa"],
                stage1_validator=stage1["validator"],
            )
            if self._episodic_orchestrator:
                slot_dict, _, memory_meta = self._episodic_orchestrator.get_slot_payload_for_current_sample(
                    text, stage1["ate"], stage1["atsa"], stage1["validator"], language_code
                )
                # C3(retrieval-only): retrieval 수행(비용/지연 유지), debate prompt에는 미주입
                # C2: advisory 주입 게이트 — polarity_conflict_raw | validator_s1_risk | alignment_failure>=2 | explicit_grounding_failure
                exposed_to_debate = memory_meta.get("exposed_to_debate", False)
                gate_ok, injection_trigger_reason = should_inject_advisory_with_reason(
                    text, stage1["ate"], stage1["atsa"], stage1["validator"]
                )
                memory_meta["injection_trigger_reason"] = injection_trigger_reason
                cap = getattr(self, "memory_prompt_injection_chars_cap", None)
                if exposed_to_debate and slot_dict and gate_ok:
                    if cap is not None and cap <= 0:
                        # C2 ablation: cap 0 = no injection (C3-like)
                        memory_meta["prompt_injection_chars"] = 0
                    else:
                        injection_str = json.dumps(slot_dict, ensure_ascii=False)
                        if cap is not None and cap > 0 and len(injection_str) > cap:
                            injection_str = injection_str[:cap] + ("…" if cap > 10 else "")
                        try:
                            slot_to_inject = json.loads(injection_str)
                        except Exception:
                            slot_to_inject = injection_str
                        ctx = json.loads(debate_context)
                        slot_name = (self._episodic_orchestrator._slot_name if self._episodic_orchestrator else "DEBATE_CONTEXT__MEMORY")
                        ctx[slot_name] = slot_to_inject
                        debate_context = json.dumps(ctx, ensure_ascii=False)
                        memory_meta["prompt_injection_chars"] = len(injection_str)
                else:
                    memory_meta["prompt_injection_chars"] = 0
                    if exposed_to_debate and slot_dict and not gate_ok:
                        memory_meta["advisory_injection_gated"] = True
                # Role-based memory access: debate slot is exposed to CJ only (G1 noise reduction).
                memory_meta["memory_access_policy"] = {"debate": "cj_only"}
                memory_meta["memory_debate_slot_present_for"] = ["cj"]
                self._last_slot_dict = slot_dict  # for Stage2 dual-channel injection
                self._last_memory_meta = memory_meta
            else:
                self._last_memory_meta = None
                self._last_slot_dict = None
            debate_output = self.debate.run(
                topic=text,
                context_json=debate_context,
                run_id=self.run_id,
                text_id=text_id,
                language_code=language_code,
                domain_id=domain_id,
                trace=trace,
            )
            debate_context_json = self._build_debate_review_context(
                debate_output,
                stage1_ate=stage1["ate"],
                stage1_atsa=stage1["atsa"],
                language_code=language_code,
            )
            # Stage2 dual-channel: add STAGE2_REVIEW_CONTEXT__MEMORY when C2 and stage2 gate passes (D1/D2).
            condition = getattr(self._episodic_orchestrator, "condition", "C1") if self._episodic_orchestrator else "C1"
            if condition == "C2" and getattr(self, "_last_slot_dict", None):
                stage2_ok, stage2_reason = should_inject_memory_for_stage2_with_reason(
                    text, stage1["ate"], stage1["atsa"], stage1["validator"]
                )
                if stage2_ok:
                    try:
                        ctx = json.loads(debate_context_json)
                        slot_name = getattr(self._episodic_orchestrator, "_slot_name", "DEBATE_CONTEXT__MEMORY")
                        bundle = (self._last_slot_dict.get(slot_name) if isinstance(self._last_slot_dict, dict) else None) or (list(self._last_slot_dict.values())[0] if self._last_slot_dict else None)
                        if bundle is not None:
                            ctx["STAGE2_REVIEW_CONTEXT__MEMORY"] = bundle
                            debate_context_json = json.dumps(ctx, ensure_ascii=False)
                        if getattr(self, "_last_memory_meta", None) is not None:
                            self._last_memory_meta["stage2_memory_injected"] = True
                            self._last_memory_meta["stage2_memory_gate_reason"] = stage2_reason
                            self._last_memory_meta["stage2_memory_prompt_injection_chars"] = len(json.dumps(bundle, ensure_ascii=False)) if bundle else 0
                    except (TypeError, ValueError, KeyError):
                        pass
                elif getattr(self, "_last_memory_meta", None) is not None:
                    self._last_memory_meta["stage2_memory_injected"] = False
                    self._last_memory_meta["stage2_memory_gate_reason"] = None
                    self._last_memory_meta["stage2_memory_prompt_injection_chars"] = 0
            elif getattr(self, "_last_memory_meta", None) is not None:
                self._last_memory_meta["stage2_memory_injected"] = False
                self._last_memory_meta["stage2_memory_gate_reason"] = None
                self._last_memory_meta["stage2_memory_prompt_injection_chars"] = 0
            try:
                self.debate_review_context = json.loads(debate_context_json)
            except Exception:
                self.debate_review_context = None

        stage2 = self._run_stage2(
            text,
            trace,
            text_id,
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
            debate_context=debate_context_json,
        )

        # Stage1 anchoring check (non-invasive)
        stage1_anchor_issues = self._find_unanchored_aspects(stage1["ate"], stage1["atsa"])

        # Apply stage2 reviews to stage1 outputs to obtain patched stage2 outputs
        patched_stage2_ate, patched_stage2_atsa, stage2_anchor_issues, correction_applied_log = self._apply_stage2_reviews(
            stage1_ate=stage1["ate"],
            stage1_atsa=stage1["atsa"],
            stage2_ate_review=stage2["ate"],
            stage2_atsa_review=stage2["atsa"],
            stage2_validator=stage2["validator"],
            stage1_validator=stage1["validator"],
            debate_review_context=self.debate_review_context,
            input_text=text,
        )
        self.patched_stage2_ate = patched_stage2_ate
        self.patched_stage2_atsa = patched_stage2_atsa

        # Stage2 adoption: decide whether to use stage1 or patched_stage2 as final (PJ3: EV gate)
        adopt_stage2, override_reason, override_candidate, ev_score, ev_adopted, ev_components = self._adopt_stage2_decision_with_ev(
            stage1_atsa=stage1["atsa"],
            patched_stage2_atsa=patched_stage2_atsa,
            stage1_validator=stage1["validator"],
            stage2_validator=stage2["validator"],
            debate_output=debate_output,
            correction_applied_log=correction_applied_log,
        )
        self._override_stats["override_candidate"] = override_candidate
        self._override_stats["override_applied"] = adopt_stage2
        self._override_stats["ev_score"] = ev_score
        self._override_stats["ev_adopted"] = ev_adopted
        self._override_stats["ev_components"] = ev_components
        # override_effect_applied = (adopted == True) only; gate APPLY여도 adopt에서 SKIP이면 False
        self._override_stats["override_effect_applied"] = bool(adopt_stage2)
        self._override_stats["override_reason"] = override_reason
        ev_rec = {
            "type": "ev_decision",
            "text_id": getattr(self, "_current_text_id", ""),
            "sample_idx": getattr(self, "_current_sample_idx", None),
            "ev_score": ev_score,
            "ev_adopted": ev_adopted,
            "ev_components": ev_components,
            "override_reason": override_reason,
        }
        self._append_override_gate_record(ev_rec)
        ev_threshold_cfg = float(self.debate_override_cfg.get("ev_threshold", 0.5))
        text_id_for_outcome = getattr(self, "_current_text_id", "")
        if text_id_for_outcome:
            self._override_sample_outcomes[text_id_for_outcome] = {
                "adopt_decision": "adopted" if adopt_stage2 else "not_adopted",
                "adopt_reason": override_reason or "",
                "ev_score": ev_score,
                "ev_threshold": ev_threshold_cfg,
            }
        # T1: gate에서 L3로 막혀서 실제 적용이 0건이면 scorecard에 override 막힘 반영 (회귀테스트 02829 T1)
        l3_skip = (self._override_stats.get("skipped_conflict_reasons") or {}).get("L3_conservative", 0) >= 1
        applied_count = self._override_stats.get("applied", 0) or 0
        if l3_skip and applied_count == 0:
            self._override_stats["override_applied"] = False
            self._override_stats["override_effect_applied"] = False
            self._override_stats["override_reason"] = "l3_conservative"

        # Get final aspect_sentiments: adopt stage2 when adoption decision says so, else stage1
        if adopt_stage2:
            final_aspect_sentiments_src = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
            kept_aspect_terms = {a.term for a in getattr(patched_stage2_ate, "aspects", [])}
        else:
            final_aspect_sentiments_src = getattr(stage1["atsa"], "aspect_sentiments", []) or []
            kept_aspect_terms = {a.term for a in getattr(stage1["ate"], "aspects", [])}
        final_aspect_sentiments = [s for s in final_aspect_sentiments_src if self._term_str(s) in kept_aspect_terms]

        # Align final with override result (우선) then debate_summary.final_tuples when present
        pol_by_term: Dict[str, str] = {}
        for log in (correction_applied_log or []):
            if isinstance(log, dict) and log.get("proposal_type") == "DEBATE_OVERRIDE" and log.get("applied"):
                t = (log.get("target_aspect") or "").strip()
                p_raw = (log.get("resulting_polarity") or "").strip()
                p = canonicalize_polarity(p_raw)
                if t and p:
                    pol_by_term[t] = p
        if debate_output and getattr(debate_output.summary, "final_tuples", None):
            debate_tuples = debate_output.summary.final_tuples
            if isinstance(debate_tuples, list) and debate_tuples:
                for item in debate_tuples:
                    if not isinstance(item, dict):
                        continue
                    raw_term = item.get("aspect_term") or item.get("term")
                    if isinstance(raw_term, dict):
                        term = (raw_term.get("term") or "").strip() if isinstance(raw_term.get("term"), str) else ""
                    else:
                        term = (raw_term or "").strip() if isinstance(raw_term, str) else ""
                    pol_raw = item.get("polarity")
                    if pol_raw is None or (isinstance(pol_raw, str) and not pol_raw.strip()):
                        continue
                    pol = canonicalize_polarity(pol_raw if isinstance(pol_raw, str) else str(pol_raw))
                    if term and term not in pol_by_term and pol is not None:
                        pol_by_term[term] = pol
        if pol_by_term:
            aligned: List[AspectSentimentItem] = []
            for s in final_aspect_sentiments:
                t = self._term_str(s)
                if t in pol_by_term:
                    new_s = AspectSentimentItem(
                        aspect_term=s.aspect_term,
                        polarity=pol_by_term[t],
                        evidence=s.evidence,
                        confidence=max(s.confidence, 0.7),
                        polarity_distribution={pol_by_term[t]: 0.9},
                        is_implicit=getattr(s, "is_implicit", False),
                    )
                    aligned.append(new_s)
                else:
                    aligned.append(s)
            final_aspect_sentiments = aligned

        # Aggregate ATE/ATSA into legacy outputs for moderator decision
        agg_stage1_ate = self._aggregate_label_from_sentiments(stage1["atsa"])
        agg_stage2_ate = self._aggregate_label_from_sentiments(patched_stage2_atsa)
        stage1_atsa_out = ATSAOutput(target=None, label=agg_stage1_ate.label, confidence=agg_stage1_ate.confidence, rationale=agg_stage1_ate.rationale)
        stage2_atsa_out = ATSAOutput(target=None, label=agg_stage2_ate.label, confidence=agg_stage2_ate.confidence, rationale=agg_stage2_ate.rationale)
        stage1_validator_out = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=stage1_anchor_issues, confidence=agg_stage1_ate.confidence)
        stage2_validator_out = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=stage2_anchor_issues, confidence=agg_stage2_ate.confidence)
        
        moderator_out = self.moderator.decide(
            agg_stage1_ate,
            agg_stage1_ate,  # use same for ATE/ATSA labels placeholder
            stage1_validator_out,
            agg_stage2_ate,
            agg_stage2_ate,
            final_aspect_sentiments=final_aspect_sentiments,
            debate_summary=debate_output.summary if debate_output else None,
        )
        trace.append(ProcessTrace(stage="moderator", agent="Moderator", input_text=text, output=moderator_out.model_dump()))

        correction_occurred = agg_stage2_ate.label != agg_stage1_ate.label
        conflict_resolved = correction_occurred

        final_confidence_score = moderator_out.confidence

        # Build final_aspects list from final aspect_sentiments
        final_aspects_list = self.moderator.build_final_aspects(final_aspect_sentiments)

        # Compute tuple lists for F1 evaluation (single source of truth for metrics)
        # When adopt_stage2, use aligned final_aspect_sentiments for stage2_tuples so S1 reflects representative single polarity per aspect (02829 regression).
        stage1_sents = getattr(stage1["atsa"], "aspect_sentiments", []) or []
        stage2_sents = (final_aspect_sentiments if adopt_stage2 else getattr(patched_stage2_atsa, "aspect_sentiments", []) or [])
        stage1_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage1_sents]))
        stage2_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage2_sents]))
        final_tuples = tuples_to_list_of_dicts(tuples_from_list(final_aspects_list))
        # 00474 |neutral 재발 방지: final_tuples 항상 채움 (None 미사용)
        if final_tuples is None:
            final_tuples = []

        final_result = FinalResult(
            label=moderator_out.final_label,
            confidence=final_confidence_score,
            rationale=moderator_out.rationale,
            final_aspects=final_aspects_list,
            stage1_tuples=stage1_tuples,
            stage2_tuples=stage2_tuples,
            final_tuples=final_tuples,
        )
        # CONTRACT-SUP-1: final_tuples polarity ∈ {positive, negative, neutral}; no silent fallback
        _assert_final_tuples_polarity_contract(final_tuples, text_id)

        flags = AnalysisFlags(
            correction_occurred=correction_occurred,
            conflict_resolved=conflict_resolved,
            final_confidence_score=final_confidence_score,
            stage2_executed=True,
        )

        store_result = None
        if self._episodic_orchestrator:
            # moderator_summary for risk→action mapping (content-strengthened memory)
            moderator_summary = self._build_moderator_summary(
                correction_applied_log=correction_applied_log,
                stage1_atsa=stage1["atsa"],
                patched_stage2_atsa=patched_stage2_atsa,
            )
            store_result = self._episodic_orchestrator.append_episode_if_needed(
                text, text_id,
                stage1["ate"], stage1["atsa"], stage1["validator"],
                patched_stage2_ate, patched_stage2_atsa, stage2["validator"],
                moderator_out, language_code=language_code, split=split or "unknown",
                moderator_summary=moderator_summary,
            )
        meta_extra = {
            "input_text": text,
            "run_id": self.run_id,
            "text_id": text_id,
            "mode": "proposed",
            "case_type": case_type,
            "split": split,
            "language_code": language_code,
            "domain_id": domain_id,
            "stage1_aspects": [a.model_dump() for a in getattr(stage1["ate"], "aspects", [])],
            "stage2_aspects": [a.model_dump() for a in getattr(patched_stage2_ate, "aspects", [])],
            "correction_applied_log": correction_applied_log,
        }
        # Polarity typo policy: ATSA repair/invalid counts for polarity_repair_rate, polarity_invalid_rate
        atsa_res = stage1.get("atsa_result")
        if atsa_res is not None and hasattr(atsa_res, "meta"):
            meta_extra["polarity_repair_count"] = getattr(atsa_res.meta, "polarity_repair_count", 0) or 0
            meta_extra["polarity_invalid_count"] = getattr(atsa_res.meta, "polarity_invalid_count", 0) or 0
        # S0/S3: Rule E and Rule B vs E order logging (moderator)
        arbiter_flags = getattr(moderator_out, "arbiter_flags", None)
        if arbiter_flags is not None:
            meta_extra["rule_e_fired"] = getattr(arbiter_flags, "rule_e_fired", False)
            meta_extra["rule_e_block_reason"] = getattr(arbiter_flags, "rule_e_block_reason", None)
            meta_extra["rule_b_applied"] = getattr(arbiter_flags, "rule_b_applied", False)
            meta_extra["rule_e_attempted_after_b"] = getattr(arbiter_flags, "rule_e_attempted_after_b", False)
        meta_extra["selected_stage"] = getattr(moderator_out, "selected_stage", None)
        if debate_output:
            meta_extra["debate_summary"] = debate_output.summary.model_dump()
            meta_extra["debate_review_context"] = json.loads(debate_context_json) if debate_context_json else None
            meta_extra["debate_override_stats"] = {k: v for k, v in self._override_stats.items() if k != "skipped_conflict_reasons"}
            meta_extra["debate_override_skip_reasons"] = self._override_stats.get("skipped_conflict_reasons") or {}
            meta_extra["ev_score"] = self._override_stats.get("ev_score")
            meta_extra["ev_threshold"] = float(self.debate_override_cfg.get("ev_threshold", 0.5)) if self.debate_override_cfg else None
            meta_extra["debate_override_effective"] = self._build_debate_override_effective()
            # 메타 3종: gate_decision(이 샘플), adopt_decision, adopt_reason (adopt 기준)
            gate_applied = any(
                isinstance(c, dict) and c.get("proposal_type") == "DEBATE_OVERRIDE" and c.get("applied")
                for c in (correction_applied_log or [])
            )
            meta_extra["gate_decision"] = "APPLY" if gate_applied else "SKIP"
            meta_extra["adopt_decision"] = "adopted" if adopt_stage2 else "not_adopted"
            meta_extra["adopt_reason"] = override_reason or ""
            # S0: override 미적용 사유 로깅 (sample-level)
            meta_extra["override_applied"] = bool(self._override_stats.get("applied", 0) > 0 or gate_applied)
            _primary_skip = None
            if self._override_stats.get("skipped_neutral_only", 0) > 0:
                _primary_skip = "neutral_only"
            elif self._override_stats.get("skipped_low_signal", 0) > 0:
                _primary_skip = "low_signal"
            elif self._override_stats.get("skipped_conflict", 0) > 0:
                _reasons = self._override_stats.get("skipped_conflict_reasons") or {}
                if _reasons.get("action_ambiguity"):
                    _primary_skip = "action_ambiguity"
                elif _reasons.get("L3_conservative"):
                    _primary_skip = "l3_conservative"
                elif _reasons.get("implicit_soft_only"):
                    _primary_skip = "implicit_soft_only"
                else:
                    _primary_skip = "conflict"
            elif self._override_stats.get("skipped_already_confident", 0) > 0:
                _primary_skip = "already_confident"
            meta_extra["override_skipped_reason"] = _primary_skip if not meta_extra["override_applied"] else None
            meta_extra["override_evidence_gate_reason"] = _primary_skip if (not meta_extra["override_applied"] and _primary_skip) else None
        if getattr(self, "_last_memory_meta", None) is not None:
            meta_extra["memory"] = self._last_memory_meta
        if store_result is not None:
            meta_extra["store_decision"] = store_result[0]
            meta_extra["store_skip_reason"] = store_result[1]
            meta_extra["store_reason_tags"] = store_result[2]

        self._write_override_gate_debug_summary()

        result = FinalOutputSchema(
            meta=meta_extra,
            stage1_ate=agg_stage1_ate,
            stage1_atsa=stage1_atsa_out,
            stage1_validator=stage1_validator_out,
            stage2_ate=agg_stage2_ate,
            stage2_atsa=stage2_atsa_out,
            stage2_validator=stage2_validator_out,
            moderator=moderator_out,
            debate=debate_output,
            process_trace=trace,
            analysis_flags=flags,
            final_result=final_result,
        )
        # Attach case context to traces for downstream integrity checks
        for tr in result.process_trace:
            tr.case_type = case_type
            tr.split = split
            tr.uid = text_id
            tr.language_code = language_code
            tr.domain_id = domain_id
        return result

    def _build_debate_context(
        self,
        *,
        text: str,
        stage1_ate: AspectExtractionStage1Schema,
        stage1_atsa: AspectSentimentStage1Schema,
        stage1_validator: StructuralValidatorStage1Schema,
    ) -> str:
        payload = {
            "text": text,
            "stage1_aspects": [a.model_dump() for a in getattr(stage1_ate, "aspects", [])],
            "stage1_aspect_sentiments": [s.model_dump() for s in getattr(stage1_atsa, "aspect_sentiments", [])],
            "stage1_structural_risks": [r.model_dump() for r in getattr(stage1_validator, "structural_risks", [])],
            "stage1_correction_proposals": [p.model_dump() for p in getattr(stage1_validator, "correction_proposals", [])],
        }
        return json.dumps(payload, ensure_ascii=False)

    def _build_debate_review_context(
        self,
        debate_output,
        *,
        stage1_ate: AspectExtractionStage1Schema,
        stage1_atsa: AspectSentimentStage1Schema,
        language_code: str,
    ) -> str:
        summary = debate_output.summary if debate_output else None
        rounds = debate_output.rounds if debate_output else []
        aspect_terms = [a.term for a in getattr(stage1_ate, "aspects", []) if a.term]
        atsa_terms = [self._term_str(s) for s in getattr(stage1_atsa, "aspect_sentiments", []) if self._term_str(s)]
        aspect_terms = list(dict.fromkeys(aspect_terms + atsa_terms))
        synonym_hints = {term: self._expand_synonyms(term, language_code=language_code) for term in aspect_terms}

        norm_map = {}
        for term in aspect_terms:
            for candidate in [term] + synonym_hints.get(term, []):
                stripped = self._strip_topic_suffix(candidate, language_code=language_code)
                norm = re.sub(r"\s+", "", stripped.lower())
                norm = re.sub(r"[^\w가-힣]", "", norm)
                if norm and norm not in norm_map:
                    norm_map[norm] = term
        def _norm_pol(raw: Any) -> Optional[str]:
            if raw is None or not str(raw).strip():
                return None
            s = str(raw).strip().lower().replace("pos", "positive").replace("neg", "negative").replace("neu", "neutral")
            return s if s in ("positive", "negative", "neutral") else None

        def _edit_attr(e: Any, key: str, default: Any = None) -> Any:
            """Read edit field from either dict or object (ProposedEdit); used so proposed_edits work when parsed as dicts."""
            if e is None:
                return default
            if isinstance(e, dict):
                return e.get(key, default)
            return getattr(e, key, default)

        hint_entries: List[Dict[str, Any]] = []
        rebuttals = []
        aspect_map = []
        idx = 0
        mapping_stats = {"direct": 0, "fallback": 0, "none": 0}
        mapping_fail_reasons = {
            "no_aspects": 0,
            "no_match": 0,
            "neutral_stance": 0,
            "fallback_used": 0,
        }
        # Gate uses aspect_hints. aspect_hints is built from hint_entries (per-edit) first, then
        # aspect_map (turn-level) only for aspects NOT already in aspect_hints. So gate uses
        # per-edit polarity when available; turn-level stance="" -> neutral must not override.
        for r in rounds:
            for t in r.turns:
                speaker = getattr(t, "agent", None) or t.speaker
                stance = (getattr(t, "stance", None) or "").strip()
                proposed_edits = getattr(t, "proposed_edits", None) or []
                if proposed_edits:
                    len_before = len(hint_entries)
                    for e in proposed_edits:
                        target = _edit_attr(e, "target")
                        target = target.model_dump() if hasattr(target, "model_dump") else (target if isinstance(target, dict) else {})
                        if not target:
                            continue
                        op = (_edit_attr(e, "op") or "").strip().lower()
                        at = target.get("aspect_term")
                        aspect_raw = (str(at).strip() if at else None) or (str(target.get("value")).strip() if op == "set_aspect_ref" and target.get("value") else None)
                        if not aspect_raw:
                            continue
                        anorm = re.sub(r"\s+", "", aspect_raw.lower())
                        aspect_mapped = norm_map.get(anorm) or (aspect_raw if aspect_raw in aspect_terms else None)
                        if not aspect_mapped:
                            for term, syns in synonym_hints.items():
                                if aspect_raw in (syns or []) or aspect_raw == term:
                                    aspect_mapped = term
                                    break
                        aspect_final = aspect_mapped or aspect_raw
                        if op == "set_polarity":
                            pol = _norm_pol(_edit_attr(e, "value"))
                            hint_entries.append({"aspect": aspect_final, "polarity_hint": pol, "weight": 0.5, "speaker": speaker, "stance": stance or "patch"})
                        elif op == "confirm_tuple":
                            pol = _norm_pol(target.get("polarity"))
                            hint_entries.append({"aspect": aspect_final, "polarity_hint": pol, "weight": 0.5, "speaker": speaker, "stance": stance or "patch"})
                        elif op == "drop_tuple":
                            hint_entries.append({"aspect": aspect_final, "polarity_hint": "negative", "weight": 0.8, "speaker": speaker, "stance": stance or "patch"})
                        elif op == "set_aspect_ref":
                            hint_entries.append({"aspect": aspect_final, "polarity_hint": None, "weight": 0.0, "speaker": speaker, "stance": stance or "patch"})
                        else:
                            pol = _norm_pol(target.get("polarity")) or _norm_pol(_edit_attr(e, "value"))
                            hint_entries.append({"aspect": aspect_final, "polarity_hint": pol, "weight": 0.5 if pol else 0.0, "speaker": speaker, "stance": stance or "patch"})
                    parts = []
                    for e in proposed_edits:
                        _t = _edit_attr(e, "target")
                        _t = _t.model_dump() if hasattr(_t, "model_dump") else (_t if isinstance(_t, dict) else {})
                        if _t and _t.get("aspect_term"):
                            parts.append(str(_t.get("aspect_term", "") or "").strip())
                        if _edit_attr(e, "value"):
                            parts.append(str(_edit_attr(e, "value")).strip())
                    text_blob = " ".join(parts) if parts else (t.message or "")
                    # Priority: set_polarity(value)/confirm_tuple -> pos/neg; drop_tuple -> anti-neutral (neg); set_aspect_ref -> exclude from score. Stance="" must not override when edits present.
                    polarity_first = None
                    for e in proposed_edits:
                        op_e = (_edit_attr(e, "op") or "").strip().lower()
                        if op_e in ("set_polarity", "confirm_tuple"):
                            _t = _edit_attr(e, "target")
                            _t = _t.model_dump() if hasattr(_t, "model_dump") else (_t if isinstance(_t, dict) else {})
                            polarity_first = _norm_pol(_edit_attr(e, "value")) or _norm_pol(_t.get("polarity"))
                            if polarity_first:
                                break
                    if polarity_first is None and any((_edit_attr(e, "op") or "").strip().lower() == "drop_tuple" for e in proposed_edits):
                        polarity_first = "negative"
                    polarity_hint = polarity_first if polarity_first is not None else None
                    stance_weight = 0.5
                    # 1-1: per-edit vs turn-level polarity_hint (same hint) for debugging overwrite
                    per_edit_slice = hint_entries[len_before:]
                    per_edit_pols = [h.get("polarity_hint") for h in per_edit_slice]
                    if per_edit_slice or polarity_hint:
                        print("[debate_review_context] speaker=%s per_edit_polarity_hints=%s turn_level_polarity_hint=%s gate_source=aspect_hints(from_hint_entries_then_aspect_map_fallback)" % (speaker, per_edit_pols, polarity_hint), flush=True)
                else:
                    # EPM/TAN/CJ가 proposed_edits 없이 나온 경우: process_trace debate 단계 raw_response로 파서 vs 에이전트 구분
                    print("[debate_review_context] turn speaker=%s proposed_edits empty (check process_trace debate stage raw_response for parser vs agent)" % speaker, flush=True)
                    parts = [t.message or ""] + (t.key_points or [])
                    text_blob = " ".join(parts)
                    if not stance:
                        polarity_hint = None
                        stance_weight = 0.0
                    else:
                        polarity_hint = self._stance_to_polarity(stance)
                        stance_weight = self._stance_weight(stance)
                blob_norm = re.sub(r"\s+", "", text_blob.lower())
                blob_norm = re.sub(r"[^\w가-힣]", "", blob_norm)
                mapped = [orig for key, orig in norm_map.items() if key and key in blob_norm]
                mapped = list(dict.fromkeys(mapped))
                direct_mapped = bool(mapped)
                if not mapped:
                    mapped = self._fallback_map_from_atsa(
                        stage1_atsa=stage1_atsa,
                        polarity_hint=polarity_hint if polarity_hint else None,
                    )
                mapping_confidence = "direct" if direct_mapped else ("fallback" if mapped else "none")
                if mapping_confidence in mapping_stats:
                    mapping_stats[mapping_confidence] += 1
                fail_reason = None
                if mapping_confidence == "fallback":
                    fail_reason = "fallback_used"
                elif mapping_confidence == "none":
                    if not aspect_terms:
                        fail_reason = "no_aspects"
                    elif polarity_hint in (None, "neutral"):
                        fail_reason = "neutral_stance"
                    else:
                        fail_reason = "no_match"
                if fail_reason and fail_reason in mapping_fail_reasons:
                    mapping_fail_reasons[fail_reason] += 1
                rebuttals.append(
                    {
                        "speaker": speaker,
                        "stance": stance or "",
                        "key_points": t.key_points,
                        "message": t.message,
                        "proposed_edits": [getattr(e, "model_dump", lambda: e)() if hasattr(e, "model_dump") else e for e in proposed_edits],
                        "aspect_terms": mapped,
                        "mapping_confidence": mapping_confidence,
                        "mapping_fail_reason": fail_reason,
                        "weight": stance_weight,
                        "polarity_hint": polarity_hint,
                        "provenance_hint": f"source:{speaker}/{stance or 'patch'}",
                    }
                )
                aspect_map.append(
                    {
                        "rebuttal_index": idx,
                        "speaker": speaker,
                        "stance": stance or "",
                        "aspect_terms": mapped,
                        "weight": stance_weight,
                        "polarity_hint": polarity_hint,
                    }
                )
                idx += 1
        if summary:
            patch = getattr(summary, "final_patch", None) or []
            for item in patch:
                if not isinstance(item, dict):
                    continue
                op = (item.get("op") or "").strip().lower()
                target = item.get("target") or {}
                at = target.get("aspect_term")
                aspect_raw = str(at).strip() if at else None
                if not aspect_raw:
                    continue
                anorm = re.sub(r"\s+", "", aspect_raw.lower())
                aspect_mapped = norm_map.get(anorm) or (aspect_raw if aspect_raw in aspect_terms else None)
                aspect_final = aspect_mapped or aspect_raw
                if op == "confirm_tuple":
                    pol = _norm_pol(target.get("polarity"))
                    hint_entries.append({"aspect": aspect_final, "polarity_hint": pol, "weight": 0.8, "speaker": "CJ", "stance": "patch"})
                elif op == "drop_tuple":
                    hint_entries.append({"aspect": aspect_final, "polarity_hint": "negative", "weight": 0.8, "speaker": "CJ", "stance": "patch"})
        aspect_hints = {}
        for h in hint_entries:
            aspect = h.get("aspect")
            if not aspect:
                continue
            aspect_hints.setdefault(aspect, []).append(
                {
                    "speaker": h.get("speaker"),
                    "stance": h.get("stance"),
                    "weight": h.get("weight"),
                    "polarity_hint": h.get("polarity_hint"),
                }
            )
        for item in aspect_map:
            for aspect in item.get("aspect_terms") or []:
                if aspect in aspect_hints:
                    continue
                aspect_hints.setdefault(aspect, []).append(
                    {
                        "speaker": item.get("speaker"),
                        "stance": item.get("stance"),
                        "weight": item.get("weight"),
                        "polarity_hint": item.get("polarity_hint"),
                    }
                )
        payload = {
            "review_guidance": (
                "Map rebuttal points to aspect_review/sentiment_review actions where applicable. "
                    "Use aspect_terms mapping when available; if empty, infer from context cautiously. "
                "Include provenance in review reason fields using provenance_hint."
            ),
            "summary": summary.model_dump() if summary else {},
            "aspect_terms": aspect_terms,
            "synonym_hints": synonym_hints,
            "rebuttal_points": rebuttals,
            "aspect_map": aspect_map,
            "aspect_hints": aspect_hints,
            "mapping_stats": mapping_stats,
            "mapping_fail_reasons": mapping_fail_reasons,
            "provenance_template": "source:{speaker}/{stance}",
            "fallback_mapping_policy": "If no aspect_terms, map to ATSA aspect with matching polarity_hint; otherwise highest-confidence aspect.",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _load_debate_override_cfg(
        self, override_cfg: dict | None, override_profile: str | None = None
    ) -> tuple[dict, Optional[str], str]:
        """
        Resolve effective override config. Returns (cfg_dict, profile_id, source).
        source: "yaml_override" | "json_profile" | "json_default" | "code_default"
        """
        if isinstance(override_cfg, dict) and override_cfg:
            profile_id = override_profile or None
            effective = {k: v for k, v in override_cfg.items() if k not in ("profiles", "default_profile")}
            if not effective:
                effective = self._default_override_cfg()
            return effective, profile_id, "yaml_override"
        cfg_path = Path("experiments") / "configs" / "debate_override_thresholds.json"
        if not cfg_path.exists():
            return self._default_override_cfg(), None, "code_default"
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_override_cfg(), None, "code_default"
        if isinstance(data.get("profiles"), dict):
            profile_id = override_profile or data.get("default_profile") or "t0"
            profile = data["profiles"].get(profile_id)
            if isinstance(profile, dict):
                return dict(profile), profile_id, "json_profile"
            return dict(data["profiles"].get("t0", self._default_override_cfg())), profile_id, "json_profile"
        # Backward compat: flat JSON
        if isinstance(data, dict) and any(k in data for k in ("min_total", "min_margin")):
            return {k: v for k, v in data.items() if k not in ("profiles", "default_profile")}, None, "json_default"
        return self._default_override_cfg(), None, "code_default"

    def _default_override_cfg(self) -> dict:
        return {
            "min_total": 1.6,
            "min_margin": 0.8,
            "min_target_conf": 0.7,
            "l3_conservative": True,
            "ev_threshold": 0.5,
        }

    def _build_debate_override_effective(self) -> Dict[str, Any]:
        """Effective override config for manifest/scorecard: profile_id, thresholds, source."""
        cfg = self.debate_override_cfg or self._default_override_cfg()
        return {
            "override_profile_id": getattr(self, "_override_profile_id", None),
            "min_total": float(cfg.get("min_total", 1.6)),
            "min_margin": float(cfg.get("min_margin", 0.8)),
            "min_target_conf": float(cfg.get("min_target_conf", 0.7)),
            "l3_conservative": cfg.get("l3_conservative", True),
            "ev_threshold": float(cfg.get("ev_threshold", 0.5)),
            "source": getattr(self, "_override_cfg_source", "code_default"),
        }

    def _append_override_gate_record(self, rec: Dict[str, Any]) -> None:
        """Append one per-aspect override gate record to in-memory list and to override_gate_debug.jsonl."""
        self._override_gate_records.append(rec)
        out_dir = Path("results") / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = out_dir / "override_gate_debug.jsonl"
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _write_override_gate_debug_summary(self) -> None:
        """Write override_gate_debug_summary.json from accumulated _override_gate_records."""
        records = getattr(self, "_override_gate_records", []) or []
        if not records:
            return
        out_dir = Path("results") / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        summary_path = out_dir / "override_gate_debug_summary.json"

        totals = [float(r.get("total", 0)) for r in records if r.get("total") is not None]
        margins = [float(r.get("margin", 0)) for r in records if r.get("margin") is not None]
        min_total_cfg = next((float(r["thresholds"].get("min_total", 1.6)) for r in records if r.get("thresholds")), 1.6)
        min_margin_cfg = next((float(r["thresholds"].get("min_margin", 0.8)) for r in records if r.get("thresholds")), 0.8)

        def _percentile(vals: List[float], p: float) -> Optional[float]:
            if not vals:
                return None
            s = sorted(vals)
            idx = (p / 100.0) * (len(s) - 1)
            i, frac = int(idx), idx % 1
            if i >= len(s) - 1:
                return round(s[-1], 4)
            return round(s[i] + frac * (s[i + 1] - s[i]), 4)

        decision_applied_n = sum(1 for r in records if r.get("decision") == "APPLY")
        decision_skip_n = sum(1 for r in records if r.get("decision") == "SKIP")
        skip_reason_counts: Dict[str, int] = {}
        for r in records:
            if r.get("decision") != "SKIP":
                continue
            reason = (r.get("skip_reason") or "other").strip() or "other"
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
        n = len(records)
        skip_reason_rates = {k: round(v / n, 4) for k, v in skip_reason_counts.items()} if n else {}
        skipped_neutral_only_n = skip_reason_counts.get("neutral_only", 0)
        low_signal_breakdown = {
            "neutral_only": skip_reason_counts.get("neutral_only", 0),
            "low_signal": skip_reason_counts.get("low_signal", 0),
        }

        total_near = sum(1 for t in totals if min_total_cfg - 0.2 <= t < min_total_cfg) if totals else 0
        margin_near = sum(1 for m in margins if min_margin_cfg - 0.2 <= m < min_margin_cfg) if margins else 0

        # Run-level totals from all records (override gate is per-aspect)
        override_hint_invalid_total = sum(int(r.get("invalid_hint_count", 0)) for r in records)
        override_hint_repair_total = sum(int(r.get("hint_repair_count", 0)) for r in records)
        total_valid_hints = sum(int(r.get("valid_hint_count", 0)) for r in records)
        override_hint_invalid_rate = (
            round(override_hint_invalid_total / (override_hint_invalid_total + total_valid_hints), 4)
            if (override_hint_invalid_total + total_valid_hints) > 0 else None
        )
        by_sample = getattr(self, "_override_sample_outcomes", None) or {}

        summary = {
            "n_aspects": n,
            "decision_applied_n": decision_applied_n,
            "decision_skip_n": decision_skip_n,
            "skipped_neutral_only_n": skipped_neutral_only_n,
            "low_signal_breakdown": low_signal_breakdown,
            "skip_reason_count": skip_reason_counts,
            "skip_reason_rate": skip_reason_rates,
            "override_hint_invalid_total": override_hint_invalid_total,
            "override_hint_repair_total": override_hint_repair_total,
            "override_hint_invalid_rate": override_hint_invalid_rate,
            "by_sample": by_sample,
            "total_dist": {
                "min": round(min(totals), 4) if totals else None,
                "mean": round(sum(totals) / len(totals), 4) if totals else None,
                "median": _percentile(totals, 50),
                "p90": _percentile(totals, 90),
                "p95": _percentile(totals, 95),
                "max": round(max(totals), 4) if totals else None,
            } if totals else {},
            "margin_dist": {
                "min": round(min(margins), 4) if margins else None,
                "mean": round(sum(margins) / len(margins), 4) if margins else None,
                "median": _percentile(margins, 50),
                "p90": _percentile(margins, 90),
                "p95": _percentile(margins, 95),
                "max": round(max(margins), 4) if margins else None,
            } if margins else {},
            "threshold_near_rate": {
                "total_in_min_total_minus_0_2_to_min_total_n": total_near,
                "total_near_rate": round(total_near / n, 4) if n else 0,
                "margin_in_min_margin_minus_0_2_to_min_margin_n": margin_near,
                "margin_near_rate": round(margin_near / n, 4) if n else 0,
            },
        }
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def _build_moderator_summary(
        self,
        *,
        correction_applied_log: List[Dict[str, Any]],
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
    ) -> Dict[str, Any]:
        """Build moderator_summary for episodic memory risk→action mapping."""
        applied = self._override_stats.get("applied", 0) or 0
        action_taken = "abstain"
        for log in correction_applied_log or []:
            if log.get("proposal_type") == "DEBATE_OVERRIDE" and log.get("applied"):
                reason = (log.get("reason") or "").lower()
                if "flip" in reason:
                    action_taken = "polarity_flip"
                    break
                if "add" in reason:
                    action_taken = "polarity_flip"
                    break
        if applied and action_taken == "abstain":
            action_taken = "defer"
        # conflict_resolved: no duplicate polarities per aspect in final
        conflict_resolved = None
        sents_final = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        pol_by_aspect: Dict[str, set] = {}
        for s in sents_final:
            t = self._term_str(s)
            p = getattr(s, "polarity", None)
            if p is None:
                continue
            pol_by_aspect.setdefault(t, set()).add(p)
        if pol_by_aspect:
            conflict_resolved = not any(len(v) > 1 for v in pol_by_aspect.values())
        return {
            "override_applied": applied > 0,
            "override_success": False,
            "override_harm": False,
            "action_taken": action_taken,
            "outcome_delta": {"conflict_resolved": conflict_resolved} if conflict_resolved is not None else None,
        }

    def _expand_synonyms(self, term: str, *, language_code: str) -> list[str]:
        """
        Lightweight synonym expansion for aspect mapping.
        This is intentionally conservative to avoid over-matching.
        """
        if not term:
            return []
        patterns = self._patterns(language_code)
        from_patterns = patterns.get("aspect_synonyms") or {}
        synonyms = []
        lower = term.lower()
        for key, values in from_patterns.items():
            if not key or not isinstance(values, list):
                continue
            if key in lower or lower in key:
                synonyms += [str(v) for v in values if v]
        if any(tok in lower for tok in ["가격", "비용", "가성비"]):
            synonyms += ["가격", "비용", "가성비", "금액"]
        if any(tok in lower for tok in ["배송", "배달"]):
            synonyms += ["배송", "배달", "출고"]
        if any(tok in lower for tok in ["서비스", "응대", "CS"]):
            synonyms += ["서비스", "응대", "cs", "고객응대"]
        if any(tok in lower for tok in ["품질", "퀄리티", "quality"]):
            synonyms += ["품질", "퀄리티", "quality", "마감"]
        if any(tok in lower for tok in ["맛", "풍미"]):
            synonyms += ["맛", "풍미", "향"]
        if any(tok in lower for tok in ["디자인", "외관", "look"]):
            synonyms += ["디자인", "외관", "look", "스타일"]
        if any(tok in lower for tok in ["성능", "속도", "퍼포먼스"]):
            synonyms += ["성능", "속도", "퍼포먼스", "performance"]
        # Deduplicate while preserving order
        seen = set()
        result = []
        for s in synonyms:
            if s not in seen:
                seen.add(s)
                result.append(s)
        return result

    @staticmethod
    def _fallback_map_from_atsa(
        *,
        stage1_atsa: AspectSentimentStage1Schema,
        polarity_hint: Optional[str],
    ) -> list[str]:
        def _t(sent):
            return (sent.aspect_term.term if sent.aspect_term else "") or ""
        sentiments = getattr(stage1_atsa, "aspect_sentiments", []) or []
        if not sentiments:
            return []
        if polarity_hint is None or polarity_hint == "neutral":
            refs = [_t(s) for s in sentiments if _t(s)]
            return [refs[0]] if len(set(refs)) == 1 else []
        candidates = [s for s in sentiments if getattr(s, "polarity", None) == polarity_hint and _t(s)]
        if not candidates:
            candidates = [s for s in sentiments if _t(s)]
        if not candidates:
            return []
        best = max(candidates, key=lambda s: s.confidence)
        return [ _t(best)] if _t(best) else []

    @staticmethod
    def _stance_weight(stance: str) -> float:
        if stance == "neutral":
            return 0.6
        if stance in {"pro", "con"}:
            return 1.0
        return 0.8

    @staticmethod
    def _stance_to_polarity(stance: str) -> str:
        if stance == "pro":
            return "positive"
        if stance == "con":
            return "negative"
        return "neutral"

    def _aggregate_label_from_sentiments(self, atsa_output: AspectSentimentStage1Schema | AspectSentimentStage2Schema) -> ATEOutput:
        sentiments = getattr(atsa_output, "aspect_sentiments", None) or []
        if not sentiments:
            return ATEOutput(label="neutral", confidence=0.0, rationale="")
        best = max(sentiments, key=lambda s: s.confidence)
        pol = getattr(best, "polarity", None)
        rationale = best.evidence or ""
        if pol is None:
            rationale = (rationale + " [missing polarity]").strip()
            pol = "neutral"  # moderator expects a string; missing is marked in rationale
        return ATEOutput(label=pol, confidence=best.confidence, rationale=rationale)

    # ---------------- helper transforms ----------------
    def _strip_topic_suffix(self, term: str, *, language_code: str) -> str:
        patterns = self._patterns(language_code)
        suffixes = tuple(s for s in patterns.get("topic_particles", []) if isinstance(s, str))
        if suffixes and term.endswith(suffixes) and len(term) > 1:
            for suf in sorted(suffixes, key=len, reverse=True):
                if term.endswith(suf) and len(term) > len(suf):
                    return term[: -len(suf)]
        return term

    def _clean_aspects(self, text: str, aspects: List[AspectExtractionItem], *, language_code: str) -> List[AspectExtractionItem]:
        cleaned: List[AspectExtractionItem] = []
        for a in aspects:
            term = a.term
            span = a.span
            if term:
                stripped = self._strip_topic_suffix(term, language_code=language_code)
                if stripped != term and span and span.end > span.start:
                    delta = len(term) - len(stripped)
                    span = Span(start=span.start, end=span.end - delta)
                term = stripped
            cleaned.append(
                AspectExtractionItem(
                    term=term,
                    span=span,
                    normalized=a.normalized,
                    syntactic_head=a.syntactic_head,
                    confidence=a.confidence,
                    rationale=a.rationale,
                )
            )
        return cleaned

    def _has_contrast(self, text: str, *, language_code: str) -> bool:
        patterns = self._patterns(language_code)
        markers = patterns.get("contrast_markers", [])
        haystack = text.lower()
        return any((m or "").lower() in haystack for m in markers if isinstance(m, str))

    def _guess_second_aspect(self, text: str, existing_terms: set[str], *, language_code: str) -> AspectExtractionItem | None:
        patterns = self._patterns(language_code)
        markers = [m for m in patterns.get("contrast_markers", []) if isinstance(m, str)]
        token_regex = patterns.get("aspect_token_regex") or r"[가-힣A-Za-z]{2,}"

        haystack = text.lower()
        start_idx = 0
        for m in markers:
            pos = haystack.find(m.lower())
            if pos != -1:
                start_idx = pos + len(m)
                break

        tail = text[start_idx:]
        try:
            m2 = re.search(token_regex, tail)
        except re.error:
            m2 = re.search(r"[A-Za-z]{3,}", tail)
        if not m2:
            return None
        term_raw = m2.group(0)
        term = self._strip_topic_suffix(term_raw, language_code=language_code)
        if term in existing_terms:
            return None
        span_start = start_idx + m2.start()
        span_end = start_idx + m2.start() + len(term)
        return AspectExtractionItem(
            term=term,
            span=Span(start=span_start, end=span_end),
            normalized=None,
            syntactic_head=None,
            confidence=0.5,
            rationale="contrast heuristic second aspect",
        )

    def _enforce_contrast_min_aspects(self, text: str, aspects: List[AspectExtractionItem], *, language_code: str) -> List[AspectExtractionItem]:
        if not self._has_contrast(text, language_code=language_code):
            return aspects
        terms = {a.term for a in aspects}
        if len(aspects) >= 2:
            return aspects
        guessed = self._guess_second_aspect(text, terms, language_code=language_code)
        if guessed:
            return aspects + [guessed]
        return aspects

    def _enforce_substring_aspects(self, text: str, aspects: List[AspectExtractionItem]) -> tuple[List[AspectExtractionItem], List[Dict[str, Any]]]:
        """PJ1: Drop aspects whose term is not a substring of text. Return (kept_list, dropped_list with rejection_reason)."""
        if not text:
            return aspects, []
        text_norm = text.strip()
        kept: List[AspectExtractionItem] = []
        dropped: List[Dict[str, Any]] = []
        for a in aspects:
            term = (a.term or "").strip()
            if not term:
                kept.append(a)
                continue
            if term in text_norm:
                kept.append(a)
            else:
                dropped.append({"term": term, "rejection_reason": "aspect_not_substring"})
        return kept, dropped

    def has_actionable_evidence(self, text: str, evidence_span: Optional[str], case_type: str) -> tuple[bool, str]:
        """PJ2: Override gate evidence check. Return (ok, reason). Reasons: no_evidence_span, evidence_span_not_in_text, evidence_span_missing_trigger."""
        span = (evidence_span or "").strip()
        if not span:
            return False, "no_evidence_span"
        if not text:
            return False, "evidence_span_not_in_text"
        text_norm = text.strip()
        if span not in text_norm:
            return False, "evidence_span_not_in_text"
        if len(span) < 2:
            return False, "evidence_span_missing_trigger"
        return True, ""

    def _backfill_sentiments(self, text: str, aspects: List[AspectExtractionItem], sentiments: List[AspectSentimentItem]):
        if not aspects:
            return sentiments
        by_term = {self._term_str(s) for s in sentiments if self._term_str(s)}
        for a in aspects:
            if a.term not in by_term:
                sentiments.append(
                    AspectSentimentItem(
                        aspect_term=AspectTerm(term=a.term, span=a.span),
                        polarity="neutral",
                        evidence=text,
                        confidence=0.5,
                        polarity_distribution={"neutral": 1.0},
                        is_implicit=False,
                        is_backfilled=True,
                        neutral_reason="missing_atsa_for_aspect",
                    )
                )
        return sentiments

    def _find_unanchored_aspects(self, ate: AspectExtractionStage1Schema, atsa: AspectSentimentStage1Schema) -> list[str]:
        """Detect aspect_sentiments whose aspect_term.term is not among ATE terms."""
        ate_terms = {a.term for a in getattr(ate, "aspects", [])}
        issues: list[str] = []
        for s in getattr(atsa, "aspect_sentiments", []):
            t = self._term_str(s)
            if t and t not in ate_terms:
                issues.append(f"stage1_aspect_term_not_in_ate:{t}")
        return issues

    def _enforce_stage2_review_only(self, agent: str, text_id: str, errors_path: str, payload: dict, forbid_keys: list[str]) -> None:
        for key in forbid_keys:
            if key in payload and payload.get(key):
                _log_error(
                    errors_path,
                    {
                        "type": "stage2_structure_error",
                        "agent": agent,
                        "run_id": self.run_id,
                        "text_id": text_id,
                        "forbidden_key": key,
                    },
                )
                raise RuntimeError(f"[stage2_structure_error] {agent} emitted forbidden key '{key}' for text_id={text_id}")

    @staticmethod
    def _map_aspect_term_to_ate_terms(term_str: str, aspect_terms: set[str]) -> str | None:
        """Map aspect_term.term to an existing ATE term via simple substring overlap."""
        for term in aspect_terms:
            if term in term_str or term_str in term:
                return term
        return None

    # Stage2 adoption reason enum (for logging / scorecard)
    OVERRIDE_REASON_RISK_RESOLVED = "risk_resolved"
    OVERRIDE_REASON_DEBATE_ACTION = "debate_action"
    OVERRIDE_REASON_GROUNDING_IMPROVED = "grounding_improved"
    OVERRIDE_REASON_CONFLICT_BLOCKED = "conflict_blocked"
    OVERRIDE_REASON_LOW_SIGNAL = "low_signal"

    def _aspect_polarity_sets(self, atsa: Any) -> Dict[str, set]:
        """Return aspect term -> set of polarities (for conflict detection)."""
        out: Dict[str, set] = {}
        for s in getattr(atsa, "aspect_sentiments", []) or []:
            t = self._term_str(s)
            if not t:
                continue
            p = getattr(s, "polarity", None)
            if p is None:
                continue
            out.setdefault(t, set()).add(p)
        return out

    def _reduce_patched_stage2_to_one_per_aspect(
        self,
        patched_stage2_atsa: Any,
        debate_output: Any,
        correction_applied_log: Optional[List[Dict[str, Any]]] = None,
    ) -> AspectSentimentStage1Schema:
        """
        대표 선택: aspect당 최대 1개 sentiment로 줄인 patched_stage2.
        conflict_blocked는 이 단일화 이후에만 평가해야 함.
        축약 우선순위: (1) override resulting_polarity (2) debate_summary.proposed_final_tuples/final_tuples (3) confidence 최대.
        """
        s2_sents = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        pol_by_term: Dict[str, str] = {}
        for log in (correction_applied_log or []):
            if isinstance(log, dict) and log.get("proposal_type") == "DEBATE_OVERRIDE" and log.get("applied"):
                t = (log.get("target_aspect") or "").strip()
                p = (log.get("resulting_polarity") or "").strip().lower()
                if p in ("pos", "positive"):
                    p = "positive"
                elif p in ("neg", "negative"):
                    p = "negative"
                elif p in ("neu", "neutral"):
                    p = "neutral"
                if t and p:
                    pol_by_term[t] = p
        if debate_output and getattr(debate_output, "summary", None):
            summary = debate_output.summary
            # (2) debate_summary.proposed_final_tuples or final_tuples polarity
            debate_tuples = getattr(summary, "proposed_final_tuples", None) or getattr(summary, "final_tuples", None) or []
            for item in debate_tuples:
                if not isinstance(item, dict):
                    continue
                raw_term = item.get("aspect_term") or item.get("term")
                term = (raw_term.get("term") or "").strip() if isinstance(raw_term, dict) else (raw_term or "").strip()
                pol_raw = item.get("polarity")
                if pol_raw is None or (isinstance(pol_raw, str) and not pol_raw.strip()):
                    continue
                pol = (pol_raw if isinstance(pol_raw, str) else str(pol_raw)).strip().lower()
                if pol in ("pos", "positive"):
                    pol = "positive"
                elif pol in ("neg", "negative"):
                    pol = "negative"
                elif pol in ("neu", "neutral"):
                    pol = "neutral"
                if term and term not in pol_by_term:
                    pol_by_term[term] = pol
        by_term: Dict[str, List[AspectSentimentItem]] = {}
        for s in s2_sents:
            t = self._term_str(s)
            if not t:
                continue
            by_term.setdefault(t, []).append(s)
        reduced: List[AspectSentimentItem] = []
        for term, group in by_term.items():
            target_pol = pol_by_term.get(term)
            if target_pol is not None:
                def _pol_norm(p: str) -> str:
                    p = (p or "").strip().lower()
                    if p in ("pos", "positive"):
                        return "positive"
                    if p in ("neg", "negative"):
                        return "negative"
                    if p in ("neu", "neutral"):
                        return "neutral"
                    return p
                chosen = next((s for s in group if _pol_norm(getattr(s, "polarity", None) or "") == target_pol), group[0])
            else:
                chosen = max(group, key=lambda s: getattr(s, "confidence", 0.0) or 0.0)
            reduced.append(chosen)
        return AspectSentimentStage1Schema(aspect_sentiments=reduced)

    def _stage2_introduces_new_conflict(
        self,
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
    ) -> bool:
        """True if stage2 has an aspect with >1 polarity where stage1 had <=1 for that aspect.
        Caller must pass patched_stage2 already reduced to one sentiment per aspect (대표 선택 이후)."""
        s1_sets = self._aspect_polarity_sets(stage1_atsa)
        s2_sets = self._aspect_polarity_sets(patched_stage2_atsa)
        for term, s2_pols in s2_sets.items():
            if len(s2_pols) <= 1:
                continue
            s1_pols = s1_sets.get(term, set())
            if len(s1_pols) <= 1:
                return True
        return False

    def _debate_has_explicit_action(self, debate_output: Any) -> bool:
        """True if debate summary has final_patch with at least one non-confirm action."""
        if not debate_output or not getattr(debate_output, "summary", None):
            return False
        summary = debate_output.summary
        patch = getattr(summary, "final_patch", None) or []
        if not patch:
            return False
        for item in patch:
            if not isinstance(item, dict):
                continue
            op = (item.get("op") or "").strip().lower()
            if op and op != "confirm_tuple":
                return True
        return False

    def _adopt_stage2_decision(
        self,
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
        stage1_validator: Any,
        stage2_validator: Any,
        debate_output: Any,
        correction_applied_log: List[Dict[str, Any]],
    ) -> tuple[bool, str, bool]:
        """
        Decide whether to adopt stage2 (patched) as final output per adopt_stage2_tuple spec.
        Returns (adopt, override_reason, override_candidate).
        """
        # 0. Stage2 없으면 채택 불가
        s2_sents = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        if not s2_sents:
            return False, self.OVERRIDE_REASON_LOW_SIGNAL, False

        # 1. Validator structural risk + stage2가 해당 risk 제거
        s1_risks = getattr(stage1_validator, "structural_risks", []) or []
        has_structural_risk = len(s1_risks) > 0
        validator_resolved = False
        if has_structural_risk and correction_applied_log:
            for c in correction_applied_log:
                if not isinstance(c, dict) or not c.get("applied"):
                    continue
                pt = c.get("proposal_type") or ""
                if pt in ("FLIP_POLARITY", "DROP_ASPECT", "REVISE_SPAN"):
                    validator_resolved = True
                    break
        if has_structural_risk and validator_resolved:
            return True, self.OVERRIDE_REASON_RISK_RESOLVED, True

        # 2. Debate 명시적 수정 제안 + conflict 비증가
        # conflict_blocked는 대표 선택(치환/단일화) 이후에만 평가: patched_stage2를 aspect당 1개로 줄인 뒤 충돌 여부 판단
        debate_explicit = self._debate_has_explicit_action(debate_output)
        if debate_explicit:
            patched_reduced = self._reduce_patched_stage2_to_one_per_aspect(
                patched_stage2_atsa, debate_output, correction_applied_log
            )
            if self._stage2_introduces_new_conflict(stage1_atsa, patched_reduced):
                return False, self.OVERRIDE_REASON_CONFLICT_BLOCKED, True
            return True, self.OVERRIDE_REASON_DEBATE_ACTION, True

        # 3. Explicit grounding 실패 -> stage2가 개선
        s1_sents = getattr(stage1_atsa, "aspect_sentiments", []) or []
        s1_explicit_count = sum(1 for s in s1_sents if not getattr(s, "is_implicit", True))
        s2_explicit_count = sum(1 for s in s2_sents if not getattr(s, "is_implicit", True))
        if s1_explicit_count == 0 and s2_explicit_count >= 1:
            return True, self.OVERRIDE_REASON_GROUNDING_IMPROVED, True

        # 4. 그 외 Stage1 유지
        return False, self.OVERRIDE_REASON_LOW_SIGNAL, False

    def compute_ev_score(
        self,
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
        debate_output: Any,
        correction_applied_log: List[Dict[str, Any]],
        would_adopt: bool,
        adopt_reason: str,
    ) -> tuple[float, Dict[str, Any]]:
        """PJ3: EV score comparing baseline (Stage1) vs proposed (Stage2). Debate hints contribute as EV components. Returns (score 0..1, components)."""
        components: Dict[str, Any] = {"debate_support": 0.0, "validator_resolved": 0.0, "alignment_improvement": 0.0, "grounding_improvement": 0.0}
        s1_sents = getattr(stage1_atsa, "aspect_sentiments", []) or []
        s2_sents = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        debate_explicit = self._debate_has_explicit_action(debate_output) if debate_output else False
        applied_override = any(
            isinstance(c, dict) and c.get("proposal_type") == "DEBATE_OVERRIDE" and c.get("applied")
            for c in (correction_applied_log or [])
        )
        components["debate_support"] = 0.4 if (debate_explicit or applied_override) else 0.0
        validator_resolved = any(
            isinstance(c, dict) and c.get("applied") and (c.get("proposal_type") or "") in ("FLIP_POLARITY", "DROP_ASPECT", "REVISE_SPAN")
            for c in (correction_applied_log or [])
        )
        components["validator_resolved"] = 0.3 if validator_resolved else 0.0
        s1_explicit = sum(1 for s in s1_sents if not getattr(s, "is_implicit", True))
        s2_explicit = sum(1 for s in s2_sents if not getattr(s, "is_implicit", True))
        components["grounding_improvement"] = 0.2 if (s1_explicit == 0 and s2_explicit >= 1) else 0.0
        s1_conf = sum(getattr(s, "confidence", 0) for s in s1_sents) / max(len(s1_sents), 1)
        s2_conf = sum(getattr(s, "confidence", 0) for s in s2_sents) / max(len(s2_sents), 1)
        components["alignment_improvement"] = min(0.1, max(0, (s2_conf - s1_conf) * 0.5))
        score = min(1.0, components["debate_support"] + components["validator_resolved"] + components["grounding_improvement"] + components["alignment_improvement"])
        return round(score, 4), components

    def _adopt_stage2_decision_with_ev(
        self,
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
        stage1_validator: Any,
        stage2_validator: Any,
        debate_output: Any,
        correction_applied_log: List[Dict[str, Any]],
    ) -> tuple[bool, str, bool, float, bool, Dict[str, Any]]:
        """PJ3: Decide adopt with EV gate. Returns (adopt, reason, override_candidate, ev_score, ev_adopted, ev_components)."""
        ev_threshold = float(self.debate_override_cfg.get("ev_threshold", 0.5))
        adopt, reason, candidate = self._adopt_stage2_decision(
            stage1_atsa, patched_stage2_atsa, stage1_validator, stage2_validator, debate_output, correction_applied_log
        )
        ev_score, ev_components = self.compute_ev_score(
            stage1_atsa, patched_stage2_atsa, debate_output, correction_applied_log, adopt, reason
        )
        if adopt and ev_score < ev_threshold:
            adopt = False
            reason = "ev_below_threshold"
        ev_adopted = adopt
        return adopt, reason, candidate, ev_score, ev_adopted, ev_components

    def _adopt_stage2_decision(
        self,
        stage1_atsa: Any,
        patched_stage2_atsa: Any,
        stage1_validator: Any,
        stage2_validator: Any,
        debate_output: Any,
        correction_applied_log: List[Dict[str, Any]],
    ) -> tuple[bool, str, bool]:
        """
        Decide whether to adopt stage2 (patched) as final output per adopt_stage2_tuple spec.
        Returns (adopt, override_reason, override_candidate).
        """
        # 0. Stage2 없으면 채택 불가
        s2_sents = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        if not s2_sents:
            return False, self.OVERRIDE_REASON_LOW_SIGNAL, False

        # 1. Validator structural risk + stage2가 해당 risk 제거
        s1_risks = getattr(stage1_validator, "structural_risks", []) or []
        has_structural_risk = len(s1_risks) > 0
        validator_resolved = False
        if has_structural_risk and correction_applied_log:
            for c in correction_applied_log:
                if not isinstance(c, dict) or not c.get("applied"):
                    continue
                pt = c.get("proposal_type") or ""
                if pt in ("FLIP_POLARITY", "DROP_ASPECT", "REVISE_SPAN"):
                    validator_resolved = True
                    break
        if has_structural_risk and validator_resolved:
            return True, self.OVERRIDE_REASON_RISK_RESOLVED, True

        # 2. Debate 명시적 수정 제안 + conflict 비증가
        debate_explicit = self._debate_has_explicit_action(debate_output)
        if debate_explicit:
            patched_reduced = self._reduce_patched_stage2_to_one_per_aspect(
                patched_stage2_atsa, debate_output, correction_applied_log
            )
            if self._stage2_introduces_new_conflict(stage1_atsa, patched_reduced):
                return False, self.OVERRIDE_REASON_CONFLICT_BLOCKED, True
            return True, self.OVERRIDE_REASON_DEBATE_ACTION, True

        # 3. Explicit grounding 실패 -> stage2가 개선
        s1_sents = getattr(stage1_atsa, "aspect_sentiments", []) or []
        s1_explicit_count = sum(1 for s in s1_sents if not getattr(s, "is_implicit", True))
        s2_explicit_count = sum(1 for s in s2_sents if not getattr(s, "is_implicit", True))
        if s1_explicit_count == 0 and s2_explicit_count >= 1:
            return True, self.OVERRIDE_REASON_GROUNDING_IMPROVED, True

        # 4. 그 외 Stage1 유지
        return False, self.OVERRIDE_REASON_LOW_SIGNAL, False

    def _apply_stage2_reviews(
        self,
        stage1_ate: AspectExtractionStage1Schema,
        stage1_atsa: AspectSentimentStage1Schema,
        stage2_ate_review: AspectExtractionStage2Schema,
        stage2_atsa_review: AspectSentimentStage2Schema,
        stage2_validator: StructuralValidatorStage2Schema | None = None,
        stage1_validator: StructuralValidatorStage1Schema | None = None,
        debate_review_context: dict | None = None,
        input_text: str = "",
    ) -> tuple[AspectExtractionStage1Schema, AspectSentimentStage1Schema, list[str], List[Dict[str, Any]]]:
        """
        Apply stage2 review actions to stage1 outputs to construct patched stage2 outputs.
        Keeps original review objects in process_trace; only patched structures are returned.
        Returns: (patched_ate, patched_atsa, anchor_issues, correction_applied_log)
        """
        aspects: List[AspectExtractionItem] = [AspectExtractionItem(**a.model_dump()) for a in getattr(stage1_ate, "aspects", [])]
        sentiments: List[AspectSentimentItem] = [AspectSentimentItem(**s.model_dump()) for s in getattr(stage1_atsa, "aspect_sentiments", [])]

        def find_aspect_idx(term: str) -> int | None:
            for idx, aspect in enumerate(aspects):
                if aspect.term == term:
                    return idx
            return None

        review_present = False
        correction_applied_log: List[Dict[str, Any]] = []

        # Apply Validator correction_proposals from stage1 (if present)
        if stage1_validator:
            proposals = getattr(stage1_validator, "correction_proposals", []) or []
            for prop in proposals:
                prop_type = getattr(prop, "proposal_type", "").upper()
                target_aspect = getattr(prop, "target_aspect", "")
                rationale = getattr(prop, "rationale", "")
                
                applied = False
                reason = ""
                
                if prop_type == "FLIP_POLARITY" and target_aspect:
                    # Find matching sentiment and flip
                    for s in sentiments:
                        if self._term_str(s) == target_aspect:
                            old_pol = s.polarity
                            new_pol = "negative" if old_pol == "positive" else "positive" if old_pol == "negative" else "neutral"
                            s.polarity = new_pol
                            s.polarity_distribution = {new_pol: 0.9, old_pol: 0.1}
                            s.confidence = max(s.confidence, 0.9)
                            applied = True
                            reason = f"flipped {old_pol}->{new_pol}"
                            break
                    if not applied:
                        reason = f"target_aspect '{target_aspect}' not found in sentiments"
                
                elif prop_type == "DROP_ASPECT" and target_aspect:
                    # Remove aspect and its sentiments
                    aspects = [a for a in aspects if a.term != target_aspect]
                    sentiments = [s for s in sentiments if self._term_str(s) != target_aspect]
                    applied = True
                    reason = "dropped aspect and sentiments"
                
                elif prop_type == "REVISE_SPAN" and target_aspect:
                    # Find and revise span
                    idx = find_aspect_idx(target_aspect)
                    if idx is not None and hasattr(prop, "revised_span"):
                        aspects[idx].span = prop.revised_span
                        applied = True
                        reason = "revised span"
                    else:
                        reason = f"target_aspect '{target_aspect}' not found or no revised_span"
                
                correction_applied_log.append({
                    "proposal_type": prop_type,
                    "target_aspect": target_aspect,
                    "rationale": rationale,
                    "applied": applied,
                    "reason": reason,
                })

        # Build provenance hints: aspect_term (string) -> "source:.../..."
        provenance_map: dict[str, str] = {}
        if self.enable_debate_override and isinstance(debate_review_context, dict):
            for aspect, hints in (debate_review_context.get("aspect_hints") or {}).items():
                if hints:
                    h0 = hints[0]
                    speaker = h0.get("speaker") or "unknown"
                    stance = h0.get("stance") or "unknown"
                    provenance_map[aspect] = f"source:{speaker}/{stance}"

        def _append_provenance(reason: str, aspect_term_str: str | None, existing_provenance: str | None) -> str:
            if existing_provenance:
                return reason
            if not aspect_term_str:
                return reason
            hint = provenance_map.get(aspect_term_str)
            if not hint:
                return reason
            if hint in (reason or ""):
                return reason
            return f"{reason} | {hint}".strip(" |")

        # Apply ATE review actions
        for review in getattr(stage2_ate_review, "aspect_review", []):
            action = (review.action or "keep").lower()
            term = review.term
            review_present = True
            if action in {"keep", "maintain"}:
                continue
            if action in {"revise_span", "revise"} and review.revised_span:
                idx = find_aspect_idx(term)
                if idx is not None:
                    aspects[idx].span = review.revised_span
            elif action in {"drop", "remove"}:
                aspects = [a for a in aspects if a.term != term]
                sentiments = [s for s in sentiments if self._term_str(s) != term]
            elif action == "add":
                if review.revised_span:
                    aspects.append(
                        AspectExtractionItem(
                            term=term,
                            span=review.revised_span,
                            confidence=0.8,
                            rationale=_append_provenance(review.reason or "", term, getattr(review, "provenance", None)),
                        )
                    )

        # Apply ATSA review actions
        for review in getattr(stage2_atsa_review, "sentiment_review", []):
            action = (review.action or "maintain").lower()
            target_term = review.aspect_term
            review_present = True
            if action in {"drop", "remove"}:
                sentiments = [s for s in sentiments if self._term_str(s) != target_term]
                continue

            matching = [s for s in sentiments if self._term_str(s) == target_term]

            # Optionally add a sentiment if none existed but stage2 proposes one
            if not matching and action == "add" and review.revised_polarity:
                sentiments.append(
                    AspectSentimentItem(
                        aspect_term=AspectTerm(term=target_term, span=Span(start=0, end=0)),
                        polarity=review.revised_polarity,
                        evidence=_append_provenance(review.reason or "", target_term, getattr(review, "provenance", None)),
                        confidence=0.9,
                        polarity_distribution={review.revised_polarity: 0.9},
                    )
                )
                continue

            for sentiment in matching:
                if action == "flip_polarity":
                    old_pol = sentiment.polarity
                    new_pol = review.revised_polarity or ("negative" if old_pol == "positive" else "positive" if old_pol == "negative" else "negative")
                    sentiment.polarity = new_pol
                    sentiment.polarity_distribution = {new_pol: 0.9, old_pol: 0.1}
                    sentiment.confidence = max(sentiment.confidence, 0.9)
                if action in {"revise_opinion_span", "revise_span"}:
                    new_span = getattr(review, "revised_opinion_span", None)
                    new_term = getattr(review, "revised_opinion_term", None)
                    if new_span:
                        if sentiment.aspect_term:
                            sentiment.aspect_term.span = new_span
                            if new_term:
                                sentiment.aspect_term.term = new_term
                        else:
                            sentiment.aspect_term = AspectTerm(term=new_term or target_term, span=new_span)
                if action == "revise_opinion_term":
                    new_term = getattr(review, "revised_opinion_term", None)
                    if new_term:
                        if sentiment.aspect_term:
                            sentiment.aspect_term.term = new_term
                        else:
                            sentiment.aspect_term = AspectTerm(term=new_term, span=Span(start=0, end=0))

        # Debate override: apply direct debate hints when Stage2 review was silent or weak.
        # Hard rules: L3-relevant risk → no polarity flip (conservative); implicit → soft hint only, no direct action.
        if not self.enable_debate_override:
            self._override_stats["override_disabled"] = True
            self._override_stats["applied"] = 0
        elif isinstance(debate_review_context, dict):
            min_total = float(self.debate_override_cfg.get("min_total", 1.6))
            min_margin = float(self.debate_override_cfg.get("min_margin", 0.8))
            min_target_conf = float(self.debate_override_cfg.get("min_target_conf", 0.7))
            l3_conservative = self.debate_override_cfg.get("l3_conservative", True)
            ev_threshold = float(self.debate_override_cfg.get("ev_threshold", 0.5))
            aspect_hints = debate_review_context.get("aspect_hints") or {}
            thresholds = {"min_total": min_total, "min_margin": min_margin, "min_target_conf": min_target_conf, "l3_conservative": l3_conservative, "ev_threshold": ev_threshold}
            profile_id = getattr(self, "_override_profile_id", None)
            l3_tags = {"NEGATION_SCOPE", "CONTRAST_SCOPE", "POLARITY_MISMATCH", "NEGATION", "CONTRAST", "IRONY"}
            l3_types: List[str] = []
            has_l3_risk = False
            if l3_conservative and stage1_validator:
                risks = getattr(stage1_validator, "structural_risks", []) or []
                for r in risks:
                    t = (getattr(r, "type", None) or "").upper().replace(" ", "_")
                    if t in l3_tags:
                        has_l3_risk = True
                        l3_types.append(t)
            summary = debate_review_context.get("summary") or {}
            aspect_evidence = summary.get("aspect_evidence") or {}
            sentence_evidence_spans = summary.get("sentence_evidence_spans") or []
            override_applied_this_sample = False
            for aspect_term_str, hints in aspect_hints.items():
                if not aspect_term_str or not isinstance(hints, list):
                    continue
                # Canonicalize polarity per hint: whitelist or edit-distance 1~2 repair; drop invalid, count repair/invalid
                valid_hints: List[Dict[str, Any]] = []
                invalid_hint_count = 0
                hint_repair_count = 0
                hint_polarity_sample: List[Dict[str, str]] = []
                for h in hints:
                    raw_pol = h.get("polarity_hint")
                    canon_pol, was_repair = canonicalize_polarity_with_repair(raw_pol)
                    if canon_pol is None:
                        invalid_hint_count += 1
                        self._override_stats["override_hint_invalid_total"] = self._override_stats.get("override_hint_invalid_total", 0) + 1
                        if len(hint_polarity_sample) < 5:
                            hint_polarity_sample.append({"raw_polarity": str(raw_pol)[:80], "canon_polarity": None})
                        continue
                    if was_repair:
                        hint_repair_count += 1
                        self._override_stats["override_hint_repair_total"] = self._override_stats.get("override_hint_repair_total", 0) + 1
                    valid_hints.append({**h, "polarity_hint": canon_pol})
                    if len(hint_polarity_sample) < 5:
                        hint_polarity_sample.append({"raw_polarity": str(raw_pol)[:80], "canon_polarity": canon_pol})
                valid_hint_count = sum(1 for h in valid_hints if h.get("polarity_hint") in ("positive", "negative"))
                pos_score = sum(float(h.get("weight") or 0) for h in valid_hints if h.get("polarity_hint") == "positive")
                neg_score = sum(float(h.get("weight") or 0) for h in valid_hints if h.get("polarity_hint") == "negative")
                total = pos_score + neg_score
                margin = abs(pos_score - neg_score)
                target_pol = "positive" if pos_score > neg_score else "negative"
                # 1-5: 점수 계산 직전 디버그 로그 (1샘플만)
                if getattr(self, "_current_sample_idx", None) == 0 and not getattr(self, "_override_debug_logged", False):
                    hints_count = len(hints)
                    per_hint = [{"speaker": h.get("speaker"), "polarity_hint": h.get("polarity_hint"), "weight": h.get("weight")} for h in hints]
                    print(
                        "[override_gate_debug] sample_idx=0 aspect=%s hints_count=%s valid_hint_count=%s invalid_hint_count=%s per_hint=%s pos_score=%.4f neg_score=%.4f total=%.4f margin=%.4f"
                        % (aspect_term_str, hints_count, valid_hint_count, invalid_hint_count, per_hint, pos_score, neg_score, total, margin),
                        flush=True,
                    )
                    self._override_debug_logged = True
                matching = [s for s in sentiments if self._term_str(s) == aspect_term_str]
                first_sent = matching[0] if matching else None
                current_pol = getattr(first_sent, "polarity", None) if first_sent else None
                current_conf = getattr(first_sent, "confidence", None) if first_sent else None
                is_implicit = any(getattr(s, "is_implicit", False) for s in matching)

                def _gate_record(decision: str, skip_reason: Optional[str] = None, override_action: Optional[str] = None, evidence_ok: Optional[bool] = None, evidence_reason: Optional[str] = None) -> Dict[str, Any]:
                    rec = {
                        "text_id": getattr(self, "_current_text_id", ""),
                        "sample_idx": getattr(self, "_current_sample_idx", None),
                        "aspect_term": aspect_term_str,
                        "aspect_key": aspect_term_str,
                        "valid_hint_count": valid_hint_count,
                        "invalid_hint_count": invalid_hint_count,
                        "hint_repair_count": hint_repair_count,
                        "hint_polarity_sample": hint_polarity_sample,
                        "profile_id": profile_id,
                        "pos_score": round(pos_score, 4),
                        "neg_score": round(neg_score, 4),
                        "total": round(total, 4),
                        "margin": round(margin, 4),
                        "target_pol": target_pol,
                        "current_pol": current_pol,
                        "current_conf": round(current_conf, 4) if current_conf is not None else None,
                        "stage2_conf": None,
                        "is_implicit": is_implicit,
                        "l3_flag": has_l3_risk,
                        "l3_types": list(l3_types),
                        "thresholds": dict(thresholds),
                        "decision": decision,
                        "skip_reason": skip_reason,
                        "override_action": override_action,
                        "evidence_ok": evidence_ok,
                        "evidence_reason": evidence_reason,
                    }
                    return rec

                if override_applied_this_sample:
                    self._override_stats["skipped_max_one_override_per_sample"] += 1
                    rec = _gate_record("SKIP", "max_one_override_per_sample", None, None, None)
                    self._append_override_gate_record(rec)
                    continue

                if valid_hint_count == 0:
                    self._override_stats["skipped_neutral_only"] += 1
                    self._override_stats["skipped_low_signal"] += 1
                    rec = _gate_record("SKIP", "neutral_only", None, None, None)
                    self._append_override_gate_record(rec)
                    continue

                evidence_span = aspect_evidence.get(aspect_term_str) or (sentence_evidence_spans[0] if sentence_evidence_spans else None)
                evidence_ok, evidence_reason = self.has_actionable_evidence(input_text, evidence_span, "override")
                if not evidence_ok:
                    if evidence_reason == "no_evidence_span":
                        self._override_stats["skipped_no_evidence_span"] += 1
                    elif evidence_reason == "evidence_span_not_in_text":
                        self._override_stats["skipped_evidence_span_not_in_text"] += 1
                    else:
                        self._override_stats["skipped_evidence_span_missing_trigger"] += 1
                    rec = _gate_record("SKIP", evidence_reason, None, False, evidence_reason)
                    self._append_override_gate_record(rec)
                    continue

                if total < min_total:
                    self._override_stats["skipped_low_signal"] += 1
                    rec = _gate_record("SKIP", "low_signal", None, True, None)
                    self._append_override_gate_record(rec)
                    continue
                if margin < min_margin:
                    self._override_stats["skipped_conflict"] += 1
                    self._override_stats["skipped_conflict_reasons"]["action_ambiguity"] += 1
                    rec = _gate_record("SKIP", "action_ambiguity", None, True, None)
                    self._append_override_gate_record(rec)
                    continue
                if has_l3_risk:
                    self._override_stats["skipped_conflict"] += 1
                    self._override_stats["skipped_conflict_reasons"]["L3_conservative"] += 1
                    rec = _gate_record("SKIP", "l3_conservative", None, True, None)
                    self._append_override_gate_record(rec)
                    continue
                if any(getattr(s, "is_implicit", False) for s in matching):
                    self._override_stats["skipped_conflict"] += 1
                    self._override_stats["skipped_conflict_reasons"]["implicit_soft_only"] += 1
                    rec = _gate_record("SKIP", "implicit_soft_only", None, True, None)
                    self._append_override_gate_record(rec)
                    continue
                if not matching:
                    sentiments.append(
                        AspectSentimentItem(
                            aspect_term=AspectTerm(term=aspect_term_str, span=Span(start=0, end=0)),
                            polarity=target_pol,
                            evidence="debate_override",
                            confidence=min_target_conf,
                            polarity_distribution={target_pol: 0.8},
                        )
                    )
                    self._override_stats["applied"] += 1
                    override_applied_this_sample = True
                    correction_applied_log.append(
                        {
                            "proposal_type": "DEBATE_OVERRIDE",
                            "target_aspect": aspect_term_str,
                            "resulting_polarity": target_pol,
                            "rationale": f"debate_hint {target_pol}",
                            "applied": True,
                            "reason": "debate_override_add",
                        }
                    )
                    rec = _gate_record("APPLY", None, f"add {target_pol}, conf={min_target_conf}", True, None)
                    self._append_override_gate_record(rec)
                    continue
                override_action_str: Optional[str] = None
                for sentiment in matching:
                    if sentiment.confidence >= min_target_conf and sentiment.polarity == target_pol:
                        self._override_stats["skipped_already_confident"] += 1
                        continue
                    old_pol = sentiment.polarity
                    sentiment.polarity = target_pol
                    sentiment.polarity_distribution = {target_pol: 0.8, old_pol: 0.2}
                    sentiment.confidence = max(sentiment.confidence, min_target_conf)
                    self._override_stats["applied"] += 1
                    override_applied_this_sample = True
                    correction_applied_log.append(
                        {
                            "proposal_type": "DEBATE_OVERRIDE",
                            "target_aspect": aspect_term_str,
                            "resulting_polarity": target_pol,
                            "rationale": f"debate_hint {target_pol}",
                            "applied": True,
                            "reason": f"debate_override_flip {old_pol}->{target_pol}",
                        }
                    )
                    if override_action_str is None:
                        override_action_str = f"flip {old_pol}->{target_pol}, conf={max(sentiment.confidence, min_target_conf)}"
                rec = _gate_record("APPLY", None, override_action_str, True, None) if override_action_str else _gate_record("SKIP", "already_confident", None, True, None)
                self._append_override_gate_record(rec)

        # Final guard: drop sentiments whose aspects were removed by ATE review
        aspect_terms = {a.term for a in aspects}
        anchor_issues: list[str] = []
        mapped_sentiments: list[AspectSentimentItem] = []
        for s in sentiments:
            t = self._term_str(s)
            mapped = self._map_aspect_term_to_ate_terms(t, aspect_terms)
            if mapped is None:
                anchor_issues.append(f"dropped_unanchored_aspect_term:{t}")
                continue
            if mapped != t:
                anchor_issues.append(f"mapped_aspect_term:{t}->{mapped}")
                s.aspect_term = AspectTerm(term=mapped, span=s.aspect_term.span if s.aspect_term else Span(start=0, end=0))
            mapped_sentiments.append(s)

        sentiments = [s for s in mapped_sentiments if self._term_str(s) in aspect_terms]

        # If reviews existed but no sentiments remain, create a neutral placeholder on first aspect to keep confidence >0.
        # Do not add placeholder when all sentiments were dropped as unanchored (test: drop unmatched aspect term).
        dropped_unanchored_only = any("dropped_unanchored" in i for i in anchor_issues)
        if review_present and not sentiments and aspect_terms and not dropped_unanchored_only:
            fallback_term = next(iter(aspect_terms))
            sentiments.append(
                AspectSentimentItem(
                    aspect_term=AspectTerm(term=fallback_term, span=Span(start=0, end=0)),
                    polarity="neutral",
                    confidence=0.5,
                    evidence="stage2 review present; placeholder sentiment",
                    polarity_distribution={"neutral": 0.5},
                    is_backfilled=True,
                    neutral_reason="stage2_placeholder_no_sentiments",
                )
            )

        # Merge any validator issues if present
        if stage2_validator and hasattr(stage2_validator, "final_validation"):
            anchor_issues.extend(getattr(stage2_validator, "issues", []))

        patched_ate = AspectExtractionStage1Schema(aspects=aspects)
        patched_atsa = AspectSentimentStage1Schema(aspect_sentiments=sentiments)
        return patched_ate, patched_atsa, anchor_issues, correction_applied_log

    @staticmethod
    def _inject_review_provenance(
        *,
        reviews: list,
        key_field: str,
        debate_review_context: dict,
    ) -> None:
        if not reviews or not isinstance(debate_review_context, dict):
            return
        aspect_hints = debate_review_context.get("aspect_hints") or {}
        for review in reviews:
            try:
                key = getattr(review, key_field, None)
                if not key:
                    continue
                if getattr(review, "provenance", None):
                    continue
                hints = aspect_hints.get(key) or []
                if not hints:
                    continue
                h0 = hints[0]
                speaker = h0.get("speaker") or "unknown"
                stance = h0.get("stance") or "unknown"
                setattr(review, "provenance", f"source:{speaker}/{stance}")
            except Exception:
                continue
