# Betatest C1 gold→gold F1=0 진단: 골드 튜플 구조 및 evaluator 매칭 로직

## 1. 골드 튜플 구조 샘플 (3줄)

### 1.1 valid.gold.jsonl (원본)

```jsonl
{"uid": "nikluge-sa-2022-train-00149", "gold_tuples": [{"aspect_ref": "본품#일반", "aspect_term": "레몬그라스 향", "polarity": "positive", "span": {"start": 31, "end": 38}}]}
{"uid": "nikluge-sa-2022-train-02879", "gold_tuples": [{"aspect_ref": "본품#품질", "aspect_term": "EWG 1등급 보습제", "polarity": "positive", "span": {"start": 42, "end": 53}}]}
{"uid": "nikluge-sa-2022-train-01089", "gold_tuples": [{"aspect_ref": "본품#품질", "aspect_term": "", "polarity": "positive", "span": {"start": 0, "end": 0}}]}
```

- **필드**: `aspect_ref`, `aspect_term`, `polarity`, (선택) `span`
- **explicit**: aspect_term 비어있지 않음 (문장 내 표면형)
- **implicit**: aspect_term="" (극성만 있음)

### 1.2 scorecard 내 inputs.gold_tuples (주입 후)

```json
{"aspect_ref": "본품#일반", "aspect_term": "레몬그라스 향", "polarity": "positive"}
```

- run_experiments가 valid.gold.jsonl을 uid로 매칭해 주입. `span`은 F1 매칭에 미사용.

---

## 2. Evaluator 매칭 로직

### 2.1 경로 (`metrics/eval_tuple.py`)

| 단계 | 함수 | 역할 |
|------|------|------|
| 추출 | `gold_tuple_set_from_record` | scorecard → `gold_tuples_from_record` → `gold_row_to_tuples` → `tuples_from_list` |
| Pair 생성 | `tuples_to_pairs` | (aspect_term, polarity) 사용 |
| Pair 생성 (pred) | `tuples_to_pairs_ref_fallback` | (aspect_ref **or** aspect_term, polarity) 사용 |
| F1 | `precision_recall_f1_tuple` | gold_pairs vs pred_pairs 교차 집합으로 TP/FP/FN 계산 |

### 2.2 핵심 불일치 (gold→gold F1=0 원인)

```
gold tuple: ('본품#일반', '레몬그라스 향', 'positive')
  - gold_pairs (tuples_to_pairs):      ('레몬그라스 향', 'positive')  ← aspect_term
  - pred_pairs (tuples_to_pairs_ref_fallback): ('본품#일반', 'positive')  ← aspect_ref or aspect_term = aspect_ref (먼저)
```

- **gold**는 항상 `tuples_to_pairs` → (aspect_term, polarity)
- **pred**는 `match_by_aspect_ref=True`(기본)일 때 `tuples_to_pairs_ref_fallback` → (aspect_ref or aspect_term, polarity)
- `aspect_ref`와 `aspect_term`이 **둘 다 있으면** `a or t`는 `aspect_ref`를 사용
- 따라서 gold를 gold와 비교할 때:
  - gold_pairs: (`레몬그라스 향`, positive)
  - pred_pairs: (`본품#일반`, positive)
- 서로 다른 키 → 매칭 0 → F1=0

### 2.3 `precision_recall_f1_tuple` 시그니처

```python
def precision_recall_f1_tuple(
    gold_tuples: Set[EvalTuple],
    pred_tuples: Set[EvalTuple],
    match_empty_aspect_by_polarity_only: bool = True,
    match_by_aspect_ref: bool = True,  # pred에 aspect_ref 사용
) -> Tuple[float, float, float]:
```

- `match_by_aspect_ref=True`: pred는 (aspect_ref or aspect_term, polarity)
- `match_by_aspect_ref=False`: pred도 (aspect_term, polarity)

---

## 3. 수정 제안

**sanity 검사 gold→gold**에서는 비교 대상이 둘 다 gold이므로 같은 키 체계를 써야 함.

`scripts/structural_error_aggregator.py`의 `run_sanity_checks`:

```python
# 현재
_, _, f1 = precision_recall_f1_tuple(gold, gold)

# 제안
_, _, f1 = precision_recall_f1_tuple(gold, gold, match_by_aspect_ref=False)
```

- `match_by_aspect_ref=False` → pred 쪽도 `tuples_to_pairs` 사용 → gold와 동일한 (aspect_term, polarity) 키 → gold→gold F1=1.

---

## 4. 요약

| 항목 | 내용 |
|------|------|
| gold 구조 | aspect_ref, aspect_term, polarity (span은 F1에 미사용) |
| gold pair 키 | (aspect_term, polarity) |
| pred pair 키 | 기본 (aspect_ref or aspect_term, polarity) |
| gold→gold 실패 원인 | gold에 aspect_ref·aspect_term 둘 다 있을 때, pred 경로가 aspect_ref를 써서 키 불일치 |
| 수정 | sanity gold→gold 검사에 `match_by_aspect_ref=False` 적용 |
