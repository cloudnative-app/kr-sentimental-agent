# mini4_b1 / mini4_b1_2 메트릭·리포트 점검 결과

**실행**: structural_error_aggregator + build_metric_report 를 `results/experiment_mini4_b1__seed42_proposed`, `results/experiment_mini4_b1_2__seed42_proposed` 에 대해 재실행 후 점검.

---

## 1. polarity_conflict_rate — final-tuples 기반 동일-aspect 충돌만

**코드**: `structural_error_aggregator.has_same_aspect_polarity_conflict(record)` 만 사용. `_extract_final_tuples(record)` 로 final_tuples 추출 후, aspect_term별 polarity 집합에서 2개 이상이면 conflict. **RuleM/Stage mismatch 참조 없음.**

**재계산 결과** (mini4_b1, mini4_b1_2):
- **polarity_conflict_rate**: 0.9 (기존 단일 run CSV 0.0과 상이 — 새 정의 반영)
- 동일 aspect "피부톤"에 neutral/positive 등이 함께 있으면 conflict로 집계됨.

**결론**: ✅ final-tuples 기반 동일-aspect 충돌로만 동작함.

---

## 2. stage_mismatch_rate, n_trials, self_consistency_eligible — CSV·리포트 노출

**CSV** (`derived/metrics/structural_metrics.csv`):
- **stage_mismatch_rate**: 컬럼 존재, 값 출력 (mini4_b1: 0.0, mini4_b1_2: 0.0)
- **n_trials**: 컬럼 존재, 단일 run이면 **1**
- **self_consistency_eligible**: 컬럼 존재, 단일 run이면 **False**

**리포트** (metric_report.html):
- RQ1 테이블: **Polarity Conflict Rate (RQ1, same-aspect)**, **Stage Mismatch Rate (RQ2)** 행 있음.
- RQ2 테이블: **Self-consistency (exact)**, **Self-consistency eligible**, **n_trials** 행 있음.
- HF split 테이블: **Stage Mismatch Rate (RQ2: RuleM / S1≠S2)** 컬럼 있음.

**결론**: ✅ stage_mismatch_rate, n_trials, self_consistency_eligible 가 CSV·리포트에 실제로 찍힘.

---

## 3. self_consistency — trials 없을 때 null + eligible False

**단일 run** (mini4_b1, mini4_b1_2: 각 1개 scorecards.jsonl, case당 1행):
- **self_consistency_exact**: CSV에서 빈 값 (null). 테이블/리포트에서는 **N/A**.
- **self_consistency_eligible**: **False**
- **n_trials**: **1**
- **risk_set_consistency**, **variance**, **flip_flop_rate**: N/A (단일 run 경로에서 None 반환)

**결론**: ✅ trials 없을 때 self_consistency_exact=null, self_consistency_eligible=False, n_trials=1 로 나옴. 재계산만으로 확인 가능 (파이프라인 재 run 불필요).

---

## 4. override 지표 — executed / accepted / success 분리

**현재 집계**:
- **override_applied_rate**: 적용된 샘플 비율 (n_applied / N)
- **override_success_rate**: 적용된 케이스 중 risk 개선 비율 (stage1_risks > 0, stage2_risks < stage1_risks)
- **override_executed_rate**, **override_accepted_rate** 는 **별도 필드로 없음**.

**권장** (stop_the_line_checks.md):
- override_executed_rate: override 시도/실행 비율
- override_accepted_rate: accepted_changes 존재 비율
- override_success_rate: accepted subset에서만 계산

**결론**: ⚠️ override 지표에서 executed / accepted / success 는 **아직 분리되지 않음**. applied = “실행/적용”에 해당하고, success 는 applied 기준으로만 계산됨. accepted_changes 기반 accepted_rate·success(on accepted) 는 스키마/집계 추가 후 재계산 필요.

---

## 5. stage별 latency (debate rounds 포함) — 로그 여부

**현재**:
- **traces.jsonl**: 각 stage(stage1 ATE/ATSA/Validator, debate, stage2, moderator)별 항목 있음. 각 항목에 **call_metadata** (tokens_in, tokens_out, cost_usd) 있음. **latency_ms / latency_sec 는 stage별로 없음.**
- **총 지연**: scorecard **meta.latency_ms** (또는 trace 최상위 **latency_sec**) 만 존재 — 샘플당 전체 파이프라인 시간.

**결론**: ❌ stage별 latency(특히 debate rounds 구간)는 **현재 로그에 남지 않음**. debate round 수는 trace의 `stage: "debate"` 항목 개수로 추릴 수 있으나, 구간별 ms 는 기록되지 않음. **stage별 타이밍을 남기려면 파이프라인(run_experiments / supervisor)에서 stage 시작·종료 시점을 기록하도록 수정 후 재 run 이 필요함.**

---

## 6. 재계산 vs 파이프라인 재 run

| 항목 | 재계산만으로 확인 | 파이프라인 재 run 필요 |
|------|-------------------|-------------------------|
| polarity_conflict_rate (동일-aspect만) | ✅ aggregator 재실행으로 확인 | 아니오 |
| stage_mismatch_rate, n_trials, eligible CSV/리포트 | ✅ 재실행으로 확인 | 아니오 |
| self_consistency null + eligible False (단일 run) | ✅ 재실행으로 확인 | 아니오 |
| override executed/accepted/success 분리 | ❌ 스키마·집계 추가 후 재계산 | 새 필드 추가 후 재계산만 (run 불필요) |
| stage별 latency (debate 등) | ❌ 현재 데이터에 없음 | ✅ 예. 파이프라인에서 stage별 시간 기록 추가 후 재 run 필요 |

---

## 7. 수정한 코드 (이번 점검 중)

- **build_metric_report.py**: `risk_res`, `guided`, `unguided` 가 rq3_table에서 참조되기 전에 정의되지 않아 NameError 발생 → `struct_metrics` 에서 risk_resolution_rate, guided_change_rate, unguided_drift_rate 를 읽어 `risk_res`, `guided`, `unguided` 로 정의하는 코드 추가.
