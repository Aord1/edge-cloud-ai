# ============================================================
# 边云协同 — 云端服务启动 (仅 MQTT 用 Docker)
# 用法:
#   .\start-cloud.ps1              # MQTT(Docker) + Cloud + Web
#   .\start-cloud.ps1 --no-web     # 跳过 Web 前端
#   Ctrl+C                          # 停止 Cloud 和 Web
#
# MQTT Docker 容器需手动停止: docker stop edgecloud-mqtt
# ============================================================

param(
    [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$pids = @()

function Stop-All {
    Write-Host "`n[关闭] 正在停止 Cloud + Web..." -ForegroundColor Yellow
    foreach ($p in $pids) {
        if ($p -and !$p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "[关闭] 已停止 (MQTT 容器仍运行: docker stop edgecloud-mqtt 可停止)" -ForegroundColor Green
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 15, [string]$Label = "服务")
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", $Port)
            $tcp.Close()
            return $true
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  边云协同 — 云端服务启动" -ForegroundColor Cyan
Write-Host "  (MQTT=Docker | PG=本地 | Cloud=本地 | Web=本地)" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan

# 依赖检测
$pyOk = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyOk) { Write-Host "[错误] 未找到 Python" -ForegroundColor Red; exit 1 }
$nodeOk = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeOk -and -not $NoWeb) { Write-Host "[错误] 未找到 Node.js" -ForegroundColor Red; exit 1 }

# ── 0. MQTT Broker (Docker) ──
Write-Host "`n[0/3] 启动 MQTT Broker (Docker)..." -ForegroundColor Cyan
$dockerOk = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerOk) { Write-Host "[错误] 未找到 Docker" -ForegroundColor Red; exit 1 }
$dockerRunning = docker info 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "[错误] Docker 未运行" -ForegroundColor Red; exit 1 }

$mqttRunning = docker ps --format "{{.Names}}" 2>&1 | Select-String "edgecloud-mqtt" -Quiet
if ($mqttRunning) {
    Write-Host "[OK]   MQTT Broker 已在运行" -ForegroundColor Green
} else {
    docker compose -f "$projectRoot\docker\docker-compose.yml" up -d mqtt 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] MQTT 启动失败" -ForegroundColor Red; exit 1 }
    Start-Sleep -Seconds 3
    Write-Host "[OK]   MQTT Broker 已启动 (容器: edgecloud-mqtt)" -ForegroundColor Green
}

# ── 1. 检测 PostgreSQL (本地) ──
Write-Host "`n[1/3] 检测 PostgreSQL (本地)..." -ForegroundColor Cyan
$dbCheck = python -c "
from cloud.config import settings
from sqlalchemy import text
from cloud.db.engine import get_engine
import asyncio
async def check():
    engine = get_engine()
    async with engine.connect() as conn:
        ver = (await conn.execute(text('SELECT version()'))).scalar()
        print(ver.split(',')[0])
    await engine.dispose()
asyncio.run(check())
" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK]   PostgreSQL 已连接: $dbCheck" -ForegroundColor Green
} else {
    Write-Host "[错误] PostgreSQL 连接失败，请检查本地 PG 服务和 .env" -ForegroundColor Red
    Write-Host $dbCheck -ForegroundColor Gray
    exit 1
}

# ── 2. Cloud API ──
Write-Host "`n[2/3] 启动 Cloud API (localhost:8000)..." -ForegroundColor Cyan
$cloudProc = Start-Process -FilePath python -ArgumentList "-m", "cloud.main" -NoNewWindow -PassThru
$pids += $cloudProc
if (Wait-Port -Port 8000 -TimeoutSec 20 -Label "Cloud API") {
    Write-Host "[OK]   Cloud API 已启动 (PID $($cloudProc.Id))" -ForegroundColor Green
} else {
    Write-Host "[警告] Cloud API 端口 8000 未就绪" -ForegroundColor Yellow
}

# ── 3. Web 前端 ──
if (-not $NoWeb) {
    Write-Host "`n[3/3] 启动 Web 前端 (localhost:5173)..." -ForegroundColor Cyan
    if (-not (Test-Path "$projectRoot\web\node_modules")) {
        Write-Host "[安装] npm install..." -ForegroundColor Gray
        Push-Location "$projectRoot\web"; npm install; Pop-Location
    }
    $webProc = Start-Process -FilePath npm -ArgumentList "run", "dev" -WorkingDirectory "$projectRoot\web" -NoNewWindow -PassThru
    $pids += $webProc
    if (Wait-Port -Port 5173 -TimeoutSec 15 -Label "Web 前端") {
        Write-Host "[OK]   Web 前端已启动 (PID $($webProc.Id))" -ForegroundColor Green
    } else {
        Write-Host "[警告] Web 前端端口 5173 未就绪" -ForegroundColor Yellow
    }
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  云端服务已就绪!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Cloud API:    http://localhost:8000/docs" -ForegroundColor White
if (-not $NoWeb) { Write-Host "  Web 管理端:   http://localhost:5173" -ForegroundColor White }
Write-Host "  MQTT Broker:  localhost:1883 (Docker)" -ForegroundColor White
Write-Host ""
Write-Host "  现在启动边端 (另开终端):" -ForegroundColor Yellow
Write-Host "    python -m edge.main --server" -ForegroundColor White
Write-Host ""
Write-Host "  Ctrl+C 停止 Cloud + Web | docker stop edgecloud-mqtt 停止 MQTT" -ForegroundColor Gray

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Stop-All
}
