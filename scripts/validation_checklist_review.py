#!/usr/bin/env python3
"""
Validation checklist review (1–5): C1/C2 (and optional C3) run 결과를 읽어
Yes/No + evidence 형태로 체크리스트 검토 결과를 출력합니다.

Usage:
  python scripts/validation_checklist_review.py --c1_dir results/experiment_mini4_validation_c1_proposed --c2_dir results/experiment_mini4_validation_c2_proposed
  python scripts/validation_checklist_review.py --c1_dir ... --c2_dir ... --c3_dir ... --out reports/mini4_validation_checklist.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_metrics_csv(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return None
    return dict(rows[0]) if rows else None


def _final_tuples_from_output(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    fr = payload.get("final_result") or {}
    ft = fr.get("final_tuples")
    if ft and isinstance(ft, list):
        return ft
    fa = fr.get("final_aspects")
    if fa and isinstance(fa, list):
        out = []
        for it in fa:
            if isinstance(it, dict):
                t = it.get("aspect_term") or it.get("term") or ""
                if isinstance(t, dict):
                    t = t.get("term") or ""
                p = it.get("polarity") or "neutral"
                out.append({"aspect_term": t, "polarity": p})
            else:
                term = getattr(it, "aspect_term", None) or getattr(it, "term", None)
                pol = getattr(it, "polarity", None) or "neutral"
                out.append({"aspect_term": term or "", "polarity": pol or "neutral"})
        return out
    return []


def _debate_summary(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    debate = payload.get("debate") or {}
    if isinstance(debate, dict):
        return debate.get("summary") or debate
    return getattr(debate, "summary", None) or None


# --- Checklist 1: Sanity ---
def _check1_sanity_fixed(outputs_c1: List[Dict[str, Any]], outputs_c2: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    lines: List[str] = []
    all_ok = True

    for name, outputs in [("C1", outputs_c1), ("C2", outputs_c2)]:
        for i, pl in enumerate(outputs):
            ft = _final_tuples_from_output(pl)
            by_term: Dict[str, List[str]] = {}
            for t in ft:
                term = (t.get("aspect_term") or "").strip() if isinstance(t, dict) else ""
                pol = (t.get("polarity") or "neutral").strip() if isinstance(t, dict) else "neutral"
                by_term.setdefault(term, []).append(pol)
            dup = [k for k, v in by_term.items() if len(set(v)) > 1]
            if dup:
                all_ok = False
                lines.append(f"  [{name}] sample {i}: aspect_term에 복수 polarity 존재: {dup}")
    lines.append("  Yes: 모든 샘플에서 동일 aspect_term당 polarity 1개." if all_ok else "  No: 위 위반 샘플 존재.")

    has_null = False
    for outputs in (outputs_c1, outputs_c2):
        for pl in outputs:
            ft = _final_tuples_from_output(pl)
            for t in ft:
                term = t.get("aspect_term") if isinstance(t, dict) else None
                if term is None or (isinstance(term, str) and not (term or "").strip()):
                    has_null = True
                    break
    lines.append("  No: final_output에 aspect_term=null/빈 tuple 존재." if has_null else "  Yes: aspect_term=null tuple 없음.")

    c2_with_patch = 0
    for pl in outputs_c2:
        summary = _debate_summary(pl)
        if not summary or not isinstance(summary, dict):
            continue
        fp = summary.get("final_patch")
        if fp is not None and isinstance(fp, list):
            c2_with_patch += 1
    lines.append(f"  Yes: C2에서 debate_output이 final_patch(action list) 형태 존재 (샘플 수: {c2_with_patch})." if c2_with_patch >= 0 else "  No: final_patch 없음.")

    keys_c1 = set()
    keys_c2 = set()
    for pl in outputs_c1:
        keys_c1.update((pl.get("final_result") or {}).keys())
    for pl in outputs_c2:
        keys_c2.update((pl.get("final_result") or {}).keys())
    schema_ok = keys_c1 == keys_c2
    lines.append("  Yes: C1/C2 final_result 스키마 동일." if schema_ok else f"  No: C1 keys={keys_c1}, C2 keys={keys_c2}.")

    return ("PASS" if all_ok and not has_null and schema_ok else "FAIL", lines)


# --- Checklist 2: Metric alignment ---
def check2_metrics(metrics_c1: Optional[Dict[str, Any]], metrics_c2: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]:
    lines: List[str] = []
    if not metrics_c1 or not metrics_c2:
        return "SKIP", ["  N/A: structural_metrics 없음 (aggregator 먼저 실행)."]

    def _f(m: Optional[Dict[str, Any]], k: str) -> float:
        if not m:
            return float("nan")
        v = m.get(k)
        if v == "" or v is None:
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    pc_c1 = _f(metrics_c1, "polarity_conflict_rate_after_rep")
    if pc_c1 != pc_c1:
        pc_c1 = _f(metrics_c1, "polarity_conflict_rate")
    pc_c2 = _f(metrics_c2, "polarity_conflict_rate_after_rep")
    if pc_c2 != pc_c2:
        pc_c2 = _f(metrics_c2, "polarity_conflict_rate")

    c2_le_c1 = pc_c2 <= pc_c1 if (pc_c1 == pc_c1 and pc_c2 == pc_c2) else None
    lines.append(f"  polarity_conflict_rate: C1={pc_c1:.4f}, C2={pc_c2:.4f} → C2≤C1? {c2_le_c1}" if c2_le_c1 is not None else "  polarity_conflict_rate: N/A")
    if c2_le_c1 is False:
        lines.append("  → No: C2 > C1. 유형별 conflict 사례는 scorecards/triptych polarity_conflict_* 열 참고.")

    l3_c1 = _f(metrics_c1, "severe_polarity_error_L3_rate")
    l3_c2 = _f(metrics_c2, "severe_polarity_error_L3_rate")
    if l3_c1 == l3_c1 and l3_c2 == l3_c2:
        lines.append(f"  severe_polarity_error_L3_rate: C1={l3_c1:.4f}, C2={l3_c2:.4f} (감소 시 patch 기여, 증가 시 patch 오류 가능).")
    else:
        lines.append("  severe_polarity_error_L3_rate: N/A")

    ta_c1 = _f(metrics_c1, "tuple_agreement_rate")
    ta_c2 = _f(metrics_c2, "tuple_agreement_rate")
    if ta_c1 == ta_c1 and ta_c2 == ta_c2:
        lines.append(f"  tuple_agreement_rate: C1={ta_c1:.4f}, C2={ta_c2:.4f} (변화 시 토론이 불안정성 감소 해석 가능 여부 참고).")
    else:
        lines.append("  tuple_agreement_rate: N/A (single run이면 1.0 또는 N/A).")

    return ("PASS" if c2_le_c1 else "FAIL" if c2_le_c1 is False else "SKIP", lines)


# --- Checklist 3: Role separation ---
def check3_role_separation(metrics_c1: Optional[Dict[str, Any]], metrics_c2: Optional[Dict[str, Any]]) -> Tuple[str, List[str]]:
    lines: List[str] = []
    if not metrics_c2:
        return "SKIP", ["  N/A: C2 structural_metrics 없음."]

    def _f(m: Optional[Dict], k: str) -> float:
        if not m:
            return float("nan")
        v = m.get(k)
        if v is None or v == "":
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    rr = _f(metrics_c2, "validator_clear_rate") or _f(metrics_c2, "risk_resolution_rate")
    lines.append(f"  risk_resolution_rate (Validator flag 해결 비율): {rr:.4f}" if rr == rr else "  risk_resolution_rate: N/A")

    over_skip = _f(metrics_c2, "debate_override_skipped_conflict")
    over_app = _f(metrics_c2, "debate_override_applied")
    total = over_skip + over_app
    if total and total == total:
        no_override_rate = over_skip / (total or 1)
        lines.append(f"  debate NO_OVERRIDE( skipped_conflict ) 종료 비율: {no_override_rate:.4f} (skipped_conflict={over_skip}, applied={over_app})")
    else:
        lines.append("  debate_override_skipped_conflict / applied: N/A")

    lines.append("  Stage2 재분석 호출 횟수/수정 폭: C1 vs C2 비교는 drift_cause_* / stage2_adopted_but_no_change 등 참고.")

    return "PASS", lines


# --- Checklist 4: Ablation (C1 vs C2 vs C3) ---
def check4_ablation(
    metrics_c1: Optional[Dict[str, Any]],
    metrics_c2: Optional[Dict[str, Any]],
    metrics_c3: Optional[Dict[str, Any]],
) -> Tuple[str, List[str]]:
    lines: List[str] = []

    def _f(m: Optional[Dict], k: str) -> float:
        if not m:
            return float("nan")
        v = m.get(k)
        if v is None or v == "":
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    if metrics_c3 is None:
        lines.append("  N/A: C3 실행 없음. experiment_mini4_validation_c3.yaml 실행 후 재검토.")
        return "SKIP", lines

    pc1 = _f(metrics_c1, "polarity_conflict_rate_after_rep") or _f(metrics_c1, "polarity_conflict_rate")
    pc3 = _f(metrics_c3, "polarity_conflict_rate_after_rep") or _f(metrics_c3, "polarity_conflict_rate")
    pc2 = _f(metrics_c2, "polarity_conflict_rate_after_rep") or _f(metrics_c2, "polarity_conflict_rate")
    c3_lt_c1 = pc3 < pc1 if (pc1 == pc1 and pc3 == pc3) else None
    lines.append(f"  C3 polarity_conflict_rate: {pc3:.4f}, C1: {pc1:.4f} → C3 < C1 (메모리 단독 효과)? {c3_lt_c1}")
    c2_lt_c3 = pc2 < pc3 if (pc2 == pc2 and pc3 == pc3) else None
    lines.append(f"  C2 polarity_conflict_rate: {pc2:.4f}, C3: {pc3:.4f} → C2 < C3 (토론 순수 기여)? {c2_lt_c3}")

    mem_used = _f(metrics_c2, "memory_used_rate") or _f(metrics_c2, "drift_cause_memory_used_changed_n")
    over_app = _f(metrics_c2, "override_applied_n") or _f(metrics_c2, "debate_override_applied")
    lines.append(f"  C2 memory_used=true 샘플 중 debate patch 적용: override_applied_n 등 참고 (memory_used_rate / override_applied_n).")

    return "PASS" if (c3_lt_c1 or c2_lt_c3) else "FAIL" if (c3_lt_c1 is False or c2_lt_c3 is False) else "SKIP", lines


# --- Checklist 5: Memory flags, OPFB, gate, after_rep, gold ---
def check5_flags_and_gold(
    run_dirs: Dict[str, Path],
    metrics_c1: Optional[Dict[str, Any]],
    metrics_c2: Optional[Dict[str, Any]],
    triptych_c2_path: Optional[Path],
) -> Tuple[str, List[str]]:
    lines: List[str] = []
    c2_dir = run_dirs.get("C2")
    if not c2_dir or not c2_dir.exists():
        return "SKIP", ["  N/A: C2 run_dir 없음."]

    scorecards_c2 = load_jsonl(c2_dir / "scorecards.jsonl")
    # 5.1 C2만 exposed_to_debate True, prompt_injection_chars > 0
    n_c2_exposed = 0
    n_c2_injected = 0
    for r in scorecards_c2:
        mem = r.get("memory") or {}
        if mem.get("exposed_to_debate"):
            n_c2_exposed += 1
        if (mem.get("prompt_injection_chars") or 0) > 0:
            n_c2_injected += 1
    lines.append(f"  C2: exposed_to_debate True 샘플={n_c2_exposed}, prompt_injection_chars>0 샘플={n_c2_injected} (기대: C2만 해당).")

    # 5.2 OPFB: memory_blocked_episode_n / memory_blocked_advisory_n / memory_block_reason
    blocked_any = sum(1 for r in scorecards_c2 if (r.get("memory") or {}).get("memory_blocked_episode_n") or (r.get("memory") or {}).get("memory_blocked_advisory_n"))
    lines.append(f"  OPFB: blocked 발동 샘플 수={blocked_any} (memory_block_reason 확인).")

    # 5.3 Gate: injection_trigger_reason
    trigger_counts: Dict[str, int] = {}
    for r in scorecards_c2:
        reason = (r.get("memory") or {}).get("injection_trigger_reason") or ""
        if reason:
            trigger_counts[reason] = trigger_counts.get(reason, 0) + 1
    lines.append(f"  주입 트리거: injection_trigger_reason counts={trigger_counts}.")

    # 5.4 after_rep: structural_metrics에 tuple_f1_s2_raw, tuple_f1_s2_after_rep, polarity_conflict_rate_raw/after_rep
    if metrics_c2:
        has_raw = "tuple_f1_s2_raw" in metrics_c2 and metrics_c2.get("tuple_f1_s2_raw") not in (None, "", "N/A")
        has_rep = "tuple_f1_s2_after_rep" in metrics_c2 and metrics_c2.get("tuple_f1_s2_after_rep") not in (None, "", "N/A")
        lines.append(f"  after_rep 컬럼: tuple_f1_s2_raw={has_raw}, tuple_f1_s2_after_rep={has_rep}, polarity_conflict_rate_raw/after_rep 채워짐.")

    # 5.5 gold
    if metrics_c2:
        gold_av = metrics_c2.get("gold_available")
        n_gold = metrics_c2.get("N_gold_total") or metrics_c2.get("N_gold")
        f1 = metrics_c2.get("tuple_f1_s2")
        lines.append(f"  gold: gold_available={gold_av}, N_gold_total={n_gold}, tuple_f1_s2={f1} (N/A 아니어야 함).")
    n_with_gold = sum(1 for r in scorecards_c2 if (r.get("inputs") or {}).get("gold_tuples"))
    lines.append(f"  scorecards에 gold_tuples 있는 행 수={n_with_gold}.")

    return "PASS", lines


def main() -> None:
    ap = argparse.ArgumentParser(description="Validation checklist review (1–5)")
    ap.add_argument("--c1_dir", required=True, help="C1 run dir (e.g. results/experiment_mini4_validation_c1_proposed)")
    ap.add_argument("--c2_dir", required=True, help="C2 run dir")
    ap.add_argument("--c3_dir", default=None, help="Optional C3 run dir (ablation)")
    ap.add_argument("--c2_eval_only_dir", default=None, help="Optional C2_eval_only run dir (ablation)")
    ap.add_argument("--out", default=None, help="Output markdown path (default: stdout)")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    c1_dir = Path(args.c1_dir)
    c2_dir = Path(args.c2_dir)
    if not c1_dir.is_absolute():
        c1_dir = (root / c1_dir).resolve()
    if not c2_dir.is_absolute():
        c2_dir = (root / c2_dir).resolve()
    c3_dir = Path(args.c3_dir).resolve() if args.c3_dir else None
    if c3_dir and not c3_dir.is_absolute():
        c3_dir = (root / args.c3_dir).resolve()
    c2_eval_only_dir = Path(args.c2_eval_only_dir).resolve() if args.c2_eval_only_dir else None
    if c2_eval_only_dir and not c2_eval_only_dir.is_absolute():
        c2_eval_only_dir = (root / args.c2_eval_only_dir).resolve()

    run_dirs: Dict[str, Path] = {"C1": c1_dir, "C2": c2_dir}
    if c3_dir and c3_dir.exists():
        run_dirs["C3"] = c3_dir
    if c2_eval_only_dir and c2_eval_only_dir.exists():
        run_dirs["C2_eval_only"] = c2_eval_only_dir

    # Resolve metrics: run_dir/derived/metrics/structural_metrics.csv or run_dir/structural_metrics.csv
    def _metrics_dir(d: Path) -> Path:
        for sub in ("derived/metrics", "derived", ""):
            p = (d / sub).resolve() if sub else d
            if (p / "structural_metrics.csv").exists():
                return p
        return d

    metrics_c1 = load_metrics_csv(_metrics_dir(c1_dir) / "structural_metrics.csv")
    metrics_c2 = load_metrics_csv(_metrics_dir(c2_dir) / "structural_metrics.csv")
    metrics_c3 = load_metrics_csv(_metrics_dir(c3_dir) / "structural_metrics.csv") if c3_dir and c3_dir.exists() else None

    outputs_c1 = load_jsonl(c1_dir / "outputs.jsonl")
    outputs_c2 = load_jsonl(c2_dir / "outputs.jsonl")

    triptych_c2 = c2_dir / "derived" / "tables" / "triptych_table.tsv"
    if not triptych_c2.exists():
        triptych_c2 = c2_dir / "derived" / "tables" / "triptych_table.csv"

    report: List[str] = [
        "# Mini4 Validation Checklist Review",
        "",
        f"- C1: {c1_dir}",
        f"- C2: {c2_dir}",
        f"- C3: {c3_dir or 'N/A'}",
        f"- C2_eval_only: {c2_eval_only_dir or 'N/A'}",
        "",
        "---",
        "",
    ]

    # 1. Sanity
    status1, lines1 = _check1_sanity_fixed(outputs_c1, outputs_c2)
    report.append("## 1. Sanity Check")
    report.append("")
    report.extend(lines1)
    report.append(f"\n**Result: {status1}**\n")

    # 2. Metric alignment
    status2, lines2 = check2_metrics(metrics_c1, metrics_c2)
    report.append("## 2. Metric Alignment Check")
    report.append("")
    report.extend(lines2)
    report.append(f"\n**Result: {status2}**\n")

    # 3. Role separation
    status3, lines3 = check3_role_separation(metrics_c1, metrics_c2)
    report.append("## 3. Role Separation Check")
    report.append("")
    report.extend(lines3)
    report.append(f"\n**Result: {status3}**\n")

    # 4. Ablation
    status4, lines4 = check4_ablation(metrics_c1, metrics_c2, metrics_c3)
    report.append("## 4. Ablation Consistency Check (C1 vs C2 vs C3)")
    report.append("")
    report.extend(lines4)
    report.append(f"\n**Result: {status4}**\n")

    # 5. Memory flags, OPFB, gate, after_rep, gold
    status5, lines5 = check5_flags_and_gold(run_dirs, metrics_c1, metrics_c2, triptych_c2 if triptych_c2.exists() else None)
    report.append("## 5. Memory Flags / OPFB / Gate / after_rep / Gold")
    report.append("")
    report.extend(lines5)
    report.append(f"\n**Result: {status5}**\n")

    text = "\n".join(report)
    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = (root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"Wrote: {out_path}")
    else:
        print(text)


if __name__ == "__main__":
    main()
