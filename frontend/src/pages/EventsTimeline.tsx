import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
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
  Input,
  Badge,
  Empty,
  DatePicker,
  Button,
  Spin,
  message,
  Dropdown,
  Menu,
  Modal,
  Descriptions,
  Tooltip,
  Switch,
  Segmented,
  Skeleton,
  theme
} from 'antd';
import { 
  ClockCircleOutlined,
  ApiOutlined,
  GlobalOutlined,
  ThunderboltOutlined,
  FileOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
  CloudServerOutlined,
  LockOutlined,
  DatabaseOutlined,
  SearchOutlined,
  DownloadOutlined,
  ReloadOutlined,
  ClusterOutlined,
  SyncOutlined,
  FilterOutlined,
  CopyOutlined,
  ExclamationCircleOutlined,
  BugOutlined,
  CloseCircleOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { 
  useGetEventStatsQuery, 
  useGetEventsQuery,
  useGetEventHistogramQuery,
  UnifiedEvent
} from '../store/api/eventsApi';
import { Analysis } from '../types';
import { ClusterBadge } from '../components/Common';
import { useTheme } from '../contexts/ThemeContext';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

// Auto-refresh intervals
const AUTO_REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

// Quick filter presets
type QuickFilterType = 'all' | 'security' | 'network' | 'process' | 'errors' | 'high_volume' | 'anomalies';

// Anomaly detection patterns for different event types
const ANOMALY_PATTERNS = {
  // Suspicious DNS queries
  dns: {
    suspicious_tlds: ['.ru', '.cn', '.tk', '.ml', '.ga', '.cf', '.onion', '.bit'],
    crypto_domains: ['pool.', 'mine.', 'stratum.', 'xmr.', 'btc.', 'eth.'],
    c2_patterns: ['dga-', 'random', 'base64'],
  },
  // Suspicious network patterns
  network: {
    suspicious_ports: [4444, 5555, 6666, 7777, 8888, 9999, 31337, 12345, 54321],
    crypto_ports: [3333, 5556, 14433, 14444, 45700],
    known_bad_ips: ['0.0.0.0', '255.255.255.255'],
  },
  // Suspicious process patterns
  process: {
    shells: ['/bin/sh', '/bin/bash', '/bin/zsh', '/bin/dash', 'sh', 'bash'],
    network_tools: ['curl', 'wget', 'nc', 'netcat', 'ncat', 'socat', 'telnet'],
    recon_tools: ['nmap', 'masscan', 'nikto', 'dirb', 'gobuster'],
    crypto_miners: ['xmrig', 'minerd', 'cpuminer', 'cgminer', 'ethminer'],
  },
  // Suspicious file patterns
  file: {
    sensitive_paths: ['/etc/passwd', '/etc/shadow', '/etc/sudoers', '.ssh/', 'id_rsa', '.kube/config', '.aws/credentials'],
    temp_executables: ['/tmp/', '/var/tmp/', '/dev/shm/'],
  },
  // Security event severities
  security: {
    critical_capabilities: ['CAP_SYS_ADMIN', 'CAP_NET_ADMIN', 'CAP_SYS_PTRACE', 'CAP_DAC_OVERRIDE'],
  }
};

// Event type configuration with icons and colors - Flowfish Ocean Theme
// Soft, professional colors consistent with brand identity
// NOTE: tcp_lifecycle removed - IG doesn't produce TCP state events
const eventTypeConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  network_flow: { label: 'Network Flow', color: '#22a6a6', icon: <ApiOutlined /> },    // Ocean teal - flow/connection
  dns_query: { label: 'DNS Query', color: '#5cdbd3', icon: <GlobalOutlined /> },       // Soft cyan - global/DNS
  process_event: { label: 'Process', color: '#b37feb', icon: <ThunderboltOutlined /> }, // Soft purple - activity
  file_event: { label: 'File I/O', color: '#b89b5d', icon: <FileOutlined /> },          // Sand amber - storage
  security_event: { label: 'Security', color: '#c97a6d', icon: <SafetyCertificateOutlined /> }, // Soft coral - security
  oom_event: { label: 'OOM Kill', color: '#f76e6e', icon: <WarningOutlined /> },        // Soft red - critical
  bind_event: { label: 'Socket Bind', color: '#0891b2', icon: <CloudServerOutlined /> }, // Brand teal - primary
  sni_event: { label: 'TLS/SNI', color: '#69b1ff', icon: <LockOutlined /> },            // Soft blue - secure
  mount_event: { label: 'Mount', color: '#ffd666', icon: <DatabaseOutlined /> },        // Soft gold - config
};

