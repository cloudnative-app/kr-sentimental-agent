# CR-M0 / L-M0 실행 명령

조건: L-M0 (legacy, no memory), CR-M0 (conflict_review, no memory).

| 조건명 | 프로토콜 | 메모리 |
|--------|----------|--------|
| L-M0 | legacy | 없음 |
| CR-M0 | conflict_review | 없음 |

---

## 1. 데이터셋 생성

### cr_n10 (n=10, seed=42)

```powershell
python scripts/make_cr_n10_dataset.py
```

- 입력: `experiments/configs/datasets/train/valid.jsonl`
- 출력: `experiments/configs/datasets/cr_n10/train.csv`, `valid.csv`, `valid.gold.jsonl`
- seed=42로 shuffle 후 valid 10개 추출

### beta_n50 (n=50, 시드 3회 실험용)

```powershell
python scripts/make_beta_n50_dataset.py
```

- 입력: `experiments/configs/datasets/train/valid.jsonl`
- 출력: `experiments/configs/datasets/beta_n50/train.csv`, `valid.csv`, `valid.gold.jsonl`
- seed=77로 shuffle 후 valid 50개 추출 (실험 seeds [42,123,456]과 구분)

---

## 2. 실행 전 검사 (권장)

```powershell
python scripts/check_experiment_config.py --config experiments/configs/cr_n10_m0.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/lm_n50_m0.yaml --strict
python scripts/check_experiment_config.py --config experiments/configs/cr_n50_m0.yaml --strict
```

---

## 3. 실행 명령

### CR-M0 (n=10, seed=42)

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n10_m0.yaml --run-id cr_n10_m0 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

### L-M0 (n=50, seeds [42,123,456])

```powershell
python scripts/run_pipeline.py --config experiments/configs/lm_n50_m0.yaml --run-id lm_n50_m0 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

### CR-M0 (n=50, seeds [42,123,456])

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0.yaml --run-id cr_n50_m0 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --seed_concurrency 3 --with_aggregate
```

---

## 4. 설정 요약

| 항목 | cr_n10_m0 | lm_n50_m0 / cr_n50_m0 |
|------|-----------|------------------------|
| 데이터셋 | cr_n10 (n=10) | beta_n50 (n=50) |
| 실험 seeds | [42] | [42, 123, 456] |
| concurrency | 1 | 3 |
| episodic_memory | C1 (없음) | C1 (없음) |
