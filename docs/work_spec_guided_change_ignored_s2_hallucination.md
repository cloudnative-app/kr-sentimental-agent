# 작업명세서: guided_change·ignored_proposal·S2·hallucination 개선

**주의:** 이 문서는 **어떤 것을 어떤 순서로 변경할지**만 정의합니다. **아직 아무 코드/설정도 수정하지 않습니다.**

---

## 현재 구조에서의 문제 요약

| 현상 | 수치 예 | 해석 |
|------|---------|------|
| risk_flagged_rate ≈ 0.142 | 위험 탐지됨 | 정상 |
| risk_resolution_rate = 1 | 위험 “해결”로 집계됨 | resolution = risk 개수 감소로 정의됨 (change applied 아님) |
| guided_change_rate = 0 | guided change 없음 | Validator proposal 적용이 한 번도 성공하지 않거나, change_type 판정이 과도하게 엄격함 |
| ignored_proposal_rate ≈ 0.88 | 제안 무시 비율 매우 높음 | 한 바구니로만 집계되어 원인 불명 |
| unguided_drift_rate ≈ 0.1, delta_f1 < 0 | S2가 F1을 깎음 | S2가 “guided refinement”가 아니라 “unguided regeneration”에 가깝게 동작 |
| aspect_hallucination / unsupported_polarity 높음 | 측정 과대 추정 가능 | span mismatch vs 진짜 out-of-text 환각 미구분 |

---

## 1순위: “guided_change가 0인가” 수정

### 1-1) Change Trigger·Resolution 정의 점검 및 용어 정리

**목표:**  
- resolution이 “change applied”인지 “validator passes(risk 감소)”인지 명확히 하고,  
- “해결”이라는 단어를 “수정 적용”과 “pass만”으로 혼용하지 않도록 함.

**작업 항목 (순서대로)**

| # | 대상 | 작업 내용 |
|---|------|-----------|
| 1.1.1 | **정의 문서화** | `docs/pipeline_structure_and_rules.md` 또는 `docs/schema_scorecard_trace.md`에 다음 정의를 명시: (a) **risk_resolution_rate** = (stage1_risks - stage2_risks) / stage1_risks → “위험 개수 감소율” (수정 적용 여부와 무관). (b) **guided_change** = stage_delta.changed && 최소 1건의 correction_applied_log.applied == True. (c) “resolution”이 “pass” 의미일 때는 **risk_passed_without_change** 등으로 용어 분리 권장. |
| 1.1.2 | **structural_error_aggregator.py** | 출력 필드 또는 주석에서: `risk_resolution_rate` 설명을 “(stage1_risk_count - stage2_risk_count) / stage1_risk_count, i.e. risk count decrease, not necessarily change applied”로 명확히 함. 필요 시 `risk_resolved_with_change` / `risk_resolved_without_change` 변수명을 **risk_passed_with_change** / **risk_passed_without_change**로 변경 검토(기존 키 호환을 위해 별도 키로 추가 후 deprecated 처리 가능). |
| 1.1.3 | **scorecard_from_smoke.py `_build_stage_delta`** | `change_type = "guided"` 조건 점검: 현재 `guided = any(log.get("applied") for log in correction_log)`. Validator proposal만 적용 로그에 남고, ATE/ATSA review로 인한 변경은 correction_applied_log에 없을 수 있음. → **guided** 정의 확장 검토: “Validator proposal 1건 이상 적용” 또는 “ATE/ATSA review 중 proposal과 연관된 변경 1건 이상” 등. 확장 시 correction_applied_log에 ATE/ATSA 적용 여부도 기록할지 결정. |
| 1.1.4 | **build_metric_report.py** | 리포트/테이블에서 “Risk Resolution Rate” 옆에 툴팁 또는 각주: “Resolution = risk count decrease (stage1→stage2); not necessarily change applied.” 추가. |

