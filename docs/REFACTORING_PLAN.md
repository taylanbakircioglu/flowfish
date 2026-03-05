# Cluster Connection Manager - Refactoring Plan

## ✅ TAMAMLANDI - 23 Aralık 2025

Bu refactoring planı başarıyla tamamlandı. Tüm fazlar uygulandı ve mevcut fonksiyonellik korunarak, merkezi bir `ClusterConnectionManager` mimarisine geçildi.

## Executive Summary

Bu plan, mevcut dağınık cluster bağlantı yönetimini merkezi bir `ClusterConnectionManager` servisine taşımayı amaçlar. Mevcut fonksiyonellik korunarak, aşamalı bir geçiş yapılacaktır.

---

## 1. ETKİ ANALİZİ

### 1.1 Mevcut Servisler ve Sorumlulukları

| Servis | Dosya | Sorumluluk | Kullanım |
|--------|-------|------------|----------|
| `cluster_info_service` | `services/cluster_info_service.py` | Remote K8s API erişimi (token/kubeconfig) | clusters.py, cluster_cache_service.py |
| `cluster_manager_client` | `grpc_clients/cluster_manager_client.py` | In-cluster gRPC (cluster-manager pod) | clusters.py, cluster_cache_service.py, namespaces.py |
| `cluster_cache_service` | `services/cluster_cache_service.py` | Redis cache layer | namespaces.py, clusters.py |
| `kubernetes_service` | `services/kubernetes_service.py` | Cluster CRUD, connection test | clusters.py |

### 1.2 Fonksiyon Kullanım Haritası

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ROUTER LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  clusters.py                                                                 │
│  ├── sync_cluster_data()                                                    │
│  │   ├── cluster_manager_client.get_cluster_info() [in-cluster]            │
│  │   ├── cluster_info_service.get_cluster_info() [remote]                  │
│  │   ├── cluster_manager_client.check_gadget_health() [in-cluster]         │
│  │   └── cluster_info_service.check_gadget_health() [remote]               │
│  │                                                                          │
│  ├── get_cluster() → [line 1509-1540]                                       │
│  │   ├── cluster_manager_client.get_cluster_info() [in-cluster]            │
│  │   ├── cluster_info_service.get_cluster_info() [remote]                  │
│  │   └── cluster_manager_client.check_gadget_health()                       │
│  │                                                                          │
│  └── test_cluster_connection()                                              │
│      ├── cluster_manager_client.get_cluster_info() [in-cluster]            │
│      ├── cluster_info_service.get_cluster_info() [token/kubeconfig]        │
│      ├── cluster_manager_client.check_gadget_health() [in-cluster]         │
│      └── Direct HTTP to gadget_endpoint [remote] *YENİ EKLENDİ*            │
│                                                                              │
│  namespaces.py                                                               │
│  ├── get_namespaces() → cluster_cache_service.get_namespaces()             │
│  ├── get_deployments() → cluster_cache_service.get_deployments()           │
│  ├── get_pods() → cluster_cache_service.get_pods()                          │
│  ├── get_labels() → cluster_cache_service.get_labels()                      │
│  └── get_services() → cluster_manager_client.list_services() [direct]      │
│                                                                              │
│  workloads.py                                                                │
│  └── get_workloads() → Database only (no K8s API)                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SERVICE LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  cluster_cache_service.py                                                    │
│  ├── get_cluster_info()                                                      │
│  │   ├── cluster_info_service.get_cluster_info() [remote]                  │
│  │   └── cluster_manager_client.get_cluster_info() [in-cluster]            │
│  │                                                                          │
│  ├── get_namespaces()                                                        │
│  │   ├── cluster_info_service.get_namespaces() [remote]                    │
│  │   └── cluster_manager_client.list_namespaces() [in-cluster]             │
│  │                                                                          │
│  ├── get_deployments()                                                       │
│  │   ├── cluster_info_service.get_deployments() [remote]                   │
│  │   └── cluster_manager_client.list_deployments() [in-cluster]            │
│  │                                                                          │
│  ├── get_pods()                                                              │
│  │   └── cluster_manager_client.list_pods() [both - TODO: add remote]      │
│  │                                                                          │
│  ├── get_labels()                                                            │
│  │   ├── cluster_info_service.get_labels() [remote]                        │
│  │   └── cluster_manager_client.get_labels() [in-cluster]                  │
│  │                                                                          │
│  └── get_gadget_health()                                                     │
│      └── cluster_manager_client.check_gadget_health() [in-cluster only!]   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Kritik Bağımlılıklar

