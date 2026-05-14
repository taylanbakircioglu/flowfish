#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[DEPLOY] APPLICATION DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==============================================================================
# Load build info from artifact
# ==============================================================================
BUILD_INFO_LOADED=false

# Try multiple possible paths for build-info file
# Note: Artifact alias is "_Flowfish-CI-Pilot" in Release Pipeline
POSSIBLE_PATHS=(
    "$BUILD_INFO_FILE"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Internal/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Internal/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/drop/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish/build-info/build-info.env"
    "$(dirname "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}")/a/_Flowfish-CI-Internal/build-info/build-info.env"
    "$(dirname "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}")/a/_Flowfish-CI-Internal/drop/build-info/build-info.env"
    "$(dirname "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}")/a/_Flowfish-CI-Pilot/build-info/build-info.env"
    "$(dirname "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}")/a/_Flowfish-CI/build-info/build-info.env"
    "$(dirname "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}")/a/_Flowfish/build-info/build-info.env"
)

echo "[CHECK] Searching for build-info.env..."
for path in "${POSSIBLE_PATHS[@]}"; do
    if [ -n "$path" ] && [ -f "$path" ]; then
        echo "[INFO] Found build info at: $path"
        source "$path"
        BUILD_INFO_LOADED=true
        echo "[OK] Build info loaded successfully!"
        echo ""
        echo "[INFO] Build Info Contents:"
        cat "$path"
        echo ""
        break
    fi
done

# Fallback: search recursively under artifact directory
if [ "$BUILD_INFO_LOADED" != "true" ] && [ -d "${SYSTEM_ARTIFACTSDIRECTORY:-}" ]; then
    FOUND_FILE=$(find "${SYSTEM_ARTIFACTSDIRECTORY}" -name "build-info.env" -type f 2>/dev/null | head -1)
    if [ -n "$FOUND_FILE" ]; then
        echo "[INFO] Found build info via search: $FOUND_FILE"
        source "$FOUND_FILE"
        BUILD_INFO_LOADED=true
        echo "[OK] Build info loaded successfully!"
        echo ""
        echo "[INFO] Build Info Contents:"
        cat "$FOUND_FILE"
        echo ""
    fi
fi

if [ "$BUILD_INFO_LOADED" != "true" ]; then
    echo "[WARN] BUILD_INFO_FILE not found in any expected location"
    echo "    Searched paths:"
    for path in "${POSSIBLE_PATHS[@]}"; do
        echo "      - ${path:-'(empty)'}"
    done
    echo ""
    echo "    Listing artifact directory contents:"
    ls -laR "${SYSTEM_ARTIFACTSDIRECTORY:-/tmp}" 2>/dev/null | head -80 || echo "    (could not list)"
    echo ""
    echo "    Will determine deployment based on manifest content"
fi

# Get commit hash
if [ -n "$BUILD_COMMIT" ]; then
    cmtHashShort="$BUILD_COMMIT"
elif [ -n "$RELEASE_ARTIFACTS__FLOWFISH_CI_SOURCEVERSION" ]; then
    cmtHashShort=$(echo $RELEASE_ARTIFACTS__FLOWFISH_CI_SOURCEVERSION | cut -c1-7)
elif [ -n "$BUILD_SOURCEVERSION" ]; then
    cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
else
    cmtHashShort="unknown"
fi

MANIFEST_DIR="${MANIFEST_DIR:-${BUILD_ARTIFACTSTAGINGDIRECTORY:-/tmp}/manifests}"

echo ""
echo "[INFO] Deployment Configuration:"
echo "   Commit: $cmtHashShort"
echo "   Namespace: ${OPENSHIFT_NAMESPACE}"
echo "   Manifest Dir: $MANIFEST_DIR"
echo "   BACKEND_BUILT: ${BACKEND_BUILT:-false}"
echo "   FRONTEND_BUILT: ${FRONTEND_BUILT:-false}"
echo ""

# ==============================================================================
# OpenShift Login
# ==============================================================================
echo "[AUTH] Logging into OpenShift..."
oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${OPENSHIFT_PASSWORD} --insecure-skip-tls-verify=true
oc project ${OPENSHIFT_NAMESPACE}
echo "[OK] OpenShift login successful"
echo ""

cd $MANIFEST_DIR

# ==============================================================================
# Helper Functions
# ==============================================================================

