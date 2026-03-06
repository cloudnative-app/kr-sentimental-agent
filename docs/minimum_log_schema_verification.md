# 최소 로그 스키마 수집 가능성 검증

**목적**: 요청된 최소 로그 스키마(A~D)를 현재 파이프라인 산출물로부터 수집·집계할 수 있는지 확인.

---

## 1. 추가 확인 항목별 현황

### 1) sample-level F1 contribution이 남는가

| 상태 | 소스 | 비고 |
|------|------|------|
| ✅ **가능** | triptych (per-sample) | `matches_final_vs_gold`, `gold_n_pairs`, `final_n_pairs` → TP = matches, FP = final_n_pairs - TP, FN = gold_n_pairs - TP. sample_f1 = 2×TP/(2×TP+FP+FN) |
| ✅ | `structural_error_aggregator --export_triptych_table` | `derived_subset/triptych.csv` 또는 `derived/tables/triptych_table.tsv` |
| ⚠️ | ref-pol vs ote-pol | triptych: `matches_final_vs_gold` (ref-pol), `matches_final_vs_gold_otepol` (ote-pol). ref-pol용 sample_f1 계산 가능 |

---

### 2) stage1 vs final tuple set이 둘 다 저장되는가

| 상태 | 소스 | 비고 |
|------|------|------|
| ✅ **가능** | triptych | `stage1_pairs`, `stage1_n_pairs`, `final_pairs`, `final_n_pairs` |
| ✅ | scorecards.jsonl | `runtime.parsed_output.final_result.stage1_tuples`, `final_tuples` |
| ✅ | outputs.jsonl | `final_result.stage1_tuples`, `final_tuples` |

---

### 3) sample별 schema/conflict flag가 남는가

| 상태 | 소스 | 비고 |
|------|------|------|
| ✅ **conflict_flag** | triptych | `polarity_conflict_raw`, `polarity_conflict_after_rep` |
| ⚠️ **schema_valid_flag** | run-level만 | `invalid_ref_rate`는 run aggregate. **per-sample invalid_ref는 없음** |
| ✅ | scorecards | `analysis_flags.conflict_flags` (per-sample) |

**schema_valid_flag per-sample**: 현재 없음. `is_valid_ref(aspect_ref)`를 pred tuple별로 적용하면 도출 가능. **추가 구현 필요**.

---

### 4) aspect_ref 단위 집계가 가능한가

| 상태 | 소스 | 비고 |
|------|------|------|
| ❌ **없음** | — | aspect_ref별 score/rank/rank_shift 산출 로직 없음 |
| ⚠️ | triptych | `gold_pairs`, `final_pairs`는 `(aspect_ref, polarity)` 문자열. 파싱 후 aspect_ref별 TP/FP/FN 집계 가능 |
| ⚠️ | scorecards | `gold_tuples`, `final_tuples`에서 aspect_ref 추출 후 집계 가능 |

**aspect_rank_metrics.csv**: **추가 구현 필요**. gold/pred tuple에서 aspect_ref 추출 → per-ref F1/TP/FP/FN → rank 계산.

---

### 5) 시드별 raw output 또는 normalized tuple output이 남는가

| 상태 | 소스 | 비고 |
|------|------|------|
| ✅ **가능** | outputs.jsonl | `results/<run_id>__seed<N>_proposed/outputs.jsonl` |
| ✅ | scorecards.jsonl | `runtime.parsed_output`에 전체 payload |
| ✅ | triptych | `gold_pairs`, `final_pairs` (정규화된 pair 문자열) |

---

## 2. 최소 로그 스키마별 수집 가능성

### A. run_summary.csv (조건 × 시드)

| 컬럼 | 수집 가능 | 소스 | 비고 |
|------|----------|------|------|
| condition | ✅ | run_id 파싱 (`_infer_condition`) | S0/M0/M1 |
| seed | ✅ | run_id (`__seed42_`) | |
| macro_f1 | ✅ | structural_metrics.csv `tuple_f1_s2_refpol` | |
| micro_f1 | ✅ | `tuple_f1_s2_refpol_micro` | |
| negative_f1 | ⚠️ | subset별 F1 | `s0_m0_subset_effect_report`에 polarity subset. **별도 집계 스크립트 필요** |
| neutral_f1 | ⚠️ | 동일 | |
| schema_validity_rate | ✅ | `invalid_ref_rate` (1 - invalid_ref_rate) | run-level |
| conflict_rate | ✅ | `polarity_conflict_rate` 또는 `conflict_count/n` | |
| fix_rate | ✅ | `fix_rate_refpol` | |
| break_rate | ✅ | `break_rate_refpol` | |
| seed_variance | ✅ | aggregate_seed_metrics `aggregated_mean_std.csv` | mean±std |

