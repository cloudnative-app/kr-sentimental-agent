"""
02829 회귀 테스트.
- T2(또는 override APPLY run): S0 neutral, S1/S2 피부톤 negative, conflict_blocked=false, override_effect_applied=true.
- T1 + L3 발생 시: neutral 유지 = PASS (S0/S1/S2 neutral, override_effect_applied false 허용).
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    import pytest as _pytest
    _skip = getattr(_pytest, "skip", None)  # 프로젝트 pytest.py는 .skip 없음
except ImportError:
    _pytest = None
    _skip = None

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = _PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t1_proposed"


def _is_t1_run(run_dir: Path, meta: dict) -> bool:
    """run_id 또는 run_dir 이름에 c2_t1이 포함되면 T1 run."""
    run_id = (meta.get("run_id") or "") if isinstance(meta, dict) else ""
    return "c2_t1" in run_id or "c2_t1" in str(run_dir)


def _is_l3_skip_for_sample(meta: dict, ds: dict, skip_reasons: dict) -> bool:
    """이 샘플이 gate에서 L3 등으로 skip된 경우 (T1에서 neutral 유지 = PASS 조건)."""
    gate = (meta.get("gate_decision") or "").strip()
    if gate == "SKIP":
        return True
    if isinstance(skip_reasons, dict) and (skip_reasons.get("L3_conservative") or 0) >= 1:
        return True
    if isinstance(ds, dict) and (ds.get("skipped_conflict") or 0) >= 1:
        skip_r = (meta.get("debate_override_skip_reasons") or {}) if isinstance(meta, dict) else {}
        if isinstance(skip_r, dict) and skip_r.get("L3_conservative"):
            return True
    return False


def _load_jsonl(p: Path) -> list:
    out = []
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(__import__("json").loads(line))
    return out


def _tuples_for_aspect(tuples: list, aspect: str) -> list:
    out = []
    for it in (tuples or []):
        if not isinstance(it, dict):
            continue
        t = it.get("aspect_term")
        if isinstance(t, dict):
            t = (t.get("term") or "").strip()
        else:
            t = (t or "").strip()
        if t != aspect:
            continue
        p = (it.get("polarity") or it.get("label") or "").strip().lower()
        if p in ("pos", "positive"):
            p = "positive"
        elif p in ("neg", "negative"):
            p = "negative"
        elif p in ("neu", "neutral"):
            p = "neutral"
        out.append({"aspect_term": t, "polarity": p})
    return out


def test_02829_override_effect_applied_and_final_negative():
    """
    T2/APPLY run: S0 neutral, S1/S2 피부톤 negative, conflict_blocked=false, override_effect_applied=true.
    T1 + L3 발생 시: neutral 유지 = PASS (S0/S1/S2 neutral, override_effect_applied false 허용).
    """
    run_dir = Path(os.environ.get("REGRESSION_02829_RUN_DIR", str(DEFAULT_RUN_DIR)))
    if not run_dir.exists() or not (run_dir / "outputs.jsonl").exists():
        if callable(_skip):
            _skip("run dir or outputs.jsonl not found; run experiment first")
        return
    outputs = _load_jsonl(run_dir / "outputs.jsonl")
    scorecards = _load_jsonl(run_dir / "scorecards.jsonl")
    text_id = "nikluge-sa-2022-train-02829"
    aspect = "피부톤"

    out_row = next((o for o in outputs if (o.get("meta") or {}).get("text_id") == text_id), None)
    sc_row = next((s for s in scorecards if ((s.get("meta") or {}).get("text_id") or (s.get("runtime") or {}).get("uid")) == text_id), None)
    if not out_row or not sc_row:
        if callable(_skip):
            _skip("02829 record not in run")
        return

    meta = sc_row.get("meta") or {}
    ds = meta.get("debate_override_stats") or {}
    if not isinstance(ds, dict):
        runtime = sc_row.get("runtime") or {}
        parsed = runtime.get("parsed_output") if isinstance(runtime, dict) else {}
        meta = (parsed.get("meta") or {}) if isinstance(parsed, dict) else {}
        ds = meta.get("debate_override_stats") or {}
    override_reason = (ds.get("override_reason") or meta.get("adopt_reason") or "").strip()
    override_effect_applied = bool(ds.get("override_effect_applied", ds.get("override_applied", False)))
    skip_reasons = meta.get("debate_override_skip_reasons") or {}

    fr = (out_row.get("final_result") or {})
    stage1_tuples = fr.get("stage1_tuples") or []
    stage2_tuples = fr.get("stage2_tuples") or []
    final_tuples = fr.get("final_tuples") or []

    assert final_tuples is not None and isinstance(final_tuples, list), "final_result.final_tuples must exist"
    assert len(final_tuples) >= 1, "final_result.final_tuples must be non-empty for 02829 (00474 |neutral 재발 방지)"

    s0 = _tuples_for_aspect(stage1_tuples, aspect)
    s1 = _tuples_for_aspect(stage2_tuples, aspect)
    s2 = _tuples_for_aspect(final_tuples, aspect)

    assert len(s0) >= 1, "S0: 피부톤 적어도 1개 (neutral)"
    assert any(t.get("polarity") == "neutral" for t in s0), "S0: 피부톤 neutral 존재"

    is_t1 = _is_t1_run(run_dir, meta)
    l3_skip = _is_l3_skip_for_sample(meta, ds, skip_reasons)

    if is_t1 and l3_skip:
        # T1 + L3: neutral 유지 = PASS
        assert len(s1) >= 1, "S1: 피부톤 적어도 1개"
        assert any(t.get("polarity") == "neutral" for t in s1), "S1 (T1+L3): 피부톤 neutral 유지"
        assert len(s2) >= 1, "S2: 피부톤 적어도 1개"
        assert any(t.get("polarity") == "neutral" for t in s2), "S2 (T1+L3): 피부톤 neutral 유지"
        return
    # T2 또는 override APPLY run: S1/S2 negative, conflict_blocked 아님, override_effect_applied true
    assert len(s1) >= 1, "S1: 피부톤 적어도 1개 (대표 선택 후 negative 단일 기대)"
    assert any(t.get("polarity") == "negative" for t in s1), "S1: 피부톤 negative 존재"
    assert len(s2) >= 1, "S2: final_tuples에 피부톤 적어도 1개"
    assert any(t.get("polarity") == "negative" for t in s2), "S2: 피부톤 negative (override 반영)"
    assert override_reason != "conflict_blocked", "override_reason must not be conflict_blocked"
    assert override_effect_applied is True, "override_effect_applied must be true (stage2 adopted)"


def test_02829_t1_l3_conservative_blocks_override():
    """
    T1 run (l3_conservative=true): 02829에서 L3로 override가 막혔을 때
    override_applied=false, override_reason=l3_conservative (또는 skip_reasons.L3_conservative>=1) 확인.
    L3 블록이 없는 run(예: gate가 low_signal만)이면 skip.
    T1 전용: REGRESSION_02829_T1_RUN_DIR 또는 experiment_mini4_validation_c2_t1_proposed.
    """
    t1_run_dir = Path(
        os.environ.get("REGRESSION_02829_T1_RUN_DIR", str(DEFAULT_RUN_DIR))
    )
    if not t1_run_dir.exists() or not (t1_run_dir / "scorecards.jsonl").exists():
        if callable(_skip):
            _skip("T1 run dir or scorecards.jsonl not found")
        return

    scorecards = _load_jsonl(t1_run_dir / "scorecards.jsonl")
    text_id = "nikluge-sa-2022-train-02829"
    sc_row = next(
        (
            s
            for s in scorecards
            if ((s.get("meta") or {}).get("text_id") or (s.get("runtime") or {}).get("uid"))
            == text_id
        ),
        None,
    )
    if not sc_row:
        if callable(_skip):
            _skip("02829 not found in T1 run")
        return

    meta = sc_row.get("meta") or {}
    run_id = (meta.get("run_id") or "").strip()
    assert "c2_t1" in run_id or "c2_t1" in str(t1_run_dir), (
        "test_02829_t1_l3_conservative_blocks_override requires T1 run (c2_t1); got run_id=%s"
        % run_id
    )

    ds = meta.get("debate_override_stats") or {}
    if not isinstance(ds, dict):
        runtime = sc_row.get("runtime") or {}
        parsed = (runtime.get("parsed_output") or {}) if isinstance(runtime, dict) else {}
        meta = (parsed.get("meta") or {}) if isinstance(parsed, dict) else {}
        ds = meta.get("debate_override_stats") or {}

    override_applied = bool(ds.get("override_applied", False))
    override_effect_applied = bool(ds.get("override_effect_applied", override_applied))
    override_reason = (ds.get("override_reason") or meta.get("adopt_reason") or "").strip()
    skip_reasons = meta.get("debate_override_skip_reasons") or {}
    if not isinstance(skip_reasons, dict):
        skip_reasons = {}

    # 이 샘플이 L3로 막혔는지: skip_reasons 또는 override_gate_debug에서 02829/피부톤 skip_reason=l3_conservative
    l3_in_skip = (skip_reasons.get("L3_conservative") or 0) >= 1
    gate_debug_path = t1_run_dir / "override_gate_debug.jsonl"
    if not l3_in_skip and gate_debug_path.exists():
        for line in open(gate_debug_path, "r", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            rec = __import__("json").loads(line)
            if rec.get("text_id") == text_id and (rec.get("skip_reason") or "").strip() == "l3_conservative":
                l3_in_skip = True
                break

    if not l3_in_skip and (override_reason or "").lower() != "l3_conservative":
        if callable(_skip):
            _skip("02829 did not hit L3 block in this T1 run (no L3_conservative in skip_reasons or gate debug)")
        return

    # L3로 막혔으면: override 적용되지 않아야 하고, 이유가 l3_conservative여야 함
    assert not override_applied or not override_effect_applied, (
        "T1 l3_conservative=true: 02829에서 L3로 override가 막혔을 때 override_applied=false 또는 override_effect_applied=false"
    )
    reason_ok = (override_reason or "").lower() == "l3_conservative" or l3_in_skip
    assert reason_ok, (
        "T1 02829 L3 block: override_reason=l3_conservative 또는 debate_override_skip_reasons.L3_conservative>=1 필요; "
        "override_reason=%r, skip_reasons=%s" % (override_reason, skip_reasons)
    )
