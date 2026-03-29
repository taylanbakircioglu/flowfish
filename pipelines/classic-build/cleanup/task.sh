#!/bin/bash
# ==============================================================================
# Flowfish Cleanup - Local Images + Harbor Registry
# ==============================================================================
# Bu script hem local build agent'daki hem de Harbor registry'deki
# eski image'ları temizler. Son 3 tag + latest korunur.
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 FLOWFISH IMAGE CLEANUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==============================================================================
# CHECK IF CLEANUP SHOULD RUN
# ==============================================================================
# isOutput=true ile DetectChanges job'undan gelen değişkenler kontrol edilir.
# Cleanup job'unun Bash Task → Environment Variables bölümünde şu şekilde tanımlanmalı:
#   BACKEND_CHANGED=$(DetectChanges.DetectChanges.BACKEND_CHANGED)
#   FRONTEND_CHANGED=$(DetectChanges.DetectChanges.FRONTEND_CHANGED)
#   API_GATEWAY_CHANGED=$(DetectChanges.DetectChanges.API_GATEWAY_CHANGED)
#   CLUSTER_MANAGER_CHANGED=$(DetectChanges.DetectChanges.CLUSTER_MANAGER_CHANGED)
#   ANALYSIS_ORCHESTRATOR_CHANGED=$(DetectChanges.DetectChanges.ANALYSIS_ORCHESTRATOR_CHANGED)
#   GRAPH_WRITER_CHANGED=$(DetectChanges.DetectChanges.GRAPH_WRITER_CHANGED)
#   GRAPH_QUERY_CHANGED=$(DetectChanges.DetectChanges.GRAPH_QUERY_CHANGED)
#   TIMESERIES_WRITER_CHANGED=$(DetectChanges.DetectChanges.TIMESERIES_WRITER_CHANGED)
#   TIMESERIES_QUERY_CHANGED=$(DetectChanges.DetectChanges.TIMESERIES_QUERY_CHANGED)
#   INGESTION_SERVICE_CHANGED=$(DetectChanges.DetectChanges.INGESTION_SERVICE_CHANGED)
#   CHANGE_WORKER_CHANGED=$(DetectChanges.DetectChanges.CHANGE_WORKER_CHANGED)

ALL_CHANGE_VARS=(
    "${BACKEND_CHANGED-}"
    "${FRONTEND_CHANGED-}"
    "${API_GATEWAY_CHANGED-}"
    "${CLUSTER_MANAGER_CHANGED-}"
    "${ANALYSIS_ORCHESTRATOR_CHANGED-}"
    "${GRAPH_WRITER_CHANGED-}"
    "${GRAPH_QUERY_CHANGED-}"
    "${TIMESERIES_WRITER_CHANGED-}"
    "${TIMESERIES_QUERY_CHANGED-}"
    "${INGESTION_SERVICE_CHANGED-}"
    "${CHANGE_WORKER_CHANGED-}"
)

VARS_RECEIVED=0
ANY_CHANGES=0

for val in "${ALL_CHANGE_VARS[@]}"; do
    if [ -n "$val" ]; then
        VARS_RECEIVED=1
        if [ "$val" -gt 0 ] 2>/dev/null; then
            ANY_CHANGES=1
        fi
    fi
done

if [ "${BUILD_ALL:-false}" = "true" ]; then
    ANY_CHANGES=1
fi

if [ "$VARS_RECEIVED" -eq 1 ] && [ "$ANY_CHANGES" -eq 0 ]; then
    echo "⏭️  No code changes detected - skipping cleanup"
    exit 0
fi

if [ "$VARS_RECEIVED" -eq 0 ]; then
    echo "⚠️  Change detection variables not received - running cleanup as safety fallback"
    echo "   Cleanup job'unun Environment Variables ayarlarını kontrol edin."
fi

echo ""

REGISTRY=${HARBOR_REGISTRY}
HARBOR_PROJECT="flowfish"
KEEP_COUNT=${CLEANUP_KEEP_COUNT:-3}  # Son kaç tag korunacak (latest hariç), default 3

