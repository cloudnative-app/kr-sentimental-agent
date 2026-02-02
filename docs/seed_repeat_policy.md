# Seed 반복 기반 실험 정책 (Fold → Seed 전환)

## 배경

- 본 실험은 **모델 학습이 목적이 아닌 LLM-as-measurement 평가**임.
- 따라서 **K-fold 평균화가 아닌, 동일 데이터셋에서 시드 고정 반복(N회)**이 실험 목적에 부합함.
- 반복의 단위는 **데이터 분할(fold)**이 아니라 **추론 시드(seed)**임.

**논문 문장 예시**

- ❌ "K-fold cross-validation was used…"
- ⭕ "Repeated inference was conducted with fixed datasets under different random seeds to assess output stability."

---

## 1. 실험 목적 재정의

| 항목 | 내용 |
|------|------|
| 목적 | 성능 향상이 아니라 **출력 안정성/일관성 평가** |
| 학습 | 없음 (fine-tuning, parameter update 없음) |
| 반복 단위 | **추론 시드(seed)** (데이터 분할 아님) |
| Methods | "The model was not trained; all experiments were conducted under a zero-shot setting with repeated inference." |

---

## 2. 데이터 정책 (단일 고정 데이터셋)

| 항목 | 내용 |
|------|------|
| **train_file** | 구조 유지를 위한 비평가 split (평가 미사용). "non-evaluated split" 내부 정의. |
| **valid_file** | **유일한 평가(report) 데이터**. 모든 반복에서 동일. |
| **test_file / blind** | 정책상 미사용. config에 두지 않음. |
| **폴드** | 사용하지 않음. `fold`가 경로·run_id에 포함되면 fail-fast ERROR. fold{i}_train/valid 생성 스크립트는 **deprecated** (단일 분할 + seed 반복으로 전환). |

- 데이터는 **한 번 정해지면 모든 seed 반복에서 동일**해야 함.

**data_roles**: `report_set`은 split label(valid 등), `report_sources`는 실제 파일 키(ground truth). paper에서는 `report_sources: ["valid_file"]`만 사용.

---

## 3. 반복 설계 (Seed)

**용어 (혼동 방지)**: **"n회 반복"** = **서로 다른 시드 n개**를 `seeds` 리스트에 두고, **각 시드당 1회만 시행**하는 것을 말함. 동일 시드를 여러 번 돌리는 것이 아님. run_pipeline 1회 실행 시 `seeds`에 나열된 순서대로 시드마다 1회씩 실행하며, 결과는 `run_id__seed42`, `run_id__seed123` 등으로 분리 저장.

| 항목 | 내용 |
|------|------|
| **반복 횟수 N** | config의 `experiment.repeat.seeds` 길이 (예: 5개 시드 = 5회 반복) |
| **각 반복** | 서로 다른 시드 하나씩, 각 1회 시행. seed만 다르고 데이터·config 동일. |
| **seed 영향** | LLM sampling (temperature > 0일 때), 기타 stochastic 요소. demo 샘플링은 k=0이므로 없음. |
| **설정** | `experiment.repeat.mode: seed`, `experiment.repeat.seeds: [42, 123, 456, 789, 101]` (5회 반복 = 5개 시드 각 1회) |

- **Fail-fast**: `experiment.repeat.mode == seed`이면 `demo.k`는 반드시 0 (zero-shot).

---

## 4. 미니 테스트 / 본실험

| 구분 | 목적 | 데이터 | 반복 |
|------|------|--------|------|
| **미니(리허설)** | 누수 방지·seed 반복 시 결과 구조 동일성 점검 | `mini/` (단일 분할, 작은 규모) | seed N회 (동일 절차) |
| **본실험(paper)** | 보고용 | `real/` (별도 데이터, 본실험 규모) | seed N회, seed 기준 집계 |

- 미니와 본실험은 **같은 절차**(valid만 평가, seed 반복), **다른 데이터·규모**만 다름.
- 결과 집계: **평균 ± 표준편차 (seed 기준)**, agreement/consistency (seed 간). **fold 기준 집계/표기는 사용하지 않음.**

---

## 5. 용어 정리

| 용어 | 사용 | 비고 |
|------|------|------|
| "train" | ❌ 학습 의미로 쓰지 않음 | 내부: "non-evaluated split" |
| "fold" | ❌ 사용 금지 | config·경로·결과에서 제거 |
| "demo" | few-shot 확장 시에만 문서에서 언급 | k=0이면 사실상 미언급 |
| "valid" | ⭕ 유일한 report set | 논문 메트릭은 valid에서만 |

---

## 6. Fail-fast 규칙

paper 또는 seed 반복 설정 시 다음이면 **ERROR**로 중단:

1. **fold 관련**: `data.train_file` 또는 `data.valid_file` 경로에 `fold` 포함.
2. **seed 반복 + demo_k > 0**: `experiment.repeat.mode == seed`인데 `demo.k > 0`.
3. **paper valid-only 위반**: `data.valid_file` 없음, `report_sources != ["valid_file"]`, `data.test_file` 또는 blind_set/blind_sources 사용.

실행 전 검사:

```powershell
python scripts/check_experiment_config.py --config experiments/configs/experiment_mini.yaml --strict
```

---

## 7. 최종 확인 질문

- 이 실험은 학습을 전혀 하지 않는가? → **Yes**
- 반복의 의미를 seed 변화로 설명할 수 있는가? → **Yes**
- 데이터셋은 모든 반복에서 동일한가? → **Yes**
- 결과 분산은 fold가 아니라 seed 기준인가? → **Yes**

---

## 8. 최종 권장 운영 문구 (README/지시서용)

1. **본 연구는 학습/튜닝을 수행하지 않는다 (Zero-shot only).**
2. **평가는 valid_file(+gold)에서만 수행한다.**
3. **리허설(mini)과 본실험(real)은 동일 파이프라인/동일 설정이며 데이터만 다르다.**
4. **반복은 fold가 아니라 seed 기반이며, seed별 run_id를 분리하여 저장한다.** (run_pipeline이 `run_id__seed42` 등으로 자동 부여)
5. **mini split은 파이프라인 점검 목적이며(보고 제외), 라벨은 gold JSONL에만 존재한다.** (train/valid CSV에는 id, text만)
