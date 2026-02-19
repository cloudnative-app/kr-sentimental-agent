# cr_v2_n100 M0 vs M1 v1 비교 보고서

**실험**: cr_v2_n100_m0_v1, cr_v2_n100_m1_v1  
**시드**: 42, 123, 456 (3개)  
**데이터**: beta_n100 (n=100)

---

## 1. 페이퍼 메트릭 비교표

### Table 1 — Surface / Schema / Error Control

| 구분 | Metric | M0 | M1 | Δ (M1−M0) | 95% CI | Direction |
|-----|--------|-----|-----|-----------|--------|-----------|
| **Aspect-Term Sentiment F1 (ATSA-F1)** | tuple_f1_s2_otepol | 0.6861 ± 0.0208 | 0.6611 ± 0.0614 | -0.0250 | [-0.1083, 0.0750] | ↓ |
| **Aspect-Category Sentiment F1 (ACSA-F1)** | tuple_f1_s2_refpol | 0.3833 ± 0.0136 | 0.5333 ± 0.0471 | 0.1500 | [0.1000, 0.2167] | ↑ |
| **#attribute f1** | tuple_f1_s2_attrpol | 0.5500 ± 0.0000 | 0.7667 ± 0.0236 | 0.2167 | - | ↑ |
| **polarity accuracy** | (generalized_f1_theta) | N/A | N/A | - | - | - |
| **Schema Assignment Completeness** | ref_fill_rate_s2 | 0.7652 ± 0.0217 | 0.6984 ± 0.0224 | -0.0668 | [-0.0752, -0.0549] | ↓ |
| **Schema Coverage** | ref_coverage_rate_s2 | 0.3968 ± 0.0224 | 0.5333 ± 0.0471 | 0.1365 | [0.0714, 0.2190] | ↑ |
| **Implicit Assignment Error Rate** | implicit_invalid_pred_rate | 0.0417 ± 0.0589 | 0.0000 ± 0.0000 | -0.0417 | - | ↓ |
| **Intra-Aspect Polarity Conflict Rate** | polarity_conflict_rate | 0.0333 ± 0.0236 | 0.0000 ± 0.0000 | -0.0333 | - | ↓ |
| **Error Correction Rate** | fix_rate_refpol | 0.0238 ± 0.0337 | 0.1111 ± 0.1571 | 0.0873 | [0.0000, 0.2619] | ↑ |
| **Error Introduction Rate** | break_rate_refpol | 0.0000 ± 0.0000 | 0.0000 ± 0.0000 | 0.0000 | [0.0000, 0.0000] | - |
| **Net Correction Gain** | net_gain_refpol | 0.0167 ± 0.0236 | 0.0667 ± 0.0943 | 0.0500 | [0.0000, 0.1500] | ↑ |
| **Run-to-Run Output Agreement** | Measurement IRR (meas_cohen) | 0.6246 ± 0.0933 | 0.6395 ± 0.3050 | 0.0149 | - | ↑ |
| **Inter-Reviewer Agreement (Action)** | Action IRR (irr_cohen) | 0.6260 ± 0.0932 | 0.5556 ± 0.3333 | -0.0704 | - | ↓ |
| **CDA** | cda | 1.0000 ± 0.0000 | 1.0000 ± 0.0000 | 0.00 | - | - |
| **AAR Majority Rate** | aar_majority_rate | 0.9894 ± 0.0075 | 1.0000 ± 0.0000 | 0.0106 | [0.0000, 0.0161] | ↑ |

**Note:** M1의 N_gold가 M0보다 낮음 (M0: 20, M1: 4.33). M1 시드별 gold 매칭 샘플 수가 적어 (n_samples 2~18 vs 16~18) IRR 해석 시 주의. polarity_accuracy는 structural_metrics에 별도 지표 없음.

- fix_rate: proportion of incorrect assignments corrected
- break_rate: new errors introduced during refinement
- net_gain: net positive correction
- Measurement IRR: stability across seeds (Cohen Kappa)
- Action IRR: reviewer decision consistency (Cohen Kappa)

---

## 2. cr_v2_patch 산출물 진단

### (1) granularity_overlap_candidate 발생 count

| 구분 | count |
|------|-------|
| M0 (seed 42, 123, 456) | 0 |
| M1 (seed 42, 123, 456) | 0 |
| **총계** | **0** |

