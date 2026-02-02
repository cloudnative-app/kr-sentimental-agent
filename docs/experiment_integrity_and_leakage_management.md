# 실험 무결성·스플릿 중복·데모 누수 관리 정리 및 개선안

README0과 코드 기준으로, **실험 무결성**, **스플릿 중복 탐지**, **데모 누수 방지** 설정과 데이터 역할·파이프라인 연결 관계를 정리하고, **누수 방지와 관리를 쉽게 하는 개선안**을 Pro/Con과 함께 제시합니다. 파이프라인 구조는 유지합니다.

---

## 1. 현재 설정 요약 (README0 §8, §9 기준)

| 항목 | 내용 |
|------|------|
| **실험 무결성** | 텍스트만 LLM 입력. 데모는 train만 사용. `demo_k=0` 기본. RunManifest에 `cfg_hash`, prompt versions, `allowed_roots`, `integrity` 기록. CaseTrace에 uid, `input_hash`, call_metadata. |
| **스플릿 중복 탐지** | `build_run_snapshot`에서 `input_hash` 기준 train/valid/test 간 중복률 계산 → `split_overlap_any_rate`, `split_overlap_pairs`. paper 프로파일에서는 0이어야 정상. |
| **데모 누수 방지** | `forbid_hashes`: valid/test 텍스트 해시 집합을 데모 풀에서 제외. paper 런에서 자동 활성화(`run_purpose==paper` 또는 `demo.hash_filter: true`). UID 기반 `forbid_uids`도 적용. |
| **Leakage guard** | `pipeline.leakage_guard: true` 시 입력 텍스트/메타에 정답·라벨·주석 용어 검출 시 RuntimeError. |
| **Run purpose** | `smoke` / `sanity` / `paper` / `dev`. smoke/sanity는 paper 테이블 빌더에서 `--force` 없이 거부. |

---

## 2. 데이터 양식·역할과 연결 관계

### 2.1 스플릿 파일 양식 (data 블록)

| 역할 | config 키 | 양식 | 비고 |
|------|------------|------|------|
| 학습 풀(데모 소스) | `train_file` | CSV: `id`, `text` (라벨 없음) | `data_roles.demo_pool`에 포함되는 split만 데모 풀에 사용 |
| 검증(리포트) | `valid_file` | 동일 | `report_set` → 메트릭/리포트에 포함 |
| 테스트(블라인드) | `test_file` | 동일 | `blind_set` → 블라인드 평가용 |

- **규칙**: 데모는 **train만** 사용(`demo_pool: [train]`). valid/test는 데모에 쓰이면 안 됨(UID·해시로 제외).
- **골드**: 채점용은 `eval.gold_valid_jsonl` / `eval.gold_test_jsonl`에 별도 JSONL. CSV와 **uid 일치** 필요(로더는 CSV `id`/`uid` 컬럼 → `InternalExample.uid`).

### 2.2 데이터 역할(data_roles)

| 키 | 의미 | 기본값 | 파이프라인 사용처 |
|----|------|--------|-------------------|
| `demo_pool` | 데모로 쓸 수 있는 split | `[train]` | run_experiments: 데모 샘플링 풀 (k=0이면 사실상 미사용) |
| `tuning_pool` | (미사용) 튜닝 후보 split | `[]` | 현재 미사용 |
| `report_set` | 메트릭/리포트에 넣을 split (fallback) | `[valid]` | report_sources 없을 때 사용 |
| `blind_set` | 블라인드 평가용 split (fallback) | `[test]` | blind_sources 없을 때 사용 |
| **`report_sources`** | **리포트에 쓸 데이터 소스 (파일 키)** | 없음 | **paper 런 필수**. 예: `["valid_file"]` 또는 `["test_file"]` |
| **`blind_sources`** | **블라인드 평가용 데이터 소스 (파일 키)** | 없음 | **paper 런 필수**(빈 배열 `[]` 가능). 예: `["test_file"]` |

- **소스 기반(sources)**: `report_sources` / `blind_sources`가 있으면 **스플릿 이름이 아닌 파일 소스**로 평가 행을 결정. `train_file`→train, `valid_file`→valid, `test_file`→test로 매핑. 폴드에서 valid가 없거나 test로 대체되는 혼란이 사라짐.
- **eval 해시**: `report_sources ∪ blind_sources`(있을 때) 또는 `report_set ∪ blind_set`에 해당하는 split 예제의 텍스트 해시를 `forbid_hashes`로 전달 → 데모에서 동일/유사 문장 제외. manifest에 `integrity.forbid_hashes_source` 기록.

