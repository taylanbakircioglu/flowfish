#!/bin/bash
#
# Inspektor Gadget Quick Deploy Script for OpenShift
# 
# This script deploys Inspektor Gadget with:
# - Trace CRD
# - RBAC (Cluster-scoped)
# - ConfigMap
# - DaemonSet with gRPC enabled
#
# Prerequisites:
# - oc CLI installed and logged in
# - Cluster-admin permissions
# - OPENSHIFT_NAMESPACE environment variable set
#
# Usage:
#   export OPENSHIFT_NAMESPACE="your-namespace"
#   ./deploy-inspektor-gadget.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Check if OPENSHIFT_NAMESPACE is set
if [ -z "$OPENSHIFT_NAMESPACE" ]; then
    print_error "OPENSHIFT_NAMESPACE environment variable is not set!"
    echo "Usage: export OPENSHIFT_NAMESPACE=\"your-namespace\" && $0"
    exit 1
fi

print_status "Deploying Inspektor Gadget to namespace: $OPENSHIFT_NAMESPACE"
echo ""

# Check if oc is available
if ! command -v oc &> /dev/null; then
    print_error "oc CLI is not installed or not in PATH"
    exit 1
fi

# Check if logged in
if ! oc whoami &> /dev/null; then
    print_error "Not logged in to OpenShift. Please run 'oc login' first."
    exit 1
fi

# Check if namespace exists
if ! oc get namespace "$OPENSHIFT_NAMESPACE" &> /dev/null; then
    print_error "Namespace '$OPENSHIFT_NAMESPACE' does not exist!"
    echo "Create it first with: oc create namespace $OPENSHIFT_NAMESPACE"
    exit 1
fi

print_status "Pre-flight checks passed"
echo ""

#
# Step 1: Apply Trace CRD
#
print_status "1/5 - Applying Trace CRD..."
if oc apply -f 09-inspektor-gadget-crds.yaml; then
    print_success "Trace CRD applied successfully"
else
    print_error "Failed to apply Trace CRD"
    exit 1
fi

# Verify CRD
if oc get crd traces.gadget.kinvolk.io &> /dev/null; then
    print_success "Trace CRD verified: traces.gadget.kinvolk.io"
else
    print_error "Trace CRD not found after apply"
    exit 1
fi
echo ""

#
# Step 2: Apply RBAC (requires cluster-admin)
#
print_status "2/5 - Applying RBAC (ClusterRole & ClusterRoleBinding)..."
if sed "s/{{OPENSHIFT_NAMESPACE}}/$OPENSHIFT_NAMESPACE/g" \
    10-inspektor-gadget-rbac-cluster.yaml | oc apply -f -; then
    print_success "RBAC applied successfully"
else
    print_error "Failed to apply RBAC (cluster-admin permissions required)"
    exit 1
fi

# Verify RBAC
if oc get clusterrole inspektor-gadget &> /dev/null; then
    print_success "ClusterRole verified: inspektor-gadget"
else
    print_error "ClusterRole not found after apply"
    exit 1
fi

if oc get clusterrolebinding inspektor-gadget &> /dev/null; then
    print_success "ClusterRoleBinding verified: inspektor-gadget"
else
    print_error "ClusterRoleBinding not found after apply"
    exit 1
fi
echo ""

#
# Step 3: Create ConfigMap
#
print_status "3/5 - Creating ConfigMap..."
if sed "s/{{OPENSHIFT_NAMESPACE}}/$OPENSHIFT_NAMESPACE/g" \
    09-inspektor-gadget-config.yaml | oc apply -f -; then
    print_success "ConfigMap created successfully"
else
    print_error "Failed to create ConfigMap"
    exit 1
fi

# Verify ConfigMap
if oc get configmap inspektor-gadget-config -n "$OPENSHIFT_NAMESPACE" &> /dev/null; then
    print_success "ConfigMap verified: inspektor-gadget-config"
else
    print_error "ConfigMap not found after apply"
    exit 1
fi
echo ""

#
# Step 4: Deploy DaemonSet
#
print_status "4/5 - Deploying DaemonSet..."
if sed "s/{{OPENSHIFT_NAMESPACE}}/$OPENSHIFT_NAMESPACE/g" \
    10-inspektor-gadget.yaml | oc apply -f -; then
    print_success "DaemonSet applied successfully"
else
    print_error "Failed to apply DaemonSet"
    exit 1
fi
echo ""

#
# Step 5: Restart pods (if already running)
#
print_status "5/5 - Restarting Inspektor Gadget pods..."
POD_COUNT=$(oc get pods -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" --no-headers 2>/dev/null | wc -l)

if [ "$POD_COUNT" -gt 0 ]; then
    print_status "Found $POD_COUNT existing pod(s), restarting..."
    if oc delete pods -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE"; then
        print_success "Pods deleted (will be recreated automatically)"
    else
        print_warning "Failed to delete pods, but they may restart automatically"
    fi
else
    print_status "No existing pods found, DaemonSet will create them"
fi
echo ""

#
# Wait for pods to be ready
#
print_status "Waiting for pods to be ready..."
if oc wait --for=condition=ready pod -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" --timeout=120s 2>/dev/null; then
    print_success "All pods are ready!"
else
    print_warning "Timeout waiting for pods, checking status..."
fi
echo ""

#
# Show deployment status
#
print_status "Deployment Status:"
echo ""
echo "Pods:"
oc get pods -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" -o wide
echo ""

#
# Check logs for errors
#
print_status "Checking pod logs for errors..."
ERROR_COUNT=$(oc logs -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" --tail=50 2>/dev/null | grep -c "level=error" || true)

if [ "$ERROR_COUNT" -gt 0 ]; then
    print_warning "Found $ERROR_COUNT error(s) in logs"
    echo ""
    echo "Recent logs:"
    oc logs -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" --tail=20
else
    print_success "No errors found in logs!"
    echo ""
    echo "✅ Key log entries:"
    oc logs -l app=inspektor-gadget -n "$OPENSHIFT_NAMESPACE" --tail=100 2>/dev/null | grep -E "(Starting trace controller|Serving on gRPC|grpc:)" | head -5
fi
echo ""

#
# Final summary
#
print_success "========================================="
print_success "Inspektor Gadget Deployment Complete! 🎉"
print_success "========================================="
echo ""
echo "📋 Deployment Summary:"
echo "  • CRD:              traces.gadget.kinvolk.io"
echo "  • ClusterRole:      inspektor-gadget"
echo "  • ClusterRoleBinding: inspektor-gadget"
echo "  • ConfigMap:        inspektor-gadget-config"
echo "  • DaemonSet:        inspektor-gadget"
echo "  • Namespace:        $OPENSHIFT_NAMESPACE"
echo ""
echo "🔍 Useful Commands:"
echo "  Check pods:   oc get pods -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE"
echo "  View logs:    oc logs -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE --tail=50"
echo "  Describe:     oc describe daemonset inspektor-gadget -n $OPENSHIFT_NAMESPACE"
echo "  Port-forward: oc port-forward -n $OPENSHIFT_NAMESPACE svc/inspektor-gadget 16060:16060"
echo ""
echo "🎯 gRPC Endpoint:"
echo "  Service:      inspektor-gadget.$OPENSHIFT_NAMESPACE:16060"
echo "  Protocol:     gRPC (plaintext)"
echo ""
echo "✅ Your Inspektor Gadget is ready for eBPF tracing!"

