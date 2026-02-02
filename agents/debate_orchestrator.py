from __future__ import annotations

from typing import Dict, List, Optional

from schemas import DebateOutput, DebatePersona, DebateRound, DebateSummary, DebateTurn, ProcessTrace
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec
from agents.prompts import load_prompt


class DebateOrchestrator:
    """
    Orchestrates a pro/con debate with planning + reflection steps and a judge summary.
    """

    def __init__(self, backbone: Optional[BackboneClient] = None, config: Optional[Dict] = None):
        self.backbone = backbone or BackboneClient()
        cfg = config or {}
        self.rounds = int(cfg.get("rounds", 2))
        self.order = list(cfg.get("order") or ["analyst", "critic", "empath"])
        self.personas = self._build_personas(cfg.get("personas"))

    def _build_personas(self, override: Optional[Dict]) -> Dict[str, DebatePersona]:
        if isinstance(override, dict) and override:
            return {k: DebatePersona(**v) for k, v in override.items()}
        return {
            "analyst": DebatePersona(
                name="분석가 패널",
                stance="neutral",
                role="분석가",
                style="건조하고 근거 중심",
                goal="증거 기반으로 중립적 판단 제시",
            ),
            "empath": DebatePersona(
                name="공감가 패널",
                stance="pro",
                role="공감가",
                style="따뜻하고 감성적",
                goal="긍정/지지적 맥락을 강화",
            ),
            "critic": DebatePersona(
                name="비평가 패널",
                stance="con",
                role="비평가",
                style="날카롭고 논리적",
                goal="부정/비판적 맥락을 강화",
            ),
        }

    def _format_history(self, turns: List[DebateTurn]) -> str:
        if not turns:
            return "없음"
        lines = []
        for t in turns:
            lines.append(f"- {t.speaker}({t.stance}): {t.message}")
        return "\n".join(lines)

    def _normalize_turn(self, turn: DebateTurn, persona: DebatePersona) -> DebateTurn:
        if not turn.speaker:
            turn.speaker = persona.name
        if not turn.stance:
            turn.stance = persona.stance
        return turn

    def run(
        self,
        *,
        topic: str,
        context_json: str,
        run_id: str,
        text_id: str,
        language_code: str = "unknown",
        domain_id: str = "unknown",
        trace: Optional[List[ProcessTrace]] = None,
    ) -> DebateOutput:
        trace = trace if trace is not None else []
        turns: List[DebateTurn] = []
        rounds: List[DebateRound] = []

        system_base = load_prompt("debate_speaker")
        for round_idx in range(1, self.rounds + 1):
            round_turns: List[DebateTurn] = []
            for speaker_key in self.order:
                persona = self.personas.get(speaker_key)
                if not persona:
                    continue
                history = self._format_history(turns)
                system_prompt = (
                    f"{system_base}\n\n"
                    f"[TOPIC]\n{topic}\n\n"
                    f"[PERSONA]\n{persona.model_dump_json()}\n\n"
                    f"[SHARED_CONTEXT_JSON]\n{context_json}\n\n"
                    f"[HISTORY]\n{history}\n"
                )
                spec = PromptSpec(
                    system=[system_prompt],
                    user=topic,
                    language_code=language_code,
                    domain_id=domain_id,
                )
                result: StructuredResult[DebateTurn] = run_structured(
                    backbone=self.backbone,
                    system_prompt=system_prompt,
                    user_text=topic,
                    schema=DebateTurn,
                    max_retries=2,
                    run_id=run_id,
                    text_id=text_id,
                    stage=f"debate_round{round_idx}_{speaker_key}",
                    mode="debate",
                    use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
                    prompt_spec=spec,
                )
                turn = self._normalize_turn(result.model, persona)
                turns.append(turn)
                round_turns.append(turn)
                trace.append(
                    ProcessTrace(
                        stage="debate",
                        agent=turn.speaker,
                        input_text=topic,
                        output=turn.model_dump(),
                        notes=result.meta.to_notes_str(),
                    )
                )
            rounds.append(DebateRound(round_index=round_idx, turns=round_turns))

        judge_prompt = (
            load_prompt("debate_judge")
            + f"\n\n[TOPIC]\n{topic}\n\n[SHARED_CONTEXT_JSON]\n{context_json}\n\n[ALL_TURNS]\n"
            + self._format_history(turns)
        )
        judge_spec = PromptSpec(
            system=[judge_prompt],
            user=topic,
            language_code=language_code,
            domain_id=domain_id,
        )
        judge_result: StructuredResult[DebateSummary] = run_structured(
            backbone=self.backbone,
            system_prompt=judge_prompt,
            user_text=topic,
            schema=DebateSummary,
            max_retries=2,
            run_id=run_id,
            text_id=text_id,
            stage="debate_judge",
            mode="debate",
            use_mock=(getattr(self.backbone, "provider", "mock") == "mock"),
            prompt_spec=judge_spec,
        )
        summary = judge_result.model
        trace.append(
            ProcessTrace(
                stage="debate_judge",
                agent="DebateJudge",
                input_text=topic,
                output=summary.model_dump(),
                notes=judge_result.meta.to_notes_str(),
            )
        )

        return DebateOutput(
            topic=topic,
            personas={k: v for k, v in self.personas.items()},
            rounds=rounds,
            summary=summary,
        )

