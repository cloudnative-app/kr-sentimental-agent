"""
CaseTraceLogger — CaseTraceV1_1 기록.
RQ1~RQ3 메트릭 계산용 필드 누락 없게 고정. 원문/CoT/골드 직접 저장 금지.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from schemas.memory_v1_1 import (
    AdvisoryBundleV1_1,
    CaseTraceV1_1,
    CoverageV1_1,
    DebateLogEntryV1_1,
    InputSignatureV1_1,
    OverrideV1_1,
    RetrievalV1_1,
    RiskV1_1,
    RiskTagMappingV1_1,
    RunMetaV1_1,
    StageSnapshotV1_1,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaseTraceLogger:
    """CaseTraceV1_1 기록. RQ1/RQ2/RQ3 계산용 필드 고정."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def log(
        self,
        *,
        run_id: str,
        condition: str,
        seed: int,
        case_id: str,
        sample_index: int | None = None,
        input_signature: InputSignatureV1_1 | Dict[str, Any],
        stage1_output: StageSnapshotV1_1 | Dict[str, Any],
        debate_log: List[DebateLogEntryV1_1] | List[Dict[str, Any]],
        memory_bundle: AdvisoryBundleV1_1 | Dict[str, Any],
        final_output: StageSnapshotV1_1 | Dict[str, Any],
        risk: RiskV1_1 | Dict[str, Any],
        override: OverrideV1_1 | Dict[str, Any],
        coverage: CoverageV1_1 | Dict[str, Any],
        timestamp: Optional[str] = None,
    ) -> CaseTraceV1_1:
        """CaseTraceV1_1 1건 생성 후 JSONL append."""
        timestamp = timestamp or _now_iso()
        run_meta = RunMetaV1_1(run_id=run_id, condition=condition, seed=seed, timestamp=timestamp)
        if isinstance(input_signature, dict):
            input_signature = InputSignatureV1_1(**input_signature)
        if isinstance(stage1_output, dict):
            stage1_output = StageSnapshotV1_1(**stage1_output)
        debate_entries = [
            DebateLogEntryV1_1(**e) if isinstance(e, dict) else e for e in debate_log
        ]
        if isinstance(memory_bundle, dict):
            memory_bundle = AdvisoryBundleV1_1(**memory_bundle)
        if isinstance(final_output, dict):
            final_output = StageSnapshotV1_1(**final_output)
        if isinstance(risk, dict):
            risk = RiskV1_1(**risk)
        if isinstance(override, dict):
            override = OverrideV1_1(**override)
        if isinstance(coverage, dict):
            coverage = CoverageV1_1(**coverage)
        retrieval_obj = None
        if retrieval is not None:
            retrieval_obj = RetrievalV1_1(**retrieval) if isinstance(retrieval, dict) else retrieval
        trace = CaseTraceV1_1(
            schema_version="1.1",
            run_meta=run_meta,
            case_id=case_id,
            sample_index=sample_index,
            input_signature=input_signature,
            stage1_output=stage1_output,
            debate_log=debate_entries,
            memory_bundle=memory_bundle,
            retrieval=retrieval_obj,
            final_output=final_output,
            risk=risk,
            override=override,
            coverage=coverage,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace.model_dump(), ensure_ascii=False) + "\n")
        return trace
