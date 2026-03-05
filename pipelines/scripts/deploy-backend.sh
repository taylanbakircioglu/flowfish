#!/bin/bash
set -e

# Deploy Backend Service

ns=$OPENSHIFT_NAMESPACE

echo "Deploying Backend..."
echo "Namespace: $ns"
echo "  Image Tag: $BACKEND_IMAGE_TAG"

# Check if deployment needed
BACKEND_CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -E "^(backend/|proto/)" | wc -l)

echo "Backend changes: $BACKEND_CHANGED"
echo "Backend built: $BACKEND_BUILT"
echo "Release-all: $RELEASE_ALL"

# Login to OpenShift
echo " Login to OpenShift..."
oc login -u $OPENSHIFT_USER -p $OPENSHIFT_PASSWORD $OPENSHIFT_API_URL --insecure-skip-tls-verify=true
oc project $ns

MANIFEST_DIR="${PIPELINE_WORKSPACE}/manifests"

# Deploy backend if needed
if [ "$RELEASE_ALL" = "true" ] || [ $BACKEND_CHANGED -gt 0 ] || [ "$BACKEND_BUILT" = "true" ]; then
    echo " Deploying Backend service..."
    
    # Update image tag
    sed -i -e "s|image-version|${BACKEND_IMAGE_TAG}|g" $MANIFEST_DIR/08-backend.yaml
    
    # Apply manifest
    oc apply -f $MANIFEST_DIR/08-backend.yaml -n $ns || {
        echo "Backend apply failed"
        exit 1
    }
    
    # Wait for deployment
    echo "  Waiting for Backend deployment..."
    oc wait --for=condition=available deployment/backend -n $ns --timeout=300s || {
        echo "Backend deployment timeout"
        oc logs deployment/backend -n $ns --tail=50
        exit 1
    }
    
    echo "Backend deployed successfully"
else
    echo "  Backend deployment skipped (no changes)"
fi

echo ""
echo " Backend Status:"
oc get pods -l app=backend -n $ns
oc get deployment backend -n $ns

