# 스테이지별 F1 추적 및 채점 튜플 진단

## 1. 스테이지별 F1 추적 여부

### 1.1 추적됨 (Yes)

- **tuple_f1_s1** / **tuple_f1_s2**: Stage1 기준 Tuple F1, Stage2+Moderator 기준 Tuple F1.
- **delta_f1**: tuple_f1_s2 − tuple_f1_s1.
- **triplet_f1_s1** / **triplet_f1_s2**: deprecated alias, 동일 값으로 채움.

**출처**

- **structural_error_aggregator**: `compute_stage2_correction_metrics(rows)` → gold 있는 행만 사용, `_extract_stage1_tuples(r)` / `_extract_final_tuples(r)` 로 S1/S2 튜플 추출 후 `_precision_recall_f1_tuple(s1, gold)`, `_precision_recall_f1_tuple(s2, gold)` 로 F1 계산 → `tuple_f1_s1`, `tuple_f1_s2`, `delta_f1` 집계.
- **build_metric_report**: `compute_stage2_correction_metrics(rows)` 동일 로직; HTML/Executive Summary에서 `tuple_f1_s1`, `tuple_f1_s2`, `delta_f1` 표시.
- **CANONICAL_METRIC_KEYS**: `tuple_f1_s1`, `tuple_f1_s2`, `triplet_f1_s1`, `triplet_f1_s2`, `delta_f1` 포함 → structural_metrics.csv에 항상 컬럼 존재.

**데이터 흐름**

1. **파이프라인**: `agents/supervisor_agent.py`에서 `FinalResult(stage1_tuples=..., stage2_tuples=..., final_tuples=...)` 생성.  
   - stage1_tuples = Stage1 ATSA `aspect_sentiments` → `tuples_to_list_of_dicts(tuples_from_list(...))`  
   - final_tuples = Moderator 최종 `final_aspects_list` → 동일 변환  
2. **run_experiments**: `result.model_dump()` → payload에 `final_result` 포함.  
3. **scorecard**: `make_scorecard(payload)` 에서 `runtime["parsed_output"] = entry`(전체 payload).  
   → scorecard에는 `runtime.parsed_output.final_result` 가 있음.  
4. **aggregator / build_metric_report**:  
   - `_extract_stage1_tuples(record)`: `record["runtime"]["parsed_output"]["final_result"]["stage1_tuples"]` 우선, 없으면 process_trace Stage1 ATSA, 최후 fallback `_extract_final_tuples`.  
   - `_extract_final_tuples(record)`: `final_result["final_tuples"]` 우선, 없으면 `final_aspects` / `inputs.aspect_sentiments`.

**결론**: 스테이지별 F1은 **추적되고 있으며**, 채점에 쓰는 S1/S2 튜플은 `final_result.stage1_tuples` / `final_result.final_tuples` 에서 올바르게 읽힌다.

---

## 2. 채점에 사용되는 튜플과 채점 정확성

### 2.1 튜플 추출 경로 (일치함)

| 구분 | Gold | Stage1 예측 | Stage2/최종 예측 |
|------|------|-------------|------------------|
| **출처** | `inputs.gold_tuples` (run_experiments에서 uid_to_gold로 주입) 또는 scorecard 최상위 `gold_tuples` | `final_result.stage1_tuples` 또는 process_trace Stage1 ATSA | `final_result.final_tuples` 또는 final_aspects / inputs.aspect_sentiments |
| **로딩** | `metrics.eval_tuple.gold_tuple_set_from_record` → `gold_row_to_tuples` → `tuples_from_list` | `_extract_stage1_tuples` | `_extract_final_tuples` |
| **F1 매칭** | `tuples_to_pairs(gold)` | `tuples_to_pairs(s1)` | `tuples_to_pairs(s2)` |

- **채점 단위**: `(aspect_term, polarity)` 쌍만 사용 (aspect_ref 무시). `docs/absa_tuple_eval.md` 및 `metrics/eval_tuple.py` 의 `tuples_to_pairs` 와 일치.
- **정규화**: `normalize_for_eval(aspect_term)`, `normalize_polarity(polarity)` 로 양쪽 모두 적용 후 집합 교차로 TP/FP/FN 계산 → **정확하게 진행됨**.

