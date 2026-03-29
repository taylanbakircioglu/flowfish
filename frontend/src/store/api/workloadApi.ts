import { createApi } from '@reduxjs/toolkit/query/react';
import { Workload, Namespace } from '../../types';
import { baseQueryWithReauth } from './baseQuery';

interface WorkloadStats {
  total_workloads: number;
  by_type: Record<string, number>;
  by_namespace: Record<string, number>;
  active_workloads: number;
}

interface DiscoveryResponse {
  message: string;
  discovered_count: number;
}

// Types for cluster resources
export interface Deployment {
  name: string;
  namespace: string;
  uid?: string;
  replicas: number;
  available_replicas: number;
  labels: Record<string, string>;
  image?: string;
  created_at?: string;
}

export interface Pod {
  name: string;
  namespace: string;
  uid?: string;
  status: string;
  node_name?: string;
  labels: Record<string, string>;
  ip?: string;
  created_at?: string;
}

export interface Service {
  name: string;
  namespace: string;
  uid?: string;
  type: string;  // ClusterIP, NodePort, LoadBalancer
  cluster_ip?: string;
  ports: Array<{
    name?: string;
    port: number;
    target_port: number | string;
    protocol: string;
  }>;
  labels: Record<string, string>;
  selector?: Record<string, string>;
  created_at?: string;
}

export interface LabelInfo {
  key: string;
  values: string[];
}

export const workloadApi = createApi({
  reducerPath: 'workloadApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['Workload', 'Namespace'],
  endpoints: (builder) => ({
    // Workloads
    getWorkloads: builder.query<Workload[], {
      cluster_id: number;
      namespace?: string;
      workload_type?: string;
      is_active?: boolean;
    }>({
      query: ({ cluster_id, namespace, workload_type, is_active = true }) => ({
        url: '/workloads',
        params: { cluster_id, namespace, workload_type, is_active }
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Workload', id: `cluster-${cluster_id}` }
      ],
    }),
    
    // Namespaces
    getNamespaces: builder.query<Namespace[], number>({
      query: (cluster_id) => ({
        url: '/namespaces',
        params: { cluster_id }
      }),
      providesTags: (result, error, cluster_id) => [
        { type: 'Namespace', id: `cluster-${cluster_id}` }
      ],
    }),
    
    // Deployments
    getDeployments: builder.query<Deployment[], { cluster_id: number; namespace?: string }>({
      query: ({ cluster_id, namespace }) => ({
        url: '/deployments',
        params: { cluster_id, namespace }
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Workload', id: `deployments-${cluster_id}` }
      ],
    }),
    
    // Pods
    getPods: builder.query<Pod[], { cluster_id: number; namespace?: string; label_selector?: string }>({
      query: ({ cluster_id, namespace, label_selector }) => ({
        url: '/pods',
        params: { cluster_id, namespace, label_selector }
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Workload', id: `pods-${cluster_id}` }
      ],
    }),
    
    // Services
    getServices: builder.query<Service[], { cluster_id: number; namespace?: string }>({
      query: ({ cluster_id, namespace }) => ({
        url: '/services',
        params: { cluster_id, namespace }
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Workload', id: `services-${cluster_id}` }
      ],
    }),
    
    // Labels
    getLabels: builder.query<string[], { cluster_id: number; resource_type?: string; namespace?: string }>({
      query: ({ cluster_id, resource_type = 'pods', namespace }) => ({
        url: '/labels',
        params: { cluster_id, resource_type, namespace }
      }),
      providesTags: (result, error, { cluster_id }) => [
        { type: 'Workload', id: `labels-${cluster_id}` }
      ],
    }),
    
    // Discovery
    triggerDiscovery: builder.mutation<DiscoveryResponse, number>({
      query: (cluster_id) => ({
        url: `/workloads/discover/${cluster_id}`,
        method: 'POST'
      }),
      invalidatesTags: (result, error, cluster_id) => [
        { type: 'Workload', id: `cluster-${cluster_id}` },
        { type: 'Namespace', id: `cluster-${cluster_id}` }
      ],
    }),
    
    // Stats - supports optional analysis_id for analysis-specific workload counts
    getWorkloadStats: builder.query<WorkloadStats, { cluster_id: number; analysis_id?: number }>({
      query: ({ cluster_id, analysis_id }) => ({
        url: `/workloads/stats/${cluster_id}`,
        params: analysis_id ? { analysis_id } : undefined,
      }),
      providesTags: (result, error, { cluster_id, analysis_id }) => [
        { type: 'Workload', id: `stats-${cluster_id}-${analysis_id || 'all'}` }
      ],
    }),
  }),
});

export const {
  useGetWorkloadsQuery,
  useGetNamespacesQuery,
  useGetDeploymentsQuery,
  useGetPodsQuery,
  useGetServicesQuery,
  useGetLabelsQuery,
  useTriggerDiscoveryMutation,
  useGetWorkloadStatsQuery,
} = workloadApi;
