# 파이프라인에서 Structural Risk 정의

Structural Risk는 **Validator가 내는 risk**와 **집계용 확장 정의(extended)** 두 층으로 정의되어 있다.

---

## 1. Validator Structural Risk (에이전트 출력)

Validator Agent가 Stage1/Stage2 검증 시 출력하는 **structural_risks** 리스트가 1차 정의다.

### 스키마 (schemas/agent_outputs.py)

- **ValidatorStructuralRiskItem**: `risk_id`, `severity`, `span`, `description`
- **risk_id** 정규화용 enum: `VALIDATOR_RISK_IDS`
  - `NEGATION_SCOPE`
  - `CONTRAST_SCOPE`
  - `POLARITY_MISMATCH`
  - `EVIDENCE_GAP`
  - `SPAN_MISMATCH`
  - `OTHER`

### 프롬프트 (agents/prompts/validator_stage1.md)

- 에이전트에게 요구하는 타입: **NEGATION | CONTRAST | IRONY**
- 각 risk: `type`, `scope` (start/end), `severity` (high | medium | low), `description`
- “문장 구조(부정, 대조, 반어)에 의해 감성 결과가 왜곡되었을 가능성”을 검증하도록 정의

### Scorecard 정규화 (scripts/scorecard_from_smoke.py)

- process_trace의 Validator 출력에서 `structural_risks`를 읽어
- `type` / `risk_id`를 `_normalize_risk_type()`으로 위 enum에 매핑 (NEGATION→NEGATION_SCOPE, CONTRAST→CONTRAST_SCOPE 등)
- scorecard의 `validator` 배열: `[{ stage, structural_risks, proposals }]`

### 집계 시 사용 (scripts/structural_error_aggregator.py)

- **count_stage1_risks(record)**: `validator` 중 stage=stage1인 블록의 `structural_risks` **개수**
- **count_stage2_risks(record)**: stage=stage2인 블록의 `structural_risks` **개수**
- **count_negation_contrast_risks_stage1/2**: 위 리스트 중 `risk_id`에 NEGATION 또는 CONTRAST가 포함된 항목만 카운트

즉, **Validator가 부여한 structural_risks**가 “Validator 기준 Structural Risk”의 정의다.

---

## 2. 확장 Structural Risk (집계·RQ3용)

risk_resolution_rate 분모를 넓히기 위해 **stage1_structural_risk** / **stage2_structural_risk**가 별도로 정의되어 있다.

### Stage1 Structural Risk (has_stage1_structural_risk)

다음 **하나라도 참**이면 stage1 structural risk가 있다고 본다.

| 조건 | 출처 |
|------|------|
| Validator Stage1에서 structural_risks 개수 > 0 | count_stage1_risks(record) |
| polarity_conflict_after_representative | 대표 tuple 선택 후에도 동일 aspect에 상충 극성이 남음 (final tuples 기준) |
| Negation/Contrast risk가 Stage1에 존재 | count_negation_contrast_risks_stage1(record) > 0 |
| alignment_failure drop 개수 ≥ 2 | ATE filtered drop 중 drop_reason=alignment_failure |
| RQ1 grounding bucket = explicit_failure | rq1_grounding_bucket(record) == "explicit_failure" |

- **polarity_conflict_after_representative**: aspect별로 대표 1개 선택(explicit > implicit, confidence, drop_reason 없음) 후, 같은 aspect에 서로 다른 polarity가 남아 있으면 True.
- **explicit_failure**: 명시적 추론 실패 버킷 (evidence/grounding 실패로 판단된 경우).

### Stage2 Structural Risk (has_stage2_structural_risk)

“Stage2에서도 유지되는 risk”만 포함한다. **resolution 분모를 쓸 수 있도록** polarity_conflict, alignment_failure, explicit_failure는 제외한다.

| 조건 | 출처 |
|------|------|
| Validator Stage2에서 structural_risks 개수 > 0 | count_stage2_risks(record) |
| Negation/Contrast risk가 Stage2에 존재 | count_negation_contrast_risks_stage2(record) > 0 |

- polarity_conflict, alignment_failure ≥ 2, explicit_failure는 “최종 상태” 지표라 stage2 전용 카운트에 넣지 않음.

---

## 3. Outcome (RQ) vs Process (Internal Diagnostic)

**논문/리포트에서 RQ 결론에 사용 가능한 지표는 Outcome (RQ)만이다.** Process 지표는 Validator 수준 진단용이며, outcome-level 오류 감소로 해석하지 않는다.

### Outcome Metrics (RQ) — paper-claimable only

| 메트릭 | 역할 |
|--------|------|
| **SeverePolarityErrorRate (L3)** | 핵심. Aspect는 gold와 매칭, polarity만 불일치 (L4/L5 제외). |
| **polarity_conflict_rate** | 핵심. 동일 aspect 내 극성 충돌 (대표 선택 후). |
| **generalized_f1@0.95** | 보수적 보조. Neveditsin et al. 변형 (θ=0.95). |
| **tuple_agreement_rate** (RQ2) | 핵심. N회 실행 시 최종 튜플 집합 완전 일치 비율 (n_trials≥2). |
| **tuple_f1_s2** | Gold 기준 (aspect_term, polarity) F1. |

⚠️ **risk_*** prefix 지표는 Outcome 지표에서 제외 (혼동 방지).

### Process Control Metrics (Internal)

