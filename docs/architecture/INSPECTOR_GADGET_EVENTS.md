# Inspector Gadget Event Types - Comprehensive Reference

## 🎯 Overview

Inspector Gadget can collect various eBPF-based events from Kubernetes clusters. This document defines **all supported event types** and their schemas across the entire Flowfish platform.

---

## 📊 Event Type Categories

### 1. Network Events
- **network_flow**: TCP/UDP connection tracking
- **tcp_lifecycle**: TCP state transitions (SYN, ACK, FIN)
- **dns_query**: DNS resolution events
- **http_request**: HTTP/HTTPS requests (parsed)
- **sni**: TLS SNI (Server Name Indication)

### 2. Process Events
- **process_exec**: Process creation (execve)
- **process_exit**: Process termination
- **process_signal**: Process signals (SIGTERM, SIGKILL, etc.)

### 3. File Events
- **file_open**: File open operations
- **file_read**: File read operations
- **file_write**: File write operations

### 4. Security Events
- **capability_check**: Linux capability checks
- **seccomp**: Seccomp violations
- **oom_kill**: Out of memory kills

### 5. Socket Events
- **socket_connect**: Socket connection events
- **socket_accept**: Socket accept events
- **socket_send**: Data send events
- **socket_recv**: Data receive events

---

## 🗂️ Event Schema Definitions

### 1. network_flow

**Description**: TCP/UDP network connection tracking

**ClickHouse Schema**:
```sql
CREATE TABLE network_flows (
    -- Timestamp
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Cluster & Analysis Context
    cluster_id String,
    cluster_name String,
    analysis_id String,
    
    -- Source
    source_namespace String,
    source_pod String,
    source_container String,
    source_node String,
    source_ip String,
    source_port UInt16,
    
    -- Destination
    dest_namespace String,
    dest_pod String,
    dest_container String,
    dest_ip String,
    dest_port UInt16,
    dest_hostname String, -- If resolved
    
    -- Connection Details
    protocol Enum8('TCP' = 1, 'UDP' = 2, 'ICMP' = 3),
    direction Enum8('inbound' = 1, 'outbound' = 2, 'internal' = 3),
    connection_state String, -- ESTABLISHED, SYN_SENT, CLOSE_WAIT, etc.
    
    -- Metrics
    bytes_sent UInt64,
    bytes_received UInt64,
    packets_sent UInt32,
    packets_received UInt32,
    duration_ms UInt32,
    latency_ms Float32,
    
    -- Errors
    error_count UInt16,
    retransmit_count UInt16,
    
    -- Labels & Metadata
    source_labels Map(String, String),
    dest_labels Map(String, String),
    
    -- Raw Event Data
    event_data_json String -- Full event JSON for debugging
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_pod, dest_pod, dest_port)
TTL timestamp + INTERVAL 90 DAY;
```

**Proto Message**:
```protobuf
message NetworkFlowEvent {
    google.protobuf.Timestamp timestamp = 1;
    string event_id = 2;
    
    // Context
    string cluster_id = 3;
    string analysis_id = 4;
    
    // Source
    string source_namespace = 5;
    string source_pod = 6;
    string source_container = 7;
    string source_ip = 8;
    uint32 source_port = 9;
    
    // Destination
    string dest_namespace = 10;
    string dest_pod = 11;
    string dest_ip = 12;
    uint32 dest_port = 13;
    
    // Connection
    string protocol = 14; // TCP, UDP, ICMP
    string direction = 15; // inbound, outbound, internal
    
    // Metrics
    uint64 bytes_sent = 16;
    uint64 bytes_received = 17;
    uint32 duration_ms = 18;
    float latency_ms = 19;
    
    // Metadata
    map<string, string> labels = 20;
}
```

---

### 2. dns_query

**Description**: DNS query and response tracking

**ClickHouse Schema**:
```sql
CREATE TABLE dns_queries (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Source
    source_namespace String,
    source_pod String,
    source_container String,
    source_ip String,
    
    -- DNS Query
    query_name String, -- domain name
    query_type Enum8('A' = 1, 'AAAA' = 2, 'CNAME' = 3, 'MX' = 4, 'TXT' = 5, 'PTR' = 6, 'NS' = 7, 'SOA' = 8),
    query_class String DEFAULT 'IN',
    
    -- DNS Response
    response_code Enum8('NOERROR' = 0, 'FORMERR' = 1, 'SERVFAIL' = 2, 'NXDOMAIN' = 3, 'NOTIMP' = 4, 'REFUSED' = 5),
    response_ips Array(String), -- Resolved IPs
    response_ttl UInt32,
    
    -- Performance
    latency_ms Float32,
    
    -- DNS Server
    dns_server_ip String,
    
    -- Metadata
    labels Map(String, String),
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_pod, query_name)
TTL timestamp + INTERVAL 90 DAY;
```

