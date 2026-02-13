# Scorecard / Manifest 검증 (A·B·C)

검증일: 2026-02-09  
대상: `results/experiment_real_n100_seed1_c1_1__seed1_proposed`

---

## A. Aggregator가 읽는 파일이 “진짜 run 결과 scorecards.jsonl”인가?

**조치**: Triptych에서 `gold_n_pairs > 0`인 한 행(text_id=`nikluge-sa-2022-train-02669`)을 골라, 동일 text_id의 scorecard 한 행을 검사.

**결과** (c1_1 scorecards.jsonl 1행):

| 항목 | 값 |
|------|-----|
| text_id | nikluge-sa-2022-train-02669 |
| **runtime.parsed_output.final_result** | **있음 (True)** |
| **inputs.gold_tuples** | **있음 (True), len=1** |
| meta.run_id | experiment_real_n100_seed1_c1_1__seed1_proposed |

**결론**:  
- 각 행에 `runtime.parsed_output.final_result`가 있고,  
- gold 주입 run인 경우 `inputs.gold_tuples`도 존재함.  
→ Aggregator가 읽는 `results/.../scorecards.jsonl`은 **run 결과와 동일한 구조**(runtime.parsed_output + inputs.gold_tuples)를 가진 정상 scorecard임.

---

## B. manifest.json에 gold 경로가 기록되어 있는가?

**조치**: `results/.../manifest.json`에서 `gold` / `eval.gold` / `gold_jsonl` 키 검색.

**결과**:

1. **상위 eval 블록**  
   `"eval": { "gold_valid_jsonl": "C:\\...\\experiments\\configs\\datasets\\real_n100_seed1\\valid.gold.jsonl" }`
2. **cfg_canonical (문자열)**  
   `"eval\": {\"gold_valid_jsonl\": \"real_n100_seed1/valid.gold.jsonl\"}`

**결론**:  
run_experiments가 gold를 주입한 run이라면, manifest(및 run config snapshot)에 `eval.gold_valid_jsonl`이 남는 것이 맞음. **현재 manifest에 gold 경로가 기록되어 있음.**

---

## C. scorecard_from_smoke로 “재생성”한 scorecards가 run 결과를 덮어쓴 적이 있는가?

**상황 요약**:

- **Run 결과**: `run_experiments`가 실행 시 `outputs.jsonl`(또는 동일한 pipeline 출력)을 만들고, 같은 run에서 `make_scorecard`로 **scorecards.jsonl**을 생성하며, 이때 `eval.gold_valid_jsonl`에서 읽은 gold를 `inputs.gold_tuples`로 주입함.
- **재생성**:  
  - 1차: `scorecard_from_smoke.py --smoke results/.../outputs.jsonl` **만** 실행 → 같은 경로 `results/.../scorecards.jsonl`에 기록 → **gold 없이 덮어씀 (gold 증발)**.  
  - 2차: `scorecard_from_smoke.py --smoke .../outputs.jsonl --gold experiments/configs/datasets/real_n100_seed1/valid.gold.jsonl` 실행 → **동일 경로에 다시 쓰며 gold 주입**.

**조치**:  
- `scorecards.jsonl`: 라인 수 100, 파일 크기 ~8.8MB, LastWriteTime = 재생성 시각.  
- `meta.run_id`: `experiment_real_n100_seed1_c1_1__seed1_proposed` (run과 일치).  
- `meta.source` 또는 “run_experiments vs scorecard_from_smoke” 구분 필드는 **없음**.

**결론**:

- **예, 재생성이 run 결과 scorecards.jsonl을 덮어쓴 적이 있음.**  
  - `--gold` 없이 재생성하면 gold가 사라짐.  
  - `--gold`를 주면 같은 경로에 덮어쓰지만, **입력은 동일 run의 outputs.jsonl**이므로 “진짜 run 결과”에서 나온 내용을 기반으로 한 scorecard임.
- **현재 파일**은 `scorecard_from_smoke`로 **`--gold`를 넣어 재생성한 버전**이며,  
  - `runtime.parsed_output`는 run 결과(outputs.jsonl)와 동일하고,  
  - `inputs.gold_tuples`는 지정한 gold 파일에서 주입된 상태임.
- **권장**:  
  - 수동 재생성 시에는 반드시 **`--gold`에 config의 gold 경로**(예: `experiments/configs/datasets/real_n100_seed1/valid.gold.jsonl`)를 넘길 것.  
  - run과 재생성 구분이 필요하면, 예를 들어 `meta.source: "scorecard_from_smoke"` 같은 필드를 추가하는 것을 고려할 수 있음.

---

## 요약 표

| 항목 | 결과 |
|------|------|
| A. runtime.parsed_output.final_result + inputs.gold_tuples | ✅ 동일 text_id 한 행에서 둘 다 존재 |
| B. manifest에 gold 경로 (eval.gold_valid_jsonl) | ✅ 존재 |
| C. 재생성으로 run 결과 덮어쓰기 | ✅ 있음; 현재는 --gold로 재생성한 버전이라 gold 있음. 재생성 시 --gold 필수. |
