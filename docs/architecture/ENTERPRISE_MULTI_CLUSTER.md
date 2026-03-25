# 🏢 Enterprise Multi-Cluster Architecture

## 📋 Overview

The Flowfish enterprise architecture supports Kubernetes/OpenShift clusters in different locations, with different security levels, and different network topologies.

---

## 🎯 Enterprise Requirements

### 1. Multi-Cluster Support
- ✅ On-premise Kubernetes clusters
- ✅ Cloud-hosted Kubernetes (AWS EKS, Azure AKS, GCP GKE)
- ✅ OpenShift clusters (on-premise, ARO, ROSA, RHOCP)
- ✅ Hybrid environments (on-prem + cloud)
- ✅ Edge clusters (restricted network)

### 2. Protocol Flexibility
- ✅ gRPC (high performance, bi-directional streaming)
- ✅ HTTP/REST (firewall-friendly, simple)
- ✅ WebSocket (real-time, NAT-friendly)
- ✅ Agent-based (secure remote access)

### 3. Security Requirements
- ✅ mTLS (mutual TLS authentication)
- ✅ API key authentication
- ✅ Service Account tokens
- ✅ OAuth2/OIDC integration
- ✅ Network isolation
- ✅ Data encryption at rest and in transit

### 4. Scalability
- ✅ 100+ clusters supported
- ✅ Geo-distributed deployments
- ✅ High availability (HA)
- ✅ Horizontal scaling

---

## 🏗️ Architecture Patterns

### Pattern 1: Direct gRPC Connection (Same Network)

**Use Case:** Flowfish and the target cluster are in the same Kubernetes/OpenShift environment

```
┌─────────────────────────────────────────────┐
│           Kubernetes Cluster                │
│                                             │
│  ┌──────────────┐         ┌──────────────┐ │
│  │  Flowfish    │ gRPC    │  Inspektor   │ │
│  │  Backend     ├────────>│  Gadget      │ │
│  └──────────────┘ :16060  └──────────────┘ │
│                                             │
└─────────────────────────────────────────────┘

✅ Best Performance
✅ Low Latency
✅ No extra components
❌ Same cluster only
```

**Configuration:**
```yaml
cluster:
  name: "local-k8s"
  connection_type: "in-cluster"
  protocol: "kubectl"  # Uses kubectl gadget CLI via K8s API
  gadget_namespace: "flowfish"  # REQUIRED from UI
  # gadget_endpoint is auto-constructed: inspektor-gadget.flowfish.svc.cluster.local:16060
```

---

### Pattern 2: Direct HTTP/REST Connection (Cross-Network)

**Use Case:** Remote cluster, behind firewall/proxy, gRPC blocked

```
┌────────────────┐                   ┌────────────────┐
│   Flowfish     │                   │  Remote K8s    │
│   Backend      │   HTTP/REST       │                │
│                ├──────────────────>│  Inspektor     │
│                │   :443 (TLS)      │  Gadget        │
│                │                   │  (HTTP Adapter)│
└────────────────┘                   └────────────────┘
      HQ                                Remote Site

✅ Firewall-friendly
✅ Works through HTTP proxies
✅ Standard ports (443)
❌ Slower than gRPC
❌ No bi-directional streaming
```

**Configuration:**
```yaml
cluster:
  name: "remote-eks"
  connection_type: "token"  # or "kubeconfig"
  protocol: "kubectl"  # Uses kubectl gadget CLI via K8s API
  gadget_namespace: "flowfish"  # REQUIRED from UI
  api_server_url: "https://api.remote-cluster.company.com:6443"
  token: "<encrypted-service-account-token>"
  ca_cert: "<encrypted-ca-certificate>"
  skip_tls_verify: false
```

---

### Pattern 3: Agent-Based Connection (Secure Remote)

**Use Case:** Production clusters, strict security, NAT/firewall, audit requirements

