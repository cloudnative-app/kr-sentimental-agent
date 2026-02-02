# 본실험(experiment_real) 데이터 배치 안내

## 1. 목적

- **experiment_real.yaml**은 본실험(paper) 보고용 설정입니다.
- 데이터는 **단일 고정 데이터셋**을 사용하며, **폴드가 아닌 seed 반복**으로 평가합니다.
- 이 디렉터리(`real/`)에 본실험용 train/valid 파일을 두고 config에서 참조합니다.

## 2. 필요한 파일

| 파일 | 설명 |
|------|------|
| `train.csv` | 비평가 split (구조 유지·데모 풀; k=0이면 미사용). 컬럼: `id`, `text` |
| `valid.csv` | 유일한 평가(report) 데이터. 컬럼: `id`, `text` |
| `valid.gold.jsonl` | valid 행별 골드. 한 줄: `{"uid": "<id와 동일>", "gold_triplets": [...]}` |

- **경로**: `experiments/configs/datasets/real/train.csv`, `valid.csv`, `valid.gold.jsonl`
- **dataset_root**: config의 `data.dataset_root`가 `experiments/configs/datasets`이므로, 위 파일은 상대 경로 `real/train.csv` 등으로 지정됩니다.

## 3. 데이터 생성 방법

### 3.1 NIKLuge SA 2022 JSONL에서 생성하는 경우

1. 소스 JSONL을 준비합니다 (예: `experiments/configs/datasets/train/valid.jsonl` 형식).
   - 한 줄: `{"id": "...", "sentence_form": "...", "annotation": [[aspect, span_info, polarity], ...]}`

2. **단일 분할(폴드 없음)** 스크립트로 train/valid를 만듭니다.
   - 리허설용 mini 데이터와 동일한 방식:
   ```powershell
   python scripts/make_mini_dataset.py --input <소스_경로.jsonl> --outdir experiments/configs/datasets/real --valid_ratio 0.2 --seed 42
   ```
   - 출력: `real/train.csv`, `real/valid.csv`, `real/valid.gold.jsonl`

3. 본실험용으로 **다른 소스·다른 규모**의 데이터를 쓸 경우:
   - 동일한 CSV/골드 형식만 맞추어 `real/` 아래에 배치하면 됩니다.
   - `make_mini_dataset.py`는 NIKLuge 형식 JSONL 기준입니다. 다른 형식이면 별도 스크립트로 `id, text` CSV와 `uid, gold_triplets` JSONL을 생성하세요.

### 3.2 이미 CSV/골드가 있는 경우

- `train.csv`, `valid.csv`: 헤더 `id`, `text` (또는 `uid`, `text`). 각 행의 `id`/`uid`는 골드와 일치해야 합니다.
- `valid.gold.jsonl`: valid의 각 행에 대해 한 줄씩 `{"uid": "<id>", "gold_triplets": [{aspect_ref, opinion_term, polarity}, ...]}`.

## 4. 실행 전 확인

```powershell
python scripts/check_experiment_config.py --config experiments/configs/experiment_real.yaml --strict
```

- `real/` 아래에 위 세 파일이 있어야 하며, config의 `data.train_file`/`valid_file`, `eval.gold_valid_jsonl`이 이 경로를 가리켜야 합니다.

## 5. Seed 반복 실행

- 본실험은 **동일 데이터**에 대해 **시드만 바꿔** N회 반복합니다 (config의 `experiment.repeat.seeds`).
- 각 시드마다 한 번씩 실행한 뒤, 결과를 **seed 기준**으로 집계합니다 (평균 ± 표준편차, agreement 등).
- 예 (시드 5회):
  ```powershell
  # 각 시드마다 demo.seed 또는 pipeline/backbone seed override 후 실행
  python scripts/run_pipeline.py --config experiments/configs/experiment_real.yaml --run-id experiment_real --mode proposed --profile paper --with_metrics
  ```
  - 시드 변경은 config에 `demo.seed` 또는 파이프라인 제공 시드 옵션을 바꾸거나, 향후 CLI에서 `--seed 123` 등으로 지원될 수 있습니다.

## 6. 요약

| 항목 | 내용 |
|------|------|
| **위치** | `experiments/configs/datasets/real/` |
| **파일** | `train.csv`, `valid.csv`, `valid.gold.jsonl` |
| **생성** | NIKLuge 형식이면 `make_mini_dataset.py --outdir .../real`; 그 외는 동일 형식으로 직접 생성 |
| **실험** | 폴드 없음. 동일 데이터 + seed 반복(N회) 후 seed 기준 집계 |

- **mini/real split 정책**: `make_mini_dataset.py`는 `stratify=None`, `random_state=42`만 사용(라벨 기반 분할 없음). 라벨은 `valid.gold.jsonl`에만 존재하며 CSV에는 `id`, `text`만 포함.
