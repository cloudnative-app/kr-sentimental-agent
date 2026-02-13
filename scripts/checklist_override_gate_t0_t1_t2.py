#!/usr/bin/env python3
"""
체크리스트: mini4 C2 T0/T1/T2 override gate 실험 결과 검토.

확인 항목:
1. override_applied_rate가 T1/T2에서 0이 아닌가?
2. skip_reason 분해에서 low_signal, action_ambiguity가 줄었는가?
3. total, margin 분포가 threshold 근처에 몰려 있었는가?
4. override 적용된 케이스만 모았을 때 conflict/L3가 개선되는가, 악화되는가?

Usage:
  python scripts/checklist_override_gate_t0_t1_t2.py --t0_dir results/experiment_mini4_validation_c2_t0_proposed --t1_dir ... --t2_dir ... --out reports/mini4_c2_t0_t1_t2_checklist.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_structural_metrics(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return dict(rows[0]) if rows else None


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _f(d: Optional[Dict[str, Any]], key: str, default: Any = None) -> Any:
    if d is None:
        return default
    v = d.get(key)
    return v if v is not None else default


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> int:
    if v is None:
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="T0/T1/T2 override gate checklist")
    ap.add_argument("--t0_dir", type=str, required=True, help="results/.../experiment_mini4_validation_c2_t0_proposed")
    ap.add_argument("--t1_dir", type=str, required=True, help="results/.../experiment_mini4_validation_c2_t1_proposed")
    ap.add_argument("--t2_dir", type=str, required=True, help="results/.../experiment_mini4_validation_c2_t2_proposed")
    ap.add_argument("--out", type=str, default="reports/mini4_c2_t0_t1_t2_checklist.md", help="Output markdown path")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    t0_dir = root / args.t0_dir
    t1_dir = root / args.t1_dir
    t2_dir = root / args.t2_dir
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _metrics_dir(d: Path) -> Path:
        return d / "derived" / "metrics" if (d / "derived" / "metrics").exists() else d

    struct_t0 = load_structural_metrics(_metrics_dir(t0_dir) / "structural_metrics.csv")
    struct_t1 = load_structural_metrics(_metrics_dir(t1_dir) / "structural_metrics.csv")
    struct_t2 = load_structural_metrics(_metrics_dir(t2_dir) / "structural_metrics.csv")

    gate_t0 = load_json(t0_dir / "override_gate_debug_summary.json")
    gate_t1 = load_json(t1_dir / "override_gate_debug_summary.json")
    gate_t2 = load_json(t2_dir / "override_gate_debug_summary.json")

    lines: list[str] = []
    lines.append("# Mini4 C2 T0/T1/T2 Override Gate 체크리스트")
    lines.append("")
    lines.append("같은 10샘플(seed 42)로 C2만 3조건 연속 실행.")
    lines.append("- **T0**: min_total=1.6, min_margin=0.8, min_target_conf=0.7, l3_conservative=true")
    lines.append("- **T1**: min_total=1.0, min_margin=0.5, min_target_conf=0.6, l3_conservative=true")
    lines.append("- **T2**: min_total=0.6, min_margin=0.3, min_target_conf=0.55, **l3_conservative=false**")
    lines.append("")

    # 1. override_applied_rate가 T1/T2에서 0이 아닌가?
    lines.append("## 1. override_applied_rate가 T1/T2에서 0이 아닌가?")
    lines.append("")
    r0 = _float(_f(struct_t0, "override_applied_rate"))
    r1 = _float(_f(struct_t1, "override_applied_rate"))
    r2 = _float(_f(struct_t2, "override_applied_rate"))
    n0 = _int(_f(struct_t0, "override_applied_n"))
    n1 = _int(_f(struct_t1, "override_applied_n"))
    n2 = _int(_f(struct_t2, "override_applied_n"))
    lines.append(f"| 조건 | override_applied_n | override_applied_rate |")
    lines.append(f"|------|--------------------|----------------------|")
    lines.append(f"| T0   | {n0} | {r0 if r0 is not None else 'N/A'} |")
    lines.append(f"| T1   | {n1} | {r1 if r1 is not None else 'N/A'} |")
    lines.append(f"| T2   | {n2} | {r2 if r2 is not None else 'N/A'} |")
    lines.append("")
    t1_ok = (r1 is not None and r1 > 0) or n1 > 0
    t2_ok = (r2 is not None and r2 > 0) or n2 > 0
    if t1_ok and t2_ok:
        lines.append("**Yes**: T1, T2에서 override_applied_rate > 0 (또는 override_applied_n > 0).")
    else:
        lines.append("**No**: T1 또는 T2에서 override 적용 샘플 없음.")
    if (r0 is not None and r0 == 0) and t1_ok and (r2 is not None and r2 > r1 if r1 else True):
        lines.append("→ **원인 = 게이트(역치/보수 규칙) 과다** 가능성 높음.")
    lines.append("")

    # 2. skip_reason 분해에서 low_signal, action_ambiguity가 줄었는가?
    lines.append("## 2. skip_reason 분해: low_signal, action_ambiguity가 줄었는가?")
    lines.append("")
    for label, gate in [("T0", gate_t0), ("T1", gate_t1), ("T2", gate_t2)]:
        if gate is None:
            lines.append(f"- **{label}**: override_gate_debug_summary.json 없음.")
            continue
        sc = gate.get("skip_reason_count") or {}
        sr = gate.get("skip_reason_rate") or {}
        low = sc.get("low_signal", 0)
        amb = sc.get("action_ambiguity", 0)
        l3 = sc.get("l3_conservative", 0)
        impl = sc.get("implicit_soft_only", 0)
        alr = sc.get("already_confident", 0)
        lines.append(f"- **{label}**: low_signal={low}, action_ambiguity={amb}, l3_conservative={l3}, implicit_soft_only={impl}, already_confident={alr}")
        lines.append(f"  - rate: {sr}")
    lines.append("")
    low0 = (gate_t0 or {}).get("skip_reason_count") or {}
    low1 = (gate_t1 or {}).get("skip_reason_count") or {}
    low2 = (gate_t2 or {}).get("skip_reason_count") or {}
    if low1.get("low_signal", 0) <= low0.get("low_signal", 0) and low2.get("low_signal", 0) <= low1.get("low_signal", 0):
        lines.append("**Yes**: low_signal T0→T1→T2 감소.")
    else:
        lines.append("**No** or N/A: low_signal 감소 아님 또는 summary 없음.")
    if low1.get("action_ambiguity", 0) <= low0.get("action_ambiguity", 0) and low2.get("action_ambiguity", 0) <= low1.get("action_ambiguity", 0):
        lines.append("**Yes**: action_ambiguity T0→T1→T2 감소.")
    else:
        lines.append("**No** or N/A: action_ambiguity 감소 아님 또는 summary 없음.")
    lines.append("")

    # 3. total, margin 분포가 threshold 근처에 몰려 있었는가?
    lines.append("## 3. total, margin 분포가 threshold 근처에 몰려 있었는가?")
    lines.append("")
    for label, gate in [("T0", gate_t0), ("T1", gate_t1), ("T2", gate_t2)]:
        if gate is None:
            lines.append(f"- **{label}**: (no summary)")
            continue
        total_dist = gate.get("total_dist") or {}
        margin_dist = gate.get("margin_dist") or {}
        near = gate.get("threshold_near_rate") or {}
        lines.append(f"- **{label}** total_dist: min={total_dist.get('min')}, mean={total_dist.get('mean')}, median={total_dist.get('median')}, p90={total_dist.get('p90')}, max={total_dist.get('max')}")
        lines.append(f"  margin_dist: min={margin_dist.get('min')}, mean={margin_dist.get('mean')}, median={margin_dist.get('median')}, p90={margin_dist.get('p90')}, max={margin_dist.get('max')}")
        lines.append(f"  threshold_near: total_near_rate={near.get('total_near_rate')}, margin_near_rate={near.get('margin_near_rate')}")
    lines.append("")
    lines.append("역치 근처 비율이 높으면: 점수 계산/매핑이 구조적으로 역치 직전에서 잘리기 쉬움.")
    lines.append("")

    # 4. override 적용된 케이스만: conflict/L3 개선 vs 악화
    lines.append("## 4. override 적용된 케이스만: conflict / L3 개선 vs 악화")
    lines.append("")
    lines.append("| 조건 | polarity_conflict_rate | polarity_conflict_rate_after_rep | severe_polarity_error_L3_rate | explicit_grounding_failure_rate |")
    lines.append("|------|------------------------|-----------------------------------|--------------------------------|----------------------------------|")
    for label, struct in [("T0", struct_t0), ("T1", struct_t1), ("T2", struct_t2)]:
        if struct is None:
            lines.append(f"| {label} | N/A | N/A | N/A | N/A |")
            continue
        pc = _f(struct, "polarity_conflict_rate")
        pcr = _f(struct, "polarity_conflict_rate_after_rep")
        sev = _f(struct, "severe_polarity_error_L3_rate")
        egf = _f(struct, "explicit_grounding_failure_rate")
        lines.append(f"| {label} | {pc} | {pcr} | {sev} | {egf} |")
    lines.append("")
    lines.append("Override 적용된 샘플만의 subset 메트릭은 aggregator에서 override_applied_* 로 제공:")
    lines.append("")
    lines.append("| 조건 | override_applied_n | override_success_rate | override_applied_negation_contrast_failure_rate | override_applied_unsupported_polarity_rate |")
    lines.append("|------|--------------------|------------------------|------------------------------------------------|---------------------------------------------|")
    for label, struct in [("T0", struct_t0), ("T1", struct_t1), ("T2", struct_t2)]:
        if struct is None:
            lines.append(f"| {label} | N/A | N/A | N/A | N/A |")
            continue
        napp = _f(struct, "override_applied_n")
        succ = _f(struct, "override_success_rate")
        neg = _f(struct, "override_applied_negation_contrast_failure_rate")
        uns = _f(struct, "override_applied_unsupported_polarity_rate")
        lines.append(f"| {label} | {napp} | {succ} | {neg} | {uns} |")
    lines.append("")
    lines.append("→ T1/T2에서 override 적용이 늘어나도 polarity_conflict_rate, severe_L3, explicit_grounding_failure가 크게 악화되지 않으면 역치 완화 가능.")
    lines.append("")

    # 요약
    lines.append("---")
    lines.append("## 요약")
    lines.append("")
    lines.append("1. **override_applied_rate T1/T2 > 0?** " + ("Yes" if (t1_ok and t2_ok) else "No"))
    lines.append("2. **skip_reason low_signal/action_ambiguity 감소?** (위 표 참고)")
    lines.append("3. **total/margin threshold 근처 몰림?** (threshold_near_rate 참고)")
    lines.append("4. **override 적용 시 conflict/L3 개선 vs 악화?** (위 표 참고)")
    lines.append("")
    lines.append("**3인(analyst/critic/empath) 구조**: critic neg + empath pos → total은 커질 수 있으나 margin 작아 action_ambiguity 다수. analyst 중립/보수 → total<1.6으로 low_signal 폭증. 현재 1.6/0.8은 다수 합의·한쪽 강승이어야만 적용이라 override 0도 자연스러움.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
