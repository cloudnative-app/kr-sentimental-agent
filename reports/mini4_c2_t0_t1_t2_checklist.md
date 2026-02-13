# Mini4 C2 T0/T1/T2 Override Gate 체크리스트

같은 10샘플(seed 42)로 C2만 3조건 연속 실행.
- **T0**: min_total=1.6, min_margin=0.8, min_target_conf=0.7, l3_conservative=true
- **T1**: min_total=1.0, min_margin=0.5, min_target_conf=0.6, l3_conservative=true
- **T2**: min_total=0.6, min_margin=0.3, min_target_conf=0.55, **l3_conservative=false**

## 1. override_applied_rate가 T1/T2에서 0이 아닌가?

| 조건 | override_applied_n | override_applied_rate |
|------|--------------------|----------------------|
| T0   | 4 | 0.4 |
| T1   | 2 | 0.2 |
| T2   | 5 | 0.5 |

**Yes**: T1, T2에서 override_applied_rate > 0 (또는 override_applied_n > 0).

## 2. skip_reason 분해: low_signal, action_ambiguity가 줄었는가?

- **T0**: low_signal=5, action_ambiguity=0, l3_conservative=0, implicit_soft_only=0, already_confident=0
  - rate: {'neutral_only': 0.6875, 'low_signal': 0.1562}
- **T1**: low_signal=3, action_ambiguity=0, l3_conservative=0, implicit_soft_only=0, already_confident=0
  - rate: {'neutral_only': 0.7857, 'low_signal': 0.1071}
- **T2**: low_signal=0, action_ambiguity=0, l3_conservative=0, implicit_soft_only=0, already_confident=0
  - rate: {'neutral_only': 0.4815}

**Yes**: low_signal T0→T1→T2 감소.
**Yes**: action_ambiguity T0→T1→T2 감소.

## 3. total, margin 분포가 threshold 근처에 몰려 있었는가?

- **T0** total_dist: min=0.0, mean=0.375, median=0.0, p90=1.6, max=1.6
  margin_dist: min=0.0, mean=0.375, median=0.0, p90=1.6, max=1.6
  threshold_near: total_near_rate=0.0, margin_near_rate=0.0
- **T1** total_dist: min=0.0, mean=0.2571, median=0.0, p90=1.04, max=1.6
  margin_dist: min=0.0, mean=0.2571, median=0.0, p90=1.04, max=1.6
  threshold_near: total_near_rate=0.1071, margin_near_rate=0.0
- **T2** total_dist: min=0.0, mean=0.7111, median=0.8, p90=1.6, max=1.6
  margin_dist: min=0.0, mean=0.7111, median=0.8, p90=1.6, max=1.6
  threshold_near: total_near_rate=0.0, margin_near_rate=0.0

역치 근처 비율이 높으면: 점수 계산/매핑이 구조적으로 역치 직전에서 잘리기 쉬움.

## 4. override 적용된 케이스만: conflict / L3 개선 vs 악화

| 조건 | polarity_conflict_rate | polarity_conflict_rate_after_rep | severe_polarity_error_L3_rate | explicit_grounding_failure_rate |
|------|------------------------|-----------------------------------|--------------------------------|----------------------------------|
| T0 | 0.0 | 0.0 | 0.1 | 0.1 |
| T1 | 0.0 | 0.0 | 0.1 | 0.1 |
| T2 | 0.0 | 0.0 | 0.2 | 0.4 |

Override 적용된 샘플만의 subset 메트릭은 aggregator에서 override_applied_* 로 제공:

| 조건 | override_applied_n | override_success_rate | override_applied_negation_contrast_failure_rate | override_applied_unsupported_polarity_rate |
|------|--------------------|------------------------|------------------------------------------------|---------------------------------------------|
| T0 | 4 | 0.0 | 0.0 | 0.75 |
| T1 | 2 | 0.0 | 0.0 | 1.0 |
| T2 | 5 | 0.0 | 0.0 | 0.8 |

→ T1/T2에서 override 적용이 늘어나도 polarity_conflict_rate, severe_L3, explicit_grounding_failure가 크게 악화되지 않으면 역치 완화 가능.

---
## 요약

1. **override_applied_rate T1/T2 > 0?** Yes
2. **skip_reason low_signal/action_ambiguity 감소?** (위 표 참고)
3. **total/margin threshold 근처 몰림?** (threshold_near_rate 참고)
4. **override 적용 시 conflict/L3 개선 vs 악화?** (위 표 참고)

**3인(analyst/critic/empath) 구조**: critic neg + empath pos → total은 커질 수 있으나 margin 작아 action_ambiguity 다수. analyst 중립/보수 → total<1.6으로 low_signal 폭증. 현재 1.6/0.8은 다수 합의·한쪽 강승이어야만 적용이라 override 0도 자연스러움.
