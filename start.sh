#!/usr/bin/env bash
# ============================================================
# 边云协同智能检测系统 — 一键启动脚本 (Bash)
# 用法:
#   bash start.sh            # 启动全部服务
#   bash start.sh --no-web   # 跳过 Web 前端
#   Ctrl+C                    # 停止全部服务
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NO_WEB=false
for arg in "$@"; do
    case "$arg" in
        --no-web) NO_WEB=true ;;
    esac
done

PIDS=()
cleanup() {
    echo ""
    echo "[关闭] 正在停止所有服务..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
    done
    echo "[关闭] 已全部停止"
    exit 0
}
trap cleanup INT TERM

echo "============================================"
echo "  边云协同智能检测系统 — 一键启动"
echo "============================================"

command -v python >/dev/null 2>&1 || { echo "[错误] 未找到 Python"; exit 1; }
if [ "$NO_WEB" = false ]; then
    command -v node >/dev/null 2>&1 || { echo "[错误] 未找到 Node.js"; exit 1; }
fi

# ── 1. 检测数据库连通性 ──
echo ""
echo "[1/5] 检测数据库连通性..."
db_check=$(python -c "
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
" 2>&1)
if [ $? -eq 0 ]; then
    echo "[OK]   数据库已连接: $db_check"
else
    echo "[错误] 数据库连接失败，请检查 .env 配置"
    echo "$db_check"
    exit 1
fi

# ── 2. 检测 MQTT 连通性 ──
echo ""
echo "[2/5] 检测 MQTT Broker..."
mqtt_check=$(python -c "
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
" 2>&1)
if echo "$mqtt_check" | grep -q "connected"; then
    echo "[OK]   MQTT Broker 已连接"
else
    echo "[警告] MQTT 连接失败，将回退 HTTP 上传"
    echo "       请确保已启动: docker compose -f docker/docker-compose.yml up -d"
fi

# ── 3. 启动 Cloud API ──
echo ""
echo "[3/5] 启动 Cloud API (localhost:8000)..."
python -m cloud.main &
PIDS+=($!)
sleep 3
echo "[OK]   Cloud API 已启动"

# ── 4. 启动 Edge Server ──
echo ""
echo "[4/5] 启动 Edge Server (localhost:8080)..."
python -m edge.main --server &
PIDS+=($!)
sleep 2
echo "[OK]   Edge Server 已启动"

# ── 5. 启动 Web 前端 ──
if [ "$NO_WEB" = false ]; then
    echo ""
    echo "[5/5] 启动 Web 前端 (localhost:5173)..."
    if [ ! -d "$SCRIPT_DIR/web/node_modules" ]; then
        echo "[安装] npm install..."
        (cd "$SCRIPT_DIR/web" && npm install)
    fi
    (cd "$SCRIPT_DIR/web" && npm run dev) &
    PIDS+=($!)
    sleep 3
    echo "[OK]   Web 前端已启动"
fi

echo ""
echo "============================================"
echo "  全部服务已启动!"
echo "============================================"
echo "  Web 管理端:   http://localhost:5173"
echo "  Cloud API:    http://localhost:8000/docs"
echo "  Edge Stream:  http://localhost:8080/stream"
echo "  Edge API:     http://localhost:8080/api/status"
echo ""
echo "  按 Ctrl+C 停止所有服务"

wait
