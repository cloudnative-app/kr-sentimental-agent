# 파이프라인 스테이지별 데이터·튜플 형태·집계·담당자 및 메트릭 표 산출

이 문서는 ABSA 파이프라인에서 **스테이지별로 수집·기록되는 데이터**, **산출되는 튜플 형태**, **최종 집계 데이터**, **담당 컴포넌트**, **메트릭 표(structural_metrics_table.md / metric_report.html)** 및 **Triptych 표(derived/tables/triptych_table.tsv)** 산출에의 이용을 정리합니다.

- **워크플로우 다이어그램·생성용 프롬프트**: `docs/pipeline_workflow_diagram.md` (Mermaid 플로우차트 + 다이어그램 생성 프롬프트).
- **공식 메트릭 정의·집계 공식**: `docs/official_metrics.md` (Official). polarity_repair_rate / polarity_invalid_rate 여부 및 override_hint_invalid_rate 등 정리.

---

## 1. 데이터 흐름 개요

```
[데이터셋 CSV/JSON]
       ↓
run_experiments (1샘플씩 runner.run)
       ↓
outputs.jsonl (FinalOutputSchema) + traces.jsonl + scorecards.jsonl
       │
       │  (C2·debate_override 사용 시 SupervisorAgent가 results/<run_id>/ 에 추가 기록)
       ├── episodic_store.jsonl (run_id별 에피소드 메모리 스토어; run_experiments 실행 시 store_path = results/<run_id>/episodic_store.jsonl 로 주입)
       ├── override_gate_debug.jsonl (aspect별 gate 레코드: pos_score, neg_score, total, margin, valid_hint_count, skip_reason 등)
       └── override_gate_debug_summary.json (run 종료 시 1회: skip_reason_count, low_signal_breakdown, skipped_neutral_only_n 등)
       ↓
structural_error_aggregator (scorecards.jsonl →)
       ↓
structural_metrics.csv / structural_metrics_table.md
       ├── (옵션) --export_triptych_table  → derived/tables/triptych_table.tsv (또는 .csv)
       └── (옵션) --export_triptych_risk_details → derived/tables/triptych_risk_details.jsonl
       ↓
build_metric_report (manifest + scorecards + structural_metrics.csv)
       ↓
metric_report.html
```

- **outputs.jsonl**: 런타임 1차 산출물(에이전트 원시 출력·final_result 포함). run_experiments가 샘플당 1줄 기록.
- **scorecards.jsonl**: run_experiments 내부에서 `make_scorecard(payload)`로 생성. 메트릭·집계용으로 정규화된 1샘플 1줄. `stage_delta`는 라벨 변경 또는 **pairs(튜플 집합) 변경** 기준으로 채워지며, `override_candidate`, `override_applied`, `override_reason` 포함(scorecard_from_smoke). C2 시 `meta.memory`(retrieved_k, retrieved_ids, exposed_to_debate, prompt_injection_chars) 주입. `meta.debate_override_stats`에 applied, skipped_low_signal, **skipped_neutral_only**, skipped_conflict 등; `meta.debate_override_skip_reasons`에 action_ambiguity, L3_conservative 등; (선택) `meta.debate_review_context`(aspect_hints, rebuttal_points 등).
- **override_gate_debug.jsonl**: SupervisorAgent가 debate override 게이트 적용 시 aspect별 1줄씩 추가. pos_score, neg_score, total, margin, **valid_hint_count**, skip_reason(neutral_only | low_signal | action_ambiguity 등), decision(SKIP|APPLY).
- **override_gate_debug_summary.json**: run 종료 시 `_write_override_gate_debug_summary()`로 1회 기록. skip_reason_count, **low_signal_breakdown**(neutral_only, low_signal), **skipped_neutral_only_n**, total_dist, margin_dist 등.
- **structural_metrics.csv / .md**: scorecards.jsonl 전체를 structural_error_aggregator가 집계한 **단일 run 1행** 메트릭. debate_override_* 는 meta.debate_override_stats(및 debate.override_stats)에서 읽음.
- **triptych_table.tsv (.csv)**: aggregator의 `--export_triptych_table`로 생성. **1행 = 1샘플(text_id)** 사람용 표. stage1/final/gold pairs, stage1_to_final_changed(**pairs set 비교**), guided_change/unguided_drift, risk 플래그, memory_enabled/retrieved_n/used/ids, episodic_memory_effect 등. `--log_tuple_sources`는 요약 로그, triptych는 사람용 표로 분리.
- **triptych_risk_details.jsonl**: `--export_triptych_risk_details`로 생성. text_id별 validator raw risks, debate_override_stats, ate_debug filtered drop_reason 상위 등(리스크 드릴다운용).
- **metric_report.html**: manifest + scorecards + structural_metrics.csv를 읽어 build_metric_report가 HTML로 시각화.