---

### B. sample_metrics.csv (조건 × 시드 × sample_id)

| 컬럼 | 수집 가능 | 소스 | 비고 |
|------|----------|------|------|
| sample_id | ✅ | triptych `text_id` 또는 `uid` | |
| condition | ✅ | run_id | |
| seed | ✅ | run_id | |
| sample_f1 | ✅ | triptych `matches_final_vs_gold`, `gold_n_pairs`, `final_n_pairs` | `2×TP/(2×TP+FP+FN)` |
| tp | ✅ | `matches_final_vs_gold` (ref-pol TP) | |
| fp | ✅ | `final_n_pairs - tp` | |
| fn | ✅ | `gold_n_pairs - tp` | |
| schema_valid_flag | ❌ | — | **per-sample 없음. 추가 구현 필요** |
| conflict_flag | ✅ | triptych `polarity_conflict_raw` 또는 `polarity_conflict_after_rep` | |
| duplicate_flag | ⚠️ | — | 정의에 따라 다름. `polarity_conflict`와 유사할 수 있음 |
| implicit_error_flag | ✅ | triptych `implicit_invalid_flag` | |
| difficulty_cell | ✅ | `gold_type` (imp), `gold_n_pairs` (multi) | imp=0/1, multi=0/1 |
| polarity_group | ⚠️ | gold에서 추출 | gold_pairs에서 polarity 분포 추출 필요 |

---

### C. transition_metrics.csv (stage1→final)

| 컬럼 | 수집 가능 | 소스 | 비고 |
|------|----------|------|------|
| condition | ✅ | run_id | |
| seed | ✅ | run_id | |
| sample_id | ✅ | triptych | |
| stage1_tp | ✅ | `matches_stage1_vs_gold` | |
| stage1_fp | ✅ | `stage1_n_pairs - stage1_tp` | |
| stage1_fn | ✅ | `gold_n_pairs - stage1_tp` | |
| final_tp | ✅ | `matches_final_vs_gold` | |
| final_fp | ✅ | `final_n_pairs - final_tp` | |
| final_fn | ✅ | `gold_n_pairs - final_tp` | |
| fix_count | ✅ | triptych `fix_flag` | 샘플당 0/1 (count=flag) |
| break_count | ✅ | triptych `break_flag` | 샘플당 0/1 |
| stage1_conflict_flag | ✅ | `polarity_conflict_raw` | merge 시점 |
| final_conflict_flag | ✅ | `polarity_conflict_after_rep` | |
| stage1_schema_valid_flag | ❌ | — | **per-sample 없음** |
| final_schema_valid_flag | ❌ | — | **per-sample 없음** |

---

### D. aspect_rank_metrics.csv (조건 × 시드 × aspect_ref)

| 컬럼 | 수집 가능 | 소스 | 비고 |
|------|----------|------|------|
| condition | ✅ | run_id | |
| seed | ✅ | run_id | |
| aspect_ref | ⚠️ | gold_tuples/final_tuples 파싱 | |
| score | ❌ | — | **aspect_ref별 F1/TP/FP/FN 집계 로직 없음** |
| rank | ❌ | — | **추가 구현 필요** |
| rank_shift | ❌ | — | **추가 구현 필요** |

**구현 방향**: scorecards/triptych에서 `(aspect_ref, polarity)` 쌍 추출 → aspect_ref별 TP/FP/FN 집계 → F1 → rank. 조건/시드 간 rank_shift 계산.

---

## 3. 수집 경로 요약

| 테이블 | 매 런당 | 추후 집계 | 선행 조건 |
|--------|---------|-----------|-----------|
| **A. run_summary** | structural_metrics.csv + aggregate | aggregated_mean_std.csv | run_pipeline + aggregate_seed_metrics |
| **B. sample_metrics** | triptych | triptych 병합 | `--export_triptych_table` 실행 |
| **C. transition_metrics** | triptych | triptych 병합 | 동일 |
| **D. aspect_rank** | — | — | **신규 스크립트 필요** |

---

