# Flowfish Microservices Build Guide

## Overview

Bu dokümanda Flowfish mikroservislerinin Docker image'larının nasıl build edileceği anlatılmaktadır.

## Prerequisites

- Docker Desktop veya Docker Engine yüklü olmalı
- Python 3.11+ (local development için)
- Protocol Buffers compiler (`protoc`) yüklü olmalı

## Proto Code Generation

Öncelikle proto dosyalarından Python kodu generate edilmeli:

```bash
# Proto compiler'ı kontrol et
protoc --version

# Proto kodunu generate et
./scripts/generate_proto.sh
```

Bu komut `shared/proto_generated/python/` dizininde Python gRPC kodlarını oluşturur.

## Building Docker Images

### 1. Ingestion Service

```bash
cd services/ingestion-service
docker build -t flowfish/ingestion-service:latest .
docker tag flowfish/ingestion-service:latest flowfish/ingestion-service:1.0.0
```

### 2. ClickHouse Writer

```bash
cd services/clickhouse-writer
docker build -t flowfish/clickhouse-writer:latest .
docker tag flowfish/clickhouse-writer:latest flowfish/clickhouse-writer:1.0.0
```

### 3. Cluster Manager

```bash
cd services/cluster-manager
docker build -t flowfish/cluster-manager:latest .
docker tag flowfish/cluster-manager:latest flowfish/cluster-manager:1.0.0
```

### 4. Analysis Orchestrator

```bash
cd services/analysis-orchestrator
docker build -t flowfish/analysis-orchestrator:latest .
docker tag flowfish/analysis-orchestrator:latest flowfish/analysis-orchestrator:1.0.0
```

### 5. API Gateway

```bash
cd services/api-gateway
docker build -t flowfish/api-gateway:latest .
docker tag flowfish/api-gateway:latest flowfish/api-gateway:1.0.0
```

## Build All Services (Script)

Tüm servisleri tek komutla build etmek için:

```bash
#!/bin/bash
# build-all.sh

set -e

SERVICES=("ingestion-service" "clickhouse-writer" "cluster-manager" "analysis-orchestrator" "api-gateway")
VERSION=${1:-1.0.0}

echo "🐟 Building Flowfish Microservices..."
echo "Version: $VERSION"

for service in "${SERVICES[@]}"; do
    echo ""
    echo "📦 Building $service..."
    cd services/$service
    docker build -t flowfish/$service:latest .
    docker tag flowfish/$service:latest flowfish/$service:$VERSION
    echo "✅ $service built successfully"
    cd ../..
done

echo ""
echo "🎉 All services built successfully!"
echo ""
echo "Images:"
docker images | grep flowfish
```

Kullanım:
```bash
chmod +x build-all.sh
./build-all.sh          # Latest version
./build-all.sh 1.0.1    # Specific version
```

## Pushing to Registry

Docker Hub veya private registry'ye push etmek için:

```bash
# Docker Hub login
docker login

# Push images
for service in ingestion-service clickhouse-writer cluster-manager analysis-orchestrator api-gateway; do
    docker push flowfish/$service:latest
    docker push flowfish/$service:1.0.0
done
```

Private registry için:
```bash
# Tag for private registry
for service in ingestion-service clickhouse-writer cluster-manager analysis-orchestrator api-gateway; do
    docker tag flowfish/$service:latest registry.example.com/flowfish/$service:latest
    docker push registry.example.com/flowfish/$service:latest
done
```

## Local Development

Her servis için local development:

```bash
# Virtual environment oluştur
cd services/<service-name>
python3 -m venv .venv
source .venv/bin/activate

# Dependencies yükle
pip install -r requirements.txt

# Proto kodunu kopyala
cp -r ../../shared/proto_generated/python/* proto/

# Servisi çalıştır
python main.py
```

## Testing

Container'ları test etmek için:

```bash
# Ingestion Service
docker run --rm -p 5000:5000 \
    -e RABBITMQ_HOST=localhost \
    -e RABBITMQ_USER=flowfish \
    -e RABBITMQ_PASSWORD=flowfish123 \
    flowfish/ingestion-service:latest

# API Gateway
docker run --rm -p 8000:8000 \
    -e CLUSTER_MANAGER_HOST=localhost \
    -e ANALYSIS_ORCHESTRATOR_HOST=localhost \
    flowfish/api-gateway:latest

# Health check
curl http://localhost:8000/api/v1/health
```

## Kubernetes Deployment

Image'lar build edildikten sonra Kubernetes'e deploy etmek için:

```bash
# Namespace oluştur
kubectl apply -f deployment/kubernetes-manifests/01-namespace.yaml

# Secrets oluştur
kubectl apply -f deployment/kubernetes-manifests/04-secrets.yaml

# Servisleri deploy et
kubectl apply -f deployment/kubernetes-manifests/10-ingestion-service.yaml
kubectl apply -f deployment/kubernetes-manifests/11-clickhouse-writer.yaml
kubectl apply -f deployment/kubernetes-manifests/12-cluster-manager.yaml
kubectl apply -f deployment/kubernetes-manifests/13-analysis-orchestrator.yaml
kubectl apply -f deployment/kubernetes-manifests/14-api-gateway.yaml

# Pod'ların durumunu kontrol et
kubectl get pods -n flowfish
```

## Image Size Optimization

Production için image size'ı optimize etmek için multi-stage build kullanılabilir:

```dockerfile
# Multi-stage build örneği
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "main.py"]
```

## Troubleshooting

### Image build hatası

```bash
# Docker cache'i temizle
docker builder prune

# Yeniden build et
docker build --no-cache -t flowfish/service:latest .
```

### Proto import hatası

```bash
# Proto kodunu yeniden generate et
./scripts/generate_proto.sh

# Proto dizinini servise kopyala
cp -r shared/proto_generated/python/* services/<service>/proto/
```

### Container çalışmıyor

```bash
# Container logs'ları kontrol et
docker logs <container-id>

# Interactive shell'e gir
docker run -it --entrypoint /bin/bash flowfish/service:latest
```

## Next Steps

1. ✅ Proto definitions (5 files)
2. ✅ Ingestion Service
3. ✅ ClickHouse Writer
4. ✅ Cluster Manager
5. ✅ Analysis Orchestrator
6. ✅ API Gateway
7. 🔲 Build all Docker images
8. 🔲 Deploy to Kubernetes
9. 🔲 Integration testing
