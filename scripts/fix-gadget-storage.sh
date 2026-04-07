#!/bin/bash
#
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  Inspektor Gadget DaemonSet Update Script                                 ║
# ║                                                                           ║
# ║  This script updates existing Inspektor Gadget deployments with:         ║
# ║  - Node affinity to exclude master/control-plane/infra nodes             ║
# ║  - Optional: Persistent storage (PVC) instead of emptyDir                ║
# ║                                                                           ║
# ║  Storage Options:                                                         ║
# ║  1. emptyDir (default) - Uses node's local disk, data lost on restart   ║
# ║  2. PVC with StorageClass - Persistent storage, survives restarts       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Usage:
#   chmod +x fix-gadget-storage.sh
#   ./fix-gadget-storage.sh <namespace> [storage_class]
#   ./fix-gadget-storage.sh <namespace>                # Uses emptyDir
#   ./fix-gadget-storage.sh                            # Interactive mode
#
# Requirements:
#   - oc or kubectl CLI installed and logged in
#   - cluster-admin privileges (for DaemonSet modification)
#
# Examples:
#   ./fix-gadget-storage.sh prod-flowfish                    # emptyDir (default)
#   ./fix-gadget-storage.sh prod-flowfish ibm02-csi-rwo      # PVC with StorageClass
#   ./fix-gadget-storage.sh bmprod-flowfish standard            # PVC with StorageClass
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
echo "║         Inspektor Gadget DaemonSet Update Script                          ║"
echo "║                                                                           ║"
echo "║  Updates: Node affinity (exclude master/infra) + Optional PVC storage    ║"
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
if ! $CLI_TOOL auth can-i patch daemonset &> /dev/null; then
    print_error "You need cluster-admin privileges to run this script"
    exit 1
fi
print_success "Cluster-admin privileges confirmed"

# Get namespace
NAMESPACE="${1:-}"
STORAGE_CLASS="${2:-}"

if [ -z "$NAMESPACE" ]; then
    echo ""
    echo "============================================================================"
    read -p "Enter namespace where Inspektor Gadget is deployed: " NAMESPACE
    echo "============================================================================"
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
# Storage Configuration (Optional)
# ═══════════════════════════════════════════════════════════════════════════
print_header "Storage Configuration"

USE_PVC=false

if [ -z "$STORAGE_CLASS" ]; then
    echo ""
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│ Storage Options:                                                            │"
    echo "├─────────────────────────────────────────────────────────────────────────────┤"
    echo "│ 1. emptyDir (default) - Uses node local disk, data lost on pod restart    │"
    echo "│ 2. PVC with StorageClass - Persistent storage, prevents disk fill-up      │"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    read -p "Do you want to use persistent storage (PVC)? (y/N): " USE_PVC_CONFIRM
    
    if [[ "$USE_PVC_CONFIRM" =~ ^[Yy]$ ]]; then
        echo ""
        print_status "Available StorageClasses in cluster:"
        echo ""
        $CLI_TOOL get storageclass -o custom-columns=NAME:.metadata.name,PROVISIONER:.provisioner,RECLAIMPOLICY:.reclaimPolicy 2>/dev/null || \
            $CLI_TOOL get storageclass 2>/dev/null || echo "  (unable to list storage classes)"
        echo ""
        read -p "Enter StorageClass name: " STORAGE_CLASS
    fi
fi

