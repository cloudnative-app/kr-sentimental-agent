"""
MemoryStore — JSONL append/load, prune(fifo), forbid_raw_text 검사.
raw_text 필드가 들어가면 즉시 fail-fast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from schemas.memory_v1_1 import EpisodicMemoryEntryV1_1

# 금지 필드: 원문·골드·CoT 저장 금지
FORBIDDEN_KEYS = {"raw_text", "raw_text_hash", "gold", "gold_label", "gold_polarity", "cot", "chain_of_thought"}


def _fail_if_raw_text(entry: Dict[str, Any], forbid_raw_text: bool = True) -> None:
    """entry에 raw_text 등 금지 필드가 있으면 즉시 예외."""
    if not forbid_raw_text:
        return
    for key in FORBIDDEN_KEYS:
        if key in entry and entry.get(key) not in (None, ""):
            raise ValueError(
                f"MemoryStore: raw text / gold / CoT 저장 금지. 금지 필드 발견: '{key}'"
            )
    # nested
    for v in entry.values():
        if isinstance(v, dict):
            _fail_if_raw_text(v, forbid_raw_text=True)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _fail_if_raw_text(item, forbid_raw_text=True)


class MemoryStore:
    """JSONL append/load, prune(fifo). forbid_raw_text 검사."""

    def __init__(
        self,
        path: str | Path,
        *,
        forbid_raw_text: bool = True,
        max_items_total: int = 5000,
        prune_enabled: bool = True,
        prune_strategy: str = "fifo",
        keep_last_n: int = 5000,
    ):
        self.path = Path(path)
        self.forbid_raw_text = forbid_raw_text
        self.max_items_total = max_items_total
        self.prune_enabled = prune_enabled
        self.prune_strategy = prune_strategy
        self.keep_last_n = keep_last_n

    def load(self) -> List[Dict[str, Any]]:
        """JSONL에서 항목 목록 로드."""
        if not self.path.exists():
            return []
        items: List[Dict[str, Any]] = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                _fail_if_raw_text(entry, self.forbid_raw_text)
                items.append(entry)
        return items

    def append(self, entry: Dict[str, Any] | EpisodicMemoryEntryV1_1) -> None:
        """항목 1건 추가. raw_text 등 금지 필드 있으면 fail-fast."""
        if isinstance(entry, EpisodicMemoryEntryV1_1):
            entry = entry.model_dump()
        _fail_if_raw_text(entry, self.forbid_raw_text)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if self.prune_enabled and self.prune_strategy == "fifo":
            self._prune_fifo()

    def _prune_fifo(self) -> None:
        """FIFO로 keep_last_n 초과분 제거."""
        items = self.load()
        if len(items) <= self.keep_last_n:
            return
        to_keep = items[-self.keep_last_n :]
        with open(self.path, "w", encoding="utf-8") as f:
            for entry in to_keep:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