### 2.2 Gold `aspect_term == ""` (암시적 관점) 시 의미적 불일치

**현상**

- `valid.gold.jsonl` 등에서 골드가 **aspect_term: ""** 로만 주어지는 경우가 있음 (암시적 관점).
- `_gold_aspect_term()` 은 `""` 를 그대로 유지하고, `tuples_to_pairs` 후 gold 쌍은 `("", "positive")` 등이 됨.
- 파이프라인 예측은 구체적 aspect 표면형(예: "피부톤")을 내므로 pred 쌍은 `("피부톤", "positive")` 등.
- **(aspect_term, polarity) 매칭**에서는 `("", "positive")` ≠ `("피부톤", "positive")` 이므로 **매칭되지 않음**.
- 그 결과 해당 샘플의 F1은 0이 되고, **tuple_f1_s1 / tuple_f1_s2 가 전부 0에 가깝게 나올 수 있음** (mini4 등에서 N_gold=10 인데 tuple_f1=0.0 인 경우와 일치).

**정리**

- 현재 규칙대로라면 **채점 로직은 (aspect_term, polarity) 기준으로 정확히 동작**한다.
- 다만 **골드가 암시적 관점(aspect_term="")만 갖는 데이터**에서는, 설계상 **구체적 aspect를 출력하는 파이프라인과는 매칭이 되지 않는다**.
- 선택지:
  1. **문서화**: “골드에 aspect_term이 비어 있으면 해당 샘플은 (aspect_term, polarity) F1에서 사실상 0으로 기여함”을 `docs/absa_tuple_eval.md` 등에 명시.
  2. **정책 확장**: “gold aspect_term이 ""일 때는 polarity만 맞으면 매칭” 같은 별도 규칙을 도입할지 결정 (구현 시 `tuples_to_pairs` 또는 F1 계산부에서 예외 처리 필요).

### 2.3 단위·정규화 일치 여부

- **structural_error_aggregator** / **build_metric_report**: F1은 `metrics.eval_tuple.precision_recall_f1_tuple(gold, pred)` 사용 (gold aspect_term=="" 시 polarity만으로 매칭). fix_rate/break_rate는 `tuple_sets_match_with_empty_rule(gold, pred)` 사용.
- **gold**: `gold_row_to_tuples` → `tuples_from_list(lst)` → `tuple_from_sent` 에서 `normalize_for_eval` / `normalize_polarity` 적용됨.

**결론**: 채점은 (aspect_term, polarity) + **gold aspect_term=="" 시 polarity만 매칭** 규칙으로 동일하게 적용됨.

---

## 3. 요약 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 스테이지별 F1 추적 | ✅ | tuple_f1_s1/s2, delta_f1, CANONICAL에 포함, CSV/리포트 출력 |
| S1/S2 튜플 출처 | ✅ | final_result.stage1_tuples / final_tuples, scorecard에 정상 저장·조회 |
| Gold 주입 | ✅ | run_experiments에서 inputs.gold_tuples, gold_tuple_set_from_record로 읽음 |
| (aspect_term, polarity) 매칭 | ✅ | tuples_to_pairs + 집합 교차, 정규화 일치 |
| Gold aspect_term="" | ✅ | polarity만으로 매칭 (precision_recall_f1_tuple, tuple_sets_match_with_empty_rule) |

---

## 4. 권장 작업

1. **docs/absa_tuple_eval.md**  
   - “스테이지별 F1은 `final_result.stage1_tuples` / `final_tuples` 기반으로 집계됨” 한 줄 추가.  
   - “Gold에서 aspect_term이 비어 있으면 (암시적 관점) (aspect_term, polarity) 매칭에서 해당 골드 쌍은 pred와 맞지 않을 수 있음” 명시.
2. **선택**  
   - 골드가 암시적만 있는 데이터셋에서 F1을 의미 있게 쓰려면 “aspect_term 비어 있을 때 polarity만으로 매칭” 등 정책을 정한 뒤, `metrics.eval_tuple` 또는 aggregator 쪽에 작은 확장으로 반영 검토.
