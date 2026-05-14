#!/bin/bash
set -e

# ==============================================================================
# Flowfish Microservices Deploy - Incremental Deployment
# ==============================================================================
# Bu script sadece yeni build edilen microservices'leri deploy eder.
# Build bilgilerini build-info.env artifact'ından okur.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[DEPLOY] MICROSERVICES INCREMENTAL DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==============================================================================
# Load build info from artifact
# ==============================================================================
echo "[CHECK] Searching for build-info.env..."

# Try multiple possible paths for build-info.env
POSSIBLE_BUILD_INFO_PATHS=(
    "$BUILD_INFO_FILE"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Internal/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Internal/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish/build-info/build-info.env"
    "${BUILD_ARTIFACTSTAGINGDIRECTORY}/_Flowfish-CI-Internal/build-info/build-info.env"
    "${BUILD_ARTIFACTSTAGINGDIRECTORY}/_Flowfish-CI-Internal/drop/build-info/build-info.env"
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

# Fallback: search recursively under artifact directory
if [ -z "$BUILD_INFO_FOUND" ] && [ -d "${SYSTEM_ARTIFACTSDIRECTORY:-}" ]; then
    BUILD_INFO_FOUND=$(find "${SYSTEM_ARTIFACTSDIRECTORY}" -name "build-info.env" -type f 2>/dev/null | head -1)
    if [ -n "$BUILD_INFO_FOUND" ]; then
        echo "[INFO] Found build info via search: $BUILD_INFO_FOUND"
    fi
fi

if [ -n "$BUILD_INFO_FOUND" ]; then
    echo "[INFO] Found build info at: $BUILD_INFO_FOUND"
    source "$BUILD_INFO_FOUND"
    echo "[OK] Build info loaded successfully!"
    echo ""
    echo "[INFO] Service Build Status:"
    echo "   API_GATEWAY_BUILT: ${API_GATEWAY_BUILT:-false} (Tag: ${API_GATEWAY_TAG:-none})"
    echo "   CLUSTER_MANAGER_BUILT: ${CLUSTER_MANAGER_BUILT:-false} (Tag: ${CLUSTER_MANAGER_TAG:-none})"
    echo "   ANALYSIS_ORCHESTRATOR_BUILT: ${ANALYSIS_ORCHESTRATOR_BUILT:-false} (Tag: ${ANALYSIS_ORCHESTRATOR_TAG:-none})"
    echo "   GRAPH_WRITER_BUILT: ${GRAPH_WRITER_BUILT:-false} (Tag: ${GRAPH_WRITER_TAG:-none})"
    echo "   GRAPH_QUERY_BUILT: ${GRAPH_QUERY_BUILT:-false} (Tag: ${GRAPH_QUERY_TAG:-none})"
    echo "   TIMESERIES_WRITER_BUILT: ${TIMESERIES_WRITER_BUILT:-false} (Tag: ${TIMESERIES_WRITER_TAG:-none})"
    echo "   TIMESERIES_QUERY_BUILT: ${TIMESERIES_QUERY_BUILT:-false} (Tag: ${TIMESERIES_QUERY_TAG:-none})"
    echo "   INGESTION_SERVICE_BUILT: ${INGESTION_SERVICE_BUILT:-false} (Tag: ${INGESTION_SERVICE_TAG:-none})"
    echo "   L7_INGESTION_SERVICE_BUILT: ${L7_INGESTION_SERVICE_BUILT:-false} (Tag: ${L7_INGESTION_SERVICE_TAG:-none})"
    echo "   L7_COLLECTOR_BUILT: ${L7_COLLECTOR_BUILT:-false} (Tag: ${L7_COLLECTOR_TAG:-none})"
    echo "   CHANGE_WORKER_BUILT: ${CHANGE_WORKER_BUILT:-false} (Tag: ${CHANGE_WORKER_TAG:-none})"
else
    echo "[WARN] BUILD_INFO_FILE not found in any expected location"
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
    echo "[ERROR] ERROR: Manifests directory not found: $MANIFEST_DIR"
    exit 1
fi

cd $MANIFEST_DIR

# OpenShift'e login
echo "[AUTH] Logging into OpenShift..."
oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${OPENSHIFT_PASSWORD} --insecure-skip-tls-verify=true
oc project ${OPENSHIFT_NAMESPACE}

echo ""
echo "[INFO] Deployment Configuration:"
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
echo "[CHECK] Checking for ConfigMap changes..."

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

echo "  [SUMMARY] backend-config checksum: $BACKEND_CONFIG_CHECKSUM"
echo "  [SUMMARY] stored checksum: ${OLD_CHECKSUM:-<none>}"

if [ -n "$OLD_CHECKSUM" ] && [ "$OLD_CHECKSUM" != "$BACKEND_CONFIG_CHECKSUM" ]; then
    echo "  [NOTE] backend-config CHANGED - marking services for restart"
    CONFIGMAP_RESTART["api-gateway"]=1
    CONFIGMAP_RESTART["cluster-manager"]=1
    CONFIGMAP_RESTART["analysis-orchestrator"]=1
    CONFIGMAP_RESTART["ingestion-service"]=1
    CONFIGMAP_RESTART["timeseries-writer"]=1
    CONFIGMAP_RESTART["timeseries-query"]=1
    CONFIGMAP_RESTART["graph-writer"]=1
    CONFIGMAP_RESTART["graph-query"]=1
    CONFIGMAP_RESTART["change-detection-worker"]=1
    CONFIGMAP_RESTART["l7-ingestion-service"]=1
    CONFIGMAP_RESTART["flowfish-l7-collector"]=1
elif [ -z "$OLD_CHECKSUM" ]; then
    echo "  [INFO] No stored checksum found (first run), storing current checksum"
else
    echo "  [OK] backend-config unchanged"
fi

# Store current checksum for next run
store_checksum "backend-config" "$BACKEND_CONFIG_CHECKSUM"

# ==============================================================================
# Secret Change Detection - Restart pods if secrets changed
# ==============================================================================
echo ""
echo "[CHECK] Checking for Secret changes..."

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

echo "  [AUTH] flowfish-secrets checksum: $SECRETS_CHECKSUM"
echo "  [AUTH] stored checksum: ${OLD_SECRET_CHECKSUM:-<none>}"

if [ -n "$OLD_SECRET_CHECKSUM" ] && [ "$OLD_SECRET_CHECKSUM" != "$SECRETS_CHECKSUM" ]; then
    echo "  [NOTE] flowfish-secrets CHANGED - marking services for restart"
    CONFIGMAP_RESTART["api-gateway"]=1
    CONFIGMAP_RESTART["cluster-manager"]=1
    CONFIGMAP_RESTART["analysis-orchestrator"]=1
    CONFIGMAP_RESTART["ingestion-service"]=1
    CONFIGMAP_RESTART["timeseries-writer"]=1
    CONFIGMAP_RESTART["timeseries-query"]=1
    CONFIGMAP_RESTART["graph-writer"]=1
    CONFIGMAP_RESTART["graph-query"]=1
    CONFIGMAP_RESTART["change-detection-worker"]=1
    CONFIGMAP_RESTART["l7-ingestion-service"]=1
    CONFIGMAP_RESTART["flowfish-l7-collector"]=1
    CONFIGMAP_RESTART["backend"]=1
elif [ -z "$OLD_SECRET_CHECKSUM" ]; then
    echo "  [INFO] No stored secret checksum found (first run), storing current checksum"
else
    echo "  [OK] flowfish-secrets unchanged"
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
            # Guard: check manifest doesn't contain placeholder tags
            if grep -qE "NEEDS_CLUSTER_TAG|NOT_BUILT|{{IMAGE_TAG}}" "$manifest_file" 2>/dev/null; then
                echo ""
                echo "[WARN] Skipping $service_name - manifest has placeholder image tag"
                SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                return 0
            fi
            
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "[DEPLOY] Deploying: $service_name ($deploy_reason)"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            
            if [ -n "$image_tag" ]; then
                echo "[INFO] Image Tag: $image_tag"
            fi
            
            oc apply -f "$manifest_file"
            
            local DEPLOY_NAME=$(grep -A 1 "kind: Deployment" "$manifest_file" 2>/dev/null | grep "name:" | head -1 | awk '{print $2}' || echo "")
            
            if [ -n "$DEPLOY_NAME" ]; then
                echo "Waiting for rollout: $DEPLOY_NAME"
                oc rollout status deployment/$DEPLOY_NAME -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
            fi
            
            echo "[OK] $service_name deployed!"
            DEPLOYED_COUNT=$((DEPLOYED_COUNT + 1))
        else
            echo "[WARN] WARNING: Manifest not found: $manifest_file"
        fi
        return 0
        
    elif [ "$should_restart" = "true" ]; then
        # ConfigMap changed - restart pods with CURRENT image (don't apply new manifest)
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "[RESTART] Restarting: $service_name ($deploy_reason)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        if oc get deployment "$deployment_name" -n ${OPENSHIFT_NAMESPACE} &>/dev/null; then
            oc rollout restart deployment/"$deployment_name" -n ${OPENSHIFT_NAMESPACE}
            oc rollout status deployment/"$deployment_name" -n ${OPENSHIFT_NAMESPACE} --timeout=5m || true
            echo "[OK] $service_name restarted!"
            RESTARTED_COUNT=$((RESTARTED_COUNT + 1))
        else
            echo "[WARN] Deployment $deployment_name not found, skipping restart"
        fi
        return 0
        
    else
        # Nothing changed - skip
        echo "[SKIP] Skipping $service_name - No changes"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        return 0
    fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[INFO] Starting Microservices Deployment..."
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
deploy_microservice "L7 Ingestion Service" "22-l7-ingestion-service.yaml" "${L7_INGESTION_SERVICE_BUILT:-false}" "${L7_INGESTION_SERVICE_TAG}" "l7-ingestion-service"
deploy_microservice "L7 Collector" "21-flowfish-l7-collector.yaml" "${L7_COLLECTOR_BUILT:-false}" "${L7_COLLECTOR_TAG}" "flowfish-l7-collector"

# Özet
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[SUMMARY] DEPLOYMENT SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[OK] Deployed:  $DEPLOYED_COUNT microservices"
echo "[RESTART] Restarted: $RESTARTED_COUNT microservices (ConfigMap change)"
echo "[SKIP] Skipped:   $SKIPPED_COUNT microservices"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $DEPLOYED_COUNT -eq 0 ] && [ $RESTARTED_COUNT -eq 0 ]; then
    echo "[INFO] No microservices needed deployment or restart"
fi

# Final status
echo ""
echo "[INFO] Microservices Status:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -l tier=microservices 2>/dev/null || true

echo ""
echo "[DONE] Microservices deployment task completed!"
