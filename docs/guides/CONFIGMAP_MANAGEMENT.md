# ConfigMap Management Strategy

## Problem

When namespace is cleaned/recreated and pipeline runs, ConfigMaps may not be created, causing pod failures:

```
MountVolume.SetUp failed for volume "config" : configmap "inspektor-gadget-config" not found
```

## Root Cause

1. **Inspektor Gadget ConfigMap** (`09-inspektor-gadget-config.yaml`) was not applied by pipeline
2. Pipeline only applied `03-configmaps.yaml` (backend-config, frontend-config)
3. Multiple ConfigMap files not handled systematically

## Solution

### 1. Pipeline Enhancement

**File:** `pipelines/classic-release/deploy-infrastructure/task.sh`

**Changes:**
- ✅ Added `apply_configmap_safe()` function
- ✅ Backs up existing ConfigMaps before applying
- ✅ Restores backup on failure
- ✅ Applies all ConfigMap files:
  - `03-configmaps.yaml` (backend-config, frontend-config)
  - `09-inspektor-gadget-config.yaml` (inspektor-gadget-config)
- ✅ Added CRD and RBAC application for Inspektor Gadget

### 2. Standalone Script

**File:** `pipelines/scripts/apply-configmaps-safe.sh`

**Features:**
- ✅ Safe ConfigMap application with backup
- ✅ Automatic rollback on failure
- ✅ Verification after apply
- ✅ Can be run manually or by pipeline

**Usage:**
```bash
cd deployment/kubernetes-manifests
../../pipelines/scripts/apply-configmaps-safe.sh <namespace>
```

## ConfigMap Files Structure

```
deployment/kubernetes-manifests/
├── 03-configmaps.yaml              # Backend & Frontend configs
├── 09-inspektor-gadget-config.yaml # Inspektor Gadget config
└── (other configmaps as needed)
```

## Pipeline Flow (Updated)

```
1. Login to OpenShift
2. Create/Switch namespace
3. Apply RBAC
4. Apply ConfigMaps (with backup)
   ├── 03-configmaps.yaml
   └── 09-inspektor-gadget-config.yaml ✅ NEW
5. Apply Secrets
6. Deploy Databases
7. Deploy Inspektor Gadget
   ├── Apply CRDs ✅ NEW
   ├── Apply RBAC ✅ NEW
   ├── Apply ConfigMap (already done in step 4)
   └── Apply DaemonSet
8. Run Migrations
```

## Manual Recovery

If ConfigMaps are missing after deployment:

### Method 1: Use Safe Script
```bash
cd deployment/kubernetes-manifests
../../pipelines/scripts/apply-configmaps-safe.sh flowfish
```

### Method 2: Manual Apply
```bash
export OPENSHIFT_NAMESPACE="flowfish"

# Apply all ConfigMaps
kubectl apply -f 03-configmaps.yaml
kubectl apply -f 09-inspektor-gadget-config.yaml

# Verify
kubectl get configmaps -n $OPENSHIFT_NAMESPACE
```

### Method 3: Restart Pipeline
```bash
# Pipeline will now create missing ConfigMaps
git push origin pilot
```

## Verification

After pipeline runs, verify all ConfigMaps exist:

```bash
oc get configmaps -n flowfish

# Expected output:
NAME                       DATA   AGE
backend-config             X      Xm
frontend-config            X      Xm
inspektor-gadget-config    1      Xm
```

Check Inspektor Gadget pods:

```bash
oc get pods -l app=inspektor-gadget -n flowfish

# Should be Running (not CrashLoopBackOff)
```

## Backup & Restore

### Automatic Backups

Pipeline creates backups in `/tmp/flowfish-configmap-backups-<timestamp>/`

### Manual Backup

```bash
# Backup all ConfigMaps
kubectl get configmaps -n flowfish -o yaml > configmaps-backup.yaml

# Restore
kubectl apply -f configmaps-backup.yaml
```

### Restore from Pipeline Backup

```bash
# Find latest backup
ls -lrt /tmp/flowfish-configmap-backups-*

# Restore specific ConfigMap
oc apply -f /tmp/flowfish-configmap-backups-<timestamp>/inspektor-gadget-config.yaml

# Restore all
oc apply -f /tmp/flowfish-configmap-backups-<timestamp>/
```

