# Drift cause decomposition (stage1_to_final_changed=1)

| drift_cause_tag | 설명 | count |
|-----------------|------|-------|
| **stage2_selected** | Stage2 선택으로 변경 (Moderator selected stage2) | 18 |
| **same_stage_tuples_differ** | 동일 stage 선택인데 tuples 변경 (정규화/중복/추출경로 차이) | 0 |
| **stage_delta_missing** | stage_delta 미기록 (B-type inconsistency) | 0 |

**Total samples with changed=1**: 18

## 메모리 노출 여부에 따른 변화 (C2 run)

| memory_used | count (changed=1) |
|-------------|------------------|
| 1 (exposed) | 18 |
| 0 (not exposed) | 0 |
