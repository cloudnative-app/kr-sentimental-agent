#!/usr/bin/env python3
"""
One-off diagnostic for mini4_b1_2: 6 checks (unsupported 1-sample, conflict aspect key,
risk_flagged risk_ids, override vs ignored units, guided vs override defs, F1 vs unsupported).
Writes docs/mini4_b1_2_checks_result.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from structural_error_aggregator import (
    _extract_final_tuples,
    _get_override_stats,
    count_stage1_risks,
    has_same_aspect_polarity_conflict,
    has_unsupported_polarity,
    stage_delta_guided_unguided,
)
from metrics.eval_tuple import (
    gold_tuple_set_from_record,
    gold_row_to_tuples,
    normalize_for_eval,
    normalize_polarity,
    tuples_to_pairs,
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _get_raw_final_tuples(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    runtime = record.get("runtime") or {}
    parsed = runtime.get("parsed_output") if isinstance(runtime.get("parsed_output"), dict) else {}
    final_result = parsed.get("final_result") or {}
    ft = final_result.get("final_tuples")
    return list(ft) if ft and isinstance(ft, list) else []


def _conflict_aspects_and_tuples(record: Dict[str, Any]) -> Tuple[Dict[str, Set[str]], List[Tuple[str, str, str]]]:
    """Same logic as has_same_aspect_polarity_conflict but return by_aspect and list of (aspect_term, polarity) for conflict keys."""
    tuples = _extract_final_tuples(record)
    by_aspect: Dict[str, Set[str]] = {}
    tuple_list: List[Tuple[str, str, str]] = []
    for (_ar, aspect_term, polarity) in tuples:
        aspect_term = (aspect_term or "").strip()
        if not aspect_term:
            continue
        if aspect_term not in by_aspect:
            by_aspect[aspect_term] = set()
        by_aspect[aspect_term].add((polarity or "").strip())
        tuple_list.append((aspect_term, polarity or "", _ar))
    return by_aspect, tuple_list


def run_checks(scorecards_path: Path, csv_path: Path, out_md: Path) -> None:
    rows = load_jsonl(scorecards_path)
    if not rows:
        out_md.write_text("# mini4_b1_2 checks\n\nNo scorecards.\n", encoding="utf-8")
        return

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(p)

    lines: List[str] = [
        "# mini4_b1_2 진단 결과 (6 checks)",
        "",
        f"**Scorecards**: `{_rel(scorecards_path)}` (N={len(rows)})",
        f"**Metrics**: `{_rel(csv_path)}`",
        "",
        "---",
        "",
        "## 체크 1 — Unsupported polarity 원인 1샘플 해부",
        "",
    ]

    # Check 1: first unsupported sample
    unsup_idx = next((i for i, r in enumerate(rows) if has_unsupported_polarity(r)), None)
    if unsup_idx is None:
        lines.append("(unsupported_polarity=True인 샘플 없음)")
    else:
        r = rows[unsup_idx]
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("uid") or f"#{unsup_idx+1}"
        lines.append(f"**샘플**: index={unsup_idx}, text_id={text_id}")
        lines.append("")
        raw_ft = _get_raw_final_tuples(r)
        lines.append("### final_tuples (원본 필드)")
        for i, t in enumerate(raw_ft):
            aspect_term = t.get("aspect_term")
            if isinstance(aspect_term, dict):
                aspect_term = aspect_term.get("term") or str(aspect_term)
            lines.append(f"- Tuple {i+1}: `aspect_term`={repr(aspect_term)}, `polarity`={repr(t.get('polarity'))}, "
                        f"`evidence`={repr(t.get('evidence'))}, `span`={repr(t.get('span'))}, 기타 keys={list(t.keys())}")
        lines.append("")
        atsa = r.get("atsa") or r.get("atsa_score") or {}
        judgements = atsa.get("sentiment_judgements") or []
        lines.append("### unsupported 판정 True가 된 이유 (코드 경로)")
        lines.append("`has_unsupported_polarity`: **완화 후** — 샘플 unsupported iff (모든 judgement 실패) OR (최종 tuple에 대응하는 judgement 실패).")
        lines.append("judgement 실패 = `opinion_grounded` is False OR issues가 존재하고 전부 'unknown/insufficient'가 아님. (evidence/span 없음만이면 unsupported로 세지 않음.)")
        lines.append("")
        for i, j in enumerate(judgements):
            issues = j.get("issues")
            og = j.get("opinion_grounded", True)
            er = j.get("evidence_relevant", True)
            triggered = bool(issues) or og is False or er is False
            lines.append(f"- Judgement {i+1}: `issues`={repr(issues)}, `opinion_grounded`={og}, `evidence_relevant`={er} → **triggered={triggered}**")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 체크 2 — Polarity conflict \"충돌 aspect key\" 확인")
    lines.append("")

    conflict_idx = next((i for i, r in enumerate(rows) if has_same_aspect_polarity_conflict(r)), None)
    if conflict_idx is None:
        lines.append("(polarity_conflict=True인 샘플 없음)")
    else:
        r = rows[conflict_idx]
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("uid") or f"#{conflict_idx+1}"
        by_aspect, tuple_list = _conflict_aspects_and_tuples(r)
        conflict_keys = [k for k, pols in by_aspect.items() if len(pols) >= 2]
        lines.append(f"**샘플**: index={conflict_idx}, text_id={text_id}")
        lines.append("")
        lines.append("### conflict를 만든 aspect key (정규화된 aspect_term)")
        lines.append("집계(aggregator)에서는 **정규화 적용**: key=normalize_for_eval(aspect_term), polarity=normalize_polarity(p). 아래는 진단용 raw key.")
        for k in conflict_keys:
            lines.append(f"- **{repr(k)}** → polarity set = {by_aspect[k]}")
        lines.append("")
        raw_ft = _get_raw_final_tuples(r)
        lines.append("### 해당 tuple들의 원문 span (있다면)")
        for t in raw_ft:
            at = t.get("aspect_term")
            term_str = at.get("term") if isinstance(at, dict) else repr(at)
            lines.append(f"- aspect_term={term_str}, polarity={repr(t.get('polarity'))}, span={repr(t.get('span'))}, evidence={repr(t.get('evidence'))}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 체크 3 — risk_flagged 샘플의 risk_id 및 polarity_conflict")
    lines.append("")

    risk_idx = next((i for i, r in enumerate(rows) if count_stage1_risks(r) > 0), None)
    if risk_idx is None:
        lines.append("(risk_flagged 샘플 없음)")
    else:
        r = rows[risk_idx]
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("uid") or f"#{risk_idx+1}"
        lines.append(f"**샘플**: index={risk_idx}, text_id={text_id}")
        lines.append("")
        validator = r.get("validator") or []
        risk_ids_s1: List[str] = []
        for vb in validator:
            if (vb.get("stage") or "").lower() == "stage1":
                for risk in (vb.get("structural_risks") or []):
                    risk_ids_s1.append((risk.get("risk_id") or "").strip())
                break
        lines.append(f"- **validator (stage1) risk_ids**: {risk_ids_s1}")
        lines.append(f"- **동일 샘플 polarity_conflict**: {has_same_aspect_polarity_conflict(r)}")
        lines.append("")
        lines.append("→ conflict가 True인데 risk_ids에 polarity conflict류가 없으면, RQ1 risk 정의는 옵션 A(Validator structural_risks만)이고, conflict와 flagged는 별개 지표.")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 체크 4 — debate_override_applied=2 인데 ignored_proposal_rate=1.0 인 이유")
    lines.append("")
    lines.append("- **debate_override_applied**: 집계 시 `sum(override_stats.applied)` over **rows** → **이벤트(제안) 수** (row당 0,1,2,… 가능).")
    lines.append("- **override_applied_rate**: 분모=N(샘플 수), 분자=**applied≥1인 샘플 수** (n_applied).")
    lines.append("- **ignored_proposal_rate**: 분모=**risk_flagged 샘플 수**, 분자=**risk_flagged이면서 stage_delta.changed=False인 샘플 수**.")
    lines.append("")
    lines.append("→ **단위 불일치**: applied=2 는 \"2번 적용 이벤트\"(예: 2개 샘플에서 각 1번, 또는 1개 샘플에서 2번). ignored=1.0 은 \"risk_flagged인 샘플 100%가 변경 없음\". ")
    lines.append("즉 applied는 proposal/tuple-level 합계, ignored는 sample-level 비율. **단위 통일**을 위해 applied도 \"샘플 수\" 기준(n_applied)으로 쓰고, 이벤트 수는 별도 컬럼(debate_override_applied)으로 두는 현재 방식이 맞음. ignored_proposal_rate=1.0이면 risk_flagged인 샘플이 1개뿐이고 그 샘플은 변경이 없다는 뜻.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 체크 5 — guided_change_rate=0 인데 override_applied_rate=0.2")
    lines.append("")
    lines.append("- **guided_change_rate**: 분모=**stage_delta.changed=True인 샘플 수**, 분자=그 중 **change_type==\"guided\"** 인 샘플 수. (코드: `stage_delta_guided_unguided` → change_type이 \"guided\"일 때만 True.)")
    lines.append("- **override_applied_rate**: debate에서 override 적용된 **샘플** 비율 (n_applied / N).")
    lines.append("")
    lines.append("→ **guided**는 파이프라인에서 \"메모리/가이드\" 기반 변경으로 붙이는 플래그일 수 있고, **override**는 debate 기반 변경. memory off이면 guided=0은 자연스럽고, override_applied=0.2는 debate로 2개 샘플이 변경 수용했다는 뜻. **guided_change의 분모/정의(what counts as guided)**를 파이프라인에서 확정해야 함 (debate 수용을 guided로 셀지 여부).")
    lines.append("")

    # Optional: one row with guided vs override
    n_guided = sum(1 for r in rows if stage_delta_guided_unguided(r)[0])
    n_changed = sum(1 for r in rows if (r.get("stage_delta") or {}).get("changed", False))
    n_applied = sum(1 for r in rows if int(_get_override_stats(r).get("applied") or 0) > 0)
    lines.append(f"(현재 run: changed 샘플 수={n_changed}, 그 중 guided={n_guided}, override applied 샘플 수={n_applied})")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 체크 6 — tuple_f1_s2 > 0 인데 unsupported_polarity_rate=1.0 의 공존")
    lines.append("")
    lines.append("- **tuple_f1_s2**: gold와의 (aspect_term, polarity) 매칭 F1 — **문자열/라벨 일치**.")
    lines.append("- **unsupported_polarity_rate**: atsa **sentiment_judgements**에서 issues/opinion_grounded/evidence_relevant 휴리스틱으로 \"근거 검증\" 실패한 샘플 비율.")
    lines.append("")
    lines.append("→ 두 지표는 **단위·정의가 다름**: F1=정답 매칭, unsupported=validator/ATSA 휴리스틱. 공존 가능. 다만 **전 샘플 100% unsupported**면 validator/ATSA 입력·기준이 과격하거나 입력 필드 불일치 가능성 큼 (예: aspect_term 형식, evidence 필드 누락).")
    lines.append("")

    # F1 0 원인 3줄 점검 + gold 정규화 전/후 + 선택 tuple → judgement 매핑
    lines.append("---")
    lines.append("")
    lines.append("## 체크 3bis — F1 0 원인 3줄 점검 (샘플 1개)")
    lines.append("")
    f1_sample_idx = next((i for i, r in enumerate(rows) if gold_tuple_set_from_record(r) is not None), None)
    if f1_sample_idx is None:
        lines.append("(gold 있는 샘플 없음)")
    else:
        r = rows[f1_sample_idx]
        text_id = (r.get("meta") or {}).get("text_id") or (r.get("meta") or {}).get("uid") or f"#{f1_sample_idx+1}"
        # Gold 원본 정규화 전/후
        inputs = r.get("inputs") or {}
        raw_gold = inputs.get("gold_tuples") or r.get("gold_tuples") or []
        norm_gold = gold_row_to_tuples({"gold_tuples": raw_gold}) if raw_gold else []
        lines.append(f"**샘플**: index={f1_sample_idx}, text_id={text_id}")
        lines.append("")
        lines.append("**gold 원본 정규화 전/후 (1개):**")
        if raw_gold and norm_gold:
            lines.append(f"- 정규화 전 (원본): `{raw_gold[0]}`")
            lines.append(f"- 정규화 후: aspect_term={repr(norm_gold[0].get('aspect_term'))}, polarity={repr(norm_gold[0].get('polarity'))}")
        else:
            lines.append("- (gold 없음)")
        lines.append("")
        gold_set = gold_tuple_set_from_record(r)
        final_set = _extract_final_tuples(r)
        gold_pairs = tuples_to_pairs(gold_set) if gold_set else set()
        final_pairs = tuples_to_pairs(final_set) if final_set else set()
        lines.append("1. **gold tuples (정규화된 키)** — `tuples_to_pairs(gold)` = (normalize_for_eval(term), normalize_polarity(p)):")
        lines.append(f"   `{sorted(gold_pairs)}`")
        lines.append("")
        lines.append("2. **final tuples (정규화된 키)** — 동일 정규화:")
        lines.append(f"   `{sorted(final_pairs)}`")
        lines.append("")
        lines.append("3. **매칭 키**: (aspect_term, polarity) — **term-only, span 미사용**. gold가 빈 aspect('')이면 pred가 아무리 좋아도 F1 의미 없음. mini4 valid.gold.jsonl에 aspect_term=\"\" 로 원본 저장된 행 있음.")
        lines.append("")

    # 선택 tuple 1개 → 대응 judgement row (key로 join)
    lines.append("---")
    lines.append("")
    lines.append("## 체크 2bis — 선택 tuple ↔ judgement 매핑 (1줄)")
    lines.append("")
    map_idx = next((i for i, r in enumerate(rows) if _extract_final_tuples(r) and (r.get("atsa") or r.get("atsa_score") or {}).get("sentiment_judgements")), None)
    if map_idx is None:
        lines.append("(final_tuples + sentiment_judgements 둘 다 있는 샘플 없음)")
    else:
        r = rows[map_idx]
        final_tuples = _extract_final_tuples(r)
        judgements = (r.get("atsa") or r.get("atsa_score") or {}).get("sentiment_judgements") or []
        # Pick first final tuple aspect_term (normalized)
        first_term = None
        for (_, t, _) in final_tuples:
            if (t or "").strip():
                first_term = normalize_for_eval((t or "").strip())
                break
        if first_term is None:
            lines.append("(첫 선택 tuple aspect_term 없음)")
        else:
            matched_ji = None
            for ji, j in enumerate(judgements):
                if normalize_for_eval((j.get("aspect_term") or "").strip()) == first_term:
                    matched_ji = ji
                    break
            if matched_ji is not None:
                lines.append(f"**샘플 index={map_idx}**: 선택 tuple aspect_term(normalized)={repr(first_term)} → **judgement index={matched_ji}** (key matched).")
            else:
                lines.append(f"**샘플 index={map_idx}**: 선택 tuple aspect_term(normalized)={repr(first_term)} → **no matching judgement** (join 실패).")
    lines.append("")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_md}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Diagnose mini4_b1_2 checks, write result md")
    ap.add_argument("--scorecards", default=None, help="Scorecards JSONL (default: results/experiment_mini4_b1_2__seed42_proposed/scorecards.jsonl)")
    ap.add_argument("--csv", default=None, help="Structural metrics CSV (default: same run derived/metrics/structural_metrics.csv)")
    ap.add_argument("--out", default=None, help="Output md (default: docs/mini4_b1_2_checks_result.md)")
    args = ap.parse_args()
    run_dir = PROJECT_ROOT / "results" / "experiment_mini4_b1_2__seed42_proposed"
    scorecards_path = Path(args.scorecards) if args.scorecards else run_dir / "scorecards.jsonl"
    csv_path = Path(args.csv) if args.csv else run_dir / "derived" / "metrics" / "structural_metrics.csv"
    out_md = Path(args.out) if args.out else PROJECT_ROOT / "docs" / "mini4_b1_2_checks_result.md"
    if not scorecards_path.is_absolute():
        scorecards_path = PROJECT_ROOT / scorecards_path
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    if not out_md.is_absolute():
        out_md = PROJECT_ROOT / out_md
    out_md.parent.mkdir(parents=True, exist_ok=True)
    run_checks(scorecards_path, csv_path, out_md)


if __name__ == "__main__":
    main()