# Get current image tag from a deployment
# Tries the given container_name first, falls back to first container
get_current_image_tag() {
    local deployment_name="$1"
    local container_name="$2"
    
    # Try specific container name
    local current_image=$(oc get deployment "$deployment_name" -n "${OPENSHIFT_NAMESPACE}" \
        -o jsonpath="{.spec.template.spec.containers[?(@.name=='$container_name')].image}" 2>/dev/null || echo "")
    
    # Fallback: get first container's image if specific name didn't match
    if [ -z "$current_image" ]; then
        current_image=$(oc get deployment "$deployment_name" -n "${OPENSHIFT_NAMESPACE}" \
            -o jsonpath="{.spec.template.spec.containers[0].image}" 2>/dev/null || echo "")
    fi
    
    if [ -n "$current_image" ]; then
        local tag="${current_image##*:}"
        if [ -n "$tag" ] && [ "$tag" != "latest" ] && [[ ! "$tag" =~ ^NOT_ ]]; then
            echo "$tag"
            return 0
        fi
    fi
    echo ""
    return 1
}

# Get last known working tag from deployment history (rollout history)
get_last_working_tag() {
    local deployment_name="$1"
    local container_name="$2"
    
    # Get the previous revision's image (revision before current)
    local history=$(oc rollout history deployment/$deployment_name -n "${OPENSHIFT_NAMESPACE}" 2>/dev/null || echo "")
    
    # Try to get tag from a running pod (if any pods are actually running)
    local running_pod=$(oc get pods -n "${OPENSHIFT_NAMESPACE}" -l app=$deployment_name \
        --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[0].image}' 2>/dev/null || echo "")
    
    if [ -n "$running_pod" ]; then
        local tag="${running_pod##*:}"
        if [ -n "$tag" ] && [ "$tag" != "latest" ]; then
            echo "$tag"
            return 0
        fi
    fi
    
    echo ""
    return 1
}

# Verify if an image tag is usable (not in error state)
verify_image_exists() {
    local deployment_name="$1"
    local tag="$2"
    
    # Check pod status for the deployment
    local pod_statuses=$(oc get pods -n "${OPENSHIFT_NAMESPACE}" -l app=$deployment_name \
        -o jsonpath='{range .items[*]}{.status.containerStatuses[*].state}{" "}{end}' 2>/dev/null || echo "")
    
    # Also check waiting reasons
    local waiting_reasons=$(oc get pods -n "${OPENSHIFT_NAMESPACE}" -l app=$deployment_name \
        -o jsonpath='{range .items[*]}{.status.containerStatuses[*].state.waiting.reason}{" "}{end}' 2>/dev/null || echo "")
    
    # If pods are in ImagePullBackOff or ErrImagePull, the tag is bad
    if echo "$waiting_reasons" | grep -qE "ImagePullBackOff|ErrImagePull" 2>/dev/null; then
        return 1
    fi
    
    # If tag contains placeholder markers, it's definitely bad
    if [[ "$tag" =~ (NOT_BUILT|NEEDS_CLUSTER_TAG|unknown|IMAGE_TAG) ]]; then
        return 1
    fi
    
    return 0
}

# Check if manifest has a valid image tag (not a placeholder or error marker)
manifest_has_valid_tag() {
    local manifest_file="$1"
    
    if [ ! -f "$manifest_file" ]; then
        return 1
    fi
    
    # Check for placeholder or error markers
    if grep -qE "{{IMAGE_TAG}}|NOT_BUILT|:unknown|NEEDS_CLUSTER_TAG" "$manifest_file" 2>/dev/null; then
        return 1
    fi
    
    return 0
}

