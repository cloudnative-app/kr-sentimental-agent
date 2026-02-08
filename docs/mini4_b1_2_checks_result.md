# mini4_b1_2 진단 결과 (6 checks)

**Scorecards**: `results/experiment_mini4_b1_2__seed42_proposed/scorecards.jsonl` (N=10)
**Metrics**: `results/experiment_mini4_b1_2__seed42_proposed/derived/metrics/structural_metrics.csv`

**적용된 코드 변경**: (1) ATSA Option B 완화 (str aspect_term 허용, evidence 없음=unknown/insufficient). (2) unsupported = 모든 judgement 실패 OR 선택 tuple 대응 judgement 실패. (4) override 적용 시 stage_delta.changed=True·change_type=guided 연결(scorecard 빌드 시). **기존 scorecards는 파이프라인 재실행 전**이므로 (1)(4) 반영된 scorecard는 아직 없음; (2)만 재집계에 반영되어 unsupported_polarity_rate 1.0→0.8로 변경됨.

---

## 체크 1 — Unsupported polarity 원인 1샘플 해부

**샘플**: index=1, text_id=nikluge-sa-2022-train-00797

### final_tuples (원본 필드)
- Tuple 1: `aspect_term`='자와선', `polarity`='negative', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']
- Tuple 2: `aspect_term`='순한 성분', `polarity`='neutral', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']
- Tuple 3: `aspect_term`='자와선', `polarity`='positive', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']

### unsupported 판정 True가 된 이유 (코드 경로)
`has_unsupported_polarity`: atsa.sentiment_judgements 중 **하나라도** 아래면 True:
- `j.get("issues")` truthy
- `j.get("opinion_grounded", True)` == False
- `j.get("evidence_relevant", True)` == False

- Judgement 1: `issues`=['opinion_not_grounded: aspect_term missing or not dict'], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**
- Judgement 2: `issues`=['opinion_not_grounded: aspect_term missing or not dict'], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**
- Judgement 3: `issues`=["opinion_not_grounded: span_text='할만큼 순' != aspect_term='순한 성분'"], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**
- Judgement 4: `issues`=["opinion_not_grounded: span_text='성분에' != aspect_term='자와선'"], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**

---

## 체크 2 — Polarity conflict "충돌 aspect key" 확인

**샘플**: index=0, text_id=nikluge-sa-2022-train-02829

### conflict를 만든 aspect key (정규화된 aspect_term)
집계 시 **정규화 없음**: final_tuples의 `aspect_term` 문자열 그대로 그룹핑.
- **'피부톤'** → polarity set = {'neutral', 'positive'}

### 해당 tuple들의 원문 span (있다면)
- aspect_term='피부톤', polarity='neutral', span=None, evidence=None
- aspect_term='피부톤', polarity='positive', span=None, evidence=None

---

## 체크 3 — risk_flagged 샘플의 risk_id 및 polarity_conflict

**샘플**: index=0, text_id=nikluge-sa-2022-train-02829

- **validator (stage1) risk_ids**: ['CONTRAST_SCOPE']
- **동일 샘플 polarity_conflict**: True

→ conflict가 True인데 risk_ids에 polarity conflict류가 없으면, RQ1 risk 정의는 옵션 A(Validator structural_risks만)이고, conflict와 flagged는 별개 지표.

---

## 체크 4 — debate_override_applied=2 인데 ignored_proposal_rate=1.0 인 이유

- **debate_override_applied**: 집계 시 `sum(override_stats.applied)` over **rows** → **이벤트(제안) 수** (row당 0,1,2,… 가능).
- **override_applied_rate**: 분모=N(샘플 수), 분자=**applied≥1인 샘플 수** (n_applied).
- **ignored_proposal_rate**: 분모=**risk_flagged 샘플 수**, 분자=**risk_flagged이면서 stage_delta.changed=False인 샘플 수**.

→ **단위 불일치**: applied=2 는 "2번 적용 이벤트"(예: 2개 샘플에서 각 1번, 또는 1개 샘플에서 2번). ignored=1.0 은 "risk_flagged인 샘플 100%가 변경 없음". 
즉 applied는 proposal/tuple-level 합계, ignored는 sample-level 비율. **단위 통일**을 위해 applied도 "샘플 수" 기준(n_applied)으로 쓰고, 이벤트 수는 별도 컬럼(debate_override_applied)으로 두는 현재 방식이 맞음. ignored_proposal_rate=1.0이면 risk_flagged인 샘플이 1개뿐이고 그 샘플은 변경이 없다는 뜻.

---

## 체크 5 — guided_change_rate=0 인데 override_applied_rate=0.2

- **guided_change_rate**: 분모=**stage_delta.changed=True인 샘플 수**, 분자=그 중 **change_type=="guided"** 인 샘플 수. (코드: `stage_delta_guided_unguided` → change_type이 "guided"일 때만 True.)
- **override_applied_rate**: debate에서 override 적용된 **샘플** 비율 (n_applied / N).

→ **guided**는 파이프라인에서 "메모리/가이드" 기반 변경으로 붙이는 플래그일 수 있고, **override**는 debate 기반 변경. memory off이면 guided=0은 자연스럽고, override_applied=0.2는 debate로 2개 샘플이 변경 수용했다는 뜻. **guided_change의 분모/정의(what counts as guided)**를 파이프라인에서 확정해야 함 (debate 수용을 guided로 셀지 여부).

(현재 run: changed 샘플 수=0, 그 중 guided=0, override applied 샘플 수=2)  
→ **(4) 반영 후**: scorecard 빌드 시 override 적용이 있으면 `stage_delta.changed=True`, `change_type=guided`로 설정하도록 수정됨. **기존 mini4_b1_2 scorecards는 파이프라인 재실행 전**이므로, changed=0 상태. 파이프라인을 다시 돌리면 override 적용된 2개 샘플에서 changed=True·guided로 나와야 함.

---

## 체크 6 — tuple_f1_s2 > 0 인데 unsupported_polarity_rate=1.0 의 공존

- **tuple_f1_s2**: gold와의 (aspect_term, polarity) 매칭 F1 — **문자열/라벨 일치**.
- **unsupported_polarity_rate**: atsa **sentiment_judgements**에서 issues/opinion_grounded/evidence_relevant 휴리스틱으로 "근거 검증" 실패한 샘플 비율.

→ 두 지표는 **단위·정의가 다름**: F1=정답 매칭, unsupported=validator/ATSA 휴리스틱. 공존 가능. 다만 **전 샘플 100% unsupported**면 validator/ATSA 입력·기준이 과격하거나 입력 필드 불일치 가능성 큼 (예: aspect_term 형식, evidence 필드 누락).

---

## 체크 3bis — F1 0 원인 3줄 점검 (샘플 1개)

**샘플**: index=0, text_id=nikluge-sa-2022-train-02829

1. **gold tuples (정규화된 키)** — `tuples_to_pairs(gold)` = (normalize_for_eval(term), normalize_polarity(p)):
   `[('', 'positive')]`

2. **final tuples (정규화된 키)** — 동일 정규화:
   `[('피부톤', 'neutral'), ('피부톤', 'positive')]`

3. **매칭 키**: (aspect_term, polarity) — **term-only, span 미사용**. `normalize_for_eval(term)` + `normalize_polarity(p)` (metrics.eval_tuple). gold가 span 기반이면 output도 동일 term 문자열을 내야 매칭됨.