## Troubleshooting

### Issue: ConfigMap not found

```bash
# Check if ConfigMap exists
oc get configmap inspektor-gadget-config -n flowfish

# If missing, apply
oc apply -f deployment/kubernetes-manifests/09-inspektor-gadget-config.yaml
```

### Issue: Pod CrashLoopBackOff (Mount Error)

```bash
# Check pod events
oc describe pod <pod-name> -n flowfish | grep -A5 "Events:"

# If "configmap not found":
1. Apply ConfigMap
2. Delete pod (will be recreated)
   oc delete pod <pod-name> -n flowfish
```

### Issue: Pipeline doesn't apply ConfigMap

```bash
# Check pipeline logs
# Look for: "Applying configmaps with backup..."

# If not found, pipeline needs update
# Check: pipelines/classic-release/deploy-infrastructure/task.sh
```

## Service Endpoints Configuration

### Critical Settings in backend-config

The following service endpoints **MUST** be configured via ConfigMap in production:

| Environment Variable | Description | Default (Dev Only) |
|---------------------|-------------|-------------------|
| `CLUSTER_MANAGER_GRPC` | Cluster Manager gRPC endpoint | `cluster-manager:5001` |
| `ANALYSIS_ORCHESTRATOR_GRPC` | Analysis Orchestrator gRPC endpoint | `analysis-orchestrator:5002` |
| `INGESTION_SERVICE_GRPC` | Ingestion Service gRPC endpoint | `ingestion-service:5000` |
| `GRAPH_QUERY_URL` | Graph Query HTTP endpoint | `http://graph-query:8001` |

### How It Works

1. **Pydantic Settings** reads from environment variables first
2. If not set, falls back to default values (for local development)
3. In Kubernetes, ConfigMap values are injected as environment variables
4. Backend logs configured endpoints on startup for verification

### Verification

Check startup logs for configured endpoints:

```bash
oc logs deployment/backend -n flowfish | grep "Service Endpoints"
```

Expected output:
```
🔧 Service Endpoints Configuration
  Environment: production
  Cluster Manager gRPC: cluster-manager:5001
  Analysis Orchestrator gRPC: analysis-orchestrator:5002
  ...
```

### Adding New Service Endpoints

1. **Add to ConfigMap** (`03-configmaps.yaml`):
   ```yaml
   NEW_SERVICE_URL: "http://new-service:8080"
   ```

2. **Add to Settings** (`backend/config.py`):
   ```python
   NEW_SERVICE_URL: str = Field(
       default="http://new-service:8080",
       description="New Service HTTP endpoint. Set via ConfigMap in production.",
       json_schema_extra={"env": "NEW_SERVICE_URL"}
   )
   ```

3. **Update deployment** to mount ConfigMap (if not already done)

4. **Push changes** - pipeline will apply new ConfigMap

## Best Practices

1. **Never delete ConfigMaps manually** unless you have backups
2. **Always use pipeline** for ConfigMap updates
3. **Verify after deployment** that all ConfigMaps exist
4. **Keep backups** of ConfigMaps in version control
5. **Test in local Kubernetes first** (when possible)
6. **Never hardcode production URLs in code** - always use environment variables
7. **Log service endpoints on startup** for debugging and verification

## Related Files

- `pipelines/classic-release/deploy-infrastructure/task.sh` - Pipeline script
- `pipelines/scripts/apply-configmaps-safe.sh` - Standalone script
- `deployment/kubernetes-manifests/03-configmaps.yaml` - Main configs
- `deployment/kubernetes-manifests/09-inspektor-gadget-config.yaml` - Gadget config
- `deployment/kubernetes-manifests/09-inspektor-gadget-crds.yaml` - Gadget CRDs
- `deployment/kubernetes-manifests/10-inspektor-gadget-rbac-cluster.yaml` - Gadget RBAC

## Version History

- **v1.0** - Initial ConfigMap management
- **v1.1** - Added backup/restore functionality
- **v1.2** - Added Inspektor Gadget ConfigMap support
- **v1.3** - Added CRD and RBAC application to pipeline

