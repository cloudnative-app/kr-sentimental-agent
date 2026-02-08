# mini4_b1_3 진단 결과 (6 checks + 3bis, 2bis)

**Run**: experiment_mini4_b1_3__seed42_proposed  
**Scorecards**: `results/experiment_mini4_b1_3__seed42_proposed/scorecards.jsonl` (N=10)  
**Metrics**: `results/experiment_mini4_b1_3__seed42_proposed/derived/metrics/structural_metrics.csv`

b1_3는 파이프라인 재실행으로 생성된 scorecard라 (4) override→stage_delta 반영 가능. 현재 run에서 changed=4, guided=3, override applied 샘플=3.

---

## 체크 1 — Unsupported polarity 원인 1샘플 해부

**샘플**: index=1, text_id=nikluge-sa-2022-train-00797

### final_tuples (원본 필드)
- Tuple 1: `aspect_term`='자와선', `polarity`='neutral', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']
- Tuple 2: `aspect_term`='순한 성분', `polarity`='neutral', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']
- Tuple 3: `aspect_term`='자와선', `polarity`='positive', `evidence`=None, `span`=None, 기타 keys=['aspect_ref', 'aspect_term', 'polarity']

### unsupported 판정 True가 된 이유 (코드 경로)
`has_unsupported_polarity`: **완화 후** — 샘플 unsupported iff (모든 judgement 실패) OR (최종 tuple에 대응하는 judgement 실패).
judgement 실패 = `opinion_grounded` is False OR issues가 존재하고 전부 'unknown/insufficient'가 아님. (evidence/span 없음만이면 unsupported로 세지 않음.)

- Judgement 1: `issues`=[], `opinion_grounded`=True, `evidence_relevant`=True → **triggered=False**
- Judgement 2: `issues`=[], `opinion_grounded`=True, `evidence_relevant`=True → **triggered=False**
- Judgement 3: `issues`=["opinion_not_grounded: span_text='할만큼 순' != aspect_term='순한 성분'"], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**
- Judgement 4: `issues`=["opinion_not_grounded: span_text='성분에' != aspect_term='자와선'"], `opinion_grounded`=False, `evidence_relevant`=True → **triggered=True**

---

## 체크 2 — Polarity conflict "충돌 aspect key" 확인

**샘플**: index=0, text_id=nikluge-sa-2022-train-02829

### conflict를 만든 aspect key (정규화된 aspect_term)
집계(aggregator)에서는 **정규화 적용**: key=normalize_for_eval(aspect_term), polarity=normalize_polarity(p). 아래는 진단용 raw key.
- **'피부톤'** → polarity set = {'negative', 'neutral'}

### 해당 tuple들의 원문 span (있다면)
- aspect_term='피부톤', polarity='neutral', span=None, evidence=None
- aspect_term='피부톤', polarity='negative', span=None, evidence=None

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

(현재 run: changed 샘플 수=4, 그 중 guided=3, override applied 샘플 수=3)

---

## 체크 6 — tuple_f1_s2 > 0 인데 unsupported_polarity_rate=1.0 의 공존

- **tuple_f1_s2**: gold와의 (aspect_term, polarity) 매칭 F1 — **문자열/라벨 일치**.
- **unsupported_polarity_rate**: atsa **sentiment_judgements**에서 issues/opinion_grounded/evidence_relevant 휴리스틱으로 "근거 검증" 실패한 샘플 비율.

→ 두 지표는 **단위·정의가 다름**: F1=정답 매칭, unsupported=validator/ATSA 휴리스틱. 공존 가능. 다만 **전 샘플 100% unsupported**면 validator/ATSA 입력·기준이 과격하거나 입력 필드 불일치 가능성 큼 (예: aspect_term 형식, evidence 필드 누락).

---

## 체크 3bis — F1 0 원인 3줄 점검 (샘플 1개)

**샘플**: index=0, text_id=nikluge-sa-2022-train-02829

**gold 원본 정규화 전/후 (1개):**
- 정규화 전 (원본): `{'aspect_ref': '본품#품질', 'aspect_term': '', 'polarity': 'positive'}`
- 정규화 후: aspect_term='', polarity='positive'

1. **gold tuples (정규화된 키)** — `tuples_to_pairs(gold)` = (normalize_for_eval(term), normalize_polarity(p)):
   `[('', 'positive')]`

2. **final tuples (정규화된 키)** — 동일 정규화:
   `[('피부톤', 'negative'), ('피부톤', 'neutral')]`

3. **매칭 키**: (aspect_term, polarity) — **term-only, span 미사용**. gold가 빈 aspect('')이면 pred가 아무리 좋아도 F1 의미 없음. mini4 valid.gold.jsonl에 aspect_term="" 로 원본 저장된 행 있음.

---

## 체크 2bis — 선택 tuple ↔ judgement 매핑 (1줄)

**샘플 index=0**: 선택 tuple aspect_term(normalized)='피부톤' → **judgement index=1** (key matched).
