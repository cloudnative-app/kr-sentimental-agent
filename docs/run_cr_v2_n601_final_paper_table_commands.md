# CR v2 n601 S0/M0/M1 Final Paper Table 생성 명령어

데이터: `beta_n601/valid`, 시드: 42, 123, 456  
산출: `reports/cr_v2_n601_v1_final_paper_table.md` (5.1 Surface ~ 5.4 Stochastic + Appendix)

---

## 사전 요구사항

- S0, M0, M1 파이프라인 실행 완료
- 시드별 메트릭 머지 및 집계 완료 (`aggregate_seed_metrics`)
- **Micro F1**: `structural_error_aggregator`가 `tuple_f1_s2_*_micro`, `tuple_f1_s2_*_tp/fp/fn` 출력 (최신 버전)
- **Subset 분석**: triptych.csv 생성 (`--export_triptych_table`)

---

## 1. Triptych 생성 (Subset 분석용, 선택)

Subset conditional 테이블(5.1.2, 5.2.2 등)을 채우려면 triptych가 필요합니다.

```powershell
# S0 (aggregated 또는 seed42)
python scripts/structural_error_aggregator.py --input results/cr_v2_n601_s0_v1_aggregated/merged_scorecards.jsonl --outdir results/cr_v2_n601_s0_v1_aggregated/merged_metrics --profile paper_main --export_triptych_table results/cr_v2_n601_s0_v1_aggregated/derived_subset/triptych.csv --triptych_sample_n 0

# M0
python scripts/structural_error_aggregator.py --input results/cr_v2_n601_m0_v1_aggregated/merged_scorecards.jsonl --outdir results/cr_v2_n601_m0_v1_aggregated/merged_metrics --profile paper_main --export_triptych_table results/cr_v2_n601_m0_v1_aggregated/derived_subset/triptych.csv --triptych_sample_n 0
```

또는 per-seed triptych 사용:

```powershell
# S0 seed42
python scripts/structural_error_aggregator.py --input results/cr_v2_n601_s0_v1__seed42_proposed/scorecards.jsonl --outdir results/cr_v2_n601_s0_v1__seed42_proposed/derived_subset --profile paper_main --export_triptych_table results/cr_v2_n601_s0_v1__seed42_proposed/derived_subset/triptych.csv --triptych_sample_n 0

# M0 seed42
python scripts/structural_error_aggregator.py --input results/cr_v2_n601_m0_v1__seed42_proposed/scorecards.jsonl --outdir results/cr_v2_n601_m0_v1__seed42_proposed/derived_subset --profile paper_main --export_triptych_table results/cr_v2_n601_m0_v1__seed42_proposed/derived_subset/triptych.csv --triptych_sample_n 0
```

---

## 2. Final Paper Table 생성

```powershell
python scripts/final_paper_table.py `
  --agg-s0 results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv `
  --agg-m0 results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv `
  --agg-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv `
  --run-dirs-s0 results/cr_v2_n601_s0_v1__seed42_proposed results/cr_v2_n601_s0_v1__seed123_proposed results/cr_v2_n601_s0_v1__seed456_proposed `
  --run-dirs-m0 results/cr_v2_n601_m0_v1__seed42_proposed results/cr_v2_n601_m0_v1__seed123_proposed results/cr_v2_n601_m0_v1__seed456_proposed `
  --run-dirs-m1 results/cr_v2_n601_m1_v1__seed42_proposed results/cr_v2_n601_m1_v1__seed123_proposed results/cr_v2_n601_m1_v1__seed456_proposed `
  --triptych-s0 results/cr_v2_n601_s0_v1_aggregated/derived_subset/triptych.csv `
  --triptych-m0 results/cr_v2_n601_m0_v1_aggregated/derived_subset/triptych.csv `
  --out reports/cr_v2_n601_v1_final_paper_table.md
```

(한 줄로, triptych 없이 subset 생략):

```powershell
python scripts/final_paper_table.py --agg-s0 results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv --agg-m0 results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs-s0 results/cr_v2_n601_s0_v1__seed42_proposed results/cr_v2_n601_s0_v1__seed123_proposed results/cr_v2_n601_s0_v1__seed456_proposed --run-dirs-m0 results/cr_v2_n601_m0_v1__seed42_proposed results/cr_v2_n601_m0_v1__seed123_proposed results/cr_v2_n601_m0_v1__seed456_proposed --run-dirs-m1 results/cr_v2_n601_m1_v1__seed42_proposed results/cr_v2_n601_m1_v1__seed123_proposed results/cr_v2_n601_m1_v1__seed456_proposed --out reports/cr_v2_n601_v1_final_paper_table.md
```

---

## 3. 전체 워크플로우 (처음부터)

```powershell
# 1) S0, M0, M1 파이프라인
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_s0_v1.yaml --run-id cr_v2_n601_s0_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_m0_v1.yaml --run-id cr_v2_n601_m0_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_m1_v1.yaml --run-id cr_v2_n601_m1_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3

# 2) IRR (M0, M1)
python scripts/compute_irr.py --input results/cr_v2_n601_m0_v1__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n601_m0_v1__seed42_proposed/irr --scorecards results/cr_v2_n601_m0_v1__seed42_proposed/scorecards.jsonl
# ... (나머지 시드 동일)

# 3) 시드별 집계
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_s0_v1__seed42_proposed,results/cr_v2_n601_s0_v1__seed123_proposed,results/cr_v2_n601_s0_v1__seed456_proposed --outdir results/cr_v2_n601_s0_v1_aggregated --metrics_profile paper_main
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_m0_v1__seed42_proposed,... --outdir results/cr_v2_n601_m0_v1_aggregated --metrics_profile paper_main
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_m1_v1__seed42_proposed,... --outdir results/cr_v2_n601_m1_v1_aggregated --metrics_profile paper_main

# 4) Final Paper Table
python scripts/final_paper_table.py --agg-s0 results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv --agg-m0 results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs-s0 ... --run-dirs-m0 ... --run-dirs-m1 ... --triptych-s0 ... --triptych-m0 ... --out reports/cr_v2_n601_v1_final_paper_table.md
```

---

## Subset Partition Verification

**Subset partitions are mutually exclusive and exhaustive.** Weighted recomputation across subsets exactly matches overall micro-F1.

서브셋 생성 기준: `docs/cr_v2_subset_partition.md`

---

## 산출물

| 항목 | 경로 |
|------|------|
| Final Paper Table | reports/cr_v2_n601_v1_final_paper_table.md |
| S0 aggregated | results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv |
| M0 aggregated | results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv |
| M1 aggregated | results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv |
