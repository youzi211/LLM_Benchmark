[CmdletBinding()]
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8020,
    [string]$DataDir = "",
    [string]$ReportsDir = "",
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

if ($DataDir) { $env:LLM_BENCHMARK_DATA_DIR = $DataDir }
if ($ReportsDir) { $env:LLM_BENCHMARK_REPORTS_DIR = $ReportsDir }

$uvArgs = @("run")
if ($NoSync) { $uvArgs += "--no-sync" }
$uvArgs += @("uvicorn", "app.main:app", "--host", $HostAddress, "--port", $Port.ToString())

Push-Location $Root
try {
    & uv @uvArgs
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
