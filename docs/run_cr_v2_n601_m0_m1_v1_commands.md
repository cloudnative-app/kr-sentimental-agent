# CR v2 n601 M0/M1 v1 실행 및 후처리 명령어

데이터: `beta_n601/train.csv`, `beta_n601/valid.csv`, `beta_n601/valid.gold.jsonl`  
시드: 42, 123, 456 | 동시실행: 3 | paper, metrics, aggregator 포함.

---

## 1. 파이프라인 실행 (M0, M1)

```powershell
# 환경 변수 (필요 시)
$env:LLM_PROVIDER="openai"
$env:OPENAI_MODEL="gpt-4.1-mini"

# M0
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_m0_v1.yaml --run-id cr_v2_n601_m0_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3

# M1
python scripts/run_pipeline.py --config experiments/configs/cr_v2_n601_m1_v1.yaml --run-id cr_v2_n601_m1_v1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 3
```

---

## 2. IRR 계산 (시드별, Paper Table용 --scorecards 필수)

```powershell
# M0
python scripts/compute_irr.py --input results/cr_v2_n601_m0_v1__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n601_m0_v1__seed42_proposed/irr --scorecards results/cr_v2_n601_m0_v1__seed42_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n601_m0_v1__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n601_m0_v1__seed123_proposed/irr --scorecards results/cr_v2_n601_m0_v1__seed123_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n601_m0_v1__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n601_m0_v1__seed456_proposed/irr --scorecards results/cr_v2_n601_m0_v1__seed456_proposed/scorecards.jsonl

# M1
python scripts/compute_irr.py --input results/cr_v2_n601_m1_v1__seed42_proposed/outputs.jsonl --outdir results/cr_v2_n601_m1_v1__seed42_proposed/irr --scorecards results/cr_v2_n601_m1_v1__seed42_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n601_m1_v1__seed123_proposed/outputs.jsonl --outdir results/cr_v2_n601_m1_v1__seed123_proposed/irr --scorecards results/cr_v2_n601_m1_v1__seed123_proposed/scorecards.jsonl
python scripts/compute_irr.py --input results/cr_v2_n601_m1_v1__seed456_proposed/outputs.jsonl --outdir results/cr_v2_n601_m1_v1__seed456_proposed/irr --scorecards results/cr_v2_n601_m1_v1__seed456_proposed/scorecards.jsonl
```

---

## 3. 시드별 메트릭 머지 및 집계

```powershell
# M0
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_m0_v1__seed42_proposed,results/cr_v2_n601_m0_v1__seed123_proposed,results/cr_v2_n601_m0_v1__seed456_proposed --outdir results/cr_v2_n601_m0_v1_aggregated --metrics_profile paper_main

# M1
python scripts/aggregate_seed_metrics.py --run_dirs results/cr_v2_n601_m1_v1__seed42_proposed,results/cr_v2_n601_m1_v1__seed123_proposed,results/cr_v2_n601_m1_v1__seed456_proposed --outdir results/cr_v2_n601_m1_v1_aggregated --metrics_profile paper_main
```

---

## 4. CR v2 Paper Table 생성

```powershell
python scripts/build_cr_v2_paper_table.py --agg-m0 results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs-m0 results/cr_v2_n601_m0_v1__seed42_proposed results/cr_v2_n601_m0_v1__seed123_proposed results/cr_v2_n601_m0_v1__seed456_proposed --run-dirs-m1 results/cr_v2_n601_m1_v1__seed42_proposed results/cr_v2_n601_m1_v1__seed123_proposed results/cr_v2_n601_m1_v1__seed456_proposed --out reports/cr_v2_n601_v1_paper_table.md
```

---

## 4b. Final Paper Table (S0 | M0 | M1, 5.1–5.4 + Appendix)

```powershell
python scripts/final_paper_table.py --agg-s0 results/cr_v2_n601_s0_v1_aggregated/aggregated_mean_std.csv --agg-m0 results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv --agg-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs-s0 results/cr_v2_n601_s0_v1__seed42_proposed results/cr_v2_n601_s0_v1__seed123_proposed results/cr_v2_n601_s0_v1__seed456_proposed --run-dirs-m0 results/cr_v2_n601_m0_v1__seed42_proposed results/cr_v2_n601_m0_v1__seed123_proposed results/cr_v2_n601_m0_v1__seed456_proposed --run-dirs-m1 results/cr_v2_n601_m1_v1__seed42_proposed results/cr_v2_n601_m1_v1__seed123_proposed results/cr_v2_n601_m1_v1__seed456_proposed --triptych-s0 results/cr_v2_n601_s0_v1_aggregated/derived_subset/triptych.csv --triptych-m0 results/cr_v2_n601_m0_v1_aggregated/derived_subset/triptych.csv --out reports/cr_v2_n601_v1_final_paper_table.md
```

자세한 명령어: `docs/run_cr_v2_n601_final_paper_table_commands.md`

---

## 5. Paper Metrics Export (선택)

```powershell
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv --agg-path-m1 results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv --run-dirs results/cr_v2_n601_m0_v1__seed42_proposed results/cr_v2_n601_m0_v1__seed123_proposed results/cr_v2_n601_m0_v1__seed456_proposed --run-dirs-m1 results/cr_v2_n601_m1_v1__seed42_proposed results/cr_v2_n601_m1_v1__seed123_proposed results/cr_v2_n601_m1_v1__seed456_proposed --out-dir results/cr_v2_n601_v1_comparison_paper
```

---

## 산출물 요약

| 항목 | 경로 |
|------|------|
| M0 aggregated | results/cr_v2_n601_m0_v1_aggregated/aggregated_mean_std.csv |
| M1 aggregated | results/cr_v2_n601_m1_v1_aggregated/aggregated_mean_std.csv |
| CR v2 Paper Table | reports/cr_v2_n601_v1_paper_table.md |
| **Final Paper Table (S0\|M0\|M1)** | reports/cr_v2_n601_v1_final_paper_table.md |
| M0 vs M1 비교 | results/cr_v2_n601_v1_comparison_paper/ |
