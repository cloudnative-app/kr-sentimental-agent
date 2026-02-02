"""
Provider dry-run: verify real backbone connectivity through SupervisorAgent (same path as schema_validation_test).

Usage (example):
    python scripts/provider_dry_run.py --text "서비스는 친절했지만 음식은 별로였어" --mode proposed

Behavior:
- Forces BACKBONE_USE_MOCK=0 and runs a single SupervisorAgent pass.
- Prints path signature (provider/model/env snapshot + which stages ran).
- Fail-fast if provider resolves to mock or common auth/model errors.
- Success summary is schema-robust: counts aspects/sentiments via multiple fallbacks and records the chosen source.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import traceback
from typing import Any, Dict, List, Tuple

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from tools.backbone_client import BackboneClient  # noqa: E402
from tools.data_tools import InternalExample  # noqa: E402
from agents.supervisor_agent import SupervisorAgent  # noqa: E402


DIAG_ENV_HINTS = {
    "openai": ["OPENAI_API_KEY", "OPENAI_BASE_URL (optional)"],
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL (optional)"],
    "google": ["GOOGLE_API_KEY", "GENAI_API_KEY"],
}

CONTRAST_TOKENS = [
    "지만",
    "하지만",
    "그런데",
    "그러나",
    "반면",
    "반면에",
    "는데",
    "은데",
    "는 데",
    "데",
]


def _format_env_snapshot(provider: str) -> str:
    base_keys = ["OPENAI_BASE_URL", "ANTHROPIC_BASE_URL", "GOOGLE_API_BASE"]
    snapshot = []
    for key in base_keys:
        val = os.getenv(key)
        if val:
            snapshot.append(f"{key} set")
    hints = ", ".join(DIAG_ENV_HINTS.get(provider, []))
    base = "; ".join(snapshot) if snapshot else "base_url: (not set)"
    return f"{base}\nrequired env: {hints or 'see provider docs'}"


def _classify_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "missing api key" in msg or "env var" in msg:
        return "auth_missing_env"
    if "unauthorized" in msg or "invalid api key" in msg:
        return "auth_invalid_key"
    if "rate limit" in msg or "429" in msg:
        return "rate_limit"
    if "not found" in msg or ("model" in msg and "not" in msg):
        return "model_not_found"
    return "unknown_error"


def _safe_get(d: Dict[str, Any], key: str) -> Any:
    return d.get(key) if isinstance(d, dict) else None


def _parse_raw_response(raw_resp: Any) -> List[Any]:
    try:
        if isinstance(raw_resp, str):
            raw_resp = json.loads(raw_resp)
        if isinstance(raw_resp, dict):
            val = raw_resp.get("aspects") or raw_resp.get("aspect_sentiments")
            if isinstance(val, list):
                return val
    except Exception:
        pass
    return []


def _extract_aspects(result_dict: Dict[str, Any]) -> Tuple[List[Any], str]:
    meta = _safe_get(result_dict, "meta") or {}
    inputs = _safe_get(result_dict, "inputs") or {}

    if isinstance(meta.get("stage1_aspects"), list):
        return meta["stage1_aspects"], "meta.stage1_aspects"

    filtered = _safe_get(inputs, "filtered_aspects")
    if isinstance(filtered, list):
        return filtered, "inputs.filtered_aspects"

    ate_debug = _safe_get(inputs, "ate_debug") or {}
    raw_list = _safe_get(ate_debug, "raw")
    if isinstance(raw_list, list):
        return raw_list, "inputs.ate_debug.raw"

    raw_resp = _safe_get(ate_debug, "raw_response")
    parsed = _parse_raw_response(raw_resp)
    if parsed:
        return parsed, "ate_debug.raw_response"

    # Try process_trace for ATE output
    for tr in result_dict.get("process_trace", []) or []:
        if tr.get("agent", "").lower() != "ate":
            continue
        out = tr.get("output", {}) or {}
        aspects = out.get("aspects")
        if isinstance(aspects, list):
            return aspects, "process_trace.ATE.aspects"
        for k, v in out.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and {"term", "span"} & set(v[0].keys()):
                return v, f"process_trace.ATE.{k}"

    return [], "missing"


def _filter_sentiment_list(lst: List[Any]) -> List[Any]:
    """Keep only entries that look aspect-specific and dedup by (ref,start,end,label)."""
    filtered = []
    seen = set()
    for s in lst or []:
        if not isinstance(s, dict):
            continue

        opinion_term = s.get("opinion_term") or {}
        if not isinstance(opinion_term, dict):
            opinion_term = {}

        ref = s.get("aspect_ref") or s.get("target")
        span = s.get("span") or s.get("opinion_span") or opinion_term.get("span")
        start = span.get("start") if isinstance(span, dict) else None
        end = span.get("end") if isinstance(span, dict) else None
        label = s.get("polarity") or s.get("label")

        if not ref:
            continue

        key = (ref, start, end, label)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(s)
    return filtered


def _extract_sentiments(
    result_dict: Dict[str, Any], stage1_atsa_obj: Any
) -> Tuple[List[Any], str, List[Any]]:
    inputs = _safe_get(result_dict, "inputs") or {}

    sents = _safe_get(inputs, "aspect_sentiments")
    if isinstance(sents, list):
        filtered = _filter_sentiment_list(sents)
        return filtered, "inputs.aspect_sentiments", sents

    # Direct attributes on stage1_atsa object
    if stage1_atsa_obj is not None:
        for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
            if hasattr(stage1_atsa_obj, cand):
                val = getattr(stage1_atsa_obj, cand)
                if isinstance(val, list):
                    filtered = _filter_sentiment_list(val)
                    return filtered, f"stage1_atsa.{cand}", val
        if hasattr(stage1_atsa_obj, "model_dump"):
            try:
                data = stage1_atsa_obj.model_dump()
                if isinstance(data, dict):
                    for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
                        val = data.get(cand)
                        if isinstance(val, list):
                            filtered = _filter_sentiment_list(val)
                            return filtered, f"stage1_atsa.model_dump.{cand}", val
                    # Any list value
                    for k, v in data.items():
                        if isinstance(v, list):
                            filtered = _filter_sentiment_list(v)
                            return filtered, f"stage1_atsa.model_dump.{k}", v
            except Exception:
                pass
        # dict-like fallback
        try:
            data = dict(stage1_atsa_obj)  # type: ignore
            if isinstance(data, dict):
                for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
                    val = data.get(cand)
                    if isinstance(val, list):
                        filtered = _filter_sentiment_list(val)
                        return filtered, f"stage1_atsa.dict.{cand}", val
                for k, v in data.items():
                    if isinstance(v, list):
                        filtered = _filter_sentiment_list(v)
                        return filtered, f"stage1_atsa.dict.{k}", v
        except Exception:
            pass

    stage1_atsa = _safe_get(result_dict, "stage1_atsa") or {}
    for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
        val = stage1_atsa.get(cand) if isinstance(stage1_atsa, dict) else None
        if val is None and hasattr(stage1_atsa, cand):
            val = getattr(stage1_atsa, cand)
        if isinstance(val, list):
            filtered = _filter_sentiment_list(val)
            return filtered, f"stage1_atsa.{cand}", val

    if isinstance(stage1_atsa, dict):
        for k, v in stage1_atsa.items():
            if isinstance(v, list):
                filtered = _filter_sentiment_list(v)
                return filtered, f"stage1_atsa.{k}", v

    # Try process_trace entries
    for tr in result_dict.get("process_trace", []) or []:
        if tr.get("agent", "").lower() != "atsa":
            continue
        out = tr.get("output", {}) or {}
        for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
            val = out.get(cand)
            if isinstance(val, list):
                filtered = _filter_sentiment_list(val)
                return filtered, f"process_trace.ATSA.{cand}", val
        # any list in output
        for k, v in out.items():
            if isinstance(v, list):
                filtered = _filter_sentiment_list(v)
                return filtered, f"process_trace.ATSA.{k}", v

    return [], "missing", []


def _path_signature(process_trace: List[Dict[str, Any]]) -> Dict[str, bool]:
    sig = {
        "stage1_ate": False,
        "stage1_atsa": False,
        "stage1_validator": False,
        "stage2_ate": False,
        "stage2_atsa": False,
        "stage2_validator": False,
        "moderator": False,
    }
    for tr in process_trace or []:
        agent = tr.get("agent", "").lower()
        stage = tr.get("stage", "").lower()
        if stage == "stage1" and agent == "ate":
            sig["stage1_ate"] = True
        elif stage == "stage1" and agent == "atsa":
            sig["stage1_atsa"] = True
        elif stage == "stage1" and agent == "validator":
            sig["stage1_validator"] = True
        elif stage == "stage2" and agent == "ate":
            sig["stage2_ate"] = True
        elif stage == "stage2" and agent == "atsa":
            sig["stage2_atsa"] = True
        elif stage == "stage2" and agent == "validator":
            sig["stage2_validator"] = True
        elif stage == "moderator":
            sig["moderator"] = True
    return sig


def _debug_atsa(stage1_atsa_obj: Any, result_obj: Any):
    print("[debug] stage1_atsa type=", type(stage1_atsa_obj))
    if hasattr(stage1_atsa_obj, "model_dump"):
        try:
            data = stage1_atsa_obj.model_dump()
            print("[debug] stage1_atsa.model_dump keys=", list(data.keys()))
            for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
                val = data.get(cand)
                if isinstance(val, list):
                    sample = val[0] if val else None
                    print(f"[debug] {cand} len={len(val)} sample={sample}")
                    break
        except Exception:
            pass
    try:
        if isinstance(stage1_atsa_obj, dict):
            print("[debug] stage1_atsa dict keys=", list(stage1_atsa_obj.keys()))
    except Exception:
        pass
    try:
        fr = getattr(result_obj, "final_result", None)
        if fr and hasattr(fr, "model_dump"):
            print("[debug] final_result keys=", list(fr.model_dump().keys()))
    except Exception:
        pass
    try:
        trace = getattr(result_obj, "process_trace", None)
        if trace:
            print(f"[debug] process_trace len={len(trace)}")
            for tr in trace:
                agent = tr.get("agent")
                stage = tr.get("stage")
                if agent and "atsa" in agent.lower():
                    out = tr.get("output", {}) or {}
                    print(f"[debug] trace agent={agent} stage={stage} keys={list(out.keys())}")
                    for cand in ("aspect_sentiments", "sentiments", "items", "results", "outputs", "pairs"):
                        val = out.get(cand)
                        if isinstance(val, list):
                            sample = val[0] if val else None
                            print(f"[debug] trace {cand} len={len(val)} sample={sample}")
                            break
                    break
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="Input text to send to the provider.")
    ap.add_argument("--mode", default="proposed", help="Pipeline mode label (logged only).")
    ap.add_argument("--provider", default=None, help="Provider override (e.g., openai, anthropic).")
    ap.add_argument("--config", default=None, help="Optional pipeline config YAML to mirror experiment settings.")
    ap.add_argument("--timeout_s", type=int, default=60, help="Timeout in seconds.")
    args = ap.parse_args()

    # Force real provider path
    os.environ["BACKBONE_USE_MOCK"] = "0"

    # Load optional pipeline config
    pipeline_cfg: Dict[str, Any] = {}
    if args.config:
        try:
            import yaml  # type: ignore

            with open(args.config, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                pipeline_cfg = cfg.get("pipeline", {}) or {}
        except Exception as e:  # pragma: no cover - best effort
            print(f"[dry-run] warning: failed to load config {args.config}: {e}")

    client = BackboneClient(provider=args.provider)
    if client.provider == "mock":
        print("[dry-run] provider resolved to 'mock'. Set BACKBONE_PROVIDER or --provider for real backend.")
        sys.exit(1)

    print(f"[dry-run] provider={client.provider}, model={client.model}")
    print(_format_env_snapshot(client.provider))

    example = InternalExample(uid="dry0", text=args.text)
    supervisor = SupervisorAgent(backbone=client, config=pipeline_cfg, run_id="dry_run")

    def _call():
        start = time.time()
        result = supervisor.run(example)
        latency_ms = int((time.time() - start) * 1000)
        result_dict = result.model_dump()
        aspects, aspect_source = _extract_aspects(result_dict)
        sentiments, sent_source, raw_sents = _extract_sentiments(
            result_dict, getattr(result, "stage1_atsa", None)
        )
        inputs_keys = list(result_dict.get("inputs", {}).keys()) if isinstance(result_dict.get("inputs"), dict) else []
        meta_keys = list(result_dict.get("meta", {}).keys()) if isinstance(result_dict.get("meta"), dict) else []
        sig = _path_signature(result_dict.get("process_trace", []))

        if aspect_source == "missing":
            print("[warn] aspects not found via known fields; reported as 0")
        if sent_source == "missing":
            print("[warn] sentiments not found via known fields; reported as 0")

        _debug_atsa(getattr(result, "stage1_atsa", None), result)
        try:
            keys_list = [list(s.keys()) for s in sentiments]
            print(f"[debug] sentiments len={len(sentiments)} keys_per_item={keys_list}")
        except Exception:
            pass
        try:
            if raw_sents:
                raw_keys = [list(s.keys()) for s in raw_sents]
                print(f"[debug] raw_sentiments len={len(raw_sents)} keys_per_item={raw_keys}")
        except Exception:
            pass

        summary = {
            "provider": client.provider,
            "model": client.model,
            "latency_ms": latency_ms,
            "stage1_aspects": len(aspects),
            "stage1_sentiments": len(sentiments),
            "aspect_source": aspect_source,
            "sentiment_source": sent_source,
            "result_top_keys": list(result_dict.keys()),
            "inputs_top_keys": inputs_keys,
            "meta_top_keys": meta_keys,
            "path_signature": sig,
            "request_id": result_dict.get("meta", {}).get("run_id"),
            "contrast_tokens_detected": any(tok in args.text for tok in CONTRAST_TOKENS),
        }
        return summary

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_call)
            summary = fut.result(timeout=args.timeout_s)
    except Exception as exc:  # pragma: no cover - diagnostics
        cause = _classify_error(exc)
        print(f"[dry-run] FAILED ({cause})")
        print(traceback.format_exc())
        sys.exit(1)

    print("[dry-run] SUCCESS")
    print(json.dumps(summary, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
