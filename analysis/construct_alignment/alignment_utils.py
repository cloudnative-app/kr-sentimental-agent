"""
Taxonomy-aware construct alignment utilities.

- build_taxonomy_tree(): ALLOWED_REFS → tree (ROOT → entity → entity#attribute)
- compute_lca(ref1, ref2): Lowest Common Ancestor
- wu_palmer_similarity(ref1, ref2): Wu-Palmer similarity [0,1]
- is_near_miss(ref1, ref2, confusion_groups): True if pair in confusion config

Deterministic only. No embeddings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.taxonomy import ALLOWED_REFS, parse_ref

# Level 0: ROOT, Level 1: entity, Level 2: entity#attribute
ROOT = "ROOT"


def build_taxonomy_tree() -> dict[str, Any]:
    """
    Build taxonomy tree from ALLOWED_REFS.
    Structure: { "id": "ROOT", "level": 0, "children": [ { "id": entity, "level": 1, "children": [ { "id": ref, "level": 2 } ] } ] }
    """
    entities: dict[str, list[str]] = {}
    for ref in sorted(ALLOWED_REFS):
        parsed = parse_ref(ref)
        if not parsed:
            continue
        entity, attr = parsed
        entities.setdefault(entity, []).append(ref)

    children: list[dict[str, Any]] = []
    for entity in sorted(entities.keys()):
        refs = sorted(entities[entity])
        entity_children = [
            {"id": r, "level": 2, "children": []}
            for r in refs
        ]
        children.append({
            "id": entity,
            "level": 1,
            "children": entity_children,
        })

    return {
        "id": ROOT,
        "level": 0,
        "children": children,
    }


def _ref_to_path(ref: str) -> list[str]:
    """Get path from ROOT to ref. e.g. '제품 전체#일반' -> ['ROOT', '제품 전체', '제품 전체#일반']."""
    if not ref or not isinstance(ref, str):
        return [ROOT]
    r = ref.strip()
    if r == ROOT:
        return [ROOT]
    parsed = parse_ref(r)
    if not parsed:
        return [ROOT]
    entity, _ = parsed
    return [ROOT, entity, r]


def _depth_of_node(node_id: str) -> int:
    """Depth: ROOT=0, entity=1, entity#attr=2."""
    if not node_id or node_id == ROOT:
        return 0
    if "#" in node_id:
        return 2
    return 1


def compute_lca(ref1: str, ref2: str) -> str:
    """
    Lowest Common Ancestor of two refs in taxonomy tree.
    Returns ROOT, entity, or ref (when ref1==ref2).
    """
    p1 = _ref_to_path(ref1)
    p2 = _ref_to_path(ref2)
    for i, (a, b) in enumerate(zip(p1, p2)):
        if a != b:
            return p1[i - 1] if i > 0 else ROOT
    return p1[min(len(p1), len(p2)) - 1]


def wu_palmer_similarity(ref1: str, ref2: str) -> float:
    """
    Wu-Palmer similarity: 2 * depth(LCA) / (depth(ref1) + depth(ref2)).
    Returns value in [0, 1]. 1.0 when ref1==ref2.
    """
    if not ref1 or not ref2:
        return 0.0
    r1 = (ref1 or "").strip()
    r2 = (ref2 or "").strip()
    if r1 == r2:
        return 1.0
    lca = compute_lca(r1, r2)
    d1 = _depth_of_node(r1)
    d2 = _depth_of_node(r2)
    d_lca = _depth_of_node(lca)
    denom = d1 + d2
    if denom == 0:
        return 1.0
    return 2.0 * d_lca / denom


def taxonomy_distance(ref1: str, ref2: str) -> float:
    """Distance = 1 - Wu-Palmer similarity. [0, 1]."""
    return 1.0 - wu_palmer_similarity(ref1, ref2)


def is_near_miss(
    ref1: str,
    ref2: str,
    confusion_groups: dict[str, Any] | None = None,
) -> bool:
    """
    True if (ref1, ref2) is a near-miss pair per confusion config.
    Supports:
    - near_miss_pairs: [[a,b], ...] exact pair match
    - confusion_groups (list of lists): [[a,b,c,...]] any two in same group
    - confusion_groups (list of dicts): [{group_id, members, status}]
      when status=accepted, any two refs in members are near-miss
    """
    if not ref1 or not ref2:
        return False
    r1 = (ref1 or "").strip()
    r2 = (ref2 or "").strip()
    if r1 == r2:
        return False  # exact match, not near-miss
    cfg = confusion_groups or {}
    pairs = cfg.get("near_miss_pairs") or []
    for p in pairs:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            a, b = (str(p[0]).strip(), str(p[1]).strip())
            if (a == r1 and b == r2) or (a == r2 and b == r1):
                return True
    groups = cfg.get("confusion_groups") or []
    for g in groups:
        if isinstance(g, dict):
            if str(g.get("status", "")).lower() != "accepted":
                continue
            members = g.get("members") or []
            refs_in_group = {str(x).strip() for x in members}
            if r1 in refs_in_group and r2 in refs_in_group:
                return True
        elif isinstance(g, (list, tuple)):
            refs_in_group = {str(x).strip() for x in g}
            if r1 in refs_in_group and r2 in refs_in_group:
                return True
    return False


def load_confusion_groups(path: Path | None = None) -> dict[str, Any]:
    """Load confusion_groups.json. Returns empty structure if missing."""
    if path is None:
        path = Path(__file__).parent / "confusion_groups.json"
    if not path.exists():
        return {"confusion_groups": [], "near_miss_pairs": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "confusion_groups": data.get("confusion_groups", []),
            "near_miss_pairs": data.get("near_miss_pairs", []),
        }
    except (json.JSONDecodeError, OSError):
        return {"confusion_groups": [], "near_miss_pairs": []}
