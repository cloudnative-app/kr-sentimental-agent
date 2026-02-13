# ABSA 파이프라인 End-to-End 정합성 점검 보고서

**Run**: `experiment_mini4_validation_c2_t0_proposed` | **Seed**: 42 (mini4 C2)

---

## 0) 즉시 수정한 표현

- **체크리스트 A-1**: outputs/scorecards/traces 레코드 수 = 10 → **감사 시점에 7건이면 [ ] FAIL (7/10)**. 현재 디렉터리 기준 10/10이어도, 과거 7건으로 감사했으면 “7인 원인 규명 + 재실행으로 10/10 확보 후”에만 PASS.
- **"Fixed: 14"**: 재현 가능한 증거(커밋 해시 / 재실행 결과) 없이 단정하지 않음. **“코드 수정 반영 후 재실행·검증 필요”**로 기술.

---

## 1) 최우선 Blocker: 왜 10이 아니라 7인가

- **manifest**: `dataset.processing_count=10`, `dataset.split_counts.valid=10`, `processing_splits=["valid"]`. 입력 파일 `mini4/valid.csv` 행 수 = 10. **config 상 10이 기대값.**
- **run_experiments**: `max_examples`, `early_stop`, `debug_n`, `profile_filter` 등 **7건에서 중단되는 조건식/옵션은 코드에 없음.**  
  → 7건만 나온다면 **런 중단**(예외/타임아웃/레이트리밋/재시도 실패 등) 가능성.
- **결론**
  - **원인이 config면**: “기대가 10이 아니라 7”로 문서 수정.
  - **원인이 런 실패면**: **재실행해서 10/10 확보한 뒤에만** 아래 항목들을 PASS 판정.
- **현재 파일 기준**: `outputs/scorecards/traces` 각 10건 확인 시 10/10. 감사 시점에 7이었으면 원인 규명 후 동일 config로 재실행 권장.

---

## A. End-to-End 파일 무결성

- outputs/scorecards/traces 레코드 수: **기대 10**. 감사 시점 7건이면 **[ ] FAIL (7/10)**.
- override_gate_debug_summary.json 존재(1개) + skip breakdown 포함: OK.
- manifest의 cfg_hash/run_id가 결과 디렉터리와 일치: OK.

---

## B. SoT/튜플 정책 (정의 + 불변식)

### 최종 튜플 SoT (단일 정의)

- **SoT = final_result.final_tuples.**  
  supervisor_agent.run()에서 final_aspects_list → tuples_to_list_of_dicts → final_result.final_tuples.  
  debate_summary.final_tuples 존재 시 final_aspect_sentiments를 그에 맞춘 뒤 final_aspects_list 빌드.  
  aggregator( structural_error_aggregator._extract_final_tuples ) 우선순위: final_result.final_tuples → final_aspects → inputs.aspect_sentiments.

### 불변식 (런타임 검사)

- **Invariant S1**: debate_summary.final_tuples가 존재하면 → final_result.final_tuples와 **정렬/정규화 후 동일**해야 함.  
  **검증 결과**: `pipeline_integrity_verification_result.json` 기준 **S1 실패 9건** (text_id 목록 포함).  
  → tuple 표현 차이(aspect_term 객체 vs 문자열, polarity 정규화) 또는 실제 불일치. **정규화 규칙 통일 후 재검증 필요.**
- **Invariant S2**: final_result.final_tuples ↔ final_result.final_aspects **동등성** (같은 튜플 집합으로 환원).  
  검증 스크립트에서 **S2 실패 10건** — final_aspects 추출 방식과 비교 로직 재점검 필요.
- **Invariant S3**: scorecards에서 aggregator가 읽은 최종 튜플 소스가 **항상 final_result.final_tuples**인지(fallback 0건).  
  **검증 결과**: fallback 0건 → **S3 통과.**

---

## C. Debate 신호 (polarity_hint)

- set_polarity(value=positive|negative) → aspect_hints에서 polarity_hint가 positive/negative로 반영되어야 함.  
  proposed_edits가 dict일 때 value/op/target 읽기 위해 `_edit_attr(e, key)` 사용 (neutral 환원 버그 대응).