```
┌────────────────┐                   ┌────────────────────┐
│   Flowfish     │                   │  Remote Cluster    │
│   Backend      │                   │                    │
│                │                   │  ┌──────────────┐  │
│                │   gRPC/HTTP       │  │  Flowfish    │  │
│                │<──────────────────┼──┤  Agent       │  │
│                │   (Agent pulls)   │  │  (DaemonSet) │  │
│                │                   │  └──────┬───────┘  │
│                │                   │         │          │
└────────────────┘                   │         │ local    │
      HQ                             │         ▼          │
                                     │  ┌──────────────┐  │
                                     │  │  Inspektor   │  │
                                     │  │  Gadget      │  │
                                     │  └──────────────┘  │
                                     └────────────────────┘

✅ Most Secure (agent initiates connection)
✅ Works behind NAT/firewall
✅ No inbound ports needed
✅ Full audit trail
✅ Rate limiting & throttling
❌ Extra component (agent)
❌ More complex deployment
```

**Configuration:**
```yaml
cluster:
  name: "prod-openshift"
  connection_type: "agent"
  protocol: "grpc"
  agent_endpoint: "flowfish-agent.production.svc.cluster.local:16061"
  use_tls: true
  auth_method: "mtls"
  client_cert: "<encrypted-cert>"
  client_key: "<encrypted-key>"
  ca_cert: "<ca-cert>"
```

---

## 📊 Protocol Comparison

| Feature | gRPC | HTTP/REST | WebSocket | Agent-Based |
|---------|------|-----------|-----------|-------------|
| **Performance** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Firewall-Friendly** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Bi-directional Streaming** | ✅ | ❌ | ✅ | ✅ |
| **NAT Traversal** | ❌ | ⚠️ | ✅ | ✅ |
| **Setup Complexity** | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Security** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Best For** | Same network | Public APIs | Real-time web | Prod/secure |

---

## 🔐 Security Models

### Model 1: API Key Authentication (HTTP/REST)

```python
# Request header
Authorization: Bearer <api-key>
X-Cluster-ID: prod-cluster-01
```

**Advantages:**
- Simple implementation
- Easy rotation
- Works with load balancers

**Disadvantages:**
- Key compromise risk
- No client verification

---

### Model 2: mTLS (Mutual TLS)

```python
# Both client and server verify each other
Client Cert → Server validates → Server Cert → Client validates
```

**Advantages:**
- Strongest authentication
- Bidirectional trust
- PKI infrastructure

**Disadvantages:**
- Certificate management complexity
- Rotation requires coordination

---

### Model 3: Service Account Token (In-Cluster)

```yaml
# Kubernetes ServiceAccount
serviceAccount:
  name: flowfish-collector
  namespace: flowfish
```

**Advantages:**
- Native Kubernetes auth
- Automatic rotation
- RBAC integration

**Disadvantages:**
- In-cluster only
- Namespace-scoped

---

## 🔧 Implementation Architecture

### Backend: Protocol Abstraction Layer

```python
# Abstract base class
class AbstractGadgetClient(ABC):
    @abstractmethod
    async def connect(self) -> bool:
        pass
    
    @abstractmethod
    async def start_trace(self, config: TraceConfig) -> str:
        pass
    
    @abstractmethod
    async def stream_events(self, trace_id: str) -> AsyncIterator[Event]:
        pass
    
    @abstractmethod
    async def stop_trace(self, trace_id: str) -> bool:
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        pass

# Implementations
class GRPCGadgetClient(AbstractGadgetClient):
    """Direct gRPC connection to Inspektor Gadget"""
    pass

class HTTPGadgetClient(AbstractGadgetClient):
    """HTTP/REST connection for remote clusters"""
    pass

class AgentGadgetClient(AbstractGadgetClient):
    """Agent-based connection for secure remote access"""
    pass

class WebSocketGadgetClient(AbstractGadgetClient):
    """WebSocket connection for real-time streaming"""
    pass
```

---

### Cluster Configuration Model

```python
class ClusterConfig:
    # Basic info
    cluster_id: int
    name: str
    environment: str  # dev, staging, prod
    
    # Connection
    connection_type: str  # in-cluster, token, kubeconfig
    protocol: str = "kubectl"  # kubectl (recommended), grpc, http (deprecated)
    
    # Endpoints
    api_server_url: str
    gadget_namespace: str  # REQUIRED from UI
    gadget_endpoint: Optional[str] = None  # Deprecated - auto-constructed
    agent_endpoint: Optional[str] = None  # Future: for agent-based connections
    
    # Authentication
    auth_method: str  # token, api_key, mtls, oauth
    kubeconfig: Optional[str]
    token: Optional[str]
    api_key: Optional[str]
    client_cert: Optional[str]
    client_key: Optional[str]
    ca_cert: Optional[str]
    
    # TLS/Security
    use_tls: bool = True
    verify_tls: bool = True
    
    # Network
    use_proxy: bool = False
    proxy_url: Optional[str]
    
    # Performance
    timeout_seconds: int = 30
    max_retries: int = 3
    
    # Features
    supports_streaming: bool = True
    supports_push: bool = False  # Agent pushes data
    supports_pull: bool = True   # Backend pulls data
```

