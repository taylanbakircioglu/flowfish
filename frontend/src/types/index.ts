// Common types for Flowfish frontend

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  first_name?: string;
  last_name?: string;
  roles: string[];
  is_active: boolean;
  created_at: string;
}

export interface Cluster {
  id: number;
  name: string;
  description?: string;
  environment?: string;
  provider?: string;
  region?: string;
  connection_type?: string;
  api_server_url?: string;
  gadget_namespace?: string;  // Namespace where Inspector Gadget is deployed
  gadget_endpoint?: string;   // Deprecated - kept for backward compatibility
  gadget_health_status?: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  gadget_version?: string;
  status?: 'active' | 'inactive' | 'maintenance' | 'deleted';
  total_nodes?: number;
  total_pods?: number;
  total_namespaces?: number;
  k8s_version?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Namespace {
  id: number;
  cluster_id: number;
  name: string;
  uid?: string;
  labels: Record<string, string>;
  status: string;
  workload_count: number;
  created_at: string;
}

export interface Workload {
  id: number;
  cluster_id: number;
  namespace_id: number;
  namespace_name?: string;  // For display purposes
  workload_type: 'pod' | 'deployment' | 'statefulset' | 'service';
  name: string;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  ip_address?: string;
  ports: Array<{ port: number; protocol: string }>;
  status: string;
  is_active: boolean;
  first_seen: string;
  last_seen: string;
}

export interface Communication {
  id: number;
  cluster_id: number;
  source_namespace: string;
  source_workload: string;
  destination_namespace: string;
  destination_workload: string;
  destination_ip: string;
  destination_port: number;
  protocol: string;
  request_count: number;
  avg_latency_ms: number;
  risk_score: number;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  is_external: boolean;
  is_cross_namespace: boolean;
  first_seen: string;
  last_seen: string;
}

export interface GraphNode {
  id: string;
  type: string;
  name: string;
  namespace: string;
  labels: Record<string, string>;
  metadata: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  port: number;
  protocol: string;
  metrics: {
    request_count: number;
    avg_latency_ms: number;
    risk_score: number;
  };
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total_nodes: number;
  total_edges: number;
}

export interface Analysis {
  id: number;
  name: string;
  description?: string;
  cluster_id: number;  // Primary cluster
  cluster_ids?: number[];  // All clusters for multi-cluster analysis
  is_multi_cluster?: boolean;  // Flag indicating multi-cluster analysis
  status: 'draft' | 'running' | 'stopped' | 'completed' | 'failed';
  scope_type: string;
  scope_config: Record<string, unknown>;
  gadget_config: Record<string, unknown>;
  time_config: Record<string, unknown>;
  output_config: Record<string, unknown>;
  // Change Detection settings
  change_detection_enabled?: boolean;
  change_detection_strategy?: 'baseline' | 'rolling_window' | 'run_comparison';
  change_detection_types?: string[];
  // Timestamps
  created_at: string;
  updated_at?: string;
  started_at?: string;
  stopped_at?: string;
  created_by: number;
  // Scheduling
  is_scheduled?: boolean;
  schedule_expression?: string;
  schedule_duration_seconds?: number;
  next_run_at?: string;
  last_run_at?: string;
  schedule_run_count?: number;
  max_scheduled_runs?: number;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  success: boolean;
}

export interface PaginatedResponse<T> {
  items: T[];
  total_items: number;
  total_pages: number;
  page: number;
  page_size: number;
}
