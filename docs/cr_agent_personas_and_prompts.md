# Conflict Review v1: 에이전트 페르소나 및 프롬프트 정리

> **대칭 명세**: Stage 1 · Review 단계를 페르소나·규칙·입출력·스키마별로 대칭 정리한 문서는 [stage1_review_symmetric_spec.md](stage1_review_symmetric_spec.md) 참조.

---

## 1. 파일 경로 요약

| 구분 | 경로 |
|------|------|
| **Stage1 트리플렛 추출** | `agents/prompts/perspective_pneg_stage1.md` |
| | `agents/prompts/perspective_pimp_stage1.md` |
| | `agents/prompts/perspective_plit_stage1.md` |
| **Review 액션 제안** | `agents/prompts/review_pneg_action.md` |
| | `agents/prompts/review_pimp_action.md` |
| | `agents/prompts/review_plit_action.md` |
| **Arbiter 합의** | `agents/prompts/review_arbiter_action.md` |
| **에이전트 구현** | `agents/protocol_conflict_review/perspective_agents.py` |
| | `agents/protocol_conflict_review/review_agents.py` |
| **스키마** | `schemas/protocol_conflict_review.py` |

---

## 2. Stage1 Perspective 에이전트

### 2.1 P-NEG (Agent A)

**파일:** `agents/prompts/perspective_pneg_stage1.md`  
**구현:** `agents/protocol_conflict_review/perspective_agents.py` → `PerspectiveAgentPneg`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent A (P-NEG): negation/contrast 관점 전용 ASTE 추출 |
| **역할** | 부정·대비 표현에 따른 극성 정확도 강화 |
| **핵심 규칙** | - 텍스트에 없는 관점/의견 생성 금지<br>- 부정(not, never, no), 대비(but, however, though, whereas) 표현 집중<br>- 불확실하면 polarity="neutral" + 낮은 confidence<br>- 개수보다 정밀도 우선 |
| **출력 스키마** | `PerspectiveASTEStage1Schema { triplets: [ASTETripletItem...] }` |
| **출력 필드** | aspect_term, aspect_ref, polarity, opinion_term, evidence, span, confidence, rationale |

---

### 2.2 P-IMP (Agent B)

**파일:** `agents/prompts/perspective_pimp_stage1.md`  
**구현:** `agents/protocol_conflict_review/perspective_agents.py` → `PerspectiveAgentPimp`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent B (P-IMP): implicit aspect/target 전용 ASTE 추출 |
| **역할** | 암시적·생략된 관점을 텍스트 근거로 추론 |
| **핵심 규칙** | - 환각 금지: 명확한 텍스트 단서가 있을 때만 암시적 관점 추론<br>- 암시적이면 aspect_ref 가능 시 설정, 아니면 aspect_term 최소화<br>- 불확실하면 polarity="neutral"<br>- 설명 가능한 추론 우선 |
| **출력 스키마** | `PerspectiveASTEStage1Schema { triplets: [ASTETripletItem...] }` |
| **출력 필드** | aspect_term, aspect_ref, polarity, opinion_term, evidence, span, confidence, rationale |

---

### 2.3 P-LIT (Agent C)

**파일:** `agents/prompts/perspective_plit_stage1.md`  
**구현:** `agents/protocol_conflict_review/perspective_agents.py` → `PerspectiveAgentPlit`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent C (P-LIT): literal/explicit evidence 전용 ASTE 추출 |
| **역할** | 문자적 단서·명시적 증거 기반 추출 |
| **핵심 규칙** | - 감정 단서가 관점에 명시적으로 연결될 때만 추론<br>- 텍스트에 없는 관점/의견 생성 금지<br>- 불확실하면 polarity="neutral"<br>- 노이즈보다 정밀도 우선 |
| **출력 스키마** | `PerspectiveASTEStage1Schema { triplets: [ASTETripletItem...] }` |
| **출력 필드** | aspect_term, aspect_ref, polarity, opinion_term, evidence, span, confidence, rationale |

---

## 3. Review 에이전트

### 3.1 Review Agent A (P-NEG)

