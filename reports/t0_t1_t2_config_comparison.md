# T0 / T1 / T2 설정 비교 요약

mini4 C2 검증 실험의 세 가지 **debate override 게이트** 설정 비교.  
데이터·백본·메모리 조건(C2)·실험 옵션은 동일하며, `pipeline.debate_override`만 다름.

---

## 1. 공통 설정 (동일)

| 항목 | 값 |
|------|-----|
| run_mode | proposed |
| dataset | mini4 (train/valid) |
| gold | mini4/valid.gold.jsonl |
| backbone | openai / gpt-4.1-mini |
| temperature | 0 |
| episodic_memory | C2 |
| enable_stage2 / validator / debate / debate_override | 모두 true |
| leakage_guard | true |
| demo | k=0, seed=42, hash_filter=true |
| experiment | seeds=[42], concurrency=1 |

---

## 2. 차이: `debate_override` 파라미터

| 파라미터 | T0 (기준선) | T1 (완화) | T2 (매우 완화) |
|----------|-------------|-----------|----------------|
| **min_total** | **1.6** | **1.0** | **0.6** |
| **min_margin** | **0.8** | **0.5** | **0.3** |
| **min_target_conf** | **0.7** | **0.6** | **0.55** |
| **l3_conservative** | **true** | **true** | **false** |

---

## 3. 설정 의도 (주석 기준)

| Run | 의도 |
|-----|------|
| **T0** | 현재 역치(게이트 기준선). 적용이 거의 안 나오는 엄격한 게이트. |
| **T1** | 완화 — “적용률이 생기게”. L3 보수적 규칙 유지. |
| **T2** | 매우 완화 — “게이트가 문제인지 확정”. **l3_conservative만 false**로 해제. |

---

## 4. 요약 표

| | T0 | T1 | T2 |
|---|----|----|-----|
| **역치** | 가장 엄격 | 중간 완화 | 가장 완화 |
| **L3 보수** | ✅ | ✅ | ❌ |
| **min_total** | 1.6 → 1.0 → 0.6 |
| **min_margin** | 0.8 → 0.5 → 0.3 |
| **min_target_conf** | 0.7 → 0.6 → 0.55 |

- **T0 → T1:** 역치만 완화 → override 적용 기회 증가 목적.  
- **T1 → T2:** 역치 추가 완화 + **L3 conservative 해제** → 게이트 자체가 병목인지 확인 목적.

설정 파일:  
`experiment_mini4_validation_c2_t0.yaml`, `_t1.yaml`, `_t2.yaml`
