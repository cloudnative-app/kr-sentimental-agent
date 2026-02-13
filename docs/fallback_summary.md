# 파이프라인 내 Fallback 정리

## 1. Aggregation fallback (structural_error_aggregator)

**위치**: `scripts/structural_error_aggregator.py` `_extract_final_tuples_with_source()`

**N_agg_fallback_used**: final_pred 소스가 `final_tuples`가 아닌 경우 행 수.

| 순위 | 소스 | 조건 | N_* | N_agg_fallback_used |
|------|------|------|-----|---------------------|
| 1 | `final_result.final_tuples` | 존재·비어있지 않음 | N_pred_final_tuples | — |
| 2 | `final_result.final_aspects` | final_tuples 없음/비어있음 | N_pred_final_aspects | ✅ +1 |
| 3 | `inputs.aspect_sentiments` | 둘 다 없음/비어있음 | N_pred_inputs_aspect_sentiments | ✅ +1 |

- **발생 조건**: `final_tuples`가 없거나 비어있어 `final_aspects` 또는 `inputs.aspect_sentiments`를 사용할 때
- **로그**: `AGG_FALLBACK_USED` 경고 (text_id, source, reason)
- **판정**: 설계상 허용. `N_pred_final_aspects=0`이면서 `n>0`이면 `final_pred_source_aspects_path_unused_flag=True` (Info flag, final_aspects 경로 미사용)

---

## 2. Stage1 tuple fallback (aggregator)

**위치**: `scripts/structural_error_aggregator.py` `_extract_stage1_tuples_with_source()`

| 순위 | 소스 | 조건 | 메트릭 |
|------|------|------|--------|
| 1 | `final_result.stage1_tuples` | 존재·비어있지 않음 | — |
| 2 | `process_trace` Stage1 ATSA `aspect_sentiments` | stage1_tuples 없음 | stage1_fallback_trace_atsa_rate |
| 3 | `_extract_final_tuples` (final fallback 포함) | 둘 다 없음 | STAGE1_SOURCE_FALLBACK_FINAL |

- **stage1_fallback_trace_atsa_rate**: stage1_tuples 미기록 시 trace ATSA 사용 비율
- **설명 가능 수준**: fallback 비율이 높으면 파이프라인 저장 누락 가능성

---

## 3. Debate mapping fallback (supervisor_agent)

**위치**: `agents/supervisor_agent.py` `_build_debate_review_context()`, `_fallback_map_from_atsa()`

토론 턴의 `proposed_edits` aspect를 Stage1 aspect_terms에 매핑할 때:

| 순위 | 방식 | 조건 | mapping_stats |
|------|------|------|---------------|
| 1 | **Direct** | 토론 텍스트(blob)에 aspect_term/substring 직접 포함 | direct |
| 2 | **Fallback** | direct 실패 시 `_fallback_map_from_atsa()` 사용 | fallback |
| 3 | **None** | 둘 다 실패 | none |

**`_fallback_map_from_atsa`**:
- Stage1 ATSA `aspect_sentiments`에서 선택
- `polarity_hint` 있음: 같은 polarity인 sentiment 중 confidence 최대
- `polarity_hint` 없음/neutral: 모든 sentiment가 동일하면 첫 항목, 아니면 []

**mapping_fail_reasons.fallback_used**: direct로는 실패했으나 fallback으로 매핑 성공한 건수.

- **debate_mapping_fallback_rate**: fallback / total_maps
- **debate_fail_fallback_used_rate**: fallback_used 건수 기준 (실패 원인 분류)

---

## 4. Aspect hints fallback (debate review context)

**위치**: `agents/supervisor_agent.py` `_build_debate_review_context()`

게이트 점수화용 `aspect_hints` 채우기:

| 순위 | 소스 | 조건 |
|------|------|------|
| 1 | **hint_entries** | `proposed_edits`에서 per-edit 추출 (set_polarity, confirm_tuple, drop_tuple 등) |
| 2 | **aspect_map** | aspect_hints에 없는 aspect에만 turn-level 추가 |

- `proposed_edits` 없으면: message/key_points + speaker stance 기반 legacy fallback

---

## 5. Moderator label fallback (Moderator)

