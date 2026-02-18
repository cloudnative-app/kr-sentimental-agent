# F1 점수 관련 메트릭 및 Gold–Pred 쌍 예시

CR v2 평가에서 사용하는 F1 메트릭과, 채점에 사용되는 gold vs pred 쌍 구조·예시를 정리합니다.

---

## 1. F1 메트릭 요약

| 메트릭 | 비교 대상 | Pair 단위 | 용도 |
|--------|-----------|-----------|------|
| **tuple_f1_s1_refpol** | gold vs stage1_tuples | (aspect_ref, polarity) | pre-review 품질 |
| **tuple_f1_s2_refpol** | gold vs final_tuples | (aspect_ref, polarity) | **주평가** (CR v2 primary) |
| **delta_f1_refpol** | — | — | tuple_f1_s2 − tuple_f1_s1 |
| **tuple_f1_s1_otepol** | gold vs stage1 | (aspect_term, polarity) | ABSA 호환 (보조) |
| **tuple_f1_s2_otepol** | gold vs final | (aspect_term, polarity) | ABSA 호환 (보조) |
| **tuple_f1_s1_attrpol** | gold vs stage1 | (attribute, polarity) | 진단용 (Table 1C) |
| **tuple_f1_s2_attrpol** | gold vs final | (attribute, polarity) | 진단용 |
| **tuple_f1_s2_explicit_only** | gold_explicit vs final | (aspect_ref, polarity) | explicit gold만 |
| **tuple_f1_explicit** | gold_explicit vs pred_explicit | (aspect_term, polarity) | Grounding 진단 |

**집계**: 샘플당 F1의 **평균** (gold 있는 샘플만). `mean(F1(gold_i, pred_i))`.

---

## 2. Pair 변환 함수

| 함수 | Pair 키 | aspect_ref 비어 있으면 |
|------|---------|------------------------|
| **tuples_to_ref_pairs** | (aspect_ref, polarity) | 제외 (invalid_ref_count++), 해당 튜플은 F1에 기여하지 않음 |
| **tuples_to_pairs** | (aspect_term, polarity) | aspect_term 사용 |
| **tuples_to_attr_pairs** | (attribute, polarity) | entity#attribute → attribute만 추출, 비어 있으면 제외 |

**정규화**:
- `normalize_for_eval(s)`: strip, lower, 공백 축약, 앞뒤 구두점 제거
- `normalize_polarity(p)`: pos→positive, neg→negative, neu→neutral

---

## 3. EvalTuple 구조

```
EvalTuple = (aspect_ref, aspect_term, polarity)
```

