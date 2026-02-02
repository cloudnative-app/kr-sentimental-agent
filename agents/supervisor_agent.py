from __future__ import annotations

from typing import Dict, Optional, List
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
    OpinionTerm,
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
from tools.pattern_loader import load_patterns


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
        self.run_id = run_id or "run"
        self.ate_agent = ate_agent or ATEAgent(self.backbone)
        self.atsa_agent = atsa_agent or ATSAAgent(self.backbone)
        self.validator = validator or ValidatorAgent(self.backbone)
        self.moderator = moderator or Moderator()
        self._pattern_cache: dict[str, dict] = {}

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
        stage2 = self._run_stage2(
            text,
            trace,
            text_id,
            demos=demos,
            language_code=language_code,
            domain_id=domain_id,
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
        # Ensure only ATE-kept aspects are included
        kept_aspect_terms = {a.term for a in getattr(patched_stage2_ate, "aspects", [])}
        final_aspect_sentiments = [s for s in final_aspect_sentiments if s.aspect_ref in kept_aspect_terms]
        
        moderator_out = self.moderator.decide(
            agg_stage1_ate,
            agg_stage1_ate,  # use same for ATE/ATSA labels placeholder
            stage1_validator_out,
            agg_stage2_ate,
            agg_stage2_ate,
            final_aspect_sentiments=final_aspect_sentiments,
        )
        trace.append(ProcessTrace(stage="moderator", agent="Moderator", input_text=text, output=moderator_out.model_dump()))

        correction_occurred = agg_stage2_ate.label != agg_stage1_ate.label
        conflict_resolved = correction_occurred

        final_confidence_score = moderator_out.confidence

        # Build final_aspects list from final aspect_sentiments
        final_aspects_list = self.moderator.build_final_aspects(final_aspect_sentiments)

        final_result = FinalResult(
            label=moderator_out.final_label,
            confidence=final_confidence_score,
            rationale=moderator_out.rationale,
            final_aspects=final_aspects_list,
        )

        flags = AnalysisFlags(
            correction_occurred=correction_occurred,
            conflict_resolved=conflict_resolved,
            final_confidence_score=final_confidence_score,
            stage2_executed=True,
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

        result = FinalOutputSchema(
            meta=meta_extra,
            stage1_ate=agg_stage1_ate,
            stage1_atsa=stage1_atsa_out,
            stage1_validator=stage1_validator_out,
            stage2_ate=agg_stage2_ate,
            stage2_atsa=stage2_atsa_out,
            stage2_validator=stage2_validator_out,
            moderator=moderator_out,
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
        by_ref = {s.aspect_ref for s in sentiments}
        for a in aspects:
            if a.term not in by_ref:
                sentiments.append(
                    AspectSentimentItem(
                        aspect_ref=a.term,
                        polarity="neutral",
                        opinion_term=None,
                        evidence=text,
                        confidence=0.5,
                        polarity_distribution={"neutral": 1.0},
                        is_implicit=False,
                    )
                )
        return sentiments

    def _find_unanchored_aspects(self, ate: AspectExtractionStage1Schema, atsa: AspectSentimentStage1Schema) -> list[str]:
        """Detect aspect_sentiments whose aspect_ref is not among ATE terms."""
        ate_terms = {a.term for a in getattr(ate, "aspects", [])}
        issues: list[str] = []
        for s in getattr(atsa, "aspect_sentiments", []):
            if s.aspect_ref not in ate_terms:
                issues.append(f"stage1_aspect_ref_not_in_ate:{s.aspect_ref}")
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
    def _map_aspect_ref_to_terms(ref: str, aspect_terms: set[str]) -> str | None:
        """Map aspect_ref to an existing ATE term via simple substring overlap."""
        for term in aspect_terms:
            if term in ref or ref in term:
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
                        if s.aspect_ref == target_aspect:
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
                    sentiments = [s for s in sentiments if s.aspect_ref != target_aspect]
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
                sentiments = [s for s in sentiments if s.aspect_ref != term]
            elif action == "add":
                if review.revised_span:
                    aspects.append(
                        AspectExtractionItem(
                            term=term,
                            span=review.revised_span,
                            confidence=0.8,
                            rationale=review.reason or "",
                        )
                    )

        # Apply ATSA review actions
        for review in getattr(stage2_atsa_review, "sentiment_review", []):
            action = (review.action or "maintain").lower()
            aspect_ref = review.aspect_ref
            review_present = True
            if action in {"drop", "remove"}:
                sentiments = [s for s in sentiments if s.aspect_ref != aspect_ref]
                continue

            matching = [s for s in sentiments if s.aspect_ref == aspect_ref]

            # Optionally add a sentiment if none existed but stage2 proposes one
            if not matching and action == "add" and review.revised_polarity:
                sentiments.append(
                    AspectSentimentItem(
                        aspect_ref=aspect_ref,
                        polarity=review.revised_polarity,
                        evidence=review.reason or "",
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
                        if sentiment.opinion_term:
                            sentiment.opinion_term.span = new_span
                            if new_term:
                                sentiment.opinion_term.term = new_term
                        else:
                            sentiment.opinion_term = OpinionTerm(term=new_term or aspect_ref, span=new_span)
                if action == "revise_opinion_term":
                    new_term = getattr(review, "revised_opinion_term", None)
                    if new_term:
                        if sentiment.opinion_term:
                            sentiment.opinion_term.term = new_term
                        else:
                            sentiment.opinion_term = OpinionTerm(term=new_term, span=Span(start=0, end=0))

        # Final guard: drop sentiments whose aspects were removed by ATE review
        aspect_terms = {a.term for a in aspects}
        anchor_issues: list[str] = []
        mapped_sentiments: list[AspectSentimentItem] = []
        for s in sentiments:
            mapped = self._map_aspect_ref_to_terms(s.aspect_ref, aspect_terms)
            if mapped is None:
                anchor_issues.append(f"dropped_unanchored_aspect_ref:{s.aspect_ref}")
                continue
            if mapped != s.aspect_ref:
                anchor_issues.append(f"mapped_aspect_ref:{s.aspect_ref}->{mapped}")
                s.aspect_ref = mapped
            mapped_sentiments.append(s)

        sentiments = [s for s in mapped_sentiments if s.aspect_ref in aspect_terms]

        # If reviews existed but no sentiments remain, create a neutral placeholder on first aspect to keep confidence >0
        if review_present and not sentiments and aspect_terms:
            fallback_ref = next(iter(aspect_terms))
            sentiments.append(
                AspectSentimentItem(
                    aspect_ref=fallback_ref,
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