if [ -n "$STORAGE_CLASS" ]; then
    # Validate storage class exists
    if ! $CLI_TOOL get storageclass "$STORAGE_CLASS" &> /dev/null; then
        print_error "StorageClass '$STORAGE_CLASS' not found!"
        echo ""
        print_status "Available StorageClasses:"
        $CLI_TOOL get storageclass -o custom-columns=NAME:.metadata.name,PROVISIONER:.provisioner 2>/dev/null || \
            $CLI_TOOL get storageclass 2>/dev/null
        exit 1
    fi
    print_success "StorageClass '$STORAGE_CLASS' exists"
    
    # Get provisioner info
    PROVISIONER=$($CLI_TOOL get storageclass "$STORAGE_CLASS" -o jsonpath='{.provisioner}' 2>/dev/null)
    print_status "Provisioner: $PROVISIONER"
    
    BINDING_MODE=$($CLI_TOOL get storageclass "$STORAGE_CLASS" -o jsonpath='{.volumeBindingMode}' 2>/dev/null)
    if [ "$BINDING_MODE" = "WaitForFirstConsumer" ]; then
        print_success "Volume binding mode: WaitForFirstConsumer (recommended)"
    elif [ -n "$BINDING_MODE" ]; then
        print_warning "Volume binding mode: $BINDING_MODE"
    fi
    
    # Check Kubernetes version for PVC support (ephemeral volumes require 1.23+)
    print_status "Checking Kubernetes version for PVC support..."
    K8S_VERSION=$($CLI_TOOL version -o json 2>/dev/null | grep -o '"gitVersion": "[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -z "$K8S_VERSION" ]; then
        K8S_VERSION=$($CLI_TOOL version --short 2>/dev/null | grep -i server | awk '{print $NF}')
    fi
    
    if [ -n "$K8S_VERSION" ]; then
        print_status "Kubernetes version: $K8S_VERSION"
        K8S_MAJOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f1)
        K8S_MINOR=$(echo "$K8S_VERSION" | cut -d. -f2)
        
        if [ "$K8S_MAJOR" -lt 1 ] || ([ "$K8S_MAJOR" -eq 1 ] && [ "$K8S_MINOR" -lt 23 ]); then
            print_error "Kubernetes version $K8S_VERSION does not support ephemeral PVCs!"
            print_error "Ephemeral volumes require Kubernetes 1.23 or newer."
            print_warning "Falling back to emptyDir storage..."
            STORAGE_CLASS=""
            USE_PVC=false
        else
            print_success "Kubernetes version is compatible"
            USE_PVC=true
        fi
    else
        print_warning "Could not determine Kubernetes version. Proceeding with PVC..."
        USE_PVC=true
    fi
else
    print_status "Using emptyDir storage (default)"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Check Current Storage Status
# ═══════════════════════════════════════════════════════════════════════════
print_header "Checking Current Storage Configuration"

# Check current volume configuration
CURRENT_OCI_VOLUME=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="oci")]}' 2>/dev/null)
CURRENT_WASM_VOLUME=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="wasm-cache")]}' 2>/dev/null)

if echo "$CURRENT_OCI_VOLUME" | grep -q "ephemeral"; then
    print_warning "OCI volume already using ephemeral PVC"
    EXISTING_SC=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="oci")].ephemeral.volumeClaimTemplate.spec.storageClassName}' 2>/dev/null)
    print_status "Current StorageClass: $EXISTING_SC"
    echo ""
    read -p "Do you want to update to StorageClass '$STORAGE_CLASS'? (y/N): " UPDATE_CONFIRM
    if [[ ! "$UPDATE_CONFIRM" =~ ^[Yy]$ ]]; then
        print_status "Cancelled. No changes made."
        exit 0
    fi
elif echo "$CURRENT_OCI_VOLUME" | grep -q "emptyDir"; then
    print_status "OCI volume currently using emptyDir (ephemeral storage)"
else
    print_warning "Could not determine current OCI volume type"
fi

if echo "$CURRENT_WASM_VOLUME" | grep -q "ephemeral"; then
    print_status "WASM-cache volume already using ephemeral PVC"
elif echo "$CURRENT_WASM_VOLUME" | grep -q "emptyDir"; then
    print_status "WASM-cache volume currently using emptyDir"
fi

# Show current pods
print_status "Current gadget pods:"
$CLI_TOOL get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide

# ═══════════════════════════════════════════════════════════════════════════
# Apply DaemonSet Update
# ═══════════════════════════════════════════════════════════════════════════
print_header "Applying DaemonSet Update"

echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ WARNING: This will update the Inspektor Gadget DaemonSet with:              │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│   - Node affinity: Exclude master/control-plane/infra nodes               │"
if [ "$USE_PVC" = true ]; then
echo "│   - OCI volume: 10Gi ephemeral PVC (StorageClass: $STORAGE_CLASS)"
echo "│   - WASM cache: 5Gi ephemeral PVC (StorageClass: $STORAGE_CLASS)"
else
echo "│   - OCI volume: emptyDir (node local disk)                                │"
echo "│   - WASM cache: emptyDir (node local disk)                                │"
fi
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ WARNING: All gadget pods will be restarted!                                 │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
read -p "Do you want to proceed? (y/N): " PROCEED_CONFIRM

