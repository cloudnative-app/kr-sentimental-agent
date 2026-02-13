# Memory metrics and ablations

## A. risk_after 실제 채우기

- **episodic_orchestrator**: `risk_after`를 stage2 validator의 structural_risks 기준으로 채웁니다.
  - `risk_before`: stage1 structural_risks의 severity 가중합 (high=3, mid=2, low=1).
  - `risk_after`: stage2 structural_risks의 severity 가중합.
  - OPFB/MemoryImpact/‘harm’ 판정은 `evaluation.risk_after.severity_sum`이 실제로 0이 아닌지 조건별로 확인하면 됩니다.

### Triptych / structural_metrics

- **Triptych** (`--export_triptych_table`): 샘플별 컬럼 추가
  - `risk_before_sum`: stage1 severity 가중합
  - `risk_after_sum`: stage2 severity 가중합
  - `risk_delta_sum`: risk_after_sum - risk_before_sum

- **structural_metrics** (조건별): 집계 컬럼 추가
  - `risk_before_sum`, `risk_after_sum`, `risk_delta_sum`: 합
  - `risk_before_sum_mean`, `risk_after_sum_mean`, `risk_delta_sum_mean`: 평균

조건별로 `risk_after_sum_mean`이 항상 0인지, severity 분포가 어떻게 나오는지 확인하면 됩니다.

---

## B. C2 주입량 cap (memory_prompt_injection_chars_cap)

- **목적**: "주입량 1060 chars"가 과도한지, context pollution 완화 여부 확인.
- **설정**: 실험 YAML의 `pipeline`에 `memory_prompt_injection_chars_cap` 추가.

```yaml
pipeline:
  memory_prompt_injection_chars_cap: 600   # 0 | 300 | 600 | 1000 (None = 무제한, 현행 근사)
```

- **cap 0**: C3와 동일하게 주입 없음 (retrieval만 수행).
- **cap 300 / 600 / 1000**: 주입 JSON을 해당 글자 수로 자르고 주입.

ablation 비교: cap 0, 300, 600, 1000 각각으로 C2 실험 후 `explicit_failure`/`conflict` 등이 cap에 단조로 반응하는지 확인.

---

## C. 게이트 coverage 메트릭

조건별로 다음 메트릭이 structural_metrics (및 CSV)에 포함됩니다.

- **memory_used_rate**: (retrieved>0 AND exposed_to_debate=True)인 샘플 비율.
- **memory_used_changed_rate**: 메모리가 실제로 주입된 샘플 중에서 stage1→final 변경이 발생한 비율.
- **injection_trigger_reason** (샘플별): scorecard `memory.injection_trigger_reason` (conflict / validator / alignment / explicit_grounding_failure).
- **집계**: `injection_trigger_conflict_n`, `injection_trigger_validator_n`, `injection_trigger_alignment_n`, `injection_trigger_explicit_grounding_failure_n`.

게이트가 “위험 샘플에만” 걸리는지, retrieval이 너무 자주 “쓸모 있다”고 판단되는 구조인지 위 메트릭으로 점검할 수 있습니다.

---

## D. Raw vs after_rep (F1 / Conflict)

- **polarity_conflict_rate_raw**: raw final_tuples 기준 동일 aspect 복수 극성 비율.
- **polarity_conflict_rate_after_rep**: 대표선택(after_rep) 적용 후 conflict 비율.

F1은 둘 다 보고할 수 있도록 추가됨:

- **tuple_f1_s2_raw**: raw final_tuples 기준 tuple F1 (기존 tuple_f1_s2와 동일 소스).
- **tuple_f1_s2_after_rep**: 대표선택(select_representative_tuples) 적용 후 tuple F1.

실험 보고 시 (A) raw final_tuples로 F1/Conflict, (B) after_rep 적용 final_tuples로 F1/Conflict를 같이 제시해 “출력 정리의 효과”를 분리해서 주장할 수 있습니다.
