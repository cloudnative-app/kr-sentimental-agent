# CR n601 M0/M1 v5 실험 실행 명령어

**설정**: n=601 (valid.jsonl 전체), seeds=[42, 123, 456, 789, 101], concurrency=5  
**입력**: `experiments/configs/datasets/train/valid.jsonl`  
**v5 변경점**: conflict_flags ref 기준 primary, term 기준 secondary. `pipeline.conflict_mode: primary_secondary`, `semantic_conflict_enabled: false`

---

## 1. 데이터셋 생성 (gold.jsonl 포함)

```powershell
python scripts/make_beta_n50_dataset.py --input experiments/configs/datasets/train/valid.jsonl --valid_size 601 --outdir experiments/configs/datasets/beta_n601 --seed 601
```

- **입력**: `experiments/configs/datasets/train/valid.jsonl` (NIKLuge 형식)
- **출력**: `experiments/configs/datasets/beta_n601/train.csv`, `valid.csv`, `valid.gold.jsonl`
- valid_size=601: valid.jsonl 전체를 valid로 사용 (train은 비어 있음)
- n이 601이 아닐 경우: `--valid_size <실제_레코드_수>` 로 조정

---

## 2. 파이프라인 (run_pipeline) — paper, metrics, aggregator

### M0 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n601_m0_v5.yaml --run-id cr_n601_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate
```

### M1 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n601_m1_v5.yaml --run-id cr_n601_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate
```

---

## 3. compute_irr (시드별)

### M0 v5

```powershell
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed42_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed123_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed456_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed456_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed789_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed789_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed101_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed101_proposed/irr/
```

### M1 v5

```powershell
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed42_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed123_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed456_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed456_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed789_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed789_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed101_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed101_proposed/irr/
```

---

## 4. 페이퍼 메트릭 export (M0, M1, M0 vs M1)

### M0 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n601_m0_v5 --mode proposed --out-dir results/cr_n601_m0_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m0_v5__seed42_proposed results/cr_n601_m0_v5__seed123_proposed results/cr_n601_m0_v5__seed456_proposed results/cr_n601_m0_v5__seed789_proposed results/cr_n601_m0_v5__seed101_proposed --out-dir results/cr_n601_m0_v5_paper
```

### M1 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n601_m1_v5 --mode proposed --out-dir results/cr_n601_m1_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m1_v5__seed42_proposed results/cr_n601_m1_v5__seed123_proposed results/cr_n601_m1_v5__seed456_proposed results/cr_n601_m1_v5__seed789_proposed results/cr_n601_m1_v5__seed101_proposed --out-dir results/cr_n601_m1_v5_paper
```

### M0 vs M1 비교 (comparison)

```powershell
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m0_v5_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_n601_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m0_v5__seed42_proposed results/cr_n601_m0_v5__seed123_proposed results/cr_n601_m0_v5__seed456_proposed results/cr_n601_m0_v5__seed789_proposed results/cr_n601_m0_v5__seed101_proposed --run-dirs-m1 results/cr_n601_m1_v5__seed42_proposed results/cr_n601_m1_v5__seed123_proposed results/cr_n601_m1_v5__seed456_proposed results/cr_n601_m1_v5__seed789_proposed results/cr_n601_m1_v5__seed101_proposed --out-dir results/cr_n601_v5_comparison_paper
```

---

## 5. 순차 실행 (전체 워크플로우)

```powershell
# 1. 데이터셋 생성 (최초 1회)
python scripts/make_beta_n50_dataset.py --input experiments/configs/datasets/train/valid.jsonl --valid_size 601 --outdir experiments/configs/datasets/beta_n601 --seed 601

# 2. M0 v5 파이프라인
python scripts/run_pipeline.py --config experiments/configs/cr_n601_m0_v5.yaml --run-id cr_n601_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate

# 3. M1 v5 파이프라인
python scripts/run_pipeline.py --config experiments/configs/cr_n601_m1_v5.yaml --run-id cr_n601_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 5 --with_aggregate

# 4. compute_irr (M0, M1 각 5시드)
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed42_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed123_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed456_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed456_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed789_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed789_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m0_v5__seed101_proposed/outputs.jsonl --outdir results/cr_n601_m0_v5__seed101_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed42_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed123_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed456_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed456_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed789_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed789_proposed/irr/
python scripts/compute_irr.py --input results/cr_n601_m1_v5__seed101_proposed/outputs.jsonl --outdir results/cr_n601_m1_v5__seed101_proposed/irr/

# 5. 페이퍼 메트릭 export (M0, M1, M0 vs M1)
python scripts/export_paper_metrics_md.py --base-run-id cr_n601_m0_v5 --mode proposed --out-dir results/cr_n601_m0_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m0_v5__seed42_proposed results/cr_n601_m0_v5__seed123_proposed results/cr_n601_m0_v5__seed456_proposed results/cr_n601_m0_v5__seed789_proposed results/cr_n601_m0_v5__seed101_proposed --out-dir results/cr_n601_m0_v5_paper

python scripts/export_paper_metrics_md.py --base-run-id cr_n601_m1_v5 --mode proposed --out-dir results/cr_n601_m1_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m1_v5__seed42_proposed results/cr_n601_m1_v5__seed123_proposed results/cr_n601_m1_v5__seed456_proposed results/cr_n601_m1_v5__seed789_proposed results/cr_n601_m1_v5__seed101_proposed --out-dir results/cr_n601_m1_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n601_m0_v5_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_n601_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n601_m0_v5__seed42_proposed results/cr_n601_m0_v5__seed123_proposed results/cr_n601_m0_v5__seed456_proposed results/cr_n601_m0_v5__seed789_proposed results/cr_n601_m0_v5__seed101_proposed --run-dirs-m1 results/cr_n601_m1_v5__seed42_proposed results/cr_n601_m1_v5__seed123_proposed results/cr_n601_m1_v5__seed456_proposed results/cr_n601_m1_v5__seed789_proposed results/cr_n601_m1_v5__seed101_proposed --out-dir results/cr_n601_v5_comparison_paper
```

---

## 산출물 경로

| 항목 | M0 v5 | M1 v5 |
|------|-------|-------|
| 시드별 run | results/cr_n601_m0_v5__seed{42,123,456,789,101}_proposed | results/cr_n601_m1_v5__seed{42,123,456,789,101}_proposed |
| merged scorecards | results/cr_n601_m0_v5_aggregated/merged_scorecards.jsonl | results/cr_n601_m1_v5_aggregated/merged_scorecards.jsonl |
| aggregated_mean_std | results/cr_n601_m0_v5_aggregated/aggregated_mean_std.csv | results/cr_n601_m1_v5_aggregated/aggregated_mean_std.csv |
| paper | results/cr_n601_m0_v5_paper/ | results/cr_n601_m1_v5_paper/ |
| M0 vs M1 비교 | results/cr_n601_v5_comparison_paper/ | |
