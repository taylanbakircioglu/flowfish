import { createApi, FetchArgs, FetchBaseQueryError, BaseQueryFn } from '@reduxjs/toolkit/query/react';
import { Cluster, Namespace } from '../../types';
import { baseQueryWithReauth } from './baseQuery';

interface ClustersResponse {
  clusters: Cluster[];
  count: number;
  message?: string;
}

// Fields that can be updated in a cluster
export interface ClusterUpdateData {
  name?: string;
  description?: string;
  environment?: string;
  provider?: string;
  region?: string;
  api_server_url?: string;
  gadget_namespace?: string;
  status?: string;
  skip_tls_verify?: boolean;
  // Sensitive fields - only updated if non-empty value provided
  token?: string;
  kubeconfig?: string;
  ca_cert?: string;
}

// Custom base query for /clusters endpoint
const clusterBaseQuery: BaseQueryFn<string | FetchArgs, unknown, FetchBaseQueryError> = async (args, api, extraOptions) => {
  // Prepend /clusters to the URL
  const adjustedArgs = typeof args === 'string' 
    ? `/clusters${args}` 
    : { ...args, url: `/clusters${args.url}` };
  return baseQueryWithReauth(adjustedArgs, api, extraOptions);
};

export const clusterApi = createApi({
  reducerPath: 'clusterApi',
  baseQuery: clusterBaseQuery,
  tagTypes: ['Cluster', 'Namespace'],
  endpoints: (builder) => ({
    getClusters: builder.query<ClustersResponse, void>({
      query: () => '',
      providesTags: ['Cluster'],
    }),
    getCluster: builder.query<Cluster, number>({
      query: (id) => `/${id}`,
      providesTags: (result, error, id) => [{ type: 'Cluster', id }],
    }),
    createCluster: builder.mutation<Cluster, Partial<Cluster>>({
      query: (cluster) => ({
        url: '',
        method: 'POST',
        body: cluster,
      }),
      invalidatesTags: ['Cluster'],
    }),
    updateCluster: builder.mutation<{ message: string; cluster: Cluster }, { id: number; data: ClusterUpdateData }>({
      query: ({ id, data }) => ({
        url: `/${id}`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: (result, error, { id }) => [{ type: 'Cluster', id }, 'Cluster'],
    }),
    deleteCluster: builder.mutation<void, number>({
      query: (id) => ({
        url: `/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Cluster'],
    }),
    syncCluster: builder.mutation<{ 
      message: string; 
      status: 'completed' | 'partial'; 
      resources: { nodes: number; pods: number; namespaces: number } | null; 
      gadget_health: string;
      warning?: string;
      gadget_details?: { version?: string; error?: string; pods_ready?: number; pods_total?: number };
    }, number>({
      query: (id) => ({
        url: `/${id}/sync`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, id) => [{ type: 'Cluster', id }, 'Cluster'],
    }),
    getClusterNamespaces: builder.query<Namespace[], number>({
      query: (clusterId) => `/${clusterId}/namespaces`,
      providesTags: (result, error, clusterId) => [
        { type: 'Namespace', id: `cluster-${clusterId}` },
      ],
    }),
    testConnection: builder.mutation<TestConnectionResponse, TestConnectionRequest>({
      query: (data) => ({
        url: '/test-connection',
        method: 'POST',
        body: data,
      }),
    }),
    getGadgetInstallScript: builder.query<string, { provider: string; mode?: string; storageClass?: string }>({
      query: ({ provider, mode = 'install', storageClass = '' }) => ({
        url: `/gadget-install-script?provider=${provider}&mode=${mode}&storage_class=${encodeURIComponent(storageClass)}`,
        responseHandler: 'text',
      }),
    }),
  }),
});

// Test connection types
interface TestConnectionRequest {
  connection_type: string;
  api_server_url?: string;
  token?: string;
  ca_cert?: string;
  skip_tls_verify?: boolean;
  gadget_namespace?: string;  // Namespace where gadget is deployed
}

interface TestConnectionResponse {
  cluster_connection: {
    status: 'success' | 'failed' | 'unknown';
    error: string | null;
    details: {
      k8s_version?: string;
      total_nodes?: number;
      total_pods?: number;
      total_namespaces?: number;
      platform?: string;
    };
  };
  gadget_connection: {
    status: 'success' | 'failed' | 'warning' | 'skipped' | 'unknown';
    error: string | null;
    details: {
      version?: string;
      pods_ready?: number;
      pods_total?: number;
    };
  };
  overall_status: 'success' | 'partial' | 'failed' | 'unknown';
  recommendations: string[];
}

export const {
  useGetClustersQuery,
  useGetClusterQuery,
  useCreateClusterMutation,
  useUpdateClusterMutation,
  useDeleteClusterMutation,
  useSyncClusterMutation,
  useGetClusterNamespacesQuery,
  useTestConnectionMutation,
  useGetGadgetInstallScriptQuery,
  useLazyGetGadgetInstallScriptQuery,
} = clusterApi;
