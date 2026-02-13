# 02829 회귀테스트 결과 (c2_t1_proposed run 기준)

## 대상 run

- **run_dir**: `results/experiment_mini4_validation_c2_t1_proposed`
- **실행**: 터미널에서 저장된 결과  
  `[proposed] Saved outputs/traces/scorecards to results\experiment_mini4_validation_c2_t1_proposed`

## 회귀테스트 실행

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t1_proposed"
pytest tests/test_02829_regression.py -v
```

## 결과: **FAIL**

### 실패 내용

- **Assertion**: `S1: 피부톤 negative 존재`
- **의미**: 02829 레코드의 `final_result.stage2_tuples`에서 aspect "피부톤"에 **negative**가 없음.

### 02829 실제 값 (이번 run)

| 항목 | 기대 (회귀테스트) | 실제 (c2_t1_proposed) |
|------|-------------------|------------------------|
| S0 (stage1_tuples 피부톤) | neutral | neutral ✓ |
| S1 (stage2_tuples 피부톤) | negative 단일 | **neutral** ✗ |
| S2 (final_tuples 피부톤) | negative | **neutral** ✗ |
| override_reason | ≠ conflict_blocked | debate_action ✓ |
| override_effect_applied | true | true (scorecard) |

### 원인 (scorecard 기준)

- **debate_override_skip_reasons**: `L3_conservative: 1`
- **debate_override_stats**: `skipped_conflict: 1`
- Validator가 **CONTRAST** structural risk를 냈고, `l3_conservative` 정책으로 **override가 APPLY되지 않고 SKIP**된 run임.
- 따라서 게이트는 “APPLY”가 아니라 “SKIP” → S1/S2에 negative가 반영되지 않음.

### 회귀테스트가 기대하는 조건

- 02829에 대해 **게이트 APPLY** (neutral → negative 반영)가 일어난 run.
- 즉, **L3_conservative로 skip되지 않고**, **conflict_blocked도 아니며**, override가 실제로 적용되어 S1/S2가 negative인 경우.

### 정리

| 구분 | 내용 |
|------|------|
| **판정** | FAIL (현재 run_dir 기준) |
| **이유** | 이번 run에서는 02829가 L3_conservative로 override SKIP → S1/S2 neutral |
| **다음** | (1) L3_conservative를 완화하거나 02829를 L3 제외하도록 설정한 뒤 재실행하여 회귀테스트 통과 run 확보, 또는 (2) 02829 회귀테스트를 “override가 APPLY된 run만 대상”으로 제한하고, 이 run은 “SKIP 사례”로 별도 문서화 |

---
*작성: c2_t1_proposed run 회귀테스트 실행 후*