**산출물:**  
- 정의·용어가 문서와 코드 주석에 반영됨.  
- (선택) `risk_passed_without_change` 등 신규/대체 키로 논문·리포트에서 “해결” 오해 방지.

---

### 1-2) “제안 무시율 0.88”을 0.5 이하로 낮추기 — 제안 무시 사유 분리

**목표:**  
- ignored_proposal_rate를 “한 바구니”가 아니라 **(A)(B)(C)(D)** 로 쪼개서,  
- 어떤 종류의 무시가 많은지 파악하고, 리허설 단계 목표치 **ignored_proposal_rate ≤ 0.6**, **guided_change_rate 0.1~0.2** 로 맞출 수 있게 함.

**작업 항목 (순서대로)**

| # | 대상 | 작업 내용 |
|---|------|-----------|
| 1.2.1 | **scorecard / run_experiments** | scorecard 또는 outputs에 “제안 무시” 사유를 남기기: (A) 제안 불가능(span이 입력에 없음 등), (B) 제안 모호, (C) 다른 제약과 충돌, (D) 수정했으나 효과 없음. 이를 위해 `_apply_stage2_reviews`의 correction_applied_log에 이미 있는 `reason`을 분류: 예) target_aspect not found → (A), applied but label unchanged → (D) 등. 필요 시 `ignore_reason` enum 필드 추가. |
| 1.2.2 | **structural_error_aggregator.py** | ignored_proposal_rate 계산 시 (A)(B)(C)(D)별 카운트 추가. 출력 CSV/딕셔너리에 `ignored_proposal_rate_A`, `ignored_proposal_rate_B`, … 또는 `ignored_proposal_by_reason` 맵 추가. |
| 1.2.3 | **build_metric_report.py** | “제안 무시율” 테이블에 (A)(B)(C)(D) breakdown 컬럼 또는 서브테이블 추가. 목표치 문구: “리허설 목표: ignored_proposal_rate ≤ 0.6, guided_change_rate 0.1~0.2.” |
| 1.2.4 | **실험·튜닝** | (A)(B)(C)(D) 분포 확인 후, 제안 형식·매칭 로직(target_aspect, span) 조정으로 “불가능/모호” 비율 감소. |

**산출물:**  
- 제안 무시가 (A)(B)(C)(D)로 구분되어 집계·리포트에 표시됨.  
- 이를 바탕으로 ignored_proposal_rate ≤ 0.6, guided_change_rate 0.1~0.2 달성 가능.

---

## 2순위: “S2가 항상 F1을 깎는가” — S2를 guided refinement로 전환

### 2-1) S2를 unguided regeneration이 아닌 edit-only(패치)로 제한

**목표:**  
- S2가 “전체 재생성”이 아니라 **수정이 필요한 항목만 패치**하도록 하고,  
- **unguided_drift_rate ≤ 0.02**, **delta_f1 평균 0 근처**로 만듦.

**작업 항목 (순서대로)**

| # | 대상 | 작업 내용 |
|---|------|-----------|
| 2.1.1 | **ATE/ATSA Stage2 스키마·프롬프트** | Stage2 출력을 “전체 목록”이 아니라 **“이 필드만 수정해라”** 형태로 제한: 예) aspect_review / sentiment_review만 허용하고, “나머지는 copy-forward”를 프롬프트와 스키마에 명시. 현재도 aspect/aspect_sentiments 금지가 있으나, **review 항목 수**를 “위험/제안과 직접 연관된 것만”으로 제한하는 옵션 검토. |
| 2.1.2 | **_apply_stage2_reviews** | “전체 교체”가 일어나지 않도록: Validator proposal → ATE review → ATSA review 순서 유지하되, **review가 없는 aspect/sentiment는 무조건 Stage1 값 유지**인지 확인. 이미 그렇게 동작하면, “변경이 없는 항목은 그대로 둠”을 코드 주석으로 명시. |
| 2.1.3 | **structural_error_aggregator / 메트릭** | unguided_drift_rate 정의 확인: change_type == "unguided"인 샘플 비율. guided 정의 확장(1-1) 후 unguided = changed && !guided 로 일관되게 유지. 목표: **unguided_drift_rate ≤ 0.02**. |
| 2.1.4 | **실험** | delta_f1 평균이 0 근처로 오는지 확인 후, 필요 시 Stage2 프롬프트에서 “변경할 항목만 나열, 나머지 유지” 문구 강화. |

