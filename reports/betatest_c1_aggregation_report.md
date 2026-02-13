# Betatest C1 시드 42·123 어그리게이션·체크리스트·머징 결과 보고서

## 1. 실행 요약

| 항목 | 내용 |
|------|------|
| 조건 | Betatest C1 (no memory, T1 override) |
| 시드 | 42, 123 |
| 데이터 | betatest_n50 (valid 50건, seed=99 추출) |
| 런 디렉터리 | `results/betatest_c1__seed42_proposed`, `results/betatest_c1__seed123_proposed` |

---

## 2. 어그리게이터 분석 (시드별 → 평균±표준편차)

### 2.1 핵심 메트릭 (Mean ± Std)

| Metric | Mean | Std | 비고 |
|--------|------|-----|------|
| n | 50.0 | 0.0 | 샘플 수 |
| N_gold_total_pairs | 51.0 | 0.0 | 골드 튜플 총 수 |
| N_pred_final_tuples | 48.0 | 0.0 | 최종 예측 튜플 |
| N_pred_final_aspects | 0.0 | 0.0 | fallback 사용 시 0 (aggregator 경고) |
| tuple_f1_s1 | 0.3814 | 0.0100 | Stage1 튜플 F1 |
| tuple_f1_s2 | 0.5063 | 0.0031 | Stage2(최종) 튜플 F1 |
| triplet_f1_s1 | 0.3814 | 0.0100 | |
| triplet_f1_s2 | 0.5063 | 0.0031 | |
| delta_f1 | 0.1249 | 0.0131 | Stage1→2 F1 향상 |
| fix_rate | 0.0738 | 0.0238 | |
| break_rate | 0.0000 | 0.0000 | |
| net_gain | 0.0600 | 0.0200 | |
| changed_samples_rate | 0.6500 | 0.0100 | 65% 샘플에서 튜플 변경 |
| guided_change_rate | 0.1378 | 0.0440 | |
| unguided_drift_rate | 0.5600 | 0.0200 | |
| debate_override_applied | 4.0 | 2.0 | T1 적용 건수 |
| override_hint_invalid_rate | 0.9535 | 0.0116 | 힌트 무효 비율 높음 |
| tuple_agreement_rate | N/A | | 단일 시드 쌍만 있어 n_trials=1 |

### 2.2 산출물 경로

- **aggregated_mean_std**: `results/betatest_c1_aggregated/aggregated_mean_std.csv`, `.md`
- **integrated_report**: `results/betatest_c1_aggregated/integrated_report.md`

---

## 3. 체크리스트 분석 (consistency_checklist)

### 3.1 seed42

| 항목 | 결과 | 비고 |
|------|------|------|
| source | OK | run_experiments |
| gold | OK | gold_injected, 50 rows with inputs.gold_tuples |
| tuple path | OK | N_pred_final_tuples=48, N_pred_used=120 |
| **sanity** | **NO-GO** | gold→gold F1=0.0 (기대 1.0) |
| inconsistency_flags | -- | aggregator --diagnostics_dir 필요 |
| triptych | -- | aggregator --export_triptych_table 필요 |

### 3.2 seed123

| 항목 | 결과 | 비고 |
|------|------|------|
| source | OK | run_experiments |
| gold | OK | gold_injected, 50 rows with inputs.gold_tuples |
| tuple path | OK | N_pred_final_tuples=48, N_pred_used=120 |
| **sanity** | **NO-GO** | gold→gold F1=0.0 (기대 1.0) |
| inconsistency_flags | -- | aggregator --diagnostics_dir 필요 |
| triptych | -- | aggregator --export_triptych_table 필요 |

### 3.3 sanity 실패 원인 (gold→gold F1=0)

- gold_tuples와 self-match 시 F1이 0 → 골드 형식과 평가기 매칭 로직 불일치 가능성.
- betatest_n50 valid.gold.jsonl의 `gold_tuples` 포맷(AspectTermV1_1 등)과 `consistency_checklist`의 gold 추출 방식 검토 필요.

---

## 4. 머징 결과

### 4.1 merged_scorecards

- **경로**: `results/betatest_c1_aggregated/merged_scorecards.jsonl`
- **행 수**: 100 (seed42 50행 + seed123 50행)

### 4.2 merged metrics (structural_error_aggregator on merged)

- **경로**: `results/betatest_c1_aggregated/merged_metrics/`
- **tuple_agreement_rate**: 0.62 (시드 간 튜플 일치율)
- **참고**: structural_error_aggregator는 final_pred_source_aspects_path_unused_flag (Info flag)만 기록하며 exit 없음. merged_metrics는 별도 run으로 생성됨.

### 4.3 metric_report.html (머지 런)

- **경로**: `reports/merged_run_betatest_c1/metric_report.html`

---

## 5. 알려진 이슈

1. **final_pred_source_aspects_path_unused_flag=True**: N_pred_final_aspects=0 with n>0 — scorecard에 final_aspects 미포함 또는 fallback 경로만 사용. Info flag (fail 아님).
2. **gold→gold F1=0**: 수정됨. 원인: gold에 aspect_ref·aspect_term 둘 다 있을 때, sanity 검사가 `match_by_aspect_ref=True`로 pred 쪽에 (aspect_ref, polarity)를 사용 → gold의 (aspect_term, polarity)와 키 불일치. `run_sanity_checks`에서 gold→gold 검사 시 `match_by_aspect_ref=False` 적용. 상세: `reports/betatest_c1_gold_sanity_diagnosis.md`.
3. **override_hint_invalid_rate≈0.95**: T1 조건에서 힌트 대부분이 invalid로 처리됨.