---

### 3. tcp_lifecycle

**Description**: TCP connection state transitions

**ClickHouse Schema**:
```sql
CREATE TABLE tcp_lifecycle (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Connection
    source_ip String,
    source_port UInt16,
    dest_ip String,
    dest_port UInt16,
    
    -- TCP State
    old_state Enum8('CLOSED' = 0, 'LISTEN' = 1, 'SYN_SENT' = 2, 'SYN_RECV' = 3, 'ESTABLISHED' = 4, 'FIN_WAIT1' = 5, 'FIN_WAIT2' = 6, 'CLOSE_WAIT' = 7, 'CLOSING' = 8, 'LAST_ACK' = 9, 'TIME_WAIT' = 10),
    new_state Enum8('CLOSED' = 0, 'LISTEN' = 1, 'SYN_SENT' = 2, 'SYN_RECV' = 3, 'ESTABLISHED' = 4, 'FIN_WAIT1' = 5, 'FIN_WAIT2' = 6, 'CLOSE_WAIT' = 7, 'CLOSING' = 8, 'LAST_ACK' = 9, 'TIME_WAIT' = 10),
    
    -- Pod Context
    source_namespace String,
    source_pod String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, source_ip, dest_ip, dest_port)
TTL timestamp + INTERVAL 30 DAY;
```

---

### 4. process_exec

**Description**: Process creation events

**ClickHouse Schema**:
```sql
CREATE TABLE process_events (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Process
    pid UInt32,
    ppid UInt32, -- Parent PID
    uid UInt32,
    gid UInt32,
    comm String, -- Command name
    exe String, -- Executable path
    args Array(String), -- Command arguments
    
    -- Event Type
    event_type Enum8('exec' = 1, 'exit' = 2, 'signal' = 3),
    exit_code Int32, -- For exit events
    signal Int32, -- For signal events (SIGTERM=15, SIGKILL=9)
    
    -- Metadata
    labels Map(String, String),
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, pid)
TTL timestamp + INTERVAL 90 DAY;
```

---

### 5. file_operations

**Description**: File system operations

**ClickHouse Schema**:
```sql
CREATE TABLE file_operations (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    
    -- File Operation
    operation Enum8('open' = 1, 'read' = 2, 'write' = 3, 'close' = 4, 'unlink' = 5),
    file_path String,
    file_flags String, -- O_RDONLY, O_WRONLY, O_RDWR, O_CREAT, etc.
    file_mode UInt32,
    
    -- Process
    pid UInt32,
    comm String,
    uid UInt32,
    
    -- Metrics
    bytes UInt64, -- Bytes read/written
    duration_us UInt32, -- Operation duration in microseconds
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, file_path)
TTL timestamp + INTERVAL 30 DAY;
```

---

### 6. capability_checks

**Description**: Linux capability checks

**ClickHouse Schema**:
```sql
CREATE TABLE capability_checks (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    
    -- Capability
    capability String, -- CAP_NET_ADMIN, CAP_SYS_ADMIN, etc.
    syscall String, -- Syscall that triggered check
    
    -- Process
    pid UInt32,
    comm String,
    uid UInt32,
    
    -- Result
    verdict Enum8('allowed' = 1, 'denied' = 2),
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod, capability)
TTL timestamp + INTERVAL 30 DAY;
```

---

### 7. oom_kills

**Description**: Out of memory kill events

**ClickHouse Schema**:
```sql
CREATE TABLE oom_kills (
    timestamp DateTime64(3) DEFAULT now64(3),
    event_id String DEFAULT generateUUIDv4(),
    
    -- Context
    cluster_id String,
    analysis_id String,
    
    -- Pod Context
    namespace String,
    pod String,
    container String,
    node String,
    
    -- Killed Process
    pid UInt32,
    comm String,
    
    -- Memory
    memory_limit UInt64, -- Container memory limit (bytes)
    memory_usage UInt64, -- Memory usage at time of kill
    
    -- Cgroup
    cgroup_path String,
    
    -- Metadata
    event_data_json String
    
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, cluster_id, namespace, pod)
TTL timestamp + INTERVAL 90 DAY;
```

---

## 🎯 Event Type Configuration

### Gadget to Event Type Mapping