**위치**: `agents/specialized_agents/moderator.py`

Stage1/Stage2 극성으로 최종 label 결정 시:

| 순위 | 소스 | 조건 |
|------|------|------|
| 1 | Stage1/Stage2 ATSA `aspect_sentiments` polarity | 정상 |
| 2 | **CJ final_tuples** | EPM/TAN/CJ flow에서 summary.final_tuples 극성 집계 |
| 3 | **Deprecated** | consensus/rationale/key_agreements/key_disagreements 텍스트 추론 |

---

## 6. LLM runner fallback (tools/llm_runner)

**위치**: `tools/llm_runner.py`

LLM 호출 실패 또는 파싱 실패 시:

| 상황 | 동작 | fallback_construct_used |
|------|------|-------------------------|
| generate_failed / json_parse / schema_validation | 빈 schema `model_construct()` 반환 | ✅ True |
| use_mock=0 (real run) | `_raise_if_realrun_fallback` → RuntimeError (fallback 금지) | — |
| use_mock=1 (mock) | 빈 모델 반환 | ✅ True |

- **scorecard**: `runtime.flags.fallback_used` = `call_meta.fallback_construct_used`
- **build_metric_report**: `fallback_used_count`, `fallback_used_rate`

---

## 7. RQ1 implicit fallback (structural_error_aggregator)

**위치**: `scripts/structural_error_aggregator.py` `rq1_grounding_bucket()`, `_is_implicit_fallback_eligible()`

explicit_failure로 판정 직전:

| 조건 | 결과 |
|------|------|
| `_is_implicit_fallback_eligible` True | explicit_failure → **implicit** 재분류 |
| 그 외 | explicit_failure 유지 |

**implicit fallback 조건**:
- doc-level polarity 유효
- `inputs.implicit_grounding_candidate==True` 또는
- ate_debug.filtered 전부 drop + drop_reason 전부 `alignment_failure`

---

## 8. Scorecard sentence sentiment fallback (scorecard_from_smoke)

**위치**: `scripts/scorecard_from_smoke.py` `build_sentence_sentiment()`

문장급 감성 추출 시 `final_result` 없을 때:

- `final_result.label`, `confidence` 사용
- `reason: "fallback to final_result"`

---

## 9. 평가/매칭 fallback (eval_tuple)

**위치**: `metrics/eval_tuple.py`

| 함수 | 역할 |
|------|------|
| `tuples_to_pairs_ref_fallback()` | pair 키를 (aspect_ref \| aspect_term, polarity)로. aspect_ref 있으면 aspect_ref 사용 (term 정규화 불일치 완화) |
| `match_by_aspect_ref=True` | gold→pred 매칭 시 pred는 ref_fallback 사용. gold는 aspect_term만 사용 |

- **gold→gold 검사** (`run_sanity_checks`): `match_by_aspect_ref=False` (aspect_term만 사용)

---

## 10. 그 외

| 위치 | 내용 |
|------|------|
| `backbone_client` | BACKBONE_PROVIDER 미설정 시 mock fallback (경고) |
| `run_pipeline` | 기본 테스트 문장 fallback |
| `build_metric_report` | 메트릭 키 없을 때 `_struct_fallback`으로 deprecated 키 참조 |
| `export_gold_pred_pairs_table` | `tuples_to_pairs_ref_fallback` 사용 |
| **Neutral fallback** | **제거됨** — invalid/missing polarity를 neutral로 묵시 매핑하지 않음 (polarity_canonicalization_policy) |

---

## 요약표

| 구분 | N_agg_fallback_used | 발생 조건 |
|------|---------------------|-----------|
| Aggregation | 행 수 | final_tuples 없음 → final_aspects 또는 inputs 사용 |
| Debate mapping | debate_mapping_fallback_rate | direct 매핑 실패 → ATSA로 fallback 매핑 |
| Stage1 tuple | stage1_fallback_trace_atsa_rate | stage1_tuples 없음 → trace ATSA 사용 |
| LLM | fallback_used_rate | 파싱/스키마 실패 → 빈 모델 반환 |
| RQ1 | — | explicit_failure → implicit 재분류 (eligible 시) |
