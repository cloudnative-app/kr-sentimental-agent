# Stage 1 · Review 대칭 명세

CR v1 파이프라인의 Stage 1(관점별 ASTE 추출)과 Review(교정 제안) 단계를 대칭 구조로 정리합니다.

**관련 스키마**: `schemas/protocol_conflict_review.py`  
**구현**: `agents/protocol_conflict_review/perspective_agents.py`, `review_agents.py`

---

## Part A. Stage 1 — 관점별 ASTE 추출

### 공통 개요

| 항목 | 내용 |
|------|------|
| **역할** | 원문에서 aspect–sentiment triplets 추출 |
| **출력 스키마** | `PerspectiveASTEStage1Schema { triplets: [ASTETripletItem...] }` |
| **구현** | `PerspectiveAgentPneg`, `PerspectiveAgentPimp`, `PerspectiveAgentPlit` |

---

### A.1 P-NEG (Agent A)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent A (P-NEG): negation/contrast 관점 전용 ASTE 추출 |
| **역할** | 부정·대비 표현에 따른 극성 정확도 강화 |
| **규칙** | (1) 텍스트에 없는 관점/의견 생성 금지 (2) negation(not, never, no), contrast(but, however, though, whereas) 집중 (3) 불확실 시 polarity="neutral" + 낮은 confidence (4) 개수보다 정밀도 우선 |
| **받는 데이터** | `text` (원문) |
| **데이터 구조 예시** | `{ "text": "사용감은 좋지만 가격은 비싸요." }` |
| **출력 스키마** | `PerspectiveASTEStage1Schema` |
| **출력 예시** | `{ "triplets": [{ "aspect_term": "사용감", "polarity": "positive", "evidence": "좋지만", ... }] }` |
| **관련 파일** | `agents/prompts/perspective_pneg_stage1.md` |

---

### A.2 P-IMP (Agent B)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent B (P-IMP): implicit aspect/target 전용 ASTE 추출 |
| **역할** | 암시적·생략된 관점을 텍스트 근거로 추론 |
| **규칙** | (1) 환각 금지: 명확한 텍스트 단서가 있을 때만 암시 추론 (2) 암시적이면 aspect_ref 설정, 아니면 aspect_term 최소화 (3) 불확실 시 polarity="neutral" (4) 설명 가능한 추론 우선 |
| **받는 데이터** | `text` (원문) |
| **데이터 구조 예시** | `{ "text": "사용감은 좋지만 가격은 비싸요." }` |
| **출력 스키마** | `PerspectiveASTEStage1Schema` |
| **출력 예시** | `{ "triplets": [{ "aspect_term": "제품", "aspect_ref": "사용감", "polarity": "positive", ... }] }` |
| **관련 파일** | `agents/prompts/perspective_pimp_stage1.md` |

---

### A.3 P-LIT (Agent C)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent C (P-LIT): literal/explicit evidence 전용 ASTE 추출 |
| **역할** | 문자적 단서·명시적 증거 기반 추출 |
| **규칙** | (1) 감정 단서가 관점에 명시적으로 연결될 때만 추론 (2) 텍스트에 없는 관점/의견 생성 금지 (3) 불확실 시 polarity="neutral" (4) 노이즈보다 정밀도 우선, evidence snippet 제공 권장 |
| **받는 데이터** | `text` (원문) |
| **데이터 구조 예시** | `{ "text": "사용감은 좋지만 가격은 비싸요." }` |
| **출력 스키마** | `PerspectiveASTEStage1Schema` |
| **출력 예시** | `{ "triplets": [{ "aspect_term": "사용감", "polarity": "positive", "evidence": "좋지만", ... }] }` |
| **관련 파일** | `agents/prompts/perspective_plit_stage1.md` |

---

### ASTETripletItem (공통 출력 항목)

```json
{
  "aspect_term": "사용감",
  "aspect_ref": "사용감",
  "polarity": "positive",
  "opinion_term": "좋다",
  "evidence": "좋지만",
  "span": {"start": 0, "end": 3},
  "confidence": 0.9,
  "rationale": "부정 대비 구조"
}
```

---

## Part B. Review — 교정 제안

### 공통 개요

| 항목 | 내용 |
|------|------|
| **역할** | conflict_flags/validator_risks 대상 tuple에 대해 교정 액션 제안 |
| **출력 스키마** | `ReviewOutputSchema { review_actions: [ReviewActionItem...] }` |
| **구현** | `ReviewAgentA`, `ReviewAgentB`, `ReviewAgentC` |
| **허용 액션** | DROP, MERGE, FLIP, KEEP, FLAG |
| **공통 규칙** | (1) 새 튜플 생성 금지 (2) conflict_flags/validator_risks에 등장한 tuple_id만 수정 (3) 불확실 시 KEEP + FLAG |

---

### B.1 Review Agent A (P-NEG)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent A (P-NEG) as reviewer |
| **역할** | negation/contrast, polarity flip 관련 교정 제안 |
| **규칙** | 공통 규칙 + negation/contrast 관련 교정 우선 |
| **받는 데이터** | text, candidates_json, conflict_flags_json, validator_risks_json, memory_context |
| **데이터 구조 예시** | (아래 「Review 입력 구조」 참조) |
| **출력 스키마** | `ReviewOutputSchema` |
| **출력 예시** | `{ "review_actions": [{ "action_type": "FLIP", "target_tuple_ids": ["t3"], "new_value": {"polarity": "negative"}, "reason_code": "NEGATION_SCOPE", "actor": "A" }] }` |
| **관련 파일** | `agents/prompts/review_pneg_action.md` |