**산출물:**  
- S2가 “수정 필요한 항목만 패치”로 동작함이 코드·프롬프트에 반영됨.  
- unguided_drift_rate ≤ 0.02, delta_f1 ≈ 0 목표로 모니터링 가능.

---

## 3순위: aspect_hallucination / unsupported_polarity 과대 추정 완화

### 3-1) Hallucination을 H1(Out-of-text) vs H2(In-text span mismatch)로 분리

**목표:**  
- “환각”을 **진짜 out-of-text**와 **텍스트 안에 있으나 span 불일치**로 나누어,  
- 측정·논문에서 “span alignment error”로 재정의 가능하게 함.

**작업 항목 (순서대로)**

| # | 대상 | 작업 내용 |
|---|------|-----------|
| 3.1.1 | **has_hallucinated_aspect / ate_score** | 현재 hallucination_flag = (filtered drop 존재 여부). **H1**: 모델이 뽑은 term이 **원문 텍스트에 전혀 등장하지 않음** (out-of-text). **H2**: 원문에는 있으나 **span이 gold/입력과 불일치** (substring, 대소문자, 복수형, tokenizer 경계 등). ate_score 또는 scorecard/aggregator에서 H1/H2 구분 가능하도록: term in text 여부, span_text vs term 일치 여부 등으로 분류. |
| 3.1.2 | **structural_error_aggregator.py** | `aspect_hallucination_rate` 대신 또는 추가로 `aspect_hallucination_rate_H1`, `aspect_hallucination_rate_H2` 출력. 기존 `aspect_hallucination_rate`는 (H1+H2) 또는 호환용으로 유지할지 결정. |
| 3.1.3 | **build_metric_report.py** | 테이블에 “H1: Out-of-text”, “H2: In-text span mismatch” 행/컬럼 추가. 각주: “H2는 span alignment error로 재정의 가능.” |
| 3.1.4 | **문서** | 논문/리포트 초안에 “aspect hallucination” 정의를 H1/H2로 분리하고, H2는 “span alignment error”로 표현하는 문구 추가. |

**산출물:**  
- H1 vs H2가 집계·리포트에 나뉘어 표시됨.  
- 수치가 높을 때 대부분 H2인지 확인 가능하며, 논문에서 방어력 향상.

---

## 작업 순서 요약 (변경하지 않고 적용할 순서만)

1. **1순위**  
   - 1-1) resolution/guided 정의 및 용어 정리 (문서 → aggregator → scorecard _build_stage_delta → metric report).  
   - 1-2) 제안 무시 사유 (A)(B)(C)(D) 분리 (correction_applied_log 확장 → aggregator → metric report → 실험).

2. **2순위**  
   - 2-1) S2 edit-only 강화 (스키마/프롬프트 → _apply_stage2_reviews 검증 → aggregator/메트릭 → 실험).

3. **3순위**  
   - 3-1) H1/H2 hallucination 분리 (ate_score/aggregator → structural_metrics 출력 → metric report → 문서).

**의존성:**  
- 1-1에서 guided 정의를 확장하면 1-2의 “무시” 분류와 2-1의 unguided_drift 해석이 일관됨.  
- 1-2의 (A)(B)(C)(D)는 `_apply_stage2_reviews`의 reason 및 scorecard 스키마에 의존하므로, 1-1 다음에 진행하는 것이 안전함.

이 순서대로 구현하면, “guided_change 0”, “제안 무시율 과다”, “S2가 F1 깎음”, “hallucination 과대 추정”을 단계적으로 개선할 수 있습니다.
