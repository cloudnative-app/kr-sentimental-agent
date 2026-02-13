# Real100 c1_1 / c2_1 최종 정합성 점검

aggregator로 derived/metrics, derived/diagnostics, derived/tables를 다시 생성한 뒤 아래 6개 항목으로 점검.

---

## 1) Fail-fast 2종 + stage1 Sanity Check

**볼 것**
- gold→gold F1 = 1.0
- stage1→stage1 F1 = 1.0 (권장 추가)
- final→final F1 = 1.0

**판정**: 하나라도 1.0이 아니면 → 추출/정규화/매칭 경로가 서로 다름 → 다른 결과는 전부 신뢰 불가.

**실행 결과 (real100 c1_1, c2_1)**  
- Sanity check passed: gold→gold, stage1→stage1, and final→final F1=1. ✅

---

## 2) tuple_source_coverage.csv (추출 경로 커버리지)

**볼 것**
- final_tuple_source가 inputs.aspect_sentiments로 떨어지는 비율
- stage1_tuple_source가 trace_atsa fallback 비율
- gold 누락 비율 (gold_tuple_source empty)

**판정**: fallback 비율이 높으면 → 파이프라인 저장(기록) 누락 또는 스키마 불일치.  
final이 inputs로 많이 떨어지면 → “최종 결과”가 scorecard에 안정적으로 기록되지 않음.

| run | final_fallback_aspect_sentiments_rate | stage1_fallback_trace_atsa_rate | gold_missing_rate |
|-----|--------------------------------------|----------------------------------|--------------------|
| c1_1 | 0.05 (5%) | 0.04 (4%) | 0 |
| c2_1 | 0.04 (4%) | 0.03 (3%) | 0 |

→ 설명 가능한 수준 (소수 fallback). ✅

---

## 3) inconsistency_flags.tsv (모순 4종)

**플래그**
1. delta_pairs_count != 0 인데 stage1_to_final_changed == 0  
2. stage1_to_final_changed == 1 인데 stage_delta.changed == 0  
3. moderator_selected_stage == stage2 인데 guided_change==0 & unguided_drift==0  
4. risk_resolution==1 인데 stage2_structural_risk==1 (정의: resolution ⇒ S2 clear)

**판정**: 1건이라도 있으면 → 표/집계/scorecard 계산 기준 불일치.

| run | inconsistency_flags 건수 | 비고 |
|-----|---------------------------|------|
| c1_1 | 76 | 아래 4유형별 건수 참고 |
| c2_1 | 3 | flag_stage2_no_guided_unguided |

**c1_1 76건 4유형별 내역**

| 유형 | 플래그 | 건수 | 의미 |
|------|--------|------|------|
| A | flag_delta_nonzero_changed_zero | 0 | delta_pairs≠0 인데 stage1_to_final_changed=0 |
| B | flag_changed_one_delta_zero | **71** | stage1_to_final_changed=1 인데 stage_delta.changed=0 (scorecard에 changed 미기록) |
| C | flag_stage2_no_guided_unguided | **5** | moderator_selected_stage=stage2 인데 guided=0 & unguided=0 |
| D | flag_risk_resolution_but_stage2_risk | 0 | risk_resolution=1 인데 stage2_structural_risk=1 |

→ **대부분 B(71건)**: triptych는 pairs 비교로 changed=1인데 scorecard의 stage_delta.changed가 False/0으로 저장됨.  
→ **C(5건)**: stage2 선택됐는데 변화 사유(guided/unguided)가 비어 있음.

→ **NO-GO** (모순 제거 전까지 정합성 미통과).

---

## 4) structural_metrics.csv (새 컬럼 정합성)

**볼 것**
- N_gold_total_pairs == N_gold_explicit_pairs + N_gold_implicit_pairs (항상 성립)
- tuple_f1_s2_explicit_only 존재 + tuple_f1_s2_overall과 관계 (대개 explicit_only ≤ overall 가능; implicit 비중 높으면 overall이 더 높을 수 있음)

**판정**: 분해 합이 안 맞으면 → split 로직/정규화 어긋남.  
explicit_only가 overall보다 대폭 낮으면 → explicit 분리 기준 또는 gold 대부분 implicit인데 분리 미반영 점검.

| run | N_gold_total_pairs | N_gold_explicit_pairs | N_gold_implicit_pairs | 합 일치 |
|-----|--------------------|------------------------|------------------------|--------|
| c1_1 | 106 | 54 | 52 | 54+52=106 ✅ |
| c2_1 | 106 | 54 | 52 | 54+52=106 ✅ |

---

## 5) triptych_table.tsv (10샘플 스팟체크)

**샘플링 규칙**: 아래 5종에서 각각 2개씩만 확인.

1. gold_type=implicit 인 행  
2. gold_type=explicit & matches_final_vs_gold > 0 (맞춘 케이스)  
3. gold_type=explicit & matches_final_vs_gold == 0 (못 맞춘 케이스)  
4. stage1_to_final_changed=1 인 행  
5. risk_flagged=1 인 행  

**눈으로 확인**
- implicit 행이 explicit F1에 끼지 않는 구조인지 (f1_eval_note 등)
- changed=1이면 실제로 pairs가 바뀌었는지
- guided/unguided가 “변화 이유”와 맞는지
- moderator_selected_stage / moderator_rules가 pairs 변화와 논리적으로 맞는지

**실행**: `python scripts/triptych_spot_check.py <run_dir>/derived/tables/triptych_table.tsv -o <run_dir>/derived/diagnostics/triptych_spot_check.tsv -n 2`  
→ 위 5종×2건 행을 `_spot_category` 컬럼과 함께 TSV로 추출. 사람이 해당 행만 열어 검토.

---

## 6) metric_report.html (리포트 UI 정합성)

**볼 것**
- HTML “Overall” 테이블이 structural_metrics.csv 새 컬럼을 반영하는지  
- polarity_conflict_rate_raw / polarity_conflict_rate_after_rep 둘 다 표시되는지  
- explicit-only F1이 “primary”로 표기되는지  

**판정**: 리포트가 CSV와 다르면 → build_metric_report가 오래된 키 참조 또는 CSV 로딩 우선순위 문제.

---

## 최종 GO / NO-GO (한 줄 규칙)

- Sanity check 통과 ✅  
- inconsistency_flags **0건** → 현재 c1_1(76건), c2_1(3건) → **NO-GO**  
- coverage fallback 비율이 설명 가능한 수준 ✅  
- N_gold_total_pairs = explicit_pairs + implicit_pairs ✅  

**→ 위 4개 중 inconsistency_flags 0건이 아니면 정합성 최종 통과로 선언하지 않음.**  
모순 원인(scorecard.stage_delta 주입/정의, triptych 계산) 정리 후 재점검 필요.
