# T0 / T1 / T2 오버라이드 파라미터 및 런·영향 정리

기존 docs/reports에서 T0·T1·T2 설정, 런 결과, 역치·범위 영향 분석을 모은 요약입니다.  
출처: `reports/t0_t1_t2_config_comparison.md`, `reports/mini4_c2_t0t1t2_02829_and_override_safety_report_20250210.md`, `reports/mini4_c2_t0_t1_t2_checklist_v2.md`, `reports/t1_metrics_summary_report.md`, `reports/regression_test_02829_spec.md`, 실험 YAML.

---

## 1. T0 / T1 / T2 파라미터 정의

mini4 C2 검증 실험의 **debate override 게이트** 3단계. 데이터·백본·메모리(C2)·실험 옵션은 동일하고 **`pipeline.debate_override`만** 다름.

| 파라미터 | T0 (기준선) | T1 (완화) | T2 (매우 완화) |
|----------|-------------|-----------|----------------|
| **min_total** | **1.6** | **1.0** | **0.6** |
| **min_margin** | **0.8** | **0.5** | **0.3** |
| **min_target_conf** | **0.7** | **0.6** | **0.55** |
| **l3_conservative** | **true** | **true** | **false** |

- **ev_threshold**: 문서/보고서에서 별도 변경 없으면 기본 0.5로 동일.
- **설정 파일**: `experiment_mini4_validation_c2_t0.yaml`, `_t1.yaml`, `_t2.yaml`.

---

## 2. 설정 의도 (문서 기준)

| Run | 의도 |
|-----|------|
| **T0** | 현재 역치(게이트 기준선). 적용이 거의 안 나오는 **엄격한** 게이트. |
| **T1** | **완화** — “적용률이 생기게”. L3 보수적 규칙 유지. |
| **T2** | **매우 완화** — “게이트가 문제인지 확정”. 역치 추가 완화 + **l3_conservative만 false**로 해제. |

- **T0 → T1**: 역치만 완화 → override 적용 기회 증가 목적.
- **T1 → T2**: 역치 추가 완화 + L3 conservative 해제 → 게이트 자체가 병목인지 확인 목적.

---

## 3. 런 결과·범위 영향 (보고서 요약)

### 3.1 override 적용률 (aspect 단위 / run 단위)

- **override_gate_debug_summary 기준 (aspect 단위, 20250209 결과)**  
  - T0: decision_applied_n 5 / n_aspects 32 ≈ **15.6%**  
  - T1: 3 / 28 ≈ **10.7%**  
  - T2: 14 / 27 ≈ **51.9%**  
  → **기대(T0 < T1 < T2)와 불일치**: T1이 T0보다 낮음. 역치 완화만으로 T1에서 적용률이 선형 증가하지 않음.

- **다른 run(체크리스트 v2)**  
  - T0: override_applied_n 5, rate 0.5  
  - T1: 8, 0.8  
  - T2: 5, 0.5  
  → run·샘플 수에 따라 T0/T1/T2 순서가 달라질 수 있음. **T1·T2에서 override_applied_rate > 0** 은 확인됨.

### 3.2 low_signal / skip_reason

- **low_signal 건수**: T0 5 → T1 3 → T2 **0** (한 보고서 기준). **low_signal 비중 T0→T1→T2 감소** ✓  
- **neutral_only**: T0 22 → T1 22 → T2 13 (동일 보고서). T2에서 감소.  
- **skip_reason 분포 (체크리스트 v2)**  
  - T0: low_signal, l3_conservative 등  
  - T1: low_signal 위주  
  - T2: low_signal=0, action_ambiguity=0, l3_conservative=0 → **neutral_only 위주**.

→ 역치 완화·L3 해제에 따라 **low_signal / action_ambiguity / L3로 인한 skip이 줄어드는** 경향.

### 3.3 total·margin 분포와 역치 근접도

