# Stop-the-line 체크 및 구조적 정합성 점검

## 1.1 pass_rate 정의·판정 로직

### 현재 계산식

- **집계**: `structural_pass_rate = (샘플 중 summary.quality_pass == True 인 수) / N`
- **출처**: `scripts/build_metric_report.py` → `compute_from_scorecards()`: `pass_count = sum(1 for r in rows if (r.get("summary") or {}).get("quality_pass") is True)`

### 판정 조건 (boolean rule)

**quality_pass**는 **scorecard_from_smoke**에서 다음 규칙으로 설정됨:

- **quality_pass = True** 초기값.
- **quality_pass = False** 인 경우 (OR 조합):
  1. `targetless_expected` 이고 `sentence_sentiment` 없음 → `targetless_missing_sentence_sentiment`
  2. `ate.valid_aspect_rate` 이 None 이거나 < 0.5 → `low_valid_aspect_rate`
  3. `atsa.opinion_grounded_rate` 이 None 이거나 < 0.5 → `low_opinion_grounded_rate`
  4. `atsa.evidence_relevance_score` 이 None 이거나 < 0.5 → `low_evidence_relevance_score`

**즉, pass_rate는 risk_flagged / residual_risk / conflict 와 직접 대응하지 않음.**  
ATE·ATSA·policy 휴리스틱(valid_aspect, opinion_grounded, evidence_relevance) 기준.

### 집계 지표와의 연결

- **risk_flagged_rate**, **residual_risk_rate**, **polarity_conflict_rate** 는 `structural_error_aggregator`에서 별도 계산 (validator/moderator 기반).
- pass_rate와 이들은 **동일한 boolean rule이 아님**. 논문에서 “구조 품질 통과”를 risk/conflict 기준으로 재정의하려면, pass 판정을 `risk_flagged==0 AND residual_risk==0 AND polarity_conflict==0` 등으로 바꾸거나, 별도 지표(예: structural_risk_pass_rate)를 도입해야 함.

### 작업 반영

- **scorecard**: `summary.pass_reason_breakdown` 추가 (기존 `fail_reasons`와 동일 내용, 리뷰어 추적용).
- **문서**: 본 절로 판정 조건 명시.

---

## 1.2 polarity_conflict_rate 정의

### 현재 정의 (반영 후)

1. **polarity_conflict_rate** (RQ1): **동일 aspect span 내 polarity 충돌**만 사용.
   - `structural_error_aggregator`: `has_same_aspect_polarity_conflict(r)` — final_tuples 기준, 동일 aspect_term에 2개 이상 polarity면 True. **RuleM/Stage mismatch 참조 없음.**
   - `build_metric_report`: `_has_same_aspect_polarity_conflict(record)` 동일. struct 키 `polarity_conflict_rate` 유지.

2. **stage_mismatch_rate** (RQ2): **RuleM 적용** 또는 **stage1_ate.label != stage2_ate.label**.
   - `has_stage_mismatch(r)` 에만 RuleM/Stage 참조. 리포트 테이블에 **stage_mismatch_rate** 행 노출.

### 문제

- **polarity_conflict_rate = 1.0** 이 나오는 경우: aggregator 정의상 “모든 샘플에서 RuleM 적용 또는 Stage1≠Stage2”이면 1.0.
- **valid_aspect_rate = 1.0** 과 동시에 나올 수 있음 (서로 다른 차원).
- RQ1(구조적 위험)과 맞추려면 **“동일 aspect 내 상충”** 하나로 고정하고, Stage 간 불일치는 RQ2(flip-flop/variance)로 두는 것이 정합적.

### 권장 작업

- **polarity_conflict** 를 **동일 aspect (span) 내 polarity 충돌** 로 고정:
  - final_tuples 기준으로 aspect_term별 polarity 집합을 만들고, 동일 aspect에 2개 이상 polarity면 conflict.
- **RuleM / Stage1≠Stage2** 는 RQ2 지표(flip_flop_rate, variance) 또는 별도 “stage_mismatch” 로 분리.

