#!/bin/bash
#
# Inspektor Gadget DaemonSet Upgrade/Rollback Script
# 
# This script upgrades or rolls back Inspektor Gadget DaemonSet in existing clusters.
# Default upgrade target: v0.48.0 (CVE-2024-24790 fix)
# Rollback target: v0.46.0
#
# Usage:
#   Upgrade:   ./upgrade-gadget-daemonset.sh <namespace> [version] [registry]
#   Rollback:  ./upgrade-gadget-daemonset.sh <namespace> --rollback [registry]
#
# Environment Variables:
#   GADGET_REGISTRY  - Image registry (default: ghcr.io/inspektor-gadget)
#
# Examples:
#   # Using ghcr.io (default)
#   ./upgrade-gadget-daemonset.sh flowfish
#   ./upgrade-gadget-daemonset.sh flowfish v0.48.0
#   ./upgrade-gadget-daemonset.sh flowfish --rollback
#
#   # Using Harbor registry
#   ./upgrade-gadget-daemonset.sh flowfish v0.48.0 harbor.example.com/flowfish
#   ./upgrade-gadget-daemonset.sh flowfish --rollback harbor.example.com/flowfish
#
#   # Using environment variable
#   export GADGET_REGISTRY="harbor.example.com/flowfish"
#   ./upgrade-gadget-daemonset.sh flowfish v0.48.0
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${CYAN}$1${NC}"
}

show_usage() {
    echo "Usage: $0 <namespace> [version|--rollback] [registry]"
    echo ""
    echo "Arguments:"
    echo "  namespace     Kubernetes namespace where Inspektor Gadget is deployed"
    echo "  version       Target version (default: v0.48.0)"
    echo "  --rollback    Rollback to v0.46.0"
    echo "  registry      Image registry (default: ghcr.io/inspektor-gadget)"
    echo ""
    echo "Environment Variables:"
    echo "  GADGET_REGISTRY  Image registry override"
    echo ""
    echo "Examples:"
    echo "  # Using ghcr.io (default)"
    echo "  $0 flowfish                    # Upgrade to v0.48.0"
    echo "  $0 flowfish v0.48.0            # Upgrade to v0.48.0"
    echo "  $0 flowfish --rollback         # Rollback to v0.46.0"
    echo ""
    echo "  # Using Harbor registry"
    echo "  $0 flowfish v0.48.0 harbor.example.com/flowfish"
    echo "  $0 flowfish --rollback harbor.example.com/flowfish"
    echo ""
    echo "  # Using environment variable"
    echo "  export GADGET_REGISTRY=\"harbor.example.com/flowfish\""
    echo "  $0 flowfish v0.48.0"
    echo ""
}

# Default versions and registry
DEFAULT_UPGRADE_VERSION="v0.48.0"
DEFAULT_ROLLBACK_VERSION="v0.46.0"
DEFAULT_REGISTRY="ghcr.io/inspektor-gadget"

# Arguments
NAMESPACE="${1:-}"
TARGET_VERSION="${2:-$DEFAULT_UPGRADE_VERSION}"
REGISTRY_ARG="${3:-}"
IS_ROLLBACK=false

# Handle --rollback flag
if [ "$TARGET_VERSION" = "--rollback" ] || [ "$TARGET_VERSION" = "-r" ]; then
    # Check if registry is provided as 3rd argument
    REGISTRY_ARG="${3:-}"
    TARGET_VERSION="$DEFAULT_ROLLBACK_VERSION"
    IS_ROLLBACK=true
fi

# Determine registry: argument > environment variable > default
if [ -n "$REGISTRY_ARG" ]; then
    IMAGE_REGISTRY="$REGISTRY_ARG"
elif [ -n "$GADGET_REGISTRY" ]; then
    IMAGE_REGISTRY="$GADGET_REGISTRY"
else
    IMAGE_REGISTRY="$DEFAULT_REGISTRY"
fi

# Detect if this is a rollback based on version comparison
if [ "$TARGET_VERSION" = "v0.46.0" ]; then
    IS_ROLLBACK=true
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace not specified!"
    echo ""
    show_usage
    exit 1
fi

# Construct full image name
FULL_IMAGE="${IMAGE_REGISTRY}/inspektor-gadget:${TARGET_VERSION}"

