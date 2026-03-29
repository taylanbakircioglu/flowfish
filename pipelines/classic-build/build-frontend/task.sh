#!/bin/bash
set -e

# ==============================================================================
# Flowfish Frontend Build - Incremental Build Support
# ==============================================================================
# Bu script "Detect Changes" task'ından sonra çalışır.
# FRONTEND_CHANGED değişkeni önceki task tarafından set edilmiş olmalı.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 FRONTEND BUILD"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ${BUILD_SOURCESDIRECTORY}

cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
environment=${DEPLOYMENT_ENV:-pilot}
HARBOR_PROJECT="flowfish"

echo ""
echo "📦 Commit Hash: $cmtHashShort"
echo "🌍 Environment: $environment"
echo "📋 FRONTEND_CHANGED: ${FRONTEND_CHANGED:-0}"

# Frontend değişikliği var mı kontrol et (varsayılan 0)
if [ "${FRONTEND_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔨 Building Frontend..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Harbor credentials check
    if [ -z "${HARBOR_REGISTRY}" ] || [ -z "${HARBOR_USER}" ] || [ -z "${HARBOR_PASSWORD}" ]; then
        echo "❌ ERROR: Harbor credentials not set!"
        exit 1
    fi
    
    podman login -u ${HARBOR_USER} -p ${HARBOR_PASSWORD} ${HARBOR_REGISTRY}
    
    # Generate unique cache bust value
    CACHE_BUST_VAL=$(date +%s)
    echo "🔄 Cache bust value: $CACHE_BUST_VAL"
    
    podman build --no-cache --rm=false \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-frontend:$cmtHashShort \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-frontend:latest \
        --build-arg environment=$environment \
        --build-arg CACHE_BUST=$CACHE_BUST_VAL \
        -f frontend/Dockerfile.production \
        .
    
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-frontend:$cmtHashShort
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-frontend:latest
    
    echo "✅ Frontend build complete!"
    echo "##vso[task.setvariable variable=FRONTEND_BUILT;isOutput=true]true"
    echo "##vso[task.setvariable variable=FRONTEND_TAG;isOutput=true]$cmtHashShort"
else
    echo ""
    echo "⏭️  Skipping Frontend build - No changes detected"
    echo "##vso[task.setvariable variable=FRONTEND_BUILT;isOutput=true]false"
fi

echo ""
echo "🎉 Frontend build task completed!"
