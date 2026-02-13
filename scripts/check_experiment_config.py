"""
실험 설정 사전 검사: paper 정책, fold 금지, seed 반복 시 demo_k=0.
Fold → Seed 반복 전환 후 fail-fast: fold 경로·seed 반복 시 demo_k>0 금지.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_yaml(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_fold_forbidden(cfg: dict) -> tuple[bool, str]:
    """Fold 관련 경로 사용 금지 (seed 반복 정책)."""
    data = cfg.get("data") or {}
    for key in ("train_file", "valid_file", "test_file"):
        val = data.get(key)
        if not val or not isinstance(val, str):
            continue
        if "fold" in val.lower():
            return False, f"data.{key} must not contain 'fold' (policy: fixed dataset, seed repeat); got {val}"
    return True, "no fold in data paths"


def check_seed_repeat_demo_zero(cfg: dict) -> tuple[bool, str]:
    """Seed 반복 모드일 때 demo.k는 0이어야 함."""
    exp = cfg.get("experiment") or {}
    repeat = exp.get("repeat") or {}
    if repeat.get("mode") != "seed":
        return True, "repeat mode is not seed, skip demo_k check"
    demo = cfg.get("demo") or {}
    k = int(demo.get("k", 0))
    if k > 0:
        return False, "experiment.repeat.mode=seed requires demo.k=0 (zero-shot); got demo.k=%s" % k
    return True, "seed repeat with demo.k=0 ok"


def check_paper_demo_inactive(cfg: dict) -> tuple[bool, str]:
    """Paper: demo는 완전 비활성. demo.k=0, enabled_for=[], force_for_proposed=false."""
    if cfg.get("run_purpose") != "paper":
        return True, "not paper, skip"
    demo = cfg.get("demo") or {}
    k = int(demo.get("k", 0))
    if k != 0:
        return False, "paper requires demo.k=0 (zero-shot only); got demo.k=%s" % k
    enabled = demo.get("enabled_for")
    if enabled is not None and enabled != []:
        return False, "paper requires demo.enabled_for=[] (demo disabled); got %s" % (enabled,)
    force = demo.get("force_for_proposed", False)
    if force is not False:
        return False, "paper requires demo.force_for_proposed=false; got %s" % force
    return True, "paper demo inactive (k=0, enabled_for=[], force_for_proposed=false)"


def _eval_splits_from_roles(roles: dict) -> set:
    """Derive eval split names from data_roles (report_sources/blind_sources or report_set/blind_set)."""
    report = roles.get("report_sources") or roles.get("report_set") or []
    blind = roles.get("blind_sources") or roles.get("blind_set") or []
    combined = set(report) | set(blind)

    def _norm(s):
        if isinstance(s, str) and s.endswith("_file"):
            return s[:-5]
        return s

    return {_norm(s) for s in combined if s}


def check_paper_valid_only(cfg: dict) -> tuple[bool, str]:
    """Paper: valid_file 필수, report_sources=[valid_file], test_file/blind 미사용."""
    if cfg.get("run_purpose") != "paper":
        return True, "not paper, skip"
    data = cfg.get("data") or {}
    if not data.get("valid_file"):
        return False, "paper requires data.valid_file"
    roles = cfg.get("data_roles") or {}
    if roles.get("report_sources") != ["valid_file"]:
        return False, "paper requires data_roles.report_sources exactly [\"valid_file\"]"
    if data.get("test_file"):
        return False, "paper must not set data.test_file"
    if (roles.get("blind_set") or []) != []:
        return False, "paper requires data_roles.blind_set [] or omitted"
    if roles.get("blind_sources") not in (None, []):
        return False, "paper requires data_roles.blind_sources [] or omitted"
    return True, "paper valid-only ok"


def run_checks(config_path: str, strict: bool) -> tuple[bool, list[str]]:
    path = Path(config_path)
    if not path.exists():
        return False, [f"ERROR: config not found: {config_path}"]
    cfg = load_yaml(config_path)
    messages = []

    ok, msg = check_fold_forbidden(cfg)
    messages.append(f"[fold_forbidden] {msg}")
    if not ok:
        messages.append("FAIL: fold in data paths (use fixed dataset + seed repeat).")

    ok2, msg2 = check_seed_repeat_demo_zero(cfg)
    messages.append(f"[seed_repeat_demo] {msg2}")
    if not ok2:
        messages.append("FAIL: seed repeat requires demo.k=0.")

    ok3, msg3 = check_paper_valid_only(cfg)
    messages.append(f"[paper_valid_only] {msg3}")
    if not ok3:
        messages.append("FAIL: paper valid-only policy violated.")

    ok4, msg4 = check_paper_demo_inactive(cfg)
    messages.append(f"[paper_demo_inactive] {msg4}")
    if not ok4:
        messages.append("FAIL: paper requires demo fully inactive (k=0, enabled_for=[], force_for_proposed=false).")

    all_ok = ok and ok2 and ok3 and ok4
    return all_ok, messages


def main() -> None:
    ap = argparse.ArgumentParser(description="Pre-run checks: no fold paths, seed repeat demo.k=0, paper valid-only")
    ap.add_argument("--config", required=True, help="Experiment config YAML path")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any failure")
    args = ap.parse_args()
    passed, messages = run_checks(args.config, args.strict)
    for m in messages:
        print(m)
    if not passed and args.strict:
        sys.exit(1)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
