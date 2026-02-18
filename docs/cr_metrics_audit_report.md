# CR 브랜치 메트릭·Conflict·Ref 집계 감사 보고서

요청된 정보 확인 결과. CR 브랜치 코드 수정 없이 검토만 수행.

---

## 1. 공통 전제 정보

### 1.1 현재 conflict 계산 위치

| 항목 | 내용 |
|------|------|
| **파일 경로** | `scripts/structural_error_aggregator.py` |
| **함수명** | `has_polarity_conflict_raw`, `has_polarity_conflict_after_representative`, `has_same_aspect_polarity_conflict` |
| **입력 단위** | **record** (scorecard 1행 = 1 sample) |
| **현재 conflict 기준** | **term 기준** (`aspect_term_norm`) |

**상세**:
- `has_polarity_conflict_raw`: `_get_final_tuples_raw(record)` → `by_aspect[key]` where `key = aspect_term_norm`
- `has_polarity_conflict_after_representative`: 동일하게 `aspect_term_norm`으로 그룹핑 후 대표 선택
- `_get_final_tuples_raw`는 `aspect_term_norm`만 사용. **aspect_ref 미사용**

**별도 conflict (추론 단계)**:
- `agents/conflict_review_runner.py` → `_compute_conflict_flags(candidates)`
- 입력: **candidates** (tuple 리스트, sample 내)
- 기준: **ref 기준 primary** (같은 aspect_ref + 다른 polarity), **term 기준 secondary** (ref 비어 있을 때)
- 이 conflict_flags는 **Review 트리거**용. aggregator의 polarity_conflict_rate와 **별개**

---

### 1.2 현재 ref 관련 집계 위치

| 메트릭 | 계산 함수 | 입력 단위 | gold 참조 | final vs stage1 |
|--------|-----------|-----------|-----------|-----------------|
| **ref_valid_rate** | `compute_stage2_correction_metrics` 내 인라인 | record | `_extract_gold_tuples` | **stage1** (s1) |
| **ref_fill_rate** | 동일 | record | — | **stage1** |
| **ref_coverage_rate** | 동일 | record | `tuples_to_ref_pairs(gold)` | **stage1** (s1 vs gold) |
| **implicit_invalid_pred_rate** | 동일 | record | `gold_implicit_polarities_from_tuples(gold)` | **final** (s2) |

**계산 위치**: `scripts/structural_error_aggregator.py` → `compute_stage2_correction_metrics()` (라인 403~687)

**ref_valid_rate / ref_fill_rate / ref_coverage_rate**:
```python
# stage1 pred 기준
for (_a, _t, _p) in (s1 or set()):
    ref = normalize_for_eval(_a) if _a else ""
    n_pred_total_ref += 1
    if ref:
        n_pred_with_ref += 1
        if is_valid_ref(ref):  # schemas.taxonomy
            n_pred_valid_ref += 1
gold_ref_pairs, _ = tuples_to_ref_pairs(gold)
pred_ref_pairs, _ = tuples_to_ref_pairs(s1 or set())
gold_refs_covered += len(gold_ref_pairs & pred_ref_pairs)
```

**implicit_invalid_pred_rate**:
- gold implicit: `gold_implicit_polarities_from_tuples(gold)` — aspect_term=="" 인 튜플의 polarity
- pred: `pred_valid_polarities_from_tuples(s2)` — final_tuples에서 polarity ∈ {pos, neg, neu}
- invalid 조건: `len(pred_valid_pols) == 0 or parse_fail or forbidden_fallback`

---

### 1.3 evaluation 단위 확인

**Primary matching 함수**: `metrics/eval_tuple.py` → `tuples_to_ref_pairs()`

| 확인 항목 | 결과 |
|-----------|------|
| **set 기반 매칭** | 예. `Set[EvalPair]` 반환, `pred_pairs & gold_pairs` 등 set 연산 |
| **multi-label 허용** | `match_empty_aspect_by_polarity_only=True` 시: gold aspect=="" 는 polarity만 매칭, pred와 1:1 매칭 |
| **empty ref 처리** | `ref == ""` 이면 **제외** (invalid_ref_count 증가), pairs에 포함 안 함 |

```python
# tuples_to_ref_pairs
for (a, _, p) in tuples_set:
    ref = normalize_for_eval(a) if a else ""
    if ref == "":
        invalid_ref_count += 1
        continue
    pairs.add((ref, normalize_polarity(p)))
```

---

## 2. 변경 대상 명세

### 2.1 conflict 정의를 ref-level로 확장

**현재 conflict 정의 코드**:
- `scripts/structural_error_aggregator.py`:
  - `has_polarity_conflict_raw` (라인 1026)
  - `has_polarity_conflict_after_representative` (라인 1039)
  - `has_same_aspect_polarity_conflict` (라인 1080, alias)

**term-level conflict 계산**:
- `by_aspect[key]` where `key = (it.get("aspect_term_norm") or "").strip()`
- `_get_final_tuples_raw`는 **aspect_ref를 추출하지 않음** (aspect_term_norm만 사용)

