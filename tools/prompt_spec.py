from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class DemoExample:
    text: str
    uid: Optional[str] = None


@dataclass
class PromptSpec:
    """
    Vendor-agnostic prompt representation.
    - system: ordered list of system strings
    - user: primary input text
    - schema: optional JSON schema hint (string)
    - constraints: optional free-text constraints
    - demos: optional list of demo examples (text-only)
    - language_code/domain_id: optional routing metadata (included in hash)
    """

    system: List[str] = field(default_factory=list)
    user: str = ""
    schema: Optional[str] = None
    constraints: Optional[str] = None
    demos: List[DemoExample] = field(default_factory=list)
    language_code: str = "unknown"
    domain_id: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system": self.system,
            "user": self.user,
            "schema": self.schema,
            "constraints": self.constraints,
            "demos": [{"text": d.text, "uid": d.uid} for d in self.demos],
            "language_code": self.language_code or "unknown",
            "domain_id": self.domain_id or "unknown",
        }

    def prompt_hash(self) -> str:
        canonical = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
        import hashlib

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _flatten_system(spec: PromptSpec) -> str:
    return "\n".join([s for s in spec.system if s is not None])


def _demo_blocks(spec: PromptSpec) -> List[str]:
    blocks = []
    for idx, d in enumerate(spec.demos):
        title = d.uid or f"demo_{idx+1}"
        blocks.append(f"[DEMO {title}]\n{d.text}")
    return blocks


class OpenAIAdapter:
    @staticmethod
    def to_messages(spec: PromptSpec) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = []
        system_text = _flatten_system(spec)
        if system_text:
            messages.append({"role": "system", "content": system_text})
        # demos as separate user messages to preserve ordering
        for block in _demo_blocks(spec):
            messages.append({"role": "user", "content": block})
        messages.append({"role": "user", "content": spec.user})
        return messages


class ClaudeAdapter:
    @staticmethod
    def to_messages(spec: PromptSpec) -> List[Dict[str, str]]:
        # Claude messages follow OpenAI-like structure for compatibility
        return OpenAIAdapter.to_messages(spec)


class GeminiAdapter:
    @staticmethod
    def to_contents(spec: PromptSpec) -> List[Dict[str, Any]]:
        # Gemini chat models expect "contents" with parts; keep minimal text-only
        parts = []
        system_text = _flatten_system(spec)
        if system_text:
            parts.append({"role": "user", "parts": [{"text": system_text}]})
        for block in _demo_blocks(spec):
            parts.append({"role": "user", "parts": [{"text": block}]})
        parts.append({"role": "user", "parts": [{"text": spec.user}]})
        return parts


__all__ = ["PromptSpec", "DemoExample", "OpenAIAdapter", "ClaudeAdapter", "GeminiAdapter"]
