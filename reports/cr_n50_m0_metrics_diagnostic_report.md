# CR v1 Metrics Diagnostic Report

**Run**: cr_n50_m0 | seeds: ['42', '123', '456']

## 1. conflict_detection_rate (raw from outputs.jsonl)

**정의**: `analysis_flags.conflict_flags` 비어있지 않은 샘플 비율 (Merge 시점, pre-review)
**export_paper_metrics_aggregated에서 N/A**: aggregated_mean_std.csv는 structural_error_aggregator 산출만 포함. aggregator는 conflict_detection_rate를 계산하지 않음. outputs.jsonl에서 별도 계산 필요.

- **seed 42**: 5/50 = 0.1000 (5 samples with ≥1 conflict_flag)
- **seed 123**: 4/50 = 0.0800 (4 samples with ≥1 conflict_flag)
- **seed 456**: 3/50 = 0.0600 (3 samples with ≥1 conflict_flag)
- **평균 (seeds)**: 0.0800

## 2. pre_conflict vs no_conflict 비교

| seed | pre_conflict (n) | no_conflict (n) | pre_conflict % |
|------|------------------|----------------|----------------|
| 42 | 5 | 45 | 10.0% |
| 123 | 4 | 46 | 8.0% |
| 456 | 3 | 47 | 6.0% |

## 3. IRR (Inter-Rater Reliability)

**seed 42**:
- Mean Cohen's κ (A-B, A-C, B-C): 0.1292
- Fleiss' κ: -0.1723
- Perfect agreement: 0.2240
- conflict vs no_conflict: {'has_conflict': 5, 'no_conflict': 45}

**seed 123**:
- Mean Cohen's κ (A-B, A-C, B-C): 0.1578
- Fleiss' κ: -0.1748
- Perfect agreement: 0.2278
- conflict vs no_conflict: {'has_conflict': 4, 'no_conflict': 46}

**seed 456**:
- Mean Cohen's κ (A-B, A-C, B-C): 0.1400
- Fleiss' κ: -0.1473
- Perfect agreement: 0.2351
- conflict vs no_conflict: {'has_conflict': 3, 'no_conflict': 47}


## 4. Stage1 baseline seed variance (tuple_f1_s1)

| seed | tuple_f1_s1 | triplet_f1_s1 |
|------|-------------|---------------|
| 42 | 0.4912 | 0.4912 |
| 123 | 0.4804 | 0.4804 |
| 456 | 0.4910 | 0.4910 |

tuple_f1_s1: mean=0.4875, std=0.0050

## 5. polarity_conflict_rate = 0.0000 해석

**에이전트 vs 어그리게이터 차이**:
- **conflict_flags** (Merge 시점): P-NEG/P-IMP/P-LIT 합친 후 동일 aspect_term에 서로 다른 polarity → **pre-review**
- **polarity_conflict_rate** (structural_error_aggregator): **final_tuples (post-review)** 기준. Arbiter 적용 후 동일 aspect에 polarity 충돌 남은 샘플 비율
- **해석**: 0.0 = Arbiter가 충돌을 해소한 후 최종 결과에는 남은 충돌이 없음 (설계상 의도된 동작)

**어그리게이터는 최종 결과(final_tuples)를 봄** — `_get_final_tuples_raw(record)` → `has_polarity_conflict_raw`, `has_polarity_conflict_after_representative`

## 6. review_intervention_rate, arb_intervention_rate 공식

### review_intervention_rate (aggregator: review_action_rate)
- **공식**: `n_review_action / N`
- **정의**: `_cr_has_review_actions(r)` = `analysis_flags.review_actions`에 ≥1개 항목이 있는 샘플
- **주의**: review_actions는 **A/B/C 각각의 합** (Arbiter 합의 전). CR 프로토콜상 A/B/C가 모두 출력하므로 **항목 ≥1**이면 True

### arb_intervention_rate (aggregator)
- **공식**: `n_arb_intervention / N`
- **정의**: `_cr_has_arb_intervention(r)` = `analysis_flags.arb_actions`에 ≥1개 항목이 있는 샘플
- **CR 설계**: Arbiter는 항상 A/B/C actions를 합쳐서 최종 arb_actions를 출력. **액션이 있으면** (KEEP 포함) arb_actions 리스트에 ≥1개
- **1.0 = 모든 샘플에서 Arbiter가 최소 1개 액션 출력** — 설계상 튜플이 있으면 Arbiter가 각 tuple_id에 대해 KEEP/FLIP/DROP 등 처리

## 7. Sample-level action counts (seed 42)

- n_review_actions ≥ 1: 50/50
- n_arb_actions ≥ 1: 50/50
- n_conflict_flags ≥ 1: 5/50

Arbiter action_type distribution (all samples):
- MERGE: 46
- DROP: 40
- KEEP: 22
- FLAG: 5
- FLIP: 2