| 필드 | 의미 | Gold 예시 | Pred 예시 |
|------|------|-----------|-----------|
| **aspect_ref** | 택소노미 (entity#attribute) | `제품 전체#일반`, `본품#품질` | `제품 전체#품질`, `본품#편의성` |
| **aspect_term** | 문장 내 관점 표면형 (OTE) | `아이립밤`, `사이즈`, `마스크팩` | `아이립밤`, `2 in 1` |
| **polarity** | positive / negative / neutral | `positive` | `positive` |

- **explicit**: aspect_term ≠ ""
- **implicit**: aspect_term == "" (전체 문장 감성)

---

## 4. Gold vs Pred 쌍 예시 (ref-pol, 주평가)

### 4.1 Gold 튜플 → ref_pairs

| gold_tuples (원본) | tuples_to_ref_pairs → (aspect_ref, polarity) |
|--------------------|-----------------------------------------------|
| `{aspect_ref: "제품 전체#일반", aspect_term: "아이립밤", polarity: "positive"}` | `("제품 전체#일반", "positive")` |
| `{aspect_ref: "패키지/구성품#편의성", aspect_term: "사이즈", polarity: "positive"}` | `("패키지/구성품#편의성", "positive")` |
| `{aspect_ref: "브랜드#품질", aspect_term: "", polarity: "negative"}` | `("브랜드#품질", "negative")` |
| `{aspect_ref: "본품#일반", aspect_term: "대용량", polarity: "positive"}` | `("본품#일반", "positive")` |

### 4.2 Pred 튜플 → ref_pairs

| final_tuples (원본) | tuples_to_ref_pairs → (aspect_ref, polarity) |
|---------------------|-----------------------------------------------|
| `{aspect_ref: "제품 전체#품질", aspect_term: "아이립밤", polarity: "positive"}` | `("제품 전체#품질", "positive")` |
| `{aspect_ref: "패키지/구성품#편의성", aspect_term: "사이즈", polarity: "positive"}` | `("패키지/구성품#편의성", "positive")` |

### 4.3 매칭 예시 (ref-pol)

| Gold pair | Pred pair | 매칭 |
|-----------|-----------|------|
| `("제품 전체#일반", "positive")` | `("제품 전체#일반", "positive")` | ✅ TP |
| `("제품 전체#일반", "positive")` | `("제품 전체#품질", "positive")` | ❌ FP (gold), FN (gold) |
| `("본품#품질", "positive")` | `("제품 전체#품질", "positive")` | ❌ ref 불일치 |

---

## 5. Gold vs Pred 쌍 예시 (ote-pol, 보조)

### 5.1 tuples_to_pairs

| gold_tuples | tuples_to_pairs → (aspect_term, polarity) |
|-------------|-------------------------------------------|
| `{aspect_ref: "본품#일반", aspect_term: "레몬그라스 향", polarity: "positive"}` | `("레몬그라스 향", "positive")` |
| `{aspect_ref: "본품#품질", aspect_term: "EWG 1등급 보습제", polarity: "positive"}` | `("ewg 1등급 보습제", "positive")` |

- 정규화: `normalize_for_eval(aspect_term)` → 소문자, 공백 축약, 구두점 제거

### 5.2 매칭 (ote-pol)

| Gold pair | Pred pair | 매칭 |
|-----------|-----------|------|
| `("레몬그라스 향", "positive")` | `("레몬그라스 향", "positive")` | ✅ TP |
| `("레몬그라스 향", "positive")` | `("레몬그라스향", "positive")` | ✅ (정규화 후 동일) |
| `("레몬그라스 향", "positive")` | `("본품#일반", "positive")` | ❌ aspect_term 불일치 |

**ote-pol** 사용 시: `match_by_aspect_ref=False` → gold와 pred 모두 `tuples_to_pairs` 사용 → (aspect_term, polarity)로 매칭. pred도 aspect_term 기준.

---

## 6. Gold vs Pred 쌍 예시 (attr-pol)

### 6.1 tuples_to_attr_pairs

entity#attribute → attribute만 추출.

| gold_tuples (aspect_ref) | tuples_to_attr_pairs → (attribute, polarity) |
|--------------------------|----------------------------------------------|
| `제품 전체#일반` | `("일반", "positive")` |
| `본품#품질` | `("품질", "positive")` |
| `패키지/구성품#편의성` | `("편의성", "positive")` |
| `브랜드#인지도` | `("인지도", "negative")` |

---

## 7. Implicit 처리 (match_empty_aspect_by_polarity_only=True)

- **exact_gold**: aspect_term ≠ "" 인 gold pair → pred와 정확히 집합 교차로 매칭
- **polarity_only_gold**: aspect_term == "" 인 gold pair → pred 중 **같은 polarity**인 쌍과 1:1 매칭 (아직 매칭 안 된 pred만)

예: gold에 `("", "positive")` 2개, pred에 `("제품 전체#품질", "positive")`, `("본품#일반", "positive")` 2개  
→ polarity_only 2개 각각 pred와 1:1 매칭 → tp_polarity = 2

---

## 8. TP/FP/FN 및 F1 공식

```
TP = tp_exact + tp_polarity  (exact: pred_pairs ∩ exact_gold, polarity_only: 1:1 매칭)
FP = |pred_pairs| − TP
FN = |gold_pairs| − TP

Precision = TP / (TP + FP)   (분모 0 → 0)
Recall    = TP / (TP + FN)   (분모 0 → 0)
F1        = 2 × P × R / (P + R)   (P+R=0 → 0)
```

---

## 9. 참고

- **구현**: `metrics/eval_tuple.py` — `precision_recall_f1_tuple`, `tuples_to_ref_pairs`, `tuples_to_pairs`, `tuples_to_attr_pairs`
- **집계**: `scripts/structural_error_aggregator.py` — `compute_stage2_correction_metrics()`
- **Paper 명세**: `docs/paper_metrics_spec.md`, `docs/cr_branch_metrics_spec.md`
