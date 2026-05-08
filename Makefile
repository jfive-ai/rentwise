.PHONY: help install setup dev api web ios macos setup-desktop stop kill-all clean lint test type-check clean-all

PYTHON := /opt/homebrew/bin/python3.12
API_DIR := apps/api
WEB_DIR := apps/web
DESKTOP_DIR := apps/desktop
API_VENV := $(API_DIR)/.venv/bin/activate

help:
	@echo "RentWise Development Commands"
	@echo "=============================="
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install         Install all dependencies (backend + frontend)"
	@echo "  make setup-api       Set up backend only"
	@echo "  make setup-web       Set up frontend only"
	@echo "  make setup-desktop   Set up macOS desktop app (first-time, ~5 min Rust build)"
	@echo ""
	@echo "Running the App:"
	@echo "  make dev             Start both API and web (browser)"
	@echo "  make api             Start API only"
	@echo "  make web             Start web only (browser)"
	@echo "  make ios             Start iOS simulator"
	@echo "  make macos           Start macOS desktop app (Tauri)"
	@echo "  make stop            Stop API and web services"
	@echo "  make kill-all        Force kill all Node/Python processes"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint            Run ruff linter on backend"
	@echo "  make format          Format code with ruff"
	@echo "  make type-check      Run type checks with mypy"
	@echo "  make test            Run pytest tests"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           Remove venvs and node_modules"
	@echo "  make clean-all       Clean + remove .env and database"
	@echo ""

# Setup & Installation
install: setup-api setup-web
	@echo "✅ All dependencies installed!"

setup-api:
	@echo "Setting up backend..."
	cd $(API_DIR) && uv sync --python 3.12
	@echo "✅ Backend ready"

setup-web:
	@echo "Setting up frontend..."
	cd $(WEB_DIR) && npm install
	@echo "✅ Frontend ready"

setup-desktop:
	@echo "Setting up macOS desktop app (Tauri)..."
	cd $(DESKTOP_DIR) && npm install
	cd $(DESKTOP_DIR) && npm run tauri build -- --debug
	@echo "✅ Desktop app ready — run 'make macos' to launch"

# Running the App
dev:
	@bash ./start.sh

api:
	@echo "Starting API on http://localhost:8000..."
	cd $(API_DIR) && . .venv/bin/activate && uvicorn rentwise.main:app --reload

web:
	@echo "Starting Web on http://localhost:8081..."
	cd $(WEB_DIR) && npm run web

ios:
	@echo "Starting iOS simulator..."
	cd $(WEB_DIR) && npm run ios

macos:
	@bash ./start-macos.sh

stop:
	@echo "Stopping RentWise services..."
	@pkill -f "uvicorn rentwise.main:app" 2>/dev/null || true
	@pkill -f "npm run web" 2>/dev/null || true
	@pkill -f "start.sh" 2>/dev/null || true
	@pkill -f "start-macos.sh" 2>/dev/null || true
	@pkill -f "tauri dev" 2>/dev/null || true
	@lsof -ti :8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti :8081 | xargs kill -9 2>/dev/null || true
	@sleep 1
	@echo "✅ Services stopped"

kill-all: stop
	@echo "Killing all Node and Python dev processes..."
	@pkill -f "node" || true
	@pkill -f "python" || true
	@echo "✅ All processes killed"

# Code Quality
lint:
	@echo "Linting backend..."
	cd $(API_DIR) && . .venv/bin/activate && ruff check .
	@echo "✅ Lint passed"

format:
	@echo "Formatting backend code..."
	cd $(API_DIR) && . .venv/bin/activate && ruff check . --fix && ruff format .
	@echo "✅ Code formatted"

type-check:
	@echo "Type checking backend..."
	cd $(API_DIR) && . .venv/bin/activate && mypy rentwise
	@echo "✅ Type checks passed"

test:
	@echo "Running tests..."
	cd $(API_DIR) && . .venv/bin/activate && pytest
	@echo "✅ Tests passed"

# Cleanup
clean:
	@echo "Cleaning up development files..."
	rm -rf $(API_DIR)/.venv
	rm -rf $(WEB_DIR)/node_modules
	rm -rf $(API_DIR)/__pycache__
	rm -rf $(API_DIR)/.pytest_cache
	find $(API_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Cleaned"

clean-all: clean
	@echo "Removing additional files..."
	rm -f .env
	rm -rf $(API_DIR)/data
	@echo "✅ Full cleanup complete"

.DEFAULT_GOAL := help
