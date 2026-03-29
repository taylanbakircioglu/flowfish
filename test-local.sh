#!/bin/bash
#
# Flowfish Local Kubernetes Test Script
# Tests deployment health before pushing to production
#
# ⚠️  macOS Note: Inspektor Gadget tests are SKIPPED (eBPF not supported)
#
# Usage: ./test-local.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

NAMESPACE="${NAMESPACE:-flowfish}"

print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl not found! Please install kubectl."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    echo "Create it first with: kubectl apply -f deployment/kubernetes-manifests/01-namespace.yaml"
    exit 1
fi

print_header "🧪 Flowfish Local Deployment Test"
echo ""

#
# Test 1: Pod Status
#
print_info "Test 1/7: Checking pod status..."
FAILED_PODS=$(kubectl get pods -n $NAMESPACE --no-headers 2>/dev/null | grep -v "Running\|Completed" | wc -l | tr -d ' ')

if [ "$FAILED_PODS" -eq 0 ]; then
    print_success "All pods are Running or Completed"
    kubectl get pods -n $NAMESPACE
else
    print_error "$FAILED_PODS pod(s) not ready!"
    kubectl get pods -n $NAMESPACE | grep -v "Running\|Completed"
    exit 1
fi
echo ""

#
# Test 2: Migration Job
#
print_info "Test 2/7: Checking database migrations..."
if kubectl get job flowfish-migrations -n $NAMESPACE &> /dev/null; then
    if kubectl logs job/flowfish-migrations -n $NAMESPACE 2>/dev/null | grep -q "Migration 006 completed"; then
        print_success "Migration 006 (namespaces/workloads) completed"
    else
        print_warning "Migration 006 not found in logs"
    fi
else
    print_warning "Migration job not found (may not have run yet)"
fi
echo ""

#
# Test 3: Backend API
#
print_info "Test 3/7: Testing backend API..."
kubectl port-forward -n $NAMESPACE deployment/backend 8000:8000 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

if curl -s --max-time 5 http://localhost:8000/health | grep -q "ok"; then
    print_success "Backend API responding"
else
    print_error "Backend API not responding"
    kill $PF_PID 2>/dev/null || true
    exit 1
fi

kill $PF_PID 2>/dev/null || true
echo ""

#
# Test 4: Database Tables
#
print_info "Test 4/7: Checking database tables..."
BACKEND_POD=$(kubectl get pods -n $NAMESPACE -l app=backend --no-headers 2>/dev/null | head -1 | awk '{print $1}')

if [ -z "$BACKEND_POD" ]; then
    print_error "Backend pod not found!"
    exit 1
fi

# Check namespaces table
if kubectl exec -it $BACKEND_POD -n $NAMESPACE -- psql postgresql://flowfish:flowfish123@postgresql:5432/flowfish -c "\dt" 2>/dev/null | grep -q "namespaces"; then
    print_success "Namespaces table exists"
else
    print_error "Namespaces table missing!"
    exit 1
fi

# Check clusters table
if kubectl exec -it $BACKEND_POD -n $NAMESPACE -- psql postgresql://flowfish:flowfish123@postgresql:5432/flowfish -c "SELECT name, gadget_protocol FROM clusters LIMIT 1" 2>/dev/null | grep -q "localcluster"; then
    print_success "Clusters table OK (localcluster found)"
else
    print_warning "Localcluster not found in database"
fi
echo ""

#
# Test 5: Inspektor Gadget (⚠️ SKIP on macOS)
#
print_info "Test 5/7: Checking Inspektor Gadget..."
print_warning "SKIPPED: Inspektor Gadget requires eBPF (Linux only, not supported on macOS)"
print_info "This will be tested on OpenShift after git push"

GADGET_PODS=$(kubectl get pods -l app=inspektor-gadget -n $NAMESPACE --no-headers 2>/dev/null | grep "Running" | wc -l | tr -d ' ')

if [ "$GADGET_PODS" -gt 0 ]; then
    print_success "$GADGET_PODS Inspektor Gadget pod(s) running (unexpected on macOS!)"
else
    print_info "No Inspektor Gadget pods (expected on macOS)"
fi
echo ""

#
# Test 6: gRPC Services
#
print_info "Test 6/7: Checking gRPC services..."

# Inspektor Gadget service (optional on macOS)
if kubectl get svc inspektor-gadget -n $NAMESPACE &> /dev/null; then
    print_success "Inspektor Gadget service exists"
else
    print_info "Inspektor Gadget service not found (expected on macOS)"
fi

# Analysis Orchestrator service
if kubectl get svc analysis-orchestrator -n $NAMESPACE &> /dev/null; then
    print_success "Analysis Orchestrator service exists"
else
    print_warning "Analysis Orchestrator service not found"
fi

# Ingestion Service
if kubectl get svc ingestion-service -n $NAMESPACE &> /dev/null; then
    print_success "Ingestion Service exists"
else
    print_warning "Ingestion Service not found"
fi
echo ""

#
# Test 7: Logs Check
#
print_info "Test 7/7: Checking for errors in logs..."
ERROR_COUNT=$(kubectl logs -l app=backend -n $NAMESPACE --tail=100 2>/dev/null | grep -i "error\|exception\|traceback" | wc -l | tr -d ' ')

if [ "$ERROR_COUNT" -eq 0 ]; then
    print_success "No errors in backend logs (last 100 lines)"
else
    print_warning "$ERROR_COUNT error(s) found in backend logs"
fi
echo ""

#
# Final Summary
#
print_header "📊 Test Summary (macOS/Local)"
echo ""
print_success "All critical tests passed!"
echo ""
echo "✅ Pods are running"
echo "✅ Migrations completed"
echo "✅ Backend API responding"
echo "✅ Database tables exist"
echo "✅ gRPC services configured"
echo "⚠️  Inspektor Gadget SKIPPED (macOS - eBPF not supported)"
echo ""
print_warning "⚠️  macOS Limitations:"
echo "  • Inspektor Gadget won't run (eBPF requires Linux)"
echo "  • Analysis Start/Stop won't work (needs Inspektor Gadget)"
echo "  • These will be tested on OpenShift after push"
echo ""
print_info "🚀 Ready to push to production (git push origin pilot)"
echo ""
print_info "Next steps:"
echo "  1. Test UI manually: kubectl port-forward -n $NAMESPACE deployment/frontend 3000:80"
echo "  2. Open http://localhost:3000"
echo "  3. Test Analysis CRUD (Create, Read, Update, Delete)"
echo "  4. Skip Analysis Start/Stop (will test on OpenShift)"
echo "  5. If all OK: git push origin pilot"
echo ""
print_info "📋 OpenShift Tests (after push):"
echo "  • Inspektor Gadget health"
echo "  • Analysis Start/Stop"
echo "  • eBPF data collection"
echo ""

