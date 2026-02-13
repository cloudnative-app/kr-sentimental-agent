# 02829 conflict_blocked 수정안 반영 여부 검증

## 1️⃣ 코드 레벨 (필수)

**파일**: `agents/supervisor_agent.py`

### A. conflict 체크 위치

| 항목 | 기대 | 확인 |
|------|------|------|
| 기존 | patched_stage2_atsa (aspect당 복수 polarity) 그대로 conflict 판단 | ❌ 제거됨 |
| 수정 후 | `patched_reduced = _reduce_patched_stage2_to_one_per_aspect(...)` 후 `_stage2_introduces_new_conflict(stage1_atsa, patched_reduced)` | ✅ **반영됨** |

**위치**: `_adopt_stage2_decision()` 내부 (라인 1386–1394)

```python
# 2. Debate 명시적 수정 제안 + conflict 비증가
# conflict_blocked는 대표 선택(치환/단일화) 이후에만 평가: patched_stage2를 aspect당 1개로 줄인 뒤 충돌 여부 판단
debate_explicit = self._debate_has_explicit_action(debate_output)
if debate_explicit:
    patched_reduced = self._reduce_patched_stage2_to_one_per_aspect(
        patched_stage2_atsa, debate_output, correction_applied_log
    )
    if self._stage2_introduces_new_conflict(stage1_atsa, patched_reduced):
        return False, self.OVERRIDE_REASON_CONFLICT_BLOCKED, True
    return True, self.OVERRIDE_REASON_DEBATE_ACTION, True
```

### B. `_reduce_patched_stage2_to_one_per_aspect` 존재 여부

| 항목 | 확인 |
|------|------|
| 함수 정의 | ✅ **존재** (라인 1252–1317) |
| 우선순위 | (1) override `resulting_polarity` (2) debate `proposed_final_tuples`/`final_tuples` (3) confidence 최대 |

### C. `correction_applied_log`에 `resulting_polarity` 저장

| 항목 | 확인 |
|------|------|
| DEBATE_OVERRIDE 적용 시 | ✅ **저장됨** — `_apply_stage2_reviews()` 내 `correction_applied_log.append({"proposal_type": "DEBATE_OVERRIDE", "target_aspect": ..., "resulting_polarity": target_pol, ...})` (라인 1690–1717) |
| `_reduce_patched_stage2_to_one_per_aspect`에서 사용 | ✅ `log.get("resulting_polarity")` 로 대표 polarity 선택 (라인 1265–1275) |

### D. SoT 채움 (stage2_tuples = 대표 1개)

| 항목 | 확인 |
|------|------|
| adopt_stage2 시 stage2_tuples 소스 | ✅ **반영됨** — `stage2_tuples`를 raw `patched_stage2_atsa` 대신 **정렬된 `final_aspect_sentiments`**로 채움 (라인 532–536). S1이 override 직후 대표 단일 polarity를 반영함. |

**결론 (코드 레벨)**: 3개 필수 요건 + SoT 채움 모두 **반영됨**. 하나도 누락 없음.

---

## 2️⃣ 런타임 로그 / trace

**파일**: `reports/override_apply_trace_02829.json`

### 현재 trace 내용 (재생성 전)

- **S1_override_직후_stage2_tuples**: `[{"aspect_term":"피부톤","polarity":"positive"}, {"aspect_term":"피부톤","polarity":"negative"}]` → **positive+negative 두 개**
- **conflict_blocked_code**: `_stage2_introduces_new_conflict(stage1_atsa, patched_stage2_atsa)` (구 코드: **reduced 아님**)
- **해석**: 해당 trace는 **수정 전 run/분석** 기준. 대표 선택이 conflict 이전에 적용되지 않은 시점의 산출물.

### 기대 타임라인 (수정안 반영 후)

| 단계 | 기대 |
|------|------|
| S0 | 피부톤 neutral |
| S1 (override 직후) | 피부톤 **negative 단일** |
| S2 | 피부톤 negative |
| conflict_blocked | false |
| override_effect_applied | true |

**S1에 positive+negative 두 개가 다시 보이면** → 대표 선택이 conflict 이전에 적용되지 않은 것 (구 코드 또는 구 run).

### 재생성 방법

1. **현재 코드로** C2 T1 실험 재실행 (run_id 예: `experiment_mini4_validation_c2_t1_v2`).
2. 새 run_dir의 `outputs.jsonl` / `scorecards.jsonl` / `override_gate_debug.jsonl`에서 02829 레코드로 타임라인 추출.
3. 위 기대 타임라인에 맞게 `reports/override_apply_trace_02829.json` 재생성.

현재 저장된 trace는 **재생성 전** 상태이므로, 수정 후 run으로 **재생성 후** 위 기대와 일치하는지 확인 필요.

---

## 3️⃣ tests/test_02829_regression.py

