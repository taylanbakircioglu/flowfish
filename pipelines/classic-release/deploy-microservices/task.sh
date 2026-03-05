#!/bin/bash
set -e

# ==============================================================================
# Flowfish Microservices Deploy - Incremental Deployment
# ==============================================================================
# Bu script sadece yeni build edilen microservices'leri deploy eder.
# Build bilgilerini build-info.env artifact'ından okur.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 MICROSERVICES INCREMENTAL DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==============================================================================
# Load build info from artifact
# ==============================================================================
echo "🔍 Searching for build-info.env..."

# Try multiple possible paths for build-info.env
POSSIBLE_BUILD_INFO_PATHS=(
    "$BUILD_INFO_FILE"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish/build-info/build-info.env"
    "${BUILD_ARTIFACTSTAGINGDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${BUILD_ARTIFACTSTAGINGDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
)

BUILD_INFO_FOUND=""
for path in "${POSSIBLE_BUILD_INFO_PATHS[@]}"; do
    if [ -n "$path" ] && [ -f "$path" ]; then
        BUILD_INFO_FOUND="$path"
        break
    fi
done

if [ -n "$BUILD_INFO_FOUND" ]; then
    echo "📦 Found build info at: $BUILD_INFO_FOUND"
    source "$BUILD_INFO_FOUND"
    echo "✅ Build info loaded successfully!"
    echo ""
    echo "📋 Service Build Status:"
    echo "   API_GATEWAY_BUILT: ${API_GATEWAY_BUILT:-false} (Tag: ${API_GATEWAY_TAG:-none})"
    echo "   CLUSTER_MANAGER_BUILT: ${CLUSTER_MANAGER_BUILT:-false} (Tag: ${CLUSTER_MANAGER_TAG:-none})"
    echo "   ANALYSIS_ORCHESTRATOR_BUILT: ${ANALYSIS_ORCHESTRATOR_BUILT:-false} (Tag: ${ANALYSIS_ORCHESTRATOR_TAG:-none})"
    echo "   GRAPH_WRITER_BUILT: ${GRAPH_WRITER_BUILT:-false} (Tag: ${GRAPH_WRITER_TAG:-none})"
    echo "   GRAPH_QUERY_BUILT: ${GRAPH_QUERY_BUILT:-false} (Tag: ${GRAPH_QUERY_TAG:-none})"
    echo "   TIMESERIES_WRITER_BUILT: ${TIMESERIES_WRITER_BUILT:-false} (Tag: ${TIMESERIES_WRITER_TAG:-none})"
    echo "   TIMESERIES_QUERY_BUILT: ${TIMESERIES_QUERY_BUILT:-false} (Tag: ${TIMESERIES_QUERY_TAG:-none})"
    echo "   INGESTION_SERVICE_BUILT: ${INGESTION_SERVICE_BUILT:-false} (Tag: ${INGESTION_SERVICE_TAG:-none})"
    echo "   CHANGE_WORKER_BUILT: ${CHANGE_WORKER_BUILT:-false} (Tag: ${CHANGE_WORKER_TAG:-none})"
else
    echo "⚠️  BUILD_INFO_FILE not found in any expected location"
    echo "    Searched paths:"
    for path in "${POSSIBLE_BUILD_INFO_PATHS[@]}"; do
        [ -n "$path" ] && echo "      - $path"
    done
    echo ""
    echo "    Listing artifact directory contents:"
    ls -la "${SYSTEM_ARTIFACTSDIRECTORY}/" 2>/dev/null || ls -la "${BUILD_ARTIFACTSTAGINGDIRECTORY}/" 2>/dev/null || echo "    (could not list)"
    echo ""
    echo "    Will use environment variables directly (all services will likely be skipped)"
fi

MANIFEST_DIR="${BUILD_ARTIFACTSTAGINGDIRECTORY}/manifests"

