"""
AdvisoryBuilder — retrieved episode → AdvisoryV1_1 생성.
no_label_hint / no_forcing / no_confidence_boost 강제.

동일 aspect_term_norm에 대해 "(현재 변경하려는 polarity)로 갔다가 실패/리스크 악화" 기록이
retrieved episode에 있으면, 그 polarity로 바꾸는 조언을 금지하거나 evidence 필수로 강등한다.
(메모리가 결정을 내리는 것이 아니라, 위험한 조언을 올리지 않거나 금지/경고 태그를 붙이는 수준.)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from schemas.memory_v1_1 import (
    AdvisoryV1_1,
    AdvisoryConstraintsV1_1,
    EvidenceV1_1,
    EpisodicMemoryEntryV1_1,
)


def _norm_aspect(s: str) -> str:
    return (s or "").strip()


def _norm_polarity(p: str) -> str:
    raw = (p or "").strip().lower()
    if raw in ("positive", "negative", "neutral"):
        return raw
    if raw in ("pos", "neg", "neu"):
        return {"pos": "positive", "neg": "negative", "neu": "neutral"}[raw]
    return raw


def _is_failure_or_risk_worsened(episode: Dict) -> bool:
    """True if this episode records failure or risk worsened (override failed/harm, or risk_after > risk_before)."""
    ep_type = (episode.get("episode_type") or "").strip().lower()
    if ep_type == "harm":
        return True
    eval_block = episode.get("evaluation") or {}
    override_applied = bool(eval_block.get("override_applied", False))
    override_success = bool(eval_block.get("override_success", True))
    override_harm = bool(eval_block.get("override_harm", False))
    if override_applied and (not override_success or override_harm):
        return True
    risk_before = (eval_block.get("risk_before") or {}).get("severity_sum", 0.0) or 0.0
    risk_after = (eval_block.get("risk_after") or {}).get("severity_sum", 0.0) or 0.0
    if risk_after > risk_before:
        return True
    return False


def _final_aspect_polarity_pairs(episode: Dict) -> Set[Tuple[str, str]]:
    """(aspect_term_norm, polarity_norm) from episode's stage_snapshot.final."""
    out: Set[Tuple[str, str]] = set()
    snap = episode.get("stage_snapshot") or {}
    final = snap.get("final") or {}
    polarities = final.get("polarities") or {}
    for aspect, pol in polarities.items():
        a = _norm_aspect(aspect)
        p = _norm_polarity(str(pol))
        if a:
            out.add((a, p))
    return out


def _dangerous_polarity_pairs(episodes: List[Dict]) -> Set[Tuple[str, str]]:
    """
    (aspect_term_norm, polarity) set from retrieved episodes that had failure/risk worsened.
    Advising a change to that polarity for that aspect can be prohibited or downgraded.
    """
    dangerous: Set[Tuple[str, str]] = set()
    for ep in episodes:
        if not _is_failure_or_risk_worsened(ep):
            continue
        for pair in _final_aspect_polarity_pairs(ep):
            dangerous.add(pair)
    return dangerous


def failed_polarities_by_aspect(episodes: List[Dict]) -> Dict[str, Set[str]]:
    """
    aspect_term_norm -> set of polarities that led to failure/risk worsened in retrieved episodes.
    OPFB: advisory 생성 시 해당 aspect에서 이 polarities 조언은 생성하지 않거나 BLOCKED.
    """
    out: Dict[str, Set[str]] = {}
    for ep in episodes:
        if not _is_failure_or_risk_worsened(ep):
            continue
        for (aspect, pol) in _final_aspect_polarity_pairs(ep):
            out.setdefault(aspect, set()).add(pol)
    return out


def _next_adv_id(existing_ids: List[str]) -> str:
    n = 1
    while True:
        cand = f"adv_{n:06d}"
        if cand not in existing_ids:
            return cand
        n += 1


# 경고 문구: 해당 aspect·polarity 조합으로 과거 실패/리스크 악화 기록이 있을 때 메시지에 붙임 (강등).
DANGEROUS_POLARITY_WARNING = " [경고: 이 조언과 동일한 aspect·polarity 조합으로 과거 실패/리스크 악화 사례가 있습니다. 증거 확인 권장.]"

# OPFB 블록 사유 (Scorecard/Triptych memory_block_reason)
BLOCK_REASON_OPPOSITE_POLARITY_FAILED = "opposite_polarity_failed"


