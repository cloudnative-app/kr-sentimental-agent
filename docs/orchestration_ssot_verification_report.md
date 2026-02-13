# 오케스트레이션·SSOT 검증 보고서

코드베이스 검증 결과를 정리합니다.

---

## 1. 오케스트레이션 진입점

| 항목 | 경로 | 비고 |
|------|------|------|
| **run_experiments** | `experiments/scripts/run_experiments.py` | 샘플 단위 실험 실행, runner.run() 호출 |
| **pipeline 실행** | `scripts/run_pipeline.py` | run_experiments를 subprocess로 호출, build_run_snapshot 등 후속 단계 실행 |

---

## 2. Supervisor / Router 코드 위치

| 항목 | 경로 | 비고 |
|------|------|------|
| **SupervisorAgent** | `agents/supervisor_agent.py` | 클래스 정의 (line 90) |
| **Router** | (없음) | 코드베이스에 Router 클래스 없음 |

---

## 3. Stage1 튜플 통일·backfill 함수

| 항목 | 파일 | 함수 | 라인 |
|------|------|------|------|
| **또는 backfill** | `agents/supervisor_agent.py` | `_backfill_sentiments` | 1464 |
| **호출 위치** | `agents/supervisor_agent.py` | `_run_stage1()` 내부 | 213 |

`_backfill_sentiments(text, aspects, sentiments)`: ATE에만 있고 ATSA에 없는 aspect에 대해 `AspectSentimentItem`을 추가해 backfill.

---

## 4. Validator 스키마·출력 생성

| 항목 | 파일 | 함수/위치 | 비고 |
|------|------|-----------|------|
| **StructuralValidatorStage1Schema** | `schemas/agent_outputs.py` | 클래스 정의 | 202 |
| **출력 생성** | `agents/specialized_agents/validator_agent.py` | `run_stage1()` | 85 |
| **생성 방식** | `tools/llm_runner.run_structured()` | schema=StructuralValidatorStage1Schema | LLM 호출 후 파싱 |

---

## 5. 토론(EPM/TAN/CJ) 코드 위치

| 역할 | 파일 | 출력 | aspect_hints 생성 |
|------|------|------|-------------------|
| **DebateOrchestrator** | `agents/debate_orchestrator.py` | DebateOutput (rounds, summary) | - |
| **EPM/TAN/CJ** | 동일 파일 내 persona | `DebateTurn.proposed_edits` (LLM 출력) | SupervisorAgent가 변환 |
| **proposed_edits** | LLM → DebateTurn schema | `op`, `target`, `value` | `_build_debate_review_context`에서 추출 |
| **aspect_hints** | `agents/supervisor_agent.py` | `_build_debate_review_context()` | 822 |

**aspect_hints 생성 흐름**:  
`proposed_edits` → hint_entries (per-edit) → aspect_hints (aspect_map은 aspect_hints에 없는 aspect에만 fallback).

---

## 6. Scorecard / metrics 빌더 경로

| 항목 | 파일 | 함수/역할 |
|------|------|-----------|
| **make_scorecard** | `scripts/scorecard_from_smoke.py` | `make_scorecard(entry, ...)` (404) |
| **structural_error_aggregator** | `scripts/structural_error_aggregator.py` | scorecards.jsonl → structural_metrics.csv/md |
| **build_metric_report** | `scripts/build_metric_report.py` | manifest + scorecards + structural_metrics.csv → metric_report.html |

---

## 7. FinalOutputSchema / outputs.jsonl 필드 스펙

| 정의 위치 | `schemas/final_output.py` |
|-----------|---------------------------|
| **FinalResult** | `label`, `confidence`, `rationale`, `final_aspects`, `stage1_tuples`, `stage2_tuples`, `final_tuples` |
| **FinalOutputSchema** | `meta`, `stage1_ate`, `stage1_atsa`, `stage1_validator`, `stage2_ate`, `stage2_atsa`, `stage2_validator`, `moderator`, `debate`, `process_trace`, `analysis_flags`, `final_result` |

### stage1_tuples / final_tuples 세팅 위치

| 필드 | 파일 | 함수/위치 | 라인 |
|------|------|-----------|------|
| **stage1_tuples** | `agents/supervisor_agent.py` | `FinalResult(...)` 생성 직전 | 669–670 |
| **final_tuples** | 동일 | 동일 | 671–675 |

**코드 요약**:
```python
stage1_sents = getattr(stage1["atsa"], "aspect_sentiments", []) or []
stage2_sents = ...
stage1_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage1_sents]))
stage2_tuples = tuples_to_list_of_dicts(tuples_from_list([s.model_dump() for s in stage2_sents]))
final_tuples = tuples_to_list_of_dicts(tuples_from_list(final_aspects_list))

final_result = FinalResult(
    ...
    stage1_tuples=stage1_tuples,
    stage2_tuples=stage2_tuples,
    final_tuples=final_tuples,
)
```

---

## 8. SSOT 관련 확인 질문 (예/아니오)

| 질문 | 답 |
|------|-----|
| **SSOT는 현재 FinalOutputSchema(outputs.jsonl)인가요?** | **예** – outputs.jsonl은 샘플당 `FinalOutputSchema.model_dump()` 한 줄. |
| **scorecards.jsonl는 outputs.jsonl에서만 생성되나요? (중간 산출물 직접 참조 없음?)** | **거의 예** – run_experiments에서 `payload = result.model_dump()`(= FinalOutputSchema)를 `make_scorecard(payload)`에 전달. 단, `inputs.gold_tuples`는 `uid_to_gold`(eval gold JSONL)에서 별도 주입. |
| **override_gate_debug_summary.json은 aggregator가 side file로 읽는 구조인가요, scorecard/메타에 흡수되는 구조인가요?** | **Side file** – aggregator는 `path.resolve().parent / "override_gate_debug_summary.json"`을 직접 읽고, `override_gate_summary` 인자로 `aggregate_merged()`에 전달. scorecard에는 흡수되지 않음. |
