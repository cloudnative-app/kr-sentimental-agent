# 중립(neutral) / 충돌(conflict) / 결측(missing) 정책

파이프라인에서 **neutral ≠ missing** 을 강제하기 위한 기준 정의 및 처리 원칙.

---

## 0. 기준 정의

| 용어 | 정의 | 처리 원칙 |
|------|------|------------|
| **neutral** | 텍스트에 명시적 pos/neg 평가가 없음 (또는 문장 전체가 사실/설명). | 의도된 중립일 때만 `polarity="neutral"` 사용. 결측을 neutral로 대체하지 않음. |
| **conflict** | 동일 aspect에서 pos/neg가 동시에 성립(대조/양면). | neutral이 아니라 **mixed / ambivalent / conflict** 로 별도 라벨. |
| **missing** | 모델/파서/파이프라인 상의 결측(필드 누락, 매핑 실패 등). | **neutral로 두면 안 됨.** invalid_pred / eval_excluded / backfill 표기 등으로 분리. |

**핵심**: **neutral ≠ missing** 을 파이프라인에서 강제한다.

---

## 1. 적용 위치 (요약)

- **평가(eval)**: pred/gold에서 polarity 없으면 neutral 대체 금지 → invalid_pred / eval_excluded 별도 집계. (`metrics/eval_tuple.py`)
- **스키마**: `polarity` 기본값을 neutral이 아닌 Optional로 두고, 실제 neutral만 명시적으로 입력. (`schemas/agent_outputs.py`)
- **Supervisor**: `item.get("polarity") or "neutral"` 제거, None 유지 + 로깅, 필요 시 neutral_reason 기록. (`agents/supervisor_agent.py`)
- **Backfill**: ATE만 있고 ATSA 없는 aspect 채움 시 `is_backfilled=True`, `neutral_reason="missing_atsa_for_aspect"` 등 표기, 평가/리포트에서 별도 분리.
- **Debate hint**: 힌트 없음은 `"neutral"`이 아닌 `None`, 스코어링에서 0 가중치/no-op.
- **Stage2 placeholder**: placeholder는 final_tuples로 넘기지 않거나 `placeholder=True` 표기 후 evaluator에서 제외/분리.
- **실험/리포트**: 라벨 없음 시 neutral 기본값 대신 `missing_label_count` 등 별도 집계.

---

## 2. 구현 요약 (적용된 수정)

- **A1** `metrics/eval_tuple.py`: `normalize_polarity(s, default_missing="neutral")` — `default_missing=None`이면 결측 시 `None` 반환. `tuple_from_sent(..., default_missing_polarity)`, `gold_row_to_tuples(..., default_missing_polarity)` 반환형 `(list, has_missing)`. `tuples_from_list_for_eval(..., default_missing_polarity=None)` → `(set, invalid_count)`. gold 결측 시 `eval_excluded`, pred 결측 시 `invalid_pred`로 분리.
- **B2** `schemas/agent_outputs.py`: `polarity: Optional[str] = None`, `is_backfilled`, `neutral_reason` 필드 추가. validator: 결측 시 `None` 허용(neutral로 대체하지 않음).
- **B3** `agents/supervisor_agent.py`: `item.get("polarity") or "neutral"` 제거, 결측 시 skip/continue. `_aggregate_label_from_sentiments`에서 polarity None이면 rationale에 `[missing polarity]` 표기.
- **C4** Backfill: `AspectSentimentItem(..., is_backfilled=True, neutral_reason="missing_atsa_for_aspect")`.
- **C5** Debate hint: 기본값 `"neutral"` → `None`, 스코어링에서 None = 0 가중치/no-op.
- **C6** Stage2 placeholder: `is_backfilled=True`, `neutral_reason="stage2_placeholder_no_sentiments"`.
- **D7** `experiments/scripts/run_experiments.py`: HF용 라벨 결측 시 `missing_label_count` 증가, manifest `integrity.missing_label_count` 기록. HF 호출 시 결측이면 `"missing"` 전달.

## 3. 관련 문서

- Stage1 ATSA polarity 파싱: `tools/llm_runner.py` 정규화 (neutral fallback 제거).
- SoT/불변식: `docs/stage_delta_ssot_checklist.md`, `reports/pipeline_integrity_audit.md`.
