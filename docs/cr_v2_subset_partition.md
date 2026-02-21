# CR v2 Subset Partition 정의

## Subset Partition Verification

**Subset partitions are mutually exclusive and exhaustive.** Weighted recomputation across subsets exactly matches overall micro-F1.

---

## 서브셋 생성 기준 및 규칙

### 공통 규칙

1. **Partition**: 각 축(Implicit/Explicit, Negation/Non-negation 등)에서 두 서브셋의 합 = 전체 샘플.
2. **Mutually exclusive**: 샘플은 각 축당 정확히 하나의 서브셋에만 속함.
3. **검증**: 서브셋별 TP+FP+FN 합산 → overall micro-F1과 일치.

---

### 1. Implicit vs Explicit (난이도 기반)

| Subset | 판별 기준 | 정의 |
|--------|----------|------|
| **Implicit** | `gold_type == "implicit"` | Gold tuple 중 **aspect_term이 비어 있는** (aspect_ref, polarity) 쌍이 **하나라도** 있는 샘플 |
| **Explicit** | `gold_type == "explicit"` | Gold tuple **모두** aspect_term이 비어 있지 않은 샘플 |

**구현 규칙** (`structural_error_aggregator.py`, `_split_gold_explicit_implicit`):
- `gold_implicit`: `normalize_for_eval(aspect_term) == ""` 인 tuple 집합
- `gold_explicit`: `aspect_term` 비어 있지 않은 tuple 집합
- `gold_type = "implicit"` ⇔ `gold_implicit` 비어 있지 않음 (implicit tuple이 하나라도 있으면 implicit)

**Partition**: Implicit ∪ Explicit = 전체. 샘플은 둘 중 하나에만 속함.

---

### 2. Negation/Contrast vs Non-negation

| Subset | 판별 기준 | 정의 |
|--------|----------|------|
| **Negation** | `has_negation == True` | **입력 텍스트**에 부정/대조 어휘가 포함된 샘플 |
| **Non-negation** | `has_negation == False` | 위 어휘 미포함 |

**Lexical cue 패턴** (`final_paper_table.py`, `NEGATION_PATTERNS`):
- 부정: `\b안\b`, `\b못\b`, `않`, `없`, `\b아니\b`
- 대조: `지만`, `그러나`, `반면`, `\b근데\b`, `\b는데\b`

**데이터 소스**: `text` (triptych) 또는 `meta.input_text` / `inputs.input_text` (scorecards)

**Partition**: Negation ∪ Non-negation = 전체.

---

### 3. Multi-aspect vs Single-aspect

| Subset | 판별 기준 | 정의 |
|--------|----------|------|
| **Single-aspect** | `gold_n_pairs == 1` | Gold (aspect_ref, polarity) pair가 1개인 샘플 |
| **Multi-aspect** | `gold_n_pairs > 1` | Gold pair가 2개 이상인 샘플 |

**구현**: `gold_n_pairs = len(tuples_to_ref_pairs(gold_tuples)[0])` — ref-level pair 개수.

**Partition**: Single-aspect ∪ Multi-aspect = 전체.

---

### 4. Conflict vs No-conflict (M0 전용)

| Subset | 판별 기준 | 정의 |
|--------|----------|------|
| **Conflict** | `conflict_flag == 1` | M0에서 `analysis_flags.conflict_flags`가 비어 있지 않음 |
| **No-conflict** | `conflict_flag == 0` | conflict_flags 비어 있음 |

**적용 범위**: M0만. S0는 단일 에이전트이므로 conflict_flag 없음.

**Partition**: Conflict ∪ No-conflict = M0 전체.

---

## 데이터 소스 및 컬럼

| 소스 | 경로 | 주요 컬럼 |
|------|------|------------|
| **Triptych** | `derived_subset/triptych.csv` | `gold_type`, `gold_n_pairs`, `text`, `matches_final_vs_gold`, `final_n_pairs` |
| **Scorecards** | `merged_scorecards.jsonl` | `inputs.gold_tuples`, `meta.input_text` |

**Triptych 생성**:
```bash
python scripts/structural_error_aggregator.py --input <scorecards> --outdir <out> --profile paper_main \
  --export_triptych_table <path>/triptych.csv --triptych_sample_n 0
```

---

## Appendix a4 서브셋 통계

`final_paper_table.py` Appendix a4에서 Gold 기준 서브셋 통계(n, %) 산출:
- **우선**: triptych.csv 사용
- **대체**: merged_scorecards.jsonl에서 gold_type, gold_n_pairs, has_negation 추정
