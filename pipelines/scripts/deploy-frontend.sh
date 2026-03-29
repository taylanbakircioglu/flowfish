#!/bin/bash
set -e

# Deploy Frontend Service

ns=$OPENSHIFT_NAMESPACE

echo "Deploying Frontend..."
echo "Namespace: $ns"
echo "  Image Tag: $FRONTEND_IMAGE_TAG"

# Check if deployment needed
FRONTEND_CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -E "^(frontend/|package\.json)" | wc -l)

echo "Frontend changes: $FRONTEND_CHANGED"
echo "Frontend built: $FRONTEND_BUILT"
echo "Release-all: $RELEASE_ALL"

# Login to OpenShift
echo " Login to OpenShift..."
oc login -u $OPENSHIFT_USER -p $OPENSHIFT_PASSWORD $OPENSHIFT_API_URL --insecure-skip-tls-verify=true
oc project $ns

MANIFEST_DIR="${PIPELINE_WORKSPACE}/manifests"

# Deploy frontend if needed
if [ "$RELEASE_ALL" = "true" ] || [ $FRONTEND_CHANGED -gt 0 ] || [ "$FRONTEND_BUILT" = "true" ]; then
    echo " Deploying Frontend service..."
    
    # Update image tag
    sed -i -e "s|image-version|${FRONTEND_IMAGE_TAG}|g" $MANIFEST_DIR/09-frontend.yaml
    
    # Apply manifest
    oc apply -f $MANIFEST_DIR/09-frontend.yaml -n $ns || {
        echo "Frontend apply failed"
        exit 1
    }
    
    # Wait for deployment
    echo "  Waiting for Frontend deployment..."
    oc wait --for=condition=available deployment/frontend -n $ns --timeout=300s || {
        echo "Frontend deployment timeout"
        oc logs deployment/frontend -n $ns --tail=50
        exit 1
    }
    
    echo "Frontend deployed successfully"
else
    echo "  Frontend deployment skipped (no changes)"
fi

# Apply Ingress/Route
echo "Applying Ingress..."
oc apply -f $MANIFEST_DIR/11-ingress.yaml -n $ns || true

echo ""
echo " Frontend Status:"
oc get pods -l app=frontend -n $ns
oc get deployment frontend -n $ns

echo ""
echo "Frontend URL:"
oc get route frontend -n $ns -o jsonpath='{.spec.host}' 2>/dev/null || echo "Route not found"

