# Fails if the Unicode replacement character appears in smoke_outputs.jsonl
$path = "experiments\results\proposed\smoke_outputs.jsonl"
if (-not (Test-Path $path)) {
  Write-Error "missing $path"
  exit 1
}
$hits = Select-String -Path $path -Pattern "�"
if ($hits) {
  Write-Error "encoding check failed: found replacement character in $path"
  exit 1
}
Write-Output "qa_check_encoding: PASS"
