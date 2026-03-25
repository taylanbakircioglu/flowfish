# OpenShift SCC (Security Context Constraints) Setup

This document describes the manual SCC permissions required for the Flowfish platform to run on OpenShift.

---

## Overview

OpenShift uses **restricted SCC** by default. Some database images (Neo4j, ClickHouse) need to run with their own user IDs and modify directory ownership, requiring **anyuid SCC**. Inspektor Gadget requires **privileged SCC** for eBPF kernel access.

---

## Manual Permission Grant (Cluster Admin Required)

### 1. Neo4j - anyuid SCC

**Service Account:** `flowfish-neo4j`

**Command:**
```bash
oc adm policy add-scc-to-user anyuid -z flowfish-neo4j -n flowfish
```

**Why Required:**
- Official Neo4j image performs `chown` operations on data directories
- Must run as Neo4j user (UID: 7474)
- Restricted SCC blocks these operations

**Verification:**
```bash
oc describe scc anyuid | grep flowfish-neo4j
```

---

### 2. ClickHouse - anyuid SCC

**Service Account:** `flowfish-clickhouse`

**Command:**
```bash
oc adm policy add-scc-to-user anyuid -z flowfish-clickhouse -n flowfish
```

**Why Required:**
- ClickHouse official image manages data and log directories
- Must run as ClickHouse user (UID: 101)
- Needs to modify file ownership and permissions
- Restricted SCC blocks these operations

**Verification:**
```bash
oc describe scc anyuid | grep flowfish-clickhouse
```

---

### 3. Inspektor Gadget - privileged SCC + ClusterRole/ClusterRoleBinding

**Service Account:** `inspektor-gadget`

**Single Command (All Permissions):**
```bash
export NAMESPACE=flowfish && oc create clusterrole inspektor-gadget --verb=get,list,watch --resource=pods,nodes,namespaces && oc create clusterrole inspektor-gadget-apps --verb=get,list,watch --resource=deployments.apps,daemonsets.apps,replicasets.apps,statefulsets.apps && oc create clusterrolebinding inspektor-gadget --clusterrole=inspektor-gadget --serviceaccount=${NAMESPACE}:inspektor-gadget && oc create clusterrolebinding inspektor-gadget-apps --clusterrole=inspektor-gadget-apps --serviceaccount=${NAMESPACE}:inspektor-gadget && oc adm policy add-scc-to-user privileged -z inspektor-gadget -n ${NAMESPACE}
```

**Step-by-Step Commands:**
```bash
export NAMESPACE=flowfish

# Create ClusterRole (read-only access to pods, nodes, namespaces)
oc create clusterrole inspektor-gadget --verb=get,list,watch --resource=pods,nodes,namespaces

# Create ClusterRole (read-only access to deployments, daemonsets, etc.)
oc create clusterrole inspektor-gadget-apps --verb=get,list,watch --resource=deployments.apps,daemonsets.apps,replicasets.apps,statefulsets.apps

# Create ClusterRoleBindings
oc create clusterrolebinding inspektor-gadget --clusterrole=inspektor-gadget --serviceaccount=${NAMESPACE}:inspektor-gadget

oc create clusterrolebinding inspektor-gadget-apps --clusterrole=inspektor-gadget-apps --serviceaccount=${NAMESPACE}:inspektor-gadget

# Grant Privileged SCC
oc adm policy add-scc-to-user privileged -z inspektor-gadget -n ${NAMESPACE}
```

**Why Required:**
- **eBPF Observability:** Inspektor Gadget monitors network traffic using eBPF
- **Privileged Access:** eBPF programs run in kernel space, require privileged mode
- **Host Network/PID:** Bypasses container network stack to monitor all traffic
- **ClusterRole:** Cluster-wide read access to monitor pods across all namespaces

**Verification:**
```bash
# Check ClusterRoles
oc get clusterrole inspektor-gadget inspektor-gadget-apps

# Check ClusterRoleBindings
oc get clusterrolebinding inspektor-gadget inspektor-gadget-apps

# Check SCC permission
oc adm policy who-can use scc privileged -n flowfish | grep inspektor-gadget
```

---

## Pre-Deployment Checklist

Before running the deployment pipeline, **ENSURE** the following permissions are granted:

- [ ] Neo4j anyuid SCC - `flowfish-neo4j` service account
- [ ] ClickHouse anyuid SCC - `flowfish-clickhouse` service account
- [ ] Inspektor Gadget privileged SCC + ClusterRole/Binding - `inspektor-gadget` service account
- [ ] Namespace created - `flowfish`
- [ ] Storage Class defined - `STORAGE_CLASS` set in variable group

---

