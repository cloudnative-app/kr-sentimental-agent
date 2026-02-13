# Finalexperiment C2_1 점검 보고서 (PJ1–PJ4 검증)

**Run**: `finalexperiment_n50_seed1_c2_1__seed1_proposed`  
**검증 일시**: structural_metrics·pipeline_integrity 사후 집계 기준

---

## 1. 필수 산출/확인

| 항목 | 요구 | 결과 | 판정 |
|------|------|------|------|
| outputs.jsonl | 50줄 | 50줄 | **PASS** |
| scorecards.jsonl | 50줄 | 50줄 | **PASS** |
| override_gate_debug.jsonl | 50줄 또는 override 단위 증가 | 167줄 (per-aspect + ev_decision) | **PASS** |
| debate 로그/summary | 존재 | scorecards `meta.debate_summary`, `debate_override_stats`, `debate_mapping_*` 존재 | **PASS** |

- **override_gate_debug.jsonl**: 167줄 = aspect 단위 gate 레코드 + 샘플당 1줄 `type: ev_decision` (PJ3). override 체크 단위로 증가한 형태로 적합.

---

## 2. Invariants (재정의 후)

**재정의 (Action 1)**: S1/S2는 FAIL → EXPECTED. S3만 진짜 FAIL.

| Invariant | 요구 | 결과 | 판정 |
|-----------|------|------|------|
| e2e_record_count | outputs/scorecards/traces 각 50, pass | 50/50/50, pass=true | **PASS** |
| invariant_s1_expected | (기대: debate≠final 허용) | 50건 | **EXPECTED** |
| invariant_s2_expected | (기대: final_tuples≠final_aspects 허용) | 50건 | **EXPECTED** |
| aggregator_source_fallback | (정보용) | 2건 | — |
| **invariant_s3_fail** | **0건** (진짜 FAIL만) | **0건** | **PASS** |
| invariant_pj1_aspect_not_substring | 0건 | 0건 | **PASS** |
| metrics_pred_consistency | pass | pass=true, mismatches=[] | **PASS** |

**S3 FAIL 조건 (둘 중 하나라도 해당 시 FAIL)**  
1. debate_summary.final_tuples ≠ final_result.final_tuples 인데, ev_decision ≠ reject 이거나 ev_reason ∉ {low_ev, conflict, no_evidence, memory_contradiction}  
2. ∃ tuple ∈ final_tuples: tuple.aspect_ref(또는 term) ∉ final_aspects  

**요약**: 재정의 후 **invariant_s3_fail = 0건**이므로 invariants는 **전부 PASS**.

---

## 3. 필수 메트릭 (GO/NO-GO) — Action2/Action3 반영 후

집계: `results/.../derived/metrics/structural_metrics.csv` (structural_error_aggregator, profile=paper_main).  
**Action2**: aspect_hallucination_rate / alignment_failure_rate는 **final(patched_stage2 or final) 기준**으로 재계산.  
**Action3**: stage2_selected_rate·override_applied_rate 단독 대신 **changed_samples_rate**, **changed_and_improved_rate**, **changed_and_degraded_rate** 사용.

| 메트릭 | 요구 | C2_1 값 (재계산 후) | 판정 |
|--------|------|---------------------|------|
| aspect_hallucination_rate | PJ1 효과로 **급락** | **0.02** (final 기준) | **GO** (급락 달성) |
| alignment_failure_rate | **급락** | **0.02** (final 기준) | **GO** (급락 달성) |
| override_applied_rate | **0.10~0.20** (PJ2+PJ4) | **0.06** (3/50) | **NO-GO** (목표 미달) |
| changed_samples_rate | (변화 있었을 때만) | **0.06** (3/50) | — |
| changed_and_improved_rate | (변화 중 개선 비율) | **0.0** (0/3) | — |
| changed_and_degraded_rate | (변화 중 악화 비율) | **0.3333** (1/3) | — |
| n_stage2_selected (참고) | — | 48 | — |
| net_gain | 음수 고정 아님 (PJ3 최소 징후) | **0.0** | **GO** |

- **Action2 적용**: hallucination/alignment를 **final 출력 기준**으로 계산해 PJ1(substring 강제) 효과가 반영됨. 0.72 → 0.02로 급락.  
- **Action3**: 안정성은 changed_samples_rate, changed_and_improved_rate, changed_and_degraded_rate로 해석 (override_applied_rate 단독 ❌, stage2_selected_rate 단독 ❌).

---

## 4. 종합 판정

| 구분 | 결과 |
|------|------|
| **필수 산출/확인** | **PASS** (outputs/scorecards/override_gate_debug/debate 존재) |
| **Invariants 전부 PASS** | **PASS** (재정의 후 S1/S2=EXPECTED, S3 fail=0건) |
| **필수 메트릭 GO/NO-GO** | **부분 GO** (Action2 적용 후 aspect_hallucination·alignment 0.02로 급락 GO; override_applied_rate 0.10 미만 NO-GO; net_gain 0 GO) |

**결론**:  
- 파이프라인 산출물·디버그·debate 로그는 요구대로 존재하며, PJ1 substring invariant는 통과했다.  
- Invariant 재정의 후 S1/S2는 EXPECTED, S3 fail=0건이므로 **invariants 전부 PASS**이다.  
- **Action2** 적용으로 hallucination/alignment를 **final 기준**으로 재계산해 **PJ1 효과가 메트릭에 반영**됨 (0.72 → 0.02).  
- PJ2+PJ4 효과(override 0.10~0.20)는 이번 C2_1에서 0.06으로 미달.  
- **Action3** 적용으로 안정성은 changed_samples_rate, changed_and_improved_rate, changed_and_degraded_rate로 해석.  
- net_gain은 “음수 고정 아님” 조건을 만족한다.

