# CR n50 M0/M1 v3 실험 실행 명령어

**설정**: seeds=[3, 123, 456], concurrency=3

---

## 1. 파이프라인 (run_pipeline)

### M0 v3

```bash
python scripts/run_pipeline.py \
  --config experiments/configs/cr_n50_m0_v3.yaml \
  --run-id cr_n50_m0_v3 \
  --mode proposed \
  --profile paper \
  --with_metrics \
  --with_aggregate
```

### M1 v3

```bash
python scripts/run_pipeline.py \
  --config experiments/configs/cr_n50_m1_v3.yaml \
  --run-id cr_n50_m1_v3 \
  --mode proposed \
  --profile paper \
  --with_metrics \
  --with_aggregate
```

---

## 2. 메트릭스 (structural_error_aggregator)

파이프라인 `--with_metrics` 시 자동 실행됨. 수동 실행:

### M0 v3

```bash
python scripts/structural_error_aggregator.py \
  --input results/cr_n50_m0_v3_aggregated/merged_scorecards.jsonl \
  --outdir results/cr_n50_m0_v3_aggregated/merged_metrics \
  --profile paper_main
```

### M1 v3

```bash
python scripts/structural_error_aggregator.py \
  --input results/cr_n50_m1_v3_aggregated/merged_scorecards.jsonl \
  --outdir results/cr_n50_m1_v3_aggregated/merged_metrics \
  --profile paper_main
```

---

## 3. 어그리게이터 (aggregate_seed_metrics)

파이프라인 `--with_aggregate` 시 자동 실행됨. 수동 실행:

### M0 v3

```bash
python scripts/aggregate_seed_metrics.py \
  --base_run_id cr_n50_m0_v3 \
  --mode proposed \
  --seeds 3,123,456 \
  --outdir results/cr_n50_m0_v3_aggregated \
  --metrics_profile paper_main
```

### M1 v3

```bash
python scripts/aggregate_seed_metrics.py \
  --base_run_id cr_n50_m1_v3 \
  --mode proposed \
  --seeds 3,123,456 \
  --outdir results/cr_n50_m1_v3_aggregated \
  --metrics_profile paper_main
```

---

## 4. 페이퍼 메트릭 (export_paper_metrics)

### M0 v3

```bash
# 시드별 paper_metrics.md, paper_metrics.csv
python scripts/export_paper_metrics_md.py \
  --base-run-id cr_n50_m0_v3 \
  --mode proposed \
  --out-dir results/cr_n50_m0_v3_paper

# aggregated_mean_std → paper_metrics_aggregated.md
python scripts/export_paper_metrics_aggregated.py \
  --agg-path results/cr_n50_m0_v3_aggregated/aggregated_mean_std.csv \
  --run-dirs results/cr_n50_m0_v3__seed3_proposed results/cr_n50_m0_v3__seed123_proposed results/cr_n50_m0_v3__seed456_proposed \
  --out-dir results/cr_n50_m0_v3_paper
```

### M1 v3

```bash
# 시드별 paper_metrics.md, paper_metrics.csv
python scripts/export_paper_metrics_md.py \
  --base-run-id cr_n50_m1_v3 \
  --mode proposed \
  --out-dir results/cr_n50_m1_v3_paper

# aggregated_mean_std → paper_metrics_aggregated.md
python scripts/export_paper_metrics_aggregated.py \
  --agg-path results/cr_n50_m1_v3_aggregated/aggregated_mean_std.csv \
  --run-dirs results/cr_n50_m1_v3__seed3_proposed results/cr_n50_m1_v3__seed123_proposed results/cr_n50_m1_v3__seed456_proposed \
  --out-dir results/cr_n50_m1_v3_paper
```

---

## 5. 순차 실행 (M0 → M1)

```bash
# M0 v3 전체
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0_v3.yaml --run-id cr_n50_m0_v3 --mode proposed --profile paper --with_metrics --with_aggregate

# M1 v3 전체
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1_v3.yaml --run-id cr_n50_m1_v3 --mode proposed --profile paper --with_metrics --with_aggregate

# 페이퍼 메트릭 (파이프라인에 포함되지 않으면 별도 실행)
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0_v3 --mode proposed --out-dir results/cr_n50_m0_v3_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_v3_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0_v3__seed3_proposed results/cr_n50_m0_v3__seed123_proposed results/cr_n50_m0_v3__seed456_proposed --out-dir results/cr_n50_m0_v3_paper

python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m1_v3 --mode proposed --out-dir results/cr_n50_m1_v3_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m1_v3_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m1_v3__seed3_proposed results/cr_n50_m1_v3__seed123_proposed results/cr_n50_m1_v3__seed456_proposed --out-dir results/cr_n50_m1_v3_paper
```

---

## 산출물 경로

| 항목 | M0 v3 | M1 v3 |
|------|-------|-------|
| 시드별 run | results/cr_n50_m0_v3__seed{3,123,456}_proposed | results/cr_n50_m1_v3__seed{3,123,456}_proposed |
| merged scorecards | results/cr_n50_m0_v3_aggregated/merged_scorecards.jsonl | results/cr_n50_m1_v3_aggregated/merged_scorecards.jsonl |
| aggregated_mean_std | results/cr_n50_m0_v3_aggregated/aggregated_mean_std.csv | results/cr_n50_m1_v3_aggregated/aggregated_mean_std.csv |
| paper | results/cr_n50_m0_v3_paper/ | results/cr_n50_m1_v3_paper/ |
