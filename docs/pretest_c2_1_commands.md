# Pretest C2_1 (n50, 조건 C2, seed1) 실행·검증 명령

- **Run ID**: `pretest_c2_1`
- **프로파일**: paper
- **메트릭 생성**: `--with_metrics` (structural_error_aggregator + build_metric_report)
- **규약**: 기존 파이프라인/스크립트만 사용 (새 py 생성 금지)

---

## 1. 데이터셋

- **규칙**: finalexperiment와 동일. `experiments/configs/datasets/real_n50_seed1/` 사용.
  - `train.csv`, `valid.csv`, `valid.gold.jsonl`
- 이미 `real_n50_seed1` 디렉터리가 있으면 별도 생성 불필요.
- 다른 소스(train/valid.json 등)에서 생성할 경우: final.yaml과 동일한 데이터 생성 규칙으로 `train.csv`, `valid.csv`, `valid.gold.jsonl`을 만들어 위 경로에 두면 됨.

---

## 2. YAML 생성

- **파일**: `experiments/configs/pretest_c2_1.yaml` (이미 생성됨)
- 내용: finalexperiment_n50_seed1_c2_1과 동일, `run_id: pretest_c2_1`만 변경.

---

## 3. 실험 실행 (run_pipeline.py)

프로젝트 루트에서:

```powershell
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_1.yaml --run-id pretest_c2_1 --mode proposed --profile paper --with_metrics
```

- `experiment.repeat.seeds: [1]` 이므로 실제 run_id는 `pretest_c2_1__seed1`, 결과 디렉터리는 **`results/pretest_c2_1__seed1_proposed`**.
- `--with_metrics`: run 후 `structural_error_aggregator.py` → `build_metric_report.py` 자동 실행 (메트릭·리포트 생성).

(선택) 실험 전 설정 규약 점검:

```powershell
python scripts/check_experiment_config.py --config experiments/configs/pretest_c2_1.yaml --strict
```

또는 파이프라인에 포함:

```powershell
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_1.yaml --run-id pretest_c2_1 --mode proposed --profile paper --with_metrics --with_integrity_check
```

---

## 4. 어그리게이터·규약 점검 (실험 후)

실행 후 **run_dir** = `results/pretest_c2_1__seed1_proposed` 기준.

### 4.1 어그리게이터 (이미 `--with_metrics`로 실행됨)

- **structural_error_aggregator**: `derived/metrics/structural_metrics.csv`, `structural_metrics_table.md`
- **build_metric_report**: `reports/pretest_c2_1__seed1_proposed/metric_report.html`

수동 재실행 시:

```powershell
python scripts/structural_error_aggregator.py --input results/pretest_c2_1__seed1_proposed/scorecards.jsonl --outdir results/pretest_c2_1__seed1_proposed/derived/metrics --profile paper_main
python scripts/build_metric_report.py --run_dir results/pretest_c2_1__seed1_proposed --out_dir reports/pretest_c2_1__seed1_proposed --metrics_profile paper_main
```

### 4.2 규약 점검용 스크립트 (A–D 매핑)

| 확인 항목 | 내용 | 사용 스크립트 |
|-----------|------|----------------|
| **A. 메모리 접근 제어** | EPM/TAN에 DEBATE_CONTEXT__MEMORY 없음, CJ에만(gate 통과 시), Stage2 리뷰에 STAGE2_REVIEW_CONTEXT__MEMORY 존재 여부 | `pipeline_integrity_verification.py` (debate_persona_memory, stage2_memory_injection) |
| **B. 조건 의미 유지** | C2_silent/C2_eval_only: retrieval_executed=True·프롬프트 노출 없음, eval_only는 store_write=False | `build_memory_condition_summary.py`(다중 조건 비교 시), scorecard/trace 메타 필드 수동 검토 |
| **C. 저장 정책** | store_write=True일 때 stored/skipped 혼합 (전부 저장 or 전부 스킵이면 실패) | `pipeline_integrity_verification.py` (selective_storage_mix) |
| **D. 메트릭 무결성** | tuple_f1_s1/s2 NaN·0·폭주 없음, implicit_invalid_pred_rate 정상, delta_f1 의미 있는 값 | `structural_error_aggregator` 출력 + `build_metric_report` / `structural_metrics.csv` 검토 |

실행 예:

```powershell
REM A, C: 메모리·저장 정책·SoT 검증 (산출: reports/pipeline_integrity_verification_pretest_c2_1.json)
python scripts/pipeline_integrity_verification.py --run_dir results/pretest_c2_1__seed1_proposed --out reports/pipeline_integrity_verification_pretest_c2_1.json

REM 일관성 체크리스트 (scorecard source, gold, triptych, 불일치 플래그 등)
python scripts/consistency_checklist.py --run_dir results/pretest_c2_1__seed1_proposed
```

B는 단일 C2 런만 할 경우 `build_memory_condition_summary`는 C1/C2/C3 여러 런을 넘길 때 유용. C2만 검토할 때는 scorecard `meta.memory` (retrieval, injection, store_decision)와 `pipeline_integrity_verification` 결과로 확인.

D는 다음 확인:
- `results/pretest_c2_1__seed1_proposed/derived/metrics/structural_metrics.csv` 에서 `tuple_f1_s1`, `tuple_f1_s2`, `delta_f1`, `implicit_invalid_pred_rate` 값이 NaN/비정상 아님.
- `reports/pretest_c2_1__seed1_proposed/metric_report.html` 에서 동일 메트릭 표시 정상.

---

## 5. 요약 커맨드 (복사용)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent

REM (선택) 설정 규약 검사
python scripts/check_experiment_config.py --config experiments/configs/pretest_c2_1.yaml --strict

REM 실험 실행 (paper + 메트릭)
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_1.yaml --run-id pretest_c2_1 --mode proposed --profile paper --with_metrics

REM 검증 (run_dir = results/pretest_c2_1__seed1_proposed)
python scripts/pipeline_integrity_verification.py --run_dir results/pretest_c2_1__seed1_proposed --out reports/pipeline_integrity_verification_pretest_c2_1.json
python scripts/consistency_checklist.py --run_dir results/pretest_c2_1__seed1_proposed
```

- **Run directory**: `results/pretest_c2_1__seed1_proposed`
- **Reports**: `reports/pretest_c2_1__seed1_proposed/` (metric_report.html 등)
- **Verification JSON**: `reports/pipeline_integrity_verification_pretest_c2_1.json`
