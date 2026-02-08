from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Iterable, TypeVar

from tools.pattern_loader import load_patterns

T = TypeVar("T")

# Retry config for rate limit (429) and server errors (503)
_RETRY_MAX_ATTEMPTS = 5
_RETRY_BASE_SECONDS = 2.0
_RETRY_STATUS_CODES = (429, 503)


def _is_retryable(exc: BaseException) -> bool:
    """True if exception indicates rate limit (429) or server overload (503)."""
    if getattr(exc, "status_code", None) in _RETRY_STATUS_CODES:
        return True
    if getattr(exc, "response", None) is not None:
        status = getattr(exc.response, "status_code", None)
        if status in _RETRY_STATUS_CODES:
            return True
    name = type(exc).__name__
    if "RateLimit" in name or "rate_limit" in str(exc).lower():
        return True
    if "503" in str(exc) or "429" in str(exc):
        return True
    return False


def _retry_with_backoff(fn: Callable[[], T], provider: str) -> T:
    """Call fn(); on 429/503 retry with exponential backoff. Raises last exception after max attempts."""
    last_exc = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt == _RETRY_MAX_ATTEMPTS or not _is_retryable(e):
                raise
            wait = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            _logger.warning(
                "[%s] %s (attempt %d/%d); retrying in %.1fs",
                provider, type(e).__name__, attempt, _RETRY_MAX_ATTEMPTS, wait,
            )
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]

# Configure module-level logger to stderr
_logger = logging.getLogger("backbone_client")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)


def _format_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "role": msg.get("role", "user"),
            "content": str(msg.get("content", "")),
        }
        for msg in messages
    ]


def _require_env(var_names: Iterable[str], provider: str) -> str:
    for var in var_names:
        val = os.getenv(var)
        if val:
            return val
    names = ", ".join(var_names)
    raise ValueError(f"Missing API key env var(s) [{names}] required for provider='{provider}'.")


def _resolve_provider(explicit: str | None) -> str:
    if explicit:
        return explicit.lower()

    env_provider = os.getenv("BACKBONE_PROVIDER")
    if env_provider:
        return env_provider.lower()

    use_mock_env = os.getenv("BACKBONE_USE_MOCK")
    if use_mock_env is not None:
        normalized = use_mock_env.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            raise ValueError(
                "BACKBONE_PROVIDER is not set but BACKBONE_USE_MOCK=0. "
                "Set BACKBONE_PROVIDER (env) or backbone.provider in config to run against a real provider."
            )

    _logger.warning("BACKBONE_PROVIDER not set; defaulting to 'mock'. Set BACKBONE_USE_MOCK=0 to forbid mock fallback.")
    return "mock"