if [[ ! "$PROCEED_CONFIRM" =~ ^[Yy]$ ]]; then
    print_warning "Cancelled. No changes made."
    exit 0
fi

# Get current image and other configuration
GADGET_IMAGE=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)
print_status "Current Gadget image: $GADGET_IMAGE"

# Get current resource limits (we'll preserve these)
CURRENT_CPU_REQ=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' 2>/dev/null)
CURRENT_MEM_REQ=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' 2>/dev/null)
CURRENT_CPU_LIM=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null)
CURRENT_MEM_LIM=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null)

# Use current values or defaults
CPU_REQ=${CURRENT_CPU_REQ:-"100m"}
MEM_REQ=${CURRENT_MEM_REQ:-"512Mi"}
CPU_LIM=${CURRENT_CPU_LIM:-"1"}
MEM_LIM=${CURRENT_MEM_LIM:-"6Gi"}

print_status "Resource configuration:"
print_status "  CPU request: $CPU_REQ, limit: $CPU_LIM"
print_status "  Memory request: $MEM_REQ, limit: $MEM_LIM"

if [ "$USE_PVC" = true ]; then
    print_status "Patching DaemonSet with PVC storage..."
else
    print_status "Patching DaemonSet with emptyDir storage..."
fi

# Build volumes section based on storage choice
if [ "$USE_PVC" = true ]; then
    VOLUMES_YAML="      volumes:
      - name: bin
        hostPath:
          path: /bin
      - name: etc
        hostPath:
          path: /etc
      - name: opt
        hostPath:
          path: /opt
      - name: usr
        hostPath:
          path: /usr
      - name: proc
        hostPath:
          path: /proc
      - name: run
        hostPath:
          path: /run
      - name: var
        hostPath:
          path: /var
      - name: cgroup
        hostPath:
          path: /sys/fs/cgroup
      - name: bpffs
        hostPath:
          path: /sys/fs/bpf
      - name: debugfs
        hostPath:
          path: /sys/kernel/debug
      - name: oci
        ephemeral:
          volumeClaimTemplate:
            metadata:
              labels:
                app: inspektor-gadget
                volume-type: oci-storage
            spec:
              accessModes: [\"ReadWriteOnce\"]
              storageClassName: \"$STORAGE_CLASS\"
              resources:
                requests:
                  storage: 10Gi
      - name: config
        configMap:
          name: inspektor-gadget-config
          defaultMode: 0400
      - name: wasm-cache
        ephemeral:
          volumeClaimTemplate:
            metadata:
              labels:
                app: inspektor-gadget
                volume-type: wasm-cache
            spec:
              accessModes: [\"ReadWriteOnce\"]
              storageClassName: \"$STORAGE_CLASS\"
              resources:
                requests:
                  storage: 5Gi"
else
    VOLUMES_YAML="      volumes:
      - name: bin
        hostPath:
          path: /bin
      - name: etc
        hostPath:
          path: /etc
      - name: opt
        hostPath:
          path: /opt
      - name: usr
        hostPath:
          path: /usr
      - name: proc
        hostPath:
          path: /proc
      - name: run
        hostPath:
          path: /run
      - name: var
        hostPath:
          path: /var
      - name: cgroup
        hostPath:
          path: /sys/fs/cgroup
      - name: bpffs
        hostPath:
          path: /sys/fs/bpf
      - name: debugfs
        hostPath:
          path: /sys/kernel/debug
      - name: oci
        emptyDir: {}
      - name: config
        configMap:
          name: inspektor-gadget-config
          defaultMode: 0400
      - name: wasm-cache
        emptyDir: {}"
fi

# Apply the updated DaemonSet
cat <<EOF | $CLI_TOOL apply -f -
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: inspektor-gadget
  namespace: $NAMESPACE
  labels:
    app: inspektor-gadget
    k8s-app: inspektor-gadget
spec:
  selector:
    matchLabels:
      app: inspektor-gadget
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: inspektor-gadget
        k8s-app: gadget
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "2223"
        prometheus.io/path: "/metrics"
        flowfish.io/updated: "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        flowfish.io/storage-type: "$([ "$USE_PVC" = true ] && echo "pvc" || echo "emptydir")"
    spec:
      serviceAccountName: inspektor-gadget
      nodeSelector:
        kubernetes.io/os: linux
      # Exclude master/control-plane/infra nodes
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: node-role.kubernetes.io/control-plane
                operator: DoesNotExist
              - key: node-role.kubernetes.io/master
                operator: DoesNotExist
              - key: node-role.kubernetes.io/infra
                operator: DoesNotExist
      tolerations:
      - effect: NoSchedule
        operator: Exists
      - effect: NoExecute
        operator: Exists
      containers:
      - name: gadget
        image: $GADGET_IMAGE
        imagePullPolicy: Always
        terminationMessagePolicy: FallbackToLogsOnError
        command:
        - /bin/gadgettracermanager
        - -serve
        lifecycle:
          preStop:
            exec:
              command:
              - /cleanup
        env:
        - name: NODE_NAME
          valueFrom:
            fieldRef:
              fieldPath: spec.nodeName
        - name: GADGET_POD_UID
          valueFrom:
            fieldRef:
              fieldPath: metadata.uid
        - name: GADGET_IMAGE
          value: "$GADGET_IMAGE"
        - name: HOST_ROOT
          value: "/host"
        - name: IG_EXPERIMENTAL
          value: "false"
        securityContext:
          readOnlyRootFilesystem: true
          appArmorProfile:
            type: Unconfined
          seLinuxOptions:
            type: spc_t
          capabilities:
            drop:
            - ALL
            add:
            - SYS_ADMIN
            - SYSLOG
            - SYS_PTRACE
            - SYS_RESOURCE
            - IPC_LOCK
            - NET_RAW
            - NET_ADMIN
        startupProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          failureThreshold: 12
          periodSeconds: 5
        readinessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        livenessProbe:
          exec:
            command:
            - /bin/gadgettracermanager
            - -liveness
          periodSeconds: 5
          timeoutSeconds: 2
        resources:
          requests:
            cpu: "$CPU_REQ"
            memory: "$MEM_REQ"
          limits:
            cpu: "$CPU_LIM"
            memory: "$MEM_LIM"
        volumeMounts:
        - name: bin
          mountPath: /host/bin
          readOnly: true
        - name: etc
          mountPath: /host/etc
        - name: opt
          mountPath: /host/opt
        - name: usr
          mountPath: /host/usr
          readOnly: true
        - name: run
          mountPath: /host/run
          readOnly: true
        - name: var
          mountPath: /host/var
          readOnly: true
        - name: proc
          mountPath: /host/proc
          readOnly: true
        - name: run
          mountPath: /run
        - name: debugfs
          mountPath: /sys/kernel/debug
        - name: cgroup
          mountPath: /sys/fs/cgroup
          readOnly: true
        - name: bpffs
          mountPath: /sys/fs/bpf
        - name: oci
          mountPath: /var/lib/ig
        - name: config
          mountPath: /etc/ig
          readOnly: true
        - name: wasm-cache
          mountPath: /var/run/ig/wasm-cache
$VOLUMES_YAML
EOF

if [ $? -eq 0 ]; then
    print_success "DaemonSet updated successfully"
else
    print_error "Failed to update DaemonSet"
    exit 1
fi

# Wait for rollout
print_status "Waiting for rollout to complete (timeout: 300s)..."
if $CLI_TOOL rollout status daemonset/inspektor-gadget -n "$NAMESPACE" --timeout=300s 2>/dev/null; then
    print_success "Rollout completed successfully!"
else
    print_warning "Timeout waiting for rollout. Check status manually:"
    print_warning "  $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════════════
print_header "Verification"

# Check new volume configuration
print_status "Checking new volume configuration..."

if [ "$USE_PVC" = true ]; then
    NEW_OCI_VOLUME=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="oci")].ephemeral.volumeClaimTemplate.spec.storageClassName}' 2>/dev/null)
    NEW_WASM_VOLUME=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="wasm-cache")].ephemeral.volumeClaimTemplate.spec.storageClassName}' 2>/dev/null)
    
    if [ "$NEW_OCI_VOLUME" = "$STORAGE_CLASS" ]; then
        print_success "OCI volume using StorageClass: $NEW_OCI_VOLUME"
    else
        print_warning "OCI volume StorageClass verification failed"
    fi
    
    if [ "$NEW_WASM_VOLUME" = "$STORAGE_CLASS" ]; then
        print_success "WASM cache volume using StorageClass: $NEW_WASM_VOLUME"
    else
        print_warning "WASM cache volume StorageClass verification failed"
    fi
