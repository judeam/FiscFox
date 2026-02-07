# FiscFox Makefile
# Docker commands for development and production

.PHONY: build build-lite build-asia up up-lite down dev logs shell test lint clean help
.PHONY: venv venv-llm venv-asia run sync format typecheck db-init db-shell
.PHONY: download-models download-model-standard download-model-lite llm-status
.PHONY: desktop-deps desktop-run desktop-build desktop-build-linux desktop-build-macos desktop-build-windows desktop-install-linux

# Default target
.DEFAULT_GOAL := help

# Regional PyPI mirror for faster downloads (set via environment or override)
# Examples:
#   make build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple  # Asia (India/SEA)
#   make build PYPI_MIRROR=https://mirrors.aliyun.com/pypi/simple    # China
PYPI_MIRROR ?=

# =============================================================================
# Docker Commands
# =============================================================================

build: ## Build Docker images with LLM support (use PYPI_MIRROR for faster regional downloads)
	@mkdir -p data/models/llm
	docker compose build --build-arg PYPI_MIRROR=$(PYPI_MIRROR) --build-arg ENABLE_LLM=true app
	docker compose --profile dev build --build-arg PYPI_MIRROR=$(PYPI_MIRROR) --build-arg ENABLE_LLM=true dev

build-lite: ## Build Docker images WITHOUT LLM (smaller image, less RAM needed)
	docker compose --profile lite build --build-arg PYPI_MIRROR=$(PYPI_MIRROR) --build-arg ENABLE_LLM=false app-lite

build-asia: ## Build with Asian mirror (fastest for India/SEA/China)
	$(MAKE) build PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

build-dev: ## Build development Docker image
	docker compose --profile dev build dev

up: ## Start production container (with LLM)
	@mkdir -p data data/models/llm
	docker compose up -d app

up-lite: ## Start production container WITHOUT LLM (less RAM needed)
	@mkdir -p data
	docker compose --profile lite up -d app-lite

down: ## Stop and remove all containers
	docker compose --profile dev --profile lite down

dev: ## Start development container with hot reload
	@mkdir -p data
	docker compose --profile dev up dev

dev-d: ## Start development container detached
	@mkdir -p data
	docker compose --profile dev up -d dev

# =============================================================================
# Utility Commands
# =============================================================================

logs: ## View container logs
	docker compose logs -f

logs-dev: ## View dev container logs
	docker compose --profile dev logs -f dev

shell: ## Open shell in running container
	docker compose exec app /bin/bash

shell-dev: ## Open shell in dev container
	docker compose --profile dev exec dev /bin/bash

restart: ## Restart production container
	docker compose restart app

# =============================================================================
# Development Commands (local, non-Docker) - uses uv for speed
# =============================================================================

venv: ## Create virtual environment with uv (use PYPI_MIRROR for faster downloads)
	uv venv .venv
	$(if $(PYPI_MIRROR),UV_INDEX_URL=$(PYPI_MIRROR)) uv pip install -e ".[dev]"

venv-llm: ## Create venv with LLM dependencies (requires 6GB+ RAM)
	uv venv .venv
	@mkdir -p data/models/llm
	@echo "Installing CPU-only PyTorch (saves 2GB+ of CUDA packages)..."
	uv pip install torch --index-url https://download.pytorch.org/whl/cpu
	@echo "Installing pre-built llama-cpp-python (avoids compilation)..."
	uv pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
	$(if $(PYPI_MIRROR),UV_INDEX_URL=$(PYPI_MIRROR)) uv pip install -e ".[dev,ml,llm-full]"
	@echo ""
	@echo "LLM environment ready! Download models with: make download-models"

venv-asia: ## Create venv with Asian mirror (fastest for India/SEA/China)
	$(MAKE) venv PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

run: ## Run locally without Docker
	uv run uvicorn src.main:app --reload --port 8000

