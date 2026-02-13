# REAL N100 C1 -> C2 -> C3 순차 실행 후 메트릭 병합
# 사용: .\scripts\run_real_n100_c1_c2_c3.ps1
# 또는: pwsh -File scripts/run_real_n100_c1_c2_c3.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path $ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "python" }

Write-Host "=== REAL N100 C1 ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c1.yaml --run-id experiment_real_n100_seed1_c1 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== REAL N100 C2 ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c2.yaml --run-id experiment_real_n100_seed1_c2 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== REAL N100 C3 ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/experiment_real_n100_seed1_c3.yaml --run-id experiment_real_n100_seed1_c3 --mode proposed --profile paper --with_metrics
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

New-Item -ItemType Directory -Force -Path reports | Out-Null
Write-Host "=== C1/C2/C3 메트릭 병합 ===" -ForegroundColor Cyan
& $py scripts/build_memory_condition_summary.py --runs "C1:results/experiment_real_n100_seed1_c1__seed1_proposed" "C2:results/experiment_real_n100_seed1_c2__seed1_proposed" "C3:results/experiment_real_n100_seed1_c3__seed1_proposed" --out reports/real_n100_c1_c2_c3_summary.md
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Summary: reports/real_n100_c1_c2_c3_summary.md" -ForegroundColor Green
