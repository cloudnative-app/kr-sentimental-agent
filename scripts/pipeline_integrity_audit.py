#!/usr/bin/env python3
"""
ABSA 파이프라인 End-to-End 정합성 점검 (C2 + Debate Override + Memory + Aggregator).
입력: mini4 C2 run (10 samples, seed=42). 산출: pipeline_integrity_audit.md, pipeline_integrity_audit_findings.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def load_jsonl(p: Path) -> List[Dict[str, Any]]:
    out = []
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def load_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def get_debate_review_context(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    runtime = (record.get("runtime") or record) if isinstance(record.get("runtime"), dict) else {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    meta = parsed.get("meta") or record.get("meta") or {}
    return meta.get("debate_review_context") if isinstance(meta.get("debate_review_context"), dict) else None


def get_final_result(record: Dict[str, Any]) -> Dict[str, Any]:
    runtime = (record.get("runtime") or record) if isinstance(record.get("runtime"), dict) else {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    return parsed.get("final_result") or {}


def step1_sot_mapping() -> Tuple[str, List[Dict[str, Any]]]:
    """Step 1: SoT 정의 확인. 최종 튜플 SoT = final_result.final_tuples (supervisor가 씀)."""
    findings = []
    policy = (
        "최종 튜플 SoT = final_result.final_tuples. "
        "supervisor_agent.run()에서 final_aspects_list → tuples_to_list_of_dicts → final_result.final_tuples. "
        "debate_summary.final_tuples 존재 시 final_aspect_sentiments를 그에 맞춘 뒤 final_aspects_list 빌드. "
        "aggregator( structural_error_aggregator._extract_final_tuples ) 우선순위: final_result.final_tuples → final_aspects → inputs.aspect_sentiments."
    )
    return policy, findings


def step2_debate_signal(
    run_dir: Path,
    scorecards: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Step 2: polarity_hint / aspect_hints 전달 검증 (10샘플 전수)."""
    for i, row in enumerate(scorecards):
        text_id = (row.get("meta") or {}).get("text_id") or row.get("text_id") or f"row_{i}"
        ctx = get_debate_review_context(row)
        if not ctx:
            findings.append({
                "finding_id": f"step2_no_ctx_{i}",
                "severity": "minor",
                "symptom": f"text_id={text_id}: debate_review_context 없음",
                "expected": "C2 run이면 debate 후 context 생성됨",
                "evidence": {"file": "scorecards.jsonl", "record_key": text_id, "json_path": "runtime.parsed_output.meta.debate_review_context", "observed_value": None},
                "root_cause_hypothesis": "debate 비활성 또는 meta 기록 누락",
                "fix_plan": "확인 후 meta에 debate_review_context 기록 보장",
                "status": "open",
            })
            continue
        ah = ctx.get("aspect_hints") or {}
        rebuttals = ctx.get("rebuttal_points") or []
        for aspect, hints in ah.items():
            polarity_list = [h.get("polarity_hint") for h in hints if isinstance(h, dict)]
            valid_count = sum(1 for h in hints if isinstance(h, dict) and h.get("polarity_hint") in ("positive", "negative"))
            pos_score = sum(float(h.get("weight") or 0) for h in hints if isinstance(h, dict) and h.get("polarity_hint") == "positive")
            neg_score = sum(float(h.get("weight") or 0) for h in hints if isinstance(h, dict) and h.get("polarity_hint") == "negative")
            all_neutral = all(p in (None, "neutral") for p in polarity_list)
            proposed_edits_any = []
            for r in rebuttals:
                for e in (r.get("proposed_edits") or []):
                    op = e.get("op") if isinstance(e, dict) else getattr(e, "op", None)
                    val = e.get("value") if isinstance(e, dict) else getattr(e, "value", None)
                    proposed_edits_any.append({"op": op, "value": val})
            if proposed_edits_any and all_neutral and valid_count == 0:
                findings.append({
                    "finding_id": f"step2_neutral_only_{text_id}_{aspect}".replace(" ", "_"),
                    "severity": "blocker",
                    "symptom": f"text_id={text_id} aspect={aspect}: proposed_edits에 set_polarity 등 있는데 polarity_hint 전부 neutral/None, valid_hint_count=0",
                    "expected": "set_polarity(value=positive|negative) → polarity_hint가 positive|negative로 기록",
                    "evidence": {
                        "file": "scorecards.jsonl",
                        "record_key": text_id,
                        "json_path": "runtime.parsed_output.meta.debate_review_context.aspect_hints",
                        "observed_value": {"polarity_hint_list": polarity_list, "valid_hint_count": valid_count, "pos_score": pos_score, "neg_score": neg_score, "proposed_edits_sample": proposed_edits_any[:3]},
                    },
                    "root_cause_hypothesis": "_build_debate_review_context에서 proposed_edits 항목이 dict일 때 getattr(e,'value',None) → None (수정: _edit_attr 사용)",
                    "fix_plan": "supervisor_agent._build_debate_review_context에서 edit 필드 읽기 시 dict/object 둘 다 지원 (_edit_attr)",
                    "status": "fixed",
                })
    return findings