### 1.1 에피소드 메모리 run 격리 및 이전 런 영향

- **런별 국한 여부**: 예. `run_experiments`는 모드마다 `store_path = results/<run_id_mode>/episodic_store.jsonl`을 주입하고, 해당 런에서만 그 경로를 사용합니다. 따라서 **서로 다른 run_id(또는 run_id_mode)** 간에는 서로 다른 파일을 사용하므로, **한 런에서 이용하는 에피소드 메모리는 그 런에만 국한**됩니다.
- **메모리 누수(다른 런 간)**: 없음. Run A(`run_id_mode=A`)와 Run B(`run_id_mode=B`)는 각각 `results/A/episodic_store.jsonl`, `results/B/episodic_store.jsonl`을 사용하므로, **이전 런의 메모리가 다른 런의 파이프라인 실행에 영향을 주지 않습니다**.
- **동일 run_id 재실행 시**: 같은 run_id로 실험을 다시 실행하면 **같은 경로**를 쓰므로, `MemoryStore.load()`가 **이전 실행에서 쌓인 JSONL**을 그대로 읽습니다. 즉, **동일 run_id에 한해 "이전 실행"의 메모리 축적이 다음 실행에 영향을 줄 수 있습니다**. 재현성·디버깅 목적의 재실행이면 의도적일 수 있고, 실행마다 완전 격리를 원하면 run 시작 시 스토어 비우기 또는 실행별 고유 경로(예: 타임스탬프)가 필요합니다.

### 1.2 실행마다 스토어 비우기 설정 (config on/off, 구현됨)

- **목적**: 동일 run_id 재실행 시 "이전 실행" 메모리가 로드되지 않도록, run 시작 시 스토어 파일을 비우는 동작을 config로 켜/끌 수 있게 함.
- **설정**: 실험 config의 `episodic_memory` 아래. 예: `episodic_memory.clear_store_at_run_start: true` (기본값 `false`, 미설정 시 기존 동작 유지).
- **동작**: `run_experiments`에서 `store_path`를 run-scoped로 설정한 직후, `make_runner` 호출 전에 플래그가 true이면 해당 경로 파일을 빈 파일로 truncate. 부모 디렉터리는 `Path(store_path).parent.mkdir(parents=True, exist_ok=True)`로 생성.
- **SSOT**: 플래그는 config에서만 읽고, 비우기는 `run_experiments` 한 곳에서만 수행. `EpisodicOrchestrator`/`MemoryStore`는 변경 없음.
- **메트릭·데이터 플로우**: 비우기는 러너 생성 전에만 수행하므로 해당 run은 빈 스토어에서 시작하며, 스코어카드·메트릭 정합성 유지.
- **manifest**: `manifest["episodic_memory"]`에 실험의 `episodic_memory`가 기록되므로 `clear_store_at_run_start` 포함 시 재현 시 추적 가능.

---

## 2. 스테이지별 수집·기록 데이터 및 담당자

### 2.1 Stage1 (독립 추론)

| 담당 | 산출 스키마 | 수집·기록되는 데이터 | scorecard 반영 |
|------|-------------|----------------------|----------------|
| **ATE** | `AspectExtractionStage1Schema` | `aspects`: List[{term, span, normalized, confidence, rationale}] | `ate`(ate_score), `inputs.ate_debug`(raw/filtered), `stage1_ate` |
| **ATSA** | `AspectSentimentStage1Schema` | `aspect_sentiments`: List[{aspect_term, polarity, evidence, confidence}] | `atsa`(atsa_score), `inputs.aspect_sentiments`, `inputs.sentence_sentiment`(대표 없을 때) |
| **Validator** | `StructuralValidatorStage1Schema` | `structural_risks`, `consistency_score`, `correction_proposals` | `validator` 배열 중 stage=stage1 블록 |

- **튜플 형태 (Stage1)**  
  - **원시**: ATSA의 `aspect_sentiments` → 항목당 (aspect_term, polarity) + evidence 등.  
  - **집계용 추출**: scorecard의 `runtime.parsed_output.final_result.stage1_tuples` 또는 `process_trace`의 stage1 ATSA `output.aspect_sentiments` → **(aspect_ref, aspect_term, polarity)** 집합.  
  - structural_error_aggregator는 `_extract_stage1_tuples(record)`로 위 소스에서 Stage1 튜플 집합을 구함.

