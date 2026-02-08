# Pull 변경사항 표 요약 (기능적 차이)

origin `main` 풀(56f1b77 → 182bca6) 기준으로, **기능적 차이**를 표로 정리했습니다.

---

## 1. 파이프라인 구조: 이전 vs 이후

| 구분 | 이전 | 이후 |
|------|------|------|
| **흐름** | Stage1(ATE/ATSA/Validator) → Stage2 리뷰 → Moderator | Stage1 → **Debate(토론)** → Stage2 리뷰 → Moderator |
| **Stage2 입력** | Stage1 + Validator 피드백만 | Stage1 + Validator + **Debate Review Context** |
| **Moderator 규칙** | Rule A–D, M, Z | Rule A–D, M, Z + **Rule E(토론 합의 힌트)** |
| **최종 보정** | Validator + Stage2 review 적용 | Validator + Stage2 review + **Debate override**(선택) |

---

## 2. 새로 추가된 기능/컴포넌트

| 영역 | 추가 항목 | 기능 요약 |
|------|-----------|-----------|
| **토론 레이어** | `agents/debate_orchestrator.py` | 분석가/공감가/비평가 페르소나가 Planning→Reflection→Action으로 발언, 심판이 요약·승자 결정 |
| **토론 프롬프트** | `debate_speaker.md`, `debate_judge.md` | 발언 생성·심판 판단용 프롬프트 |
| **스키마** | `DebatePersona`, `DebateTurn`, `DebateRound`, `DebateSummary`, `DebateOutput` | 토론 결과를 정식 산출물로 저장 |
| **FinalOutput** | `debate` 필드 | 최종 결과에 토론 요약 포함 |
| **Stage2 리뷰** | Debate Review Context 주입 | rebuttal_points, aspect_refs, aspect_hints, mapping_stats를 Stage2 ATE/ATSA에 전달 |
| **provenance** | `AspectExtractionReviewItem.provenance`, `SentimentReviewItem.provenance` | 토론 출처를 코드에서 자동 주입, LLM 불필요 |
| **Moderator** | Rule E | 토론 합의 힌트로 저신뢰 상황 보정 |
| **Supervisor** | Debate 단계 + `_apply_stage2_reviews` 내 Debate override | 토론 후 Stage2 적용 시 강한 논점 기반 polarity 보정(설정으로 on/off) |

---

## 3. 스키마/데이터 구조 변경

| 파일 | 변경 내용 | 기능적 의미 |
|------|-----------|-------------|
| `schemas/agent_outputs.py` | Debate 관련 스키마 + Stage2 review에 `provenance` | 토론이 정식 산출물로, 리뷰 항목별 출처 추적 |
| `schemas/final_output.py` | `FinalOutputSchema`에 `debate` 추가 | outputs.jsonl에 토론 요약 포함 |
| `schemas/__init__.py` | 새 스키마 export | 외부에서 Debate 타입 사용 가능 |
| `resources/patterns/ko.json` | 동의어/패턴 확장 | Debate→Stage2 aspect 매칭 시 fallback 강화 |

---

## 4. 에이전트별 변경

| 에이전트 | 변경 요약 | 기능적 차이 |
|----------|-----------|-------------|
| **SupervisorAgent** | Debate 단계 삽입, Debate Review Context 생성, Stage2 적용 시 Debate override | 토론 실행·매핑·보정까지 일괄 처리 |
| **ATE Agent** | Stage2 프롬프트에 debate context + provenance | 리뷰 시 토론 반박 포인트 참고, 출처 명시 |
| **ATSA Agent** | 동일 | 리뷰 시 토론 반박 포인트 참고, 출처 명시 |
| **Validator Agent** | (Stage2 재검증 유지) | 동일 |
| **Moderator** | Rule E 추가 | 토론 합의를 최종 결정에 반영 |

---

## 5. 출력물(Output) 변화

**있음.** 아래 파일·필드가 추가되거나 확장되었습니다.

| 출력 파일 | 이전 | 이후 (추가/변경 필드) |
|-----------|------|------------------------|
| **outputs.jsonl** | `meta`, `stage1_ate/atsa/validator`, `stage2_*`, `moderator`, `process_trace`, `analysis_flags`, `final_result` | **`debate`** (DebateOutput: topic, personas, rounds, summary) |
| **FinalOutputSchema** | `debate` 없음 | **`debate: Optional[DebateOutput]`** 추가 |
| **traces.jsonl** | Stage1/Validator/Stage2/Moderator trace | **Debate 단계 trace** 추가 (stage=debate, agent=debate_orchestrator 등) |
| **scorecards.jsonl** | ate, atsa, validator, moderator, stage_delta, latency, flags 등 | **`meta.debate_mapping_stats`**, **`meta.debate_mapping_coverage`**, **`meta.debate_mapping_fail_reasons`**, **`meta.debate_override_stats`** / **`debate`** 블록 전체 (mapping_stats, mapping_coverage, mapping_fail_reasons, override_stats) |
| **correction_applied_log** (meta 내부) | Validator/ATE/ATSA 적용 로그 | **`DEBATE_OVERRIDE`** 항목 추가 (토론 기반 polarity 보정 시 기록) |
| **Stage2 리뷰 스키마** | `AspectExtractionReviewItem`, `SentimentReviewItem` (reason 등만) | **`provenance`** 필드 추가 (source: speaker/stance, 코드에서 자동 주입) |

---

## 6. 메트릭(Metrics) 변화

**있음.** 토론 관련 지표가 전 단계에 추가됩니다.

