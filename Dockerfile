# ==============================================================================
# HobbyFi Copilot - Production Dockerfile
# ==============================================================================
# Production-ready Docker image for the HobbyFi AI Copilot.
#
# Build:
#   docker build -t hobbyfi-copilot .
#
# Run:
#   docker run -p 8000:8000 hobbyfi-copilot
#
# ==============================================================================

FROM python:3.11-slim

# ------------------------------------------------------------------------------
# Python Configuration
# ------------------------------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ------------------------------------------------------------------------------
# System Dependencies
# ------------------------------------------------------------------------------
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------------------
# Install Python Dependencies
# ------------------------------------------------------------------------------
COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    pip install -r requirements.txt

# ------------------------------------------------------------------------------
# Copy Application
# ------------------------------------------------------------------------------
COPY . .

# ------------------------------------------------------------------------------
# Expose Port
# ------------------------------------------------------------------------------
EXPOSE 8000

# ------------------------------------------------------------------------------
# Start FastAPI
# ------------------------------------------------------------------------------
# Render injects PORT automatically.
# Local Docker falls back to 8000.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]