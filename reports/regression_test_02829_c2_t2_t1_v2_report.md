# 02829 회귀테스트 결과 — C2 T2 v2 / C2 T1 v2

## 요약

- **대상 결과**: `c2_t2_v2`, `c2_t1_v2` 실험 결과 디렉터리  
  (`results/experiment_mini4_validation_c2_t2_v2_proposed`,  
   `results/experiment_mini4_validation_c2_t1_v2_proposed`)
- **보고서 생성 여부**: 이 결과는 **c2_t2_v2 / c2_t1_v2 전용 회귀테스트 보고서**가 아니었음.  
  기존 `reports/regression_test_02829_c2_t2_report.md`는 v2 디렉터리가 없던 시점에 **c2_t2_proposed**만 사용한 보고서임.  
  따라서 **v2 결과에 대해 회귀테스트를 새로 실행**하고 본 보고서로 정리함.

## 실행 조건

| 항목 | 값 |
|------|-----|
| T2 run_dir | `results/experiment_mini4_validation_c2_t2_v2_proposed` |
| T1 run_dir | `results/experiment_mini4_validation_c2_t1_v2_proposed` |
| 테스트 | `tests/test_02829_regression.py` (T2: override APPLY, T1: L3 blocks override) |

## 실행 명령

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t2_v2_proposed"
$env:REGRESSION_02829_T1_RUN_DIR = "results\experiment_mini4_validation_c2_t1_v2_proposed"
python -c "
import sys; sys.path.insert(0,'.')
from tests.test_02829_regression import test_02829_override_effect_applied_and_final_negative, test_02829_t1_l3_conservative_blocks_override
test_02829_override_effect_applied_and_final_negative()
print('T2: PASS')
test_02829_t1_l3_conservative_blocks_override()
print('T1: PASS')
"
```

## 결과

| 테스트 | 결과 | 비고 |
|--------|------|------|
| **T2** (`test_02829_override_effect_applied_and_final_negative`) | **PASS** | S0 neutral, S1/S2 피부톤 negative, override_effect_applied=true, override_reason ≠ conflict_blocked |
| **T1** (`test_02829_t1_l3_conservative_blocks_override`) | **PASS** | 02829에서 L3로 override 막힌 경우 override_applied/override_effect_applied=false, override_reason=l3_conservative |

**종합: c2_t2_v2 / c2_t1_v2 결과에 대한 02829 회귀테스트 모두 통과.**

---
*작성: c2_t2_v2_proposed, c2_t1_v2_proposed 기준 02829 회귀테스트 실행 후*
