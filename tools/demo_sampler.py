from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import List, Set, Sequence, Optional, Dict

from data.datasets.loader import InternalExample


def _compute_text_hash(text: str) -> str:
    """Compute SHA256 hash of normalized text for overlap detection."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass
class DemoSampleResult:
    """Result of demo sampling with integrity tracking."""
    demos: List[InternalExample]
    removed_by_uid: int
    removed_by_hash: int
    total_excluded: int


class DemoSampler:
    """
    Centralized sampler to avoid demo leakage.
    - Samples only from the provided pool (demo_pool)
    - Enforces forbid_uids exclusion (UID-based)
    - Enforces forbid_hashes exclusion (text hash-based, for near-duplicate detection)
    - Deterministic given seed
    """

    def __init__(self, pool: Sequence[InternalExample]):
        self.pool = [ex for ex in pool]
        # Pre-compute text hashes for the pool
        self._pool_hashes: Dict[str, str] = {}
        for ex in self.pool:
            self._pool_hashes[ex.uid] = _compute_text_hash(ex.text)

    def get_pool_hashes(self) -> Dict[str, str]:
        """Return mapping of uid -> text_hash for the demo pool."""
        return dict(self._pool_hashes)

    def sample(
        self,
        k: int,
        seed: int,
        forbid_uids: Set[str] | None = None,
        forbid_hashes: Set[str] | None = None,
    ) -> List[InternalExample]:
        """
        Sample k demos from pool, excluding forbidden UIDs and text hashes.

        Args:
            k: Number of demos to sample
            seed: Random seed for deterministic sampling
            forbid_uids: Set of UIDs to exclude (eval set UIDs)
            forbid_hashes: Set of text hashes to exclude (for hash-based overlap detection)

        Returns:
            List of InternalExample demos
        """
        result = self.sample_with_stats(k, seed, forbid_uids, forbid_hashes)
        return result.demos

    def sample_with_stats(
        self,
        k: int,
        seed: int,
        forbid_uids: Set[str] | None = None,
        forbid_hashes: Set[str] | None = None,
    ) -> DemoSampleResult:
        """
        Sample k demos with detailed statistics about exclusions.

        Returns:
            DemoSampleResult with demos and exclusion counts
        """
        forbid_uid_set = forbid_uids or set()
        forbid_hash_set = forbid_hashes or set()

        removed_by_uid = 0
        removed_by_hash = 0
        candidates = []

        for ex in self.pool:
            if ex.uid in forbid_uid_set:
                removed_by_uid += 1
                continue
            ex_hash = self._pool_hashes.get(ex.uid, _compute_text_hash(ex.text))
            if ex_hash in forbid_hash_set:
                removed_by_hash += 1
                continue
            candidates.append(ex)

        if k <= 0 or not candidates:
            return DemoSampleResult(
                demos=[],
                removed_by_uid=removed_by_uid,
                removed_by_hash=removed_by_hash,
                total_excluded=removed_by_uid + removed_by_hash,
            )

        rng = random.Random(seed)
        # deterministic shuffle then pick first k
        rng.shuffle(candidates)
        chosen = candidates[: min(k, len(candidates))]

        # Gate: ensure no overlap (double-check)
        overlap = set(ex.uid for ex in chosen) & forbid_uid_set
        if overlap:
            raise RuntimeError(f"demo/eval overlap detected: {overlap}")

        return DemoSampleResult(
            demos=chosen,
            removed_by_uid=removed_by_uid,
            removed_by_hash=removed_by_hash,
            total_excluded=removed_by_uid + removed_by_hash,
        )


def compute_eval_hashes(examples: Sequence[InternalExample], splits: Set[str]) -> Set[str]:
    """
    Compute text hashes for examples in the specified splits.
    Use this to build forbid_hashes for demo sampling.
    """
    hashes = set()
    for ex in examples:
        if ex.split in splits:
            hashes.add(_compute_text_hash(ex.text))
    return hashes


__all__ = ["DemoSampler", "DemoSampleResult", "compute_eval_hashes", "_compute_text_hash"]