| 메트릭 | 역할 |
|--------|------|
| **risk_resolution_rate** / **validator_clear_rate** | 진단. "This metric reflects validator-level resolution and is not interpreted as an outcome-level error reduction." |
| **validator_residual_risk_rate** | 내부 점검. Stage2 Validator structural_risks>0 비율. 최종 출력 품질 리스크(예: polarity conflict) 미포함. |

- **outcome_residual_risk_rate**: 내부 통합 진단용. 논문 RQ 주장에는 Outcome (RQ) 테이블의 위 메트릭만 사용.

---

## 4. 사용처 요약

| 개념 | 정의 위치 | 사용 예 |
|------|------------|----------|
| **Validator structural risk** | Validator 출력 스키마 + conditions/aggregator 카운트 | validator_clear_rate, validator_residual_risk_rate, count_stage1_risks, count_stage2_risks, negation_contrast_failure_rate |
| **Stage1 structural risk (확장)** | has_stage1_structural_risk | validator_clear_rate 분모, scorecard.stage1_structural_risk |
| **Stage2 structural risk (확장)** | has_stage2_structural_risk | validator_clear_rate 분자(해소 = s1 True & s2 False), scorecard.stage2_structural_risk |
| **risk_flagged (확장)** | validator risk OR negation/contrast OR polarity_conflict OR alignment_failure ≥ 2 | risk_flagged_rate |
| **Outcome 잔여 위험** | outcome_residual_risk(r) = S2 risk OR polarity_conflict OR unsupported OR negation/contrast | outcome_residual_risk_rate |

---

## 5. 요약 표

| 구분 | 포함 조건 |
|------|------------|
| **Validator Structural Risk** | Validator가 내는 structural_risks (risk_id: NEGATION_SCOPE, CONTRAST_SCOPE, POLARITY_MISMATCH, EVIDENCE_GAP, SPAN_MISMATCH, OTHER) |
| **Stage1 확장** | Validator S1 risk **OR** polarity_conflict(대표 선택 후) **OR** Negation/Contrast S1 **OR** alignment_failure ≥ 2 **OR** explicit_grounding_failure |
| **Stage2 확장** | Validator S2 risk **OR** Negation/Contrast S2 (resolution 계산용으로만 사용) |

- **코드**: Validator 스키마·프롬프트 → `schemas/agent_outputs.py`, `agents/prompts/validator_stage1.md`  
- **집계·확장 정의**: `scripts/structural_error_aggregator.py` (count_stage1_risks, count_stage2_risks, has_stage1_structural_risk, has_stage2_structural_risk)  
- **Scorecard**: `scripts/scorecard_from_smoke.py` (validator 정규화, stage1_structural_risk / stage2_structural_risk 기록)

---

## 6. validator_clear_rate (Risk Resolution) vs 오답→정답 correction rate (fix_rate)

### 같은 개념인가?

**아니요.** 서로 다른 정의를 쓰는 별도 메트릭이다.

| 메트릭 | 정의 | 기준 |
|--------|------|------|
| **validator_clear_rate** (Risk Resolution) | Stage1에서 structural risk가 있던 샘플 중, Stage2에서 그 risk가 **해소된** 비율. 분모 = stage1_structural_risk True 개수, 분자 = 그중 stage2_structural_risk False 개수. | **Risk 기준** (gold 없음). “구조적 위험이 S2에서 사라진 비율”. |
| **fix_rate** (correction rate) | Stage1이 **gold 대비 오답**이던 샘플 중, Stage2에서 **gold 대비 정답**이 된 비율. 분모 = need_fix (S1 오답), 분자 = n_fix (S1 오답 → S2 정답). | **Gold 기준**. “오답 → 정답 전환 비율”. |

- **validator_clear_rate**: structural risk 유무만 본다. 정답/오답과 직접 대응하지 않는다 (risk 해소 ≠ 반드시 정답).
- **fix_rate**: gold와의 일치 여부로 “오답/정답”을 정의하고, “오답→정답”만 비율로 낸다.

따라서 **validator_clear_rate(구 risk_resolution_rate)를 “오답→정답 correction rate”와 동일한 개념으로 보면 안 되고**,  
오답→정답 관점의 지표는 **fix_rate**를 사용해야 한다.

### Correction rate (fix_rate)는 파이프라인에 산출되는가?

**예.** Gold가 있는 run에서 다음처럼 집계·산출된다.

- **집계**: `scripts/structural_error_aggregator.py`의 `compute_stage2_correction_metrics(rows)`에서 gold 기준으로 S1/S2 tuple set을 비교해 `n_fix`(S1 오답 → S2 정답), `need_fix = n_fix + n_still`(S1 오답 샘플 수)를 구하고, **fix_rate = n_fix / need_fix** 로 계산.
- **산출**: 위 결과가 `aggregate_single_run()` 안에서 `out["fix_rate"]` 등으로 합쳐지며, **structural_metrics.csv / structural_metrics_table.md** 에 포함된다.  
  함께 나가는 gold 기반 메트릭: `tuple_f1_s1`, `tuple_f1_s2`, `delta_f1`, **fix_rate**, **break_rate**, **net_gain**, `N_gold`, `gold_available`.
- **리포트**: `scripts/build_metric_report.py`에서 Fix = “S1 오답 → S2 정답”, Break = “S1 정답 → S2 오답”으로 표시.

정리하면, **오답→정답 correction rate에 해당하는 지표는 fix_rate**이며, **이미 파이프라인 메트릭으로 집계·산출되고 있다.**
