# 외부 파인튜닝 모델 비교 명세 (Paper Metrics 기준)

**목적**: 페이퍼 메트릭 기준으로 외부 파인튜닝 모델 출력과 CR v2 결과를 비교하기 위한 최소 설정·정규화 요건.

**비교 대상 메트릭**: (aspect_ref, polarity) ref-pol **Macro F1**, **Micro F1**. 선택: 스키마 충돌 관련 진단.

---

## 1. 비교 메트릭 정의

| 메트릭 | 정의 | Paper 키 |
|--------|------|----------|
| **tuple_f1_s2_refpol** (Macro) | 샘플별 F1의 산술평균. Pair 단위: (aspect_ref, polarity) | Table 2 |
| **tuple_f1_s2_refpol_micro** (Micro) | 전체 TP/FP/FN 합산 후 F1 = 2PR/(P+R) | Table 2 |
| **invalid_ref_rate** (선택) | aspect_ref가 택소노미 미준수인 pred 비율 | Appendix |
| **polarity_conflict_rate** (선택) | 동일 aspect_ref에 ≥2 극성이 있는 샘플 비율 | 진단 |

**Pair 변환**: `tuples_to_ref_pairs` — (aspect_ref, polarity). aspect_ref가 비어 있으면 해당 튜플은 F1에서 제외.

---

## 2. 파인튜닝 모델 출력 최소 스키마

### 2.1 샘플 단위 출력 형식

각 샘플당 **1개 예측 객체**가 필요. CR v2 scorecard/aggregator와 호환되려면 다음 필드가 있어야 함.

```json
{
  "meta": { "uid": "nikluge-sa-2022-dev-00001", "text_id": "..." },
  "inputs": { "gold_tuples": [...] },
  "final_result": {
    "final_tuples": [
      { "aspect_ref": "제품 전체#일반", "aspect_term": "부직포 포장", "polarity": "positive" }
    ]
  }
}
```

**최소 필수**:
- `meta.uid` 또는 `meta.text_id`: gold와 1:1 매칭용
- `final_result.final_tuples`: 예측 튜플 리스트
- 각 튜플: `aspect_ref`, `polarity` 필수. `aspect_term`은 선택(ref-pol 비교 시 미사용)

### 2.2 튜플 필드 규격

| 필드 | 필수 | 형식 | 비고 |
|------|------|------|------|
| **aspect_ref** | ✅ | `entity#attribute` 문자열 | `#` 포함. 비어 있으면 F1에서 제외 |
| **polarity** | ✅ | `positive` \| `negative` \| `neutral` \| `mixed` | 또는 pos/neg/neu (정규화됨) |
| **aspect_term** | ❌ | 문자열 | ref-pol 비교 시 미사용 |

---

## 3. 정규화 규칙 (평가 시 자동 적용)

파인튜닝 모델 출력은 **저장 시점에 정규화하지 않아도 됨**. 평가 시 아래 규칙이 적용됨.

### 3.1 aspect_ref (`normalize_ref_for_eval`)

| 규칙 | 예시 |
|------|------|
| strip, 연속 공백 → 단일 공백 | `"  제품 전체 # 품질  "` → `"제품 전체#품질"` |
| `#` 좌우 공백 제거 | `"제품 전체 # 품질"` → `"제품 전체#품질"` |
| `패키지/구성품` → `패키지·구성품` | gold 호환 |
| **# 절대 훼손 금지** | 삭제·치환 금지 |

### 3.2 polarity (`normalize_polarity`)

| 입력 | 출력 |
|------|------|
| pos, positive | positive |
| neg, negative | negative |
| neu, neutral | neutral |
| mixed | mixed |
| 결측/빈 문자열 | default_missing (기본 "neutral") |

---

## 4. aspect_ref 택소노미 (NIKLuge v1)

**형식**: `entity#attribute`

**Entity**: 제품 전체, 본품, 패키지·구성품, 브랜드  
**Attribute**: 일반, 가격, 디자인, 품질, 편의성, 다양성, 인지도