## 4. 실행 시점별 수집 방법

### 매 런당 (run_pipeline 직후)

1. **structural_error_aggregator** 실행 (이미 `--with_metrics` 시 수행)
   - `derived/metrics/structural_metrics.csv` → A 테이블 일부
2. **triptych export** (`--export_triptych_table` 추가)
   - `derived_subset/triptych.csv` → B, C 테이블 원천

```powershell
python scripts/structural_error_aggregator.py --input results/<run_id>__seed<N>_proposed/scorecards.jsonl --outdir results/<run_id>__seed<N>_proposed/derived/metrics --profile paper_main --export_triptych_table results/<run_id>__seed<N>_proposed/derived_subset/triptych.csv --triptych_sample_n 0
```

### 추후 집계

1. **aggregate_seed_metrics** → A 테이블 (조건×시드 mean±std)
2. **triptych 병합** → 조건별/시드별 triptych.csv concat → B, C 테이블 생성 스크립트
3. **aspect_rank** → scorecards/triptych 기반 신규 스크립트

---

## 5. 갭 및 권장사항

| 갭 | 영향 | 권장 |
|----|------|------|
| **per-sample schema_valid_flag** | schema 충돌 상관분석 불가 | pred tuple별 `is_valid_ref()` 적용 후 플래그 추가 |
| **aspect_ref 단위 집계** | 결과 타당도/순위 해석 제한 | aspect_ref별 TP/FP/FN 집계 스크립트 신규 작성 |
| **negative_f1, neutral_f1** | polarity subset별 F1 | `s0_m0_subset_effect_report` 로직 재사용 또는 triptych 기반 subset 필터 |
| **duplicate_flag** | 정의 정립 필요 | polarity_conflict와 동일/유사 여부 확인 후 매핑 |

---

## 6. triptych 컬럼 → 스키마 매핑

| 최소 스키마 컬럼 | triptych 컬럼 |
|------------------|---------------|
| sample_id | text_id, uid |
| sample_f1 | matches_final_vs_gold, gold_n_pairs, final_n_pairs (계산) |
| tp | matches_final_vs_gold |
| fp | final_n_pairs - matches_final_vs_gold |
| fn | gold_n_pairs - matches_final_vs_gold |
| conflict_flag | polarity_conflict_raw |
| implicit_error_flag | implicit_invalid_flag |
| difficulty_cell (imp) | gold_type == "implicit" → 1 |
| difficulty_cell (multi) | gold_n_pairs > 1 → 1 |
| fix_flag | fix_flag |
| break_flag | break_flag |
| stage1_tp | matches_stage1_vs_gold |
| stage1_fp | stage1_n_pairs - matches_stage1_vs_gold |
| stage1_fn | gold_n_pairs - matches_stage1_vs_gold |

---

## 7. 구현 완료 (최소 작업지시서)

### 작업 1: triptych export 강제
- `run_pipeline.py --with_metrics` 시 `structural_error_aggregator`에 `--export_triptych_table`, `--triptych_sample_n 0` 자동 추가
- 출력: `results/<run_id>_proposed/derived_subset/triptych.csv`
- `aggregate_seed_metrics.py`의 `ensure_structural_metrics`에도 동일 옵션 추가

### 작업 2: per-sample schema_valid_flag
- `structural_error_aggregator._triptych_row`에 `stage1_schema_valid_flag`, `final_schema_valid_flag` 추가
- 규칙: pred tuple 중 하나라도 invalid ref → 0, 모두 valid → 1

### 작업 3~5: A/B/C 테이블 export 스크립트
| 스크립트 | 출력 | 입력 |
|----------|------|------|
| `scripts/export_run_summary.py` | `analysis_exports/run_summary.csv` | 각 run의 `structural_metrics.csv` |
| `scripts/export_sample_metrics.py` | `analysis_exports/sample_metrics.csv` | 각 run의 `triptych.csv` |
| `scripts/export_transition_metrics.py` | `analysis_exports/transition_metrics.csv` | 각 run의 `triptych.csv` |

**실행 예**:
```powershell
# run_dirs로 지정
python scripts/export_run_summary.py --run_dirs results/final_260306_s0__seed42_proposed,results/final_260306_s0__seed123_proposed,...

# base_run_id + seeds
python scripts/export_run_summary.py --base_run_id final_260306_s0 --seeds 42,123,456,789,1024 --mode proposed
```