if [ ! -d "$MANIFEST_DIR" ]; then
    echo "❌ ERROR: Manifests directory not found: $MANIFEST_DIR"
    exit 1
fi

cd $MANIFEST_DIR

# OpenShift'e login
echo "🔐 Logging into OpenShift..."
oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${OPENSHIFT_PASSWORD} --insecure-skip-tls-verify=true
oc project ${OPENSHIFT_NAMESPACE}

echo ""
echo "📋 Deployment Configuration:"
echo "   Namespace: ${OPENSHIFT_NAMESPACE}"
echo "   RELEASE_ALL: ${RELEASE_ALL:-false}"
echo ""

# Counter
DEPLOYED_COUNT=0
SKIPPED_COUNT=0
RESTARTED_COUNT=0

# ==============================================================================
# ConfigMap Change Detection - Restart pods if config changed
# ==============================================================================
echo ""
echo "🔍 Checking for ConfigMap changes..."

# Function to get ConfigMap data checksum (only .data field, not metadata/status)
# This avoids false positives from OpenShift-added fields
get_configmap_data_checksum() {
    local cm_name=$1
    oc get configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data}' 2>/dev/null | md5sum | cut -d' ' -f1 || echo "none"
}

# Function to get stored checksum from ConfigMap annotation
get_stored_checksum() {
    local cm_name=$1
    oc get configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.metadata.annotations.flowfish\.io/data-checksum}' 2>/dev/null || echo ""
}

# Function to store checksum as ConfigMap annotation
store_checksum() {
    local cm_name=$1
    local checksum=$2
    oc annotate configmap "$cm_name" -n ${OPENSHIFT_NAMESPACE} "flowfish.io/data-checksum=$checksum" --overwrite 2>/dev/null || true
}

# Track which deployments need restart due to ConfigMap changes
declare -A CONFIGMAP_RESTART

# Check backend-config - affects most microservices
BACKEND_CONFIG_CHECKSUM=$(get_configmap_data_checksum "backend-config")
OLD_CHECKSUM=$(get_stored_checksum "backend-config")

echo "  📊 backend-config checksum: $BACKEND_CONFIG_CHECKSUM"
echo "  📊 stored checksum: ${OLD_CHECKSUM:-<none>}"

if [ -n "$OLD_CHECKSUM" ] && [ "$OLD_CHECKSUM" != "$BACKEND_CONFIG_CHECKSUM" ]; then
    echo "  📝 backend-config CHANGED - marking services for restart"
    CONFIGMAP_RESTART["api-gateway"]=1
    CONFIGMAP_RESTART["cluster-manager"]=1
    CONFIGMAP_RESTART["analysis-orchestrator"]=1
    CONFIGMAP_RESTART["ingestion-service"]=1
    CONFIGMAP_RESTART["timeseries-writer"]=1
    CONFIGMAP_RESTART["timeseries-query"]=1
    CONFIGMAP_RESTART["graph-writer"]=1
    CONFIGMAP_RESTART["graph-query"]=1
    CONFIGMAP_RESTART["change-detection-worker"]=1
elif [ -z "$OLD_CHECKSUM" ]; then
    echo "  ℹ️  No stored checksum found (first run), storing current checksum"
else
    echo "  ✅ backend-config unchanged"
fi

# Store current checksum for next run
store_checksum "backend-config" "$BACKEND_CONFIG_CHECKSUM"

# ==============================================================================
# Secret Change Detection - Restart pods if secrets changed
# ==============================================================================
echo ""
echo "🔍 Checking for Secret changes..."

# Function to get Secret data checksum (only .data field)
get_secret_data_checksum() {
    local secret_name=$1
    oc get secret "$secret_name" -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data}' 2>/dev/null | md5sum | cut -d' ' -f1 || echo "none"
}

# Function to get stored secret checksum from ConfigMap
get_stored_secret_checksum() {
    local secret_name=$1
    oc get configmap "flowfish-checksums" -n ${OPENSHIFT_NAMESPACE} -o jsonpath="{.data.$secret_name}" 2>/dev/null || echo ""
}

