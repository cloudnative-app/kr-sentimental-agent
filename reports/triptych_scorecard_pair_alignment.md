# Triptych vs Scorecard Pair 생성 경로 통일

목표: 01557 / 02917 / 00474 같은 mismatch 제거. triptych pair 생성이 scorecard/aggregator와 **동일한 추출 함수**를 쓰도록 통일.

---

## 1. 현재 경로 요약

| 경로 | 소스 | 추출 함수 | 비고 |
|------|------|----------|------|
| **Triptych** `final_pairs` | scorecard row | `_extract_final_tuples_with_source(record)` → `_tuples_from_list_of_dicts` → `tuples_to_pairs` | `final_result.final_tuples` → `final_aspects` → `inputs.aspect_sentiments` 순 fallback |
| **Scorecard 비교** (pipeline_integrity_verification) | `fr = runtime.parsed_output.final_result` | 인라인: `fr.get("final_tuples")` 순회, `it.get("aspect_term")` / `term.get("term")` | fallback 없음; 정규화 `_norm_t(sc_final)` vs `_norm_t(t_final.replace(";","").replace("|",""))` 로 비교 (형식 불일치 가능) |

- Triptych: `scripts/structural_error_aggregator.py` — `_triptych_row` → `_extract_final_tuples_with_source`, `_aspect_term_text`, `normalize_for_eval`, `normalize_polarity`, `tuples_to_pairs`.
- Scorecard 쪽 비교: `scripts/pipeline_integrity_verification.py` — `final_result.final_tuples`만 직접 순회, aspect_term 추출이 `_aspect_term_text`와 다를 수 있음.

---

## 2. Mismatch별 원인 및 조치

### 2.1. 00474 — `|neutral` (1순위)

| 항목 | 내용 |
|------|------|
| **Scorecard** | `인정|neutral` (final_result.final_tuples 기준) |
| **Triptych** | `|neutral` (aspect_term 빈 문자열) |
| **원인** | Triptych가 해당 레코드에서 `final_result.final_tuples`를 쓰지 못하고 **inputs.aspect_sentiments** fallback을 탄 경우. 또는 `final_tuples` 항목의 aspect_term이 dict/다른 필드로 저장돼 있어 `_aspect_term_text`가 ""를 반환하는 경우. |
| **해석** | `|neutral`은 “aspect_term이 빈 문자열로 정규화되거나, 다른 필드를 aspect_term로 잘못 읽는” 신호로 1순위로 잡아야 함. |
| **통일 조치** | (1) 두 경로 모두 **동일 추출**: `final_result.final_tuples` 우선, 항목별 `_aspect_term_text(it)` + `normalize_for_eval` / `normalize_polarity` 후 `tuples_to_pairs` 형태로 canon_pair 생성. (2) pipeline_integrity_verification의 scorecard 쪽도 aggregator의 `_extract_final_tuples(record)` 또는 `_get_final_tuples_raw` + 동일 정규화로 pairs 생성. (3) 00474 scorecard에 `final_tuples`가 있음에도 triptych가 fallback을 타면, triptych가 읽는 `record`(예: run_dir/scorecards 경로)와 검증 스크립트의 scorecard가 동일한지 확인. |

### 2.2. 01557 — 부작용 vs 부작용 걱정

| 항목 | 내용 |
|------|------|
| **Scorecard** | `가슴크림|neutral;미생물 발효기술|neutral;부작용|neutral` (일부 보고서에서는 `부작용`만 표기된 경우 있음) |
| **Triptych** | `가슴크림|neutral;미생물 발효기술|neutral;부작용 걱정|neutral` |
| **원인** | 동일 레코드에서 **final_tuples**와 **stage1_tuples/trace_atsa** 등 다른 소스의 aspect_term 표기가 다름(예: "부작용" vs "부작용 걱정"). 또는 scorecard 비교 시 사용하는 필드가 final_tuples가 아닌 다른 필드와 혼합됨. |
| **통일 조치** | Triptych와 scorecard 비교 모두 **final_result.final_tuples**만 사용하고, 동일한 `_aspect_term_text` + 정규화로 pair 생성. 그러면 “부작용”/“부작용 걱정” 중 하나로 통일되어 동일해져야 함. |

