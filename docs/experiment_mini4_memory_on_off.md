# experiment_mini4 메모리 ON/OFF 실행 및 결과 리포트

## 설정

- **experiment_mini4_proposed.yaml**: 에피소드 메모리 ON (C2)
- **experiment_mini4_b1.yaml**: 에피소드 메모리 OFF (C1)
- 데이터: `experiments/configs/datasets/mini4/` (train 570, valid 10)
- 시드: `[42]` (1회). 2회 이상은 `seeds: [42, 123]` 등으로 변경

## 0. 데이터 준비 (최초 1회)

mini4 데이터셋이 없으면 생성:

```bash
python scripts/make_mini4_dataset.py
```

입력: `experiments/configs/datasets/train/valid.jsonl`  
출력: `experiments/configs/datasets/mini4/train.csv`, `valid.csv`, `valid.gold.jsonl`

## 1. 설정 검사 (선택)

```bash
python scripts/check_experiment_config.py --config experiments/configs/experiment_mini4_proposed.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/experiment_mini4_b1.yaml --strict
```

## 2. 실험 실행 + 메트릭 리포트까지 한 번에

**메모리 ON (C2)**

```bash
python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_proposed.yaml --run-id experiment_mini4_proposed --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

**메모리 OFF (C1)**

```bash
python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_b1.yaml --run-id experiment_mini4_b1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

- 결과: `results/experiment_mini4_proposed__seed42_proposed/`, `results/experiment_mini4_b1__seed42_proposed/`
- 리포트: `reports/experiment_mini4_proposed__seed42_proposed/metric_report.html`, `reports/experiment_mini4_b1__seed42_proposed/metric_report.html` (파이프라인에서 `build_metric_report` 자동 실행)

## 3. 실험만 먼저 돌리고, 리포트는 나중에 생성

실험만 실행:

```bash
python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_proposed.yaml --run-id experiment_mini4_proposed --mode proposed --profile paper
python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_b1.yaml --run-id experiment_mini4_b1 --mode proposed --profile paper
```

이후 메트릭 리포트만 생성:

```bash
python scripts/build_metric_report.py --run_dir results/experiment_mini4_proposed__seed42_proposed --out_dir reports/experiment_mini4_proposed__seed42_proposed --metrics_profile paper_main
python scripts/build_metric_report.py --run_dir results/experiment_mini4_b1__seed42_proposed --out_dir reports/experiment_mini4_b1__seed42_proposed --metrics_profile paper_main
```

## 4. 시드 2개로 실행 (예: 42, 123)

config에서 `seeds: [42, 123]`으로 수정 후:

```bash
python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_proposed.yaml --run-id experiment_mini4_proposed --mode proposed --profile paper --with_metrics --with_aggregate
```

- 결과: `results/experiment_mini4_proposed__seed42_proposed/`, `results/experiment_mini4_proposed__seed123_proposed/`
- `--with_aggregate`: 시드 완료 후 `aggregate_seed_metrics.py`로 머징·평균±표준편차·통합 보고서 생성

## 요약

| 단계 | 명령 |
|------|------|
| 데이터 생성 | `python scripts/make_mini4_dataset.py` |
| 메모리 ON 실행+리포트 | `python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_proposed.yaml --run-id experiment_mini4_proposed --mode proposed --profile paper --with_metrics --metrics_profile paper_main` |
| 메모리 OFF 실행+리포트 | `python scripts/run_pipeline.py --config experiments/configs/experiment_mini4_b1.yaml --run-id experiment_mini4_b1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main` |
