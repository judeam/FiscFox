# syntax=docker/dockerfile:1
# FiscFox Dockerfile
# Multi-stage build with uv for fast dependency installation

# ============================================
# Stage 0: Build frontend assets (Tailwind CSS)
# ============================================
FROM debian:bookworm-slim AS frontend

WORKDIR /app

# Download Tailwind CSS standalone CLI
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sLO https://github.com/tailwindlabs/tailwindcss/releases/latest/download/tailwindcss-linux-x64 \
    && chmod +x tailwindcss-linux-x64 \
    && mv tailwindcss-linux-x64 /usr/local/bin/tailwindcss \
    && rm -rf /var/lib/apt/lists/*

# Copy config and source files
COPY tailwind.config.js .
COPY src/web/templates ./src/web/templates
COPY src/web/static/css/input.css ./src/web/static/css/

# Build Tailwind CSS (minified for production)
RUN tailwindcss -i ./src/web/static/css/input.css -o ./src/web/static/css/tailwind.css --minify

# ============================================
# Stage 1: Build dependencies with uv
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for llama-cpp-python and uv
# cmake and g++ are required for llama-cpp-python CPU build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    cmake \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.local/bin:$PATH"

# Regional PyPI mirror configuration for faster downloads
# Set via build arg: --build-arg PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
# Common mirrors:
#   Asia (fastest for India/SEA): https://pypi.tuna.tsinghua.edu.cn/simple
#   China (Alibaba):              https://mirrors.aliyun.com/pypi/simple
#   Default (global CDN):         https://pypi.org/simple
ARG PYPI_MIRROR=""
ENV UV_INDEX_URL=${PYPI_MIRROR}

# LLM feature toggle - set to "true" to include local LLM inference
# Build without LLM: docker build --build-arg ENABLE_LLM=false .
# Build with LLM:    docker build --build-arg ENABLE_LLM=true .
ARG ENABLE_LLM=true

# Create virtual environment with uv
RUN uv venv /opt/venv
ENV VIRTUAL_ENV="/opt/venv"
ENV PATH="/opt/venv/bin:$PATH"

# Copy pyproject.toml and install dependencies with uv (much faster than pip)
COPY pyproject.toml .

# Install CPU-only PyTorch first (avoids 2GB+ of NVIDIA CUDA packages)
RUN uv pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install base + ML dependencies, optionally add LLM
RUN if [ "$ENABLE_LLM" = "true" ]; then \
        echo "Installing with LLM support..." && \
        uv pip install -e ".[ml,llm-full]"; \
    else \
        echo "Installing without LLM support..." && \
        uv pip install -e ".[ml]"; \
    fi

# Models directory for embeddings and LLM models
# - HuggingFace models (~80MB) download on first use
# - LLM GGUF models should be mounted from host
ENV HF_HOME=/opt/models
RUN mkdir -p /opt/models /opt/models/llm

# ============================================
# Stage 2: Production image
# ============================================
FROM python:3.11-slim AS production

WORKDIR /app

# Install runtime dependencies for PDF extraction and OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV HF_HOME=/opt/models

# LLM configuration environment variables
# Models directory - mount GGUF files here
ENV FISCFOX_LLM_MODELS_DIR=/opt/models/llm
# Enable/disable LLM features (can be overridden at runtime)
ENV FISCFOX_LLM_ENABLED=true
# Model size: "standard" (7B, needs 16GB RAM) or "lite" (3B, needs 8GB RAM)
ENV FISCFOX_LLM_MODEL_SIZE=standard
# Context window size
ENV FISCFOX_LLM_CONTEXT_LENGTH=8192

# Copy application code
COPY src/ ./src/

# Copy built Tailwind CSS from frontend stage
COPY --from=frontend /app/src/web/static/css/tailwind.css ./src/web/static/css/

# Create data directory for SQLite, uploads, and models, set permissions
RUN mkdir -p /app/data /app/data/uploads/invoices /opt/models /opt/models/llm && \
    useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app /opt/models

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Production command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================
# Stage 3: Development image
# ============================================
FROM python:3.11-slim AS development

WORKDIR /app

# Install runtime dependencies, uv for fast installs
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV HF_HOME=/opt/models

# LLM configuration environment variables (same as production)
ENV FISCFOX_LLM_MODELS_DIR=/opt/models/llm
ENV FISCFOX_LLM_ENABLED=true
ENV FISCFOX_LLM_MODEL_SIZE=standard
ENV FISCFOX_LLM_CONTEXT_LENGTH=8192

# Install dev dependencies with uv (ML/LLM deps already in venv from builder)
COPY pyproject.toml .
RUN uv pip install -e ".[dev]"

# Copy application code (will be overwritten by volume mount)
COPY src/ ./src/

# Copy built Tailwind CSS from frontend stage
COPY --from=frontend /app/src/web/static/css/tailwind.css ./src/web/static/css/

# Create data directory and user with matching UID for volume permissions
ARG UID=1000
ARG GID=1000
RUN mkdir -p /app/data /app/data/uploads/invoices /opt/models /opt/models/llm && \
    groupadd -g ${GID} appuser && \
    useradd --create-home --shell /bin/bash -u ${UID} -g ${GID} appuser && \
    chown -R appuser:appuser /app /opt/models

USER appuser

EXPOSE 8000

# Development command with hot reload
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
