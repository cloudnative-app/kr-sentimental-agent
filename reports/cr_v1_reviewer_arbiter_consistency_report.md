# CR v1 Reviewer/Arbiter 정합성 개선 작업 보고

**실행일**: 2025-02-12

---

## 1. 목표 달성 요약

| 항목 | 상태 |
|------|------|
| Reviewer 역할을 "polarity 재판단자" → 관점 기반 validation 평가자로 재정의 | ✅ |
| Arbiter A>B>C 권위 규칙 제거 | ✅ |
| 메트릭 계산 로직 변경 없음 | ✅ |
| IRR 계산 구조 변경 없음 | ✅ |
| action_type 체계 유지 (DROP/MERGE/FLIP/KEEP/FLAG) | ✅ |

---

## 2. 수행한 변경 사항

### 2.1 Reviewer 프롬프트 수정

| 에이전트 | 파일 | 변경 핵심 |
|----------|------|-----------|
| **ReviewA (P-NEG)** | `agents/prompts/review_pneg_action.md` | NEGATION/CONTRAST VALIDATOR. 구조적 극성 정확도만 검증. DROP(암시적/evidence 부족) 금지 |
| **ReviewB (P-IMP)** | `agents/prompts/review_pimp_action.md` | IMPLICIT INFERENCE VALIDATOR. 암시 추론 정당성만 검증. polarity 변경은 논리적 모순 시에만 |
| **ReviewC (P-LIT)** | `agents/prompts/review_plit_action.md` | EXPLICIT EVIDENCE VALIDATOR. 문자적 근거만 검증. 유효한 암시 추론 덮어쓰기 금지 |

### 2.2 reason_code 확장

**파일**: `schemas/protocol_conflict_review.py`

추가 항목:
- `WEAK_INFERENCE`
- `EXPLICIT_NOT_REQUIRED`
- `STRUCTURAL_INCONSISTENT`

기존 reason_code는 모두 유지.

### 2.3 Arbiter 규칙 수정

**파일**: `agents/conflict_review_runner.py` (`_arbiter_vote`), `agents/prompts/review_arbiter_action.md`

- ❌ A>B>C 권위 규칙 제거 (이미 제거됨, 재확인)
- ✅ Aggregation Rule 문서화:
  1. ≥2 DROP → DROP
  2. ≥2 KEEP → KEEP
  3. ≥2 FLIP → FLIP
  4. 1 FLIP + 1 DROP + 1 KEEP: FLIP의 reason_code가 structural(NEGATION_SCOPE, CONTRAST_CLAUSE, STRUCTURAL_INCONSISTENT)이면 → FLIP; 아니면 → FLAG
  5. Tie(1 KEEP, 1 DROP, 1 FLAG) → KEEP + FLAG

### 2.4 _group_actions_by_tuple

`reason_code`를 action_dict에 포함하여 Arbiter가 reason 기반 판단에 사용.

### 2.5 _apply_review_actions

변경 없음. DROP/FLIP/KEEP/FLAG 동작 유지.

---

## 3. 메트릭·IRR 영향

| 항목 | 영향 |
|------|------|
| tuple_f1_s1 | 없음 |
| tuple_f1_s2 | 없음 |
| delta_f1 | 없음 |
| fix_rate | 없음 |
| break_rate | 없음 |
| polarity_conflict_rate | 없음 |
| IRR 계산 | 없음 |
| change_rate | 없음 |

---

## 4. 단위 테스트 (Arbiter)

- Majority DROP ✅
- 1 FLIP + 1 DROP + 1 KEEP (structural reason) → FLIP ✅
- 1 FLIP + 1 DROP + 1 KEEP (weak reason) → FLAG ✅
- All disagree → FLAG ✅
- 2 FLIP + 1 KEEP → FLIP ✅
