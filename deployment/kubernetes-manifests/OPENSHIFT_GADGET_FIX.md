# Inspektor Gadget OpenShift Fix

## Problem
Inspektor Gadget pod'ları restart oluyor ve şu hata ile crash ediyor:
```
failed to wait for trace caches to sync: timed out waiting for cache to be synced for Kind *v1alpha1.Trace
```

## Root Cause
1. **Trace CRD eksik**: `gadget.kinvolk.io/v1alpha1` API group'u için `Trace` CRD yüklü değil
2. **RBAC yetersiz**: Inspektor Gadget'ın Trace CRD'lerine erişim izni yok
3. **ConfigMap eksik**: `/etc/ig/config.yaml` bulunamıyor

## Solution

### 1. Apply Trace CRD
```bash
oc apply -f 09-inspektor-gadget-crds.yaml
```

### 2. Update RBAC (Cluster Admin gerekli)
```bash
oc apply -f 10-inspektor-gadget-rbac-cluster.yaml
```

### 3. Create ConfigMap
```bash
oc apply -f 09-inspektor-gadget-config.yaml
```

### 4. Update DaemonSet
```bash
oc apply -f 10-inspektor-gadget.yaml
```

### 5. Verify
```bash
# Check if CRD is installed
oc get crd traces.gadget.kinvolk.io

# Check RBAC
oc get clusterrole inspektor-gadget
oc get clusterrolebinding inspektor-gadget

# Check ConfigMap
oc get configmap inspektor-gadget-config -n $OPENSHIFT_NAMESPACE

# Check DaemonSet pods
oc get pods -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE

# Check logs (should NOT have "failed to wait for trace caches" error)
oc logs -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE --tail=50
```

## Expected Output
After fix, logs should show:
```
time="..." level=info msg="Starting trace controller manager"
time="..." level=info msg="Serving on gRPC socket /run/gadgettracermanager.socket"
time="..." level=info msg="Starting gRPC server on 0.0.0.0:16060"
```

## Quick Deploy Script (Automated)

**Recommended Method:** Use the provided deployment script:

```bash
# Set your namespace
export OPENSHIFT_NAMESPACE="flowfish"

# Run the automated deployment script
cd deployment/kubernetes-manifests
./deploy-inspektor-gadget.sh
```

The script (`deploy-inspektor-gadget.sh`) will automatically:
1. ✅ Apply Trace CRD
2. ✅ Configure RBAC
3. ✅ Create ConfigMap
4. ✅ Deploy DaemonSet
5. ✅ Restart pods
6. ✅ Verify deployment
7. ✅ Check logs for errors

### Manual Deployment (Alternative)

If you prefer manual deployment (manifests use flowfish namespace by default):

```bash
export OPENSHIFT_NAMESPACE="${OPENSHIFT_NAMESPACE:-flowfish}"

echo "1. Applying Trace CRD..."
oc apply -f 09-inspektor-gadget-crds.yaml

echo "2. Applying RBAC (requires cluster-admin)..."
oc apply -f 10-inspektor-gadget-rbac-cluster.yaml

echo "3. Creating ConfigMap..."
oc apply -f 09-inspektor-gadget-config.yaml

echo "4. Updating DaemonSet..."
oc apply -f 10-inspektor-gadget.yaml

echo "5. Restarting pods..."
oc delete pods -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE

echo "6. Waiting for pods to be ready..."
oc wait --for=condition=ready pod -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE --timeout=120s

echo "✅ Inspektor Gadget fixed and deployed!"
```

## Known Issues

### Issue: Node Disk Full - Core Dump Files (core-ocihookgadget-*)

**Symptoms:**
- Node disk fills up and goes read-only
- Files named `core-ocihookgadget-sig6-user0-group0-pid*-time*` accumulate in `/var`
- Error in gadget logs: `kubernetes enricher: failed to get owner reference... jobs.batch is forbidden`

**Root Cause:**
Missing RBAC permission for `batch` API group (jobs, cronjobs). When gadget's kubernetes enricher can't resolve owner references for Job pods, it crashes (SIGABRT) and generates core dump files.

**Solution:**
1. Run the RBAC fix script:
   ```bash
   # From flowfish repo
   ./scripts/fix-gadget-rbac.sh <NAMESPACE>
   ```

2. Clean up existing core dump files on affected nodes:
   ```bash
   # Run on each affected node
   find /var -name 'core-ocihookgadget*' -type f -delete 2>/dev/null
   rm -f /var/lib/systemd/coredump/core.ocihookgadget.* 2>/dev/null
   df -h /var
   ```

3. Verify fix:
   ```bash
   # Should return no results
   oc logs -l app=inspektor-gadget -n $OPENSHIFT_NAMESPACE --tail=100 | grep "forbidden.*jobs"
   ```

**Prevention:**
The RBAC in `10-inspektor-gadget-rbac-cluster.yaml` now includes:
```yaml
- apiGroups: ["batch"]
  resources: ["jobs", "cronjobs"]
  verbs: ["get", "list", "watch"]
```

---

## Troubleshooting

### If pods still restart:
```bash
# Check SCC
oc get scc privileged-gadget

# Ensure ServiceAccount has SCC
oc adm policy add-scc-to-user privileged-gadget -z inspektor-gadget -n $OPENSHIFT_NAMESPACE

# Check if nodes allow DaemonSet
oc describe daemonset inspektor-gadget -n $OPENSHIFT_NAMESPACE
```

### If gRPC not working:
```bash
# Port-forward to test
oc port-forward -n $OPENSHIFT_NAMESPACE svc/inspektor-gadget 16060:16060

# Test from another pod
oc run grpcurl --rm -it --image=fullstorydev/grpcurl --command -- \
  grpcurl -plaintext inspektor-gadget.flowfish:16060 list
```

