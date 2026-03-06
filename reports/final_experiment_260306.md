# Final Experiment 260306 — 실행 명령어

**데이터**: `nikluge-sa-2022-dev.jsonl` → `final_260306` (train=2235, valid=559)  
**시드**: 5개 [42, 123, 456, 789, 1024], concurrency=5  
**참조**: [README_cr_v1](docs/README_cr_v1.md), [run_cr_v2_n601_final_paper_table_commands](docs/run_cr_v2_n601_final_paper_table_commands.md)

---

## Condition 개요

| # | Condition | Description | 역할/구분 | Config |
|---|-----------|-------------|-----------|--------|
| 1 | S0 | Single-pass baseline | Primary comparator | final_260306_s0 |
| 2 | S0+Budget | S0 + token budget control | 계산량 통제 baseline | final_260306_s0_bg |
| 3 | M0 | MFRA (without memory) | Primary treatment | final_260306_m0 |
| 3-1 | M1 | MFRA + episodic memory | Exploratory extension (RQ2) | final_260306_m1 |
| 3-2 | M0+nt | MFRA (no trigger) | Ablation | final_260306_m0_nt |
| 4* | Supervised | Fine-tuned external baseline | 외부 성능 참조 | https://github.com/teddysum/korean_ABSA_baseline | 
---
*조건 4는 한국어 absa 베이스라인으로 별도 튜닝과 학습습 없이 해당 모델로 실행 필요. 튜플 단위는 (aspect_ref, polarity) 의 출력물을 산출하도록 조정 필요. 같은 정규화 규칙과 메트릭 계산 코드 필요. 평가 데이터는 @experiments/configs/datasets/test/nikluge-sa-2022-dev.jsonl 이용 . seed k=5.
*메트릭계산과 정규화 관련 출력 규칙만 설정 필요: docs/external_finetuned_model_comparison_spec.md 참조 
*메트릭 계산 코드는 @cr_branch_metrics_spec.md 
*정규화 규칙은 @docs/normalization_rules_and_locations.md

## 0. 데이터셋 생성 (완료 시 생략)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent

python scripts/make_mini_dataset.py `
  --input experiments/configs/datasets/test/nikluge-sa-2022-dev.jsonl `
  --outdir experiments/configs/datasets/final_260306 `
  --valid_ratio 0.2 `
  --seed 42
```

**생성 파일**: `final_260306/train.csv`, `final_260306/valid.csv`, `final_260306/valid.gold.jsonl`

---

## 1. run_pipeline (S0, M0, M1, M0+nt)

전체 시드 동시 실행, paper 프로필, 메트릭, 어그리게이터 포함.

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_MODEL="gpt-4.1-mini"

# S0 (Single-pass baseline)
python scripts/run_pipeline.py --config experiments/configs/final_260306_s0.yaml --run-id final_260306_s0 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5

# M0 (MFRA, Primary treatment)
python scripts/run_pipeline.py --config experiments/configs/final_260306_m0.yaml --run-id final_260306_m0 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5

# M1 (MFRA + memory)
python scripts/run_pipeline.py --config experiments/configs/final_260306_m1.yaml --run-id final_260306_m1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5

# M0+nt (Ablation, no trigger)
python scripts/run_pipeline.py --config experiments/configs/final_260306_m0_nt.yaml --run-id final_260306_m0_nt --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5
```

---

## 2. S0+Budget (별도 스크립트)

```powershell
python scripts/run_s0_budget_and_aggregate.py --config experiments/configs/final_260306_s0_bg.yaml --run-id final_260306_s0_bg --mode proposed
```

**출력**: `results/final_260306_s0_bg__seed{N}__budget_aggregated_proposed/` (시드별 K회 majority-vote 집계)

---

## 3. compute_irr (시드별, subset IRR용)

M0, M1, M0+nt에 대해 시드별 실행. `--scorecards`로 gold_tuples 병합 (subset IRR용).

```powershell
# M0
42,123,456,789,1024 | ForEach-Object { python scripts/compute_irr.py --input "results/final_260306_m0__seed$_`_proposed/outputs.jsonl" --outdir "results/final_260306_m0__seed$_`_proposed/irr" --scorecards "results/final_260306_m0__seed$_`_proposed/scorecards.jsonl" }

