# Scorecard and Trace Schema (CBL ABSA Pipeline)

## 1. scorecard.jsonl (per-sample)

Each line is a JSON object with the following **required / extended** fields.

### Top-level

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | string | Run identifier (e.g. `run_proposed`). |
| `profile` | `"smoke"` \| `"regression"` \| `"paper_main"` | Latency/profile for this run. |
| `meta` | object | `text_id`, `mode`, `input_text`, `case_type`, `split`, `manifest_path`, `cfg_hash`, `profile`. |
| `ate` | object | ATE metrics; see below. |
| `atsa` | object | ATSA metrics; see below. |
| `validator` | array | Normalized validator output per stage; see below. |
| `moderator` | object | Moderator decision; see below. |
| `stage_delta` | object | Stage1↔Stage2 change summary; see below. |
| `latency` | object | Latency and gate status; see below. |
| `flags` | object | `parse_failed`, `generate_failed`, `fallback_used` (boolean). |
| `aux_signals` | object | Append-only aux signals (e.g. HF); toggleable. See below. |
| `correctness` | object | **Label experiments only.** Post-hoc evaluator only; Validator/Moderator unchanged. See below. |
| `triplet_correctness` | array | Optional; per-triplet correctness for transition aggregation. See below. |

### `correctness` (label experiments only; filled by post-hoc evaluator)

Sample-level correctness snapshot. **Validator / Moderator are not modified**; this block is written by a post-hoc evaluator after gold is available.

```json
"correctness": {
  "stage1": {
    "is_correct": true,
    "matched_triplets": 2,
    "gold_triplets": 3
  },
  "stage2": {
    "is_correct": false,
    "matched_triplets": 1,
    "gold_triplets": 3
  }
}
```

- Used by `transition_aggregator.py`: C1 = `stage1.is_correct`, C2 = `stage2.is_correct` → Fix (C1=0,C2=1), Keep (C1=1,C2=1), Break (C1=1,C2=0), StillWrong (C1=0,C2=0).

### `triplet_correctness` (optional; per-triplet)

More precise than sample-level `correctness` when aggregating by triplet:

```json
"triplet_correctness": [
  {
    "triplet_id": "g1",
    "stage1_correct": false,
    "stage2_correct": true
  }
]
```

- If present, transition aggregator can derive sample-level (e.g. sample correct iff all triplets correct) or aggregate per-triplet counts.

### `ate`

- Canonical source for **hallucinated aspect**: derive from filtered drop or set `ate.hallucination_flag` when aspect does not match input span.
- Fields: `aspect_judgements`, `missing_aspects`, `valid_aspect_rate`, `span_ok_rate`; optional `hallucination_flag` (boolean).

### `atsa`

- Canonical source for **unsupported polarity**: `atsa.evidence_flags` or sentiment_judgements with `opinion_grounded` / `evidence_relevant`.
- Fields: `sentiment_judgements`, `mean_attribution_score`, `opinion_grounded_rate`, `evidence_relevance_score`; optional `evidence_flags`.

### `validator` (array of stage blocks)

Each element (stage1 / stage2) has the **same schema** for S1/S2 comparison:

```json
{
  "stage": "stage1" | "stage2",
  "structural_risks": [
    {
      "risk_id": "NEGATION_SCOPE" | "CONTRAST_SCOPE" | "POLARITY_MISMATCH" | "EVIDENCE_GAP" | "SPAN_MISMATCH" | "OTHER",
      "severity": "low" | "mid" | "high",
      "span": [start, end],
      "description": ""
    }
  ],
  "proposals": [
    {
      "target": "ATE" | "ATSA",
      "action": "revise_span" | "revise_polarity" | "recheck_evidence" | "other",
      "reason": ""
    }
  ]
}
```

- Canonical source for **negation/contrast failure**: `validator[*].structural_risks` (risk_id NEGATION_SCOPE, CONTRAST_SCOPE).

### `moderator`

```json
{
  "selected_stage": "stage1" | "stage2",
  "applied_rules": ["RuleA", "RuleC", ...],
  "decision_reason": "",
  "final_label": "",
  "confidence": float,
  "arbiter_flags": {
    "stage2_rejected_due_to_confidence": true | false,
    "validator_override_applied": true | false,
    "confidence_margin_used": float
  }
}
```

- Enables metrics: why Stage2 was accepted/rejected; guided vs unguided change.

### `stage_delta`

```json
{
  "changed": true | false,
  "change_type": "guided" | "unguided" | "none",
  "related_proposal_ids": []
}
```

- Canonical source for **Stage1↔Stage2 change** and **guided vs unguided** aggregation.