# Fix manifest image tag if needed (use current cluster tag for non-built services)
# $1: manifest_file  $2: deployment_name  $3: container_name
# $4: built_flag      $5: image_short_name (e.g. "change-worker" for flowfish-change-worker)
fix_manifest_if_needed() {
    local manifest_file="$1"
    local deployment_name="$2"
    local container_name="$3"
    local built_flag="$4"
    local image_short_name="${5:-$deployment_name}"
    
    if [ ! -f "$manifest_file" ]; then
        return 0
    fi
    
    # Get the tag currently in the manifest using the actual image name
    local manifest_tag=$(grep -oP "flowfish-${image_short_name}:\K[^\s\"']+" "$manifest_file" 2>/dev/null | head -1 || echo "")
    
    # If service was NOT built, we MUST use a working tag
    if [ "${built_flag}" != "true" ]; then
        echo "  [CHECK] Service not rebuilt, finding a working image tag..."
        
        # First, check if current cluster tag is actually working
        local current_tag=$(get_current_image_tag "$deployment_name" "$container_name")
        local use_tag=""
        
        if [ -n "$current_tag" ]; then
            # Verify if this tag is actually working (not in ImagePullBackOff)
            if verify_image_exists "$deployment_name" "$current_tag"; then
                use_tag="$current_tag"
                echo "  [OK] Current cluster tag '$current_tag' is valid"
            else
                echo "  [WARN] Current cluster tag '$current_tag' is NOT working (ImagePullBackOff)"
                # Try to get last working tag from running pods
                local working_tag=$(get_last_working_tag "$deployment_name" "$container_name")
                if [ -n "$working_tag" ]; then
                    use_tag="$working_tag"
                    echo "  [RESTART] Found working tag from history: $working_tag"
                fi
            fi
        fi
        
        # If no cluster tag found, this may be a first-time deployment.
        # Check if the manifest already has a valid tag (set by prepare-manifests).
        if [ -z "$use_tag" ]; then
            if [ -n "$manifest_tag" ] && [[ ! "$manifest_tag" =~ (NOT_BUILT|unknown|IMAGE_TAG|NEEDS_CLUSTER_TAG) ]]; then
                echo "  [INFO] No existing deployment found. Using manifest tag '$manifest_tag' (first-time deploy)"
                use_tag="$manifest_tag"
            else
                echo "  [WARN] No working tag found for $deployment_name - SKIPPING deployment"
                echo "     (Service will keep running with current image)"
                return 0
            fi
        fi
        
        if [ "$use_tag" != "$manifest_tag" ]; then
            echo "  [BUILD] Fixing $manifest_file: $manifest_tag -> $use_tag"
            sed -i -E "s|(image:.*flowfish-${image_short_name}:)[^[:space:]]+|\1${use_tag}|g" "$manifest_file"
        fi
        return 0
    fi
    
    # Check for obviously invalid tags (including NEEDS_CLUSTER_TAG from prepare-manifests)
    if grep -qE "NOT_BUILT|:unknown|{{IMAGE_TAG}}|NEEDS_CLUSTER_TAG" "$manifest_file" 2>/dev/null; then
        echo "  [BUILD] Fixing invalid tag in $manifest_file..."
        local current_tag=$(get_current_image_tag "$deployment_name" "$container_name")
        if [ -n "$current_tag" ]; then
            if verify_image_exists "$deployment_name" "$current_tag"; then
                sed -i -E "s|(image:.*flowfish-${image_short_name}:)[^[:space:]]+|\1${current_tag}|g" "$manifest_file"
                echo "     -> Using cluster tag: $current_tag"
            else
                echo "     [WARN] Cluster tag '$current_tag' not found in registry - SKIPPING"
                return 0
            fi
        else
            echo "     [WARN] No valid tag found - SKIPPING deployment"
            return 0
        fi
    fi
    
    return 0
}

# Deploy a service
# $1: display name  $2: manifest file  $3: built flag  $4: deployment name
# $5: container name (defaults to $4)  $6: image short name (defaults to $4)
deploy_service() {
    local service_name="$1"
    local manifest_file="$2"
    local built_flag="$3"
    local deployment_name="${4:-$service_name}"
    local container_name="${5:-$deployment_name}"
    local image_short_name="${6:-$deployment_name}"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[INFO] Processing $service_name..."
    
    if [ ! -f "$manifest_file" ]; then
        echo "[WARN] Manifest not found: $manifest_file - Skipping $service_name"
        return 0
    fi
    
    # CRITICAL: Fix manifest if service was not built (use cluster's current tag)
    fix_manifest_if_needed "$manifest_file" "$deployment_name" "$container_name" "$built_flag" "$image_short_name"
    
    # Verify manifest has valid tag
    if ! manifest_has_valid_tag "$manifest_file"; then
        echo "[WARN] $service_name has invalid image tag - Skipping to prevent deployment failure"
        return 0
    fi
    
    # Extract image tag from manifest for logging
    local image_tag=$(grep -oP "flowfish-${image_short_name}:\K[^\s\"']+" "$manifest_file" 2>/dev/null | head -1 || echo "unknown")
    
    if [ "${built_flag}" = "true" ]; then
        echo "[BUILD] Deploying $service_name (NEW BUILD)"
        echo "[INFO] Image Tag: $image_tag"
    else
        echo "[RESTART] Deploying $service_name (existing image from cluster)"
        echo "[INFO] Image Tag: $image_tag"
    fi
    
    # Apply manifest
    oc apply -f "$manifest_file"
    
    # Wait for rollout if it's a deployment
    if grep -q "kind: Deployment" "$manifest_file" 2>/dev/null; then
        echo "Waiting for $deployment_name rollout..."
        if oc rollout status deployment/$deployment_name -n ${OPENSHIFT_NAMESPACE} --timeout=300s; then
            echo "[OK] $service_name deployed successfully!"
else
            echo "[WARN] $service_name rollout timed out or failed"
            # Don't fail the entire deployment - continue with other services
        fi
    else
        echo "[OK] $service_name applied!"
    fi
    
echo ""
}

