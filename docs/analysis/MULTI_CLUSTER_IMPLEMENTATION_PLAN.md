# 🐟 Flowfish - Multi-Cluster Implementation Plan

## ✅ TAMAMLANDI - Aralık 2025

Bu implementasyon planı başarıyla tamamlandı.

## Kullanıcı Gereksinimleri

1. ✅ Header'daki cluster selector kaldırıldı (gereksiz)
2. ✅ New Analysis → Target Cluster çoklu seçim (multiple select)
3. ✅ Cluster Management formu genişletildi (token, gadget endpoint, grpc)
4. ✅ Cluster kaydetme sırasında Inspektor Gadget health check
5. ✅ Cluster seçildiğinde live Kubernetes obje listesi (namespace, deployment, vb.)
6. ✅ Analiz başlatma → Inspektor Gadget veri toplama → ClickHouse'a yazma
7. ✅ ClusterConnectionManager ile merkezi cluster erişimi
8. ✅ Per-cluster ve unified scope mode destekli analiz wizard
9. ✅ Multi-cluster analysis ID formatı ({analysis_id}-{cluster_id})
10. ✅ Remote cluster için Inspector Gadget kurulum scripti

## Mimari Değişiklikler

### Frontend (✅ Tamamlandı)
1. **Header.tsx** - Cluster selector kaldırıldı
2. **AnalysisWizard.tsx** - `cluster_id` → `cluster_ids` (multiple select)
3. **ClusterManagement.tsx** - Form alanları eklendi:
   - `token` - ServiceAccount token
   - `gadget_grpc_endpoint` - Inspektor Gadget gRPC endpoint
   - `gadget_token` - Inspektor Gadget auth token (optional)
   - `verify_ssl` - SSL doğrulama checkbox

### Backend (🔄 Devam Ediyor)

#### 1. Cluster Model Güncellemesi
```python
# backend/models/cluster.py
class Cluster(Base):
    __tablename__ = "clusters"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    cluster_type = Column(String(50))  # kubernetes, openshift
    api_url = Column(String(500), nullable=False)
    token = Column(Text, nullable=False)  # ServiceAccount token
    gadget_grpc_endpoint = Column(String(500))  # e.g., gadget.gadget.svc.cluster.local:1234
    gadget_token = Column(Text)  # Optional Inspektor Gadget token
    verify_ssl = Column(Boolean, default=True)
    
    # Health & Status
    health_status = Column(String(50), default='unknown')  # healthy, degraded, unhealthy
    last_health_check = Column(DateTime)
    node_count = Column(Integer, default=0)
    pod_count = Column(Integer, default=0)
    namespace_count = Column(Integer, default=0)
    
    # Metadata
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### 2. Cluster CRUD API Endpoints

**POST /api/v1/clusters**
- Create cluster
- Validate Kubernetes API connection
- Validate Inspektor Gadget gRPC connection
- Return health status

**GET /api/v1/clusters**
- List all clusters with health status

**GET /api/v1/clusters/{id}/health**
- Check cluster health (K8s API + Inspektor Gadget)
- Update health_status in database

**GET /api/v1/clusters/{id}/namespaces**
- Live namespace list from Kubernetes API

**GET /api/v1/clusters/{id}/deployments**
- Live deployment list from Kubernetes API (optional namespace filter)

**GET /api/v1/clusters/{id}/statefulsets**
- Live statefulset list

**GET /api/v1/clusters/{id}/services**
- Live service list

#### 3. Inspektor Gadget Health Check Service

```python
# backend/services/inspektor_gadget_service.py

import grpc
from typing import Dict, Optional

