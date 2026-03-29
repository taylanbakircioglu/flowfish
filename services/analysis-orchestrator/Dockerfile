# Flowfish Analysis Orchestrator Service Dockerfile

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
    curl -LO "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-x86_64.zip" && \
    unzip protoc-${PROTOC_VERSION}-linux-x86_64.zip -d /usr/local && \
    rm protoc-${PROTOC_VERSION}-linux-x86_64.zip

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
COPY services/analysis-orchestrator/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy generated proto files from builder stage
COPY --from=proto-builder /build/proto_generated ./proto

# Copy application code from service directory
COPY services/analysis-orchestrator/ .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g=u /app

USER appuser

# Expose gRPC port
EXPOSE 5002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:5002'); channel.close()" || exit 1

# Run the service
CMD ["python", "main.py"]
