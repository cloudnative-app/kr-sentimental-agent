# Mini4 validation (C1 / C2 / C3 / C2_eval_only) 실행 및 체크리스트

## 개요

- **데이터셋**: mini4 (mini4_b1 / proposed와 동일 규칙, N=10 valid)
- **지원 조건**:
  - **C1**: no memory
  - **C2**: debate + memory (주입)
  - **C3**: retrieval-only (주입 없음, v1_1 C2_silent)
  - **C2_eval_only**: retrieval + 주입 마스킹, store 미저장 (v1_2, ablation)

## YAML

| 조건 | 설정 파일 |
|------|------------|
| C1 | `experiments/configs/experiment_mini4_validation_c1.yaml` |
| C2 | `experiments/configs/experiment_mini4_validation_c2.yaml` |
| C3 | `experiments/configs/experiment_mini4_validation_c3.yaml` |
| C2_eval_only | `experiments/configs/experiment_mini4_validation_c2_eval_only.yaml` |

## 한 번에 실행 (순차 실행 + 메트릭 + 체크리스트)

**프로젝트 루트**에서:

### 기본 (C1 + C2만)

```bash
python scripts/run_mini4_validation_c1_c2.py
```

### C1, C2, C3, C2_eval_only 전부 실행

```bash
python scripts/run_mini4_validation_c1_c2.py --all
```

### 실행할 조건만 지정

```bash
python scripts/run_mini4_validation_c1_c2.py --conditions c1 c2 c3 c2_eval_only
python scripts/run_mini4_validation_c1_c2.py --conditions c1 c2
python scripts/run_mini4_validation_c1_c2.py --conditions c2_eval_only c2
```

### 체크리스트만 재실행 (실험 스킵)

```bash
python scripts/run_mini4_validation_c1_c2.py --skip_run --conditions c1 c2 c3 c2_eval_only
```

### 결과 리포트 경로 지정

```bash
python scripts/run_mini4_validation_c1_c2.py --out reports/mini4_validation_checklist.md
```

---

### PowerShell

```powershell
# 기본: C1, C2
.\scripts\run_mini4_validation_c1_c2.ps1

# C1, C2, C3, C2_eval_only 전부
.\scripts\run_mini4_validation_c1_c2.ps1 -All

# 조건 지정 (쉼표 또는 공백 구분)
.\scripts\run_mini4_validation_c1_c2.ps1 -Conditions c1,c2,c3,c2_eval_only
.\scripts\run_mini4_validation_c1_c2.ps1 -Conditions c1 c2

# 실험 스킵, 체크리스트만
.\scripts\run_mini4_validation_c1_c2.ps1 -SkipRun -All

# 리포트 경로
.\scripts\run_mini4_validation_c1_c2.ps1 -Out reports/mini4_validation_checklist.md
```

## 실행 순서 (스크립트 내부)

1. 선택된 조건 순서대로 `run_experiments --config experiment_mini4_validation_<조건>.yaml` 실행  
   → `results/experiment_mini4_validation_<조건>_proposed/`
2. 각 run에 대해 `structural_error_aggregator` → `derived/metrics/`, `derived/tables/triptych_table.tsv`
3. `validation_checklist_review.py` (C1/C2 필수, C3·C2_eval_only는 있으면 전달)  
   → `reports/mini4_validation_checklist.md` (또는 `--out` 경로)

## 체크리스트 항목 (1–5)

1. **Sanity**: final_output aspect 단일 polarity, aspect_term null 없음, debate final_patch 형태, 스키마 동일
2. **Metric alignment**: polarity_conflict_rate C2≤C1, severe_polarity_error_L3_rate, tuple_agreement_rate
3. **Role separation**: risk_resolution_rate, NO_OVERRIDE 비율, Stage2 호출/수정 폭
4. **Ablation (C1 vs C2 vs C3)**: C3 메모리 단독 효과, C2 토론 순수 기여, memory_used 샘플 중 patch 적용 비율
5. **Memory / OPFB / Gate / after_rep / Gold**: C2만 exposed_to_debate·prompt_injection_chars, OPFB block, injection_trigger_reason, raw/after_rep 컬럼, gold_available·N_gold·tuple_f1_s2

검토 결과는 Yes/No + evidence 형태로 `--out`에 저장됩니다.