# Determine operation type
if [ "$IS_ROLLBACK" = true ]; then
    OPERATION="ROLLBACK"
    OPERATION_COLOR="${YELLOW}"
else
    OPERATION="UPGRADE"
    OPERATION_COLOR="${GREEN}"
fi

echo ""
echo "================================================"
echo -e "Inspektor Gadget DaemonSet ${OPERATION_COLOR}${OPERATION}${NC}"
echo "================================================"
echo "Namespace:      $NAMESPACE"
echo "Target Version: $TARGET_VERSION"
echo "Registry:       $IMAGE_REGISTRY"
echo "Full Image:     $FULL_IMAGE"
if [ "$IS_ROLLBACK" = true ]; then
    echo "Mode:           ROLLBACK (downgrade)"
else
    echo "Mode:           UPGRADE"
fi
echo "================================================"
echo ""

# Check if kubectl/oc is available
if command -v oc &> /dev/null; then
    KUBE_CMD="oc"
elif command -v kubectl &> /dev/null; then
    KUBE_CMD="kubectl"
else
    print_error "kubectl or oc not found!"
    exit 1
fi

print_status "Using CLI: $KUBE_CMD"

# Check if logged in / has access
if ! $KUBE_CMD auth can-i get daemonsets -n "$NAMESPACE" &>/dev/null; then
    print_error "No access to namespace $NAMESPACE. Please login first."
    exit 1
fi

# Check if DaemonSet exists
if ! $KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" &>/dev/null; then
    print_error "inspektor-gadget DaemonSet not found in namespace: $NAMESPACE"
    exit 1
fi

# Get current version
CURRENT_IMAGE=$($KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].image}')
print_status "Current image: $CURRENT_IMAGE"

# Extract current version from image tag
CURRENT_VERSION=$(echo "$CURRENT_IMAGE" | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
print_status "Current version: $CURRENT_VERSION"

# Check if already at target version
if [ "$CURRENT_IMAGE" = "$FULL_IMAGE" ]; then
    print_success "DaemonSet is already using image: $FULL_IMAGE"
    exit 0
fi

# Show current pods
print_status "Current pods:"
$KUBE_CMD get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide

# Get node count and ready pods
DESIRED=$($KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.status.desiredNumberScheduled}')
READY=$($KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.status.numberReady}')
print_status "DaemonSet status: $READY/$DESIRED pods ready"

# Confirm operation
echo ""
if [ "$IS_ROLLBACK" = true ]; then
    print_warning "About to ROLLBACK DaemonSet"
    print_warning "  From: $CURRENT_IMAGE"
    print_warning "  To:   $FULL_IMAGE"
else
    print_warning "About to UPGRADE DaemonSet"
    print_warning "  From: $CURRENT_IMAGE"
    print_warning "  To:   $FULL_IMAGE"
fi
print_warning "This will restart all Inspektor Gadget pods (rolling update)"
echo ""
read -p "Do you want to continue? (y/N): " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    print_status "Cancelled."
    exit 0
fi

# Save current state for potential rollback info
PREVIOUS_IMAGE="$CURRENT_IMAGE"
PREVIOUS_VERSION="$CURRENT_VERSION"

# Update DaemonSet image
print_status "Updating DaemonSet image to: $FULL_IMAGE"
$KUBE_CMD set image daemonset/inspektor-gadget \
    gadget="$FULL_IMAGE" \
    -n "$NAMESPACE"

# Also update GADGET_IMAGE environment variable if it exists
if $KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="GADGET_IMAGE")]}' | grep -q "GADGET_IMAGE"; then
    print_status "Updating GADGET_IMAGE environment variable..."
    # Remove the tag from the image for GADGET_IMAGE env var
    GADGET_IMAGE_VALUE="${IMAGE_REGISTRY}/inspektor-gadget:${TARGET_VERSION}"
    $KUBE_CMD set env daemonset/inspektor-gadget \
        GADGET_IMAGE="$GADGET_IMAGE_VALUE" \
        -n "$NAMESPACE" 2>/dev/null || true
fi

