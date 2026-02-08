"""
InjectionController — DEBATE_CONTEXT__MEMORY 슬롯 생성(항상).
조건별: C1(OFF) / C2(ON) / C2_silent(retrieval 실행·주입 마스킹).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from schemas.memory_v1_1 import (
    AdvisoryBundleV1_1,
    AdvisoryBundleMetaV1_1,
    AdvisoryV1_1,
)


def build_slot(
    slot_name: str,
    *,
    memory_mode: str,
    retrieval_executed: bool,
    injection_mask: bool,
    retrieved: Optional[List[AdvisoryV1_1]] = None,
    topk: int = 3,
) -> Dict[str, Any]:
    """
    DEBATE_CONTEXT__MEMORY 슬롯 생성. 3조건 모두 동일 슬롯 구조.
    C1: retrieval_executed=False, injection_mask=True → retrieved=[] 강제
    C2: retrieval_executed=True, injection_mask=False → retrieved 그대로
    C2_silent: retrieval_executed=True, injection_mask=True → retrieved=[] 마스킹
    """
    if retrieved is None:
        retrieved = []
    if injection_mask:
        retrieved = []
    memory_on = memory_mode == "on" and not injection_mask
    meta = AdvisoryBundleMetaV1_1(
        memory_mode=memory_mode,
        topk=topk,
        masked_injection=injection_mask,
        retrieval_executed=retrieval_executed,
    )
    bundle = AdvisoryBundleV1_1(
        schema_version="1.1",
        memory_on=memory_on,
        retrieved=retrieved[:topk],
        warnings=[],
        meta=meta,
    )
    return {slot_name: bundle.model_dump()}


def get_slot_payload_for_debate(
    condition: str,
    *,
    slot_memory_name: str = "DEBATE_CONTEXT__MEMORY",
    retrieved_advisories: Optional[List[AdvisoryV1_1]] = None,
    topk: int = 3,
) -> str:
    """
    조건(C1/C2/C2_silent)에 따라 슬롯 페이로드 생성 후 JSON 문자열 반환.
    debate prompt에 넣을 슬롯: 항상 존재, 내용만 조건별로 다름.
    """
    if condition == "C1":
        memory_mode = "off"
        retrieval_executed = False
        injection_mask = True
    elif condition == "C2":
        memory_mode = "on"
        retrieval_executed = True
        injection_mask = False
    elif condition == "C2_silent":
        memory_mode = "silent"
        retrieval_executed = True
        injection_mask = True
    else:
        memory_mode = "off"
        retrieval_executed = False
        injection_mask = True
    slot = build_slot(
        slot_memory_name,
        memory_mode=memory_mode,
        retrieval_executed=retrieval_executed,
        injection_mask=injection_mask,
        retrieved=retrieved_advisories or [],
        topk=topk,
    )
    return json.dumps(slot, ensure_ascii=False)


class InjectionController:
    """DEBATE_CONTEXT__MEMORY 슬롯 생성. 조건별 OFF/ON/SILENT 마스킹."""

    def __init__(
        self,
        *,
        slot_memory_name: str = "DEBATE_CONTEXT__MEMORY",
        topk: int = 3,
    ):
        self.slot_memory_name = slot_memory_name
        self.topk = topk

    def build_slot_payload(
        self,
        condition: str,
        retrieved_advisories: Optional[List[AdvisoryV1_1]] = None,
    ) -> str:
        return get_slot_payload_for_debate(
            condition,
            slot_memory_name=self.slot_memory_name,
            retrieved_advisories=retrieved_advisories,
            topk=self.topk,
        )
