#!/bin/bash
set -e

echo "================================================"
echo "Preparing Kubernetes Manifests"
echo "================================================"

# ==============================================================================
# Load build info from artifact
# ==============================================================================
BUILD_INFO_LOADED=false

# Try multiple possible paths for build-info file
# Note: Artifact alias is "_Flowfish-CI-Pilot" in Release Pipeline
POSSIBLE_BUILD_INFO_PATHS=(
    "$BUILD_INFO_FILE"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_ARTIFACTSDIRECTORY}/Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_DEFAULTWORKINGDIRECTORY}/_Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_DEFAULTWORKINGDIRECTORY}/Flowfish-CI-Pilot/build-info/build-info.env"
    "${SYSTEM_DEFAULTWORKINGDIRECTORY}/_Flowfish-CI/build-info/build-info.env"
    "${SYSTEM_DEFAULTWORKINGDIRECTORY}/Flowfish-CI/build-info/build-info.env"
)

for path in "${POSSIBLE_BUILD_INFO_PATHS[@]}"; do
    if [ -n "$path" ] && [ -f "$path" ]; then
        echo "📦 Loading build info from: $path"
        source "$path"
        BUILD_INFO_LOADED=true
    echo "✅ Build info loaded successfully"
    echo ""
    echo "📋 Build Info Contents:"
        cat "$path"
    echo ""
        break
    fi
done

if [ "$BUILD_INFO_LOADED" != "true" ]; then
    echo "⚠️  BUILD_INFO_FILE not found in any expected location"
    echo "    Tried paths:"
    for path in "${POSSIBLE_BUILD_INFO_PATHS[@]}"; do
        echo "      - ${path:-'(empty)'}"
    done
    echo "    Will query cluster for current image tags"
fi

# Get commit hash - prefer BUILD_COMMIT from build-info.env
if [ -n "$BUILD_COMMIT" ]; then
    cmtHashShort="$BUILD_COMMIT"
    echo "📌 Using Build Commit from artifact: $cmtHashShort"
elif [ -n "$RELEASE_ARTIFACTS__FLOWFISH_CI_SOURCEVERSION" ]; then
    cmtHashShort=$(echo $RELEASE_ARTIFACTS__FLOWFISH_CI_SOURCEVERSION | cut -c1-7)
    echo "📌 Using Release Artifact Source Version: $cmtHashShort"
elif [ -n "$BUILD_SOURCEVERSION" ]; then
    cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
    echo "📌 Using BUILD_SOURCEVERSION: $cmtHashShort"
else
    cmtHashShort="unknown"
    echo "⚠️  No commit hash available"
fi

HARBOR_PROJECT="flowfish"

echo ""
echo "Commit Hash: $cmtHashShort"
echo "Environment: ${DEPLOYMENT_ENV}"
echo "Harbor Registry: ${HARBOR_REGISTRY}"
echo "Harbor Project: $HARBOR_PROJECT"

# ==============================================================================
# OpenShift Login - CRITICAL for incremental deployments
# ==============================================================================
OC_LOGIN_SUCCESS=false

echo ""
echo "🔐 Attempting OpenShift login..."

if [ -n "${OPENSHIFT_API_URL}" ] && [ -n "${OPENSHIFT_USER}" ] && [ -n "${OPENSHIFT_PASSWORD}" ]; then
    if oc login "${OPENSHIFT_API_URL}" -u "${OPENSHIFT_USER}" -p "${OPENSHIFT_PASSWORD}" --insecure-skip-tls-verify=true 2>&1; then
        if oc project "${OPENSHIFT_NAMESPACE}" 2>&1; then
            OC_LOGIN_SUCCESS=true
            echo "✅ OpenShift login successful"
        else
            echo "⚠️  Failed to switch to project ${OPENSHIFT_NAMESPACE}"
        fi
    else
        echo "⚠️  OpenShift login failed"
    fi
else
    echo "⚠️  OpenShift credentials not configured"
fi

