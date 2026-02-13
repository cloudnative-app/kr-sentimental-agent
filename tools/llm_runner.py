from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Type, Dict, Any, Optional, List, TypeVar, Generic, Tuple

from pydantic import BaseModel, ValidationError

from .backbone_client import BackboneClient
from .prompt_spec import PromptSpec, DemoExample, OpenAIAdapter, ClaudeAdapter, GeminiAdapter
from schemas.agent_outputs import (
    normalize_polarity_distribution,
    canonicalize_polarity_with_repair,
)

logger = logging.getLogger(__name__)


def _normalize_atsa_stage1_parsed(parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
    """
    Normalize raw ATSA Stage1 parsed dict: aspect_term mapping, polarity whitelist/repair (edit distance 1~2).
    Invalid polarity → None (sample invalid, run continues). Returns (parsed_dict, polarity_repair_count, polarity_invalid_count).
    """
    raw_items: List[Dict[str, Any]] = parsed.get("aspect_sentiments") or []
    if not raw_items:
        return (parsed, 0, 0)

    normalized_items: List[Dict[str, Any]] = []
    repair_count = 0
    invalid_count = 0
    for raw_item in raw_items:
        # aspect_term: from aspect_term, aspect_ref, or opinion_term.term
        aspect_term = raw_item.get("aspect_term")
        if not aspect_term or not (aspect_term.get("term") if isinstance(aspect_term, dict) else None):
            ref = raw_item.get("aspect_ref")
            if isinstance(ref, str) and ref.strip():
                aspect_term = {"term": ref.strip(), "span": {"start": 0, "end": 0}}
            else:
                ot = raw_item.get("opinion_term")
                if isinstance(ot, dict) and ot.get("term"):
                    aspect_term = {"term": (ot["term"] or "").strip(), "span": ot.get("span") or {"start": 0, "end": 0}}
                elif isinstance(ot, dict) and isinstance(ref, str) and ref.strip():
                    aspect_term = {"term": ref.strip(), "span": {"start": 0, "end": 0}}
                else:
                    aspect_term = {"term": "", "span": {"start": 0, "end": 0}}
        if isinstance(aspect_term, dict) and not aspect_term.get("term") and raw_item.get("aspect_ref"):
            aspect_term = {"term": (raw_item["aspect_ref"] or "").strip(), "span": aspect_term.get("span") or {"start": 0, "end": 0}}

        # polarity: whitelist or edit-distance 1~2 repair; invalid → None, run continues
        raw_pol = raw_item.get("polarity")
        if raw_pol is None or (isinstance(raw_pol, str) and not raw_pol.strip()):
            polarity = None
            invalid_count += 1
        else:
            canon, was_repair = canonicalize_polarity_with_repair(raw_pol)
            polarity = canon
            if was_repair:
                repair_count += 1
            elif canon is None:
                invalid_count += 1

        confidence = raw_item.get("confidence")
        if confidence is None:
            confidence = 0.5
        else:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        pol_dist = normalize_polarity_distribution(raw_item.get("polarity_distribution"))

        normalized_items.append({
            "aspect_term": aspect_term,
            "polarity": polarity,
            "evidence": raw_item.get("evidence") or "",
            "confidence": confidence,
            "polarity_distribution": pol_dist,
            "is_implicit": bool(raw_item.get("is_implicit", False)),
        })
    return ({"aspect_sentiments": normalized_items}, repair_count, invalid_count)

_semaphore_cache: Dict[int, threading.BoundedSemaphore] = {}
_sem_lock = threading.Lock()

T = TypeVar("T", bound=BaseModel)


@dataclass
class StructuredResultMeta:
    """Metadata captured during run_structured execution."""
    raw_response: str = ""
    retries: int = 0
    repair_used: bool = False
    fallback_construct_used: bool = False
    error: Optional[str] = None
    prompt_hash: Optional[str] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    usage_parse_failed: bool = False
    polarity_repair_count: int = 0
    polarity_invalid_count: int = 0

    def to_notes_str(self) -> str:
        """Format metadata for ProcessTrace.notes field."""
        return json.dumps({
            "raw_response": self.raw_response[:500],
            "retries": self.retries,
            "repair_used": self.repair_used,
            "fallback_construct_used": self.fallback_construct_used,
            "error": self.error,
            "prompt_hash": self.prompt_hash,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": self.cost_usd,
            "usage_parse_failed": self.usage_parse_failed,
            "polarity_repair_count": self.polarity_repair_count,
            "polarity_invalid_count": self.polarity_invalid_count,
        }, ensure_ascii=False)


@dataclass
class StructuredResult(Generic[T]):
    """Wrapper for run_structured output with metadata."""
    model: T
    meta: StructuredResultMeta = field(default_factory=StructuredResultMeta)


def _compact_schema(schema_model: Type[BaseModel]) -> str:
    js = schema_model.model_json_schema()
    required = set(js.get("required", []))
    props = js.get("properties", {})
    parts = []
    for name, spec in props.items():
        t = spec.get("type", "any")
        req = "required" if name in required else "optional"
        parts.append(f"{name}:{t}({req})")
    return "; ".join(parts)


def _build_retry_prompt(system_prompt: str, user_text: str, error: str, previous: str, compact_schema: str) -> str:
    return (
        f"{system_prompt}\n\n"
        f"You MUST output valid JSON matching this schema: {compact_schema}\n"
        f"Validation error: {error}\n"
        f"Original text: {user_text}\n"
        f"Previous response: {previous}\n"
        f"Return ONLY a JSON object."
    )


def _log_error(path: str, payload: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def default_errors_path(run_id: str, mode: str | None = None, stage: str | None = None) -> str:
    """
    Build a run-scoped errors path to avoid log mixing across runs.
    Uses mode when provided, otherwise falls back to stage or 'logs'.
    """
    bucket = (mode or stage or "logs").lower().replace(" ", "_")
    return str(Path("experiments") / "results" / bucket / run_id / f"errors_{run_id}.jsonl")


def _get_semaphore(max_concurrency: int) -> threading.BoundedSemaphore:
    with _sem_lock:
        if max_concurrency not in _semaphore_cache:
            _semaphore_cache[max_concurrency] = threading.BoundedSemaphore(max_concurrency)
        return _semaphore_cache[max_concurrency]


def _raise_if_realrun_fallback(
    backbone: BackboneClient,
    errors_path: str,
    run_id: str,
    text_id: str,
    stage: str,
    error: str,
    attempt: int,
    use_mock: bool,
) -> None:
    """
    If backbone is not mock and fallback is needed, log fatal error and raise RuntimeError.
    Real runs (use_mock=0) must not silently use fallback constructs.
    Backbones without a 'provider' attribute are treated as mock (for backwards compatibility with tests).
    """
    provider = getattr(backbone, "provider", "mock")  # Default to mock if not set
    if use_mock or provider == "mock":
        return
    if provider != "mock":
        _log_error(
            errors_path,
            {
                "type": "fatal_fallback_realrun",
                "run_id": run_id,
                "text_id": text_id,
                "stage": stage,
                "error": error,
                "attempt": attempt,
                "provider": provider,
            },
        )
        raise RuntimeError(
            f"[fatal_fallback_realrun] Real run (provider={provider}) failed after {attempt} attempts. "
            f"stage={stage}, text_id={text_id}, error={error}"
        )


def run_structured(
    backbone: BackboneClient,
    system_prompt: str,
    user_text: str,
    schema: Type[T],
    *,
    max_retries: int = 2,
    run_id: str,
    text_id: str,
    stage: str,
    mode: str = "",
    errors_path: Optional[str] = None,
    max_concurrency: int = 1,
    use_mock: bool = False,
    prompt_spec: Optional[PromptSpec] = None,
) -> StructuredResult[T]:
    """
    Run backbone, enforce JSON schema, repair on failures, and log errors without raising.
    - max_concurrency: simple semaphore guard to avoid provider rate limits (default 1).
    - errors_path defaults to experiments/results/<mode>/<run_id>/errors.jsonl (or stage if mode missing).
    - On repeated failures, returns a fallback model_construct() and records error metadata.
    - Returns StructuredResult containing the model and metadata (raw_response, retries, repair_used).
    """
    errors_path = errors_path or default_errors_path(run_id, mode or None, stage)
    mode_for_backbone = f"{mode or ''}:{stage}".strip(":")
    sem = _get_semaphore(max_concurrency)
    compact = _compact_schema(schema)
    attempt = 0
    last_response = ""
    last_error = ""
    spec = prompt_spec or PromptSpec(system=[system_prompt], user=user_text)
    prompt_hash = spec.prompt_hash()
    result_meta = StructuredResultMeta(prompt_hash=prompt_hash)

    while attempt <= max_retries:
        repair_used = attempt > 0
        prompt = (
            system_prompt
            if attempt == 0
            else _build_retry_prompt(system_prompt, user_text, last_error, last_response, compact)
        )
        acquired = False
        try:
            acquired = sem.acquire()
            spec_for_send = PromptSpec(
                system=[prompt],
                user=user_text,
                demos=spec.demos,
                schema=spec.schema,
                constraints=spec.constraints,
                language_code=spec.language_code,
                domain_id=spec.domain_id,
            )
            if backbone.provider == "anthropic":
                messages = ClaudeAdapter.to_messages(spec_for_send)
            else:
                messages = OpenAIAdapter.to_messages(spec_for_send)
            response_text, usage_dict = backbone.generate(
                messages,
                temperature=0.0,
                response_format="json",
                mode=mode_for_backbone,
                text_id=text_id,
            )
            # Extract usage info
            result_meta.tokens_in = usage_dict.get("tokens_in")
            result_meta.tokens_out = usage_dict.get("tokens_out")
            result_meta.cost_usd = usage_dict.get("cost_usd")
            # Check if usage parsing failed (all None for non-mock provider)
            if backbone.provider != "mock" and result_meta.tokens_in is None and result_meta.tokens_out is None:
                result_meta.usage_parse_failed = True
            response = response_text
        except Exception as e:  # provider timeout/429/etc.
            last_error = f"generate_failed:{type(e).__name__}:{e}"
            attempt += 1
            if attempt > max_retries:
                _log_error(
                    errors_path,
                    {
                        "type": "exception",
                        "run_id": run_id,
                        "text_id": text_id,
                        "stage": stage,
                        "error": last_error,
                        "attempt": attempt,
                        "response_snippet": last_response[:500] if last_response else "",
                    },
                )
                result_meta.raw_response = last_response
                result_meta.retries = attempt - 1
                result_meta.repair_used = repair_used
                result_meta.fallback_construct_used = True
                result_meta.error = last_error
                # Log fallback_construct usage
                _log_error(
                    errors_path,
                    {
                        "type": "fallback_construct",
                        "run_id": run_id,
                        "text_id": text_id,
                        "stage": stage,
                        "reason": last_error,
                        "attempt": attempt,
                    },
                )
                # Fatal error if real run
                _raise_if_realrun_fallback(backbone, errors_path, run_id, text_id, stage, last_error, attempt, use_mock=use_mock)
                fallback = schema.model_construct()
                if hasattr(fallback, "meta") and isinstance(getattr(fallback, "meta"), dict):
                    fallback.meta["llm_runner_error"] = last_error
                return StructuredResult(model=fallback, meta=result_meta)
            continue
        finally:
            if acquired:
                try:
                    sem.release()
                except ValueError:
                    pass

        last_response = response
        result_meta.raw_response = response
        result_meta.retries = attempt
        result_meta.repair_used = repair_used

        try:
            parsed = json.loads(response)
            # Stage1 ATSA: whitelist/repair polarity (edit distance 1~2); invalid → None, run continues
            schema_name = getattr(schema, "__name__", "")
            if schema_name == "AspectSentimentStage1Schema":
                parsed, pol_repair, pol_invalid = _normalize_atsa_stage1_parsed(parsed)
                result_meta.polarity_repair_count = (getattr(result_meta, "polarity_repair_count", 0) or 0) + pol_repair
                result_meta.polarity_invalid_count = (getattr(result_meta, "polarity_invalid_count", 0) or 0) + pol_invalid
            validated_model = schema.model_validate(parsed)
            # FIX-3: polarity mismatch guard for Stage1 ATSA
            if schema_name == "AspectSentimentStage1Schema":
                raw_items = (parsed.get("aspect_sentiments") or [])
                for i, val_item in enumerate(getattr(validated_model, "aspect_sentiments", []) or []):
                    if i >= len(raw_items):
                        break
                    expected_pol = raw_items[i].get("polarity")
                    parsed_pol = getattr(val_item, "polarity", None)
                    if expected_pol != parsed_pol:
                        logger.error(
                            "ATSA_POLARITY_MISMATCH",
                            extra={
                                "raw": expected_pol,
                                "parsed": parsed_pol,
                                "text_id": text_id or "",
                                "index": i,
                            },
                        )
                        assert expected_pol == parsed_pol, "ATSA polarity must match normalized raw polarity"
            # Success - return result with metadata
            return StructuredResult(model=validated_model, meta=result_meta)
        except json.JSONDecodeError as e:
            last_error = f"json_parse_failed:{type(e).__name__}:{e}"
            # Always log parsing failures
            _log_error(
                errors_path,
                {
                    "type": "json_parse_error",
                    "run_id": run_id,
                    "text_id": text_id,
                    "stage": stage,
                    "error": last_error,
                    "attempt": attempt + 1,
                    "response_snippet": last_response[:500],
                },
            )
            attempt += 1
            if attempt > max_retries:
                result_meta.fallback_construct_used = True
                result_meta.error = last_error
                _log_error(
                    errors_path,
                    {
                        "type": "fallback_construct",
                        "run_id": run_id,
                        "text_id": text_id,
                        "stage": stage,
                        "reason": last_error,
                        "attempt": attempt,
                    },
                )
                # Fatal error if real run
                _raise_if_realrun_fallback(backbone, errors_path, run_id, text_id, stage, last_error, attempt, use_mock=use_mock)
                fallback = schema.model_construct()
                if hasattr(fallback, "meta") and isinstance(getattr(fallback, "meta"), dict):
                    fallback.meta["llm_runner_error"] = last_error
                return StructuredResult(model=fallback, meta=result_meta)
            continue
        except ValueError as e:
            # ATSA normalizer: missing/invalid polarity (no neutral fallback)
            last_error = f"atsa_parse_failed:{type(e).__name__}:{e}"
            _log_error(
                errors_path,
                {
                    "type": "atsa_parse_error",
                    "run_id": run_id,
                    "text_id": text_id,
                    "stage": stage,
                    "error": last_error,
                    "attempt": attempt + 1,
                    "response_snippet": last_response[:500],
                },
            )
            attempt += 1
            if attempt > max_retries:
                result_meta.fallback_construct_used = True
                result_meta.error = last_error
                _log_error(
                    errors_path,
                    {
                        "type": "fallback_construct",
                        "run_id": run_id,
                        "text_id": text_id,
                        "stage": stage,
                        "reason": last_error,
                        "attempt": attempt,
                    },
                )
                _raise_if_realrun_fallback(backbone, errors_path, run_id, text_id, stage, last_error, attempt, use_mock=use_mock)
                fallback = schema.model_construct()
                if hasattr(fallback, "meta") and isinstance(getattr(fallback, "meta"), dict):
                    fallback.meta["llm_runner_error"] = last_error
                return StructuredResult(model=fallback, meta=result_meta)
            continue
        except ValidationError as e:
            last_error = f"schema_validation_failed:{type(e).__name__}:{e}"
            # Always log schema validation failures
            _log_error(
                errors_path,
                {
                    "type": "schema_validation_error",
                    "run_id": run_id,
                    "text_id": text_id,
                    "stage": stage,
                    "error": last_error,
                    "attempt": attempt + 1,
                    "response_snippet": last_response[:500],
                },
            )
            attempt += 1
            if attempt > max_retries:
                result_meta.fallback_construct_used = True
                result_meta.error = last_error
                _log_error(
                    errors_path,
                    {
                        "type": "fallback_construct",
                        "run_id": run_id,
                        "text_id": text_id,
                        "stage": stage,
                        "reason": last_error,
                        "attempt": attempt,
                    },
                )
                # Fatal error if real run
                _raise_if_realrun_fallback(backbone, errors_path, run_id, text_id, stage, last_error, attempt, use_mock=use_mock)
                fallback = schema.model_construct()
                if hasattr(fallback, "meta") and isinstance(getattr(fallback, "meta"), dict):
                    fallback.meta["llm_runner_error"] = last_error
                return StructuredResult(model=fallback, meta=result_meta)
            continue

    # Fallback at end of loop (should not normally reach here)
    result_meta.fallback_construct_used = True
    result_meta.error = last_error or "unknown_error"
    _log_error(
        errors_path,
        {
            "type": "fallback_construct",
            "run_id": run_id,
            "text_id": text_id,
            "stage": stage,
            "reason": last_error or "unknown_error",
            "attempt": attempt,
        },
    )
    # Fatal error if real run
    _raise_if_realrun_fallback(backbone, errors_path, run_id, text_id, stage, last_error or "unknown_error", attempt)
    fallback = schema.model_construct()
    if hasattr(fallback, "meta") and isinstance(getattr(fallback, "meta"), dict):
        fallback.meta["llm_runner_error"] = last_error or "unknown_error"
    return StructuredResult(model=fallback, meta=result_meta)
