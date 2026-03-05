# Flowfish Cluster Connectivity Architecture

## ✅ IMPLEMENTED - December 2025

This architecture has been fully implemented with the `ClusterConnectionManager` refactoring.

---

## Current Architecture (Implemented)

### Features Implemented
- ✅ Connection pooling (per-cluster connection caching)
- ✅ Credential caching and decryption
- ✅ Unified error handling
- ✅ Background health monitoring with circuit breaker
- ✅ Abstract connection types (InCluster, RemoteToken)

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RECOMMENDED ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐                                                           │
│   │  Backend    │                                                           │
│   │  API        │                                                           │
│   └──────┬──────┘                                                           │
│          │                                                                   │
│          ▼                                                                   │
│   ┌──────────────────────────────────────────────────────────────┐          │
│   │              UNIFIED CLUSTER MANAGER SERVICE                  │          │
│   │                                                               │          │
│   │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │          │
│   │  │ Connection Pool │  │ Credential Mgmt │  │ Health Check │  │          │
│   │  │ (per cluster)   │  │ (encrypted)     │  │ (periodic)   │  │          │
│   │  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘  │          │
│   │           │                    │                   │          │          │
│   │           └────────────────────┼───────────────────┘          │          │
│   │                                │                              │          │
│   │                                ▼                              │          │
│   │  ┌─────────────────────────────────────────────────────────┐ │          │
│   │  │                   CLUSTER CONNECTIONS                    │ │          │
│   │  │                                                          │ │          │
│   │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │ │          │
│   │  │  │ Cluster 1    │  │ Cluster 2    │  │ Cluster N    │   │ │          │
│   │  │  │ (in-cluster) │  │ (remote)     │  │ (remote)     │   │ │          │
│   │  │  │              │  │              │  │              │   │ │          │
│   │  │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │   │ │          │
│   │  │  │ │ K8s API  │ │  │ │ K8s API  │ │  │ │ K8s API  │ │   │ │          │
│   │  │  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │   │ │          │
│   │  │  │ ┌──────────┐ │  │ ┌──────────┐ │  │ ┌──────────┐ │   │ │          │
│   │  │  │ │ Gadget   │ │  │ │ Gadget   │ │  │ │ Gadget   │ │   │ │          │
│   │  │  │ │ gRPC     │ │  │ │ HTTP/gRPC│ │  │ │ HTTP/gRPC│ │   │ │          │
│   │  │  │ └──────────┘ │  │ └──────────┘ │  │ └──────────┘ │   │ │          │
│   │  │  └──────────────┘  └──────────────┘  └──────────────┘   │ │          │
│   │  └─────────────────────────────────────────────────────────┘ │          │
│   └──────────────────────────────────────────────────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Unified ClusterConnectionManager

Create a single service that manages all cluster connections:

```python
# backend/services/cluster_connection_manager.py

class ClusterConnectionManager:
    """
    Unified manager for all cluster connections.
    Handles both in-cluster and remote cluster connections.
    """
    
    def __init__(self):
        self._connections: Dict[int, ClusterConnection] = {}
        self._connection_pool_size = 5
        self._health_check_interval = 30  # seconds
        
    async def get_connection(self, cluster_id: int) -> ClusterConnection:
        """Get or create a connection for a cluster"""
        
    async def test_connection(self, cluster_config: ClusterConfig) -> ConnectionTestResult:
        """Test connection before saving cluster"""
        
    async def health_check_all(self) -> Dict[int, HealthStatus]:
        """Periodic health check for all clusters"""
        
    async def refresh_credentials(self, cluster_id: int):
        """Refresh expired tokens/certificates"""
```

### Phase 2: ClusterConnection Class