| Bağımlılık | Risk | Etki |
|------------|------|------|
| `cluster_manager_client` gRPC proto | YÜKSEK | Proto değişirse tüm in-cluster çağrılar bozulur |
| `cluster_info_service` K8s client | ORTA | Token/kubeconfig geçersizse remote cluster erişimi yok |
| Redis cache | DÜŞÜK | Cache yoksa sadece performans düşer |
| PostgreSQL credentials | YÜKSEK | Şifreli token/cert okunamazsa remote erişim yok |

### 1.4 Eksiklikler (Mevcut Sistem)

1. ❌ `cluster_cache_service.get_pods()` - Remote cluster için `cluster_info_service.get_pods()` YOK
2. ❌ `cluster_cache_service.get_gadget_health()` - Remote cluster desteği YOK
3. ❌ `namespaces.py/get_services()` - Remote cluster desteği YOK
4. ❌ Connection pooling YOK
5. ❌ Credential refresh/rotation YOK
6. ❌ Circuit breaker YOK

---

## 2. REFACTORING PLANI

### Faz 0: Hazırlık (Mevcut Kodu Stabilize Et)
**Süre: 30 dakika**

- [x] Mevcut test connection düzeltmesi (gadget HTTP)
- [ ] Eksik `get_pods()` metodunu `cluster_info_service`'e ekle
- [ ] Eksik `get_services()` metodunu `cluster_info_service`'e ekle
- [ ] Remote gadget health check metodunu `cluster_info_service`'e ekle

### Faz 1: ClusterConnectionManager Skeleton
**Süre: 1 saat**

Yeni dosya: `backend/services/cluster_connection_manager.py`

```python
class ClusterConnectionManager:
    """
    Unified cluster connection manager.
    Single entry point for all cluster operations.
    """
    
    # Connection Management
    async def get_connection(cluster_id: int) -> ClusterConnection
    async def test_connection(config: ConnectionConfig) -> TestResult
    async def close_connection(cluster_id: int)
    async def close_all()
    
    # Cluster Info
    async def get_cluster_info(cluster_id: int) -> ClusterInfo
    async def get_namespaces(cluster_id: int) -> List[Namespace]
    async def get_deployments(cluster_id: int, namespace: str) -> List[Deployment]
    async def get_pods(cluster_id: int, namespace: str) -> List[Pod]
    async def get_services(cluster_id: int, namespace: str) -> List[Service]
    async def get_labels(cluster_id: int, namespace: str) -> List[Label]
    
    # Gadget
    async def check_gadget_health(cluster_id: int) -> GadgetHealth
    
    # Health Monitoring
    async def health_check_all() -> Dict[int, HealthStatus]
```

### Faz 2: ClusterConnection Abstraction
**Süre: 1.5 saat**

Yeni dosya: `backend/services/connections/base.py`

```python
class ClusterConnection(ABC):
    """Abstract base for cluster connections"""
    
    @abstractmethod
    async def get_k8s_client(self) -> ApiClient
    
    @abstractmethod
    async def get_cluster_info(self) -> ClusterInfo
    
    @abstractmethod
    async def check_gadget_health(self) -> GadgetHealth
```

Yeni dosya: `backend/services/connections/in_cluster.py`

