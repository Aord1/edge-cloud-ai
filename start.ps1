# ============================================================
# 边云协同智能检测系统 — 一键启动脚本 (Windows PowerShell)
# 用法:
#   .\start.ps1              # 启动全部服务
#   .\start.ps1 --no-db      # 跳过 Docker 数据库（已手动启动）
#   .\start.ps1 --no-web     # 跳过 Web 前端
#   Ctrl+C                    # 停止全部服务
# ============================================================

param(
    [switch]$NoDb,
    [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── 进程追踪（用于清理） ──
$pids = @()

function Stop-All {
    Write-Host "`n[关闭] 正在停止所有服务..." -ForegroundColor Yellow
    foreach ($p in $pids) {
        if ($p -and !$p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $NoDb) {
        Write-Host "[关闭] 停止 PostgreSQL..." -ForegroundColor Yellow
        docker compose -f "$projectRoot\docker\docker-compose.yml" down 2>$null
    }
    Write-Host "[关闭] 已全部停止" -ForegroundColor Green
}

# ── 前置检测 ──
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  边云协同智能检测系统 — 一键启动" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# Docker
if (-not $NoDb) {
    $dockerOk = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerOk) {
        Write-Host "[错误] 未找到 Docker，请安装 Docker Desktop" -ForegroundColor Red
        exit 1
    }
}

# Python
$pyOk = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyOk) {
    Write-Host "[错误] 未找到 Python" -ForegroundColor Red
    exit 1
}

# Node (only if web)
if (-not $NoWeb) {
    $nodeOk = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeOk) {
        Write-Host "[错误] 未找到 Node.js" -ForegroundColor Red
        exit 1
    }
}

# ── 1. 启动 PostgreSQL ──
if (-not $NoDb) {
    Write-Host "`n[1/4] 启动 PostgreSQL..." -ForegroundColor Cyan
    docker compose -f "$projectRoot\docker\docker-compose.yml" up -d

    Write-Host "[等待] 等待数据库就绪..." -ForegroundColor Gray
    $retry = 0
    do {
        Start-Sleep -Seconds 2
        $healthy = docker inspect --format="{{json .State.Health.Status}}" edgecloud-db 2>$null
        $retry++
    } while ($healthy -ne '"healthy"' -and $retry -lt 15)

    if ($healthy -ne '"healthy"') {
        Write-Host "[警告] 数据库可能未就绪，继续启动..." -ForegroundColor Yellow
    } else {
        Write-Host "[OK]   数据库已就绪 (localhost:5432)" -ForegroundColor Green
    }
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

# ── 等待 Ctrl+C ──
try {
    while ($true) { Start-Sleep -Seconds 1 }
} finally {
    Stop-All
}
