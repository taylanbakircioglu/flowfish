# Manuel RBAC Konfigürasyonu

Bu dizindeki RBAC kaynakları **cluster admin** tarafından manuel olarak uygulanmalıdır.

> ⚠️ **Pipeline bu dosyaları deploy ETMEZ!**

---

## 📋 Gerekli RBAC Kaynakları

| # | ClusterRole | ClusterRoleBinding | Açıklama |
|---|-------------|-------------------|----------|
| 1 | `inspektor-gadget` | `inspektor-gadget` | Gadget DaemonSet için node/pod erişimi |
| 2 | `flowfish-gadget-reader` | `flowfish-gadget-reader-binding` | kubectl-gadget için cross-namespace erişim |

---

## 🚀 Uygulama

### Tek Komut ile Tümünü Uygula

```bash
NS=pilot-flowfish

# Tüm RBAC'ı uygula
cat <<'EOF' | sed "s/pilot-flowfish/$NS/g" | oc apply -f -
# ============================================
# 1. Inspektor Gadget ClusterRole
# ============================================
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: inspektor-gadget
rules:
- apiGroups: [""]
  resources: ["pods", "nodes", "namespaces", "configmaps", "services", "events"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apiextensions.k8s.io"]
  resources: ["customresourcedefinitions"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: inspektor-gadget
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: inspektor-gadget
subjects:
- kind: ServiceAccount
  name: inspektor-gadget
  namespace: pilot-flowfish
---
# ============================================
# 2. Flowfish kubectl-gadget ClusterRole
# ============================================
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flowfish-gadget-reader
rules:
- apiGroups: [""]
  resources: ["pods", "namespaces", "nodes"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["pods/portforward", "pods/exec", "pods/log"]
  verbs: ["create", "get"]
- apiGroups: ["gadget.kinvolk.io"]
  resources: ["traces"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
  verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flowfish-gadget-reader-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flowfish-gadget-reader
subjects:
- kind: ServiceAccount
  name: flowfish
  namespace: pilot-flowfish
EOF

# SCC izni ver
oc adm policy add-scc-to-user privileged -z inspektor-gadget -n $NS
```

---

## ✅ Doğrulama

```bash
NS=pilot-flowfish

echo "=== ClusterRole'ler ===" && \
oc get clusterrole | grep -E "inspektor-gadget|flowfish-gadget" && \
echo -e "\n=== ClusterRoleBinding'ler ===" && \
oc get clusterrolebinding | grep -E "inspektor-gadget|flowfish-gadget" && \
echo -e "\n=== İzin Testleri ===" && \
echo -n "inspektor-gadget list pods: " && \
oc auth can-i list pods --as=system:serviceaccount:$NS:inspektor-gadget -A && \
echo -n "flowfish list pods: " && \
oc auth can-i list pods --as=system:serviceaccount:$NS:flowfish -A && \
echo -n "flowfish create traces: " && \
oc auth can-i create traces.gadget.kinvolk.io --as=system:serviceaccount:$NS:flowfish -A && \
echo -n "flowfish portforward: " && \
oc auth can-i create pods/portforward --as=system:serviceaccount:$NS:flowfish -n $NS
```

**Beklenen Çıktı:**
```
=== ClusterRole'ler ===
flowfish-gadget-reader   2025-11-26T23:19:34Z
inspektor-gadget         2025-11-26T23:00:00Z

=== ClusterRoleBinding'ler ===
flowfish-gadget-reader-binding   ClusterRole/flowfish-gadget-reader   1h
inspektor-gadget                 ClusterRole/inspektor-gadget         1h

=== İzin Testleri ===
inspektor-gadget list pods: yes
flowfish list pods: yes
flowfish create traces: yes
flowfish portforward: yes
```

---

## 🔒 Güvenlik Notu

Bu RBAC izinleri:

| Resource | İzinler | Risk |
|----------|---------|------|
| pods | get, list, watch | ✅ Okuma - Risk yok |
| pods/portforward | create, get | ⚠️ kubectl-gadget bağlantısı için gerekli |
| pods/exec | create, get | ⚠️ kubectl-gadget bağlantısı için gerekli |
| pods/log | create, get | ✅ Log okuma - Risk yok |
| namespaces | get, list, watch | ✅ Okuma - Risk yok |
| nodes | get, list, watch | ✅ Okuma - Risk yok |
| deployments | get, list, watch | ✅ Okuma - Risk yok |
| traces.gadget.kinvolk.io | CRUD | ⚠️ Sadece Gadget CRD - Workload'ları etkilemez |

> **Not:** `pods/portforward` ve `pods/exec` izinleri, kubectl-gadget'ın Inspektor Gadget
> pod'larına bağlanması için zorunludur. Bu izinler sadece `flowfish` service account'u için
> verilir ve workload'ları değiştirmez.

---

## 🗑️ Kaldırma

```bash
# Tüm RBAC'ı kaldır
oc delete clusterrolebinding inspektor-gadget flowfish-gadget-reader-binding
oc delete clusterrole inspektor-gadget flowfish-gadget-reader

# SCC'yi kaldır
oc adm policy remove-scc-from-user privileged -z inspektor-gadget -n $NS
```
