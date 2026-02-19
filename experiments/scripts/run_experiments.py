from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from evaluation.baselines import make_runner, resolve_run_mode
from tools.backbone_client import BackboneClient
from tools.data_tools import InternalExample
from tools.llm_runner import default_errors_path
from data.datasets.loader import load_datasets, resolve_dataset_paths, BlockedDatasetPathError
from agents.prompts import PROMPT_DIR
from tools.demo_sampler import DemoSampler, compute_eval_hashes
from tools.pattern_loader import load_patterns

# Reuse existing scorecard generator to avoid metric drift
from scripts.scorecard_from_smoke import make_scorecard
from tools.aux_hf_runner import build_hf_signal
from metrics.eval_tuple import final_aspects_from_final_tuples, gold_row_to_tuples


# -------------- Hashing / utils --------------
def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path | str | None) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _hash_cfg(cfg: Dict[str, Any]) -> Tuple[str, str]:
    canonical = json.dumps(cfg, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), canonical


def _git_commit_hash() -> Optional[str]:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return None


def _prompt_hashes(prompt_dir: Path = PROMPT_DIR) -> Dict[str, Optional[str]]:
    hashes: Dict[str, Optional[str]] = {}
    if prompt_dir.exists():
        for path in prompt_dir.glob("*.md"):
            hashes[path.stem] = _sha256_file(path)
    return hashes


def _load_allow_terms(path: Optional[str]) -> Tuple[set[str], Optional[str]]:
    """Load allowlist terms (if provided) and return (set, sha256)."""
    if not path:
        return set(), None
    allow_path = Path(path)
    if not allow_path.exists():
        return set(), None
    content = allow_path.read_text(encoding="utf-8-sig")
    terms: set[str] = set()
    for line in content.splitlines():
        for tok in line.replace(",", " ").replace("\t", " ").split():
            if tok:
                terms.add(tok.strip())
    return terms, _sha256_file(allow_path)


def _flatten_examples(train: Sequence[InternalExample], valid: Sequence[InternalExample], test: Sequence[InternalExample]) -> List[InternalExample]:
    result: List[InternalExample] = []
    result.extend(train or [])
    result.extend(valid or [])
    result.extend(test or [])
    return result


def _examples_from_splits(
    train: Sequence[InternalExample],
    valid: Sequence[InternalExample],
    test: Sequence[InternalExample],
    processing_splits: Sequence[str],
) -> List[InternalExample]:
    """Build the example list for the inference loop from only the given splits (P1: paper eval-only)."""
    want = set(processing_splits)
    result: List[InternalExample] = []
    if "train" in want:
        result.extend(train or [])
    if "valid" in want:
        result.extend(valid or [])
    if "test" in want:
        result.extend(test or [])
    return result


def _resolve_split_source_path(data_cfg: Dict[str, Any], split: str) -> Optional[str]:
    fmt = data_cfg.get("input_format", "csv")
    key_map = {
        "csv": {"train": "train_file", "valid": "valid_file", "test": "test_file"},
        "nikluge_sa_2022": {"train": "train_file", "valid": "valid_file", "test": "test_file"},
        "json_internal": {"train": "json_dir_train", "valid": "json_dir_valid", "test": "json_dir_test"},
    }
    key = key_map.get(fmt, {}).get(split)
    return data_cfg.get(key) if key else None


def _enforce_leakage_guard(
    examples: Sequence[InternalExample],
    *,
    split: str,
    source_path: Optional[str],
    text_terms: Sequence[str] = ("annotation", '"label"', "gold"),
    meta_key_tokens: Sequence[str] = ("annotation", "gold", "label"),
) -> None:
    def _fail(uid: str, reason: str) -> None:
        src = source_path or "<unknown>"
        raise RuntimeError(f"[leakage_guard] split={split} uid={uid} {reason} source={src}")

    for ex in examples:
        if ex.label is not None:
            _fail(ex.uid, "label present")
        if ex.target is not None:
            _fail(ex.uid, "target present")
        if ex.span is not None:
            _fail(ex.uid, "span present")

        meta = ex.metadata or {}
        for key in meta.keys():
            key_norm = str(key).lower()
            if any(tok in key_norm for tok in meta_key_tokens):
                _fail(ex.uid, f"metadata key '{key}' suggests gold annotation")

        text_norm = (ex.text or "").lower()
        for term in text_terms:
            term_norm = term.lower()
            if not term_norm:
                continue
            if term_norm == "gold":
                if ("gold" in text_norm) and (("label" in text_norm) or ("annotation" in text_norm)):
                    _fail(ex.uid, "text contains suspicious gold-reference near label/annotation")
            elif term_norm in text_norm:
                _fail(ex.uid, f"text contains suspicious term '{term}'")


def _normalize_example(example: InternalExample, *, idx: int) -> InternalExample:
    """Ensure required fields are present; set defaults without inference."""
    uid = example.uid or f"ex{idx:05d}"
    text = example.text or ""
    if not example.uid:
        print(f"[warn] example idx={idx} missing uid; assigned {uid}", file=sys.stderr)
    if not example.text:
        print(f"[warn] example uid={uid} has empty text", file=sys.stderr)
    case_type = example.case_type or "unknown"
    split = example.split or "unknown"
    language_code = example.language_code or "unknown"
    domain_id = example.domain_id or "unknown"
    if not example.case_type:
        print(f"[warn] example uid={uid} missing case_type; defaulting to 'unknown'", file=sys.stderr)
    if not example.split:
        print(f"[warn] example uid={uid} missing split; defaulting to 'unknown'", file=sys.stderr)
    if not example.language_code or example.language_code == "unknown":
        print(f"[warn] example uid={uid} missing language_code; defaulting to 'unknown'", file=sys.stderr)
    if not example.domain_id or example.domain_id == "unknown":
        print(f"[warn] example uid={uid} missing domain_id; defaulting to 'unknown'", file=sys.stderr)
    return InternalExample(
        uid=uid,
        text=text,
        case_type=case_type,
        split=split,
        label=example.label,
        target=example.target,
        span=example.span,
        metadata=example.metadata,
        language_code=language_code,
        domain_id=domain_id,
    )


