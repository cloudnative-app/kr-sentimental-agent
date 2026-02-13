# REAL N50: 데이터셋 생성 → C1 → C2 → C3 → C2_eval_only 순차 실행 → 메트릭 병합 (한 번에 실행)
# real n100 규칙 적용, valid N=50, seed=1. C2_eval_only = v1_2 조건(평가 전용, 저장 안 함).
# 사용: 프로젝트 루트(kr-sentimental-agent)에서 실행
#   .\scripts\run_real_n50_c1_c2_c3.ps1
#   .\scripts\run_real_n50_c1_c2_c3.ps1 -RunIdSuffix run2   # 다른 run_id로 한 번 더 수행 (결과 덮어쓰기 없음)
# 또는: pwsh -File scripts/run_real_n50_c1_c2_c3.ps1 (실행 전 Set-Location으로 프로젝트 루트로 이동)

param(
    [string]$RunIdSuffix = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "python" }

# RunIdSuffix가 있으면 run_id에 붙여서 결과 디렉터리 분리 (예: experiment_real_n50_seed1_c1_run2__seed1_proposed)
$idSuf = $RunIdSuffix.Trim()
if ($idSuf) { $idSuf = "_" + $idSuf }
$r1 = "experiment_real_n50_seed1_c1$idSuf"
$r2 = "experiment_real_n50_seed1_c2$idSuf"
$r3 = "experiment_real_n50_seed1_c3$idSuf"
$r2e = "experiment_real_n50_seed1_c2_eval_only$idSuf"
$summaryOut = if ($idSuf) { "reports/real_n50_c1_c2_c3_c2_eval_only${idSuf}_summary.md" } else { "reports/real_n50_c1_c2_c3_c2_eval_only_summary.md" }

# 1) 데이터셋 생성: real_n50_seed1 (valid 50개, seed=1)
Write-Host "=== REAL N50 데이터셋 생성 (valid_size=50, seed=1) ===" -ForegroundColor Cyan
& $py scripts/make_real_n100_seed1_dataset.py --valid_size 50 --seed 1 --outdir experiments/configs/datasets/real_n50_seed1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 2) C1 (no memory)
Write-Host "=== REAL N50 C1 (no memory) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n50_seed1_c1.yaml --run-id $r1 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 3) C2 (advisory memory)
Write-Host "=== REAL N50 C2 (advisory) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n50_seed1_c2.yaml --run-id $r2 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 4) C3 (retrieval-only / silent)
Write-Host "=== REAL N50 C3 (retrieval-only) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n50_seed1_c3.yaml --run-id $r3 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 5) C2_eval_only (v1_2, 평가 전용: 주입 마스킹, 저장 안 함)
Write-Host "=== REAL N50 C2_eval_only (eval-only) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n50_seed1_c2_eval_only.yaml --run-id $r2e --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 6) C1/C2/C3/C2_eval_only 메트릭 병합 (run_id에 __seed1 붙은 결과 디렉터리 사용)
$r1Dir = "results/${r1}__seed1_proposed"
$r2Dir = "results/${r2}__seed1_proposed"
$r3Dir = "results/${r3}__seed1_proposed"
$r2eDir = "results/${r2e}__seed1_proposed"
New-Item -ItemType Directory -Force -Path reports | Out-Null
Write-Host "=== C1/C2/C3/C2_eval_only 메트릭 병합 ===" -ForegroundColor Cyan
& $py scripts/build_memory_condition_summary.py --runs "C1:$r1Dir" "C2:$r2Dir" "C3:$r3Dir" "C2_eval_only:$r2eDir" --out $summaryOut
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Dataset: experiments/configs/datasets/real_n50_seed1/ | Summary: $summaryOut" -ForegroundColor Green