echo "📦 Registry: $REGISTRY"
echo "📁 Project: $HARBOR_PROJECT"
echo "🔢 Keeping last $KEEP_COUNT tags + latest"
echo ""

SERVICES=(
    "flowfish-backend"
    "flowfish-frontend"
    "flowfish-api-gateway"
    "flowfish-cluster-manager"
    "flowfish-analysis-orchestrator"
    "flowfish-graph-writer"
    "flowfish-graph-query"
    "flowfish-timeseries-writer"
    "flowfish-timeseries-query"
    "flowfish-ingestion-service"
    "flowfish-change-worker"
)

# Local cleanup counter
LOCAL_DELETED=0
HARBOR_DELETED=0

# ==============================================================================
# PART 1: Local Image Cleanup (Build Agent)
# ==============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🖥️  LOCAL IMAGE CLEANUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

for service in "${SERVICES[@]}"; do
    echo ""
    echo "📋 Cleaning local: $service"
    
    # List current images (exclude latest, keep last 3)
    images=$(podman images --format "{{.Repository}}:{{.Tag}}" \
        --filter "reference=$REGISTRY/$HARBOR_PROJECT/$service" 2>/dev/null | \
        grep -v ":latest$" | \
        sort -r)
    
    if [ -z "$images" ]; then
        echo "   No local images found"
        continue
    fi
    
    count=0
    while IFS= read -r image; do
        count=$((count + 1))
        if [ $count -le $KEEP_COUNT ]; then
            echo "   ✅ Keep: $image"
        else
            echo "   🗑️  Remove: $image"
            podman rmi "$image" 2>/dev/null && LOCAL_DELETED=$((LOCAL_DELETED + 1)) || true
        fi
    done <<< "$images"
done

# ==============================================================================
# PART 2: Harbor Registry Cleanup (via API)
# ==============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐 HARBOR REGISTRY CLEANUP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Harbor credentials check
if [ -z "${HARBOR_USER}" ] || [ -z "${HARBOR_PASSWORD}" ]; then
    echo "⚠️  Harbor credentials not set, skipping registry cleanup"
    echo "   Set HARBOR_USER and HARBOR_PASSWORD to enable"