# Function to store secret checksum
store_secret_checksum() {
    local secret_name=$1
    local checksum=$2
    # Ensure checksum ConfigMap exists
    if ! oc get configmap "flowfish-checksums" -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
        oc create configmap "flowfish-checksums" -n ${OPENSHIFT_NAMESPACE} --from-literal="init=true" 2>/dev/null || true
    fi
    oc patch configmap "flowfish-checksums" -n ${OPENSHIFT_NAMESPACE} -p "{\"data\":{\"$secret_name\":\"$checksum\"}}" 2>/dev/null || true
}

# Check flowfish-secrets - affects all microservices
SECRETS_CHECKSUM=$(get_secret_data_checksum "flowfish-secrets")
OLD_SECRET_CHECKSUM=$(get_stored_secret_checksum "flowfish-secrets")

echo "  🔐 flowfish-secrets checksum: $SECRETS_CHECKSUM"
echo "  🔐 stored checksum: ${OLD_SECRET_CHECKSUM:-<none>}"

if [ -n "$OLD_SECRET_CHECKSUM" ] && [ "$OLD_SECRET_CHECKSUM" != "$SECRETS_CHECKSUM" ]; then
    echo "  📝 flowfish-secrets CHANGED - marking services for restart"
    CONFIGMAP_RESTART["api-gateway"]=1
    CONFIGMAP_RESTART["cluster-manager"]=1
    CONFIGMAP_RESTART["analysis-orchestrator"]=1
    CONFIGMAP_RESTART["ingestion-service"]=1
    CONFIGMAP_RESTART["timeseries-writer"]=1
    CONFIGMAP_RESTART["timeseries-query"]=1
    CONFIGMAP_RESTART["graph-writer"]=1
    CONFIGMAP_RESTART["graph-query"]=1
    CONFIGMAP_RESTART["change-detection-worker"]=1
    CONFIGMAP_RESTART["backend"]=1
elif [ -z "$OLD_SECRET_CHECKSUM" ]; then
    echo "  ℹ️  No stored secret checksum found (first run), storing current checksum"
else
    echo "  ✅ flowfish-secrets unchanged"
fi

# Store current secret checksum for next run
store_secret_checksum "flowfish-secrets" "$SECRETS_CHECKSUM"

