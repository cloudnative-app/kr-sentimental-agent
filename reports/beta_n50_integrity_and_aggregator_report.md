# Beta N50: 파이프라인 정합성 검사 및 에러 어그리게이터 결과 보고서

**실행 일시**: 2025-02-11  
**대상**: beta_n50 (C1, C2, C3, C2_eval_only) × seeds 42, 123, 456 (총 12 runs)

---

## 1. 파이프라인 정합성 검사 (pipeline_integrity_verification)

### 1.1 검사 항목

| 항목 | 설명 |
|------|------|
| **E2E record count** | outputs / scorecards / traces 레코드 수 일치 (N=50) |
| **S3 불변식** | debate_summary.final_tuples ≠ final_result.final_tuples 시 ev_decision=reject 등 |
| **PJ1** | aspect가 substring이 아닌 위반 |
| **metrics_pred_consistency** | scorecard ↔ structural_metrics pred 일치 |
| **selective_storage_mix** | store_write=true일 때 stored+skipped 혼재 |

### 1.2 결과 요약

| Run | E2E | S3 fail | PJ1 | metrics_consistency | storage_mix |
|-----|-----|---------|-----|---------------------|-------------|
| beta_n50_c1__seed42_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |
| beta_n50_c1__seed123_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |
| beta_n50_c1__seed456_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |
| beta_n50_c2__seed42_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c2__seed123_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c2__seed456_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c3__seed42_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c3__seed123_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c3__seed456_proposed | ✅ | 0 | 0 | ✅ | ✅ |
| beta_n50_c2_eval_only__seed42_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |
| beta_n50_c2_eval_only__seed123_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |
| beta_n50_c2_eval_only__seed456_proposed | ✅ | 0 | 0 | ✅ | ⚠️ |

### 1.3 selective_storage_mix 비고

- **C1, C2_eval_only**: `store_write=false` → 모든 샘플 `store_decision=skipped` (store_write_disabled).  
  `selective_storage_mix` 체크는 `store_write=true` 런용( stored+skipped 혼재 기대). C1/C2_eval에서 `storage_mix=False`는 **예상 동작**이며 오류 아님.

### 1.4 상세 결과 파일

- `reports/pipeline_integrity_beta_n50_beta_n50_<condition>__seed<N>_proposed.json`

---

## 2. structural_error_aggregator 실행

### 2.1 실행 내용

각 시드별 run에 대해 다음 명령으로 aggregator를 실행함:

```
python scripts/structural_error_aggregator.py --input results/<run>/scorecards.jsonl --outdir results/<run>/derived/metrics --profile paper_main
```

**산출물** (12 runs × 2):  
- `structural_metrics.csv`  
- `structural_metrics_table.md`

### 2.2 aggregate_seed_metrics 실행

조건별 시드 머징·평균±표준편차 및 통합 보고서 생성:

```
python scripts/aggregate_seed_metrics.py --base_run_id beta_n50_<c1|c2|c3|c2_eval_only> --seeds 42,123,456 --outdir results/beta_n50_<cond>_aggregated --metrics_profile paper_main
```

**산출물** (4 conditions):

| 조건 | 경로 | 내용 |
|------|------|------|
| C1 | `results/beta_n50_c1_aggregated/` | merged_scorecards.jsonl, merged_metrics/, aggregated_mean_std.csv, integrated_report.md |
| C2 | `results/beta_n50_c2_aggregated/` | 동일 |
| C3 | `results/beta_n50_c3_aggregated/` | 동일 |
| C2_eval_only | `results/beta_n50_c2_eval_only_aggregated/` | 동일 |

---

## 3. 집계 메트릭 요약 (시드 평균±SD)

### 3.1 RQ1 핵심 지표

| 조건 | unsupported_polarity_rate | severe_polarity_error_L3_rate | risk_resolution_rate | tuple_f1_s2_explicit_only |
|------|---------------------------|-------------------------------|----------------------|---------------------------|
| C1 | 0.0000 (0.0000) | 0.0867 (0.0189) | 1.0000 (0.0000) | 0.4110 (0.0148) |
| C2 | 0.0067 (0.0094) | 0.0733 (0.0094) | 1.0000 (0.0000) | 0.3945 (0.0276) |
| C3 | 0.0000 (0.0000) | 0.0733 (0.0094) | 1.0000 (0.0000) | 0.3833 (0.0552) |
| C2_eval_only | 0.0000 (0.0000) | 0.0667 (0.0094) | 1.0000 (0.0000) | 0.4208 (0.0110) |

### 3.2 메모리·드리프트 (C2 vs C1/C3)

| 조건 | memory_used_rate | drift_cause_memory_used_changed_n | drift_cause_memory_retrieved_changed_n |
|------|------------------|-----------------------------------|----------------------------------------|
| C1 | 0.0000 | 0 | 0 |
| C2 | 0.9800 (0.0000) | 22.33 (1.25) | 23.67 (1.25) |
| C3 | 0.0000 | 0 | 0 |
| C2_eval_only | 0.0000 | 0 | 0 |

---

## 4. 결론

- **파이프라인 정합성**: 12 runs 모두 E2E, S3, PJ1, metrics_pred_consistency **통과**. selective_storage_mix는 C1/C2_eval에서 store_write 비활성으로 인해 `False`이며 예상된 결과.
- **structural_error_aggregator**: 12 runs 모두 정상 실행, `structural_metrics.csv` 및 `structural_metrics_table.md` 생성 완료.
- **aggregate_seed_metrics**: 4 conditions 모두 머징·평균±표준편차·통합 보고서 생성 완료.
