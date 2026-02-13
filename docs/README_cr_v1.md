# README — Conflict Review v1 (CR v1)

Conflict Review v1 프로토콜 개요, 에이전트 워크플로우, 데이터 플로우, 관련 문서를 정리합니다.

---

## 1. 개요

**Conflict Review v1**는 Legacy 파이프라인(ATE/ATSA/Validator/Debate/Moderator)과 다른 ASTE 프로토콜입니다.

- **3개 관점 에이전트**: P-NEG, P-IMP, P-LIT
- **3개 리뷰 에이전트**: ReviewA, ReviewB, ReviewC
- **1개 합의 에이전트**: Arbiter
- **없음**: Validator, Debate, Moderator

---

## 2. 에이전트 워크플로우

```
text
  │
  ├─► P-NEG (Stage1) ──► triplets (negation/contrast 관점)
  ├─► P-IMP (Stage1) ──► triplets (implicit 관점)
  └─► P-LIT (Stage1) ──► triplets (literal/explicit 관점)
       │
       ▼
  Merge: A(r_neg) + B(r_imp) + C(r_lit) → candidates (tuple_id, origin_agent)
       │
       ▼
  conflict_flags = _compute_conflict_flags(candidates)
       │
       ├─► ReviewA ──► review_actions
       ├─► ReviewB ──► review_actions
       └─► ReviewC ──► review_actions
       │
       ▼
  Arbiter ──► 최종 review_actions (A/B/C 합침)
       │
       ▼
  _apply_review_actions(candidates, arb_actions) → final_candidates
       │
       ▼
  FinalResult (stage1_tuples, final_tuples, final_aspects)
```

**에이전트 목록 (7개 LLM 호출)**

| 순서 | 에이전트 | 역할 | 출력 |
|------|----------|------|------|
| 1 | P-NEG | 부정/대비 관점 ASTE | triplets |
| 2 | P-IMP | 암시적 관점 ASTE | triplets |
| 3 | P-LIT | 문자적 관점 ASTE | triplets |
| 4 | ReviewA | A 관점 리뷰 | review_actions |
| 5 | ReviewB | B 관점 리뷰 | review_actions |
| 6 | ReviewC | C 관점 리뷰 | review_actions |
| 7 | Arbiter | A/B/C 합의 | review_actions |

---

## 3. 데이터 플로우

```
outputs.jsonl (FinalOutputSchema)
       │
       ▼
scorecards.jsonl (make_scorecard)
       │
       ▼
structural_error_aggregator → structural_metrics.csv
       │
       ▼
build_metric_report → metric_report.html
```

**CR 튜플 소스**

| 구분 | 필드 | CR 의미 |
|------|------|---------|
| stage1 | final_result.stage1_tuples | pre_review (merge 후 candidates) |
| final | final_result.final_tuples | post_review (Arbiter 적용 후) |

---

## 4. 실행 방법

```bash
# 통합 스크립트 (권장)
python scripts/run_cr_m0_m1_m2_pipeline.py
```

자세한 내용: [how_to_run_cr_v1.md](how_to_run_cr_v1.md)

---

## 5. 참고 문서

### 에이전트·워크플로우

| 문서 | 설명 |
|------|------|
| [protocol_conflict_review_vs_legacy_comparison.md](protocol_conflict_review_vs_legacy_comparison.md) | CR vs Legacy 에이전트 워크플로우·데이터 플로우 비교 |
| [protocol_mode_conflict_review.md](protocol_mode_conflict_review.md) | protocol_mode 설정·에이전트 구조 |

### 데이터 플로우·메트릭

| 문서 | 설명 |
|------|------|
| [cr_branch_metrics_spec.md](cr_branch_metrics_spec.md) | CR 메트릭, 데이터 플로우, 산출물 경로 |
| [pipeline_stages_data_and_metrics_flow.md](pipeline_stages_data_and_metrics_flow.md) | 파이프라인 단계·데이터·메트릭 흐름 |
| [pipeline_workflow_diagram.md](pipeline_workflow_diagram.md) | 파이프라인 워크플로우 다이어그램 |

### 실행·설정

| 문서 | 설명 |
|------|------|
| [how_to_run_cr_v1.md](how_to_run_cr_v1.md) | CR v1 실행 방법 (통합 스크립트 포함) |
| [run_cr_m0_m1_m2_commands.md](run_cr_m0_m1_m2_commands.md) | CR-M0/M1/M2 실행 명령 |
| [exp_lm_cr_m0_m1_m2_run_commands.md](exp_lm_cr_m0_m1_m2_run_commands.md) | L-M0 vs CR-M0, CR-M0 vs CR-M1 vs CR-M2 실험 가이드 |

### 기타

| 문서 | 설명 |
|------|------|
| [stage_delta_ssot_checklist.md](stage_delta_ssot_checklist.md) | stage_delta SSOT, pairs 기반 changed |
| [schema_scorecard_trace.md](schema_scorecard_trace.md) | scorecard 스키마 |
| [cr_agent_personas_and_prompts.md](cr_agent_personas_and_prompts.md) | CR 에이전트 페르소나·프롬프트 |