```python
class ClusterConnection:
    """
    Represents a connection to a single cluster.
    Manages K8s API client and Gadget client.
    """
    
    def __init__(self, cluster_config: ClusterConfig):
        self.cluster_id = cluster_config.id
        self.connection_type = cluster_config.connection_type
        self._k8s_client: Optional[ApiClient] = None
        self._gadget_client: Optional[GadgetClient] = None
        self._last_health_check: Optional[datetime] = None
        
    @property
    def k8s_client(self) -> ApiClient:
        """Lazy-loaded K8s API client with connection pooling"""
        
    @property
    def gadget_client(self) -> GadgetClient:
        """Lazy-loaded Gadget gRPC/HTTP client"""
        
    async def get_cluster_info(self) -> ClusterInfo:
        """Get cluster information (nodes, pods, namespaces)"""
        
    async def check_gadget_health(self) -> GadgetHealth:
        """Check Inspector Gadget health status"""
        
    async def close(self):
        """Clean up connections"""
```

### Phase 3: Connection Types

```python
class InClusterConnection(ClusterConnection):
    """Connection for the cluster where Flowfish is deployed"""
    
    def _setup_k8s_client(self):
        config.load_incluster_config()
        return client.ApiClient()
        
    def _setup_gadget_client(self):
        # Use in-cluster service discovery
        return GadgetGrpcClient("inspektor-gadget.{namespace}:16060")


class RemoteTokenConnection(ClusterConnection):
    """Connection using ServiceAccount token"""
    
    def _setup_k8s_client(self):
        configuration = client.Configuration()
        configuration.host = self.api_server_url
        configuration.api_key = {"authorization": f"Bearer {self.token}"}
        configuration.verify_ssl = not self.skip_tls_verify
        if self.ca_cert:
            configuration.ssl_ca_cert = self._write_ca_cert()
        return client.ApiClient(configuration)
        
    def _setup_gadget_client(self):
        # Use external endpoint
        return GadgetHttpClient(self.gadget_endpoint)


class RemoteKubeconfigConnection(ClusterConnection):
    """Connection using kubeconfig file"""
    
    def _setup_k8s_client(self):
        config.load_kube_config(config_file=self._kubeconfig_path)
        return client.ApiClient()
```

---

## Best Practices

### 1. Connection Pooling
```python
# Use httpx connection pooling for HTTP clients
self._http_client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_keepalive_connections=5,
        max_connections=10,
        keepalive_expiry=30.0
    ),
    timeout=httpx.Timeout(10.0, connect=5.0)
)
```

### 2. Credential Management
```python
# Encrypt credentials at rest
from utils.encryption import encrypt_data, decrypt_data

class SecureCredentials:
    def __init__(self, token: str, ca_cert: Optional[str] = None):
        self._encrypted_token = encrypt_data(token)
        self._encrypted_ca_cert = encrypt_data(ca_cert) if ca_cert else None
        
    @property
    def token(self) -> str:
        return decrypt_data(self._encrypted_token)
```

### 3. Health Monitoring
```python
# Background health check task
async def health_monitor_task():
    while True:
        for cluster_id, connection in connections.items():
            try:
                health = await connection.check_health()
                await update_cluster_health_status(cluster_id, health)
            except Exception as e:
                logger.error(f"Health check failed for cluster {cluster_id}", error=str(e))
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
```

### 4. Graceful Degradation
```python
async def get_cluster_info(self, cluster_id: int) -> ClusterInfo:
    connection = await self.get_connection(cluster_id)
    
    # Try primary method
    try:
        return await connection.get_cluster_info()
    except ApiException as e:
        if e.status == 401:
            # Token expired, try refresh
            await self.refresh_credentials(cluster_id)
            return await connection.get_cluster_info()
        raise
```

### 5. Circuit Breaker Pattern
```python
from circuitbreaker import circuit

class ClusterConnection:
    @circuit(failure_threshold=3, recovery_timeout=60)
    async def get_cluster_info(self) -> ClusterInfo:
        """Protected by circuit breaker"""
        ...
```

---

## Migration Steps

1. **Create ClusterConnectionManager service**
2. **Migrate cluster_info_service methods**
3. **Migrate kubernetes_service methods**
4. **Update routers to use new manager**
5. **Add background health monitoring**
6. **Remove deprecated services**

---

## Security Considerations

1. **Credential Encryption**: All tokens and certificates encrypted at rest (Fernet)
2. **TLS Verification**: Default enabled, explicit opt-out required
3. **Token Rotation**: Support for short-lived tokens with refresh
4. **Audit Logging**: Log all cluster access operations
5. **Network Isolation**: Recommend network policies for gadget endpoints

