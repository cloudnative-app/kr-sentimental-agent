# Finalexperiment C2_1 테스트런 (PJ1–PJ4 점검)

C2와 동일한 데이터(n50, seed 1, real_n50_seed1)·override 설정. run_id만 `finalexperiment_n50_seed1_c2_1`로 구분.  
**어그리게이터 포함**: `--with_metrics`로 structural_error_aggregator + metric_report 자동 실행.

---

## 전제

- 데이터셋 `experiments/configs/datasets/real_n50_seed1/` 존재 (없으면 아래 1번 먼저 실행).

---

## 1) 데이터셋 없을 때만 (최초 1회)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent
python scripts/make_real_n100_seed1_dataset.py --valid_size 50 --seed 1 --outdir experiments/configs/datasets/real_n50_seed1
```

---

## 2) C2_1 단일 런 (파이프라인 + 어그리게이터)

**PowerShell:**

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent
python scripts/run_pipeline.py --config experiments/configs/finalexperiment_n50_seed1_c2_1.yaml --run-id finalexperiment_n50_seed1_c2_1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

**한 줄 (프로젝트 루트 가정):**

```powershell
python scripts/run_pipeline.py --config experiments/configs/finalexperiment_n50_seed1_c2_1.yaml --run-id finalexperiment_n50_seed1_c2_1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
```

- 결과: `results/finalexperiment_n50_seed1_c2_1__seed1_proposed/`
- 메트릭/어그리게이터: `results/.../derived/metrics/` (structural_metrics.csv 등), `reports/.../metric_report.html`

---

## 3) 파이썬 래퍼로 C2_1만 실행 (데이터셋 생성 옵션 포함)

```powershell
cd c:\Users\wisdo\Documents\kr-sentimental-agent
python scripts/run_finalexperiment_n50_seed1.py --conditions c2_1
```

데이터셋 이미 있으면:

```powershell
python scripts/run_finalexperiment_n50_seed1.py --conditions c2_1 --skip_dataset
```

---

## 4) 점검 시 참고

- **PJ1**: `invariant_pj1_aspect_not_substring` → `scripts/pipeline_integrity_verification.py` 실행 시 또는 파이프라인 후 수동 검증.
- **PJ2/PJ4**: `results/.../override_gate_debug.jsonl`, `override_gate_debug_summary.json` (evidence_ok, skip_reason, max_one_override_per_sample).
- **PJ3**: `override_gate_debug.jsonl` 내 `type: ev_decision` 레코드 (ev_score, ev_adopted, ev_components).

 pipeline_integrity 검증 (선택):

```powershell
python scripts/pipeline_integrity_verification.py results/finalexperiment_n50_seed1_c2_1__seed1_proposed
```
