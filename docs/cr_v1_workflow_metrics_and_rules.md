# CR v1 에이전트 워크플로우·메트릭·의사결정규칙·SSOT

Conflict Review v1 프로토콜의 에이전트 워크플로우, 메트릭 데이터 플로우, 의사결정규칙, SSOT를 통합 정리합니다.

---

## 1. 에이전트 워크플로우 (단독)

```
text
  │
  ├─► P-NEG (Stage1) ──► triplets (negation/contrast 관점)
  ├─► P-IMP (Stage1) ──► triplets (implicit 관점)
  └─► P-LIT (Stage1) ──► triplets (literal/explicit 관점)
       │
       ▼
  Merge: A(r_neg) + B(r_imp) + C(r_lit) → candidates (tuple_id, origin_agent)
       │
       ▼
  conflict_flags = _compute_conflict_flags(candidates)  [동일 aspect_term + 상이 polarity]
       │
       ├─► ReviewA (text, candidates, conflict_flags) ──► review_actions
       ├─► ReviewB (text, candidates, conflict_flags) ──► review_actions
       └─► ReviewC (text, candidates, conflict_flags) ──► review_actions
       │
       ▼
  Arbiter (actions_by_tuple) ──► arb_actions (다수결 + Rule 3)
       │
       ▼
  _apply_review_actions(candidates, arb_actions) → final_candidates
       │
       ▼
  _finalize_normalize_ref(final_candidates)  [P1: No-op, aspect_ref 보존]
       │
       ▼
  FinalResult (stage1_tuples, final_tuples, final_aspects, label)
```

**에이전트 목록 (6개 LLM 호출 + 1개 코드 조정자)**

| 순서 | 에이전트 | 역할 | 출력 | LLM |
|------|----------|------|------|-----|
| 1 | P-NEG | 부정/대비 관점 ASTE | triplets | ✓ |
| 2 | P-IMP | 암시적 관점 ASTE | triplets | ✓ |
| 3 | P-LIT | 문자적 관점 ASTE | triplets | ✓ |
| 4 | ReviewA | A 관점 리뷰 | review_actions | ✓ |
| 5 | ReviewB | B 관점 리뷰 | review_actions | ✓ |
| 6 | ReviewC | C 관점 리뷰 | review_actions | ✓ |
| 7 | Arbiter | A/B/C 합의 (다수결 + Rule 3) | arb_actions | ✗ (코드) |

- **Validator, Debate, Moderator 없음**
- **Label**: final_tuples 극성 집계로 결정 (all pos→positive, all neg→negative, 혼합→mixed, 없음→neutral)

---

## 2. 메트릭 데이터 플로우

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  1. 추론 (Conflict Review Runner)                                                │
│     P-NEG/P-IMP/P-LIT → merge → ReviewA/B/C → Arbiter → FinalOutputSchema       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  2. outputs.jsonl (런 단위)                                                       │
│     FinalOutputSchema.model_dump()                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  3. scorecards.jsonl (make_scorecard)                                            │
│     stage_delta, gold_tuples, runtime.parsed_output = entry                      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  4. structural_error_aggregator                                                  │
│     입력: scorecards.jsonl (또는 merged_scorecards.jsonl)                         │
│     출력: structural_metrics.csv, structural_metrics_table.md                    │
│     - _extract_stage1_tuples, _extract_final_tuples → F1, fix/break/net_gain      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  5. aggregate_seed_metrics (시드 반복 시)                                         │
│     merged_scorecards.jsonl → aggregated_mean_std.csv, integrated_report.md      │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  6. build_metric_report → metric_report.html                                     │
│  7. export_paper_metrics_md / export_paper_metrics_aggregated → paper 테이블      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**튜플 추출 SSOT**

| 구분 | 필드 | CR 의미 | aggregator 함수 |
|------|------|---------|-----------------|
| stage1 | final_result.stage1_tuples | pre_review (merge 후 candidates) | _extract_stage1_tuples |
| final | final_result.final_tuples | post_review (Arbiter 적용 후) | _extract_final_tuples |

---

## 3. 에이전트 규칙

### 3.1 Perspective 에이전트 (P-NEG, P-IMP, P-LIT)

- **출력 스키마**: `ASTETripletItem` (aspect_term, aspect_ref?, polarity, evidence?, span?, confidence)
- **규칙**: 각 관점별로 ASTE 수행. LLM 출력은 스키마 검증 후 triplets로 수집.

### 3.2 Review 에이전트 (A, B, C)

- **입력**: text, candidates, conflict_flags
- **출력**: `ReviewOutputSchema.review_actions` — `ReviewActionItem` 리스트
- **액션 타입**: DROP | MERGE | FLIP | KEEP | FLAG
- **reason_code**: NEGATION_SCOPE, CONTRAST_CLAUSE, IMPLICIT_ASPECT, ASPECT_REF_MISMATCH, SPAN_OVERLAP_MERGE, DUPLICATE_TUPLE, WEAK_EVIDENCE, POLARITY_UNCERTAIN, FORMAT_INCOMPLETE, KEEP_BEST_SUPPORTED, WEAK_INFERENCE, EXPLICIT_NOT_REQUIRED, STRUCTURAL_INCONSISTENT

