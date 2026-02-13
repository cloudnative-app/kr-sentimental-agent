# Beta N50 실행 명령 (Quick_start 기준)

Quick_start 설정: n=50, seeds [42,123,456], concurrency=3, t1 override, clear_store_at_run_start off, episodic memory run_id별 스토어.

## 1. 데이터셋 생성

```powershell
python scripts/make_beta_n50_dataset.py
```

- 입력: `experiments/configs/datasets/train/valid.jsonl`
- 출력: `experiments/configs/datasets/beta_n50/train.csv`, `valid.csv`, `valid.gold.jsonl`
- seed=77로 shuffle 후 valid 50개 추출 (betatest_n50 seed=99, real_n50_seed1 seed=1과 구분)

## 2. 실행 전 검사 (권장)

```powershell
python scripts/check_experiment_config.py --config experiments/configs/beta_n50_c1.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/beta_n50_c2.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/beta_n50_c3.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/beta_n50_c2_eval_only.yaml --strict
```

## 3. 조건별 run_pipeline (각각 실행)

### C1 (episodic memory OFF)

```powershell
python scripts/run_pipeline.py --config experiments/configs/beta_n50_c1.yaml --run-id beta_n50_c1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

### C2 (episodic memory ON, advisory)

```powershell
python scripts/run_pipeline.py --config experiments/configs/beta_n50_c2.yaml --run-id beta_n50_c2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

### C3 (retrieval-only / silent)

```powershell
python scripts/run_pipeline.py --config experiments/configs/beta_n50_c3.yaml --run-id beta_n50_c3 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

### C2_eval_only (평가 전용)

```powershell
python scripts/run_pipeline.py --config experiments/configs/beta_n50_c2_eval_only.yaml --run-id beta_n50_c2_eval_only --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

## 4. 설정 요약

| 항목 | 값 |
|------|-----|
| 데이터셋 | beta_n50 (train/valid.jsonl, seed=77, valid 50개) |
| Override | t1 |
| episodic_memory | run_id별 스토어 자동 분리, clear_store_at_run_start off |
| seeds | [42, 123, 456] |
| concurrency | 3 |
| run_purpose | paper |
| demo | k=0, hash_filter=false |

## 5. 결과 경로

| 조건 | 결과 디렉터리 | 머지 결과 |
|------|----------------|-----------|
| C1 | results/beta_n50_c1__seed42_proposed, __seed123_proposed, __seed456_proposed | results/beta_n50_c1_aggregated/ |
| C2 | results/beta_n50_c2__seed42_proposed, ... | results/beta_n50_c2_aggregated/ |
| C3 | results/beta_n50_c3__seed42_proposed, ... | results/beta_n50_c3_aggregated/ |
| C2_eval_only | results/beta_n50_c2_eval_only__seed42_proposed, ... | results/beta_n50_c2_eval_only_aggregated/ |
