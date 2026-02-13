# Polarity & Final Tuples 체크리스트

**Run dir**: `C:\Users\wisdo\Documents\kr-sentimental-agent\results\experiment_mini4_validation_c2_t0_proposed`

## 기본
- scorecards.jsonl 레코드 수: **10**
- outputs.jsonl 레코드 수: **10**
- stage2 리뷰 컨텍스트: scorecards 내 runtime.parsed_output.meta.debate_review_context 사용

## 체크리스트 1 — polarity_hint 생성 로직
### 1-1 힌트 원천 vs polarity_hint 일치 / 전부 neutral 버그 후보
  row0 EPM: proposed_edits→[] polarity_hint=neutral
  row0 TAN: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  row0 CJ: proposed_edits→[('drop_tuple', 'neutral')] polarity_hint=neutral
  row1 EPM: proposed_edits→[('set_aspect_ref', None), ('set_aspect_ref', None), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row1 TAN: proposed_edits→[] polarity_hint=neutral
  row1 CJ: proposed_edits→[] polarity_hint=neutral
  row2 EPM: proposed_edits→[] polarity_hint=neutral
  row2 TAN: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  row2 CJ: proposed_edits→[('drop_tuple', 'neutral')] polarity_hint=neutral
  row3 EPM: proposed_edits→[] polarity_hint=neutral
  row3 TAN: proposed_edits→[('set_aspect_ref', None), ('set_aspect_ref', None)] polarity_hint=neutral
  row3 CJ: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row4 EPM: proposed_edits→[] polarity_hint=neutral
  row4 TAN: proposed_edits→[('set_aspect_ref', None), ('set_aspect_ref', None)] polarity_hint=neutral
  row4 CJ: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row5 EPM: proposed_edits→[] polarity_hint=neutral
  row5 TAN: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  row5 CJ: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row6 EPM: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row6 TAN: proposed_edits→[('set_aspect_ref', None), ('set_aspect_ref', None)] polarity_hint=neutral
  row6 CJ: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row7 EPM: proposed_edits→[] polarity_hint=neutral
  row7 TAN: proposed_edits→[('set_aspect_ref', None), ('set_aspect_ref', None)] polarity_hint=neutral
  row7 CJ: proposed_edits→[] polarity_hint=neutral
  row8 EPM: proposed_edits→[] polarity_hint=neutral
  row8 TAN: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  row8 CJ: proposed_edits→[('drop_tuple', 'neutral'), ('drop_tuple', 'neutral'), ('drop_tuple', 'neutral')] polarity_hint=neutral
  row9 EPM: proposed_edits→[] polarity_hint=neutral
  row9 TAN: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  row9 CJ: proposed_edits→[('set_aspect_ref', None)] polarity_hint=neutral
  OK: 일치하거나 검사할 편집 없음.

### 1-2 stance="" 처리
  stance 빈 문자열 시 polarity_hint: 코드에서 proposed_edits 기반으로 세팅하는지 확인.
  (supervisor _build_debate_review_context: hint_entries는 per-edit, rebuttals는 turn별 polarity_first or neutral)
  강제 neutral 덮어쓰기 의심 패턴: 있음
  proposed_edits에서 polarity 사용: 있음

### 1-3 TAN(set_aspect_ref) 점수 제외
  aspect_hints에 polarity_hint=None/weight=0 항목 없음(샘플에서). 코드상 set_aspect_ref는 weight=0, polarity_hint=None → total 제외.

### 1-4 CJ(drop_tuple) 점수화 규칙
  코드: drop_tuple → polarity_hint='negative', weight=0.8 (anti-neutral 신호로 neg 쪽에 합산).

### 1-5 점수 계산 직전 디버그 로그
  supervisor: _apply_stage2_reviews 내 sample_idx==0 1회 로그(per_hint, pos_score, neg_score, total, margin) 있음.
  override_gate_debug.jsonl 첫 샘플(aspect): pos_score=0 neg_score=0 total=0 margin=0 skip_reason=low_signal

## 체크리스트 2 — total/margin 0 원인 (A/B/C)
  (A) 힌트 0개 → 추출 실패: 2
  (B) 힌트 있는데 polarity_hint 전부 neutral/None: 26
  (C) polarity_hint 있는데 가중치 0: 0
  샘플: B: text_id=nikluge-sa-2022-train-02829 aspect=피부톤 hints=3 모두 neutral/None; B: text_id=nikluge-sa-2022-train-00797 aspect=순한 성분 hints=3 모두 neutral/None; B: text_id=nikluge-sa-2022-train-00797 aspect=자와선 hints=3 모두 neutral/None; B: text_id=nikluge-sa-2022-train-00474 aspect=인정 hints=3 모두 neutral/None; B: text_id=nikluge-sa-2022-train-01065 aspect=하루 한장 hints=3 모두 neutral/None

## 체크리스트 3 — final_tuples 정책 및 일치
### 3-1 최종 tuple source-of-truth
  정책: debate_summary.final_tuples 존재 시 final_aspect_sentiments(및 final_result.final_tuples)를 그에 맞춤. 코드: run() 내 debate_output.summary.final_tuples 반영.

### 3-2 stage2 conflict / dedup 후 judge 일치
  검사한 샘플에서 stage2 conflict 없음 / final_tuples와 debate_summary 일치.

### 3-3 moderator.final_label ↔ final_tuples 동기화
  OK: moderator final_label과 final_tuples polarity 모순 없음.

---
체크리스트 4(게이트 실험 T0/T1/T2 재검증)는 run_mini4_c2_t0_t1_t2.py + checklist_override_gate_t0_t1_t2.py로 수행.