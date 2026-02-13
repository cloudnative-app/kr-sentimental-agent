# Mini4 validation: C1 / C2 / C3 / C2_eval_only 선택 실행, 메트릭 생성, 체크리스트 검토
# 프로젝트 루트에서 실행
#
# 예:
#   .\scripts\run_mini4_validation_c1_c2.ps1
#   .\scripts\run_mini4_validation_c1_c2.ps1 -All
#   .\scripts\run_mini4_validation_c1_c2.ps1 -Conditions c1,c2,c3,c2_eval_only
#   .\scripts\run_mini4_validation_c1_c2.ps1 -Conditions c1 c2
#   .\scripts\run_mini4_validation_c1_c2.ps1 -SkipRun -All

param(
    [string[]]$Conditions = @("c1", "c2"),
    [switch]$All,
    [string]$Out = "reports/mini4_validation_checklist.md",
    [switch]$SkipRun
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $root)) { $root = (Get-Location).Path }
Set-Location $root

$py = "python"
if (Get-Command python3 -ErrorAction SilentlyContinue) { $py = "python3" }

$args = @("scripts/run_mini4_validation_c1_c2.py", "--out", $Out)
if ($All) {
    $args += "--all"
} elseif ($Conditions -and $Conditions.Count -gt 0) {
    # Support -Conditions "c1,c2,c3,c2_eval_only" or -Conditions c1,c2,c3,c2_eval_only
    $flat = @($Conditions) | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ }
    if ($flat.Count -gt 0) {
        $args += "--conditions"
        $args += $flat
    }
}
if ($SkipRun) { $args += "--skip_run" }

& $py $args
exit $LASTEXITCODE
