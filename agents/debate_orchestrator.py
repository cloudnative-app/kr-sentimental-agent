from __future__ import annotations

import json
from typing import Dict, List, Optional

from schemas import DebateOutput, DebatePersona, DebateRound, DebateSummary, DebateTurn, ProcessTrace
from tools.backbone_client import BackboneClient
from tools.llm_runner import run_structured, StructuredResult
from tools.prompt_spec import PromptSpec
from agents.prompts import load_prompt

# Role-based memory access: only CJ sees DEBATE_CONTEXT__MEMORY (noise reduction).
DEFAULT_SLOT_MEMORY_NAME = "DEBATE_CONTEXT__MEMORY"
MEMORY_SLOT_PRESENT_FOR = ["cj"]  # EPM/TAN get context without memory slot.


class DebateOrchestrator:
    """
    EPM → TAN → CJ annotation correctors. Patch-only output; no pro/con battle.
    Goal: tuple set converges to one consistent answer. 1 round (EPM→TAN→CJ) by default.
    Memory: DEBATE_CONTEXT__MEMORY is exposed only to CJ (epm/tan get context without it).
    """

    def __init__(self, backbone: Optional[BackboneClient] = None, config: Optional[Dict] = None):
        self.backbone = backbone or BackboneClient()
        cfg = config or {}
        self.rounds = int(cfg.get("rounds", 1))
        self.order = list(cfg.get("order") or ["epm", "tan", "cj"])
        self.personas = self._build_personas(cfg.get("personas"))
        self._slot_memory_name = str(cfg.get("slot_memory_name") or DEFAULT_SLOT_MEMORY_NAME)

    def _build_personas(self, override: Optional[Dict]) -> Dict[str, DebatePersona]:
        if isinstance(override, dict) and override:
            return {k: DebatePersona(**v) for k, v in override.items()}
        return {
            "epm": DebatePersona(
                name="EPM",
                role="Evidence–Polarity Mapper",
                goal="Determine polarity only when supported by explicit textual evidence",
                stance="",
                style="",
            ),
            "tan": DebatePersona(
                name="TAN",
                role="Target–Aspect Normalizer",
                goal="Resolve null, duplicate, or misaligned aspect targets",
                stance="",
                style="",
            ),
            "cj": DebatePersona(
                name="CJ",
                role="Consistency Judge",
                goal="Produce a single, consistent set of aspect–polarity tuples",
                stance="",
                style="",
            ),
        }

    def _format_history(self, turns: List[DebateTurn]) -> str:
        if not turns:
            return "없음"
        lines = []
        for t in turns:
            agent = t.agent or t.speaker or "?"
            if getattr(t, "proposed_edits", None):
                for e in t.proposed_edits:
                    lines.append(f"- {agent}: {e.op} target={e.target} value={getattr(e, 'value', None)} evidence={getattr(e, 'evidence', None)}")
            else:
                lines.append(f"- {agent}: {t.message or '(no proposed_edits)'}")
        return "\n".join(lines)

    def _normalize_turn(self, turn: DebateTurn, persona: DebatePersona, speaker_key: str) -> DebateTurn:
        if not turn.agent:
            turn.agent = persona.name or speaker_key.upper()
        if not turn.speaker:
            turn.speaker = persona.name or speaker_key.upper()
        return turn

    def _context_json_for_persona(self, context_json: str, speaker_key: str) -> str:
        """CJ-only memory: EPM/TAN get context without DEBATE_CONTEXT__MEMORY; CJ gets full context."""
        if speaker_key in ("epm", "tan"):
            try:
                ctx = json.loads(context_json)
                if isinstance(ctx, dict):
                    ctx = dict(ctx)
                    ctx.pop(self._slot_memory_name, None)
                    return json.dumps(ctx, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return context_json

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
                persona_context = self._context_json_for_persona(context_json, speaker_key)
                system_prompt = (
                    f"{system_base}\n\n"
                    f"[TOPIC]\n{topic}\n\n"
                    f"[PERSONA]\n{persona.model_dump_json()}\n\n"
                    f"[SHARED_CONTEXT_JSON]\n{persona_context}\n\n"
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
                turn = self._normalize_turn(result.model, persona, speaker_key)
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

        # Judge (CJ role) sees full context including DEBATE_CONTEXT__MEMORY
        judge_context = self._context_json_for_persona(context_json, "cj")
        judge_prompt = (
            load_prompt("debate_judge")
            + f"\n\n[TOPIC]\n{topic}\n\n[SHARED_CONTEXT_JSON]\n{judge_context}\n\n[ALL_TURNS]\n"
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

