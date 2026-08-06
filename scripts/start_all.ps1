[CmdletBinding()]
param(
    [string]$MainHost = "0.0.0.0",
    [int]$MainPort = 8000,
    [switch]$NoSync
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root ".tmp\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$mainArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start_main.ps1"), "-HostAddress", $MainHost, "-Port", $MainPort)
if ($NoSync) {
    $mainArgs += "-NoSync"
}

$ps = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
$mainProc = Start-Process -FilePath $ps -ArgumentList $mainArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "main.out.log") -RedirectStandardError (Join-Path $LogDir "main.err.log")

Write-Host "LLM_Benchmark 主服务 PID: $($mainProc.Id), 地址: http://127.0.0.1:$MainPort"
Write-Host "EvalScope 执行模式: in-process（主服务内直接 import evalscope）"
Write-Host "日志目录: $LogDir"
Write-Host "停止时请结束以上 PID，或关闭本脚本后手动 Stop-Process。"

Wait-Process -Id $mainProc.Id