**평가 단위(EVAL_MODE): 튜플 추출 경로 고정**  
- "평가 모드"는 config 선언이 아니라 **각 extract 함수가 어떤 소스를 쓰는지**로 고정됨.  
- `--log_tuple_sources PATH`로 샘플당 `stage1_tuple_source`, `final_tuple_source`, `gold_tuple_source` 및 각 N을 TSV에 기록.  
- gold: `_extract_gold_tuples(record)` → `inputs.gold_tuples`.  
- stage1: `_extract_stage1_tuples(record)` → `final_result.stage1_tuples` \| `process_trace` stage1 ATSA.  
- final: `_extract_final_tuples(record)` → `final_result.final_tuples` \| `final_aspects` \| `inputs.aspect_sentiments`.  
- N_pred는 단일 값이 아님: `N_pred_final_tuples`(행 수), `N_pred_final_aspects`, `N_pred_inputs_aspect_sentiments`, `N_pred_used`(F1에 쓴 pred 튜플 총개수).  
- polarity: 모든 extract에서 `normalize_polarity()` 일원화. tuple 키: (aspect_ref, aspect_term, polarity); F1 매칭은 (aspect_term, polarity)만 사용(aspect_ref 무시).

### 2.2 Debate (선택)

| 담당 | 산출 스키마 | 수집·기록되는 데이터 | scorecard 반영 |
|------|-------------|----------------------|----------------|
| **Debate** | `DebateOutput` | `rounds`, `summary`, 토론 턴별 speaker/stance/message/key_points, **proposed_edits**(set_polarity/drop_tuple/set_aspect_ref 등) | `debate`: mapping_stats, mapping_coverage, mapping_fail_reasons, override_stats |

- **Debate review context**: SupervisorAgent의 `_build_debate_review_context()`가 **hint_entries(per-edit)** 와 **rebuttal_points(turn-level)** 를 만듦. **게이트 점수화는 `aspect_hints`만 사용**하며, aspect_hints는 **hint_entries(per-edit)** 로 먼저 채우고, aspect_map(turn-level)은 aspect_hints에 없는 aspect에만 fallback으로 추가. 유효 힌트 수(**valid_hint_count**: polarity_hint ∈ {positive, negative})가 0이면 skip_reason=**neutral_only**로 기록.
- **override_stats / debate_override_stats**: applied, skipped_low_signal, **skipped_neutral_only**, skipped_conflict, skipped_already_confident, override_candidate, override_applied, override_reason. skip_reason 세분화는 override_gate_debug_summary의 **low_signal_breakdown**(neutral_only, low_signal) 참고.
- Stage2 프롬프트에 debate review context가 주입되며, scorecard에는 매핑/override 통계와 (선택) meta.debate_review_context가 기록됨.

### 2.3 Stage2 (재분석·Validator 피드백 반영)

| 담당 | 산출 스키마 | 수집·기록되는 데이터 | scorecard 반영 |
|------|-------------|----------------------|----------------|
| **ATE** | `AspectExtractionStage2Schema` | `aspect_review`: List[{term, action, revised_span, reason, provenance}] | process_trace stage2 ATE output; 최종 반영 결과는 Moderator 입력으로 합쳐짐 |
| **ATSA** | `AspectSentimentStage2Schema` | `sentiment_review`: List[{aspect_term, action, revised_polarity, reason, provenance}] | process_trace stage2 ATSA output; 동일 |
| **Validator** | `StructuralValidatorStage2Schema` | `structural_risks`, `final_validation` 등 | `validator` 배열 중 stage=stage2 블록 |

- **튜플 형태 (Stage2/최종)**  
  - Moderator가 Stage1/Stage2 결과를 규칙(A–D)으로 합쳐 **최종 문장 극성 + 관점별 리스트**를 냄.  
  - **최종 튜플**: `final_result.final_aspects` (또는 final_tuples) — 각 항목 (aspect_term, polarity) + evidence 등.  
  - **Source of truth**: debate_summary.final_tuples가 있으면 SupervisorAgent.run()에서 final_aspect_sentiments(및 final_result.final_tuples)를 그에 맞춤. 없으면 기존 Stage1/Stage2 합침 결과 유지.  
  - structural_error_aggregator는 `_extract_final_tuples(record)`로 `final_result.final_tuples` → `final_result.final_aspects` → `inputs.aspect_sentiments` 순으로 fallback하여 최종 튜플 집합을 구함.

