# Finalexperiment C2: Polarity Flip 케이스별 원인 정리

**Run**: `finalexperiment_n50_seed1_c2__seed1_proposed`  
**기준**: Gold와 동일 aspect term인데 최종( final ) polarity가 다른 케이스 16건 (L3 severe polarity error 후보).

---

## 요약

| 구분 | 건수 |
|------|------|
| **positive → negative** | 6 |
| **positive → neutral** | 10 |
| **Moderator stage2 선택** | 16/16 |
| **메모리 주입(memory_injected=1)** | 12/16 |
| **Override 적용(override_applied=True)** | 11/16 |
| **Override 미적용(low_signal)** | 4/16 |
| **ate_debug 상위: alignment_failure** | 12/16 |

---

## 케이스별 원인 표

| # | text_id | Gold → Final (term \| polarity) | Moderator | 메모리 주입 | Override 적용 | override_reason | drift_cause | ate_debug 상위 |
|---|---------|---------------------------------|------------|-------------|---------------|-----------------|-------------|-----------------|
| 1 | nikluge-sa-2022-train-02211 | 라임리치향: pos→neg | stage2 | N | Y | debate_action | stage2_selected | — |
| 2 | nikluge-sa-2022-train-02482 | 젤제형: pos→neu | stage2 | Y | N | low_signal | — | alignment_failure×4 |
| 3 | nikluge-sa-2022-train-01721 | 게임: pos→neg | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure×4 |
| 4 | nikluge-sa-2022-train-00536 | 마스크팩: pos→neu | stage2 | Y | N | low_signal | — | alignment_failure×4 |
| 5 | nikluge-sa-2022-train-00356 | 사진찍기놀이 소품: pos→neu | stage2 | N | Y | debate_action | — | — |
| 6 | nikluge-sa-2022-train-00546 | 부피: pos→neu | stage2 | N | Y | debate_action | — | — |
| 7 | nikluge-sa-2022-train-00037 | 배색: pos→neu | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 8 | nikluge-sa-2022-train-00203 | 샴푸: pos→neu | stage2 | Y | N | low_signal | — | alignment_failure×3 |
| 9 | nikluge-sa-2022-train-00630 | 아이라이너 색: pos→neg | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 10 | nikluge-sa-2022-train-01699 | 블러셔: pos→neg | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 11 | nikluge-sa-2022-train-01108 | 실내복: pos→neg | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 12 | nikluge-sa-2022-train-01495 | 보습폼클렌저: pos→neu | stage2 | Y | Y | debate_action | — | alignment_failure×3 |
| 13 | nikluge-sa-2022-train-01919 | 마스크팩: pos→neu | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 14 | nikluge-sa-2022-train-02270 | 페이즐리 쉬폰블라우스: pos→neu | stage2 | N | Y | debate_action | — | — |
| 15 | nikluge-sa-2022-train-00244 | 앰플캡: pos→neg | stage2 | Y | Y | debate_action | stage2_selected | alignment_failure |
| 16 | nikluge-sa-2022-train-00489 | 스포트라이트 조명: pos→neu | stage2 | Y | N | low_signal | — | alignment_failure×3 |

---

## 원인 분해 요약

1. **Stage2 선택**  
   - 16건 모두 **moderator_selected_stage = stage2**.  
   - 즉, polarity flip은 전부 “Stage2 출력 채택” 구간에서 발생.

2. **메모리 주입 여부**  
   - **memory_injected=1**: 12건 (02211, 00356, 00546, 02270은 미주입).  
   - 주입된 12건에서 debate/override와 결합해 neutral·negative로 바뀐 비중이 큼.

3. **Override 적용 vs 미적용**  
   - **override_applied=True (debate_action)**: 11건 → 토론 결과 반영으로 최종이 gold와 달라진 케이스.  
   - **override_applied=False (low_signal)**: 4건 (02482, 00536, 00203, 00489) → override 미적용.  
   - 이 4건은 “neutral_only” 등으로 스킵된 뒤에도 Stage2 채택으로 인해 final이 neutral로 남은 경우.

4. **Validator/ATE 디버그**  
   - 12/16건에서 **ate_debug_filtered_drop_reasons_top10** 상위에 **alignment_failure** 포함.  
   - Gold span과의 정렬 실패가 많이 관찰되며, 이 구간에서 polarity가 보수적으로 neutral/negative로 나온 경향과 맞음.

5. **정리**  
   - **원인 3요소**: (i) Stage2 채택, (ii) 메모리 주입(12/16), (iii) Override 적용(11건) 또는 미적용 시 Stage2 자체 출력(4건).  
   - 개선 포인트: **alignment_failure** 감소(정렬/span 매칭), **override low_signal** 구간에서의 Stage2 신뢰도 조정, 메모리 주입 시 gold와 충돌하는 hint 억제 검토.

---

*산출: `reports/finalexperiment_c2_polarity_flip_cases.md` — triptych_table.tsv, triptych_risk_details.jsonl 기준.*