# M1
42,123,456,789,1024 | ForEach-Object { python scripts/compute_irr.py --input "results/final_260306_m1__seed$_`_proposed/outputs.jsonl" --outdir "results/final_260306_m1__seed$_`_proposed/irr" --scorecards "results/final_260306_m1__seed$_`_proposed/scorecards.jsonl" }

# M0+nt
42,123,456,789,1024 | ForEach-Object { python scripts/compute_irr.py --input "results/final_260306_m0_nt__seed$_`_proposed/outputs.jsonl" --outdir "results/final_260306_m0_nt__seed$_`_proposed/irr" --scorecards "results/final_260306_m0_nt__seed$_`_proposed/scorecards.jsonl" }
```

**개별 실행 예 (M0 seed42)**:
```powershell
python scripts/compute_irr.py --input results/final_260306_m0__seed42_proposed/outputs.jsonl --outdir results/final_260306_m0__seed42_proposed/irr --scorecards results/final_260306_m0__seed42_proposed/scorecards.jsonl
```

---

## 4. aggregate_seed_metrics (IRR 반영 후)

compute_irr 완료 후 재집계하여 subset_irr_* 반영.

```powershell
$SEEDS = "42,123,456,789,1024"

# S0
python scripts/aggregate_seed_metrics.py --base_run_id final_260306_s0 --seeds $SEEDS --mode proposed --outdir results/final_260306_s0_aggregated --metrics_profile paper_main --with_metric_report

# M0
python scripts/aggregate_seed_metrics.py --base_run_id final_260306_m0 --seeds $SEEDS --mode proposed --outdir results/final_260306_m0_aggregated --metrics_profile paper_main --with_metric_report

# M1
python scripts/aggregate_seed_metrics.py --base_run_id final_260306_m1 --seeds $SEEDS --mode proposed --outdir results/final_260306_m1_aggregated --metrics_profile paper_main --with_metric_report

# M0+nt
python scripts/aggregate_seed_metrics.py --base_run_id final_260306_m0_nt --seeds $SEEDS --mode proposed --outdir results/final_260306_m0_nt_aggregated --metrics_profile paper_main --with_metric_report
```

**S0+Budget**: run_s0_budget_and_aggregate가 시드별 budget_aggregated 결과를 생성. aggregate_seed_metrics로 시드 간 mean±std 산출. `--ensure_per_seed_metrics`로 structural_metrics.csv 자동 생성.

```powershell
python scripts/aggregate_seed_metrics.py --run_dirs results/final_260306_s0_bg__seed42__budget_aggregated_proposed,results/final_260306_s0_bg__seed123__budget_aggregated_proposed,results/final_260306_s0_bg__seed456__budget_aggregated_proposed,results/final_260306_s0_bg__seed789__budget_aggregated_proposed,results/final_260306_s0_bg__seed1024__budget_aggregated_proposed --outdir results/final_260306_s0_bg_aggregated --metrics_profile paper_main --with_metric_report --ensure_per_seed_metrics
```

---

## 5. Triptych (Subset 분석, 선택)

**참고**: `run_pipeline --with_metrics` 실행 시 각 run에 `derived_subset/triptych.csv`가 자동 생성됨. 아래는 aggregated merged용 triptych (선택).

subset conditional 테이블용 triptych 생성.

```powershell
# S0
python scripts/structural_error_aggregator.py --input results/final_260306_s0_aggregated/merged_scorecards.jsonl --outdir results/final_260306_s0_aggregated/merged_metrics --profile paper_main --export_triptych_table results/final_260306_s0_aggregated/derived_subset/triptych.csv --triptych_sample_n 0

# M0
python scripts/structural_error_aggregator.py --input results/final_260306_m0_aggregated/merged_scorecards.jsonl --outdir results/final_260306_m0_aggregated/merged_metrics --profile paper_main --export_triptych_table results/final_260306_m0_aggregated/derived_subset/triptych.csv --triptych_sample_n 0