---

### B.2 Review Agent B (P-IMP)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent B (P-IMP) as reviewer |
| **역할** | implicit aspect, aspect_ref 불일치, MERGE 통합 제안 |
| **규칙** | 공통 규칙 + 암시적/불명확한 관점은 새로 만들지 말고 MERGE 또는 FLAG |
| **받는 데이터** | text, candidates_json, conflict_flags_json, validator_risks_json, memory_context |
| **데이터 구조 예시** | (아래 「Review 입력 구조」 참조) |
| **출력 스키마** | `ReviewOutputSchema` |
| **출력 예시** | `{ "review_actions": [{ "action_type": "MERGE", "target_tuple_ids": ["t1","t2"], "new_value": {"normalized_ref": "사용감"}, "reason_code": "ASPECT_REF_MISMATCH", "actor": "B" }] }` |
| **관련 파일** | `agents/prompts/review_pimp_action.md` |

---

### B.3 Review Agent C (P-LIT)

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent C (P-LIT) as reviewer |
| **역할** | explicit evidence, 명시적 단서, 중복/노이즈 제거 제안 |
| **규칙** | 공통 규칙 + 명시적 단서가 있는 튜플은 KEEP, 약한/미지지 증거는 DROP 또는 FLAG |
| **받는 데이터** | text, candidates_json, conflict_flags_json, validator_risks_json, memory_context |
| **데이터 구조 예시** | (아래 「Review 입력 구조」 참조) |
| **출력 스키마** | `ReviewOutputSchema` |
| **출력 예시** | `{ "review_actions": [{ "action_type": "DROP", "target_tuple_ids": ["t5"], "reason_code": "WEAK_EVIDENCE", "actor": "C" }] }` |
| **관련 파일** | `agents/prompts/review_plit_action.md` |

---

### Review 입력 구조

#### candidates (JSON)

```json
[
  {
    "tuple_id": "t0",
    "aspect_term": "사용감",
    "aspect_ref": "사용감",
    "polarity": "positive",
    "evidence": "좋아요",
    "span": {"start": 0, "end": 5},
    "origin_agent": "A"
  },
  {
    "tuple_id": "t3",
    "aspect_term": "사용감",
    "aspect_ref": "사용감",
    "polarity": "negative",
    "evidence": "별로",
    "origin_agent": "B"
  }
]
```

#### conflict_flags (JSON)

```json
[
  {
    "aspect_term": "사용감",
    "tuple_ids": ["t0", "t3"],
    "conflict_type": "polarity_mismatch"
  }
]
```

#### validator_risks (JSON)

```json
[]
```

#### memory_context (string)

```
Memory advisory (from similar past cases):
- 부정 대비 시 절대 극성 우선.
```

---

### ReviewActionItem (출력 항목)

```json
{
  "action_type": "FLIP",
  "target_tuple_ids": ["t3"],
  "new_value": {"polarity": "negative"},
  "reason_code": "NEGATION_SCOPE",
  "actor": "A"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| action_type | string | DROP \| MERGE \| FLIP \| KEEP \| FLAG |
| target_tuple_ids | string[] | 대상 tuple_id 목록 |
| new_value | object | FLIP: `{"polarity":"..."}` / MERGE: `{"normalized_ref":"..."}` |
| reason_code | string | 표준 reason_code |
| actor | string | "A" \| "B" \| "C" |

---

### reason_code 표준 목록

```
NEGATION_SCOPE, CONTRAST_CLAUSE, IMPLICIT_ASPECT,
ASPECT_REF_MISMATCH, SPAN_OVERLAP_MERGE, DUPLICATE_TUPLE,
WEAK_EVIDENCE, POLARITY_UNCERTAIN, FORMAT_INCOMPLETE,
KEEP_BEST_SUPPORTED,
WEAK_INFERENCE, EXPLICIT_NOT_REQUIRED, STRUCTURAL_INCONSISTENT
```

---

## Part C. 관련 파일 및 스키마 요약

| 구분 | 경로 |
|------|------|
| **Stage1 프롬프트** | `agents/prompts/perspective_pneg_stage1.md` |
| | `agents/prompts/perspective_pimp_stage1.md` |
| | `agents/prompts/perspective_plit_stage1.md` |
| **Review 프롬프트** | `agents/prompts/review_pneg_action.md` |
| | `agents/prompts/review_pimp_action.md` |
| | `agents/prompts/review_plit_action.md` |
| **Arbiter** | `agents/prompts/review_arbiter_action.md` |
| **에이전트 구현** | `agents/protocol_conflict_review/perspective_agents.py` |
| | `agents/protocol_conflict_review/review_agents.py` |
| **스키마** | `schemas/protocol_conflict_review.py` |
| **러너** | `agents/conflict_review_runner.py` |

### 스키마 클래스

| 클래스 | 용도 |
|--------|------|
| ASTETripletItem | Stage1 triplet 항목 |
| PerspectiveASTEStage1Schema | Stage1 출력 |
| ReviewActionItem | Review 액션 항목 |
| ReviewOutputSchema | Review 출력 |
| Span | span 필드 (start, end) |
