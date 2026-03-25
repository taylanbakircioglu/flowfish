import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { 
  Card, 
  Steps, 
  Typography, 
  Button, 
  Space, 
  Form, 
  Input, 
  Select, 
  Checkbox, 
  InputNumber,
  Radio,
  message,
  DatePicker,
  Alert,
  Spin,
  Tag,
  Tooltip,
  Badge,
  Divider,
  Tabs,
  Row,
  Col,
  Statistic,
  Switch
} from 'antd';
import { 
  ExperimentOutlined, 
  AimOutlined, 
  AppstoreOutlined, 
  ClockCircleOutlined, 
  CheckCircleOutlined,
  ClusterOutlined,
  InfoCircleOutlined,
  GlobalOutlined,
  DatabaseOutlined,
  AppstoreAddOutlined,
  ContainerOutlined,
  ThunderboltOutlined,
  HddOutlined,
  SyncOutlined,
  StopOutlined,
  FieldTimeOutlined,
  CalendarOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { 
  useGetNamespacesQuery, 
  useGetDeploymentsQuery, 
  useGetPodsQuery, 
  useGetLabelsQuery,
  Deployment,
  Pod
} from '../store/api/workloadApi';
import { useGetEventTypesQuery } from '../store/api/eventTypeApi';
import { useCreateAnalysisMutation, useScheduleAnalysisMutation, AnalysisCreateRequest } from '../store/api/analysisApi';
import { Namespace } from '../types';

// Multi-cluster color palette for visual distinction
const CLUSTER_COLORS = [
  '#0891b2', // Blue
  '#4d9f7c', // Green
  '#7c8eb5', // Purple
  '#b89b5d', // Orange
  '#a67c9e', // Magenta
  '#22a6a6', // Cyan
  '#c75450', // Red
  '#c9a55a', // Gold
];

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

// ============================================
// Constants - Defined outside component to prevent re-creation on each render
// ============================================

// Event generation rates per pod per hour (based on gadget type and data_volume)
// These are conservative estimates based on typical Kubernetes cluster behavior
// Keys match event type IDs from backend (network_flow, dns_query, etc.)
const GADGET_EVENT_RATES: Record<string, { eventsPerPodPerHour: number; avgEventSizeKB: number }> = {
  // Network Flow - high volume (trace_network gadget)
  'network_flow': { eventsPerPodPerHour: 500, avgEventSizeKB: 0.8 },
  // DNS Query - medium volume (trace_dns gadget)
  'dns_query': { eventsPerPodPerHour: 100, avgEventSizeKB: 0.4 },
  // TCP Throughput - medium volume (top_tcp gadget) - Required for bytes sent/received
  'tcp_throughput': { eventsPerPodPerHour: 200, avgEventSizeKB: 0.5 },
  // TCP Retransmit - low volume (trace_tcpretrans gadget) - Required for network errors
  'tcp_retransmit': { eventsPerPodPerHour: 20, avgEventSizeKB: 0.3 },
  // Process Execution - low volume (trace_exec gadget)
  'process_exec': { eventsPerPodPerHour: 50, avgEventSizeKB: 0.6 },
  // File Operations - high volume (trace_open gadget)
  'file_operations': { eventsPerPodPerHour: 300, avgEventSizeKB: 0.5 },
  // Capability Checks - low volume (trace_capabilities gadget)
  'capability_checks': { eventsPerPodPerHour: 20, avgEventSizeKB: 0.3 },
  // OOM Kills - very low volume (trace_oomkill gadget)
  'oom_kills': { eventsPerPodPerHour: 5, avgEventSizeKB: 0.4 },
  // Socket Bind - low volume (trace_bind gadget)
  'bind_events': { eventsPerPodPerHour: 30, avgEventSizeKB: 0.4 },
  // TLS/SNI - medium volume (trace_sni gadget)
  'sni_events': { eventsPerPodPerHour: 80, avgEventSizeKB: 0.4 },
  // Mount Events - low volume (trace_mount gadget)
  'mount_events': { eventsPerPodPerHour: 10, avgEventSizeKB: 0.3 },
};

// Default event rate for unknown gadgets
const DEFAULT_EVENT_RATE = { eventsPerPodPerHour: 100, avgEventSizeKB: 0.5 };

// Interface for per-cluster scope configuration
interface PerClusterScope {
  namespaces?: string[];
  deployments?: string[];
  pods?: string[];
  labels?: string[];
}

// Interface for cluster with resources
interface ClusterWithResources {
  id: number;
  name: string;
  color: string;
  environment?: string;
  provider?: string;
  namespaces: Namespace[];
  deployments: Deployment[];
  pods: Pod[];
  labels: string[];
  isLoading: boolean;
}

// Default system noise exclusion patterns (OpenShift + Kubernetes infra)
const DEFAULT_EXCLUDE_NAMESPACES = [
  'openshift-*',
  'kube-system',
  'kube-public',
  'kube-node-lease',
];
const DEFAULT_EXCLUDE_POD_PATTERNS = [
  'calico-node-*',
  'kube-proxy-*',
  'node-exporter-*',
];

// Preset groups for quick selection
const EXCLUSION_PRESETS: { label: string; namespaces: string[]; pods: string[] }[] = [
  {
    label: 'OpenShift System',
    namespaces: ['openshift-*'],
    pods: [],
  },
  {
    label: 'Kubernetes Infra',
    namespaces: ['kube-system', 'kube-public', 'kube-node-lease'],
    pods: ['kube-proxy-*'],
  },
  {
    label: 'Network Plugins',
    namespaces: ['calico-system', 'tigera-operator'],
    pods: ['calico-node-*'],
  },
  {
    label: 'Monitoring',
    namespaces: ['monitoring', 'openshift-monitoring'],
    pods: ['node-exporter-*', 'prometheus-*'],
  },
];

const AnalysisWizard: React.FC = () => {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [currentStep, setCurrentStep] = useState(0);
  const [wizardData, setWizardData] = useState<Partial<AnalysisCreateRequest>>({});
  const [isMultiCluster, setIsMultiCluster] = useState(false);
  const [perClusterScope, setPerClusterScope] = useState<Record<number, PerClusterScope>>({});
  const [scopeMode, setScopeMode] = useState<'unified' | 'per-cluster'>('unified');
  
  // System noise exclusion (default ON)
  const [excludeEnabled, setExcludeEnabled] = useState(true);
  const [excludeNamespaces, setExcludeNamespaces] = useState<string[]>([...DEFAULT_EXCLUDE_NAMESPACES]);
  const [excludePodPatterns, setExcludePodPatterns] = useState<string[]>([...DEFAULT_EXCLUDE_POD_PATTERNS]);
  
  // ============================================
  // Global Settings for Continuous Mode Auto-Stop
  // ============================================
  const [defaultContinuousDuration, setDefaultContinuousDuration] = useState<number>(10);
  
  // Fetch global settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const token = localStorage.getItem('flowfish_token');
        const response = await fetch('/api/v1/settings/analysis-limits', {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
        if (response.ok) {
          const data = await response.json();
          if (data.default_continuous_duration_minutes) {
            setDefaultContinuousDuration(data.default_continuous_duration_minutes);
          }
        }
      } catch {
        // Silently fail, use default value
      }
    };
    fetchSettings();
  }, []);
  
  // ============================================
  // Form State Tracking for Reliable Reactivity
  // ============================================
  // Track form values in state for reliable estimation updates
  const [formState, setFormState] = useState<{
    cluster_id?: number;
    cluster_ids?: number[];
    scope_type?: string;
    namespaces?: string[];
    deployments?: string[];
    pods?: string[];
    enabled_gadgets?: string[];
  }>({});
  
  // Update formState when form values change
  // IMPORTANT: Only update values that are defined in allValues to preserve values from previous steps
  const handleFormValuesChange = useCallback((changedValues: any, allValues: any) => {
    setFormState(prev => ({
      ...prev,
      // Only update if the value is explicitly set (not undefined)
      // This prevents losing values from previous steps
      cluster_id: allValues.cluster_id !== undefined ? allValues.cluster_id : prev.cluster_id,
      cluster_ids: allValues.cluster_ids !== undefined ? allValues.cluster_ids : prev.cluster_ids,
      scope_type: allValues.scope_type !== undefined ? allValues.scope_type : prev.scope_type,
      namespaces: allValues.namespaces !== undefined ? allValues.namespaces : prev.namespaces,
      deployments: allValues.deployments !== undefined ? allValues.deployments : prev.deployments,
      pods: allValues.pods !== undefined ? allValues.pods : prev.pods,
      enabled_gadgets: allValues.enabled_gadgets !== undefined ? allValues.enabled_gadgets : prev.enabled_gadgets,
    }));
  }, []);
  
  // API hooks
  const { data: clustersResponse, isLoading: isClustersLoading } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  // For single cluster mode
  const selectedClusterId = Form.useWatch('cluster_id', form);
  // For multi-cluster mode
  const selectedClusterIds = Form.useWatch('cluster_ids', form) as number[] | undefined;
  const selectedNamespaces = Form.useWatch('namespaces', form) as string[] | undefined;
  const scopeType = Form.useWatch('scope_type', form);
  
  // Get cluster info with color
  const getClusterInfo = useCallback((clusterId: number) => {
    const cluster = clusters.find((c: any) => c.id === clusterId);
    const index = (selectedClusterIds || []).indexOf(clusterId);
    return {
      ...cluster,
      color: CLUSTER_COLORS[index % CLUSTER_COLORS.length] || CLUSTER_COLORS[0],
      index
    };
  }, [clusters, selectedClusterIds]);
  
  // Get the primary cluster for loading resources (single cluster mode or first in multi-cluster)
  const primaryClusterId = useMemo(() => {
    if (isMultiCluster && selectedClusterIds?.length) {
      return selectedClusterIds[0];
    }
    return selectedClusterId;
  }, [isMultiCluster, selectedClusterIds, selectedClusterId]);
  
  // ============================================
  // Multi-Cluster Resource Fetching
  // ============================================
  
  // For single cluster or primary cluster in multi-cluster mode
  const { data: namespacesData, isLoading: isNamespacesLoading } = useGetNamespacesQuery(primaryClusterId!, { 
    skip: !primaryClusterId 
  });
  const primaryNamespaces = Array.isArray(namespacesData) ? namespacesData : [];
  
  // Fetch resources for additional clusters in multi-cluster mode
  // We use individual queries for each cluster (up to 4 additional clusters)
  const cluster2Id = selectedClusterIds?.[1];
  const cluster3Id = selectedClusterIds?.[2];
  const cluster4Id = selectedClusterIds?.[3];
  
  const { data: ns2Data, isLoading: isNs2Loading } = useGetNamespacesQuery(cluster2Id!, { skip: !cluster2Id || !isMultiCluster });
  const { data: ns3Data, isLoading: isNs3Loading } = useGetNamespacesQuery(cluster3Id!, { skip: !cluster3Id || !isMultiCluster });
  const { data: ns4Data, isLoading: isNs4Loading } = useGetNamespacesQuery(cluster4Id!, { skip: !cluster4Id || !isMultiCluster });
  
  // Deployments for all clusters
  const { data: deploymentsData, isLoading: isDeploymentsLoading } = useGetDeploymentsQuery(
    { cluster_id: primaryClusterId!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !primaryClusterId || scopeType !== 'deployment' }
  );
  const { data: dep2Data, isLoading: isDep2Loading } = useGetDeploymentsQuery(
    { cluster_id: cluster2Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster2Id || !isMultiCluster || scopeType !== 'deployment' }
  );
  const { data: dep3Data, isLoading: isDep3Loading } = useGetDeploymentsQuery(
    { cluster_id: cluster3Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster3Id || !isMultiCluster || scopeType !== 'deployment' }
  );
  const { data: dep4Data, isLoading: isDep4Loading } = useGetDeploymentsQuery(
    { cluster_id: cluster4Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster4Id || !isMultiCluster || scopeType !== 'deployment' }
  );
  
  // Pods for all clusters
  const { data: podsData, isLoading: isPodsLoading } = useGetPodsQuery(
    { cluster_id: primaryClusterId!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !primaryClusterId || scopeType !== 'pod' }
  );
  const { data: pods2Data, isLoading: isPods2Loading } = useGetPodsQuery(
    { cluster_id: cluster2Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster2Id || !isMultiCluster || scopeType !== 'pod' }
  );
  const { data: pods3Data, isLoading: isPods3Loading } = useGetPodsQuery(
    { cluster_id: cluster3Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster3Id || !isMultiCluster || scopeType !== 'pod' }
  );
  const { data: pods4Data, isLoading: isPods4Loading } = useGetPodsQuery(
    { cluster_id: cluster4Id!, namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster4Id || !isMultiCluster || scopeType !== 'pod' }
  );
  
  // Labels for all clusters
  const { data: labelsData, isLoading: isLabelsLoading } = useGetLabelsQuery(
    { cluster_id: primaryClusterId!, resource_type: 'pods', namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !primaryClusterId || scopeType !== 'label' }
  );
  const { data: labels2Data, isLoading: isLabels2Loading } = useGetLabelsQuery(
    { cluster_id: cluster2Id!, resource_type: 'pods', namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster2Id || !isMultiCluster || scopeType !== 'label' }
  );
  const { data: labels3Data, isLoading: isLabels3Loading } = useGetLabelsQuery(
    { cluster_id: cluster3Id!, resource_type: 'pods', namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster3Id || !isMultiCluster || scopeType !== 'label' }
  );
  const { data: labels4Data, isLoading: isLabels4Loading } = useGetLabelsQuery(
    { cluster_id: cluster4Id!, resource_type: 'pods', namespace: selectedNamespaces?.length === 1 ? selectedNamespaces[0] : undefined },
    { skip: !cluster4Id || !isMultiCluster || scopeType !== 'label' }
  );
  
  // Aggregate all cluster resources with metadata
  const allClusterResources = useMemo((): ClusterWithResources[] => {
    if (!isMultiCluster || !selectedClusterIds?.length) {
      // Single cluster mode
      if (!primaryClusterId) return [];
      const clusterInfo = getClusterInfo(primaryClusterId);
      return [{
        id: primaryClusterId,
        name: clusterInfo?.name || `Cluster ${primaryClusterId}`,
        color: clusterInfo?.color || CLUSTER_COLORS[0],
        environment: clusterInfo?.environment,
        provider: clusterInfo?.provider,
        namespaces: primaryNamespaces,
        deployments: Array.isArray(deploymentsData) ? deploymentsData : [],
        pods: Array.isArray(podsData) ? podsData : [],
        labels: Array.isArray(labelsData) ? labelsData : [],
        isLoading: isNamespacesLoading || isDeploymentsLoading || isPodsLoading || isLabelsLoading
      }];
    }
    
    // Multi-cluster mode - aggregate resources from all selected clusters
    const resources: ClusterWithResources[] = [];
    
    if (primaryClusterId) {
      const info = getClusterInfo(primaryClusterId);
      resources.push({
        id: primaryClusterId,
        name: info?.name || `Cluster ${primaryClusterId}`,
        color: info?.color || CLUSTER_COLORS[0],
        environment: info?.environment,
        provider: info?.provider,
        namespaces: primaryNamespaces,
        deployments: Array.isArray(deploymentsData) ? deploymentsData : [],
        pods: Array.isArray(podsData) ? podsData : [],
        labels: Array.isArray(labelsData) ? labelsData : [],
        isLoading: isNamespacesLoading || isDeploymentsLoading || isPodsLoading || isLabelsLoading
      });
    }
    
    if (cluster2Id) {
      const info = getClusterInfo(cluster2Id);
      resources.push({
        id: cluster2Id,
        name: info?.name || `Cluster ${cluster2Id}`,
        color: info?.color || CLUSTER_COLORS[1],
        environment: info?.environment,
        provider: info?.provider,
        namespaces: Array.isArray(ns2Data) ? ns2Data : [],
        deployments: Array.isArray(dep2Data) ? dep2Data : [],
        pods: Array.isArray(pods2Data) ? pods2Data : [],
        labels: Array.isArray(labels2Data) ? labels2Data : [],
        isLoading: isNs2Loading || isDep2Loading || isPods2Loading || isLabels2Loading
      });
    }
    
    if (cluster3Id) {
      const info = getClusterInfo(cluster3Id);
      resources.push({
        id: cluster3Id,
        name: info?.name || `Cluster ${cluster3Id}`,
        color: info?.color || CLUSTER_COLORS[2],
        environment: info?.environment,
        provider: info?.provider,
        namespaces: Array.isArray(ns3Data) ? ns3Data : [],
        deployments: Array.isArray(dep3Data) ? dep3Data : [],
        pods: Array.isArray(pods3Data) ? pods3Data : [],
        labels: Array.isArray(labels3Data) ? labels3Data : [],
        isLoading: isNs3Loading || isDep3Loading || isPods3Loading || isLabels3Loading
      });
    }
    
    if (cluster4Id) {
      const info = getClusterInfo(cluster4Id);
      resources.push({
        id: cluster4Id,
        name: info?.name || `Cluster ${cluster4Id}`,
        color: info?.color || CLUSTER_COLORS[3],
        environment: info?.environment,
        provider: info?.provider,
        namespaces: Array.isArray(ns4Data) ? ns4Data : [],
        deployments: Array.isArray(dep4Data) ? dep4Data : [],
        pods: Array.isArray(pods4Data) ? pods4Data : [],
        labels: Array.isArray(labels4Data) ? labels4Data : [],
        isLoading: isNs4Loading || isDep4Loading || isPods4Loading || isLabels4Loading
      });
    }
    
    return resources;
  }, [
    isMultiCluster, selectedClusterIds, primaryClusterId, cluster2Id, cluster3Id, cluster4Id,
    getClusterInfo, primaryNamespaces, deploymentsData, podsData, labelsData,
    ns2Data, dep2Data, pods2Data, labels2Data,
    ns3Data, dep3Data, pods3Data, labels3Data,
    ns4Data, dep4Data, pods4Data, labels4Data,
    isNamespacesLoading, isDeploymentsLoading, isPodsLoading, isLabelsLoading,
    isNs2Loading, isDep2Loading, isPods2Loading, isLabels2Loading,
    isNs3Loading, isDep3Loading, isPods3Loading, isLabels3Loading,
    isNs4Loading, isDep4Loading, isPods4Loading, isLabels4Loading
  ]);
  
  // Check if any cluster is loading
  const isAnyClusterLoading = allClusterResources.some(c => c.isLoading);
  
  const { data: eventTypes = [], isLoading: isEventTypesLoading } = useGetEventTypesQuery();
  
  const [createAnalysis, { isLoading: isCreating }] = useCreateAnalysisMutation();
  const [scheduleAnalysis] = useScheduleAnalysisMutation();
  
  // Default gadgets: all available event types
  const defaultGadgets = useMemo(() => 
    eventTypes.filter((et: any) => et.status === 'available').map((et: any) => et.id),
    [eventTypes]
  );
  
  // ============================================
  // Smart Estimation Calculator
  // ============================================
  
  // Create a version key that changes whenever formState changes
  // This ensures useMemo dependencies are primitive values
  const formStateVersion = useMemo(() => {
    return JSON.stringify({
      cluster_id: formState.cluster_id,
      cluster_ids: formState.cluster_ids,
      scope_type: formState.scope_type,
      namespaces: formState.namespaces?.length,
      deployments: formState.deployments?.length,
      pods: formState.pods?.length,
      enabled_gadgets: formState.enabled_gadgets?.length,
    });
  }, [formState]);
  
  // Get selected gadgets directly (not memoized to ensure reactivity)
  const getSelectedGadgets = () => {
    if (formState.enabled_gadgets !== undefined) {
      return formState.enabled_gadgets;
    }
    return defaultGadgets;
  };
  
  // Calculate estimated metrics based on scope, cluster resources, and selected gadgets
  // Uses formState values directly for reliable reactivity
  const estimatedMetrics = useMemo(() => {
    // Get values directly from formState (formStateVersion ensures reactivity)
    const clusterId = formState.cluster_id;
    const clusterIds = formState.cluster_ids;
    const currentScopeType = formState.scope_type;
    const namespaces = formState.namespaces;
    const deployments = formState.deployments;
    const pods = formState.pods;
    const gadgets = getSelectedGadgets();
    
    // Get pod count based on scope - uses actual resource data
    let estimatedPodCount = 0;
    
    // Helper: Get cluster info by ID (handles type mismatches)
    const getClusterById = (cId: number | string) => {
      return clusters.find((cl: any) => 
        cl.id === cId || 
        cl.id === Number(cId) || 
        String(cl.id) === String(cId)
      );
    };
    
    // Calculate based on scope type
    if (currentScopeType === 'cluster' || !currentScopeType) {
      // CLUSTER SCOPE: Use total_pods from cluster info
      // Priority: 1. formState clusterIds, 2. formState clusterId, 3. primaryClusterId, 4. First cluster
      
      if (isMultiCluster && clusterIds?.length) {
        // Multi-cluster mode: sum total_pods from all selected clusters
        estimatedPodCount = clusterIds.reduce((sum, cId) => {
          const clusterInfo = getClusterById(cId);
          return sum + (clusterInfo?.total_pods || 0);
        }, 0);
      } else if (clusterId) {
        // Single cluster mode: use clusterId from formState
        const clusterInfo = getClusterById(clusterId);
        estimatedPodCount = clusterInfo?.total_pods || 0;
      } else if (primaryClusterId) {
        // Fallback to primaryClusterId
        const clusterInfo = getClusterById(primaryClusterId);
        estimatedPodCount = clusterInfo?.total_pods || 0;
      }
      
      // Last resort: if still 0 and clusters are available, show first cluster's pods
      if (estimatedPodCount === 0 && clusters.length > 0) {
        estimatedPodCount = clusters[0]?.total_pods || 0;
      }
      
    } else if (currentScopeType === 'namespace') {
      // NAMESPACE SCOPE: Use workload_count from selected namespaces
      const selectedNs = namespaces || [];
      
      if (selectedNs.length > 0 && allClusterResources.length > 0) {
        estimatedPodCount = allClusterResources.reduce((sum, clusterResource) => {
          // Parse namespace values (format: "ns-name" or "ns-name@clusterId")
          const nsNamesForCluster = selectedNs
            .filter(ns => ns.includes('@') ? ns.endsWith(`@${clusterResource.id}`) : true)
            .map(ns => ns.includes('@') ? ns.split('@')[0] : ns);
          
          // Sum workload_count for selected namespaces (workload_count = pod count)
          const podsInSelectedNs = clusterResource.namespaces
            .filter(ns => nsNamesForCluster.includes(ns.name))
            .reduce((nsSum, ns) => nsSum + (ns.workload_count || 0), 0);
          
          return sum + podsInSelectedNs;
        }, 0);
      }
      
      // Fallback: if still 0, estimate based on cluster total
      if (estimatedPodCount === 0 && selectedNs.length > 0) {
        // Estimate: each namespace has roughly (total_pods / total_namespaces) pods
        const activeClusterId = clusterId || primaryClusterId;
        const clusterInfo = activeClusterId ? getClusterById(activeClusterId) : clusters[0];
        if (clusterInfo?.total_pods && clusterInfo?.total_namespaces) {
          const avgPodsPerNs = Math.ceil(clusterInfo.total_pods / clusterInfo.total_namespaces);
          estimatedPodCount = selectedNs.length * avgPodsPerNs;
        }
      }
      
    } else if (currentScopeType === 'deployment') {
      // DEPLOYMENT SCOPE: Use deployment replica counts
      const selectedDeps = deployments || [];
      
      if (selectedDeps.length > 0 && allClusterResources.length > 0) {
        estimatedPodCount = allClusterResources.reduce((sum, c) => {
          const depsForCluster = selectedDeps
            .filter(d => d.includes('@') ? d.endsWith(`@${c.id}`) : true)
            .map(d => d.includes('@') ? d.split('@')[0] : d);
          
          const podsFromDeps = c.deployments
            .filter(d => depsForCluster.includes(d.name))
            .reduce((depSum, d) => depSum + (d.available_replicas || d.replicas || 1), 0);
          return sum + podsFromDeps;
        }, 0);
      }
      
      // Fallback: estimate 3 pods per deployment
      if (estimatedPodCount === 0 && selectedDeps.length > 0) {
        estimatedPodCount = selectedDeps.length * 3;
      }
      
    } else if (currentScopeType === 'pod') {
      // POD SCOPE: Exact count from selection
      estimatedPodCount = pods?.length || 0;
      
    } else if (currentScopeType === 'label') {
      // LABEL SCOPE: Estimate 20% of cluster pods
      const activeClusterId = clusterId || primaryClusterId;
      const clusterInfo = activeClusterId ? getClusterById(activeClusterId) : clusters[0];
      const totalPods = clusterInfo?.total_pods || 0;
      estimatedPodCount = Math.ceil(totalPods * 0.2);
    }
    
    // Ensure minimum of 1 pod for calculations
    estimatedPodCount = Math.max(estimatedPodCount, 1);
    
    // Calculate events per hour based on selected gadgets
    let totalEventsPerHour = 0;
    let totalMBPerHour = 0;
    
    const gadgetsToUse = gadgets || [];
    
    gadgetsToUse.forEach(gadgetId => {
      const rates = GADGET_EVENT_RATES[gadgetId] || DEFAULT_EVENT_RATE;
      const eventsForGadget = rates.eventsPerPodPerHour * estimatedPodCount;
      totalEventsPerHour += eventsForGadget;
      totalMBPerHour += (eventsForGadget * rates.avgEventSizeKB) / 1024;
    });
    
    // If no gadgets selected, use defaults (assuming at least network_flow)
    if (gadgetsToUse.length === 0) {
      const defaultRate = GADGET_EVENT_RATES['network_flow'] || DEFAULT_EVENT_RATE;
      totalEventsPerHour = defaultRate.eventsPerPodPerHour * estimatedPodCount;
      totalMBPerHour = (totalEventsPerHour * defaultRate.avgEventSizeKB) / 1024;
    }
    
    // Ensure minimum values to prevent division by zero and show meaningful estimates
    totalMBPerHour = Math.max(totalMBPerHour, 0.1);
    
    return {
      podCount: estimatedPodCount,
      namespaceCount: allClusterResources.reduce((sum, c) => sum + c.namespaces.length, 0),
      nodeCount: allClusterResources.reduce((sum, c) => {
        const clusterInfo = clusters.find((cl: any) => cl.id === c.id);
        return sum + (clusterInfo?.total_nodes || 3);
      }, 0),
      gadgetCount: gadgetsToUse.length || 1, // Show at least 1 for default estimation
      eventsPerHour: Math.round(totalEventsPerHour),
      mbPerHour: Math.round(totalMBPerHour * 10) / 10, // Round to 1 decimal
      // Duration estimates for given size (guaranteed non-zero due to minimum mbPerHour)
      hoursFor100MB: Math.round(100 / totalMBPerHour),
      hoursFor500MB: Math.round(500 / totalMBPerHour),
      hoursFor1GB: Math.round(1024 / totalMBPerHour),
    };
  }, [formStateVersion, formState, defaultGadgets, allClusterResources, clusters, isMultiCluster, primaryClusterId]);
  
  // Reset per-cluster scope when clusters change
  useEffect(() => {
    if (selectedClusterIds?.length) {
      setPerClusterScope(prev => {
        const newScope: Record<number, PerClusterScope> = {};
        selectedClusterIds.forEach(id => {
          newScope[id] = prev[id] || {};
        });
        return newScope;
      });
    }
  }, [selectedClusterIds]);
  
  // Sync formState when navigating between steps or when clusters load
  // This ensures estimation metrics are accurate even before user makes changes
  useEffect(() => {
    const currentValues = form.getFieldsValue(true);
    setFormState(prev => ({
      ...prev,
      cluster_id: currentValues.cluster_id || selectedClusterId,
      cluster_ids: currentValues.cluster_ids || selectedClusterIds,
      scope_type: currentValues.scope_type || 'cluster',
      namespaces: currentValues.namespaces,
      deployments: currentValues.deployments,
      pods: currentValues.pods,
      enabled_gadgets: currentValues.enabled_gadgets,
    }));
  }, [currentStep, clusters, form, selectedClusterId, selectedClusterIds]);

  const steps = [
    {
      title: 'Scope Selection',
      icon: <AimOutlined />,
      description: 'Choose what to analyze',
    },
    {
      title: 'Gadget Modules',
      icon: <AppstoreOutlined />,
      description: 'Select event types',
    },
    {
      title: 'Time & Sizing',
      icon: <ClockCircleOutlined />,
      description: 'Timing & data limits',
    },
  ];

  const handleNext = async () => {
    try {
      await form.validateFields();
      const values = form.getFieldsValue(true);
      
      // Step 0 (Scope Selection): Validate scope-specific requirements
      if (currentStep === 0) {
        // Namespace scope requires at least one namespace selected
        if (values.scope_type === 'namespace') {
          if (!values.namespaces || values.namespaces.length === 0) {
            message.error('Please select at least one namespace');
            return;
          }
        }
        // Deployment scope requires at least one deployment selected (if enabled)
        if (values.scope_type === 'deployment') {
          if (!values.deployments || values.deployments.length === 0) {
            message.error('Please select at least one deployment');
            return;
          }
        }
        // Pod scope requires at least one pod selected (if enabled)
        if (values.scope_type === 'pod') {
          if (!values.pods || values.pods.length === 0) {
            message.error('Please select at least one pod');
            return;
          }
        }
        // Label scope requires labels to be defined (if enabled)
        if (values.scope_type === 'label') {
          if (!values.labels || values.labels.length === 0) {
            message.error('Please enter at least one label selector');
            return;
          }
        }
      }
      
      setWizardData({ ...wizardData, ...values });
      setCurrentStep(currentStep + 1);
    } catch (error) {
      message.error('Please fill in all required fields');
    }
  };

  const handlePrevious = () => {
    setCurrentStep(currentStep - 1);
  };

  const handleFinish = async () => {
    try {
      await form.validateFields();
      const finalValues = form.getFieldsValue(true);
      
      // Determine cluster configuration based on mode
      const clusterIds = isMultiCluster ? finalValues.cluster_ids : [finalValues.cluster_id];
      const primaryCluster = clusterIds[0];
      
      // Helper to parse multi-cluster values (format: "value@clusterId")
      // ALWAYS strips @clusterId suffix, even in single-cluster mode
      const parseMultiClusterValues = (values: string[] | undefined): { 
        cleanValues: string[], 
        perCluster: Record<string, string[]> 
      } => {
        if (!values) {
          return { cleanValues: [], perCluster: {} };
        }
        
        const cleanValues: string[] = [];
        const perCluster: Record<string, string[]> = {};
        
        values.forEach(val => {
          // Always strip @clusterId suffix if present
          if (val.includes('@')) {
            const atIndex = val.lastIndexOf('@');
            const cleanVal = val.substring(0, atIndex);
            const clusterId = val.substring(atIndex + 1);
            cleanValues.push(cleanVal);
            if (isMultiCluster) {
              if (!perCluster[clusterId]) {
                perCluster[clusterId] = [];
              }
              perCluster[clusterId].push(cleanVal);
            }
          } else {
            cleanValues.push(val);
          }
        });
        
        // Remove duplicates
        return { 
          cleanValues: Array.from(new Set(cleanValues)), 
          perCluster 
        };
      };
      
      // Build per-cluster scope configuration for multi-cluster mode
      let perClusterScopeConfig: Record<string, any> | undefined;
      
      // Parse scope values and build per-cluster config
      let cleanNamespaces: string[] | undefined;
      let cleanDeployments: string[] | undefined;
      let cleanPods: string[] | undefined;
      
      if (isMultiCluster && scopeMode === 'per-cluster' && Object.keys(perClusterScope).length > 0) {
        // Per-cluster mode: use perClusterScope state directly
        perClusterScopeConfig = {};
        for (const [clusterId, scope] of Object.entries(perClusterScope)) {
          if (Object.keys(scope).some(k => (scope as any)[k]?.length > 0)) {
            perClusterScopeConfig[clusterId] = scope;
          }
        }
      } else if (isMultiCluster && scopeMode === 'unified') {
        // Unified mode: parse "value@clusterId" format and build per-cluster config
        perClusterScopeConfig = {};
        
        if (finalValues.scope_type === 'namespace' && finalValues.namespaces) {
          const parsed = parseMultiClusterValues(finalValues.namespaces);
          cleanNamespaces = parsed.cleanValues;
          for (const [clusterId, nsValues] of Object.entries(parsed.perCluster)) {
            if (!perClusterScopeConfig[clusterId]) perClusterScopeConfig[clusterId] = {};
            perClusterScopeConfig[clusterId].namespaces = nsValues;
          }
        }
        
        if (finalValues.scope_type === 'deployment' && finalValues.deployments) {
          const parsed = parseMultiClusterValues(finalValues.deployments);
          cleanDeployments = parsed.cleanValues;
          for (const [clusterId, depValues] of Object.entries(parsed.perCluster)) {
            if (!perClusterScopeConfig[clusterId]) perClusterScopeConfig[clusterId] = {};
            perClusterScopeConfig[clusterId].deployments = depValues;
          }
        }
        
        if (finalValues.scope_type === 'pod' && finalValues.pods) {
          const parsed = parseMultiClusterValues(finalValues.pods);
          cleanPods = parsed.cleanValues;
          for (const [clusterId, podValues] of Object.entries(parsed.perCluster)) {
            if (!perClusterScopeConfig[clusterId]) perClusterScopeConfig[clusterId] = {};
            perClusterScopeConfig[clusterId].pods = podValues;
          }
        }
        
        // Clean empty per-cluster config
        if (Object.keys(perClusterScopeConfig).length === 0) {
          perClusterScopeConfig = undefined;
        }
      } else {
        // Single-cluster mode: still need to strip @clusterId suffix from values
        if (finalValues.scope_type === 'namespace' && finalValues.namespaces) {
          const parsed = parseMultiClusterValues(finalValues.namespaces);
          cleanNamespaces = parsed.cleanValues;
        }
        if (finalValues.scope_type === 'deployment' && finalValues.deployments) {
          const parsed = parseMultiClusterValues(finalValues.deployments);
          cleanDeployments = parsed.cleanValues;
        }
        if (finalValues.scope_type === 'pod' && finalValues.pods) {
          const parsed = parseMultiClusterValues(finalValues.pods);
          cleanPods = parsed.cleanValues;
        }
      }
      
      // Use clean values (always parsed to remove @clusterId suffix)
      const finalNamespaces = cleanNamespaces || finalValues.namespaces;
      const finalDeployments = cleanDeployments || finalValues.deployments;
      const finalPods = cleanPods || finalValues.pods;
      
      // Calculate duration in seconds if using duration mode
      let durationSeconds: number | undefined;
      if (finalValues.time_mode === 'duration' && finalValues.duration_value) {
        const multipliers: Record<string, number> = {
          'minutes': 60,
          'hours': 3600,
          'days': 86400
        };
        const unit = finalValues.duration_unit || 'hours';
        durationSeconds = finalValues.duration_value * (multipliers[unit] || 3600);
      }
      
      // Build schedule fields for recurring mode
      let scheduleExpression: string | undefined;
      let scheduleDurationSeconds: number | undefined;
      if (finalValues.time_mode === 'recurring') {
        const hour = finalValues.schedule_hour ?? 2;
        const minute = finalValues.schedule_minute ?? 0;
        if (finalValues.schedule_type === 'custom' && finalValues.custom_cron) {
          scheduleExpression = finalValues.custom_cron;
        } else if (finalValues.schedule_type === 'weekly') {
          scheduleExpression = `${minute} ${hour} * * 1-5`;
        } else {
          scheduleExpression = `${minute} ${hour} * * *`;
        }
        const rUnit = finalValues.recurring_duration_unit || 'hours';
        const rValue = finalValues.recurring_duration_value || 2;
        scheduleDurationSeconds = rValue * (rUnit === 'hours' ? 3600 : 60);
      }
      
      // Validate data retention configuration
      const retentionPolicy = finalValues.data_retention_policy || 'unlimited';
      let maxDataSizeMb: number | undefined = undefined;
      
      if (retentionPolicy !== 'unlimited') {
        // Ensure max_data_size_mb is set for size-limited policies
        maxDataSizeMb = finalValues.max_data_size_mb;
        if (!maxDataSizeMb || maxDataSizeMb < 10) {
          maxDataSizeMb = 500; // Default to 500 MB if not set
        }
      }

      // Build complete analysis request with multi-cluster support
      const analysisRequest: AnalysisCreateRequest = {
        name: finalValues.name,
        description: finalValues.description,
        scope: {
          cluster_id: primaryCluster,
          cluster_ids: isMultiCluster ? clusterIds : undefined,
          scope_type: finalValues.scope_type,
          namespaces: finalValues.scope_type === 'namespace' ? finalNamespaces : undefined,
          deployments: finalValues.scope_type === 'deployment' ? finalDeployments : undefined,
          pods: finalValues.scope_type === 'pod' ? finalPods : undefined,
          labels: finalValues.scope_type === 'label' ? finalValues.labels : undefined,
          per_cluster_scope: perClusterScopeConfig,
          exclude_namespaces: excludeEnabled && excludeNamespaces.length > 0 ? excludeNamespaces : undefined,
          exclude_pod_patterns: excludeEnabled && excludePodPatterns.length > 0 ? excludePodPatterns : undefined,
        },
        gadgets: {
          enabled_gadgets: finalValues.enabled_gadgets || [],
        },
        time_config: {
          mode: finalValues.time_mode === 'duration' ? 'timed' : finalValues.time_mode,
          start_time: finalValues.start_time?.toISOString(),
          end_time: finalValues.end_time?.toISOString(),
          duration_seconds: durationSeconds,
          duration_minutes: durationSeconds ? Math.round(durationSeconds / 60) : undefined,
          data_retention_policy: retentionPolicy,
          max_data_size_mb: maxDataSizeMb,
          schedule_expression: scheduleExpression,
          schedule_duration_seconds: scheduleDurationSeconds,
        },
        output: {
          // Default output configuration - dashboard always enabled
          enable_dashboard: true,
          enable_llm_analysis: false,
          enable_alarms: false,
          enable_webhooks: false,
        },
        // Change Detection - enabled by default
        change_detection_enabled: finalValues.change_detection_enabled !== false,
        // Change Detection Strategy - baseline, rolling_window, or run_comparison
        change_detection_strategy: finalValues.change_detection_strategy || 'baseline',
        // Change Detection Types - always track all types
        change_detection_types: ['all'],
      };

      const createdAnalysis = await createAnalysis(analysisRequest).unwrap();
      
      // For recurring mode, register the schedule with the orchestrator
      if (finalValues.time_mode === 'recurring' && scheduleExpression && scheduleDurationSeconds) {
        try {
          const maxRuns = finalValues.max_scheduled_runs || 0;
          await scheduleAnalysis({
            id: createdAnalysis.id,
            body: {
              cron_expression: scheduleExpression,
              duration_seconds: scheduleDurationSeconds,
              max_runs: maxRuns > 0 ? maxRuns : undefined,
            }
          }).unwrap();
          message.success('Recurring analysis created and scheduled!');
        } catch (schedErr) {
          console.error('Schedule registration failed:', schedErr);
          message.warning('Analysis created but scheduling failed. You can schedule it from the analysis list.');
        }
      } else {
        const successMessage = isMultiCluster 
          ? `Multi-cluster analysis created with ${clusterIds.length} clusters!` 
          : 'Analysis created successfully!';
        message.success(successMessage);
      }
      navigate('/analyses');
    } catch (error) {
      message.error('Failed to create analysis');
      console.error(error);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: // Scope Selection
        return (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <div>
              <Title level={4}>Basic Information</Title>
              <Form.Item
                name="name"
                label="Analysis Name"
                rules={[{ required: true, message: 'Please enter analysis name' }]}
              >
                <Input placeholder="e.g., Production Network Traffic Analysis" />
              </Form.Item>
              
              <Form.Item
                name="description"
                label="Description"
              >
                <TextArea rows={3} placeholder="Describe the purpose of this analysis" />
              </Form.Item>

              <Form.Item
                name="change_detection_enabled"
                label="Change Detection"
                valuePropName="checked"
                initialValue={true}
                tooltip="Track infrastructure changes (workload additions/removals, config changes) during analysis"
              >
                <Switch 
                  checkedChildren="Enabled" 
                  unCheckedChildren="Disabled"
                  defaultChecked
                />
              </Form.Item>

              {/* Change Detection Strategy - only show when enabled */}
              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) => 
                  prevValues.change_detection_enabled !== currentValues.change_detection_enabled
                }
              >
                {({ getFieldValue }) => 
                  getFieldValue('change_detection_enabled') !== false && (
                    <>
                      <Form.Item
                        name="change_detection_strategy"
                        label="Detection Strategy"
                        initialValue="baseline"
                        tooltip="How changes are detected: Baseline compares against initial state, Rolling Window compares recent periods, Run Comparison compares between analysis runs"
                      >
                        <Radio.Group>
                          <Radio.Button value="baseline">
                            <Tooltip title="Builds a baseline from initial behavior, then detects any deviations. Best for: Long-running analyses, drift detection. Auto-adapts to analysis duration.">
                              Baseline
                            </Tooltip>
                          </Radio.Button>
                          <Radio.Button value="rolling_window">
                            <Tooltip title="Continuously compares recent activity vs previous period for real-time detection. Best for: Continuous monitoring, immediate anomaly detection. Requires at least 4+ minutes to build comparison data.">
                              Rolling Window
                            </Tooltip>
                          </Radio.Button>
                          <Radio.Button value="run_comparison">
                            <Tooltip title="Compares current run against previous runs. Best for: Deployment validation, A/B testing. If no previous run exists, automatically falls back to baseline behavior.">
                              Run Comparison
                            </Tooltip>
                          </Radio.Button>
                        </Radio.Group>
                      </Form.Item>
                    </>
                  )
                }
              </Form.Item>
            </div>

            <div>
              <Title level={4}>
                <Space>
                  <ClusterOutlined />
                  Scope Configuration
                </Space>
              </Title>
              
              {clusters.length === 0 && !isClustersLoading && (
                <Alert
                  message="No Clusters Available"
                  description="Please add a cluster first from Management > Clusters before creating an analysis."
                  type="warning"
                  showIcon
                  style={{ marginBottom: 16 }}
                  action={
                    <Button size="small" type="primary" onClick={() => navigate('/management/clusters')}>
                      Add Cluster
                    </Button>
                  }
                />
              )}
              
              {/* Multi-Cluster Toggle */}
              <Form.Item 
                label={
                  <Space>
                    <span>Analysis Mode</span>
                    <Tooltip title="Multi-cluster analysis allows you to monitor multiple clusters simultaneously and compare communications across them.">
                      <InfoCircleOutlined style={{ color: '#0891b2' }} />
                    </Tooltip>
                  </Space>
                }
              >
                <Radio.Group 
                  value={isMultiCluster} 
                  onChange={(e) => {
                    setIsMultiCluster(e.target.value);
                    // Reset cluster selection when switching modes
                    if (e.target.value) {
                      form.setFieldValue('cluster_id', undefined);
                      form.setFieldValue('cluster_ids', []);
                    } else {
                      form.setFieldValue('cluster_ids', undefined);
                    }
                  }}
                >
                  <Radio.Button value={false}>
                    <Space>
                      <ClusterOutlined />
                      Single Cluster
                    </Space>
                  </Radio.Button>
                  <Radio.Button value={true}>
                    <Space>
                      <GlobalOutlined />
                      Multi-Cluster
                      <Badge count={selectedClusterIds?.length || 0} size="small" style={{ marginLeft: 4 }} />
                    </Space>
                  </Radio.Button>
                </Radio.Group>
              </Form.Item>
              
              {isMultiCluster && (
                <Alert
                  message="Multi-Cluster Analysis"
                  description={
                    <span>
                      Select multiple clusters to analyze. Events and communications from all selected clusters 
                      will be collected and displayed together. Use <strong>Ctrl+Click</strong> or <strong>Cmd+Click</strong> to 
                      select multiple clusters.
                      <br /><br />
                      <InfoCircleOutlined /> You can configure scope for each cluster separately or use unified scope 
                      across all clusters.
                    </span>
                  }
                  type="info"
                  showIcon
                  icon={<GlobalOutlined />}
                  style={{ marginBottom: 16 }}
                />
              )}
              
              {/* Multi-cluster scope mode selection */}
              {isMultiCluster && selectedClusterIds && selectedClusterIds.length > 1 && (
                <Form.Item 
                  label={
                    <Space>
                      <span>Scope Configuration Mode</span>
                      <Tooltip 
                        title={
                          <div style={{ maxWidth: 350 }}>
                            <div style={{ fontWeight: 600, marginBottom: 8 }}>Multi-Cluster Scope Configuration</div>
                            
                            <div style={{ marginBottom: 12 }}>
                              <div style={{ fontWeight: 500, color: '#4d9f7c' }}>🌐 Unified Scope</div>
                              <div style={{ fontSize: 12, marginTop: 4 }}>
                                Monitor the <strong>same namespaces</strong> across all clusters. 
                                Ideal for comparing the same application's behavior in different environments (Prod vs Stage).
                              </div>
                              <div style={{ fontSize: 11, color: '#aaa', marginTop: 4, fontStyle: 'italic' }}>
                                Example: Monitor "payments" namespace in both clusters
                              </div>
                            </div>
                            
                            <div>
                              <div style={{ fontWeight: 500, color: '#0891b2' }}>🎯 Per-Cluster Scope</div>
                              <div style={{ fontSize: 12, marginTop: 4 }}>
                                Select <strong>different namespaces</strong> for each cluster individually. 
                                Use when clusters have different naming conventions or you want to monitor different applications.
                              </div>
                              <div style={{ fontSize: 11, color: '#aaa', marginTop: 4, fontStyle: 'italic' }}>
                                Example: Monitor "payments" in Prod, "payments-test" in Stage
                              </div>
                            </div>
                          </div>
                        }
                        overlayStyle={{ maxWidth: 400 }}
                      >
                        <InfoCircleOutlined style={{ color: '#0891b2', cursor: 'help' }} />
                      </Tooltip>
                    </Space>
                  }
                >
                  <Radio.Group 
                    value={scopeMode} 
                    onChange={(e) => setScopeMode(e.target.value)}
                    optionType="button"
                    buttonStyle="solid"
                  >
                    <Tooltip title="Same namespaces in all clusters (for Prod vs Stage comparison)">
                      <Radio.Button value="unified">
                        <Space>
                          <GlobalOutlined />
                          Unified Scope
                        </Space>
                      </Radio.Button>
                    </Tooltip>
                    <Tooltip title="Different namespaces per cluster (for different naming or applications)">
                      <Radio.Button value="per-cluster">
                        <Space>
                          <ClusterOutlined />
                          Per-Cluster Scope
                        </Space>
                      </Radio.Button>
                    </Tooltip>
                  </Radio.Group>
                </Form.Item>
              )}
              
              {/* Single Cluster Selection */}
              {!isMultiCluster && (
                <Form.Item
                  name="cluster_id"
                  label="Target Cluster"
                  rules={[{ required: !isMultiCluster, message: 'Please select a cluster' }]}
                >
                  <Select 
                    placeholder="Select a cluster" 
                    showSearch
                    loading={isClustersLoading}
                    optionFilterProp="children"
                  >
                    {clusters.map((cluster: any) => (
                      <Option key={cluster.id} value={cluster.id}>
                        <Space>
                          <span>{cluster.name}</span>
                          <Tag color={cluster.environment === 'production' ? 'red' : cluster.environment === 'staging' ? 'orange' : 'blue'}>
                            {cluster.environment}
                          </Tag>
                          <Tag color={cluster.gadget_health_status === 'healthy' ? 'green' : 'orange'}>
                            {cluster.provider?.toUpperCase()}
                          </Tag>
                        </Space>
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
              
              {/* Multi-Cluster Selection */}
              {isMultiCluster && (
                <Form.Item
                  name="cluster_ids"
                  label={
                    <Space>
                      <span>Target Clusters</span>
                      {selectedClusterIds?.length ? (
                        <Tag color="blue">{selectedClusterIds.length} selected</Tag>
                      ) : null}
                    </Space>
                  }
                  rules={[{ 
                    required: isMultiCluster, 
                    message: 'Please select at least one cluster',
                    validator: async (_, value) => {
                      if (isMultiCluster && (!value || value.length === 0)) {
                        throw new Error('Please select at least one cluster');
                      }
                    }
                  }]}
                  extra={
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      <InfoCircleOutlined /> Hold Ctrl/Cmd and click to select multiple clusters
                    </Text>
                  }
                >
                  <Select 
                    mode="multiple"
                    placeholder="Select clusters (Ctrl+Click for multiple)" 
                    showSearch
                    loading={isClustersLoading}
                    optionFilterProp="children"
                    maxTagCount={5}
                    style={{ width: '100%' }}
                  >
                    {clusters.map((cluster: any) => (
                      <Option key={cluster.id} value={cluster.id}>
                        <Space>
                          <span>{cluster.name}</span>
                          <Tag color={cluster.environment === 'production' ? 'red' : cluster.environment === 'staging' ? 'orange' : 'blue'} style={{ fontSize: 10 }}>
                            {cluster.environment}
                          </Tag>
                          <Tag color={cluster.gadget_health_status === 'healthy' ? 'green' : 'orange'} style={{ fontSize: 10 }}>
                            {cluster.provider?.toUpperCase()}
                          </Tag>
                          {cluster.gadget_health_status !== 'healthy' && (
                            <Tooltip title="Inspector Gadget may not be healthy on this cluster">
                              <Tag color="warning" style={{ fontSize: 10 }}>⚠️</Tag>
                            </Tooltip>
                          )}
                        </Space>
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
              )}
              
              <Divider />

              <Form.Item
                name="scope_type"
                label="Scope Type"
                rules={[{ required: true }]}
                initialValue="cluster"
              >
                <Radio.Group>
                  <Radio.Button value="cluster">Entire Cluster</Radio.Button>
                  <Radio.Button value="namespace">Namespace(s)</Radio.Button>
                  <Radio.Button value="deployment" disabled title="Coming soon">Deployment(s)</Radio.Button>
                  <Radio.Button value="pod" disabled title="Coming soon">Pod(s)</Radio.Button>
                  <Radio.Button value="label" disabled title="Coming soon">Label Selector</Radio.Button>
                </Radio.Group>
              </Form.Item>

              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) => 
                  prevValues.scope_type !== currentValues.scope_type || 
                  prevValues.cluster_id !== currentValues.cluster_id ||
                  prevValues.cluster_ids !== currentValues.cluster_ids ||
                  prevValues.namespaces !== currentValues.namespaces
                }
              >
                {({ getFieldValue }) => {
                  const currentScopeType = getFieldValue('scope_type');
                  const clusterId = getFieldValue('cluster_id');
                  const clusterIdsValue = getFieldValue('cluster_ids') as number[] | undefined;
                  const hasCluster = isMultiCluster ? (clusterIdsValue && clusterIdsValue.length > 0) : !!clusterId;
                  
                  // Calculate total resources across all clusters
                  const totalNamespaces = allClusterResources.reduce((sum, c) => sum + c.namespaces.length, 0);
                  const totalDeployments = allClusterResources.reduce((sum, c) => sum + c.deployments.length, 0);
                  const totalPods = allClusterResources.reduce((sum, c) => sum + c.pods.length, 0);
                  
                  // Render cluster-grouped namespace selector for multi-cluster unified mode
                  const renderMultiClusterNamespaceSelector = () => (
                    <Form.Item 
                      name="namespaces" 
                      label={
                        <Space>
                          <DatabaseOutlined />
                          <span>Namespaces</span>
                          {isMultiCluster && selectedClusterIds && selectedClusterIds.length > 1 && (
                            <Tag color="blue">{allClusterResources.length} clusters</Tag>
                          )}
                        </Space>
                      }
                      extra={totalNamespaces > 0 ? (
                        <Space>
                          <span>{totalNamespaces} namespaces across {allClusterResources.length} cluster(s)</span>
                          {isAnyClusterLoading && <Spin size="small" />}
                        </Space>
                      ) : undefined}
                    >
                      <Select 
                        mode="multiple" 
                        placeholder="Select namespaces (grouped by cluster)"
                        loading={isAnyClusterLoading}
                        disabled={!hasCluster}
                        showSearch
                        optionFilterProp="label"
                        maxTagCount={5}
                        style={{ width: '100%' }}
                        tagRender={(props) => {
                          const { label, closable, onClose } = props;
                          // Extract cluster info from value for coloring
                          const valueStr = String(props.value);
                          const clusterId = valueStr.includes('@') ? parseInt(valueStr.split('@')[1]) : undefined;
                          const clusterInfo = clusterId ? getClusterInfo(clusterId) : undefined;
                          return (
                            <Tag
                              closable={closable}
                              onClose={onClose}
                              style={{ 
                                marginRight: 3,
                                borderLeft: clusterInfo ? `3px solid ${clusterInfo.color}` : undefined
                              }}
                            >
                              {label}
                            </Tag>
                          );
                        }}
                      >
                        {allClusterResources.map((cluster) => (
                          <Select.OptGroup 
                            key={cluster.id} 
                            label={
                              <Space>
                                <span style={{ 
                                  display: 'inline-block', 
                                  width: 10, 
                                  height: 10, 
                                  borderRadius: '50%', 
                                  backgroundColor: cluster.color,
                                  marginRight: 4
                                }} />
                                <strong>{cluster.name}</strong>
                                <Tag color={cluster.environment === 'production' ? 'red' : 'blue'} style={{ fontSize: 10 }}>
                                  {cluster.environment || 'default'}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: 11 }}>
                                  ({cluster.namespaces.length} namespaces)
                                </Text>
                              </Space>
                            }
                          >
                            {cluster.isLoading ? (
                              <Option key={`loading-${cluster.id}`} value="" disabled>
                                <Spin size="small" /> Loading namespaces...
                              </Option>
                            ) : cluster.namespaces.length === 0 ? (
                              <Option key={`empty-${cluster.id}`} value="" disabled>
                                No namespaces found
                              </Option>
                            ) : (
                              cluster.namespaces.map((ns: any) => (
                                <Option 
                                  key={`${ns.name}@${cluster.id}`} 
                                  value={`${ns.name}@${cluster.id}`}
                                  label={`${ns.name} (${cluster.name})`}
                                >
                                  <Space>
                                    <span style={{ 
                                      display: 'inline-block', 
                                      width: 6, 
                                      height: 6, 
                                      borderRadius: '50%', 
                                      backgroundColor: cluster.color 
                                    }} />
                                    <span>{ns.name}</span>
                                    {ns.status && (
                                      <Tag color={ns.status === 'Active' ? 'green' : 'orange'} style={{ fontSize: 10 }}>
                                        {ns.status}
                                      </Tag>
                                    )}
                                  </Space>
                                </Option>
                              ))
                            )}
                          </Select.OptGroup>
                        ))}
                      </Select>
                    </Form.Item>
                  );
                  
                  // Render cluster-grouped deployment selector
                  const renderMultiClusterDeploymentSelector = () => (
                    <>
                      <Form.Item 
                        name="deployments" 
                        label={
                          <Space>
                            <AppstoreAddOutlined />
                            <span>Deployments</span>
                            {isMultiCluster && selectedClusterIds && selectedClusterIds.length > 1 && (
                              <Tag color="purple">{allClusterResources.length} clusters</Tag>
                            )}
                          </Space>
                        }
                        extra={totalDeployments > 0 ? (
                          <Space>
                            <span>{totalDeployments} deployments across {allClusterResources.length} cluster(s)</span>
                            {isAnyClusterLoading && <Spin size="small" />}
                          </Space>
                        ) : undefined}
                      >
                        <Select 
                          mode="multiple" 
                          placeholder="Select deployments (grouped by cluster)"
                          loading={isAnyClusterLoading}
                          disabled={!hasCluster}
                          showSearch
                          optionFilterProp="label"
                          maxTagCount={5}
                          style={{ width: '100%' }}
                          tagRender={(props) => {
                            const { label, closable, onClose } = props;
                            const valueStr = String(props.value);
                            const clusterId = valueStr.includes('@') ? parseInt(valueStr.split('@').pop() || '0') : undefined;
                            const clusterInfo = clusterId ? getClusterInfo(clusterId) : undefined;
                            return (
                              <Tag
                                closable={closable}
                                onClose={onClose}
                                style={{ 
                                  marginRight: 3,
                                  borderLeft: clusterInfo ? `3px solid ${clusterInfo.color}` : undefined
                                }}
                              >
                                {label}
                              </Tag>
                            );
                          }}
                        >
                          {allClusterResources.map((cluster) => (
                            <Select.OptGroup 
                              key={cluster.id} 
                              label={
                                <Space>
                                  <span style={{ 
                                    display: 'inline-block', 
                                    width: 10, 
                                    height: 10, 
                                    borderRadius: '50%', 
                                    backgroundColor: cluster.color,
                                    marginRight: 4
                                  }} />
                                  <strong>{cluster.name}</strong>
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    ({cluster.deployments.length} deployments)
                                  </Text>
                                </Space>
                              }
                            >
                              {cluster.isLoading ? (
                                <Option key={`loading-${cluster.id}`} value="" disabled>
                                  <Spin size="small" /> Loading deployments...
                                </Option>
                              ) : cluster.deployments.length === 0 ? (
                                <Option key={`empty-${cluster.id}`} value="" disabled>
                                  No deployments found
                                </Option>
                              ) : (
                                cluster.deployments.map((dep: any) => (
                                  <Option 
                                    key={`${dep.namespace}/${dep.name}@${cluster.id}`} 
                                    value={`${dep.namespace}/${dep.name}@${cluster.id}`}
                                    label={`${dep.name} (${cluster.name})`}
                                  >
                                    <Space>
                                      <span style={{ 
                                        display: 'inline-block', 
                                        width: 6, 
                                        height: 6, 
                                        borderRadius: '50%', 
                                        backgroundColor: cluster.color 
                                      }} />
                                      <span>{dep.name}</span>
                                      <Tag color="blue" style={{ fontSize: 10 }}>{dep.namespace}</Tag>
                                      <Text type="secondary" style={{ fontSize: 10 }}>
                                        {dep.available_replicas || 0}/{dep.replicas || 0}
                                      </Text>
                                    </Space>
                                  </Option>
                                ))
                              )}
                            </Select.OptGroup>
                          ))}
                        </Select>
                      </Form.Item>
                    </>
                  );
                  
                  // Render cluster-grouped pod selector
                  const renderMultiClusterPodSelector = () => (
                    <>
                      <Form.Item 
                        name="pods" 
                        label={
                          <Space>
                            <ContainerOutlined />
                            <span>Pods</span>
                            {isMultiCluster && selectedClusterIds && selectedClusterIds.length > 1 && (
                              <Tag color="cyan">{allClusterResources.length} clusters</Tag>
                            )}
                          </Space>
                        }
                        extra={totalPods > 0 ? (
                          <Space>
                            <span>{totalPods} pods across {allClusterResources.length} cluster(s)</span>
                            {isAnyClusterLoading && <Spin size="small" />}
                          </Space>
                        ) : undefined}
                      >
                        <Select 
                          mode="multiple" 
                          placeholder="Select pods (grouped by cluster)"
                          loading={isAnyClusterLoading}
                          disabled={!hasCluster}
                          showSearch
                          optionFilterProp="label"
                          maxTagCount={5}
                          style={{ width: '100%' }}
                          virtual={totalPods > 100}
                          tagRender={(props) => {
                            const { label, closable, onClose } = props;
                            const valueStr = String(props.value);
                            const clusterId = valueStr.includes('@') ? parseInt(valueStr.split('@').pop() || '0') : undefined;
                            const clusterInfo = clusterId ? getClusterInfo(clusterId) : undefined;
                            return (
                              <Tag
                                closable={closable}
                                onClose={onClose}
                                style={{ 
                                  marginRight: 3,
                                  borderLeft: clusterInfo ? `3px solid ${clusterInfo.color}` : undefined
                                }}
                              >
                                {label}
                              </Tag>
                            );
                          }}
                        >
                          {allClusterResources.map((cluster) => (
                            <Select.OptGroup 
                              key={cluster.id} 
                              label={
                                <Space>
                                  <span style={{ 
                                    display: 'inline-block', 
                                    width: 10, 
                                    height: 10, 
                                    borderRadius: '50%', 
                                    backgroundColor: cluster.color,
                                    marginRight: 4
                                  }} />
                                  <strong>{cluster.name}</strong>
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    ({cluster.pods.length} pods)
                                  </Text>
                                </Space>
                              }
                            >
                              {cluster.isLoading ? (
                                <Option key={`loading-${cluster.id}`} value="" disabled>
                                  <Spin size="small" /> Loading pods...
                                </Option>
                              ) : cluster.pods.length === 0 ? (
                                <Option key={`empty-${cluster.id}`} value="" disabled>
                                  No pods found
                                </Option>
                              ) : (
                                cluster.pods.map((pod: any) => (
                                  <Option 
                                    key={`${pod.namespace}/${pod.name}@${cluster.id}`} 
                                    value={`${pod.namespace}/${pod.name}@${cluster.id}`}
                                    label={`${pod.name} (${cluster.name})`}
                                  >
                                    <Space>
                                      <span style={{ 
                                        display: 'inline-block', 
                                        width: 6, 
                                        height: 6, 
                                        borderRadius: '50%', 
                                        backgroundColor: cluster.color 
                                      }} />
                                      <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                        {pod.name}
                                      </span>
                                      <Tag color="blue" style={{ fontSize: 10 }}>{pod.namespace}</Tag>
                                      <Tag color={pod.status === 'Running' ? 'green' : 'orange'} style={{ fontSize: 10 }}>
                                        {pod.status}
                                      </Tag>
                                    </Space>
                                  </Option>
                                ))
                              )}
                            </Select.OptGroup>
                          ))}
                        </Select>
                      </Form.Item>
                    </>
                  );
                  
                  // Render per-cluster scope configuration with tabs
                  const renderPerClusterScopeConfig = () => {
                    if (!isMultiCluster || scopeMode !== 'per-cluster' || !selectedClusterIds?.length) {
                      return null;
                    }
                    
                    return (
                      <Card 
                        size="small" 
                        title={
                          <Space>
                            <ClusterOutlined />
                            <span>Per-Cluster Scope Configuration</span>
                          </Space>
                        }
                        style={{ marginTop: 16 }}
                      >
                        <Tabs
                          type="card"
                          items={allClusterResources.map((cluster, index) => ({
                            key: String(cluster.id),
                            label: (
                              <Space>
                                <span style={{ 
                                  display: 'inline-block', 
                                  width: 8, 
                                  height: 8, 
                                  borderRadius: '50%', 
                                  backgroundColor: cluster.color 
                                }} />
                                <span>{cluster.name}</span>
                                {perClusterScope[cluster.id] && 
                                  Object.values(perClusterScope[cluster.id]).some(v => (v as any)?.length > 0) && (
                                  <Badge status="success" />
                                )}
                              </Space>
                            ),
                            children: (
                              <div style={{ padding: '8px 0' }}>
                                {cluster.isLoading ? (
                                  <div style={{ textAlign: 'center', padding: 20 }}>
                                    <Spin tip={`Loading resources from ${cluster.name}...`} />
                                  </div>
                                ) : (
                                  <Space direction="vertical" style={{ width: '100%' }}>
                                    {/* Per-cluster namespace selection */}
                                    {currentScopeType === 'namespace' && (
                                      <div>
                                        <Text strong style={{ marginBottom: 8, display: 'block' }}>
                                          Namespaces in {cluster.name}
                                        </Text>
                                        <Select
                                          mode="multiple"
                                          placeholder={`Select namespaces from ${cluster.name}`}
                                          style={{ width: '100%' }}
                                          value={perClusterScope[cluster.id]?.namespaces || []}
                                          onChange={(values) => {
                                            setPerClusterScope(prev => ({
                                              ...prev,
                                              [cluster.id]: {
                                                ...prev[cluster.id],
                                                namespaces: values
                                              }
                                            }));
                                          }}
                                          maxTagCount={3}
                                        >
                                          {cluster.namespaces.map((ns: any) => (
                                            <Option key={ns.name} value={ns.name}>
                                              <Space>
                                                <span>{ns.name}</span>
                                                {ns.status && (
                                                  <Tag color={ns.status === 'Active' ? 'green' : 'orange'} style={{ fontSize: 10 }}>
                                                    {ns.status}
                                                  </Tag>
                                                )}
                                              </Space>
                                            </Option>
                                          ))}
                                        </Select>
                                        <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                                          {cluster.namespaces.length} namespaces available
                                        </Text>
                                      </div>
                                    )}
                                    
                                    {/* Per-cluster deployment selection */}
                                    {currentScopeType === 'deployment' && (
                                      <div>
                                        <Text strong style={{ marginBottom: 8, display: 'block' }}>
                                          Deployments in {cluster.name}
                                        </Text>
                                        <Select
                                          mode="multiple"
                                          placeholder={`Select deployments from ${cluster.name}`}
                                          style={{ width: '100%' }}
                                          value={perClusterScope[cluster.id]?.deployments || []}
                                          onChange={(values) => {
                                            setPerClusterScope(prev => ({
                                              ...prev,
                                              [cluster.id]: {
                                                ...prev[cluster.id],
                                                deployments: values
                                              }
                                            }));
                                          }}
                                          maxTagCount={3}
                                        >
                                          {cluster.deployments.map((dep: any) => (
                                            <Option 
                                              key={`${dep.namespace}/${dep.name}`} 
                                              value={`${dep.namespace}/${dep.name}`}
                                            >
                                              <Space>
                                                <span>{dep.name}</span>
                                                <Tag color="blue" style={{ fontSize: 10 }}>{dep.namespace}</Tag>
                                              </Space>
                                            </Option>
                                          ))}
                                        </Select>
                                        <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                                          {cluster.deployments.length} deployments available
                                        </Text>
                                      </div>
                                    )}
                                    
                                    {/* Per-cluster pod selection */}
                                    {currentScopeType === 'pod' && (
                                      <div>
                                        <Text strong style={{ marginBottom: 8, display: 'block' }}>
                                          Pods in {cluster.name}
                                        </Text>
                                        <Select
                                          mode="multiple"
                                          placeholder={`Select pods from ${cluster.name}`}
                                          style={{ width: '100%' }}
                                          value={perClusterScope[cluster.id]?.pods || []}
                                          onChange={(values) => {
                                            setPerClusterScope(prev => ({
                                              ...prev,
                                              [cluster.id]: {
                                                ...prev[cluster.id],
                                                pods: values
                                              }
                                            }));
                                          }}
                                          maxTagCount={3}
                                          virtual={cluster.pods.length > 50}
                                        >
                                          {cluster.pods.map((pod: any) => (
                                            <Option 
                                              key={`${pod.namespace}/${pod.name}`} 
                                              value={`${pod.namespace}/${pod.name}`}
                                            >
                                              <Space>
                                                <span>{pod.name}</span>
                                                <Tag color="blue" style={{ fontSize: 10 }}>{pod.namespace}</Tag>
                                                <Tag color={pod.status === 'Running' ? 'green' : 'orange'} style={{ fontSize: 10 }}>
                                                  {pod.status}
                                                </Tag>
                                              </Space>
                                            </Option>
                                          ))}
                                        </Select>
                                        <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                                          {cluster.pods.length} pods available
                                        </Text>
                                      </div>
                                    )}
                                    
                                    {/* Per-cluster label selection */}
                                    {currentScopeType === 'label' && (
                                      <div>
                                        <Text strong style={{ marginBottom: 8, display: 'block' }}>
                                          Labels in {cluster.name}
                                        </Text>
                                        <Select
                                          mode="tags"
                                          placeholder={`Select or enter labels for ${cluster.name}`}
                                          style={{ width: '100%' }}
                                          value={perClusterScope[cluster.id]?.labels || []}
                                          onChange={(values) => {
                                            setPerClusterScope(prev => ({
                                              ...prev,
                                              [cluster.id]: {
                                                ...prev[cluster.id],
                                                labels: values
                                              }
                                            }));
                                          }}
                                          tokenSeparators={[',']}
                                        >
                                          {cluster.labels.map((label: string) => (
                                            <Option key={label} value={label}>{label}</Option>
                                          ))}
                                        </Select>
                                        <Text type="secondary" style={{ fontSize: 11, marginTop: 4, display: 'block' }}>
                                          {cluster.labels.length} label combinations available
                                        </Text>
                                      </div>
                                    )}
                                    
                                    {currentScopeType === 'cluster' && (
                                      <Alert
                                        message="Cluster-wide Scope"
                                        description={`All workloads in ${cluster.name} will be analyzed.`}
                                        type="info"
                                        showIcon
                                      />
                                    )}
                                  </Space>
                                )}
                              </div>
                            ),
                          }))}
                        />
                      </Card>
                    );
                  };
                  
                  // Main scope rendering logic
                  if (currentScopeType === 'namespace') {
                    if (isMultiCluster && scopeMode === 'per-cluster' && selectedClusterIds?.length) {
                      return renderPerClusterScopeConfig();
                    }
                    return renderMultiClusterNamespaceSelector();
                  }
                  
                  if (currentScopeType === 'deployment') {
                    if (isMultiCluster && scopeMode === 'per-cluster' && selectedClusterIds?.length) {
                      return renderPerClusterScopeConfig();
                    }
                    return renderMultiClusterDeploymentSelector();
                  }
                  
                  if (currentScopeType === 'pod') {
                    if (isMultiCluster && scopeMode === 'per-cluster' && selectedClusterIds?.length) {
                      return renderPerClusterScopeConfig();
                    }
                    return renderMultiClusterPodSelector();
                  }
                  
                  if (currentScopeType === 'label') {
                    if (isMultiCluster && scopeMode === 'per-cluster' && selectedClusterIds?.length) {
                      return renderPerClusterScopeConfig();
                    }
                    // Unified label selector
                    const allLabels = allClusterResources.flatMap(c => c.labels);
                    const uniqueLabels = Array.from(new Set(allLabels));
                    return (
                      <>
                        <Form.Item 
                          name="labels" 
                          label="Label Selector"
                          extra={
                            uniqueLabels.length > 0 
                              ? `Available labels: ${uniqueLabels.slice(0, 5).join(', ')}${uniqueLabels.length > 5 ? '...' : ''}` 
                              : 'Enter labels in format: key=value'
                          }
                        >
                          <Select 
                            mode="tags" 
                            placeholder="Select or enter labels (e.g., app=nginx)"
                            loading={isAnyClusterLoading}
                            disabled={!hasCluster}
                            tokenSeparators={[',']}
                          >
                            {uniqueLabels.map((label: string) => (
                              <Option key={label} value={label}>{label}</Option>
                            ))}
                          </Select>
                        </Form.Item>
                        <Alert
                          message="Label Selector Syntax"
                          description={
                            <div>
                              <p>Use Kubernetes label selector syntax:</p>
                              <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
                                <li><code>app=nginx</code> - exact match</li>
                                <li><code>env in (prod, staging)</code> - set membership</li>
                                <li><code>tier!=frontend</code> - not equal</li>
                              </ul>
                            </div>
                          }
                          type="info"
                          showIcon
                          style={{ marginTop: 8 }}
                        />
                      </>
                    );
                  }
                  
                  if (currentScopeType === 'cluster') {
                    const clusterMessage = isMultiCluster && selectedClusterIds?.length 
                      ? `This analysis will monitor all workloads across all namespaces in ${selectedClusterIds.length} selected clusters.`
                      : 'This analysis will monitor all workloads across all namespaces in the selected cluster.';
                    
                    return (
                      <>
                        <Alert
                          message="Cluster-wide Analysis"
                          description={clusterMessage}
                          type="info"
                          showIcon
                        />
                        {isMultiCluster && selectedClusterIds && selectedClusterIds.length > 1 && (
                          <div style={{ marginTop: 16 }}>
                            <Text strong>Selected Clusters:</Text>
                            <Row gutter={[8, 8]} style={{ marginTop: 8 }}>
                              {allClusterResources.map((cluster) => (
                                <Col key={cluster.id}>
                                  <Card size="small" style={{ borderLeft: `4px solid ${cluster.color}` }}>
                                    <Space>
                                      <ClusterOutlined />
                                      <span>{cluster.name}</span>
                                      <Tag color={cluster.environment === 'production' ? 'red' : 'blue'}>
                                        {cluster.environment || 'default'}
                                      </Tag>
                                      <Text type="secondary" style={{ fontSize: 11 }}>
                                        {cluster.namespaces.length} ns
                                      </Text>
                                    </Space>
                                  </Card>
                                </Col>
                              ))}
                            </Row>
                          </div>
                        )}
                      </>
                    );
                  }
                  
                  return null;
                }}
              </Form.Item>
            </div>

            {/* System Noise Exclusion Filter */}
            <div>
              <Title level={4}>
                <Space>
                  <StopOutlined />
                  System Noise Filter
                </Space>
              </Title>
              <Alert
                message="Reduces noise from system/infrastructure pods"
                description="Only events where BOTH source and destination match exclusion patterns are filtered. Traffic between your application and system components (ingress, DNS, monitoring) is always preserved."
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
              <div style={{ marginBottom: 16 }}>
                <Space align="center">
                  <Switch
                    checked={excludeEnabled}
                    onChange={(checked) => setExcludeEnabled(checked)}
                    checkedChildren="Enabled"
                    unCheckedChildren="Disabled"
                  />
                  <Text strong>Filter system noise</Text>
                  {excludeEnabled && (
                    <Text type="secondary">
                      ({excludeNamespaces.length} namespace patterns, {excludePodPatterns.length} pod patterns)
                    </Text>
                  )}
                </Space>
              </div>

              {excludeEnabled && (
                <>
                  <div style={{ marginBottom: 12 }}>
                    <Text strong style={{ display: 'block', marginBottom: 8 }}>Quick Presets:</Text>
                    <Space wrap>
                      {EXCLUSION_PRESETS.map((preset) => {
                        const allNsIncluded = preset.namespaces.every(ns => excludeNamespaces.includes(ns));
                        const allPodsIncluded = preset.pods.every(p => excludePodPatterns.includes(p));
                        const isActive = allNsIncluded && allPodsIncluded && (preset.namespaces.length > 0 || preset.pods.length > 0);
                        return (
                          <Tag
                            key={preset.label}
                            color={isActive ? 'blue' : undefined}
                            style={{ cursor: 'pointer', userSelect: 'none' }}
                            onClick={() => {
                              if (isActive) {
                                setExcludeNamespaces(prev => prev.filter(ns => !preset.namespaces.includes(ns)));
                                setExcludePodPatterns(prev => prev.filter(p => !preset.pods.includes(p)));
                              } else {
                                setExcludeNamespaces(prev => Array.from(new Set([...prev, ...preset.namespaces])));
                                setExcludePodPatterns(prev => Array.from(new Set([...prev, ...preset.pods])));
                              }
                            }}
                          >
                            {isActive ? <CheckCircleOutlined /> : null} {preset.label}
                          </Tag>
                        );
                      })}
                    </Space>
                  </div>

                  <Row gutter={16}>
                    <Col span={12}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>Excluded Namespace Patterns</Text>
                      <Select
                        mode="tags"
                        style={{ width: '100%' }}
                        placeholder="e.g. openshift-*, kube-system"
                        value={excludeNamespaces}
                        onChange={(values) => setExcludeNamespaces(values)}
                        tokenSeparators={[',']}
                        maxTagCount={10}
                      />
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Supports glob patterns: openshift-* matches openshift-monitoring, openshift-ingress, etc.
                      </Text>
                    </Col>
                    <Col span={12}>
                      <Text strong style={{ display: 'block', marginBottom: 8 }}>Excluded Pod Patterns</Text>
                      <Select
                        mode="tags"
                        style={{ width: '100%' }}
                        placeholder="e.g. calico-node-*, kube-proxy-*"
                        value={excludePodPatterns}
                        onChange={(values) => setExcludePodPatterns(values)}
                        tokenSeparators={[',']}
                        maxTagCount={10}
                      />
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Supports glob patterns: calico-node-* matches calico-node-abc123, etc.
                      </Text>
                    </Col>
                  </Row>

                  <div style={{ marginTop: 12 }}>
                    <Space>
                      <Button
                        size="small"
                        onClick={() => {
                          setExcludeNamespaces([...DEFAULT_EXCLUDE_NAMESPACES]);
                          setExcludePodPatterns([...DEFAULT_EXCLUDE_POD_PATTERNS]);
                        }}
                      >
                        Reset to Defaults
                      </Button>
                      <Button
                        size="small"
                        danger
                        onClick={() => {
                          setExcludeNamespaces([]);
                          setExcludePodPatterns([]);
                        }}
                      >
                        Clear All
                      </Button>
                    </Space>
                  </div>
                </>
              )}
            </div>
          </Space>
        );

      case 1: // Gadget Modules (Event Types)
        return (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <div>
              <Title level={4}>Select Inspector Gadget Event Types</Title>
              <Paragraph type="secondary">
                Choose which eBPF event types to collect from Inspector Gadget
              </Paragraph>
            </div>

            {isEventTypesLoading ? (
              <div style={{ textAlign: 'center', padding: '40px' }}>
                <Spin size="large" tip="Loading event types..." />
              </div>
            ) : eventTypes.length === 0 ? (
              <Alert
                message="No Event Types Available"
                description="Event types could not be loaded. Please check your backend connection."
                type="error"
                showIcon
              />
            ) : (
              <Form.Item
                name="enabled_gadgets"
                rules={[{ required: true, message: 'Select at least one event type' }]}
                initialValue={eventTypes
                  .filter((et: any) => et.status === 'available')
                  .map((et: any) => et.id)}
              >
                <Checkbox.Group style={{ width: '100%' }}>
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    {eventTypes
                      .filter((et: any) => et.status === 'available')
                      .map((eventType: any) => (
                        <Card 
                          key={eventType.id} 
                          size="small"
                          style={{ 
                            borderColor: eventType.performance_impact === 'low' ? '#4d9f7c' : undefined,
                            borderWidth: eventType.performance_impact === 'low' ? 2 : 1
                          }}
                        >
                          <Checkbox value={eventType.id}>
                            <Space direction="vertical" size={0}>
                              <Space>
                                <strong>{eventType.display_name}</strong>
                                {eventType.performance_impact === 'low' && (
                                  <Tag color="blue" style={{ fontSize: '11px' }}>Recommended</Tag>
                                )}
                                <Tag color={
                                  eventType.performance_impact === 'low' ? 'green' : 
                                  eventType.performance_impact === 'medium' ? 'orange' : 'red'
                                } style={{ fontSize: '11px' }}>
                                  {eventType.performance_impact.toUpperCase()} Impact
                                </Tag>
                              </Space>
                              <Text type="secondary" style={{ fontSize: '13px' }}>
                                {eventType.description}
                              </Text>
                              <Text type="secondary" style={{ fontSize: '11px' }}>
                                Gadget: <code>{eventType.gadget_name}</code> | Volume: {eventType.data_volume}
                              </Text>
                            </Space>
                          </Checkbox>
                        </Card>
                      ))}
                  </Space>
                </Checkbox.Group>
              </Form.Item>
            )}
          </Space>
        );

      case 2: // Time & Sizing
        return (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* Section 1: Execution Mode */}
            <Card 
              size="small" 
              title={
                <Space>
                  <ClockCircleOutlined style={{ color: '#0891b2' }} />
                  <span>Execution Mode</span>
                </Space>
              }
              style={{ borderColor: '#0891b220' }}
            >
              <Form.Item
                name="time_mode"
                rules={[{ required: true }]}
                initialValue="continuous"
                style={{ marginBottom: 16 }}
              >
                <Radio.Group style={{ width: '100%' }}>
                  <Row gutter={[16, 16]}>
                    <Col xs={24} sm={6}>
                      <Card 
                        size="small" 
                        hoverable
                        style={{ 
                          borderColor: form.getFieldValue('time_mode') === 'continuous' ? '#4d9f7c' : undefined,
                          backgroundColor: form.getFieldValue('time_mode') === 'continuous' ? '#f6ffed' : undefined
                        }}
                        onClick={() => form.setFieldValue('time_mode', 'continuous')}
                      >
                        <Radio value="continuous">
                          <Space direction="vertical" size={0}>
                            <Space>
                              <SyncOutlined spin={false} style={{ color: '#4d9f7c' }} />
                              <strong>Continuous</strong>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              Auto-stop after {defaultContinuousDuration} min
                            </Text>
                          </Space>
                        </Radio>
                      </Card>
                    </Col>
                    <Col xs={24} sm={6}>
                      <Card 
                        size="small" 
                        hoverable
                        style={{ 
                          borderColor: form.getFieldValue('time_mode') === 'duration' ? '#0891b2' : undefined,
                          backgroundColor: form.getFieldValue('time_mode') === 'duration' ? '#e6f7ff' : undefined
                        }}
                        onClick={() => form.setFieldValue('time_mode', 'duration')}
                      >
                        <Radio value="duration">
                          <Space direction="vertical" size={0}>
                            <Space>
                              <FieldTimeOutlined style={{ color: '#0891b2' }} />
                              <strong>Fixed Duration</strong>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              Run for specific time period
                            </Text>
                          </Space>
                        </Radio>
                      </Card>
                    </Col>
                    <Col xs={24} sm={6}>
                      <Card 
                        size="small" 
                        hoverable
                        style={{ 
                          borderColor: form.getFieldValue('time_mode') === 'time_range' ? '#7c8eb5' : undefined,
                          backgroundColor: form.getFieldValue('time_mode') === 'time_range' ? '#f9f0ff' : undefined
                        }}
                        onClick={() => form.setFieldValue('time_mode', 'time_range')}
                      >
                        <Radio value="time_range">
                          <Space direction="vertical" size={0}>
                            <Space>
                              <ClockCircleOutlined style={{ color: '#7c8eb5' }} />
                              <strong>Scheduled</strong>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              Run between specific dates
                            </Text>
                          </Space>
                        </Radio>
                      </Card>
                    </Col>
                    <Col xs={24} sm={6}>
                      <Card 
                        size="small" 
                        hoverable
                        style={{ 
                          borderColor: form.getFieldValue('time_mode') === 'recurring' ? '#d48806' : undefined,
                          backgroundColor: form.getFieldValue('time_mode') === 'recurring' ? '#fffbe6' : undefined
                        }}
                        onClick={() => form.setFieldValue('time_mode', 'recurring')}
                      >
                        <Radio value="recurring">
                          <Space direction="vertical" size={0}>
                            <Space>
                              <CalendarOutlined style={{ color: '#d48806' }} />
                              <strong>Recurring</strong>
                            </Space>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              Cron-based schedule
                            </Text>
                          </Space>
                        </Radio>
                      </Card>
                    </Col>
                  </Row>
                </Radio.Group>
              </Form.Item>

              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) => 
                  prevValues.time_mode !== currentValues.time_mode
                }
              >
                {({ getFieldValue }) => {
                  const timeMode = getFieldValue('time_mode');
                  
                  if (timeMode === 'duration') {
                    return (
                      <>
                        <Row gutter={16}>
                          <Col xs={24} sm={12}>
                            <Form.Item 
                              name="duration_value" 
                              label="Duration" 
                              initialValue={10}
                              rules={[{ required: true, message: 'Please enter duration' }]}
                            >
                              <InputNumber 
                                min={1} 
                                max={1440}
                                style={{ width: '100%' }}
                                placeholder="e.g., 10"
                              />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={12}>
                            <Form.Item 
                              name="duration_unit" 
                              label="Unit" 
                              initialValue="minutes"
                              rules={[{ required: true }]}
                            >
                              <Select>
                                <Option value="minutes">Minutes</Option>
                                <Option value="hours">Hours</Option>
                                <Option value="days">Days</Option>
                              </Select>
                            </Form.Item>
                          </Col>
                        </Row>
                        <Alert
                          message="Fixed Duration - Auto-Stop Enabled"
                          description={
                            <span>
                              <strong>⏱️ Auto-Stop:</strong> Analysis will automatically stop after the configured duration.
                              <br />
                              <strong>✓ Manual Control:</strong> You can also stop it earlier using the Stop button.
                              <br />
                              <strong>📊 Data Limits:</strong> Combine with size limits below for additional control.
                            </span>
                          }
                          type="success"
                          showIcon
                          icon={<FieldTimeOutlined />}
                          style={{ marginTop: 8 }}
                        />
                      </>
                    );
                  }
                  
                  if (timeMode === 'time_range') {
                    return (
                      <Row gutter={16}>
                        <Col xs={24} sm={12}>
                          <Form.Item 
                            name="start_time" 
                            label="Start Time"
                            rules={[{ required: true, message: 'Please select start time' }]}
                          >
                            <DatePicker 
                              showTime 
                              style={{ width: '100%' }} 
                              placeholder="Select start time"
                            />
                          </Form.Item>
                        </Col>
                        <Col xs={24} sm={12}>
                          <Form.Item 
                            name="end_time" 
                            label="End Time"
                            rules={[{ required: true, message: 'Please select end time' }]}
                          >
                            <DatePicker 
                              showTime 
                              style={{ width: '100%' }} 
                              placeholder="Select end time"
                            />
                          </Form.Item>
                        </Col>
                      </Row>
                    );
                  }
                  
                  if (timeMode === 'continuous') {
                    return (
                      <Alert
                        message="Continuous Analysis"
                        description={
                          <span>
                            Analysis will automatically stop after <strong>{defaultContinuousDuration} minutes</strong> 
                            {' '}(configurable by admins in Settings).
                            <br /><br />
                            <strong>Auto-Stop:</strong> Prevents analyses from running indefinitely.<br />
                            <strong>Warning:</strong> You will receive a notification 2 minutes before auto-stop.<br />
                            <strong>Manual Stop:</strong> You can stop earlier using the Stop button.
                            <br /><br />
                            Need a custom duration? Select <strong>Fixed Duration</strong> mode instead.
                          </span>
                        }
                        type="info"
                        showIcon
                        icon={<ClockCircleOutlined />}
                      />
                    );
                  }
                  
                  if (timeMode === 'recurring') {
                    return (
                      <>
                        <Row gutter={16}>
                          <Col xs={24} sm={8}>
                            <Form.Item
                              name="schedule_type"
                              label="Schedule"
                              initialValue="daily"
                              rules={[{ required: true }]}
                            >
                              <Select>
                                <Option value="daily">Daily</Option>
                                <Option value="weekly">Weekly (Mon-Fri)</Option>
                                <Option value="custom">Custom Cron</Option>
                              </Select>
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={8}>
                            <Form.Item
                              name="schedule_hour"
                              label="Run At (Hour)"
                              initialValue={2}
                              rules={[{ required: true }]}
                            >
                              <InputNumber min={0} max={23} style={{ width: '100%' }} placeholder="e.g., 2 (02:00)" />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={8}>
                            <Form.Item
                              name="schedule_minute"
                              label="Minute"
                              initialValue={0}
                            >
                              <InputNumber min={0} max={59} style={{ width: '100%' }} placeholder="0" />
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item
                          noStyle
                          shouldUpdate={(prev, curr) => prev.schedule_type !== curr.schedule_type}
                        >
                          {({ getFieldValue: getVal }) => 
                            getVal('schedule_type') === 'custom' ? (
                              <Form.Item
                                name="custom_cron"
                                label="Cron Expression"
                                rules={[{ required: true, message: 'Enter a valid cron expression' }]}
                                extra="Format: minute hour day-of-month month day-of-week (e.g., 0 3 * * 1-5)"
                              >
                                <Input placeholder="0 3 * * 1-5" />
                              </Form.Item>
                            ) : null
                          }
                        </Form.Item>
                        <Row gutter={16}>
                          <Col xs={24} sm={12}>
                            <Form.Item
                              name="recurring_duration_value"
                              label="Per-Run Duration"
                              initialValue={2}
                              rules={[{ required: true, message: 'Set how long each run should last' }]}
                            >
                              <InputNumber min={1} max={1440} style={{ width: '100%' }} placeholder="e.g., 2" />
                            </Form.Item>
                          </Col>
                          <Col xs={24} sm={12}>
                            <Form.Item
                              name="recurring_duration_unit"
                              label="Unit"
                              initialValue="hours"
                            >
                              <Select>
                                <Option value="minutes">Minutes</Option>
                                <Option value="hours">Hours</Option>
                              </Select>
                            </Form.Item>
                          </Col>
                        </Row>
                        <Form.Item
                          name="max_scheduled_runs"
                          label="Max Runs (0 = unlimited)"
                          initialValue={0}
                        >
                          <InputNumber min={0} max={10000} style={{ width: '100%' }} />
                        </Form.Item>
                        <Alert
                          message="Recurring Analysis"
                          description={
                            <span>
                              Analysis will run automatically on the configured schedule. Each run collects data for the specified duration, then auto-stops.
                              <br /><br />
                              <strong>Recommended:</strong> Use <em>Rolling Window</em> retention below to keep disk usage bounded.
                            </span>
                          }
                          type="warning"
                          showIcon
                          icon={<CalendarOutlined />}
                          style={{ marginTop: 8 }}
                        />
                      </>
                    );
                  }
                  
                  return null;
                }}
              </Form.Item>
            </Card>

            {/* Section 2: Smart Estimation Panel */}
            <Card 
              size="small" 
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: '#7c8eb5' }} />
                  <span>Estimated Data Generation</span>
                  <Tooltip title="Estimates based on your scope selection, cluster resources, and selected gadgets from previous steps.">
                    <InfoCircleOutlined style={{ color: '#0891b2', cursor: 'help' }} />
                  </Tooltip>
                </Space>
              }
              style={{ borderColor: '#7c8eb520', marginBottom: 16 }}
            >
              <Row gutter={[16, 16]}>
                <Col xs={12} sm={6}>
                  <Statistic 
                    title={<Space><ContainerOutlined /> Pods in Scope</Space>}
                    value={estimatedMetrics.podCount}
                    valueStyle={{ color: '#0891b2', fontSize: 20 }}
                  />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic 
                    title={<Space><AppstoreOutlined /> Gadgets Selected</Space>}
                    value={estimatedMetrics.gadgetCount}
                    valueStyle={{ color: '#4d9f7c', fontSize: 20 }}
                  />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic 
                    title="Events / Hour"
                    value={estimatedMetrics.eventsPerHour.toLocaleString()}
                    valueStyle={{ color: '#b89b5d', fontSize: 20 }}
                  />
                </Col>
                <Col xs={12} sm={6}>
                  <Statistic 
                    title="Data / Hour"
                    value={estimatedMetrics.mbPerHour}
                    suffix="MB"
                    valueStyle={{ color: '#a67c9e', fontSize: 20 }}
                  />
                </Col>
              </Row>
              
              <Divider style={{ margin: '16px 0' }} />
              
              <Row gutter={[16, 8]}>
                <Col span={24}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <strong>Time to reach size limits:</strong>
                  </Text>
                </Col>
                <Col xs={8}>
                  <Tag color="green">100 MB → ~{estimatedMetrics.hoursFor100MB}h</Tag>
                </Col>
                <Col xs={8}>
                  <Tag color="blue">500 MB → ~{estimatedMetrics.hoursFor500MB}h</Tag>
                </Col>
                <Col xs={8}>
                  <Tag color="purple">1 GB → ~{estimatedMetrics.hoursFor1GB}h</Tag>
                </Col>
              </Row>
              
              {estimatedMetrics.mbPerHour > 100 && (
                <Alert
                  message="High Data Rate Detected"
                  description={
                    <span>
                      With <strong>{estimatedMetrics.mbPerHour} MB/hour</strong>, consider using 
                      <strong> Stop on Limit</strong> or <strong>Rolling Window</strong> to manage storage.
                    </span>
                  }
                  type="warning"
                  showIcon
                  style={{ marginTop: 12 }}
                />
              )}
            </Card>

            {/* Section 3: Data Size Limits */}
            <Card 
              size="small" 
              title={
                <Space>
                  <HddOutlined style={{ color: '#b89b5d' }} />
                  <span>Data Size Limits</span>
                  <Tooltip title="Control how much data the analysis collects. This is important for long-running analyses to prevent storage overload.">
                    <InfoCircleOutlined style={{ color: '#0891b2', cursor: 'help' }} />
                  </Tooltip>
                </Space>
              }
              style={{ borderColor: '#b89b5d20' }}
            >
              <Form.Item
                name="data_retention_policy"
                label={
                  <Space>
                    <span>Data Retention Policy</span>
                  </Space>
                }
                initialValue="unlimited"
                rules={[{ required: true }]}
              >
                <Radio.Group style={{ width: '100%' }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Card 
                      size="small"
                      style={{ 
                        borderColor: form.getFieldValue('data_retention_policy') === 'unlimited' ? '#4d9f7c' : undefined,
                        cursor: 'pointer'
                      }}
                      onClick={() => form.setFieldValue('data_retention_policy', 'unlimited')}
                    >
                      <Radio value="unlimited">
                        <Space>
                          <ThunderboltOutlined style={{ color: '#4d9f7c' }} />
                          <div>
                            <strong>Unlimited</strong>
                            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                              Collect all data without limits (monitor storage usage)
                            </Text>
                          </div>
                        </Space>
                      </Radio>
                    </Card>
                    
                    <Card 
                      size="small"
                      style={{ 
                        borderColor: form.getFieldValue('data_retention_policy') === 'stop_on_limit' ? '#b89b5d' : undefined,
                        cursor: 'pointer'
                      }}
                      onClick={() => form.setFieldValue('data_retention_policy', 'stop_on_limit')}
                    >
                      <Radio value="stop_on_limit">
                        <Space>
                          <StopOutlined style={{ color: '#b89b5d' }} />
                          <div>
                            <strong>Stop on Limit</strong>
                            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                              Auto-stop when data size reaches limit
                            </Text>
                          </div>
                        </Space>
                      </Radio>
                    </Card>
                    
                    <Card 
                      size="small"
                      style={{ 
                        borderColor: form.getFieldValue('data_retention_policy') === 'rolling_window' ? '#0891b2' : undefined,
                        cursor: 'pointer'
                      }}
                      onClick={() => form.setFieldValue('data_retention_policy', 'rolling_window')}
                    >
                      <Radio value="rolling_window">
                        <Space>
                          <SyncOutlined style={{ color: '#0891b2' }} />
                          <div>
                            <strong>Rolling Window</strong>
                            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                              Keep fixed size, delete oldest data as new arrives
                            </Text>
                          </div>
                        </Space>
                      </Radio>
                    </Card>
                  </Space>
                </Radio.Group>
              </Form.Item>

              <Form.Item
                noStyle
                shouldUpdate={(prevValues, currentValues) => 
                  prevValues.data_retention_policy !== currentValues.data_retention_policy
                }
              >
                {({ getFieldValue }) => {
                  const policy = getFieldValue('data_retention_policy');
                  
                  if (policy === 'stop_on_limit' || policy === 'rolling_window') {
                    return (
                      <>
                        <Divider style={{ margin: '16px 0' }} />
                        <Form.Item
                          name="max_data_size_mb"
                          label="Maximum Data Size"
                          initialValue={500}
                          rules={[{ required: true, message: 'Please set data size limit' }]}
                        >
                          <InputNumber
                            min={50}
                            max={10000}
                            step={50}
                            style={{ width: 150 }}
                            addonAfter="MB"
                          />
                        </Form.Item>
                        <Space wrap style={{ marginBottom: 16 }}>
                          <Text type="secondary" style={{ fontSize: 12 }}>Quick:</Text>
                          <Button size="small" onClick={() => form.setFieldValue('max_data_size_mb', 100)}>100 MB</Button>
                          <Button size="small" onClick={() => form.setFieldValue('max_data_size_mb', 500)}>500 MB</Button>
                          <Button size="small" onClick={() => form.setFieldValue('max_data_size_mb', 1000)}>1 GB</Button>
                          <Button size="small" onClick={() => form.setFieldValue('max_data_size_mb', 2000)}>2 GB</Button>
                          <Button size="small" onClick={() => form.setFieldValue('max_data_size_mb', 5000)}>5 GB</Button>
                        </Space>
                        
                        <Row gutter={16} style={{ marginTop: 16 }}>
                          <Col xs={24} sm={8}>
                            <Statistic 
                              title="Estimated Events" 
                              value={estimatedMetrics.mbPerHour > 0 
                                ? Math.floor((getFieldValue('max_data_size_mb') || 500) / estimatedMetrics.mbPerHour * estimatedMetrics.eventsPerHour)
                                : Math.floor((getFieldValue('max_data_size_mb') || 500) * 2000)
                              }
                              suffix="events"
                              valueStyle={{ fontSize: 16 }}
                            />
                          </Col>
                          <Col xs={24} sm={8}>
                            <Statistic 
                              title="Estimated Duration" 
                              value={estimatedMetrics.mbPerHour > 0 
                                ? Math.round((getFieldValue('max_data_size_mb') || 500) / estimatedMetrics.mbPerHour)
                                : '~'
                              }
                              suffix="hours"
                              valueStyle={{ fontSize: 16, color: '#0891b2' }}
                            />
                          </Col>
                          <Col xs={24} sm={8}>
                            <Statistic 
                              title="Based on" 
                              value={estimatedMetrics.mbPerHour}
                              suffix="MB/hr"
                              valueStyle={{ fontSize: 16, color: '#4d9f7c' }}
                            />
                          </Col>
                        </Row>

                        {policy === 'stop_on_limit' && (
                          <>
                            <Alert
                              message="Auto-Stop on Size Limit"
                              description={
                                <span>
                                  <strong>🛑 Auto-Stop Enabled:</strong> Analysis will automatically stop when reaching{' '}
                                  <strong>{getFieldValue('max_data_size_mb') || 500} MB</strong>.
                                  <br />
                                  Estimated to reach limit in <strong>~{
                                    estimatedMetrics.mbPerHour > 0 
                                      ? Math.round((getFieldValue('max_data_size_mb') || 500) / estimatedMetrics.mbPerHour)
                                      : '?'
                                  } hours</strong>.
                                  <br /><br />
                                  <strong>✓ Manual Control:</strong> You can also stop earlier using the Stop button.
                                  <br />
                                  <strong>📊 Monitoring:</strong> Check the Events dashboard to monitor collected data size.
                                </span>
                              }
                              type="success"
                              showIcon
                              icon={<StopOutlined />}
                              style={{ marginTop: 16 }}
                            />
                          </>
                        )}
                        
                        {policy === 'rolling_window' && (
                          <>
                            <Alert
                              message="Rolling Window - Coming Soon"
                              description={
                                <span>
                                  Target window: <strong>{getFieldValue('max_data_size_mb') || 500} MB</strong> 
                                  (approximately <strong>{
                                    estimatedMetrics.mbPerHour > 0 
                                      ? Math.round((getFieldValue('max_data_size_mb') || 500) / estimatedMetrics.mbPerHour)
                                      : '?'
                                  } hours</strong> of history).
                                  <br /><br />
                                  <strong>🔜 Coming Soon:</strong> Automatic deletion of oldest events when reaching the size limit.
                                  Analysis will run continuously and old data will be rotated out.
                                  <br /><br />
                                  <strong>📋 Current Behavior:</strong> Analysis runs until manually stopped. 
                                  Use the Events dashboard to monitor data size.
                                </span>
                              }
                              type="warning"
                              showIcon
                              icon={<SyncOutlined />}
                              style={{ marginTop: 16 }}
                            />
                          </>
                        )}
                      </>
                    );
                  }
                  
                  if (policy === 'unlimited') {
                    return (
                      <Alert
                        message="Storage Consideration"
                        description={
                          <span>
                            Based on your configuration, estimated data generation is <strong>{estimatedMetrics.mbPerHour} MB/hour</strong>. 
                            {estimatedMetrics.mbPerHour > 50 && (
                              <span>
                                <br />This means <strong>~{Math.round(estimatedMetrics.mbPerHour * 24)} MB/day</strong> and <strong>~{Math.round(estimatedMetrics.mbPerHour * 24 * 7 / 1024 * 10) / 10} GB/week</strong>.
                              </span>
                            )}
                            <br /><br />
                            For long-running analyses, consider using <strong>Stop on Limit</strong> or <strong>Rolling Window</strong> 
                            to prevent storage issues.
                          </span>
                        }
                        type={estimatedMetrics.mbPerHour > 50 ? 'warning' : 'info'}
                        showIcon
                        style={{ marginTop: 8 }}
                      />
                    );
                  }
                  
                  return null;
                }}
              </Form.Item>
            </Card>

            {/* Section 4: Quick Presets */}
            <Card 
              size="small" 
              title={
                <Space>
                  <ThunderboltOutlined style={{ color: '#22a6a6' }} />
                  <span>Quick Presets</span>
                </Space>
              }
              style={{ borderColor: '#22a6a620' }}
            >
              <Row gutter={[12, 12]}>
                <Col xs={12} sm={6}>
                  <Button 
                    block 
                    style={{ height: 60 }}
                    onClick={() => {
                      form.setFieldsValue({
                        time_mode: 'duration',
                        duration_value: 10,
                        duration_unit: 'minutes',
                        data_retention_policy: 'stop_on_limit',
                        max_data_size_mb: 100
                      });
                    }}
                  >
                    <Space direction="vertical" size={0}>
                      <strong>10 Min Test</strong>
                      <Text type="secondary" style={{ fontSize: 11 }}>Quick test run</Text>
                    </Space>
                  </Button>
                </Col>
                <Col xs={12} sm={6}>
                  <Button 
                    block 
                    style={{ height: 60 }}
                    onClick={() => {
                      form.setFieldsValue({
                        time_mode: 'duration',
                        duration_value: 1,
                        duration_unit: 'hours',
                        data_retention_policy: 'stop_on_limit',
                        max_data_size_mb: 500
                      });
                    }}
                  >
                    <Space direction="vertical" size={0}>
                      <strong>1 Hour Scan</strong>
                      <Text type="secondary" style={{ fontSize: 11 }}>Standard analysis</Text>
                    </Space>
                  </Button>
                </Col>
                <Col xs={12} sm={6}>
                  <Button 
                    block 
                    style={{ height: 60 }}
                    onClick={() => {
                      form.setFieldsValue({
                        time_mode: 'continuous',
                        data_retention_policy: 'stop_on_limit',
                        max_data_size_mb: 1000
                      });
                    }}
                  >
                    <Space direction="vertical" size={0}>
                      <strong>Size Limited</strong>
                      <Text type="secondary" style={{ fontSize: 11 }}>Stop at 1 GB</Text>
                    </Space>
                  </Button>
                </Col>
                <Col xs={12} sm={6}>
                  <Button 
                    block 
                    type="dashed"
                    style={{ height: 60 }}
                    onClick={() => {
                      form.setFieldsValue({
                        time_mode: 'continuous',
                        data_retention_policy: 'unlimited'
                      });
                    }}
                  >
                    <Space direction="vertical" size={0}>
                      <strong>Default</strong>
                      <Text type="secondary" style={{ fontSize: 11 }}>{defaultContinuousDuration} min auto-stop</Text>
                    </Space>
                  </Button>
                </Col>
              </Row>
            </Card>
          </Space>
        );

      default:
        return null;
    }
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Title level={2}>
          <ExperimentOutlined /> New Analysis
        </Title>
        <Paragraph>
          Create a new analysis to discover application communications and dependencies using Inspector Gadget
        </Paragraph>
      </div>
      
      <Card>
        <Steps current={currentStep} items={steps} style={{ marginBottom: 32 }} />
        
        <Form
          form={form}
          layout="vertical"
          style={{ minHeight: 400 }}
          onValuesChange={handleFormValuesChange}
        >
          {renderStepContent()}
        </Form>

        <div style={{ marginTop: 24, textAlign: 'right' }}>
          <Space>
            {currentStep > 0 && (
              <Button onClick={handlePrevious}>
                Previous
              </Button>
            )}
            {currentStep < steps.length - 1 && (
              <Button type="primary" onClick={handleNext}>
                Next
              </Button>
            )}
            {currentStep === steps.length - 1 && (
              <Button 
                type="primary" 
                icon={<CheckCircleOutlined />}
                onClick={handleFinish}
                loading={isCreating}
              >
                Create Analysis
              </Button>
            )}
          </Space>
        </div>
      </Card>
    </div>
  );
};

export default AnalysisWizard;