### 2.3. 02917 — term 개수/표현 차이

| 항목 | 내용 |
|------|------|
| **Scorecard** | `수분 공급|neutral;수분보호막|neutral;촉촉하고 생기있게|neutral` (3개) |
| **Triptych** | `생기|neutral;수분 공급|neutral;수분보호막|neutral;촉촉|neutral` (4개) |
| **원인** | Scorecard 쪽은 final_tuples에서 “촉촉하고 생기있게” 하나로, triptych는 stage1/다른 소스에서 “촉촉”, “생기” 등으로 분리되었을 가능성. 또는 final_tuples vs final_aspects/inputs 경로 차이. |
| **통일 조치** | **final_result.final_tuples** 단일 소스 + 동일 `_aspect_term_text` 적용 시, 같은 레코드라면 term 개수와 문자열이 맞춰져야 함. 변경 후 동일 여부 표에 반영. |

---

## 3. 통일 후 검증 결과

**코드 변경**: `pipeline_integrity_verification`에서 scorecard 쪽 pairs를 aggregator의 `_extract_final_tuples(record)` + `tuples_to_pairs`로 생성하고, canon_pair set으로 비교하도록 수정함.

**실행 결과** (run_dir=results/experiment_mini4_validation_c2_t1_proposed):  
- 비교 경로 통일 후 **mismatch 10건 → 3건**으로 감소 (02829, 00797, 01065, 01233, 01230, 01089, 00692 등은 동일 판정).
- 남은 3건: 00474, 01557, 02917.

| text_id | 왜 달랐는지 | 변경 후 동일해졌는지 |
|---------|-------------|----------------------|
| 00474 | Triptych가 해당 레코드에서 `final_tuples` 없이 **inputs.aspect_sentiments** fallback → `\|neutral` | **아직 불일치**. Scorecard는 `_extract_final_tuples`로 "인정\|neutral". Triptych TSV는 이전 빌드에서 fallback 사용. Triptych 재빌드 시 동일 run의 scorecards에 `final_tuples` 있으면 동일해짐. |
| 01557 | Scorecard final_tuples "부작용" vs Triptych "부작용 걱정" (다른 소스/필드) | **아직 불일치**. 단일 소스(final_tuples) + 동일 정규화로 통일 후 재빌드하면 동일 목표. |
| 02917 | Scorecard "촉촉하고 생기있게" 1개 vs Triptych "생기, 수분 공급, 수분보호막, 촉촉" 4개 | **아직 불일치**. final_tuples 단일 소스로 triptych 재빌드 시 동일해짐. |

---

## 4. 코드 변경 권장 사항

1. **공통 pair 추출**  
   - `structural_error_aggregator`: 이미 `_extract_final_tuples_with_source` → `_tuples_from_list_of_dicts` → `tuples_to_pairs` 사용.  
   - **pipeline_integrity_verification**: scorecard 쪽 pairs를 위와 동일하게 만들기 위해, aggregator의 `_extract_final_tuples(record)` 및 `tuples_to_pairs`를 import하여 사용.  
   - 비교 시: `canon_pair` set (정규화된 (aspect_term, polarity))로 비교하면, S2 canon recheck처럼 “표현 차이”만 제거된 진짜 불일치만 남김.

2. **비교 형식**  
   - pipeline_integrity_verification에서 `_norm_t(sc_final) != _norm_t(t_final.replace(";", "").replace("|", ""))` 제거하고,  
   - scorecard/triptych 모두 `_extract_final_tuples(record)` → `tuples_to_pairs` → 정렬된 문자열 또는 canon set 비교로 통일.

3. **Run 경로**  
   - Triptych 테이블 생성과 pipeline_integrity_verification이 **동일한 run_dir**(예: `results/experiment_mini4_validation_c2_t1_proposed`)의 scorecards를 사용하는지 확인.

이후 재실행 시 `reports/triptych_scorecard_pair_alignment.md`의 “변경 후 동일해졌는지” 열을 실제 결과로 갱신하면 됨.