else
    HARBOR_API="https://${REGISTRY}/api/v2.0"
    # Use printf for consistent base64 encoding (echo -n can be inconsistent)
    AUTH=$(printf '%s:%s' "${HARBOR_USER}" "${HARBOR_PASSWORD}" | base64 | tr -d '\n')
    
    echo "🔐 Testing Harbor API connection..."
    echo "   User: ${HARBOR_USER}"
    echo "   API: ${HARBOR_API}"
    
    for service in "${SERVICES[@]}"; do
        echo ""
        echo "📋 Cleaning Harbor: $service"
        
        # Get all artifacts (tags) for this repository
        # Harbor API: /projects/{project}/repositories/{repo}/artifacts
        REPO_URL="${HARBOR_API}/projects/${HARBOR_PROJECT}/repositories/${service}/artifacts?page_size=100"
        
        response=$(curl -s -k -H "Authorization: Basic ${AUTH}" \
            -H "Accept: application/json" \
            "$REPO_URL" 2>/dev/null)
        
        if [ -z "$response" ] || [ "$response" = "null" ]; then
            echo "   No artifacts found or API error"
            continue
        fi
        
        # Check if response is valid JSON array
        if ! echo "$response" | jq -e '.' >/dev/null 2>&1; then
            echo "   Invalid API response"
            continue
        fi
        
        # Parse artifacts - get digest and tags, sort by push_time
        # Keep latest tag and last N builds
        artifacts=$(echo "$response" | jq -r '
            sort_by(.push_time) | reverse |
            .[] | 
            select(.tags != null) |
            .digest as $digest |
            .tags[] |
            select(.name != "latest") |
            "\($digest)|\(.name)"
        ' 2>/dev/null)
        
        if [ -z "$artifacts" ]; then
            echo "   No deletable artifacts found"
            continue
        fi
        
        count=0
        while IFS= read -r line; do
            digest=$(echo "$line" | cut -d'|' -f1)
            tag=$(echo "$line" | cut -d'|' -f2)
            
            count=$((count + 1))
            if [ $count -le $KEEP_COUNT ]; then
                echo "   ✅ Keep: $tag"
            else
                echo "   🗑️  Delete from Harbor: $tag"
                
                # URL-encode the digest (sha256: contains colon)
                encoded_digest=$(echo "$digest" | sed 's/:/%3A/g')
                
                # Delete artifact by reference (tag name is simpler than digest)
                delete_url="${HARBOR_API}/projects/${HARBOR_PROJECT}/repositories/${service}/artifacts/${tag}"
                
                delete_response=$(curl -s -k -X DELETE \
                    -H "Authorization: Basic ${AUTH}" \
                    -H "Content-Type: application/json" \
                    -w "%{http_code}" \
                    -o /dev/null \
                    "$delete_url" 2>/dev/null)
                
                if [ "$delete_response" = "200" ] || [ "$delete_response" = "202" ] || [ "$delete_response" = "204" ]; then
                    echo "      ✅ Deleted successfully"
                    HARBOR_DELETED=$((HARBOR_DELETED + 1))
                elif [ "$delete_response" = "401" ]; then
                    echo "      ❌ Auth failed (401) - Check user permissions in Harbor"
                elif [ "$delete_response" = "403" ]; then
                    echo "      ❌ Forbidden (403) - User lacks delete permission"
                elif [ "$delete_response" = "404" ]; then
                    echo "      ⚠️  Not found (404) - Already deleted or doesn't exist"
                else
                    echo "      ⚠️  Failed (HTTP $delete_response)"
                fi
            fi
        done <<< "$artifacts"
    done
fi

# ==============================================================================
# PART 3: Clean only Flowfish dangling/untagged images (SAFE - project specific)
# ==============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 CLEANING FLOWFISH UNTAGGED IMAGES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Only remove untagged images that belong to Flowfish project
# This is SAFE - won't affect other projects
FLOWFISH_DANGLING=0

# Find and remove untagged Flowfish images (images with <none> tag)
for service in "${SERVICES[@]}"; do
    # Find images with <none> tag for this specific service
    dangling=$(podman images --format "{{.ID}} {{.Repository}}" 2>/dev/null | \
        grep "$REGISTRY/$HARBOR_PROJECT/$service" | \
        grep "<none>" | \
        awk '{print $1}' || true)
    
    if [ -n "$dangling" ]; then
        while IFS= read -r image_id; do
            if [ -n "$image_id" ]; then
                echo "   🗑️  Removing untagged: $service ($image_id)"
                podman rmi "$image_id" 2>/dev/null && FLOWFISH_DANGLING=$((FLOWFISH_DANGLING + 1)) || true
            fi
        done <<< "$dangling"
    fi
done

# Also clean any image that starts with flowfish- and has no tag
other_flowfish=$(podman images --format "{{.ID}} {{.Repository}}:{{.Tag}}" 2>/dev/null | \
    grep -E "(flowfish-|/flowfish/)" | \
    grep "<none>" | \
    awk '{print $1}' || true)

if [ -n "$other_flowfish" ]; then
    while IFS= read -r image_id; do
        if [ -n "$image_id" ]; then
            echo "   🗑️  Removing untagged flowfish image: $image_id"
            podman rmi "$image_id" 2>/dev/null && FLOWFISH_DANGLING=$((FLOWFISH_DANGLING + 1)) || true
        fi
    done <<< "$other_flowfish"
fi

echo "   ✅ Removed $FLOWFISH_DANGLING untagged Flowfish images"

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 CLEANUP SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🖥️  Local tagged images deleted: $LOCAL_DELETED"
echo "🖥️  Local untagged images deleted: $FLOWFISH_DANGLING"
echo "🌐 Harbor images deleted: $HARBOR_DELETED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Cleanup complete (only Flowfish images affected)"