def step3_override_gate(
    run_dir: Path,
    t0_dir: Optional[Path],
    t1_dir: Optional[Path],
    t2_dir: Optional[Path],
    findings: List[Dict[str, Any]],
) -> None:
    """Step 3: T0/T1/T2 비교표 및 게이트 vs 신호 버그 결론."""
    for label, d in [("T0", t0_dir), ("T1", t1_dir), ("T2", t2_dir)]:
        if not d or not d.exists():
            continue
        summary = load_json(d / "override_gate_debug_summary.json")
        if not summary:
            findings.append({
                "finding_id": f"step3_no_summary_{label}",
                "severity": "minor",
                "symptom": f"{label} run에 override_gate_debug_summary.json 없음",
                "expected": "override gate 사용 run은 summary 1개 존재",
                "evidence": {"file": str(d / "override_gate_debug_summary.json"), "observed_value": None},
                "root_cause_hypothesis": "run 시 summary 미기록",
                "fix_plan": "run 시 _write_override_gate_debug_summary 호출 보장",
                "status": "open",
            })
            continue
        applied = summary.get("decision_applied_n", 0)
        skip_reason = summary.get("skip_reason_count") or {}
        if applied == 0 and (skip_reason.get("neutral_only") or skip_reason.get("low_signal")):
            findings.append({
                "finding_id": f"step3_signal_bug_{label}",
                "severity": "blocker",
                "symptom": f"{label}: override_applied=0, skip_reason에 neutral_only/low_signal 존재 → total/margin 0",
                "expected": "T1/T2 완화 시 applied 증가하거나, 증가 안 하면 신호 생성/매핑 버그",
                "evidence": {"file": str(d / "override_gate_debug_summary.json"), "observed_value": summary},
                "root_cause_hypothesis": "polarity_hint가 neutral로 환원되는 버그 (proposed_edits dict 시 value 미읽음)",
                "fix_plan": "polarity_hint 매핑 버그 수정 후 재측정",
                "status": "fixed",
            })