class InspektorGadgetService:
    """Service to interact with Inspektor Gadget gRPC API"""
    
    async def check_health(
        self, 
        grpc_endpoint: str, 
        token: Optional[str] = None,
        verify_ssl: bool = True
    ) -> Dict[str, any]:
        """
        Check if Inspektor Gadget is reachable and healthy
        
        Args:
            grpc_endpoint: gRPC server address (e.g., gadget.gadget.svc.cluster.local:1234)
            token: Optional authentication token
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            {
                "healthy": bool,
                "version": str,
                "gadgets_available": List[str],
                "error": Optional[str]
            }
        """
        try:
            # Create gRPC channel
            if verify_ssl:
                credentials = grpc.ssl_channel_credentials()
                channel = grpc.secure_channel(grpc_endpoint, credentials)
            else:
                channel = grpc.insecure_channel(grpc_endpoint)
            
            # Call health check or list gadgets
            # (Depends on Inspektor Gadget API spec)
            
            return {
                "healthy": True,
                "version": "v0.x.x",
                "gadgets_available": ["trace_network", "trace_tcp", "trace_dns"],
                "error": None
            }
        except Exception as e:
            return {
                "healthy": False,
                "version": None,
                "gadgets_available": [],
                "error": str(e)
            }
    
    async def start_trace(
        self,
        cluster_id: int,
        analysis_id: int,
        gadget_modules: List[str],
        scope_config: Dict,
        duration_seconds: Optional[int] = None
    ) -> str:
        """
        Start eBPF tracing on specified scope
        
        Args:
            cluster_id: Target cluster ID
            analysis_id: Analysis ID for data tagging
            gadget_modules: List of gadget modules to enable (e.g., ["network_traffic", "dns_queries"])
            scope_config: Scope configuration (namespace, pod selector, etc.)
            duration_seconds: Optional duration limit
            
        Returns:
            trace_id: Unique identifier for this tracing session
        """
        # Start Inspektor Gadget trace
        # Data will be streamed to ClickHouse
        pass
    
    async def stop_trace(self, trace_id: str):
        """Stop active trace session"""
        pass
    
    async def get_trace_status(self, trace_id: str) -> Dict:
        """Get current status of trace session"""
        pass
```

#### 4. Kubernetes Service Integration

```python
# backend/services/kubernetes_service.py

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import List, Dict, Optional

class KubernetesService:
    """Service to interact with Kubernetes API"""
    
    def __init__(self, api_url: str, token: str, verify_ssl: bool = True):
        configuration = client.Configuration()
        configuration.host = api_url
        configuration.api_key = {"authorization": f"Bearer {token}"}
        configuration.verify_ssl = verify_ssl
        
        self.api_client = client.ApiClient(configuration)
        self.core_v1 = client.CoreV1Api(self.api_client)
        self.apps_v1 = client.AppsV1Api(self.api_client)
    
    async def check_health(self) -> Dict:
        """Check Kubernetes API health"""
        try:
            # Try to get API version
            version = await self.core_v1.get_api_resources()
            return {"healthy": True, "version": version}
        except ApiException as e:
            return {"healthy": False, "error": str(e)}
    
    async def list_namespaces(self) -> List[Dict]:
        """Get list of namespaces"""
        try:
            ns_list = await self.core_v1.list_namespace()
            return [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                    "created_at": ns.metadata.creation_timestamp
                }
                for ns in ns_list.items
            ]
        except ApiException as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    async def list_deployments(self, namespace: Optional[str] = None) -> List[Dict]:
        """Get list of deployments"""
        try:
            if namespace:
                deploy_list = await self.apps_v1.list_namespaced_deployment(namespace)
            else:
                deploy_list = await self.apps_v1.list_deployment_for_all_namespaces()
            
            return [
                {
                    "name": d.metadata.name,
                    "namespace": d.metadata.namespace,
                    "replicas": d.spec.replicas,
                    "available": d.status.available_replicas,
                    "labels": d.metadata.labels
                }
                for d in deploy_list.items
            ]
        except ApiException as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    async def list_statefulsets(self, namespace: Optional[str] = None) -> List[Dict]:
        """Get list of statefulsets"""
        pass
    
    async def list_services(self, namespace: Optional[str] = None) -> List[Dict]:
        """Get list of services"""
        pass
    
    async def list_pods(self, namespace: Optional[str] = None, label_selector: Optional[str] = None) -> List[Dict]:
        """Get list of pods"""
        pass
