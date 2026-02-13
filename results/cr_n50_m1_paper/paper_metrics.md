# Paper Metrics Export

## Table 1. Overall Outcome (RQ1)

| run | tuple_f1_s1 | tuple_f1_s2 | delta_f1 | fix_rate | break_rate | net_gain | implicit_invalid_pred_rate | polarity_conflict_rate | N_agg_fallback_used |
|---|---|---|---|---|---|---|---|---|---|
| cr_n50_m1__seed123_proposed | 0.5105 | 0.6207 | 0.1102 | 0.2381 | 0.0000 | 0.2000 | 0.0000 | 0.0000 | 0.0000 |
| cr_n50_m1__seed42_proposed | 0.4920 | 0.6064 | 0.1144 | 0.2791 | 0.1429 | 0.2200 | 0.0000 | 0.0000 | 0.0000 |
| cr_n50_m1__seed456_proposed | 0.4866 | 0.6808 | 0.1942 | 0.3571 | 0.0000 | 0.3030 | 0.0000 | 0.0000 | 0.0000 |

## Table 2. Reliability / Stability (RQ2)

| run | irr_fleiss_kappa | irr_cohen_kappa_mean | irr_perfect_agreement_rate | irr_majority_agreement_rate |
|---|---|---|---|---|
| cr_n50_m1__seed123_proposed | -0.1411 | 0.1404 | 0.2756 | 0.3976 |
| cr_n50_m1__seed42_proposed | -0.1324 | 0.1462 | 0.2897 | 0.4286 |
| cr_n50_m1__seed456_proposed | -0.1859 | 0.1150 | 0.2391 | 0.5272 |

## Table 3. Process Evidence (CR)

| run | conflict_detection_rate | pre_to_post_change_rate | review_nontrivial_action_rate | arb_nonkeep_rate |
|---|---|---|---|---|
| cr_n50_m1__seed123_proposed | 0.0800 | 0.4200 | 0.9800 | 0.9800 |
| cr_n50_m1__seed42_proposed | 0.1200 | 0.5000 | 0.9800 | 0.9800 |
| cr_n50_m1__seed456_proposed | 0.0303 | 0.4242 | 1.0000 | 1.0000 |

---

*Note: validator/risk 계열(validator_clear_rate 등)은 CR에서 0 반환. 논문 표에서는 제외 권장.*
