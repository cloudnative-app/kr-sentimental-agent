# CR v2 n100 M0/M1 v3 실행 및 후처리 명령어

v2 YAML 설정 기반. run_pipeline: 동시실행 3, paper, metrics, aggregator 포함.

---

## 1. 파이프라인 실행 (M0, M1)

```powershell
# 환경 변수
$env:LLM_PROVIDER="openai"
$env:OPENAI_MODEL="gpt-4.1-mini"

# M0 v3 (3 seeds, concurrency 3)
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n100_m0_v3.yaml --run-id cr_v2_n100_m0_v3 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3

# M1 v3 (3 seeds, concurrency 3)
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n100_m1_v3.yaml --run-id cr_v2_n100_m1_v3 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
```

---

## 2. Recheck Rate 확인

```powershell
# M0
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v3__seed42_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v3__seed123_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m0_v3__seed456_proposed/outputs.jsonl

# M1
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v3__seed42_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v3__seed123_proposed/outputs.jsonl
python scripts/check_recheck_rate.py --input results/cr_v2_n100_m1_v3__seed456_proposed/outputs.jsonl
```

---

## 3. IRR 계산 (시드별)

```powershell
# M0
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v3__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v3__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v3__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v3__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m0_v3__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m0_v3__seed456_proposed/irr/

# M1
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v3__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v3__seed42_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v3__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v3__seed123_proposed/irr/
python scripts/compute_irr.py --input results/cr_v2_n100_m1_v3__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n100_m1_v3__seed456_proposed/irr/
```

---

## 4. 시드별 메트릭 머지 및 집계

```powershell
# M0
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m0_v3__seed42_proposed,results/cr_v2_n100_m0_v3__seed123_proposed,results/cr_v2_n100_m0_v3__seed456_proposed --outdir results/cr_v2_n100_m0_v3_aggregated --metrics_profile paper_main

# M1
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n100_m1_v3__seed42_proposed,results/cr_v2_n100_m1_v3__seed123_proposed,results/cr_v2_n100_m1_v3__seed456_proposed --outdir results/cr_v2_n100_m1_v3_aggregated --metrics_profile paper_main
```

---

## 5. Paper Metrics Export (M0 vs M1 비교)

```powershell
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_v2_n100_m0_v3_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_v2_n100_m1_v3_aggregated/aggregated_mean_std.csv --run-dirs results/cr_v2_n100_m0_v3__seed42_proposed results/cr_v2_n100_m0_v3__seed123_proposed results/cr_v2_n100_m0_v3__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v3__seed42_proposed results/cr_v2_n100_m1_v3__seed123_proposed results/cr_v2_n100_m1_v3__seed456_proposed --out-dir results/cr_v2_n100_v3_comparison_paper
```

---

## 6. CR v2 Paper Table 생성

```powershell
python scripts/build_cr_v2_paper_table.py --agg-m0 results/cr_v2_n100_m0_v3_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n100_m1_v3_aggregated/aggregated_mean_std.csv --run-dirs-m0 results/cr_v2_n100_m0_v3__seed42_proposed results/cr_v2_n100_m0_v3__seed123_proposed results/cr_v2_n100_m0_v3__seed456_proposed --run-dirs-m1 results/cr_v2_n100_m1_v3__seed42_proposed results/cr_v2_n100_m1_v3__seed123_proposed results/cr_v2_n100_m1_v3__seed456_proposed --out reports/cr_v2_paper_table.md
```

---

## 산출물 요약

| 항목 | 경로 |
|------|------|
| M0 aggregated | results/cr_v2_n100_m0_v3_aggregated/aggregated_mean_std.csv |
| M1 aggregated | results/cr_v2_n100_m1_v3_aggregated/aggregated_mean_std.csv |
| M0 vs M1 비교 | results/cr_v2_n100_v3_comparison_paper/paper_metrics_aggregated_comparison.md |
| CR v2 Paper Table | reports/cr_v2_paper_table.md |
| IRR (시드별) | results/cr_v2_n100_*_v3__seed*_proposed/irr/irr_run_summary.json |
