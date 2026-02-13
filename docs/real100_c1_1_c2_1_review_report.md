# real100 c1_1 / c2_1 검토 보고서

검토일: 2025-02-09  
대상: `results/experiment_real_n100_seed1_c1_1__seed1_proposed`, `results/experiment_real_n100_seed1_c2_1__seed1_proposed`

---

## 1. Triptych: final_pairs가 0인지 아닌지 (상위 5행만)

**c1_1** `derived/tables/triptych_table.tsv` (데이터 5행):

| 행 | text_id | final_n_pairs | final_pairs |
|----|---------|---------------|-------------|
| 1 | nikluge-sa-2022-train-02669 | 2 | 컨실러\|neutral;컨실러\|positive |
| 2 | nikluge-sa-2022-train-02211 | 2 | 라임리치향\|neutral;라임리치향\|positive |
| 3 | nikluge-sa-2022-train-01786 | 2 | 파우치\|neutral;파우치\|positive |
| 4 | nikluge-sa-2022-train-02482 | 6 | 발림성\|negative;…;피부\|neutral |
| 5 | nikluge-sa-2022-train-01939 | 3 | 머리부터 발끝까지…;잔향\|neutral;잔향\|positive |

**c2_1** `derived/tables/triptych_table.tsv` (데이터 5행):

| 행 | text_id | final_n_pairs | final_pairs |
|----|---------|---------------|-------------|
| 1 | nikluge-sa-2022-train-02669 | 2 | 컨실러\|neutral;컨실러\|positive |
| 2 | nikluge-sa-2022-train-02211 | 2 | 라임리치향\|neutral;라임리치향\|positive |
| 3 | nikluge-sa-2022-train-01786 | 2 | 파우치\|neutral;파우치\|positive |
| 4 | nikluge-sa-2022-train-02482 | 4 | 발림성\|positive;…;피부\|neutral |
| 5 | nikluge-sa-2022-train-01939 | 4 | 머리부터 발끝까지\|neutral;…;잔향\|positive |

**결론**: 상위 5행 모두 **final_n_pairs > 0**. final_pairs가 0인 행 없음.

---

## 2. Scorecard raw JSON에서 `final_aspects` 키 실제 위치

**실제 위치** (scorecard 한 줄 기준):

- **경로**: `runtime.parsed_output.final_result.final_aspects`
- **동일 객체 내**: `runtime.parsed_output.final_result` 아래에 `final_tuples`, `final_aspects`, `stage1_tuples`, `stage2_tuples`, `label`, `confidence`, `rationale` 등이 함께 존재.

**확인 방법**: c1_1 scorecards.jsonl 첫 줄에서

- `runtime.parsed_output` 상위 키: `meta`, `stage1_ate`, `stage1_atsa`, …, `process_trace`, `analysis_flags`, **`final_result`**, `aux_signals` 등
- `final_result` 키: `label`, `confidence`, `rationale`, **`final_aspects`**, `stage1_tuples`, `stage2_tuples`, **`final_tuples`**

즉, scorecard에는 **`final_aspects`**가 **`runtime.parsed_output.final_result`** 안에 있으며, pipeline 출력이 그대로 `runtime.parsed_output`에 들어간 구조와 일치함.

---

## 3. Aggregator `_extract_final_tuples`가 그 키를 참조하는지

**참조함.**

- **파일**: `scripts/structural_error_aggregator.py`
- **함수**: `_extract_final_tuples_with_source` (218–237행), `_extract_final_tuples`(241–243행)는 그 결과의 tuple set만 반환.

**우선순위**:

1. `parsed = record["runtime"]["parsed_output"]`, `final_result = parsed.get("final_result")`
2. **`final_result.get("final_tuples")`** → 있으면 리스트를 tuple set으로 변환해 반환 (source: `final_tuples`)
3. 없으면 **`final_result.get("final_aspects")`** → 있으면 `tuples_from_list(final_aspects)`로 변환해 반환 (source: `final_aspects`)
4. 없으면 `record.get("inputs", {}).get("aspect_sentiments")` (source: `inputs.aspect_sentiments`)

