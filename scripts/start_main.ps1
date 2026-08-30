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

# EvalScope SandboxService 是进程级单例，并发智力评测任务会在各自 run_task 的 finally
# 里互相 shutdown 共享沙箱，导致代码类数据集（mbpp/humaneval 等）批量执行失败。
# 因此智力评测任务默认串行执行（并发=1）。如确需并发，显式覆盖该变量即可。
if (-not $env:LLM_BENCHMARK_EVALSCOPE_JOB_MAX_CONCURRENCY) {
    $env:LLM_BENCHMARK_EVALSCOPE_JOB_MAX_CONCURRENCY = "1"
}

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
