#!/bin/bash
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Inspektor Gadget RBAC Fix Script                                         ║
# ║                                                                           ║
# ║  This script fixes the missing RBAC permissions for batch API group       ║
# ║  (jobs, cronjobs) that causes kubernetes enricher errors and core dump   ║
# ║  files (core-ocihookgadget-*) filling up node disks.                     ║
# ║                                                                           ║
# ║  Root Cause:                                                              ║
# ║  - Gadget's kubernetes enricher fails to get owner references for Jobs   ║
# ║  - This causes OCI hook to crash (SIGABRT) and generate core dumps       ║
# ║  - Core dumps accumulate on node's /var directory                        ║
# ║                                                                           ║
# ║  Solution:                                                                ║
# ║  - Add batch API group (jobs, cronjobs) permissions to ClusterRole       ║
# ║  - Clean up existing core dump files (separate operation)                ║
# ║  - Restart gadget pods to apply new permissions                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   chmod +x fix-gadget-rbac.sh
#   ./fix-gadget-rbac.sh <namespace>
#
# Requirements:
#   - oc or kubectl CLI installed and logged in
#   - cluster-admin privileges (for ClusterRole modification)
#
# Examples:
#   ./fix-gadget-rbac.sh bmprod-flowfish
#   ./fix-gadget-rbac.sh flowfish
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_header() { echo -e "\n${CYAN}${BOLD}═══ $1 ═══${NC}\n"; }

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║         Inspektor Gadget RBAC Fix Script                                  ║"
echo "║                                                                           ║"
echo "║  Fixes: kubernetes enricher forbidden error for batch/jobs               ║"
echo "║  Prevents: core-ocihookgadget-* files filling node disks                 ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Pre-flight Checks
# ═══════════════════════════════════════════════════════════════════════════
print_header "Pre-flight Checks"

# Detect CLI tool
if command -v oc &> /dev/null; then
    CLI_TOOL="oc"
elif command -v kubectl &> /dev/null; then
    CLI_TOOL="kubectl"
else
    print_error "Neither oc nor kubectl CLI found!"
    exit 1
fi
print_success "$CLI_TOOL CLI found"

# Check login
if ! $CLI_TOOL whoami &> /dev/null 2>&1; then
    if ! $CLI_TOOL auth can-i get pods &> /dev/null 2>&1; then
        print_error "Not logged in. Please run '$CLI_TOOL login' first."
        exit 1
    fi
fi
CURRENT_USER=$($CLI_TOOL whoami 2>/dev/null || echo "service-account")
print_success "Logged in as: $CURRENT_USER"

# Check cluster-admin
if ! $CLI_TOOL auth can-i patch clusterrole &> /dev/null; then
    print_error "You need cluster-admin privileges to run this script"
    exit 1
fi
print_success "Cluster-admin privileges confirmed"

