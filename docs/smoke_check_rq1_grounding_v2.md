# RQ1 Grounding v2 체크리스트 + 샘플 출력 예시

## 1. 체크리스트

### 스키마/데이터

- [ ] `inputs.ate_debug.filtered[*].drop_reason`가 drop인 항목에서 비어 있지 않음  
- [ ] `drop_reason` 값이 taxonomy에 포함됨: `alignment_failure`, `filter_rejection`, `semantic_hallucination`

### 수치 불변식

- [ ] `0 ≤ semantic/alignment/filter_rate ≤ aspect_hallucination_rate ≤ 1`  
- [ ] RQ1 one-hot 합: `implicit + explicit + explicit_failure + unsupported == 1.0` (±ε)  
- [ ] `unsupported_polarity_rate`가 “implicit 허용” 이후에도 1.0 근처로 고정되지 않음 (미니런 sanity)

### 리포트 해석

- [ ] RQ1 섹션 표에는 hallucination 세부 rate를 포함하지 않음 (별도 섹션)  
- [ ] Hallucination 관련은 “ATE/Pipeline robustness (Auxiliary)”로 표기

### 회귀/호환성

- [ ] 기존 `aspect_hallucination_rate`가 이전 정의(“drop≥1인 샘플 비율”)와 동일하게 유지됨  
- [ ] 기존 보고서/빌더가 새 컬럼 추가로 깨지지 않음 (필드 optional 처리)

## 2. 5줄 진단 스크립트

샘플 1개에 대해 다음을 한 화면에 출력하는 스크립트:  
`scripts/diagnose_rq1_grounding_sample.py`

- **1) Selected tuple**: (aspect_term_norm, polarity)  
- **2) Selected judgement idx**: 0-based index (없으면 None)  
- **3) RQ1 bucket**: implicit | explicit | explicit_failure | unsupported  
- **4) drop_reason 카운트(3종)**: alignment_failure, filter_rejection, semantic_hallucination (해당 샘플 내 drop 항목 기준)

### 샘플 출력 예시

```
text_id: nikluge-sa-2022-train-00797
selected_tuple: (aspect_term_norm='성분', polarity='positive')
selected_judgement_idx: 0
rq1_bucket: explicit
drop_reason_counts: alignment_failure=0, filter_rejection=1, semantic_hallucination=0
```

## 3. 실행 방법

```bash
# Scorecard 생성 (drop_reason 세분화 반영)
python scripts/scorecard_from_smoke.py --smoke experiments/results/proposed/smoke_outputs.jsonl

# 집계 (ATE 분해 + RQ1 one-hot)
python scripts/structural_error_aggregator.py --input experiments/results/proposed/scorecards.jsonl --outdir results/metrics

# 5줄 진단 (샘플 1개)
python scripts/diagnose_rq1_grounding_sample.py --input experiments/results/proposed/scorecards.jsonl --index 0
```

## 4. 검증

- `structural_metrics.csv`에 `alignment_failure_rate`, `filter_rejection_rate`, `semantic_hallucination_rate`, `implicit_grounding_rate`, `explicit_grounding_rate`, `explicit_grounding_failure_rate`, `unsupported_polarity_rate`, `rq1_one_hot_sum` 존재.  
- `rq1_one_hot_sum` ≈ 1.0 (부동소수 오차 허용).
