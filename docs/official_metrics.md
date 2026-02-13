# 공식 메트릭 정의 및 집계 (Official)

**Official.** 이 문서는 파이프라인에서 **실제로 집계·산출되는** 메트릭의 정의·공식·출처를 확정합니다.  
데이터 흐름·스테이지별 담당: `docs/pipeline_stages_data_and_metrics_flow.md`.  
논문/RQ 역할: `docs/metrics_for_paper.md`, `docs/rq_metrics_field_mapping.md`.

---

## 1. polarity_repair_rate / polarity_invalid_rate 여부

| 메트릭명 | 집계 여부 | 비고 |
|----------|------------|------|
| **polarity_repair_rate** | **집계되지 않음** | 레포·docs 전역 검색 결과 정의·산출 코드 없음. |
| **polarity_invalid_rate** | **이름으로는 없음** | “Polarity invalid”는 **override hint** 맥락에서만 사용되며, 아래 **override_hint_invalid_rate** 로 집계됨. |

- **polarity_repair_rate**: 현재 파이프라인에서 정의·집계되지 않음. 필요 시 스키마·aggregator·문서에 추가 정의 필요.
- **polarity_invalid_rate**: 일반적인 “최종 출력의 invalid polarity 비율” 메트릭은 없음.  
  C2 debate override용 **hint** 에서 polarity가 canonicalize 불가인 경우만 **override_hint_invalid_rate** 로 집계됨(정의·공식은 §3).

---

## 2. 집계 소스 및 산출물

| 단계 | 담당 | 입력 | 산출 |
|------|------|------|------|
| Run | run_experiments, SupervisorAgent | 샘플·gold | scorecards.jsonl, override_gate_debug_summary.json |
| 집계 | structural_error_aggregator | scorecards.jsonl, (선택) override_gate_summary | structural_metrics.csv, structural_metrics_table.md |
| 리포트 | build_metric_report | manifest + scorecards + structural_metrics.csv | metric_report.html |

- **structural_metrics.csv** 1행 = 1 run 집계 결과. 컬럼 목록은 `scripts/structural_error_aggregator.py` 의 `CANONICAL_METRIC_KEYS` 가 정본.
- **override_hint_invalid_*** 는 run 단위로 SupervisorAgent가 만든 **override_gate_debug_summary.json** 에서 읽어 aggregator가 CSV에 채움.

---

## 3. Polarity·Override 관련 공식 메트릭

### 3.1 polarity_conflict_rate_raw / polarity_conflict_rate / polarity_conflict_rate_after_rep

- **polarity_conflict_rate_raw**: 대표 선택 없이, 동일 aspect_term에 서로 다른 polarity가 2개 이상 있으면 conflict.  
  집계: conflict 샘플 수 / N.
- **polarity_conflict_rate** (= polarity_conflict_rate_after_rep): **대표 1개 선택 후** 동일 aspect에 서로 다른 polarity가 남는지로 판단(`has_polarity_conflict_after_representative`).  
  집계: 해당 샘플 수 / N.  
  소스: `structural_error_aggregator` → scorecard final_aspects 및 대표 선택 로직.

### 3.2 override_hint_invalid_total / override_hint_invalid_rate (Official)

**정의**

- **override_hint_invalid_total**: Run 전체에서, debate override용 **aspect hint** 의 `polarity_hint` 를 canonicalize했을 때 **None**(정규화 불가)인 힌트 건수.
- **override_hint_invalid_rate**:  
  `override_hint_invalid_total / (override_hint_invalid_total + total_valid_hints)`  
  단, `total_valid_hints` = run 중 모든 aspect에 대해 `valid_hint_count`(polarity_hint ∈ {positive, negative}) 합계.  
  분모가 0이면 **None**.

**집계 경로**