- set_aspect_ref는 polarity 점수에서 제외 (weight 0 / polarity_hint None).
- drop_tuple 점수화 규칙(anti-signal neg): 코드/로그와 일치.

### Override Gate 검증 (2단계)

- **decision_applied_n=5**인 run 기준:
  - **Applied 5건**에 대해: hint→점수 경로 증거는 `pipeline_integrity_verification_result.json`의 **override_applied_hint_evidence** 참고 (valid_hint_count=2, neg_score=1.6, total=1.6, margin=1.6 등).
- **neutral_only 22~25건**에 대해:
  - 검증 결과: **전수 “hint_absent”** (valid_hint_count=0).  
  - **판정**: “힌트는 있는데 neutral_only”가 아니라 **“힌트 자체가 빈번히 없음”** → 토론 에이전트 프롬프트/출력 스키마가 ABSA에 도움 되게 설계되지 않은 상태(설계 문제) 가능성.  
  - “힌트 있었는데 neutral로 환원” 경로가 있으면 조건식/필드키 mismatch로 특정 필요.

---

## D. Override Gate (T0/T1/T2)

- T0 summary: decision_applied_n=5, skipped_neutral_only_n=22, low_signal=5, total_dist.max=1.6 등 (override_gate_debug_summary.json 참고).
- T1/T2 완화에도 applied가 0이면 → 게이트 역치가 아니라 **신호 생성/매핑/점수화 버그** 결론.
- total_dist.max=1.6이 계속 임계값에만 걸리는 패턴이면, 가중치/스케일이 지나치게 이산적이거나 힌트가 일부 케이스에서만 살아있는 상태일 수 있음.

---

## E. Stage2 리뷰 계약

- debate_review_context가 Stage2 입력(extra_context)에 포함됨(증거: supervisor._run_stage2).
- Stage2 output provenance는 _inject_review_provenance로 source:EPM/patch 등 생성.
- Stage2 리뷰 → Moderator 선택/규칙 → final_tuples 반영 경로 1개로 닫힘.

---

## F. Memory 계약/게이트 (로그 + 사용 가능성)

- scorecard meta.memory: retrieved_k, retrieved_ids, exposed_to_debate, prompt_injection_chars, memory_blocked_*, advisory_injection_gated 기록.
- **E2E 유효성**: `pipeline_integrity_verification_result.json`의 **memory_samples** 참고.  
  - retrieved episode가 stage2 입력에 실제 주입되었는지: prompt_injection_chars>0인 샘플 9/10건.  
  - 주입되었더라도 금지된 advisory/프롬프트 인젝션이 차단되는지: prompt_injection_chars, memory_block_reason, advisory_injection_gated로 케이스별 목록화 필요(현재 일부 scorecard에 advisory_injection_gated null).

---

## G. Aggregator/Metric 정합성

- **동일 run 내 3출력 일치**: scorecards.jsonl의 final tuple ↔ triptych_table.tsv의 final_pairs ↔ structural_metrics.csv의 N_pred_used / tuple_f1 사용 pred가 **동일한 pred 튜플**을 참조해야 함.
- **검증 결과**: `pipeline_integrity_verification_result.json`의 **metrics_pred_consistency** 기준 **pass=false**.  
  - 예: text_id 01230 (scorecard 2 pairs vs triptych 1 pair), 00692 (scorecard 3 pairs vs triptych 5 pairs) 등 **불일치 존재** → report builder 정합성 깨짐.  
  - “0인데 샘플에 존재” 같은 정의/추출 경로 불일치 제거 필요.

---

## 발견 요약 (pipeline_integrity_audit_findings.json)

- Blocker / Major / Minor 건수는 findings.json 참고.
- **Fixed: 14** → 재현 증거(커밋/해시/재실행 결과)로 검증 전까지 “수정 반영됨” 수준으로만 기술.

---

## 체크리스트 (요청 5) + 추가 체크리스트

### A. End-to-End 파일 무결성
- [ ] **outputs/scorecards/traces 레코드 수 = 10**  
  → 감사 시점 7이면 **[ ] FAIL (7/10)**. 원인 규명 후 재실행으로 10/10 확보 후 PASS.
