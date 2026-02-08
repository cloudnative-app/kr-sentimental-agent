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
)
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample
from tools.llm_runner import StructuredResult, _log_error, default_errors_path
from agents.specialized_agents import ATEAgent, ATSAAgent, ValidatorAgent, Moderator
from agents.debate_orchestrator import DebateOrchestrator
from tools.pattern_loader import load_patterns
from memory.episodic_orchestrator import EpisodicOrchestrator
from pathlib import Path
from metrics.eval_tuple import tuples_from_list, tuples_to_list_of_dicts


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
        self.enable_stage2 = self.config.get("enable_stage2", True)
        self.enable_validator = self.config.get("enable_validator", True)
        self.enable_moderator = self.config.get("enable_moderator", True)
        self.enable_debate = self.config.get("enable_debate", True)
        self.enable_debate_override = self.config.get("enable_debate_override", True)
        self.debate_override_cfg = self._load_debate_override_cfg(self.config.get("debate_override"))
        self.run_id = run_id or "run"
        self.ate_agent = ate_agent or ATEAgent(self.backbone)
        self.atsa_agent = atsa_agent or ATSAAgent(self.backbone)
        self.validator = validator or ValidatorAgent(self.backbone)
        self.moderator = moderator or Moderator()
        self.debate = DebateOrchestrator(self.backbone, config=self.config.get("debate"))
        self._pattern_cache: dict[str, dict] = {}
        self._override_stats: dict[str, int] = {"applied": 0, "skipped_low_signal": 0, "skipped_conflict": 0, "skipped_already_confident": 0}
        episodic_cfg = self.config.get("episodic_memory")
        self._episodic_orchestrator: Optional[EpisodicOrchestrator] = EpisodicOrchestrator(episodic_cfg) if episodic_cfg else None

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
        # Post-process ATE aspects: strip topic particles, enforce contrast rule
        ate_aspects = getattr(ate_result.model, "aspects", [])
        ate_aspects = self._clean_aspects(text, ate_aspects, language_code=language_code, )
        ate_aspects = self._enforce_contrast_min_aspects(text, ate_aspects, language_code=language_code)
        ate_result.model.aspects = ate_aspects

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
        # Ensure sentiments align to aspects; backfill missing aspect sentiments neutrally
        atsa_sents = getattr(atsa_result.model, "aspect_sentiments", [])
        atsa_sents = self._backfill_sentiments(text, ate_aspects, atsa_sents)
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
        return {"ate": ate_result.model, "atsa": atsa_result.model, "validator": validator_model}

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
        self._override_stats = {"applied": 0, "skipped_low_signal": 0, "skipped_conflict": 0, "skipped_already_confident": 0}
        self._last_memory_meta = None
        text = example.text
        text_id = getattr(example, "uid", "text") or "text"
        case_type = getattr(example, "case_type", None) or "unknown"
        split = getattr(example, "split", None) or "unknown"
        language_code = getattr(example, "language_code", None) or "unknown"
        domain_id = getattr(example, "domain_id", None) or "unknown"
        demos = []
        if getattr(example, "metadata", None):
            demos = list(getattr(example, "metadata").get("demo_texts") or [])
        trace: list[ProcessTrace] = []

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
                # C3(silent): retrieval은 수행하되 debate prompt에는 노출하지 않음
                exposed_to_debate = memory_meta.get("exposed_to_debate", False)
                if exposed_to_debate and slot_dict:
                    ctx = json.loads(debate_context)
                    ctx.update(slot_dict)
                    debate_context = json.dumps(ctx, ensure_ascii=False)
                    memory_meta["prompt_injection_chars"] = len(json.dumps(slot_dict, ensure_ascii=False))
                else:
                    memory_meta["prompt_injection_chars"] = 0
                self._last_memory_meta = memory_meta
            else:
                self._last_memory_meta = None
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
        )
        self.patched_stage2_ate = patched_stage2_ate
        self.patched_stage2_atsa = patched_stage2_atsa

        # Aggregate ATE/ATSA into legacy outputs for moderator decision
        agg_stage1_ate = self._aggregate_label_from_sentiments(stage1["atsa"])
        agg_stage2_ate = self._aggregate_label_from_sentiments(patched_stage2_atsa)
        stage1_atsa_out = ATSAOutput(target=None, label=agg_stage1_ate.label, confidence=agg_stage1_ate.confidence, rationale=agg_stage1_ate.rationale)
        stage2_atsa_out = ATSAOutput(target=None, label=agg_stage2_ate.label, confidence=agg_stage2_ate.confidence, rationale=agg_stage2_ate.rationale)
        stage1_validator_out = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=stage1_anchor_issues, confidence=agg_stage1_ate.confidence)
        stage2_validator_out = ValidatorOutput(agrees_with_ate=True, agrees_with_atsa=True, suggested_label=None, issues=stage2_anchor_issues, confidence=agg_stage2_ate.confidence)

        # Get final aspect_sentiments (only from ATE-kept aspects)
        final_aspect_sentiments = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        # Ensure only ATE-kept aspects are included (match by aspect_term.term)
        kept_aspect_terms = {a.term for a in getattr(patched_stage2_ate, "aspects", [])}
        final_aspect_sentiments = [s for s in final_aspect_sentiments if self._term_str(s) in kept_aspect_terms]
        
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
        stage1_sents = getattr(stage1["atsa"], "aspect_sentiments", []) or []
        stage2_sents = getattr(patched_stage2_atsa, "aspect_sentiments", []) or []
        stage1_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage1_sents]))
        stage2_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage2_sents]))
        final_tuples = tuples_to_list_of_dicts(tuples_from_list(final_aspects_list))

        final_result = FinalResult(
            label=moderator_out.final_label,
            confidence=final_confidence_score,
            rationale=moderator_out.rationale,
            final_aspects=final_aspects_list,
            stage1_tuples=stage1_tuples,
            stage2_tuples=stage2_tuples,
            final_tuples=final_tuples,
        )

        flags = AnalysisFlags(
            correction_occurred=correction_occurred,
            conflict_resolved=conflict_resolved,
            final_confidence_score=final_confidence_score,
            stage2_executed=True,
        )

        if self._episodic_orchestrator:
            self._episodic_orchestrator.append_episode_if_needed(
                text, text_id,
                stage1["ate"], stage1["atsa"], stage1["validator"],
                patched_stage2_ate, patched_stage2_atsa, stage2["validator"],
                moderator_out, language_code=language_code, split=split or "unknown",
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
        if debate_output:
            meta_extra["debate_summary"] = debate_output.summary.model_dump()
            meta_extra["debate_review_context"] = json.loads(debate_context_json) if debate_context_json else None
            meta_extra["debate_override_stats"] = self._override_stats
        if getattr(self, "_last_memory_meta", None) is not None:
            meta_extra["memory"] = self._last_memory_meta

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
        for r in rounds:
            for t in r.turns:
                parts = [t.message or ""] + (t.key_points or [])
                text_blob = " ".join(parts)
                blob_norm = re.sub(r"\s+", "", text_blob.lower())
                blob_norm = re.sub(r"[^\w가-힣]", "", blob_norm)
                mapped = [orig for key, orig in norm_map.items() if key and key in blob_norm]
                mapped = list(dict.fromkeys(mapped))
                direct_mapped = bool(mapped)
                stance_weight = self._stance_weight(t.stance)
                polarity_hint = self._stance_to_polarity(t.stance)
                if not mapped:
                    mapped = self._fallback_map_from_atsa(
                        stage1_atsa=stage1_atsa,
                        polarity_hint=polarity_hint,
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
                    elif polarity_hint == "neutral":
                        fail_reason = "neutral_stance"
                    else:
                        fail_reason = "no_match"
                if fail_reason and fail_reason in mapping_fail_reasons:
                    mapping_fail_reasons[fail_reason] += 1
                rebuttals.append(
                    {
                        "speaker": t.speaker,
                        "stance": t.stance,
                        "key_points": t.key_points,
                        "message": t.message,
                        "aspect_terms": mapped,
                        "mapping_confidence": mapping_confidence,
                        "mapping_fail_reason": fail_reason,
                        "weight": stance_weight,
                        "polarity_hint": polarity_hint,
                        "provenance_hint": f"source:{t.speaker}/{t.stance}",
                    }
                )
                aspect_map.append(
                    {
                        "rebuttal_index": idx,
                        "speaker": t.speaker,
                        "stance": t.stance,
                        "aspect_terms": mapped,
                        "weight": stance_weight,
                        "polarity_hint": polarity_hint,
                    }
                )
                idx += 1
        aspect_hints = {}
        for item in aspect_map:
            for aspect in item.get("aspect_terms") or []:
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

    def _load_debate_override_cfg(self, override_cfg: dict | None) -> dict:
        if isinstance(override_cfg, dict) and override_cfg:
            return override_cfg
        cfg_path = Path("experiments") / "configs" / "debate_override_thresholds.json"
        if not cfg_path.exists():
            return {}
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

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
        polarity_hint: str,
    ) -> list[str]:
        def _t(sent):
            return (sent.aspect_term.term if sent.aspect_term else "") or ""
        sentiments = getattr(stage1_atsa, "aspect_sentiments", []) or []
        if not sentiments:
            return []
        if polarity_hint == "neutral":
            refs = [_t(s) for s in sentiments if _t(s)]
            return [refs[0]] if len(set(refs)) == 1 else []
        candidates = [s for s in sentiments if s.polarity == polarity_hint and _t(s)]
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
        return ATEOutput(label=best.polarity, confidence=best.confidence, rationale=best.evidence or "")

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

    def _apply_stage2_reviews(
        self,
        stage1_ate: AspectExtractionStage1Schema,
        stage1_atsa: AspectSentimentStage1Schema,
        stage2_ate_review: AspectExtractionStage2Schema,
        stage2_atsa_review: AspectSentimentStage2Schema,
        stage2_validator: StructuralValidatorStage2Schema | None = None,
        stage1_validator: StructuralValidatorStage1Schema | None = None,
        debate_review_context: dict | None = None,
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

        # Debate override: apply direct debate hints when Stage2 review was silent or weak
        if isinstance(debate_review_context, dict):
            min_total = float(self.debate_override_cfg.get("min_total", 1.6))
            min_margin = float(self.debate_override_cfg.get("min_margin", 0.8))
            min_target_conf = float(self.debate_override_cfg.get("min_target_conf", 0.7))
            aspect_hints = debate_review_context.get("aspect_hints") or {}
            for aspect_term_str, hints in aspect_hints.items():
                if not aspect_term_str or not isinstance(hints, list):
                    continue
                pos_score = sum(float(h.get("weight") or 0) for h in hints if h.get("polarity_hint") == "positive")
                neg_score = sum(float(h.get("weight") or 0) for h in hints if h.get("polarity_hint") == "negative")
                total = pos_score + neg_score
                if total < min_total:
                    self._override_stats["skipped_low_signal"] += 1
                    continue
                if abs(pos_score - neg_score) < min_margin:
                    self._override_stats["skipped_conflict"] += 1
                    continue
                target_pol = "positive" if pos_score > neg_score else "negative"

                matching = [s for s in sentiments if self._term_str(s) == aspect_term_str]
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
                    correction_applied_log.append(
                        {
                            "proposal_type": "DEBATE_OVERRIDE",
                            "target_aspect": aspect_term_str,
                            "rationale": f"debate_hint {target_pol}",
                            "applied": True,
                            "reason": "debate_override_add",
                        }
                    )
                    continue
                for sentiment in matching:
                    if sentiment.confidence >= min_target_conf and sentiment.polarity == target_pol:
                        self._override_stats["skipped_already_confident"] += 1
                        continue
                    old_pol = sentiment.polarity
                    sentiment.polarity = target_pol
                    sentiment.polarity_distribution = {target_pol: 0.8, old_pol: 0.2}
                    sentiment.confidence = max(sentiment.confidence, min_target_conf)
                    self._override_stats["applied"] += 1
                    correction_applied_log.append(
                        {
                            "proposal_type": "DEBATE_OVERRIDE",
                            "target_aspect": aspect_term_str,
                            "rationale": f"debate_hint {target_pol}",
                            "applied": True,
                            "reason": f"debate_override_flip {old_pol}->{target_pol}",
                        }
                    )

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

        # If reviews existed but no sentiments remain, create a neutral placeholder on first aspect to keep confidence >0
        if review_present and not sentiments and aspect_terms:
            fallback_term = next(iter(aspect_terms))
            sentiments.append(
                AspectSentimentItem(
                    aspect_term=AspectTerm(term=fallback_term, span=Span(start=0, end=0)),
                    polarity="neutral",
                    confidence=0.5,
                    evidence="stage2 review present; placeholder sentiment",
                    polarity_distribution={"neutral": 0.5},
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