**파일:** `agents/prompts/review_pneg_action.md`  
**구현:** `agents/protocol_conflict_review/review_agents.py` → `ReviewAgentA`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent A (P-NEG) as reviewer |
| **역할** | conflict_flags/validator_risks에 있는 항목만 교정 제안 |
| **집중 영역** | negation/contrast, polarity flips |
| **허용 액션** | DROP, MERGE, FLIP, KEEP, FLAG |
| **입력** | text, candidates_json, conflict_flags_json, validator_risks_json |
| **출력 스키마** | `ReviewOutputSchema { review_actions: [ReviewActionItem...] }` |
| **규칙** | 새 튜플 생성 금지, conflict_flags/validator_risks에 등장한 tuple_id만 수정 |

---

### 3.2 Review Agent B (P-IMP)

**파일:** `agents/prompts/review_pimp_action.md`  
**구현:** `agents/protocol_conflict_review/review_agents.py` → `ReviewAgentB`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent B (P-IMP) as reviewer |
| **역할** | conflict_flags/validator_risks에 있는 항목만 교정 제안 |
| **집중 영역** | implicit aspect/target, aspect_ref 불일치, MERGE 통합 |
| **허용 액션** | DROP, MERGE, FLIP, KEEP, FLAG |
| **입력** | text, candidates_json, conflict_flags_json, validator_risks_json |
| **출력 스키마** | `ReviewOutputSchema { review_actions: [ReviewActionItem...] }` |
| **규칙** | 암시적/불명확한 관점은 새로 만들지 말고 MERGE 또는 FLAG |

---

### 3.3 Review Agent C (P-LIT)

**파일:** `agents/prompts/review_plit_action.md`  
**구현:** `agents/protocol_conflict_review/review_agents.py` → `ReviewAgentC`

| 항목 | 내용 |
|------|------|
| **페르소나** | Agent C (P-LIT) as reviewer |
| **역할** | conflict_flags/validator_risks에 있는 항목만 교정 제안 |
| **집중 영역** | explicit evidence, 명시적 단서, 중복/노이즈 제거 |
| **허용 액션** | DROP, MERGE, FLIP, KEEP, FLAG |
| **입력** | text, candidates_json, conflict_flags_json, validator_risks_json |
| **출력 스키마** | `ReviewOutputSchema { review_actions: [ReviewActionItem...] }` |
| **규칙** | 명시적 단서가 있는 튜플은 KEEP, 약한/미지지 증거는 DROP 또는 FLAG |

---

### 3.4 Arbiter

**파일:** `agents/prompts/review_arbiter_action.md`  
**구현:** `agents/protocol_conflict_review/review_agents.py` → `ReviewAgentArbiter`

| 항목 | 내용 |
|------|------|
| **페르소나** | Arbiter (Moderator-lite) |
| **역할** | A/B/C의 review_actions를 합쳐 최종 action set 결정 |
| **우선순위** | 1) validator_risks 높은 심각도<br>2) A > B > C<br>3) 불명확 시 KEEP + FLAG (POLARITY_UNCERTAIN) |
| **입력** | text, candidates_json, conflict_flags_json, validator_risks_json, actions_A_json, actions_B_json, actions_C_json |
| **출력 스키마** | `ReviewOutputSchema { review_actions: [ReviewActionItem...] }` |
| **규칙** | 새 action_type 금지, 충돌만 해결, 불필요한 액션은 최소화 |

---

## 4. 프롬프트 호출 구조

```
load_prompt(prompt_name)
  → perspective_pneg_stage1 | perspective_pimp_stage1 | perspective_plit_stage1
  → review_pneg_action | review_pimp_action | review_plit_action | review_arbiter_action

_split_system_user(content) → ---USER--- 기준으로 system / user 템플릿 분리
user 템플릿 치환: {text}, {candidates_json}, {conflict_flags_json}, {validator_risks_json}
  (Arbiter: + {actions_A_json}, {actions_B_json}, {actions_C_json})
```

---

## 5. 참조

- **프로토콜 설정:** `docs/protocol_mode_conflict_review.md`
- **프롬프트 로드:** `agents/prompts/__init__.py` → `load_prompt(name)`
- **스키마:** `schemas/protocol_conflict_review.py` (ASTETripletItem, PerspectiveASTEStage1Schema, ReviewActionItem, ReviewOutputSchema)
