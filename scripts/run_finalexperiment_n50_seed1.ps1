# Finalexperiment n50 seed1: 데이터셋 생성 → C1 → C2 → C3 → C2_eval_only 순차 실행 (run_pipeline paper + metrics)
# T2(v2) 기본조건. real n50 seed1 표본규칙. 프로젝트 루트에서 실행.
#
# 예:
#   .\scripts\run_finalexperiment_n50_seed1.ps1
#   .\scripts\run_finalexperiment_n50_seed1.ps1 -RunIdSuffix v2
#   .\scripts\run_finalexperiment_n50_seed1.ps1 -SkipDataset
#   .\scripts\run_finalexperiment_n50_seed1.ps1 -Conditions c1,c2,c3

param(
    [string]$RunIdSuffix = "",
    [string[]]$Conditions = @(),
    [switch]$SkipDataset,
    [switch]$SkipSummary
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "python" }

$args = @("scripts/run_finalexperiment_n50_seed1.py")
if ($RunIdSuffix) { $args += "--run-id-suffix"; $args += $RunIdSuffix }
if ($SkipDataset) { $args += "--skip_dataset" }
if ($SkipSummary) { $args += "--skip_summary" }
if ($Conditions -and $Conditions.Count -gt 0) {
    $flat = @($Conditions) | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ }
    if ($flat.Count -gt 0) {
        $args += "--conditions"
        $args += $flat
    }
}

& $py $args
exit $LASTEXITCODE
