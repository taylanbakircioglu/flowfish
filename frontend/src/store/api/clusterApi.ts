import { createApi, FetchArgs, FetchBaseQueryError, BaseQueryFn } from '@reduxjs/toolkit/query/react';
import { Cluster, Namespace } from '../../types';
import { baseQueryWithReauth } from './baseQuery';

interface ClustersResponse {
  clusters: Cluster[];
  count: number;
  message?: string;
  supported_gadget_version?: string;
  supported_beyla_version?: string;
}

/** Single-cluster GET/PATCH response — Beyla/L7 fields come from `Cluster` in types. */
export type ClusterResponse = Cluster;

// Fields that can be updated in a cluster
export interface ClusterUpdateData {
  name?: string;
  description?: string;
  environment?: string;
  provider?: string;
  region?: string;
  api_server_url?: string;
  gadget_namespace?: string;
  beyla_namespace?: string;
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
      beyla_health?: string;
      beyla_version?: string;
      warning?: string;
      gadget_details?: { version?: string; error?: string; pods_ready?: number; pods_total?: number };
      beyla_details?: { daemonset_ready?: number; daemonset_total?: number; collector_ready?: boolean; issues?: string[]; error?: string };
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
    getGadgetInstallScript: builder.query<string, { provider: string; imageRegistry?: string }>({
      query: ({ provider, imageRegistry = '' }) => {
        let url = `/gadget-install-script?provider=${encodeURIComponent(provider)}&mode=install`;
        if (imageRegistry) url += `&image_registry=${encodeURIComponent(imageRegistry)}`;
        return { url, responseHandler: 'text' as const };
      },
    }),
    getGadgetUninstallScript: builder.query<string, { provider: string }>({
      query: ({ provider }) => ({
        url: `/gadget-install-script?provider=${encodeURIComponent(provider)}&mode=uninstall`,
        responseHandler: 'text' as const,
      }),
    }),
    getGadgetFixStorageScript: builder.query<string, { provider: string }>({
      query: ({ provider }) => ({
        url: `/gadget-fix-storage-script?provider=${encodeURIComponent(provider)}`,
        responseHandler: 'text' as const,
      }),
    }),
    getGadgetUpgradeScript: builder.query<string, { clusterId: number; targetVersion?: string; memoryLimit?: string }>({
      query: ({ clusterId, targetVersion = 'v0.50.1', memoryLimit = '6Gi' }) => ({
        url: `/${clusterId}/gadget-upgrade-script?target_version=${encodeURIComponent(targetVersion)}&memory_limit=${encodeURIComponent(memoryLimit)}`,
        responseHandler: 'text' as const,
      }),
    }),
    getBeylaInstallScriptGeneral: builder.query<string, { provider: string; mode?: string; namespace?: string; beylaVersion?: string; imageRegistry?: string; collectorTag?: string }>({
      query: ({ provider, mode = 'install', namespace = '', beylaVersion = 'v3.9.5', imageRegistry = '', collectorTag = '' }) => {
        let url = `/beyla-install-script?provider=${encodeURIComponent(provider)}&mode=${encodeURIComponent(mode)}&beyla_version=${encodeURIComponent(beylaVersion)}`;
        if (namespace) url += `&namespace=${encodeURIComponent(namespace)}`;
        if (imageRegistry) url += `&image_registry=${encodeURIComponent(imageRegistry)}`;
        if (collectorTag) url += `&collector_tag=${encodeURIComponent(collectorTag)}`;
        return { url, responseHandler: 'text' as const };
      },
    }),
    getBeylaInstallScript: builder.query<string, { clusterId: number; provider?: string; mode?: string; namespace?: string; beylaVersion?: string; imageRegistry?: string; collectorTag?: string }>({
      query: ({ clusterId, provider = 'kubernetes', mode = 'install', namespace = '', beylaVersion = 'v3.9.5', imageRegistry = '', collectorTag = '' }) => {
        let url = `/${clusterId}/beyla-install-script?provider=${encodeURIComponent(provider)}&mode=${encodeURIComponent(mode)}&beyla_version=${encodeURIComponent(beylaVersion)}`;
        if (namespace) url += `&namespace=${encodeURIComponent(namespace)}`;
        if (imageRegistry) url += `&image_registry=${encodeURIComponent(imageRegistry)}`;
        if (collectorTag) url += `&collector_tag=${encodeURIComponent(collectorTag)}`;
        return { url, responseHandler: 'text' as const };
      },
    }),
    getBeylaUpgradeScript: builder.query<string, { clusterId: number; targetVersion?: string }>({
      query: ({ clusterId, targetVersion = 'v3.9.5' }) => ({
        url: `/${clusterId}/beyla-upgrade-script?target_version=${encodeURIComponent(targetVersion)}`,
        responseHandler: 'text' as const,
      }),
    }),
    getL7UninstallScript: builder.query<string, { provider: string }>({
      query: ({ provider }) => ({
        url: `/l7-uninstall-script?provider=${encodeURIComponent(provider)}`,
        responseHandler: 'text' as const,
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
  gadget_namespace?: string;
  cluster_id?: number;
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
  useLazyGetGadgetInstallScriptQuery,
  useLazyGetGadgetUninstallScriptQuery,
  useLazyGetGadgetUpgradeScriptQuery,
  useLazyGetGadgetFixStorageScriptQuery,
  useLazyGetBeylaInstallScriptGeneralQuery,
  useLazyGetBeylaInstallScriptQuery,
  useLazyGetBeylaUpgradeScriptQuery,
  useLazyGetL7UninstallScriptQuery,
} = clusterApi;
