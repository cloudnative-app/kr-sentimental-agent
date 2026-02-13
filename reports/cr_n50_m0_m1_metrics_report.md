# CR n50 M0/M1 메트릭 재생성 결과 보고

**실행일**: 2025-02-12  
**대상**: cr_n50_m0, cr_n50_m1 (시드 42, 123, 456)

---

## 1. 실행한 작업

| 단계 | 스크립트 | 대상 |
|------|----------|------|
| 1 | build_run_snapshot | 시드별 run_dir |
| 2 | structural_error_aggregator | 시드별 scorecards → derived/metrics |
| 3 | aggregate_seed_metrics | M0/M1 각각 merged_scorecards, aggregated_mean_std |
| 4 | compute_irr | 시드별 outputs.jsonl → irr/ |
| 5 | export_paper_metrics_md | 시드별 paper_metrics.md, paper_metrics.csv |
| 6 | export_paper_metrics_aggregated | aggregated_mean_std → paper_metrics_aggregated.md |

---

## 2. 산출물 경로

| 조건 | 산출물 | 경로 |
|------|--------|------|
| M0 | 시드별 메트릭 | `results/cr_n50_m0__seed<N>_proposed/derived/metrics/` |
| M0 | IRR | `results/cr_n50_m0__seed<N>_proposed/irr/` |
| M0 | Aggregated | `results/cr_n50_m0_aggregated/` |
| M0 | Paper metrics | `results/cr_n50_m0_paper/paper_metrics_aggregated.md` |
| M1 | 시드별 메트릭 | `results/cr_n50_m1__seed<N>_proposed/derived/metrics/` |
| M1 | IRR | `results/cr_n50_m1__seed<N>_proposed/irr/` |
| M1 | Aggregated | `results/cr_n50_m1_aggregated/` |
| M1 | Paper metrics | `results/cr_n50_m1_paper/paper_metrics_aggregated.md` |

---

## 3. 집계 메트릭 요약 (Paper)

### Table 1. Overall Outcome (RQ1)

| metric | M0 | M1 |
|--------|-----|-----|
| tuple_f1_s1 | 0.4875 ± 0.0050 | 0.4963 ± 0.0102 |
| tuple_f1_s2 | 0.6034 ± 0.0099 | 0.6360 ± 0.0322 |
| delta_f1 | 0.1159 ± 0.0078 | 0.1396 ± 0.0387 |
| fix_rate | 0.2361 ± 0.0170 | 0.2914 ± 0.0494 |
| break_rate | 0.0000 ± 0.0000 | 0.0476 ± 0.0673 |
| net_gain | 0.2000 ± 0.0163 | 0.2410 ± 0.0446 |
| polarity_conflict_rate | 0.0000 ± 0.0000 | 0.0000 ± 0.0000 |

### Table 2. IRR (RQ2)

| metric | M0 | M1 |
|--------|-----|-----|
| irr_fleiss_kappa | -0.1648 ± 0.0124 | -0.1531 ± 0.0235 |
| irr_cohen_kappa_mean | 0.1423 ± 0.0118 | 0.1339 ± 0.0135 |
| irr_perfect_agreement_rate | 0.2290 ± 0.0046 | 0.2681 ± 0.0213 |
| irr_majority_agreement_rate | 0.4994 ± 0.0405 | 0.4511 ± 0.0552 |

### Table 3. Process Evidence (CR)

| metric | M0 | M1 |
|--------|-----|-----|
| conflict_detection_rate | 0.0800 ± 0.0163 | 0.0768 ± 0.0367 |
| pre_to_post_change_rate | 0.3933 ± 0.0340 | 0.4481 ± 0.0368 |
| review_nontrivial_action_rate | 0.9800 ± 0.0000 | 0.9867 ± 0.0094 |
| arb_nonkeep_rate | 0.9800 ± 0.0000 | 0.9867 ± 0.0094 |

---

## 4. 참고 사항

- **M0**: merged_scorecards 150 rows (N=50 × 3 seeds)
- **M1**: merged_scorecards 133 rows (seed456에서 N=33 — 일부 샘플 누락 가능)
- **IRR**: compute_irr 시 statsmodels kappa 비분율 경고가 발생할 수 있음 (정상 동작)
- **Paper metrics**: `results/cr_n50_m0_paper/`, `results/cr_n50_m1_paper/` 에서 상세 확인
