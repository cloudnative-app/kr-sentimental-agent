# 진단 체크 1~7 반영 및 결론

## 1) Option B 이후 judgement "dict만 기대" 잔여 경로

**체크**: atsa.sentiment_judgements를 만드는 함수는 **단일 진입점 1곳** — `scripts/scorecard_from_smoke.py`의 `atsa_score(text, kept_terms, sentiments)`.

- **aspect_term / aspect 필드**: `s.get("aspect_term")` 또는 `s.get("opinion_term")`에서 읽음. Option B 적용 후:
  - `op`가 str이면 → `opinion_grounded=True`, issues 만들지 않음.
  - dict이지만 `span` 없으면 → 동일하게 str 허용 완화.
- **결론**: "aspect_term missing or not dict" 문구는 **Option B 적용 코드에서는 더 이상 생성되지 않음**. 기존에 그 문구가 보이는 scorecard는 **파이프라인 재실행 전**에 만들어진 것이므로, 재실행 후 생성된 scorecard에서는 해당 이슈 텍스트가 사라져야 정상.

---

## 2) "선택 tuple 대응 judgement 실패" 매핑

**체크**: 선택 tuple ↔ judgement 매핑 키 = **normalize_for_eval(aspect_term)** (양쪽 모두 정규화 후 비교).

- **선택 tuple**: `_extract_final_tuples(record)`에서 (aspect_ref, aspect_term, polarity); aspect_term을 normalize_for_eval로 key화.
- **judgement**: `j.get("aspect_term")`을 normalize_for_eval로 key화.
- **join**: `term_norm in final_terms_norm`이고 해당 judgement가 실패하면 selected_fail=True.
- **빠른 점검**: 진단 스크립트에 **체크 2bis** 추가 — 샘플 1개에서 "선택 tuple aspect_term(normalized)=X → judgement index=i (key matched)" 또는 "no matching judgement" 1줄 출력.

---

## 3) F1 0 / gold 빈 aspect 원인

**체크**: mini4 `valid.gold.jsonl`에서 **원본에 aspect_term=""** 로 저장된 행이 있음 (예: nikluge-sa-2022-train-02829). 정규화에서 날아간 것이 아님.

- **gold 로더**: `metrics.eval_tuple.gold_row_to_tuples` → `_gold_aspect_term(t)`.  
  `"aspect_term" in t and t.get("aspect_term") == ""` 이면 **명시적 빈 문자열**로 "" 반환.
- **데이터셋**: mini4 gold는 `aspect_ref`는 있으나 `aspect_term`을 빈 문자열로 둔 행이 있음. nikluge-sa-2022 형식 매핑은 `gold_tuples` 리스트 내 `aspect_term`/`aspect_ref`/`polarity` 사용.
- **빠른 점검**: 진단에 **gold 원본 정규화 전/후** 2줄 추가 — 정규화 전(원본 dict 1개), 정규화 후(aspect_term, polarity).
- **결론**: gold가 빈 aspect이면 pred가 아무리 좋아도 F1이 의미 없음. **데이터셋 제작 시** 해당 행에 aspect_term/span을 채우거나, aspect_ref를 term 폴백으로 쓰는 정책을 정해야 함.

---

## 4) conflict 집계의 aspect key 정규화

**적용**: `has_same_aspect_polarity_conflict`에서

- **key**: `normalize_for_eval(aspect_term)` 사용.
- **polarity**: `normalize_polarity(p)` 사용.
- **dedup**: 동일 (key, polarity)는 set으로 자동 dedup. 동일 key에 서로 다른 polarity가 2개 이상이면 conflict.

논문에서 RQ "구조적 불일치"로 쓸 때 정규화+dedup 적용 상태로 통일됨.

---

## 5) override → stage_delta.changed 복구

**체크**:

- **순서**: scorecard는 파이프라인에서 **override 적용이 반영된 payload**로 `make_scorecard(entry)` 호출. `_build_stage_delta(entry)`는 `entry`의 `debate_override_stats`/`override_stats`를 읽으므로, override 적용 **이후**에 stage_delta가 계산됨.
- **단일 결정점**: `scorecard_from_smoke._build_stage_delta` 한 곳에서만 결정.  
  `changed = ... or (override_applied > 0)`  
  `change_type = "guided" if (guided from correction_log or override_applied > 0) else "unguided"`  
  override 적용 시 `changed=True`, `change_type=guided`.

재실행 후 scorecard에서는 override 적용된 샘플에 changed=True가 나와야 함.

---

## 6) scorecards / derived 동일 소스 보장

**체크**:

- **derived**: `structural_error_aggregator`는 **scorecards.jsonl만** 읽어서 `structural_metrics.csv` 등 생성. raw outputs를 다시 읽지 않음.
- **동일 run**: `run_pipeline`이 같은 run_id로 scorecards를 쓴 뒤, 같은 run_dir에 대해 aggregator를 돌리면 scorecards와 derived가 **같은 run_id·같은 파이프라인 실행**에서 나옴.
- **manifest**: run_dir에 `manifest.json` (run_id, cfg_hash, timestamp 등) 있음. **커밋 해시/빌드 스탬프**는 현재 manifest에 없음 — 필요 시 파이프라인에서 채우도록 확장 가능.

결론: derived는 scorecard만 보고 계산되며, 동일 run_dir에서 생성되면 동일 소스로 간주 가능.

---

## 7) evidence/span 없을 때 → metric 반영

**체크**:

- **unknown/insufficient**: Option B에서 evidence/span 없을 때 issues에 `"unknown/insufficient"`만 추가.
- **aggregator**: `_judgement_fail_for_unsupported(j)`에서  
  `issues`가 있고 **전부 `"unknown/insufficient"`**이면 **return False** (실패로 세지 않음).  
  따라서 **unknown/insufficient만 있으면 unsupported로 치지 않음** — B의 취지와 일치.
- **insufficient-evidence 별도 bucket**: 현재 aggregator에는 "issues가 전부 unknown/insufficient인 judgement 수" 집계는 없음.  
  groundedness 관련 지표에서 **unknown을 별도 bucket(예: insufficient-evidence)**으로 분리해 보고서에 표시하려면, aggregator에 해당 카운트를 추가하고 리포트에 행/컬럼을 넣으면 됨.

---

## b1_3 재분석 및 진단

- **aggregator** 재실행: `results/experiment_mini4_b1_3__seed42_proposed/scorecards.jsonl` → `derived/metrics/structural_metrics.csv`.
- **build_metric_report** 재실행: 동일 run_dir → `reports/.../metric_report.html`.
- **diagnose**: `--scorecards`/`--csv`/`--out`으로 b1_3 경로 지정 → `docs/mini4_b1_3_checks_result.md` 생성.

위 순서로 실행 후, mini4_b1_3 결과에 대한 진단 보고는 `docs/mini4_b1_3_checks_result.md`를 참고하면 됨.