1. **산출**: `agents/supervisor_agent.py`  
   - `_build_debate_review_context` → aspect_hints 각 hint에 대해 `canonicalize_polarity(raw_pol)`; None이면 `_override_stats["override_hint_invalid_total"]` += 1.  
   - Run 종료 시 `_write_override_gate_debug_summary()` 에서  
     `override_hint_invalid_rate = override_hint_invalid_total / (override_hint_invalid_total + total_valid_hints)` (분모 0이면 None).  
   - 결과를 **override_gate_debug_summary.json** 에 기록.
2. **집계 반영**: `scripts/structural_error_aggregator.py`  
   - `aggregate_single_run(..., override_gate_summary)` 에서 `override_gate_summary` 에  
     `override_hint_invalid_total`, `override_hint_invalid_rate` 가 있으면 그대로 `out` 에 넣어 structural_metrics.csv/MD에 포함.

**문서 요약**

- “힌트 polarity invalid” = debate proposed_edits에서 나온 hint의 polarity가 positive/negative/neutral 등으로 정규화되지 않는 경우.  
  이 비율이 **override_hint_invalid_rate** 로만 집계되며, **polarity_invalid_rate** 라는 별도 메트릭은 없음.

### 3.3 severe_polarity_error_L3_rate

- **의미**: Aspect boundary는 gold와 매칭되는데 **polarity만 불일치**한 샘플 비율 (L4/L5 제외).
- **집계**: severe_polarity_error_L3_count / N_gold (N_gold 있을 때).  
  소스: structural_error_aggregator 내 L3 severe polarity 판정.

### 3.4 unsupported_polarity_rate / implicit_invalid_pred_rate

- **unsupported_polarity_rate**: RQ1 one-hot에서 “unsupported polarity”인 샘플 비율.
- **implicit_invalid_pred_rate**: implicit gold가 있는 샘플 중, implicit polarity 예측이 유효하게 0개이거나 파싱 실패·금지된 neutral fallback인 샘플 비율.  
  공식: `docs/f1_metrics_formula.md` §5 참고.

---

## 4. F1·보정 메트릭 집계 공식

- **tuple_f1_s1 / tuple_f1_s2 / delta_f1, fix_rate, break_rate, net_gain**:  
  `docs/f1_metrics_formula.md` 및 `scripts/structural_error_aggregator.py` 의 `compute_stage2_correction_metrics()` 참고.
- **tuple_f1_s2_after_rep**: 대표 선택 후 최종 튜플 vs gold F1의 샘플 평균.

---

## 5. 정본 메트릭 키 목록

집계 스크립트에 정의된 정본 목록은 다음 상수입니다.

- **파일**: `scripts/structural_error_aggregator.py`  
- **상수**: `CANONICAL_METRIC_KEYS`  
- **순서**: Outcome (RQ) → Process → 기타(debug/diagnostic).  
- **Outcome vs Process** 역할: `docs/metrics_for_paper.md`, `docs/rq_metrics_field_mapping.md`.

polarity·override 관련 키 일부:

- severe_polarity_error_L3_count, severe_polarity_error_L3_rate  
- polarity_conflict_rate_raw, polarity_conflict_rate, polarity_conflict_rate_after_rep  
- override_hint_invalid_total, override_hint_invalid_rate  
- override_applied_*, override_skipped_* 등

---

## 6. 요약

| 항목 | 내용 |
|------|------|
| **polarity_repair_rate** | **미집계.** 정의·산출 코드 없음. |
| **polarity_invalid_rate** | **미집계.** 동일 이름 메트릭 없음. Hint 관점의 invalid만 **override_hint_invalid_rate** 로 집계. |
| **override_hint_invalid_rate** | **집계됨.** 정의·공식 §3.2. 소스: override_gate_debug_summary → aggregator → structural_metrics.csv/MD. |
| **데이터·메트릭 흐름** | `docs/pipeline_stages_data_and_metrics_flow.md` 현행화본 참고. |

이 문서는 위 내용을 **공식(Official)** 로 확정합니다.  
추가 메트릭(polarity_repair_rate 등)을 도입할 경우 이 문서와 aggregator·스키마를 함께 갱신할 것.
