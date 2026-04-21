#!/bin/bash
#
# BBOCR Server Shutdown
# config.yaml에서 포트를 읽어 해당 프로세스를 종료합니다.
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── config.yaml에서 포트 읽기 ─────────────────────────────
read_ports() {
    python3 -c "
import yaml
with open('config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
server = cfg.get('server', {})
print(server.get('backend', {}).get('port', 5015))
print(server.get('frontend', {}).get('port', 5017))
" 2>/dev/null
}

PORTS=$(read_ports)
BACKEND_PORT=$(echo "$PORTS" | sed -n '1p')
FRONTEND_PORT=$(echo "$PORTS" | sed -n '2p')

echo "========================================"
echo "  BBOCR Server Shutdown"
echo "========================================"

# ── 서버 종료 함수 ──────────────────────────────────────────
# PID 파일 → 포트 기반 fallback → 자식 프로세스까지 정리
stop_server() {
    local name="$1"
    local pid_file="$2"
    local port="$3"

    # 1) PID 파일로 프로세스 그룹 종료
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            # 프로세스 그룹 전체 종료 (자식 포함)
            kill -- -"$PID" 2>/dev/null || kill "$PID" 2>/dev/null
            echo "[OK] $name stopped (PID: $PID)"
        fi
        rm -f "$pid_file"
    fi

    # 2) 포트에 남아있는 프로세스도 정리
    sleep 0.5
    PIDS=$(lsof -i:"$port" -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill 2>/dev/null
        echo "[OK] $name: cleaned remaining processes on port $port"
    fi

    # 3) 최종 확인
    sleep 0.5
    if lsof -i:"$port" -sTCP:LISTEN -t > /dev/null 2>&1; then
        # 강제 종료
        lsof -i:"$port" -sTCP:LISTEN -t 2>/dev/null | xargs kill -9 2>/dev/null
        echo "[OK] $name: force killed on port $port"
    fi
}

stop_server "Backend"  "logs/backend.pid"  "$BACKEND_PORT"
stop_server "Frontend" "logs/frontend.pid" "$FRONTEND_PORT"

# ── Celery Worker 종료 ────────────────────────────────────
if [ -f "logs/worker.pid" ]; then
    WORKER_PID=$(cat logs/worker.pid)
    if kill -0 "$WORKER_PID" 2>/dev/null; then
        kill "$WORKER_PID" 2>/dev/null
        echo "[OK] Celery Worker stopped (PID: $WORKER_PID)"
    fi
    rm -f logs/worker.pid
fi

# ── Redis 종료 ────────────────────────────────────────────
if [ -f "logs/redis.pid" ]; then
    REDIS_PID=$(cat logs/redis.pid)
    if kill -0 "$REDIS_PID" 2>/dev/null; then
        kill "$REDIS_PID" 2>/dev/null
        echo "[OK] Redis stopped (PID: $REDIS_PID)"
    fi
    rm -f logs/redis.pid
fi

echo "========================================"
echo "  All servers stopped."
echo "========================================"