### `latency`

```json
{
  "total_ms": int | null,
  "gate_threshold_ms": int,
  "gate_status": "PASS" | "WARN" | "FAIL",
  "profile": "smoke" | "regression" | "paper_main"
}
```

- Policy: per `latency_gate_config.yaml`, latency gate is **WARN only** (never FAIL) for smoke / regression / paper_main.

### `aux_signals` (append-only; no impact on Validator/Moderator)

When `pipeline.aux_hf_enabled` and `pipeline.aux_hf_checkpoint` are set, HF runs after Stage1/Stage2/Moderator and only attaches to the scorecard:

```json
"aux_signals": {
  "hf": {
    "task": "sentiment",
    "label": "pos" | "neg" | "neu",
    "confidence": 0.0,
    "model_id": "distilbert-... (optional)",
    "disagrees_with": {
      "stage1_final": true | false,
      "stage2_final": false
    }
  }
}
```

- HF does **not** affect Validator/Moderator; it is for metrics/stratification only.
- To disable: do not set `aux_hf_enabled` or set `aux_hf_checkpoint` to empty.

### Structural error canonical sources (Task 3)

| Error type | Canonical location |
|------------|--------------------|
| Hallucinated aspect | `ate.hallucination_flag` or derived from ate filtered drop |
| Unsupported polarity | `atsa.evidence_flags` / sentiment_judgements issues |
| Polarity conflict | aggregator / merged `conflict_flags` or moderator RuleM |
| Negation/contrast failure | `validator.structural_risks` (risk_id) |
| Stage1↔Stage2 change | `stage_delta` |
| Self-consistency / risk-set | merged_scorecards (multi-run) |

---

## 2. trace.jsonl (per-sample)

Each line is a JSON object (case trace) with:

| Field | Type | Description |
|-------|------|-------------|
| `uid` | string | Example/case id. |
| `run_id` | string | Run id. |
| `stages` | array | Per-stage entries (process_trace); each can include `output`, `call_metadata`. |
| `prompt_hash` | string | Hash of prompt_versions for reproducibility. |
| `prompt_versions` | object | Optional; name → sha256 per prompt. |
| `latency_sec` | float | Wall-clock latency. |
| `meta` | object | Same as result.meta. |

- **proposal_id ↔ stage2 change**: link via `stage_delta.related_proposal_ids` in the **scorecard** for the same case; trace `stages` contain Validator output with correction_proposals that can be indexed by id.

---

## 3. 메트릭 채점(평가)이 이루어지는 위치와 인풋 데이터

### 채점이 이루어지는 곳

| 경로 | 채점 수행 위치 | 설명 |
|------|----------------|------|
| **gold_triplets** | `build_paper_tables.py`, `build_metric_report.py` | scorecard에 `gold_triplets`(또는 `inputs.gold_triplets`)가 있으면, **예측 triplet vs gold triplet** 비교(F1, Fix/Keep/Break/StillWrong)를 이 스크립트들이 수행합니다. 즉 채점은 **리포트/페이퍼 테이블 빌더 내부**에서 이루어집니다. |
| **correctness / triplet_correctness** | **post-hoc evaluator (별도 구현)** | `correctness`·`triplet_correctness`는 **파이프라인/Validator/Moderator가 채우지 않습니다.** 정답과 비교해 `is_correct` 등을 채우는 것은 **post-hoc evaluator**가 하며, 이 레포에는 해당 evaluator 구현이 없습니다. 채워진 scorecard를 `transition_aggregator.py`가 읽어 Fix/Keep/Break/StillWrong만 **집계**합니다. |

### 인풋 데이터: 파이프라인 인풋과 동일한가?

- **파이프라인 인풋**: `run_experiments`는 설정의 `data.train_file` / `valid_file` / `test_file`로부터 `load_datasets()`로 `InternalExample`(uid, text, label, metadata 등)을 읽습니다. **분석 파이프라인에 들어가는 인풋**은 이 데이터셋 행(동일 CSV/JSON)입니다.
- **채점용 gold**:
  - **gold_triplets 경로**: 채점은 scorecard **한 건 단위**로 `gold_triplets`를 읽어 수행합니다. **config에 `eval.gold_valid_jsonl` / `eval.gold_test_jsonl`이 있으면** run_experiments가 해당 JSONL을 읽어 uid별 gold를 scorecard `inputs.gold_triplets`에 자동 주입합니다. 없으면 “파이프라인과 동일한 인풋(같은 데이터셋 행)”으로 채점하려면, (1) 같은 데이터셋에서 gold triplet을 만들고 (2) **별도 후처리**로 각 scorecard 행(uid/text_id 기준)에 `gold_triplets`(또는 `inputs.gold_triplets`)를 붙여야 합니다. 즉 **논리적으로는 동일 인풋(같은 행)**이지만, **현재 파이프라인은 채점용 gold를 자동 주입하지 않습니다.**
  - **correctness 경로**: post-hoc evaluator가 **파이프라인 출력(scorecard) + gold(예: gold.json 또는 동일 데이터셋에서 추출)**를 uid/text_id로 매칭해 채점한 뒤 `correctness`/`triplet_correctness`를 scorecard에 기록합니다. 이때 gold는 파이프라인 인풋과 **동일 데이터셋(같은 행)**에서 뽑을 수 있습니다.
