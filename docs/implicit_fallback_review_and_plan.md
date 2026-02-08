# Implicit fallback 검토 및 방안 (반영 완료)

## 1. 요청 사항 정리

| 구분 | 항목 | 요청 내용 |
|------|------|-----------|
| ✔ Scorecard | `implicit_grounding_candidate: bool` | 암시적 grounding 후보 여부 |
| ✔ Scorecard | `implicit_trigger_reason: {explicit_alignment_failed, no_aspect, etc.}` | implicit 후보로 보는 이유 |
| ✔ RQ1 one-hot assigner | explicit_failure 이전 implicit 체크 | 만족 시 **explicit_failure → implicit** 재분류 |
| ✔ Aggregator | implicit_grounding_rate / rq1_one_hot_sum | 계산 유지, one-hot 합 1.0 유지 |

---

## 2. 현재 파이프라인 처리 여부

### 2.1 Scorecard

- **implicit_grounding_candidate**: **미구현**. 코드베이스에 해당 필드 없음.
- **implicit_trigger_reason**: **미구현**. 동일.

**결론**: Scorecard에 위 두 필드는 현재 없음. `scorecard_from_smoke.py`의 `make_scorecard()`에서 `inputs.ate_debug`, `ate`, `atsa` 등만 세팅하고, implicit 후보/trigger는 세팅하지 않음.

### 2.2 RQ1 one-hot assigner (`rq1_grounding_bucket`)

- **현재 동작**:
  1. `selected_term_norm == ""` 이면 (또는 final tuple 없고 document label만 있으면) → **implicit** 후보, polarity 정상이면 implicit 반환.
  2. 그 다음 selected_term != "" 이고 opinion_grounded True, issues가 unknown/insufficient만 → **explicit**.
  3. 그 다음 opinion_grounded False 또는 mismatch 이슈 → **explicit_failure**.
  4. 나머지 → **unsupported**.

- **“explicit_failure 이전에 implicit 조건 체크, 만족 시 explicit_failure → implicit 재분류”**: **미구현**.  
  현재는 “선택된 tuple이 명시적(term != "")이고, 해당 judgement가 실패”하면 무조건 **explicit_failure**만 반환함.  
  “실패했지만 문서급 polarity는 유효하므로 implicit으로 간주”하는 **fallback** 로직은 없음.

**결론**: explicit_failure로 가기 **직전**에 implicit fallback을 넣는 단계는 없음.

### 2.3 Aggregator

- **implicit_grounding_rate**: 이미 `rq1_grounding_bucket(r) == RQ1_BUCKET_IMPLICIT` 인 샘플 비율로 계산됨.
- **rq1_one_hot_sum**: 이미 4개 버킷 비율 합으로 계산되며, 버킷이 one-hot이면 1.0.

**결론**: 집계 방식은 이미 요청 사항과 일치. **assigner만** implicit을 더 많이 반환하도록 바꾸면, **별도 수정 없이** implicit_grounding_rate가 올라가고 rq1_one_hot_sum은 1.0 유지됨.

---

## 3. “현재 메트릭 집계 방식에서 자연스럽게 집계되는가?”

**가능함.**

- Aggregator는 `rq1_grounding_bucket(record)` 결과만 보고 각 버킷 수를 세고,  
  `implicit_grounding_rate` = (implicit 수)/N,  
  `rq1_one_hot_sum` = 4개 rate 합으로 계산함.
- 따라서:
  - **assigner에서만** “explicit_failure로 갈 케이스 중 일부를 implicit으로 재분류”하도록 바꾸면,
  - Aggregator 코드 변경 없이 **자연스럽게** implicit_grounding_rate가 증가하고, explicit_grounding_failure_rate가 감소하며, rq1_one_hot_sum은 그대로 1.0으로 유지됨.

---

## 4. 제안 방안 (파이프라인 수정 최소화)

### 4.1 원칙

