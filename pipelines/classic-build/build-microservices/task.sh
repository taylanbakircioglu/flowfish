#!/bin/bash
set -e

# ==============================================================================
# Flowfish Microservices Build - Incremental Build Support
# ==============================================================================
# Bu script "Detect Changes" task'ından sonra çalışır.
# *_CHANGED değişkenleri önceki task tarafından set edilmiş olmalı.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 MICROSERVICES BUILD"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ${BUILD_SOURCESDIRECTORY}

cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
environment=${DEPLOYMENT_ENV:-pilot}
HARBOR_PROJECT="flowfish"

echo ""
echo "📦 Commit Hash: $cmtHashShort"
echo "🌍 Environment: $environment"
echo "🏭 Harbor Project: $HARBOR_PROJECT"
echo ""
echo "📋 Change Detection Results (from previous task):"
echo "   API_GATEWAY_CHANGED: ${API_GATEWAY_CHANGED:-0}"
echo "   CLUSTER_MANAGER_CHANGED: ${CLUSTER_MANAGER_CHANGED:-0}"
echo "   ANALYSIS_ORCHESTRATOR_CHANGED: ${ANALYSIS_ORCHESTRATOR_CHANGED:-0}"
echo "   GRAPH_WRITER_CHANGED: ${GRAPH_WRITER_CHANGED:-0}"
echo "   GRAPH_QUERY_CHANGED: ${GRAPH_QUERY_CHANGED:-0}"
echo "   TIMESERIES_WRITER_CHANGED: ${TIMESERIES_WRITER_CHANGED:-0}"
echo "   TIMESERIES_QUERY_CHANGED: ${TIMESERIES_QUERY_CHANGED:-0}"
echo "   INGESTION_SERVICE_CHANGED: ${INGESTION_SERVICE_CHANGED:-0}"
echo "   CHANGE_WORKER_CHANGED: ${CHANGE_WORKER_CHANGED:-0}"

# Harbor'a login
if [ -z "${HARBOR_REGISTRY}" ] || [ -z "${HARBOR_USER}" ] || [ -z "${HARBOR_PASSWORD}" ]; then
    echo "❌ ERROR: Harbor credentials not set!"
    exit 1
fi

podman login -u ${HARBOR_USER} -p ${HARBOR_PASSWORD} ${HARBOR_REGISTRY}

# Microservice build fonksiyonu
build_microservice() {
    local service_name="$1"
    local changed_flag="${2:-0}"
    local dockerfile_path="services/$service_name/Dockerfile"
    
    # Değişiklik flag'i kontrolü (varsayılan 0)
    if [ "${changed_flag:-0}" -gt 0 ] 2>/dev/null; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🔨 Building: $service_name"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        podman build --no-cache --rm=false \
            -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-$service_name:$cmtHashShort \
            -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-$service_name:latest \
            --build-arg environment=$environment \
            -f $dockerfile_path \
            .
        
        podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-$service_name:$cmtHashShort
        podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-$service_name:latest
        
        echo "✅ $service_name build complete!"
        
        # Azure DevOps output variable - bu servisin derlendiğini bildir
        local var_name=$(echo "${service_name}" | tr '-' '_' | tr '[:lower:]' '[:upper:]')
        echo "##vso[task.setvariable variable=${var_name}_BUILT;isOutput=true]true"
        echo "##vso[task.setvariable variable=${var_name}_TAG;isOutput=true]$cmtHashShort"
        return 0
    else
        echo "⏭️  Skipping $service_name - No changes detected"
        local var_name=$(echo "${service_name}" | tr '-' '_' | tr '[:lower:]' '[:upper:]')
        echo "##vso[task.setvariable variable=${var_name}_BUILT;isOutput=true]false"
        return 0
    fi
}

# Counter for built services
BUILT_COUNT=0
SKIPPED_COUNT=0

# Her microservice için ayrı build
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Starting Microservices Build..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# API Gateway
build_microservice "api-gateway" "${API_GATEWAY_CHANGED:-0}"
if [ "${API_GATEWAY_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Cluster Manager
build_microservice "cluster-manager" "${CLUSTER_MANAGER_CHANGED:-0}"
if [ "${CLUSTER_MANAGER_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Analysis Orchestrator
build_microservice "analysis-orchestrator" "${ANALYSIS_ORCHESTRATOR_CHANGED:-0}"
if [ "${ANALYSIS_ORCHESTRATOR_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Graph Writer
build_microservice "graph-writer" "${GRAPH_WRITER_CHANGED:-0}"
if [ "${GRAPH_WRITER_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Graph Query
build_microservice "graph-query" "${GRAPH_QUERY_CHANGED:-0}"
if [ "${GRAPH_QUERY_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Timeseries Writer
build_microservice "timeseries-writer" "${TIMESERIES_WRITER_CHANGED:-0}"
if [ "${TIMESERIES_WRITER_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Timeseries Query
build_microservice "timeseries-query" "${TIMESERIES_QUERY_CHANGED:-0}"
if [ "${TIMESERIES_QUERY_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Ingestion Service
build_microservice "ingestion-service" "${INGESTION_SERVICE_CHANGED:-0}"
if [ "${INGESTION_SERVICE_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Change Detection Worker - Special case: uses backend/Dockerfile.worker
if [ "${CHANGE_WORKER_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔨 Building: change-detection-worker"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Change Detection Worker uses backend codebase with special Dockerfile
    podman build --no-cache --rm=false \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-change-worker:$cmtHashShort \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-change-worker:latest \
        --build-arg environment=$environment \
        -f backend/Dockerfile.worker \
        .
    
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-change-worker:$cmtHashShort
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-change-worker:latest
    
    echo "✅ change-detection-worker build complete!"
    echo "##vso[task.setvariable variable=CHANGE_WORKER_BUILT;isOutput=true]true"
    echo "##vso[task.setvariable variable=CHANGE_WORKER_TAG;isOutput=true]$cmtHashShort"
    BUILT_COUNT=$((BUILT_COUNT + 1))
else
    echo "⏭️  Skipping change-detection-worker - No changes detected"
    echo "##vso[task.setvariable variable=CHANGE_WORKER_BUILT;isOutput=true]false"
    SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
fi

# Özet
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 BUILD SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Built: $BUILT_COUNT microservices"
echo "⏭️  Skipped: $SKIPPED_COUNT microservices"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $BUILT_COUNT -eq 0 ]; then
    echo "ℹ️  No microservices needed building"
fi

# ==============================================================================
# NOTE: Gadget OCI images are pulled directly from ghcr.io at runtime
# No mirroring needed - GADGET_REGISTRY is set to empty string in ConfigMap
# This ensures proper OCI image index (multi-arch) support
# ==============================================================================

echo ""
echo "🎉 Microservices build task completed!"
