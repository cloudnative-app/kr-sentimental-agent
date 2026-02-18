# CR n50 M0/M1 v5 실험 실행 명령어

**설정**: seeds=[3, 123, 456], concurrency=3  
**v5 변경점**: conflict_flags ref 기준 primary, term 기준 secondary. `pipeline.conflict_mode: primary_secondary`, `semantic_conflict_enabled: false`

---

## 1. 파이프라인 (run_pipeline) — paper 프로파일, 메트릭스, 어그리게이터

### M0 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0_v5.yaml --run-id cr_n50_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --with_aggregate
```

### M1 v5

```powershell
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1_v5.yaml --run-id cr_n50_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --with_aggregate
```

---

## 2. 메트릭스 (structural_error_aggregator)

파이프라인 `--with_metrics` 시 자동 실행됨. 수동 실행:

### M0 v5

```powershell
python scripts/structural_error_aggregator.py --input results/cr_n50_m0_v5_aggregated/merged_scorecards.jsonl --outdir results/cr_n50_m0_v5_aggregated/merged_metrics --profile paper_main
```

### M1 v5

```powershell
python scripts/structural_error_aggregator.py --input results/cr_n50_m1_v5_aggregated/merged_scorecards.jsonl --outdir results/cr_n50_m1_v5_aggregated/merged_metrics --profile paper_main
```

---

## 3. 어그리게이터 (aggregate_seed_metrics)

파이프라인 `--with_aggregate` 시 자동 실행됨. 수동 실행:

### M0 v5

```powershell
python scripts/aggregate_seed_metrics.py --base_run_id cr_n50_m0_v5 --mode proposed --seeds 3,123,456 --outdir results/cr_n50_m0_v5_aggregated --metrics_profile paper_main
```

### M1 v5

```powershell
python scripts/aggregate_seed_metrics.py --base_run_id cr_n50_m1_v5 --mode proposed --seeds 3,123,456 --outdir results/cr_n50_m1_v5_aggregated --metrics_profile paper_main
```

---

## 4. 페이퍼 메트릭 (export_paper_metrics)

### M0 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0_v5 --mode proposed --out-dir results/cr_n50_m0_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0_v5__seed3_proposed results/cr_n50_m0_v5__seed123_proposed results/cr_n50_m0_v5__seed456_proposed --out-dir results/cr_n50_m0_v5_paper
```

### M1 v5

```powershell
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m1_v5 --mode proposed --out-dir results/cr_n50_m1_v5_paper

python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m1_v5__seed3_proposed results/cr_n50_m1_v5__seed123_proposed results/cr_n50_m1_v5__seed456_proposed --out-dir results/cr_n50_m1_v5_paper
```

---

## 5. 순차 실행 (M0 → M1)

```powershell
# M0 v5 전체
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m0_v5.yaml --run-id cr_n50_m0_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --with_aggregate

# M1 v5 전체
python scripts/run_pipeline.py --config experiments/configs/cr_n50_m1_v5.yaml --run-id cr_n50_m1_v5 --mode proposed --profile paper --with_metrics --metrics_profile paper_main --with_aggregate

# 페이퍼 메트릭 (파이프라인에 포함되지 않으면 별도 실행)
python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m0_v5 --mode proposed --out-dir results/cr_n50_m0_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m0_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m0_v5__seed3_proposed results/cr_n50_m0_v5__seed123_proposed results/cr_n50_m0_v5__seed456_proposed --out-dir results/cr_n50_m0_v5_paper

python scripts/export_paper_metrics_md.py --base-run-id cr_n50_m1_v5 --mode proposed --out-dir results/cr_n50_m1_v5_paper
python scripts/export_paper_metrics_aggregated.py --agg-path results/cr_n50_m1_v5_aggregated/aggregated_mean_std.csv --run-dirs results/cr_n50_m1_v5__seed3_proposed results/cr_n50_m1_v5__seed123_proposed results/cr_n50_m1_v5__seed456_proposed --out-dir results/cr_n50_m1_v5_paper
```

---

## 산출물 경로

| 항목 | M0 v5 | M1 v5 |
|------|-------|-------|
| 시드별 run | results/cr_n50_m0_v5__seed{3,123,456}_proposed | results/cr_n50_m1_v5__seed{3,123,456}_proposed |
| merged scorecards | results/cr_n50_m0_v5_aggregated/merged_scorecards.jsonl | results/cr_n50_m1_v5_aggregated/merged_scorecards.jsonl |
| aggregated_mean_std | results/cr_n50_m0_v5_aggregated/aggregated_mean_std.csv | results/cr_n50_m1_v5_aggregated/aggregated_mean_std.csv |
| paper | results/cr_n50_m0_v5_paper/ | results/cr_n50_m1_v5_paper/ |

---

## v5 YAML 수정 요약

| 설정 | 설명 |
|------|------|
| `pipeline.conflict_mode: primary_secondary` | Primary: ref-pol mismatch. Secondary: term-pol mismatch (ref 비어 있을 때) |
| `pipeline.semantic_conflict_enabled: false` | Semantic conflict 후보 플래그 비활성화 (테스트 시 true로 변경 가능) |

**수정 없이 실행 시**: 코드 기본값 `conflict_mode=primary_secondary`, `semantic_conflict_enabled=False`가 적용되므로 M1 v3처럼 기존 yaml만 있어도 동작은 동일. 다만 v5 yaml에 명시해 두면 설정이 문서화되고, 나중에 `primary` 전용·semantic 활성화 등으로 바꾸기 쉽다.
