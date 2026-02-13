# REAL N100 C2 -> C3 순차 실행 (run ID: c2_2, c3_2 / paper 프로파일 + 메트릭)
# 사용: 프로젝트 루트(kr-sentimental-agent)에서 실행
#   cd C:\Users\wisdo\Documents\kr-sentimental-agent
#   .\scripts\run_real_n100_c2_c3.ps1
# 또는: pwsh -File "C:\...\kr-sentimental-agent\scripts\run_real_n100_c2_c3.ps1" (실행 전 Set-Location으로 프로젝트 루트로 이동)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "python" }

# C2 (advisory) → run-id c2_2
Write-Host "=== REAL N100 C2 (advisory) run-id: experiment_real_n100_seed1_c2_2 ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c2.yaml --run-id experiment_real_n100_seed1_c2_2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# C3 (retrieval-only) → run-id c3_2
Write-Host "=== REAL N100 C3 (retrieval-only) run-id: experiment_real_n100_seed1_c3_2 ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c3.yaml --run-id experiment_real_n100_seed1_c3_2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# C2_2 / C3_2 메트릭 병합 (선택)
New-Item -ItemType Directory -Force -Path reports | Out-Null
Write-Host "=== C2_2 / C3_2 메트릭 병합 ===" -ForegroundColor Cyan
& $py scripts/build_memory_condition_summary.py --runs "C2:results/experiment_real_n100_seed1_c2_2__seed1_proposed" "C3:results/experiment_real_n100_seed1_c3_2__seed1_proposed" --out reports/real_n100_c2_2_c3_2_summary.md
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Summary: reports/real_n100_c2_2_c3_2_summary.md" -ForegroundColor Green
