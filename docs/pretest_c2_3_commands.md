# Pretest C2_3 (n50, C2, seed1, override T1) 실행·검증 명령

- **Run ID**: `pretest_c2_3`
- **Override**: T1 프로파일 (`debate_override_thresholds.json` t1: min_total=1.0, min_margin=0.5, min_target_conf=0.6, l3_conservative=true, ev_threshold=0.5)
- **프로파일**: paper
- **메트릭 생성**: `--with_metrics`
- **SSOT/규약**: pipeline_integrity_verification, structural_error_aggregator, consistency_checklist 등

---

## 1. 데이터셋

- **경로**: `experiments/configs/datasets/real_n50_seed1/`  
  - `train.csv`, `valid.csv`, `valid.gold.jsonl`
- pretest_c2_1 / finalexperiment와 동일 소스 사용.

---

## 2. YAML

- **파일**: `experiments/configs/pretest_c2_3.yaml`
- **Override**: `override_profile: t1` (인라인 `pipeline.debate_override` 없음 → manifest `debate_override_effective.source: json_profile`)

---

## 3. 실험 실행 (run_pipeline.py, 프로파일 paper, 메트릭 생성)

프로젝트 루트에서:

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent

REM (선택) 설정 규약 검사
python scripts/check_experiment_config.py --config experiments/configs/pretest_c2_3.yaml --strict

REM 실험 실행: paper 프로파일 + 메트릭 생성
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_3.yaml --run-id pretest_c2_3 --mode proposed --profile paper --with_metrics
```

- `experiment.repeat.seeds: [1]` → 실제 run_id는 `pretest_c2_3__seed1`, 결과 디렉터리 **`results/pretest_c2_3__seed1_proposed`**.
- `--with_metrics`: 실행 후 `structural_error_aggregator.py` → `build_metric_report.py` 자동 실행.

(선택) 무결성 검사 포함:

```powershell
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_3.yaml --run-id pretest_c2_3 --mode proposed --profile paper --with_metrics --with_integrity_check
```

---

## 4. SSOT/규약 검증용 스크립트 (실험 후)

**run_dir** = `results/pretest_c2_3__seed1_proposed` 기준.

### 4.1 어그리게이터 (이미 `--with_metrics`로 실행됨)

수동 재실행 시:

```powershell
python scripts/structural_error_aggregator.py --input results/pretest_c2_3__seed1_proposed/scorecards.jsonl --outdir results/pretest_c2_3__seed1_proposed/derived/metrics --profile paper_main
python scripts/build_metric_report.py --run_dir results/pretest_c2_3__seed1_proposed --out_dir reports/pretest_c2_3__seed1_proposed --metrics_profile paper_main
```

### 4.2 벨리데이터·규약 점검 (A–D 매핑)

| 확인 항목 | 내용 | 사용 스크립트 |
|-----------|------|----------------|
| **A. 메모리 접근 제어** | EPM/TAN에 DEBATE_CONTEXT__MEMORY 없음, CJ에만, Stage2 리뷰에 STAGE2_REVIEW_CONTEXT__MEMORY 존재 | `pipeline_integrity_verification.py` |
| **B. 조건 의미 유지** | C2: retrieval·프롬프트 노출·store 정책 | scorecard/trace 메타 + `build_memory_condition_summary.py`(다중 조건 시) |
| **C. 저장 정책** | store_write 시 stored/skipped 혼합 | `pipeline_integrity_verification.py` (selective_storage_mix) |
| **D. 메트릭 무결성** | tuple_f1_s1/s2, delta_f1, implicit_invalid_pred_rate 등 정상 | `structural_metrics.csv` + `metric_report.html` |

실행 예:

```powershell
REM A, C: 메모리·저장 정책·SSOT 검증 (산출: reports/pipeline_integrity_verification_pretest_c2_3.json)
python scripts/pipeline_integrity_verification.py --run_dir results/pretest_c2_3__seed1_proposed --out reports/pipeline_integrity_verification_pretest_c2_3.json

REM 일관성 체크리스트 (scorecard source, gold, triptych, 불일치 플래그 등)
python scripts/consistency_checklist.py --run_dir results/pretest_c2_3__seed1_proposed
```

### 4.3 Override T1 확인

- **manifest**: `results/pretest_c2_3__seed1_proposed/manifest.json` → `debate_override_effective.override_profile_id: "t1"`, `source: "json_profile"`.
- **scorecard meta**: 각 row `meta.debate_override_effective` 에 동일 값.
- **override_gate_debug_summary.json**: `override_hint_invalid_total`, `override_hint_invalid_rate`, `by_sample` 등.

---

## 5. 요약 커맨드 (복사용)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent

REM (선택) 설정 규약 검사
python scripts/check_experiment_config.py --config experiments/configs/pretest_c2_3.yaml --strict

REM 실험 실행 (paper + 메트릭)
python scripts/run_pipeline.py --config experiments/configs/pretest_c2_3.yaml --run-id pretest_c2_3 --mode proposed --profile paper --with_metrics

REM SSOT/규약 검증
python scripts/pipeline_integrity_verification.py --run_dir results/pretest_c2_3__seed1_proposed --out reports/pipeline_integrity_verification_pretest_c2_3.json
python scripts/consistency_checklist.py --run_dir results/pretest_c2_3__seed1_proposed

REM (선택) 어그리게이터·리포트 수동 재실행
python scripts/structural_error_aggregator.py --input results/pretest_c2_3__seed1_proposed/scorecards.jsonl --outdir results/pretest_c2_3__seed1_proposed/derived/metrics --profile paper_main
python scripts/build_metric_report.py --run_dir results/pretest_c2_3__seed1_proposed --out_dir reports/pretest_c2_3__seed1_proposed --metrics_profile paper_main
```

- **Run directory**: `results/pretest_c2_3__seed1_proposed`
- **Reports**: `reports/pretest_c2_3__seed1_proposed/` (metric_report.html 등)
- **Verification JSON**: `reports/pipeline_integrity_verification_pretest_c2_3.json`