# Handle AppArmor based on K8s version and target version
# For K8s 1.30+, we need appArmorProfile in securityContext
if [ "$IS_ROLLBACK" = false ]; then
    # UPGRADE: Check for deprecated AppArmor annotation and patch
    if $KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.metadata.annotations}' 2>/dev/null | grep -q "container.apparmor.security.beta.kubernetes.io"; then
        print_warning "Deprecated AppArmor annotation detected (K8s 1.30+ deprecation)"
        print_status "Patching securityContext with appArmorProfile..."
        
        PATCH='{"spec":{"template":{"spec":{"containers":[{"name":"gadget","securityContext":{"appArmorProfile":{"type":"Unconfined"}}}]}}}}'
        if $KUBE_CMD patch daemonset inspektor-gadget -n "$NAMESPACE" --type=strategic -p "$PATCH" 2>/dev/null; then
            print_success "AppArmor securityContext patched successfully"
        else
            print_warning "Could not patch AppArmor securityContext automatically"
            echo "  Note: K8s 1.30+ requires appArmorProfile in securityContext"
        fi
    fi
fi

# Wait for rollout
print_status "Waiting for rollout to complete..."
if $KUBE_CMD rollout status daemonset/inspektor-gadget -n "$NAMESPACE" --timeout=300s; then
    print_success "Rollout completed successfully!"
else
    print_error "Rollout timed out or failed!"
    echo ""
    print_warning "To rollback to previous image, run:"
    echo "  $0 $NAMESPACE $PREVIOUS_VERSION ${IMAGE_REGISTRY}"
    echo ""
    print_status "Checking pod status..."
    $KUBE_CMD get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide
    exit 1
fi

# Verify
print_status "Verifying update..."
NEW_IMAGE=$($KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].image}')

if [ "$NEW_IMAGE" = "$FULL_IMAGE" ]; then
    print_success "Image updated successfully: $NEW_IMAGE"
else
    print_error "Image verification failed."
    print_error "  Expected: $FULL_IMAGE"
    print_error "  Got:      $NEW_IMAGE"
    echo ""
    print_warning "To rollback to previous image, run:"
    echo "  $0 $NAMESPACE $PREVIOUS_VERSION ${IMAGE_REGISTRY}"
    exit 1
fi

# Show updated pods
echo ""
print_status "Updated pods:"
$KUBE_CMD get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide

# Check pod health
READY_NEW=$($KUBE_CMD get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.status.numberReady}')
if [ "$READY_NEW" = "$DESIRED" ]; then
    print_success "All $READY_NEW/$DESIRED pods are ready!"
else
    print_warning "Only $READY_NEW/$DESIRED pods are ready. Please check pod status."
    echo ""
    print_warning "If pods are failing, rollback with:"
    echo "  $0 $NAMESPACE $PREVIOUS_VERSION ${IMAGE_REGISTRY}"
fi

# Test kubectl-gadget connection
echo ""
print_status "Testing gadget connectivity..."
if timeout 10 $KUBE_CMD gadget version 2>/dev/null; then
    print_success "kubectl-gadget connection successful!"
else
    print_warning "kubectl-gadget test skipped or failed - manual verification recommended"
    echo "  Run: kubectl gadget trace dns -n $NAMESPACE --timeout 5"
fi

# Final summary
echo ""
echo "================================================"
if [ "$IS_ROLLBACK" = true ]; then
    print_success "Inspektor Gadget ROLLBACK to $TARGET_VERSION completed!"
else
    print_success "Inspektor Gadget UPGRADE to $TARGET_VERSION completed!"
fi
echo "================================================"
echo ""

# Show checklist and rollback info
print_header "Post-update checklist:"
echo "  [x] DaemonSet image updated to: $FULL_IMAGE"
echo "  [ ] Verify all pods are Running:"
echo "      kubectl get pods -l app=inspektor-gadget -n $NAMESPACE"
echo "  [ ] Test trace functionality:"
echo "      kubectl gadget trace dns -n $NAMESPACE --timeout 5"
echo "  [ ] Check pod logs for errors:"
echo "      kubectl logs -l app=inspektor-gadget -n $NAMESPACE --tail=50"
echo ""

# Always show rollback command
if [ "$IS_ROLLBACK" = true ]; then
    print_header "To upgrade back to v0.48.0:"
    echo "  $0 $NAMESPACE v0.48.0 ${IMAGE_REGISTRY}"
else
    print_header "If you encounter issues, rollback with:"
    echo "  $0 $NAMESPACE --rollback ${IMAGE_REGISTRY}"
    echo "  # or explicitly:"
    echo "  $0 $NAMESPACE $PREVIOUS_VERSION ${IMAGE_REGISTRY}"
fi
echo ""
