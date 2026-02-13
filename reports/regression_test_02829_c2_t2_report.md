# 02829 회귀테스트 결과 — C2 T2

## 대상 run

- **요청**: c2_t2_v2 결과에 대한 회귀테스트
- **실제 사용 run_dir**: `results/experiment_mini4_validation_c2_t2_proposed`  
  (디렉터리 `experiment_mini4_validation_c2_t2_v2_proposed` 없음 → 기존 C2 T2 run으로 실행)

## 실행

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t2_proposed"
python -c "import sys; sys.path.insert(0,'.'); from tests.test_02829_regression import test_02829_override_effect_applied_and_final_negative; test_02829_override_effect_applied_and_final_negative(); print('PASS')"
```

## 결과: **PASS**

- 02829 회귀테스트 **통과**.
- T2 run (l3_conservative=false) 기준: S0 neutral, S1/S2 피부톤 negative, override_reason ≠ conflict_blocked, override_effect_applied=true 조건을 만족한 것으로 판단.

## 참고

- **c2_t2_v2**: `results/experiment_mini4_validation_c2_t2_v2_proposed` 디렉터리가 없어, 동일 설정의 기존 run `experiment_mini4_validation_c2_t2_proposed`로 테스트함.
- v2 전용 결과로 다시 테스트하려면 `--run-id experiment_mini4_validation_c2_t2_v2` 로 실험을 완료한 뒤,  
  `REGRESSION_02829_RUN_DIR=results\experiment_mini4_validation_c2_t2_v2_proposed` 로 동일 테스트 실행하면 됨.

---
*작성: C2 T2 run_dir 기준 02829 회귀테스트 실행 후*