---

### Factory Pattern for Client Creation

```python
class GadgetClientFactory:
    """Factory for creating appropriate gadget client based on config"""
    
    @staticmethod
    def create_client(cluster_config: ClusterConfig) -> AbstractGadgetClient:
        protocol = cluster_config.protocol.lower()
        
        # RECOMMENDED: kubectl-gadget CLI via K8s API (works for both in-cluster and remote)
        if protocol == "kubectl":
            return KubectlGadgetClient(
                gadget_namespace=cluster_config.gadget_namespace,  # REQUIRED from UI
                api_server_url=cluster_config.api_server_url,
                token=cluster_config.token,
                ca_cert=cluster_config.ca_cert,
                kubeconfig=cluster_config.kubeconfig,
                skip_tls_verify=not cluster_config.verify_tls
            )
        
        # DEPRECATED: Direct gRPC (requires network access to port 16060)
        elif protocol == "grpc":
            endpoint = cluster_config.gadget_endpoint or f"inspektor-gadget.{cluster_config.gadget_namespace}:16060"
            return GRPCGadgetClient(
                endpoint=endpoint,
                use_tls=cluster_config.use_tls,
                client_cert=cluster_config.client_cert,
                client_key=cluster_config.client_key,
                ca_cert=cluster_config.ca_cert
            )
        
        # DEPRECATED: HTTP/REST
        elif protocol == "http" or protocol == "rest":
            endpoint = cluster_config.gadget_endpoint or f"http://inspektor-gadget.{cluster_config.gadget_namespace}:16060"
            return HTTPGadgetClient(
                endpoint=endpoint,
                api_key=cluster_config.api_key,
                use_tls=cluster_config.use_tls,
                verify_tls=cluster_config.verify_tls
            )
        
        # FUTURE: Agent-based connections
        elif protocol == "agent":
            return AgentGadgetClient(
                agent_endpoint=cluster_config.agent_endpoint,
                use_tls=cluster_config.use_tls,
                client_cert=cluster_config.client_cert,
                client_key=cluster_config.client_key
            )
        
        else:
            raise ValueError(f"Unsupported protocol: {protocol}")
```

---

## 🎨 Frontend UI Changes

### Cluster Add/Edit Form

```typescript
interface ClusterFormData {
  // Basic
  name: string;
  description: string;
  environment: 'dev' | 'staging' | 'prod';
  
  // Connection Type (determines available protocols)
  connection_type: 'in-cluster' | 'token' | 'kubeconfig';
  
  // Protocol Selection (kubectl is recommended for all connection types)
  protocol: 'kubectl' | 'grpc' | 'http';  // kubectl recommended
  
  // Endpoints
  api_server_url?: string;  // Required for token/kubeconfig
  gadget_namespace: string;  // REQUIRED from UI
  gadget_endpoint?: string;  // Deprecated - auto-constructed
  
  // Authentication (conditional based on auth_method)
  auth_method: 'token' | 'api_key' | 'mtls' | 'kubeconfig';
  kubeconfig?: File;
  token?: string;
  api_key?: string;
  certificates?: {
    client_cert: File;
    client_key: File;
    ca_cert: File;
  };
  
  // Security
  use_tls: boolean;
  verify_tls: boolean;
  
  // Network (optional)
  use_proxy?: boolean;
  proxy_url?: string;
}
```

### UI Wizard Steps

```
Step 1: Connection Type
  ○ In-Cluster (Same Kubernetes)
  ○ Remote (Different network/cloud)
  ○ Agent-Based (Secure remote with agent)

Step 2: Protocol Selection (based on connection type)
  In-Cluster:
    ● gRPC (recommended)
    ○ HTTP/REST
  
  Remote:
    ○ gRPC (if accessible)
    ● HTTP/REST (recommended)
    ○ WebSocket
  
  Agent:
    ● Agent gRPC (recommended)

Step 3: Authentication
  [Dynamic form based on protocol]
  
Step 4: Test Connection
  [Validate before saving]
```

