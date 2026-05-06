#!/bin/bash
set -e

echo "🚀 Starting RentWise..."
echo ""
echo "API:  http://localhost:8000"
echo "Web:  http://localhost:8081"
echo "Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to kill both processes
cleanup() {
    echo ""
    echo "🛑 Stopping services..."
    kill $API_PID $WEB_PID 2>/dev/null || true
    exit 0
}
trap cleanup EXIT INT TERM

# Start API
echo "📡 Starting API..."
cd apps/api
. .venv/bin/activate
uvicorn rentwise.main:app --reload &
API_PID=$!

# Wait for API to start
sleep 2

# Start Web
echo "🌐 Starting Web..."
cd ../web
npm run web &
WEB_PID=$!

# Keep script running
wait
