# Betatest 실행 명령

Betatest: C1/C2/C3/C2_eval_only 조건 실험. betatest_n50 데이터셋(seed=99로 추출, real_n50_seed1과 구분), T1 설정, paper 프로파일, seeds [42, 123], concurrency 2.

## 1. 데이터셋 생성

```powershell
python scripts/make_betatest_n50_dataset.py
```

- 입력: `experiments/configs/datasets/train/valid.jsonl`
- 출력: `experiments/configs/datasets/betatest_n50/train.csv`, `valid.csv`, `valid.gold.jsonl`
- seed=99로 shuffle 후 valid 50개 추출. real_n50_seed1(seed=1)과 **다른 ID 집합**.
- 동일 seed로 재실행 시 항상 동일한 50개 추출 (재현성).

## 2. 정합성 검사 (실행 전 권장)

```powershell
python scripts/check_experiment_config.py --config experiments/configs/betatest_c1.yaml --strict
```

## 3. 전체 실행 (한 번에)

```powershell
.\scripts\run_betatest.ps1
```

- 데이터셋 생성 → C1 → C2 → C3 → C2_eval_only 순차 실행 → 메트릭 병합.
- 각 조건별 `--profile paper --with_metrics --metrics_profile paper_main` 적용.
- 결과: `results/betatest_c1__seed42_proposed`, `betatest_c1__seed123_proposed`, … (seeds 42, 123 × 4 조건).

## 4. 조건별 개별 실행 (C2, C3, C2_eval_only)

각 조건은 `--with_metrics --metrics_profile paper_main`으로 structural_error_aggregator + build_metric_report 포함.

```powershell
# C2 (advisory memory) — 에피소드 메모리 ON, retrieval + 주입
python scripts/run_pipeline.py --config experiments/configs/betatest_c2.yaml --run-id betatest_c2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main

# C3 (retrieval-only / silent) — retrieval 실행, debate 주입 마스킹
python scripts/run_pipeline.py --config experiments/configs/betatest_c3.yaml --run-id betatest_c3 --mode proposed --profile paper --with_metrics --metrics_profile paper_main

# C2_eval_only (v1_2, 평가 전용) — retrieval + 주입 마스킹, store_write false
python scripts/run_pipeline.py --config experiments/configs/betatest_c2_eval_only.yaml --run-id betatest_c2_eval_only --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

### 4.1 C2/C3/C2_eval 완료 후 어그리게이션·체크리스트·머징

```powershell
# C2 시드별 머징
python scripts/aggregate_seed_metrics.py --run_dirs results/betatest_c2__seed42_proposed,results/betatest_c2__seed123_proposed --outdir results/betatest_c2_aggregated --metrics_profile paper_main --with_metric_report

# C3 시드별 머징
python scripts/aggregate_seed_metrics.py --run_dirs results/betatest_c3__seed42_proposed,results/betatest_c3__seed123_proposed --outdir results/betatest_c3_aggregated --metrics_profile paper_main --with_metric_report

# C2_eval_only 시드별 머징
python scripts/aggregate_seed_metrics.py --run_dirs results/betatest_c2_eval_only__seed42_proposed,results/betatest_c2_eval_only__seed123_proposed --outdir results/betatest_c2_eval_only_aggregated --metrics_profile paper_main --with_metric_report
```

### 4.2 체크리스트 (각 조건·시드별)

```powershell
# C2 seed42
python scripts/consistency_checklist.py --run_dir results/betatest_c2__seed42_proposed --triptych_n 5

# C3 seed42
python scripts/consistency_checklist.py --run_dir results/betatest_c3__seed42_proposed --triptych_n 5

# C2_eval_only seed42
python scripts/consistency_checklist.py --run_dir results/betatest_c2_eval_only__seed42_proposed --triptych_n 5
```

## 5. 메트릭 병합 (조건별 실행 후)

```powershell
python scripts/build_memory_condition_summary.py --runs "C1:results/betatest_c1__seed42_proposed" "C2:results/betatest_c2__seed42_proposed" "C3:results/betatest_c3__seed42_proposed" "C2_eval_only:results/betatest_c2_eval_only__seed42_proposed" --out reports/betatest_c1_c2_c3_c2_eval_only_summary.md
```

## 6. 정합성 체크리스트 (실행 후)

```powershell
python scripts/consistency_checklist.py --run_dir results/betatest_c1__seed42_proposed --triptych_n 5
```

## 설정 요약

| 항목 | 값 |
|------|-----|
| 데이터셋 | betatest_n50 (train/valid.jsonl, seed=99, valid 50개) |
| Override | t1 (min_total=1.0, min_margin=0.5, l3_conservative=true) |
| episodic_memory | run별 분리(store_path 자동 주입), clear_store_at_run_start off |
| seeds | [42, 123] |
| concurrency | 2 |
| run_purpose | paper |
| demo | k=0, hash_filter=false |