# M1
python scripts/structural_error_aggregator.py --input results/final_260306_m1_aggregated/merged_scorecards.jsonl --outdir results/final_260306_m1_aggregated/merged_metrics --profile paper_main --export_triptych_table results/final_260306_m1_aggregated/derived_subset/triptych.csv --triptych_sample_n 0
```

---

## 5-1. 타당성 검증용 A/B/C 테이블 (최소 로그 스키마)

변별 타당성·구성 타당도·순위비교 분석용. `run_pipeline --with_metrics`로 생성된 triptych·structural_metrics 기반.

```powershell
$SEEDS = "42,123,456,789,1024"

# A: run_summary (조건×시드)
python scripts/export_run_summary.py --base_run_id final_260306_s0 --seeds $SEEDS --mode proposed
python scripts/export_run_summary.py --base_run_id final_260306_m0 --seeds $SEEDS --mode proposed
python scripts/export_run_summary.py --base_run_id final_260306_m1 --seeds $SEEDS --mode proposed
python scripts/export_run_summary.py --base_run_id final_260306_m0_nt --seeds $SEEDS --mode proposed

# B: sample_metrics (조건×시드×sample_id)
python scripts/export_sample_metrics.py --base_run_id final_260306_s0 --seeds $SEEDS --mode proposed
python scripts/export_sample_metrics.py --base_run_id final_260306_m0 --seeds $SEEDS --mode proposed
# ... (M1, M0+nt 동일)

# C: transition_metrics (stage1→final)
python scripts/export_transition_metrics.py --base_run_id final_260306_s0 --seeds $SEEDS --mode proposed
python scripts/export_transition_metrics.py --base_run_id final_260306_m0 --seeds $SEEDS --mode proposed
# ... (M1, M0+nt 동일)
```

**출력**: `analysis_exports/run_summary.csv`, `sample_metrics.csv`, `transition_metrics.csv`  
**참조**: [minimum_log_schema_verification.md](docs/minimum_log_schema_verification.md)

---

## 6. Final Paper Table (CI, 페이퍼 메트릭)

S0, M0, M1 비교 테이블. Bootstrap 95% CI 포함.

```powershell
python scripts/final_paper_table.py `
  --agg-s0 results/final_260306_s0_aggregated/aggregated_mean_std.csv `
  --agg-m0 results/final_260306_m0_aggregated/aggregated_mean_std.csv `
  --agg-m1 results/final_260306_m1_aggregated/aggregated_mean_std.csv `
  --run-dirs-s0 results/final_260306_s0__seed42_proposed results/final_260306_s0__seed123_proposed results/final_260306_s0__seed456_proposed results/final_260306_s0__seed789_proposed results/final_260306_s0__seed1024_proposed `
  --run-dirs-m0 results/final_260306_m0__seed42_proposed results/final_260306_m0__seed123_proposed results/final_260306_m0__seed456_proposed results/final_260306_m0__seed789_proposed results/final_260306_m0__seed1024_proposed `
  --run-dirs-m1 results/final_260306_m1__seed42_proposed results/final_260306_m1__seed123_proposed results/final_260306_m1__seed456_proposed results/final_260306_m1__seed789_proposed results/final_260306_m1__seed1024_proposed `
  --triptych-s0 results/final_260306_s0_aggregated/derived_subset/triptych.csv `
  --triptych-m0 results/final_260306_m0_aggregated/derived_subset/triptych.csv `
  --out reports/final_experiment_260306_paper_table.md
```

**triptych 없이 (subset 생략)**:
```powershell
python scripts/final_paper_table.py --agg-s0 results/final_260306_s0_aggregated/aggregated_mean_std.csv --agg-m0 results/final_260306_m0_aggregated/aggregated_mean_std.csv --agg-m1 results/final_260306_m1_aggregated/aggregated_mean_std.csv --run-dirs-s0 results/final_260306_s0__seed42_proposed results/final_260306_s0__seed123_proposed results/final_260306_s0__seed456_proposed results/final_260306_s0__seed789_proposed results/final_260306_s0__seed1024_proposed --run-dirs-m0 results/final_260306_m0__seed42_proposed results/final_260306_m0__seed123_proposed results/final_260306_m0__seed456_proposed results/final_260306_m0__seed789_proposed results/final_260306_m0__seed1024_proposed --run-dirs-m1 results/final_260306_m1__seed42_proposed results/final_260306_m1__seed123_proposed results/final_260306_m1__seed456_proposed results/final_260306_m1__seed789_proposed results/final_260306_m1__seed1024_proposed --out reports/final_experiment_260306_paper_table.md
```