### 2.3 프로파일·목적별 설정

| 목적 | run_purpose | 용도 | 스플릿 중복 | paper 테이블 | 데모 해시 필터 |
|------|-------------|------|-------------|--------------|----------------|
| smoke | smoke | 스모크 테스트(동일 파일 재사용 가능) | 허용(경고) | 거부(—force 시 DO NOT REPORT) | 선택(`demo.hash_filter`) |
| sanity | sanity | 무결성/스키마 검증 | 허용(경고) | 거부(—force 시 DO NOT REPORT) | 선택 |
| paper | paper | 논문/본실험 | 0이어야 pass | 허용 | 자동 on |
| dev | dev | 개발·디버깅 | 경고만 | 허용 | 선택 |

- **run_purpose** 추론: config의 `run_purpose` > config 경로 basename(`smoke`/`sanity` 포함 시 해당).

### 2.4 파이프라인에서의 연결

```
config (YAML)
  ├── data (train/valid/test 파일, dataset_root, allowed_roots)
  ├── data_roles (demo_pool, report_set, blind_set, report_sources, blind_sources, tuning_pool)
  ├── eval (gold_valid_jsonl, gold_test_jsonl)
  ├── demo (k, seed, hash_filter, enabled_for, force_for_proposed)
  ├── pipeline (leakage_guard, strict_integrity, ...)
  └── run_purpose (선택)

run_experiments
  → 데이터 로드 (train/valid/test)
  → eval_splits = report_sources/blind_sources 있으면 파일 키→split 매핑, 없으면 report_set ∪ blind_set
  → eval_splits 텍스트 해시 → forbid_hashes (paper 또는 hash_filter 시)
  → 데모 샘플링 시 forbid_uids(forbid_hashes) 적용
  → 골드 있으면 uid별 gold_triplets scorecard에 주입
  → manifest 작성 (data_roles 기록), integrity.forbid_hashes_source 기록(소스 사용 시)

build_run_snapshot
  → scorecards/traces에서 input_hash별 split 분류
  → split_overlap_any_rate 계산 → run_snapshot.md에 기록

build_paper_tables / build_metric_report
  → manifest.purpose 가 smoke/sanity면 --force 없이 거부
  → report_splits = manifest.data_roles.report_sources → split 이름 (있으면), else report_set (기본 ["valid"])
```

---

## 3. 데모·페이퍼 정책 요약 (필수 준수)

- **데모 풀**: 데모는 **반드시 train만** 사용. `data_roles.demo_pool: [train]` 권장. valid/test를 demo_pool에 넣으면 **누수**.
- **데모 개수**: 논문/본실험에서는 `demo.k: 0` 사용 권장. 데모를 쓸 경우에도 eval split(valid/test)과 UID·텍스트 해시 중복 없어야 함.
- **해시 필터**: `run_purpose: paper`이면 **자동** `forbid_hashes` 적용(valid/test 텍스트 해시를 데모에서 제외). config에 `demo.hash_filter: true` 명시해도 됨.
- **Leakage guard**: 본실험 시 `pipeline.leakage_guard: true` 유지. 입력 텍스트/메타에 정답·라벨·주석 용어가 들어가면 RuntimeError.
- **Paper 런 스플릿**: paper 목적이면 train/valid/test **파일 경로가 서로 달라야** 함(동일 파일 재사용 시 스플릿 중복으로 run_snapshot에서 경고).
- **report_sources / blind_sources**: paper 런에서는 **필수**. `report_sources: ["valid_file"]` 또는 `["test_file"]`, `blind_sources: ["test_file"]` 또는 `[]` 등으로 명시. 스키마·check_experiment_config에서 검사.
- **실행 전 검사**: paper 또는 엄격한 런 전에 `python scripts/check_experiment_config.py --config <config.yaml> --strict` 실행 권장.

---

## 3.1 리포트·블라인드·골드 경로·형식 규칙 (F)

