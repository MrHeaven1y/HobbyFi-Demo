# ==============================================================================
# HobbyFi Copilot - Production Dockerfile
# ==============================================================================
# Multi-stage build for the HobbyFi AI Copilot vendor portal.
# Uses Python 3.11-slim as the base image for a minimal footprint.
#
# Build:  docker build -t hobbyfi-copilot .
# Run:    docker-compose up  (preferred, see docker-compose.yml)
# ==============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
# so logs appear in real-time in Docker logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by psycopg2 and sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies first (Docker layer caching optimization)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Run the application with uvicorn
# --host 0.0.0.0 binds to all interfaces inside the container
# --workers 1 is suitable for development; increase for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