- **실행 파이프라인(ATE/ATSA/Validator/Moderator 등)** 은 건드리지 않음.
- **Scorecard 생성**(`scorecard_from_smoke.py`)과 **RQ1 버킷 assigner**(`structural_error_aggregator.rq1_grounding_bucket`)만 확장.
- Aggregator의 **집계 수식/컬럼**은 그대로 두고, assigner 출력만 바뀌게 함.

### 4.2 Scorecard (선택·권장)

**위치**: `scripts/scorecard_from_smoke.py` → `make_scorecard()` 내, `inputs` 또는 상위에 블록 추가.

**추가 필드**:

- `implicit_grounding_candidate: bool`  
  - True로 둘 조건 예:  
    - **no_aspect**: kept_terms가 비어 있음 (또는 raw aspect가 없음).  
    - **explicit_alignment_failed**: 모든 aspect가 drop이고, drop 원인이 모두 `alignment_failure`인 경우(명시적 정렬 실패만 있고, 문서급 감정은 있을 수 있음).  
  - 그 외 “문서급 polarity는 있지만 명시적 aspect 정렬이 실패한 경우”를 정책에 맞게 한두 가지 더 넣을 수 있음.
- `implicit_trigger_reason: str`  
  - 값 예: `"no_aspect"`, `"explicit_alignment_failed"`, `"etc"` (또는 정책에 맞게 세분화).

**세팅 시점**:  
`raw_aspects`, `filtered`, `kept_terms`, `ate`, `inputs.ate_debug` 등이 이미 만들어진 뒤,  
`inputs.ate_debug.filtered`의 `drop_reason`과 `kept_terms`만으로 판단 가능.  
따라서 **파이프라인 실행 결과는 그대로 두고**, scorecard **파생 필드**만 추가하면 됨.

**효과**:  
- RQ1 assigner나 리포팅에서 “이 샘플이 왜 implicit 후보인지”를 **이미 scorecard에서** 읽을 수 있음.  
- Aggregator는 그대로 두고, **assigner**에서 이 필드를 참고할 수 있음(아래).

### 4.3 RQ1 one-hot assigner (필수)

**위치**: `scripts/structural_error_aggregator.py` → `rq1_grounding_bucket()`.

**변경 요지**:  
지금 **explicit_failure**를 반환하기 **직전**에, “implicit fallback” 조건을 한 번 더 검사하고, 만족하면 **implicit**을 반환하도록 함.

**추가할 로직 (의사코드)**:

```text
# 현재: (3) explicit_failure 반환 직전
# 추가: (2.5) Implicit fallback
#   - “이번 샘플이 explicit_failure로 갈 예정”인데,
#     (a) scorecard에 implicit_grounding_candidate == True 이고
#     (b) 최종 polarity가 정상 범주(positive/negative/neutral/mixed)이면
#   → explicit_failure 대신 implicit 반환.
```

**구체화**:

1. **Scorecard 필드 사용 시**  
   - `record.get("inputs", {}).get("implicit_grounding_candidate") is True`  
   - 그리고 `final_label`(또는 first tuple의 polarity)이 정상 범주  
   → `return RQ1_BUCKET_IMPLICIT`.
2. **Scorecard 필드 없이 assigner만으로 할 때 (최소 변경)**  
   - record에 이미 있는 정보만 사용:  
     - `inputs.ate_debug.filtered`에서 “모든 drop이고, drop_reason이 모두 alignment_failure” 또는  
       kept_terms가 비어 있음(no_aspect),  
     - 그리고 moderator/ final_result에 유효한 document-level polarity 존재  
   → 동일한 조건이면 `return RQ1_BUCKET_IMPLICIT`.

**순서 유지**:  
- 기존 1) implicit(selected_term == "" 등), 2) explicit, 3) explicit_failure 후보 구간 **끝**에서,  
  “explicit_failure로 return하기 직전”에만 위 fallback을 넣으면 됨.  
- 그 결과 **한 샘플당 여전히 하나의 버킷만** 반환되므로 one-hot과 rq1_one_hot_sum = 1.0 유지.

### 4.4 Aggregator