- **데이터셋 경로**: `data.dataset_root`는 **반드시** `data.allowed_roots` 중 하나의 하위 경로여야 함. `check_experiment_config`에서 검사.
- **리포트/블라인드용 파일**: report_set·blind_set에 쓰는 train/valid/test 파일은 `dataset_root` 기준 상대 경로 또는 allowed_roots 내 절대 경로 사용. 일관성 위해 `experiments/configs/datasets/` 하위 배치 권장.
- **골드**: 채점용 골드는 **반드시** config의 `eval.gold_valid_jsonl` / `eval.gold_test_jsonl`로만 지정. JSONL 한 줄: `{"uid" 또는 "text_id": "...", "gold_triplets": [...]}`. 상대 경로는 `dataset_root` 기준으로 resolve.
- **CSV id/uid 컬럼**: 골드 uid 매칭을 위해 train/valid/test **CSV에는 `id` 또는 `uid` 컬럼이 필수**. 없으면 scorecard에 gold_triplets가 주입되지 않아 골드 기반 메트릭이 계산되지 않음. `check_experiment_config`에서 `input_format: csv`일 때 id/uid 존재 여부 검사(선택 비활성화: `--no-csv-id-check`).

### 3.2 체크리스트 요약 (실험 무결성·누수·실수 방지)

| 구분 | 내용 | 검사 위치 |
|------|------|-----------|
| **A. 설정 정합성** | report_sources/blind_sources 명시(paper), sources↔data.*_file 매핑 유효, 중복 없음, paper zero-shot(demo_k=0, demo_pool [] 또는 [train]) | check_experiment_config, 스키마 |
| **B. 데이터 무결성** | CSV id/uid·text 필수, report/blind 행 수 > 0(해당 소스 있을 때), 골드 uid 매칭 | check_experiment_config(csv_id), run_experiments(로딩) |
| **C. 누수 방지** | forbid_hashes = report_sources ∪ blind_sources 대응 split, manifest에 forbid_hashes_source 기록, leakage_guard 활성 | run_experiments |
| **D. 스냅샷·리포트** | manifest에 report_sources/blind_sources·run_purpose 기록, split_overlap_any_rate==0(paper), build_paper_tables가 manifest sources 사용 | build_run_snapshot, build_paper_tables |
| **E. 의도적 실패** | demo_pool∩eval overlap 시 스키마/검사에서 차단, 로그에 명확히 기록 | test_intentional_failure_demo_overlap_with_eval |

---

## 4. (과거) 갭 정리 — A·C·D·E·F 및 소스 기반 역할 적용 후

- **manifest에 data_roles**: ✅ 적용됨(A). run_experiments가 manifest에 `data_roles`(report_sources, blind_sources 포함)를 기록. build_paper_tables는 manifest의 report_sources→split으로 report_splits 결정(없으면 report_set fallback).
- **소스 기반 역할**: ✅ paper 런에서 `report_sources`/`blind_sources` 필수. 스키마·check_experiment_config에서 검사. forbid_hashes 출처는 manifest.integrity.forbid_hashes_source에 기록.
- **실행 전 검사**: ✅ 적용됨(C). `scripts/check_experiment_config.py --config <yaml> --strict`로 sources 명시·sources↔data 매핑·demo_pool∩eval 공집합·paper zero-shot·스플릿 파일 상이 여부 검사.
- **정책 문서화**: ✅ 적용됨(D). 위 §3 데모·페이퍼 정책 요약 및 본 문서에 기본값·필수 준수 사항 명시.
- **config 스키마 검증**: ✅ 적용됨(E). `schemas/experiment_config_schema.py`에 Pydantic 스키마 정의. check_experiment_config 실행 시 data_roles 겹침·paper demo_pool 규칙 검증. `--skip-schema`로 비활성화 가능.
- **경로·골드·CSV 규칙**: ✅ 적용됨(F). §3.1 문서화. check_experiment_config에서 dataset_root under allowed_roots, CSV id/uid 컬럼 검사. `--no-csv-id-check`로 CSV 검사만 비활성화 가능.

---

## 5. 개선안 (선택용 Pro/Con)

아래는 **파이프라인 구조를 해치지 않는 선**에서의 관리·누수 방지 강화안입니다.

---

### 방안 A: manifest에 data_roles 기록 — ✅ 적용됨

- **내용**: `_write_manifest()` 시 config의 `data_roles`를 manifest에 `data_roles` 키로 저장.
- **Pros**: build_paper_tables가 report_set을 manifest 한 곳에서만 읽음. paper_table_2에 실제 사용한 역할이 남아 감사·재현에 유리. 단일 소스.
- **Cons**: manifest 스키마 버전 확장(필드 추가). 기존 이미 돌린 런은 data_roles가 비어 있음(기본값 fallback 유지).

---

### 방안 B: “실험 프로파일” preset YAML

