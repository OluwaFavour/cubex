# ============================================================================
# Dockerfile for CubeX FastAPI Application
# ============================================================================
# Multi-stage build for optimized production images
#
# Build targets:
#   - base: Common dependencies and setup
#   - api: FastAPI application server
#   - scheduler: APScheduler background jobs
#   - worker: RabbitMQ message consumer
#
# Usage:
#   docker build --target api -t cubex-api .
#   docker build --target scheduler -t cubex-scheduler .
#   docker build --target worker -t cubex-worker .
# ============================================================================

# ============================================================================
# Base Stage - Common dependencies
# ============================================================================
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# ============================================================================
# API Stage - FastAPI Application Server
# ============================================================================
FROM base AS api

# Expose the application port
EXPOSE 8000

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command - run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================================
# Scheduler Stage - APScheduler Background Jobs
# ============================================================================
FROM base AS scheduler

# Switch to non-root user
USER appuser

# Run the scheduler
CMD ["python", "-m", "app.infrastructure.scheduler.main"]

# ============================================================================
# Worker Stage - RabbitMQ Message Consumer
# ============================================================================
FROM base AS worker

# Switch to non-root user
USER appuser

# Run the message consumer
CMD ["python", "-m", "app.infrastructure.messaging.main"]