---

## 7. CR v2 Paper Table (M0 vs M1, 대안)

```powershell
python scripts/build_cr_v2_paper_table.py `
  --agg-m0 results/final_260306_m0_aggregated/aggregated_mean_std.csv `
  --agg-m1 results/final_260306_m1_aggregated/aggregated_mean_std.csv `
  --run-dirs-m0 results/final_260306_m0__seed42_proposed results/final_260306_m0__seed123_proposed results/final_260306_m0__seed456_proposed results/final_260306_m0__seed789_proposed results/final_260306_m0__seed1024_proposed `
  --run-dirs-m1 results/final_260306_m1__seed42_proposed results/final_260306_m1__seed123_proposed results/final_260306_m1__seed456_proposed results/final_260306_m1__seed789_proposed results/final_260306_m1__seed1024_proposed `
  --out reports/final_experiment_260306_cr_v2_table.md
```

---

## 8. 전체 워크플로우 (처음부터)

```powershell
# 0) 데이터셋 (이미 있으면 생략)
python scripts/make_mini_dataset.py --input experiments/configs/datasets/test/nikluge-sa-2022-dev.jsonl --outdir experiments/configs/datasets/final_260306 --valid_ratio 0.2 --seed 42

# 1) S0, M0, M1, M0+nt 파이프라인
python scripts/run_pipeline.py --config experiments/configs/final_260306_s0.yaml --run-id final_260306_s0 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5
python scripts/run_pipeline.py --config experiments/configs/final_260306_m0.yaml --run-id final_260306_m0 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5
python scripts/run_pipeline.py --config experiments/configs/final_260306_m1.yaml --run-id final_260306_m1 --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5
python scripts/run_pipeline.py --config experiments/configs/final_260306_m0_nt.yaml --run-id final_260306_m0_nt --mode proposed --profile paper --with_metrics --with_aggregate --seed_concurrency 5

# 2) S0+Budget
python scripts/run_s0_budget_and_aggregate.py --config experiments/configs/final_260306_s0_bg.yaml --run-id final_260306_s0_bg --mode proposed

# 3) IRR (M0, M1, M0+nt)
# ... (섹션 3 명령 실행)

# 4) aggregate_seed_metrics
# ... (섹션 4 명령 실행)

# 5) Triptych (선택)
# ... (섹션 5 명령 실행)

# 6) Final Paper Table
python scripts/final_paper_table.py --agg-s0 ... --agg-m0 ... --agg-m1 ... --run-dirs-s0 ... --run-dirs-m0 ... --run-dirs-m1 ... --out reports/final_experiment_260306_paper_table.md
```

---

## 9. 산출물 요약

| 항목 | 경로 |
|------|------|
| **데이터셋** | experiments/configs/datasets/final_260306/ |
| **시드별 결과** | results/final_260306_{s0,m0,m1,m0_nt}__seed{N}_proposed/ |
| **시드별 triptych** | results/.../derived_subset/triptych.csv (`--with_metrics` 시 자동) |
| **S0+Budget** | results/final_260306_s0_bg__seed{N}__budget_aggregated_proposed/ |
| **Aggregated** | results/final_260306_{s0,m0,m1,m0_nt,s0_bg}_aggregated/ |
| **aggregated_mean_std** | results/final_260306_*_aggregated/aggregated_mean_std.csv |
| **integrated_report** | results/final_260306_*_aggregated/integrated_report.md |
| **IRR (시드별)** | results/.../irr/irr_run_summary.json, irr_subset_summary.json |
| **타당성 검증 (A/B/C)** | analysis_exports/run_summary.csv, sample_metrics.csv, transition_metrics.csv |
| **Final Paper Table** | reports/final_experiment_260306_paper_table.md |
| **CR v2 Table** | reports/final_experiment_260306_cr_v2_table.md |
| **HTML 리포트** | reports/final_260306_*_proposed/index.html, metric_report.html |

---

## 10. 무결성 검사

```powershell
python scripts/check_experiment_config.py --config experiments/configs/final_260306_s0.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/final_260306_m0.yaml --strict
# ... (나머지 config 동일)
```
