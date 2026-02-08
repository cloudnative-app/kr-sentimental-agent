# experiment_mini2: 시드 2개에 대한 1런 (타임아웃 없이 1회 시행)

**정의**: mini2는 **시드 2개**(42, 123)에 대한 **1런만** 수행. run_pipeline **1회** 실행 시 시드 42 → 시드 123 순차 실행. **타임아웃 없이** 1회만 시행.

**용어 (실험 루트)**  
- **"n회 반복"** = 서로 다른 시드 n개(`seeds` 리스트)로 **각 1회만 시행**. 동일 시드를 여러 번 돌리는 것이 아님.  
- 예: seeds = [42, 123, 456, 789, 101] → 5회 반복 = 시드 42, 123, 456, 789, 101 각 1회씩.

---

## 1. mini2 1회 실행 (시드 2개, 타임아웃 없이)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent
.\venv\Scripts\Activate.ps1

# mini2: 시드 2개(42, 123) 1런. 타임아웃 없이 1회만 시행.
python scripts/run_pipeline.py --config experiments/configs/experiment_mini2.yaml --run-id experiment_mini2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

**산출** (실행 완료 시):

- `results/experiment_mini2__seed42_proposed/`
- `results/experiment_mini2__seed123_proposed/`

---

## 2. 머징·보고서 (2개 시드 완료 후)

```powershell
python scripts/aggregate_seed_metrics.py --base_run_id experiment_mini2 --mode proposed --seeds 42,123 --outdir results/experiment_mini2_aggregated --with_metric_report --metrics_profile paper_main
```

**산출** (덮어쓰기 방지: 실험별 고유 경로):

- `results/experiment_mini2_aggregated/` (merged_scorecards.jsonl, merged_metrics/, merged_run_experiment_mini2/)
- `reports/merged_run_experiment_mini2/metric_report.html`
