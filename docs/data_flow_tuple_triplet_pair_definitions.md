# 데이터 플로우: 튜플·트리플·페어 정의 및 스코어카드·메트릭 집계

---

## 1. 용어 정의 (CR v2)

| 용어 | 정의 | 필드/구조 | 용도 |
|------|------|-----------|------|
| **GoldUnit** | 주평가 키 | `(aspect_ref, polarity)` | Ref-level F1 (본문) |
| **SurfaceUnit** | 보조평가 키 | `(aspect_term, polarity)` | Explicit-only (Appendix) |
| **EvalTuple** | 내부 평가용 3-tuple | `(aspect_ref, aspect_term, polarity)` | 추출·정규화 후 집합 연산 |
| **Triplet** | 에이전트 원본 | `ASTETripletItem` | 파이프라인 입출력 |

**선언**: In CR v2, the primary evaluation unit is **(aspect_ref, polarity)**. Surface-level aspect terms are used only for auxiliary grounding analysis. See `docs/evaluation_cr_v2.md`.

---

## 2. 필드 구조: aspect_ref vs aspect_term vs opinion_term

### 2.1 골드 (gold_tuples / gold_triplets)

**형식**: `{aspect_ref, aspect_term, polarity}` (또는 legacy: `{aspect_ref, opinion_term: {term}, polarity}`)

| 필드 | 의미 | 예시 |
|------|------|------|
| **aspect_ref** | 택소노미/카테고리 (NIKLuge annotation ann[0]) | `제품 전체#일반`, `본품#품질` |
| **aspect_term** | 문장 내 관점 표면형 (OTE, 평가 대상) | `아이립밤`, `사이즈`, `마스크팩` |
| **opinion_term** | (legacy) opinion_term.term → aspect_term으로 해석 | gold_triplets 호환용 |

**NIKLuge annotation → gold_tuples 변환** (`make_beta_n50_dataset.annotation_to_gold_tuples`):
- `ann[0]` → aspect_ref (택소노미)
- `ann[1]` → span_info → aspect_term (span 텍스트 또는 span_info[0])
- `ann[2]` → polarity

**aspect_ref#aspect_term 형식 아님**. aspect_ref와 aspect_term은 **별도 필드**로 저장.

---

### 2.2 CR 에이전트 출력 (ASTETripletItem)

| 필드 | 타입 | 의미 |
|------|------|------|
| **aspect_term** | str (required) | OTE, 평가 대상 표면형 |
| **aspect_ref** | Optional[str] | 택소노미/정규화 참조 (대부분 null) |
| **opinion_term** | Optional[str] | 감성 표현 (opinion word) — aspect_term과 구분 |
| **polarity** | str | positive/negative/neutral/mixed |

**CR 파이프라인**: `_triplet_to_candidate` → `{aspect_term, aspect_ref, polarity, evidence, span, ...}`. opinion_term은 후속 평가 경로에서 사용하지 않음.

---

### 2.3 final_result (stage1_tuples, final_tuples)

```python
{"aspect_ref": str, "aspect_term": str, "polarity": str}
```

- aspect_ref: `d.get("aspect_ref") or ""`
- aspect_term: `d.get("aspect_term") or ""`
- opinion_term 없음 (튜플 형태로 단순화)

---

## 3. 에이전트별 산출물 및 행 이름

### 3.1 CR Stage1 (P-NEG, P-IMP, P-LIT)

| 에이전트 | 산출물 | 구조 | 저장 위치 |
|----------|--------|------|-----------|
| P-NEG | triplets | `ASTETripletItem[]` | process_trace[agent=P-NEG].output.triplets |
| P-IMP | triplets | `ASTETripletItem[]` | process_trace[agent=P-IMP].output.triplets |
| P-LIT | triplets | `ASTETripletItem[]` | process_trace[agent=P-LIT].output.triplets |

**Triplet 필드**: aspect_term, aspect_ref, opinion_term, polarity, evidence, span, confidence, rationale

### 3.2 Merge → candidates

`{tuple_id, aspect_term, aspect_ref, polarity, evidence, span, origin_agent}`

### 3.3 Review (A, B, C) → arb_actions

`{action_type, target_tuple_ids, new_value?, reason_code, actor}` — 튜플 자체는 변경하지 않음.

### 3.4 FinalResult

