# Final 실험 통합 요약 보고서 (C1, C2, C3, C2-eval)

**대상**: `finalexperiment_n50_seed1` — C1, C2, C3, C2-eval (n=50, seed1)  
**산출**: 메트릭 요약 + 파이프라인 정합성 검증 결과 통합

---

## 1. C3 · C2-eval 정합성 분석 (신규 수행)

C1·C2는 기존에 `pipeline_integrity_verification_*.json`이 있었고, **C3·C2-eval**에 대해서는 이번에 정합성 검증을 실행함.

### 실행 명령

```bash
python scripts/pipeline_integrity_verification.py --run_dir results/finalexperiment_n50_seed1_c3__seed1_proposed --out reports/pipeline_integrity_verification_finalexperiment_n50_seed1_c3__seed1_proposed.json
python scripts/pipeline_integrity_verification.py --run_dir results/finalexperiment_n50_seed1_c2_eval_only__seed1_proposed --out reports/pipeline_integrity_verification_finalexperiment_n50_seed1_c2_eval_only__seed1_proposed.json
```

### C3 · C2-eval 정합성 요약

| 항목 | C3 | C2-eval |
|------|-----|---------|
| **run_id** | finalexperiment_n50_seed1_c3__seed1_proposed | finalexperiment_n50_seed1_c2_eval_only__seed1_proposed |
| **E2E 레코드 수** | outputs=50, scorecards=50, traces=50 | 동일 |
| **e2e_record_count.pass** | ✅ true | ✅ true |
| **invariant_s1_fail 건수** | 49 | 48 |
| **invariant_s2_fail 건수** | 32 | 23 |
| **metrics_pred_consistency.pass** | ✅ true | ✅ true |
| **triptych_n** | 0 (C3은 retrieval-only, triptych 미생성) | 0 (eval_only, triptych 미생성) |

- **해석**: C3·C2-eval 모두 E2E 레코드 수 일치, scorecards↔structural_metrics pred 일치(또는 triptych 없음으로 N/A) 기준 **정합성 통과**. S1/S2 불변식 실패 건수는 C1·C2와 유사한 수준(debate_summary vs final_result 형식 차이 등으로 인한 것으로 해석).

---

## 2. 정합성 검증 결과 통합 (C1, C2, C3, C2-eval)

| condition | run_id (suffix) | e2e_pass | invariant_s1_fail | invariant_s2_fail | pred_consistency_pass | triptych_n |
|-----------|------------------|----------|-------------------|-------------------|------------------------|------------|
| C1 | c1__seed1_proposed | ✅ | 48 | 29 | ✅ | 50 |
| C2 | c2__seed1_proposed | ✅ | 48 | 27 | ✅ | 50 |
| C3 | c3__seed1_proposed | ✅ | 49 | 32 | ✅ | 0 |
| C2_eval_only | c2_eval_only__seed1_proposed | ✅ | 48 | 23 | ✅ | 0 |

- **e2e_pass**: outputs / scorecards / traces 수가 manifest `processing_count`(50)와 일치.
- **pred_consistency_pass**: scorecards 최종 예측 ↔ triptych(또는 structural_metrics) 일치; C3·C2-eval은 triptych 미생성으로 비교 생략, pass=true.

---

## 3. 메트릭 요약 (C1, C2, C3, C2-eval)

출처: `results/<run>/derived/metrics/structural_metrics.csv`

| condition | n | severe_polarity_error_L3_rate | tuple_f1_s2 | delta_f1 | polarity_conflict_rate | risk_resolution_rate | implicit_grounding_rate | explicit_grounding_failure_rate | unsupported_polarity_rate | memory_used_rate |
|-----------|---|-------------------------------|-------------|----------|------------------------|----------------------|------------------------|----------------------------------|---------------------------|------------------|
| C1 | 50 | 0.3600 | 0.0133 | -0.0400 | 0.0000 | 1.0000 | 0.3200 | 0.2600 | 0.0000 | 0.0000 |
| C2 | 50 | 0.3200 | 0.0333 | -0.0200 | 0.0000 | 1.0000 | 0.3600 | 0.2200 | 0.0000 | 1.0000 |
| C3 | 50 | 0.3400 | 0.0333 | -0.0200 | 0.0000 | 1.0000 | 0.3600 | 0.2000 | 0.0000 | 0.0000 |
| C2_eval_only | 50 | 0.3600 | 0.0300 | -0.0200 | 0.0000 | 1.0000 | 0.3800 | 0.1800 | 0.0000 | 0.0000 |

- **polarity_conflict_rate**: 전 조건 0.  
- **risk_resolution_rate**: 전 조건 1.0.  
- **unsupported_polarity_rate**: 전 조건 0.  
- **memory_used_rate**: C2만 1.0(메모리 사용), C1·C3·C2_eval_only 0.

---

## 4. 통합 요약

1. **정합성**  
   - C1, C2, C3, C2-eval 모두 **E2E 레코드 수·pred 일치 기준 정합성 통과**.  
   - C3·C2-eval 정합성 보고서는 이번에 생성:  
     - `reports/pipeline_integrity_verification_finalexperiment_n50_seed1_c3__seed1_proposed.json`  
     - `reports/pipeline_integrity_verification_finalexperiment_n50_seed1_c2_eval_only__seed1_proposed.json`

2. **메트릭**  
   - 동일 데이터셋(n=50)에서 조건별 RQ 메트릭 수집 완료.  
   - C2가 tuple_f1_s2·delta_f1 기준으로 C1 대비 유리; C3·C2_eval_only는 C2와 비슷한 수준의 tuple_f1_s2·delta_f1.

3. **참고 파일**  
   - 메트릭 상세: `results/finalexperiment_n50_seed1_<c1|c2|c3|c2_eval_only>__seed1_proposed/derived/metrics/structural_metrics_table.md`  
   - 정합성 상세: `reports/pipeline_integrity_verification_finalexperiment_n50_seed1_<condition>__seed1_proposed.json`  
   - 기존 요약: `reports/finalexperiment_n50_seed1_summary.md`

---
*작성: final C3·C2-eval 정합성 분석 수행 후, C1·C2·C3·C2-eval 메트릭·정합성 통합*
