#!/bin/bash
# ==============================================================================
# Publish Build Info - Creates artifact with built image tags
# ==============================================================================
# Bu script, hangi servislerin build edildiğini ve hangi tag'lerle
# build edildiğini bir dosyaya yazar. Release pipeline bu dosyayı okuyarak
# doğru image tag'lerini kullanır.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 PUBLISHING BUILD INFO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BUILD_INFO_DIR="${BUILD_ARTIFACTSTAGINGDIRECTORY}/build-info"
mkdir -p "$BUILD_INFO_DIR"

BUILD_INFO_FILE="$BUILD_INFO_DIR/build-info.env"
cmtHashShort=$(echo $BUILD_SOURCEVERSION | cut -c1-7)

echo "📌 Current Commit: $cmtHashShort"
echo "📌 Build ID: $BUILD_BUILDID"
echo ""

# Write build info header
cat > "$BUILD_INFO_FILE" << EOF
# Flowfish Build Info
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Commit: $BUILD_SOURCEVERSION
# Build ID: $BUILD_BUILDID

BUILD_COMMIT=$cmtHashShort
BUILD_ID=$BUILD_BUILDID
BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

echo "" >> "$BUILD_INFO_FILE"
echo "# Service Build Status and Tags" >> "$BUILD_INFO_FILE"
echo "# BUILT=true means the service was rebuilt in this pipeline run" >> "$BUILD_INFO_FILE"
echo "# TAG is the image tag to use for deployment" >> "$BUILD_INFO_FILE"
echo "" >> "$BUILD_INFO_FILE"

# Function to record build status
record_build_status() {
    local service_name="$1"
    local changed_var="$2"
    local tag_var="${service_name}_TAG"
    local built_var="${service_name}_BUILT"
    
    if [ "${!changed_var:-0}" -gt 0 ] 2>/dev/null; then
        echo "${tag_var}=$cmtHashShort" >> "$BUILD_INFO_FILE"
        echo "${built_var}=true" >> "$BUILD_INFO_FILE"
        echo "✅ $service_name: $cmtHashShort (rebuilt)"
    else
        echo "${built_var}=false" >> "$BUILD_INFO_FILE"
        echo "⏭️  $service_name: not rebuilt"
    fi
}

# Record all service build statuses
record_build_status "BACKEND" "BACKEND_CHANGED"
record_build_status "FRONTEND" "FRONTEND_CHANGED"
record_build_status "API_GATEWAY" "API_GATEWAY_CHANGED"
record_build_status "CLUSTER_MANAGER" "CLUSTER_MANAGER_CHANGED"
record_build_status "ANALYSIS_ORCHESTRATOR" "ANALYSIS_ORCHESTRATOR_CHANGED"
record_build_status "GRAPH_WRITER" "GRAPH_WRITER_CHANGED"
record_build_status "GRAPH_QUERY" "GRAPH_QUERY_CHANGED"
record_build_status "TIMESERIES_WRITER" "TIMESERIES_WRITER_CHANGED"
record_build_status "TIMESERIES_QUERY" "TIMESERIES_QUERY_CHANGED"
record_build_status "INGESTION_SERVICE" "INGESTION_SERVICE_CHANGED"
record_build_status "CHANGE_WORKER" "CHANGE_WORKER_CHANGED"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📄 Build Info File Contents:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat "$BUILD_INFO_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Build info published to: $BUILD_INFO_FILE"
echo ""
echo "📌 To use in Release Pipeline:"
echo "   1. Add artifact alias: Flowfish-CI"
echo "   2. Set variable: BUILD_INFO_FILE = \$(System.ArtifactsDirectory)/Flowfish-CI/build-info/build-info.env"
echo ""
