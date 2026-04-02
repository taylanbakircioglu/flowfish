import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { 
  Card, 
  Typography, 
  Space, 
  Select, 
  Table, 
  Tag, 
  Row, 
  Col,
  Statistic,
  DatePicker,
  Badge,
  Empty,
  Alert,
  Button,
  Tabs,
  Timeline,
  Tooltip,
  Collapse,
  Spin,
  message,
  Dropdown,
  Switch,
  Divider,
  Skeleton,
} from 'antd';
import type { MenuProps, TablePaginationConfig } from 'antd';
import { 
  SwapOutlined,
  PlusCircleOutlined,
  MinusCircleOutlined,
  EditOutlined,
  ClockCircleOutlined,
  DownloadOutlined,
  FilterOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  ApiOutlined,
  CloudServerOutlined,
  SyncOutlined,
  ReloadOutlined,
  FileExcelOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileOutlined,
  BarChartOutlined,
  WifiOutlined,
  DisconnectOutlined,
  RadarChartOutlined,
  ThunderboltOutlined,
  GlobalOutlined,
  CodeOutlined,
  AlertOutlined,
  BugOutlined,
  DatabaseOutlined,
  CheckCircleOutlined,
  PauseCircleOutlined,
  CloseCircleOutlined,
  BranchesOutlined,
  FieldTimeOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { 
  useGetChangesQuery,
  useCompareSnapshotsQuery,
  useGetAnalysisRunsQuery,
  useCompareRunsQuery,
  Change,
  ChangeType,
  RiskLevel,
  AnalysisRun,
  RunComparisonChange
} from '../store/api/changesApi';
import { Analysis } from '../types';
import { exportChanges, ExportFormat, ExportData } from '../utils/exportUtils';
import { useAnimatedCounter } from '../hooks/useAnimatedCounter';
import ChangeDetailDrawer from '../components/ChangeDetailDrawer';
import ChangeAnalytics from '../components/ChangeAnalytics';
import SavedFilters, { FilterConfig } from '../components/SavedFilters';
import SnapshotComparison from '../components/SnapshotComparison';
import { useChangeDetectionSocket } from '../hooks/useChangeDetectionSocket';
import { useTheme } from '../contexts/ThemeContext';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;
const { Panel } = Collapse;

// Change types configuration - organized by category
const changeTypeConfig: Record<ChangeType, { label: string; color: string; icon: React.ReactNode; category: string }> = {
  // Legacy types
  workload_added: { label: 'Workload Added', color: '#4d9f7c', icon: <PlusCircleOutlined />, category: 'legacy' },
  workload_removed: { label: 'Workload Removed', color: '#c75450', icon: <MinusCircleOutlined />, category: 'legacy' },
  namespace_changed: { label: 'Namespace Changed', color: '#a67c9e', icon: <SwapOutlined />, category: 'legacy' },
  
  // Infrastructure changes (K8s API) - Workloads
  replica_changed: { label: 'Replica Changed', color: '#c9a55a', icon: <SyncOutlined />, category: 'infrastructure' },
  config_changed: { label: 'Config Changed', color: '#22a6a6', icon: <EditOutlined />, category: 'infrastructure' },
  image_changed: { label: 'Image Changed', color: '#9254de', icon: <DatabaseOutlined />, category: 'infrastructure' },
  label_changed: { label: 'Label Changed', color: '#597ef7', icon: <EditOutlined />, category: 'infrastructure' },
  resource_changed: { label: 'Resource Changed', color: '#d48806', icon: <BarChartOutlined />, category: 'infrastructure' },
  env_changed: { label: 'Env Changed', color: '#7cb305', icon: <CodeOutlined />, category: 'infrastructure' },
  spec_changed: { label: 'Spec Changed', color: '#531dab', icon: <FileOutlined />, category: 'infrastructure' },
  // Infrastructure changes (K8s API) - Services
  service_port_changed: { label: 'Service Port Changed', color: '#08979c', icon: <EditOutlined />, category: 'infrastructure' },
  service_selector_changed: { label: 'Service Selector Changed', color: '#c41d7f', icon: <SwapOutlined />, category: 'infrastructure' },
  service_type_changed: { label: 'Service Type Changed', color: '#1d39c4', icon: <CloudServerOutlined />, category: 'infrastructure' },
  service_added: { label: 'Service Added', color: '#389e0d', icon: <PlusCircleOutlined />, category: 'infrastructure' },
  service_removed: { label: 'Service Removed', color: '#cf1322', icon: <MinusCircleOutlined />, category: 'infrastructure' },
  // Infrastructure changes (K8s API) - Network / Ingress / Route
  network_policy_added: { label: 'Network Policy Added', color: '#389e0d', icon: <PlusCircleOutlined />, category: 'infrastructure' },
  network_policy_removed: { label: 'Network Policy Removed', color: '#cf1322', icon: <MinusCircleOutlined />, category: 'infrastructure' },
  network_policy_changed: { label: 'Network Policy Changed', color: '#d46b08', icon: <ApiOutlined />, category: 'infrastructure' },
  ingress_added: { label: 'Ingress Added', color: '#389e0d', icon: <PlusCircleOutlined />, category: 'infrastructure' },
  ingress_removed: { label: 'Ingress Removed', color: '#cf1322', icon: <MinusCircleOutlined />, category: 'infrastructure' },
  ingress_changed: { label: 'Ingress Changed', color: '#d46b08', icon: <GlobalOutlined />, category: 'infrastructure' },
  route_added: { label: 'Route Added', color: '#389e0d', icon: <PlusCircleOutlined />, category: 'infrastructure' },
  route_removed: { label: 'Route Removed', color: '#cf1322', icon: <MinusCircleOutlined />, category: 'infrastructure' },
  route_changed: { label: 'Route Changed', color: '#d46b08', icon: <BranchesOutlined />, category: 'infrastructure' },

  // Connection changes (eBPF)
  connection_added: { label: 'New Connection', color: '#4d9f7c', icon: <PlusCircleOutlined />, category: 'anomaly' },
  port_changed: { label: 'Port Changed', color: '#7c8eb5', icon: <EditOutlined />, category: 'connection' },
  
  // Anomaly detection (eBPF)
  connection_removed: { label: 'Connection Anomaly', color: '#c75450', icon: <DisconnectOutlined />, category: 'anomaly' },
  traffic_anomaly: { label: 'Traffic Anomaly', color: '#d4756a', icon: <ThunderboltOutlined />, category: 'anomaly' },
  dns_anomaly: { label: 'DNS Anomaly', color: '#0891b2', icon: <GlobalOutlined />, category: 'anomaly' },
  process_anomaly: { label: 'Process Anomaly', color: '#7c8eb5', icon: <CodeOutlined />, category: 'anomaly' },
  error_anomaly: { label: 'Error Anomaly', color: '#cf1322', icon: <BugOutlined />, category: 'anomaly' },
};

// Category labels and colors
const categoryConfig = {
  infrastructure: { label: 'Infrastructure', color: '#0891b2', icon: <CloudServerOutlined /> },
  connection: { label: 'Connections', color: '#4d9f7c', icon: <WifiOutlined /> },
  anomaly: { label: 'Anomalies', color: '#d4756a', icon: <RadarChartOutlined /> },
  legacy: { label: 'Legacy', color: '#8c8c8c', icon: <SwapOutlined /> },
};

// Risk levels configuration
const riskLevelConfig: Record<RiskLevel, { color: string; label: string }> = {
  critical: { color: '#cf1322', label: 'Critical' },
  high: { color: '#c75450', label: 'High' },
  medium: { color: '#b89b5d', label: 'Medium' },
  low: { color: '#4d9f7c', label: 'Low' },
};

// Default page size for consistent pagination
const DEFAULT_PAGE_SIZE = 20;

// Analysis status helper functions
const getStatusIcon = (status: string) => {
  switch (status) {
    case 'running': return <SyncOutlined spin />;
    case 'completed': return <CheckCircleOutlined />;
    case 'stopped': return <PauseCircleOutlined />;
    case 'failed': return <CloseCircleOutlined />;
    default: return <ClockCircleOutlined />;
  }
};

const getStatusColor = (status: string): string => {
  switch (status) {
    case 'running': return 'processing';
    case 'completed': return 'success';
    case 'stopped': return 'warning';
    case 'failed': return 'error';
    default: return 'default';
  }
};

const getStatusLabel = (status: string): string => {
  switch (status) {
    case 'running': return 'Running';
    case 'completed': return 'Completed';
    case 'stopped': return 'Stopped';
    case 'failed': return 'Failed';
    default: return status;
  }
};

const getStatusTooltip = (status: string, wsConnected: boolean): string => {
  switch (status) {
    case 'running': return wsConnected ? 'Analysis running - Real-time updates active' : 'Analysis running - Connecting...';
    case 'completed': return 'Analysis completed successfully';
    case 'stopped': return 'Analysis stopped by user';
    case 'failed': return 'Analysis failed';
    default: return `Analysis status: ${status}`;
  }
};

// Anomaly types constant - defined outside component to avoid recreation on each render
const ANOMALY_TYPES: string[] = ['connection_added', 'connection_removed', 'traffic_anomaly', 'dns_anomaly', 'process_anomaly', 'error_anomaly'];

const INFRASTRUCTURE_TYPES: string[] = [
  'replica_changed', 'config_changed', 'image_changed', 'label_changed',
  'resource_changed', 'env_changed', 'spec_changed',
  'service_port_changed', 'service_selector_changed', 'service_type_changed',
  'service_added', 'service_removed',
  'network_policy_added', 'network_policy_removed', 'network_policy_changed',
  'ingress_added', 'ingress_removed', 'ingress_changed',
  'route_added', 'route_removed', 'route_changed',
  'workload_added', 'workload_removed', 'namespace_changed',
];

const CONNECTION_TYPES: string[] = ['port_changed'];

const NON_ANOMALY_TYPES: string[] = [...INFRASTRUCTURE_TYPES, ...CONNECTION_TYPES];

const ChangeDetection: React.FC = () => {
  const { isDark } = useTheme();
  const [searchParams] = useSearchParams();
  const cardBg = isDark ? '#262626' : '#fafbfc';
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#a0aec0';
  
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  
  // Initialize from URL parameters (when navigating from Dashboard)
  useEffect(() => {
    const urlAnalysisId = searchParams.get('analysisId');
    const urlClusterId = searchParams.get('clusterId');
    
    if (urlAnalysisId && !selectedAnalysisId) {
      const parsedId = parseInt(urlAnalysisId, 10);
      if (!isNaN(parsedId)) {
        setSelectedAnalysisId(parsedId);
      }
    }
    if (urlClusterId && !selectedClusterId) {
      const parsedId = parseInt(urlClusterId, 10);
      if (!isNaN(parsedId)) {
        setSelectedClusterId(parsedId);
      }
    }
  }, [searchParams]); // Only run on mount or when searchParams change
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [selectedChangeTypes, setSelectedChangeTypes] = useState<string[]>([]);
  const [selectedRiskLevels, setSelectedRiskLevels] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState('timeline');
  const [pagination, setPagination] = useState({ current: 1, pageSize: DEFAULT_PAGE_SIZE });
  
  // Drawer state
  const [selectedChangeId, setSelectedChangeId] = useState<number | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  
  // Advanced filter state
  const [changedByFilter, setChangedByFilter] = useState<string | undefined>(undefined);
  const [minAffectedFilter, setMinAffectedFilter] = useState<number | undefined>(undefined);
  const [maxAffectedFilter, setMaxAffectedFilter] = useState<number | undefined>(undefined);
  const [namespaceFilter, setNamespaceFilter] = useState<string[]>([]);
  
  // Anomaly filter - default to hiding anomalies (they are NOT real changes)
  // Anomalies are operational events (errors, retransmits, etc.), not infrastructure changes
  const [hideAnomalies, setHideAnomalies] = useState(true);
  
  // Reset to page 1 when filters change to avoid showing an empty out-of-range page
  useEffect(() => {
    setPagination(p => p.current === 1 ? p : { ...p, current: 1 });
  }, [selectedChangeTypes, selectedRiskLevels, hideAnomalies, namespaceFilter, changedByFilter]);
  
  // Noise filter toggles - only apply when anomalies are shown
  // These filter specific types of anomalies
  const [hideInternalDns, setHideInternalDns] = useState(false);
  const [hideNormalProcesses, setHideNormalProcesses] = useState(false);
  const [hideRetransmitErrors, setHideRetransmitErrors] = useState(false);
  
  // Stats card filter state for clickable filtering
  const [activeStatFilter, setActiveStatFilter] = useState<string | null>(null);
  
  // Snapshot comparison state
  const [compareAnalysisId, setCompareAnalysisId] = useState<number | undefined>(undefined);

  // Run comparison state
  const [runA, setRunA] = useState<number | undefined>(undefined);
  const [runB, setRunB] = useState<number | undefined>(undefined);

  // Reset run selection when analysis changes
  useEffect(() => {
    setRunA(undefined);
    setRunB(undefined);
  }, [selectedAnalysisId]);

  // Ensure runA != runB (handle edge case where user changes runA to equal runB)
  useEffect(() => {
    if (runA !== undefined && runB !== undefined && runA === runB) {
      // Reset runB if it becomes equal to runA
      setRunB(undefined);
    }
  }, [runA, runB]);

  // API queries
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  // Fetch ALL analyses (no cluster filter) - user selects analysis first
  const { data: analyses = [], isLoading: isAnalysesLoading } = useGetAnalysesQuery({});
  
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  // Handle analysis change - set analysis ID and clear cluster (useEffect will set correct cluster)
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    // Always clear clusterId immediately - useEffect will set the correct one
    // This prevents race condition where old clusterId is used with new analysisId
    setSelectedClusterId(undefined);
    setPagination(prev => ({ ...prev, current: 1 }));
  }, []);

  // Get selected analysis object
  const selectedAnalysis = useMemo(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      return (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
    }
    return undefined;
  }, [selectedAnalysisId, analyses]);

  // Auto-set cluster when analysis changes
  useEffect(() => {
    if (selectedAnalysis) {
      setSelectedClusterId(selectedAnalysis.cluster_id);
    }
  }, [selectedAnalysis]);

  // Build query params
  // When anomalies are hidden and no explicit type filter is set, send non-anomaly
  // types to the server so every page contains only real changes (correct pagination).
  // Tabs that show grouped/aggregate views (byType, analytics) fetch more data.
  const queryParams = useMemo(() => {
    let effectiveChangeTypes = selectedChangeTypes;
    if (hideAnomalies && selectedChangeTypes.length === 0) {
      effectiveChangeTypes = NON_ANOMALY_TYPES;
    }
    const needsAllData = activeTab === 'byType' || activeTab === 'analytics';
    const effectiveLimit = needsAllData ? 500 : pagination.pageSize;
    const effectiveOffset = needsAllData ? 0 : (pagination.current - 1) * pagination.pageSize;
    return {
      cluster_id: selectedClusterId!,
      analysis_id: selectedAnalysisId,
      start_time: dateRange?.[0]?.toISOString(),
      end_time: dateRange?.[1]?.toISOString(),
      change_types: effectiveChangeTypes.length > 0 ? effectiveChangeTypes.join(',') : undefined,
      risk_levels: selectedRiskLevels.length > 0 ? selectedRiskLevels.join(',') : undefined,
      limit: effectiveLimit,
      offset: effectiveOffset,
    };
  }, [selectedClusterId, selectedAnalysisId, dateRange, selectedChangeTypes, selectedRiskLevels, pagination, hideAnomalies, activeTab]);

  // Get changes from API
  const { 
    data: changesData, 
    isLoading: isChangesLoading, 
    isError: isChangesError,
    error: changesError,
    refetch: refetchChanges 
  } = useGetChangesQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const changes = changesData?.changes || [];
  const stats = changesData?.stats;
  const comparison = changesData?.comparison;
  const totalChanges = changesData?.total || 0;

  // WebSocket for real-time updates
  const { isConnected: wsConnected } = useChangeDetectionSocket({
    enabled: !!selectedAnalysisId,
    analysisId: selectedAnalysisId,
    showNotifications: true,
    onChangeDetected: useCallback(() => {
      // Refetch when a new change is detected
      refetchChanges();
    }, [refetchChanges]),
    onViewChange: useCallback((changeId: number) => {
      if (changeId) {
        setSelectedChangeId(changeId);
        setDrawerOpen(true);
      }
    }, []),
  });

  // Snapshot comparison query (only when compare tab is active)
  const { data: snapshotComparisonData, isLoading: isComparisonLoading } = useCompareSnapshotsQuery(
    {
      cluster_id: selectedClusterId!,
      analysis_id_before: compareAnalysisId!,
      analysis_id_after: selectedAnalysisId!,
    },
    { 
      skip: !selectedClusterId || !selectedAnalysisId || !compareAnalysisId || activeTab !== 'compare' 
    }
  );

  // Get runs for the selected analysis (for run comparison)
  const { data: runsData, isLoading: isRunsLoading } = useGetAnalysisRunsQuery(
    selectedAnalysisId!,
    { skip: !selectedAnalysisId }
  );
  const runs = runsData?.runs || [];

  // Validate selected runs still exist when runs data changes
  useEffect(() => {
    if (runs.length > 0) {
      const runNumbers = runs.map((r: AnalysisRun) => r.run_number);
      // Reset runA if it no longer exists
      if (runA !== undefined && !runNumbers.includes(runA)) {
        setRunA(undefined);
      }
      // Reset runB if it no longer exists
      if (runB !== undefined && !runNumbers.includes(runB)) {
        setRunB(undefined);
      }
    }
  }, [runs, runA, runB]);

  // Run comparison query (only when compare-runs tab is active)
  const { 
    data: runComparisonData, 
    isLoading: isRunComparisonLoading,
    error: runComparisonError,
    isError: isRunComparisonError
  } = useCompareRunsQuery(
    {
      analysis_id: selectedAnalysisId!,
      run_a: runA!,
      run_b: runB!,
    },
    { 
      skip: !selectedAnalysisId || !runA || !runB || activeTab !== 'compare-runs' 
    }
  );

  // Noise filter helper functions
  // K8s internal DNS pattern - .svc.cluster.local queries
  const isInternalDns = useCallback((change: Change) => {
    return change.change_type === 'dns_anomaly' && 
      (change.target.includes('.svc.cluster.local') ||
       change.target.includes('.cluster.local.'));
  }, []);

  // Normal process list - common system processes that are typically harmless
  const NORMAL_PROCESSES = ['python', 'python3', 'java', 'node', 'bash', 'sh', 'sleep', 'pause', 'tini'];
  
  const isNormalProcess = useCallback((change: Change) => {
    if (change.change_type !== 'process_anomaly') return false;
    
    // Target format: "pod-name/container: process_name"
    const processName = change.target.split(': ').pop()?.toLowerCase() || '';
    return NORMAL_PROCESSES.includes(processName);
  }, []);

  // Retransmit error pattern - normal TCP behavior, not critical errors
  // CONNECTION_RESET, TIMEOUT, REFUSED are real issues and should NOT be hidden
  const isRetransmitError = useCallback((change: Change) => {
    if (change.change_type !== 'error_anomaly') return false;
    
    // Check error_type in metadata or details
    // metadata is Record<string, unknown>, so we need to cast to string
    const errorType = String(change.metadata?.error_type || '').toUpperCase();
    const details = (change.details || '').toUpperCase();
    
    // RETRANSMIT types are normal TCP behavior (packet loss recovery)
    const isRetransmit = errorType.includes('RETRANSMIT') || details.includes('RETRANSMIT');
    
    return isRetransmit;
  }, []);

  // Helper to check if a change is an anomaly (ANOMALY_TYPES defined outside component)
  const isAnomaly = useCallback((change: Change) => {
    return ANOMALY_TYPES.includes(change.change_type);
  }, []);

  // Filter changes client-side for additional filtering
  const filteredChanges = useMemo(() => {
    return changes
      .filter((change: Change) => {
        // PRIMARY FILTER: Hide anomalies by default (they are NOT real changes)
        // Anomalies are operational events (errors, retransmits, traffic spikes)
        // Real changes are: workload add/remove, connection add/remove, config changes, etc.
        if (hideAnomalies && isAnomaly(change)) {
          return false;
        }
        
        // Filter by changed_by
        if (changedByFilter && change.changed_by !== changedByFilter) {
          return false;
        }
        // Filter by min affected services
        if (minAffectedFilter !== undefined && change.affected_services < minAffectedFilter) {
          return false;
        }
        // Filter by max affected services
        if (maxAffectedFilter !== undefined && change.affected_services > maxAffectedFilter) {
          return false;
        }
        // Filter by namespace
        if (namespaceFilter.length > 0 && !namespaceFilter.includes(change.namespace)) {
          return false;
        }
        
        // Noise filters (client-side toggle) - only apply to anomalies
        // Data is NOT lost, just filtered from display
        if (hideInternalDns && isInternalDns(change)) {
          return false;
        }
        if (hideNormalProcesses && isNormalProcess(change)) {
          return false;
        }
        if (hideRetransmitErrors && isRetransmitError(change)) {
          return false;
        }
        
        return true;
      })
      .map((change: Change) => ({
        ...change,
        key: change.id,
      }));
  }, [changes, hideAnomalies, isAnomaly, changedByFilter, minAffectedFilter, maxAffectedFilter, namespaceFilter, 
      hideInternalDns, hideNormalProcesses, hideRetransmitErrors, isInternalDns, isNormalProcess, isRetransmitError]);

  // Get available namespaces from current changes
  const availableNamespaces = useMemo(() => {
    const namespaces = new Set<string>();
    changes.forEach((change: Change) => namespaces.add(change.namespace));
    return Array.from(namespaces).sort();
  }, [changes]);

  // Get available changed_by from current changes
  const availableChangedBy = useMemo(() => {
    const users = new Set<string>();
    changes.forEach((change: Change) => users.add(change.changed_by));
    return Array.from(users).sort();
  }, [changes]);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    refetchChanges();
    message.success('Data refreshed');
  }, [refetchChanges]);

  // Handle row click to open drawer
  const handleRowClick = useCallback((record: Change) => {
    setSelectedChangeId(record.id);
    setDrawerOpen(true);
  }, []);

  // Handle table pagination change
  const handleTableChange = useCallback((newPagination: TablePaginationConfig) => {
    setPagination({
      current: newPagination.current || 1,
      pageSize: newPagination.pageSize || DEFAULT_PAGE_SIZE,
    });
  }, []);

  // Handle export
  const handleExport = useCallback((format: ExportFormat) => {
    if (!changesData) {
      message.warning('No data to export');
      return;
    }
    
    const exportData: ExportData = {
      changes: changesData.changes,
      stats: changesData.stats,
      comparison: changesData.comparison,
      metadata: {
        clusterId: selectedClusterId,
        analysisId: selectedAnalysisId,
        exportTime: dayjs().toISOString(),
        dateRange: dateRange ? {
          start: dateRange[0].format('YYYY-MM-DD HH:mm'),
          end: dateRange[1].format('YYYY-MM-DD HH:mm'),
        } : undefined,
      },
    };
    
    try {
      exportChanges(format, exportData);
      message.success(`Exported to ${format.toUpperCase()}`);
    } catch (error) {
      message.error('Export failed');
      console.error('Export error:', error);
    }
  }, [changesData, selectedClusterId, selectedAnalysisId, dateRange]);

  // Handle applying saved/advanced filters
  const handleApplyFilter = useCallback((filter: FilterConfig) => {
    // Clear stat card filter when applying a saved/advanced filter
    setActiveStatFilter(null);
    
    // Reset all filters first if "Clear" is applied
    if (filter.name === 'Clear') {
      setSelectedChangeTypes([]);
      setSelectedRiskLevels([]);
      setChangedByFilter(undefined);
      setMinAffectedFilter(undefined);
      setMaxAffectedFilter(undefined);
      setNamespaceFilter([]);
      message.info('Filters cleared');
      return;
    }
    
    // Apply filter values
    if (filter.changeTypes) {
      setSelectedChangeTypes(filter.changeTypes);
    }
    if (filter.riskLevels) {
      setSelectedRiskLevels(filter.riskLevels);
    }
    if (filter.changedBy !== undefined) {
      setChangedByFilter(filter.changedBy || undefined);
    }
    if (filter.minAffectedServices !== undefined) {
      setMinAffectedFilter(filter.minAffectedServices);
    }
    if (filter.maxAffectedServices !== undefined) {
      setMaxAffectedFilter(filter.maxAffectedServices);
    }
    if (filter.namespaces) {
      setNamespaceFilter(filter.namespaces);
    }
    
    message.success(`Filter "${filter.name}" applied`);
  }, []);

  // Handle stat card click for filtering
  const handleStatCardClick = useCallback((cardType: string) => {
    if (activeStatFilter === cardType) {
      // Toggle off - clear filters and reset to default
      setActiveStatFilter(null);
      setSelectedChangeTypes([]);
      setSelectedRiskLevels([]);
      setHideAnomalies(true);
      return;
    }
    
    setActiveStatFilter(cardType);
    switch (cardType) {
      case 'total':
        setSelectedChangeTypes([]);
        setSelectedRiskLevels([]);
        setHideAnomalies(true);
        break;
      case 'infrastructure':
        setSelectedChangeTypes([...INFRASTRUCTURE_TYPES]);
        setSelectedRiskLevels([]);
        setHideAnomalies(true);
        break;
      case 'connections':
        setSelectedChangeTypes([...CONNECTION_TYPES]);
        setSelectedRiskLevels([]);
        setHideAnomalies(true);
        break;
      case 'anomalies':
        setSelectedChangeTypes([...ANOMALY_TYPES]);
        setSelectedRiskLevels([]);
        setHideAnomalies(false);
        break;
      case 'critical':
        setSelectedChangeTypes([]);
        setSelectedRiskLevels(['critical']);
        setHideAnomalies(false);
        break;
      case 'high':
        setSelectedChangeTypes([]);
        setSelectedRiskLevels(['critical', 'high']);
        setHideAnomalies(false);
        break;
      default:
        setSelectedChangeTypes([]);
        setSelectedRiskLevels([]);
        setHideAnomalies(true);
    }
  }, [activeStatFilter]);

  // Clear all filters handler - resets to default state
  const handleClearAllFilters = useCallback(() => {
    setSelectedChangeTypes([]);
    setSelectedRiskLevels([]);
    setChangedByFilter(undefined);
    setMinAffectedFilter(undefined);
    setMaxAffectedFilter(undefined);
    setNamespaceFilter([]);
    // Reset to defaults: anomalies hidden, noise filters off
    setHideAnomalies(true);
    setHideInternalDns(false);
    setHideNormalProcesses(false);
    setHideRetransmitErrors(false);
    setActiveStatFilter(null);
    message.info('All filters cleared');
  }, []);

  // Export menu items
  const exportMenuItems: MenuProps['items'] = [
    {
      key: 'csv',
      icon: <FileTextOutlined />,
      label: 'Export as CSV',
      onClick: () => handleExport('csv'),
    },
    {
      key: 'json',
      icon: <FileOutlined />,
      label: 'Export as JSON',
      onClick: () => handleExport('json'),
    },
    {
      key: 'excel',
      icon: <FileExcelOutlined />,
      label: 'Export as Excel',
      onClick: () => handleExport('excel'),
    },
    {
      type: 'divider',
    },
    {
      key: 'pdf',
      icon: <FilePdfOutlined />,
      label: 'Print / Save as PDF',
      onClick: () => handleExport('pdf'),
    },
  ];

  // Table columns
  const columns = [
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
      render: (timestamp: string) => (
        <Space>
          <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
          <Text>{dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss')}</Text>
        </Space>
      ),
    },
    {
      title: 'Change Type',
      dataIndex: 'change_type',
      key: 'change_type',
      width: 160,
      filters: Object.entries(changeTypeConfig).map(([key, val]) => ({ text: val.label, value: key })),
      onFilter: (value: any, record: any) => record.change_type === value,
      render: (type: ChangeType) => {
        const config = changeTypeConfig[type];
        return (
          <Tag color={config?.color} icon={config?.icon}>
            {config?.label || type}
          </Tag>
        );
      },
    },
    {
      title: 'Target',
      dataIndex: 'target',
      key: 'target',
      render: (target: string, record: Change) => (
        <div>
          <Text strong>{target}</Text>
          <br />
          <Text type="secondary" style={{ fontSize: 11 }}>{record.namespace}</Text>
        </div>
      ),
    },
    {
      title: 'Details',
      dataIndex: 'details',
      key: 'details',
      ellipsis: true,
      render: (details: string) => (
        <Tooltip title={details}>
          <Text type="secondary">{details}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Risk',
      dataIndex: 'risk',
      key: 'risk',
      width: 100,
      filters: Object.entries(riskLevelConfig).map(([key, val]) => ({ text: val.label, value: key })),
      onFilter: (value: any, record: any) => record.risk === value,
      sorter: (a: any, b: any) => {
        const order = ['critical', 'high', 'medium', 'low'];
        return order.indexOf(a.risk) - order.indexOf(b.risk);
      },
      render: (risk: RiskLevel) => {
        const config = riskLevelConfig[risk];
        return <Tag color={config?.color}>{config?.label}</Tag>;
      },
    },
    {
      title: 'Impact',
      dataIndex: 'affected_services',
      key: 'affected_services',
      width: 100,
      sorter: (a: any, b: any) => a.affected_services - b.affected_services,
      render: (count: number) => (
        <Tooltip title={`${count} services affected`}>
          <Badge count={count} style={{ backgroundColor: count > 5 ? '#c75450' : count > 2 ? '#b89b5d' : '#4d9f7c' }} />
        </Tooltip>
      ),
    },
    {
      title: 'Changed By',
      dataIndex: 'changed_by',
      key: 'changed_by',
      width: 140,
      render: (user: string) => <Text type="secondary">{user}</Text>,
    },
  ];

  // Timeline items
  const timelineItems = filteredChanges.map((change: Change) => {
    const typeConfig = changeTypeConfig[change.change_type];
    const riskConfig = riskLevelConfig[change.risk];
    
    return {
      key: change.id,
      color: typeConfig?.color || '#8c8c8c',
      children: (
        <div 
          onClick={() => handleRowClick(change)}
          style={{ cursor: 'pointer', padding: '4px 0' }}
        >
          <Space>
            <Tag color={typeConfig?.color || '#8c8c8c'} icon={typeConfig?.icon}>{typeConfig?.label || change.change_type}</Tag>
            <Tag color={riskConfig?.color || '#8c8c8c'}>{riskConfig?.label || change.risk}</Tag>
          </Space>
          <div style={{ marginTop: 4 }}>
            <Text strong>{change.target}</Text>
            <Text type="secondary" style={{ marginLeft: 8 }}>({change.namespace})</Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text type="secondary">{change.details}</Text>
          </div>
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              <ClockCircleOutlined /> {dayjs(change.timestamp).format('YYYY-MM-DD HH:mm:ss')} • {change.changed_by}
            </Text>
          </div>
        </div>
      ),
    };
  });

  const criticalCount = stats?.by_risk?.critical || 0;
  const highCount = stats?.by_risk?.high || 0;
  
  const anomalyCount = ANOMALY_TYPES.reduce((sum, type) => sum + (stats?.by_type?.[type] || 0), 0);
  const connectionCount = CONNECTION_TYPES.reduce((sum, type) => sum + (stats?.by_type?.[type] || 0), 0);
  const infrastructureCount = INFRASTRUCTURE_TYPES.reduce((sum, type) => sum + (stats?.by_type?.[type] || 0), 0);
  
  // Real changes = Infrastructure + Connections (NOT anomalies)
  // Anomalies are operational events (errors, spikes), not actual infrastructure changes
  const realChangesCount = infrastructureCount + connectionCount;
  
  // Count anomalies and real changes in current loaded data (for accurate empty state messages)
  const anomaliesInData = useMemo(() => changes.filter(c => ANOMALY_TYPES.includes(c.change_type)).length, [changes]);
  const realChangesInData = useMemo(() => changes.filter(c => !ANOMALY_TYPES.includes(c.change_type)).length, [changes]);

  // ============================================
  // ANIMATED COUNTERS for Stats Cards
  // ============================================
  // Total Changes now shows REAL changes only (Infrastructure + Connections)
  // Anomalies are shown separately as they are not actual changes
  const animatedTotalChanges = useAnimatedCounter(realChangesCount, 1200, !selectedAnalysisId || isChangesLoading);
  const animatedInfrastructure = useAnimatedCounter(infrastructureCount, 1200, !selectedAnalysisId || isChangesLoading);
  const animatedConnections = useAnimatedCounter(connectionCount, 1200, !selectedAnalysisId || isChangesLoading);
  const animatedAnomalies = useAnimatedCounter(anomalyCount, 1200, !selectedAnalysisId || isChangesLoading);
  const animatedCritical = useAnimatedCounter(criticalCount, 1200, !selectedAnalysisId || isChangesLoading);
  const animatedHigh = useAnimatedCounter(highCount, 1200, !selectedAnalysisId || isChangesLoading);

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Space align="center">
          <SwapOutlined style={{ fontSize: 28, color: '#b89b5d' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Change Detection</Title>
            <Text type="secondary">
              Track infrastructure changes and behavioral anomalies with eBPF-powered analysis
            </Text>
          </div>
        </Space>
        {selectedAnalysis && (
          <Tooltip title={getStatusTooltip(selectedAnalysis.status, wsConnected)}>
            <Tag 
              icon={getStatusIcon(selectedAnalysis.status)} 
              color={getStatusColor(selectedAnalysis.status)}
            >
              {getStatusLabel(selectedAnalysis.status)}
            </Tag>
          </Tooltip>
        )}
      </div>

      {/* Filters */}
      <Card bordered={false} style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Analysis</Text>
            <Select
              placeholder="Select analysis"
              style={{ width: 280 }}
              value={selectedAnalysisId}
              onChange={handleAnalysisChange}
              loading={isAnalysesLoading}
              allowClear
            >
              {availableAnalyses.map((analysis: Analysis) => {
                const cluster = clusters.find((c: any) => c.id === analysis.cluster_id);
                const clusterName = cluster?.name || `Cluster ${analysis.cluster_id}`;
                return (
                  <Option key={analysis.id} value={analysis.id}>
                    <Space>
                      <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                      {analysis.name}
                      <Text type="secondary" style={{ fontSize: 11 }}>({clusterName})</Text>
                    </Space>
                  </Option>
                );
              })}
            </Select>
          </Col>
          {/* Detection Strategy Badge with Context */}
          {selectedAnalysis && selectedAnalysis.change_detection_enabled !== false && (
            <Col>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Detection Strategy</Text>
              <Space size={4}>
                <Tooltip 
                  title={
                    selectedAnalysis.change_detection_strategy === 'baseline' 
                      ? 'Comparing current behavior against initial baseline (first 10 min) to detect drift'
                      : selectedAnalysis.change_detection_strategy === 'rolling_window'
                      ? 'Continuously comparing recent 5 min window vs previous 5 min for real-time anomaly detection'
                      : selectedAnalysis.change_detection_strategy === 'run_comparison'
                      ? 'Comparing current run against previous runs for deployment validation'
                      : 'Default detection strategy'
                  }
                >
                  <Tag 
                    color={
                      selectedAnalysis.change_detection_strategy === 'baseline' ? 'processing' 
                      : selectedAnalysis.change_detection_strategy === 'rolling_window' ? 'success'
                      : selectedAnalysis.change_detection_strategy === 'run_comparison' ? 'purple'
                      : 'default'
                    }
                    icon={
                      selectedAnalysis.change_detection_strategy === 'baseline' ? <LineChartOutlined /> 
                      : selectedAnalysis.change_detection_strategy === 'rolling_window' ? <SyncOutlined spin />
                      : selectedAnalysis.change_detection_strategy === 'run_comparison' ? <BranchesOutlined />
                      : <LineChartOutlined />
                    }
                    style={{ fontSize: 13, padding: '4px 12px', cursor: 'help' }}
                  >
                    {selectedAnalysis.change_detection_strategy === 'baseline' && 'Baseline'}
                    {selectedAnalysis.change_detection_strategy === 'rolling_window' && 'Rolling Window'}
                    {selectedAnalysis.change_detection_strategy === 'run_comparison' && 'Run Comparison'}
                    {!selectedAnalysis.change_detection_strategy && 'Baseline'}
                  </Tag>
                </Tooltip>
                {/* Strategy-specific indicators */}
                {selectedAnalysis.change_detection_strategy === 'baseline' && selectedAnalysis.started_at && (
                  (() => {
                    const startTime = dayjs(selectedAnalysis.started_at);
                    const baselinePeriod = 10; // minutes
                    
                    // For completed/stopped analyses, check if they ran long enough
                    if (selectedAnalysis.status === 'completed' || selectedAnalysis.status === 'stopped') {
                      const endTime = selectedAnalysis.stopped_at 
                        ? dayjs(selectedAnalysis.stopped_at) 
                        : dayjs();
                      const totalDuration = endTime.diff(startTime, 'minute');
                      const wasBaselineComplete = totalDuration >= baselinePeriod;
                      return (
                        <Tooltip title={wasBaselineComplete 
                          ? `Baseline was captured. Analysis ran for ${totalDuration} minutes.` 
                          : `Analysis stopped before baseline was complete (${totalDuration}/${baselinePeriod} min).`
                        }>
                          <Tag 
                            color={wasBaselineComplete ? 'success' : 'warning'}
                            icon={wasBaselineComplete ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                            style={{ fontSize: 11 }}
                          >
                            {wasBaselineComplete ? 'Baseline Ready' : 'Incomplete'}
                          </Tag>
                        </Tooltip>
                      );
                    }
                    
                    // For running analyses, show live progress
                    const elapsed = dayjs().diff(startTime, 'minute');
                    const isBaselineComplete = elapsed >= baselinePeriod;
                    return (
                      <Tooltip title={isBaselineComplete 
                        ? `Baseline captured (first ${baselinePeriod} min). Now detecting drift.` 
                        : `Building baseline: ${elapsed}/${baselinePeriod} min. Detection starts after baseline completes.`
                      }>
                        <Tag 
                          color={isBaselineComplete ? 'success' : 'processing'}
                          icon={isBaselineComplete ? <CheckCircleOutlined /> : <FieldTimeOutlined />}
                          style={{ fontSize: 11 }}
                        >
                          {isBaselineComplete ? 'Baseline Ready' : `${Math.max(0, baselinePeriod - elapsed)}m left`}
                        </Tag>
                      </Tooltip>
                    );
                  })()
                )}
                {selectedAnalysis.change_detection_strategy === 'rolling_window' && selectedAnalysis.status === 'running' && (
                  <Tooltip title="Comparing last 5 min vs previous 5 min. Updates every detection cycle (60s).">
                    <Tag color="processing" icon={<SyncOutlined spin />} style={{ fontSize: 11 }}>
                      Live
                    </Tag>
                  </Tooltip>
                )}
                {selectedAnalysis.change_detection_strategy === 'run_comparison' && runs.length > 0 && (
                  <Tooltip title={`${runs.length} run(s) available for comparison. Use "Compare Runs" tab.`}>
                    <Tag icon={<SyncOutlined />} style={{ fontSize: 11, color: '#667eea', borderColor: '#667eea', background: 'rgba(102, 126, 234, 0.1)' }}>
                      {runs.length} runs
                    </Tag>
                  </Tooltip>
                )}
              </Space>
            </Col>
          )}
          {selectedAnalysis && selectedAnalysis.change_detection_enabled === false && (
            <Col>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Change Detection</Text>
              <Tag color="default" icon={<PauseCircleOutlined />} style={{ fontSize: 13, padding: '4px 12px' }}>
                Disabled
              </Tag>
            </Col>
          )}
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Time Range</Text>
            <RangePicker
              showTime
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              presets={[
                { label: 'Last Hour', value: [dayjs().subtract(1, 'hour'), dayjs()] },
                { label: 'Last 24 Hours', value: [dayjs().subtract(24, 'hour'), dayjs()] },
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day'), dayjs()] },
              ]}
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right', paddingTop: 22 }}>
            <Space>
              <Button 
                icon={<ReloadOutlined />} 
                onClick={handleRefresh}
                loading={isChangesLoading}
              >
                Refresh
              </Button>
              <Dropdown 
                menu={{ items: exportMenuItems }} 
                disabled={!changesData || changesData.changes.length === 0}
              >
                <Button icon={<DownloadOutlined />}>
                  Export Report
                </Button>
              </Dropdown>
            </Space>
          </Col>
        </Row>
        
        {/* Quick & Saved Filters */}
        {selectedAnalysisId && (
          <Row style={{ marginTop: 12 }}>
            <Col span={24}>
              <Space wrap>
                <Text type="secondary">Quick filters:</Text>
                <SavedFilters
                  onApplyFilter={handleApplyFilter}
                  currentFilter={{
                    changeTypes: selectedChangeTypes as any,
                    riskLevels: selectedRiskLevels as any,
                    changedBy: changedByFilter,
                    minAffectedServices: minAffectedFilter,
                    namespaces: namespaceFilter,
                  }}
                  availableNamespaces={availableNamespaces}
                  availableChangedBy={availableChangedBy}
                />
                
                {/* Anomaly Filter - Primary toggle */}
                <Divider type="vertical" />
                <Tooltip title="Anomalies are operational events (errors, retransmits, traffic spikes) - NOT actual infrastructure changes. Toggle to show/hide.">
                  <Space size={4}>
                    <Switch 
                      size="small"
                      checked={!hideAnomalies}
                      onChange={(checked) => {
                        const showAnomalies = checked;
                        setHideAnomalies(!showAnomalies);
                        // If hiding anomalies and Anomalies card is selected, clear the selection
                        if (!showAnomalies && activeStatFilter === 'anomalies') {
                          setActiveStatFilter(null);
                          setSelectedChangeTypes([]);
                        }
                      }}
                    />
                    <Text style={{ fontSize: 12, fontWeight: hideAnomalies ? 'normal' : 'bold' }}>
                      Show Anomalies {!hideAnomalies && `(${anomalyCount})`}
                    </Text>
                  </Space>
                </Tooltip>
                
                {/* Noise Filter Toggles - Only show when anomalies are visible */}
                {!hideAnomalies && (
                  <>
                    <Divider type="vertical" />
                    <Text type="secondary" style={{ fontSize: 11 }}>Anomaly Filters:</Text>
                    <Tooltip title="K8s internal service discovery DNS queries (*.svc.cluster.local)">
                      <Space size={4}>
                        <Switch 
                          size="small"
                          checked={hideInternalDns}
                          onChange={setHideInternalDns}
                        />
                        <Text style={{ fontSize: 11 }}>Internal DNS</Text>
                      </Space>
                    </Tooltip>
                    <Tooltip title="Normal system processes (python, bash, sleep, etc.)">
                      <Space size={4}>
                        <Switch 
                          size="small"
                          checked={hideNormalProcesses}
                          onChange={setHideNormalProcesses}
                        />
                        <Text style={{ fontSize: 11 }}>Normal Processes</Text>
                      </Space>
                    </Tooltip>
                    <Tooltip title="TCP retransmit errors (normal packet loss recovery, not critical)">
                      <Space size={4}>
                        <Switch 
                          size="small"
                          checked={hideRetransmitErrors}
                          onChange={setHideRetransmitErrors}
                        />
                        <Text style={{ fontSize: 11 }}>Retransmit Errors</Text>
                      </Space>
                    </Tooltip>
                  </>
                )}
              </Space>
            </Col>
          </Row>
        )}
        
        {/* Active Filters Bar - only show when user has actively set filters
            Exclude 'total' stat card since it represents the default unfiltered view */}
        {(selectedChangeTypes.length > 0 || selectedRiskLevels.length > 0 || 
          changedByFilter || namespaceFilter.length > 0 || 
          (!hideAnomalies && (hideInternalDns || hideNormalProcesses || hideRetransmitErrors)) || 
          (activeStatFilter && activeStatFilter !== 'total')) && (
          <Row style={{ marginTop: 8 }}>
            <Col span={24}>
              <Space wrap size={[4, 4]}>
                <Text type="secondary" style={{ fontSize: 12 }}>Active filters:</Text>
                
                {activeStatFilter && (
                  <Tag 
                    closable 
                    onClose={() => {
                      setActiveStatFilter(null);
                      setSelectedChangeTypes([]);
                      setSelectedRiskLevels([]);
                    }}
                    color="geekblue"
                  >
                    {activeStatFilter === 'total' ? 'All Changes' :
                     activeStatFilter === 'infrastructure' ? 'Infrastructure' :
                     activeStatFilter === 'connections' ? 'Connections' :
                     activeStatFilter === 'anomalies' ? 'Anomalies' :
                     activeStatFilter === 'critical' ? 'Critical' :
                     activeStatFilter === 'high' ? 'High Risk' : activeStatFilter}
                  </Tag>
                )}
                
                {/* Only show individual change types if no stat filter is active */}
                {!activeStatFilter && selectedChangeTypes.map(type => (
                  <Tag 
                    key={type}
                    closable 
                    onClose={() => setSelectedChangeTypes(prev => prev.filter(t => t !== type))}
                    color="blue"
                  >
                    {changeTypeConfig[type]?.label || type}
                  </Tag>
                ))}
                
                {/* Only show individual risk levels if no stat filter is active */}
                {!activeStatFilter && selectedRiskLevels.map(level => (
                  <Tag 
                    key={level}
                    closable 
                    onClose={() => setSelectedRiskLevels(prev => prev.filter(l => l !== level))}
                    color="orange"
                  >
                    Risk: {level}
                  </Tag>
                ))}
                
                {changedByFilter && (
                  <Tag closable onClose={() => setChangedByFilter(undefined)} color="cyan">
                    Changed by: {changedByFilter}
                  </Tag>
                )}
                
                {namespaceFilter.map(ns => (
                  <Tag 
                    key={ns}
                    closable 
                    onClose={() => setNamespaceFilter(prev => prev.filter(n => n !== ns))}
                    color="green"
                  >
                    Namespace: {ns}
                  </Tag>
                ))}
                
                {/* Show anomaly-related tags only when anomalies are visible */}
                {!hideAnomalies && hideInternalDns && (
                  <Tag closable onClose={() => setHideInternalDns(false)} color="purple">
                    Internal DNS hidden
                  </Tag>
                )}
                
                {!hideAnomalies && hideNormalProcesses && (
                  <Tag closable onClose={() => setHideNormalProcesses(false)} color="purple">
                    Normal Processes hidden
                  </Tag>
                )}
                
                {!hideAnomalies && hideRetransmitErrors && (
                  <Tag closable onClose={() => setHideRetransmitErrors(false)} color="purple">
                    Retransmit Errors hidden
                  </Tag>
                )}
                
                <Button 
                  type="link" 
                  size="small" 
                  danger
                  onClick={handleClearAllFilters}
                >
                  Clear All
                </Button>
              </Space>
            </Col>
          </Row>
        )}
      </Card>

      {/* Summary Stats - Clickable for filtering */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {/* Changes - Infrastructure + Connections (NOT anomalies) */}
        <Col span={4}>
          <Tooltip title="Infrastructure and Connection changes. Enable 'Show Anomalies' to see operational events.">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('total')}
              style={{ 
                cursor: 'pointer',
                border: activeStatFilter === 'total' ? '2px solid #b89b5d' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Changes</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <SwapOutlined style={{ color: '#b89b5d', fontSize: 20 }} />
                    <span style={{ fontSize: 24, fontWeight: 600 }}>
                      {animatedTotalChanges.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
        
        {/* Infrastructure Changes */}
        <Col span={4}>
          <Tooltip title="Click to filter infrastructure changes">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('infrastructure')}
              style={{ 
                cursor: 'pointer',
                border: activeStatFilter === 'infrastructure' ? '2px solid #0891b2' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
                    <CloudServerOutlined style={{ color: '#0891b2', marginRight: 4 }} />Infrastructure
                  </Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 24, fontWeight: 600, color: infrastructureCount > 0 ? '#0891b2' : undefined }}>
                      {animatedInfrastructure.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
        
        {/* Connection Changes */}
        <Col span={4}>
          <Tooltip title="Click to filter connection changes">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('connections')}
              style={{ 
                cursor: 'pointer',
                border: activeStatFilter === 'connections' ? '2px solid #4d9f7c' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
                    <WifiOutlined style={{ color: '#4d9f7c', marginRight: 4 }} />Connections
                  </Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 24, fontWeight: 600, color: connectionCount > 0 ? '#4d9f7c' : undefined }}>
                      {animatedConnections.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
        
        {/* Anomalies - Highlighted */}
        <Col span={4}>
          <Tooltip title="Click to filter anomalies">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('anomalies')}
              style={{ 
                cursor: 'pointer',
                background: anomalyCount > 0
                  ? isDark
                    ? 'linear-gradient(135deg, rgba(212, 117, 106, 0.18) 0%, rgba(212, 117, 106, 0.08) 100%)'
                    : 'linear-gradient(135deg, #fff2e8 0%, #fff7e6 100%)'
                  : undefined,
                borderLeft: anomalyCount > 0 ? '3px solid #d4756a' : undefined,
                border: activeStatFilter === 'anomalies' ? '2px solid #d4756a' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
                    <AlertOutlined style={{ color: '#d4756a', marginRight: 4 }} />Anomalies
                  </Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 24, fontWeight: anomalyCount > 0 ? 600 : 400, color: anomalyCount > 0 ? '#d4756a' : undefined }}>
                      {animatedAnomalies.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
        
        {/* Critical */}
        <Col span={4}>
          <Tooltip title="Click to filter critical changes">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('critical')}
              style={{ 
                cursor: 'pointer',
                border: activeStatFilter === 'critical' ? '2px solid #cf1322' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Critical</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ExclamationCircleOutlined style={{ color: criticalCount > 0 ? '#cf1322' : '#8c8c8c', fontSize: 20 }} />
                    <span style={{ fontSize: 24, fontWeight: 600, color: criticalCount > 0 ? '#cf1322' : undefined }}>
                      {animatedCritical.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
        
        {/* High Risk */}
        <Col span={4}>
          <Tooltip title="Click to filter high risk changes">
            <Card 
              bordered={false}
              hoverable
              onClick={() => handleStatCardClick('high')}
              style={{ 
                cursor: 'pointer',
                border: activeStatFilter === 'high' ? '2px solid #c75450' : undefined,
              }}
            >
              {isChangesLoading && !changesData ? (
                <Skeleton.Input active size="small" style={{ width: 100, marginTop: 8 }} block />
              ) : (
                <div>
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>High Risk</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <WarningOutlined style={{ color: highCount > 0 ? '#c75450' : '#8c8c8c', fontSize: 20 }} />
                    <span style={{ fontSize: 24, fontWeight: 600, color: highCount > 0 ? '#c75450' : undefined }}>
                      {animatedHigh.toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </Card>
          </Tooltip>
        </Col>
      </Row>

      {/* Comparison Cards */}
      {comparison && (
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card 
              title={<Space><ClockCircleOutlined /> Before (Start of Period)</Space>}
              bordered={false}
              size="small"
            >
              <Row gutter={16}>
                <Col span={8}>
                  <Tooltip title="Active workloads in the cluster at the start of the analysis period">
                    <div>
                      <Statistic title="Workloads" value={comparison.before?.workloads || 0} prefix={<CloudServerOutlined />} />
                    </div>
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title="Active service-to-service connections. Shows 0 if no communication data is available yet.">
                    <div>
                      <Statistic title="Connections" value={comparison.before?.connections || 0} prefix={<ApiOutlined />} />
                    </div>
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title="Kubernetes namespaces being monitored in this cluster">
                    <div>
                      <Statistic title="Namespaces" value={comparison.before?.namespaces || 0} />
                    </div>
                  </Tooltip>
                </Col>
              </Row>
            </Card>
          </Col>
          <Col span={12}>
            <Card 
              title={<Space><ClockCircleOutlined /> After (End of Period)</Space>}
              bordered={false}
              size="small"
            >
              <Row gutter={16}>
                <Col span={8}>
                  <Tooltip title="Current active workloads. Difference from 'Before' shows workloads added or removed.">
                    <div>
                      <Statistic 
                        title="Workloads" 
                        value={comparison.after?.workloads || 0} 
                        prefix={<CloudServerOutlined />}
                        suffix={
                          comparison.after?.workloads !== comparison.before?.workloads && (
                            <Text style={{ fontSize: 12, color: (comparison.after?.workloads || 0) > (comparison.before?.workloads || 0) ? '#4d9f7c' : '#c75450' }}>
                              ({(comparison.after?.workloads || 0) > (comparison.before?.workloads || 0) ? '+' : ''}{(comparison.after?.workloads || 0) - (comparison.before?.workloads || 0)})
                            </Text>
                          )
                        }
                      />
                    </div>
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title="Current service-to-service connections. Difference shows new connections established.">
                    <div>
                      <Statistic 
                        title="Connections" 
                        value={comparison.after?.connections || 0} 
                        prefix={<ApiOutlined />}
                        suffix={
                          comparison.after?.connections !== comparison.before?.connections && (
                            <Text style={{ fontSize: 12, color: '#4d9f7c' }}>
                              (+{(comparison.after?.connections || 0) - (comparison.before?.connections || 0)})
                            </Text>
                          )
                        }
                      />
                    </div>
                  </Tooltip>
                </Col>
                <Col span={8}>
                  <Tooltip title="Current monitored namespaces in the cluster">
                    <div>
                      <Statistic title="Namespaces" value={comparison.after?.namespaces || 0} />
                    </div>
                  </Tooltip>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>
      )}

      {/* Critical Changes Alert */}
      {criticalCount > 0 && (
        <Alert
          message="Critical Changes Detected"
          description={`${criticalCount} critical change(s) require immediate attention. These changes may significantly impact service availability.`}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" danger onClick={() => setActiveTab('table')}>
              Review Now
            </Button>
          }
        />
      )}

      {/* Main Content */}
      <Card bordered={false}>
        {!selectedAnalysisId ? (
          <Empty 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" align="center">
                <Text strong>No Analysis Selected</Text>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  Select an analysis from the dropdown above to view its change detection history
                </Text>
              </Space>
            }
          />
        ) : isChangesError ? (
          <Alert
            type="error"
            message="Failed to Load Changes"
            description={
              <span>
                Unable to fetch change data. Please try refreshing or check your network connection.
                {changesError && (
                  <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                    Error: {JSON.stringify(changesError)}
                  </Text>
                )}
              </span>
            }
            showIcon
            action={
              <Button size="small" onClick={handleRefresh}>
                Retry
              </Button>
            }
          />
        ) : isChangesLoading && !changesData ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading changes...</Text>
          </div>
        ) : (
          <Tabs activeKey={activeTab} onChange={setActiveTab}>
            <Tabs.TabPane
              tab={<span><ClockCircleOutlined /> Timeline</span>}
              key="timeline"
            >
              {timelineItems.length > 0 ? (
                <>
                  <Timeline items={timelineItems} />
                  {totalChanges > pagination.pageSize && (
                    <div style={{ textAlign: 'center', marginTop: 16 }}>
                      <Space>
                        <Button 
                          disabled={pagination.current <= 1}
                          onClick={() => setPagination(p => ({ ...p, current: p.current - 1 }))}
                        >
                          Previous
                        </Button>
                        <Text type="secondary">
                          Page {pagination.current} of {Math.ceil(totalChanges / pagination.pageSize)} ({totalChanges} total)
                        </Text>
                        <Button 
                          disabled={pagination.current >= Math.ceil(totalChanges / pagination.pageSize)}
                          onClick={() => setPagination(p => ({ ...p, current: p.current + 1 }))}
                        >
                          Next
                        </Button>
                      </Space>
                    </div>
                  )}
                </>
              ) : (
                <Empty 
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Space direction="vertical" align="center">
                      {/* Debug info: Show if there's a mismatch between stats and actual data */}
                      {stats?.total_changes && stats.total_changes > 0 && changes.length === 0 ? (
                        <>
                          <Text type="warning" strong>
                            <ExclamationCircleOutlined /> Data Loading Issue
                          </Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Stats show {stats.total_changes} changes but no data was returned.
                          </Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            This may be a data format issue. Try refreshing or check backend logs.
                          </Text>
                        </>
                      ) : changes.length > 0 && filteredChanges.length === 0 ? (
                        <>
                          <Text type="warning">
                            <FilterOutlined /> All {changes.length} items are filtered
                          </Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {hideAnomalies && anomaliesInData > 0 && realChangesInData === 0
                              ? `${anomaliesInData} anomalies are hidden. Anomalies are operational events, not changes.`
                              : hideAnomalies && anomaliesInData > 0 && realChangesInData > 0
                              ? `${anomaliesInData} anomalies hidden + ${realChangesInData} changes filtered by other filters.`
                              : 'Items are hidden by active filters.'}
                          </Text>
                          <Space style={{ marginTop: 8 }} wrap>
                            {hideAnomalies && anomaliesInData > 0 && <Tag color="orange" closable onClose={() => setHideAnomalies(false)}>Anomalies hidden ({anomaliesInData})</Tag>}
                            {!hideAnomalies && hideInternalDns && <Tag closable onClose={() => setHideInternalDns(false)}>Internal DNS hidden</Tag>}
                            {!hideAnomalies && hideNormalProcesses && <Tag closable onClose={() => setHideNormalProcesses(false)}>Normal Processes hidden</Tag>}
                            {!hideAnomalies && hideRetransmitErrors && <Tag closable onClose={() => setHideRetransmitErrors(false)}>Retransmit Errors hidden</Tag>}
                          </Space>
                        </>
                      ) : (
                        <>
                          <Text>No changes detected in this time range</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {selectedChangeTypes.length > 0 || selectedRiskLevels.length > 0 
                              ? 'Try adjusting your filters or expanding the time range'
                              : 'Changes will appear here when detected by the analysis'}
                          </Text>
                        </>
                      )}
                    </Space>
                  }
                >
                  {(selectedChangeTypes.length > 0 || selectedRiskLevels.length > 0) && (
                    <Button type="primary" onClick={handleClearAllFilters}>
                      Clear Filters
                    </Button>
                  )}
                  {changes.length > 0 && filteredChanges.length === 0 && (
                    <Space style={{ marginTop: 8 }}>
                      {/* Show anomalies toggle if they are hidden */}
                      {hideAnomalies && anomaliesInData > 0 && (
                        <Button 
                          type="default"
                          onClick={() => setHideAnomalies(false)}
                        >
                          Show Anomalies ({anomaliesInData})
                        </Button>
                      )}
                      {/* Clear all filters button - shows EVERYTHING including anomalies */}
                      <Button 
                        type="primary" 
                        onClick={() => {
                          // Clear ALL filters to show everything (including anomalies)
                          setHideAnomalies(false);
                          setHideInternalDns(false);
                          setHideNormalProcesses(false);
                          setHideRetransmitErrors(false);
                          setChangedByFilter(undefined);
                          setMinAffectedFilter(undefined);
                          setMaxAffectedFilter(undefined);
                          setNamespaceFilter([]);
                          setSelectedChangeTypes([]);
                          setSelectedRiskLevels([]);
                          setActiveStatFilter(null);
                          message.info('All filters cleared - showing all items');
                        }}
                      >
                        Show All ({changes.length})
                      </Button>
                    </Space>
                  )}
                </Empty>
              )}
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><SwapOutlined /> Table View ({totalChanges})</span>}
              key="table"
            >
              <Table
                dataSource={filteredChanges}
                columns={columns}
                loading={isChangesLoading}
                pagination={{ 
                  current: pagination.current,
                  pageSize: pagination.pageSize,
                  total: totalChanges,
                  showTotal: (total) => `Total ${total} changes`,
                  showSizeChanger: true,
                  pageSizeOptions: ['10', '20', '50', '100'],
                }}
                onChange={handleTableChange}
                size="middle"
                locale={{ 
                  emptyText: (
                    <Empty 
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <Space direction="vertical" align="center">
                          {/* Debug info: Show detailed reason for empty table */}
                          {stats?.total_changes && stats.total_changes > 0 && changes.length === 0 ? (
                            <>
                              <Text type="warning" strong>
                                <ExclamationCircleOutlined /> Data Mismatch Detected
                              </Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                Server reports {stats.total_changes} changes but none were loaded.
                              </Text>
                              <Button 
                                type="link" 
                                onClick={handleRefresh}
                                style={{ marginTop: 4 }}
                              >
                                Try Refreshing
                              </Button>
                            </>
                          ) : changes.length > 0 && filteredChanges.length === 0 ? (
                            <>
                              <Text type="warning">
                                <FilterOutlined /> {changes.length} items hidden by filters
                              </Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {hideAnomalies && anomaliesInData > 0 && realChangesInData === 0
                                  ? `${anomaliesInData} anomalies are hidden. They are operational events, not changes.`
                                  : hideAnomalies && anomaliesInData > 0 && realChangesInData > 0
                                  ? `${anomaliesInData} anomalies hidden + ${realChangesInData} changes filtered by other filters.`
                                  : 'Items are hidden by active filters.'}
                              </Text>
                              <Space style={{ marginTop: 8 }}>
                                {/* Show anomalies toggle if they are hidden */}
                                {hideAnomalies && anomaliesInData > 0 && (
                                  <Button 
                                    type="default" 
                                    size="small"
                                    onClick={() => setHideAnomalies(false)}
                                  >
                                    Show Anomalies ({anomaliesInData})
                                  </Button>
                                )}
                                {/* Clear all filters button - shows EVERYTHING including anomalies */}
                                <Button 
                                  type="primary" 
                                  size="small"
                                  onClick={() => {
                                    // Clear ALL filters to show everything (including anomalies)
                                    setHideAnomalies(false);
                                    setHideInternalDns(false);
                                    setHideNormalProcesses(false);
                                    setHideRetransmitErrors(false);
                                    setChangedByFilter(undefined);
                                    setMinAffectedFilter(undefined);
                                    setMaxAffectedFilter(undefined);
                                    setNamespaceFilter([]);
                                    setSelectedChangeTypes([]);
                                    setSelectedRiskLevels([]);
                                    setActiveStatFilter(null);
                                    message.info('All filters cleared - showing all items');
                                  }}
                                >
                                  Show All ({changes.length})
                                </Button>
                              </Space>
                            </>
                          ) : (
                            <>
                              <Text>No changes match your current filters</Text>
                              {(selectedChangeTypes.length > 0 || selectedRiskLevels.length > 0) && (
                                <Button type="link" onClick={handleClearAllFilters}>
                                  Clear filters to see all changes
                                </Button>
                              )}
                            </>
                          )}
                        </Space>
                      }
                    />
                  ) 
                }}
                onRow={(record) => ({
                  onClick: () => handleRowClick(record),
                  style: { cursor: 'pointer' },
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><FilterOutlined /> By Type</span>}
              key="byType"
            >
              {(() => {
                const hasActiveFilters = selectedChangeTypes.length > 0 || selectedRiskLevels.length > 0;
                return (
                  <Collapse defaultActiveKey={Object.keys(changeTypeConfig)}>
                    {Object.entries(changeTypeConfig).map(([type, config]) => {
                      const isAnomalyType = ANOMALY_TYPES.includes(type);
                      if (hideAnomalies && isAnomalyType) return null;
                      
                      const typeChanges = filteredChanges.filter((c: Change) => c.change_type === type);
                      const serverCount = stats?.by_type?.[type] || 0;
                      const displayCount = hasActiveFilters ? typeChanges.length : Math.max(typeChanges.length, serverCount);
                      if (displayCount === 0) return null;
                      
                      return (
                        <Panel 
                          header={
                            <Space>
                              <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
                              <Badge 
                                count={displayCount} 
                                style={{ backgroundColor: config.color }} 
                                showZero={false}
                              />
                            </Space>
                          }
                          key={type}
                        >
                          <Table
                            dataSource={typeChanges}
                            columns={columns.filter(c => c.key !== 'change_type')}
                            pagination={typeChanges.length > 10 ? { pageSize: 10 } : false}
                            size="small"
                            onRow={(record) => ({
                              onClick: () => handleRowClick(record),
                              style: { cursor: 'pointer' },
                            })}
                          />
                          {!hasActiveFilters && serverCount > typeChanges.length && typeChanges.length > 0 && (
                            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                              Showing {typeChanges.length} of {serverCount} total
                            </Text>
                          )}
                        </Panel>
                      );
                    })}
                  </Collapse>
                );
              })()}
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><BarChartOutlined /> Analytics</span>}
              key="analytics"
            >
              <ChangeAnalytics
                changes={filteredChanges}
                stats={stats}
                comparison={comparison}
                dateRange={dateRange}
                loading={isChangesLoading}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><SwapOutlined /> Compare Snapshots</span>}
              key="compare"
            >
              <div style={{ marginBottom: 16 }}>
                <Space>
                  <Text>Compare with analysis:</Text>
                  <Select
                    placeholder="Select analysis to compare"
                    style={{ width: 280 }}
                    value={compareAnalysisId}
                    onChange={setCompareAnalysisId}
                    allowClear
                  >
                    {availableAnalyses
                      .filter((a: Analysis) => a.id !== selectedAnalysisId)
                      .map((analysis: Analysis) => (
                        <Option key={analysis.id} value={analysis.id}>
                          #{analysis.id} - {analysis.name}
                        </Option>
                      ))}
                  </Select>
                </Space>
              </div>
              {compareAnalysisId ? (
                <SnapshotComparison
                  data={snapshotComparisonData}
                  loading={isComparisonLoading}
                />
              ) : (
                <Empty description="Select an analysis to compare with the current one" />
              )}
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={
                <span>
                  <SyncOutlined /> Compare Runs
                  {runs.length > 1 && (
                    <Badge 
                      count={runs.length} 
                      size="small" 
                      style={{ marginLeft: 8, backgroundColor: '#667eea' }} 
                      showZero={false}
                    />
                  )}
                </span>
              }
              key="compare-runs"
              disabled={runs.length < 2}
            >
              {runs.length < 2 ? (
                <Empty 
                  description={
                    <span>
                      <Text>This analysis needs at least 2 runs to compare.</Text>
                      <br />
                      <Text type="secondary">Current runs: {runs.length}</Text>
                    </span>
                  }
                />
              ) : (
                <>
                  <Alert
                    message="Compare Changes Between Runs"
                    description="Select two runs of this analysis to see what changed between them. Useful for deployment validation, A/B testing, or tracking drift over time."
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  <Row gutter={16} style={{ marginBottom: 16 }}>
                    <Col span={8}>
                      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Run A (Earlier)</Text>
                      <Select
                        placeholder="Select first run"
                        style={{ width: '100%' }}
                        value={runA}
                        onChange={setRunA}
                        loading={isRunsLoading}
                      >
                        {runs
                          .filter((r: AnalysisRun) => r.run_number !== runB)
                          .map((run: AnalysisRun) => (
                            <Option key={run.run_number} value={run.run_number}>
                              <Space>
                                <Badge 
                                  status={run.status === 'running' ? 'processing' : run.status === 'completed' ? 'success' : 'default'} 
                                />
                                Run #{run.run_number}
                                {run.start_time && (
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    {dayjs(run.start_time).format('MM/DD HH:mm')}
                                  </Text>
                                )}
                              </Space>
                            </Option>
                          ))}
                      </Select>
                    </Col>
                    <Col span={8}>
                      <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Run B (Later)</Text>
                      <Select
                        placeholder="Select second run"
                        style={{ width: '100%' }}
                        value={runB}
                        onChange={setRunB}
                        loading={isRunsLoading}
                      >
                        {runs
                          .filter((r: AnalysisRun) => r.run_number !== runA)
                          .map((run: AnalysisRun) => (
                            <Option key={run.run_number} value={run.run_number}>
                              <Space>
                                <Badge 
                                  status={run.status === 'running' ? 'processing' : run.status === 'completed' ? 'success' : 'default'} 
                                />
                                Run #{run.run_number}
                                {run.start_time && (
                                  <Text type="secondary" style={{ fontSize: 11 }}>
                                    {dayjs(run.start_time).format('MM/DD HH:mm')}
                                  </Text>
                                )}
                              </Space>
                            </Option>
                          ))}
                      </Select>
                    </Col>
                    <Col span={8} style={{ display: 'flex', alignItems: 'flex-end' }}>
                      <Button 
                        type="primary" 
                        icon={<SwapOutlined />}
                        onClick={() => {
                          // Swap runs
                          const temp = runA;
                          setRunA(runB);
                          setRunB(temp);
                        }}
                        disabled={!runA || !runB}
                      >
                        Swap Runs
                      </Button>
                    </Col>
                  </Row>
                  
                  {runA && runB ? (
                    isRunComparisonLoading ? (
                      <div style={{ textAlign: 'center', padding: 40 }}>
                        <Spin size="large" />
                        <Text style={{ display: 'block', marginTop: 16 }}>Comparing runs...</Text>
                      </div>
                    ) : isRunComparisonError ? (
                      <Alert
                        type="error"
                        message="Failed to compare runs"
                        description={
                          runComparisonError && 'data' in runComparisonError 
                            ? String((runComparisonError as { data?: { detail?: string } }).data?.detail || 'Unknown error occurred')
                            : 'Failed to fetch comparison data. Please try again.'
                        }
                        showIcon
                      />
                    ) : runComparisonData ? (
                      <>
                        {/* Comparison Summary Cards */}
                        <Row gutter={16} style={{ marginBottom: 16 }}>
                          <Col span={6}>
                            <Card bordered={false} style={{ background: isDark ? 'rgba(8, 145, 178, 0.15)' : '#e6f7ff', borderLeft: '3px solid #0891b2' }}>
                              <Statistic
                                title={<><SyncOutlined style={{ color: '#0891b2' }} /> Run #{runA}</>}
                                value={runComparisonData.comparison.total_in_run_a}
                                suffix="changes"
                                valueStyle={{ color: '#0891b2' }}
                              />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {runComparisonData.run_a.start_time && dayjs(runComparisonData.run_a.start_time).format('MM/DD HH:mm')}
                              </Text>
                            </Card>
                          </Col>
                          <Col span={6}>
                            <Card bordered={false} style={{ background: isDark ? 'rgba(77, 159, 124, 0.15)' : '#f6ffed', borderLeft: '3px solid #4d9f7c' }}>
                              <Statistic
                                title={<><SyncOutlined style={{ color: '#4d9f7c' }} /> Run #{runB}</>}
                                value={runComparisonData.comparison.total_in_run_b}
                                suffix="changes"
                                valueStyle={{ color: '#4d9f7c' }}
                              />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {runComparisonData.run_b.start_time && dayjs(runComparisonData.run_b.start_time).format('MM/DD HH:mm')}
                              </Text>
                            </Card>
                          </Col>
                          <Col span={6}>
                            <Card bordered={false} style={{ background: isDark ? 'rgba(184, 155, 93, 0.15)' : '#fff2e8', borderLeft: '3px solid #b89b5d' }}>
                              <Statistic
                                title={<><PlusCircleOutlined style={{ color: '#b89b5d' }} /> New in Run #{runB}</>}
                                value={runComparisonData.comparison.only_in_run_b}
                                suffix="changes"
                                valueStyle={{ color: '#b89b5d' }}
                              />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                Not present in Run #{runA}
                              </Text>
                            </Card>
                          </Col>
                          <Col span={6}>
                            <Card bordered={false} style={{ background: isDark ? 'rgba(199, 84, 80, 0.15)' : '#fff1f0', borderLeft: '3px solid #c75450' }}>
                              <Statistic
                                title={<><MinusCircleOutlined style={{ color: '#c75450' }} /> Gone from #{runA}</>}
                                value={runComparisonData.comparison.only_in_run_a}
                                suffix="changes"
                                valueStyle={{ color: '#c75450' }}
                              />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                Not present in Run #{runB}
                              </Text>
                            </Card>
                          </Col>
                        </Row>

                        {/* Detailed Changes Tabs */}
                        <Tabs defaultActiveKey="new">
                          <Tabs.TabPane 
                            tab={
                              <span style={{ color: '#b89b5d' }}>
                                <PlusCircleOutlined /> New in Run #{runB} ({runComparisonData.changes_only_in_b.length})
                              </span>
                            } 
                            key="new"
                          >
                            {runComparisonData.changes_only_in_b.length > 0 ? (
                              <Table
                                dataSource={runComparisonData.changes_only_in_b}
                                rowKey={(r: RunComparisonChange) => `${r.change_type}-${r.target_namespace}-${r.target_name}`}
                                size="small"
                                pagination={{ pageSize: 10 }}
                                columns={[
                                  {
                                    title: 'Type',
                                    dataIndex: 'change_type',
                                    key: 'type',
                                    width: 150,
                                    render: (type: string) => {
                                      const config = changeTypeConfig[type as ChangeType];
                                      return config ? (
                                        <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
                                      ) : (
                                        <Tag>{type}</Tag>
                                      );
                                    }
                                  },
                                  {
                                    title: 'Target',
                                    key: 'target',
                                    render: (_: unknown, record: RunComparisonChange) => (
                                      <Text>{record.target_namespace}/{record.target_name}</Text>
                                    )
                                  },
                                  {
                                    title: 'Risk',
                                    dataIndex: 'risk_level',
                                    key: 'risk',
                                    width: 100,
                                    render: (risk: string) => (
                                      <Tag color={riskLevelConfig[risk as RiskLevel]?.color}>{risk}</Tag>
                                    )
                                  },
                                  {
                                    title: 'Details',
                                    dataIndex: 'details',
                                    key: 'details',
                                    ellipsis: true
                                  }
                                ]}
                              />
                            ) : (
                              <Empty description={`No new changes in Run #${runB}`} />
                            )}
                          </Tabs.TabPane>
                          <Tabs.TabPane 
                            tab={
                              <span style={{ color: '#c75450' }}>
                                <MinusCircleOutlined /> Gone from Run #{runA} ({runComparisonData.changes_only_in_a.length})
                              </span>
                            } 
                            key="gone"
                          >
                            {runComparisonData.changes_only_in_a.length > 0 ? (
                              <Table
                                dataSource={runComparisonData.changes_only_in_a}
                                rowKey={(r: RunComparisonChange) => `${r.change_type}-${r.target_namespace}-${r.target_name}`}
                                size="small"
                                pagination={{ pageSize: 10 }}
                                columns={[
                                  {
                                    title: 'Type',
                                    dataIndex: 'change_type',
                                    key: 'type',
                                    width: 150,
                                    render: (type: string) => {
                                      const config = changeTypeConfig[type as ChangeType];
                                      return config ? (
                                        <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
                                      ) : (
                                        <Tag>{type}</Tag>
                                      );
                                    }
                                  },
                                  {
                                    title: 'Target',
                                    key: 'target',
                                    render: (_: unknown, record: RunComparisonChange) => (
                                      <Text>{record.target_namespace}/{record.target_name}</Text>
                                    )
                                  },
                                  {
                                    title: 'Risk',
                                    dataIndex: 'risk_level',
                                    key: 'risk',
                                    width: 100,
                                    render: (risk: string) => (
                                      <Tag color={riskLevelConfig[risk as RiskLevel]?.color}>{risk}</Tag>
                                    )
                                  },
                                  {
                                    title: 'Details',
                                    dataIndex: 'details',
                                    key: 'details',
                                    ellipsis: true
                                  }
                                ]}
                              />
                            ) : (
                              <Empty description={`No changes from Run #${runA} are missing in Run #${runB}`} />
                            )}
                          </Tabs.TabPane>
                          <Tabs.TabPane 
                            tab={
                              <span style={{ color: '#4d9f7c' }}>
                                <CheckCircleOutlined /> Common ({runComparisonData.common_changes.length})
                              </span>
                            } 
                            key="common"
                          >
                            {runComparisonData.common_changes.length > 0 ? (
                              <Table
                                dataSource={runComparisonData.common_changes}
                                rowKey={(r: RunComparisonChange) => `${r.change_type}-${r.target_namespace}-${r.target_name}`}
                                size="small"
                                pagination={{ pageSize: 10 }}
                                columns={[
                                  {
                                    title: 'Type',
                                    dataIndex: 'change_type',
                                    key: 'type',
                                    width: 150,
                                    render: (type: string) => {
                                      const config = changeTypeConfig[type as ChangeType];
                                      return config ? (
                                        <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
                                      ) : (
                                        <Tag>{type}</Tag>
                                      );
                                    }
                                  },
                                  {
                                    title: 'Target',
                                    key: 'target',
                                    render: (_: unknown, record: RunComparisonChange) => (
                                      <Text>{record.target_namespace}/{record.target_name}</Text>
                                    )
                                  },
                                  {
                                    title: 'Risk',
                                    dataIndex: 'risk_level',
                                    key: 'risk',
                                    width: 100,
                                    render: (risk: string) => (
                                      <Tag color={riskLevelConfig[risk as RiskLevel]?.color}>{risk}</Tag>
                                    )
                                  },
                                  {
                                    title: 'Details',
                                    dataIndex: 'details',
                                    key: 'details',
                                    ellipsis: true
                                  }
                                ]}
                              />
                            ) : (
                              <Empty description="No common changes between the runs" />
                            )}
                          </Tabs.TabPane>
                        </Tabs>
                      </>
                    ) : (
                      <Empty description="Error loading comparison data" />
                    )
                  ) : (
                    <Empty description="Select two runs to compare" />
                  )}
                </>
              )}
            </Tabs.TabPane>
          </Tabs>
        )}
      </Card>

      {/* Change Type Legend */}
      <Card bordered={false} style={{ marginTop: 16 }} size="small">
        <Space wrap>
          <Text strong>Change Types:</Text>
          {Object.entries(changeTypeConfig).map(([key, config]) => (
            <Tag 
              key={key} 
              color={config.color} 
              icon={config.icon}
              style={{ cursor: 'pointer' }}
              onClick={() => {
                if (selectedChangeTypes.includes(key)) {
                  setSelectedChangeTypes(selectedChangeTypes.filter(t => t !== key));
                } else {
                  setSelectedChangeTypes([...selectedChangeTypes, key]);
                }
              }}
            >
              {config.label}
            </Tag>
          ))}
        </Space>
      </Card>

      {/* Change Detail Drawer */}
      <ChangeDetailDrawer
        changeId={selectedChangeId}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setSelectedChangeId(null);
        }}
        onViewRelated={(changeId) => {
          setSelectedChangeId(changeId);
        }}
      />
    </div>
  );
};

export default ChangeDetection;
