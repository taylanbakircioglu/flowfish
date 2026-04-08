#!/bin/bash
set -e

# Prepare Kubernetes Manifests
# Replaces placeholders with actual values from CompanyVariable group

echo "Preparing Kubernetes manifests..."

cd deployment/kubernetes-manifests

# Generate image tags
buildId=$BUILD_BUILDID
commitHash=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
cmtHashShort="${commitHash}-${buildId}"

echo "  Image Tag: $cmtHashShort"
echo "Registry: $HARBOR_REGISTRY"
echo " Project: flowfish"
echo " Environment: $DEPLOYMENT_ENV"
echo "  Company: $COMPANY_NAME"

# Replace ALL placeholders in ALL YAML files
for manifest in *.yaml; do
    if [ -f "$manifest" ]; then
        echo "    Processing $manifest"
        
        # Image registry and tags
        sed -i -e "s|{{HARBOR_REGISTRY}}|${HARBOR_REGISTRY}|g" $manifest
        sed -i -e "s|{{HARBOR_PROJECT}}|flowfish|g" $manifest
        sed -i -e "s|{{IMAGE_TAG}}|${cmtHashShort}|g" $manifest
        sed -i -e "s|image-version|${cmtHashShort}|g" $manifest
        
        # Namespace placeholders
        sed -i -e "s|{{OPENSHIFT_NAMESPACE}}|${OPENSHIFT_NAMESPACE}|g" $manifest
        sed -i -e "s|{{DEPLOYMENT_ENV}}|${DEPLOYMENT_ENV}|g" $manifest
        sed -i -e "s|env-flowfish|${DEPLOYMENT_ENV}-flowfish|g" $manifest
        
        # Company placeholders
        sed -i -e "s|company\.com\.tr|${COMPANY_NAME}.com.tr|g" $manifest
        
        # Database hosts
        sed -i -e "s|{{POSTGRES_HOST}}|${POSTGRES_HOST}|g" $manifest
        sed -i -e "s|{{REDIS_HOST}}|${REDIS_HOST}|g" $manifest
        sed -i -e "s|{{CLICKHOUSE_HOST}}|${CLICKHOUSE_HOST}|g" $manifest
        sed -i -e "s|{{NEO4J_HOST}}|${NEO4J_HOST}|g" $manifest
        sed -i -e "s|{{RABBITMQ_HOST}}|${RABBITMQ_HOST}|g" $manifest
        
        # API URLs
        sed -i -e "s|{{API_BASE_URL}}|${API_BASE_URL}|g" $manifest
        
        # Frontend URL (should be hostname only, without protocol)
        # e.g., flowfish.example.com (not https://flowfish.example.com)
        sed -i -e "s|{{FRONTEND_URL}}|${FRONTEND_URL}|g" $manifest
        
        # Storage Class
        sed -i -e "s|{{STORAGE_CLASS}}|${STORAGE_CLASS}|g" $manifest
        
        # Gadget version
        if [ -n "${GADGET_VERSION}" ]; then
            sed -i -e "s|{{GADGET_VERSION}}|${GADGET_VERSION}|g" $manifest
        fi
        
        # Events buffer length (default: 16384 for production clusters)
        EVENTS_BUFFER_LENGTH="${EVENTS_BUFFER_LENGTH:-16384}"
        sed -i -e "s|{{EVENTS_BUFFER_LENGTH}}|${EVENTS_BUFFER_LENGTH}|g" $manifest
        
        # TLS Secret (if variable is set)
        if [ -n "${TLS_SECRET_NAME}" ]; then
            sed -i -e "s|{{TLS_SECRET_NAME}}|${TLS_SECRET_NAME}|g" $manifest
        fi
    fi
done

echo "Manifests prepared successfully"
echo ""
echo " Image Tags:"
echo "  Backend: $HARBOR_REGISTRY/flowfish/flowfish-backend:$cmtHashShort"
echo "  Frontend: $HARBOR_REGISTRY/flowfish/flowfish-frontend:$cmtHashShort"

