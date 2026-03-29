import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// Event Types
// NOTE: tcp_lifecycle/tcp_connection removed - Inspektor Gadget trace_tcp doesn't
// produce TCP state transition events. TCP info is captured in network_flow.
// tcp_throughput and tcp_retransmit are now separate gadgets for bytes/errors.
export type EventType = 
  | 'network_flow' 
  | 'dns_query' 
  | 'tcp_throughput'   // TCP throughput with bytes sent/received (top_tcp gadget)
  | 'tcp_retransmit'   // TCP retransmit/errors for network error detection
  | 'process_event' 
  | 'file_event' 
  | 'security_event' 
  | 'oom_event'
  | 'bind_event'
  | 'sni_event'
  | 'mount_event';

// Base event interface
export interface BaseEvent {
  timestamp: string;
  event_id: string;
  cluster_id: string;
  cluster_name?: string;  // Cluster display name for multi-cluster visibility
  analysis_id: string;
  namespace: string;
  pod: string;
  container?: string;
}

// Network Flow Event
export interface NetworkFlowEvent extends BaseEvent {
  event_type: 'network_flow';
  source_ip: string;
  source_port: number;
  source_pod?: string;        // Source pod name (from top_tcp)
  source_namespace?: string;  // Source namespace (from top_tcp)
  dest_ip: string;
  dest_port: number;
  dest_pod?: string;          // Destination pod name
  dest_namespace?: string;    // Destination namespace
  protocol: string;           // TCP, UDP, ICMP, etc.
  direction: string;          // inbound, outbound
  bytes_sent: number;
  bytes_received: number;
  latency_ms: number;
  connection_state?: string;  // TCP connection state
  comm?: string;              // Process name (from top_tcp)
  // Error fields from ClickHouse
  error_count?: number;       // Number of errors (retransmits, resets, etc.)
  retransmit_count?: number;  // Number of TCP retransmissions
  error_type?: string;        // Error type: RETRANSMIT_RETRANS, CONNECTION_RESET, etc.
}

// DNS Query Event
export interface DnsQueryEvent extends BaseEvent {
  event_type: 'dns_query';
  query_name: string;
  query_type: string;
  response_code: string;
  response_ips: string[];
  latency_ms: number;
  dns_server_ip: string;
}

// Process Event
export interface ProcessEvent extends BaseEvent {
  event_type: 'process_event';
  pid: number;              // Process ID
  ppid: number;             // Parent Process ID
  comm: string;             // Command name
  exe: string;              // Executable path
  args: string[];           // Command line arguments
  event_subtype: 'exec' | 'exit' | 'signal';
  exit_code?: number;       // Exit code (for exit events)
  signal?: number;          // Signal number (for signal events)
  uid?: number;             // User ID
  gid?: number;             // Group ID
}

// File Event
export interface FileEvent extends BaseEvent {
  event_type: 'file_event';
  operation: string;        // open, read, write, close, unlink, rename
  file_path: string;
  file_flags: string;
  file_mode?: number;       // File permissions mode
  bytes: number;            // Bytes read/written
  duration_us: number;      // Operation duration in microseconds
  error_code: number;       // Error code (0 = success)
  pid: number;
  comm: string;
  uid?: number;             // User ID
  gid?: number;             // Group ID
}

// Security Event
export interface SecurityEvent extends BaseEvent {
  event_type: 'security_event';
  security_type: 'capability' | 'seccomp' | 'selinux';
  capability?: string;      // Linux capability name (e.g., CAP_NET_ADMIN)
  syscall?: string;         // System call name
  verdict: 'allowed' | 'denied';
  pid: number;
  comm: string;
  uid?: number;             // User ID
  gid?: number;             // Group ID
}

// OOM Event
export interface OomEvent extends BaseEvent {
  event_type: 'oom_event';
  node?: string;              // Node where OOM occurred
  pid: number;
  comm: string;
  memory_limit: number;       // Memory limit in bytes
  memory_usage: number;       // Memory usage at OOM time in bytes
  memory_pages_total?: number; // Total memory pages
  memory_pages_free?: number;  // Free memory pages  
  cgroup_path: string;
}

// Bind Event (Socket Bind)
export interface BindEvent extends BaseEvent {
  event_type: 'bind_event';
  node?: string;            // Node name
  bind_addr: string;        // Bind address (IP)
  bind_port: number;        // Bind port
  protocol: string;         // TCP, UDP, etc.
  interface: string;        // Network interface
  error_code: number;       // Error code (0 = success)
  pid: number;
  comm: string;
  uid?: number;             // User ID
}

// SNI Event (TLS/SSL)
export interface SniEvent extends BaseEvent {
  event_type: 'sni_event';
  server_name: string;      // TLS SNI hostname (backend uses server_name)
  sni_name?: string;        // Alias for backwards compatibility
  src_ip?: string;          // Source IP (optional, from ClickHouse)
  src_port?: number;        // Source port (optional)
  dest_ip: string;          // Destination IP (backend uses dest_ip)
  dest_port: number;        // Destination port (backend uses dest_port)
  dst_ip?: string;          // Alias for backwards compatibility
  dst_port?: number;        // Alias for backwards compatibility
  tls_version: string;
  cipher_suite: string;
  pid?: number;             // Process ID (optional)
  comm?: string;            // Command name (optional)
}

