#!/bin/bash
# Push Inspektor Gadget OCI images to local registry
# Skips images that already exist in the target registry
#
# NOTE: This script mirrors OCI gadget images (trace_network, trace_dns, etc.)
# The main DaemonSet image (inspektor-gadget:vX.Y.Z) is pushed manually to Harbor.

set -e

echo "================================================"
echo "Pushing Inspektor Gadget OCI Images to Registry"
echo "================================================"

# Configuration - GADGET_VERSION must be set externally
if [ -z "${GADGET_VERSION}" ]; then
    echo "ERROR: GADGET_VERSION environment variable must be set"
    echo "  Example: export GADGET_VERSION=v0.50.1"
    exit 1
fi

SOURCE_REGISTRY="ghcr.io/inspektor-gadget/gadget"
TARGET_REGISTRY="${HARBOR_REGISTRY}/${HARBOR_PROJECT:-flowfish}/gadget"

# List of gadgets to push
GADGETS=(
    "trace_network"
    "trace_dns"
    "trace_exec"
    "trace_tcp"
    "trace_open"
    "trace_capabilities"
    "trace_oomkill"
    "trace_bind"
    "trace_sni"
    "trace_mount"
    # Top gadgets for metrics/throughput data
    "top_tcp"         # TCP throughput (bytes sent/received per connection)
    "top_file"        # File I/O throughput
    "top_blockio"     # Block I/O throughput
)

echo "Source Registry: $SOURCE_REGISTRY"
echo "Target Registry: $TARGET_REGISTRY"
echo "Gadget Version: $GADGET_VERSION"
echo ""

# Check if we have Docker/Podman access
if command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
elif command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
else
    echo "WARNING: Neither docker nor podman found. Skipping gadget image push."
    echo "  Gadget images must be manually pushed to: $TARGET_REGISTRY"
    exit 0
fi

echo "Using container runtime: $CONTAINER_CMD"

# Login to target registry (if credentials provided)
if [ -n "$HARBOR_USER" ] && [ -n "$HARBOR_PASSWORD" ]; then
    echo "Logging into target registry..."
    echo "$HARBOR_PASSWORD" | $CONTAINER_CMD login "$HARBOR_REGISTRY" -u "$HARBOR_USER" --password-stdin
fi

# Track statistics
PUSHED=0
SKIPPED=0
FAILED=0

# Check for skopeo (required for multi-arch support)
USE_SKOPEO=false
if command -v skopeo &> /dev/null; then
    USE_SKOPEO=true
    echo "Using skopeo for multi-arch image copy (recommended)"
fi

echo ""
echo "================================================"
echo "Mirroring OCI gadget images"
echo "================================================"

for gadget in "${GADGETS[@]}"; do
    SOURCE_IMAGE="$SOURCE_REGISTRY/$gadget:$GADGET_VERSION"
    TARGET_IMAGE="$TARGET_REGISTRY/$gadget:$GADGET_VERSION"
    
    echo ""
    echo "Processing: $gadget"
    echo "  Source: $SOURCE_IMAGE"
    echo "  Target: $TARGET_IMAGE"
    
    # Check if image already exists in target registry
    if $CONTAINER_CMD manifest inspect "$TARGET_IMAGE" &>/dev/null; then
        echo "  [SKIP] Already exists in target registry"
        ((SKIPPED++))
        continue
    fi
    
    if [ "$USE_SKOPEO" = true ]; then
        # Use skopeo to preserve multi-arch manifest (OCI image index)
        # This is REQUIRED for Inspector Gadget v0.46.0+
        echo "  Copying with skopeo (preserving multi-arch manifest)..."
        SKOPEO_OPTS="--all"
        if [ -n "$HARBOR_USER" ] && [ -n "$HARBOR_PASSWORD" ]; then
            SKOPEO_OPTS="$SKOPEO_OPTS --dest-creds=$HARBOR_USER:$HARBOR_PASSWORD"
        fi
        if skopeo copy $SKOPEO_OPTS "docker://$SOURCE_IMAGE" "docker://$TARGET_IMAGE"; then
            echo "  [OK] Successfully copied (multi-arch)"
            ((PUSHED++))
        else
            echo "  [FAIL] Failed to copy"
            ((FAILED++))
        fi
    else
        # Fallback to docker/podman (WARNING: loses multi-arch support!)
        echo "  WARNING: Using $CONTAINER_CMD - multi-arch manifest will be lost!"
        echo "    Install 'skopeo' for proper multi-arch support (required for Inspector Gadget v0.46+)"
        
        # Try to pull from source
        echo "  Pulling from source..."
        if ! $CONTAINER_CMD pull "$SOURCE_IMAGE" 2>/dev/null; then
            echo "  [FAIL] Failed to pull from source (network access required)"
            ((FAILED++))
            continue
        fi
        
        # Tag for target registry
        echo "  Tagging..."
        $CONTAINER_CMD tag "$SOURCE_IMAGE" "$TARGET_IMAGE"
        
        # Push to target registry
        echo "  Pushing to target..."
        if $CONTAINER_CMD push "$TARGET_IMAGE"; then
            echo "  [OK] Successfully pushed (single-arch only)"
            ((PUSHED++))
        else
            echo "  [FAIL] Failed to push"
            ((FAILED++))
        fi
    fi
done

echo ""
echo "================================================"
echo "Gadget Image Push Summary"
echo "================================================"
echo "  Pushed:  $PUSHED"
echo "  Skipped: $SKIPPED (already exist)"
echo "  Failed:  $FAILED"
echo "================================================"

if [ $FAILED -gt 0 ]; then
    echo "WARNING: Some images failed. You may need to manually push them."
    echo "  Or ensure the build agent has access to ghcr.io"
fi
