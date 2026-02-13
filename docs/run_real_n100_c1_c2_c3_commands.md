# REAL N100 C1 / C2 / C3 실행·메트릭 집계·병합 커맨드

로컬에서 REAL N100 조건 C1, C2, C3을 **순차 실행**하고, 메트릭 집계·병합까지 수행하기 위한 커맨드 정리.

---

## 사전 조건

- 데이터셋: `experiments/configs/datasets/real_n100_seed1/` (valid.csv, valid.gold.jsonl 등)
  - 없으면: `python scripts/make_real_n100_seed1_dataset.py` 로 생성
- Python 환경에서 프로젝트 루트가 현재 디렉터리

---

## 1. C1 → C2 → C3 순차 실행 (각 조건별 1회 실행)

각 커맨드는 해당 조건만 실행하며, `--with_metrics` 로 run 종료 후 **structural_error_aggregator**까지 실행해  
`results/<run_id>__seed1_proposed/derived/metrics/` 에 CSV/MD를 남깁니다.

```powershell
# 프로젝트 루트에서
cd C:\Users\wisdo\Documents\kr-sentimental-agent

# C1 (no memory)
python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c1.yaml --run-id experiment_real_n100_seed1_c1 --mode proposed --profile paper --with_metrics

# C2 (advisory memory)
python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c2.yaml --run-id experiment_real_n100_seed1_c2 --mode proposed --profile paper --with_metrics

# C3 (silent memory)
python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c3.yaml --run-id experiment_real_n100_seed1_c3 --mode proposed --profile paper --with_metrics
```

**산출물 (각 조건당)**  
- `results/experiment_real_n100_seed1_c1__seed1_proposed/`  
  - `outputs.jsonl`, `scorecards.jsonl`, `traces.jsonl`, `manifest.json`  
  - `derived/metrics/structural_metrics.csv`, `structural_metrics_table.md`  
  - `reports/experiment_real_n100_seed1_c1__seed1_proposed/` (HTML 등)  
- C2, C3은 `c2`, `c3` 로 동일 구조.

---

## 2. 이미 실행된 run만 메트릭 집계 (재집계)

이미 `scorecards.jsonl` 만 있고 메트릭을 다시 만들고 싶을 때:

```powershell
# C1
python scripts/structural_error_aggregator.py --input results/experiment_real_n100_seed1_c1__seed1_proposed/scorecards.jsonl --outdir results/experiment_real_n100_seed1_c1__seed1_proposed/derived/metrics --profile paper_main

# C2
python scripts/structural_error_aggregator.py --input results/experiment_real_n100_seed1_c2__seed1_proposed/scorecards.jsonl --outdir results/experiment_real_n100_seed1_c2__seed1_proposed/derived/metrics --profile paper_main

# C3
python scripts/structural_error_aggregator.py --input results/experiment_real_n100_seed1_c3__seed1_proposed/scorecards.jsonl --outdir results/experiment_real_n100_seed1_c3__seed1_proposed/derived/metrics --profile paper_main
```

선택: 튜플 소스 로그·sanity check  
`--log_tuple_sources results/.../derived/metrics/tuple_source_log.tsv --log_sample_n 10`  
`--sanity_check`

---

## 3. C1/C2/C3 메트릭 병합 (조건 비교 테이블)

세 run의 `derived/metrics/structural_metrics.csv` 를 읽어 한 테이블로 만듦:

```powershell
python scripts/build_memory_condition_summary.py --runs "C1:results/experiment_real_n100_seed1_c1__seed1_proposed" "C2:results/experiment_real_n100_seed1_c2__seed1_proposed" "C3:results/experiment_real_n100_seed1_c3__seed1_proposed" --out reports/real_n100_c1_c2_c3_summary.md
```

산출: `reports/real_n100_c1_c2_c3_summary.md` (condition, n, unsupported_polarity_rate, implicit_grounding_rate, explicit_grounding_failure_rate, polarity_conflict_rate, risk_resolution_rate, memory_prompt_injection_chars_mean 등).

---

## 4. 단일 run 통합 (스냅샷 + 논문 테이블 + HTML + 메트릭)

한 run만 스냅샷·논문 테이블·HTML·메트릭까지 한 번에 돌리려면:

```powershell
python scripts/experiment_results_integrate.py --run_dir results/experiment_real_n100_seed1_c2__seed1_proposed --with_metrics --metrics_profile paper_main
```

---

## 5. 한 번에 돌리기 (PowerShell 스크립트)

C1 → C2 → C3 순차 실행 후 병합까지:

```powershell
$ErrorActionPreference = "Stop"
cd C:\Users\wisdo\Documents\kr-sentimental-agent

python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c1.yaml --run-id experiment_real_n100_seed1_c1 --mode proposed --profile paper --with_metrics
python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c2.yaml --run-id experiment_real_n100_seed1_c2 --mode proposed --profile paper --with_metrics
python scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c3.yaml --run-id experiment_real_n100_seed1_c3 --mode proposed --profile paper --with_metrics

New-Item -ItemType Directory -Force -Path reports | Out-Null
python scripts/build_memory_condition_summary.py --runs "C1:results/experiment_real_n100_seed1_c1__seed1_proposed" "C2:results/experiment_real_n100_seed1_c2__seed1_proposed" "C3:results/experiment_real_n100_seed1_c3__seed1_proposed" --out reports/real_n100_c1_c2_c3_summary.md
Write-Host "Done. Summary: reports/real_n100_c1_c2_c3_summary.md"
```

---

## 요약

| 단계 | 커맨드 |
|------|--------|
| C1 실행+메트릭 | `run_pipeline.py --config .../experiment_real_n100_seed1_c1.yaml --run-id experiment_real_n100_seed1_c1 --mode proposed --profile paper --with_metrics` |
| C2 실행+메트릭 | `run_pipeline.py --config .../experiment_real_n100_seed1_c2.yaml --run-id experiment_real_n100_seed1_c2 --mode proposed --profile paper --with_metrics` |
| C3 실행+메트릭 | `run_pipeline.py --config .../experiment_real_n100_seed1_c3.yaml --run-id experiment_real_n100_seed1_c3 --mode proposed --profile paper --with_metrics` |
| 메트릭만 재집계 | `structural_error_aggregator.py --input <run>/scorecards.jsonl --outdir <run>/derived/metrics --profile paper_main` |
| C1/C2/C3 병합 테이블 | `build_memory_condition_summary.py --runs C1:... C2:... C3:... --out reports/real_n100_c1_c2_c3_summary.md` |
