# RQ2·RQ3 가설 진단: implicit ↑ → polarity_conflict ↓ ? / explicit_failure ↓ → risk_resolution ↑ ?

**대상 런**: `mini4_proposed_2__seed42_proposed` vs `experiment_mini4_b1_4__seed42_proposed`  
**메트릭 소스**: 각 run `derived/metrics/structural_metrics_table.md` (N=10).  
**결과 재생성**: scorecards(gold) + structural_error_aggregator + RQ1 진단 재실행 반영.

---

## 1. 요약 표

| 메트릭 | proposed_2 | mini4_b1_4 | 방향 |
|--------|------------|------------|------|
| **RQ1** | | | |
| implicit_grounding_rate | **0.6000** | 0.4000 | proposed_2 ↑ |
| explicit_grounding_failure_rate | **0.2000** | 0.4000 | proposed_2 ↓ |
| **RQ2** | | | |
| polarity_conflict_rate | **0.8000** | 0.9000 | proposed_2 ↓ |
| stage_mismatch_rate | 0.0000 | 0.1000 | — |
| **RQ3** | | | |
| risk_resolution_rate (확장) | 1.0000 | 1.0000 | 동일 |
| risk_resolution_rate_legacy | 0.0000 | 0.0000 | 동일 |
| risk_flagged_rate | 0.9000 | 0.9000 | 동일 |
| risk_affected_change_rate | 0.2222 | 0.4444 | b1_4 ↑ |
| risk_resolved_with_change_rate | 0.0000 | 0.0000 | 동일 |
| ignored_proposal_rate | 0.7778 | 0.5556 | — |

---

## 2. RQ2: implicit 증가 → polarity_conflict_rate 감소?

**가설**: implicit fallback이 많아질수록(명시적 추론 실패를 문장급으로 흡수) aspect별 극성 충돌이 줄어든다.

**관측**:
- proposed_2: implicit **0.60**, polarity_conflict_rate **0.80**
- mini4_b1_4: implicit **0.40**, polarity_conflict_rate **0.90**

**해석**:
- **방향은 가설과 일치**: implicit가 더 높은 run(proposed_2)에서 polarity_conflict_rate가 더 낮음 (0.80 < 0.90).
- **가능한 메커니즘**: implicit로 빠진 샘플은 “대표 tuple 1개(문장급)”로 수렴하므로, 동일 aspect에 복수 극성이 남는 경우가 줄어들어 conflict 집계가 감소할 수 있음.
- **한계**: 런이 2개, N=10으로 표본이 작아 인과나 일반화는 단정할 수 없음. 추가 런·더 큰 N에서 재검증 필요.

**결론**: 현재 두 run 비교에서는 **implicit ↑ → polarity_conflict_rate ↓ 방향이 관측됨**. 가설을 지지하는 경향으로 해석 가능.

---

## 3. RQ3: explicit_failure 감소 → risk_resolution_rate 증가?

**가설**: explicit_failure가 줄면(명시적 추론 실패가 적으면) validator가 잡은 risk가 stage2에서 더 잘 해소되어 risk_resolution_rate가 올라간다.

**관측 (재생성 결과)**:
- proposed_2: explicit_failure **0.20**, risk_resolution_rate(확장) **1.00**, risk_resolution_rate_legacy **0.00**, risk_resolved_with_change_rate **0.00**
- mini4_b1_4: explicit_failure **0.40**, risk_resolution_rate(확장) **1.00**, risk_resolution_rate_legacy **0.00**, risk_resolved_with_change_rate **0.00**

**해석**:
- **explicit_failure는 가설대로**: proposed_2에서 더 낮음 (0.20 < 0.40).
- **risk_resolution_rate(확장)**: 분모를 stage1_structural_risk로 확장한 정의 적용 시 두 run 모두 **1.00**. **Differential Effect 미충족**: C1 vs C2에서 동일(1.00). **Change-Coupled Resolution 미충족**: risk_resolved_with_change_rate 두 run 모두 **0.00**.
- **원인 정리**:
  - `risk_resolution_rate` 정의: **(stage1에서 validator가 잡은 risk 수 − stage2 risk 수) / stage1 risk 수** (분모 > 0일 때).
  - 두 run 모두 **validator가 stage1에서 structural_risks를 잡은 샘플이 없음** (count_stage1_risks = 0) → 분모 0 → 0으로 산출.
  - 반면 `risk_flagged_rate`는 **확장 정의**(validator risk OR negation/contrast OR polarity_conflict OR alignment_failure≥2)라 0.9로, “위험 조건” 샘플은 많지만, “validator가 부여한 risk”가 없어 resolution률이 계산되지 않음.

**결론**: 확장 정의로 risk_resolution_rate는 이제 측정 가능(1.00)하지만, C1 vs C2 차이가 없고 risk_resolved_with_change_rate = 0이므로 **"성능 개선"이 아닌 "메트릭 정의 개선"**으로만 보고해야 함.

---

## 4. 권장 후속

| 목표 | 권장 |
|------|------|
| RQ2 추가 검증 | 더 많은 run·N, 또는 동일 설정에서 seed/구성 변경해 implicit vs polarity_conflict 재측정. |
| RQ3 검증 가능하게 | validator가 stage1에서 structural_risks를 내는 데이터/프롬프트·설정으로 실험하거나, negation/contrast 등이 포함된 valid set을 써서 risk_resolution_rate의 분모가 > 0이 되도록 설계. |
| 메트릭 정리 | risk_flagged(확장) vs “validator가 부여한 risk” 기준을 문서에 명시해, resolution률 해석 시 혼동을 줄이기. |

---

## 5. RQ3 개선 주장 전 검증 요건

RQ3에서 **"advisory memory가 structural risk 제어를 개선한다"**고 주장하기 전에는 아래 세 가지 검증을 충족해야 한다. 미충족 시 **"메트릭 정의 개선"**으로만 보고하고, **"성능 개선"**으로 주장하지 않는다.

- **1) Differential Effect**: risk_resolution_rate가 C1(memory OFF) vs C2(memory ON)에서 **다르게** 나와야 함 (동일 데이터·시드).
- **2) Change-Coupled Resolution**: risk_resolved_with_change_rate **> 0** (해소가 정의적 artifact가 아님을 확인).
- **3) Stability Check**: polarity_conflict_rate 등 안정성 메트릭이 memory ON에서 **악화되지 않아야** 함.

자세한 조건·보고 규칙: [Validation Requirements Before Claiming Improvement](validation_requirements_before_claiming_improvement.md).