real100 c1_1/c2_1 scorecard에서는 `final_result.final_tuples`가 채워져 있어, 현재 데이터에서는 **final_tuples**가 사용되고 **final_aspects**는 fallback으로만 정의되어 있음.  
코드 상으로는 **`final_aspects` 키를 반드시 참조**하며, `final_tuples`가 비어 있거나 없을 때 사용됨.

---

## 4. N_gold_explicit / N_gold_implicit 분류 함수가 gold row에서 보는 키와 정책

**함수**: `_split_gold_explicit_implicit` (156–168행)

**gold 입력**: `_extract_gold_tuples(record)` → **`inputs.gold_tuples`** (또는 상위 `gold_tuples`).  
각 gold 항목은 **(aspect_ref, aspect_term, polarity)** 3-tuple.

**분류 기준**:

- 한 gold tuple `(a, t, p)`에 대해  
  `tn = normalize_for_eval((t or "").strip())`
- **`tn`이 비지 않으면** → explicit
- **`tn`이 비면** → implicit (즉 **aspect_term == ""** 또는 정규화 후 빈 문자열이면 implicit)

**정리**:

- **참조 키**: gold는 **`inputs.gold_tuples`** (또는 record 상위 `gold_tuples`)에서 옴.
- **분류에 쓰는 필드**: tuple의 **두 번째 요소 `aspect_term`**.
- **정책**: **aspect_term이 빈 문자열(또는 정규화 후 빈 문자열)이면 implicit, 아니면 explicit** → “aspect_term=="" 유지” 정책과 일치.

---

## 5. 대표 선택(after_rep) 로직: “판정”만 vs “출력”에도 반영 여부

**대표 선택 로직**:

- **함수**: `select_representative_tuples(record)` (681–708행)  
  - `_get_final_tuples_raw(record)`로 raw final tuples를 가져온 뒤,  
  - aspect_norm별로 묶고, explicit > confidence > drop_reason 없음 순으로 정렬해 **aspect당 1개 대표 tuple** 선택.

**사용처**:

- **`has_polarity_conflict_after_representative(record)`** (726–749행): 대표 선택 후에도 동일 aspect에 서로 다른 polarity가 남아 있으면 True.
- 이 값이 **`polarity_conflict_after_rep`** (및 `polarity_conflict_rate_after_rep`) 등 **판정/메트릭**에만 사용됨.

**출력(F1·Triptych) 쪽**:

- **F1 / Triptych에 쓰이는 final tuple set**: **`_extract_final_tuples(record)`** (또는 `_extract_final_tuples_with_source`)만 사용.
- 이 함수는 **`final_result.final_tuples` → `final_aspects` → `inputs.aspect_sentiments`** 순으로 읽으며, **대표 선택을 적용하지 않음**.

**결론**:

- **대표 선택(after_rep) 로직은 “판정”에만 사용됨**  
  (polarity conflict 여부: `polarity_conflict_after_rep`, `polarity_conflict_rate_after_rep` 등).
- **Triptych/F1에 쓰이는 “출력” final pairs는 대표 선택을 거치지 않고**, pipeline이 저장한 `final_tuples`(또는 fallback으로 `final_aspects`/`inputs.aspect_sentiments`)를 그대로 사용함.

---

## 요약 표

| 항목 | 결과 |
|------|------|
| Triptych 상위 5행 final_pairs | 모두 > 0 (0인 행 없음) |
| final_aspects 위치 | `runtime.parsed_output.final_result.final_aspects` |
| aggregator가 final_aspects 참조 | 예 (final_tuples 다음 fallback) |
| N_gold explicit/implicit 참조 키 | gold: `inputs.gold_tuples`; 분류는 tuple의 **aspect_term** (빈 문자열 → implicit) |
| after_rep 로직 | 판정( polar conflict after rep)에만 사용, **출력(F1/Triptych)에는 미반영** |