```json
{
  "network": ["network_flow", "tcp_lifecycle"],
  "dns": ["dns_query"],
  "process": ["process_exec"],
  "exec": ["process_exec"],
  "open": ["file_operations"],
  "capabilities": ["capability_checks"],
  "oomkill": ["oom_kills"],
  "tcp": ["tcp_lifecycle"],
  "socket": ["network_flow"]
}
```

### Event Type Categories for UI

```typescript
export enum EventCategory {
  NETWORK = "network",
  DNS = "dns",
  PROCESS = "process",
  FILE = "file",
  SECURITY = "security",
  RESOURCE = "resource"
}

export interface EventTypeDefinition {
  id: string;
  name: string;
  description: string;
  category: EventCategory;
  gadgetName: string; // Inspector Gadget gadget name
  tableName: string; // ClickHouse table name
  defaultEnabled: boolean;
  icon: string;
  color: string;
  fields: EventField[];
}

export const EVENT_TYPES: EventTypeDefinition[] = [
  {
    id: "network_flow",
    name: "Network Flows",
    description: "TCP/UDP connection tracking with metrics",
    category: EventCategory.NETWORK,
    gadgetName: "network",
    tableName: "network_flows",
    defaultEnabled: true,
    icon: "network",
    color: "#1890ff",
    fields: [
      { name: "source_pod", label: "Source Pod", type: "string", filterable: true },
      { name: "dest_pod", label: "Destination Pod", type: "string", filterable: true },
      { name: "dest_port", label: "Port", type: "number", filterable: true },
      { name: "protocol", label: "Protocol", type: "enum", values: ["TCP", "UDP", "ICMP"] },
      { name: "bytes_sent", label: "Bytes Sent", type: "number", aggregatable: true },
      { name: "latency_ms", label: "Latency (ms)", type: "float", aggregatable: true }
    ]
  },
  {
    id: "dns_query",
    name: "DNS Queries",
    description: "DNS resolution tracking with latency",
    category: EventCategory.DNS,
    gadgetName: "dns",
    tableName: "dns_queries",
    defaultEnabled: true,
    icon: "dns",
    color: "#52c41a",
    fields: [
      { name: "query_name", label: "Domain", type: "string", filterable: true },
      { name: "query_type", label: "Query Type", type: "enum", values: ["A", "AAAA", "CNAME"] },
      { name: "response_code", label: "Response", type: "enum", values: ["NOERROR", "NXDOMAIN"] },
      { name: "latency_ms", label: "Latency (ms)", type: "float", aggregatable: true }
    ]
  },
  {
    id: "tcp_lifecycle",
    name: "TCP Lifecycle",
    description: "TCP state transitions (SYN, ACK, FIN)",
    category: EventCategory.NETWORK,
    gadgetName: "tcp",
    tableName: "tcp_lifecycle",
    defaultEnabled: false,
    icon: "connection",
    color: "#faad14",
    fields: [
      { name: "old_state", label: "Old State", type: "enum", values: ["CLOSED", "LISTEN", "SYN_SENT", "ESTABLISHED"] },
      { name: "new_state", label: "New State", type: "enum", values: ["CLOSED", "LISTEN", "SYN_SENT", "ESTABLISHED"] }
    ]
  },
  {
    id: "process_exec",
    name: "Process Execution",
    description: "Process creation and termination",
    category: EventCategory.PROCESS,
    gadgetName: "exec",
    tableName: "process_events",
    defaultEnabled: false,
    icon: "code",
    color: "#722ed1",
    fields: [
      { name: "comm", label: "Command", type: "string", filterable: true },
      { name: "exe", label: "Executable", type: "string", filterable: true },
      { name: "args", label: "Arguments", type: "array" },
      { name: "uid", label: "User ID", type: "number" }
    ]
  },
  {
    id: "file_operations",
    name: "File Operations",
    description: "File system read/write tracking",
    category: EventCategory.FILE,
    gadgetName: "open",
    tableName: "file_operations",
    defaultEnabled: false,
    icon: "file",
    color: "#eb2f96",
    fields: [
      { name: "operation", label: "Operation", type: "enum", values: ["open", "read", "write", "close"] },
      { name: "file_path", label: "File Path", type: "string", filterable: true },
      { name: "bytes", label: "Bytes", type: "number", aggregatable: true }
    ]
  },
  {
    id: "capability_checks",
    name: "Capability Checks",
    description: "Linux capability permission checks",
    category: EventCategory.SECURITY,
    gadgetName: "capabilities",
    tableName: "capability_checks",
    defaultEnabled: false,
    icon: "shield",
    color: "#fa541c",
    fields: [
      { name: "capability", label: "Capability", type: "string", filterable: true },
      { name: "verdict", label: "Verdict", type: "enum", values: ["allowed", "denied"] },
      { name: "syscall", label: "Syscall", type: "string" }
    ]
  },
  {
    id: "oom_kills",
    name: "OOM Kills",
    description: "Out of memory kill events",
    category: EventCategory.RESOURCE,
    gadgetName: "oomkill",
    tableName: "oom_kills",
    defaultEnabled: true,
    icon: "warning",
    color: "#f5222d",
    fields: [
      { name: "comm", label: "Process", type: "string" },
      { name: "memory_limit", label: "Memory Limit", type: "number" },
      { name: "memory_usage", label: "Memory Usage", type: "number" }
    ]
  }
];
```