### 3.3 Conflict 플래그 규칙

- **정의**: 동일 `aspect_term`(또는 aspect_ref)에 서로 다른 `polarity`가 2개 이상 있으면 conflict
- **출력**: `{aspect_term, tuple_ids, conflict_type: "polarity_mismatch"}`

---

## 4. Arbiter(조정자) 규칙

**위치**: `agents/conflict_review_runner._arbiter_vote`

| 규칙 | 조건 | 최종 액션 |
|------|------|-----------|
| **Rule 1** | ≥2 identical vote | 해당 액션 채택 |
| **Rule 2** | A/B/C 전부 상이 | KEEP + FLAG |
| **Rule 3** | 1 FLIP + 1 DROP + 1 KEEP | FLIP의 reason_code ∈ {NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT} → FLIP; else FLAG |
| **Rule 4** | MERGE vote | KEEP으로 대체 (Arbiter는 MERGE 출력 안 함) |

**액션 적용** (`_apply_review_actions`):

- **DROP**: 해당 tuple_id 제거
- **FLIP**: new_value.polarity로 극성 변경
- **KEEP / FLAG**: 유지 (FLAG = KEEP, 플래그만 부여)

---

## 5. 정규화 규칙

### 5.1 평가용 (P0–P2)

| 정책 | 내용 |
|------|------|
| **P0** | 평가 키는 (aspect_term, polarity)만 사용. aspect_ref는 부가 메타데이터, F1/break/fix에 미사용 |
| **P1** | 파이프라인에서 aspect_ref 덮어쓰지 않음. _finalize_normalize_ref는 No-op |
| **P2** | Tier1+Tier2(strict)를 gold/parse/eval 전 경로에 공통 적용 |

### 5.2 문자열 (aspect_term)

| 함수 | 규칙 | 위치 |
|------|------|------|
| normalize_for_eval | strip, lower, 공백 축소, 앞뒤 구두점 제거. None→"" | metrics/eval_tuple.py |

### 5.3 극성 (polarity)

| 함수 | 규칙 | 위치 |
|------|------|------|
| normalize_polarity | pos→positive, neg→negative, neu→neutral. 결측→default_missing | metrics/eval_tuple.py |

### 5.4 CR 파이프라인 내

| 항목 | 규칙 | 비고 |
|------|------|------|
| _finalize_normalize_ref | No-op (P1) | aspect_ref 원본 보존 |
| ASTETripletItem.normalize_span | dict/list/str → {start, end} | protocol_conflict_review.py |

---

## 6. 파이프라인 내 의사결정규칙 요약

| 구분 | 규칙 | SSOT 위치 |
|------|------|-----------|
| **Merge** | A+B+C triplets → candidates (tuple_id, origin_agent) | conflict_review_runner |
| **Conflict** | 동일 term + 상이 polarity → conflict_flags | _compute_conflict_flags |
| **Arbiter** | Rule 1~4 (다수결, FLIP structural, MERGE→KEEP) | _arbiter_vote |
| **Apply** | DROP 제거, FLIP 극성 변경, KEEP/FLAG 유지 | _apply_review_actions |
| **Label** | all pos→positive, all neg→negative, 혼합→mixed | FinalResult 생성 시 |
| **stage_delta.changed** | s1_pairs != final_pairs or label_changed | scorecard_from_smoke._build_stage_delta |
| **change_type** | (review_actions or arb_actions) 존재 → guided_by_review; else unguided | scorecard_from_smoke |

---

## 7. SSOT 정리

| 데이터 | SSOT | 비고 |
|--------|------|------|
| **튜플 소스** | final_result.stage1_tuples, final_result.final_tuples | aggregator 추출 우선순위: stage1_tuples → trace → final_tuples fallback |
| **stage_delta.changed** | (s1_pairs != final_pairs) or (stage1_label != final_label) | tuples_to_pairs, _extract_* 동일 함수 사용 |
| **F1 매칭** | (aspect_term, polarity) 쌍. match_by_aspect_ref=False | precision_recall_f1_tuple |
| **fix/break** | tuple_sets_match_with_empty_rule(gold, pred) | prec=1 and rec=1 |
| **정규화** | normalize_for_eval, normalize_polarity | gold/parse/eval 동일 체인 |
| **Arbiter 규칙** | _arbiter_vote (Rule 1~4) | conflict_review_runner.py |

---

## 8. 참고 문서

| 문서 | 설명 |
|------|------|
| [README_cr_v1.md](README_cr_v1.md) | CR v1 개요 |
| [cr_v1_spec_and_conventions.md](cr_v1_spec_and_conventions.md) | CR v1 Spec·규약 (작업 원칙, 정규화, Debug, Sanity) |
| [cr_branch_metrics_spec.md](cr_branch_metrics_spec.md) | CR 메트릭 명세 |
| [normalization_rules_and_locations.md](normalization_rules_and_locations.md) | 정규화 규칙·발생 지점 |
| [stage_delta_ssot_checklist.md](stage_delta_ssot_checklist.md) | stage_delta SSOT |
| [protocol_conflict_review_vs_legacy_comparison.md](protocol_conflict_review_vs_legacy_comparison.md) | CR vs Legacy 비교 |
