# CR-M0 vs CR-M1 vs CR-M2 실행 명령

n=50, seeds 3 (42, 123, 456). configs: cr_n50_m0.yaml, cr_n50_m1.yaml, cr_n50_m2.yaml.

---

## 1. 통합 스크립트 (권장)

```bash
# 전체 실행 (pipeline → IRR → paper metrics)
python scripts/run_cr_m0_m1_m2_pipeline.py

# 옵션
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-pipeline
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-irr
python scripts/run_cr_m0_m1_m2_pipeline.py --skip-paper-metrics
python scripts/run_cr_m0_m1_m2_pipeline.py --conditions m0 m1
```

---

## 2. 수동 실행 (순차)

### 2.1 run_pipeline

```bash
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0.yaml --run-id cr_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate

python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1.yaml --run-id cr_n50_m1 --mode proposed --profile paper --with_metrics --with_aggregate

python scripts/run_pipeline.py --config experiments/configs/cr_n50_m2.yaml --run-id cr_n50_m2 --mode proposed --profile paper --with_metrics --with_aggregate
```

### 2.2 compute_irr (시드별)

```bash
# M0
python scripts/compute_irr.py --input results/cr_n50_m0__seed42_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m0__seed123_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m0__seed456_proposed/outputs.jsonl --outdir results/cr_n50_m0__seed456_proposed/irr/

# M1
python scripts/compute_irr.py --input results/cr_n50_m1__seed42_proposed/outputs.jsonl --outdir results/cr_n50_m1__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m1__seed123_proposed/outputs.jsonl --outdir results/cr_n50_m1__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m1__seed456_proposed/outputs.jsonl --outdir results/cr_n50_m1__seed456_proposed/irr/

# M2
python scripts/compute_irr.py --input results/cr_n50_m2__seed42_proposed/outputs.jsonl --outdir results/cr_n50_m2__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m2__seed123_proposed/outputs.jsonl --outdir results/cr_n50_m2__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_n50_m2__seed456_proposed/outputs.jsonl --outdir results/cr_n50_m2__seed456_proposed/irr/
```

### 2.3 export_paper_metrics_md

```bash
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0 --mode proposed
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m1 --mode proposed
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m2 --mode proposed
```

### 2.4 export_paper_metrics_aggregated

```bash
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_aggregated/aggregated_mean_std.csv
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m1_aggregated/aggregated_mean_std.csv
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m2_aggregated/aggregated_mean_std.csv
```

---

## 3. 산출물 경로

| 조건 | run_id | results 디렉터리 |
|------|--------|------------------|
| M0 | cr_n50_m0 | cr_n50_m0__seed42_proposed, cr_n50_m0__seed123_proposed, cr_n50_m0__seed456_proposed |
| M1 | cr_n50_m1 | cr_n50_m1__seed42_proposed, ... |
| M2 | cr_n50_m2 | cr_n50_m2__seed42_proposed, ... |

| 산출물 | 경로 |
|--------|------|
| IRR | results/<run_id>__seed<N>_proposed/irr/irr_sample_level.csv, irr_run_summary.json |
| Paper metrics (seed) | results/<run_id>_paper/paper_metrics.md, paper_metrics.csv |
| Paper metrics (agg) | results/<run_id>_paper/paper_metrics_aggregated.md |
| Aggregated | results/<run_id>_aggregated/aggregated_mean_std.csv, integrated_report.md |

---

## 4. 데이터 요구사항

- `experiments/configs/datasets/beta_n50/train.csv`, `valid.csv`, `valid.gold.jsonl` 존재
- 없으면: `python scripts/make_beta_n50_dataset.py --outdir experiments/configs/datasets/beta_n50 --valid_size 50 --seed 77`