```

#### 5. Analysis Start Logic

```python
# backend/routers/analyses.py

@router.post("/{analysis_id}/start", response_model=AnalysisResponse)
async def start_analysis(
    analysis_id: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Start analysis - Begin Inspektor Gadget data collection
    
    Steps:
    1. Get analysis configuration from database
    2. Validate target clusters are healthy
    3. For each cluster:
        a. Get cluster credentials
        b. Start Inspektor Gadget trace with scope config
        c. Configure ClickHouse as data sink
    4. Update analysis status to "running"
    5. Return trace IDs
    """
    try:
        # Get analysis config
        analysis = await database.fetch_one(
            "SELECT * FROM analyses WHERE id = :id",
            {"id": analysis_id}
        )
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        # Get cluster IDs
        cluster_ids = analysis["scope_config"]["cluster_ids"]
        
        # Start trace on each cluster
        trace_ids = []
        for cluster_id in cluster_ids:
            # Get cluster info
            cluster = await database.fetch_one(
                "SELECT * FROM clusters WHERE id = :id",
                {"id": cluster_id}
            )
            
            # Initialize Inspektor Gadget service
            gadget_service = InspektorGadgetService()
            
            # Start trace
            trace_id = await gadget_service.start_trace(
                cluster_id=cluster_id,
                analysis_id=analysis_id,
                gadget_modules=analysis["gadget_modules"],
                scope_config=analysis["scope_config"],
                duration_seconds=analysis["time_config"].get("duration")
            )
            
            trace_ids.append({
                "cluster_id": cluster_id,
                "cluster_name": cluster["name"],
                "trace_id": trace_id
            })
        
        # Update analysis status
        await database.execute(
            """
            UPDATE analyses 
            SET status = 'running', 
                started_at = NOW(),
                trace_ids = :trace_ids
            WHERE id = :id
            """,
            {"id": analysis_id, "trace_ids": json.dumps(trace_ids)}
        )
        
        return {"message": "Analysis started", "trace_ids": trace_ids}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### 6. ClickHouse Data Collection

```python
# backend/services/clickhouse_service.py

class ClickHouseService:
    """Service to write Inspektor Gadget data to ClickHouse"""
    
    async def create_analysis_table(self, analysis_id: int, cluster_id: int):
        """
        Create ClickHouse tables for analysis data
        
        Tables:
        - network_flows_{analysis_id}_{cluster_id}
        - dns_queries_{analysis_id}_{cluster_id}
        - tcp_connections_{analysis_id}_{cluster_id}
        """
        table_name = f"network_flows_{analysis_id}_{cluster_id}"
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            timestamp DateTime64(3),
            cluster_id UInt32,
            analysis_id UInt32,
            namespace String,
            pod_name String,
            container_name String,
            src_ip String,
            src_port UInt16,
            dst_ip String,
            dst_port UInt16,
            protocol String,
            bytes_sent UInt64,
            bytes_received UInt64,
            packets_sent UInt32,
            packets_received UInt32,
            duration_ms UInt32,
            INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 3,
            INDEX idx_pod pod_name TYPE bloom_filter(0.01) GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (timestamp, cluster_id, pod_name)
        """
        
        await self.execute(create_table_sql)
    
    async def insert_network_flow(self, analysis_id: int, cluster_id: int, data: Dict):
        """Insert network flow data"""
        pass
    
    async def query_flows(self, analysis_id: int, cluster_id: int, filters: Dict) -> List[Dict]:
        """Query collected network flows"""
        pass
```

## Database Schema Updates

### PostgreSQL

```sql
-- Update clusters table
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS token TEXT;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS gadget_grpc_endpoint VARCHAR(500);
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS gadget_token TEXT;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS verify_ssl BOOLEAN DEFAULT TRUE;
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS last_health_check TIMESTAMP;

-- Update analyses table
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS trace_ids JSONB;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS error_message TEXT;
```

### ClickHouse

```sql
-- Network flows table (per analysis)
CREATE TABLE IF NOT EXISTS network_flows (
    timestamp DateTime64(3),
    cluster_id UInt32,
    analysis_id UInt32,
    analysis_name String,
    namespace String,
    pod_name String,
    container_name String,
    src_ip String,
    src_port UInt16,
    dst_ip String,
    dst_port UInt16,
    protocol String,
    bytes_sent UInt64,
    bytes_received UInt64,
    packets_sent UInt32,
    packets_received UInt32,
    duration_ms UInt32,
    INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 3,
    INDEX idx_pod pod_name TYPE bloom_filter(0.01) GRANULARITY 1,
    INDEX idx_analysis analysis_id TYPE minmax GRANULARITY 1
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), cluster_id)
ORDER BY (timestamp, cluster_id, analysis_id, pod_name);