class BackboneClient:
    """Unified backbone client. Default provider is a deterministic mock."""

    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = _resolve_provider(provider)
        self.model = model or os.getenv("BACKBONE_MODEL", "gpt-3.5-turbo")

    def generate(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str = "text",
        mode: str = "",
        text_id: str = "",
    ) -> tuple[str, Dict[str, Any]]:
        """
        Returns: (response_text, usage_dict)
        usage_dict contains: tokens_in, tokens_out, cost_usd (or None if unavailable)
        """
        msgs = _format_messages(messages)
        prompt_len = sum(len(m.get("content", "")) for m in msgs)
        _logger.info(
            "generate() called: mode=%s, provider=%s, model_name=%s, text_id=%s, prompt_len=%d",
            mode or "unknown",
            self.provider,
            self.model,
            text_id or "unknown",
            prompt_len,
        )

        if self.provider == "mock":
            user_text = msgs[-1]["content"] if msgs else ""
            stage = mode or ""

            lang_guess = "ko" if re.search(r"[가-힣]", user_text or "") else "en"
            patterns, _, _ = load_patterns(lang_guess)
            contrast_tokens = patterns.get("contrast_markers") or []
            topic_suffixes = tuple(patterns.get("topic_particles") or [])
            token_regex = patterns.get("aspect_token_regex") or r"[가-힣A-Za-z]{2,}"
            try:
                token_pattern = re.compile(token_regex)
            except re.error:
                token_pattern = re.compile(r"[A-Za-z]{2,}")
            pos_keys = patterns.get("positive_keywords") or ["good", "great"]
            neg_keys = patterns.get("negative_keywords") or ["bad", "poor"]

            def _detect_contrast(text: str):
                for tok in contrast_tokens:
                    m = re.search(tok, text)
                    if m:
                        return m
                return None

            def _strip_topic(term: str):
                if term.endswith(topic_suffixes) and len(term) > 1:
                    return term[:-1]
                return term

            def _first_token_with_span(text: str, offset: int = 0):
                for m in token_pattern.finditer(text):
                    term = _strip_topic(m.group(0))
                    if len(term) == 0:
                        continue
                    start = offset + m.start()
                    end = start + len(term)
                    return term, start, end
                return None

            def _clause_aspect(clause: str, offset: int = 0):
                hit = _first_token_with_span(clause, offset)
                if hit:
                    return hit
                if clause:
                    return clause[0], offset, offset + 1
                return "서비스", offset, offset + 3

            def pick_aspects(text: str):
                text = text or ""
                m = _detect_contrast(text)
                if not m:
                    return [_clause_aspect(text, 0)]
                left = text[: m.start()]
                right = text[m.end() :]
                aspects = []
                lh = _clause_aspect(left, 0)
                rh = _clause_aspect(right, m.end())
                if lh:
                    aspects.append(lh)
                if rh and not any(a[1] == rh[1] and a[2] == rh[2] for a in aspects):
                    aspects.append(rh)
                return aspects or [_clause_aspect(text, 0)]

            def _aspect_term_span(text: str, start_after: int):
                """Return (term_text, start, end) for aspect surface form in text."""
                m = token_pattern.search(text, start_after)
                if m:
                    return m.group(0), m.start(), m.end()
                if start_after < len(text):
                    end = min(len(text), start_after + 4)
                    return text[start_after:end], start_after, end
                return text[:1] or "좋다", 0, max(1, len(text))

            def sentiment_for(text: str) -> str:
                lower = text.lower()
                if any(k.lower() in lower for k in pos_keys):
                    return "positive"
                if any(k.lower() in lower for k in neg_keys):
                    return "negative"
                return "neutral"

            aspects_raw = pick_aspects(user_text)
            contrast = _detect_contrast(user_text) is not None and len(aspects_raw) >= 2
            pol = sentiment_for(user_text)
            if pol == "neutral" and len(user_text) >= 5:
                pol = "positive"

            payload: Dict[str, Any] = {}

            if "ATE" in stage and "reanalysis" not in stage:
                payload = {
                    "aspects": [
                        {
                            "term": term,
                            "span": {"start": s, "end": e},
                            "confidence": 0.78 if i == 0 else 0.5,
                            "rationale": "mock aspect" if i == 0 else "contrast heuristic second aspect",
                        }
                        for i, (term, s, e) in enumerate(aspects_raw)
                    ]
                }
            elif "ATSA" in stage and "reanalysis" not in stage:
                sentiments = []
                for i, (term, s, e) in enumerate(aspects_raw):
                    at_term, at_s, at_e = _aspect_term_span(user_text, e)
                    pol_i = "positive"
                    if contrast:
                        pol_i = "negative" if i == 1 else "positive"
                    else:
                        pol_i = pol
                    sentiments.append(
                        {
                            "aspect_term": {"term": at_term, "span": {"start": at_s, "end": at_e}},
                            "polarity": pol_i,
                            "evidence": user_text[max(0, s - 2) : min(len(user_text), at_e + 6)],
                            "confidence": 0.8 if i == 0 else 0.7,
                            "polarity_distribution": {pol_i: 0.8, "neutral": 0.1},
                            "is_implicit": False,
                        }
                    )
                payload = {"aspect_sentiments": sentiments}
            elif "Validator" in stage and "reanalysis" not in stage:
                payload = {"structural_risks": [], "consistency_score": 1.0, "correction_proposals": []}
            elif "ATE" in stage and "reanalysis" in stage:
                payload = {
                    "aspect_review": [
                        {"term": term, "action": "keep", "revised_span": {"start": s, "end": e}, "reason": "mock review"}
                        for term, s, e in aspects_raw
                    ]
                }
            elif "ATSA" in stage and "reanalysis" in stage:
                neg_words = ["안", "못", "별로", "싫", "최악", "짜증", "불만", "나빠"]
                if any(w in user_text for w in neg_words) and aspects_raw:
                    payload = {
                        "sentiment_review": [
                            {
                                "aspect_term": aspects_raw[0][0],
                                "action": "flip_polarity",
                                "revised_polarity": "negative",
                                "reason": "mock flip on negation keyword",
                            }
                        ]
                    }
                else:
                    payload = {"sentiment_review": []}
            elif "Validator" in stage and "reanalysis" in stage:
                payload = {"final_validation": {"resolved_risks": [], "remaining_risks": [], "final_consistency_score": 1.0}}
            else:
                payload = {}

            response_text = json.dumps(payload, ensure_ascii=False) if response_format == "json" else str(payload)
            # Mock provider: no real usage tracking
            usage = {"tokens_in": None, "tokens_out": None, "cost_usd": None}
            return response_text, usage

        if self.provider == "openai":
            from openai import OpenAI  # type: ignore

            _require_env(["OPENAI_API_KEY"], "openai")
            client = OpenAI()  # api_key read from env; ensured above
            resp = client.chat.completions.create(
                model=self.model,
                messages=msgs,
                temperature=temperature if temperature is not None else 0.0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"} if response_format == "json" else None,
            )
            response_text = resp.choices[0].message.content or ""
            # Extract usage from OpenAI response
            usage = {"tokens_in": None, "tokens_out": None, "cost_usd": None}
            if hasattr(resp, "usage"):
                usage["tokens_in"] = getattr(resp.usage, "prompt_tokens", None)
                usage["tokens_out"] = getattr(resp.usage, "completion_tokens", None)
                # Cost calculation (approximate, model-dependent)
                if usage["tokens_in"] is not None and usage["tokens_out"] is not None:
                    # Rough pricing: adjust per model
                    cost = None
                    if "gpt-4" in self.model.lower():
                        cost = (usage["tokens_in"] / 1_000_000 * 10.0) + (usage["tokens_out"] / 1_000_000 * 30.0)
                    elif "gpt-3.5" in self.model.lower():
                        cost = (usage["tokens_in"] / 1_000_000 * 0.5) + (usage["tokens_out"] / 1_000_000 * 1.5)
                    usage["cost_usd"] = cost
            return response_text, usage

        if self.provider == "anthropic":
            from anthropic import Anthropic  # type: ignore

            _require_env(["ANTHROPIC_API_KEY"], "anthropic")
            client = Anthropic()  # api_key read from env; ensured above

            def _call_anthropic():
                return client.messages.create(
                    model=self.model,
                    messages=msgs,
                    temperature=temperature if temperature is not None else 0.0,
                    max_tokens=max_tokens or 1024,
                )

            resp = _retry_with_backoff(_call_anthropic, "anthropic")
            response_text = resp.content[0].text if resp.content else ""
            # Extract usage from Anthropic response
            usage = {"tokens_in": None, "tokens_out": None, "cost_usd": None}
            if hasattr(resp, "usage"):
                usage["tokens_in"] = getattr(resp.usage, "input_tokens", None)
                usage["tokens_out"] = getattr(resp.usage, "output_tokens", None)
                # Cost calculation (approximate)
                if usage["tokens_in"] is not None and usage["tokens_out"] is not None:
                    # Rough pricing for Claude models
                    cost = (usage["tokens_in"] / 1_000_000 * 3.0) + (usage["tokens_out"] / 1_000_000 * 15.0)
                    usage["cost_usd"] = cost
            return response_text, usage

        if self.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore

            _require_env(["GOOGLE_API_KEY", "GENAI_API_KEY"], "google")
            llm = ChatGoogleGenerativeAI(
                model=self.model,
                temperature=temperature if temperature is not None else 0.0,
                max_output_tokens=max_tokens,
            )

            def _call_google():
                return llm.invoke(msgs)

            result = _retry_with_backoff(_call_google, "google")
            response_text = getattr(result, "content", str(result))
            # Google provider: usage extraction may vary by SDK version
            usage = {"tokens_in": None, "tokens_out": None, "cost_usd": None}
            # Try to extract usage if available
            if hasattr(result, "response_metadata"):
                meta = result.response_metadata
                if isinstance(meta, dict):
                    usage_info = meta.get("usage_metadata") or meta.get("usage")
                    if usage_info:
                        usage["tokens_in"] = usage_info.get("prompt_token_count") or usage_info.get("input_tokens")
                        usage["tokens_out"] = usage_info.get("candidates_token_count") or usage_info.get("output_tokens")
            return response_text, usage

        raise ValueError(f"Unsupported BACKBONE_PROVIDER '{self.provider}'")
