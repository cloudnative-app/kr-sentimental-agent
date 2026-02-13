# Finalexperiment n50 seed1 실행 커맨드

T2(v2) 기본조건(finalexperiment) + real n50 seed1 표본규칙. C1/C2/C3/C2_eval_only run_experiments → 메트릭 생성 → 페이퍼 프로파일(paper tables, metric_report) 순차 자동 실행.

## 전제

- **파이프라인**: run_pipeline `--profile paper --with_metrics` (실험 → build_run_snapshot → build_paper_tables → build_html_report → structural_error_aggregator → build_metric_report).
- **데이터**: `experiments/configs/datasets/real_n50_seed1/` (valid 50, seed=1). 없으면 스크립트가 `make_real_n100_seed1_dataset.py --valid_size 50 --seed 1` 로 생성.
- **설정**: `experiments/configs/finalexperiment_n50_seed1_c1.yaml` 등 4개. debate_override = T2 (min_total=0.6, min_margin=0.3, min_target_conf=0.55, l3_conservative=false).

## 한 번에 실행 (권장)

**PowerShell (프로젝트 루트):**

```powershell
.\scripts\run_finalexperiment_n50_seed1.ps1
```

- 데이터셋 생성(없을 때) → C1 → C2 → C3 → C2_eval_only 순차 run_pipeline(paper + metrics) → build_memory_condition_summary.

**아이디 분리 (기존 결과 덮어쓰기 방지):**

```powershell
.\scripts\run_finalexperiment_n50_seed1.ps1 -RunIdSuffix v2
```

- run_id: `finalexperiment_n50_seed1_c1_v2`, `finalexperiment_n50_seed1_c2_v2` 등.
- 결과: `results/finalexperiment_n50_seed1_c1_v2__seed1_proposed/` 등.

**데이터셋 이미 있을 때:**

```powershell
.\scripts\run_finalexperiment_n50_seed1.ps1 -SkipDataset
```

**일부 조건만:**

```powershell
.\scripts\run_finalexperiment_n50_seed1.ps1 -Conditions c1,c2
.\scripts\run_finalexperiment_n50_seed1.ps1 -Conditions c1 c2 c3
```

**요약 스킵:**

```powershell
.\scripts\run_finalexperiment_n50_seed1.ps1 -SkipSummary
```

## Python 직접 호출

```powershell
python scripts/run_finalexperiment_n50_seed1.py
python scripts/run_finalexperiment_n50_seed1.py --run-id-suffix v2
python scripts/run_finalexperiment_n50_seed1.py --skip_dataset
python scripts/run_finalexperiment_n50_seed1.py --conditions c1 c2 c3 c2_eval_only
python scripts/run_finalexperiment_n50_seed1.py --all --run-id-suffix v2
```

## 산출물

- **결과 디렉터리**: `results/finalexperiment_n50_seed1_c1__seed1_proposed/` (및 c2, c3, c2_eval_only). 각 run: scorecards.jsonl, outputs.jsonl, paper_outputs/, derived/metrics/, experiments/reports/.../metric_report.html 등.
- **요약**: `reports/finalexperiment_n50_seed1_summary.md` (또는 `finalexperiment_n50_seed1_v2_summary.md` when suffix).

## 설정 파일

| 조건 | 설정 |
|------|------|
| C1 | `finalexperiment_n50_seed1_c1.yaml` (episodic_memory C1, T2 pipeline) |
| C2 | `finalexperiment_n50_seed1_c2.yaml` (episodic_memory C2, T2 pipeline) |
| C3 | `finalexperiment_n50_seed1_c3.yaml` (memory silent, T2 pipeline) |
| C2_eval_only | `finalexperiment_n50_seed1_c2_eval_only.yaml` (v1_2 conditions, T2 pipeline) |
