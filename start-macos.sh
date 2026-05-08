#!/bin/bash
set -e

echo "🚀 Starting RentWise (macOS desktop app)..."
echo ""
echo "API:    http://localhost:8000"
echo "Web:    http://localhost:8081"
echo "Tauri:  RentWise.app window"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

API_PID=""
WEB_PID=""

cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    [ -n "$API_PID" ] && kill $API_PID 2>/dev/null || true
    [ -n "$WEB_PID" ] && kill $WEB_PID 2>/dev/null || true
    exit 0
}
trap cleanup EXIT INT TERM

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

if lsof -ti :8000 >/dev/null 2>&1; then
    echo "📡 API already running on :8000 — reusing"
else
    echo "📡 Starting API..."
    cd "$ROOT_DIR/apps/api"
    . .venv/bin/activate
    uvicorn rentwise.main:app --reload >/dev/null 2>&1 &
    API_PID=$!
fi

if lsof -ti :8081 >/dev/null 2>&1; then
    echo "🌐 Web already running on :8081 — reusing"
else
    echo "🌐 Starting Web..."
    cd "$ROOT_DIR/apps/web"
    npm run web >/dev/null 2>&1 &
    WEB_PID=$!
fi

echo "⏳ Waiting for Expo dev server on :8081..."
for i in {1..120}; do
    if curl -sf http://localhost:8081 >/dev/null 2>&1; then
        echo "✅ Expo dev server is up"
        break
    fi
    if [ -n "$WEB_PID" ] && ! kill -0 $WEB_PID 2>/dev/null; then
        echo "❌ Web process exited before binding :8081"
        exit 1
    fi
    sleep 1
done

if ! curl -sf http://localhost:8081 >/dev/null 2>&1; then
    echo "❌ Expo dev server didn't come up within 120s"
    exit 1
fi

echo "🖥  Launching Tauri..."
cd "$ROOT_DIR/apps/desktop"
npm run tauri dev
