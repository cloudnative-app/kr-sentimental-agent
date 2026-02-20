# CR v2 Subset Partition 정의

## Subset Partition Verification

**Subset partitions are mutually exclusive and exhaustive.** Weighted recomputation across subsets exactly matches overall micro-F1.

---

## 서브셋 생성 기준

### 1. Implicit vs Explicit (난이도 기반, Partition)

| Subset | 기준 | 설명 |
|--------|------|------|
| **Implicit** | `gold_type == "implicit"` | Gold에서 aspect_term이 비어 있는 (aspect_ref, polarity) 쌍만 있는 샘플 |
| **Explicit** | `gold_type == "explicit"` | Gold에서 aspect_term이 비어 있지 않은 샘플 |

- **Partition**: Implicit ∪ Explicit = 전체. 샘플은 둘 중 하나에만 속함.
- **검증**: implicit TP+FP+FN + explicit TP+FP+FN = overall TP+FP+FN → weighted micro-F1 일치

### 2. Negation/Contrast vs Non-negation

| Subset | 기준 | 설명 |
|--------|------|------|
| **Negation** | `has_negation == True` | 입력 텍스트에 부정/대조 어휘 포함 (lexical cue: 안, 못, 않, 없, 아니, 지만, 그러나, 반면, 근데, 는데 등) |
| **Non-negation** | `has_negation == False` | 위 어휘 미포함 |

- **Partition**: Negation ∪ Non-negation = 전체.
- **검증**: negation + non_negation TP/FP/FN 합산 → overall micro-F1 일치

### 3. Multi-aspect vs Single-aspect

| Subset | 기준 | 설명 |
|--------|------|------|
| **Single-aspect** | `gold_n_pairs == 1` | Gold pair 1개 |
| **Multi-aspect** | `gold_n_pairs > 1` | Gold pair 2개 이상 |

- **Partition**: Single-aspect ∪ Multi-aspect = 전체.
- **검증**: single + multi TP/FP/FN 합산 → overall micro-F1 일치

### 4. Conflict vs No-conflict (M0 only, 트리거 기반)

| Subset | 기준 | 설명 |
|--------|------|------|
| **Conflict** | `conflict_flag == 1` | M0에서 analysis_flags.conflict_flags 비어 있지 않음 |
| **No-conflict** | `conflict_flag == 0` | conflict_flags 비어 있음 |

- **M0 전용**: S0는 단일 에이전트이므로 conflict_flag 없음.
- **Partition**: Conflict ∪ No-conflict = M0 전체.

---

## 데이터 소스

- **Triptych**: `derived_subset/triptych.csv` 또는 `derived/tables/triptych_table.tsv`
- **컬럼**: `gold_type`, `gold_n_pairs`, `matches_final_vs_gold`, `gold_n_pairs`, `final_n_pairs`, `text` (negation 패턴 검사용)