**허용 조합**: `schemas/taxonomy.py` — `ALLOWED_REFS`, `ALLOWED_REF_PAIRS`

**Gold 호환**: `패키지/구성품` → `패키지·구성품`으로 정규화하여 매칭.

**정책**: Gold는 allowlist로 필터링하지 않음. **invalid_ref는 pred만** 진단용(invalid_ref_rate).

---

## 5. Gold 데이터 요건

- **형식**: `valid.gold.jsonl` — 한 줄당 `{"uid": "...", "gold_tuples": [...]}`
- **gold_tuples**: `[{aspect_ref, aspect_term, polarity}, ...]`
- **uid**: 파인튜닝 모델 입력·출력과 1:1 대응

**동일 gold 사용**: CR v2와 동일한 `valid.gold.jsonl`, 동일 샘플 집합 사용 시 직접 비교 가능.

---

## 6. 스키마 충돌 관련 비교 (선택)

| 진단 | 정의 | 산출 |
|------|------|------|
| **invalid_ref_rate** | aspect_ref가 ALLOWED_REFS에 없거나 `#` 없음 | pred 튜플 중 제외 비율 |
| **polarity_conflict_rate** | 동일 aspect_ref에 ≥2 서로 다른 polarity | 해당 샘플 수 / N |
| **invalid_ref_count** | 샘플당 invalid ref 튜플 수 | 진단용 |

**비교 시**: CR v2는 `invalid_ref_rate`, `polarity_conflict_rate`를 structural_metrics에 출력. 파인튜닝 모델도 동일 규칙으로 계산하면 스키마 충돌 수준을 비교할 수 있음.

---

## 7. 최소 설정 체크리스트

파인튜닝 모델을 Paper Metrics 기준으로 비교하려면:

- [ ] **동일 gold**: CR v2와 같은 `valid.gold.jsonl` 사용
- [ ] **동일 샘플 집합**: uid 집합 일치
- [ ] **출력 스키마**: `final_result.final_tuples` 또는 이에 대응하는 예측 리스트
- [ ] **튜플 필드**: 각 튜플에 `aspect_ref`, `polarity` 포함
- [ ] **aspect_ref 형식**: `entity#attribute`, `#` 포함
- [ ] **polarity 값**: positive/negative/neutral (또는 pos/neg/neu)
- [ ] **정규화**: 저장 전 정규화 불필요(평가 시 적용). 단, `#` 훼손 금지

---

## 8. 평가 파이프라인 연동

파인튜닝 모델 출력을 CR v2 scorecard 형식으로 변환한 뒤 `structural_error_aggregator`에 입력하면 ref-pol Macro/Micro F1을 산출할 수 있음.

**변환 예시** (스크립트 작성 시):
1. 파인튜닝 모델 출력 → `outputs.jsonl` (FinalOutputSchema 호환)
2. `make_scorecard` 또는 동등 로직으로 `scorecards.jsonl` 생성
3. `structural_error_aggregator --input scorecards.jsonl --outdir ... --profile paper_main`
4. `aggregated_mean_std.csv` 또는 `structural_metrics.csv`에서 `tuple_f1_s2_refpol`, `tuple_f1_s2_refpol_micro` 확인

---

## 9. 참고 문서

| 문서 | 설명 |
|------|------|
| [paper_metrics_spec.md](paper_metrics_spec.md) | Paper 메트릭 3-Level 구조 |
| [cr_branch_metrics_spec.md](cr_branch_metrics_spec.md) | CR 메트릭 명세 |
| [evaluation_cr_v2.md](evaluation_cr_v2.md) | Macro/Micro F1 정의 |
| [normalization_rules_and_locations.md](normalization_rules_and_locations.md) | 정규화 규칙 상세 |
| [taxonomy_nikluge_v1.md](taxonomy_nikluge_v1.md) | aspect_ref 택소노미 |
| [f1_metrics_and_scoring_examples.md](f1_metrics_and_scoring_examples.md) | Gold–Pred 쌍 예시 |
