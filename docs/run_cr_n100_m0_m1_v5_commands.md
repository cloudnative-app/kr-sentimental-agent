# CR n100 M0/M1 v5 실험 실행 명령어

**설정**: n=100, seeds=[42, 123, 456, 789, 101], concurrency=5  
**v5 변경점**: conflict_flags ref 기준 primary, term 기준 secondary. `pipeline.conflict_mode: primary_secondary`, `semantic_conflict_enabled: false`

---

## 1. 데이터셋 생성

```powershell
python scripts/make_beta_n50_dataset.py --valid_size 100 --outdir experiments/configs/datasets/beta_n100 --seed 100
```

- 입력: `experiments/configs/datasets/train/valid.jsonl`
- 출력: `experiments/configs/datasets/beta_n100/train.csv`, `valid.csv`, `valid.gold.jsonl`
- seed=100으로 shuffle 후 valid 100개 추출 (beta_n50 seed=77과 구분)

---

## 2. 파이프라인 (run_pipeline) — paper 프로파일, 메트릭스, 어그리게이터

### M0 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n100_m0_v5.yaml --run-id cr_n100_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate
```

### M1 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n100_m1_v5.yaml --run-id cr_n100_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate
```

---

## 3. 메트릭스 (structural_error_aggregator)

파이프라인 `--with_metrics` 시 자동 실행됨. 수동 실행:

### M0 v5

```powershell
python scripts/structural_error_aggregator.py --input results/cr_n100_m0_v5_aggregated/merged_scorecards.jsonl --outdir results/cr_n100_m0_v5_aggregated/merged_metrics --profile paper_main
```

### M1 v5

```powershell
python scripts/structural_error_aggregator.py --input results/cr_n100_m1_v5_aggregated/merged_scorecards.jsonl --outdir results/cr_n100_m1_v5_aggregated/merged_metrics --profile paper_main
```

---

## 4. 어그리게이터 (aggregate_seed_metrics)

파이프라인 `--with_aggregate` 시 자동 실행됨. 수동 실행:

### M0 v5

```powershell
python scripts/aggregate_seed_metrics.py --base_run_id cr_n100_m0_v5 --mode proposed --seeds 42,123,456,789,101 --outdir results/cr_n100_m0_v5_aggregated --metrics_profile paper_main
```

### M1 v5

```powershell
python scripts/aggregate_seed_metrics.py --base_run_id cr_n100_m1_v5 --mode proposed --seeds 42,123,456,789,101 --outdir results/cr_n100_m1_v5_aggregated --metrics_profile paper_main
```

---

## 5. 페이퍼 메트릭 (export_paper_metrics)

### M0 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n100_m0_v5 --mode proposed --out-dir results/cr_n100_m0_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m0_v5__seed42_proposed results/cr_n100_m0_v5__seed123_proposed results/cr_n100_m0_v5__seed456_proposed results/cr_n100_m0_v5__seed789_proposed results/cr_n100_m0_v5__seed101_proposed --out-dir results/cr_n100_m0_v5_paper
```

### M1 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n100_m1_v5 --mode proposed --out-dir results/cr_n100_m1_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m1_v5__seed42_proposed results/cr_n100_m1_v5__seed123_proposed results/cr_n100_m1_v5__seed456_proposed results/cr_n100_m1_v5__seed789_proposed results/cr_n100_m1_v5__seed101_proposed --out-dir results/cr_n100_m1_v5_paper
```

### M0 vs M1 비교 (comparison)

```powershell
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m0_v5_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_n100_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m0_v5__seed42_proposed results/cr_n100_m0_v5__seed123_proposed results/cr_n100_m0_v5__seed456_proposed results/cr_n100_m0_v5__seed789_proposed results/cr_n100_m0_v5__seed101_proposed --run-dirs-m1 results/cr_n100_m1_v5__seed42_proposed results/cr_n100_m1_v5__seed123_proposed results/cr_n100_m1_v5__seed456_proposed results/cr_n100_m1_v5__seed789_proposed results/cr_n100_m1_v5__seed101_proposed --out-dir results/cr_n100_v5_comparison_paper
```

---

## 6. 순차 실행 (M0 → M1)

```powershell
# 1. 데이터셋 생성 (최초 1회)
python scripts/make_beta_n50_dataset.py --valid_size 100 --outdir experiments/configs/datasets/beta_n100 --seed 100

# 2. M0 v5 전체 (파이프라인 + 페이퍼 메트릭)
python scripts/run_pipeline.py --config experiments/configs/cr_n100_m0_v5.yaml --run-id cr_n100_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate

python scripts/export_paper_metrics_md.py --base-run-id cr_n100_m0_v5 --mode proposed --out-dir results/cr_n100_m0_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m0_v5__seed42_proposed results/cr_n100_m0_v5__seed123_proposed results/cr_n100_m0_v5__seed456_proposed results/cr_n100_m0_v5__seed789_proposed results/cr_n100_m0_v5__seed101_proposed --out-dir results/cr_n100_m0_v5_paper

# 3. M1 v5 전체
python scripts/run_pipeline.py --config experiments/configs/cr_n100_m1_v5.yaml --run-id cr_n100_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate

python scripts/export_paper_metrics_md.py --base-run-id cr_n100_m1_v5 --mode proposed --out-dir results/cr_n100_m1_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m1_v5__seed42_proposed results/cr_n100_m1_v5__seed123_proposed results/cr_n100_m1_v5__seed456_proposed results/cr_n100_m1_v5__seed789_proposed results/cr_n100_m1_v5__seed101_proposed --out-dir results/cr_n100_m1_v5_paper

# 4. M0 vs M1 비교
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n100_m0_v5_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_n100_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n100_m0_v5__seed42_proposed results/cr_n100_m0_v5__seed123_proposed results/cr_n100_m0_v5__seed456_proposed results/cr_n100_m0_v5__seed789_proposed results/cr_n100_m0_v5__seed101_proposed --run-dirs-m1 results/cr_n100_m1_v5__seed42_proposed results/cr_n100_m1_v5__seed123_proposed results/cr_n100_m1_v5__seed456_proposed results/cr_n100_m1_v5__seed789_proposed results/cr_n100_m1_v5__seed101_proposed --out-dir results/cr_n100_v5_comparison_paper
```

---

## 산출물 경로

| 항목 | M0 v5 | M1 v5 |
|------|-------|-------|
| 시드별 run | results/cr_n100_m0_v5__seed{42,123,456,789,101}_proposed | results/cr_n100_m1_v5__seed{42,123,456,789,101}_proposed |
| merged scorecards | results/cr_n100_m0_v5_aggregated/merged_scorecards.jsonl | results/cr_n100_m1_v5_aggregated/merged_scorecards.jsonl |
| aggregated_mean_std | results/cr_n100_m0_v5_aggregated/aggregated_mean_std.csv | results/cr_n100_m1_v5_aggregated/aggregated_mean_std.csv |
| paper | results/cr_n100_m0_v5_paper/ | results/cr_n100_m1_v5_paper/ |
| M0 vs M1 비교 | results/cr_n100_v5_comparison_paper/ | |
