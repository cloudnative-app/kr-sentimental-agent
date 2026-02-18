# CR v1 aspect_ref 설정·에이전트 작업·추출·메트릭 반영

---

## 1. aspect_ref: 입력 금지인가?

**아니요. 금지가 아닙니다.** 선택(optional) 필드이며, 출력 가능합니다.

| 구분 | 설정 | 위치 |
|------|------|------|
| **스키마** | `aspect_ref: Optional[str] = Field(default=None)` | `schemas/protocol_conflict_review.py` ASTETripletItem |
| **P-NEG** | `aspect_ref (optional)` — 출력 가능, 필수 아님 | `agents/prompts/perspective_pneg_stage1.md` |
| **P-IMP** | `If the aspect is implicit, set aspect_ref when possible` — 암시적 관점 시 설정 권장 | `agents/prompts/perspective_pimp_stage1.md` |
| **P-LIT** | `aspect_ref (optional)` — 출력 가능, 필수 아님 | `agents/prompts/perspective_plit_stage1.md` |

**실제 동작**: LLM이 대부분 `aspect_ref`를 비워둠(생략). P-IMP만 암시적 관점 시 설정하라고 명시되어 있으나, 실제 출력에서는 자주 생략됨.

**파이프라인 정책 (P1)**: `_finalize_normalize_ref`는 **No-op**. aspect_ref를 덮어쓰지 않고 원본을 그대로 유지함.

---

## 2. 단계별 에이전트 작업·추출 대상

### 2.1 Stage1: P-NEG, P-IMP, P-LIT

| 에이전트 | 작업 | 출력 | aspect_ref |
|----------|------|------|------------|
| P-NEG | 부정/대비 관점 ASTE | `ASTETripletItem` 리스트 | optional, 대부분 null |
| P-IMP | 암시적 관점 ASTE | `ASTETripletItem` 리스트 | implicit 시 설정 권장 |
| P-LIT | 문자적 관점 ASTE | `ASTETripletItem` 리스트 | optional, 대부분 null |

**추출**: `_triplet_to_candidate(t)` → `aspect_ref: t.aspect_ref` 그대로 전달. LLM이 null이면 `None` → 후속에서 `""`로 변환.

### 2.2 Merge

| 작업 | 입력 | 출력 |
|------|------|------|
| A(r_neg) + B(r_imp) + C(r_lit) | triplets | candidates (tuple_id, aspect_term, aspect_ref, polarity, ...) |

**추출**: candidates 그대로. aspect_ref 변경 없음.

### 2.3 Review: A, B, C

| 에이전트 | 작업 | 출력 | tuple 변경 |
|----------|------|------|------------|
| ReviewA | conflict_flags 기반 리뷰 | review_actions (DROP/MERGE/FLIP/KEEP/FLAG) | 없음 |
| ReviewB | implicit/aspect_ref 불일치 등 | review_actions | 없음 |
| ReviewC | explicit evidence 검토 | review_actions | 없음 |

**추출**: review_actions만. tuple의 aspect_ref는 수정하지 않음.

### 2.4 Arbiter

| 작업 | 입력 | 출력 |
|------|------|------|
| 다수결 + Rule 3 | actions_by_tuple | arb_actions (KEEP/DROP/FLIP) |

**추출**: arb_actions. MERGE는 KEEP으로 대체. aspect_ref 변경 없음.

### 2.5 Apply + Finalize

| 단계 | 작업 | aspect_ref |
|------|------|------------|
| _apply_review_actions | DROP 제거, FLIP 극성 변경 | 변경 없음 |
| _finalize_normalize_ref | **No-op (P1)** | 덮어쓰지 않음, 원본 유지 |

### 2.6 FinalResult 빌드

```python
def _tup(d):
    return {
        "aspect_ref": (d.get("aspect_ref") or ""),
        "aspect_term": (d.get("aspect_term") or ""),
        "polarity": (d.get("polarity") or "neutral"),
    }
stage1_tuples = [_tup(c) for c in candidates]
final_tuples = [_tup(c) for c in final_candidates]
```

**추출 대상**: `final_result.stage1_tuples`, `final_result.final_tuples`. 둘 다 `{aspect_ref, aspect_term, polarity}` 형태.

---

## 3. 메트릭에 반영되는 데이터

### 3.1 추출 함수 (structural_error_aggregator)

| 데이터 | SSOT | 추출 함수 | 튜플 형태 |
|--------|------|-----------|-----------|
| gold | inputs.gold_tuples | _extract_gold_tuples | (aspect_ref, aspect_term, polarity) |
| stage1 | final_result.stage1_tuples | _extract_stage1_tuples | (aspect_ref, aspect_term, polarity) |
| final | final_result.final_tuples | _extract_final_tuples | (aspect_ref, aspect_term, polarity) |

`_tuples_from_list_of_dicts`: `aspect_ref`, `aspect_term`, `polarity`를 모두 읽어 `(a, t, p)` 튜플로 변환.

### 3.2 메트릭 계산 시 aspect_ref 사용 여부

| 메트릭 | 사용 함수 | aspect_ref 사용 | 비고 |
|--------|-----------|-----------------|------|
| **F1** (tuple_f1_s1, tuple_f1_s2) | precision_recall_f1_tuple | **미사용** | match_by_aspect_ref=False (P0) |
| **pairs** (changed 판단) | tuples_to_pairs | **미사용** | (aspect_term, polarity)만 사용 |
| **stage_delta.changed** | s1_pairs != s2_pairs | **미사용** | pairs 기반 |
| **fix/break** | tuple_sets_match_with_empty_rule | **미사용** | match_by_aspect_ref=False |
| **guided/unguided** | review_actions/arb_actions 존재 여부 | - | change_type 분류 |

### 3.3 tuples_to_pairs vs tuples_to_pairs_ref_fallback

| 함수 | pair 키 | 용도 |
|------|---------|------|
| tuples_to_pairs | (aspect_term, polarity) | stage_delta.changed, F1 pred (match_by_aspect_ref=False) |
| tuples_to_pairs_ref_fallback | (aspect_ref or aspect_term, polarity) | match_by_aspect_ref=True 시에만 (현재 미사용) |

**P0**: 평가 키는 (aspect_term, polarity)만 사용. aspect_ref는 부가 메타데이터이며 F1/break/fix에 사용하지 않음.

---

## 4. 요약

| 질문 | 답변 |
|------|------|
| aspect_ref 입력 금지? | **아님**. optional 필드, 출력 가능 |
| 출력 작업 금지? | **아님**. P-IMP는 implicit 시 설정 권장 |
| 왜 비어 있나? | LLM이 optional 필드를 자주 생략함 |
| 파이프라인에서 덮어쓰기? | **아님**. _finalize_normalize_ref는 No-op (P1) |
| 메트릭에 반영? | **아님**. F1/changed/fix/break는 (aspect_term, polarity)만 사용 (P0) |

---

## 5. 참고

- [cr_v1_workflow_metrics_and_rules.md](cr_v1_workflow_metrics_and_rules.md) — 워크플로우·규칙
- [normalization_rules_and_locations.md](normalization_rules_and_locations.md) — 정규화
- [ghost_change_fix_summary.md](ghost_change_fix_summary.md) — P0/P1 정책