- **요약**: 채점은 (1) gold_triplets가 scorecard에 있을 때는 **build_paper_tables / build_metric_report**에서, (2) correctness가 scorecard에 있을 때는 **transition_aggregator**가 이미 채워진 값만 집계합니다. **config에 eval.gold_valid_jsonl / gold_test_jsonl을 두면** run_experiments가 gold를 scorecard에 자동 주입하므로, 인풋 데이터는 파이프라인과 동일한 데이터셋(같은 uid 행)을 쓰면 됩니다.

---

## 4. 실험 설정 YAML과 eval 블록

- **run_purpose**: config에 `run_purpose: paper` 등으로 지정 가능. 없으면 config 경로 basename으로 추론.
- **eval** (선택): `gold_valid_jsonl`, `gold_test_jsonl` 경로. **절대경로**이면 그대로 사용, **상대경로**이면 `data.dataset_root` 기준으로 resolve. **필요한 split만 지정**하면 됨 (예: 채점을 VALID만 쓰면 `gold_valid_jsonl`만 두고 `gold_test_jsonl` 생략 가능). 있으면 run_experiments가 uid별 `gold_triplets`를 scorecard에 넣고, manifest에 실제 사용한 경로만 `eval: { gold_valid_jsonl?, gold_test_jsonl? }` 로 기록.
- **Gold JSONL**: 한 줄에 한 샘플. `uid`(또는 `text_id`), `gold_triplets`: list of {aspect_ref/term, opinion_term, polarity/label}.
- **UID 매칭**: run_experiments는 `uid_to_gold[example.uid]`로 골드를 주입합니다. **CSV에 `id` 또는 `uid` 컬럼이 있으면** 로더(`data/datasets/loader.py`)가 해당 값을 예제 uid로 사용하므로, gold JSONL의 uid와 일치해야 합니다. CSV에 id/uid가 없으면 uid가 `{파일명}:{행번호}`로 설정되어 gold JSONL의 uid와 맞지 않아 **골드 기반 메트릭(ΔF1, FixRate, BreakRate 등)이 채워지지 않습니다.**

### DATASETS 디렉터리와 물리적 하위 폴더 (train/valid/test)

파이프라인은 **디렉터리 구조**가 아니라 config에 적힌 **파일 경로**만 사용합니다. `data.train_file` / `valid_file` / `test_file`이 **실제 파일을 가리키면** 하위 폴더 구조는 자유롭게 둬도 됩니다.

- **예: 하위 폴더 구조**
  - `DATASETS/` (또는 `dataset_root`로 쓰는 폴더)
    - `train/train.csv`
    - `valid/valid.csv`
    - `test/test.csv`
- **config 예 (상대 경로)**  
  `dataset_root`가 `DATASETS`일 때:
  - `train_file: train/train.csv`
  - `valid_file: valid/valid.csv`
  - `test_file: test/test.csv`
- **allowed_roots**: `dataset_root`를 포함한 루트를 넣어 두면, 위처럼 resolve된 경로(`DATASETS/train/train.csv` 등)는 자동으로 허용됩니다. **코드 수정 없이** 하위 폴더 사용 가능합니다.

### 효율적인 데이터 관리·파이프라인 수정 최소화

- **절대경로 사용**: gold 파일이 데이터셋 루트 밖에 있으면 `eval.gold_valid_jsonl` 등에 **절대경로**를 주면 됨. 코드 변경 없이 지원됨.
- **VALID만 채점**: 리포트를 valid split만 쓰면 `eval`에 `gold_valid_jsonl`만 두고 `gold_test_jsonl`은 비우거나 생략. test gold는 나중에 추가해도 됨.
- **한 곳에 gold 보관**: 예) `eval.gold_valid_jsonl: /data/absa/gold/valid.gold.jsonl` 처럼 채점용 gold를 한 디렉터리에 두고, 여러 실험 config에서 동일 경로를 참조하면 데이터 중복 없이 관리 가능.
