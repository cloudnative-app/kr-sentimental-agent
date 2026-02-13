# Drift cause decomposition (stage1_to_final_changed=1)

| drift_cause_tag | 설명 | count |
|-----------------|------|-------|
| **stage2_selected** | Stage2 선택으로 변경 (Moderator selected stage2) | 23 |
| **same_stage_tuples_differ** | 동일 stage 선택인데 tuples 변경 (정규화/중복/추출경로 차이) | 5 |
| **stage_delta_missing** | stage_delta 미기록 (B-type inconsistency) | 0 |

**Total samples with changed=1**: 28

## Memory (retrieved vs injected)

| metric | 설명 | count (changed=1) |
|--------|------|------------------|
| drift_cause_memory_used_changed_n (==injected) | changed=1 이면서 memory_injected=1 | 22 |
| drift_cause_memory_retrieved_changed_n | changed=1 이면서 memory_retrieved=1 (C3에서 크면: 검색은 하는데 주입 없이 stage2 변화) | 28 |

## 메모리 주입 여부 (C2 run, changed=1)

| memory_used (=injected) | count |
|------------------------|-------|
| 1 (injected) | 22 |
| 0 (not injected) | 6 |
