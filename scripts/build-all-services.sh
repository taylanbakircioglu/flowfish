#!/bin/bash
#
# Flowfish Microservices Build Script
# Builds all microservice Docker images
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICES=("ingestion-service" "timeseries-writer" "cluster-manager" "analysis-orchestrator" "api-gateway" "graph-writer" "graph-query")
VERSION=${1:-1.0.0}
REGISTRY=${DOCKER_REGISTRY:-""}

# Functions
log_info() {
    echo -e "${BLUE}ℹ ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅${NC} $1"
}

log_error() {
    echo -e "${RED}❌${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠️ ${NC} $1"
}

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    log_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

echo ""
echo "🐟 Flowfish Microservices Build"
echo "================================"
echo ""
log_info "Version: $VERSION"
log_info "Services: ${#SERVICES[@]}"
if [ -n "$REGISTRY" ]; then
    log_info "Registry: $REGISTRY"
fi
echo ""

# Check if proto code is generated
if [ ! -d "shared/proto_generated/python" ]; then
    log_warning "Proto code not found. Generating..."
    ./scripts/generate_proto.sh
    log_success "Proto code generated"
    echo ""
fi

# Build each service
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_SERVICES=()

for service in "${SERVICES[@]}"; do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "Building: $service"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    cd "services/$service"
    
    # Copy proto files to service
    log_info "Copying proto files..."
    mkdir -p proto
    cp -r ../../shared/proto_generated/python/* proto/ 2>/dev/null || true
    
    # Build image
    IMAGE_NAME="flowfish/$service"
    if [ -n "$REGISTRY" ]; then
        IMAGE_NAME="$REGISTRY/$IMAGE_NAME"
    fi
    
    log_info "Building Docker image: $IMAGE_NAME:$VERSION"
    
    if docker build -t "$IMAGE_NAME:latest" -t "$IMAGE_NAME:$VERSION" . ; then
        log_success "$service built successfully"
        ((SUCCESS_COUNT++))
    else
        log_error "$service build failed"
        FAILED_SERVICES+=("$service")
        ((FAILED_COUNT++))
    fi
    
    cd ../..
    echo ""
done

# Summary
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Build Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log_success "Successful: $SUCCESS_COUNT"
if [ $FAILED_COUNT -gt 0 ]; then
    log_error "Failed: $FAILED_COUNT"
    echo "   Failed services: ${FAILED_SERVICES[*]}"
fi
echo ""

# List built images
log_info "Built images:"
echo ""
docker images | grep flowfish | head -n 10
echo ""

# Success or failure
if [ $FAILED_COUNT -eq 0 ]; then
    log_success "All services built successfully! 🎉"
    echo ""
    echo "Next steps:"
    echo "  1. Push images to registry (if needed):"
    echo "     docker push flowfish/service:$VERSION"
    echo ""
    echo "  2. Deploy to Kubernetes:"
    echo "     kubectl apply -f deployment/kubernetes-manifests/"
    echo ""
    exit 0
else
    log_error "Some services failed to build"
    exit 1
fi

