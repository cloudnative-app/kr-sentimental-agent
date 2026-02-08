# Memory Growth Analysis — Go/No-Go 체크리스트

## 구조

- [x] C1 / C2 / C2_silent 모두 동일 집계 코드 사용 (`analysis/memory_growth_analysis.py`, `--memory_mode all|off|on|silent`)
- [x] silent에서 `advisories_present == false` 확인 (C2_silent 시 masked_injection; 트레이스에 따라 기록됨)
- [x] follow_rate가 silent에서 0 또는 N/A (advisories_present가 없으면 follow_rate 분모 0 → N/A)

## 해석

- [x] "learning", "training" 관련 변수 없음
- [x] 주요 메트릭은 risk / usage / stability 중심 (store_size, advisory_presence_rate, follow_rate, mean_delta_risk_*, harm_rate_*)
- [x] 정확도/F1은 **보조지표**로 선택 포함 가능 (trace에 tuple_f1_s2, correct 또는 --scorecards 병합 시)

## 입력/출력

- 입력: `results/<run_id>/traces.jsonl` (flat, CaseTraceV1_1 nested, 또는 run_experiments 최소 trace: uid/stages/final_result)
- `--scorecards` 사용 시: 메모리 off에서도 RQ 메트릭(mean_tuple_f1_s2, accuracy_rate) 출력; 메모리 성장 관련 필드는 null
- 출력: `results/<run_id>/memory_growth_metrics.jsonl` (윈도우 단위 JSONL, canonical 키 일괄 출력)
- 시각화: `analysis/plot_memory_growth.py` (matplotlib)

## 파이프라인

- `build_metric_report.py`: `memory_growth_metrics.jsonl` 없고 `traces.jsonl`·`scorecards.jsonl` 있으면 `memory_growth_analysis.py` 자동 실행 (window=min(50, len(scorecards)))
- 메모리 off run에서도 Memory Growth 섹션에 RQ 메트릭 테이블 표시 (null 필드는 "—")