# Get namespace
NAMESPACE="${1:-}"
if [ -z "$NAMESPACE" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    read -p "Enter namespace where Inspektor Gadget is deployed: " NAMESPACE
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

if [ -z "$NAMESPACE" ]; then
    print_error "Namespace cannot be empty!"
    exit 1
fi

# Check namespace exists
if ! $CLI_TOOL get namespace "$NAMESPACE" &> /dev/null; then
    print_error "Namespace '$NAMESPACE' does not exist!"
    exit 1
fi
print_success "Namespace '$NAMESPACE' exists"

# Check if gadget is deployed
if ! $CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" &> /dev/null; then
    print_error "Inspektor Gadget DaemonSet not found in namespace '$NAMESPACE'"
    exit 1
fi
print_success "Inspektor Gadget DaemonSet found"

# ═══════════════════════════════════════════════════════════════════════════
# Check Current RBAC Status
# ═══════════════════════════════════════════════════════════════════════════
print_header "Checking Current RBAC Status"

# Check if batch permission already exists
BATCH_PERM=$($CLI_TOOL get clusterrole inspektor-gadget -o jsonpath='{.rules[?(@.apiGroups[0]=="batch")].resources}' 2>/dev/null || echo "")

if [ -n "$BATCH_PERM" ] && echo "$BATCH_PERM" | grep -q "jobs"; then
    print_success "batch/jobs permission already exists in ClusterRole"
    echo ""
    print_status "Current batch permissions: $BATCH_PERM"
    echo ""
    
    # Still check for errors in logs
    print_status "Checking for recent forbidden errors in gadget logs..."
    ERROR_COUNT=$($CLI_TOOL logs -l app=inspektor-gadget -n "$NAMESPACE" --tail=500 2>/dev/null | grep "forbidden.*jobs" | wc -l | tr -d ' ')
    ERROR_COUNT=${ERROR_COUNT:-0}
    
    if [ "$ERROR_COUNT" -eq 0 ] 2>/dev/null; then
        print_success "No forbidden errors found. RBAC is correctly configured."
        echo ""
        print_warning "If core dump files still exist, they are from before the fix."
        print_warning "Run the cleanup commands provided by this script on affected nodes."
        exit 0
    else
        print_warning "Found $ERROR_COUNT forbidden errors. Pods may need restart."
    fi
else
    print_warning "batch/jobs permission NOT found in ClusterRole"
    print_status "This is the root cause of the core dump issue"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Apply RBAC Fix
# ═══════════════════════════════════════════════════════════════════════════
print_header "Applying RBAC Fix"

print_status "Patching ClusterRole 'inspektor-gadget' to add batch API permissions..."

# Create the updated ClusterRole
cat <<'EOF' | $CLI_TOOL apply -f -
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: inspektor-gadget
rules:
# Core resources - for kubernetes enricher
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces", "configmaps", "services", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["create", "update", "patch", "delete"]
# Apps resources - for owner reference enrichment
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
# Batch resources - REQUIRED for kubernetes enricher to resolve owner references
# Without this, gadget crashes when processing containers from Jobs/CronJobs
# causing core dump files (core-ocihookgadget-*) that fill up node disks
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch"]
# Gadget traces CRD
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get", "list", "watch"]
EOF

if [ $? -eq 0 ]; then
    print_success "ClusterRole updated successfully"
else
    print_error "Failed to update ClusterRole"
    exit 1
fi

# Verify the fix
print_status "Verifying RBAC update..."
BATCH_PERM_NEW=$($CLI_TOOL get clusterrole inspektor-gadget -o jsonpath='{.rules[?(@.apiGroups[0]=="batch")].resources}' 2>/dev/null || echo "")
if echo "$BATCH_PERM_NEW" | grep -q "jobs"; then
    print_success "Verified: batch/jobs permission now exists"
else
    print_error "Verification failed: batch/jobs permission not found"
    exit 1
fi

# ═══════════════════════════════════════════════════════════════════════════
# Restart Gadget Pods
# ═══════════════════════════════════════════════════════════════════════════
print_header "Restarting Gadget Pods"

print_status "Current pod status:"
$CLI_TOOL get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide

echo ""
read -p "Do you want to restart gadget pods to apply new permissions? (y/N): " RESTART_CONFIRM

if [[ "$RESTART_CONFIRM" =~ ^[Yy]$ ]]; then
    print_status "Restarting gadget pods..."
    $CLI_TOOL delete pods -l app=inspektor-gadget -n "$NAMESPACE" --wait=false
    
    print_status "Waiting for pods to restart (timeout: 180s)..."
    sleep 5
    
    if $CLI_TOOL wait --for=condition=ready pod -l app=inspektor-gadget -n "$NAMESPACE" --timeout=180s 2>/dev/null; then
        print_success "All gadget pods are ready!"
    else
        print_warning "Timeout waiting for pods. Check status manually:"
        print_warning "  $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
    fi
    
    echo ""
    print_status "New pod status:"
    $CLI_TOOL get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide
else
    print_warning "Pods not restarted. New permissions will apply after next pod restart."
fi

# ═══════════════════════════════════════════════════════════════════════════
# Verify Fix
# ═══════════════════════════════════════════════════════════════════════════
print_header "Verification"

print_status "Checking for forbidden errors in recent logs..."
sleep 3

# Use grep with single count output (avoid multi-line count from multiple pods)
ERROR_COUNT=$($CLI_TOOL logs -l app=inspektor-gadget -n "$NAMESPACE" --tail=100 --since=1m 2>/dev/null | grep "forbidden.*jobs" | wc -l | tr -d ' ')
ERROR_COUNT=${ERROR_COUNT:-0}

if [ "$ERROR_COUNT" -eq 0 ] 2>/dev/null; then
    print_success "No forbidden errors in recent logs!"
else
    print_warning "Still seeing $ERROR_COUNT forbidden errors. Pods may still be initializing."
    print_warning "Wait a few minutes and check again with:"
    print_warning "  $CLI_TOOL logs -l app=inspektor-gadget -n $NAMESPACE --tail=100 | grep forbidden"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Completion and Cleanup Instructions
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                           ║"
echo "║   ✅ RBAC FIX COMPLETE                                                    ║"
echo "║                                                                           ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 📋 SUMMARY                                                                   │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ ✅ ClusterRole 'inspektor-gadget' updated with batch/jobs permission       │"
echo "│ ✅ Gadget can now resolve owner references for Jobs and CronJobs           │"
echo "│ ✅ kubernetes enricher will no longer crash on batch workloads             │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ ⚠️  IMPORTANT: CORE DUMP CLEANUP REQUIRED                                   │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│                                                                             │"
echo "│ Existing core dump files must be cleaned up manually on affected nodes.    │"
echo "│ Send these commands to your infrastructure team:                           │"
echo "│                                                                             │"
echo "│ 1. Check disk usage and core dump files:                                   │"
echo "│    find /var -name 'core-ocihookgadget*' -type f 2>/dev/null | wc -l      │"
echo "│    du -sh /var/lib/systemd/coredump/ 2>/dev/null                          │"
echo "│                                                                             │"
echo "│ 2. Clean up core dump files (run on each affected node):                   │"
echo "│    # List files first                                                      │"
echo "│    find /var -name 'core-ocihookgadget*' -type f -ls 2>/dev/null          │"
echo "│                                                                             │"
echo "│    # Delete files (AFTER VERIFICATION)                                     │"
echo "│    find /var -name 'core-ocihookgadget*' -type f -delete 2>/dev/null      │"
echo "│                                                                             │"
echo "│ 3. Also check and clean systemd-coredump storage:                          │"
echo "│    coredumpctl list 2>/dev/null | grep ocihookgadget                       │"
echo "│    rm -f /var/lib/systemd/coredump/core.ocihookgadget.* 2>/dev/null       │"
echo "│                                                                             │"
echo "│ 4. Verify disk space recovered:                                            │"
echo "│    df -h /var                                                              │"
echo "│                                                                             │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ 🔍 MONITORING COMMANDS                                                      │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ Check for RBAC errors:                                                      │"
echo "│   $CLI_TOOL logs -l app=inspektor-gadget -n $NAMESPACE --tail=100 | grep forbidden"
echo "│                                                                             │"
echo "│ Monitor pod health:                                                         │"
echo "│   $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE -w              │"
echo "│                                                                             │"
echo "│ View recent logs:                                                           │"
echo "│   $CLI_TOOL logs -l app=inspektor-gadget -n $NAMESPACE --tail=50           │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
print_success "RBAC fix applied. Please ensure core dump cleanup is performed on affected nodes."
echo ""