test: ## Run tests locally
	uv run pytest tests/ -v

lint: ## Run linter locally
	uv run ruff check src/
	uv run ruff format --check src/

format: ## Format code locally
	uv run ruff format src/

typecheck: ## Run type checker locally
	uv run mypy src/

sync: ## Sync dependencies with uv
	uv pip sync pyproject.toml

# =============================================================================
# Database Commands
# =============================================================================

db-init: ## Initialize database (local)
	uv run python -c "import asyncio; from src.db.repository import db_manager; asyncio.run(db_manager.initialize())"

db-migrate: ## Run database migrations
	@echo "Running migrations..."
	@for f in src/db/migrations/*.sql; do \
		echo "Applying $$f..."; \
		sqlite3 data/FiscFox.db < "$$f" 2>/dev/null || echo "  (already applied or skipped)"; \
	done
	@echo "Migrations complete."

db-shell: ## Open SQLite shell
	sqlite3 data/FiscFox.db

# =============================================================================
# LLM Model Commands
# =============================================================================

download-models: ## Download LLM models (Qwen3 4B standard + Phi-3.5 lite)
	@mkdir -p data/models/llm
	@echo "Downloading Qwen3-4B-Instruct-2507 (Q4_K_M, ~2.5GB)..."
	@echo "Source: https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF"
	@if [ ! -f data/models/llm/Qwen3-4B-Instruct-2507-Q4_K_M.gguf ]; then \
		curl -L --progress-bar -o data/models/llm/Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
			"https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"; \
	else \
		echo "  Already exists, skipping..."; \
	fi
	@echo ""
	@echo "Downloading Phi-3.5-mini-instruct (Q4_K_M, ~2.3GB)..."
	@echo "Source: https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF"
	@if [ ! -f data/models/llm/Phi-3.5-mini-instruct-Q4_K_M.gguf ]; then \
		curl -L --progress-bar -o data/models/llm/Phi-3.5-mini-instruct-Q4_K_M.gguf \
			"https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf"; \
	else \
		echo "  Already exists, skipping..."; \
	fi
	@echo ""
	@echo "Models downloaded to data/models/llm/"
	@ls -lh data/models/llm/

download-model-standard: ## Download only standard model (Qwen3 4B, ~2.5GB, needs 6GB RAM)
	@mkdir -p data/models/llm
	@echo "Downloading Qwen3-4B-Instruct-2507 (Q4_K_M, ~2.5GB)..."
	@echo "Source: https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF"
	@curl -L --progress-bar -o data/models/llm/Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
		"https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
	@echo "Done! Model ready at data/models/llm/"

download-model-lite: ## Download only lite model (Phi-3.5, ~2.3GB, needs 4GB RAM)
	@mkdir -p data/models/llm
	@echo "Downloading Phi-3.5-mini-instruct (Q4_K_M, ~2.3GB)..."
	@echo "Source: https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF"
	@curl -L --progress-bar -o data/models/llm/Phi-3.5-mini-instruct-Q4_K_M.gguf \
		"https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF/resolve/main/Phi-3.5-mini-instruct-Q4_K_M.gguf"
	@echo "Done! Run with: FISCFOX_LLM_MODEL_SIZE=lite make run"

llm-status: ## Check LLM service status
	@curl -s http://localhost:8000/api/llm/status | python -m json.tool 2>/dev/null || echo "Server not running"

# =============================================================================
# Cleanup Commands
# =============================================================================

clean: ## Remove Docker images and volumes
	docker compose --profile dev --profile lite down -v --rmi local

clean-all: ## Remove all Docker artifacts including cache
	docker compose --profile dev --profile lite down -v --rmi all
	docker builder prune -f

# =============================================================================
# Desktop App Commands (Cross-Platform)
# =============================================================================

desktop-deps: ## Install desktop dependencies (Linux: requires system GTK/WebKit)
	@if [ "$$(uname)" = "Linux" ]; then \
		echo "Linux detected: recreating venv with system Python for GTK access..."; \
		rm -rf .venv-desktop; \
		/usr/bin/python3 -m venv .venv-desktop --system-site-packages; \
		.venv-desktop/bin/pip install -e ".[desktop]"; \
		echo ""; \
		echo "Desktop venv created at .venv-desktop"; \
		echo "Run with: make desktop-run"; \
	else \
		uv pip install -e ".[desktop]"; \
	fi

desktop-run: ## Run desktop app (development)
	@if [ "$$(uname)" = "Linux" ] && [ -d ".venv-desktop" ]; then \
		.venv-desktop/bin/python desktop.py --debug; \
	else \
		uv run python desktop.py --debug; \
	fi

desktop-build: ## Build standalone executable for current platform
	@echo "Building FiscFox desktop app..."
	@mkdir -p dist
	pyinstaller fiscfox.spec --clean
	@echo ""
	@echo "Build complete! Output in dist/"
	@ls -lh dist/

desktop-build-linux: ## Build Linux executable (run on Linux)
	@echo "Building for Linux..."
	@echo "Note: Requires GTK3 and WebKitGTK. Install with:"
	@echo "  Debian/Ubuntu: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1"
	@echo "  Fedora: sudo dnf install python3-gobject gtk3 webkit2gtk4.1"
	@echo "  Arch: sudo pacman -S python-gobject gtk3 webkit2gtk-4.1"
	@echo ""
	@if [ -d ".venv-desktop" ]; then \
		.venv-desktop/bin/pyinstaller fiscfox.spec --clean; \
	else \
		pyinstaller fiscfox.spec --clean; \
	fi
	@echo "Output: dist/fiscfox"

desktop-install-linux: ## Install desktop entry and icon on Linux
	@echo "Installing FiscFox desktop entry..."
	@mkdir -p ~/.local/share/applications
	@mkdir -p ~/.local/share/icons/hicolor/512x512/apps
	@mkdir -p ~/.local/share/icons/hicolor/256x256/apps
	@cp assets/fiscfox.desktop ~/.local/share/applications/
	@cp assets/icon_512.png ~/.local/share/icons/hicolor/512x512/apps/fiscfox.png
	@cp assets/icon.png ~/.local/share/icons/hicolor/256x256/apps/fiscfox.png
	@gtk-update-icon-cache ~/.local/share/icons/hicolor/ 2>/dev/null || true
	@update-desktop-database ~/.local/share/applications/ 2>/dev/null || true
	@echo "Desktop entry installed! FiscFox should appear in your application menu."

desktop-build-macos: ## Build macOS app bundle (run on macOS)
	@echo "Building for macOS..."
	pyinstaller fiscfox.spec --clean
	@echo "Output: dist/FiscFox.app"

desktop-build-windows: ## Build Windows executable (run on Windows)
	@echo "Building for Windows..."
	pyinstaller fiscfox.spec --clean
	@echo "Output: dist/FiscFox.exe"

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "FiscFox - Freelance Tax Management System"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Docker targets:"
	@grep -E '^(build|build-lite|build-asia|up|up-lite|down|dev|dev-d|logs|logs-dev|shell|shell-dev|restart|clean|clean-all):.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "  Tip: Use PYPI_MIRROR for faster downloads in your region:"
	@echo "    make build-asia           # India/SEA/China (Tsinghua mirror)"
	@echo "    make build PYPI_MIRROR=https://your-mirror/simple"
	@echo ""
	@echo "LLM targets:"
	@grep -E '^(download-model|llm-|venv-llm)[a-zA-Z_-]*:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Desktop app targets:"
	@grep -E '^desktop-[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Local development targets (uv):"
	@grep -E '^(venv|sync|run|test|lint|format|typecheck|db-init|db-shell):.*?## .*$$' $(MAKEFILE_LIST) | grep -v llm | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
