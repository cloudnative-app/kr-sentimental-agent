# Paper Metrics Spec (Paper Metric Realignment Freeze)

CR 브랜치 논문용 메트릭 테이블 정의. **3-level hierarchy** 고정.

**용어 정렬**:
- aspect_ref → entity#attribute (표기 병기)
- ref-pol → entity#attribute–polarity
- ote-pol → OTE–polarity

---

## 1. 개요

| 산출물 | 경로 | 생성 스크립트 |
|--------|------|---------------|
| paper_metrics_aggregated.md | `results/<run_id>_paper/paper_metrics_aggregated.md` | export_paper_metrics_aggregated.py |
| aggregated_mean_std.csv | `results/<run_id>_aggregated/aggregated_mean_std.csv` | aggregate_seed_metrics.py |
| irr_run_summary.json | `results/<run_id>__seed<N>_proposed/irr/irr_run_summary.json` | compute_irr.py |

**데이터 흐름**:
```
structural_metrics.csv (시드별) → aggregate_seed_metrics → aggregated_mean_std.csv
outputs.jsonl (시드별)         → export 시 --run-dirs → conflict_detection_rate, AAR 등
irr/irr_run_summary.json       → export 시 --run-dirs → IRR 메트릭
```

---

## 2. Paper 테이블 구조 (3-Level Hierarchy)

| Level | 정의 | Table |
|-------|------|-------|
| **Level 1: Surface** | OTE–polarity (micro-level ABSA unit) | Table 1 |
| **Level 2: Projection** | entity#attribute–polarity mapping into taxonomy | Table 2 |
| **Level 3: Error Control** | change in error state transition | Table 3A/B/C |

---

### Table 1 — Surface Measurement (OTE–polarity)

| Paper 메트릭 | aggregator 컬럼 | 공식/의미 |
|--------------|-----------------|-----------|
| tuple_f1_s1_otepol | tuple_f1_s1_otepol | `mean(F1(gold, stage1))` (aspect_term, polarity) |
| tuple_f1_s2_otepol | tuple_f1_s2_otepol | `mean(F1(gold, final))` |
| delta_f1_otepol | delta_f1_otepol | tuple_f1_s2_otepol − tuple_f1_s1_otepol |
| tuple_f1_explicit | tuple_f1_explicit | explicit-only (aspect_term, polarity) F1 |

**Note.** Surface Measurement = OTE–polarity (micro-level ABSA unit). Unit: mean(F1(gold_i, pred_i)) per sample. Key: tuples_to_pairs / match_by_aspect_ref=False.

---

### Table 2 — Schema Projection (entity#attribute–polarity)

| Paper 메트릭 | aggregator 컬럼 | 공식/의미 |
|--------------|-----------------|-----------|
| tuple_f1_s1_refpol | tuple_f1_s1_refpol | `mean(F1(gold, stage1))` (aspect_ref, polarity) |
| tuple_f1_s2_refpol | tuple_f1_s2_refpol | `mean(F1(gold, final))` |
| delta_f1_refpol | delta_f1_refpol | tuple_f1_s2_refpol − tuple_f1_s1_refpol |
| ref_fill_rate_s2 | ref_fill_rate_s2 | stage2 aspect_ref (entity#attribute) 채움 비율 |
| ref_coverage_rate_s2 | ref_coverage_rate_s2 | stage2 gold ref coverage |

**Note.** Schema Projection = entity#attribute–polarity mapping into taxonomy. aspect_ref (entity#attribute) is schema label space. Key: tuples_to_ref_pairs.

---

### Table 3 — Error Control

#### 3A Error Reduction

| Paper 메트릭 | aggregator 컬럼 | 공식/의미 |
|--------------|-----------------|-----------|
| fix_rate_refpol | fix_rate_refpol | n_fix / (n_fix + n_still); S1 wrong → S2 right |
| break_rate_refpol | break_rate_refpol | n_break / (n_break + n_keep); S1 right → S2 wrong |
| net_gain_refpol | net_gain_refpol | (n_fix − n_break) / N |
| cda | cda | **CDA** = n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed). Gold-based. |

**Note.** Error Control = change in error state transition. fix_rate: S1 wrong → S2 right. break_rate: S1 right → S2 wrong. CDA = n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed). Gold-based.

#### 3B Error Detection

| Paper 메트릭 | 소스 | 공식/의미 |
|--------------|------|-----------|
| conflict_detection_rate | outputs.jsonl (--run-dirs) | n(samples with ≥1 conflict flag) / N |
| aar_majority_rate | structural_error_aggregator | **AAR** = n(majority agreement in review actions) / total_tuples |

**Note.** Error Detection. conflict_detection_rate: samples with ≥1 conflict flag. AAR = n(majority agreement in review actions) / total_tuples. Uses IRR action labels (KEEP/DROP/FLIP_*/MERGE/OTHER).

#### 3C Stability