### 2.4 Moderator (규칙 기반)

| 담당 | 산출 스키마 | 수집·기록되는 데이터 | scorecard 반영 |
|------|-------------|----------------------|----------------|
| **Moderator** | `ModeratorOutput` | `final_label`, `confidence`, `rationale`, `selected_stage`, `applied_rules`, `decision_reason`, `arbiter_flags` | `moderator` 블록 전부 |

- 최종 출력: `FinalOutputSchema.final_result` = {label, confidence, rationale, **final_aspects**}.  
- scorecard에는 이 블록이 `runtime.parsed_output`(또는 동일 payload) 안에 들어가며, `inputs`에는 ate_debug / aspect_sentiments / sentence_sentiment / (선택) gold_tuples 가 보강됨.

### 2.5 Scorecard에만 추가되는 보조 데이터

| 출처 | 용도 | scorecard 필드 |
|------|------|----------------|
| run_experiments | uid별 gold 주입 (eval.gold_* 설정 시) | `inputs.gold_tuples` |
| scorecard_from_smoke / make_scorecard | RQ3 확장 risk 플래그 | `stage1_structural_risk`, `stage2_structural_risk` |
| scorecard_from_smoke / make_scorecard | Stage1↔최종 변경 여부·유형 | `stage_delta`: changed(라벨 또는 **pairs 집합** 변경), change_type(guided\|unguided\|none), related_proposal_ids, **override_candidate**, **override_applied**, **override_reason**, stage2_adopted_but_no_change |
| pipeline (SupervisorAgent, C2) | 메모리 retrieval/주입 | `memory`: retrieved_k, retrieved_ids, exposed_to_debate, prompt_injection_chars (meta.memory → scorecard.memory) |
| pipeline (SupervisorAgent, debate_override) | Debate 게이트 통계 | `meta.debate_override_stats`: applied, skipped_low_signal, **skipped_neutral_only**, skipped_conflict, skipped_already_confident, override_candidate, override_applied, override_reason. `meta.debate_override_skip_reasons`: action_ambiguity, L3_conservative 등. (선택) `meta.debate_review_context`: aspect_hints, rebuttal_points, aspect_map 등. |
| pipeline (aux_hf) | HF 외부 참조 신호 | `aux_signals.hf` |
| run_experiments | 데모/레이턴시/프로파일 | `meta` (profile, latency_ms, demo_*, manifest_path 등) |

---

## 3. 튜플 형태 요약

| 구분 | 저장 위치 | 형태 | 메트릭에서 사용 |
|------|-----------|------|-----------------|
| **Stage1 튜플** | final_result.stage1_tuples 또는 process_trace stage1 ATSA output | (aspect_ref, aspect_term, polarity) 집합 | tuple_f1_s1, triplet_f1_s1, fix_rate/break_rate 분모·분자 |
| **최종(Stage2) 튜플** | final_result.final_tuples / final_aspects 또는 inputs.aspect_sentiments | 동일 (aspect_ref, aspect_term, polarity) 집합 | tuple_f1_s2, triplet_f1_s2, delta_f1, fix_rate, break_rate, net_gain |
| **Gold 튜플** | inputs.gold_tuples (eval gold JSONL에서 uid 매칭 주입) | 동일 스키마 집합 | F1·fix/break/net 전부 (gold 있는 샘플만) |

- 채점/집계는 **aspect_term + polarity** 기준 매칭 (docs/absa_tuple_eval.md).  
- **polarity_conflict_rate_raw**: 대표 선택 없이, 같은 aspect_term에 polarity 2개 이상이면 conflict.  
- **polarity_conflict_rate** (= polarity_conflict_rate_after_rep): **대표 1개 선택 후** 같은 aspect에 서로 다른 polarity가 남는지로 판단 (has_polarity_conflict_after_representative). 둘 다 표에 출력.  
- **polarity_repair_rate**, **polarity_invalid_rate**: aggregator가 row.meta.polarity_repair_count·polarity_invalid_count + override_gate_summary(override_hint_repair_total·override_hint_invalid_total)에서 집계. 화이트리스트/편집거리 1~2 repair vs invalid 비율. 정의: `docs/polarity_canonicalization_policy.md`.

---

## 4. 최종 집계 데이터 (structural_metrics) 및 Triptych 표

