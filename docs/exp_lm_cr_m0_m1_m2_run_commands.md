# L-M0 vs CR-M0, CR-M0 vs CR-M1 vs CR-M2 실험 실행 가이드

## 1. 조건 요약

| 조건 | 실험 | n | seeds | config |
|------|------|---|-------|--------|
| 1 | L-M0 vs CR-M0 | 50 | 3 (42, 123, 456) | lm_n50_m0, cr_n50_m0 |
| 2 | CR-M0 vs CR-M1 vs CR-M2 | 50 | 5 (42, 123, 456, 789, 101) | cr_n50_m0_s5, cr_n50_m1, cr_n50_m2 |

## 2. 데이터 준비

### 2.1 데이터셋 생성 (beta_n50)

```bash
python scripts/make_beta_n50_dataset.py --outdir experiments/configs/datasets/beta_n50 --valid_size 50 --seed 77
```

출력: `experiments/configs/datasets/beta_n50/train.csv`, `valid.csv`, `valid.gold.jsonl`

### 2.2 데이터셋 존재 확인

```bash
ls experiments/configs/datasets/beta_n50/
# train.csv, valid.csv, valid.gold.jsonl
```

---

## 3. Experiment Config YAML

| 파일 | 내용 |
|------|------|
| `experiments/configs/lm_n50_m0.yaml` | L-M0 (legacy, override_profile t1), seeds 3 |
| `experiments/configs/cr_n50_m0.yaml` | CR-M0 (no memory), seeds 3 |
| `experiments/configs/cr_n50_m0_s5.yaml` | CR-M0 (no memory), seeds 5 |
| `experiments/configs/cr_n50_m1.yaml` | CR-M1 (read-only retrieve), seeds 5 |
| `experiments/configs/cr_n50_m2.yaml` | CR-M2 (read+write retrieve), seeds 5 |

---

## 4. Pipeline 실행 명령

### 4.1 조건 1: L-M0 vs CR-M0 (seeds 3)

```bash
# L-M0
python scripts/run_pipeline.py --config experiments/configs/lm_n50_m0.yaml --run-id lm_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate

# CR-M0
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0.yaml --run-id cr_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate
```

### 4.2 조건 2: CR-M0 vs CR-M1 vs CR-M2 (seeds 5)

```bash
# CR-M0 (seeds 5)
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0_s5.yaml --run-id cr_n50_m0_s5 --mode proposed --profile paper --with_metrics --with_aggregate

# CR-M1
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1.yaml --run-id cr_n50_m1 --mode proposed --profile paper --with_metrics --with_aggregate

# CR-M2
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m2.yaml --run-id cr_n50_m2 --mode proposed --profile paper --with_metrics --with_aggregate
```

### 4.3 옵션

| 옵션 | 의미 |
|------|------|
| `--with_metrics` | structural_error_aggregator + build_metric_report |
| `--with_aggregate` | aggregate_seed_metrics (시드별 머징·평균±표준편차·통합 보고서) |
| `--metrics_profile paper_main` | paper 메트릭 프로필 (기본값) |
| `--seed N` | 특정 시드만 실행 (예: `--seed 42`) |
| `--seed_concurrency N` | 시드 병렬 실행 수 (기본 1) |

---

## 5. SSOT 검증용 산출물

### 5.1 Run별 산출물 (per seed)

| 경로 | 설명 |
|------|------|
| `results/<run_id>__seed<N>_proposed/` | 런별 출력 |
| `results/<run_id>__seed<N>_proposed/outputs.jsonl` | FinalOutputSchema (SSOT) |
| `results/<run_id>__seed<N>_proposed/scorecards.jsonl` | stage_delta, pairs-based changed 등 |
| `results/<run_id>__seed<N>_proposed/traces.jsonl` | 파이프라인 추적 |
| `results/<run_id>__seed<N>_proposed/derived/metrics/structural_metrics.csv` | 구조적 메트릭 |
| `results/<run_id>__seed<N>_proposed/derived/metrics/structural_metrics_table.md` | 메트릭 마크다운 |
| `reports/<run_id>__seed<N>_proposed/metric_report.html` | 검증용 HTML |
| `reports/<run_id>__seed<N>_proposed/index.html` | Run 리포트 |

### 5.2 Aggregated 산출물 (with_aggregate)

| 경로 | 설명 |
|------|------|
| `results/<run_id>_aggregated/merged_scorecards.jsonl` | 시드별 scorecards 머지 |
| `results/<run_id>_aggregated/structural_metrics.csv` | 머지 기반 메트릭 |
| `results/<run_id>_aggregated/aggregated_mean_std.csv` | 평균±표준편차 |
| `results/<run_id>_aggregated/integrated_report.md` | 통합 보고서 |
| `results/<run_id>_aggregated/metric_report.html` | 통합 메트릭 리포트 (--with_metric_report 시) |

### 5.3 SSOT 체크리스트 (stage_delta)

- `stage_delta.changed` = pairs 기반 (s1_pairs != final_pairs) or (stage1_label != final_label)
- `stage_delta.pairs_changed`, `label_changed`, `n_s1_pairs`, `n_final_pairs` 저장
- `stage2_adopted_but_no_change` 분리

### 5.4 CR 전용 SSOT 필드

- `meta.stage1_perspective_aste` (A/B/C triplets)
- `final_tuples_pre_review`, `final_tuples_post_review`
- `review_actions`, `arb_actions`

---

## 6. 전체 실행 순서 (권장)

```bash
# 1. 데이터 생성
python scripts/make_beta_n50_dataset.py --outdir experiments/configs/datasets/beta_n50 --valid_size 50 --seed 77

# 2. 조건 1: L-M0 vs CR-M0
python scripts/run_pipeline.py --config experiments/configs/lm_n50_m0.yaml --run-id lm_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0.yaml --run-id cr_n50_m0 --mode proposed --profile paper --with_metrics --with_aggregate

# 3. 조건 2: CR-M0 vs CR-M1 vs CR-M2
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0_s5.yaml --run-id cr_n50_m0_s5 --mode proposed --profile paper --with_metrics --with_aggregate
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1.yaml --run-id cr_n50_m1 --mode proposed --profile paper --with_metrics --with_aggregate
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m2.yaml --run-id cr_n50_m2 --mode proposed --profile paper --with_metrics --with_aggregate
```

---

## 7. 결과 디렉터리 요약

| 조건 | base_run_id | results 디렉터리 |
|------|-------------|------------------|
| 1 | lm_n50_m0 | lm_n50_m0__seed42_proposed, lm_n50_m0__seed123_proposed, lm_n50_m0__seed456_proposed |
| 1 | cr_n50_m0 | cr_n50_m0__seed42_proposed, cr_n50_m0__seed123_proposed, cr_n50_m0__seed456_proposed |
| 2 | cr_n50_m0_s5 | cr_n50_m0_s5__seed42_proposed, ...seed123, ...seed456, ...seed789, ...seed101 |
| 2 | cr_n50_m1 | cr_n50_m1__seed42_proposed, ... |
| 2 | cr_n50_m2 | cr_n50_m2__seed42_proposed, ... |