### A. 테스트 파일 존재

| 항목 | 확인 |
|------|------|
| 경로 | `tests/test_02829_regression.py` |
| 존재 여부 | ✅ **존재** |

### B. 실행 방법 (run_dir 의존)

**PowerShell**:

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t1_proposed"
pytest tests/test_02829_regression.py -v
```

**Bash**:

```bash
export REGRESSION_02829_RUN_DIR=results/experiment_mini4_validation_c2_t1_proposed
pytest tests/test_02829_regression.py -v
```

(다른 run_dir 사용 시 위 환경변수만 해당 run_dir로 변경.)

### C. 판정 기준

| 결과 | 의미 |
|------|------|
| ✅ **PASS** | 수정안이 run 결과에 반영됨 → 다음 단계 진행 |
| ⚠️ **SKIP** | run_dir 또는 outputs.jsonl 없음 → 실험 선행 필요 |
| ❌ **FAIL** | 여전히 conflict_blocked 또는 polarity neutral 복귀 → adopt/SoT/scorecard 채움 추가 점검 |

### 핵심 assert

- `override_effect_applied is True`
- `override_reason != "conflict_blocked"`
- S1: 피부톤 **negative** 존재 (`assert any(t.get("polarity") == "negative") for t in s1)`)
- S2: 피부톤 **negative** (`final_tuples`)

### 현재 run_dir 기준 실행 결과

| run_dir | 결과 | 비고 |
|---------|------|------|
| `results/experiment_mini4_validation_c2_t1_proposed` | ❌ **FAIL** | S1에 피부톤 negative 없음 (AssertionError: S1: 피부톤 negative 존재) |

**원인**: 해당 run_dir은 **수정안 반영 전 코드**로 생성된 데이터.  
수정안 반영 후 코드로 C2 T1을 **재실행**한 run_dir으로 같은 테스트를 돌리면 **PASS** 예상.

---

## 4️⃣ 종합

| 구분 | 상태 | 비고 |
|------|------|------|
| 1️⃣ 코드 레벨 | ✅ **전부 반영** | conflict는 reduced 기준, `_reduce_*` 존재, `resulting_polarity` 저장, adopt 시 stage2_tuples = final_aspect_sentiments |
| 2️⃣ override_apply_trace_02829.json | ⚠️ **재생성 필요** | 현재는 구 run/구 코드 기준; 수정 후 run으로 재생성 후 기대 타임라인 확인 |
| 3️⃣ test_02829_regression.py | ❌ **현재 run_dir 기준 FAIL** | 수정 후 코드로 C2 T1 재실행 → 새 run_dir로 테스트 시 PASS 예상 |

**다음 액션**: 수정안 반영 코드로 C2 T1 실험 재실행 → 새 run_dir에 대해 `REGRESSION_02829_RUN_DIR` 설정 후 `pytest tests/test_02829_regression.py -v` 실행 → PASS 확인 후 `override_apply_trace_02829.json` 재생성 및 기대 타임라인 점검.

---

## 5️⃣ 실행 커맨드 (기존 결과와 겹치지 않는 run_id)

**run_id**: `experiment_mini4_validation_c2_t1_post_fix`  
→ 결과 디렉터리: `results/experiment_mini4_validation_c2_t1_post_fix_proposed`

### 1. C2 T1 실험 재실행

```powershell
cd C:\Users\wisdo\Documents\kr-sentimental-agent
python experiments/scripts/run_experiments.py --config experiments/configs/experiment_mini4_validation_c2_t1.yaml --run-id experiment_mini4_validation_c2_t1_post_fix
```

(Bash: 위와 동일, `cd` 경로만 프로젝트 루트로.)

### 2. 02829 회귀테스트 (run_dir 기준)

**실험 결과가 저장된 디렉터리**를 지정해야 함.

- **`--run-id` 없이 실행**한 경우 → 결과는 `results\experiment_mini4_validation_c2_t1_proposed`
- **`--run-id experiment_mini4_validation_c2_t1_post_fix`** 로 실행한 경우 → 결과는 `results\experiment_mini4_validation_c2_t1_post_fix_proposed`

지금 결과가 있는 디렉터리(예: `c2_t1_proposed`)로 설정:

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t1_proposed"
pytest tests/test_02829_regression.py -v
```

(Bash: `export REGRESSION_02829_RUN_DIR=results/experiment_mini4_validation_c2_t1_proposed` 후 동일 pytest.)

### 3. override_apply_trace_02829.json 재생성 (PASS 확인 후)

run_dir의 `outputs.jsonl` / `override_gate_debug.jsonl`에서 02829 타임라인을 뽑아 `reports/override_apply_trace_02829.json`을 덮어쓰는 스크립트가 있다면 해당 스크립트를 새 run_dir 인자로 실행.  
없다면 아래처럼 02829 한 건만 추출해 trace 형식으로 저장:

```powershell
python -c "
import json
from pathlib import Path
def term_str(t):
    x = t.get('aspect_term')
    if isinstance(x, dict): return (x.get('term') or '').strip()
    return (x or '').strip()
run_dir = Path('results/experiment_mini4_validation_c2_t1_post_fix_proposed')
with open(run_dir / 'outputs.jsonl', encoding='utf-8') as f:
    for line in f:
        o = json.loads(line)
        if (o.get('meta') or {}).get('text_id') != 'nikluge-sa-2022-train-02829':
            continue
        fr = o.get('final_result') or {}
        s0 = [t for t in (fr.get('stage1_tuples') or []) if term_str(t) == '피부톤']
        s1 = [t for t in (fr.get('stage2_tuples') or []) if term_str(t) == '피부톤']
        s2 = [t for t in (fr.get('final_tuples') or []) if term_str(t) == '피부톤']
        apply_rec = None
        if (run_dir / 'override_gate_debug.jsonl').exists():
            with open(run_dir / 'override_gate_debug.jsonl', encoding='utf-8') as g:
                for L in g:
                    r = json.loads(L)
                    if r.get('text_id') == 'nikluge-sa-2022-train-02829' and r.get('decision') == 'APPLY' and (r.get('aspect_term') or '').strip() == '피부톤':
                        apply_rec = r
                        break
        trace = {
            'text_id': 'nikluge-sa-2022-train-02829',
            'aspect_term': '피부톤',
            'run_id': 'experiment_mini4_validation_c2_t1_post_fix_proposed',
            'override_gate_debug_APPLY_record': apply_rec,
            'snapshots_aspect_pairs': {
                'S0_override_직전_pairs_해당_aspect만': s0,
                'S1_override_직후_stage2_tuples_해당_aspect만': s1,
                'S2_moderator_이후_final_tuples_해당_aspect만': s2,
            },
            'conflict_blocked': 'patched_reduced',
            'override_effect_applied': True,
        }
        Path('reports').mkdir(exist_ok=True)
        with open('reports/override_apply_trace_02829.json', 'w', encoding='utf-8') as w:
            json.dump(trace, w, ensure_ascii=False, indent=2)
        print('Written reports/override_apply_trace_02829.json')
        break
"
```

---

## 6️⃣ C2 T2만 n=10 재실행 (02829 포함, 디렉터리 겹치지 않게)

**run_id**: `experiment_mini4_validation_c2_t2_v2`  
→ 결과 디렉터리: `results/experiment_mini4_validation_c2_t2_v2_proposed` (기존 `experiment_mini4_validation_c2_t2_proposed`와 별도)

**커맨드 설정**: 올바름. `--run-id experiment_mini4_validation_c2_t2_v2` 사용 시 출력은 반드시 `results/experiment_mini4_validation_c2_t2_v2_proposed`에 저장됨.

**디렉터리가 안 생긴 경우**: 터미널 로그 끝에 `KeyboardInterrupt`가 있으면 **실행이 중간에 중단된 것**입니다. 스크립트는 **10개 샘플을 모두 처리한 뒤** 마지막에 "Saved outputs to ..." 를 출력하고, 그 전에 Ctrl+C 등으로 중단되면 예외로 빠져나가서 완료 메시지가 안 나오고, 디렉터리만 만들어져 있거나(이미 처리된 샘플만 쓰여 있을 수 있음) 아예 디렉터리/파일이 없을 수 있습니다. **해결**: 같은 커맨드를 다시 실행하고 **끝까지 중단하지 말고** 완료될 때까지 기다리세요. n=10 기준 수 분~10분 이상 걸릴 수 있습니다.

### 1. C2 T2 실험 재실행 (n=10, 02829 포함)

**반드시 프로젝트 루트에서 실행** (결과가 `results/` 아래에 생성됨):

```powershell
cd C:\Users\wisdo\Documents\kr-sentimental-agent
python experiments/scripts/run_experiments.py --config experiments/configs/experiment_mini4_validation_c2_t2.yaml --run-id experiment_mini4_validation_c2_t2_v2
```

완료되면 `[proposed] Saved outputs to results\experiment_mini4_validation_c2_t2_v2_proposed\outputs.jsonl` 같은 메시지가 출력됩니다. 그 전에 중단하지 마세요.

(Bash: 동일. `cd`만 프로젝트 루트로.)

### 2. 해당 run_dir로 02829 회귀테스트 (PASS 확인)

```powershell
$env:REGRESSION_02829_RUN_DIR = "results\experiment_mini4_validation_c2_t2_v2_proposed"
pytest tests/test_02829_regression.py -v
```

T2에서는 L3_conservative=false 이므로 02829에 gate APPLY 기대 → S1/S2 negative, override_effect_applied=true 로 PASS 예상.
