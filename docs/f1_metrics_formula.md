# F1 메트릭 정리 및 산출 공식

## 1. 집계되는 F1 지표 요약

| 지표명 | 의미 | 산출 단위 |
|--------|------|-----------|
| **tuple_f1_s1** | Stage1 예측 vs gold F1 | 샘플당 F1의 **평균** (gold 있는 샘플만) |
| **tuple_f1_s2** | Stage2+Mod 최종 예측 vs gold F1 | 샘플당 F1의 **평균** |
| **tuple_f1_s2_overall** | tuple_f1_s2와 동일 (참조용) | 동일 |
| **tuple_f1_s2_explicit_only** | gold 중 **explicit만** vs s2 F1 | explicit gold 있는 샘플만 평균 |
| **tuple_f1_s2_implicit_only** | gold 중 **implicit만** (aspect_term=="") vs s2 valid polarity; set 기반 P/R/F1 | implicit gold 있는 샘플만 평균 |
| **tuple_f1_s2_raw** | s2(raw final_tuples) vs gold F1 | tuple_f1_s2와 동일(동일 pred 사용) |
| **tuple_f1_s2_after_rep** | 대표 tuple 선택 후(s2_after_rep) vs gold F1 | 샘플당 F1의 평균 |
| **triplet_f1_s1** / **triplet_f1_s2** | tuple_f1_s1 / tuple_f1_s2와 동일 (deprecated alias) | 동일 |
| **delta_f1** | tuple_f1_s2 − tuple_f1_s1 | 스칼라 |

- **데이터 출처**: `scripts/structural_error_aggregator.py` → `compute_stage2_correction_metrics()`, 산출물은 `derived/metrics/structural_metrics.csv` 등.
- **Gold 없음**: gold pair가 0인 run은 F1 계열·delta_f1 모두 미계산(N/A).

---

## 2. 기본 F1 산출 공식 (샘플 1개)

위치: `metrics/eval_tuple.py` — `precision_recall_f1_tuple(gold_tuples, pred_tuples, ...)`.

### 2.1 매칭 단위

- **Gold 쌍**: 항상 `(aspect_term, polarity)`. `aspect_ref`는 사용 안 함.
- **Pred 쌍**: 기본 `match_by_aspect_ref=True` → `(aspect_ref or aspect_term, polarity)` (ref 없으면 term만).
- 정규화: `normalize_for_eval(문자열)`, `normalize_polarity(극성)` → (term, polarity) 쌍으로 집합 생성.

### 2.2 TP/FP/FN (match_empty_aspect_by_polarity_only=True, 기본)

- **exact_gold**: aspect_term ≠ "" 인 gold 쌍.
- **polarity_only_gold**: aspect_term == "" 인 gold 쌍.
- **TP**:
  - `tp_exact` = |pred_pairs ∩ exact_gold|
  - polarity_only gold 각각에 대해, 아직 매칭 안 된 pred 중 **같은 polarity**인 쌍 하나씩 1:1 매칭 → `tp_polarity`
  - **tp = tp_exact + tp_polarity**
- **FP** = |pred_pairs| − tp  
- **FN** = |gold_pairs| − tp  

### 2.3 Precision / Recall / F1

- **Precision** = TP / (TP + FP)  (분모 0이면 0)
- **Recall**    = TP / (TP + FN)   (분모 0이면 0)
- **F1**       = 2 × P × R / (P + R)  (P+R=0이면 0)

즉, **F1 = 2 × (TP) / (2×TP + FP + FN)**.

---

## 3. Run 단위 집계 공식 (structural_error_aggregator)

- **대상**: `gold_tuples`가 존재하고 비어 있지 않은 샘플만. 개수 `N = len(rows_with_gold)`.
- **샘플별 입력**:
  - **gold**: `_extract_gold_tuples(record)` (gold_tuples/gold_triplets)
  - **s1**: `_extract_stage1_tuples(record)` (Stage1 ATSA → tuple set)
  - **s2**: `_extract_final_tuples(record)` (final_result.final_tuples)
  - **s2_after_rep**: `select_representative_tuples(record)` (aspect_norm당 대표 1개 선택)

집계:

- **tuple_f1_s1** = (1/N) × Σᵢ F1(goldᵢ, s1ᵢ)
- **tuple_f1_s2** = (1/N) × Σᵢ F1(goldᵢ, s2ᵢ)
- **tuple_f1_s2_raw** = tuple_f1_s2 (동일 pred = s2)
- **tuple_f1_s2_after_rep** = (1/N) × Σᵢ F1(goldᵢ, s2_after_repᵢ)
- **tuple_f1_s2_explicit_only**: gold 중 aspect_term이 비어 있지 않은 것만 모은 `gold_explicit`에 대해, 해당하는 샘플만 골라 F1(gold_explicitᵢ, s2ᵢ)의 평균.
- **delta_f1** = tuple_f1_s2 − tuple_f1_s1

---

## 4. 참고

- **문서**: `docs/absa_tuple_eval.md` — gold/채점 기준/용어.
- **대표 선택**: `select_representative_tuples()` — aspect_norm별로 explicit > implicit, confidence 내림차순, drop_reason 없음 순으로 정렬 후 첫 번째만 사용.
- **Sanity check**: gold→gold, stage1→stage1, final→final 각각 F1=1 기대 (`scripts/structural_error_aggregator.py` `--sanity_check`).

---

## 5. Implicit-only F1 및 invalid rate

- **Implicit gold**: gold pair 중 `aspect_term == ""` (정규화 후). polarity는 `{positive, negative, neutral}`.
- **Valid pred**: polarity가 존재하고 정규화 후 `{positive, negative, neutral}`. 그 외는 invalid.
- **tuple_f1_s2_implicit_only**: implicit gold가 있는 샘플만 대상, gold implicit polarity set vs pred valid polarity set으로 set 기반 P/R/F1 후 샘플 평균.
- **implicit_invalid_pred_rate**: 분모 = implicit gold가 존재하는 샘플 수, 분자 = 그 중 “implicit polarity pred가 유효하게 0개” 또는 파싱 실패 또는 금지된 neutral fallback이 발생한 샘플 수.  
  invalid에 포함: polarity 누락/빈문자열/unknown, 파싱 실패(해당 샘플), 금지된 neutral fallback(플래그 기반).
- **implicit_gold_sample_n** / **implicit_invalid_sample_n**: 위 분모·분자 (보조치).
