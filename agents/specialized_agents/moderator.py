from __future__ import annotations

from typing import Any, Dict, List, Optional

from schemas import ATEOutput, ATSAOutput, ArbiterFlags, ModeratorOutput, ValidatorOutput, AspectSentimentItem, DebateSummary


class Moderator:
    """Rule-based moderator (no LLM). Combines ATE/ATSA/Validator outputs via Rules A-D."""

    @staticmethod
    def _iou(span_a: Optional[dict], span_b: Optional[dict]) -> float:
        if not span_a or not span_b:
            return 0.0
        a_start, a_end = span_a["start"], span_a["end"]
        b_start, b_end = span_b["start"], span_b["end"]
        inter = max(0, min(a_end, b_end) - max(a_start, b_start))
        union = max(a_end, b_end) - min(a_start, b_start)
        return inter / union if union > 0 else 0.0

    def _rule_a_span_alignment(self, candidate_atsa: ATSAOutput, stage1_atsa: ATSAOutput, final_label: str, confidence: float):
        """Rule A: Span alignment boost if IoU>0.8 and labels align."""
        iou = self._iou(
            getattr(candidate_atsa, "span", None) and candidate_atsa.span.model_dump() if getattr(candidate_atsa, "span", None) else None,
            getattr(stage1_atsa, "span", None) and stage1_atsa.span.model_dump() if getattr(stage1_atsa, "span", None) else None,
        )
        rationale = None
        if iou >= 0.8 and candidate_atsa.label == final_label:
            confidence = (confidence + candidate_atsa.confidence) / 2
            rationale = f"RuleA: IoU {iou:.2f}>=0.8 span aligned."
        return confidence, rationale

    def _rule_b_stage2_preference(self, stage1_ate: ATEOutput, stage2_ate: Optional[ATEOutput]):
        """Rule B: Stage2 preferred unless confidence drop>=0.2."""
        if not stage2_ate:
            return stage1_ate, False, 0.0, "RuleB: Stage2 missing; keep Stage1."
        drop = stage1_ate.confidence - stage2_ate.confidence
        if drop >= 0.2:
            return stage1_ate, True, float(drop), "RuleB: Stage2 drop>=0.2; keep Stage1."
        return stage2_ate, False, 0.0, "RuleB: Stage2 preferred."

    def _rule_c_validator_veto(self, validator: ValidatorOutput, current_label: str, current_conf: float):
        """Rule C: Critical risk/proposal -> validator suggestion if higher/critical."""
        rationale = None
        if validator.suggested_label:
            critical = any(
                risk.lower().startswith(("negation", "irony", "contrast")) or "severity:high" in risk.lower()
                for risk in validator.issues
            )
            if critical or validator.confidence >= current_conf:
                return validator.suggested_label, max(current_conf, validator.confidence), "RuleC: Validator critical veto."
        return current_label, current_conf, rationale

    def _rule_d_confidence_resolution(self, ate_label: str, ate_conf: float, atsa_label: str, atsa_conf: float):
        """Rule D: Confidence tie-break."""
        diff = abs(ate_conf - atsa_conf)
        rationale = None
        final_label = ate_label
        final_conf = ate_conf
        if atsa_label != ate_label:
            if diff < 0.1 - 1e-6:
                rationale = "RuleD: diff<0.1 conflict -> sentence ATE."
                final_label, final_conf = ate_label, ate_conf
            else:
                if atsa_conf > ate_conf:
                    final_label, final_conf = atsa_label, atsa_conf
                    rationale = "RuleD: diff>=0.1 ATSA wins."
                else:
                    rationale = "RuleD: diff>=0.1 ATE wins."
        return final_label, final_conf, rationale

    def _infer_label_from_debate(self, summary: Optional[DebateSummary]) -> Optional[str]:
        if summary is None:
            return None
        parts = [
            summary.consensus or "",
            summary.rationale or "",
            " ".join(summary.key_agreements or []),
            " ".join(summary.key_disagreements or []),
        ]
        text = " ".join(p for p in parts if p).lower()
        if any(tok in text for tok in ["혼합", "mixed", "엇갈", "양면"]):
            return "mixed"
        if any(tok in text for tok in ["긍정", "호의", "좋다", "positive"]):
            return "positive"
        if any(tok in text for tok in ["부정", "비판", "나쁘", "negative"]):
            return "negative"
        if any(tok in text for tok in ["중립", "neutral", "모호"]):
            return "neutral"
        return None

    def decide(
        self,
        stage1_ate: ATEOutput,
        stage1_atsa: ATSAOutput,
        validator: ValidatorOutput,
        stage2_ate: ATEOutput | None = None,
        stage2_atsa: ATSAOutput | None = None,
        final_aspect_sentiments: List[AspectSentimentItem] | None = None,
        debate_summary: Optional[DebateSummary] = None,
    ) -> ModeratorOutput:
        rationale_parts: List[str] = []
        applied_rules: List[str] = []

        if stage1_ate.confidence == 0.0 and (stage2_ate.confidence if stage2_ate else 0.0) == 0.0:
            return ModeratorOutput(
                final_label="neutral",
                confidence=0.0,
                rationale="RuleZ: insufficient signal (both confidences 0).",
                selected_stage="stage1",
                applied_rules=["RuleZ"],
                decision_reason="RuleZ: insufficient signal (both confidences 0).",
                arbiter_flags=ArbiterFlags(stage2_rejected_due_to_confidence=False, validator_override_applied=False, confidence_margin_used=0.0),
            )

        # Rule B
        candidate_ate, drop_guard, confidence_margin, rationale_b = self._rule_b_stage2_preference(stage1_ate, stage2_ate)
        rationale_parts.append(rationale_b)
        applied_rules.append("RuleB")

        candidate_atsa = stage2_atsa or stage1_atsa
        final_label = candidate_ate.label
        confidence = candidate_ate.confidence
        selected_stage: str = "stage2" if (stage2_ate is not None and candidate_ate is stage2_ate and not drop_guard) else "stage1"

        # Rule M: explicit conflict between stage1 and stage2 ATE -> mixed
        if stage2_ate and stage1_ate.label != stage2_ate.label:
            final_label = "mixed"
            confidence = max(stage1_ate.confidence, stage2_ate.confidence)
            rationale_parts.append("RuleM: conflicting stage1/stage2 labels -> mixed.")
            applied_rules.append("RuleM")

        # Rule C
        validator_override = False
        final_label, confidence, rationale_c = self._rule_c_validator_veto(validator, final_label, confidence)
        if rationale_c:
            rationale_parts.append(rationale_c)
            applied_rules.append("RuleC")
            validator_override = True

        # Rule A (skip if drop_guard from B)
        if not drop_guard:
            conf_after_span, rationale_a = self._rule_a_span_alignment(candidate_atsa, stage1_atsa, final_label, confidence)
            if rationale_a:
                confidence = conf_after_span
                rationale_parts.append(rationale_a)
                applied_rules.append("RuleA")

        # Rule D
        final_label, confidence, rationale_d = self._rule_d_confidence_resolution(final_label, confidence, candidate_atsa.label, candidate_atsa.confidence)
        if rationale_d:
            rationale_parts.append(rationale_d)
            applied_rules.append("RuleD")

        # Rule E: Debate consensus hint (low-confidence override)
        inferred = self._infer_label_from_debate(debate_summary)
        if inferred and inferred != final_label and (confidence < 0.55 or final_label == "mixed"):
            rationale_parts.append(f"RuleE: debate consensus -> {inferred}.")
            applied_rules.append("RuleE")
            final_label = inferred

        if not rationale_parts:
            rationale_parts.append("Rule default: no change.")

        decision_reason = " ".join(rationale_parts)
        arbiter_flags = ArbiterFlags(
            stage2_rejected_due_to_confidence=drop_guard,
            validator_override_applied=validator_override,
            confidence_margin_used=confidence_margin,
        )
        return ModeratorOutput(
            final_label=final_label,
            confidence=confidence,
            rationale=decision_reason,
            selected_stage=selected_stage,
            applied_rules=applied_rules,
            decision_reason=decision_reason,
            arbiter_flags=arbiter_flags,
        )
    
    def build_final_aspects(
        self,
        final_aspect_sentiments: List[AspectSentimentItem] | None,
    ) -> List[Dict[str, Any]]:
        """Convert final aspect_sentiments to final_aspects list for FinalResult. 암시적(is_implicit)이면 aspect_term을 \"\"로 통일."""
        if not final_aspect_sentiments:
            return []
        out: List[Dict[str, Any]] = []
        for s in final_aspect_sentiments:
            d = s.model_dump()
            if d.get("is_implicit") is True:
                d["aspect_term"] = {"term": "", "span": {"start": 0, "end": 0}}
            out.append(d)
        return out