def episode_to_advisory(
    episode: Dict | EpisodicMemoryEntryV1_1,
    *,
    advisory_type: str = "consistency_anchor",
    strength: str = "moderate",
    relevance_score: float = 0.8,
    existing_ids: Optional[List[str]] = None,
    dangerous_pairs: Optional[Set[Tuple[str, str]]] = None,
) -> AdvisoryV1_1:
    """
    episode 1건 → AdvisoryV1_1.
    polarity/aspect 정답 힌트 직접 노출 금지. constraints 강제.
    dangerous_pairs가 주어지고 이 episode의 final (aspect, polarity)가 그 집합과 겹치면
    메시지에 금지/경고 문구를 붙여 강등(evidence 필수 권장).
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
    # Content strengthening: risk → action mapping (this risk type, this action, outcome)
    risk_type = episode.get("risk_type")
    action_taken = episode.get("action_taken")
    outcome_delta = episode.get("outcome_delta") or {}
    if risk_type or action_taken:
        suffix = " [Risk type: %s. Action: %s." % (risk_type or "—", action_taken or "—")
        cr = outcome_delta.get("conflict_resolved")
        if cr is not None:
            suffix += " Conflict resolved: %s.]" % cr
        else:
            suffix += "]"
        message = (message + suffix)[:800]

    # 강등: 동일 aspect·polarity로 과거 실패/리스크 악화 기록이 있으면 경고 붙임
    if dangerous_pairs:
        ep_pairs = _final_aspect_polarity_pairs(episode)
        if ep_pairs & dangerous_pairs:
            message = (message + DANGEROUS_POLARITY_WARNING)[:800]

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


def _blocked_stats(
    episodes: List[Dict],
    dangerous: Set[Tuple[str, str]],
    blocked_count: int,
    blocked_aspect_terms: List[str],
    blocked_polarities: List[str],
) -> Dict[str, Any]:
    """OPFB 로그: advisory_blocked_n, blocked_aspect_terms, blocked_polarities, memory_blocked_*."""
    n_ep_failed = sum(1 for ep in episodes if _is_failure_or_risk_worsened(ep))
    return {
        "memory_blocked_episode_n": n_ep_failed,
        "memory_blocked_advisory_n": blocked_count,
        "memory_block_reason": BLOCK_REASON_OPPOSITE_POLARITY_FAILED if blocked_count else "",
        "advisory_blocked_n": blocked_count,
        "blocked_aspect_terms": list(dict.fromkeys(blocked_aspect_terms)),
        "blocked_polarities": list(dict.fromkeys(blocked_polarities)),
    }


class AdvisoryBuilder:
    """retrieved episode → AdvisoryV1_1. no_label_hint/no_forcing/no_confidence_boost 강제.
    OPFB: 동일 aspect_term_norm에 대해 해당 polarity로 갔다가 실패/리스크 악화 기록이 있으면
    그 조언을 생성하지 않음(블록)하고 로그(advisory_blocked_n, blocked_aspect_terms, blocked_polarities) 반환.
    """

    def build_from_episodes(
        self,
        episodes: List[Dict],
        *,
        advisory_type: str = "consistency_anchor",
        strength: str = "moderate",
        prohibit_dangerous: bool = True,
    ) -> Tuple[List[AdvisoryV1_1], Dict[str, Any]]:
        """
        Returns (advisories, blocked_stats).
        blocked_stats: memory_blocked_episode_n, memory_blocked_advisory_n, memory_block_reason,
                       advisory_blocked_n, blocked_aspect_terms, blocked_polarities.
        """
        advisories: List[AdvisoryV1_1] = []
        existing_ids: List[str] = []
        dangerous = _dangerous_polarity_pairs(episodes)
        blocked_aspect_terms: List[str] = []
        blocked_polarities: List[str] = []
        blocked_count = 0

        for ep in episodes:
            ep_pairs = _final_aspect_polarity_pairs(ep)
            if prohibit_dangerous and (ep_pairs & dangerous):
                blocked_count += 1
                for (a, p) in (ep_pairs & dangerous):
                    blocked_aspect_terms.append(a)
                    blocked_polarities.append(p)
                continue
            adv = episode_to_advisory(
                ep,
                advisory_type=advisory_type,
                strength=strength,
                existing_ids=existing_ids,
                dangerous_pairs=dangerous if dangerous else None,
            )
            advisories.append(adv)
            existing_ids.append(adv.advisory_id)

        blocked_stats = _blocked_stats(
            episodes, dangerous, blocked_count, blocked_aspect_terms, blocked_polarities
        )
        return (advisories, blocked_stats)
