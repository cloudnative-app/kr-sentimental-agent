# S0 vs M0 subset effect report (seed 42, n=601)

**집계 방식**: pair-level micro F1 (TP=matches, FN=gold−matches, FP=final−matches, F1=2PR/(P+R)). Subset은 동일 방식으로 TP/FP/FN 합산 후 F1 계산. Partition subset(implicit+explicit)은 weighted recompute로 전체와 일치 검증.

## 0. Overall pair-level micro F1

| Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |
|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|
| S0 | 601 | 636 | 271 | 442 | 365 | 0.4018 | — |
| M0 | 601 | 636 | 349 | 1027 | 287 | 0.3469 | **-0.0549** |

## 1. Implicit vs Explicit

| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |
|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|
| Implicit (gold aspect_term empty) | S0 | 299 | 323 | 127 | 224 | 196 | 0.3769 | — |
| | M0 | 299 | 323 | 195 | 526 | 128 | 0.3736 | **-0.0033** |
| Explicit | S0 | 302 | 313 | 144 | 218 | 169 | 0.4267 | — |
| | M0 | 302 | 313 | 154 | 501 | 159 | 0.3182 | **-0.1085** |

*Weighted recompute (implicit+explicit → all): S0 F1=0.4018 (vs overall 0.4018), M0 F1=0.3469 (vs overall 0.3469)*

## 2. Negation/Contrast 포함 vs 미포함

| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |
|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|
| Negation/Contrast 포함 (lexical cue) | S0 | 117 | 125 | 62 | 117 | 63 | 0.4079 | — |
| | M0 | 117 | 125 | 71 | 258 | 54 | 0.3128 | **-0.0951** |
| Negation 미포함 | S0 | 484 | 511 | 209 | 325 | 302 | 0.4000 | — |
| | M0 | 484 | 511 | 278 | 769 | 233 | 0.3569 | **-0.0431** |

*Weighted recompute (negation+non_negation → all): S0 F1=0.4018, M0 F1=0.3469*

## 3. Multi-aspect vs Single-aspect

| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) | Δ (M0−S0) |
|--------|-----------|-----------|---------|-----|-----|-----|-----------------|-----------|
| Single-aspect (gold_n_pairs=1) | S0 | 571 | 571 | 235 | 412 | 336 | 0.3859 | — |
| | M0 | 571 | 571 | 314 | 940 | 257 | 0.3441 | **-0.0418** |
| Multi-aspect (gold_n_pairs>1) | S0 | 30 | 65 | 36 | 30 | 29 | 0.5496 | — |
| | M0 | 30 | 65 | 35 | 87 | 30 | 0.3743 | **-0.1753** |

*Weighted recompute (single+multi_aspect → all): S0 F1=0.4018, M0 F1=0.3469*

## 4. Conflict_flag 발생 vs 비발생 (M0 only, S0 비교 불가)

*S0는 단일 에이전트이므로 conflict_flag 없음. M0만 집계.*

| Subset | Condition | n_samples | n_pairs | TP | FP | FN | ACSA-F1 (micro) |
|--------|-----------|-----------|---------|-----|-----|-----|-----------------|
| Conflict 발생 | M0 | 130 | 148 | 84 | 318 | 64 | 0.3055 |
| Conflict 비발생 | M0 | 471 | 488 | 265 | 709 | 223 | 0.3625 |

*동일 샘플(no_conflict)에 대해 S0 vs M0: S0 F1=0.3996, M0 F1=0.3625, Δ=-0.0371*