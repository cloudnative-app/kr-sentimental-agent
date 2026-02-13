# Betatest: betatest_n50 데이터셋 생성 → C1 → C2 → C3 → C2_eval_only 순차 실행 → 메트릭 병합
# 데이터: train/valid.jsonl에서 seed=99로 50개 추출 (real_n50_seed1과 구분). T1 설정, paper 프로파일.
# 사용: 프로젝트 루트(kr-sentimental-agent)에서 실행
#   .\scripts\run_betatest.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $ProjectRoot)) {
    $ProjectRoot = (Get-Location).Path
}
Set-Location $ProjectRoot

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = "python" }

# 1) 데이터셋 생성: betatest_n50 (valid 50개, seed=99)
Write-Host "=== Betatest 데이터셋 생성 (valid_size=50, seed=99) ===" -ForegroundColor Cyan
& $py scripts/make_betatest_n50_dataset.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 2) 정합성 검사
Write-Host "=== 정합성 검사 (check_experiment_config --strict) ===" -ForegroundColor Cyan
& $py scripts/check_experiment_config.py --config experiments/configs/betatest_c1.yaml --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 3) C1 (no memory)
Write-Host "=== Betatest C1 (no memory) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/betatest_c1.yaml --run-id betatest_c1 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 4) C2 (advisory memory)
Write-Host "=== Betatest C2 (advisory) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/betatest_c2.yaml --run-id betatest_c2 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 5) C3 (retrieval-only / silent)
Write-Host "=== Betatest C3 (retrieval-only) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/betatest_c3.yaml --run-id betatest_c3 --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 6) C2_eval_only (v1_2, 평가 전용)
Write-Host "=== Betatest C2_eval_only (eval-only) ===" -ForegroundColor Cyan
& $py scripts/run_pipeline.py --config experiments/configs/betatest_c2_eval_only.yaml --run-id betatest_c2_eval_only --mode proposed --profile paper --with_metrics --metrics_profile paper_main
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 7) C1/C2/C3/C2_eval_only 메트릭 병합 (seeds 42, 123 → __seed42, __seed123)
$r1Dir = "results/betatest_c1__seed42_proposed"
$r2Dir = "results/betatest_c2__seed42_proposed"
$r3Dir = "results/betatest_c3__seed42_proposed"
$r2eDir = "results/betatest_c2_eval_only__seed42_proposed"
New-Item -ItemType Directory -Force -Path reports | Out-Null
Write-Host "=== C1/C2/C3/C2_eval_only 메트릭 병합 (seed42 기준) ===" -ForegroundColor Cyan
& $py scripts/build_memory_condition_summary.py --runs "C1:$r1Dir" "C2:$r2Dir" "C3:$r3Dir" "C2_eval_only:$r2eDir" --out reports/betatest_c1_c2_c3_c2_eval_only_summary.md
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Done. Dataset: experiments/configs/datasets/betatest_n50/ | Summary: reports/betatest_c1_c2_c3_c2_eval_only_summary.md" -ForegroundColor Green
