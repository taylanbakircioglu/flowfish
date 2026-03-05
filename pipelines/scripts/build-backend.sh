#!/bin/bash
set -e

# Backend Build Script for Flowfish Platform
# Builds backend FastAPI application

environment=${DEPLOYMENT_ENV:-pilot}
project=$(echo $SYSTEM_TEAMPROJECT | tr '[:upper:]' '[:lower:]')
registry=${HARBOR_REGISTRY}

# Generate unique image tag
buildId=$BUILD_BUILDID
commitHash=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
cmtHashShort="${commitHash}-${buildId}-${environment}"

echo "Backend Build - Checking for changes..."
echo " Build ID: $buildId"
echo " Commit: $commitHash"
echo " Tag: $cmtHashShort"

# Check backend changes
BACKEND_CHANGED=$(git diff --name-only HEAD~1 HEAD | grep -E "^(backend/|proto/)" | wc -l)

echo "Backend changed files: $BACKEND_CHANGED"
echo "Build-all flag: $BUILD_ALL"
echo "Current working directory: $(pwd)"

# Force build if build-all is true OR if backend files changed
if [ "$BUILD_ALL" = "true" ] || [ $BACKEND_CHANGED -gt 0 ]; then
    if [ "$BUILD_ALL" = "true" ]; then
        echo "Force build triggered by build-all flag"
    else
        echo "Backend changes detected - Building new image..."
    fi
    
    # Login to registry
    echo " Login to Harbor Registry"
    podman login -u $HARBOR_USER -p $HARBOR_PASSWORD $registry
    
    # Build backend
    app=flowfish-backend
    echo "Building: $registry/$project/$app:$cmtHashShort"
    echo "Dockerfile: backend/Dockerfile"
    echo "Context: $(pwd)/backend"
    
    # Build without cache when build-all is true
    if [ "$BUILD_ALL" = "true" ]; then
        echo " Building without cache (build-all=true)"
        podman build --no-cache -t $registry/$project/$app:$cmtHashShort -f backend/Dockerfile ./backend
    else
        podman build -t $registry/$project/$app:$cmtHashShort -f backend/Dockerfile ./backend
    fi
    
    podman push $registry/$project/$app:$cmtHashShort
    
    echo "Backend build completed: $cmtHashShort"
    echo "##vso[task.setvariable variable=BackendImageTag;isOutput=true]$cmtHashShort"
    echo "##vso[task.setvariable variable=BackendBuilt;isOutput=true]true"
else
    # Use current buildId even for unchanged backend
    LAST_BACKEND_COMMIT=$(git log --oneline --follow --format="%H" -- backend/ proto/ 2>/dev/null | head -1 | cut -c1-7)
    LAST_BACKEND_TAG="${LAST_BACKEND_COMMIT}-${buildId}-${environment}"
    
    echo " No backend changes - Using previous commit with new build ID: $LAST_BACKEND_TAG"
    echo "##vso[task.setvariable variable=BackendImageTag;isOutput=true]$LAST_BACKEND_TAG"
    echo "##vso[task.setvariable variable=BackendBuilt;isOutput=true]false"
fi

echo "Backend build task completed!"

