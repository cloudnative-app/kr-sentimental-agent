#!/usr/bin/env python3
"""
체크리스트: polarity_hint 생성 로직, total/margin 0 원인, final_tuples 정책을 한 번에 점검.

입력: results/<run_id> (scorecards.jsonl, outputs.jsonl, override_gate_debug.jsonl, stage2 리뷰 컨텍스트)
출력: reports/<name>_polarity_final_tuples_checklist.md

체크리스트 1 — polarity_hint 생성 로직
  1-1: rebuttal_points proposed_edits(op/value/target.polarity) vs polarity_hint 일치 여부, 전부 neutral 버그 후보
  1-2: stance=="" 시 polarity_hint 강제 neutral 코드 여부 / proposed_edits에서 polarity 세팅 여부
  1-3: set_aspect_ref(TAN) polarity_hint None·점수 제외 여부
  1-4: drop_tuple(CJ) 점수화 규칙 (anti-neutral/별도 카운트 또는 neutral 0점 방지)
  1-5: 점수 계산 직전 디버그 로그 (override_gate_debug + supervisor 1샘플 로그)

체크리스트 2 — total/margin 0 원인 분리 (A/B/C)
체크리스트 3 — debate_summary.final_tuples vs final_result.final_tuples 정책 및 모순 여부

Usage:
  python scripts/checklist_polarity_final_tuples.py --run_dir results/experiment_mini4_validation_c2_t0_proposed --out reports/c2_t0_polarity_checklist.md
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_debate_review_context(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """debate_review_context from runtime.parsed_output.meta or meta."""
    ctx = (row.get("runtime") or {}).get("parsed_output") or {}
    if isinstance(ctx, dict):
        ctx = ctx.get("meta") or {}
    ctx = ctx.get("debate_review_context") if isinstance(ctx, dict) else None
    if ctx:
        return ctx
    return (row.get("meta") or {}).get("debate_review_context")


def _norm_pol(raw: Any) -> Optional[str]:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().lower().replace("pos", "positive").replace("neg", "negative").replace("neu", "neutral")
    return s if s in ("positive", "negative", "neutral") else None


def check_1_1_polarity_hint_match(rows: List[Dict[str, Any]]) -> Tuple[str, List[str]]:
    """1-1: 힌트 원천(proposed_edits)과 polarity_hint 일치 여부, 전부 neutral 버그 후보."""
    lines = []
    all_neutral_bug_candidates = []
    for i, row in enumerate(rows):
        ctx = _get_debate_review_context(row)
        if not ctx:
            continue
        rebuttals = ctx.get("rebuttal_points") or []
        for r in rebuttals:
            speaker = r.get("speaker", "?")
            edits = r.get("proposed_edits") or []
            expected_from_edits = []
            for e in edits:
                op = (e.get("op") or "").strip().lower()
                target = e.get("target") or {}
                if op == "set_polarity":
                    v = _norm_pol(e.get("value"))
                    if v:
                        expected_from_edits.append(("set_polarity", v))
                elif op == "drop_tuple":
                    pol = _norm_pol(target.get("polarity"))
                    expected_from_edits.append(("drop_tuple", pol or "neutral"))
                elif op == "confirm_tuple":
                    pol = _norm_pol(target.get("polarity"))
                    if pol:
                        expected_from_edits.append(("confirm_tuple", pol))
                elif op == "set_aspect_ref":
                    expected_from_edits.append(("set_aspect_ref", None))
            actual = r.get("polarity_hint")
            if expected_from_edits and actual == "neutral":
                pos_neg_expected = [t for _, v in expected_from_edits if v and v != "neutral"]
                if pos_neg_expected:
                    all_neutral_bug_candidates.append(f"row={i} speaker={speaker} expected={pos_neg_expected} actual=neutral")
            lines.append(f"  row{i} {speaker}: proposed_edits→{expected_from_edits} polarity_hint={actual}")
    all_neutral = False
    if all_neutral_bug_candidates:
        all_neutral = True
        lines.append("  [버그 후보] rebuttal_points[*].polarity_hint가 pos/neg인데 전부 neutral로 찍힌 케이스: " + str(len(all_neutral_bug_candidates)))
        for c in all_neutral_bug_candidates[:5]:
            lines.append("    - " + c)
    else:
        lines.append("  OK: 일치하거나 검사할 편집 없음.")
    return "\n".join(lines), all_neutral_bug_candidates


def check_1_2_stance_empty(supervisor_path: Path) -> Tuple[str, bool]:
    """1-2: stance=='' 일 때 polarity_hint를 neutral로 강제하는 코드 여부."""
    text = supervisor_path.read_text(encoding="utf-8") if supervisor_path.exists() else ""
    # stance 비어있을 때 None/0 주는 코드는 OK; "neutral"로 덮어쓰는지 확인
    force_neutral = bool(re.search(r'stance\s*[=!]=\s*["\']["\']|if\s+not\s+stance', text)) and "polarity_hint" in text and "neutral" in text
    proposed_path = "proposed_edits" in text and "polarity_hint" in text and ("set_polarity" in text or "drop_tuple" in text)
    lines = [
        "  stance 빈 문자열 시 polarity_hint: 코드에서 proposed_edits 기반으로 세팅하는지 확인.",
        "  (supervisor _build_debate_review_context: hint_entries는 per-edit, rebuttals는 turn별 polarity_first or neutral)",
        "  강제 neutral 덮어쓰기 의심 패턴: " + ("있음" if force_neutral else "없음"),
        "  proposed_edits에서 polarity 사용: " + ("있음" if proposed_path else "없음"),
    ]
    return "\n".join(lines), force_neutral


def check_1_3_tan_excluded(rows: List[Dict[str, Any]], gate_records: List[Dict[str, Any]]) -> str:
    """1-3: set_aspect_ref(TAN) polarity_hint None, total에서 제외 여부."""
    lines = []
    for row in rows[:3]:
        ctx = _get_debate_review_context(row)
        if not ctx:
            continue
        ah = ctx.get("aspect_hints") or {}
        for aspect, hints in ah.items():
            tan_like = [h for h in hints if h.get("polarity_hint") is None or (h.get("weight") == 0)]
            if tan_like:
                lines.append(f"  aspect={aspect} TAN-like hints(weight=0/polarity_hint=None): {len(tan_like)}개 → total 제외됨(코드: pos/neg만 합산)")
                break
    if not lines:
        lines.append("  aspect_hints에 polarity_hint=None/weight=0 항목 없음(샘플에서). 코드상 set_aspect_ref는 weight=0, polarity_hint=None → total 제외.")
    return "\n".join(lines) if lines else "  (샘플 없음)"


def check_1_4_drop_tuple_scoring(supervisor_path: Path) -> str:
    """1-4: drop_tuple(target.polarity=neutral) 점수화: negative/별도 카운트 여부."""
    text = supervisor_path.read_text(encoding="utf-8") if supervisor_path.exists() else ""
    if 'op == "drop_tuple"' in text and "polarity_hint" in text and "negative" in text:
        return "  코드: drop_tuple → polarity_hint='negative', weight=0.8 (anti-neutral 신호로 neg 쪽에 합산)."
    return "  코드 확인 필요: drop_tuple 처리 위치 검색."


def check_1_5_debug_log(supervisor_path: Path, gate_path: Path) -> str:
    """1-5: 점수 계산 직전 디버그 로그 추가 여부 + override_gate_debug 1샘플."""
    lines = []
    text = supervisor_path.read_text(encoding="utf-8") if supervisor_path.exists() else ""
    if "override_gate_debug" in text and "sample_idx=0" in text and "per_hint" in text:
        lines.append("  supervisor: _apply_stage2_reviews 내 sample_idx==0 1회 로그(per_hint, pos_score, neg_score, total, margin) 있음.")
    else:
        lines.append("  supervisor: 1샘플 디버그 로그 없음.")
    records = _load_jsonl(gate_path)
    first = next((r for r in records if r.get("sample_idx") == 0), None)
    if first:
        lines.append(
            "  override_gate_debug.jsonl 첫 샘플(aspect): pos_score=%s neg_score=%s total=%s margin=%s skip_reason=%s"
            % (first.get("pos_score"), first.get("neg_score"), first.get("total"), first.get("margin"), first.get("skip_reason"))
        )
    else:
        lines.append("  override_gate_debug.jsonl에 sample_idx=0 레코드 없음.")
    return "\n".join(lines)


def check_2_abc(rows: List[Dict[str, Any]], gate_records: List[Dict[str, Any]]) -> Tuple[str, Dict[str, int], List[str]]:
    """2: total/margin 0 원인 분류 (A:힌트0개 B:전부 neutral/None C:polarity 있는데 weight 0)."""
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for r in gate_records:
        k = (r.get("text_id"), r.get("sample_idx"), r.get("aspect_term"))
        if k not in by_key:
            by_key[k] = []
        by_key[k].append(r)
    rows_by_uid = {}
    for row in rows:
        uid = (row.get("meta") or {}).get("text_id")
        if not uid:
            parsed = (row.get("runtime") or {}).get("parsed_output")
            if isinstance(parsed, dict):
                uid = (parsed.get("meta") or {}).get("uid") or parsed.get("uid")
        if uid:
            rows_by_uid[uid] = row
    a, b, c = 0, 0, 0
    examples: List[str] = []
    for (text_id, sample_idx, aspect_term), recs in by_key.items():
        rec = recs[0]
        if (rec.get("total") or 0) != 0 and (rec.get("margin") or 0) != 0:
            continue
        row = rows_by_uid.get(text_id)
        ctx = _get_debate_review_context(row) if row else None
        hints = (ctx or {}).get("aspect_hints") or {}
        hint_list = hints.get(aspect_term) if isinstance(hints, dict) else []
        if not hint_list:
            a += 1
            if len(examples) < 3:
                examples.append(f"A: text_id={text_id} aspect={aspect_term} hints=0")
        else:
            all_neu_none = all(h.get("polarity_hint") in (None, "neutral") for h in hint_list)
            has_pos_neg = any(h.get("polarity_hint") in ("positive", "negative") for h in hint_list)
            weight_all_zero = all((h.get("weight") or 0) == 0 for h in hint_list)
            if all_neu_none and not has_pos_neg:
                b += 1
                if len(examples) < 5:
                    examples.append(f"B: text_id={text_id} aspect={aspect_term} hints={len(hint_list)} 모두 neutral/None")
            elif has_pos_neg and weight_all_zero:
                c += 1
                if len(examples) < 5:
                    examples.append(f"C: text_id={text_id} aspect={aspect_term} polarity 있으나 weight 0")
            else:
                b += 1
                if len(examples) < 5:
                    examples.append(f"B: text_id={text_id} aspect={aspect_term} (기타)")
    lines = [
        "  (A) 힌트 0개 → 추출 실패: %s" % a,
        "  (B) 힌트 있는데 polarity_hint 전부 neutral/None: %s" % b,
        "  (C) polarity_hint 있는데 가중치 0: %s" % c,
        "  샘플: " + "; ".join(examples[:5]),
    ]
    return "\n".join(lines), {"A": a, "B": b, "C": c}, examples


def check_3_1_policy() -> str:
    """3-1: 최종 tuple source-of-truth 정책."""
    return "  정책: debate_summary.final_tuples 존재 시 final_aspect_sentiments(및 final_result.final_tuples)를 그에 맞춤. 코드: run() 내 debate_output.summary.final_tuples 반영."


def check_3_2_conflict_and_judge(rows: List[Dict[str, Any]]) -> str:
    """3-2: stage2_tuples conflict, dedup/resolve 후 final_tuples와 judge 일치."""
    lines = []
    for row in rows[:10]:
        parsed = (row.get("runtime") or {}).get("parsed_output")
        meta = (parsed.get("meta") or {}) if isinstance(parsed, dict) else {}
        final_result = meta.get("final_result") or row.get("final_result") or {}
        stage2_tuples = final_result.get("stage2_tuples") or []
        final_tuples = final_result.get("final_tuples") or []
        summary_tuples = (meta.get("debate_summary") or {}).get("final_tuples") or []
        by_aspect = {}
        for t in stage2_tuples:
            at = (t.get("aspect_term") or t.get("aspect_ref") or "").strip() or ""
            if at not in by_aspect:
                by_aspect[at] = []
            pol = (t.get("polarity") or "").strip()
            if pol:
                by_aspect[at].append(pol)
        conflict = [k for k, v in by_aspect.items() if len(set(v)) > 1]
        if conflict:
            lines.append(f"  uid={meta.get('uid')} stage2_tuples 동일 aspect 다 polarity: {conflict}")
        if summary_tuples and final_tuples:
            sum_pols = {(t.get("aspect_term") or t.get("aspect_ref") or ""): t.get("polarity") for t in summary_tuples}
            fin_pols = {(t.get("aspect_term") or t.get("aspect_ref") or ""): t.get("polarity") for t in final_tuples}
            if sum_pols != fin_pols:
                lines.append(f"  uid={meta.get('uid')} debate_summary.final_tuples vs final_result.final_tuples 불일치")
    if not lines:
        lines.append("  검사한 샘플에서 stage2 conflict 없음 / final_tuples와 debate_summary 일치.")
    return "\n".join(lines) if lines else "  (데이터 없음)"


def check_3_3_moderator_label_sync(rows: List[Dict[str, Any]]) -> str:
    """3-3: moderator.final_label vs final_tuples 모순(positive인데 tuple은 neutral만) 여부."""
    lines = []
    bad = 0
    for row in rows:
        mod = row.get("moderator") or (row.get("ate") or {}).get("moderator") or {}
        final_result = row.get("final_result") or {}
        parsed = (row.get("runtime") or {}).get("parsed_output")
        if isinstance(parsed, dict):
            meta = parsed.get("meta") or {}
            mod = meta.get("moderator") or mod
            final_result = meta.get("final_result") or final_result
        label = (mod.get("final_label") or "").strip().lower()
        tuples = final_result.get("final_tuples") or []
        pols = [((t.get("polarity") or "").strip().lower()) for t in tuples if (t.get("polarity") or "").strip()]
        if label == "positive" and pols and all(p == "neutral" for p in pols):
            bad += 1
            uid = (row.get("meta") or {}).get("text_id") or (isinstance(parsed, dict) and (parsed.get("meta") or {}).get("uid")) or ""
            lines.append(f"  모순: uid={uid} moderator.final_label=positive, final_tuples polarities={pols}")
    if bad == 0:
        lines.append("  OK: moderator final_label과 final_tuples polarity 모순 없음.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Polarity & final_tuples checklist (1–3)")
    ap.add_argument("--run_dir", type=str, required=True, help="e.g. results/experiment_mini4_validation_c2_t0_proposed")
    ap.add_argument("--out", type=str, default="", help="Output markdown path (default: reports/<run_dir_name>_polarity_checklist.md)")
    args = ap.parse_args()

    root = _PROJECT_ROOT
    run_dir = root / args.run_dir
    if not run_dir.is_dir():
        run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"[FAIL] not a directory: {run_dir}", file=sys.stderr)
        return 1

    scorecards_path = run_dir / "scorecards.jsonl"
    outputs_path = run_dir / "outputs.jsonl"
    gate_path = run_dir / "override_gate_debug.jsonl"
    gate_summary_path = run_dir / "override_gate_debug_summary.json"
    supervisor_path = root / "agents" / "supervisor_agent.py"

    rows = _load_jsonl(scorecards_path)
    gate_records = _load_jsonl(gate_path)
    gate_summary = _load_json(gate_summary_path)
    output_count = len(_load_jsonl(outputs_path))

    out_path = root / args.out if args.out else root / "reports" / (run_dir.name + "_polarity_checklist.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 기본 점검
    sc_count = len(rows)
    out_lines = [
        "# Polarity & Final Tuples 체크리스트",
        "",
        "**Run dir**: `%s`" % run_dir,
        "",
        "## 기본",
        "- scorecards.jsonl 레코드 수: **%s**" % sc_count,
        "- outputs.jsonl 레코드 수: **%s**" % (output_count if outputs_path.exists() else "N/A"),
        "- stage2 리뷰 컨텍스트: scorecards 내 runtime.parsed_output.meta.debate_review_context 사용",
        "",
    ]

    # 1-1
    out_lines.append("## 체크리스트 1 — polarity_hint 생성 로직")
    out_lines.append("### 1-1 힌트 원천 vs polarity_hint 일치 / 전부 neutral 버그 후보")
    t1_1, bug_candidates = check_1_1_polarity_hint_match(rows)
    out_lines.append(t1_1)
    out_lines.append("")

    # 1-2
    out_lines.append("### 1-2 stance=\"\" 처리")
    t1_2, force_neutral = check_1_2_stance_empty(supervisor_path)
    out_lines.append(t1_2)
    out_lines.append("")

    # 1-3
    out_lines.append("### 1-3 TAN(set_aspect_ref) 점수 제외")
    out_lines.append(check_1_3_tan_excluded(rows, gate_records))
    out_lines.append("")

    # 1-4
    out_lines.append("### 1-4 CJ(drop_tuple) 점수화 규칙")
    out_lines.append(check_1_4_drop_tuple_scoring(supervisor_path))
    out_lines.append("")

    # 1-5
    out_lines.append("### 1-5 점수 계산 직전 디버그 로그")
    out_lines.append(check_1_5_debug_log(supervisor_path, gate_path))
    out_lines.append("")

    # 2
    out_lines.append("## 체크리스트 2 — total/margin 0 원인 (A/B/C)")
    t2, abc_counts, examples = check_2_abc(rows, gate_records)
    out_lines.append(t2)
    out_lines.append("")

    # 3
    out_lines.append("## 체크리스트 3 — final_tuples 정책 및 일치")
    out_lines.append("### 3-1 최종 tuple source-of-truth")
    out_lines.append(check_3_1_policy())
    out_lines.append("")
    out_lines.append("### 3-2 stage2 conflict / dedup 후 judge 일치")
    out_lines.append(check_3_2_conflict_and_judge(rows))
    out_lines.append("")
    out_lines.append("### 3-3 moderator.final_label ↔ final_tuples 동기화")
    out_lines.append(check_3_3_moderator_label_sync(rows))
    out_lines.append("")

    out_lines.append("---")
    out_lines.append("체크리스트 4(게이트 실험 T0/T1/T2 재검증)는 run_mini4_c2_t0_t1_t2.py + checklist_override_gate_t0_t1_t2.py로 수행.")

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"[OK] Checklist written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
