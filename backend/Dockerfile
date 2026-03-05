# Flowfish Backend Dockerfile

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies (Debian-based, more stable than Alpine)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    make \
    && rm -rf /var/lib/apt/lists/*

# Create app user (UID will be overridden by OpenShift)
RUN useradd -m -u 1000 -s /bin/bash appuser

# Set work directory
WORKDIR /app

# Install Python dependencies (build context is workspace root)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code from backend directory first (excluding proto/)
COPY backend/ .

# Copy proto source files and generate Python code (AFTER backend copy to override any stale files)
COPY proto/ ./proto_source/
RUN mkdir -p proto && \
    python -m grpc_tools.protoc \
    -I./proto_source \
    --python_out=./proto \
    --grpc_python_out=./proto \
    proto_source/*.proto && \
    for file in ./proto/*_pb2.py ./proto/*_pb2_grpc.py; do \
        if [ -f "$file" ]; then \
            sed -i 's/^import \(.*_pb2\)/from . import \1/' "$file"; \
        fi \
    done && \
    touch proto/__init__.py && \
    rm -rf proto_source

# OpenShift compatibility: Set permissions for arbitrary UID
RUN chown -R appuser:0 /app && \
    chmod -R g=u /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Production command - Use main.py with all routers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