def _inflate_call_metadata(trace_obj: Any) -> None:
    """Populate call_metadata from notes JSON if available."""
    if getattr(trace_obj, "call_metadata", None):
        return
    notes = getattr(trace_obj, "notes", None)
    if not notes:
        return
    try:
        trace_obj.call_metadata = json.loads(notes)
    except Exception:
        trace_obj.call_metadata = None


def _attach_case_meta(
    result: Any,
    example: InternalExample,
    cfg_hash: str,
    manifest_path: Path,
    *,
    latency_sec: float | None = None,
    backbone_model_id: Optional[str] = None,
) -> None:
    """Augment FinalOutputSchema with integrity fields and propagate to traces."""
    case_type = example.case_type or "unknown"
    split = example.split or "unknown"
    uid = example.uid
    meta = result.meta or {}
    meta.update(
        {
            "case_type": case_type,
            "split": split,
            "uid": uid,
            "language_code": example.language_code or "unknown",
            "domain_id": example.domain_id or "unknown",
            "cfg_hash": cfg_hash,
            "manifest_path": str(manifest_path),
            "backbone_model_id": backbone_model_id,
            "latency_ms": int(latency_sec * 1000) if latency_sec is not None else None,
        }
    )
    result.meta = meta
    for tr in getattr(result, "process_trace", []) or []:
        tr.case_type = case_type
        tr.split = split
        tr.uid = uid
        tr.language_code = example.language_code or "unknown"
        tr.domain_id = example.domain_id or "unknown"
        tr.input_hash = tr.input_hash or _sha256_text(example.text)
        _inflate_call_metadata(tr)


def _span_out_of_range(text: str, obj: Any) -> bool:
    """Recursively detect spans that fall outside text boundaries."""
    max_len = len(text or "")

    def _walk(node: Any) -> bool:
        if isinstance(node, dict):
            if {"start", "end"} <= set(node.keys()):
                try:
                    start = int(float(node.get("start", -1)))
                    end = int(float(node.get("end", -1)))
                except Exception:
                    start, end = -1, -1
                if start < 0 or end < 0 or end > max_len or start >= end:
                    return True
            for v in node.values():
                if _walk(v):
                    return True
        elif isinstance(node, (list, tuple)):
            for v in node:
                if _walk(v):
                    return True
        return False

    return _walk(obj)


def _check_case_integrity(result: Any, example: InternalExample, *, strict: bool = False) -> None:
    expected = example.case_type or "unknown"
    missing = []
    for tr in getattr(result, "process_trace", []) or []:
        if (getattr(tr, "case_type", None) or "unknown") != expected:
            missing.append(getattr(tr, "stage", "unknown"))
    if missing:
        msg = f"[case_integrity] uid={example.uid} case_type expected '{expected}' missing/mismatched in stages={missing}"
        if strict:
            raise RuntimeError(msg)
        print(f"[warn] {msg}", file=sys.stderr)