**ref-level polarity grouping 가능 여부**:
- `_extract_final_tuples(record)` → `tuples_from_list(final_tuples)` → EvalTuple = (aspect_ref, aspect_term, polarity)
- `final_tuples` 스키마에 `aspect_ref` 필드 있음 (`schemas/protocol_conflict_review.py` ASTETripletItem)
- `tuples_from_list`는 `it.get("aspect_ref")` 사용 → **ref-level grouping 가능**

**final_tuples 구조 예시** (CR pipeline):
```python
# final_result.final_tuples 각 항목
{"aspect_term": "성능", "aspect_ref": "본품#품질", "polarity": "positive", "confidence": 0.8, ...}
{"aspect_term": "가격", "aspect_ref": "제품 전체#가격", "polarity": "negative", ...}
{"aspect_term": "", "aspect_ref": "본품#일반", "polarity": "neutral", "is_implicit": True, ...}
```

**확인 필요**:
- 동일 aspect_ref에 polarity set 길이 > 1 인지? → **가능** (aspect_ref로 그룹핑 후 pols 집합 확인)
- explicit null 허용? → `aspect_ref`가 None/"" 이면 `tuples_to_ref_pairs`에서 제외
- DROP된 tuple 제외? → `_get_final_tuples_raw`는 `final_tuples` 그대로 사용. DROP은 `_apply_review_actions`에서 제거되므로 **final_tuples에는 DROP된 tuple 없음**

---

### 2.2 Construct Integrity Block 추가

**export_paper_metrics_aggregated.py 내부**:
- Table 1A 생성: `main()` → `build_section(PAPER_METRICS_TABLE_1A)` → `to_markdown_table(table_1a_rows, ["metric", "value"])`
- 위치: 라인 374~385

**출력 포맷**: **Markdown만** (`paper_metrics_aggregated.md`)

**현재 Table 1A 메트릭 순서**:
```
tuple_f1_s1_refpol, tuple_f1_s2_refpol, delta_f1_refpol,
fix_rate_refpol, break_rate_refpol, net_gain_refpol,
implicit_invalid_pred_rate,
ref_fill_rate, ref_valid_rate, ref_coverage_rate,
N_agg_fallback_used
```

**결정 필요**:
- Table 1A 내 하위 블록으로 표시? (예: "Outcome" / "Construct Integrity" 구분)
- 별도 subsection? (예: "## Table 1A-2. Construct Integrity")
- 순서 유지? (현재 ref_* 가 implicit_invalid_pred_rate 다음에 옴)

---

### 2.3 implicit_invalid_pred_rate 해석 분리

**계산 함수**: `compute_stage2_correction_metrics` 내 (라인 554~565)

**gold implicit 판별**: `_split_gold_explicit_implicit` → `aspect_term` 정규화 후 `""` 이면 implicit

**pred_valid_polars 정의**: `pred_valid_polarities_from_tuples(s2)` → polarity ∈ {positive, negative, neutral} 만 수집. mixed/빈값/unknown → invalid

**invalid_implicit 조건** (OR):
1. `len(pred_valid_pols) == 0` — pred에 유효 polarity 없음
2. `parse_fail` — `_record_parse_failed(record)` (parse_failed, generate_failed, runtime.error)
3. `forbidden_fallback` — `_record_has_forbidden_neutral_fallback(record)` (polarity 빈값 → neutral 기본값 사용)

**coverage 실패 vs polarity 실패 구분**: **현재 구분 안 함**. 하나의 `invalid_implicit` 플래그로만 집계.

**분리 집계 후보**:
| 구분 | 정의 | 현재 포함 여부 |
|------|------|----------------|
| **implicit coverage failure** | gold implicit 있는데 pred에 해당 polarity가 아예 없음 (len=0) | ✅ (len==0에 포함) |
| **implicit polarity failure** | pred에 polarity는 있으나 gold와 불일치 (F1 낮음) | ❌ (implicit_invalid_pred_rate와 별개, tuple_f1_s2_implicit_only로 별도) |
| **implicit null assignment** | pred가 polarity를 빈값/unknown으로 둠 → forbidden_neutral_fallback | ✅ (forbidden_fallback에 포함) |

**판단**: coverage 실패(len=0)와 null/fallback 실패(forbidden_fallback)는 **현재 하나로 합쳐짐**. parse_fail은 별도. 분리하려면 `n_implicit_invalid_samples`를 `n_implicit_coverage_fail`, `n_implicit_null_fail`, `n_implicit_parse_fail` 등으로 쪼개야 함.

---

## 3. 요약 표

| 항목 | 현재 상태 |
|------|-----------|
| aggregator conflict | term 기준 (aspect_term_norm) |
| conflict_review_runner conflict | ref 기준 primary, term 기준 secondary |
| ref_* 메트릭 기준 | stage1 (s1) |
| implicit_invalid 기준 | final (s2), gold implicit 샘플만 |
| tuples_to_ref_pairs | set 기반, empty ref 제외 |
| Table 1A 출력 | Markdown, 단일 테이블 |
| implicit_invalid 세분화 | 미구현 (coverage/null/parse 합침) |
