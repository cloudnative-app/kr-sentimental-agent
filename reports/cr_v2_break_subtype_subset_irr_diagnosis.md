# break subtype / subset IRR 미산출 원인 검토

## 1. break subtype (implicit, negation, simple) — 빈 값 원인

### 데이터 흐름

```
structural_error_aggregator (scorecards) → derived/metrics/structural_metrics.csv
         ↓
aggregate_seed_metrics (per-seed CSV) → aggregated_mean_std.csv
         ↓
build_cr_v2_paper_table (agg CSV) → cr_v2_paper_table.md
```

### 원인

**aggregated_mean_std.csv에 `break_rate_implicit`, `break_rate_negation`, `break_rate_simple`가 없음.**

- **per-seed structural_metrics.csv**에는 해당 컬럼이 존재함  
  - 예: `results/cr_v2_n100_m0_v4__seed42_proposed/derived/metrics/structural_metrics.csv`  
  - `break_rate_implicit`, `break_rate_negation`, `break_rate_simple`, `break_rate_*_refpol` 포함
- **aggregate_seed_metrics**의 출력 로직 문제  
  - 223행: `for col in numeric_cols`로만 쓰기 → `cols_for_report` 미사용  
  - `REPORT_METRICS_ALWAYS`에 break subtype 미포함 (26–32행)  
  - 집계 시점에 per-seed CSV에 break subtype이 없었을 경우 `numeric_cols`에 포함되지 않아 누락

### 해결 방안

1. **REPORT_METRICS_ALWAYS에 break subtype 추가**  
   `scripts/aggregate_seed_metrics.py` 26–32행:
   ```python
   "break_rate_implicit_refpol", "break_rate_negation_refpol", "break_rate_simple_refpol",
   ```
2. **aggregated_mean_std.csv 쓰기 시 `cols_for_report` 사용**  
   `compute_mean_std`가 `cols_for_report`를 반환하도록 수정 후, 223행에서 `for col in cols_for_report` 사용
3. **aggregate_seed_metrics 재실행**  
   `--ensure_per_seed_metrics`로 per-seed structural_metrics를 다시 생성한 뒤 집계

---

## 2. subset IRR (implicit, negation) — 빈 값 원인

### 데이터 흐름

```
compute_irr (outputs.jsonl) → irr/irr_subset_summary.json
         ↓
build_cr_v2_paper_table (_load_subset_irr) → Table 2
```

### irr_subset_summary.json 실제 값

```json
{
  "conflict": {"n": 24, "meas_cohen_kappa_mean": 0.35, "irr_cohen_kappa_mean": 0.29},
  "implicit": {"n": 0, "meas_cohen_kappa_mean": null, "irr_cohen_kappa_mean": null},
  "negation": {"n": 0, "meas_cohen_kappa_mean": null, "irr_cohen_kappa_mean": null}
}
```

### 원인

**implicit / negation subset의 n=0 → 해당 subset에 속하는 샘플이 없음.**

| subset   | 판별 조건 (compute_irr.py) | CR pipeline에서의 상태 |
|----------|---------------------------|-------------------------|
| **implicit** | `inputs.gold_tuples` 중 `aspect_term==""` 인 tuple 존재 | `outputs.jsonl`에 `inputs` 없음. gold는 scorecard에만 주입되고 outputs에는 미포함 |
| **negation** | `validator.structural_risks`에 NEGATION_SCOPE/CONTRAST_SCOPE 존재 | CR 파이프라인은 `stage1_validator: null`, `stage2_validator: null`. Validator 단계 없음 |

- **implicit n=0**: `compute_irr`가 `outputs.jsonl`만 사용하는데, 여기에는 `inputs.gold_tuples`가 없음.  
  - `run_experiments`는 gold를 scorecard에만 넣고, outputs에는 넣지 않음.
- **negation n=0**: CR 파이프라인에 validator 단계가 없어 `structural_risks`가 항상 비어 있음.

### 해결 방안

1. **implicit**: `compute_irr`가 `inputs.gold_tuples`를 사용할 수 있도록  
   - `outputs.jsonl`에 `inputs.gold_tuples` 포함시키거나  
   - `compute_irr`가 scorecard/별도 gold 소스를 참조하도록 수정
2. **negation**: CR 파이프라인에 negation/contrast 검출 단계 추가  
   - 또는 `analysis_flags`/`conflict_flags` 등 기존 필드에서 negation 신호를 추출하는 방식으로 `_has_negation_case` 로직 변경

---

## 3. 요약

| 항목           | 원인 | 확인용 파일 |
|----------------|------|-------------|
| break subtype  | aggregated_mean_std.csv에 break subtype 누락. aggregate가 `numeric_cols`만 쓰고 REPORT_METRICS_ALWAYS 미포함 | `scripts/aggregate_seed_metrics.py` (26–32, 223행), `results/cr_v2_n100_m0_v4_aggregated/aggregated_mean_std.csv`, `results/cr_v2_n100_m0_v4__seed42_proposed/derived/metrics/structural_metrics.csv` |
| subset IRR (implicit) | outputs.jsonl에 `inputs.gold_tuples` 없음 → implicit 판별 불가 | `scripts/compute_irr.py` (_is_implicit_case), `results/cr_v2_n100_m1_v4__seed42_proposed/outputs.jsonl` (inputs 없음), `results/*/irr/irr_subset_summary.json` |
| subset IRR (negation) | CR 파이프라인에 validator 단계 없음 → negation 판별 불가 | `scripts/compute_irr.py` (_has_negation_case), `agents/conflict_review_runner.py` |
