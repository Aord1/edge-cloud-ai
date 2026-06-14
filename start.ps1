# ============================================================
# 边云协同智能检测系统 — 一键启动脚本 (Windows PowerShell)
# 用法:
#   .\start.ps1              # 启动全部服务
#   .\start.ps1 --no-web     # 跳过 Web 前端
#   Ctrl+C                    # 停止全部服务
# ============================================================

param(
    [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$pids = @()

function Stop-All {
    Write-Host "`n[关闭] 正在停止所有服务..." -ForegroundColor Yellow
    foreach ($p in $pids) {
        if ($p -and !$p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "[关闭] 已全部停止" -ForegroundColor Green
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
Write-Host "  边云协同智能检测系统 — 一键启动" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Python
$pyOk = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyOk) {
    Write-Host "[错误] 未找到 Python" -ForegroundColor Red
    exit 1
}

# Node
if (-not $NoWeb) {
    $nodeOk = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeOk) {
        Write-Host "[错误] 未找到 Node.js" -ForegroundColor Red
        exit 1
    }
}

# ── 1. 检测数据库连通性 (P1) ──
Write-Host "`n[1/5] 检测数据库连通性..." -ForegroundColor Cyan
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
    Write-Host "[OK]   数据库已连接: $dbCheck" -ForegroundColor Green
} else {
    Write-Host "[错误] 数据库连接失败，请检查 .env 和 Docker" -ForegroundColor Red
    Write-Host "       docker compose -f docker/docker-compose.yml up -d" -ForegroundColor Gray
    Write-Host $dbCheck -ForegroundColor Gray
    exit 1
}

# ── 2. 检测 MQTT Broker (P1) ──
Write-Host "`n[2/5] 检测 MQTT Broker..." -ForegroundColor Cyan
$mqttCheck = python -c "
from edge.config import edge_settings
import socket
s = socket.socket()
s.settimeout(3)
try:
    s.connect((edge_settings.mqtt_broker_host, edge_settings.mqtt_broker_port))
    print('connected')
except Exception as e:
    print(f'{e}')
finally:
    s.close()
" 2>&1
if ($mqttCheck -match 'connected') {
    Write-Host "[OK]   MQTT Broker 已连接" -ForegroundColor Green
} else {
    Write-Host "[警告] MQTT 连接失败，将回退 HTTP 上传" -ForegroundColor Yellow
    Write-Host "       docker compose -f docker/docker-compose.yml up -d mqtt" -ForegroundColor Gray
}

# ── 3. 启动 Cloud API (P2) ──
Write-Host "`n[3/5] 启动 Cloud API (localhost:8000)..." -ForegroundColor Cyan
$cloudProc = Start-Process -FilePath python -ArgumentList "-m", "cloud.main" -NoNewWindow -PassThru
$pids += $cloudProc
if (Wait-Port -Port 8000 -TimeoutSec 15 -Label "Cloud API") {
    Write-Host "[OK]   Cloud API 已启动 (PID $($cloudProc.Id))" -ForegroundColor Green
} else {
    Write-Host "[警告] Cloud API 端口 8000 未就绪，可能需要更长时间" -ForegroundColor Yellow
}

# ── 4. 启动 Edge Server (P3) ──
Write-Host "`n[4/5] 启动 Edge Server (localhost:8080)..." -ForegroundColor Cyan
$edgeProc = Start-Process -FilePath python -ArgumentList "-m", "edge.main", "--server" -NoNewWindow -PassThru
$pids += $edgeProc
if (Wait-Port -Port 8080 -TimeoutSec 15 -Label "Edge Server") {
    Write-Host "[OK]   Edge Server 已启动 (PID $($edgeProc.Id))" -ForegroundColor Green
} else {
    Write-Host "[警告] Edge Server 端口 8080 未就绪，可能需要更长时间" -ForegroundColor Yellow
}

# ── 5. 启动 Web 前端 (P4) ──
if (-not $NoWeb) {
    Write-Host "`n[5/5] 启动 Web 前端 (localhost:5173)..." -ForegroundColor Cyan
    if (-not (Test-Path "$projectRoot\web\node_modules")) {
        Write-Host "[安装] npm install..." -ForegroundColor Gray
        Push-Location "$projectRoot\web"
        npm install
        Pop-Location
    }
    $webProc = Start-Process -FilePath npm -ArgumentList "run", "dev" -WorkingDirectory "$projectRoot\web" -NoNewWindow -PassThru
    $pids += $webProc
    if (Wait-Port -Port 5173 -TimeoutSec 15 -Label "Web 前端") {
        Write-Host "[OK]   Web 前端已启动 (PID $($webProc.Id))" -ForegroundColor Green
    } else {
        Write-Host "[警告] Web 前端端口 5173 未就绪，可能需要更长时间" -ForegroundColor Yellow
    }
}

# ── 完成 ──
Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "  全部服务已启动!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Web 管理端:   http://localhost:5173" -ForegroundColor White
Write-Host "  Cloud API:    http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Edge Stream:  http://localhost:8080/stream" -ForegroundColor White
Write-Host "  Edge API:     http://localhost:8080/api/status" -ForegroundColor White
Write-Host "`n  按 Ctrl+C 停止所有服务" -ForegroundColor Gray

try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Stop-All
}