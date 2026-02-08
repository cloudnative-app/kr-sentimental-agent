# RQ1 Grounding v2: 정의·공식·해석 가이드

## 1. 목표

- **ATE Drop 분해**: `aspect_hallucination_rate`가 혼합하던 현상(semantic/alignment/filter)을 원인별로 분리해 ATE 품질·파이프라인 안정성 지표로 재정렬.
- **RQ1 One-hot**: RQ1(groundedness)을 implicit grounding 포함으로 확장하되, 결과 지표를 **배타적(one-hot)**으로 설계해 해석 충돌 제거.

## 2. ATE Drop 분해 (원인 지표)

### 2.1 공통 정의

- **소스**: Scorecard `inputs.ate_debug.filtered[]` 중 `action == "drop"`인 항목.
- **샘플 단위 rate**: “해당 원인 drop이 1개 이상 존재하는 샘플 비율” (분모 = N).

### 2.2 drop_reason taxonomy

| drop_reason | 의미 | 조건(권장) |
|-------------|------|------------|
| `alignment_failure` | term–span 불일치(정렬 오류) | span 존재 AND term != span_text |
| `filter_rejection` | stop/allowlist/길이 규칙 등 “타깃 유효성” 탈락 | is_valid == False |
| `semantic_hallucination` | 원문 외 표현 / span이 원문과 무관 | span 없음 또는 out-of-text |

### 2.3 산출 공식 (샘플 단위 rate)

- `alignment_failure_rate` = (#samples with ≥1 drop_reason=="alignment_failure") / N  
- `filter_rejection_rate` = (#samples with ≥1 drop_reason=="filter_rejection") / N  
- `semantic_hallucination_rate` = (#samples with ≥1 drop_reason=="semantic_hallucination") / N  
- **기존**: `aspect_hallucination_rate` = (#samples with any drop) / N (유지)

### 2.4 불변식

- `0 ≤ semantic/alignment/filter_rate ≤ aspect_hallucination_rate ≤ 1`
- `aspect_hallucination_rate ≤ alignment_failure_rate + filter_rejection_rate + semantic_hallucination_rate` (샘플 중복 허용)

## 3. RQ1 Grounding One-hot (결과 지표)

### 3.1 원칙

- 샘플당 **정확히 1개** 라벨만 부여 (one-hot).
- **Selected tuple** 기준: 최종 선택/채택된 tuple(또는 대표 tuple).
- **원인(ATE drop)과 결과(RQ1 grounding) 분리**: ATE drop이 있어도 RQ1은 implicit/explicit로 정상 처리될 수 있음.

### 3.2 분류 규칙 (결정 트리, 배타적)

1. **Implicit grounded**  
   - 조건: selected_aspect_term == "" (또는 명시적 implicit) AND polarity가 정상 범주(positive/negative/neutral/mixed).  
   - 산출: `implicit_grounding_rate` = (#implicit_grounded samples) / N  

2. **Explicit grounded**  
   - 조건: selected_aspect_term != "" AND selected judgement `opinion_grounded == True` AND issues 비어있거나 "unknown/insufficient"만.  
   - 산출: `explicit_grounding_rate` = (#explicit_grounded samples) / N  

3. **Explicit grounding failure**  
   - 조건: selected_aspect_term != "" AND selected judgement 실패(opinion_grounded==False 또는 명시적 mismatch issue).  
   - 산출: `explicit_grounding_failure_rate` = (#explicit_grounding_failure samples) / N  

4. **Unsupported polarity (RQ1 failure)**  
   - 조건: 위 1~3에 해당하지 않음(근거 부재/비논리/불가능).  
   - 산출: `unsupported_polarity_rate` = (#unsupported samples) / N  

### 3.3 One-hot 검증

- `implicit_grounding_rate + explicit_grounding_rate + explicit_grounding_failure_rate + unsupported_polarity_rate == 1.0` (부동소수 오차 허용).  
- 집계 출력에 `rq1_one_hot_sum`으로 저장해 검증.

### 3.4 Legacy 지표

- `legacy_unsupported_polarity_rate`: 기존 정의(atsa opinion_grounded/evidence issues 휴리스틱) 유지. 초기 이행기 병행용.

## 4. RQ2/기타와의 분리

- `polarity_conflict_rate`는 RQ2(일관성) 지표로 유지. RQ1 one-hot 분류에는 conflict를 직접 반영하지 않음.
- Override/guided change 등 변경 지표는 그대로 두고, RQ1 분류는 **최종 상태** 기준으로 계산.

## 5. 구현 위치

- **drop_reason 세분화**: `scripts/scorecard_from_smoke.py` → `build_filtered_aspects()`
- **ATE 분해 rate**: `scripts/structural_error_aggregator.py` → `count_hallucination_types()`, `aggregate_single_run()`
- **RQ1 one-hot**: `scripts/structural_error_aggregator.py` → `_get_first_final_tuple()`, `get_selected_judgement()`, `rq1_grounding_bucket()`, `aggregate_single_run()`

## 6. 리포트 해석

- RQ1 섹션 표에는 **hallucination 세부 rate를 포함하지 않음** (별도 “ATE/Pipeline robustness (Auxiliary)” 섹션).
- Hallucination 관련은 “ATE/Pipeline robustness (Auxiliary)”로 표기해 혼동 방지.
