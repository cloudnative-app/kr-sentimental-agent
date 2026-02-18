# Ghost Change 제거 수정 요약

**목표**: changed=False인데 F1이 달라지는 현상 제거, SSOT 유지, 정규화 체인 통일.

---

## 수정 내용

### 1. F1/break 평가 키 통일 (P0)

**파일**: `metrics/eval_tuple.py`

- `precision_recall_f1_tuple(..., match_by_aspect_ref=False)` 기본값 변경 (True → False)
- `tuple_sets_match_with_empty_rule(..., match_by_aspect_ref=False)` 기본값 변경
- pred pair key: (aspect_term, polarity)만 사용. aspect_ref 미사용.

### 2. aspect_ref 덮어쓰기 제거 (P1)

**파일**: `agents/conflict_review_runner.py`

- `_finalize_normalize_ref`: No-op으로 변경. aspect_ref를 덮어쓰지 않고 원본 보존.

### 3. 정규화 SSOT 모듈 추가 (P2)

**파일**: `metrics/normalization.py` (신규)

- `canonical_normalize_text(s)`: Tier1+Tier2 문자열 정규화
- `normalize_polarity_strict(s)`: Tier1+Tier2 극성 정규화 (whitelist만, edit-distance 없음)

---

## 검증 결과

| 조건 | ghost_change_n | pairs_equal_f1_diff_n | break_n |
|------|----------------|----------------------|---------|
| M0 v2 (수정 후) | **0** | **0** | 0 |
| M1 v2 (수정 후) | **0** | **0** | 0 |
| M2 v2 (수정 후) | **0** | **0** | 0 |

- `s1_pairs == s2_pairs` 이면 `f1_s1 == f1_s2_raw` 성립
- 기존 break 2건(00644, 00237)은 aspect_ref 차이로 인한 ghost artifact였음 → term-only로 0건

---

## 체크리스트

- [x] ghost_change_diagnostic: ghost_change == 0, pairs_equal_f1_diff == 0
- [x] s1_pairs == s2_pairs인 모든 케이스에서 f1_s1 == f1_s2_raw
- [x] F1/break/fix 계산에서 aspect_ref 미사용 (match_by_aspect_ref=False)
- [x] tuples_to_pairs_ref_fallback가 outcome 경로에서 호출되지 않음 (default False)
- [x] _finalize_normalize_ref가 aspect_ref를 덮어쓰지 않음