- **내용**: `experiments/configs/presets/paper.yaml`, `smoke.yaml` 등에서 run_purpose, data_roles, demo.k, pipeline.leakage_guard, demo.hash_filter 등을 한 번에 정의. 각 실험 config는 `extends: presets/paper.yaml` 형태로 preset을 참조.
- **Pros**: paper/smoke/blind 등 목적별로 한 파일에서 관리. 실수로 smoke 설정으로 paper 런을 돌리는 일을 줄일 수 있음.
- **Cons**: YAML extend/merge 규칙 도입 필요. 기존 config 일부를 preset으로 옮기는 작업 필요.

---

### 방안 C: 실행 전 무결성·누수 검사 스크립트 — ✅ 적용됨

- **내용**: `scripts/check_experiment_config.py`에서 (1) demo_pool ∩ (report_set ∪ blind_set) = ∅, (2) paper 시 demo_pool=[train], (3) paper 시 train/valid/test 파일 경로 상이 여부 검사. `--strict` 시 실패하면 exit 1.
- **Pros**: run_experiments 돌리기 전에 설정 오류·잠재 누수 조건을 fail-fast로 잡을 수 있음.
- **Cons**: 스크립트와 규칙 유지보수. 해시 기반 중복 체크는 파일이 클 경우 비용 고려 필요(현재는 경로 동일 여부만 검사).

---

### 방안 D: demo·paper 정책 문서화 + 기본값 강화 — ✅ 적용됨

- **내용**: README0 및 `docs/experiment_integrity_and_leakage_management.md`에 “paper 런은 demo_pool=train만, hash_filter는 paper 시 자동 on, 실행 전 check_experiment_config 권장” 등 명시. 기본값(demo_k=0, demo_pool=[train]) 정리.
- **Pros**: 구현 부담 없음. 이미 동작하는 방어(해시 필터, leakage_guard)와의 연결만 명확히 함.
- **Cons**: 설정 실수 시 탐지는 런 후 스냅샷 + 실행 전 스크립트(C)로 보완.

---

### 방안 E: config 스키마/검증 레이어 — ✅ 적용됨

- **내용**: `schemas/experiment_config_schema.py`에 Pydantic 스키마(DataRolesSchema, ExperimentConfigSchema) 정의. check_experiment_config에서 YAML 로드 후 검증: demo_pool∩(report_set∪blind_set)=∅, run_purpose=paper 시 demo_pool=[train]만 허용.
- **Pros**: 잘못된 조합을 실행 전에 차단. 타입·필수 키 누락도 함께 잡을 수 있음.
- **Cons**: 스키마 정의·버전 관리 필요. `--skip-schema`로 스키마 검사만 건너뛸 수 있음.

---

### 방안 F: 리포트·블라인드·골드 경로 규칙 정리 — ✅ 적용됨

- **내용**: §3.1에 경로·골드·CSV 규칙 문서화. check_experiment_config에서 dataset_root under allowed_roots 검사, `input_format: csv`일 때 train/valid/test CSV의 id 또는 uid 컬럼 존재 검사. 골드는 `eval.gold_valid_jsonl` / `eval.gold_test_jsonl`만 사용(문서 명시).
- **Pros**: 데이터 위치·형식 일관성, 골드 매칭 오류 감소. 파이프라인 구조는 그대로.
- **Cons**: 기존에 다른 경로를 쓰는 실험이 있으면 이전하거나 `--no-csv-id-check`로 CSV 검사만 건너뛸 수 있음.

---

## 6. 권장 조합 (선택 시 참고)

- **최소 변경**: **D + F** — 문서와 경로·형식 규칙만 정리. 누수 방지는 현재 코드(해시 필터, leakage_guard)에 맡기고, “무엇을 지켜야 하는지”만 명확히 함.
- **감사·재현 강화**: **A + D** — manifest에 data_roles를 남기고, paper 테이블/메트릭이 어떤 report_set으로 계산됐는지 추적 가능하게 함.
- **실수 방지 강화**: **A + C** 또는 **A + E** — manifest 기록(A)에 더해, 실행 전에 설정 검사(C) 또는 스키마 검증(E)으로 paper 런의 스플릿·데모 정책을 보장.

원하시는 방향(최소 변경 / 감사 강화 / 실수 방지 우선)에 따라 위 방안을 조합해 선택하시면 됩니다. **A·C·D·E·F는 이미 적용되어 있으며**, paper 런 전 `check_experiment_config.py --config <yaml> --strict` 실행과 본 문서 §3·§3.1 정책 준수를 권장합니다.
