"""
AdvisoryBuilder — retrieved episode → AdvisoryV1_1 생성.
no_label_hint / no_forcing / no_confidence_boost 강제.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from schemas.memory_v1_1 import (
    AdvisoryV1_1,
    AdvisoryConstraintsV1_1,
    EvidenceV1_1,
    EpisodicMemoryEntryV1_1,
)


def _next_adv_id(existing_ids: List[str]) -> str:
    n = 1
    while True:
        cand = f"adv_{n:06d}"
        if cand not in existing_ids:
            return cand
        n += 1


def episode_to_advisory(
    episode: Dict | EpisodicMemoryEntryV1_1,
    *,
    advisory_type: str = "consistency_anchor",
    strength: str = "moderate",
    relevance_score: float = 0.8,
    existing_ids: Optional[List[str]] = None,
) -> AdvisoryV1_1:
    """
    episode 1건 → AdvisoryV1_1.
    polarity/aspect 정답 힌트 직접 노출 금지. constraints 강제.
    """
    if isinstance(episode, EpisodicMemoryEntryV1_1):
        episode = episode.model_dump()
    existing_ids = existing_ids or []
    adv_id = _next_adv_id(existing_ids)

    correction = episode.get("correction") or {}
    principle_id = correction.get("principle_id") or ""
    applicable = correction.get("applicable_conditions") or []
    corrective_principle = correction.get("corrective_principle") or ""
    message = corrective_principle[:800] if corrective_principle else "No principle text."

    eval_block = episode.get("evaluation") or {}
    risk_after = eval_block.get("risk_after") or {}
    risk_tags = list(risk_after.get("tags") or [])

    evidence = EvidenceV1_1(
        source_episode_ids=[episode.get("episode_id") or ""],
        risk_tags=risk_tags,
        principle_id=principle_id,
        stats=None,
    )
    constraints = AdvisoryConstraintsV1_1(
        no_label_hint=True,
        no_forcing=True,
        no_confidence_boost=True,
    )
    return AdvisoryV1_1(
        schema_version="1.1",
        advisory_id=adv_id,
        advisory_type=advisory_type,
        message=message,
        strength=strength,
        relevance_score=min(1.0, max(0.0, relevance_score)),
        evidence=evidence,
        constraints=constraints,
    )


class AdvisoryBuilder:
    """retrieved episode → AdvisoryV1_1. no_label_hint/no_forcing/no_confidence_boost 강제."""

    def build_from_episodes(
        self,
        episodes: List[Dict],
        *,
        advisory_type: str = "consistency_anchor",
        strength: str = "moderate",
    ) -> List[AdvisoryV1_1]:
        advisories: List[AdvisoryV1_1] = []
        existing_ids: List[str] = []
        for ep in episodes:
            adv = episode_to_advisory(
                ep,
                advisory_type=advisory_type,
                strength=strength,
                existing_ids=existing_ids,
            )
            advisories.append(adv)
            existing_ids.append(adv.advisory_id)
        return advisories
