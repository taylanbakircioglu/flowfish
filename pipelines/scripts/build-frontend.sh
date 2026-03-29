#!/bin/bash
set -e

# Frontend Build Script for Flowfish Platform
# Builds React + TypeScript frontend

environment=${DEPLOYMENT_ENV:-pilot}
project=$(echo $SYSTEM_TEAMPROJECT | tr '[:upper:]' '[:lower:]')
registry=${HARBOR_REGISTRY}

# Generate unique image tag
buildId=$BUILD_BUILDID
commitHash=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
cmtHashShort="${commitHash}-${buildId}-${environment}"

echo "Frontend Build - Checking for changes..."
echo " Build ID: $buildId"
echo " Commit: $commitHash"
echo " Tag: $cmtHashShort"

# Check frontend changes - look at last 5 commits to catch all pending changes
FRONTEND_CHANGED=$(git diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E "^(frontend/|package\.json)" | wc -l || echo "0")

# If git diff fails, assume changes exist (safer approach)
if [ -z "$FRONTEND_CHANGED" ] || [ "$FRONTEND_CHANGED" = "0" ]; then
    # Also check if Dockerfile was modified (forces rebuild)
    DOCKERFILE_CHANGED=$(git diff --name-only HEAD~5 HEAD 2>/dev/null | grep -E "^frontend/Dockerfile" | wc -l || echo "0")
    if [ "$DOCKERFILE_CHANGED" -gt 0 ]; then
        FRONTEND_CHANGED=1
        echo "Dockerfile changed - forcing frontend rebuild"
    fi
fi

echo "Frontend changed files: $FRONTEND_CHANGED"
echo "Build-all flag: $BUILD_ALL"
echo "Current working directory: $(pwd)"

# Force build if build-all is true OR if frontend files changed
if [ "$BUILD_ALL" = "true" ] || [ $FRONTEND_CHANGED -gt 0 ]; then
    if [ "$BUILD_ALL" = "true" ]; then
        echo "Force build triggered by build-all flag"
    else
        echo "Frontend changes detected - Building new image..."
    fi
    
    # Login to registry
    echo " Login to Harbor Registry"
    podman login -u $HARBOR_USER -p $HARBOR_PASSWORD $registry
    
    # Build frontend
    app=flowfish-frontend
    echo "Building: $registry/$project/$app:$cmtHashShort"
    echo "Dockerfile: frontend/Dockerfile"
    echo "Context: $(pwd)/frontend"
    
    # Build without cache when build-all is true
    if [ "$BUILD_ALL" = "true" ]; then
        echo " Building without cache (build-all=true)"
        podman build --no-cache \
            --build-arg REACT_APP_API_URL=${REACT_APP_API_URL} \
            -t $registry/$project/$app:$cmtHashShort \
            -f frontend/Dockerfile ./frontend
    else
        podman build \
            --build-arg REACT_APP_API_URL=${REACT_APP_API_URL} \
            -t $registry/$project/$app:$cmtHashShort \
            -f frontend/Dockerfile ./frontend
    fi
    
    podman push $registry/$project/$app:$cmtHashShort
    
    echo "Frontend build completed: $cmtHashShort"
    echo "##vso[task.setvariable variable=FrontendImageTag;isOutput=true]$cmtHashShort"
    echo "##vso[task.setvariable variable=FrontendBuilt;isOutput=true]true"
else
    # Use current buildId even for unchanged frontend
    LAST_FRONTEND_COMMIT=$(git log --oneline --follow --format="%H" -- frontend/ package.json 2>/dev/null | head -1 | cut -c1-7)
    LAST_FRONTEND_TAG="${LAST_FRONTEND_COMMIT}-${buildId}-${environment}"
    
    echo " No frontend changes - Using previous commit with new build ID: $LAST_FRONTEND_TAG"
    echo "##vso[task.setvariable variable=FrontendImageTag;isOutput=true]$LAST_FRONTEND_TAG"
    echo "##vso[task.setvariable variable=FrontendBuilt;isOutput=true]false"
fi

echo "Frontend build task completed!"

