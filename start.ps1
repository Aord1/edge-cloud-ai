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

# ── 1. 检测数据库连通性 ──
Write-Host "`n[1/4] 检测数据库连通性..." -ForegroundColor Cyan
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
    Write-Host "[错误] 数据库连接失败，请检查 .env 配置" -ForegroundColor Red
    Write-Host $dbCheck -ForegroundColor Gray
    exit 1
}

# ── 2. 启动 Cloud API ──
Write-Host "`n[2/4] 启动 Cloud API (localhost:8000)..." -ForegroundColor Cyan
$cloudProc = Start-Process -FilePath python -ArgumentList "-m", "cloud.main" -NoNewWindow -PassThru
$pids += $cloudProc
Start-Sleep -Seconds 3
Write-Host "[OK]   Cloud API 已启动" -ForegroundColor Green

# ── 3. 启动 Edge Server ──
Write-Host "`n[3/4] 启动 Edge Server (localhost:8080)..." -ForegroundColor Cyan
$edgeProc = Start-Process -FilePath python -ArgumentList "-m", "edge.main", "--server" -NoNewWindow -PassThru
$pids += $edgeProc
Start-Sleep -Seconds 2
Write-Host "[OK]   Edge Server 已启动" -ForegroundColor Green

# ── 4. 启动 Web 前端 ──
if (-not $NoWeb) {
    Write-Host "`n[4/4] 启动 Web 前端 (localhost:5173)..." -ForegroundColor Cyan
    if (-not (Test-Path "$projectRoot\web\node_modules")) {
        Write-Host "[安装] npm install..." -ForegroundColor Gray
        Push-Location "$projectRoot\web"
        npm install
        Pop-Location
    }
    $webProc = Start-Process -FilePath npm -ArgumentList "run", "dev" -WorkingDirectory "$projectRoot\web" -NoNewWindow -PassThru
    $pids += $webProc
    Start-Sleep -Seconds 3
    Write-Host "[OK]   Web 前端已启动" -ForegroundColor Green
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
