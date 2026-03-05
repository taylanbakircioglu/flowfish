# Cluster Manager Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Force IPv4 to avoid IPv6 connectivity issues in build environments
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY services/cluster-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files and generate Python code
COPY proto/ /app/proto/
RUN python -m grpc_tools.protoc \
    -I/app/proto \
    --python_out=/app/proto \
    --grpc_python_out=/app/proto \
    /app/proto/cluster_manager.proto

# Fix proto imports
RUN sed -i 's/^import cluster_manager_pb2/from . import cluster_manager_pb2/' /app/proto/cluster_manager_pb2_grpc.py

# Create __init__.py for proto package
RUN echo "# Generated proto package" > /app/proto/__init__.py

# Copy application code
COPY services/cluster-manager/app/ /app/app/

# Create non-root user
RUN useradd --create-home appuser
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose gRPC port
EXPOSE 5001

# Run the server
CMD ["python", "-m", "app.grpc_server"]