- [x] override_gate_debug_summary.json 존재(1개) + skip breakdown 포함
- [x] manifest의 cfg_hash/run_id가 결과 디렉터리와 일치

### B. SoT/튜플 정책
- [x] 최종 튜플 SoT가 1개로 정의됨(문서+코드): final_result.final_tuples
- [x] aggregator tuple 추출 우선순위가 SoT와 동일
- [ ] **Invariant S1**: debate_summary.final_tuples ↔ final_result.final_tuples 동일 (검증 결과 9건 실패 → 재검증)
- [ ] **Invariant S2**: final_tuples ↔ final_aspects 동등 (검증 스크립트 로직·정규화 보완 후 재검증)
- [x] **Invariant S3**: aggregator final_tuple_source가 항상 final_result.final_tuples (fallback 0건)

### C. Debate 신호(핵심)
- [x] set_polarity → polarity_hint pos/neg 반영 (코드: _edit_attr)
- [x] drop_tuple 점수화 규칙(anti-signal) 코드/로그와 일치
- [x] set_aspect_ref는 polarity 점수에서 제외
- [x] neutral_only 원인 분해: 현재 run에서 전수 “hint_absent” (설계/에이전트 출력 이슈)
- [ ] total/margin=0 원인: “진짜 신호 없음” vs “버그” 결론 유지(재실행·증거로 검증)

### D. Override Gate(T0/T1/T2)
- [x] applied 케이스 100%에 대해 힌트→점수 경로 증거 확보 (override_applied_hint_evidence 참고)
- [x] neutral_only 케이스에서 “힌트 없음 vs 환원” 분해 표 제출 (전수 hint_absent)

### E. Stage2 리뷰 계약
- [x] debate_review_context가 stage2 입력에 포함됨(증거)
- [x] stage2 output provenance가 기대 스키마로 생성됨
- [x] stage2 리뷰가 moderator/최종 튜플에 반영됨(증거)

### F. Memory 계약/게이트
- [x] retrieval 메타가 scorecard에 항상 기록됨
- [ ] **memory: retrieved→주입→차단 로직이 케이스별로 기대대로 작동(샘플 목록 포함)**  
  → memory_samples 참고, advisory_injection_gated 등 보완 후 검증

### G. Aggregator/Metric 정합성
- [ ] **metrics: scorecards ↔ triptych ↔ structural_metrics 참조 pred 튜플이 동일(불일치 0건)**  
  → 현재 불일치 있음(metrics_pred_consistency.mismatches)

---

## 추가 체크리스트 (보고서에 그대로 반영)

- [ ] **E2E 레코드 수 10/10 달성**(미달 시 원인 규명 + 재실행)
- [ ] **Invariant S1**: debate_summary.final_tuples ↔ final_result.final_tuples 동일
- [ ] **Invariant S2**: final_tuples ↔ final_aspects 동등
- [x] **Invariant S3**: aggregator final_tuple_source가 항상 final_result.final_tuples (fallback 0건)
- [x] **override_gate**: applied 케이스 100%에 대해 힌트→점수 경로 증거 확보
- [x] **neutral_only** 케이스에서 “힌트 없음 vs 환원” 분해 표 제출
- [ ] **memory**: retrieved→주입→차단 로직이 케이스별로 기대대로 작동(샘플 목록 포함)
- [ ] **metrics**: scorecards ↔ triptych ↔ structural_metrics 참조 pred 튜플이 동일(불일치 0건)

---

## 검증 스크립트

- **SoT/게이트/메모리/메트릭 검증**:  
  `python scripts/pipeline_integrity_verification.py --run_dir results/experiment_mini4_validation_c2_t0_proposed --out reports/pipeline_integrity_verification_result.json`
- **산출**: `reports/pipeline_integrity_verification_result.json`  
  (e2e_record_count, invariant_s1_fail, invariant_s2_fail, invariant_s3_fallbacks, override_applied_hint_evidence, neutral_only_breakdown, memory_samples, metrics_pred_consistency)
