#!/bin/bash
#
# BBOCR Server Launcher
# config.yaml에서 포트를 읽어 백엔드 + 프론트엔드를 시작합니다.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── config.yaml에서 설정 읽기 ──────────────────────────────
read_config() {
    /c/Users/glgld/.conda/envs/bbocr/python.exe -c "
import yaml, sys
with open('config.yaml', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
server = cfg.get('server', {})
be = server.get('backend', {})
fe = server.get('frontend', {})
print(be.get('host', '0.0.0.0'))
print(be.get('port', 5015))
print(fe.get('host', '0.0.0.0'))
print(fe.get('port', 5017))
" 2>/dev/null
}

CONFIG_OUTPUT=$(read_config)
if [ -z "$CONFIG_OUTPUT" ]; then
    echo "[ERROR] config.yaml 파싱 실패. 기본값을 사용합니다."
    BACKEND_HOST="0.0.0.0"
    BACKEND_PORT=5015
    FRONTEND_HOST="0.0.0.0"
    FRONTEND_PORT=5017
else
    BACKEND_HOST=$(echo "$CONFIG_OUTPUT" | sed -n '1p')
    BACKEND_PORT=$(echo "$CONFIG_OUTPUT" | sed -n '2p')
    FRONTEND_HOST=$(echo "$CONFIG_OUTPUT" | sed -n '3p')
    FRONTEND_PORT=$(echo "$CONFIG_OUTPUT" | sed -n '4p')
fi

echo "========================================"
echo "  BBOCR Server Launcher"
echo "========================================"
echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
echo "========================================"

# ── 이미 실행 중인지 확인 ──────────────────────────────────
port_in_use() {
    netstat -an 2>/dev/null | grep -q ":$1 .*LISTEN" || \
    netstat -an 2>/dev/null | grep -q ":$1 .*LISTENING"
}

if port_in_use "$BACKEND_PORT"; then
    echo "[WARN] Backend port $BACKEND_PORT already in use. Stop existing server first."
    echo "       Run: ./stop.sh"
    exit 1
fi

if port_in_use "$FRONTEND_PORT"; then
    echo "[WARN] Frontend port $FRONTEND_PORT already in use. Stop existing server first."
    echo "       Run: ./stop.sh"
    exit 1
fi

# ── 로그 디렉토리 확인 ────────────────────────────────────
mkdir -p logs

# ── Frontend .env.local 설정 ───────────────────────────────
# 이미 .env.local이 존재하면 그대로 사용 (수동 설정 존중)
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    # Windows fallback: ipconfig로 IPv4 주소 추출
    SERVER_IP=$(ipconfig 2>/dev/null | grep -m1 "IPv4" | awk '{print $NF}' | tr -d '\r')
fi
if [ -z "$SERVER_IP" ]; then
    SERVER_IP="localhost"
fi

if [ -f "frontend/.env.local" ]; then
    echo "[INFO] frontend/.env.local already exists, keeping existing config:"
    echo "       $(cat frontend/.env.local)"
else
    cat > frontend/.env.local <<EOF
NEXT_PUBLIC_API_URL=http://${SERVER_IP}:${BACKEND_PORT}
EOF
    echo "[INFO] frontend/.env.local generated (API -> http://${SERVER_IP}:${BACKEND_PORT})"
fi

# ── Backend 시작 ──────────────────────────────────────────
echo "[INFO] Starting backend server..."
cd backend
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
nohup /c/Users/glgld/.conda/envs/bbocr/python.exe -m uvicorn main:app \
    --host "$BACKEND_HOST" \
    --port "$BACKEND_PORT" \
    > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > ../logs/backend.pid
cd ..
echo "[OK] Backend started (PID: $BACKEND_PID)"

# ── Frontend 빌드 후 프로덕션 모드로 시작 ────────────────────
# Windows에서 next dev의 webpack.js 파일 잠금(errno -4094) 문제를 회피합니다.
echo "[INFO] Building frontend (production build)..."
cd frontend
npx next build > ../logs/frontend_build.log 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Frontend build failed. See logs/frontend_build.log"
    cat ../logs/frontend_build.log | tail -20
    exit 1
fi
echo "[INFO] Starting frontend server (production mode)..."
nohup npx next start \
    -p "$FRONTEND_PORT" \
    -H "$FRONTEND_HOST" \
    > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > ../logs/frontend.pid
cd ..
echo "[OK] Frontend started (PID: $FRONTEND_PID)"

echo ""
echo "========================================"
echo "  Servers started successfully!"
echo "========================================"
echo "  Backend:  http://${SERVER_IP}:${BACKEND_PORT}  (PID: $BACKEND_PID)"
echo "  Frontend: http://${SERVER_IP}:${FRONTEND_PORT}  (PID: $FRONTEND_PID)"
echo ""
echo "  Logs:     tail -f logs/backend.log"
echo "            tail -f logs/frontend.log"
echo "  Stop:     ./stop.sh"
echo "  Status:   ./status.sh"
echo "========================================"
