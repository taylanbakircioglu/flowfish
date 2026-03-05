#!/bin/bash
set -e

# Generic Microservice Build Script for Flowfish Platform
# Usage: SERVICE_NAME=api-gateway ./build-microservice.sh

if [ -z "$SERVICE_NAME" ]; then
    echo "ERROR: SERVICE_NAME environment variable is required"
    exit 1
fi

environment=${DEPLOYMENT_ENV:-pilot}
project=$(echo $SYSTEM_TEAMPROJECT | tr '[:upper:]' '[:lower:]')
registry=${HARBOR_REGISTRY}

# Generate unique image tag
buildId=$BUILD_BUILDID
commitHash=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
cmtHashShort="${commitHash}-${buildId}-${environment}"

SERVICE_DIR="services/${SERVICE_NAME}"
VAR_PREFIX=$(echo $SERVICE_NAME | tr '[:lower:]' '[:upper:]' | tr '-' '_')

echo "${SERVICE_NAME} Build - Checking for changes..."
echo " Build ID: $buildId"
echo " Commit: $commitHash"
echo " Tag: $cmtHashShort"
echo "Service Dir: $SERVICE_DIR"

# Check service changes
SERVICE_CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -E "^(${SERVICE_DIR}/|proto/)" | wc -l)

echo "${SERVICE_NAME} changed files: $SERVICE_CHANGED"
echo "Build-all flag: $BUILD_ALL"
echo "Current working directory: $(pwd)"

# Force build if build-all is true OR if service files changed
if [ "$BUILD_ALL" = "true" ] || [ $SERVICE_CHANGED -gt 0 ]; then
    if [ "$BUILD_ALL" = "true" ]; then
        echo "Force build triggered by build-all flag"
    else
        echo "${SERVICE_NAME} changes detected - Building new image..."
    fi
    
    # Login to registry
    echo " Login to Harbor Registry"
    podman login -u $HARBOR_USER -p $HARBOR_PASSWORD $registry
    
    # Build service
    app="flowfish-${SERVICE_NAME}"
    echo "Building: $registry/$project/$app:$cmtHashShort"
    echo "Dockerfile: ${SERVICE_DIR}/Dockerfile"
    echo "Context: $(pwd)/${SERVICE_DIR}"
    
    # Copy proto files to service directory for build
    echo "Copying proto files..."
    cp -r proto ${SERVICE_DIR}/ || true
    
    # Build without cache when build-all is true
    if [ "$BUILD_ALL" = "true" ]; then
        echo " Building without cache (build-all=true)"
        podman build --no-cache -t $registry/$project/$app:$cmtHashShort -f ${SERVICE_DIR}/Dockerfile ./${SERVICE_DIR}
    else
        podman build -t $registry/$project/$app:$cmtHashShort -f ${SERVICE_DIR}/Dockerfile ./${SERVICE_DIR}
    fi
    
    # Cleanup
    rm -rf ${SERVICE_DIR}/proto
    
    podman push $registry/$project/$app:$cmtHashShort
    
    echo "${SERVICE_NAME} build completed: $cmtHashShort"
    echo "##vso[task.setvariable variable=${VAR_PREFIX}ImageTag;isOutput=true]$cmtHashShort"
    echo "##vso[task.setvariable variable=${VAR_PREFIX}Built;isOutput=true]true"
else
    # Use current buildId even for unchanged service
    LAST_COMMIT=$(git log --oneline --follow --format="%H" -- ${SERVICE_DIR}/ proto/ 2>/dev/null | head -1 | cut -c1-7)
    LAST_TAG="${LAST_COMMIT}-${buildId}-${environment}"
    
    echo " No ${SERVICE_NAME} changes - Using previous commit with new build ID: $LAST_TAG"
    echo "##vso[task.setvariable variable=${VAR_PREFIX}ImageTag;isOutput=true]$LAST_TAG"
    echo "##vso[task.setvariable variable=${VAR_PREFIX}Built;isOutput=true]false"
fi

echo "${SERVICE_NAME} build task completed!"

