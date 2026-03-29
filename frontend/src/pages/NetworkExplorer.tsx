import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { 
  Card, 
  Typography, 
  Space, 
  Select, 
  Tabs, 
  Table, 
  Tag, 
  Row, 
  Col,
  Statistic,
  Input,
  Badge,
  Spin,
  Empty,
  Button,
  DatePicker,
  message,
  Tooltip,
  Switch,
  Modal,
  Descriptions,
  theme
} from 'antd';
import { useTheme } from '../contexts/ThemeContext';
import type { FilterValue, SorterResult, TablePaginationConfig } from 'antd/es/table/interface';
import { 
  ApiOutlined,
  GlobalOutlined,
  CloudServerOutlined,
  LockOutlined,
  SearchOutlined,
  SwapOutlined,
  ReloadOutlined,
  DownloadOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
  GroupOutlined,
  UnorderedListOutlined,
  ExclamationCircleOutlined,
  AlertOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { useGetDependencyGraphQuery, useGetCommunicationStatsQuery, useGetErrorStatsQuery } from '../store/api/communicationApi';
import { 
  useGetEventStatsQuery,
  useGetDnsQueriesQuery, 
  useGetSniEventsQuery,
  useGetBindEventsQuery,
  useGetNetworkFlowsQuery,
  DnsQueryEvent,
  SniEvent,
  BindEvent,
  NetworkFlowEvent
} from '../store/api/eventsApi';
import { useGetErrorAnomalySummaryQuery } from '../store/api/changesApi';
import { Analysis } from '../types';
import { ClusterBadge } from '../components/Common';
import { useAnimatedCounter } from '../hooks/useAnimatedCounter';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

// Protocol colors
const protocolColors: Record<string, string> = {
  'TCP': '#f97316',
  'UDP': '#ec4899',
  'HTTP': '#3b82f6',
  'HTTPS': '#22c55e',
  'GRPC': '#8b5cf6',
  'DNS': '#06b6d4',
};

// DNS response code colors
const dnsResponseColors: Record<string, string> = {
  'NOERROR': '#4d9f7c',
  'NXDOMAIN': '#c75450',
  'SERVFAIL': '#b89b5d',
  'REFUSED': '#f76e6e',
  'TIMEOUT': '#8c8c8c',
};

// TLS version colors
const tlsVersionColors: Record<string, string> = {
  'TLS 1.3': '#4d9f7c',
  'TLS 1.2': '#0891b2',
  'TLS 1.1': '#b89b5d',
  'TLS 1.0': '#c75450',
  'SSL 3.0': '#cf1322',
};

const NetworkExplorer: React.FC = () => {
  const { token } = theme.useToken();
  const { isDark } = useTheme();
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedClusterIds, setSelectedClusterIds] = useState<number[]>([]); // Multi-cluster filter
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState('');
  // Server-side search: debounced search term for API calls (min 3 chars)
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  
  // Debounce searchTerm for API calls (300ms delay, min 3 chars)
  // This prevents API calls on every keystroke - only triggers after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      // Only search if 3+ characters (prevents expensive operations for short inputs)
      if (searchTerm.length >= 3) {
        setDebouncedSearchTerm(searchTerm);
      } else {
        setDebouncedSearchTerm('');
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);
  
  const [activeTab, setActiveTab] = useState('flows');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 1000 });
  const [groupByConnection, setGroupByConnection] = useState(false); // Group unique connections
  
  // Column filters state - for each tab
  const [flowsColumnFilters, setFlowsColumnFilters] = useState<Record<string, FilterValue | null>>({});
  const [servicesColumnFilters, setServicesColumnFilters] = useState<Record<string, FilterValue | null>>({});
  const [dnsColumnFilters, setDnsColumnFilters] = useState<Record<string, FilterValue | null>>({});
  const [sniColumnFilters, setSniColumnFilters] = useState<Record<string, FilterValue | null>>({});
  
  // Detail modal state
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<any>(null);
  const [selectedRecordType, setSelectedRecordType] = useState<'flow' | 'service' | 'dns' | 'sni'>('flow');

  // Table onChange handlers for each tab
  const handleFlowsTableChange = useCallback((
    _pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    _sorter: SorterResult<any> | SorterResult<any>[]
  ) => {
    setFlowsColumnFilters(filters);
  }, []);

  const handleServicesTableChange = useCallback((
    _pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    _sorter: SorterResult<any> | SorterResult<any>[]
  ) => {
    setServicesColumnFilters(filters);
  }, []);

  const handleDnsTableChange = useCallback((
    _pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    _sorter: SorterResult<any> | SorterResult<any>[]
  ) => {
    setDnsColumnFilters(filters);
  }, []);

  const handleSniTableChange = useCallback((
    _pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    _sorter: SorterResult<any> | SorterResult<any>[]
  ) => {
    setSniColumnFilters(filters);
  }, []);

  // Reset pagination to page 1 when search term changes
  useEffect(() => {
    setPagination(prev => ({ ...prev, current: 1 }));
  }, [debouncedSearchTerm]);

  // Client-side search helper - fallback filter after server-side search
  // This ensures UI always shows correct results even if server returns unfiltered data
  const matchesSearch = useCallback((searchTerm: string, ...values: (string | number | undefined | null)[]): boolean => {
    if (!searchTerm || searchTerm.length < 3) return true;
    const searchLower = searchTerm.toLowerCase().trim();
    return values.some(v => {
      if (v === null || v === undefined) return false;
      return String(v).toLowerCase().includes(searchLower);
    });
  }, []);

  // API queries
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  // Create cluster lookup map for O(1) access
  const clusterInfoMap = useMemo(() => {
    const map: Record<number, any> = {};
    clusters.forEach((c: any) => { map[c.id] = c; });
    return {
      get: (id: number | string) => {
        const numId = typeof id === 'string' ? parseInt(id, 10) : id;
        return map[numId];
      }
    };
  }, [clusters]);
  
  // Fetch ALL analyses (no cluster filter) - user selects analysis first
  const { data: analyses = [], isLoading: isAnalysesLoading } = useGetAnalysesQuery({});
  
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  // Get selected analysis details
  const selectedAnalysis = useMemo(() => {
    if (!selectedAnalysisId || !analyses.length) return null;
    return (Array.isArray(analyses) ? analyses : []).find(
      (a: Analysis) => a.id === selectedAnalysisId
    ) || null;
  }, [selectedAnalysisId, analyses]);

  // Check if this is a multi-cluster analysis
  const isMultiClusterAnalysis = useMemo(() => {
    return selectedAnalysis?.is_multi_cluster || 
           (selectedAnalysis?.cluster_ids && selectedAnalysis.cluster_ids.length > 1);
  }, [selectedAnalysis]);

  // Get all cluster IDs for this analysis
  const analysisClusterIds = useMemo(() => {
    if (!selectedAnalysis) return [];
    return selectedAnalysis.cluster_ids || [selectedAnalysis.cluster_id];
  }, [selectedAnalysis]);

  // Handle analysis change - set analysis ID and clear cluster (useEffect will set correct cluster)
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    // Always clear clusterId immediately - useEffect will set the correct one
    // This prevents race condition where old clusterId is used with new analysisId
    setSelectedClusterId(undefined);
    setSelectedClusterIds([]);
  }, []);

  // Auto-set cluster when analysis changes (separate effect to avoid stale closure)
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        const clusterIds = analysis.cluster_ids || [analysis.cluster_id];
        if (clusterIds.length === 1) {
          setSelectedClusterId(clusterIds[0]);
          setSelectedClusterIds(clusterIds);
        } else {
          // Multi-cluster - show all by default
          setSelectedClusterIds(clusterIds);
          setSelectedClusterId(clusterIds[0]); // Primary for API calls
        }
      }
    }
  }, [selectedAnalysisId, analyses]);

  // Memoize query params to prevent unnecessary re-fetches
  const queryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    // Server-side search - filters at the database level for accurate results
    search: debouncedSearchTerm || undefined,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: pagination.pageSize,
    offset: (pagination.current - 1) * pagination.pageSize,
  }), [selectedClusterId, selectedAnalysisId, debouncedSearchTerm, dateRange, pagination]);

  // Memoize graph query params separately (no pagination)
  const graphQueryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
  }), [selectedClusterId, selectedAnalysisId, dateRange]);

  const { data: graphData, isLoading: isGraphLoading, refetch: refetchGraph } = useGetDependencyGraphQuery(
    graphQueryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: stats } = useGetCommunicationStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );
  
  // Categorized error statistics (NO LIMIT - accurate counts)
  const { data: errorStats } = useGetErrorStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Error anomaly summary from change detection
  const { data: errorAnomalySummary } = useGetErrorAnomalySummaryQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: eventStats } = useGetEventStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // DNS queries - use separate params without flows pagination
  const dnsQueryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    search: debouncedSearchTerm || undefined,  // Server-side search
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: 1000,  // DNS has its own limit
    offset: 0,
  }), [selectedClusterId, selectedAnalysisId, debouncedSearchTerm, dateRange]);

  const { data: dnsData, isLoading: isDnsLoading, refetch: refetchDns } = useGetDnsQueriesQuery(
    dnsQueryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // SNI/TLS events - use separate params without flows pagination
  const sniQueryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    search: debouncedSearchTerm || undefined,  // Server-side search
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: 1000,  // SNI has its own limit
    offset: 0,
  }), [selectedClusterId, selectedAnalysisId, debouncedSearchTerm, dateRange]);

  const { data: sniData, isLoading: isSniLoading, refetch: refetchSni } = useGetSniEventsQuery(
    sniQueryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Bind events (listening ports) - use separate params
  const bindQueryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    search: debouncedSearchTerm || undefined,  // Server-side search
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: 1000,
    offset: 0,
  }), [selectedClusterId, selectedAnalysisId, debouncedSearchTerm, dateRange]);

  const { data: bindData, isLoading: isBindLoading, refetch: refetchBind } = useGetBindEventsQuery(
    bindQueryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Network flows from ClickHouse (time range supported)
  const { data: networkFlowsData, isLoading: isFlowsLoading, refetch: refetchFlows } = useGetNetworkFlowsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Dynamic filter values - computed from actual data
  // Unique namespaces from flows data
  const uniqueFlowNamespaces = useMemo(() => {
    if (!networkFlowsData?.events) return [];
    const nsSet = new Set<string>();
    networkFlowsData.events.forEach(e => {
      if (e.namespace) nsSet.add(e.namespace);
      if (e.source_namespace) nsSet.add(e.source_namespace);
      if (e.dest_namespace) nsSet.add(e.dest_namespace);
    });
    return Array.from(nsSet).filter(Boolean).sort().map(ns => ({ text: ns, value: ns }));
  }, [networkFlowsData]);

  // Unique ports from flows data (top 20)
  const uniqueFlowPorts = useMemo(() => {
    if (!networkFlowsData?.events) return [];
    const portSet = new Set<number>();
    networkFlowsData.events.forEach(e => {
      if (e.dest_port && typeof e.dest_port === 'number') portSet.add(e.dest_port);
    });
    return Array.from(portSet).sort((a, b) => a - b).slice(0, 20)
      .map(p => ({ text: String(p), value: p }));
  }, [networkFlowsData]);

  // Unique sources from flows data (top 30) - for Source column filter
  const uniqueFlowSources = useMemo(() => {
    if (!networkFlowsData?.events) return [];
    const sourceSet = new Set<string>();
    networkFlowsData.events.forEach(e => {
      const source = e.pod || e.source_ip;
      if (source) sourceSet.add(source);
    });
    return Array.from(sourceSet).sort().slice(0, 30)
      .map(s => ({ text: s, value: s }));
  }, [networkFlowsData]);

  // Unique targets from flows data (top 30) - for Target column filter
  const uniqueFlowTargets = useMemo(() => {
    if (!networkFlowsData?.events) return [];
    const targetSet = new Set<string>();
    networkFlowsData.events.forEach(e => {
      if (e.dest_ip) targetSet.add(e.dest_ip);
    });
    return Array.from(targetSet).sort().slice(0, 30)
      .map(t => ({ text: t, value: t }));
  }, [networkFlowsData]);

  // Unique namespaces from services/bind data
  const uniqueServiceNamespaces = useMemo(() => {
    if (!bindData?.events) return [];
    const nsSet = new Set<string>();
    bindData.events.forEach(e => {
      if (e.namespace) nsSet.add(e.namespace);
    });
    return Array.from(nsSet).filter(Boolean).sort().map(ns => ({ text: ns, value: ns }));
  }, [bindData]);

  // Unique ports from SNI/TLS data
  const uniqueSniPorts = useMemo(() => {
    if (!sniData?.events) return [];
    const portSet = new Set<number>();
    sniData.events.forEach(e => {
      const port = e.dest_port ?? e.dst_port;
      if (port && typeof port === 'number') portSet.add(port);
    });
    return Array.from(portSet).sort((a, b) => a - b).slice(0, 15)
      .map(p => ({ text: String(p), value: p }));
  }, [sniData]);

  // Process flows data from ClickHouse (time-based data)
  const flowsData = useMemo(() => {
    let rawFlows: any[] = [];
    
    // Primary: Use ClickHouse network_flows (supports time range filtering)
    // Server-side search + client-side fallback for guaranteed accuracy
    if (networkFlowsData?.events?.length) {
      rawFlows = networkFlowsData.events
        // Apply cluster filter first
        .filter((flow: NetworkFlowEvent) => {
          // Multi-cluster filter
          if (isMultiClusterAnalysis && selectedClusterIds.length > 0 && selectedClusterIds.length < analysisClusterIds.length) {
            const flowClusterId = typeof flow.cluster_id === 'string' ? parseInt(flow.cluster_id, 10) : flow.cluster_id;
            if (!selectedClusterIds.includes(flowClusterId)) return false;
          }
          return true;
        })
        .map((flow: NetworkFlowEvent, idx: number) => ({
          key: idx,
          cluster_id: flow.cluster_id,  // Include cluster_id for multi-cluster display
          source: flow.pod || flow.source_ip || '-',
          sourceNs: flow.namespace || '-',
          target: flow.dest_ip || '-',
          targetNs: '-',
          protocol: flow.protocol || 'TCP',
          port: flow.dest_port || '-',
          requestCount: 1,
          errorCount: (flow as any).error_count || 0,
          retransmitCount: (flow as any).retransmit_count || 0,
          lastErrorType: (flow as any).error_type || '',
          bytesTransferred: (flow.bytes_sent || 0) + (flow.bytes_received || 0),
          _sourceIp: flow.source_ip || '',
          _targetIp: flow.dest_ip || '',
          timestamp: flow.timestamp,
          direction: flow.direction,
        }));
    } else if (graphData?.edges) {
      // Fallback: Use Neo4j graph edges (aggregate data, no time filtering)
      rawFlows = graphData.edges
        .map((edge, idx) => {
          const sourceNode = graphData.nodes.find(n => n.id === edge.source_id);
          const targetNode = graphData.nodes.find(n => n.id === edge.target_id);
          return {
            key: idx,
            source: sourceNode?.name || edge.source_id,
            sourceNs: sourceNode?.namespace || '-',
            target: targetNode?.name || edge.target_id,
            targetNs: targetNode?.namespace || '-',
            protocol: edge.protocol || 'TCP',
            port: edge.port || '-',
            requestCount: edge.request_count || 0,
            errorCount: edge.error_count || 0,
            retransmitCount: edge.retransmit_count || 0,
            lastErrorType: edge.last_error_type || '',
            bytesTransferred: (edge as any).bytes_transferred || 0,
            _sourceIp: sourceNode?.ip,
            _targetIp: targetNode?.ip,
          };
        });
    }

    // Client-side search filter - filters on DISPLAYED values (source, target)
    // This ensures users see only matching rows based on what's visible in the table
    if (debouncedSearchTerm && debouncedSearchTerm.length >= 3) {
      rawFlows = rawFlows.filter((flow) => 
        matchesSearch(debouncedSearchTerm,
          flow.source, flow.target, flow.sourceNs, flow.targetNs,
          flow.protocol, flow.port, flow._sourceIp, flow._targetIp
        )
      );
    }

    // Group by unique connections if enabled
    if (groupByConnection && rawFlows.length > 0) {
      const groupMap = new Map<string, any>();
      
      rawFlows.forEach((flow) => {
        const key = `${flow.source}|${flow.target}|${flow.protocol}|${flow.port}`;
        const existing = groupMap.get(key);
        
        if (existing) {
          existing.requestCount += flow.requestCount || 1;
          existing.errorCount += flow.errorCount || 0;
          existing.bytesTransferred += flow.bytesTransferred || 0;
          if (flow.timestamp > existing.timestamp) {
            existing.timestamp = flow.timestamp;
          }
        } else {
          groupMap.set(key, { ...flow, key });
        }
      });
      
      return Array.from(groupMap.values());
    }
    
    return rawFlows;
  }, [networkFlowsData, graphData, groupByConnection, isMultiClusterAnalysis, selectedClusterIds, analysisClusterIds, debouncedSearchTerm, matchesSearch]);

  // Process services/bind data
  const servicesData = useMemo(() => {
    // Priority 1: Use bind events if available (most accurate service data)
    if (bindData?.events && bindData.events.length > 0) {
      const bindMap = new Map<string, {
        key: string;
        pod: string;
        namespace: string;
        ports: number[];
        protocols: Set<string>;
        bindCount: number;
        lastSeen: string;
        comm: string;
      }>();

      bindData.events.forEach((event: BindEvent) => {
        const key = `${event.pod}`;
        const existing = bindMap.get(key);
        
        if (existing) {
          if (!existing.ports.includes(event.bind_port)) {
            existing.ports.push(event.bind_port);
          }
          existing.protocols.add(event.protocol);
          existing.bindCount++;
          if (event.timestamp > existing.lastSeen) {
            existing.lastSeen = event.timestamp;
          }
        } else {
          bindMap.set(key, {
            key,
            pod: event.pod,
            namespace: event.namespace,
            ports: [event.bind_port],
            protocols: new Set([event.protocol]),
            bindCount: 1,
            lastSeen: event.timestamp,
            comm: event.comm,
          });
        }
      });

      return Array.from(bindMap.values()).map(s => ({
        ...s,
        protocols: Array.from(s.protocols),
      }));
    }
    
    // Priority 2: Derive services from network_flows (destination targets with ports)
    if (networkFlowsData?.events && networkFlowsData.events.length > 0) {
      const serviceMap = new Map<string, {
        key: string;
        pod: string;
        name: string;
        namespace: string;
        ports: number[];
        protocols: Set<string>;
        bindCount: number;
        lastSeen: string;
        comm: string;
      }>();
      
      networkFlowsData.events.forEach((flow: NetworkFlowEvent, idx: number) => {
        // Services are destinations that have ports
        if (flow.dest_port && flow.dest_port > 0) {
          const destKey = flow.dest_pod || flow.dest_ip || `unknown-${idx}`;
          const existing = serviceMap.get(destKey);
          
          if (existing) {
            if (!existing.ports.includes(flow.dest_port)) {
              existing.ports.push(flow.dest_port);
            }
            existing.protocols.add(flow.protocol || 'TCP');
            existing.bindCount++;
            if (flow.timestamp && flow.timestamp > existing.lastSeen) {
              existing.lastSeen = flow.timestamp;
            }
          } else {
            serviceMap.set(destKey, {
              key: destKey,
              pod: flow.dest_pod || flow.dest_ip || '',
              name: flow.dest_pod || flow.dest_ip || '',
              namespace: flow.dest_namespace || '-',
              ports: [flow.dest_port],
              protocols: new Set([flow.protocol || 'TCP']),
              bindCount: 1,
              lastSeen: flow.timestamp || '',
              comm: '', // Not available from network flows
            });
          }
        }
      });
      
      return Array.from(serviceMap.values()).map(s => ({
        ...s,
        protocols: Array.from(s.protocols),
      }));
    }
    
    // Priority 3: Fallback to graph-based services
    if (graphData?.nodes && graphData.nodes.length > 0) {
      const services: any[] = [];
      graphData.nodes.forEach((node, idx) => {
        const nodePorts = new Set<number>();
        graphData.edges.forEach(edge => {
          if (edge.target_id === node.id && edge.port) {
            nodePorts.add(edge.port);
          }
        });
        if (nodePorts.size > 0) {
          services.push({
            key: idx,
            name: node.name,
            pod: node.name,
            namespace: node.namespace || 'default',
            ports: Array.from(nodePorts),
            protocols: ['TCP'],
            protocol: 'TCP',
            connections: graphData.edges.filter(e => e.target_id === node.id).length,
            bindCount: 0,
            lastSeen: '',
            comm: '',
          });
        }
      });
      return services;
    }
    
    return [];
  }, [bindData?.events, networkFlowsData?.events, graphData]);

  // NOTE: Services data uses bind events which are filtered server-side
  // Client-side filtering no longer needed for search
  const filteredServicesData = useMemo(() => {
    if (!servicesData.length) return [];
    
    // Client-side search fallback for services
    if (debouncedSearchTerm && debouncedSearchTerm.length >= 3) {
      return servicesData.filter((s: any) => 
        matchesSearch(debouncedSearchTerm,
          s.pod, s.name, s.namespace, s.comm,
          ...(s.ports || []).map(String),
          ...(s.protocols || [])
        )
      );
    }
    return servicesData;
  }, [servicesData, debouncedSearchTerm, matchesSearch]);

  // Filter DNS queries using specific search
  const filteredDnsQueries = useMemo(() => {
    if (!dnsData?.queries) return [];
    
    // Server-side search + client-side fallback for guaranteed accuracy
    const filtered = dnsData.queries
      .filter((e: DnsQueryEvent) => {
        // Multi-cluster filter
        if (isMultiClusterAnalysis && selectedClusterIds.length > 0 && selectedClusterIds.length < analysisClusterIds.length) {
          const eventClusterId = typeof e.cluster_id === 'string' ? parseInt(e.cluster_id, 10) : e.cluster_id;
          if (!selectedClusterIds.includes(eventClusterId)) return false;
        }
        // Client-side search fallback
        if (debouncedSearchTerm && debouncedSearchTerm.length >= 3) {
          return matchesSearch(debouncedSearchTerm,
            e.query_name, e.dns_server_ip, e.pod, e.namespace,
            e.query_type, e.response_code, ...(e.response_ips || [])
          );
        }
        return true;
      })
      .map((e: DnsQueryEvent) => ({
        key: `${e.timestamp}-${e.pod}-${e.query_name}`,
        ...e,
        queryCount: 1,
      }));

    // Group by unique DNS queries if enabled
    if (groupByConnection && filtered.length > 0) {
      const groupMap = new Map<string, any>();
      
      filtered.forEach((query) => {
        const key = `${query.pod}|${query.query_name}|${query.query_type}`;
        const existing = groupMap.get(key);
        
        if (existing) {
          existing.queryCount += 1;
          // Keep latest response info
          if (query.timestamp > existing.timestamp) {
            existing.timestamp = query.timestamp;
            existing.response_code = query.response_code;
            existing.response_ips = query.response_ips;
            existing.latency_ms = query.latency_ms;
          }
          // Track average latency
          existing._totalLatency = (existing._totalLatency || existing.latency_ms || 0) + (query.latency_ms || 0);
          existing._latencyCount = (existing._latencyCount || 1) + 1;
          existing.avg_latency_ms = existing._totalLatency / existing._latencyCount;
        } else {
          groupMap.set(key, { ...query, key, _totalLatency: query.latency_ms || 0, _latencyCount: 1 });
        }
      });
      
      return Array.from(groupMap.values());
    }
    
    return filtered;
  }, [dnsData?.queries, groupByConnection, isMultiClusterAnalysis, selectedClusterIds, analysisClusterIds, debouncedSearchTerm, matchesSearch]);

  // Filter SNI events using specific search
  const filteredSniEvents = useMemo(() => {
    if (!sniData?.events) return [];
    
    // Server-side search + client-side fallback for guaranteed accuracy
    const filtered = sniData.events
      .filter((e: SniEvent) => {
        // Multi-cluster filter
        if (isMultiClusterAnalysis && selectedClusterIds.length > 0 && selectedClusterIds.length < analysisClusterIds.length) {
          const eventClusterId = typeof e.cluster_id === 'string' ? parseInt(e.cluster_id, 10) : e.cluster_id;
          if (!selectedClusterIds.includes(eventClusterId)) return false;
        }
        // Client-side search fallback
        if (debouncedSearchTerm && debouncedSearchTerm.length >= 3) {
          const sniName = e.server_name || e.sni_name || '';
          const destIp = e.dest_ip || e.dst_ip || '';
          const destPort = e.dest_port ?? e.dst_port;
          return matchesSearch(debouncedSearchTerm,
            e.pod, e.namespace, sniName, destIp, destPort,
            e.tls_version, e.cipher_suite, e.comm
          );
        }
        return true;
      })
      .map((e: SniEvent) => ({
        key: `${e.timestamp}-${e.pod}-${e.server_name || e.sni_name}`,
        ...e,
        connectionCount: 1,
      }));

    // Group by unique TLS connections if enabled
    if (groupByConnection && filtered.length > 0) {
      const groupMap = new Map<string, any>();
      
      filtered.forEach((sni) => {
        const sniName = sni.server_name || sni.sni_name || '';
        const destIp = sni.dest_ip || sni.dst_ip || '';
        const destPort = sni.dest_port || sni.dst_port || '';
        const key = `${sni.pod}|${sniName}|${destIp}:${destPort}`;
        const existing = groupMap.get(key);
        
        if (existing) {
          existing.connectionCount += 1;
          // Keep latest timestamp
          if (sni.timestamp > existing.timestamp) {
            existing.timestamp = sni.timestamp;
          }
        } else {
          groupMap.set(key, { ...sni, key });
        }
      });
      
      return Array.from(groupMap.values());
    }
    
    return filtered;
  }, [sniData?.events, groupByConnection, isMultiClusterAnalysis, selectedClusterIds, analysisClusterIds, debouncedSearchTerm, matchesSearch]);

  // ============================================
  // ANIMATED COUNTERS for Stats Cards
  // Values update with search/filter changes
  // ============================================
  const networkFlowsCount = searchTerm ? flowsData.length : (networkFlowsData?.total || eventStats?.event_counts?.network_flow || flowsData.length);
  const servicesCount = searchTerm ? filteredServicesData.length : (bindData?.total || servicesData.length);
  const dnsCount = searchTerm ? filteredDnsQueries.length : (dnsData?.total || eventStats?.event_counts?.dns_query || 0);
  const tlsCount = searchTerm ? filteredSniEvents.length : (sniData?.total || eventStats?.event_counts?.sni_event || 0);
  
  const animatedFlows = useAnimatedCounter(networkFlowsCount, 1200, !selectedAnalysisId);
  const animatedServices = useAnimatedCounter(servicesCount, 1200, !selectedAnalysisId);
  const animatedDns = useAnimatedCounter(dnsCount, 1200, !selectedAnalysisId);
  const animatedTls = useAnimatedCounter(tlsCount, 1200, !selectedAnalysisId);
  
  // Error calculation for animated counter with Critical/Warning categorization
  const { 
    totalErrors, 
    totalCritical, 
    totalWarnings, 
    criticalByType, 
    warningsByType, 
    errorHealthStatus, 
    errorHealthMessage,
    hasErrors, 
    hasCriticalErrors 
  } = useMemo(() => {
    // Helper to categorize error type
    const isCriticalError = (errorType: string): boolean => {
      const criticalPatterns = ['RESET', 'REFUSED', 'TIMEOUT', 'UNREACHABLE', 'ERROR', 'SOCKET'];
      return criticalPatterns.some(pattern => errorType.toUpperCase().includes(pattern));
    };
    
    // Use new errorStats endpoint (accurate counts, NO LIMIT)
    if (errorStats) {
      return {
        totalErrors: errorStats.total_errors,
        totalCritical: errorStats.total_critical,
        totalWarnings: errorStats.total_warnings,
        criticalByType: errorStats.critical_by_type || {},
        warningsByType: errorStats.warnings_by_type || {},
        errorHealthStatus: errorStats.health_status || 'healthy',
        errorHealthMessage: errorStats.health_message || '',
        hasErrors: errorStats.total_errors > 0,
        hasCriticalErrors: errorStats.total_critical > 0
      };
    }
    
    // Fallback to stats (limited sample) if errorStats not available
    if (stats) {
      return {
        totalErrors: stats.total_errors || 0,
        totalCritical: stats.total_critical || 0,
        totalWarnings: stats.total_warnings || 0,
        criticalByType: stats.critical_by_type || {},
        warningsByType: stats.warnings_by_type || {},
        errorHealthStatus: stats.error_health_status || 'healthy',
        errorHealthMessage: '',
        hasErrors: (stats.total_errors || 0) > 0,
        hasCriticalErrors: (stats.total_critical || 0) > 0
      };
    }
    
    // Final fallback to flowsData (limited)
    let total = 0;
    let critical = 0;
    let warnings = 0;
    const criticalTypes: Record<string, number> = {};
    const warningTypes: Record<string, number> = {};
    
    (flowsData as any[]).forEach((flow: any) => {
      const errorCount = flow.errorCount || 0;
      const retransmitCount = flow.retransmitCount || 0;
      const errorType = flow.lastErrorType || '';
      
      const combinedCount = errorCount + retransmitCount;
      total += combinedCount;
      
      if (combinedCount > 0 && errorType) {
        if (isCriticalError(errorType)) {
          critical += combinedCount;
          criticalTypes[errorType] = (criticalTypes[errorType] || 0) + combinedCount;
        } else {
          warnings += combinedCount;
          warningTypes[errorType] = (warningTypes[errorType] || 0) + combinedCount;
        }
      } else if (combinedCount > 0) {
        warnings += combinedCount;
      }
    });
    
    return { 
      totalErrors: total, 
      totalCritical: critical,
      totalWarnings: warnings,
      criticalByType: criticalTypes,
      warningsByType: warningTypes,
      errorHealthStatus: critical === 0 ? 'healthy' : critical < 10 ? 'good' : 'warning',
      errorHealthMessage: '',
      hasErrors: total > 0,
      hasCriticalErrors: critical > 0
    };
  }, [errorStats, stats, flowsData]);
  
  const animatedCritical = useAnimatedCounter(totalCritical, 1200, !selectedAnalysisId);
  const animatedWarnings = useAnimatedCounter(totalWarnings, 1200, !selectedAnalysisId);
  
  // Data transferred calculation for animated counter
  // Priority: 1. ClickHouse network_flows, 2. Neo4j stats, 3. Calculated from flowsData
  const totalBytesTransferred = useMemo(() => {
    // Try ClickHouse data first (most accurate, real-time)
    const clickhouseBytes = networkFlowsData?.events?.reduce((sum: number, flow: any) => 
      sum + (flow.bytes_sent || 0) + (flow.bytes_received || 0), 0) || 0;
    if (clickhouseBytes > 0) return clickhouseBytes;
    
    // Try Neo4j stats (aggregated from graph edges)
    if (stats?.total_bytes_transferred && stats.total_bytes_transferred > 0) {
      return stats.total_bytes_transferred;
    }
    
    // Fallback: Calculate from flowsData (derived from graphData edges)
    const flowsBytes = flowsData?.reduce((sum: number, flow: any) => 
      sum + (flow.bytesTransferred || 0), 0) || 0;
    
    return flowsBytes;
  }, [networkFlowsData?.events, stats?.total_bytes_transferred, flowsData]);
  
  const animatedBytes = useAnimatedCounter(Math.round(totalBytesTransferred / (1024 * 1024) * 100) / 100, 1200, !selectedAnalysisId);

  // Refresh handler
  const handleRefresh = useCallback(() => {
    refetchGraph();
    refetchDns();
    refetchSni();
    refetchBind();
    refetchFlows();
    message.success('Data refreshed');
  }, [refetchGraph, refetchDns, refetchSni, refetchBind, refetchFlows]);

  // Export handler - exports current tab data as CSV
  const handleExport = useCallback(() => {
    let data: any[] = [];
    let filename = '';
    let headers: string[] = [];
    
    // Helper to get cluster name from ID
    const getClusterName = (clusterId: string | number) => {
      const cluster = clusterInfoMap.get(clusterId);
      return cluster?.name || `Cluster ${clusterId}`;
    };

    switch (activeTab) {
      case 'flows':
        data = flowsData;
        filename = `network-flows-${dayjs().format('YYYY-MM-DD-HHmmss')}.csv`;
        headers = isMultiClusterAnalysis 
          ? ['Cluster', 'Source', 'Source Namespace', 'Target', 'Target Namespace', 'Protocol', 'Port', 'Flow Count', 'Errors', 'Bytes', 'Timestamp']
          : ['Source', 'Source Namespace', 'Target', 'Target Namespace', 'Protocol', 'Port', 'Flow Count', 'Errors', 'Bytes', 'Timestamp'];
        break;
      case 'services':
        data = filteredServicesData;
        filename = `services-${dayjs().format('YYYY-MM-DD-HHmmss')}.csv`;
        headers = isMultiClusterAnalysis
          ? ['Cluster', 'Pod', 'Namespace', 'Process', 'Ports', 'Protocols', 'Bind Count', 'Last Seen']
          : ['Pod', 'Namespace', 'Process', 'Ports', 'Protocols', 'Bind Count', 'Last Seen'];
        break;
      case 'dns':
        data = filteredDnsQueries;
        filename = `dns-queries-${dayjs().format('YYYY-MM-DD-HHmmss')}.csv`;
        headers = [
          isMultiClusterAnalysis ? 'Cluster' : '',
          'Timestamp', 'Pod', 'Namespace', 'Query Name', 'Query Type', 'Response Code', 'Response IPs', 'Latency (ms)', 'DNS Server', 
          groupByConnection ? 'Query Count' : ''
        ].filter(Boolean);
        break;
      case 'tls':
        data = filteredSniEvents;
        filename = `tls-connections-${dayjs().format('YYYY-MM-DD-HHmmss')}.csv`;
        headers = [
          isMultiClusterAnalysis ? 'Cluster' : '',
          'Timestamp', 'Pod', 'Namespace', 'SNI Name', 'Destination', 'TLS Version', 'Cipher Suite', 'Process', 
          groupByConnection ? 'Connection Count' : ''
        ].filter(Boolean);
        break;
    }

    if (data.length === 0) {
      message.warning('No data to export');
      return;
    }

    // Convert data to CSV rows
    const csvRows: string[] = [headers.join(',')];
    
    data.forEach((row) => {
      let values: string[] = [];
      const clusterName = isMultiClusterAnalysis ? `"${getClusterName(row.cluster_id)}"` : null;
      
      switch (activeTab) {
        case 'flows':
          values = [
            `"${row.source || ''}"`,
            `"${row.sourceNs || ''}"`,
            `"${row.target || ''}"`,
            `"${row.targetNs || ''}"`,
            row.protocol || '',
            String(row.port || ''),
            String(row.requestCount || 1),
            String(row.errorCount || 0),
            String(row.bytesTransferred || 0),
            row.timestamp || '',
          ];
          if (clusterName) values.unshift(clusterName);
          break;
        case 'services':
          values = [
            `"${row.pod || row.name || ''}"`,
            `"${row.namespace || ''}"`,
            `"${row.comm || ''}"`,
            `"${(row.ports || []).join('; ')}"`,
            `"${(row.protocols || [row.protocol]).join('; ')}"`,
            String(row.bindCount || ''),
            row.lastSeen || '',
          ];
          if (clusterName) values.unshift(clusterName);
          break;
        case 'dns':
          values = [
            row.timestamp || '',
            `"${row.pod || ''}"`,
            `"${row.namespace || ''}"`,
            `"${row.query_name || ''}"`,
            row.query_type || '',
            row.response_code || '',
            `"${(row.response_ips || []).join('; ')}"`,
            String(row.latency_ms || ''),
            row.dns_server_ip || '',
          ];
          if (groupByConnection) values.push(String(row.queryCount || 1));
          if (clusterName) values.unshift(clusterName);
          break;
        case 'tls':
          const sniName = row.server_name || row.sni_name || '';
          const destIp = row.dest_ip || row.dst_ip || '';
          const destPort = row.dest_port || row.dst_port || '';
          values = [
            row.timestamp || '',
            `"${row.pod || ''}"`,
            `"${row.namespace || ''}"`,
            `"${sniName}"`,
            `${destIp}:${destPort}`,
            row.tls_version || '',
            `"${row.cipher_suite || ''}"`,
            `${row.comm || ''} (${row.pid || ''})`,
          ];
          if (groupByConnection) values.push(String(row.connectionCount || 1));
          if (clusterName) values.unshift(clusterName);
          break;
      }
      csvRows.push(values.join(','));
    });

    // Create and download file
    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    
    message.success(`Exported ${data.length} records to ${filename}`);
  }, [activeTab, flowsData, filteredServicesData, filteredDnsQueries, filteredSniEvents, groupByConnection, isMultiClusterAnalysis, clusterInfoMap]);

  // Flows table columns - dynamically include cluster column for multi-cluster analysis
  const flowColumns = useMemo(() => {
    const columns: any[] = [];
    
    // Add cluster column for multi-cluster analysis
    if (isMultiClusterAnalysis) {
      columns.push({
        title: 'Cluster',
        key: 'cluster',
        width: 200,
        minWidth: 180,
        ellipsis: false,
        render: (_: any, record: any) => {
          const cluster = clusterInfoMap.get(record.cluster_id);
          return cluster ? (
            <ClusterBadge
              clusterId={cluster.id}
              clusterName={cluster.name}
              environment={cluster.environment}
              provider={cluster.provider}
              size="small"
              showEnvironment={true}
              showProvider={false}
            />
          ) : (
            <Tag color="default">C{record.cluster_id}</Tag>
          );
        },
      });
    }
    
    columns.push(
      {
        title: 'Source',
        key: 'source',
        width: 220,
        filters: uniqueFlowSources,
        filteredValue: flowsColumnFilters.source || null,
        onFilter: (value: any, record: any) => record.source === value,
        ellipsis: true,
        render: (_: any, record: any) => (
          <div>
            <Text strong>{record.source}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{record.sourceNs}</Text>
          </div>
        ),
      },
      {
        title: '',
        key: 'arrow',
        width: 40,
        render: () => <SwapOutlined style={{ color: '#8c8c8c' }} />,
      },
      {
        title: 'Target',
        key: 'target',
        width: 180,
        filters: uniqueFlowTargets,
        filteredValue: flowsColumnFilters.target || null,
        onFilter: (value: any, record: any) => record.target === value,
        ellipsis: true,
        render: (_: any, record: any) => (
          <div>
            <Text strong>{record.target}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{record.targetNs}</Text>
          </div>
        ),
      },
      {
        title: 'Protocol',
        dataIndex: 'protocol',
        key: 'protocol',
        width: 105,
        filters: [
          { text: 'TCP', value: 'TCP' },
          { text: 'UDP', value: 'UDP' },
          { text: 'ICMP', value: 'ICMP' },
        ],
        filteredValue: flowsColumnFilters.protocol || null,
        onFilter: (value: any, record: any) => record.protocol === value,
        render: (protocol: string) => (
          <Tag color={protocolColors[protocol] || '#8c8c8c'}>{protocol}</Tag>
        ),
      },
      {
        title: 'Direction',
        dataIndex: 'direction',
        key: 'direction',
        width: 105,
        filters: [
          { text: 'Ingress', value: 'ingress' },
          { text: 'Egress', value: 'egress' },
        ],
        filteredValue: flowsColumnFilters.direction || null,
        onFilter: (value: any, record: any) => record.direction === value,
        render: (dir: string) => dir ? (
          <Tag color={dir === 'ingress' ? 'green' : 'blue'}>{dir}</Tag>
        ) : <Text type="secondary">-</Text>,
      },
      {
        title: 'Namespace',
        dataIndex: 'sourceNs',
        key: 'namespace',
        width: 160,
        filters: uniqueFlowNamespaces,
        filteredValue: flowsColumnFilters.namespace || null,
        onFilter: (value: any, record: any) => record.sourceNs === value,
        ellipsis: true,
      },
      {
        title: 'Port',
        dataIndex: 'port',
        key: 'port',
        width: 80,
        filters: uniqueFlowPorts,
        filteredValue: flowsColumnFilters.port || null,
        onFilter: (value: any, record: any) => record.port === value || record.port === String(value),
      },
      {
        title: 'Flows',
        dataIndex: 'requestCount',
        key: 'requestCount',
        width: 100,
        sorter: (a: any, b: any) => a.requestCount - b.requestCount,
        render: (count: number) => count.toLocaleString(),
      },
      {
        title: 'Errors',
        dataIndex: 'errorCount',
        key: 'errorCount',
        width: 120,
        filters: [
          { text: 'No Errors', value: 0 },
          { text: 'Has Errors', value: 'has_errors' },
          { text: 'Critical Only', value: 'critical' },
          { text: 'Warnings Only', value: 'warning' },
        ],
        filteredValue: flowsColumnFilters.errorCount || null,
        onFilter: (value: any, record: any) => {
          const errorType = record.lastErrorType || record.error_type || '';
          const isCritical = ['RESET', 'REFUSED', 'TIMEOUT', 'UNREACHABLE', 'ERROR', 'SOCKET']
            .some(pattern => errorType.toUpperCase().includes(pattern));
          
          if (value === 0) return !record.errorCount || record.errorCount === 0;
          if (value === 'has_errors') return record.errorCount > 0;
          if (value === 'critical') return record.errorCount > 0 && isCritical;
          if (value === 'warning') return record.errorCount > 0 && !isCritical;
          return true;
        },
        sorter: (a: any, b: any) => (a.errorCount || 0) - (b.errorCount || 0),
        render: (count: number, record: any) => {
          if (!count || count === 0) return <Text type="secondary">0</Text>;
          
          const errorType = record.lastErrorType || record.error_type || '';
          // Determine if this is a critical error or a warning (retransmit)
          const criticalPatterns = ['RESET', 'REFUSED', 'TIMEOUT', 'UNREACHABLE', 'ERROR', 'SOCKET'];
          const isCritical = criticalPatterns.some(pattern => errorType.toUpperCase().includes(pattern));
          
          const errorLabel = errorType ? errorType.replace(/_/g, ' ') : (isCritical ? 'Error' : 'Warning');
          const shortLabel = errorType === 'RETRANSMIT' || errorType.startsWith('RETRANSMIT_') 
            ? 'RTX' 
            : errorType === 'CONNECTION_RESET' 
              ? 'RST' 
              : errorType === 'TIMEOUT' 
                ? 'TO' 
                : '';
          
          return (
            <Tooltip 
              title={
                <div>
                  <div style={{ fontWeight: 500 }}>{count} {errorLabel.toLowerCase()}</div>
                  <div style={{ fontSize: 11, color: isCritical ? '#fca5a5' : '#fdba74' }}>
                    {isCritical ? 'Critical error - requires attention' : 'Warning - normal TCP behavior'}
                  </div>
                </div>
              }
            >
              <Tag 
                color={isCritical ? 'red' : 'orange'} 
                style={{ cursor: 'help' }}
              >
                {isCritical ? '!' : '~'} {count}{shortLabel ? ` ${shortLabel}` : ''}
              </Tag>
            </Tooltip>
          );
        },
      },
      {
        title: 'Data',
        dataIndex: 'bytesTransferred',
        key: 'bytesTransferred',
        width: 100,
        sorter: (a: any, b: any) => (a.bytesTransferred || 0) - (b.bytesTransferred || 0),
        render: (bytes: number) => {
          if (!bytes || bytes === 0) return <Text type="secondary">—</Text>;
          if (bytes < 1024) return `${bytes} B`;
          if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
          return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
        },
      }
    );
    
    return columns;
  }, [isMultiClusterAnalysis, clusterInfoMap, uniqueFlowNamespaces, uniqueFlowPorts, uniqueFlowSources, uniqueFlowTargets, flowsColumnFilters]);

  // Services table columns - with filters
  const serviceColumns = useMemo(() => [
    {
      title: 'Pod',
      key: 'pod',
      render: (_: any, record: any) => (
        <Space>
          <CloudServerOutlined style={{ color: '#0891b2' }} />
          <div>
            <Text strong>{record.pod || record.name}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{record.namespace}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Namespace',
      dataIndex: 'namespace',
      key: 'namespace',
      width: 140,
      filters: uniqueServiceNamespaces,
      filteredValue: servicesColumnFilters.namespace || null,
      onFilter: (value: any, record: any) => record.namespace === value,
      ellipsis: true,
    },
    {
      title: 'Process',
      dataIndex: 'comm',
      key: 'comm',
      width: 120,
      render: (comm: string) => comm ? <Text code>{comm}</Text> : '-',
    },
    {
      title: 'Listening Ports',
      dataIndex: 'ports',
      key: 'ports',
      render: (ports: number[]) => (
        <Space wrap>
          {(ports || []).slice(0, 5).map(port => (
            <Tag key={port} color="blue">{port}</Tag>
          ))}
          {ports?.length > 5 && <Tag>+{ports.length - 5} more</Tag>}
        </Space>
      ),
    },
    {
      title: 'Protocol',
      key: 'protocol',
      width: 120,
      filters: [
        { text: 'TCP', value: 'TCP' },
        { text: 'UDP', value: 'UDP' },
      ],
      filteredValue: servicesColumnFilters.protocol || null,
      onFilter: (value: any, record: any) => {
        const protocols = record.protocols || [record.protocol];
        return (Array.isArray(protocols) ? protocols : [protocols]).includes(value);
      },
      render: (_: any, record: any) => {
        const protocols = record.protocols || [record.protocol];
        return (
          <Space>
            {(Array.isArray(protocols) ? protocols : [protocols]).map((p: string) => (
              <Tag key={p} color={protocolColors[p] || '#8c8c8c'}>{p}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: 'Binds',
      dataIndex: 'bindCount',
      key: 'bindCount',
      width: 80,
      sorter: (a: any, b: any) => (a.bindCount || 0) - (b.bindCount || 0),
      render: (count: number) => count || '-',
    },
    {
      title: 'Last Seen',
      dataIndex: 'lastSeen',
      key: 'lastSeen',
      width: 160,
      sorter: (a: any, b: any) => dayjs(a.lastSeen).unix() - dayjs(b.lastSeen).unix(),
      render: (ts: string) => ts ? dayjs(ts).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
  ], [uniqueServiceNamespaces, servicesColumnFilters]);

  // DNS table columns - dynamically include queryCount when grouping and cluster for multi-cluster
  const dnsColumns = useMemo(() => {
    const columns: any[] = [];
    
    // Add cluster column for multi-cluster analysis
    if (isMultiClusterAnalysis) {
      columns.push({
        title: 'Cluster',
        key: 'cluster',
        width: 200,
        minWidth: 180,
        ellipsis: false,
        render: (_: any, record: DnsQueryEvent) => {
          const cluster = clusterInfoMap.get(record.cluster_id);
          return cluster ? (
            <ClusterBadge
              clusterId={cluster.id}
              clusterName={cluster.name}
              environment={cluster.environment}
              provider={cluster.provider}
              size="small"
              showEnvironment={true}
              showProvider={false}
            />
          ) : (
            <Tag color="default">C{record.cluster_id}</Tag>
          );
        },
      });
    }
    
    columns.push(
      {
        title: 'Timestamp',
        dataIndex: 'timestamp',
        key: 'timestamp',
        width: 160,
        render: (ts: string) => (
          <Space>
            <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
            <Text type="secondary">{dayjs(ts).format('HH:mm:ss.SSS')}</Text>
          </Space>
        ),
        sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
      },
      {
        title: 'Pod',
        key: 'pod',
        render: (_: any, record: DnsQueryEvent) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.pod}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
          </Space>
        ),
      },
      {
        title: 'Query',
        dataIndex: 'query_name',
        key: 'query_name',
        ellipsis: true,
        render: (name: string) => (
          <Tooltip title={name}>
            <Space>
              <GlobalOutlined style={{ color: '#06b6d4' }} />
              <Text strong>{name}</Text>
            </Space>
          </Tooltip>
        ),
      },
      {
        title: 'Type',
        dataIndex: 'query_type',
        key: 'query_type',
        width: 80,
        filters: [
          { text: 'A', value: 'A' },
          { text: 'AAAA', value: 'AAAA' },
          { text: 'CNAME', value: 'CNAME' },
          { text: 'MX', value: 'MX' },
          { text: 'SRV', value: 'SRV' },
          { text: 'TXT', value: 'TXT' },
        ],
        filteredValue: dnsColumnFilters.query_type || null,
        onFilter: (value: any, record: any) => record.query_type === value,
        render: (type: string) => <Tag>{type}</Tag>,
      },
      {
        title: 'Response',
        dataIndex: 'response_code',
        key: 'response_code',
        width: 120,
        filters: [
          { text: 'NOERROR', value: 'NOERROR' },
          { text: 'NXDOMAIN', value: 'NXDOMAIN' },
          { text: 'SERVFAIL', value: 'SERVFAIL' },
          { text: 'REFUSED', value: 'REFUSED' },
        ],
        filteredValue: dnsColumnFilters.response_code || null,
        onFilter: (value: any, record: any) => record.response_code === value,
        render: (code: string) => (
          <Tag color={dnsResponseColors[code] || '#8c8c8c'}>
            {code === 'NOERROR' ? <CheckCircleOutlined /> : <CloseCircleOutlined />} {code}
          </Tag>
        ),
      },
      {
        title: 'Response IPs',
        dataIndex: 'response_ips',
        key: 'response_ips',
        ellipsis: true,
        render: (ips: string[]) => (
          ips && ips.length > 0 ? (
            <Tooltip title={ips.join(', ')}>
              <Text code>{ips[0]}{ips.length > 1 ? ` +${ips.length - 1}` : ''}</Text>
            </Tooltip>
          ) : <Text type="secondary">-</Text>
        ),
      },
      {
        title: 'Latency',
        dataIndex: 'latency_ms',
        key: 'latency_ms',
        width: 115,
        filters: [
          { text: '< 50ms', value: 'fast' },
          { text: '50-100ms', value: 'medium' },
          { text: '> 100ms', value: 'slow' },
        ],
        filteredValue: dnsColumnFilters.latency_ms || null,
        onFilter: (value: any, record: any) => {
          const ms = record.latency_ms || 0;
          if (value === 'fast') return ms < 50;
          if (value === 'medium') return ms >= 50 && ms <= 100;
          if (value === 'slow') return ms > 100;
          return true;
        },
        sorter: (a: any, b: any) => (a.latency_ms || 0) - (b.latency_ms || 0),
        render: (ms: number, record: any) => {
          const displayMs = groupByConnection && record.avg_latency_ms ? record.avg_latency_ms : ms;
          const color = displayMs > 100 ? '#c75450' : displayMs > 50 ? '#b89b5d' : '#4d9f7c';
          return (
            <Tooltip title={groupByConnection ? 'Average latency' : 'Latency'}>
              <Text style={{ color }}>{displayMs?.toFixed(2) || '-'} ms</Text>
            </Tooltip>
          );
        },
      },
      {
        title: 'DNS Server',
        dataIndex: 'dns_server_ip',
        key: 'dns_server_ip',
        width: 120,
        render: (ip: string) => ip ? <Text code>{ip}</Text> : <Text type="secondary">-</Text>,
      }
    );

    // Add query count column when grouping is enabled
    if (groupByConnection) {
      columns.splice(isMultiClusterAnalysis ? 5 : 4, 0, {
        title: 'Queries',
        dataIndex: 'queryCount',
        key: 'queryCount',
        width: 80,
        sorter: (a: any, b: any) => (a.queryCount || 1) - (b.queryCount || 1),
        render: (count: number) => (
          <Tag color="blue">{(count || 1).toLocaleString()}</Tag>
        ),
      });
    }

    return columns;
  }, [groupByConnection, isMultiClusterAnalysis, clusterInfoMap, dnsColumnFilters]);

  // SNI/TLS table columns - dynamically include connectionCount when grouping and cluster for multi-cluster
  const sniColumns = useMemo(() => {
    const columns: any[] = [];
    
    // Add cluster column for multi-cluster analysis
    if (isMultiClusterAnalysis) {
      columns.push({
        title: 'Cluster',
        key: 'cluster',
        width: 200,
        minWidth: 180,
        ellipsis: false,
        render: (_: any, record: SniEvent) => {
          const cluster = clusterInfoMap.get(record.cluster_id);
          return cluster ? (
            <ClusterBadge
              clusterId={cluster.id}
              clusterName={cluster.name}
              environment={cluster.environment}
              provider={cluster.provider}
              size="small"
              showEnvironment={true}
              showProvider={false}
            />
          ) : (
            <Tag color="default">C{record.cluster_id}</Tag>
          );
        },
      });
    }
    
    columns.push(
      {
        title: 'Timestamp',
        dataIndex: 'timestamp',
        key: 'timestamp',
        width: 160,
        render: (ts: string) => (
          <Space>
            <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
            <Text type="secondary">{dayjs(ts).format('HH:mm:ss.SSS')}</Text>
          </Space>
        ),
        sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
      },
      {
        title: 'Pod',
        key: 'pod',
        render: (_: any, record: SniEvent) => (
          <Space direction="vertical" size={0}>
            <Text strong>{record.pod}</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
          </Space>
        ),
      },
      {
        title: 'SNI Name',
        dataIndex: 'server_name',
        key: 'server_name',
        ellipsis: true,
        render: (_: any, record: SniEvent) => {
          const sniName = record.server_name || record.sni_name || '-';
          return (
            <Tooltip title={sniName}>
              <Space>
                <SafetyCertificateOutlined style={{ color: '#22c55e' }} />
                <Text strong>{sniName}</Text>
              </Space>
            </Tooltip>
          );
        },
      },
      {
        title: 'Destination',
        key: 'destination',
        render: (_: any, record: SniEvent) => {
          const destIp = record.dest_ip || record.dst_ip || '-';
          const destPort = record.dest_port || record.dst_port || 0;
          return <Text code>{destIp}:{destPort}</Text>;
        },
      },
      {
        title: 'Port',
        key: 'dest_port',
        width: 80,
        filters: uniqueSniPorts,
        filteredValue: sniColumnFilters.dest_port || null,
        onFilter: (value: any, record: SniEvent) => {
          const port = record.dest_port ?? record.dst_port;
          return port === value;
        },
        render: (_: any, record: SniEvent) => {
          const port = record.dest_port ?? record.dst_port;
          return port ? <Tag color="blue">{port}</Tag> : '-';
        },
      },
      {
        title: 'TLS Version',
        dataIndex: 'tls_version',
        key: 'tls_version',
        width: 120,
        filters: [
          { text: 'TLS 1.3', value: 'TLS 1.3' },
          { text: 'TLS 1.2', value: 'TLS 1.2' },
          { text: 'TLS 1.1', value: 'TLS 1.1' },
          { text: 'TLS 1.0', value: 'TLS 1.0' },
        ],
        filteredValue: sniColumnFilters.tls_version || null,
        onFilter: (value: any, record: any) => record.tls_version === value,
        render: (version: string) => (
          <Tag color={tlsVersionColors[version] || '#8c8c8c'}>
            <LockOutlined /> {version}
          </Tag>
        ),
      },
      {
        title: 'Cipher Suite',
        dataIndex: 'cipher_suite',
        key: 'cipher_suite',
        width: 200,
        ellipsis: true,
        render: (cipher: string) => (
          <Tooltip title={cipher}>
            <Text type="secondary" style={{ fontSize: 11 }}>{cipher || '-'}</Text>
          </Tooltip>
        ),
      },
      {
        title: 'Process',
        key: 'process',
        width: 120,
        render: (_: any, record: SniEvent) => (
          <Text type="secondary">{record.comm} ({record.pid})</Text>
        ),
      }
    );

    // Add connection count column when grouping is enabled
    if (groupByConnection) {
      columns.splice(isMultiClusterAnalysis ? 5 : 4, 0, {
        title: 'Connections',
        dataIndex: 'connectionCount',
        key: 'connectionCount',
        width: 100,
        sorter: (a: any, b: any) => (a.connectionCount || 1) - (b.connectionCount || 1),
        render: (count: number) => (
          <Tag color="green">{(count || 1).toLocaleString()}</Tag>
        ),
      });
    }

    return columns;
  }, [groupByConnection, isMultiClusterAnalysis, clusterInfoMap, uniqueSniPorts, sniColumnFilters]);

  const isLoading = isAnalysesLoading || isGraphLoading;

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center">
          <ApiOutlined style={{ fontSize: 28, color: '#0891b2' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Network Explorer</Title>
            <Text type="secondary">Explore network flows, DNS queries, and service connections</Text>
          </div>
        </Space>
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
                const isMulti = analysis.is_multi_cluster && analysis.cluster_ids?.length > 1;
                const clusterCount = analysis.cluster_ids?.length || 1;
                return (
                  <Option key={analysis.id} value={analysis.id}>
                    <Space>
                      <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                      {analysis.name}
                      {isMulti ? (
                        <Tag color="blue" style={{ fontSize: 10, padding: '0 4px' }}>
                          {clusterCount} Clusters
                        </Tag>
                      ) : (
                        <Text type="secondary" style={{ fontSize: 11 }}>({clusterName})</Text>
                      )}
                    </Space>
                  </Option>
                );
              })}
            </Select>
          </Col>
          {/* Multi-cluster filter */}
          {isMultiClusterAnalysis && analysisClusterIds.length > 1 && (
            <Col>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Cluster Filter</Text>
              <Tooltip title="Filter by cluster in multi-cluster analysis. Use Ctrl+Click for multiple selection.">
                <Select
                  mode="multiple"
                  placeholder="All Clusters"
                  style={{ width: 200 }}
                  allowClear
                  value={selectedClusterIds.length === analysisClusterIds.length ? [] : selectedClusterIds}
                  onChange={(values) => {
                    if (values.length === 0) {
                      setSelectedClusterIds(analysisClusterIds);
                    } else {
                      setSelectedClusterIds(values);
                    }
                  }}
                  maxTagCount={1}
                  maxTagPlaceholder={(omittedValues) => `+${omittedValues.length}`}
                >
                  {analysisClusterIds.map((clusterId: number) => {
                    const clusterInfo = clusters.find((c: any) => c.id === clusterId);
                    return (
                      <Option key={clusterId} value={clusterId}>
                        {clusterInfo?.name || `Cluster ${clusterId}`}
                      </Option>
                    );
                  })}
                </Select>
              </Tooltip>
            </Col>
          )}
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Time Range</Text>
            <RangePicker
              showTime
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              style={{ width: 300 }}
              presets={[
                { label: 'Last Hour', value: [dayjs().subtract(1, 'hour'), dayjs()] },
                { label: 'Last 24 Hours', value: [dayjs().subtract(24, 'hour'), dayjs()] },
              ]}
            />
          </Col>
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Search</Text>
            <Input
              placeholder="Search all fields..."
              prefix={<SearchOutlined />}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: 220 }}
              allowClear
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right', paddingTop: 22 }}>
            <Space size="middle">
              <Tooltip title={groupByConnection 
                ? "Showing unique connections (grouped). Toggle off to see all individual events." 
                : "Showing all individual events. Toggle on to group by unique connections."}>
                <Space>
                  <Switch
                    checked={groupByConnection}
                    onChange={setGroupByConnection}
                    checkedChildren={<GroupOutlined />}
                    unCheckedChildren={<UnorderedListOutlined />}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {groupByConnection ? 'Grouped' : 'All Events'}
                  </Text>
                </Space>
              </Tooltip>
              <Button 
                icon={<ReloadOutlined />} 
                onClick={handleRefresh}
                loading={isLoading || isDnsLoading || isSniLoading || isFlowsLoading}
              >
                Refresh
              </Button>
              <Button 
                icon={<DownloadOutlined />} 
                onClick={handleExport}
                disabled={!selectedClusterId}
              >
                Export CSV
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Stats - Update based on search filter with animated counters */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Tooltip title={searchTerm ? `Filtered by "${searchTerm}"` : 'Total network flows in selected time range'}>
            <Card bordered={false}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Network Flows</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <SwapOutlined style={{ color: '#0891b2', fontSize: 20 }} />
                  <span style={{ fontSize: 24, fontWeight: 600 }}>
                    {!selectedAnalysisId ? '-' : animatedFlows.toLocaleString()}
                  </span>
                </div>
              </div>
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title={searchTerm ? `Filtered by "${searchTerm}"` : 'Total services with open ports'}>
            <Card bordered={false}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Services</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CloudServerOutlined style={{ color: '#4d9f7c', fontSize: 20 }} />
                  <span style={{ fontSize: 24, fontWeight: 600 }}>
                    {!selectedAnalysisId ? '-' : animatedServices.toLocaleString()}
                  </span>
                </div>
              </div>
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title={searchTerm ? `Filtered by "${searchTerm}"` : 'Total DNS queries in selected time range'}>
            <Card bordered={false}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>DNS Queries</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <GlobalOutlined style={{ color: '#06b6d4', fontSize: 20 }} />
                  <span style={{ fontSize: 24, fontWeight: 600 }}>
                    {!selectedAnalysisId ? '-' : animatedDns.toLocaleString()}
                  </span>
                </div>
              </div>
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title={searchTerm ? `Filtered by "${searchTerm}"` : 'Total TLS/SNI connections in selected time range'}>
            <Card bordered={false}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>TLS Connections</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <LockOutlined style={{ color: '#22c55e', fontSize: 20 }} />
                  <span style={{ fontSize: 24, fontWeight: 600 }}>
                    {!selectedAnalysisId ? '-' : animatedTls.toLocaleString()}
                  </span>
                </div>
              </div>
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          {/* Error card - uses pre-calculated values from useMemo with Critical/Warning split */}
          <Tooltip 
            title={
              <div style={{ minWidth: 220, fontFamily: 'inherit' }}>
                {/* Header with health status */}
                <div style={{ 
                  fontWeight: 600, 
                  marginBottom: 10, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between',
                  paddingBottom: 8,
                  borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                    {errorHealthStatus === 'healthy' || errorHealthStatus === 'good' ? (
                      <CheckCircleOutlined style={{ color: '#10b981' }} />
                    ) : errorHealthStatus === 'warning' ? (
                      <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />
                    ) : (
                      <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
                    )}
                    Network Health
                  </span>
                  <span style={{ 
                    fontSize: 11, 
                    padding: '2px 8px', 
                    borderRadius: 4,
                    fontWeight: 500,
                    background: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                      ? 'rgba(16, 185, 129, 0.15)' 
                      : errorHealthStatus === 'warning' 
                        ? 'rgba(245, 158, 11, 0.15)' 
                        : 'rgba(239, 68, 68, 0.15)',
                    color: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                      ? '#10b981' 
                      : errorHealthStatus === 'warning' 
                        ? '#f59e0b' 
                        : '#ef4444'
                  }}>
                    {(errorHealthStatus || 'healthy').charAt(0).toUpperCase() + (errorHealthStatus || 'healthy').slice(1)}
                  </span>
                </div>
                
                {/* Critical/Warning split display */}
                <div style={{ display: 'flex', gap: 20, marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444' }} />
                      Critical
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: totalCritical > 0 ? '#ef4444' : '#10b981' }}>
                      {totalCritical.toLocaleString()}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b' }} />
                      Warnings
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: totalWarnings > 0 ? '#f59e0b' : '#10b981' }}>
                      {totalWarnings.toLocaleString()}
                    </div>
                  </div>
                </div>
                
                {/* Critical errors breakdown */}
                {Object.keys(criticalByType).length > 0 && (
                  <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(239, 68, 68, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                    <div style={{ marginBottom: 4, color: '#ef4444', fontWeight: 500, fontSize: 11 }}>Critical Errors</div>
                    {Object.entries(criticalByType).map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(239, 68, 68, 0.9)' : 'rgba(239, 68, 68, 0.85)' }}>
                        <span>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 500 }}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Warnings breakdown */}
                {Object.keys(warningsByType).length > 0 && (
                  <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(245, 158, 11, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                    <div style={{ marginBottom: 4, color: '#f59e0b', fontWeight: 500, fontSize: 11 }}>Retransmits (Normal)</div>
                    {Object.entries(warningsByType).map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(245, 158, 11, 0.9)' : 'rgba(245, 158, 11, 0.85)' }}>
                        <span>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 500 }}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Health message */}
                {errorHealthMessage && (
                  <div style={{ 
                    fontSize: 11, 
                    color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', 
                    borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`, 
                    paddingTop: 6,
                    marginTop: 4
                  }}>
                    {errorHealthMessage}
                  </div>
                )}
                
                {/* Error anomaly alert */}
                {errorAnomalySummary && errorAnomalySummary.total_anomalies > 0 && (
                  <div style={{ marginTop: 8, padding: '6px 8px', background: 'rgba(102, 126, 234, 0.1)', borderRadius: 4, border: '1px solid rgba(102, 126, 234, 0.2)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#667eea', fontWeight: 500 }}>
                      <AlertOutlined style={{ fontSize: 12 }} />
                      {errorAnomalySummary.total_anomalies} Anomal{errorAnomalySummary.total_anomalies === 1 ? 'y' : 'ies'} Detected
                    </div>
                    <div style={{ fontSize: 11, marginTop: 2, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)' }}>
                      Trend: {errorAnomalySummary?.trends?.trend || 'stable'}
                    </div>
                  </div>
                )}
                
                {/* No errors state */}
                {!hasErrors && (
                  <div style={{ color: '#10b981', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <CheckCircleOutlined style={{ fontSize: 14 }} />
                    No network errors detected
                  </div>
                )}
              </div>
            } 
            mouseEnterDelay={0.3}
            color={isDark ? token.colorBgElevated : '#fff'}
            overlayInnerStyle={{ 
              padding: 12,
              boxShadow: isDark ? '0 6px 16px rgba(0,0,0,0.4)' : '0 6px 16px rgba(0,0,0,0.08)',
              borderRadius: 8
            }}
          >
            <Card bordered={false} style={{ position: 'relative' }}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Network Health</Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {/* Critical errors count */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <ExclamationCircleOutlined style={{ 
                      color: hasCriticalErrors ? '#ef4444' : (isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)'), 
                      fontSize: 18 
                    }} />
                    <span style={{ 
                      fontSize: 22, 
                      fontWeight: 600, 
                      color: hasCriticalErrors ? '#ef4444' : undefined 
                    }}>
                      {!selectedAnalysisId ? '-' : animatedCritical.toLocaleString()}
                    </span>
                  </div>
                  {/* Separator */}
                  <span style={{ color: isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)', fontSize: 14 }}>/</span>
                  {/* Warnings count */}
                  <span style={{ 
                    fontSize: 16, 
                    fontWeight: 500, 
                    color: totalWarnings > 0 ? '#f59e0b' : (isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)')
                  }}>
                    {!selectedAnalysisId ? '-' : animatedWarnings.toLocaleString()}
                  </span>
                </div>
              </div>
              {/* Anomaly badge */}
              {errorAnomalySummary && errorAnomalySummary.total_anomalies > 0 && (
                <Tag 
                  style={{ 
                    position: 'absolute', 
                    top: 8, 
                    right: 8, 
                    fontSize: 10,
                    background: 'rgba(102, 126, 234, 0.15)',
                    color: '#667eea',
                    border: '1px solid rgba(102, 126, 234, 0.3)'
                  }}
                >
                  {errorAnomalySummary.total_anomalies} Anomal{errorAnomalySummary.total_anomalies === 1 ? 'y' : 'ies'}
                </Tag>
              )}
              {/* Health status indicator */}
              {selectedAnalysisId && (
                <div 
                  style={{ 
                    position: 'absolute', 
                    bottom: 8, 
                    right: 8, 
                    width: 10, 
                    height: 10, 
                    borderRadius: '50%',
                    background: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                      ? '#10b981' 
                      : errorHealthStatus === 'warning' 
                        ? '#f59e0b' 
                        : '#ef4444'
                  }} 
                />
              )}
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          {/* Data Transferred card - Shows total bytes or connection count as fallback */}
          <Tooltip 
            title={totalBytesTransferred > 0 
              ? `Total data transferred: ${(totalBytesTransferred / (1024 * 1024)).toFixed(2)} MB (${totalBytesTransferred.toLocaleString()} bytes)`
              : `Byte data not available. Showing total connections instead. Note: TCP Throughput (top_tcp) gadget requires kernel 5.4+ for byte metrics.`
            }
          >
            <Card bordered={false}>
              <div>
                <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>
                  {totalBytesTransferred > 0 ? 'Data Transferred' : 'Connections'}
                </Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <ApiOutlined style={{ color: totalBytesTransferred > 0 ? '#0891b2' : '#6366f1', fontSize: 20 }} />
                  <span style={{ fontSize: 24, fontWeight: 600 }}>
                    {!selectedAnalysisId ? '-' : (
                      totalBytesTransferred > 0 
                        ? animatedBytes.toFixed(2)
                        : (flowsData?.length || graphData?.edges?.length || 0).toLocaleString()
                    )}
                  </span>
                  {totalBytesTransferred > 0 && (
                    <span style={{ fontSize: 14, color: '#94a3b8' }}>MB</span>
                  )}
                </div>
              </div>
            </Card>
          </Tooltip>
        </Col>
      </Row>

      {/* Main Content */}
      <Card bordered={false}>
        {!selectedAnalysisId ? (
          <Empty description="Select an analysis to view network data" />
        ) : isLoading && !graphData ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading network data...</Text>
          </div>
        ) : (
          <Tabs activeKey={activeTab} onChange={setActiveTab}>
            <Tabs.TabPane
              tab={<span><SwapOutlined /> Flows ({searchTerm ? flowsData.length : (networkFlowsData?.total || flowsData.length)})</span>}
              key="flows"
            >
              <Table
                dataSource={flowsData}
                columns={flowColumns}
                onChange={handleFlowsTableChange}
                pagination={{ 
                  current: pagination.current,
                  pageSize: 100,
                  total: networkFlowsData?.total || flowsData.length,
                  showSizeChanger: true,
                  pageSizeOptions: ['50', '100', '500', '1000'],
                  showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} flows`,
                  onChange: (page, pageSize) => setPagination({ current: page, pageSize: pageSize || 100 })
                }}
                size="middle"
                loading={isFlowsLoading}
                locale={{ emptyText: <Empty description="No network flows recorded" /> }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedRecord(record);
                    setSelectedRecordType('flow');
                    setDetailModalVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><CloudServerOutlined /> Services ({searchTerm ? filteredServicesData.length : servicesData.length})</span>}
              key="services"
            >
              <Table
                dataSource={filteredServicesData}
                columns={serviceColumns}
                onChange={handleServicesTableChange}
                pagination={{ 
                  pageSize: 20, 
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} services`
                }}
                size="middle"
                loading={isBindLoading}
                locale={{ emptyText: <Empty description="No listening services found" /> }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedRecord(record);
                    setSelectedRecordType('service');
                    setDetailModalVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><GlobalOutlined /> DNS ({searchTerm ? filteredDnsQueries.length : (dnsData?.total || filteredDnsQueries.length)})</span>}
              key="dns"
            >
              <Table
                dataSource={filteredDnsQueries}
                columns={dnsColumns}
                onChange={handleDnsTableChange}
                pagination={{ 
                  pageSize: 100, 
                  showSizeChanger: true,
                  pageSizeOptions: ['50', '100', '500', '1000'],
                  showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} DNS queries`
                }}
                size="middle"
                loading={isDnsLoading}
                locale={{ emptyText: <Empty description="No DNS queries recorded" /> }}
                scroll={{ x: 1300 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedRecord(record);
                    setSelectedRecordType('dns');
                    setDetailModalVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><LockOutlined /> TLS/SNI ({searchTerm ? filteredSniEvents.length : (sniData?.total || filteredSniEvents.length)})</span>}
              key="tls"
            >
              <Table
                dataSource={filteredSniEvents}
                columns={sniColumns}
                onChange={handleSniTableChange}
                pagination={{ 
                  pageSize: 100, 
                  showSizeChanger: true,
                  pageSizeOptions: ['50', '100', '500', '1000'],
                  showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} TLS connections`
                }}
                size="middle"
                loading={isSniLoading}
                locale={{ emptyText: <Empty description="No TLS/SNI connections recorded" /> }}
                scroll={{ x: 1200 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedRecord(record);
                    setSelectedRecordType('sni');
                    setDetailModalVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
          </Tabs>
        )}
      </Card>

      {/* Record Detail Modal */}
      <Modal
        title={
          <Space>
            {selectedRecordType === 'flow' && <SwapOutlined />}
            {selectedRecordType === 'service' && <CloudServerOutlined />}
            {selectedRecordType === 'dns' && <GlobalOutlined />}
            {selectedRecordType === 'sni' && <LockOutlined />}
            <span>
              {selectedRecordType === 'flow' && 'Network Flow Details'}
              {selectedRecordType === 'service' && 'Service Details'}
              {selectedRecordType === 'dns' && 'DNS Query Details'}
              {selectedRecordType === 'sni' && 'TLS/SNI Connection Details'}
            </span>
          </Space>
        }
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedRecord(null);
        }}
        footer={[
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            Close
          </Button>
        ]}
        width={700}
      >
        {selectedRecord && selectedRecordType === 'flow' && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="Source" span={2}>
              <Text strong>{selectedRecord.source}</Text>
              {selectedRecord._sourceIp && selectedRecord._sourceIp !== selectedRecord.source && (
                <Text type="secondary" style={{ marginLeft: 8 }}>({selectedRecord._sourceIp})</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Source Namespace">
              <Tag>{selectedRecord.sourceNs || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Target" span={2}>
              <Text strong>{selectedRecord.target}</Text>
              {selectedRecord._targetIp && selectedRecord._targetIp !== selectedRecord.target && (
                <Text type="secondary" style={{ marginLeft: 8 }}>({selectedRecord._targetIp})</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Target Namespace">
              <Tag>{selectedRecord.targetNs || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Protocol">
              <Tag color={protocolColors[selectedRecord.protocol] || '#8c8c8c'}>{selectedRecord.protocol}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Port">
              <Text code>{selectedRecord.port}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Direction">
              {selectedRecord.direction ? (
                <Tag color={selectedRecord.direction === 'ingress' ? 'green' : 'blue'}>{selectedRecord.direction}</Tag>
              ) : <Text type="secondary">-</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Flow Count">
              {selectedRecord.requestCount?.toLocaleString() || 1}
            </Descriptions.Item>
            <Descriptions.Item label="Errors">
              <Text type={selectedRecord.errorCount > 0 ? 'danger' : 'secondary'}>
                {selectedRecord.errorCount || 0}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="Data Transferred">
              {selectedRecord.bytesTransferred > 0 
                ? `${(selectedRecord.bytesTransferred / 1024).toFixed(2)} KB`
                : '-'}
            </Descriptions.Item>
            {selectedRecord.timestamp && (
              <Descriptions.Item label="Timestamp" span={2}>
                <Space>
                  <ClockCircleOutlined />
                  {dayjs(selectedRecord.timestamp).format('YYYY-MM-DD HH:mm:ss.SSS')}
                </Space>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}

        {selectedRecord && selectedRecordType === 'service' && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="Service/Pod" span={2}>
              <Text strong>{selectedRecord.name || selectedRecord.pod}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Namespace">
              <Tag>{selectedRecord.namespace || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Process">
              <Text code>{selectedRecord.comm || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Ports" span={2}>
              {selectedRecord.ports?.length > 0 
                ? selectedRecord.ports.map((p: number) => <Tag key={p}>{p}</Tag>)
                : <Text type="secondary">-</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Protocols" span={2}>
              {selectedRecord.protocols?.length > 0 
                ? selectedRecord.protocols.map((p: string) => (
                    <Tag key={p} color={protocolColors[p] || '#8c8c8c'}>{p}</Tag>
                  ))
                : <Text type="secondary">-</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Bind Count">
              {selectedRecord.bindCount || 1}
            </Descriptions.Item>
            {selectedRecord.timestamp && (
              <Descriptions.Item label="Last Seen">
                <Space>
                  <ClockCircleOutlined />
                  {dayjs(selectedRecord.timestamp).format('YYYY-MM-DD HH:mm:ss')}
                </Space>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}

        {selectedRecord && selectedRecordType === 'dns' && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="Query Name" span={2}>
              <Text strong copyable>{selectedRecord.query_name}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Query Type">
              <Tag>{selectedRecord.query_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Response Code">
              <Tag color={dnsResponseColors[selectedRecord.response_code] || '#8c8c8c'}>
                {selectedRecord.response_code === 'NOERROR' ? <CheckCircleOutlined /> : <CloseCircleOutlined />} {selectedRecord.response_code}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Pod" span={2}>
              <Text strong>{selectedRecord.pod}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Namespace">
              <Tag>{selectedRecord.namespace || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="DNS Server">
              <Text code>{selectedRecord.dns_server_ip || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Response IPs" span={2}>
              {selectedRecord.response_ips?.length > 0 
                ? selectedRecord.response_ips.map((ip: string, i: number) => <Tag key={i}>{ip}</Tag>)
                : <Text type="secondary">-</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Latency">
              {selectedRecord.latency_ms != null 
                ? <Text type={selectedRecord.latency_ms > 100 ? 'warning' : 'success'}>{selectedRecord.latency_ms}ms</Text>
                : <Text type="secondary">-</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="Timestamp">
              <Space>
                <ClockCircleOutlined />
                {dayjs(selectedRecord.timestamp).format('YYYY-MM-DD HH:mm:ss.SSS')}
              </Space>
            </Descriptions.Item>
          </Descriptions>
        )}

        {selectedRecord && selectedRecordType === 'sni' && (
          <Descriptions bordered column={2} size="small">
            <Descriptions.Item label="SNI Name" span={2}>
              <Text strong copyable>{selectedRecord.server_name || selectedRecord.sni_name}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="TLS Version">
              <Tag color={tlsVersionColors[selectedRecord.tls_version] || '#8c8c8c'}>
                <SafetyCertificateOutlined /> {selectedRecord.tls_version || '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Cipher Suite">
              <Text code style={{ fontSize: 11 }}>{selectedRecord.cipher_suite || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Pod" span={2}>
              <Text strong>{selectedRecord.pod}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Namespace">
              <Tag>{selectedRecord.namespace || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Process">
              <Text code>{selectedRecord.comm || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Destination IP">
              <Text code>{selectedRecord.dest_ip || selectedRecord.dst_ip || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Destination Port">
              <Text code>{selectedRecord.dest_port ?? selectedRecord.dst_port ?? '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Timestamp" span={2}>
              <Space>
                <ClockCircleOutlined />
                {dayjs(selectedRecord.timestamp).format('YYYY-MM-DD HH:mm:ss.SSS')}
              </Space>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default NetworkExplorer;