```python
class InClusterConnection(ClusterConnection):
    """Uses cluster-manager gRPC"""
    
    def __init__(self):
        self._grpc_client = cluster_manager_client
```

Yeni dosya: `backend/services/connections/remote_token.py`

```python
class RemoteTokenConnection(ClusterConnection):
    """Direct K8s API with token auth"""
    
    def __init__(self, api_url, token, ca_cert, skip_tls):
        self._config = self._create_config()
```

### Faz 3: Mevcut Servisleri Adapter Pattern ile Wrap Et
**Süre: 1 saat**

```python
# cluster_connection_manager.py

class ClusterConnectionManager:
    def __init__(self):
        self._connections: Dict[int, ClusterConnection] = {}
        
        # Wrap existing services (backward compatibility)
        self._cluster_info_service = cluster_info_service
        self._cluster_manager_client = cluster_manager_client
```

**ÖNEMLİ**: Bu aşamada mevcut servisler DEĞİŞTİRİLMEZ, sadece wrap edilir.

### Faz 4: Router Migration (Aşamalı)
**Süre: 2 saat**

#### 4.1 clusters.py Güncellemesi

```python
# ÖNCE (mevcut)
cluster_info = await cluster_info_service.get_cluster_info(...)

# SONRA (yeni)
cluster_info = await cluster_connection_manager.get_cluster_info(cluster_id)
```

#### 4.2 namespaces.py Güncellemesi

```python
# ÖNCE (mevcut)
services = await cluster_manager_client.list_services(...)

# SONRA (yeni)
services = await cluster_connection_manager.get_services(cluster_id, namespace)
```

### Faz 5: Cache Service Integration
**Süre: 1 saat**

`cluster_cache_service.py` → `ClusterConnectionManager` kullanacak şekilde güncelle:

```python
# ÖNCE
if self._is_remote_cluster(connection_info):
    data = await cluster_info_service.get_cluster_info(...)
else:
    data = await cluster_manager_client.get_cluster_info(...)

# SONRA
data = await cluster_connection_manager.get_cluster_info(cluster_id)
```

### Faz 6: Health Monitoring (Background Task)
**Süre: 1 saat**

```python
# backend/services/health/cluster_health_monitor.py

class ClusterHealthMonitor:
    """Background task for periodic health checks"""
    
    async def start(self):
        while True:
            await self._check_all_clusters()
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
    
    async def _check_all_clusters(self):
        clusters = await self._get_active_clusters()
        for cluster in clusters:
            try:
                health = await cluster_connection_manager.check_gadget_health(cluster.id)
                await self._update_health_status(cluster.id, health)
            except Exception as e:
                logger.error("Health check failed", cluster_id=cluster.id, error=str(e))
```

### Faz 7: Cleanup ve Deprecation
**Süre: 30 dakika**

1. Eski servisleri deprecated olarak işaretle
2. Import warning'leri ekle
3. Dokümantasyon güncelle

---

## 3. DOSYA YAPISI (SONUÇ)

```
backend/
├── services/
│   ├── cluster_connection_manager.py    # YENİ - Merkezi Manager
│   ├── connections/                      # YENİ - Connection implementations
│   │   ├── __init__.py
│   │   ├── base.py                       # Abstract base class
│   │   ├── in_cluster.py                 # InClusterConnection
│   │   ├── remote_token.py               # RemoteTokenConnection
│   │   └── remote_kubeconfig.py          # RemoteKubeconfigConnection
│   ├── health/                           # YENİ - Health monitoring
│   │   ├── __init__.py
│   │   └── cluster_health_monitor.py
│   │
│   ├── cluster_info_service.py           # MEVCUT - Deprecate sonra
│   ├── cluster_cache_service.py          # MEVCUT - Güncelle
│   ├── kubernetes_service.py             # MEVCUT - Koru
│   └── event_service.py                  # MEVCUT - Değişmez
│
├── grpc_clients/
│   └── cluster_manager_client.py         # MEVCUT - Internal kullanım
│
└── routers/
    ├── clusters.py                       # Güncelle
    └── namespaces.py                     # Güncelle
```

