# 🐟 Flowfish - OpenShift Compatibility Guide

## Overview

All Flowfish Kubernetes deployments are designed to be compatible with both standard Kubernetes and OpenShift Container Platform. This guide explains the security context requirements and best practices.

---

## Security Context Requirements

### OpenShift SCC (Security Context Constraints)

OpenShift enforces **Security Context Constraints (SCC)** which are stricter than standard Kubernetes. The default SCC is **restricted**, which:

1. **Forbids running as root** (`runAsNonRoot: true` required)
2. **Assigns random UID/GID** from namespace range (don't specify `runAsUser`, `runAsGroup`, `fsGroup`)
3. **Prevents privilege escalation** (`allowPrivilegeEscalation: false`)
4. **Drops all capabilities** by default

### ✅ Correct Security Context (OpenShift Compatible)

```yaml
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        # OpenShift compatibility: Do NOT specify runAsUser, runAsGroup, fsGroup
        # OpenShift will assign UID/GID automatically from namespace range
        seccompProfile:
          type: RuntimeDefault
      
      containers:
      - name: myapp
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true  # optional but recommended
          capabilities:
            drop:
            - ALL
```

### ❌ Incorrect Security Context (Not OpenShift Compatible)

```yaml
spec:
  template:
    spec:
      securityContext:
        runAsUser: 1000        # ❌ Don't specify - OpenShift assigns this
        runAsGroup: 1000       # ❌ Don't specify - OpenShift assigns this
        fsGroup: 2000          # ❌ Don't specify - OpenShift assigns this
```

---

## Flowfish Components Security Context

### 1. PostgreSQL
```yaml
securityContext:
  runAsNonRoot: true
  # OpenShift assigns UID/GID automatically
```

### 2. RabbitMQ
```yaml
securityContext:
  runAsNonRoot: true
  # OpenShift assigns UID/GID automatically
```

### 3. Redis
```yaml
securityContext:
  runAsNonRoot: true
  # OpenShift assigns UID/GID automatically
```

### 4. ClickHouse
```yaml
securityContext:
  runAsNonRoot: true
  # OpenShift assigns UID/GID automatically
```

### 5. Backend (FastAPI)
```yaml
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault

containers:
- name: backend
  securityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: false  # FastAPI needs write for temp files
    capabilities:
      drop:
      - ALL
```

### 6. Frontend (Nginx)
```yaml
securityContext:
  runAsNonRoot: true
  seccompProfile:
    type: RuntimeDefault

containers:
- name: frontend
  securityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    capabilities:
      drop:
      - ALL
```

### 7. Inspektor Gadget (Exception - Requires Privileged)

**⚠️ Note:** Inspektor Gadget is the **only** component that requires privileged access because it uses eBPF.

```yaml
securityContext:
  seccompProfile:
    type: Unconfined  # Required for eBPF

containers:
- name: gadget
  securityContext:
    privileged: true  # Required for eBPF
    capabilities:
      add:
      - SYS_ADMIN
      - SYS_RESOURCE
      - SYS_PTRACE
      - NET_ADMIN
      - IPC_LOCK
      - BPF
```

**OpenShift Requirement:**  
You must grant the service account `anyuid` or `privileged` SCC:

```bash
# Grant privileged SCC to Inspektor Gadget service account
oc adm policy add-scc-to-user privileged -z gadget-service-account -n flowfish
```

---

## Container Image Considerations

### Image User Configuration

Container images should be built to run as non-root:

#### ✅ Correct Dockerfile
```dockerfile
FROM python:3.11-slim

# Create non-root user (OpenShift will override UID)
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set ownership (OpenShift will override UID but maintain permissions)
WORKDIR /app
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

CMD ["python", "app.py"]
```

#### ❌ Incorrect Dockerfile
```dockerfile
FROM python:3.11-slim

# Running as root
WORKDIR /app
COPY . .

# No USER directive - defaults to root ❌
CMD ["python", "app.py"]
```

---

## OpenShift-Specific Namespace Configuration

### Namespace UID/GID Range

OpenShift assigns a UID/GID range to each namespace:

```bash
# View namespace UID/GID range
oc describe namespace flowfish | grep -E "openshift.io/sa.scc"

# Example output:
# openshift.io/sa.scc.uid-range=1000640000/10000
# openshift.io/sa.scc.supplemental-groups=1000640000/10000
```

Containers in the `flowfish` namespace will run with UIDs in the range `1000640000-1000650000`.

---

## Persistent Volume Permissions

### Problem
When using Persistent Volumes, file ownership might not match the dynamically assigned UID.

### Solution 1: Init Container (Recommended for OpenShift)

```yaml
initContainers:
- name: fix-permissions
  image: busybox
  command: ['sh', '-c', 'chown -R 1000640000:1000640000 /data']
  volumeMounts:
  - name: data
    mountPath: /data
  securityContext:
    runAsUser: 0  # Init container can run as root
```

### Solution 2: fsGroup (Works on Kubernetes, may not work on OpenShift restricted SCC)

```yaml
# Only use on Kubernetes or with relaxed SCC
securityContext:
  fsGroup: 2000
```

---

## Testing OpenShift Compatibility

### 1. Test with Kubernetes (Mimic OpenShift Restrictions)

```bash
# Create a restricted Pod Security Standard namespace
kubectl label namespace flowfish pod-security.kubernetes.io/enforce=restricted
kubectl label namespace flowfish pod-security.kubernetes.io/audit=restricted
kubectl label namespace flowfish pod-security.kubernetes.io/warn=restricted
```

### 2. Deploy and Verify

```bash
# Deploy Flowfish
kubectl apply -f deployment/kubernetes-manifests/

# Check for SCC violations
kubectl get pods -n flowfish
kubectl describe pod <pod-name> -n flowfish | grep -i "security"
```

### 3. Common Errors

#### Error: "container has runAsNonRoot and image will run as root"
**Solution:** Ensure container image has a non-root USER directive.

#### Error: "unable to validate against any security context constraint"
**Solution:** Don't specify `runAsUser`, `runAsGroup`, `fsGroup` in securityContext.

#### Error: "Forbidden: may not add capabilities"
**Solution:** Only drop capabilities, don't add (except for privileged containers like Inspektor Gadget).

---

## Summary Checklist

### ✅ OpenShift Compatibility Checklist

- [ ] All pods have `runAsNonRoot: true`
- [ ] No `runAsUser`, `runAsGroup`, `fsGroup` specified (except init containers if needed)
- [ ] Container images run as non-root (USER directive in Dockerfile)
- [ ] No privilege escalation (`allowPrivilegeEscalation: false`)
- [ ] All capabilities dropped by default
- [ ] Inspektor Gadget service account has privileged SCC (exception)
- [ ] Persistent volume permissions handled (init container or fsGroup)
- [ ] seccompProfile set to RuntimeDefault (best practice)
- [ ] Tested with restricted Pod Security Standard

---

## References

- [OpenShift Security Context Constraints (SCC)](https://docs.openshift.com/container-platform/latest/authentication/managing-security-context-constraints.html)
- [Kubernetes Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [eBPF and OpenShift](https://www.redhat.com/en/blog/introduction-ebpf-red-hat-openshift)

---

**Status:** ✅ All Flowfish deployments are OpenShift compatible  
**Last Updated:** 2024-11-21

