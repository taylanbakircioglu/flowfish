#!/bin/bash
set -e

# ==============================================================================
# Flowfish Backend Build - Incremental Build Support
# ==============================================================================
# Bu script "Detect Changes" task'ından sonra çalışır.
# BACKEND_CHANGED değişkeni önceki task tarafından set edilmiş olmalı.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 BACKEND BUILD"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ${BUILD_SOURCESDIRECTORY}

cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)
environment=${DEPLOYMENT_ENV:-pilot}
HARBOR_PROJECT="flowfish"

echo ""
echo "📦 Commit Hash: $cmtHashShort"
echo "🌍 Environment: $environment"
echo "📋 BACKEND_CHANGED: ${BACKEND_CHANGED:-0}"

# Backend değişikliği var mı kontrol et (varsayılan 0)
if [ "${BACKEND_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔨 Building Backend..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # Harbor credentials check
    if [ -z "${HARBOR_REGISTRY}" ] || [ -z "${HARBOR_USER}" ] || [ -z "${HARBOR_PASSWORD}" ]; then
        echo "❌ ERROR: Harbor credentials not set!"
        exit 1
    fi
    
    podman login -u ${HARBOR_USER} -p ${HARBOR_PASSWORD} ${HARBOR_REGISTRY}
    
    podman build --no-cache --rm=false \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-backend:$cmtHashShort \
        -t ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-backend:latest \
        --build-arg environment=$environment \
        -f backend/Dockerfile \
        .
    
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-backend:$cmtHashShort
    podman push ${HARBOR_REGISTRY}/$HARBOR_PROJECT/flowfish-backend:latest
    
    echo "✅ Backend build complete!"
    echo "##vso[task.setvariable variable=BACKEND_BUILT;isOutput=true]true"
    echo "##vso[task.setvariable variable=BACKEND_TAG;isOutput=true]$cmtHashShort"
else
    echo ""
    echo "⏭️  Skipping Backend build - No changes detected"
    echo "##vso[task.setvariable variable=BACKEND_BUILT;isOutput=true]false"
fi

echo ""
echo "🎉 Backend build task completed!"