**담당**: `scripts/structural_error_aggregator.py`  
**입력**: `scorecards.jsonl` (또는 merged_scorecards.jsonl)  
**출력**  
- **집계**: `structural_metrics.csv` (1행), `structural_metrics_table.md` (동일 내용 표)  
- **옵션**: `--export_triptych_table PATH` → 1행=1샘플 TSV/CSV (triptych_table). `--export_triptych_risk_details PATH` → triptych_risk_details.jsonl.

**참고**: `override_gate_debug.jsonl`·`override_gate_debug_summary.json`은 **SupervisorAgent**가 run 중/종료 시 `results/<run_id>/` 에 기록. aggregator는 scorecard의 debate_override_stats만 읽어 집계에 반영.

집계 시 **scorecard 한 줄 = 1샘플**로, 아래 함수들로 각 레코드에서 값을 읽어 합/비율을 냄.  
**Triptych 표**는 같은 scorecard를 읽어 샘플당 1행으로 쓰며, **stage1_to_final_changed**는 **pairs set 비교**(s1_pairs ≠ s2_pairs)로 고정. guided_change/unguided_drift는 scorecard의 stage_delta에서 읽고, pairs만 바뀌었는데 delta가 비어 있으면 unguided_drift=1로 추론.

| 메트릭/역할 | scorecard 소스 (함수/필드) |
|-------------|----------------------------|
| n | 행 개수 (profile_filter 적용 후) |
| aspect_hallucination_rate | has_hallucinated_aspect(r) → ate, inputs.ate_debug.filtered (drop) |
| alignment_failure_rate 등 | count_hallucination_types(r) → inputs.ate_debug.filtered drop_reason |
| implicit_grounding_rate 등 | rq1_grounding_bucket(r) → ate/atsa/inputs/implicit_grounding_candidate |
| polarity_conflict_rate | has_polarity_conflict_after_representative(r) → final_aspects/대표 선택 로직 |
| stage_mismatch_rate | has_stage_mismatch(r) → moderator.selected_stage vs stage1/2 |
| negation_contrast_failure_rate | count_negation_contrast_risks(r) → validator[*].structural_risks |
| guided_change_rate, unguided_drift_rate | stage_delta_guided_unguided(r) → stage_delta |
| risk_resolution_rate | has_stage1_structural_risk(r), has_stage2_structural_risk(r) (또는 scorecard.stage1_structural_risk, stage2_structural_risk) |
| risk_resolution_rate_legacy | count_stage1_risks(r), count_stage2_risks(r) |
| risk_flagged_rate | is_risk_flagged(r) → validator S1, negation/contrast, polarity_conflict, alignment_failure≥2 |
| residual_risk_rate | count_stage2_risks(r) > 0 (Validator S2만) |
| risk_affected_change_rate 등 | stage_delta.changed, is_resolved(Validator S1/S2 개수). stage_delta.changed는 make_scorecard에서 라벨 변경 또는 **pairs 변경** 기준으로 채워짐 |
| debate_* | debate.mapping_stats, debate.override_stats, meta.debate_override_stats (applied, skipped_low_signal, skipped_neutral_only, skipped_conflict 등) |
| override_* | debate.override_stats / meta.debate_override_stats, rows_applied/rows_conflict 서브셋. 세부 breakdown(neutral_only vs low_signal)은 override_gate_debug_summary.json |
| override_hint_invalid_total, override_hint_repair_total, override_hint_invalid_rate | override_gate_summary (override_gate_debug_summary.json)에서 읽음. SupervisorAgent run 종료 시 기록. 정의·공식: `docs/official_metrics.md` §3.2 |
| polarity_repair_n, polarity_invalid_n, polarity_repair_rate, polarity_invalid_rate | row.meta.polarity_repair_count·polarity_invalid_count 합 + override_gate_summary. strict 오타 정책(화이트리스트/편집거리 1~2). `docs/polarity_canonicalization_policy.md` |
| tuple_f1_s1, tuple_f1_s2, delta_f1, fix_rate, break_rate, net_gain, N_gold | compute_stage2_correction_metrics(rows) → _extract_gold_tuples, _extract_stage1_tuples, _extract_final_tuples |

---

## 5. 메트릭 표 산출에의 이용

### 5.1 structural_metrics_table.md