---

## 📋 Decision Matrix

### When to Use Each Pattern?

| Scenario | Recommended Pattern | Protocol | Auth Method |
|----------|-------------------|----------|-------------|
| Same K8s cluster | Direct gRPC | gRPC | ServiceAccount |
| Remote cluster (full access) | Direct gRPC | gRPC | mTLS |
| Remote cluster (firewall) | HTTP/REST | HTTP | API Key |
| Production (strict security) | Agent-based | Agent gRPC | mTLS |
| Edge/IoT clusters | Agent-based | Agent gRPC | mTLS |
| Multi-cloud (AWS→Azure) | HTTP/REST | HTTP | API Key + TLS |
| Multi-region same cloud | Direct gRPC | gRPC | mTLS |
| Development/staging | Direct gRPC | gRPC | Token |

---

## 🚀 Migration Strategy

### Phase 1: Current State (MVP)
- ✅ Direct gRPC only
- ✅ In-cluster connection
- ✅ Single cluster

### Phase 2: Protocol Abstraction (Sprint 6)
- 🔲 Abstract base class
- 🔲 gRPC implementation (refactor existing)
- 🔲 HTTP/REST implementation
- 🔲 Protocol selection in UI

### Phase 3: Agent Implementation (Sprint 7-8)
- 🔲 Flowfish Agent service
- 🔲 Agent deployment manifests
- 🔲 Agent health monitoring
- 🔲 Push-based data collection

### Phase 4: Enterprise Features (Sprint 9+)
- 🔲 mTLS certificate management
- 🔲 OAuth2/OIDC integration
- 🔲 Multi-tenancy
- 🔲 Geo-replication
- 🔲 HA/DR setup

---

## 📦 Deliverables

### Backend Components:
1. `backend/collectors/protocols/abstract_gadget_client.py`
2. `backend/collectors/protocols/grpc_client.py` (refactor from existing)
3. `backend/collectors/protocols/http_client.py` (new)
4. `backend/collectors/protocols/websocket_client.py` (new)
5. `backend/collectors/protocols/agent_client.py` (new)
6. `backend/collectors/protocols/client_factory.py`
7. `backend/models/cluster.py` (updated with new fields)

### Frontend Components:
1. `frontend/src/pages/ClusterManagement.tsx` (protocol selection)
2. `frontend/src/components/ClusterForm.tsx` (wizard with protocol options)
3. `frontend/src/components/AuthMethodSelector.tsx` (dynamic auth form)
4. `frontend/src/components/ConnectionTest.tsx` (validate before save)

### Deployment:
1. `deployment/kubernetes-manifests/20-flowfish-agent.yaml` (new)
2. `deployment/helm/flowfish-agent/` (new chart)

### Documentation:
1. `docs/architecture/ENTERPRISE_MULTI_CLUSTER.md` (this file)
2. `docs/guides/MULTI_CLUSTER_SETUP.md` (setup guide)
3. `docs/guides/AGENT_DEPLOYMENT.md` (agent deployment)

---

## 🎯 Success Criteria

### Technical:
- ✅ Support 3+ protocols (gRPC, HTTP, Agent)
- ✅ Protocol switching without code changes
- ✅ Connection validation before cluster add
- ✅ Auto-discovery of best protocol
- ✅ Graceful fallback (gRPC → HTTP)

### User Experience:
- ✅ Simple cluster add wizard
- ✅ Clear protocol recommendations
- ✅ Visual connection status
- ✅ One-click test connection
- ✅ Error messages with solutions

### Security:
- ✅ All credentials encrypted at rest
- ✅ TLS by default
- ✅ Certificate rotation support
- ✅ Audit logging
- ✅ Rate limiting per cluster

### Performance:
- ✅ < 5s connection establishment
- ✅ < 100ms event streaming latency
- ✅ Support 100+ concurrent clusters
- ✅ Auto-reconnect on failure
- ✅ Connection pooling

---

**Version:** 1.0.0  
**Status:** 🎯 Design Complete - Ready for Implementation  
**Target Sprint:** Sprint 6-7  
**Owner:** Flowfish Core Team