---

## File Structure

```
backend/
├── services/
│   ├── cluster_connection_manager.py  # Main unified manager
│   ├── connections/
│   │   ├── __init__.py
│   │   ├── base.py                    # ClusterConnection base class
│   │   ├── in_cluster.py              # InClusterConnection
│   │   ├── remote_token.py            # RemoteTokenConnection
│   │   └── remote_kubeconfig.py       # RemoteKubeconfigConnection
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── gadget_client.py           # Unified Gadget client
│   │   └── k8s_client_factory.py      # K8s client factory
│   └── health/
│       ├── __init__.py
│       └── cluster_health_monitor.py  # Background health monitor
```

---

## Timeline Estimate

| Phase | Task | Duration |
|-------|------|----------|
| 1 | ClusterConnectionManager skeleton | 2 hours |
| 2 | Connection classes | 3 hours |
| 3 | Gadget client unification | 2 hours |
| 4 | Router migration | 2 hours |
| 5 | Health monitoring | 2 hours |
| 6 | Testing & cleanup | 3 hours |
| **Total** | | **~14 hours** |

---

## Implementation Status

### Completed Components

| Component | Status | Location |
|-----------|--------|----------|
| ClusterConnectionManager | ✅ Done | `services/cluster_connection_manager.py` |
| ClusterConnection Base | ✅ Done | `services/connections/base.py` |
| InClusterConnection | ✅ Done | `services/connections/in_cluster.py` |
| RemoteTokenConnection | ✅ Done | `services/connections/remote_token.py` |
| ClusterHealthMonitor | ✅ Done | `services/health/cluster_health_monitor.py` |
| Router Migration | ✅ Done | `routers/clusters.py`, `routers/namespaces.py` |
| Cache Integration | ✅ Done | `services/cluster_cache_service.py` |

### Current Data Flow (Direct Mode - Default)

```
┌─────────────────────────────────────────────────────────────────┐
│                        ROUTER LAYER                              │
│  clusters.py, namespaces.py                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CACHE LAYER (Redis)                         │
│  cluster_cache_service.py                                        │
│  - TTL-based caching (5 min)                                     │
│  - Stale-while-revalidate                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               UNIFIED CONNECTION LAYER                           │
│  cluster_connection_manager.py                                   │
│  - Connection pooling (Dict[int, ClusterConnection])             │
│  - Auto-detect connection type from DB                           │
│  - Fernet credential decryption                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│   InClusterConnection    │    │  RemoteTokenConnection   │
│   (gRPC to cluster-mgr)  │    │  (Direct K8s API)        │
└──────────────────────────┘    └──────────────────────────┘
              │                               │
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  cluster_manager_client  │    │  cluster_info_service    │
│  (gRPC Client)           │    │  (K8s Python Client)     │
└──────────────────────────┘    └──────────────────────────┘
```

---

## Gateway Pattern Architecture (January 2026)

### Overview

The Gateway Pattern centralizes ALL Kubernetes API access through the `cluster-manager` service.
This provides better security, unified credential management, and simplified network topology.

ALL remote cluster K8s API calls route through cluster-manager gRPC.

### Gateway Architecture Diagram