- **생성**: structural_error_aggregator의 `main()`  
- **과정**: scorecards.jsonl 로드 → profile_filter 적용 → `aggregate_single_run(rows)` 호출 → 반환 dict를 CSV 1행으로 저장 + 동일 내용을 Markdown 테이블로 저장.  
- **이용**:  
  - build_metric_report: `ensure_structural_metrics()`로 run_dir에 derived/metrics/structural_metrics.csv가 없으면 aggregator를 실행해 생성한 뒤, 해당 CSV를 읽어 **Overall** 등 HTML 테이블에 채움.  
  - aggregate_seed_metrics: 시드별 run_dir의 derived/metrics/structural_metrics.csv를 수집해 평균·표준편차 등 시드 집계에 사용.

### 5.2 metric_report.html

- **생성**: build_metric_report (`scripts/build_metric_report.py`)  
- **입력**: run_dir 내 manifest.json, scorecards.jsonl, derived/metrics/structural_metrics.csv (및 transition_summary 등)  
- **이용 방식**:  
  - **structural_metrics.csv**: F1, risk_*, polarity_conflict_rate, RQ1/RQ2/RQ3 지표 등 **전체 메트릭 값**의 주 소스. HTML의 “Overall” 열 등은 이 CSV를 우선 사용.  
  - **scorecards.jsonl**: compute_from_scorecards(scorecards)로 보조 통계(risk resolution, stage2 adoption, polarity_conflict 등) 계산 가능하나, **리포트는 structural_metrics.csv가 있으면 CSV 기준으로 통일**해 표시.  
  - **Stage1/최종 튜플**: aggregator 내 compute_stage2_correction_metrics에서 scorecard별 _extract_stage1_tuples / _extract_final_tuples / _extract_gold_tuples로 F1·fix/break/net_gain 계산 → structural_metrics.csv의 tuple_f1_s1, tuple_f1_s2, delta_f1, fix_rate, break_rate, net_gain으로 출력 → 동일 값이 metric_report.html에 반영.

### 5.3 Triptych 표 (derived/tables/triptych_table.tsv)

- **생성**: structural_error_aggregator의 `--export_triptych_table PATH` (기본 TSV, .csv면 CSV).
- **입력**: 동일 scorecards.jsonl.
- **내용**: 1행 = 1샘플(text_id). 식별(text_id, uid, profile), 입력(text 옵션), stage1/final/gold tuple_source·n_pairs·pairs 문자열, delta_pairs_count, **stage1_to_final_changed**(pairs set 비교), stage1_to_final_changed_from_delta(scorecard 기준), guided_change, unguided_drift, matches_*_vs_gold, new_correct_in_final, new_wrong_in_final, risk_flagged·stage1/2_structural_risk·risk_resolution, polarity_conflict_raw/after_rep, stage_mismatch, unsupported_polarity, aspect_hallucination, alignment_failure_count, validator_s1/s2_risk_ids, moderator_selected_stage, moderator_rules, **episodic_memory_effect**, **memory_enabled**, **memory_retrieved_n**, **memory_used**, **memory_ids_or_hash** 등.
- **용도**: 실험 결과를 샘플 단위로 한눈에 보는 사람용 표. risk_flagged=1인 행은 triptych_risk_details.jsonl로 드릴다운 가능.
- **평가 설계 참고**: gold span이 매우 긴 경우(B1)·aspect_term=""인 implicit gold(B2)는 matches=0이 정의상 나올 수 있음 → structural_error_aggregator 모듈 docstring 및 보조 지표 검토.

### 5.4 요약

| 산출물 | 담당 스크립트 | 입력 | 메트릭 표와의 관계 |
|--------|----------------|------|--------------------|
| scorecards.jsonl | run_experiments (make_scorecard) | outputs(payload) + gold 주입 | structural_metrics의 **유일한 샘플 단위 입력** |
| structural_metrics.csv | structural_error_aggregator | scorecards.jsonl | **메트릭 표의 수치 소스** (1 run = 1행) |
| structural_metrics_table.md | structural_error_aggregator | 동일 집계 결과 | CSV와 동일 내용의 Markdown 버전 |
| triptych_table.tsv (.csv) | structural_error_aggregator (--export_triptych_table) | scorecards.jsonl | **샘플 단위 사람용 표** (1행=1샘플). stage1_to_final_changed=pairs 비교, memory 열 포함 |
| triptych_risk_details.jsonl | structural_error_aggregator (--export_triptych_risk_details) | scorecards.jsonl | 리스크 드릴다운(validator raw, debate_override, ate_debug drop_reason 등) |
| metric_report.html | build_metric_report | manifest + scorecards + structural_metrics.csv | CSV 값을 읽어 HTML 테이블·차트로 시각화 |
| override_gate_debug.jsonl | SupervisorAgent (run 중) | (없음, run_id 결과 디렉터리) | aspect별 gate 레코드(valid_hint_count, skip_reason 등). 디버그·체크리스트 입력 |
| override_gate_debug_summary.json | SupervisorAgent (run 종료 시) | 동일 | skip_reason_count, low_signal_breakdown, skipped_neutral_only_n 등. T0/T1/T2 체크리스트 입력 |

