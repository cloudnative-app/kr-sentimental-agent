# 리허설 실험(experiment_mini) 체크리스트 검증 보고

## 1. 파이프라인 수정 사항 (런타임 초과 대응)

- **--seed N**: seed 반복 시 **한 시드만** 실행. 5시드 한 번에 돌리면 길어져서 환경 타임아웃에 걸릴 수 있으므로, 시드별로 나눠 실행할 수 있음.
  - 예: `python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics --seed 42`
  - 동일 config로 `--seed 123`, `--seed 456`, `--seed 789`, `--seed 101` 각각 실행하면 `experiment_mini__seed42_proposed`, … 디렉터리에 결과가 나뉘어 저장됨 (덮어쓰기 없음).
- **--timeout SECONDS**: (선택) 스텝당 최대 초. 기본값 없음(무제한). 환경 제한이 있으면 사용 가능.
- **seed 반복 시 run_id/outdir**: `experiment.repeat.mode: seed`이고 `seeds`가 있으면, `run_pipeline`이 시드마다 `run_id__seedN`으로 한 번씩 실행해 결과 디렉터리를 분리함.

## 2. 리허설 체크리스트 검증 결과

### A. 리허설 목적 (개념)

| 항목 | 상태 | 비고 |
|------|------|------|
| 본실험과 동일 파이프라인(stage2, validator, leakage_guard) | ✅ | experiment_mini.yaml에 동일 설정 |
| 본실험과 동일 실행 규칙(zero-shot, seed 반복) | ✅ | demo.k=0, experiment.repeat.mode=seed |
| 데이터만 작고 규칙 동일 | ✅ | mini/ (train 480, valid 121) |
| 결과 “구조” 동일 여부 확인 | ⏳ | 실행 성공 시 scorecard·metric 구조로 확인 |

### B. 데이터 무결성

| 항목 | 상태 | 비고 |
|------|------|------|
| mini/train.csv, mini/valid.csv 서로 다른 파일 | ✅ | 경로·내용 상이 |
| CSV 컬럼 id, text만 (label/polarity 없음) | ✅ | train/valid 모두 id, text |
| valid.gold.jsonl의 uid와 valid.csv의 id 완전 일치 | ✅ | 121건 모두 일치 (gold.uid ⊂ valid.id) |
| gold는 valid에만 (train에는 gold 없음) | ✅ | valid.gold.jsonl만 존재 |
| dataset_root 하위, allowed_roots 통과 | ✅ | mini/ 경로, check_experiment_config 통과 |

### C. 분할 규칙 (리허설 전용)

| 항목 | 상태 | 비고 |
|------|------|------|
| KFold 미사용 | ✅ | make_mini_dataset.py는 train_test_split 1회만 |
| train_test_split 1회 | ✅ | stratify=None, random_state=42 |
| random_state 고정(42) | ✅ | |
| stratify=None (권장) | ✅ | |

### D. 실행 설정

| 항목 | 상태 | 비고 |
|------|------|------|
| run_purpose: paper | ✅ | |
| demo.k = 0 | ✅ | check_experiment_config 통과 |
| demo.enabled_for = [] | ✅ | |
| blind_set = [] | ✅ | |
| report_sources = ["valid_file"] | ✅ | |
| experiment.repeat.mode = seed | ✅ | |
| seed 목록 본실험과 동일 | ✅ | [42, 123, 456, 789, 101] |

### E. 반복 실행 구조

| 항목 | 상태 | 비고 |
|------|------|------|
| 시드마다 run_id/outdir 분리 | ✅ | experiment_mini__seed42_proposed 등 |
| 결과 덮어쓰기 없음 | ✅ | --seed N 또는 자동 seed 반복 시 분리 |
| 시드별 결과 나중에 묶어 집계 가능 | ✅ | run_id prefix로 묶을 수 있음 |

### F. 결과 구조 (실행 성공 시)

| 항목 | 상태 | 비고 |
|------|------|------|
| 모든 시드에서 동일 출력 스키마 | ⏳ | 실행 완료 후 확인 |
| scorecard에 gold_triplets 주입 | ⏳ | run_experiments 성공 시 |
| metric 계산 | ⏳ | build_paper_tables 등 성공 시 |
| split_overlap/leakage 경고 0 | ⏳ | run_snapshot 등으로 확인 |

## 3. 실행 실패 원인 및 재실행 방법

- **실패 로그**: `run_experiments` 단계에서 `ModuleNotFoundError: No module named 'openai'` 발생.
- **원인**: 파이프라인이 사용한 Python이 **venv가 아닌 시스템(Store) Python**이어서, `openai` 패키지가 없는 환경에서 실행된 것으로 보임.
- **해결**: **venv를 활성화한 뒤** 같은 명령을 다시 실행.

```powershell
# venv 활성화 (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# 한 시드만 실행 (타임아웃 회피 권장)
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics --seed 42

# 5시드 모두 한 번에 실행 (시간 오래 걸릴 수 있음)
python scripts/run_pipeline.py --config experiments/configs/experiment_mini.yaml --run-id experiment_mini --mode proposed --profile paper --with_metrics
```

- LLM 프로바이더는 환경변수로 설정되어 있다고 가정 (venv 환경에서 동일하게 적용).

## 4. Fail-Fast 규칙 점검

- **개념**: demo.k=0, enabled_for에 stage 없음, experiment.repeat.mode=seed → check_experiment_config에서 통과.
- **데이터**: valid_file·gold_valid_jsonl 있음, CSV에 label/polarity 없음, gold.uid ⊂ valid.id → 검증 완료.
- **평가**: report_sources=["valid_file"], blind_set·test_file 미사용, report_set=["valid"] → 설정 일치.
- **반복**: 시드별 run_id/outdir 분리(—seed 사용 시에도 동일) → 충족.
- **무결성/누수**: leakage_guard 등은 실행 완료 후 스냅샷/로그로 확인.

## 5. 한 줄 요약

리허설 실험은 “작은 데이터로 본실험 규칙이 그대로 작동하는지 확인하는 절차”이며, 성능/통계가 아니라 **구조와 규칙**을 본다.  
현재 **설정·데이터·분할·실행 구조**는 체크리스트 기준을 만족하며, **실제 파이프라인 실행과 결과 구조 검증**은 venv에서 위 명령으로 재실행한 뒤 완료할 수 있다.