```
                                  ┌─────────────────────────────────────────────────────────────┐
                                  │                  flowfish namespace                          │
                                  │                                                              │
┌──────────────────┐              │  ┌─────────────────────────────────────────────────────┐    │
│                  │              │  │                 BACKEND POD                          │    │
│  change-         │              │  │                                                      │    │
│  detection-      │──gRPC────────┼─►│  ClusterConnectionManager                           │    │
│  worker          │              │  │         │                                            │    │
│                  │              │  │         ├── InClusterConnection ────────┐            │    │
└──────────────────┘              │  │         │                               │            │    │
                                  │  │         └── RemoteTokenConnection ──────┼────gRPC───┐│    │
                                  │  │                (USE_K8S_GATEWAY_MODE)   │           ││    │
                                  │  └─────────────────────────────────────────┼───────────┼┘    │
                                  │                                            │           │     │
                                  │  ┌─────────────────────────────────────────┼───────────┼─┐   │
                                  │  │           CLUSTER-MANAGER POD (GATEWAY) │           │ │   │
                                  │  │                                         │           │ │   │
                                  │  │  ┌────────────────────────────────┐     │           │ │   │
                                  │  │  │        gRPC Server :5001       │◄────┘           │ │   │
                                  │  │  │                                │◄────────────────┘ │   │
                                  │  │  │   _get_k8s_client(cluster_id)  │                   │   │
                                  │  │  └─────────────┬──────────────────┘                   │   │
                                  │  │                │                                      │   │
                                  │  │                ▼                                      │   │
                                  │  │  ┌────────────────────────────────┐                   │   │
                                  │  │  │   KubernetesClientFactory      │                   │   │
                                  │  │  │   - Client caching (TTL 5min)  │                   │   │
                                  │  │  │   - Connection pooling         │                   │   │
                                  │  │  └─────────────┬──────────────────┘                   │   │
                                  │  │                │                                      │   │
                                  │  │      ┌─────────┴─────────┐                            │   │
                                  │  │      ▼                   ▼                            │   │
                                  │  │  ┌────────┐        ┌────────────┐                     │   │
                                  │  │  │In-     │        │ Remote     │                     │   │
                                  │  │  │Cluster │        │ Clusters   │                     │   │
                                  │  │  │Client  │        │ (DB creds) │                     │   │
                                  │  │  └───┬────┘        └──────┬─────┘                     │   │
                                  │  │      │                    │                           │   │
                                  │  └──────┼────────────────────┼───────────────────────────┘   │
                                  │         │                    │                               │
                                  └─────────┼────────────────────┼───────────────────────────────┘
                                            │                    │
                                            ▼                    ▼
                                  ┌──────────────┐    ┌────────────────────────┐
                                  │ Local K8s    │    │   Remote Clusters      │
                                  │ API :6443    │    │   (Cluster 9, 12, ...) │
                                  └──────────────┘    │   via token + CA cert  │
                                                      └────────────────────────┘
```

### Gateway Implementation Details

#### cluster-manager Service Updates

```python
# services/cluster-manager/app/grpc_server.py

async def _get_k8s_client(self, cluster_id: str) -> KubernetesClient:
    """
    Get appropriate K8s client based on cluster_id.
    - cluster_id="default" or "0" -> in-cluster client
    - cluster_id=<numeric> -> fetch credentials from DB, create remote client
    """
    if not cluster_id or cluster_id == "default" or cluster_id == "0":
        return self.k8s_client  # In-cluster (singleton)
    
    # Fetch credentials from PostgreSQL
    cluster = await self._db.get_cluster_credentials(int(cluster_id))
    
    # Decrypt credentials and create client via factory
    return KubernetesClientFactory.get_client(
        cluster_id=cluster_id,
        connection_type=cluster["connection_type"],
        api_server_url=cluster["api_server_url"],
        token=_decrypt_value(cluster["token_encrypted"]),
        ca_cert=_decrypt_value(cluster["ca_cert_encrypted"])
    )
```

#### RemoteTokenConnection Implementation

```python
# backend/services/connections/remote_token.py

class RemoteTokenConnection(ClusterConnection):
    """
    Routes ALL K8s API calls through cluster-manager gRPC gateway.
    """
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._grpc_client = cluster_manager_client
    
    async def get_deployments(self, namespace: Optional[str] = None):
        result = await self._grpc_client.list_deployments(
            cluster_id=str(self.config.cluster_id),
            namespace=namespace or ""
        )
        # Convert to Deployment objects...
```

### Benefits of Gateway Pattern

1. **Centralized K8s API Access**: All access from single pod (better firewall rules)
2. **Unified Credential Management**: Decryption only in cluster-manager
3. **Connection Pooling**: Shared clients across requests
4. **Simplified Network Policies**: Only cluster-manager needs external access
5. **Single Audit Point**: All K8s API calls logged in one place

### Current State

Gateway mode is NOW the default and only mode for remote clusters.
All remote cluster K8s API calls route through cluster-manager gRPC.

**Rollback (if needed):**
```bash
git revert <commit-hash>
```

---

*Last Updated: January 2026*