def _prompt_hash_from_versions(prompt_versions: Dict[str, Optional[str]]) -> Optional[str]:
    """Single hash for trace: canonical JSON of prompt name -> sha256."""
    if not prompt_versions:
        return None
    canonical = json.dumps({k: v for k, v in sorted(prompt_versions.items()) if v}, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_case_trace(
    example: InternalExample,
    result: Any,
    *,
    run_id: str,
    manifest_path: Path,
    cfg_hash: str,
    latency_sec: float,
    prompt_versions: Dict[str, Optional[str]],
) -> Dict[str, Any]:
    stages = [tr.model_dump() if hasattr(tr, "model_dump") else tr for tr in getattr(result, "process_trace", [])]
    return {
        "uid": example.uid,
        "case_type": example.case_type,
        "split": example.split,
        "language_code": example.language_code,
        "domain_id": example.domain_id,
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "cfg_hash": cfg_hash,
        "input_hash": _sha256_text(example.text),
        "input_preview": example.text[:120],
        "runner": result.meta.get("mode"),
        "stages": stages,
        "prompt_hash": _prompt_hash_from_versions(prompt_versions),
        "analysis_flags": getattr(result, "analysis_flags", None).model_dump() if getattr(result, "analysis_flags", None) else None,
        "final_result": getattr(result, "final_result", None).model_dump() if getattr(result, "final_result", None) else None,
        "meta": result.meta,
        "latency_sec": latency_sec,
        "prompt_versions": prompt_versions,
        "demo_uids": result.meta.get("demo_uids") if isinstance(result.meta, dict) else [],
        "demo_k": result.meta.get("demo_k") if isinstance(result.meta, dict) else None,
        "demo_seed": result.meta.get("demo_seed") if isinstance(result.meta, dict) else None,
    }


def _infer_run_purpose(cfg: Dict[str, Any], cfg_path: str) -> str:
    """
    Determine run purpose from config or infer from config path basename.
    Valid purposes: smoke, sanity, paper, dev.
    """
    # A) Prefer explicit config key if present
    explicit = cfg.get("run_purpose")
    if explicit and explicit in ("smoke", "sanity", "paper", "dev"):
        return explicit

    # B) Infer from config path basename
    base = Path(cfg_path).stem.lower()
    if "smoke" in base:
        return "smoke"
    if "sanity" in base:
        return "sanity"

    # Default to dev for unspecified runs
    return "dev"


def _resolve_eval_gold_path(
    path_str: Optional[str],
    data_cfg: Dict[str, Any],
    resolved_paths: Dict[str, str],
) -> Optional[Path]:
    """Resolve eval gold JSONL path (relative to dataset_root or absolute). Return None if path_str empty or file missing."""
    if not path_str or not isinstance(path_str, str):
        return None
    p = Path(path_str)
    if not p.is_absolute():
        root = data_cfg.get("dataset_root")
        if root:
            p = Path(root) / p
        p = p.resolve()
    if not p.exists():
        return None
    return p


def _load_eval_gold(
    cfg: Dict[str, Any],
    data_cfg: Dict[str, Any],
    resolved_paths: Dict[str, str],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load uid -> gold_tuples from eval.gold_valid_jsonl and eval.gold_test_jsonl.
    Accepts gold_tuples (preferred) or gold_triplets (backward compat: opinion_term.term → aspect_term).
    Returns dict uid -> list of normalized gold dicts {aspect_ref, aspect_term, polarity}.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    eval_cfg = cfg.get("eval") or {}
    for key in ("gold_valid_jsonl", "gold_test_jsonl"):
        path_str = eval_cfg.get(key)
        path = _resolve_eval_gold_path(path_str, data_cfg, resolved_paths)
        if path is None:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            uid = row.get("uid") or row.get("text_id") or row.get("id")
            if not uid:
                continue
            normalized, _ = gold_row_to_tuples(row)
            if normalized:
                out[str(uid)] = normalized
    return out


def _compute_split_files(data_cfg: Dict[str, Any], resolved_paths: Dict[str, str]) -> Dict[str, Any]:
    """
    Compute split_files dict and check if all splits point to the same file.
    Returns: {train, valid, test, all_same: bool}
    """
    fmt = data_cfg.get("input_format", "csv")

    # Extract split file paths based on format
    split_files = {"train": None, "valid": None, "test": None}

    if fmt in ("csv", "nikluge_sa_2022"):
        split_files["train"] = resolved_paths.get("train_file") or data_cfg.get("train_file")
        split_files["valid"] = resolved_paths.get("valid_file") or data_cfg.get("valid_file")
        split_files["test"] = resolved_paths.get("test_file") or data_cfg.get("test_file")
    elif fmt == "json_internal":
        split_files["train"] = resolved_paths.get("json_dir_train") or data_cfg.get("json_dir_train")
        split_files["valid"] = resolved_paths.get("json_dir_valid") or data_cfg.get("json_dir_valid")
        split_files["test"] = resolved_paths.get("json_dir_test") or data_cfg.get("json_dir_test")

    # Check if all splits are the same (potential smoke/debug run)
    paths = [split_files.get(s) for s in ("train", "valid", "test") if split_files.get(s)]
    all_same = len(set(paths)) <= 1 if paths else False

    return {
        "train": split_files.get("train"),
        "valid": split_files.get("valid"),
        "test": split_files.get("test"),
        "all_same": all_same,
    }


def _write_manifest(
    *,
    run_id: str,
    mode: str,
    cfg: Dict[str, Any],
    cfg_path: str,
    data_cfg: Dict[str, Any],
    train_count: int,
    valid_count: int,
    test_count: int,
    backbone_cfg: Dict[str, Any],
    allowlist_path: Optional[str],
    allowlist_hash: Optional[str],
    prompt_versions: Dict[str, Optional[str]],
    cfg_hash: str,
    cfg_canonical: str,
    resolved_paths: Dict[str, str],
    allowed_roots: List[str],
    blocked_path_error: Optional[str] = None,
    manifest_paths: Iterable[Path],
    pattern_versions: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
    languages: Optional[Iterable[str]] = None,
    purpose: Optional[str] = None,
    integrity: Optional[Dict[str, Any]] = None,
    eval_paths: Optional[Dict[str, str]] = None,
    data_roles: Optional[Dict[str, Any]] = None,
    processing_splits: Optional[Sequence[str]] = None,
    processing_count: Optional[int] = None,
    splits_loaded: Optional[Sequence[str]] = None,
    debate_override_effective: Optional[Dict[str, Any]] = None,
) -> Path:
    # Compute split files info
    split_files_info = _compute_split_files(data_cfg, resolved_paths)

    manifest = {
        "manifest_version": 2,
        "run_id": f"{run_id}_{mode}",
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "git_commit": _git_commit_hash(),
        "config_path": cfg_path,
        "cfg_hash": cfg_hash,
        "cfg_canonical": cfg_canonical,
        "purpose": purpose or "dev",
        "backbone": {
            "provider": backbone_cfg.get("provider"),
            "model": backbone_cfg.get("model"),
            "temperature": cfg.get("pipeline", {}).get("temperature"),
            "max_tokens": cfg.get("pipeline", {}).get("max_tokens"),
            "seed": cfg.get("seed"),
        },
        "prompt_versions": prompt_versions,
        "patterns": pattern_versions or {},
        "languages": sorted(set(languages or [])),
        "allowlist": {"path": allowlist_path, "sha256": allowlist_hash, "version_id": allowlist_hash},
        "merging_rule": {"path": cfg.get("merging_rule"), "sha256": _sha256_file(cfg.get("merging_rule") or None)},
        "dataset": {
            "input_format": data_cfg.get("input_format", "csv"),
            "paths": {k: v for k, v in data_cfg.items() if isinstance(v, str) and ("file" in k or "path" in k or "dir" in k)},
            "split_counts": {"train": train_count, "valid": valid_count, "test": test_count},
            "resolved_paths": resolved_paths,
            "allowed_roots": allowed_roots,
            "split_files": {
                "train": split_files_info.get("train"),
                "valid": split_files_info.get("valid"),
                "test": split_files_info.get("test"),
            },
            "split_files_all_same": split_files_info.get("all_same", False),
            "processing_splits": list(processing_splits) if processing_splits is not None else None,
            "processing_count": processing_count,
            "splits_loaded": list(splits_loaded) if splits_loaded else None,
        },
        "mode": mode,
        "blocked_path_error": blocked_path_error,
        "integrity": integrity or {},
    }
    if integrity is not None:
        manifest["integrity"] = integrity
    if isinstance(eval_paths, dict) and eval_paths:
        manifest["eval"] = eval_paths
    if isinstance(data_roles, dict) and data_roles:
        manifest["data_roles"] = data_roles
    if cfg.get("episodic_memory") is not None:
        manifest["episodic_memory"] = cfg["episodic_memory"]
    if debate_override_effective is not None:
        manifest["debate_override_effective"] = debate_override_effective

    # CR protocol: stamp conflict_mode and conflict_flags_ref_primary for reproducibility
    pipeline_cfg = cfg.get("pipeline") or {}
    if pipeline_cfg.get("protocol_mode") == "conflict_review_v1":
        conflict_mode = (pipeline_cfg.get("conflict_mode") or "primary_secondary").strip()
        manifest.setdefault("pipeline", {})["conflict_mode"] = conflict_mode
        # ref primary only (no term fallback) = true; ref+term = false
        manifest["conflict_flags_ref_primary"] = conflict_mode == "primary"

    last_path = None
    for p in manifest_paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        last_path = p
    return last_path or Path()


def read_config(path: str) -> Dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_debate_override_effective(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Resolve effective debate override config for manifest (profile_id, thresholds, source).
    Returns None if override is disabled or not configured.
    """
    pipeline = cfg.get("pipeline") or {}
    if not pipeline.get("enable_debate_override", True):
        return None
    override_cfg = pipeline.get("debate_override")
    override_profile = cfg.get("override_profile") or pipeline.get("override_profile")
    if isinstance(override_cfg, dict) and override_cfg:
        effective = {k: v for k, v in override_cfg.items() if k not in ("profiles", "default_profile")}
        if not effective:
            effective = {"min_total": 1.6, "min_margin": 0.8, "min_target_conf": 0.7, "l3_conservative": True, "ev_threshold": 0.5}
        return {
            "override_profile_id": override_profile,
            "min_total": float(effective.get("min_total", 1.6)),
            "min_margin": float(effective.get("min_margin", 0.8)),
            "min_target_conf": float(effective.get("min_target_conf", 0.7)),
            "l3_conservative": effective.get("l3_conservative", True),
            "ev_threshold": float(effective.get("ev_threshold", 0.5)),
            "source": "yaml_override",
        }
    cfg_path = Path("experiments") / "configs" / "debate_override_thresholds.json"
    if not cfg_path.exists():
        return {"override_profile_id": None, "min_total": 1.6, "min_margin": 0.8, "min_target_conf": 0.7, "l3_conservative": True, "ev_threshold": 0.5, "source": "code_default"}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {"override_profile_id": None, "min_total": 1.6, "min_margin": 0.8, "min_target_conf": 0.7, "l3_conservative": True, "ev_threshold": 0.5, "source": "code_default"}
    if isinstance(data.get("profiles"), dict):
        profile_id = override_profile or data.get("default_profile") or "t0"
        profile = data["profiles"].get(profile_id) or data["profiles"].get("t0", {})
        if isinstance(profile, dict):
            return {
                "override_profile_id": profile_id,
                "min_total": float(profile.get("min_total", 1.6)),
                "min_margin": float(profile.get("min_margin", 0.8)),
                "min_target_conf": float(profile.get("min_target_conf", 0.7)),
                "l3_conservative": profile.get("l3_conservative", True),
                "ev_threshold": float(profile.get("ev_threshold", 0.5)),
                "source": "json_profile",
            }
    if isinstance(data, dict) and any(k in data for k in ("min_total", "min_margin")):
        flat = {k: v for k, v in data.items() if k not in ("profiles", "default_profile")}
        return {
            "override_profile_id": None,
            "min_total": float(flat.get("min_total", 1.6)),
            "min_margin": float(flat.get("min_margin", 0.8)),
            "min_target_conf": float(flat.get("min_target_conf", 0.7)),
            "l3_conservative": flat.get("l3_conservative", True),
            "ev_threshold": float(flat.get("ev_threshold", 0.5)),
            "source": "json_default",
        }
    return {"override_profile_id": None, "min_total": 1.6, "min_margin": 0.8, "min_target_conf": 0.7, "l3_conservative": True, "ev_threshold": 0.5, "source": "code_default"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="experiments/configs/default.yaml")
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--mode", type=str, choices=["proposed", "bl1", "bl2", "bl3", "all"], default=None, help="Pipeline mode (CLI overrides config/env).")
    parser.add_argument("--strict_config", action="store_true", help="Fail if pipeline.debate_override is set (YAML override); protects experiment reproducibility.")
    args = parser.parse_args()

    cfg_path = args.config
    cfg = read_config(cfg_path)

    # Optional: warn / fail when YAML override is in use (JSON default ignored)
    pipeline = cfg.get("pipeline") or {}
    yaml_override = isinstance(pipeline.get("debate_override"), dict) and bool(pipeline.get("debate_override"))
    if yaml_override and pipeline.get("enable_debate_override", True):
        print("\n" + "!" * 60, file=sys.stderr)
        print("  [WARN] pipeline.debate_override is set: JSON default values are IGNORED.", file=sys.stderr)
        print("  Effective thresholds come from YAML. For t0/t1/t2 comparison use override_profile instead.", file=sys.stderr)
        print("!" * 60 + "\n", file=sys.stderr)
        if getattr(args, "strict_config", False):
            blocked_error = "strict_config: pipeline.debate_override is set; aborting for reproducibility. Use override_profile (t0/t1/t2) instead."
            print(blocked_error, file=sys.stderr)
            raise RuntimeError(blocked_error)
    # CLI --run-id overrides config so distinct runs (e.g. v2) do not overwrite the same dir
    run_id = args.run_id or cfg.get("run_id") or "run"
    mode = resolve_run_mode(args.mode, os.getenv("RUN_MODE"), cfg.get("run_mode") or cfg.get("mode"))
    backbone_cfg = cfg.get("backbone", {})
    backbone = BackboneClient(provider=backbone_cfg.get("provider"), model=backbone_cfg.get("model"))

    blocked_error = None
    resolved_data_cfg = cfg["data"]
    resolved_paths: Dict[str, str] = {}
    allowed_roots: List[str] = []
    pattern_versions: Dict[str, Dict[str, Optional[str]]] = {}
    try:
        resolved_data_cfg, resolved_paths, allowed_roots = resolve_dataset_paths(cfg["data"])
        # Compute processing_splits and splits_to_load before load_datasets (eval-only: load valid only)
        FILE_KEY_TO_SPLIT = {"train_file": "train", "valid_file": "valid", "test_file": "test"}
        data_roles_defaults = {
            "demo_pool": ["train"],
            "tuning_pool": [],
            "report_set": ["valid"],
            "blind_set": ["test"],
            "report_sources": None,
            "blind_sources": None,
        }
        data_roles = {**data_roles_defaults, **(cfg.get("data_roles") or {})}
        if data_roles.get("report_sources") is None:
            data_roles["report_sources"] = None
        if data_roles.get("blind_sources") is None:
            data_roles["blind_sources"] = None
        demo_cfg = cfg.get("demo") or {}
        demo_k = int(demo_cfg.get("k", 0))
        demo_seed = int(demo_cfg.get("seed", 42))
        demo_enabled_for = set(demo_cfg.get("enabled_for") or [])
        force_proposed = bool(demo_cfg.get("force_for_proposed", False))
        report_src = data_roles.get("report_sources")
        blind_src = data_roles.get("blind_sources")
        if report_src is not None or blind_src is not None:
            report_split_names = {FILE_KEY_TO_SPLIT[k] for k in (report_src or []) if k in FILE_KEY_TO_SPLIT}
            blind_split_names = {FILE_KEY_TO_SPLIT[k] for k in (blind_src or []) if k in FILE_KEY_TO_SPLIT}
            processing_splits_set = report_split_names | blind_split_names
        else:
            processing_splits_set = set(data_roles.get("report_set", ["valid"])) | set(data_roles.get("blind_set", []))
        processing_splits = sorted(processing_splits_set)
        eval_splits = processing_splits_set
        run_purpose = _infer_run_purpose(cfg, cfg_path)
        demo_pool_splits = set(data_roles.get("demo_pool", ["train"]))
        splits_to_load = processing_splits_set if demo_k == 0 else (processing_splits_set | demo_pool_splits)
        train, valid, test = load_datasets(resolved_data_cfg, splits_to_load=splits_to_load)
    except BlockedDatasetPathError as e:
        blocked_error = str(e)
        train, valid, test = [], [], []
        data_roles = cfg.get("data_roles") or {}
        processing_splits = []
        processing_splits_set = set()
        eval_splits = set()
        splits_to_load = None
        run_purpose = "dev"
        demo_k = 0
        demo_cfg = cfg.get("demo") or {}
        demo_seed = 42
        demo_enabled_for = set()
        force_proposed = False

    leakage_guard_enabled = bool(cfg.get("pipeline", {}).get("leakage_guard", True))
    if leakage_guard_enabled:
        for split_name, split_examples in (("train", train), ("valid", valid), ("test", test)):
            _enforce_leakage_guard(
                split_examples,
                split=split_name,
                source_path=_resolve_split_source_path(resolved_data_cfg, split_name),
            )
    all_loaded = _flatten_examples(train, valid, test)
    if not all_loaded:
        raise ValueError("No examples found in any split (train/valid/test).")
    language_codes = {ex.language_code or "unknown" for ex in all_loaded}
    for lang in sorted(language_codes):
        _, path, sha = load_patterns(lang)
        if path and path.exists():
            pattern_versions[lang] = {"path": str(path), "sha256": sha}

    # demo_pool from loaded splits; used only when demo.k>0 for sampling
    demo_pool_splits = set(data_roles.get("demo_pool", ["train"]))
    demo_pool = [ex for ex in (list(train) + list(valid) + list(test)) if ex.split in demo_pool_splits]
    demo_sampler = DemoSampler(demo_pool)

    # Eval gold (optional): load gold_tuples by uid for scorecard injection
    uid_to_gold: Dict[str, List[Dict[str, Any]]] = _load_eval_gold(cfg, resolved_data_cfg, resolved_paths)
    if uid_to_gold:
        print(f"Eval gold: loaded gold_tuples for {len(uid_to_gold)} uids (gold_valid_jsonl / gold_test_jsonl)")
    eval_paths_for_manifest: Dict[str, str] = {}
    if cfg.get("eval"):
        for key in ("gold_valid_jsonl", "gold_test_jsonl"):
            path = _resolve_eval_gold_path(
                cfg["eval"].get(key), resolved_data_cfg, resolved_paths
            )
            if path is not None:
                eval_paths_for_manifest[key] = str(path)

    # Fail-fast: paper + demo.k=0 must not process train
    if run_purpose == "paper" and demo_k == 0 and "train" in processing_splits_set:
        raise RuntimeError(
            "[fail-fast] run_purpose=paper and demo.k=0 but processing_splits contains 'train'. "
            "Policy P1: paper runs are eval-only (valid/test)."
        )

    # Build examples for the inference loop from processing_splits only (no train in loop when paper + demo.k=0)
    examples = _examples_from_splits(train, valid, test, processing_splits)
    if not examples:
        raise ValueError("No examples in processing_splits; check report_sources/blind_sources or report_set/blind_set.")
    eval_uid_set = {ex.uid for ex in examples}
    eval_hashes = compute_eval_hashes(examples, eval_splits)

    cfg_hash, cfg_canonical = _hash_cfg(cfg)
    prompt_versions = _prompt_hashes()
    allow_terms, allow_hash = _load_allow_terms(cfg.get("aspect_allowlist"))
    strict_integrity = bool(cfg.get("pipeline", {}).get("strict_integrity", False))

    modes = ["proposed", "bl1", "bl2", "bl3"] if mode == "all" else [mode]

    for m in modes:
        run_id_mode = f"{run_id}_{m}"
        pipeline_cfg = dict(cfg.get("pipeline") or {})
        if cfg.get("override_profile") is not None:
            pipeline_cfg["override_profile"] = cfg["override_profile"]
        # memory.enable + memory.mode (advisory|silent) → episodic_memory.condition (C1/C2/C2_silent)
        if cfg.get("memory") and isinstance(cfg.get("memory"), dict):
            enable = cfg["memory"].get("enable", False)
            mode = (cfg["memory"].get("mode") or "advisory").strip().lower()
            cond = "C1" if not enable else ("C2" if mode == "advisory" else "C2_silent")
            pipeline_cfg["episodic_memory"] = dict(cfg.get("episodic_memory") or {})
            pipeline_cfg["episodic_memory"]["condition"] = cond
            cfg["episodic_memory"] = pipeline_cfg["episodic_memory"]  # for manifest/integrity
        elif "episodic_memory" in cfg:
            pipeline_cfg["episodic_memory"] = cfg["episodic_memory"]
        # Run-scoped episodic store: store_path = results/<run_id_mode>/episodic_store.jsonl (SSOT, 메트릭 정합성 유지)
        if pipeline_cfg.get("episodic_memory") and isinstance(pipeline_cfg["episodic_memory"], dict):
            _base = cfg.get("output_dir")
            _run_out = (Path(_base) / run_id_mode) if _base else Path("results") / run_id_mode
            pipeline_cfg["episodic_memory"]["store_path"] = str(_run_out / "episodic_store.jsonl")
            # 실행마다 스토어 비우기: clear_store_at_run_start=true 시 run 시작 시 파일 truncate
            if pipeline_cfg["episodic_memory"].get("clear_store_at_run_start"):
                _store_path = pipeline_cfg["episodic_memory"].get("store_path")
                if _store_path:
                    _p = Path(_store_path)
                    _p.parent.mkdir(parents=True, exist_ok=True)
                    _p.write_text("")
        runner = make_runner(run_mode=m, backbone=backbone, config=pipeline_cfg, run_id=run_id_mode)

        # Demo enable/disable per mode
        demo_k_mode = demo_k
        if demo_enabled_for:
            if m not in demo_enabled_for:
                demo_k_mode = 0
        if m == "proposed" and not force_proposed and "proposed" not in demo_enabled_for:
            demo_k_mode = 0

        base_outdir = cfg.get("output_dir")
        outdir = Path(base_outdir) / run_id_mode if base_outdir else Path(f"results/{run_id_mode}")
        outdir.mkdir(parents=True, exist_ok=True)
        report_dir = Path("experiments/reports") / run_id_mode

        # Run-start log: loaded counts, processing_splits, processing_count, policy
        print(
            f"[{m}] run start | loaded counts train={len(train)} valid={len(valid)} test={len(test)} | "
            f"processing_splits={processing_splits} | processing_count={len(examples)}"
        )
        if run_purpose == "paper":
            print(f"[{m}] policy P1: paper is eval only (valid/test); train not in inference loop when demo.k=0")

        # Prepare integrity tracking dict (demo overlap removal count added later)
        integrity_info: Dict[str, Any] = {}

        manifest_path = _write_manifest(
            run_id=run_id,
            mode=m,
            cfg=cfg,
            cfg_path=cfg_path,
            data_cfg=resolved_data_cfg,
            train_count=len(train),
            valid_count=len(valid),
            test_count=len(test),
            backbone_cfg=backbone_cfg,
            allowlist_path=cfg.get("aspect_allowlist"),
            allowlist_hash=allow_hash,
            prompt_versions=prompt_versions,
            cfg_hash=cfg_hash,
            cfg_canonical=cfg_canonical,
            resolved_paths=resolved_paths,
            manifest_paths=[outdir / "manifest.json", report_dir / "manifest.json"],
            allowed_roots=allowed_roots,
            blocked_path_error=blocked_error,
            pattern_versions=pattern_versions,
            languages=language_codes,
            purpose=run_purpose,
            integrity=integrity_info,
            eval_paths=eval_paths_for_manifest if eval_paths_for_manifest else None,
            data_roles=data_roles,
            processing_splits=processing_splits,
            processing_count=len(examples),
            splits_loaded=list(splits_to_load) if splits_to_load else None,
            debate_override_effective=_resolve_debate_override_effective(cfg),
        )

        if blocked_error:
            # Fail-fast after logging manifest
            raise RuntimeError(blocked_error)

        output_path = outdir / "outputs.jsonl"
        trace_path = outdir / "traces.jsonl"
        scorecard_path = outdir / "scorecards.jsonl"

        # Enable hash-based demo filtering for paper runs (default on), optional for smoke/sanity
        enable_demo_hash_filter = run_purpose == "paper" or cfg.get("demo", {}).get("hash_filter", False)
        demo_forbid_hashes = eval_hashes if enable_demo_hash_filter else None

        # Track demo exclusion stats for integrity logging
        total_demo_overlap_removed = 0
        missing_label_count = 0  # neutral ≠ missing: count samples where label was missing (not defaulted to neutral)

        with output_path.open("w", encoding="utf-8", newline="\n") as f_out, trace_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as f_trace, scorecard_path.open("w", encoding="utf-8", newline="\n") as f_score:
            for idx, ex in enumerate(examples):
                normalized = _normalize_example(ex, idx=idx)
                demo_result = demo_sampler.sample_with_stats(
                    demo_k_mode, demo_seed, forbid_uids=eval_uid_set, forbid_hashes=demo_forbid_hashes
                )
                demo_examples = demo_result.demos
                total_demo_overlap_removed += demo_result.removed_by_hash
                demo_uids = [d.uid for d in demo_examples]
                demo_texts = [d.text for d in demo_examples]
                meta_aug = dict(normalized.metadata or {})
                meta_aug["demo_texts"] = demo_texts
                meta_aug["demo_uids"] = demo_uids
                normalized = InternalExample(
                    uid=normalized.uid,
                    text=normalized.text,
                    case_type=normalized.case_type,
                    split=normalized.split,
                    label=normalized.label,
                    target=normalized.target,
                    span=normalized.span,
                    metadata=meta_aug,
                )
                start = time.time()
                result = runner.run(normalized)
                latency = time.time() - start
                # attach demo info before meta propagation
                if isinstance(result.meta, dict):
                    result.meta["demo_uids"] = demo_uids
                    result.meta["demo_k"] = demo_k_mode
                    result.meta["demo_seed"] = demo_seed
                _attach_case_meta(
                    result,
                    normalized,
                    cfg_hash,
                    manifest_path,
                    latency_sec=latency,
                    backbone_model_id=backbone_cfg.get("model"),
                )
                # Profile for latency gate and scorecard: smoke | regression | paper_main
                profile = "smoke" if run_purpose == "smoke" else ("paper_main" if run_purpose == "paper" else "regression")
                if isinstance(result.meta, dict):
                    result.meta["profile"] = profile
                _check_case_integrity(result, normalized, strict=strict_integrity)

                span_flag = any(
                    _span_out_of_range(normalized.text, tr.output) for tr in getattr(result, "process_trace", []) or []
                )
                if isinstance(result.meta, dict):
                    result.meta["span_out_of_range"] = span_flag
                if span_flag and strict_integrity:
                    raise RuntimeError(f"[span_integrity] uid={normalized.uid} split={normalized.split} span out of range")

                payload = result.model_dump()
                # HF aux signal only (no impact on Validator/Moderator); append-only, toggleable
                pipeline_cfg = cfg.get("pipeline") or {}
                aux_hf_enabled = pipeline_cfg.get("aux_hf_enabled", False)
                aux_hf_checkpoint = pipeline_cfg.get("aux_hf_checkpoint") or ""
                if aux_hf_enabled and aux_hf_checkpoint and not (aux_hf_checkpoint.strip().startswith("llm:")):
                    _s1 = (payload.get("stage1_ate") or {}).get("label")
                    _s2 = (payload.get("final_result") or {}).get("label") or (payload.get("moderator") or {}).get("final_label")
                    _s1_missing = _s1 is None or (isinstance(_s1, str) and not _s1.strip())
                    _s2_missing = _s2 is None or (isinstance(_s2, str) and not _s2.strip())
                    if _s1_missing or _s2_missing:
                        missing_label_count += 1
                    stage1_final = _s1 if not _s1_missing else "missing"
                    stage2_final = _s2 if not _s2_missing else (stage1_final if stage1_final != "missing" else "missing")
                    aux_hf_id2label = pipeline_cfg.get("aux_hf_id2label")
                    if isinstance(aux_hf_id2label, list):
                        aux_hf_id2label = {i: str(v) for i, v in enumerate(aux_hf_id2label)}
                    hf_signal = build_hf_signal(
                        normalized.text,
                        aux_hf_checkpoint,
                        aux_hf_id2label,
                        stage1_final,
                        stage2_final,
                        model_id=pipeline_cfg.get("aux_hf_model_id"),
                    )
                    payload["aux_signals"] = {"hf": hf_signal} if hf_signal else {}
                else:
                    payload.setdefault("aux_signals", {})
                # Ensure final_aspects in both outputs.jsonl and scorecards: reconstruct from final_tuples when missing/empty
                fr = payload.get("final_result") or {}
                if fr.get("final_tuples") and not (fr.get("final_aspects") and len(fr.get("final_aspects") or [])):
                    payload.setdefault("final_result", {})["final_aspects"] = final_aspects_from_final_tuples(fr["final_tuples"])
                # Inject gold_tuples into outputs for compute_irr subset (implicit/negation) classification
                if uid_to_gold and normalized.uid in uid_to_gold:
                    payload.setdefault("inputs", {})["gold_tuples"] = uid_to_gold[normalized.uid]
                f_out.write(json.dumps(payload, ensure_ascii=False) + "\n")

                case_trace = _build_case_trace(
                    normalized,
                    result,
                    run_id=run_id_mode,
                    manifest_path=manifest_path,
                    cfg_hash=cfg_hash,
                    latency_sec=latency,
                    prompt_versions=prompt_versions,
                )
                f_trace.write(json.dumps(case_trace, ensure_ascii=False) + "\n")

                if isinstance(payload.get("meta"), dict) and "profile" not in payload["meta"]:
                    payload["meta"]["profile"] = "smoke" if run_purpose == "smoke" else ("paper_main" if run_purpose == "paper" else "regression")
                gold_injected = bool(uid_to_gold and normalized.uid in uid_to_gold)
                gold_path_str = eval_paths_for_manifest.get("gold_valid_jsonl") or eval_paths_for_manifest.get("gold_test_jsonl") or None
                meta_extra = {
                    "scorecard_source": "run_experiments",
                    "gold_injected": gold_injected,
                    "gold_path": gold_path_str,
                    "outputs_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                }
                scorecard = make_scorecard(payload, extra_allow=allow_terms, meta_extra=meta_extra)
                if gold_injected:
                    scorecard.setdefault("inputs", {})["gold_tuples"] = uid_to_gold[normalized.uid]
                meta = scorecard.get("meta", {})
                meta.update(
                    {
                        "run_id": run_id_mode,
                        "text_id": normalized.uid,
                        "case_type": normalized.case_type,
                        "split": normalized.split,
                        "language_code": normalized.language_code,
                        "domain_id": normalized.domain_id,
                        "manifest_path": str(manifest_path),
                        "cfg_hash": cfg_hash,
                        "backbone_model_id": result.meta.get("backbone_model_id") if isinstance(result.meta, dict) else None,
                        "latency_ms": result.meta.get("latency_ms") if isinstance(result.meta, dict) else None,
                        "demo_uids": result.meta.get("demo_uids") if isinstance(result.meta, dict) else demo_uids,
                        "demo_k": demo_k_mode,
                        "demo_seed": demo_seed,
                        "span_out_of_range": bool(result.meta.get("span_out_of_range")) if isinstance(result.meta, dict) else span_flag,
                    }
                )
                scorecard["meta"] = meta
                scorecard.setdefault("summary", {})
                scorecard["summary"]["span_out_of_range"] = bool(
                    result.meta.get("span_out_of_range") if isinstance(result.meta, dict) else span_flag
                )
                f_score.write(json.dumps(scorecard, ensure_ascii=False) + "\n")

        print(f"[{m}] Saved outputs to {output_path}")
        print(f"[{m}] Saved traces to {trace_path}")
        print(f"[{m}] Saved scorecards to {scorecard_path}")
        run_errors_path = cfg.get("pipeline", {}).get("errors_path") or default_errors_path(run_id_mode, m)
        print(f"Errors (if any) are logged to {run_errors_path}")

        # Update manifest with final integrity info (demo overlap counts, missing_label_count, forbid_hashes source)
        if total_demo_overlap_removed > 0 or enable_demo_hash_filter or missing_label_count > 0 or data_roles.get("report_sources") is not None or data_roles.get("blind_sources") is not None:
            try:
                primary_manifest = outdir / "manifest.json"
                if primary_manifest.exists():
                    manifest_data = json.loads(primary_manifest.read_text(encoding="utf-8"))
                    manifest_data.setdefault("integrity", {})
                    manifest_data["integrity"]["demo_overlap_removed"] = total_demo_overlap_removed
                    manifest_data["integrity"]["demo_hash_filter_enabled"] = enable_demo_hash_filter
                    manifest_data["integrity"]["missing_label_count"] = missing_label_count
                    if data_roles.get("report_sources") is not None or data_roles.get("blind_sources") is not None:
                        manifest_data["integrity"]["forbid_hashes_source"] = {
                            "report_sources": data_roles.get("report_sources"),
                            "blind_sources": data_roles.get("blind_sources"),
                        }
                    primary_manifest.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
                backup_manifest = report_dir / "manifest.json"
                if backup_manifest.exists():
                    backup_data = json.loads(backup_manifest.read_text(encoding="utf-8"))
                    backup_data.setdefault("integrity", {})
                    backup_data["integrity"]["demo_overlap_removed"] = total_demo_overlap_removed
                    backup_data["integrity"]["demo_hash_filter_enabled"] = enable_demo_hash_filter
                    backup_data["integrity"]["missing_label_count"] = missing_label_count
                    if data_roles.get("report_sources") is not None or data_roles.get("blind_sources") is not None:
                        backup_data["integrity"]["forbid_hashes_source"] = {
                            "report_sources": data_roles.get("report_sources"),
                            "blind_sources": data_roles.get("blind_sources"),
                        }
                    backup_manifest.write_text(json.dumps(backup_data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[warn] Failed to update manifest with integrity info: {e}", file=sys.stderr)

        # Integrity check (C1/C2/C2_silent): slot_present, memory_mode, rounds_equal
        try:
            em = cfg.get("episodic_memory")
            slot_present = True  # DEBATE_CONTEXT__MEMORY slot always present in pipeline (can be empty)
            memory_mode = "off"
            if isinstance(em, dict):
                cond = em.get("condition") or ""
                memory_mode = "on" if cond == "C2" else ("silent" if cond == "C2_silent" else "off")
            elif cfg.get("memory") and isinstance(cfg.get("memory"), dict):
                enable = cfg["memory"].get("enable", False)
                mode = (cfg["memory"].get("mode") or "advisory").strip().lower()
                memory_mode = "off" if not enable else ("on" if mode == "advisory" else "silent")
            rounds_equal = True  # TODO: set from per-sample debate round count comparison when available
            integrity_check = {
                "slot_present": slot_present,
                "memory_mode": memory_mode,
                "rounds_equal": rounds_equal,
            }
            (outdir / "integrity_check.json").write_text(
                json.dumps(integrity_check, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"[warn] Failed to write integrity_check.json: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
