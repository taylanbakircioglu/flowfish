# Flowfish Security Guide

## 🔐 Multi-Cluster Security Architecture

Bu doküman, Flowfish'in uzak cluster'lara güvenli bağlantı kurma mekanizmalarını açıklar.

---

## 1. Kimlik Doğrulama (Authentication)

### Service Account Token
Remote cluster'lara bağlantı için **read-only ServiceAccount** kullanılır:

```yaml
# Minimum Required Permissions
rules:
  - apiGroups: [""]
    resources: ["pods", "nodes", "namespaces", "services", "events"]
    verbs: ["get", "list", "watch"]  # SADECE OKUMA
  - apiGroups: ["apps"]
    resources: ["deployments", "daemonsets", "replicasets", "statefulsets"]
    verbs: ["get", "list", "watch"]  # SADECE OKUMA
  - apiGroups: ["gadget.kinvolk.io"]
    resources: ["traces"]
    verbs: ["get", "list", "watch"]  # SADECE OKUMA
```

### Token Güvenliği
- ✅ Tokenlar Fernet (AES-128-CBC) ile şifrelenerek PostgreSQL'de saklanır
- ✅ Şifreleme anahtarı environment variable olarak geçirilir
- ❌ Token'ı kaynak kodda veya config dosyalarında saklamayın
- ❌ Token'ı log'lara yazdırmayın

### Token Oluşturma
```bash
# 1 yıllık token oluştur (production için daha kısa önerilir)
oc create token flowfish-remote-reader -n flowfish --duration=8760h
```

---

## 2. TLS/SSL Güvenliği

### CA Sertifikası Doğrulaması
Remote cluster bağlantısında **mutlaka** TLS doğrulama yapılmalıdır:

```
┌──────────────────┐          TLS          ┌──────────────────┐
│   Flowfish       │ ◄──────────────────── │   Remote         │
│   (Internal)     │  CA Cert Verified     │   Cluster        │
└──────────────────┘                        └──────────────────┘
```

### Yapılandırma Seçenekleri

| Seçenek | Açıklama | Güvenlik |
|---------|----------|----------|
| CA Certificate | Remote cluster'ın CA sertifikası | ✅ Önerilen |
| Skip TLS Verify | TLS doğrulamayı atla | ⚠️ Sadece test ortamı |

### CA Sertifikası Alma
```bash
# OpenShift/Kubernetes'ten CA sertifikasını al
oc get secret flowfish-reader-token -n flowfish -o jsonpath='{.data.ca\.crt}' | base64 -d
```

---

## 3. Network Güvenliği

### Inspector Gadget gRPC Bağlantısı

```
┌──────────────────┐                        ┌──────────────────┐
│   Flowfish       │     gRPC:16060         │   Remote         │
│   Ingestion      │ ──────────────────────►│   Inspector      │
│   Service        │     (LoadBalancer)     │   Gadget         │
└──────────────────┘                        └──────────────────┘
```

### Önerilen Network Politikaları

```yaml
# Remote cluster'da Inspector Gadget için NetworkPolicy
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-flowfish-ingress
  namespace: flowfish
spec:
  podSelector:
    matchLabels:
      app: inspektor-gadget
  ingress:
    - from:
        - ipBlock:
            cidr: 10.0.0.0/8  # Flowfish internal cluster IP range
      ports:
        - protocol: TCP
          port: 16060
```

---

## 4. Şifreleme Yapılandırması

### Encryption Key Oluşturma
```bash
# Yeni Fernet key oluştur
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Kubernetes Secret Olarak Saklama
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: flowfish-encryption-key
  namespace: flowfish
type: Opaque
stringData:
  FLOWFISH_ENCRYPTION_KEY: "your-generated-fernet-key-here"
```

### Deployment'a Ekleme
```yaml
env:
  - name: FLOWFISH_ENCRYPTION_KEY
    valueFrom:
      secretKeyRef:
        name: flowfish-encryption-key
        key: FLOWFISH_ENCRYPTION_KEY
```

---

## 5. Yetkilendirme (Authorization)

### RBAC Prensipleri

| Prensip | Uygulama |
|---------|----------|
| **Least Privilege** | Sadece gerekli minimum yetkiler |
| **Read-Only** | GET, LIST, WATCH - CREATE/UPDATE/DELETE yok |
| **Namespace Scoped** | Mümkünse ClusterRole yerine Role kullan |
| **Audit Trail** | Tüm erişimler loglanır |

### Yetki Matrisi

| Kaynak | get | list | watch | create | update | delete |
|--------|-----|------|-------|--------|--------|--------|
| pods | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| nodes | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| namespaces | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| deployments | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| traces | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |

---

## 6. Güvenlik Kontrol Listesi

### Production Deployment Öncesi

- [ ] `FLOWFISH_ENCRYPTION_KEY` environment variable ayarlandı
- [ ] Remote cluster için read-only ServiceAccount oluşturuldu
- [ ] CA sertifikası yapılandırıldı (skip_tls_verify = false)
- [ ] NetworkPolicy'ler uygulandı
- [ ] Token süresi uygun (önerilen: 90 gün, max: 1 yıl)
- [ ] Audit logging aktif

### Periyodik Güvenlik Görevleri

| Görev | Sıklık |
|-------|--------|
| Token rotasyonu | Her 90 gün |
| RBAC audit | Aylık |
| CA sertifikası yenileme | Sertifika süresine göre |
| Güvenlik log incelemesi | Haftalık |

---

## 7. Sorun Giderme

### TLS Hataları
```
SSL: CERTIFICATE_VERIFY_FAILED
```
**Çözüm:** CA sertifikasını kontrol edin veya yeniden indirin.

### Yetki Hataları
```
403 Forbidden - User cannot list resource
```
**Çözüm:** ClusterRoleBinding'in doğru namespace ve ServiceAccount'a bağlı olduğunu kontrol edin.

### Token Süresi Dolmuş
```
401 Unauthorized - Token expired
```
**Çözüm:** Yeni token oluşturun:
```bash
oc create token flowfish-remote-reader -n flowfish --duration=2160h
```

---

## 8. İletişim

Güvenlik açıkları için: security@flowfish.io