# Create working directory for manifests
MANIFEST_DIR="${BUILD_ARTIFACTSTAGINGDIRECTORY:-/tmp}/manifests"
mkdir -p $MANIFEST_DIR

# Copy manifests to working directory
echo ""
echo "Copying manifests..."
cp -r ${BUILD_SOURCESDIRECTORY}/deployment/kubernetes-manifests/* $MANIFEST_DIR/

cd $MANIFEST_DIR

echo ""
echo "Replacing placeholders in manifests..."

# Replace image registry and tags
for manifest in *.yaml; do
  echo "Processing $manifest..."
  
  # Replace Harbor registry
  sed -i -e "s|{{HARBOR_REGISTRY}}|${HARBOR_REGISTRY}|g" $manifest
  
  # Replace Harbor project
  sed -i -e "s|{{HARBOR_PROJECT}}|${HARBOR_PROJECT}|g" $manifest
  
  # Replace environment
  sed -i -e "s|{{DEPLOYMENT_ENV}}|${DEPLOYMENT_ENV}|g" $manifest
  
  # Replace Gadget version
  if [ -n "${GADGET_VERSION}" ]; then
    sed -i -e "s|{{GADGET_VERSION}}|${GADGET_VERSION}|g" $manifest
  fi
done

# ==============================================================================
# Image Tag Resolution Functions
# ==============================================================================

# Get current image tag from cluster deployment
get_current_cluster_tag() {
    local deployment_name="$1"
    local container_name="$2"
    
    if [ "$OC_LOGIN_SUCCESS" != "true" ]; then
echo ""
        return 1
    fi
    
    local current_image=$(oc get deployment "$deployment_name" -n "${OPENSHIFT_NAMESPACE}" \
        -o jsonpath="{.spec.template.spec.containers[?(@.name=='$container_name')].image}" 2>/dev/null || echo "")
    
    if [ -n "$current_image" ]; then
        local tag="${current_image##*:}"
        # Ensure tag is valid (not empty, not 'latest', not a placeholder)
        if [ -n "$tag" ] && [ "$tag" != "latest" ] && [[ ! "$tag" =~ ^NOT_ ]] && [[ ! "$tag" =~ ^\{\{ ]]; then
            echo "$tag"
            return 0
        fi
    fi
    
    echo ""
    return 1
}

# Set image tag for a service manifest
set_service_image_tag() {
    local manifest_file="$1"
    local built_flag="$2"
    local service_tag="$3"
    local deployment_name="$4"
    local container_name="$5"
    
    if [ ! -f "$manifest_file" ]; then
        return
    fi
    
    local final_tag=""
    local tag_source=""
    
    # Priority 1: Service was built in this pipeline run - use the new tag
    if [ "${built_flag}" = "true" ] && [ -n "$service_tag" ] && [ "$service_tag" != "false" ]; then
        final_tag="$service_tag"
        tag_source="new build ✅"
    fi
    
    # Priority 2: Service NOT built - MUST get current tag from cluster
    # DO NOT use commit hash for non-built services - it won't exist in registry!
    if [ -z "$final_tag" ] && [ -n "$deployment_name" ]; then
        local cluster_tag=$(get_current_cluster_tag "$deployment_name" "$container_name")
        if [ -n "$cluster_tag" ]; then
            final_tag="$cluster_tag"
            tag_source="cluster (keeping existing) ✅"
        else
            # Mark as needing fix by deploy-application
            final_tag="NEEDS_CLUSTER_TAG"
            tag_source="⚠️ NEEDS FIX - deploy-application will resolve"
        fi
    fi
    
    # Priority 3: Only use commit hash if we have NO other option AND service was supposedly built
    if [ -z "$final_tag" ] || [ "$final_tag" = "NEEDS_CLUSTER_TAG" ]; then
        if [ "${built_flag}" = "true" ]; then
            final_tag="$cmtHashShort"
            tag_source="commit hash (built but no tag provided)"
        fi
        # If still NEEDS_CLUSTER_TAG, leave it - deploy-application will fix
    fi
    
    echo "  📌 $manifest_file → $final_tag ($tag_source)"
    
    # Replace placeholder with final tag
    sed -i -e "s|{{IMAGE_TAG}}|${final_tag}|g" "$manifest_file"
}

# ==============================================================================
# Set Image Tags for All Services
# ==============================================================================
echo ""
echo "Setting image tags based on build status..."

# Backend and Frontend
set_service_image_tag "08-backend.yaml" "${BACKEND_BUILT:-false}" "${BACKEND_TAG}" "backend" "backend"
set_service_image_tag "09-frontend.yaml" "${FRONTEND_BUILT:-false}" "${FRONTEND_TAG}" "frontend" "frontend"

# Microservices
set_service_image_tag "14-api-gateway.yaml" "${API_GATEWAY_BUILT:-false}" "${API_GATEWAY_TAG}" "api-gateway" "api-gateway"
set_service_image_tag "12-cluster-manager.yaml" "${CLUSTER_MANAGER_BUILT:-false}" "${CLUSTER_MANAGER_TAG}" "cluster-manager" "cluster-manager"
set_service_image_tag "13-analysis-orchestrator.yaml" "${ANALYSIS_ORCHESTRATOR_BUILT:-false}" "${ANALYSIS_ORCHESTRATOR_TAG}" "analysis-orchestrator" "analysis-orchestrator"
set_service_image_tag "10-ingestion-service.yaml" "${INGESTION_SERVICE_BUILT:-false}" "${INGESTION_SERVICE_TAG}" "ingestion-service" "ingestion-service"
set_service_image_tag "11-timeseries-writer.yaml" "${TIMESERIES_WRITER_BUILT:-false}" "${TIMESERIES_WRITER_TAG}" "timeseries-writer" "timeseries-writer"
set_service_image_tag "15-graph-writer.yaml" "${GRAPH_WRITER_BUILT:-false}" "${GRAPH_WRITER_TAG}" "graph-writer" "graph-writer"
set_service_image_tag "16-graph-query.yaml" "${GRAPH_QUERY_BUILT:-false}" "${GRAPH_QUERY_TAG}" "graph-query" "graph-query"
set_service_image_tag "17-timeseries-query.yaml" "${TIMESERIES_QUERY_BUILT:-false}" "${TIMESERIES_QUERY_TAG}" "timeseries-query" "timeseries-query"
set_service_image_tag "18-change-detection-worker.yaml" "${CHANGE_WORKER_BUILT:-false}" "${CHANGE_WORKER_TAG}" "change-detection-worker" "change-detection-worker"

# Replace any remaining {{IMAGE_TAG}} placeholders
for manifest in *.yaml; do
    if grep -q "{{IMAGE_TAG}}" "$manifest" 2>/dev/null; then
        # Try to get from cluster first
        dep_name=$(basename "$manifest" .yaml | sed 's/^[0-9]*-//')
        cluster_tag=$(get_current_cluster_tag "$dep_name" "$dep_name" 2>/dev/null || echo "")
        if [ -n "$cluster_tag" ]; then
            sed -i -e "s|{{IMAGE_TAG}}|${cluster_tag}|g" "$manifest"
            echo "  📌 $manifest → ${cluster_tag} (from cluster)"
        else
            sed -i -e "s|{{IMAGE_TAG}}|${cmtHashShort}|g" "$manifest"
            echo "  📌 $manifest → ${cmtHashShort} (default)"
        fi
    fi
done

echo ""

# ==============================================================================
# Replace ConfigMap and Secret Values
# ==============================================================================
echo "Replacing service hosts..."
sed -i -e "s|{{POSTGRES_HOST}}|${POSTGRES_HOST}|g" 03-configmaps.yaml
sed -i -e "s|{{REDIS_HOST}}|${REDIS_HOST}|g" 03-configmaps.yaml
sed -i -e "s|{{CLICKHOUSE_HOST}}|${CLICKHOUSE_HOST}|g" 03-configmaps.yaml
sed -i -e "s|{{RABBITMQ_HOST}}|${RABBITMQ_HOST}|g" 03-configmaps.yaml

echo "Replacing domain and URLs..."
sed -i -e "s|{{DOMAIN_NAME}}|${DOMAIN_NAME}|g" 11-ingress.yaml
sed -i -e "s|{{FRONTEND_URL}}|${FRONTEND_URL}|g" 11-ingress.yaml
sed -i -e "s|{{API_BASE_URL}}|${API_BASE_URL}|g" 11-ingress.yaml
sed -i -e "s|{{TLS_SECRET_NAME}}|${TLS_SECRET_NAME}|g" 11-ingress.yaml

echo "Replacing namespace..."
for manifest in *.yaml; do
  sed -i -e "s|{{OPENSHIFT_NAMESPACE}}|${OPENSHIFT_NAMESPACE}|g" $manifest
done

echo "Replacing storage class..."
for manifest in *.yaml; do
  sed -i -e "s|{{STORAGE_CLASS}}|${STORAGE_CLASS}|g" $manifest
done

echo "Replacing secret credentials..."
sed -i -e "s|{{POSTGRES_USER}}|${POSTGRES_USER}|g" 04-secrets.yaml
sed -i -e "s|{{POSTGRES_PASSWORD}}|${POSTGRES_PASSWORD}|g" 04-secrets.yaml
sed -i -e "s|{{REDIS_PASSWORD}}|${REDIS_PASSWORD}|g" 04-secrets.yaml
sed -i -e "s|{{CLICKHOUSE_USER}}|${CLICKHOUSE_USER}|g" 04-secrets.yaml
sed -i -e "s|{{CLICKHOUSE_PASSWORD}}|${CLICKHOUSE_PASSWORD}|g" 04-secrets.yaml
sed -i -e "s|{{RABBITMQ_USER}}|${RABBITMQ_USER}|g" 04-secrets.yaml
sed -i -e "s|{{RABBITMQ_PASSWORD}}|${RABBITMQ_PASSWORD}|g" 04-secrets.yaml
sed -i -e "s|{{RABBITMQ_ERLANG_COOKIE}}|${RABBITMQ_ERLANG_COOKIE}|g" 04-secrets.yaml
sed -i -e "s|{{NEO4J_PASSWORD}}|${NEO4J_PASSWORD}|g" 04-secrets.yaml
sed -i -e "s|{{JWT_SECRET_KEY}}|${JWT_SECRET_KEY}|g" 04-secrets.yaml
sed -i -e "s|{{WEBHOOK_SECRET}}|${WEBHOOK_SECRET}|g" 04-secrets.yaml

# FLOWFISH_ENCRYPTION_KEY handling
if [ -z "${FLOWFISH_ENCRYPTION_KEY}" ]; then
    echo "FLOWFISH_ENCRYPTION_KEY not provided, checking existing secret..."
    if [ "$OC_LOGIN_SUCCESS" = "true" ]; then
    EXISTING_KEY=$(oc get secret flowfish-secrets -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.data.FLOWFISH_ENCRYPTION_KEY}' 2>/dev/null | base64 -d 2>/dev/null || echo "")
        if [ -n "${EXISTING_KEY}" ]; then
        FLOWFISH_ENCRYPTION_KEY="${EXISTING_KEY}"
            echo "Using existing FLOWFISH_ENCRYPTION_KEY from cluster"
        fi
    fi
    
    if [ -z "${FLOWFISH_ENCRYPTION_KEY}" ]; then
        echo "Generating new FLOWFISH_ENCRYPTION_KEY..."
        FLOWFISH_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
        echo "⚠️  New key generated - save this for future releases!"
    fi
fi
sed -i -e "s|{{FLOWFISH_ENCRYPTION_KEY}}|${FLOWFISH_ENCRYPTION_KEY}|g" 04-secrets.yaml

echo ""
echo "================================================"
echo "Manifest preparation complete"
echo "================================================"
echo "Manifests location: $MANIFEST_DIR"
ls -la $MANIFEST_DIR
echo "================================================"
