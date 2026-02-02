# 변경사항 상세 요약

이 문서는 최근 변경된 내용을 연구원에게 공유하기 위한 상세 요약입니다.  
핵심은 **토론(상호 논증/합의) 레이어를 파이프라인에 추가**하고, **토론 발언이 Stage2 리뷰에 직접 반영**되며, **그 품질을 지표로 계량화**하는 것입니다.

---

## 1. 토론 레이어 추가

### 1.1 스키마 확장
- 새 토론 스키마 추가: `DebatePersona`, `DebateTurn`, `DebateRound`, `DebateSummary`, `DebateOutput`
- `FinalOutputSchema`에 `debate` 필드 추가

파일:
- `schemas/agent_outputs.py`
- `schemas/final_output.py`
- `schemas/__init__.py`

효과:
토론 결과가 단순 로그가 아니라 **정식 산출물**로 저장됩니다.

### 1.2 토론 오케스트레이터
- `agents/debate_orchestrator.py` 추가
- 토론자 발언은 **Planning → Reflection → Action** 구조로 생성
- 심판 에이전트가 토론 요약/합의/승자 결정

기본 페르소나:
- 분석가(중립), 공감가(긍정), 비평가(부정)

### 1.3 토론 프롬프트
- `agents/prompts/debate_speaker.md`
- `agents/prompts/debate_judge.md`

---

## 2. 파이프라인 통합 (Stage1 → Debate → Stage2)

- `SupervisorAgent`에 토론 단계 삽입
- 토론 결과를 **Stage2 리뷰 프롬프트에 직접 주입**

파일:
- `agents/supervisor_agent.py`
- `agents/specialized_agents/ate_agent.py`
- `agents/specialized_agents/atsa_agent.py`
- `agents/specialized_agents/validator_agent.py`

---

## 3. 토론 발언 → Stage2 리뷰 직접 매핑

### 3.1 Debate Review Context 생성
토론 결과를 아래 형태로 구조화하여 Stage2에 전달:
- `summary`
- `rebuttal_points` (speaker/stance/key_points/message)
- `aspect_refs` (자동 매핑)
- `aspect_hints`, `mapping_stats`

파일:
- `agents/supervisor_agent.py`

### 3.2 매핑 강화
1) 정규화 매칭 (공백/구두점 제거)  
2) ATSA fallback 매핑  
3) 동의어 확장 (`resources/patterns/ko.json`)  
4) speaker/stance 기반 `weight`, `polarity_hint` 제공

### 3.3 provenance 필드 분리
Stage2 review 항목에 `provenance` 필드 추가:
- `AspectExtractionReviewItem.provenance`
- `SentimentReviewItem.provenance`

LLM이 쓰지 않아도 **코드에서 자동 주입**됩니다.

파일:
- `schemas/agent_outputs.py`
- `agents/supervisor_agent.py`
- `agents/prompts/ate_stage2.md`
- `agents/prompts/atsa_stage2.md`

---

## 4. Moderator에 토론 합의 반영

- Rule E 추가: 토론 합의 힌트를 저신뢰 상황에서 보정

파일:
- `agents/specialized_agents/moderator.py`
- `agents/supervisor_agent.py`

---

## 5. 토론 품질 지표 추가

### 5.1 scorecard 확장
추가 필드:
- `debate.mapping_stats`
- `debate.mapping_coverage`
- `debate.mapping_fail_reasons`

파일:
- `scripts/scorecard_from_smoke.py`

### 5.2 구조 메트릭 집계
추가 지표:
- `debate_mapping_coverage`
- `debate_mapping_direct_rate`
- `debate_mapping_fallback_rate`
- `debate_mapping_none_rate`
- 실패 원인 비율 (no_aspects / no_match / neutral_stance / fallback_used)

파일:
- `scripts/structural_error_aggregator.py`

### 5.3 quality_report 집계
overall/bucket 테이블에 debate 지표 평균·표준편차 추가

파일:
- `scripts/quality_report.py`

---

## 6. Metric Report(HTML) 개선

### 6.1 KPI 확장
추가 KPI:
- Debate Mapping Coverage
- Debate Fail (no_match)
- Debate Fail (neutral)

### 6.2 KPI 설명 강화
- KPI 툴팁 제공
- 클릭 시 모달로 상세 설명
- severity 색상 + 범례 표시

### 6.3 경고 배너 개선
- LOW/HIGH 레벨 표시
- 자동 개선 제안 출력

### 6.4 Threshold 외부화
- 경고 기준: `experiments/configs/debate_thresholds.json`
- Debate override 임계값: `experiments/configs/debate_override_thresholds.json`
- Debate override ablation: `experiments/configs/abl_no_debate_override.yaml`

파일:
- `scripts/build_metric_report.py`
- `experiments/configs/debate_thresholds.json`
- `experiments/configs/debate_override_thresholds.json`
- `experiments/configs/abl_no_debate_override.yaml`

---

## 7. 테스트 구성

### 7.1 스모크 설정 추가
`experiments/configs/test_small.yaml`:
- `data/test_small.csv`로 실행
- label 포함으로 leakage_guard 비활성화
- mock backbone 사용

### 7.2 실행 및 산출물
명령:
```
python experiments/scripts/run_experiments.py --config experiments/configs/test_small.yaml --run-id test_small --mode proposed
python scripts/structural_error_aggregator.py --input results/test_small_proposed/scorecards.jsonl --outdir results/test_small_proposed/derived/metrics --profile smoke
python scripts/build_metric_report.py --run_dir results/test_small_proposed --metrics_profile smoke
```

생성 파일:
- `results/test_small_proposed/outputs.jsonl`
- `results/test_small_proposed/traces.jsonl`
- `results/test_small_proposed/scorecards.jsonl`
- `results/test_small_proposed/derived/metrics/structural_metrics.csv`
- `reports/test_small_proposed/metric_report.html`

### 7.3 Debate override ablation
실행 스크립트:
- `scripts/run_debate_override_ablation.py`

예시:
```
python scripts/run_debate_override_ablation.py --run-id debate_override_ablation --profile smoke
```

---

## 8. 문서 업데이트

- `docs/pipeline_structure_and_rules.md`에
  - 토론 단계 삽입
  - Debate Review Context 설명
  - mapping_fail_reasons 기록
  - thresholds 설정 위치 반영

---

## 9. 요약

1. **토론이 파이프라인의 정식 단계로 추가됨**
2. **토론 발언이 Stage2 리뷰에 직접 매핑됨**
3. **토론 품질 지표를 scorecard/metric/리포트에 반영**
4. **Threshold 관리와 경고 시스템까지 포함**
