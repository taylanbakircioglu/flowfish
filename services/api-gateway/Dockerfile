# Flowfish API Gateway Service Dockerfile

# Stage 1: Proto Generation
FROM python:3.11-slim AS proto-builder

WORKDIR /build

# Install protoc
# Force IPv4 to avoid IPv6 connectivity issues in build environments
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN PROTOC_VERSION="23.4" && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then PROTOC_ARCH="linux-aarch_64"; else PROTOC_ARCH="linux-x86_64"; fi && \
    curl -LO "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-${PROTOC_ARCH}.zip" && \
    unzip protoc-${PROTOC_VERSION}-${PROTOC_ARCH}.zip -d /usr/local && \
    rm protoc-${PROTOC_VERSION}-${PROTOC_ARCH}.zip

# Install grpcio-tools (version 1.60.x for protobuf 5.x compatibility)
RUN pip install --no-cache-dir 'grpcio-tools<1.61' 'grpcio<1.61'

# Copy proto files from workspace root
COPY proto ./proto_source

# Generate Python code
RUN mkdir -p ./proto_generated && \
    python -m grpc_tools.protoc \
    -I./proto_source \
    --python_out=./proto_generated \
    --grpc_python_out=./proto_generated \
    ./proto_source/*.proto

# Fix imports in both _pb2.py and _pb2_grpc.py files
RUN for file in ./proto_generated/*_pb2.py ./proto_generated/*_pb2_grpc.py; do \
        if [ -f "$file" ]; then \
            sed -i 's/^import \(.*_pb2\)/from . import \1/' "$file"; \
        fi \
    done && \
    touch ./proto_generated/__init__.py

# Stage 2: Application
FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
# Force IPv4 to avoid IPv6 connectivity issues in build environments
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from service directory (build context is workspace root)
COPY services/api-gateway/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy generated proto files from builder stage
COPY --from=proto-builder /build/proto_generated ./proto

# Copy application code from service directory
COPY services/api-gateway/ .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g=u /app

USER appuser

# Expose HTTP port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health')" || exit 1

# Run the service
CMD ["python", "main.py"]

