# CR-M0 (cr_n10) 진단 보고서

**Run ID:** `cr_n10_m0__seed42_proposed`  
**실험:** Conflict Review Protocol v1, n=10, seed=42  
**진단 일시:** 2026-02-12

---

## 1. 산출물 체크리스트 (필수 파일)

| 파일 | 존재 | 크기 | 레코드 수 | 비고 |
|------|------|------|-----------|------|
| `results/cr_n10_m0__seed42_proposed/outputs.jsonl` | ✅ | 0 bytes | 0 | **비어 있음** |
| `results/cr_n10_m0__seed42_proposed/scorecards.jsonl` | ✅ | 0 bytes | 0 | **비어 있음** |
| `results/cr_n10_m0__seed42_proposed/derived/metrics/structural_metrics.csv` | ❌ | - | - | **미생성** |
| `results/cr_n10_m0__seed42_proposed/metric_report.html` | ❌ | - | - | **미생성** |

**결론:** outputs.jsonl, scorecards.jsonl은 파일은 존재하나 **0 레코드**로 비어 있음. run이 완료되지 않았거나 첫 샘플 처리 전에 중단된 것으로 추정됨. derived/metrics, metric_report.html 미생성.

---

## 2. SSOT 필드 체크 (샘플 1개라도 확인)

**상태:** outputs.jsonl 레코드가 없어 **샘플 확인 불가**.

추가로, `conflict_review_runner.py`가 현재 출력하는 스키마를 체크리스트와 비교하면:

| 체크리스트 필수 필드 | conflict_review_runner 현재 출력 | 일치 |
|---------------------|----------------------------------|------|
| `meta.stage1_perspective_aste` (A/B/C 존재) | ❌ 없음 | **불일치** |
| `final_result.final_tuples_pre_review` | ❌ 없음 (stage1_tuples만 있음) | **불일치** |
| `final_result.final_tuples_post_review` | ❌ 없음 (final_tuples만 있음) | **불일치** |
| `analysis_flags.review_actions` | ❌ 없음 | **불일치** |
| `analysis_flags.arb_actions` | ❌ 없음 | **불일치** |
| `stage1_validator` / `stage2_validator` | ❌ conflict_review_v1에서는 validator 없음 | **N/A** |

**현재 러너 출력 필드:**
- `meta`: input_text, run_id, text_id, mode, protocol_mode, case_type, split, language_code, domain_id
- `final_result`: label, confidence, rationale, final_aspects, **stage1_tuples**, **stage2_tuples**, **final_tuples**
- `analysis_flags`: stage2_executed

**결론:** 체크리스트 SSOT 필드 중 `stage1_perspective_aste`, `final_tuples_pre_review`, `final_tuples_post_review`, `review_actions`, `arb_actions` 가 모두 구현되어 있지 않음.

---

## 3. 합격/불합격 기준 (Phase 0)

### 합격 조건 (ALL)

| 조건 | 결과 | 비고 |
|------|------|------|
| parse_generate_failure_rate == 0 | N/A | outputs 없음 |
| missing_required_field_rate == 0 | N/A | outputs 없음 |
| n=10 중 최소 1개 pre != post | ❌ | outputs 없음 |
| pre_to_post_change_rate >= 0.10 | ❌ | outputs 없음 |

### 불합격 조건 (ANY)

| 조건 | 결과 | 비고 |
|------|------|------|
| outputs.jsonl 필수 필드 누락 | ✅ **불합격** | outputs 비어 있음 + SSOT 필드 미구현 |
| pre/post 전 샘플 동일 (교정율 0) | ✅ **불합격** | outputs 없음 → 교정율 계산 불가 |
| scorecard/aggregator 재현 실패 | N/A | scorecards 비어 있음 |

---

## 4. 종합 판정

| 항목 | 판정 |
|------|------|
| **Phase 0 합격** | ❌ **불합격** |

### 불합격 사유
1. **outputs.jsonl 비어 있음** – run이 완료되지 않았거나 첫 샘플 처리 전 중단
2. **SSOT 필드 미구현** – `conflict_review_runner.py`가 체크리스트 필수 필드를 출력하지 않음
3. **derived/metrics, metric_report.html 미생성** – `--with_metrics` 없이 실행되었거나 outputs 없어 생성 불가

---

## 5. 권장 조치

1. **cr_n10_m0 재실행**
   - `python scripts/run_pipeline.py --config experiments/configs/cr_n10_m0.yaml --run-id cr_n10_m0 --mode proposed --profile smoke --with_metrics --metrics_profile paper_main`
   - outputs.jsonl, scorecards.jsonl에 10개 레코드가 생성되는지 확인

2. **conflict_review_runner 스키마 보강**
   - `meta.stage1_perspective_aste`: A/B/C triplets 저장
   - `final_result.final_tuples_pre_review` = stage1에서 merge한 후, review 적용 전
   - `final_result.final_tuples_post_review` = Arbiter actions 적용 후 (현재 final_tuples)
   - `analysis_flags.review_actions`: A/B/C 각각의 review_actions 리스트
   - `analysis_flags.arb_actions`: Arbiter의 review_actions

3. **메트릭 생성 확인**
   - `--with_metrics`로 재실행 후 `derived/metrics/structural_metrics.csv`, `metric_report.html` 생성 여부 확인