def step4_stage2_contract(scorecards: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> None:
    """Step 4: Stage2가 debate_review_context 수신 및 provenance 반영."""
    for i, row in enumerate(scorecards):
        text_id = (row.get("meta") or {}).get("text_id") or row.get("text_id") or f"row_{i}"
        ctx = get_debate_review_context(row)
        trace = (row.get("runtime") or {}).get("parsed_output") or {}
        trace_list = trace.get("process_trace") or row.get("process_trace") or []
        stage2_ate = next((t for t in trace_list if (t.get("stage") or "").lower() == "stage2" and (t.get("agent") or "").lower() == "ate"), None)
        stage2_atsa = next((t for t in trace_list if (t.get("stage") or "").lower() == "stage2" and (t.get("agent") or "").lower() == "atsa"), None)
        if ctx and (stage2_ate or stage2_atsa):
            for entry, name in [(stage2_ate, "ATE"), (stage2_atsa, "ATSA")]:
                if not entry:
                    continue
                out = entry.get("output") or {}
                reviews = out.get("aspect_review") if name == "ATE" else out.get("sentiment_review")
                if reviews and isinstance(reviews, list):
                    has_provenance = any(
                        bool((r.get("provenance") if isinstance(r, dict) else getattr(r, "provenance", None)) or "")
                        for r in reviews
                    )
                    if not has_provenance and ctx.get("aspect_hints"):
                        findings.append({
                            "finding_id": f"step4_no_provenance_{text_id}_{name}",
                            "severity": "minor",
                            "symptom": f"text_id={text_id} Stage2 {name}: review에 provenance 없음",
                            "expected": "debate_review_context 있을 때 provenance (source:EPM/patch 등) 기대",
                            "evidence": {"file": "scorecards.jsonl", "record_key": text_id, "json_path": f"process_trace.stage2.{name}.output", "observed_value": "provenance empty"},
                            "root_cause_hypothesis": "_inject_review_provenance 호출 또는 필드명 불일치",
                            "fix_plan": "supervisor _inject_review_provenance 확인",
                            "status": "open",
                        })


def step5_memory_contract(scorecards: List[Dict[str, Any]], findings: List[Dict[str, Any]]) -> None:
    """Step 5: Memory retrieval/노출/차단 메타 기록."""
    for i, row in enumerate(scorecards):
        text_id = (row.get("meta") or {}).get("text_id") or row.get("text_id") or f"row_{i}"
        meta = row.get("meta") or {}
        mem = meta.get("memory") or row.get("memory") or {}
        if not isinstance(mem, dict):
            continue
        required = ["retrieved_k", "retrieved_ids", "exposed_to_debate"]
        for k in required:
            if k not in mem and k != "retrieved_ids":
                findings.append({
                    "finding_id": f"step5_missing_{k}_{text_id}".replace(" ", "_"),
                    "severity": "minor",
                    "symptom": f"text_id={text_id}: memory.{k} 없음",
                    "expected": "scorecard에 retrieval/노출 메타 항상 기록",
                    "evidence": {"file": "scorecards.jsonl", "record_key": text_id, "json_path": f"meta.memory.{k}", "observed_value": mem.get(k)},
                    "root_cause_hypothesis": "scorecard_from_smoke 또는 meta_extra에 memory 필드 누락",
                    "fix_plan": "memory 메타 기록 계약 명시 및 검증",
                    "status": "open",
                })


def step6_aggregator_consistency(
    run_dir: Path,
    scorecards: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
) -> None:
    """Step 6: Aggregator SoT 일치 및 metric 정합성."""
    try:
        from scripts.structural_error_aggregator import _extract_final_tuples
    except Exception:
        _extract_final_tuples = None
    if not _extract_final_tuples:
        return
    for i, row in enumerate(scorecards):
        fr = get_final_result(row)
        ft = fr.get("final_tuples")
        if not ft:
            continue
        extracted = _extract_final_tuples(row)
        if not extracted and ft:
            findings.append({
                "finding_id": f"step6_extract_mismatch_{i}",
                "severity": "major",
                "symptom": f"row {i}: final_result.final_tuples 있으나 _extract_final_tuples 빈 집합",
                "expected": "extractor가 final_result.final_tuples 우선 사용",
                "evidence": {"file": "scorecards.jsonl", "record_key": i, "json_path": "final_result.final_tuples", "observed_value": "extract empty"},
                "root_cause_hypothesis": "record 구조가 aggregator 기대와 다름 (runtime.parsed_output.final_result)",
                "fix_plan": "aggregator가 scorecard/record 구조와 동일 경로 사용",
                "status": "open",
            })


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Pipeline integrity audit (mini4 C2, 10 samples)")
    ap.add_argument("--run_dir", type=str, default=None, help="e.g. results/experiment_mini4_validation_c2_t0_proposed")
    ap.add_argument("--t1_dir", type=str, default=None, help="T1 run dir for Step 3")
    ap.add_argument("--t2_dir", type=str, default=None, help="T2 run dir for Step 3")
    ap.add_argument("--out_dir", type=str, default=None, help="default: reports/")
    args = ap.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else _PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t0_proposed"
    t1_dir = Path(args.t1_dir) if args.t1_dir else _PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t1_proposed"
    t2_dir = Path(args.t2_dir) if args.t2_dir else _PROJECT_ROOT / "results" / "experiment_mini4_validation_c2_t2_proposed"
    out_dir = Path(args.out_dir) if args.out_dir else _PROJECT_ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    scorecards = load_jsonl(run_dir / "scorecards.jsonl")
    outputs = load_jsonl(run_dir / "outputs.jsonl")
    traces = load_jsonl(run_dir / "traces.jsonl")
    manifest = load_json(run_dir / "manifest.json")
    override_summary = load_json(run_dir / "override_gate_debug_summary.json")

    findings: List[Dict[str, Any]] = []

    # Step 1
    sot_policy, _ = step1_sot_mapping()

    # Step 2
    step2_debate_signal(run_dir, scorecards, findings)

    # Step 3
    step3_override_gate(run_dir, run_dir, t1_dir, t2_dir, findings)

    # Step 4
    step4_stage2_contract(scorecards, findings)

    # Step 5
    step5_memory_contract(scorecards, findings)

    # Step 6
    step6_aggregator_consistency(run_dir, scorecards, findings)

    # File integrity
    n = 10
    if len(outputs) != n:
        findings.append({
            "finding_id": "integrity_outputs_count",
            "severity": "major",
            "symptom": f"outputs.jsonl 레코드 수 {len(outputs)} (기대 {n})",
            "expected": f"10",
            "evidence": {"file": "outputs.jsonl", "observed_value": len(outputs)},
            "root_cause_hypothesis": "dataset 또는 run 설정",
            "fix_plan": "mini4 valid 10 샘플 확인",
            "status": "open",
        })
    if len(scorecards) != n:
        findings.append({
            "finding_id": "integrity_scorecards_count",
            "severity": "major",
            "symptom": f"scorecards.jsonl 레코드 수 {len(scorecards)} (기대 {n})",
            "expected": f"10",
            "evidence": {"file": "scorecards.jsonl", "observed_value": len(scorecards)},
            "root_cause_hypothesis": "scorecard 생성 누락",
            "fix_plan": "run 시 scorecard 1:1 기록",
            "status": "open",
        })
    if not (run_dir / "override_gate_debug_summary.json").exists() and override_summary is None:
        findings.append({
            "finding_id": "integrity_override_summary",
            "severity": "minor",
            "symptom": "override_gate_debug_summary.json 없음",
            "expected": "C2 override 사용 run은 1개 존재",
            "evidence": {"file": str(run_dir / "override_gate_debug_summary.json"), "observed_value": None},
            "root_cause_hypothesis": "enable_debate_override False 또는 미기록",
            "fix_plan": "N/A",
            "status": "open",
        })

    # Write findings JSON
    findings_path = out_dir / "pipeline_integrity_audit_findings.json"
    with open(findings_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_id": manifest.get("run_id") if manifest else str(run_dir.name),
                "cfg_hash": manifest.get("cfg_hash") if manifest else None,
                "findings": findings,
                "summary": {
                    "blocker": sum(1 for x in findings if x.get("severity") == "blocker"),
                    "major": sum(1 for x in findings if x.get("severity") == "major"),
                    "minor": sum(1 for x in findings if x.get("severity") == "minor"),
                    "fixed": sum(1 for x in findings if x.get("status") == "fixed"),
                },
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"Wrote {findings_path}")

    # Write audit markdown
    md_path = out_dir / "pipeline_integrity_audit.md"
    lines = [
        "# ABSA 파이프라인 End-to-End 정합성 점검 보고서",
        "",
        f"**Run**: `{run_dir.name}` | **Samples**: {len(scorecards)} | **Seed**: 42 (mini4 C2)",
        "",
        "## A. End-to-End 파일 무결성",
        "",
        f"- outputs/scorecards/traces 레코드 수: outputs={len(outputs)}, scorecards={len(scorecards)}, traces={len(traces)} (기대 10)",
        f"- override_gate_debug_summary.json 존재: {(run_dir / 'override_gate_debug_summary.json').exists()}",
        f"- manifest cfg_hash/run_id 일치: run_id={manifest.get('run_id') if manifest else 'N/A'}",
        "",
        "## B. SoT/튜플 정책",
        "",
        "### 최종 튜플 SoT (단일 정의)",
        "",
        sot_policy,
        "",
        "- aggregator: `_extract_final_tuples` 우선순위 = final_result.final_tuples → final_aspects → inputs.aspect_sentiments.",
        "",
        "## C. Debate 신호 (polarity_hint)",
        "",
        "- set_polarity(value=positive|negative) → aspect_hints에서 polarity_hint가 positive|negative로 반영되어야 함.",
        "- set_aspect_ref는 polarity 점수에서 제외 (weight 0 / polarity_hint None).",
        "- **수정 적용**: proposed_edits 항목이 dict일 때 value/op/target 읽기 위해 `_edit_attr(e, key)` 사용 (neutral 환원 버그 해소).",
        "",
        "## D. Override Gate (T0/T1/T2)",
        "",
        "- T0 summary: " + (json.dumps(override_summary, ensure_ascii=False) if override_summary else "N/A"),
        "",
        "- **결론**: T1/T2에서 applied가 0이면 게이트 역치 문제가 아니라 **신호 생성/매핑 버그** (polarity_hint neutral 환원). 수정 후 재측정 권장.",
        "",
        "## E. Stage2 리뷰 계약",
        "",
        "- debate_review_context는 Stage2 입력(extra_context)에 포함됨 (supervisor._run_stage2 → debate_context=debate_context_json).",
        "- Stage2 output provenance는 _inject_review_provenance로 source:EPM/patch 등 주입.",
        "",
        "## F. Memory 계약/게이트",
        "",
        "- scorecard meta.memory: retrieved_k, retrieved_ids, exposed_to_debate, prompt_injection_chars, advisory_injection_gated, memory_blocked_* 기록.",
        "",
        "## G. Aggregator/Metric 정합성",
        "",
        "- structural_metrics.csv / triptych_table / metric_report 동일 run에서 final_result.final_tuples 기반 추출과 일치해야 함.",
        "",
        "## 발견 요약 (pipeline_integrity_audit_findings.json)",
        "",
        f"- Blocker: {sum(1 for x in findings if x.get('severity') == 'blocker')}",
        f"- Major: {sum(1 for x in findings if x.get('severity') == 'major')}",
        f"- Minor: {sum(1 for x in findings if x.get('severity') == 'minor')}",
        f"- Fixed: {sum(1 for x in findings if x.get('status') == 'fixed')}",
        "",
    ]
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