| Paper 메트릭 | IRR JSON 키 | 의미 |
|--------------|-------------|------|
| meas_fleiss_kappa | mean_fleiss_measurement | Measurement IRR: Fleiss' κ (POS/NEG/NEU/DROP) |
| meas_cohen_kappa_mean | mean_kappa_measurement | Cohen's κ 평균 |
| meas_perfect_agreement_rate | mean_perfect_agreement_measurement | 완전 일치 비율 |
| meas_majority_agreement_rate | mean_majority_agreement_measurement | 다수 일치 비율 |
| --- Process IRR (aux) --- | (구분자) | |
| irr_fleiss_kappa | mean_fleiss | Process IRR (aux): Fleiss' κ (KEEP/DROP/FLIP_*/MERGE/OTHER) |
| irr_cohen_kappa_mean | mean_kappa | Cohen's κ 평균 |
| irr_perfect_agreement_rate | mean_perfect_agreement | 완전 일치 비율 |
| irr_majority_agreement_rate | mean_majority_agreement | 다수 일치 비율 |

**Note.** Stability. Measurement IRR: final decision (POS/NEG/NEU/DROP). Process IRR (aux): action labels (KEEP/DROP/FLIP_*/MERGE/OTHER).

---

### Appendix — Diagnostics (삭제하지 않음)

attr-pol 진단, invalid_* grounding 진단, implicit_* 메트릭. 재현성용 보존.

| Paper 메트릭 | aggregator 컬럼 |
|--------------|-----------------|
| tuple_f1_s1_attrpol, tuple_f1_s2_attrpol, delta_f1_attrpol | attr-pol |
| fix_rate_attrpol, break_rate_attrpol, net_gain_attrpol | |
| invalid_target_rate, invalid_language_rate, invalid_ref_rate | invalid_* grounding |
| implicit_invalid_pred_rate, implicit_coverage_fail_rate, implicit_null_fail_rate, implicit_parse_fail_rate | implicit_* |
| tuple_f1_s2_otepol_explicit_only, polarity_conflict_rate, N_agg_fallback_used | 기타 진단 |

**Note.** Appendix: attr-pol diagnostics, invalid_* grounding, implicit_* metrics. Kept for reproducibility; not in main paper tables.

---

## 3. CDA / AAR 정의 (구현)

### CDA (Correction Directional Accuracy)

**파일**: `scripts/structural_error_aggregator.py` — `compute_stage2_correction_metrics`

```
CDA = n(S1 incorrect AND S2 correct) / n(S1 incorrect AND S2 changed)
```

Gold 기준. S1=stage1, S2=final. 분모: S1이 틀렸고 S2에서 변경이 발생한 샘플 수.

### AAR (Action Agreement Rate)

**파일**: `scripts/structural_error_aggregator.py` — `compute_aar_cda_metrics`

```
AAR = n(majority agreement in review actions) / total_tuples
```

기존 IRR 계산 데이터 활용. 3명 rater 중 2명 이상 동일 라벨 = majority agreement.

---

## 4. Lookup 우선순위 (export_paper_metrics_aggregated.py)

1. **extra_metrics**: `--run-dirs` 지정 시 outputs.jsonl + irr/irr_run_summary.json에서 계산
2. **agg**: aggregated_mean_std.csv (aggregator → aggregate_seed_metrics)
3. **paper_to_agg**: AGG_TO_PAPER 역매핑 (paper 이름 → agg 컬럼명)
4. **PAPER_METRICS_CORE_FALLBACK**: refpol/otepol 없을 때 비접미사 키 사용

---

## 5. 출력 형식

- **mean ± std**: 시드 2개 이상일 때
- **mean**: 시드 1개 또는 std 없을 때
- **N/A**: 값 없음, NaN, 빈 문자열

---

## 6. 실행 예시

```powershell
python scripts/export_paper_metrics_aggregated.py `
  --agg-path results/cr_n50_m0_v5_aggregated/aggregated_mean_std.csv `
  --run-dirs results/cr_n50_m0_v5__seed3_proposed results/cr_n50_m0_v5__seed123_proposed results/cr_n50_m0_v5__seed456_proposed `
  --out-dir results/cr_n50_m0_v5_paper
```

`--run-dirs` 없이 실행 시: aggregated_mean_std.csv만 사용. conflict_detection_rate, AAR 등은 agg에서 수집 (AAR), outputs 기반(conflict_detection_rate)은 N/A.

---

## 7. 참고

- `docs/cr_branch_metrics_spec.md` — CR 메트릭 전체 명세
- `docs/f1_metrics_and_scoring_examples.md` — F1 메트릭 및 gold–pred 쌍 예시
- `scripts/export_paper_metrics_aggregated.py` — Paper export 구현
- `scripts/structural_error_aggregator.py` — CANONICAL_METRIC_KEYS, CDA, AAR 산출
- `scripts/compute_irr.py` — IRR 산출 (Process / Measurement)