## Security Notes

### Scope:
- **Only specified ServiceAccounts** receive permissions
- **Only within the target namespace** (`flowfish`)
- Does **NOT AFFECT** other applications or pods

### What is anyuid SCC? (Neo4j, ClickHouse)
- Allows containers to run with any User ID (UID)
- Includes root (UID 0)
- Privilege escalation is still **BLOCKED**
- No host network/storage access

### What is privileged SCC? (Inspektor Gadget)
- **Highest privilege level**
- Host network, host PID, host IPC access
- Can run eBPF programs (kernel level)
- All Linux capabilities (SYS_ADMIN, NET_ADMIN, BPF, etc.)
- **Should only be used for observability/monitoring tools**

### Risk Assessment:
- **Low Risk (Databases):** Containers only work within their own volumes, isolated
- **Medium Risk (Inspektor Gadget):** 
  - **Read-only observability:** Only monitors network traffic, does not modify
  - **DaemonSet:** Runs on every node, accesses kernel via eBPF
  - **ClusterRole (read-only):** Can view all namespaces but cannot modify
  - **Safe usage:** Official image, regularly updated for security vulnerabilities

---

## Remove Permissions (If Needed)

```bash
# Remove Neo4j permission
oc adm policy remove-scc-from-user anyuid -z flowfish-neo4j -n flowfish

# Remove ClickHouse permission
oc adm policy remove-scc-from-user anyuid -z flowfish-clickhouse -n flowfish

# Remove Inspektor Gadget permissions (all)
export NAMESPACE=flowfish
oc delete clusterrolebinding inspektor-gadget inspektor-gadget-apps
oc delete clusterrole inspektor-gadget inspektor-gadget-apps
oc adm policy remove-scc-from-user privileged -z inspektor-gadget -n ${NAMESPACE}
```

---

## Troubleshooting

### Neo4j not starting - "chown: Operation not permitted"
**Solution:** anyuid SCC not granted
```bash
oc adm policy add-scc-to-user anyuid -z flowfish-neo4j -n flowfish
oc delete pod neo4j-0 -n flowfish  # Restart pod
```

### ClickHouse not starting - "Access to file denied" or "Group 0 is not found"
**Solution:** anyuid SCC not granted
```bash
oc adm policy add-scc-to-user anyuid -z flowfish-clickhouse -n flowfish
oc delete pod clickhouse-0 -n flowfish  # Restart pod
```

### Inspektor Gadget not starting - "image pull timeout" or "privileged not allowed"
**Solution 1:** Privileged SCC not granted
```bash
export NAMESPACE=flowfish
oc adm policy add-scc-to-user privileged -z inspektor-gadget -n ${NAMESPACE}
oc delete daemonset inspektor-gadget -n flowfish  # Restart DaemonSet
```

**Solution 2:** ClusterRole/ClusterRoleBinding missing
```bash
# Use single command to grant all permissions (see section 3 above)
export NAMESPACE=flowfish && oc create clusterrole inspektor-gadget --verb=get,list,watch --resource=pods,nodes,namespaces && oc create clusterrole inspektor-gadget-apps --verb=get,list,watch --resource=deployments.apps,daemonsets.apps,replicasets.apps,statefulsets.apps && oc create clusterrolebinding inspektor-gadget --clusterrole=inspektor-gadget --serviceaccount=${NAMESPACE}:inspektor-gadget && oc create clusterrolebinding inspektor-gadget-apps --clusterrole=inspektor-gadget-apps --serviceaccount=${NAMESPACE}:inspektor-gadget && oc adm policy add-scc-to-user privileged -z inspektor-gadget -n ${NAMESPACE}
```

### Check SCC permissions
```bash
# For Neo4j
oc get pod neo4j-0 -n flowfish -o yaml | grep scc

# For ClickHouse
oc get pod clickhouse-0 -n flowfish -o yaml | grep scc

# For Inspektor Gadget (runs on all nodes)
oc get pods -l app=inspektor-gadget -n flowfish -o yaml | grep "openshift.io/scc"

# Expected output: 
#   Neo4j/ClickHouse: openshift.io/scc: anyuid
#   Inspektor Gadget: openshift.io/scc: privileged
```

---

## References

- [OpenShift SCC Documentation](https://docs.openshift.com/container-platform/latest/authentication/managing-security-context-constraints.html)
- [Neo4j Docker Documentation](https://neo4j.com/docs/operations-manual/current/docker/)
- [ClickHouse Docker Documentation](https://hub.docker.com/r/clickhouse/clickhouse-server)
- [Inspektor Gadget Documentation](https://www.inspektor-gadget.io/docs/latest/)