| 필드 | 내용 |
|------|------|
| stage1_tuples | `[{aspect_ref, aspect_term, polarity}]` (candidates에서 변환) |
| final_tuples | `[{aspect_ref, aspect_term, polarity}]` (final_candidates에서 변환) |
| final_aspects | `[{aspect_term: {term, span}, polarity, evidence}]` (표시용) |

---

## 4. 스코어카드 행 구조

### 4.1 행 식별 (row key)

| 구분 | 필드 | 설명 |
|------|------|------|
| **단일 런** | `meta.text_id` 또는 `runtime.uid` | 샘플당 1행 |
| **병합 런** | `meta.case_id` 또는 `meta.text_id` | 동일 text_id에 여러 run_id 행 |

**파일**: `results/<run_id>/scorecards.jsonl` — 한 줄에 한 JSON 객체(한 행).

### 4.2 스코어카드 필드 (튜플 관련)

| 필드 | 경로 | 내용 |
|------|------|------|
| gold | `inputs.gold_tuples` | `[{aspect_ref, aspect_term, polarity}]` |
| stage1 | `runtime.parsed_output.final_result.stage1_tuples` | `[{aspect_ref, aspect_term, polarity}]` |
| final | `runtime.parsed_output.final_result.final_tuples` | `[{aspect_ref, aspect_term, polarity}]` |
| process_trace | `runtime.parsed_output.process_trace` | P-NEG/P-IMP/P-LIT raw triplets |

---

## 5. 메트릭 채점·집계

### 5.1 추출 함수 (structural_error_aggregator)

| 데이터 | SSOT | 추출 함수 | 출력 형태 |
|--------|------|-----------|-----------|
| gold | inputs.gold_tuples | _extract_gold_tuples | `Set[(a, t, p)]` EvalTuple |
| stage1 | final_result.stage1_tuples | _extract_stage1_tuples | `Set[(a, t, p)]` |
| final | final_result.final_tuples | _extract_final_tuples | `Set[(a, t, p)]` |

**_tuples_from_list_of_dicts** 변환 규칙:
- aspect_ref: `it.get("aspect_ref") or ""`
- aspect_term: `_aspect_term_text(it)` → aspect_term (str 또는 dict.term) 또는 opinion_term.term (legacy)
- polarity: `normalize_polarity(...)`

### 5.2 Pair 변환 (F1용)

| 함수 | Pair 키 | 사용처 |
|------|---------|--------|
| tuples_to_pairs | `(aspect_term, polarity)` | stage_delta.changed, F1 (P0) |
| tuples_to_pairs_ref_fallback | `(aspect_ref or aspect_term, polarity)` | match_by_aspect_ref=True 시 (현재 미사용) |

**P0**: F1/break/fix는 `(aspect_term, polarity)`만 사용. aspect_ref는 메타데이터.

### 5.3 집계 출력 (structural_metrics.csv)

**본문 표**: Ref_F1_S1, Ref_F1_S2, Delta, Break, Fix (aspect_ref 기반)

| 컬럼 예 | 의미 |
|---------|------|
| tuple_f1_s1 | gold vs stage1 Ref F1 |
| tuple_f1_s2 | gold vs final Ref F1 |
| delta_f1 | tuple_f1_s2 - tuple_f1_s1 |
| fix_rate | stage1 오답→final 정답 비율 |
| break_rate | stage1 정답→final 오답 비율 |
| N_gold | gold 있는 행 수 |
| N_gold_total_pairs | gold pair 총 개수 |

**Appendix**: tuple_f1_explicit, precision_explicit, recall_explicit (SurfaceUnit), invalid_target_rate, OTE_Null_Rate

**행 단위**: scorecard 1행 = 1샘플. 집계는 전체 행에 대해 합산/비율 계산.

---

## 6. 요약

| 구분 | aspect_ref | aspect_term | opinion_term |
|------|------------|-------------|--------------|
| **골드** | 택소노미 (제품 전체#일반) | OTE 표면형 | legacy: opinion_term.term→aspect_term |
| **CR triplet** | optional, 대부분 null | OTE (필수) | 감성 표현 (별도 필드) |
| **튜플 (EvalTuple)** | (a, t, p) 중 a | (a, t, p) 중 t | 사용 안 함 |
| **주평가 (GoldUnit)** | **(a, p)** 키 | — | Ref-level F1 |
| **보조평가 (SurfaceUnit)** | — | **(t, p)** 키 | Explicit-only Appendix |

**CR v2**: 주평가는 (aspect_ref, polarity). aspect_ref#aspect_term 형식은 사용하지 않음.
