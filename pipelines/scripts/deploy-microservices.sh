#!/bin/bash
set -e

# ==============================================================================
# Deploy Microservices - Incremental Deployment
# ==============================================================================
# YAML pipeline için optimize edilmiş versiyon
# Sadece yeni build edilen servisleri deploy eder
# ==============================================================================

ns=$OPENSHIFT_NAMESPACE

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 MICROSERVICES INCREMENTAL DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Namespace: $ns"
echo "📋 RELEASE_ALL: ${RELEASE_ALL:-false}"
echo ""

# OpenShift Login
echo "🔐 Logging into OpenShift..."
oc login -u $OPENSHIFT_USER -p $OPENSHIFT_PASSWORD $OPENSHIFT_API_URL --insecure-skip-tls-verify=true
oc project $ns

MANIFEST_DIR="${PIPELINE_WORKSPACE}/manifests"

# Deployment counter
DEPLOYED_COUNT=0
SKIPPED_COUNT=0

# Generic deploy function
deploy_service() {
    local service_name="$1"
    local manifest_file="$2"
    local image_tag="$3"
    local built_var="$4"  # Environment variable name that indicates if it was built
    
    # Check if we should deploy this service
    local should_deploy=false
    
    if [ "${RELEASE_ALL:-false}" = "true" ]; then
        should_deploy=true
    elif [ -n "$image_tag" ]; then
        # If image tag is provided, it means it was built
        should_deploy=true
    fi
    
    if [ "$should_deploy" = "true" ]; then
        if [ -f "$MANIFEST_DIR/$manifest_file" ]; then
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "🚀 Deploying: $service_name"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            
            if [ -n "$image_tag" ]; then
                echo "📌 Image Tag: $image_tag"
                sed -i -e "s|image-version|${image_tag}|g" "$MANIFEST_DIR/$manifest_file"
            fi
            
            oc apply -f "$MANIFEST_DIR/$manifest_file" -n $ns
            
            # Extract deployment name
            local deployment_name=$(echo "$service_name" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
            oc wait --for=condition=available deployment/$deployment_name -n $ns --timeout=180s || true
            
            echo "✅ $service_name deployed!"
            DEPLOYED_COUNT=$((DEPLOYED_COUNT + 1))
        else
            echo "⚠️  Manifest not found: $manifest_file"
        fi
    else
        echo "⏭️  Skipping $service_name - Not built in this run"
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    fi
}

# Deploy services based on what was built
deploy_service "API Gateway" "14-api-gateway.yaml" "${API_GATEWAY_IMAGE_TAG}" "API_GATEWAY"
deploy_service "Cluster Manager" "12-cluster-manager.yaml" "${CLUSTER_MANAGER_IMAGE_TAG}" "CLUSTER_MANAGER"
deploy_service "Analysis Orchestrator" "13-analysis-orchestrator.yaml" "${ANALYSIS_ORCHESTRATOR_IMAGE_TAG}" "ANALYSIS_ORCHESTRATOR"
deploy_service "Graph Writer" "15-graph-writer.yaml" "${GRAPH_WRITER_IMAGE_TAG}" "GRAPH_WRITER"
deploy_service "Graph Query" "16-graph-query.yaml" "${GRAPH_QUERY_IMAGE_TAG}" "GRAPH_QUERY"
deploy_service "Timeseries Writer" "11-timeseries-writer.yaml" "${TIMESERIES_WRITER_IMAGE_TAG}" "TIMESERIES_WRITER"
deploy_service "Ingestion Service" "10-ingestion-service.yaml" "${INGESTION_SERVICE_IMAGE_TAG}" "INGESTION_SERVICE"

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 DEPLOYMENT SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployed: $DEPLOYED_COUNT microservices"
echo "⏭️  Skipped: $SKIPPED_COUNT microservices"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "📋 Microservices Status:"
oc get pods -l tier=microservice -n $ns || true

echo ""
echo "🎉 Microservices deployment completed!"
