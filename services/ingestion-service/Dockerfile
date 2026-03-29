# Flowfish Ingestion Service Dockerfile

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

RUN set -e && \
    PROTOC_VERSION="23.4" && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then PROTOC_ARCH="linux-aarch_64"; else PROTOC_ARCH="linux-x86_64"; fi && \
    PROTOC_URL="https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-${PROTOC_ARCH}.zip" && \
    PROTOC_FILE="protoc-${PROTOC_VERSION}-${PROTOC_ARCH}.zip" && \
    attempt=1 && \
    max_attempts=5 && \
    wait_time=10 && \
    while [ $attempt -le $max_attempts ]; do \
        echo "Downloading protoc from GitHub (attempt $attempt/$max_attempts)..."; \
        if curl -fSL --ipv4 \
            --retry 3 \
            --retry-delay 5 \
            --retry-connrefused \
            --connect-timeout 30 \
            --max-time 300 \
            -o "$PROTOC_FILE" "$PROTOC_URL"; then \
            echo "Download successful!"; \
            break; \
        fi; \
        echo "Attempt $attempt failed, waiting ${wait_time}s..."; \
        sleep $wait_time; \
        wait_time=$((wait_time * 2)); \
        attempt=$((attempt + 1)); \
        if [ $attempt -gt $max_attempts ]; then \
            echo "All download attempts failed!"; \
            exit 1; \
        fi; \
    done && \
    unzip "$PROTOC_FILE" -d /usr/local && \
    rm -f "$PROTOC_FILE"

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

# Install system dependencies including curl for kubectl download
# Force IPv4 to avoid IPv6 connectivity issues in build environments
RUN echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4 && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
# CVE-2024-24790 (net/netip) and CVE-2024-45338 (golang.org/x/net/html v0.33.0+) fixes
# kubectl v1.32.11 (Dec 16, 2025) includes golang.org/x/net v0.33.0+ with CVE-2024-45338 fix
ARG KUBECTL_VERSION=v1.32.11
RUN set -e && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then K8S_ARCH="arm64"; else K8S_ARCH="amd64"; fi && \
    KUBECTL_URL_PRIMARY="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${K8S_ARCH}/kubectl" && \
    KUBECTL_URL_MIRROR="https://storage.googleapis.com/kubernetes-release/release/${KUBECTL_VERSION}/bin/linux/${K8S_ARCH}/kubectl" && \
    download_kubectl() { \
        local url="$1"; \
        local attempt=1; \
        local max_attempts=5; \
        local wait_time=10; \
        while [ $attempt -le $max_attempts ]; do \
            echo "Downloading kubectl from $url (attempt $attempt/$max_attempts)..."; \
            if curl -fSL --ipv4 \
                --retry 3 \
                --retry-delay 5 \
                --retry-connrefused \
                --connect-timeout 30 \
                --max-time 600 \
                -o kubectl "$url"; then \
                echo "Download successful!"; \
                return 0; \
            fi; \
            echo "Attempt $attempt failed, waiting ${wait_time}s..."; \
            sleep $wait_time; \
            wait_time=$((wait_time * 2)); \
            attempt=$((attempt + 1)); \
        done; \
        return 1; \
    } && \
    (download_kubectl "$KUBECTL_URL_PRIMARY" || \
     (echo "Primary URL failed, trying mirror..." && download_kubectl "$KUBECTL_URL_MIRROR")) && \
    chmod +x kubectl && \
    mv kubectl /usr/local/bin/kubectl && \
    kubectl version --client=true

# Install kubectl-gadget plugin (from GitHub releases)
# CVE-2024-24790 fix: v0.36.0+ is built with Go 1.22.4+ which includes the fix
# v0.48.0 includes latest security patches
ARG GADGET_VERSION=v0.48.0
RUN set -e && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then GADGET_ARCH="arm64"; else GADGET_ARCH="amd64"; fi && \
    GADGET_URL="https://github.com/inspektor-gadget/inspektor-gadget/releases/download/${GADGET_VERSION}/kubectl-gadget-linux-${GADGET_ARCH}-${GADGET_VERSION}.tar.gz" && \
    GADGET_FILE="kubectl-gadget-linux-${GADGET_ARCH}-${GADGET_VERSION}.tar.gz" && \
    attempt=1 && \
    max_attempts=5 && \
    wait_time=10 && \
    while [ $attempt -le $max_attempts ]; do \
        echo "Downloading kubectl-gadget from GitHub (attempt $attempt/$max_attempts)..."; \
        if curl -fSL --ipv4 \
            --retry 3 \
            --retry-delay 5 \
            --retry-connrefused \
            --connect-timeout 30 \
            --max-time 600 \
            -o "$GADGET_FILE" "$GADGET_URL"; then \
            echo "Download successful!"; \
            break; \
        fi; \
        echo "Attempt $attempt failed, waiting ${wait_time}s..."; \
        sleep $wait_time; \
        wait_time=$((wait_time * 2)); \
        attempt=$((attempt + 1)); \
        if [ $attempt -gt $max_attempts ]; then \
            echo "All download attempts failed!"; \
            exit 1; \
        fi; \
    done && \
    tar -xzf "$GADGET_FILE" && \
    chmod +x kubectl-gadget && \
    mv kubectl-gadget /usr/local/bin/kubectl-gadget && \
    rm -f "$GADGET_FILE" && \
    kubectl-gadget version || true

# Copy requirements from service directory (build context is workspace root)
COPY services/ingestion-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy generated proto files from builder stage
COPY --from=proto-builder /build/proto_generated ./proto

# Copy application code from service directory
COPY services/ingestion-service/ .

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:0 /app && \
    chmod -R g=u /app

USER appuser

# Expose gRPC port
EXPOSE 5003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:5003'); channel.close()" || exit 1

# Run the service
CMD ["python", "main.py"]
