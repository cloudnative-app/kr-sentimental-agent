from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple, Optional

PATTERN_DIR = Path("resources") / "patterns"


def _sha256_file(path: Path) -> Optional[str]:
    if not path or not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=None)
def load_patterns(language_code: str | None) -> Tuple[Dict, Path, Optional[str]]:
    """
    Load language-specific pattern config.
    Returns (patterns_dict, path_used, sha256).
    Falls back to 'en' when language file missing.
    """
    lang = (language_code or "unknown").lower()
    lang = lang.split("-")[0] if "-" in lang else lang
    candidates = [PATTERN_DIR / f"{lang}.json"]
    if lang != "en":
        candidates.append(PATTERN_DIR / "en.json")

    for path in candidates:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            return data, path, _sha256_file(path)
    return {}, Path(), None


def pattern_manifest(entries: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """
    Build manifest-ready mapping {lang: {path, sha256}} from language->code map.
    """
    result: Dict[str, Dict[str, str]] = {}
    for lang, path_str in entries.items():
        p = Path(path_str)
        result[lang] = {"path": str(p), "sha256": _sha256_file(p)}
    return result


__all__ = ["load_patterns", "pattern_manifest", "PATTERN_DIR"]
