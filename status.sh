#!/bin/bash
#
# BBOCR Server Status
# config.yaml에서 포트를 읽어 서버 상태를 확인합니다.
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── config.yaml에서 설정 읽기 ─────────────────────────────
read_config() {
    python3 -c "
import yaml
with open('config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
server = cfg.get('server', {})
print(server.get('backend', {}).get('port', 5015))
print(server.get('frontend', {}).get('port', 5017))
" 2>/dev/null
}

PORTS=$(read_config)
BACKEND_PORT=$(echo "$PORTS" | sed -n '1p')
FRONTEND_PORT=$(echo "$PORTS" | sed -n '2p')

SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$SERVER_IP" ] && SERVER_IP="localhost"

echo "========================================"
echo "  BBOCR Server Status"
echo "========================================"

# ── 서버 상태 확인 ────────────────────────────────────────
check_server() {
    local name="$1"
    local port="$2"
    local pid_file="$3"

    local pid=""
    local status="STOPPED"
    local color="\033[31m"  # red

    # PID 파일 확인
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            status="RUNNING"
            color="\033[32m"  # green
        else
            pid=""
        fi
    fi

    # PID 파일 없으면 포트로 확인
    if [ -z "$pid" ]; then
        pid=$(lsof -i:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
        if [ -n "$pid" ]; then
            status="RUNNING"
            color="\033[32m"
        fi
    fi

    local reset="\033[0m"
    if [ "$status" = "RUNNING" ]; then
        echo -e "  $name:  ${color}${status}${reset}  (PID: $pid, port: $port)"
        echo "           http://${SERVER_IP}:${port}"
    else
        echo -e "  $name:  ${color}${status}${reset}  (port: $port)"
    fi
}

check_server "Backend " "$BACKEND_PORT"  "logs/backend.pid"
check_server "Frontend" "$FRONTEND_PORT" "logs/frontend.pid"

echo ""

# ── GPU 상태 ──────────────────────────────────────────────
if command -v nvidia-smi &> /dev/null; then
    echo "  GPU:"
    nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null | while read line; do
        echo "    $line"
    done
else
    echo "  GPU: nvidia-smi not found"
fi

echo "========================================"
