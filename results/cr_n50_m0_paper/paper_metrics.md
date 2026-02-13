# Paper Metrics Export

## Table 1. Overall Outcome (RQ1)

| run | tuple_f1_s1 | tuple_f1_s2 | delta_f1 | fix_rate | break_rate | net_gain | implicit_invalid_pred_rate | polarity_conflict_rate | N_agg_fallback_used |
|---|---|---|---|---|---|---|---|---|---|
| cr_n50_m0__seed123_proposed | 0.4804 | 0.5950 | 0.1146 | 0.2143 | 0.0000 | 0.1800 | 0.0000 | 0.0000 | 0.0000 |
| cr_n50_m0__seed42_proposed | 0.4912 | 0.6173 | 0.1261 | 0.2558 | 0.0000 | 0.2200 | 0.0000 | 0.0000 | 0.0000 |
| cr_n50_m0__seed456_proposed | 0.4910 | 0.5980 | 0.1070 | 0.2381 | 0.0000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 |

## Table 2. Reliability / Stability (RQ2)

| run | irr_fleiss_kappa | irr_cohen_kappa_mean | irr_perfect_agreement_rate | irr_majority_agreement_rate |
|---|---|---|---|---|
| cr_n50_m0__seed123_proposed | -0.1748 | 0.1578 | 0.2278 | 0.5560 |
| cr_n50_m0__seed42_proposed | -0.1723 | 0.1292 | 0.2240 | 0.4640 |
| cr_n50_m0__seed456_proposed | -0.1473 | 0.1400 | 0.2351 | 0.4781 |

## Table 3. Process Evidence (CR)

| run | conflict_detection_rate | pre_to_post_change_rate | review_nontrivial_action_rate | arb_nonkeep_rate |
|---|---|---|---|---|
| cr_n50_m0__seed123_proposed | 0.0800 | 0.3600 | 0.9800 | 0.9800 |
| cr_n50_m0__seed42_proposed | 0.1000 | 0.4400 | 0.9800 | 0.9800 |
| cr_n50_m0__seed456_proposed | 0.0600 | 0.3800 | 0.9800 | 0.9800 |

---

*Note: validator/risk 계열(validator_clear_rate 등)은 CR에서 0 반환. 논문 표에서는 제외 권장.*