const EventsTimeline: React.FC = () => {
  const { isDark } = useTheme();
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedClusterIds, setSelectedClusterIds] = useState<number[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [selectedNamespace, setSelectedNamespace] = useState<string | undefined>(undefined);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50 });
  const [isExporting, setIsExporting] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);
  
  // New feature states
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(0);
  const [quickFilter, setQuickFilter] = useState<QuickFilterType>('all');
  const [showTimeline, setShowTimeline] = useState(true);
  const [groupByType, setGroupByType] = useState(false);
  const autoRefreshTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // Debounce search term for API calls (300ms delay, min 3 chars)
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchTerm.length >= 3) {
        setDebouncedSearchTerm(searchTerm);
      } else {
        setDebouncedSearchTerm('');
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);
  
  // Reset pagination when search changes
  useEffect(() => {
    setPagination(prev => ({ ...prev, current: 1 }));
  }, [debouncedSearchTerm]);

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
  
  // Get available clusters for this analysis
  const analysisClusterIds = useMemo(() => {
    if (!selectedAnalysis) return [];
    return selectedAnalysis.cluster_ids || [selectedAnalysis.cluster_id];
  }, [selectedAnalysis]);

  // Handle analysis change - set analysis ID and manage cluster selection
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    setSelectedClusterId(undefined);
    setSelectedClusterIds([]);
    setPagination({ ...pagination, current: 1 });
  }, [pagination]);

  // Auto-set cluster(s) when analysis changes
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        const clusterIds = analysis.cluster_ids || [analysis.cluster_id];
        if (clusterIds.length === 1) {
          // Single cluster - select it automatically
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

  // Build query params for events
  const eventsQueryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    event_types: selectedTypes.length > 0 ? selectedTypes.join(',') : undefined,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: pagination.pageSize,
    offset: (pagination.current - 1) * pagination.pageSize,
  }), [selectedClusterId, selectedAnalysisId, selectedTypes, dateRange, pagination]);

  // Get events from API
  const { data: eventsData, isLoading: isEventsLoading, refetch: refetchEvents } = useGetEventsQuery(
    eventsQueryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Get event statistics (with time range filter)
  const statsParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
  }), [selectedClusterId, selectedAnalysisId, dateRange]);

  const { data: eventStats, isLoading: isStatsLoading, refetch: refetchStats } = useGetEventStatsQuery(
    statsParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const histogramParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    event_types: selectedTypes.length > 0 ? selectedTypes.join(',') : undefined,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    bucket_count: 60,
  }), [selectedClusterId, selectedAnalysisId, selectedTypes, dateRange]);

  const { data: histogramData, isLoading: isHistogramLoading, refetch: refetchHistogram } = useGetEventHistogramQuery(
    histogramParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  /**
   * Smart matching for identifiers (pods, namespaces, IPs, paths).
   * Matches if string starts with search term or term appears after delimiter.
   */
  const smartMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    const valueLower = value.toLowerCase();
    const searchLower = search.toLowerCase();
    
    if (valueLower === searchLower || valueLower.startsWith(searchLower)) return true;
    
    const delimiters = ['.', '-', ':', '/', '_'];
    for (const d of delimiters) {
      if (valueLower.includes(d + searchLower)) return true;
    }
    return false;
  }, []);

  /**
   * Simple contains for short keywords (event type, severity, etc.)
   */
  const simpleMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    return value.toLowerCase().includes(search.toLowerCase());
  }, []);

  // Event search - searches displayed fields with smart matching
  const eventMatchesSearch = useCallback((event: UnifiedEvent, term: string): boolean => {
    if (!term) return true;
    
    // Smart match for pod, namespace, container, source, target
    if (smartMatch(event.pod, term)) return true;
    if (smartMatch(event.namespace, term)) return true;
    if (smartMatch(event.container, term)) return true;
    if (smartMatch(event.source, term)) return true;
    if (smartMatch(event.target, term)) return true;
    
    // Simple match for event_type, severity, details
    if (simpleMatch(event.event_type, term)) return true;
    if (simpleMatch(event.severity, term)) return true;
    if (simpleMatch(event.details, term)) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

  // Anomaly detection for events
  const isAnomalousEvent = useCallback((event: UnifiedEvent): { isAnomaly: boolean; reason: string } => {
    const details = event.details?.toLowerCase() || '';
    const target = event.target?.toLowerCase() || '';
    const source = event.source?.toLowerCase() || '';
    
    // DNS anomalies
    if (event.event_type === 'dns_query') {
      for (const tld of ANOMALY_PATTERNS.dns.suspicious_tlds) {
        if (target.endsWith(tld)) {
          return { isAnomaly: true, reason: `Suspicious TLD: ${tld}` };
        }
      }
      for (const pattern of ANOMALY_PATTERNS.dns.crypto_domains) {
        if (target.includes(pattern)) {
          return { isAnomaly: true, reason: `Crypto mining domain pattern: ${pattern}` };
        }
      }
    }
    
    // Network anomalies
    if (event.event_type === 'network_flow' || event.event_type === 'bind_event') {
      const portMatch = target.match(/:(\d+)$/);
      if (portMatch) {
        const port = parseInt(portMatch[1], 10);
        if (ANOMALY_PATTERNS.network.suspicious_ports.includes(port)) {
          return { isAnomaly: true, reason: `Suspicious port: ${port}` };
        }
        if (ANOMALY_PATTERNS.network.crypto_ports.includes(port)) {
          return { isAnomaly: true, reason: `Crypto mining port: ${port}` };
        }
      }
    }
    
    // Process anomalies
    if (event.event_type === 'process_event') {
      for (const shell of ANOMALY_PATTERNS.process.shells) {
        if (details.includes(shell) || source.includes(shell)) {
          return { isAnomaly: true, reason: `Shell execution: ${shell}` };
        }
      }
      for (const tool of ANOMALY_PATTERNS.process.network_tools) {
        if (details.includes(tool) || source.includes(tool)) {
          return { isAnomaly: true, reason: `Network tool: ${tool}` };
        }
      }
      for (const miner of ANOMALY_PATTERNS.process.crypto_miners) {
        if (details.includes(miner) || source.includes(miner)) {
          return { isAnomaly: true, reason: `Crypto miner: ${miner}` };
        }
      }
    }
    
    // File anomalies
    if (event.event_type === 'file_event') {
      for (const path of ANOMALY_PATTERNS.file.sensitive_paths) {
        if (details.includes(path) || target.includes(path)) {
          return { isAnomaly: true, reason: `Sensitive file access: ${path}` };
        }
      }
      for (const tmpPath of ANOMALY_PATTERNS.file.temp_executables) {
        if ((details.includes(tmpPath) || target.includes(tmpPath)) && details.includes('exec')) {
          return { isAnomaly: true, reason: `Temp directory execution: ${tmpPath}` };
        }
      }
    }
    
    // Security event anomalies
    if (event.event_type === 'security_event') {
      for (const cap of ANOMALY_PATTERNS.security.critical_capabilities) {
        if (details.includes(cap.toLowerCase())) {
          return { isAnomaly: true, reason: `Critical capability: ${cap}` };
        }
      }
    }
    
    // OOM events are always anomalies
    if (event.event_type === 'oom_event') {
      return { isAnomaly: true, reason: 'Out of Memory Kill' };
    }
    
    return { isAnomaly: false, reason: '' };
  }, []);

  // Filter events client-side for search and quick filters
  const filteredEvents = useMemo(() => {
    if (!eventsData?.events) return [];
    
    // Use debounced search term for filtering
    let filtered = eventsData.events.filter(event => eventMatchesSearch(event, debouncedSearchTerm));
    
    // Apply namespace filter
    if (selectedNamespace) {
      filtered = filtered.filter(event => event.namespace === selectedNamespace);
    }
    
    // Apply quick filters
    if (quickFilter !== 'all') {
      switch (quickFilter) {
        case 'security':
          filtered = filtered.filter(e => 
            e.event_type === 'security_event' || 
            e.event_type === 'oom_event' ||
            e.severity === 'error'
          );
          break;
        case 'network':
          filtered = filtered.filter(e => 
            e.event_type === 'network_flow' || 
            e.event_type === 'dns_query' ||
            e.event_type === 'sni_event' ||
            e.event_type === 'bind_event'
          );
          break;
        case 'process':
          filtered = filtered.filter(e => 
            e.event_type === 'process_event' || 
            e.event_type === 'file_event'
          );
          break;
        case 'errors':
          filtered = filtered.filter(e => 
            e.severity === 'error' ||
            e.event_type === 'oom_event'
          );
          break;
        case 'high_volume':
          // Group by event type and show types with > 100 events
          const typeCounts: Record<string, number> = {};
          eventsData.events.forEach(e => {
            typeCounts[e.event_type] = (typeCounts[e.event_type] || 0) + 1;
          });
          const highVolumeTypes = Object.keys(typeCounts).filter(t => typeCounts[t] > 100);
          filtered = filtered.filter(e => highVolumeTypes.includes(e.event_type));
          break;
        case 'anomalies':
          filtered = filtered.filter(e => isAnomalousEvent(e).isAnomaly);
          break;
      }
    }
    
    return filtered;
  }, [eventsData?.events, debouncedSearchTerm, eventMatchesSearch, selectedNamespace, quickFilter, isAnomalousEvent]);
  
  // Group events by type for grouped view
  const groupedEvents = useMemo(() => {
    if (!groupByType || filteredEvents.length === 0) return null;
    
    const groups: Record<string, { events: UnifiedEvent[]; count: number; latestTime: string }> = {};
    
    filteredEvents.forEach(event => {
      const key = event.event_type;
      if (!groups[key]) {
        groups[key] = { events: [], count: 0, latestTime: event.timestamp };
      }
      groups[key].events.push(event);
      groups[key].count++;
      if (dayjs(event.timestamp).isAfter(dayjs(groups[key].latestTime))) {
        groups[key].latestTime = event.timestamp;
      }
    });
    
    return Object.entries(groups)
      .map(([type, data]) => ({
        key: type,
        event_type: type,
        count: data.count,
        latest_time: data.latestTime,
        sample_events: data.events.slice(0, 5),
      }))
      .sort((a, b) => b.count - a.count);
  }, [filteredEvents, groupByType]);
  
  // Count anomalies for badge
  const anomalyCount = useMemo(() => {
    if (!eventsData?.events) return 0;
    return eventsData.events.filter(e => isAnomalousEvent(e).isAnomaly).length;
  }, [eventsData?.events, isAnomalousEvent]);
  
  // Get unique namespaces from events
  const availableNamespaces = useMemo(() => {
    if (!eventsData?.events) return [];
    const namespaces = new Set<string>();
    eventsData.events.forEach(e => e.namespace && namespaces.add(e.namespace));
    return Array.from(namespaces).sort();
  }, [eventsData?.events]);
  
  // Timeline data from server-side histogram
  const timelineData = useMemo(() => {
    if (!histogramData?.buckets || histogramData.buckets.length === 0) {
      return [];
    }
    
    const intervalSeconds = histogramData.interval_seconds || 1;
    const start = histogramData.time_range?.start ? dayjs(histogramData.time_range.start) : null;
    const end = histogramData.time_range?.end ? dayjs(histogramData.time_range.end) : null;
    const isMultiDay = start && end && end.diff(start, 'day') >= 1;
    const timeFormat = isMultiDay ? 'DD MMM HH:mm' : 'HH:mm';
    
    return histogramData.buckets.map((bucket) => {
      const bucketStart = dayjs(bucket.time);
      const bucketEnd = bucketStart.add(intervalSeconds, 'second');
      return {
        time: bucketStart.format(timeFormat),
        count: bucket.count,
        types: bucket.types,
        startTime: bucketStart,
        endTime: bucketEnd,
      };
    });
  }, [histogramData]);
  
  // Max value for timeline scaling
  const timelineMax = useMemo(() => {
    return Math.max(...timelineData.map(b => b.count), 1);
  }, [timelineData]);
  
  // Refresh handler
  const handleRefresh = useCallback((silent = false) => {
    refetchEvents();
    refetchStats();
    refetchHistogram();
    if (!silent) message.success('Data refreshed');
  }, [refetchEvents, refetchStats, refetchHistogram]);
  
  // Auto-refresh effect
  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = null;
    }
    
    if (autoRefreshInterval > 0 && selectedAnalysisId) {
      autoRefreshTimerRef.current = setInterval(() => {
        handleRefresh(true);
      }, autoRefreshInterval);
    }
    
    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [autoRefreshInterval, selectedAnalysisId, handleRefresh]);
  
  // Reset pagination when filters change
  useEffect(() => {
    setPagination(prev => ({ ...prev, current: 1 }));
  }, [dateRange, selectedNamespace, quickFilter]);
  
  // Copy event to clipboard
  const copyToClipboard = useCallback((event: any) => {
    const jsonStr = JSON.stringify(event, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
      message.success('Event copied to clipboard');
    }).catch(() => {
      message.error('Failed to copy');
    });
  }, []);

  // Event type distribution from stats
  const typeDistribution = useMemo(() => {
    return eventStats?.event_counts || {};
  }, [eventStats]);

  // Export handler - uses fetch with auth token for protected endpoints
  const handleExport = useCallback(async (format: 'csv' | 'json') => {
    if (!selectedAnalysisId || !selectedClusterId) {
      message.warning('Please select an analysis first');
      return;
    }
    
    setIsExporting(true);
    try {
      const baseUrl = '/api/v1/export';
      const params = new URLSearchParams({
        cluster_id: selectedClusterId.toString(),
        analysis_id: selectedAnalysisId.toString(),
      });
      
      if (selectedTypes.length > 0) {
        params.append('event_types', selectedTypes.join(','));
      }
      if (dateRange?.[0]) {
        params.append('start_time', dateRange[0].toISOString());
      }
      if (dateRange?.[1]) {
        params.append('end_time', dateRange[1].toISOString());
      }
      if (selectedNamespace) {
        params.append('namespace', selectedNamespace);
      }

      const url = `${baseUrl}/events/${format}?${params.toString()}`;
      
      // Fetch with authentication
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `Export failed with status ${response.status}`);
      }
      
      // Get blob and create download
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `flowfish_events_${selectedClusterId}_${new Date().toISOString().slice(0,10)}.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
      
      message.success(`Export completed - ${format.toUpperCase()} file downloaded`);
    } catch (error: any) {
      console.error('Export error:', error);
      message.error(`Export failed: ${error.message || 'Unknown error'}`);
    } finally {
      setIsExporting(false);
    }
  }, [selectedClusterId, selectedAnalysisId, selectedTypes, dateRange, selectedNamespace]);

  // Table columns - dynamically include cluster column for multi-cluster analysis
  const columns = useMemo(() => {
    const cols: any[] = [];
    
    // Add cluster column for multi-cluster analysis
    if (isMultiClusterAnalysis) {
      cols.push({
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
    
    cols.push(
      {
        title: 'Timestamp',
        dataIndex: 'timestamp',
        key: 'timestamp',
        width: 180,
        render: (timestamp: string) => (
          <Space>
            <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
            <Text>{dayjs(timestamp).format('YYYY-MM-DD HH:mm:ss')}</Text>
          </Space>
        ),
        sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
      },
      {
        title: 'Type',
      dataIndex: 'event_type',
      key: 'event_type',
      width: 140,
      filters: Object.entries(eventTypeConfig).map(([key, config]) => ({
        text: config.label,
        value: key,
      })),
      onFilter: (value: any, record: any) => record.event_type === value,
      render: (type: string, record: any) => {
        const config = eventTypeConfig[type];
        return (
          <Tag 
            color={config?.color} 
            icon={config?.icon}
            style={{ cursor: 'pointer' }}
            onClick={() => {
              setSelectedEvent(record);
              setDetailModalVisible(true);
            }}
          >
            {config?.label || type}
          </Tag>
        );
      },
    },
    {
      title: 'Namespace / Pod',
      key: 'namespace_pod',
      width: 200,
      render: (_: any, record: any) => (
        <Space direction="vertical" size={2} style={{ lineHeight: 1.3 }}>
          <Tag color="blue" style={{ margin: 0 }}>{record.namespace || '-'}</Tag>
          <Text strong style={{ fontSize: 12 }}>{record.pod || '-'}</Text>
        </Space>
      ),
    },
    {
      title: 'Source',
      key: 'source',
      width: 180,
      render: (_: any, record: any) => {
        // Try multiple source fields
        const source = record.source || record.src_ip || record.source_ip || 
                      (record.event_data_json ? JSON.parse(record.event_data_json)?.src_ip : null);
        return source ? (
          <Text code style={{ fontSize: 11 }}>{source}</Text>
        ) : (
          <Text type="secondary">-</Text>
        );
      },
    },
    {
      title: 'Target',
      key: 'target',
      width: 180,
      render: (_: any, record: any) => {
        // Try multiple target fields
        const target = record.target || record.dst_ip || record.dest_ip || record.destination ||
                      (record.event_data_json ? JSON.parse(record.event_data_json)?.dst_ip : null);
        return target ? (
          <Text code style={{ fontSize: 11 }}>{target}</Text>
        ) : (
          <Text type="secondary">-</Text>
        );
      },
    },
    {
      title: 'Data',
      key: 'bytes',
      width: 90,
      render: (_: any, record: any) => {
        // Show bytes for network_flow events (from top_tcp gadget)
        if (record.event_type !== 'network_flow') return <Text type="secondary">—</Text>;
        
        const bytesSent = record.bytes_sent || 0;
        const bytesRecv = record.bytes_received || 0;
        const totalBytes = bytesSent + bytesRecv;
        
        if (totalBytes === 0) return <Text type="secondary">—</Text>;
        
        // Format bytes
        const formatBytes = (b: number) => {
          if (b < 1024) return `${b} B`;
          if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
          return `${(b / (1024 * 1024)).toFixed(2)} MB`;
        };
        
        return (
          <Tooltip title={`↑ ${formatBytes(bytesSent)} | ↓ ${formatBytes(bytesRecv)}`}>
            <Text style={{ color: '#0891b2', fontSize: 11 }}>{formatBytes(totalBytes)}</Text>
          </Tooltip>
        );
      },
    },
      {
        title: 'Anomaly',
        key: 'anomaly',
        width: 100,
        render: (_: any, record: any) => {
          const { isAnomaly, reason } = isAnomalousEvent(record);
          if (!isAnomaly) return <Text type="secondary">—</Text>;
          return (
            <Tooltip title={reason}>
              <Tag color="red" icon={<ExclamationCircleOutlined />} style={{ fontSize: 10 }}>
                Anomaly
              </Tag>
          </Tooltip>
        );
      },
    },
      {
        title: 'Details',
        key: 'details',
        ellipsis: true,
        render: (_: any, record: any) => {
          // Build details from various fields
          let details = record.details || '';
          if (!details && record.query_name) details = `DNS: ${record.query_name}`;
          if (!details && record.file_path) details = `File: ${record.file_path}`;
          if (!details && record.comm) details = `Process: ${record.comm}`;
          if (!details && record.capability) details = `Cap: ${record.capability}`;
          return <Text type="secondary" style={{ fontSize: 11 }}>{details || '-'}</Text>;
        },
      }
    );
    
    return cols;
  }, [isMultiClusterAnalysis, clusterInfoMap]);

  // Export menu
  const exportMenu = (
    <Menu>
      <Menu.Item key="csv" onClick={() => handleExport('csv')}>
        <FileOutlined /> Export as CSV
      </Menu.Item>
      <Menu.Item key="json" onClick={() => handleExport('json')}>
        <FileOutlined /> Export as JSON
      </Menu.Item>
    </Menu>
  );

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center">
          <ClockCircleOutlined style={{ fontSize: 28, color: '#22a6a6' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Events Timeline</Title>
            <Text type="secondary">Unified view of all captured eBPF events across the cluster</Text>
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
                const clusterIds = analysis.cluster_ids || [analysis.cluster_id];
                const isMulti = analysis.is_multi_cluster || clusterIds.length > 1;
                const clusterName = clusters.find((c: any) => c.id === analysis.cluster_id)?.name || `Cluster ${analysis.cluster_id}`;
                return (
                  <Option key={analysis.id} value={analysis.id}>
                    <Space>
                      <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                      {analysis.name}
                      {isMulti ? (
                        <Tag color="purple" style={{ fontSize: 10 }}>
                          <GlobalOutlined style={{ marginRight: 2 }} />
                          {clusterIds.length} clusters
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
          
          {/* Multi-cluster filter - show when multi-cluster analysis is selected */}
          {isMultiClusterAnalysis && analysisClusterIds.length > 1 && (
            <Col>
              <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>
                <ClusterOutlined style={{ marginRight: 4 }} />
                Clusters
              </Text>
              <Select
                mode="multiple"
                placeholder="All clusters"
                style={{ width: 220 }}
                value={selectedClusterIds}
                onChange={(values) => {
                  setSelectedClusterIds(values);
                  if (values.length > 0) {
                    setSelectedClusterId(values[0]);
                  }
                  setPagination({ ...pagination, current: 1 });
                }}
                maxTagCount={2}
              >
                {analysisClusterIds.map((clusterId: number) => {
                  const cluster = clusters.find((c: any) => c.id === clusterId);
                  return (
                    <Option key={clusterId} value={clusterId}>
                      <Space>
                        <ClusterOutlined />
                        {cluster?.name || `Cluster ${clusterId}`}
                      </Space>
                    </Option>
                  );
                })}
              </Select>
            </Col>
          )}
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Event Types</Text>
            <Select
              mode="multiple"
              placeholder="All types"
              style={{ width: 280 }}
              value={selectedTypes}
              onChange={(values) => {
                setSelectedTypes(values);
                setPagination({ ...pagination, current: 1 });
              }}
              maxTagCount={2}
            >
              {Object.entries(eventTypeConfig).map(([key, config]) => (
                <Option key={key} value={key}>
                  <Space>
                    {config.icon}
                    {config.label}
                  </Space>
                </Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Time Range</Text>
            <RangePicker
              showTime
              value={dateRange}
              onChange={(dates) => {
                setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null);
                setPagination({ ...pagination, current: 1 });
              }}
              style={{ width: 320 }}
              presets={[
                { label: 'Last Hour', value: [dayjs().subtract(1, 'hour'), dayjs()] },
                { label: 'Last 6 Hours', value: [dayjs().subtract(6, 'hour'), dayjs()] },
                { label: 'Last 24 Hours', value: [dayjs().subtract(24, 'hour'), dayjs()] },
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day'), dayjs()] },
              ]}
            />
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 16 }} align="middle">
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Namespace</Text>
            <Select
              placeholder="All namespaces"
              style={{ width: 180 }}
              value={selectedNamespace}
              onChange={setSelectedNamespace}
              allowClear
              showSearch
              optionFilterProp="children"
              suffixIcon={<FilterOutlined />}
              disabled={!selectedAnalysisId}
            >
              {availableNamespaces.map(ns => (
                <Option key={ns} value={ns}>{ns}</Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Search</Text>
            <Input
              placeholder="Search events..."
              prefix={<SearchOutlined />}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right', paddingTop: 22 }}>
            <Space size="middle">
              {/* Group By Toggle */}
              <Tooltip title="Group events by type for summary view">
            <Space>
                  <Switch 
                    size="small" 
                    checked={groupByType} 
                    onChange={setGroupByType}
                  />
                  <Text type="secondary" style={{ fontSize: 12 }}>Group</Text>
                </Space>
              </Tooltip>
              
              {/* Quick Filters */}
              <Tooltip title="Filter by event category">
                <Select
                  value={quickFilter}
                  onChange={setQuickFilter}
                  style={{ width: 150 }}
                  suffixIcon={<ExclamationCircleOutlined />}
                >
                  <Option value="all">All Events</Option>
                  <Option value="anomalies">
                    <Space>
                      <ExclamationCircleOutlined style={{ color: '#c75450' }} /> 
                      Anomalies
                      {anomalyCount > 0 && <Badge count={anomalyCount} size="small" style={{ marginLeft: 4 }} />}
                    </Space>
                  </Option>
                  <Option value="security">
                    <Space><SafetyCertificateOutlined style={{ color: '#c75450' }} /> Security</Space>
                  </Option>
                  <Option value="network">
                    <Space><ApiOutlined style={{ color: '#0891b2' }} /> Network</Space>
                  </Option>
                  <Option value="process">
                    <Space><ThunderboltOutlined style={{ color: '#7c8eb5' }} /> Process/File</Space>
                  </Option>
                  <Option value="errors">
                    <Space><CloseCircleOutlined style={{ color: '#c75450' }} /> Errors</Space>
                  </Option>
                  <Option value="high_volume">
                    <Space><BugOutlined style={{ color: '#b89b5d' }} /> High Volume</Space>
                  </Option>
                </Select>
              </Tooltip>
              
              {/* Auto Refresh */}
              <Tooltip title="Auto-refresh interval for live monitoring">
                <Select
                  value={autoRefreshInterval}
                  onChange={setAutoRefreshInterval}
                  style={{ width: 90 }}
                  suffixIcon={autoRefreshInterval > 0 ? <SyncOutlined spin style={{ color: '#4d9f7c' }} /> : <SyncOutlined />}
                >
                  {AUTO_REFRESH_OPTIONS.map(opt => (
                    <Option key={opt.value} value={opt.value}>
                      {opt.value === 0 ? 'Manual' : opt.label}
                    </Option>
                  ))}
                </Select>
              </Tooltip>
              
              <Button 
                icon={<ReloadOutlined />} 
                onClick={() => handleRefresh(false)}
                loading={isEventsLoading}
              >
                Refresh
              </Button>
              <Dropdown overlay={exportMenu} disabled={!selectedClusterId}>
                <Button icon={<DownloadOutlined />} loading={isExporting}>
                  Export
                </Button>
              </Dropdown>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Mini Timeline Chart */}
      {showTimeline && selectedAnalysisId && (
        <Card 
          bordered={false} 
          style={{ marginBottom: 16 }}
          title={
            <Space>
              <ClockCircleOutlined style={{ color: '#22a6a6' }} />
              <Text strong>Events Timeline</Text>
              {histogramData?.total_events != null && histogramData.total_events > 0 && (
                <Tag color="cyan" style={{ marginLeft: 4 }}>{histogramData.total_events.toLocaleString()} events</Tag>
              )}
              <Text type="secondary" style={{ fontSize: 12 }}>
                {timelineData.length > 0 && timelineData[0].startTime ? 
                  `(${timelineData[0].startTime.format('DD MMM HH:mm')} - ${timelineData[timelineData.length - 1].endTime?.format('DD MMM HH:mm') || 'Now'})` : 
                  isHistogramLoading ? '' : '(No data)'}
              </Text>
            </Space>
          }
          extra={
            <Button 
              size="small" 
              type="text" 
              icon={<CloseCircleOutlined />}
              onClick={() => setShowTimeline(false)}
            />
          }
          bodyStyle={{ padding: '12px 16px' }}
        >
          {isHistogramLoading ? (
            <Skeleton.Input active block style={{ height: 64 }} />
          ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {/* Bars */}
            <div style={{ display: 'flex', alignItems: 'flex-end', height: 64, gap: 1 }}>
              {timelineData.map((bucket, idx) => {
                const barHeight = bucket.count > 0 ? Math.max((bucket.count / timelineMax) * 58, 3) : 1;
                const eventTypeOrder = Object.keys(eventTypeConfig);
                const typeEntries = Object.entries(bucket.types)
                  .sort(([a], [b]) => eventTypeOrder.indexOf(a) - eventTypeOrder.indexOf(b));
                
                return (
                  <Tooltip 
                    key={idx} 
                    title={
                      <div>
                        <div><strong>{bucket.time}</strong></div>
                        {typeEntries.map(([type, count]) => (
                          <div key={type} style={{ color: eventTypeConfig[type]?.color }}>
                            {eventTypeConfig[type]?.label || type}: {count}
                          </div>
                        ))}
                        <div><strong>Total: {bucket.count}</strong></div>
                      </div>
                    }
                  >
                    <div
                      onClick={() => {
                        if (bucket.count > 0) {
                          setDateRange([bucket.startTime, bucket.endTime]);
                        }
                      }}
                      style={{
                        flex: 1,
                        height: barHeight,
                        borderRadius: 1,
                        cursor: bucket.count > 0 ? 'pointer' : 'default',
                        overflow: 'hidden',
                        display: 'flex',
                        flexDirection: 'column',
                        transition: 'opacity 0.2s ease',
                        opacity: bucket.count > 0 ? 1 : 0.3,
                        backgroundColor: bucket.count === 0 ? (isDark ? '#333' : '#f0f0f0') : undefined,
                      }}
                      onMouseEnter={(e) => { if (bucket.count > 0) e.currentTarget.style.opacity = '0.8'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.opacity = bucket.count > 0 ? '1' : '0.3'; }}
                    >
                      {bucket.count > 0 && typeEntries.map(([type, count]) => (
                        <div
                          key={type}
                          style={{
                            flex: count,
                            backgroundColor: eventTypeConfig[type]?.color || '#0891b2',
                            minHeight: 1,
                          }}
                        />
                      ))}
                    </div>
                  </Tooltip>
                );
              })}
            </div>
            {/* Time labels - 5 evenly spaced */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, paddingLeft: 2, paddingRight: 2 }}>
              {timelineData.length > 0 && [0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
                const idx = Math.min(Math.floor(pct * (timelineData.length - 1)), timelineData.length - 1);
                return (
                  <Text key={i} type="secondary" style={{ fontSize: 10 }}>
                    {timelineData[idx]?.time || ''}
                  </Text>
                );
              })}
            </div>
          </div>
          )}
          {/* Legend - show all types present in data */}
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }}>
            <Space size={12} wrap>
              {Object.entries(eventTypeConfig)
                .filter(([key]) => histogramData?.buckets?.some(b => key in b.types))
                .map(([key, config]) => (
                <Space key={key} size={4}>
                  <div style={{ width: 8, height: 8, backgroundColor: config.color, borderRadius: 2 }} />
                  <Text type="secondary" style={{ fontSize: 10 }}>{config.label}</Text>
                </Space>
              ))}
            </Space>
          </div>
        </Card>
      )}

      {/* Show Timeline Button (when hidden) */}
      {!showTimeline && selectedAnalysisId && (
        <Button 
          type="dashed" 
          block 
          style={{ marginBottom: 16 }}
          onClick={() => setShowTimeline(true)}
          icon={<ClockCircleOutlined />}
        >
          Show Events Timeline
        </Button>
      )}

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Tooltip title="Total number of events captured across all types">
            <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="Total Events"
              value={eventStats?.total_events || 0}
                prefix={<ClockCircleOutlined style={{ color: '#22a6a6' }} />}
              loading={isStatsLoading}
                valueStyle={{ fontSize: 22 }}
            />
          </Card>
          </Tooltip>
        </Col>
        {Object.entries(typeDistribution).slice(0, 5).map(([type, count]) => (
          <Col span={4} key={type}>
            <Tooltip title={`${eventTypeConfig[type]?.label || type} events captured by eBPF`}>
              <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
              <Statistic
                title={eventTypeConfig[type]?.label || type}
                value={count as number}
                prefix={eventTypeConfig[type]?.icon}
                  valueStyle={{ color: eventTypeConfig[type]?.color, fontSize: 22 }}
                  loading={isStatsLoading}
              />
            </Card>
            </Tooltip>
          </Col>
        ))}
      </Row>

      {/* Event Type Legend */}
      <Card bordered={false} style={{ marginBottom: 16 }} size="small">
        <Space wrap>
          <Text strong style={{ marginRight: 8 }}>Event Types:</Text>
          {Object.entries(eventTypeConfig).map(([key, config]) => (
            <Tag 
              key={key} 
              color={config.color} 
              icon={config.icon}
              style={{ cursor: 'pointer' }}
              onClick={() => {
                if (selectedTypes.includes(key)) {
                  setSelectedTypes(selectedTypes.filter(t => t !== key));
                } else {
                  setSelectedTypes([...selectedTypes, key]);
                }
              }}
            >
              {config.label} {typeDistribution[key] ? `(${typeDistribution[key]})` : ''}
            </Tag>
          ))}
        </Space>
      </Card>

      {/* Events Table */}
      <Card bordered={false}>
        {!selectedAnalysisId ? (
          <Empty description="Select an analysis to view events" />
        ) : isEventsLoading ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading events...</Text>
          </div>
        ) : groupByType && groupedEvents ? (
          /* Grouped View */
          <Table
            dataSource={groupedEvents}
            columns={[
              {
                title: 'Event Type',
                key: 'event_type',
                width: 200,
                render: (_: any, record: any) => {
                  const config = eventTypeConfig[record.event_type];
                  return (
                    <Tag color={config?.color} icon={config?.icon} style={{ fontSize: 13 }}>
                      {config?.label || record.event_type}
                    </Tag>
                  );
                },
              },
              {
                title: 'Count',
                dataIndex: 'count',
                key: 'count',
                width: 120,
                sorter: (a: any, b: any) => a.count - b.count,
                defaultSortOrder: 'descend',
                render: (count: number) => (
                  <Text strong style={{ fontSize: 16 }}>{count.toLocaleString()}</Text>
                ),
              },
              {
                title: 'Latest Event',
                dataIndex: 'latest_time',
                key: 'latest_time',
                width: 180,
                render: (time: string) => (
                  <Space>
                    <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                    <Text>{dayjs(time).format('HH:mm:ss')}</Text>
                  </Space>
                ),
              },
              {
                title: 'Sample Events',
                key: 'samples',
                render: (_: any, record: any) => (
                  <Space wrap size={4}>
                    {record.sample_events.slice(0, 3).map((e: any, idx: number) => (
                      <Tooltip key={idx} title={`${e.namespace}/${e.pod}: ${e.details || e.target || '-'}`}>
                        <Tag 
                          style={{ cursor: 'pointer', fontSize: 10 }} 
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setSelectedEvent(e);
                            setDetailModalVisible(true);
                          }}
                        >
                          {e.pod?.substring(0, 20) || e.namespace || 'event'}
                        </Tag>
                      </Tooltip>
                    ))}
                    {record.count > 3 && (
                      <Text type="secondary" style={{ fontSize: 11 }}>+{record.count - 3} more</Text>
                    )}
                  </Space>
                ),
              },
              {
                title: 'Anomalies',
                key: 'anomalies',
                width: 100,
                render: (_: any, record: any) => {
                  const anomalyCount = record.sample_events.filter((e: any) => isAnomalousEvent(e).isAnomaly).length;
                  if (anomalyCount === 0) return <Text type="secondary">—</Text>;
                  return (
                    <Badge count={anomalyCount} style={{ backgroundColor: '#c75450' }} />
                  );
                },
              },
            ]}
            rowKey="key"
            pagination={false}
            size="middle"
            expandable={{
              expandedRowRender: (record: any) => (
                <Table
                  dataSource={record.sample_events}
                  columns={columns}
                  rowKey={(r) => r.event_id || `${r.timestamp}-${Math.random()}`}
                  pagination={false}
                  size="small"
                  onRow={(r) => ({
                    onClick: () => {
                      setSelectedEvent(r);
                      setDetailModalVisible(true);
                    },
                    style: { cursor: 'pointer' }
                  })}
                />
              ),
              rowExpandable: (record: any) => record.sample_events.length > 0,
            }}
          />
        ) : (
          /* Normal View */
          <Table
            dataSource={filteredEvents}
            columns={columns}
            rowKey={(record) => record.event_id || `${record.timestamp}-${record.event_type}-${Math.random()}`}
            pagination={{ 
              ...pagination,
              total: eventsData?.total || 0,
              showSizeChanger: true,
              pageSizeOptions: ['20', '50', '100', '200'],
              showTotal: (total) => `Total ${total} events`,
              onChange: (page, pageSize) => {
                setPagination({ current: page, pageSize: pageSize || 50 });
              },
            }}
            size="middle"
            rowClassName={(record) => {
              const { isAnomaly } = isAnomalousEvent(record);
              return `event-row-${record.event_type}${isAnomaly ? ' anomaly-row' : ''}`;
            }}
            scroll={{ x: 1300 }}
            onRow={(record) => ({
              onClick: () => {
                setSelectedEvent(record);
                setDetailModalVisible(true);
              },
              style: { 
                cursor: 'pointer',
                backgroundColor: isAnomalousEvent(record).isAnomaly 
                  ? (isDark ? 'rgba(247, 110, 110, 0.15)' : '#fff2f0') 
                  : undefined,
              }
            })}
          />
        )}
      </Card>

      {/* Event Detail Modal */}
      <Modal
        title={
          <Space>
            {selectedEvent && eventTypeConfig[selectedEvent.event_type]?.icon}
            <span>Event Details</span>
            {selectedEvent && (
              <Tag color={eventTypeConfig[selectedEvent.event_type]?.color}>
                {eventTypeConfig[selectedEvent.event_type]?.label || selectedEvent.event_type}
              </Tag>
            )}
          </Space>
        }
        open={detailModalVisible}
        onCancel={() => {
          setDetailModalVisible(false);
          setSelectedEvent(null);
        }}
        footer={[
          <Button 
            key="copy" 
            icon={<CopyOutlined />} 
            onClick={() => copyToClipboard(selectedEvent)}
          >
            Copy JSON
          </Button>,
          <Button key="close" type="primary" onClick={() => setDetailModalVisible(false)}>
            Close
          </Button>
        ]}
        width={700}
      >
        {selectedEvent && (
          <Descriptions bordered column={2} size="small">
            {/* Anomaly Alert */}
            {isAnomalousEvent(selectedEvent).isAnomaly && (
              <Descriptions.Item label="⚠️ Anomaly Detected" span={2}>
                <Tag color="red" icon={<ExclamationCircleOutlined />}>
                  {isAnomalousEvent(selectedEvent).reason}
                </Tag>
              </Descriptions.Item>
            )}
            <Descriptions.Item label="Event ID" span={2}>
              <Text copyable code style={{ fontSize: 11 }}>{selectedEvent.event_id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Timestamp" span={2}>
              <Space>
                <ClockCircleOutlined />
                {dayjs(selectedEvent.timestamp).format('YYYY-MM-DD HH:mm:ss.SSS')}
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Namespace">
              <Tag>{selectedEvent.namespace || '-'}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Pod">
              <Text strong>{selectedEvent.pod || '-'}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Container">
              {selectedEvent.container || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="Event Type">
              <Tag color={eventTypeConfig[selectedEvent.event_type]?.color}>
                {eventTypeConfig[selectedEvent.event_type]?.label || selectedEvent.event_type}
              </Tag>
            </Descriptions.Item>
            {selectedEvent.source && (
              <Descriptions.Item label="Source" span={2}>
                <Text code>{selectedEvent.source}</Text>
              </Descriptions.Item>
            )}
            {selectedEvent.target && (
              <Descriptions.Item label="Target" span={2}>
                <Text code>{selectedEvent.target}</Text>
              </Descriptions.Item>
            )}
            {selectedEvent.details && (
              <Descriptions.Item label="Details" span={2}>
                <div style={{ 
                  background: isDark ? '#262626' : '#f5f5f5', 
                  padding: 12, 
                  borderRadius: 4,
                  maxHeight: 200,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: 12,
                  color: isDark ? 'rgba(255,255,255,0.85)' : 'inherit'
                }}>
                  {selectedEvent.details}
                </div>
              </Descriptions.Item>
            )}
            {selectedEvent.data && Object.keys(selectedEvent.data).length > 0 && (
              <Descriptions.Item label="Additional Data" span={2}>
                <div style={{ 
                  background: isDark ? '#1a2638' : '#f0f5ff', 
                  padding: 12, 
                  borderRadius: 4,
                  maxHeight: 200,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  fontFamily: 'monospace',
                  fontSize: 11,
                  color: isDark ? 'rgba(255,255,255,0.85)' : 'inherit'
                }}>
                  {JSON.stringify(selectedEvent.data, null, 2)}
                </div>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default EventsTimeline;
