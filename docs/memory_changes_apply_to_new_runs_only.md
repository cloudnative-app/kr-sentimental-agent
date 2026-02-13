# 메모리 관련 수정사항 적용 범위

## 결론

- **메모리 관련 수정사항은 새로운 런에만 적용됩니다.**
- **기존 실험 결과(scorecards/traces/outputs)에는 나중에 적용할 수 없습니다.**

새 동작을 반영하려면 파이프라인을 다시 실행해야 합니다.

---

## 이유

메모리·어드바이저·모더레이터 관련 로직은 **추론 시점(파이프라인 실행 시)** 에만 동작합니다.

| 단계 | 역할 | 적용 시점 |
|------|------|-----------|
| **Retrieval** | `EpisodicOrchestrator.get_slot_payload_for_current_sample()` | 샘플마다 런 중 호출 |
| **Advisory 빌드** | `AdvisoryBuilder.build_from_episodes()` → debate 프롬프트 슬롯 | 런 중 |
| **Debate** | LLM이 advisory가 포함된 프롬프트로 토론 | 런 중 |
| **Override/Skip** | L3 conservative, implicit soft-only, skip reasons 등 | 런 중 `SupervisorAgent` 내부 |
| **에피소드 저장** | `append_episode_if_needed()` → episodic_store.jsonl | 샘플 끝날 때마다 런 중 |

저장되는 결과물은 이미 위 단계를 **한 번 거친 최종 결과**입니다.

- **scorecards.jsonl**: 샘플별 최종 튜플, 메타, override 통계 등 (이미 결정된 값)
- **outputs.jsonl** / **traces.jsonl**: 당시 코드가 만든 입력·출력·메타

따라서:

1. **모델 입력**(어드바이저 문구, 슬롯 내용)은 그 런이 돌았을 때의 코드로 이미 고정됨.
2. **모델 출력**(최종 튜플, override 적용 여부)도 그때 생성된 것이며, “새 규칙으로 다시 override만 돌리기”에 필요한 중간 상태(전체 debate, confidence, risk_type 등)가 전부 보존되어 있지 않을 수 있음.
3. **에피소드 저장**은 순차적 상태(이전 샘플들의 에피소드)에 의존하므로, “중간부터 다시 돌리기”도 새 런이 아니면 불가능에 가깝습니다.

---

## 어떤 수정이 “새 런에만” 적용되는지

- 에피소드 스키마 변경 (risk_type, action_taken, outcome_delta 등)
- Advisory 빌드 방식 (메시지 포맷, evidence 필드)
- C1/C2/C3 조건 플래그 (retrieval_execute, injection_mask, store_write)
- 모더레이터 규칙 (L3 conservative, implicit soft-only, skip reason 기록)
- Override threshold, debate 설정

위와 같은 **메모리/어드바이저/모더레이터 관련 코드 변경**은 모두 **새로 파이프라인을 돌린 런**에만 반영됩니다.

---

## 기존 결과로 할 수 있는 것

- **집계/리포트만** 바꾼 경우(예: structural_metrics 계산 방식, 리포트 HTML):  
  기존 `scorecards.jsonl`만으로 **재집계·리포트 재생성** 가능.
- **메모리/어드바이저/모더레이터 동작**을 바꾼 경우:  
  기존 실험 결과에는 적용 불가 → **새 런**을 돌려야 새 동작이 반영됩니다.
