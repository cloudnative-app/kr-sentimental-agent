# pipeline.protocol_mode: legacy | conflict_review_v1

Feature flag for protocol selection. 기존 실험 파이프라인 깨짐 방지용.

## 설정

```yaml
pipeline:
  protocol_mode: legacy   # 기본값. ATE/ATSA/Validator/Debate/Moderator 흐름
  # protocol_mode: conflict_review_v1  # P-NEG/P-IMP/P-LIT + Review A/B/C + Arbiter
```

- **legacy** (기본): 기존 Stage1(ATE/ATSA/Validator) → Debate → Stage2 → Moderator 흐름.
- **conflict_review_v1**: Stage1(P-NEG, P-IMP, P-LIT) → Review(A, B, C) → Arbiter → 최종 triplets.

## conflict_review_v1 구조

| 단계 | 에이전트 | 스키마 | 프롬프트 |
|------|----------|--------|----------|
| Stage1 | P-NEG (Agent A) | PerspectiveASTEStage1Schema | perspective_pneg_stage1 |
| Stage1 | P-IMP (Agent B) | PerspectiveASTEStage1Schema | perspective_pimp_stage1 |
| Stage1 | P-LIT (Agent C) | PerspectiveASTEStage1Schema | perspective_plit_stage1 |
| Review | Agent A | ReviewOutputSchema | review_pneg_action |
| Review | Agent B | ReviewOutputSchema | review_pimp_action |
| Review | Agent C | ReviewOutputSchema | review_plit_action |
| Review | Arbiter | ReviewOutputSchema | review_arbiter_action |

## 관련 파일

- 스키마: `schemas/protocol_conflict_review.py`
- 에이전트: `agents/protocol_conflict_review/`
- 러너: `agents/conflict_review_runner.py`
- 프롬프트: `agents/prompts/perspective_*.md`, `agents/prompts/review_*.md`
- 실험 설정: `experiments/configs/experiment_conflict_review_v1_mini4.yaml`