---

## 5. Step 2) 매칭 실패 (정규화) — 확인 및 조치

**확인 포인트**  
- gold의 aspect_term 정규화 함수와 pred 정규화 함수가 **완전히 동일한지**  
- aspect_ref 매칭이 가능한 데이터면 **term 대신 aspect_ref로 매칭**하도록 evaluator 변경

**조치 완료**  
1. **정규화 통일**: gold·pred 모두 `tuple_from_sent` → `normalize_for_eval` / `normalize_polarity` 동일 적용 (metrics/eval_tuple.py).  
2. **aspect_ref 매칭**:  
   - `tuples_to_pairs_ref_fallback(tuples_set)`: (aspect_ref or aspect_term, polarity)로 pair 생성.  
   - `precision_recall_f1_tuple(..., match_by_aspect_ref=True)` (기본값): 위 pair로 F1 매칭.  
   - aspect_ref가 있으면 term 정규화 차이(공백/조사/특수문자/케이스)와 무관하게 ref 기준 매칭 가능.

**결과**: evaluator는 **aspect_ref 우선 매칭**으로 변경 완료. 기존 c2_1 run은 이미 완료된 scorecards 기준이라, **재실행 시** 새 evaluator가 적용되어 F1이 개선될 수 있음 (gold에 aspect_ref가 있는 샘플).

---

## 6. outputs.jsonl / final_aspects / aggregator 읽기 확인

| 항목 | 요구 | 결과 | 판정 |
|------|------|------|------|
| outputs.jsonl에 final_result.final_aspects | 저장됨 | 첫 줄 확인: `final_aspects` 키 존재, len≥1 | **PASS** |
| scorecards에 final_aspects | runtime.parsed_output.final_result 내 존재 | 첫 줄 확인: `final_aspects` 키 존재, len≥1 | **PASS** |
| aggregator가 final_aspects 사용 | final_result에서 final_aspects 또는 final_tuples→재구성 사용 | `_extract_final_tuples_with_source`: final_aspects 우선, 없으면 final_tuples에서 재구성 | **PASS** |
| N_pred_final_aspects | 0이면 FAIL | 48 (0 아님) | **PASS** |

- **outputs.jsonl**: run_experiments에서 payload 작성 직후 `final_aspects` 없으면 `final_aspects_from_final_tuples(final_tuples)`로 채운 뒤 기록 → outputs.jsonl·scorecards 모두 동일 payload 기준으로 final_aspects 보장.  
- **aggregator**: scorecards의 `record["runtime"]["parsed_output"]["final_result"]`에서 `final_aspects` 또는 `final_tuples` 읽음; `final_aspects`가 비어 있으면 `final_tuples`로 재구성 후 `FINAL_SOURCE_FINAL_ASPECTS`로 집계.

---

## 7. 참고 수치 (structural_metrics, 재집계 후)

- n: 50  
- N_pred_final_aspects: 48, N_pred_final_tuples: 0, N_pred_inputs_aspect_sentiments: 2  
- tuple_f1_s1 / tuple_f1_s2: 0.0000 (gold·pred의 aspect·polarity가 서로 달라 매칭 0건 → 정규화/aspect_ref 변경과 무관)  
- aspect_hallucination_rate: 0.02, alignment_failure_rate: 0.02 (final 기준)  
- changed_samples_rate: 0.06, changed_and_improved_rate: 0.0, changed_and_degraded_rate: 0.3333 (1/3)  
- override_applied: 3, stage_mismatch_rate: 0.0  
- validator_clear_rate: 1.0, outcome_residual_risk_rate: 0.06  
- invariant_pj1_aspect_not_substring: 0건

---

## 8. 메트릭 변화 요약 (코드 변경 대비)

**변화한 메트릭**  
- **N_pred_final_aspects**: final_aspects 우선(또는 final_tuples 재구성) 사용으로 **48**로 집계. 이전에는 final_tuples 우선 시 N_pred_final_tuples만 증가해 N_pred_final_aspects가 0이 될 수 있었음 → 이제 0이면 aggregator FAIL.  
- **outputs.jsonl / scorecards**: payload 기록 직전에 final_aspects 보강 → 두 파일 모두 `final_result.final_aspects` 존재 보장.

**변화 없음(이유)**  
- **tuple_f1_s2 = 0.0000**: gold와 pred의 (aspect_ref or aspect_term, polarity) pair가 겹치지 않음. 샘플 확인 시 gold는 예) (제품 전체#일반, positive), pred는 예) (컨실러, neutral) 등 **서로 다른 aspect·polarity**라 매칭 0건. 정규화·aspect_ref 매칭을 바꿔도 “같은 관점인데 표기만 다름”인 경우가 아니면 F1은 그대로 0.  
- 즉, **정규화/매칭 방식 변경**은 “동일 관점인데 공백·조사·케이스만 다른 경우”에만 F1을 올리고, 현재 c2_1 run은 gold와 pred가 **관점·극성 자체가 다르기 때문에** 메트릭 변화가 없는 것이 맞음.