### 작업 반영 (완료)

- **polarity_conflict_rate**: **동일 aspect span 내 polarity 충돌**만 사용 (final_tuples 기준, aspect_term별 polarity 집합에서 2개 이상이면 conflict).
- **stage_mismatch_rate** (RQ2): RuleM 적용 또는 stage1_label ≠ stage2_label 비율. `structural_error_aggregator` 및 CANONICAL_METRIC_KEYS에 추가됨.
- **build_metric_report** 및 **structural_error_aggregator** 모두 `_has_same_aspect_polarity_conflict` / `has_same_aspect_polarity_conflict` 로 통일.

### 검증 (점검 사항)

- **structural_error_aggregator.py**
  - **polarity_conflict** 쪽: `polarity_conflict_rate` 집계는 `has_same_aspect_polarity_conflict(r)` 만 사용 (final_tuples 기반, 동일 aspect 내 상충). `has_polarity_conflict` 는 legacy alias로 동일 함수 호출.
  - **RuleM / Stage mismatch**: `has_stage_mismatch(r)` 에만 존재 (moderator RuleM, stage1_ate.label != stage2_ate.label). `polarity_conflict_rate` 계산 경로에서는 **참조 없음**.
- **build_metric_report.py**
  - **참조 키**: `_has_polarity_conflict` → `_has_same_aspect_polarity_conflict` (RuleM/Stage 미참조). struct에서 읽는 키는 `polarity_conflict_rate` (동일). **stage_mismatch_rate** 는 리포트 테이블에 노출되도록 추가 필요 (아래 1.4·2.1 반영).
- **리포트 템플릿**: RQ/테이블에 **stage_mismatch_rate** 행 추가됨 (build_metric_report 수정 반영).

---

## 1.3 valid_aspect_rate vs aspect_hallucination_rate

### 현재 정의

| 지표 | 출처 | 의미 |
|------|------|------|
| **valid_aspect_rate** (scorecard ate) | scorecard_from_smoke | 해당 행에서 allowlist 필터 후 **1개 이상 aspect 유지**면 1.0, 없으면 None. |
| **valid_aspect_rate** (build_paper_tables) | build_paper_tables | **최종 triplet 1개 이상 있는 샘플 비율** (mean_bool(valid_triplet), valid_triplet = len(final_ts)>0). |
| **aspect_hallucination_rate** | structural_error_aggregator | **has_hallucinated_aspect(r)** 비율. ate.hallucination_flag 또는 (filtered drop) 존재. |

### 개념 충돌

- **valid_aspect_rate = 1.0** (paper_tables): “대부분 샘플에 final tuple이 1개 이상”.
- **aspect_hallucination_rate ≈ 0.8**: “대부분 샘플에서 hallucination_flag 또는 drop 발생”.
- 서로 **분모·분자·의미가 다름**: valid는 “샘플당 1개라도 있으면 유효”, hallucination은 “샘플당 drop/flag 있으면 홀루시네이션”.

### 권장 작업

- 지표 분리:
  - **aspect_detected_rate**: 최소 1개 aspect 출력된 샘플 비율.
  - **aspect_grounded_rate**: (정의 확정 후) evidence/span 일치 비율.
  - **aspect_hallucination_rate**: 기존 유지 (ate.hallucination_flag / drop 기반).
- 논문에는 **grounded / hallucination** 만 사용하고, “valid_aspect”는 내부 휴리스틱으로만 쓰거나 정의를 명시.

---

## 1.4 RQ2 self_consistency_exact

### 현재 동작

- **structural_error_aggregator**:
  - **단일 run**: `self_consistency_exact = 1.0`.
  - **merged scorecards** (동일 text_id에 여러 run): 동일 text_id 내에서 최종 레이블이 모두 같으면 1, 아니면 0; 그 비율을 집계.