# Deployment fonksiyonu
deploy_microservice() {
    local service_name="$1"
    local manifest_file="$2"
    local built_flag="${3:-false}"
    local image_tag="$4"
    local deployment_name="$5"
    
    # Deployment logic:
    # 1. Service built (new image) → Apply manifest with new image tag
    # 2. ConfigMap changed (no new image) → Just restart pods with current image
    # 3. Nothing changed → Skip
    
    local should_deploy=false
    local should_restart=false
    local deploy_reason=""
    
    # Check if new image was built
    if [ "${built_flag:-false}" = "true" ]; then
        should_deploy=true
        deploy_reason="new build"
    fi
    
    # Check if ConfigMap changed (only restart, don't redeploy with potentially non-existent image)
    if [ "${CONFIGMAP_RESTART[$deployment_name]:-0}" = "1" ] && [ "$should_deploy" = "false" ]; then
        should_restart=true
        deploy_reason="ConfigMap changed"
    fi
    
    if [ "$should_deploy" = "true" ]; then
        # New image built - apply manifest with new image tag
        if [ -f "$manifest_file" ]; then
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "🚀 Deploying: $service_name ($deploy_reason)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            
            if [ -n "$image_tag" ]; then
                echo "📌 Image Tag: $image_tag"
            fi
            
            oc apply -f "$manifest_file"
            
            local DEPLOY_NAME=$(grep -A 1 "kind: Deployment" "$manifest_file" 2>/dev/null | grep "name:" | head -1 | awk '{print $2}' || echo "")
            
            if [ -n "$DEPLOY_NAME" ]; then
                echo "⏳ Waiting for rollout: $DEPLOY_NAME"
                oc rollout status deployment/$DEPLOY_NAME -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
            fi
            
            echo "✅ $service_name deployed!"
            DEPLOYED_COUNT=$((DEPLOYED_COUNT + 1))
        else
            echo "⚠️  WARNING: Manifest not found: $manifest_file"
        fi
        return 0
        
    elif [ "$should_restart" = "true" ]; then
        # ConfigMap changed - restart pods with CURRENT image (don't apply new manifest)
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🔄 Restarting: $service_name ($deploy_reason)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        if oc get deployment "$deployment_name" -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
            oc rollout restart deployment/"$deployment_name" -n ${OPENSHIFT_NAMESPACE}
            oc rollout status deployment/"$deployment_name" -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
            echo "✅ $service_name restarted!"
            RESTARTED_COUNT=$((RESTARTED_COUNT + 1))
        else
            echo "⚠️  Deployment $deployment_name not found, skipping restart"
        fi
        return 0
        
    else
        # Nothing changed - skip
        echo "⏭️  Skipping $service_name - No changes"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        return 0
    fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Starting Microservices Deployment..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Deploy microservices - sıralı olarak
# Parameters: "Display Name" "manifest.yaml" "BUILT_FLAG" "IMAGE_TAG" "deployment-name"
deploy_microservice "API Gateway" "14-api-gateway.yaml" "${API_GATEWAY_BUILT:-false}" "${API_GATEWAY_TAG}" "api-gateway"
deploy_microservice "Cluster Manager" "12-cluster-manager.yaml" "${CLUSTER_MANAGER_BUILT:-false}" "${CLUSTER_MANAGER_TAG}" "cluster-manager"
deploy_microservice "Ingestion Service" "10-ingestion-service.yaml" "${INGESTION_SERVICE_BUILT:-false}" "${INGESTION_SERVICE_TAG}" "ingestion-service"
deploy_microservice "Timeseries Writer" "11-timeseries-writer.yaml" "${TIMESERIES_WRITER_BUILT:-false}" "${TIMESERIES_WRITER_TAG}" "timeseries-writer"
deploy_microservice "Timeseries Query" "17-timeseries-query.yaml" "${TIMESERIES_QUERY_BUILT:-false}" "${TIMESERIES_QUERY_TAG}" "timeseries-query"
deploy_microservice "Graph Writer" "15-graph-writer.yaml" "${GRAPH_WRITER_BUILT:-false}" "${GRAPH_WRITER_TAG}" "graph-writer"
deploy_microservice "Graph Query" "16-graph-query.yaml" "${GRAPH_QUERY_BUILT:-false}" "${GRAPH_QUERY_TAG}" "graph-query"
deploy_microservice "Analysis Orchestrator" "13-analysis-orchestrator.yaml" "${ANALYSIS_ORCHESTRATOR_BUILT:-false}" "${ANALYSIS_ORCHESTRATOR_TAG}" "analysis-orchestrator"
deploy_microservice "Change Detection Worker" "18-change-detection-worker.yaml" "${CHANGE_WORKER_BUILT:-false}" "${CHANGE_WORKER_TAG}" "change-detection-worker"

# Özet
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 DEPLOYMENT SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployed:  $DEPLOYED_COUNT microservices"
echo "🔄 Restarted: $RESTARTED_COUNT microservices (ConfigMap change)"
echo "⏭️  Skipped:   $SKIPPED_COUNT microservices"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $DEPLOYED_COUNT -eq 0 ] && [ $RESTARTED_COUNT -eq 0 ]; then
    echo "ℹ️  No microservices needed deployment or restart"
fi

# Final status
echo ""
echo "📋 Microservices Status:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -l tier=microservices 2>/dev/null || true

echo ""
echo "🎉 Microservices deployment task completed!"
