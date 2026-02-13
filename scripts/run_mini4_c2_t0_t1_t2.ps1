# Mini4 C2 T0/T1/T2: 3조건 연속 실행 + 체크리스트 + 02829 회귀테스트
# 프로젝트 루트에서 실행. 아이디 겹치지 않게 하려면 -RunIdSuffix 사용.
#
# 예:
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1 -RunIdSuffix v2
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1 -RunIdSuffix (Get-Date -Format "yyyyMMdd_HHmm")
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1 -SkipRun
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1 -SkipRun -RunIdSuffix v2
#   .\scripts\run_mini4_c2_t0_t1_t2.ps1 -SkipRegression

param(
    [string]$RunIdSuffix = "",
    [string]$Out = "reports/mini4_c2_t0_t1_t2_checklist.md",
    [switch]$SkipRun,
    [switch]$SkipRegression
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $root)) { $root = (Get-Location).Path }
Set-Location $root

$py = "python"
if (Get-Command python3 -ErrorAction SilentlyContinue) { $py = "python3" }

$args = @("scripts/run_mini4_c2_t0_t1_t2.py", "--out", $Out)
if ($RunIdSuffix) { $args += "--run-id-suffix"; $args += $RunIdSuffix }
if ($SkipRun) { $args += "--skip_run" }
if ($SkipRegression) { $args += "--skip_regression" }

& $py $args
exit $LASTEXITCODE