- **total_dist / margin_dist**: T0 mean 0.64 → T1 0.41 → T2 0.33 수준으로, 역치 완화에 따라 “통과 가능” 구간이 넓어짐.  
- **threshold_near_rate**: 역치 직전(total ∈ [min_total−0.2, min_total] 등)에 몰린 비율.  
  - 한 run에서 T0/T2는 total_near_rate=0, T1만 0.1034 등으로 보고됨.  
  → “점수 계산/매핑이 역치 직전에서 잘리는” 구조적 경향은 run별로 상이.

### 3.4 Safety 메트릭 (conflict / L3 / grounding)

- **polarity_conflict_rate**: T0·T1·T2 모두 **0** 유지.  
- **severe_polarity_error_L3_rate**: T0 0.1 → T1·T2 0.2로 **소폭 상승** (역치 완화·override 증가에 따른 트레이드오프로 해석, 모니터링 권장).  
- **explicit_grounding_failure_rate**: 한 보고서에서 T0·T1 0.2 → T2 0.1로 **감소**.  
- **override 적용 케이스만**: override_applied_negation_contrast_failure_rate 0 유지, override_applied_unsupported_polarity_rate는 T0 0.8 → T2 0.6 등으로 run에 따라 개선 가능.

→ **conflict는 유지**, **L3는 소폭 악화 가능**, **grounding failure는 T2에서 개선**된 run도 있음.

---

## 4. 02829(피부톤) 케이스와 회귀 테스트

- **목적**: `_adopt_stage2_decision`의 치환/대표선택 → conflict 체크 순서 변경 후, 02829/피부톤에서 override가 정상 적용되는지 검증.  
- **T0**: 02829/피부톤에 대해 aspect_hints 2개·pos/neg 0 → neutral_only + low_signal만 존재, **(B) 불충족**.  
- **T1/T2**: 동일 aspect에 대해 pos/neg 힌트·total=1.6·APPLY 경로 존재 → **(B) 충족**.  
  - 단, scorecard 기준 02829는 T1/T2 모두 **override_applied=false, conflict_blocked** 로 최종 적용이 막힌 run도 있음(구현/대표선택 순서 반영 전).  
- **회귀 명세**: S0 피부톤 neutral → S1/S2 피부톤 negative, conflict_blocked=false, override_effect_applied=true 기대.  
  - 상세: `reports/regression_test_02829_spec.md`.

---

## 5. 결론·권장 (기존 문서 종합)

1. **파라미터**: T0=엄격(1.6/0.8/0.7, L3 on), T1=완화(1.0/0.5/0.6, L3 on), T2=매우 완화(0.6/0.3/0.55, L3 off).  
2. **override 적용률**: run·샘플에 따라 **T0 < T1 < T2** 가 항상 성립하지 않음. T1에서 T0보다 낮게 나온 run 있음.  
3. **low_signal 비중** 및 **L3/action_ambiguity로 인한 skip**은 T0→T1→T2로 **감소** 경향.  
4. **Safety**: conflict 0 유지, L3_rate 소폭 상승 가능, explicit_grounding_failure는 T2에서 개선된 run 있음.  
5. **pretest_c2_2** 등 다른 실험에서 T2와 동일한 수치(0.6/0.3/0.55, l3_conservative=false)를 쓰면 **T2와 동일한 게이트**가 적용됨.

---

## 6. 참고 문서·설정

| 문서 | 내용 |
|------|------|
| `reports/t0_t1_t2_config_comparison.md` | T0/T1/T2 파라미터 비교·의도 |
| `reports/mini4_c2_t0t1t2_02829_and_override_safety_report_20250210.md` | 02829/피부톤, override_applied_rate, low_signal, safety 메트릭 |
| `reports/mini4_c2_t0_t1_t2_checklist_v2.md` | override_applied_n/rate, skip_reason, total/margin 분포, override 적용 시 conflict/L3 |
| `reports/t1_metrics_summary_report.md` | T1 run 메트릭·override 사유 분포 |
| `reports/regression_test_02829_spec.md` | 02829 회귀 테스트 기대값·검증 방법 |
| `docs/override_rules.md` | 게이트 판정 순서·파라미터 의미 |
| `experiments/configs/experiment_mini4_validation_c2_t0.yaml` (t1, t2) | 실제 설정 파일 |