---

## 4. MİGRASYON TABLOSU

| Mevcut Çağrı | Yeni Çağrı | Dosya |
|--------------|------------|-------|
| `cluster_info_service.get_cluster_info()` | `ccm.get_cluster_info()` | clusters.py |
| `cluster_manager_client.get_cluster_info()` | `ccm.get_cluster_info()` | clusters.py |
| `cluster_info_service.check_gadget_health()` | `ccm.check_gadget_health()` | clusters.py |
| `cluster_manager_client.check_gadget_health()` | `ccm.check_gadget_health()` | clusters.py, cache |
| `cluster_info_service.get_namespaces()` | `ccm.get_namespaces()` | cache |
| `cluster_manager_client.list_namespaces()` | `ccm.get_namespaces()` | cache |
| `cluster_info_service.get_deployments()` | `ccm.get_deployments()` | cache |
| `cluster_manager_client.list_deployments()` | `ccm.get_deployments()` | cache |
| `cluster_manager_client.list_pods()` | `ccm.get_pods()` | cache |
| `cluster_info_service.get_labels()` | `ccm.get_labels()` | cache |
| `cluster_manager_client.get_labels()` | `ccm.get_labels()` | cache |
| `cluster_manager_client.list_services()` | `ccm.get_services()` | namespaces.py |

---

## 5. RİSK YÖNETİMİ

### 5.1 Rollback Stratejisi

Her faz için rollback:
- **Faz 1-3**: Yeni dosyaları sil, import'ları kaldır
- **Faz 4-5**: Git revert ile eski router/service koduna dön
- **Faz 6**: Background task'ı devre dışı bırak

### 5.2 Test Stratejisi

Her faz sonrası test:
1. ✅ In-cluster connection çalışıyor mu?
2. ✅ Remote token connection çalışıyor mu?
3. ✅ Cache çalışıyor mu?
4. ✅ Gadget health check çalışıyor mu?
5. ✅ UI cluster listesi yükleniyor mu?
6. ✅ UI test connection çalışıyor mu?

### 5.3 Fallback Mekanizması

```python
class ClusterConnectionManager:
    async def get_cluster_info(self, cluster_id: int):
        try:
            # Yeni yöntem
            connection = await self.get_connection(cluster_id)
            return await connection.get_cluster_info()
        except Exception as e:
            # Fallback: Eski yöntem
            logger.warning("Falling back to legacy service", error=str(e))
            return await self._legacy_get_cluster_info(cluster_id)
```

---

## 6. UYGULAMA TAKVİMİ

| Faz | Görev | Süre | Kümülatif |
|-----|-------|------|-----------|
| 0 | Hazırlık - Eksik metodları ekle | 30 dk | 30 dk |
| 1 | ClusterConnectionManager skeleton | 1 saat | 1.5 saat |
| 2 | Connection abstractions | 1.5 saat | 3 saat |
| 3 | Adapter pattern wrap | 1 saat | 4 saat |
| 4 | Router migration | 2 saat | 6 saat |
| 5 | Cache service integration | 1 saat | 7 saat |
| 6 | Health monitoring | 1 saat | 8 saat |
| 7 | Cleanup & docs | 30 dk | 8.5 saat |

**TOPLAM: ~8.5 saat (yaklaşık 1-2 iş günü)**

---

## 7. BAŞLANGIÇ NOKTASI

**Faz 0'dan başlıyoruz:**

1. `cluster_info_service`'e eksik metodları ekle:
   - `get_pods()`
   - `get_services()`
   - `check_gadget_health_remote()` (HTTP-based)

2. Mevcut test connection fix'ini commit'le

Başlamak için onayınızı bekliyorum.