-- DNS queries table
CREATE TABLE IF NOT EXISTS dns_queries (
    timestamp DateTime64(3),
    cluster_id UInt32,
    analysis_id UInt32,
    namespace String,
    pod_name String,
    query_name String,
    query_type String,
    response_ip String,
    response_code UInt16,
    latency_ms Float32
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), cluster_id)
ORDER BY (timestamp, cluster_id, analysis_id, pod_name);

-- TCP connections table
CREATE TABLE IF NOT EXISTS tcp_connections (
    timestamp DateTime64(3),
    cluster_id UInt32,
    analysis_id UInt32,
    namespace String,
    pod_name String,
    src_ip String,
    src_port UInt16,
    dst_ip String,
    dst_port UInt16,
    state String,
    rtt_ms Float32
) ENGINE = MergeTree()
PARTITION BY (toYYYYMM(timestamp), cluster_id)
ORDER BY (timestamp, cluster_id, analysis_id, pod_name);
```

## API Endpoints Summary

### Cluster Management
- `POST /api/v1/clusters` - Create cluster + validate
- `GET /api/v1/clusters` - List all clusters
- `GET /api/v1/clusters/{id}` - Get cluster details
- `PUT /api/v1/clusters/{id}` - Update cluster
- `DELETE /api/v1/clusters/{id}` - Delete cluster
- `POST /api/v1/clusters/{id}/health-check` - Manual health check
- `GET /api/v1/clusters/{id}/namespaces` - Live namespace list
- `GET /api/v1/clusters/{id}/deployments` - Live deployment list
- `GET /api/v1/clusters/{id}/statefulsets` - Live statefulset list
- `GET /api/v1/clusters/{id}/services` - Live service list
- `GET /api/v1/clusters/{id}/pods` - Live pod list

### Analysis Management
- `POST /api/v1/analyses` - Create analysis definition
- `GET /api/v1/analyses` - List analyses
- `GET /api/v1/analyses/{id}` - Get analysis details
- `POST /api/v1/analyses/{id}/start` - Start analysis (begin tracing)
- `POST /api/v1/analyses/{id}/stop` - Stop analysis
- `GET /api/v1/analyses/{id}/status` - Get current status
- `GET /api/v1/analyses/{id}/results` - Get collected data

## Implementation Steps

### Sprint 7 (Current)
1. ✅ Frontend: Header cluster selector kaldırma
2. ✅ Frontend: Multi-cluster selection in AnalysisWizard
3. ✅ Frontend: Cluster form fields (token, gadget endpoint)
4. 🔄 Backend: Update cluster model (add new fields)
5. 🔄 Backend: Implement cluster health check
6. 🔄 Backend: Kubernetes service integration
7. 🔄 Backend: Live object listing endpoints

### Sprint 8
1. Backend: Inspektor Gadget gRPC client
2. Backend: Analysis start/stop logic
3. Backend: ClickHouse schema creation
4. Backend: Data collection pipeline
5. Frontend: Analysis status monitoring
6. Frontend: Live data visualization

### Sprint 9
1. Multi-cluster orchestration
2. Data aggregation across clusters
3. Dependency graph generation
4. Change detection logic
5. Performance optimization

---

**Status:** Sprint 7 in progress  
**Last Updated:** 21 Kasım 2025