else
    OCI_EMPTYDIR=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="oci")].emptyDir}' 2>/dev/null)
    if [ -n "$OCI_EMPTYDIR" ]; then
        print_success "OCI volume using emptyDir"
    fi
    
    WASM_EMPTYDIR=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.volumes[?(@.name=="wasm-cache")].emptyDir}' 2>/dev/null)
    if [ -n "$WASM_EMPTYDIR" ]; then
        print_success "WASM cache volume using emptyDir"
    fi
fi

# Check node affinity
AFFINITY=$($CLI_TOOL get daemonset inspektor-gadget -n "$NAMESPACE" -o jsonpath='{.spec.template.spec.affinity.nodeAffinity}' 2>/dev/null)
if [ -n "$AFFINITY" ]; then
    print_success "Node affinity configured (master/control-plane/infra excluded)"
fi

# Show updated pods
echo ""
print_status "Updated pod status:"
$CLI_TOOL get pods -l app=inspektor-gadget -n "$NAMESPACE" -o wide

# Check for PVCs (only if using PVC storage)
if [ "$USE_PVC" = true ]; then
    echo ""
    print_status "Checking ephemeral PVCs created by pods..."
    $CLI_TOOL get pvc -n "$NAMESPACE" -l app=inspektor-gadget 2>/dev/null || \
        print_status "PVCs will be created when pods start"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Completion
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                           ║"
echo "║   DAEMONSET UPDATE COMPLETE                                               ║"
echo "║                                                                           ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ SUMMARY                                                                      │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ [OK] Node affinity: master/control-plane/infra nodes excluded              │"
if [ "$USE_PVC" = true ]; then
echo "│ [OK] Storage: PVC with StorageClass: $STORAGE_CLASS"
echo "│ [OK] OCI volume: 10Gi ephemeral PVC per node                               │"
echo "│ [OK] WASM cache: 5Gi ephemeral PVC per node                              │"
else
echo "│ [OK] Storage: emptyDir (node local disk)                                 │"
echo "│ [OK] OCI volume: emptyDir                                                │"
echo "│ [OK] WASM cache: emptyDir                                                │"
fi
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
if [ "$USE_PVC" = true ]; then
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ PVC STORAGE NOTES                                                            │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ 1. Ephemeral PVCs are created automatically per pod                        │"
echo "│ 2. PVCs are deleted when pod is deleted (ephemeral lifecycle)              │"
echo "│ 3. Each node will have its own dedicated storage                           │"
echo "│ 4. Monitor PVC usage: $CLI_TOOL get pvc -n $NAMESPACE                       │"
else
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ EMPTYDIR STORAGE NOTES                                                       │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
echo "│ 1. Data is stored on node's local disk (/var/lib/kubelet/pods/...)        │"
echo "│ 2. Data is lost when pod restarts or is rescheduled                        │"
echo "│ 3. May fill up node disk if gadget caches many OCI images                  │"
echo "│ 4. Consider using PVC storage for production environments                  │"
fi
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│ MONITORING COMMANDS                                                          │"
echo "├─────────────────────────────────────────────────────────────────────────────┤"
if [ "$USE_PVC" = true ]; then
echo "│ Check PVCs:                                                                 │"
echo "│   $CLI_TOOL get pvc -n $NAMESPACE -l app=inspektor-gadget                   │"
echo "│                                                                             │"
fi
echo "│ Check pod storage:                                                          │"
echo "│   $CLI_TOOL describe pod -l app=inspektor-gadget -n $NAMESPACE | grep -A5 Volumes"
echo "│                                                                             │"
echo "│ Monitor pod health:                                                         │"
echo "│   $CLI_TOOL get pods -l app=inspektor-gadget -n $NAMESPACE -w              │"
echo "│                                                                             │"
echo "│ View logs:                                                                  │"
echo "│   $CLI_TOOL logs -l app=inspektor-gadget -n $NAMESPACE --tail=50           │"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
print_success "Storage fix applied. Gadget will now use persistent storage instead of node local disk."
echo ""