---

## 📡 RabbitMQ Routing

### Queue Naming Convention

```
flowfish.events.{event_type}.{cluster_id}

Examples:
- flowfish.events.network_flow.prod-cluster-1
- flowfish.events.dns_query.prod-cluster-1
- flowfish.events.process_exec.staging-cluster
```

### Exchange Configuration

```yaml
exchange:
  name: flowfish.events
  type: topic
  durable: true

routing_keys:
  - flowfish.events.network_flow.*
  - flowfish.events.dns_query.*
  - flowfish.events.tcp_lifecycle.*
  - flowfish.events.process_exec.*
  - flowfish.events.file_operations.*
  - flowfish.events.capability_checks.*
  - flowfish.events.oom_kills.*
```

---

## 🎨 Frontend Event Selector Component

```typescript
// Analysis Wizard - Step 3: Event Types Selection

interface EventTypeSelection {
  eventTypeId: string;
  enabled: boolean;
  filters?: Record<string, any>; // Optional filters per event type
}

const EventTypeSelector: React.FC = () => {
  const [selectedEvents, setSelectedEvents] = useState<EventTypeSelection[]>([
    { eventTypeId: "network_flow", enabled: true },
    { eventTypeId: "dns_query", enabled: true }
  ]);

  return (
    <div className="event-type-selector">
      <h3>Select Event Types to Collect</h3>
      
      {Object.values(EventCategory).map(category => (
        <div key={category} className="event-category">
          <h4>{category.toUpperCase()}</h4>
          
          {EVENT_TYPES.filter(et => et.category === category).map(eventType => (
            <Card key={eventType.id}>
              <Checkbox
                checked={selectedEvents.find(e => e.eventTypeId === eventType.id)?.enabled}
                onChange={(e) => handleToggle(eventType.id, e.target.checked)}
              >
                <Space>
                  <Badge color={eventType.color} />
                  <strong>{eventType.name}</strong>
                </Space>
              </Checkbox>
              
              <p>{eventType.description}</p>
              
              {/* Advanced filters (collapsible) */}
              <Collapse>
                <Panel header="Advanced Filters">
                  {eventType.fields.filter(f => f.filterable).map(field => (
                    <Form.Item key={field.name} label={field.label}>
                      <Input placeholder={`Filter by ${field.label}`} />
                    </Form.Item>
                  ))}
                </Panel>
              </Collapse>
            </Card>
          ))}
        </div>
      ))}
    </div>
  );
};
```

---

## 🔄 Data Flow

```
1. User creates Analysis with selected event types

2. Analysis Orchestrator → Gadget.StartTrace(gadgets=["network", "dns"])

3. Inspector Gadget → eBPF programs active

4. Events → Ingestion Service (gRPC stream)

5. Ingestion Service → Transform → RabbitMQ
   - flowfish.events.network_flow.cluster-1
   - flowfish.events.dns_query.cluster-1

6. Consumers:
   - Timeseries Writer → ClickHouse (network_flows, dns_queries tables)
   - Graph Writer → Neo4j (aggregated connections)

7. Frontend queries:
   - ClickHouse: SELECT * FROM network_flows WHERE analysis_id = ?
   - Neo4j: MATCH (src)-[e:COMMUNICATES_WITH]->(dst) WHERE e.analysis_id = ?
```

---

## ✅ Implementation Checklist

- [x] Event type definitions documented
- [ ] ClickHouse schemas created (7 tables)
- [ ] Proto event messages defined
- [ ] RabbitMQ routing configured
- [ ] Ingestion Service event parsing
- [ ] Timeseries Writer multi-table support
- [ ] Analysis configuration event selection
- [ ] Frontend EventTypeSelector component
- [ ] API endpoints for event type metadata
- [ ] Documentation for each event type

---

**🎯 Result: Complete event collection and visualization pipeline for all Inspector Gadget capabilities!**