### 5.5 실험·체크리스트 스크립트 (post-run)

| 스크립트 | 역할 | 입·출력 |
|----------|------|---------|
| **run_mini4_c2_t0_t1_t2.py** | C2 T0/T1/T2 3조건 연속 실행 → aggregator → override-gate 체크리스트 | `--run-id-suffix SUFFIX` 로 run_id 분리(예: experiment_mini4_validation_c2_t0_test_proposed). 결과: results/<run_id>_proposed, reports/mini4_c2_t0_t1_t2_checklist[_suffix].md |
| **run_c2_t0_and_checklist.py** | C2 T0 1회 실행 → aggregator → polarity/final_tuples 체크리스트 | 결과: results/<run_id>_proposed, reports/<run_id>_polarity_checklist.md |
| **checklist_override_gate_t0_t1_t2.py** | T0/T1/T2 override_gate_debug_summary·structural_metrics 비교 | --t0_dir, --t1_dir, --t2_dir, --out → override_applied_rate, skip_reason 분해, total/margin 분포 등 |
| **checklist_polarity_final_tuples.py** | polarity_hint 생성 로직·total/margin 0 원인·final_tuples 정책 점검 | --run_dir → reports/<run_id>_polarity_checklist.md (1–1~3–3, A/B/C 분류) |
| **diagnose_epm_proposed_edits.py** | EPM proposed_edits 빈 케이스: raw_response vs 파서 구분 | --run_dir 또는 --traces → stdout (empty_but_raw_has_set_polarity vs agent empty) |

- 논문 메트릭 정의·역할: `docs/metrics_for_paper.md`. RQ 메트릭 필드 매핑: `docs/rq_metrics_field_mapping.md` 참고.

---

## 6. 담당자(컴포넌트) 요약

| 단계 | 담당 | 산출/기록 |
|------|------|-----------|
| 데이터 로드 | run_experiments | config data.* / eval.gold_* → InternalExample, uid_to_gold |
| 1샘플 추론 | SupervisorAgent (ATE→ATSA→Validator→Debate→Stage2→Moderator) | FinalOutputSchema 1건 (outputs.jsonl 1줄). debate_override 사용 시 results/<run_id>/override_gate_debug.jsonl에 aspect별 레코드 추가 |
| Debate review context | SupervisorAgent._build_debate_review_context | hint_entries(per-edit), rebuttal_points(turn-level), aspect_hints. 게이트는 aspect_hints만 사용. run 종료 시 override_gate_debug_summary.json 1회 기록 |
| Scorecard 생성 | run_experiments 내 make_scorecard(payload) | scorecards.jsonl 1줄 (정규화·ate/atsa/validator/moderator/stage_delta/inputs/memory 등). stage_delta는 라벨 또는 pairs 변경 기준, override_candidate/override_applied/override_reason 포함 |
| Trace 기록 | run_experiments | traces.jsonl 1줄 (case trace) |
| 메트릭 집계 | structural_error_aggregator | scorecards.jsonl → structural_metrics.csv, structural_metrics_table.md. debate_override_* 는 meta.debate_override_stats(및 debate.override_stats)에서 읽음. 옵션: triptych_table.tsv, triptych_risk_details.jsonl |
| 리포트 생성 | build_metric_report | manifest + scorecards + structural_metrics.csv → metric_report.html |
| 시드 집계 | aggregate_seed_metrics | 시드별 scorecards/structural_metrics 수집·머지·평균 등 |

---

## 7. 메트릭 표(CSV/MD) 항목 ↔ scorecard 소스 매핑

structural_metrics_table.md / structural_metrics.csv의 각 항목이 **어떤 scorecard 필드·함수에서 계산되는지** 요약합니다.

