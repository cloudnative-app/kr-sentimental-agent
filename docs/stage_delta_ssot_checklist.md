# stage_delta SSOT 및 inconsistency B/C 제거 체크리스트

## 조치 1) stage_delta.changed를 pairs 기준 SSOT로 강제 — B(71) 제거

### 수정 내용 (scorecard_from_smoke.py `_build_stage_delta`)

- **규칙(고정)**  
  `s1_pairs = tuples_to_pairs(extract_stage1_tuples(record))`  
  `final_pairs = tuples_to_pairs(extract_final_tuples(record))`  
  `stage_delta.changed = (s1_pairs != final_pairs) or (stage1_label != final_label)`
- **동일 함수 사용**: `_extract_stage1_tuples`, `_extract_final_tuples`, `tuples_to_pairs`는 aggregator와 동일(scripts.structural_error_aggregator + metrics.eval_tuple). record 형태는 `{"runtime": {"parsed_output": entry}}`로 wrap.
- **추가 필드**  
  - `stage_delta.pairs_changed` (bool)  
  - `stage_delta.label_changed` (bool)  
  - `stage_delta.n_s1_pairs`, `stage_delta.n_final_pairs` (count)

→ B(71)는 “stage_delta.changed가 pairs 변경을 반영하지 않음”이었으므로, 위처럼 changed를 pairs 기준으로 강제하면 구조적으로 제거됨.

### 체크리스트

- [x] stage_delta.changed 산식이 pairs 기반인지 확인  
- [x] pairs 산출 함수가 aggregator/triptych와 동일한지 확인(정규화 포함)  
- [x] stage_delta에 pairs_changed, label_changed, n_s1_pairs, n_final_pairs 저장  

---

## 조치 2) selected_stage=stage2 & changed=0 → stage2_adopted_but_no_change — C(5) 제거

### 수정 내용

- **2-1)** `stage2_adopted`는 moderator.selected_stage == "stage2" 로 판단(별도 플래그로 분리).
- **2-2)** `changed == 0`이면 guided_change=0, unguided_drift=0 으로 두고, **stage2_adopted_but_no_change = 1** 로 저장.
- **2-3)** 변경이 있었는데도 guided/unguided가 둘 다 0이면(진짜 C): **Option A** — `change_type = "unguided"` 로 처리(이미 `guided else "unguided"` 로 처리됨).

inconsistency 플래그 C: **stage2_adopted_but_no_change**가 True인 행은 C로 세지 않음(정의된 케이스).

### 체크리스트

- [x] selected_stage==stage2 & changed==0 케이스는 stage2_adopted_but_no_change로 분리  
- [x] inconsistency_flags에서 stage2_adopted_but_no_change이면 flag_c 미부여  

---

## 실행 절차 (기존 런 재사용, LLM 재호출 없음)

1. **make_scorecard만 다시 실행**  
   기존 outputs.jsonl(또는 pipeline 출력)을 입력으로 scorecard_from_smoke를 돌려 **scorecards.jsonl 재생성**.
2. **structural_error_aggregator 재실행**  
   `--input scorecards.jsonl --outdir ... --diagnostics_dir ... --export_triptych_table ...`
3. **GO/NO-GO 확인**  
   - Sanity check 통과 유지  
   - inconsistency_flags 0건  

---

## GO/NO-GO (한 줄 규칙)

- Sanity check 통과 ✅  
- inconsistency_flags 0건 ✅  
- coverage fallback 비율이 설명 가능한 수준 ✅  
- N_gold_total_pairs = explicit_pairs + implicit_pairs ✅  

→ 위 4개 만족 시 정합성 최종 통과.