- **build_paper_tables**: `compute_self_consistency()` — 여러 run artifact가 있을 때만 계산, 그렇지 않으면 None.

### CSV에서 비어 있는 이유

- **반복 추론(trials)** 이 없으면: 입력이 단일 run scorecards 뿐이라, aggregator는 1.0을 넣지만, paper_tables는 “n_runs_required” 미달로 None을 낼 수 있음.
- **runner/profile** 별로 trials 옵션이 다르면, 일부 run만 merged 되어 self_consistency가 채워짐.

### 권장 작업

- **RQ2용 runner**는 **trials ≥ 3** 강제 (동일 config로 여러 run 후 scorecards 머지).
- **self_consistency_exact** 는 **CANONICAL_METRIC_KEYS** 에 이미 포함 → 스키마상 필수 필드로 출력. 단일 run이면 1.0으로 채움.

---

## 2.1 RQ별 지표 재배치

- **RQ1**: 구조적 위험만 (risk_flagged, residual_risk, risk_resolution, polarity_conflict 등).
- **RQ2**: 안정성/변동성만 (self_consistency, flip_flop_rate, variance).
- **RQ3**: 토론·메모리 개입 효과만 (override_applied_rate, override_success_rate 등).
- **cost, latency, tokens** → Appendix로 이동 (현재 build_metric_report에서 Efficiency 섹션 등에 분리 가능).

---

## 2.2 override_success_rate 정의 일관성

### 현재 정의 (structural_error_aggregator)

- **override_success_rate** = (applied 중에서 **stage1_risks > 0 이고 stage2_risks < stage1_risks** 인 샘플 수) / (applied 샘플 수).
- **gold / correctness 미사용.** risk 개수만 사용.

### 확인

- 코드에서 `correctness`, `gold`, `decision.correct` 참조 없음. **risk delta 기반 계산만 사용** → 요구사항 충족.

---

## 2.3 Memory OFF 조건의 비용/지연

### 현재 C1(메모리 OFF) 경로

- **episodic_orchestrator**: `_flags.retrieval_execute = False` (C1).
- **get_slot_payload_for_current_sample**:
  - `retrieval_execute == False` → **store.load(), retriever.retrieve() 호출 안 함.** advisories = [].
  - 슬롯은 **항상 생성** (DEBATE_CONTEXT__MEMORY 존재, 빈 retrieved).
- **append_episode_if_needed**: C1에서는 `store_write` False → **에피소드 append 안 함.**

즉, **retrieval / advisory builder 호출은 C1에서 차단됨.**  
68초 지연은 **토론 라운드(debate)** 또는 Stage1/Stage2/Moderator 호출에서 발생할 가능성이 큼.

### 권장 작업

- **stage별 latency 로그 분리**: 각 stage(ATE, ATSA, Validator, Debate, Stage2, Moderator)별로 latency_ms 기록해, 어느 단계에서 지연이 큰지 확인.
- **memory OFF 시**: retrieval / advisory builder 호출이 없음을 로그 또는 integrity_check에 명시 (이미 C1 경로에서 호출 없음).

---

## 요약 체크리스트

| 항목 | 상태 | 비고 |
|------|------|------|
| 1.1 pass_rate 규칙 문서화 | 완료 | 본 문서 + scorecard에 pass_reason_breakdown 추가 |
| 1.2 polarity_conflict 정의 고정 | 문서화 | “동일 aspect 내 충돌”로 통일 시 코드 수정 필요 |
| 1.3 valid_aspect vs aspect_hallucination 분리 | 문서화 | aspect_detected / grounded / hallucination 분리 권장 |
| 1.4 self_consistency 필수 필드 | 확인 | CANONICAL에 포함, 단일 run 시 1.0 |
| 2.1 RQ 테이블 분리 | 권장 | cost/latency → Appendix |
| 2.2 override_success gold 미참조 | 확인 | risk delta만 사용 |
| 2.3 Memory OFF retrieval 차단 | 확인 | C1에서 retrieval/advisory 미호출 |
