# Windows PowerShell 版的一键启动。等价于 scripts/dev.sh。
# 用法：powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "需要 uv：https://docs.astral.sh/uv/"
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error "需要 npm（Node.js 22+）"
    exit 1
}

if (-not (Test-Path "server\.env")) {
    Write-Host "-> 拷一份 server\.env.example -> server\.env，记得填 LLM_API_KEY"
    Copy-Item "server\.env.example" "server\.env"
}
if (-not (Test-Path "web\.env")) {
    Copy-Item "web\.env.example" "web\.env"
}

# Windows 上 npm 实际是 npm.cmd；Start-Process 直传 "npm" 偶尔解析不到，先取绝对路径
$uvPath = (Get-Command uv).Source
$npmPath = (Get-Command npm).Source

# 后端
$back = Start-Process -PassThru -NoNewWindow -FilePath $uvPath `
    -WorkingDirectory "server" `
    -ArgumentList @("run", "uvicorn", "biri_youyaku.app:app", "--reload",
                    "--host", "127.0.0.1", "--port", "17821")

# 前端
if (-not (Test-Path "web\node_modules")) {
    Push-Location web
    & $npmPath install
    Pop-Location
}
$front = Start-Process -PassThru -NoNewWindow -FilePath $npmPath `
    -WorkingDirectory "web" `
    -ArgumentList @("run", "dev")

Write-Host ""
Write-Host "-> 后端 http://127.0.0.1:17821"
Write-Host "-> 前端 http://127.0.0.1:5173"
Write-Host "-> Ctrl+C 退出"
Write-Host ""

try {
    Wait-Process -Id $back.Id, $front.Id
} finally {
    foreach ($p in @($back, $front)) {
        if ($p -and -not $p.HasExited) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}
