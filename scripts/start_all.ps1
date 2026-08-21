[CmdletBinding()]
param(
    [string]$MainHost = "0.0.0.0",
    [int]$MainPort = 8020,
    [switch]$NoSync,
    [switch]$StartSandbox,
    [string]$SandboxHost = "0.0.0.0",
    [int]$SandboxPort = 1234
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root ".tmp\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$ps = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
$sandboxProc = $null
$mainProc = $null

try {
    if ($StartSandbox) {
        if (-not (Get-Command ms-enclave -ErrorAction SilentlyContinue)) {
            throw "未找到 ms-enclave 命令；请先安装 evalscope[sandbox] 或去掉 -StartSandbox。"
        }
        $sandboxArgs = @("server", "--host", $SandboxHost, "--port", $SandboxPort.ToString())
        $sandboxProc = Start-Process -FilePath "ms-enclave" -ArgumentList $sandboxArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "sandbox.out.log") -RedirectStandardError (Join-Path $LogDir "sandbox.err.log")
        Write-Host "EvalScope sandbox PID: $($sandboxProc.Id), 地址: http://127.0.0.1:$SandboxPort"
    }
    else {
        Write-Host "Sandbox 模式: 默认不启动；如需随脚本启动，请传入 -StartSandbox。"
    }

    $mainArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start_main.ps1"), "-HostAddress", $MainHost, "-Port", $MainPort)
    if ($NoSync) {
        $mainArgs += "-NoSync"
    }
    $mainProc = Start-Process -FilePath $ps -ArgumentList $mainArgs -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LogDir "main.out.log") -RedirectStandardError (Join-Path $LogDir "main.err.log")

    Write-Host "LLM_Benchmark 主服务 PID: $($mainProc.Id), 地址: http://127.0.0.1:$MainPort"
    Write-Host "EvalScope 执行模式: in-process（主服务内直接 import evalscope）"
    if ($sandboxProc) {
        Write-Host "Sandbox 模式: 已随脚本启动 ms-enclave；日志: $(Join-Path $LogDir 'sandbox.out.log') / $(Join-Path $LogDir 'sandbox.err.log')"
    }
    else {
        Write-Host "Sandbox 提醒: 默认不会启动 ms-enclave；代码评分请提前独立启动，或传入 -StartSandbox。"
    }
    Write-Host "日志目录: $LogDir"
    Write-Host "停止时请结束以上 PID，或关闭本脚本后手动 Stop-Process。"

    if ($sandboxProc) {
        while (-not $mainProc.HasExited) {
            Start-Sleep -Seconds 2
            $mainProc.Refresh()
            $sandboxProc.Refresh()
            if ($sandboxProc.HasExited) {
                Write-Host "EvalScope sandbox 已退出，正在停止主服务。请查看 $(Join-Path $LogDir 'sandbox.err.log')。" -ForegroundColor Red
                if (-not $mainProc.HasExited) {
                    Stop-Process -Id $mainProc.Id -Force -ErrorAction SilentlyContinue
                }
                exit 1
            }
        }
        exit $mainProc.ExitCode
    }

    Wait-Process -Id $mainProc.Id
    $mainProc.Refresh()
    exit $mainProc.ExitCode
}
finally {
    if ($mainProc -and -not $mainProc.HasExited) {
        Stop-Process -Id $mainProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($sandboxProc -and -not $sandboxProc.HasExited) {
        Stop-Process -Id $sandboxProc.Id -Force -ErrorAction SilentlyContinue
    }
}
