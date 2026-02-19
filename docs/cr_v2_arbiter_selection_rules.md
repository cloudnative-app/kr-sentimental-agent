# CR_V2 Arbiter 선택 규칙

**위치**: `agents/conflict_review_runner._arbiter_vote`  
**입력**: `actions_by_tuple` (tuple_id → {A, B, C} 각 에이전트 액션), `conflict_flags` (conflict_type 매핑)

---

## 1. 규칙 요약

| Rule | 조건 | 결과 |
|------|------|------|
| **Rule 1** | ≥2 동일 액션 | 해당 액션 채택. 단, **소수 에이전트가 _FACET_PRIORITY에 해당**하면 → FLAG (FACET_MINORITY_SIGNAL) |
| **Rule 2** | 전원 다름 (다수 없음, 1FLIP+1DROP+1KEEP 아님) | KEEP + FLAG. granularity_overlap_candidate → REDUNDANT_REF_UNCERTAIN, 그 외 → POLARITY_UNCERTAIN |
| **Rule 3** | 1 FLIP + 1 DROP + 1 KEEP | FLIP structural → FLIP; **DROP justified** → DROP; 그 외 → FLAG |
| **Rule 4** | MERGE vote | KEEP으로 대체 (Arbiter는 MERGE 출력 안 함) |

---

## 2. Rule 1: 다수결 + Facet 소수 보호

- **조건**: `majority_count >= 2` (동일 액션이 2명 이상)
- **기본**: 다수 액션 채택
- **예외**: `conflict_type`이 `_FACET_PRIORITY`에 있고, **소수 에이전트가 preferred actor**에 있으면
  - `final_action = "FLAG"`
  - `flag_reason = "FACET_MINORITY_SIGNAL"`
  - 즉, 다수결을 채택하지 않고 FLAG로 유지 (C가 소수일 때 C 의견을 무시하지 않음)

**Facet 우선 에이전트**: `_FACET_PRIORITY`

| conflict_type | preferred actor |
|---------------|------------------|
| granularity_overlap_candidate | C |
| REDUNDANT_UPPER_REF | C |

---

## 3. Rule 2: 전원 다름 (tie)

- **조건**: 다수 없음, 1FLIP+1DROP+1KEEP 아님 (예: 2FLIP+1KEEP, 2DROP+1FLIP 등)
- **결과**: `final_action = "FLAG"`
- **flag_reason**:
  - `conflict_type == "granularity_overlap_candidate"` → `REDUNDANT_REF_UNCERTAIN`
  - 그 외 → `POLARITY_UNCERTAIN`

---

## 4. Rule 3: 1 FLIP + 1 DROP + 1 KEEP

- **조건**: `set(votes_adopted) == {"FLIP", "DROP", "KEEP"}`
- **우선순위**:

  1. **FLIP structural**  
     FLIP의 `reason_code` ∈ `_STRUCTURAL_REASON_CODES` → **FLIP 채택**

  2. **DROP justified**  
     DROP의 `reason_code` ∈ `_DROP_JUSTIFIED` → **DROP 채택**

  3. **그 외**  
     → **FLAG**  
     - `conflict_type == "granularity_overlap_candidate"` → `REDUNDANT_REF_UNCERTAIN`
     - 그 외 → `TIE_UNRESOLVED`

**Structural reason codes**:

```
_STRUCTURAL_REASON_CODES = frozenset({
    "NEGATION_SCOPE",
    "CONTRAST_CLAUSE",
    "STRUCTURAL_INCONSISTENT",
})
```

**DROP justified reason codes**:

```
_DROP_JUSTIFIED = frozenset({
    "WEAK_EVIDENCE",
    "REDUNDANT_UPPER_REF",
})
```

---

## 5. Rule 4: MERGE 처리

- MERGE vote는 Arbiter 내부에서 **KEEP**으로 대체
- Arbiter는 MERGE를 출력하지 않음 (Finalize 단계로 이동, 현재 P1은 no-op)

---

## 6. 액션 공간

| 액션 | 설명 |
|------|------|
| KEEP | 유지 |
| DROP | 제거 |
| FLIP | polarity 변경 (`new_value.polarity`) |
| FLAG | 유지 + 불확실 표시 |

---

## 7. CR v1 vs CR v2 차이

| 항목 | CR v1 | CR v2 |
|------|-------|-------|
| Rule 1 | ≥2 동일 → 채택 | + Facet 소수 보호: preferred actor가 소수면 FLAG |
| Rule 2 | 전원 다름 → KEEP+FLAG (POLARITY_UNCERTAIN) | + granularity_overlap_candidate → REDUNDANT_REF_UNCERTAIN |
| Rule 3 | FLIP structural → FLIP; else FLAG | + DROP justified → DROP; else FLAG (REDUNDANT_REF_UNCERTAIN / TIE_UNRESOLVED) |
| Facet 우선 | 없음 | _FACET_PRIORITY (granularity / REDUNDANT_UPPER_REF → C) |
| DROP 정당화 | 없음 | _DROP_JUSTIFIED (WEAK_EVIDENCE, REDUNDANT_UPPER_REF) |

---

## 8. 참조

| 항목 | 파일 |
|------|------|
| Arbiter 구현 | `agents/conflict_review_runner._arbiter_vote` |
| Arbiter 프롬프트 | `agents/prompts/review_arbiter_action.md` |
| conflict 플래깅 | `agents/conflict_review_runner._compute_conflict_flags` |
| granularity | `agents/conflict_review_runner._detect_granularity_overlap` |