// Mount Event
export interface MountEvent extends BaseEvent {
  event_type: 'mount_event';
  node?: string;            // Node name
  operation: 'mount' | 'umount';
  source: string;           // Mount source (device/path)
  target: string;           // Mount target (mount point)
  fs_type: string;          // Filesystem type (ext4, nfs, etc.)
  flags: string;            // Mount flags
  options: string;          // Mount options
  error_code: number;       // Error code (0 = success)
  pid: number;
  comm: string;
}

// Union type for all events
export type Event = 
  | NetworkFlowEvent 
  | DnsQueryEvent 
  | ProcessEvent 
  | FileEvent 
  | SecurityEvent 
  | OomEvent
  | BindEvent
  | SniEvent
  | MountEvent;

// Event statistics
export interface EventStats {
  cluster_id: string;
  analysis_id: string;
  total_events: number;
  event_counts: Record<EventType, number>;
  time_range: {
    start: string;
    end: string;
  };
  top_namespaces: { namespace: string; count: number }[];
  top_pods: { pod: string; namespace: string; count: number }[];
}

// Query parameters
export interface EventsQueryParams {
  cluster_id?: number;  // Optional for multi-cluster (use analysis_id)
  analysis_id?: number;
  event_type?: EventType;
  event_types?: string; // comma-separated list for multiple types
  namespace?: string;
  pod?: string;
  search?: string;      // Full-text search across relevant fields
  start_time?: string;
  end_time?: string;
  limit?: number;
  offset?: number;
}

// Unified event for timeline display (flattened structure)
export interface UnifiedEvent {
  event_id: string;
  timestamp: string;
  event_type: EventType;
  cluster_id: string;
  analysis_id: string;
  namespace: string;
  pod: string;
  container?: string;
  source?: string;  // formatted source (IP:port, path, etc.)
  target?: string;  // formatted target
  details?: string; // human-readable summary
  severity?: 'info' | 'warning' | 'error';
  raw_data?: Record<string, unknown>;
}

export interface EventsResponse {
  events: UnifiedEvent[];
  total: number;
  has_more: boolean;
}

export const eventsApi = createApi({
  reducerPath: 'eventsApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Events', 'EventStats'],
  endpoints: (builder) => ({
    // Get events list
    getEvents: builder.query<EventsResponse, EventsQueryParams>({
      query: (params) => ({
        url: '/events',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Events', id: `${params.cluster_id}-${params.analysis_id || 'all'}` }
      ],
    }),
    
    // Get event statistics
    getEventStats: builder.query<EventStats, { cluster_id?: number; analysis_id?: number }>({
      query: (params) => ({
        url: '/events/stats',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'EventStats', id: `${params.cluster_id}-${params.analysis_id || 'all'}` }
      ],
    }),
    
    // Get DNS queries - cache invalidated when search changes
    getDnsQueries: builder.query<{ queries: DnsQueryEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/dns',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Events', id: `dns-${params.cluster_id}-${params.analysis_id}-${params.search || 'all'}` }
      ],
    }),
    
    // Get TLS/SNI events - cache invalidated when search changes
    getSniEvents: builder.query<{ events: SniEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/sni',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Events', id: `sni-${params.cluster_id}-${params.analysis_id}-${params.search || 'all'}` }
      ],
    }),
    
    // Get security events
    getSecurityEvents: builder.query<{ events: SecurityEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/security',
        params,
      }),
      providesTags: ['Events'],
    }),
    
    // Get process events
    getProcessEvents: builder.query<{ events: ProcessEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/process',
        params,
      }),
      providesTags: ['Events'],
    }),
    
    // Get file events
    getFileEvents: builder.query<{ events: FileEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/file',
        params,
      }),
      providesTags: ['Events'],
    }),
    
    // Get bind events (listening ports) - cache invalidated when search changes
    getBindEvents: builder.query<{ events: BindEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/bind',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Events', id: `bind-${params.cluster_id}-${params.analysis_id}-${params.search || 'all'}` }
      ],
    }),
    
    // Get mount events
    getMountEvents: builder.query<{ events: MountEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/mount',
        params,
      }),
      providesTags: ['Events'],
    }),
    
    // Get OOM events
    getOomEvents: builder.query<{ events: OomEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/oom',
        params,
      }),
      providesTags: ['Events'],
    }),
    
    // Get network flow events (from ClickHouse network_flows table) - cache invalidated when search changes
    getNetworkFlows: builder.query<{ events: NetworkFlowEvent[]; total: number }, EventsQueryParams>({
      query: (params) => ({
        url: '/events/network',
        params,
      }),
      providesTags: (result, error, params) => [
        { type: 'Events', id: `network-${params.cluster_id}-${params.analysis_id}-${params.search || 'all'}` }
      ],
    }),
  }),
});

export const {
  useGetEventsQuery,
  useGetEventStatsQuery,
  useGetDnsQueriesQuery,
  useGetSniEventsQuery,
  useGetSecurityEventsQuery,
  useGetProcessEventsQuery,
  useGetFileEventsQuery,
  useGetBindEventsQuery,
  useGetMountEventsQuery,
  useGetOomEventsQuery,
  useGetNetworkFlowsQuery,
} = eventsApi;

