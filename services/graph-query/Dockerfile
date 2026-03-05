# Graph Query Service Dockerfile

FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
# Force IPv4 to avoid IPv6 connectivity issues in build environments
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service directory (build context is workspace root)
COPY services/graph-query/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from service directory
COPY services/graph-query/ .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g=u /app

USER appuser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

# Run the service
CMD ["python", "main.py"]