| 메트릭 (표 항목) | scorecard 소스 (aggregator 내) |
|------------------|--------------------------------|
| n | 행 수 (profile_filter 적용 후) |
| aspect_hallucination_rate | has_hallucinated_aspect(r) → ate, inputs.ate_debug.filtered (drop) |
| alignment_failure_rate | count_hallucination_types(r)[alignment_failure] → inputs.ate_debug.filtered drop_reason |
| filter_rejection_rate | count_hallucination_types(r)[filter_rejection] |
| semantic_hallucination_rate | count_hallucination_types(r)[semantic_hallucination] |
| implicit_grounding_rate | rq1_grounding_bucket(r)==implicit |
| explicit_grounding_rate | rq1_grounding_bucket(r)==explicit |
| explicit_grounding_failure_rate | rq1_grounding_bucket(r)==explicit_failure |
| unsupported_polarity_rate | rq1_grounding_bucket(r)==unsupported |
| polarity_conflict_rate | has_polarity_conflict_after_representative(r) → final_aspects 대표 선택 후 동일 aspect 극성 충돌 |
| stage_mismatch_rate | has_stage_mismatch(r) → moderator.selected_stage vs stage1/2 |
| negation_contrast_failure_rate | count_negation_contrast_risks(r) → validator[*].structural_risks (risk_id) |
| guided_change_rate | stage_delta_guided_unguided(r)[0] → stage_delta.change_type==guided. stage_delta는 make_scorecard에서 라벨 또는 pairs 변경 시 채워짐 |
| unguided_drift_rate | stage_delta_guided_unguided(r)[1] → stage_delta.change_type==unguided. Triptych에서는 pairs만 바뀌었는데 delta 비어 있으면 unguided_drift=1 추론 |
| risk_resolution_rate | has_stage1_structural_risk(r), has_stage2_structural_risk(r) 또는 scorecard.stage1_structural_risk, stage2_structural_risk |
| risk_resolution_rate_legacy | count_stage1_risks(r), count_stage2_risks(r) |
| risk_flagged_rate | is_risk_flagged(r) → validator S1 OR negation/contrast OR polarity_conflict OR alignment_failure≥2 |
| residual_risk_rate | count_stage2_risks(r)>0 → validator stage2 structural_risks |
| risk_affected_change_rate 등 | stage_delta.changed, count_stage1/2_risks(r) 기반 is_resolved |
| debate_* | debate.mapping_stats, debate.override_stats, meta.debate_override_stats (applied, skipped_low_signal, **skipped_neutral_only**, skipped_conflict 등) |
| override_* | debate.override_stats / meta.debate_override_stats, rows_applied/rows_conflict 서브셋 + count_stage1/2_risks. override_gate_debug_summary.json의 low_signal_breakdown(neutral_only, low_signal)은 별도 파일 |
| override_hint_invalid_total, override_hint_invalid_rate | override_gate_debug_summary.json (SupervisorAgent run 종료 시 기록). aggregator가 override_gate_summary에서 읽어 표에 채움. 정의·공식: `docs/official_metrics.md` §3.2 |
| tuple_f1_s1, tuple_f1_s2, delta_f1 | _extract_stage1_tuples(r), _extract_final_tuples(r), _extract_gold_tuples(r) → precision_recall_f1_tuple |
| fix_rate, break_rate, net_gain | 동일 튜플 소스로 S1/S2 vs gold 매칭 → compute_stage2_correction_metrics |

- **튜플 소스**: Stage1 = final_result.stage1_tuples 또는 process_trace stage1 ATSA aspect_sentiments. 최종 = final_result.final_tuples / final_aspects 또는 inputs.aspect_sentiments. Gold = inputs.gold_tuples.
- **Triptych 전용**: stage1_to_final_changed는 **pairs set 비교**(tuples_to_pairs(s1) ≠ tuples_to_pairs(s2))로 고정. memory_enabled/retrieved_n/used/ids_or_hash는 scorecard.memory(또는 run_id의 C2 여부)에서 채움.

이 문서는 스테이지별 데이터·튜플 형태·집계·담당자와 메트릭 표(CSV/MD/HTML)·Triptych 표·override gate 산출 관계를 한곳에서 참조하기 위한 요약입니다.  
- **공식 메트릭 정의·집계 공식**: `docs/official_metrics.md` (Official). polarity_repair_rate / polarity_invalid_rate 미집계, override_hint_invalid_rate 등.  
- 스키마 상세: `docs/pipeline_output_formats.md`, `docs/schema_scorecard_trace.md`  
- 논문 메트릭·RQ 역할: `docs/metrics_for_paper.md`  
- RQ 메트릭 필드 매핑: `docs/rq_metrics_field_mapping.md`  
- Polarity hint·override gate 조치 요약: `reports/polarity_hint_fix_report.md` (해당 조치 적용 시)