- **수정 없음.**  
- `implicit_grounding_rate`는 이미 `rq1_grounding_bucket(r) == "implicit"` 비율로 계산되고,  
- `rq1_one_hot_sum`은 4개 rate 합이므로, assigner가 implicit을 더 반환하면 자동으로 반영됨.

---

## 5. 구현 순서 제안 (실행하지 않고 제안만)

1. **Phase 1 – Assigner만 (최소)**  
   - `rq1_grounding_bucket()`에만 “explicit_failure 직전 implicit fallback” 추가.  
   - 조건: record 내 기존 필드만 사용 (예: filtered 전부 alignment_failure 또는 no kept_terms + 유효 document polarity).  
   - Scorecard 변경 없이도 **현재 집계 방식으로** implicit_grounding_rate 상승·rq1_one_hot_sum 1.0 유지 가능.

2. **Phase 2 – Scorecard 명시 (권장)**  
   - `scorecard_from_smoke.make_scorecard()`에서  
     `implicit_grounding_candidate`, `implicit_trigger_reason` 세팅.  
   - Assigner는 Phase 1 조건을 **scorecard 필드**로 대체하거나, scorecard가 있으면 우선 사용하도록 정리.  
   - 리포팅/진단 시 “왜 implicit인지”를 scorecard만 보고 설명 가능.

3. **검증**  
   - 기존처럼 `structural_error_aggregator`로 집계한 뒤  
     `rq1_one_hot_sum == 1.0` (부동소수 오차 내),  
     implicit_grounding_rate + explicit_grounding_rate + explicit_grounding_failure_rate + unsupported_polarity_rate = 1.0 인지 확인.

---

## 6. 요약

| 질문 | 답 |
|------|----|
| 1. 현재 파이프라인에서 해당 사항이 처리되나요? | **아니오.** Scorecard에 implicit_grounding_candidate/implicit_trigger_reason 없음. Assigner에 “explicit_failure → implicit” 재분류 없음. Aggregator는 이미 implicit_grounding_rate·rq1_one_hot_sum 계산 중. |
| 2. 미처리 시, 현재 메트릭 집계에서 자연스럽게 집계되게 할 수 있나요? | **예.** Assigner에서만 explicit_failure 직전에 implicit fallback을 넣으면, Aggregator 수정 없이 implicit_grounding_rate가 올라가고 rq1_one_hot_sum = 1.0 유지됨. |
| 방안 | (1) **필수**: `rq1_grounding_bucket()`에 “explicit_failure 반환 직전” implicit 조건 체크 후 만족 시 implicit 반환. (2) **권장**: Scorecard에 `implicit_grounding_candidate`, `implicit_trigger_reason` 추가 후 assigner에서 참고. (3) Aggregator 변경 없음. |

위와 같이 하면 파이프라인 수정을 최소화하면서 요청하신 항목이 현재 메트릭 집계 방식에 자연스럽게 반영됩니다.

---

## 7. 반영 완료 (구현 요약)

- **Scorecard** (`scripts/scorecard_from_smoke.py`): `inputs.implicit_grounding_candidate`(bool), `inputs.implicit_trigger_reason`("no_aspect" | "explicit_alignment_failed" | "") 추가. `kept_terms` 비어 있으면 no_aspect, 전부 drop이고 drop_reason이 모두 alignment_failure이면 explicit_alignment_failed.
- **RQ1 assigner** (`scripts/structural_error_aggregator.py`): `_is_implicit_fallback_eligible(record, final_label, first)` 추가. explicit_failure 반환 직전에 이 조건이 만족하면 **implicit** 반환. (scorecard 필드 우선, 없으면 filtered/drop_reason으로 추론.)
- **Aggregator**: 변경 없음. implicit_grounding_rate·rq1_one_hot_sum 자동 반영.
- **검증**: mini4_b1_4 재집계 시 implicit_grounding_rate 0.0→0.4, explicit_grounding_failure_rate 0.8→0.4, rq1_one_hot_sum 1.0 유지.