**해석**: beta_n100 데이터셋에서 동일 attribute+polarity에서 "제품 전체"와 "본품"/"패키지·구성품"이 동시에 있는 케이스가 없음.

### (2) Review C에서 REDUNDANT_UPPER_REF로 DROP 발생 count

| 구분 | count |
|------|-------|
| M0 seed 42 | 3 |
| M0 seed 123 | 3 |
| M0 seed 456 | 4 |
| M1 seed 42 | 2 |
| M1 seed 123 | 2 |
| M1 seed 456 | 2 |
| **총계** | **16** |

**해석**: Review C가 REDUNDANT_UPPER_REF reason_code로 DROP을 제안한 케이스가 16건 발생. (granularity_overlap_candidate 플래그 없이도 다른 conflict 경로에서 발생 가능)

### (3) Arbiter Rule 3 수정으로 "1FLIP+1DROP+1KEEP → DROP 선택" 케이스 존재 여부

| 구분 | count |
|------|-------|
| M0 (seed 42, 123, 456) | 0 |
| M1 (seed 42, 123, 456) | 0 |
| **총계** | **0** |

**해석**: 1FLIP+1DROP+1KEEP 분기에서 Arbiter가 DROP을 선택한 케이스 없음. 해당 분기가 발생하지 않았거나, FLIP structural / DROP justified 조건이 동시에 만족되지 않음.

### (4) eval 정규화 적용 전/후 패키지/구성품 관련 FP/FN 변화

**패키지/구성품 관련 예시**: beta_n100 데이터셋에서 해당 패턴이 포함된 gold/pred 샘플이 없어 구체적 FP/FN 예시를 추출하지 못함.

**정규화 적용**: `normalize_ref_for_eval`에서 `패키지/구성품` → `패키지·구성품` 치환 추가됨. 단위 테스트 `test_normalize_ref_package_component_slash_to_midpoint`로 gold "패키지/구성품#일반" ↔ pred "패키지·구성품#일반" 매칭 검증 완료.

---

## 3. 실행 명령어 요약

```powershell
# compute_irr (시드별)
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v1__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v1__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v1__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v1__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v1__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v1__seed456_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v1__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v1__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v1__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v1__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v1__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v1__seed456_proposed/irr/

# aggregate_seed_metrics
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m0_v1__seed42_proposed,results/cr_v2_n100_m0_v1__seed123_proposed,results/cr_v2_n100_m0_v1__seed456_proposed --outdir results/cr_v2_n100_m0_v1_aggregated --metrics_profile paper_main
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m1_v1__seed42_proposed,results/cr_v2_n100_m1_v1__seed123_proposed,results/cr_v2_n100_m1_v1__seed456_proposed --outdir results/cr_v2_n100_m1_v1_aggregated --metrics_profile paper_main

# export_paper_metrics_aggregated
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_v2_n100_m0_v1_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_v2_n100_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs results/cr_v2_n100_m0_v1__seed42_proposed results/cr_v2_n100_m0_v1__seed123_proposed results/cr_v2_n100_m0_v1__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v1__seed42_proposed results/cr_v2_n100_m1_v1__seed123_proposed results/cr_v2_n100_m1_v1__seed456_proposed --out-dir results/cr_v2_n100_v1_comparison_paper

# diagnose_cr_v2_outputs
python scripts/diagnose_cr_v2_outputs.py --run-dirs results/cr_v2_n100_m0_v1__seed42_proposed,results/cr_v2_n100_m0_v1__seed123_proposed,results/cr_v2_n100_m0_v1__seed456_proposed,results/cr_v2_n100_m1_v1__seed42_proposed,results/cr_v2_n100_m1_v1__seed123_proposed,results/cr_v2_n100_m1_v1__seed456_proposed
```

---

## 4. 산출물 경로

| 항목 | 경로 |
|------|------|
| M0 aggregated | results/cr_v2_n100_m0_v1_aggregated/aggregated_mean_std.csv |
| M1 aggregated | results/cr_v2_n100_m1_v1_aggregated/aggregated_mean_std.csv |
| M0 vs M1 비교 | results/cr_v2_n100_v1_comparison_paper/paper_metrics_aggregated_comparison.md |
| IRR (시드별) | results/cr_v2_n100_*_proposed/irr/irr_run_summary.json |
