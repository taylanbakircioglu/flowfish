FROM python:3.11-slim

WORKDIR /app

# Install dependencies (build context is workspace root)
COPY services/timeseries-query/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from service directory
COPY services/timeseries-query/app/ ./app/
COPY services/timeseries-query/main.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g=u /app

USER appuser

# Expose ports
EXPOSE 8002

# Health check (using Python since curl not available in slim image)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8002/health', timeout=5); exit(0 if r.status_code == 200 else 1)"

# Run
CMD ["python", "main.py"]

