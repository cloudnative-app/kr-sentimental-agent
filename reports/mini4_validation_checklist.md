# Mini4 Validation Checklist Review

- C1: C:\Users\wisdo\Documents\kr-sentimental-agent\results\experiment_mini4_validation_c1_proposed
- C2: C:\Users\wisdo\Documents\kr-sentimental-agent\results\experiment_mini4_validation_c2_proposed
- C3: C:\Users\wisdo\Documents\kr-sentimental-agent\results\experiment_mini4_validation_c3_proposed
- C2_eval_only: C:\Users\wisdo\Documents\kr-sentimental-agent\results\experiment_mini4_validation_c2_eval_only_proposed

---

## 1. Sanity Check

  [C1] sample 0: aspect_term에 복수 polarity 존재: ['피부톤']
  [C1] sample 1: aspect_term에 복수 polarity 존재: ['순한 성분']
  [C1] sample 3: aspect_term에 복수 polarity 존재: ['하루 한장']
  [C1] sample 4: aspect_term에 복수 polarity 존재: ['싱크대거름망']
  [C1] sample 5: aspect_term에 복수 polarity 존재: ['퀄리티']
  [C1] sample 6: aspect_term에 복수 polarity 존재: ['블루 에센스']
  [C1] sample 7: aspect_term에 복수 polarity 존재: ['피부']
  [C1] sample 8: aspect_term에 복수 polarity 존재: ['가슴크림']
  [C1] sample 9: aspect_term에 복수 polarity 존재: ['수분보호막']
  [C2] sample 0: aspect_term에 복수 polarity 존재: ['피부톤']
  [C2] sample 1: aspect_term에 복수 polarity 존재: ['자와선']
  [C2] sample 3: aspect_term에 복수 polarity 존재: ['하루 한장']
  [C2] sample 4: aspect_term에 복수 polarity 존재: ['친환경제품']
  [C2] sample 5: aspect_term에 복수 polarity 존재: ['퀄리티']
  [C2] sample 6: aspect_term에 복수 polarity 존재: ['자외선 차단효과']
  [C2] sample 7: aspect_term에 복수 polarity 존재: ['선스크린']
  [C2] sample 8: aspect_term에 복수 polarity 존재: ['부작용 걱정']
  [C2] sample 9: aspect_term에 복수 polarity 존재: ['수분보호막']
  No: 위 위반 샘플 존재.
  No: final_output에 aspect_term=null/빈 tuple 존재.
  Yes: C2에서 debate_output이 final_patch(action list) 형태 존재 (샘플 수: 10).
  Yes: C1/C2 final_result 스키마 동일.

**Result: FAIL**

## 2. Metric Alignment Check

  polarity_conflict_rate: C1=0.9000, C2=0.9000 → C2≤C1? True
  severe_polarity_error_L3_rate: C1=0.2000, C2=0.2000 (감소 시 patch 기여, 증가 시 patch 오류 가능).
  tuple_agreement_rate: N/A (single run이면 1.0 또는 N/A).

**Result: PASS**

## 3. Role Separation Check

  risk_resolution_rate (Validator flag 해결 비율): 1.0000
  debate_override_skipped_conflict / applied: N/A
  Stage2 재분석 호출 횟수/수정 폭: C1 vs C2 비교는 drift_cause_* / stage2_adopted_but_no_change 등 참고.

**Result: PASS**

## 4. Ablation Consistency Check (C1 vs C2 vs C3)

  C3 polarity_conflict_rate: 0.9000, C1: 0.9000 → C3 < C1 (메모리 단독 효과)? False
  C2 polarity_conflict_rate: 0.9000, C3: 0.9000 → C2 < C3 (토론 순수 기여)? False
  C2 memory_used=true 샘플 중 debate patch 적용: override_applied_n 등 참고 (memory_used_rate / override_applied_n).

**Result: FAIL**

## 5. Memory Flags / OPFB / Gate / after_rep / Gold

  C2: exposed_to_debate True 샘플=10, prompt_injection_chars>0 샘플=8 (기대: C2만 해당).
  OPFB: blocked 발동 샘플 수=0 (memory_block_reason 확인).
  주입 트리거: injection_trigger_reason counts={'validator': 1, 'alignment': 7}.
  after_rep 컬럼: tuple_f1_s2_raw=True, tuple_f1_s2_after_rep=True, polarity_conflict_rate_raw/after_rep 채워짐.
  gold: gold_available=True, N_gold_total=10, tuple_f1_s2=0.30666666666666664 (N/A 아니어야 함).
  scorecards에 gold_tuples 있는 행 수=10.

**Result: PASS**