# ==============================================================================
# Deploy Applications
# ==============================================================================

# Deploy Backend
deploy_service "Backend" "08-backend.yaml" "${BACKEND_BUILT:-false}" "backend"

# Deploy Frontend
deploy_service "Frontend" "09-frontend.yaml" "${FRONTEND_BUILT:-false}" "frontend"

# ==============================================================================
# Deploy Microservices
# ==============================================================================

# Deploy API Gateway
deploy_service "API Gateway" "14-api-gateway.yaml" "${API_GATEWAY_BUILT:-false}" "api-gateway"

# Deploy Cluster Manager
deploy_service "Cluster Manager" "12-cluster-manager.yaml" "${CLUSTER_MANAGER_BUILT:-false}" "cluster-manager"

# Deploy Analysis Orchestrator
deploy_service "Analysis Orchestrator" "13-analysis-orchestrator.yaml" "${ANALYSIS_ORCHESTRATOR_BUILT:-false}" "analysis-orchestrator"

# Deploy Graph Writer
deploy_service "Graph Writer" "15-graph-writer.yaml" "${GRAPH_WRITER_BUILT:-false}" "graph-writer"

# Deploy Graph Query
deploy_service "Graph Query" "16-graph-query.yaml" "${GRAPH_QUERY_BUILT:-false}" "graph-query"

# Deploy Timeseries Writer
deploy_service "Timeseries Writer" "11-timeseries-writer.yaml" "${TIMESERIES_WRITER_BUILT:-false}" "timeseries-writer"

# Deploy Timeseries Query
deploy_service "Timeseries Query" "17-timeseries-query.yaml" "${TIMESERIES_QUERY_BUILT:-false}" "timeseries-query"

# Deploy Ingestion Service
deploy_service "Ingestion Service" "10-ingestion-service.yaml" "${INGESTION_SERVICE_BUILT:-false}" "ingestion-service"

# Deploy Change Detection Worker (if manifest exists)
# container name is "worker", image name is "flowfish-change-worker"
if [ -f "18-change-detection-worker.yaml" ]; then
    deploy_service "Change Worker" "18-change-detection-worker.yaml" "${CHANGE_WORKER_BUILT:-false}" "change-detection-worker" "worker" "change-worker"
fi

# Deploy L7 Ingestion Service (if manifest exists)
if [ -f "22-l7-ingestion-service.yaml" ]; then
    deploy_service "L7 Ingestion Service" "22-l7-ingestion-service.yaml" "${L7_INGESTION_SERVICE_BUILT:-false}" "l7-ingestion-service"
fi

# Deploy Flowfish L7 Collector (if manifest exists)
if [ -f "21-flowfish-l7-collector.yaml" ]; then
    deploy_service "L7 Collector" "21-flowfish-l7-collector.yaml" "${L7_COLLECTOR_BUILT:-false}" "flowfish-l7-collector" "l7-collector" "l7-collector"
fi

# ==============================================================================
# Apply Ingress/Routes (if not already configured)
# ==============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[NET] Checking Ingress/Routes..."

# Check if route already exists (OpenShift manages routes, not Ingress)
existing_route=$(oc get route flowfish -n ${OPENSHIFT_NAMESPACE} -o name 2>/dev/null || echo "")
if [ -n "$existing_route" ]; then
    echo "[OK] Route already exists - skipping ingress apply"
    oc get route flowfish -n ${OPENSHIFT_NAMESPACE} -o wide 2>/dev/null || true
else
    echo "[WARN] No existing route found. Route should be created via OpenShift console or separate manifest."
    echo "   (11-ingress.yaml contains placeholders that need to be replaced)"
fi
echo ""

# ==============================================================================
# Deployment Summary
# ==============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "[SUMMARY] DEPLOYMENT SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "[INFO] Current Deployments:"
oc get deployments -n ${OPENSHIFT_NAMESPACE} -o wide 2>/dev/null || true

echo ""
echo "[NET] Routes:"
oc get routes -n ${OPENSHIFT_NAMESPACE} 2>/dev/null || true

echo ""
echo "[DONE] Application deployment completed!"