| 구분 | 메트릭 이름 | 설명 | 사용처 |
|------|-------------|------|--------|
| **scorecard (샘플별)** | `debate.mapping_stats` | direct / fallback / none 매핑 건수 | scorecards.jsonl |
| | `debate.mapping_coverage` | (direct+fallback)/total, 0~1 | scorecards.jsonl |
| | `debate.mapping_fail_reasons` | no_aspects, no_match, neutral_stance, fallback_used 건수 | scorecards.jsonl |
| | `debate.override_stats` | applied, skipped_low_signal, skipped_conflict 건수 | scorecards.jsonl |
| **structural_metrics (집계)** | `debate_mapping_coverage` | run 전체 coverage 평균 | structural_metrics.csv, HTML |
| | `debate_mapping_direct_rate` | direct 비율 평균 | CSV, quality_report, HTML |
| | `debate_mapping_fallback_rate` | fallback 비율 평균 | 동일 |
| | `debate_mapping_none_rate` | none 비율 평균 | 동일 |
| | `debate_fail_no_aspects_rate` | no_aspects 비율 | 동일 |
| | `debate_fail_no_match_rate` | no_match 비율 | 동일 |
| | `debate_fail_neutral_stance_rate` | neutral_stance 비율 | 동일 |
| | `debate_fail_fallback_used_rate` | fallback_used 비율 | 동일 |
| | `debate_override_applied` | override 적용 횟수 (합계) | 동일 |
| | `debate_override_skipped_low_signal` | 신호 부족으로 스킵 횟수 | 동일 |
| | `debate_override_skipped_conflict` | 충돌로 스킵 횟수 | 동일 |
| **metric_report.html KPI** | Debate Mapping Coverage | KPI 카드 1개 (threshold 기반 경고) | HTML 대시보드 |
| | Debate Fail (no_match) | KPI 카드 | HTML |
| | Debate Fail (neutral) | KPI 카드 | HTML |
| **quality_report** | overall/bucket 테이블 | 위 debate_* 지표들의 평균·표준편차 컬럼 추가 | quality_report 출력 |
| **경고(threshold)** | coverage_warn, coverage_high, no_match_warn/high, neutral_warn/high | `debate_thresholds.json`에서 로드, HTML 경고 배너·툴팁에 사용 | build_metric_report.py |

---

## 7. 지표·리포트·품질 (요약)

| 구분 | 추가/변경 항목 | 용도 |
|------|----------------|------|
| **scorecard** | `debate.mapping_stats`, `debate.mapping_coverage`, `debate.mapping_fail_reasons`, `debate.override_stats` | 샘플별 토론–리뷰 매핑·override 품질 |
| **structural_metrics** | 위 표의 debate_* 집계 메트릭 전부 | 구조 메트릭 CSV·리포트 |
| **quality_report** | overall/bucket 테이블에 debate 지표 평균·표준편차 | 실험 단위 품질 요약 |
| **metric_report.html** | Debate KPI 카드, 툴팁/모달, severity 색상·범례, 경고 배너(LOW/HIGH), 개선 제안 | 대시보드에서 토론 품질·경고 확인 |
| **threshold** | `debate_thresholds.json`, `debate_override_thresholds.json` | 경고/override 기준 외부화 |

---

## 8. 설정·실험

| 항목 | 내용 | 기능적 차이 |
|------|------|-------------|
| `experiments/configs/debate_thresholds.json` | coverage/no_match/neutral 경고 임계값 | 리포트 경고 기준 조정 |
| `experiments/configs/debate_override_thresholds.json` | Debate override 적용/스킵 기준 | polarity 보정 강도 조정 |
| `experiments/configs/abl_no_debate_override.yaml` | `enable_debate_override: false` | 토론은 하되 override만 끈 ablation |
| `experiments/configs/test_small.yaml` | test_small.csv, mock, label 포함 | 스모크/검증용 소규모 실행 |

---

## 9. 스크립트·도구

| 스크립트 | 역할 | 언제 사용 |
|----------|------|-----------|
| `scripts/run_debate_override_ablation.py` | Debate override on/off 비교 실행 | ablation 실험 |
| `scripts/structural_error_aggregator.py` | scorecards → structural_metrics (debate 포함) | 메트릭 파이프라인 |
| `scripts/build_metric_report.py` | run_dir + metrics_profile → HTML 리포트 (KPI·경고·threshold 반영) | 결과 시각화 |
| `scripts/quality_report.py` | debate 지표 집계 추가 | 품질 요약 |
| `scripts/scorecard_from_smoke.py` | scorecard에 debate 매핑 필드 출력 | 스모크/실험 결과 기록 |

---

## 10. 문서

| 문서 | 변경 요약 |
|------|-----------|
| `README.md` | 토론 레이어·실행 순서·에이전트 페르소나·실험 방법·용어 정리 |
| `docs/changes_summary.md` | 변경사항 상세 요약(신규) |
| `docs/pipeline_structure_and_rules.md` | 토론 단계, Debate Review Context, mapping_fail_reasons, threshold 위치 반영 |

---

## 11. 한 줄 요약

| 이전 | 이후 |
|------|------|
| Stage1 → Stage2 리뷰 → Moderator로 종료 | Stage1 → **토론(Debate)** → Stage2 리뷰(토론 반영) → **Debate override** → Moderator(**Rule E**) |
| 토론 없음, 리뷰 품질 지표 없음 | 토론 정식 단계화, **mapping coverage/실패 원인/경고/threshold/ablation** 지원 |
