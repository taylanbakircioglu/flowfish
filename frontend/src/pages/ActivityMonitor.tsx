import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
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
  Empty,
  Spin,
  Button,
  DatePicker,
  message,
  Tooltip,
  Modal,
  Descriptions,
  Switch,
  Segmented,
  Dropdown,
  theme
} from 'antd';
import type { MenuProps } from 'antd';
import { 
  ThunderboltOutlined,
  FileOutlined,
  DatabaseOutlined,
  SearchOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  StopOutlined,
  WarningOutlined,
  ApiOutlined,
  SwapOutlined,
  FilterOutlined,
  CopyOutlined,
  SyncOutlined,
  GroupOutlined,
  UnorderedListOutlined,
  ExclamationCircleOutlined,
  BugOutlined,
  SafetyCertificateOutlined,
  ApartmentOutlined,
  LinkOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { 
  useGetEventStatsQuery,
  useGetProcessEventsQuery,
  useGetFileEventsQuery,
  useGetMountEventsQuery,
  useGetNetworkFlowsQuery,
  ProcessEvent,
  FileEvent,
  MountEvent,
  NetworkFlowEvent
} from '../store/api/eventsApi';
import { Analysis } from '../types';
import { ClusterBadge } from '../components/Common';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

// File operation colors
const fileOpColors: Record<string, string> = {
  read: '#0891b2',
  write: '#b89b5d',
  open: '#4d9f7c',
  close: '#8c8c8c',
  delete: '#c75450',
  rename: '#7c8eb5',
  create: '#22a6a6',
  unlink: '#c75450',
};

// Process event subtype colors
const processSubtypeColors: Record<string, { color: string; icon: React.ReactNode }> = {
  exec: { color: '#4d9f7c', icon: <PlayCircleOutlined /> },
  exit: { color: '#8c8c8c', icon: <StopOutlined /> },
  signal: { color: '#b89b5d', icon: <WarningOutlined /> },
};

// Suspicious process patterns for anomaly detection
const SUSPICIOUS_PATTERNS = {
  // Shell spawning (potential reverse shell)
  shells: ['/bin/sh', '/bin/bash', '/bin/zsh', '/bin/dash', '/bin/ash', 'sh', 'bash', 'zsh'],
  // Privilege escalation tools
  privesc: ['sudo', 'su', 'doas', 'pkexec', 'setuid'],
  // Network tools (potential data exfiltration)
  network: ['curl', 'wget', 'nc', 'netcat', 'ncat', 'socat', 'telnet', 'ssh', 'scp', 'rsync'],
  // Reconnaissance tools
  recon: ['nmap', 'masscan', 'zmap', 'nikto', 'dirb', 'gobuster', 'ffuf'],
  // Crypto miners
  miners: ['xmrig', 'minerd', 'cpuminer', 'cgminer', 'bfgminer', 'ethminer'],
  // Sensitive file access
  sensitive: ['/etc/passwd', '/etc/shadow', '/etc/sudoers', '.ssh', 'id_rsa', '.kube/config', '.aws/credentials'],
  // Package managers in running containers (suspicious)
  packageMgrs: ['apt', 'apt-get', 'yum', 'dnf', 'apk', 'pip', 'npm', 'gem'],
};

// Quick filter presets
type QuickFilterType = 'all' | 'suspicious' | 'shells' | 'network' | 'errors' | 'high_activity';

// Auto-refresh intervals
const AUTO_REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
];

const ActivityMonitor: React.FC = () => {
  const { token } = theme.useToken();
  const [searchParams] = useSearchParams();
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [searchTerm, setSearchTerm] = useState('');
  // Server-side search: debounced search term for API calls (min 3 chars)
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  
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
  
  const [activeTab, setActiveTab] = useState('processes');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [selectedNamespace, setSelectedNamespace] = useState<string | undefined>(undefined);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50 });
  const [eventDetailVisible, setEventDetailVisible] = useState(false);
  const [selectedActivityEvent, setSelectedActivityEvent] = useState<any>(null);
  
  // New feature states
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(0);
  const [groupByProcess, setGroupByProcess] = useState(false);
  const [quickFilter, setQuickFilter] = useState<QuickFilterType>('all');
  const [relatedEventsVisible, setRelatedEventsVisible] = useState(false);
  const [relatedEventsData, setRelatedEventsData] = useState<{ process: any; files: any[]; network: any[] } | null>(null);
  const [processTreeVisible, setProcessTreeVisible] = useState(false);
  const [processTreeData, setProcessTreeData] = useState<any[]>([]);
  const [showTimeline, setShowTimeline] = useState(true);
  const autoRefreshTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  // Reset pagination when search or filters change
  useEffect(() => {
    setPagination(prev => ({ ...prev, current: 1 }));
  }, [debouncedSearchTerm, dateRange, selectedNamespace]);

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

  // Handle analysis change - set analysis ID and clear cluster (useEffect will set correct cluster)
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    // Always clear clusterId immediately - useEffect will set the correct one
    // This prevents race condition where old clusterId is used with new analysisId
    setSelectedClusterId(undefined);
  }, []);

  // Auto-set cluster when analysis changes (separate effect to avoid stale closure)
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        setSelectedClusterId(analysis.cluster_id);
      }
    }
  }, [selectedAnalysisId, analyses]);

  // Get selected analysis details for multi-cluster detection
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

  const queryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    namespace: selectedNamespace || undefined,
    // Server-side search - filters at the database level for accurate results
    search: debouncedSearchTerm || undefined,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: pagination.pageSize,
    offset: (pagination.current - 1) * pagination.pageSize,
  }), [selectedClusterId, selectedAnalysisId, selectedNamespace, debouncedSearchTerm, dateRange, pagination]);

  // Stats query with time range
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

  const { data: processData, isLoading: isProcessLoading, refetch: refetchProcess } = useGetProcessEventsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: fileData, isLoading: isFileLoading, refetch: refetchFile } = useGetFileEventsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: mountData, isLoading: isMountLoading, refetch: refetchMount } = useGetMountEventsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: networkData, isLoading: isNetworkLoading, refetch: refetchNetwork } = useGetNetworkFlowsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  /**
   * Smart matching for paths, pod names, namespaces.
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
   * Simple contains for short keywords
   */
  const simpleMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    return value.toLowerCase().includes(search.toLowerCase());
  }, []);

  // Client-side search helper - fallback filter after server-side search
  // This ensures UI always shows correct results even if server returns unfiltered data
  const matchesSearch = useCallback((term: string, ...values: (string | number | undefined | null)[]): boolean => {
    if (!term || term.length < 3) return true;
    const searchLower = term.toLowerCase().trim();
    return values.some(v => {
      if (v === null || v === undefined) return false;
      return String(v).toLowerCase().includes(searchLower);
    });
  }, []);

  // Process events - search in pod, namespace, comm, exe, args
  const processMatchesSearch = useCallback((e: ProcessEvent, term: string): boolean => {
    if (!term || term.length < 3) return true;
    
    // Smart match for pod, namespace, executable path
    if (smartMatch(e.pod, term)) return true;
    if (smartMatch(e.namespace, term)) return true;
    if (smartMatch(e.exe, term)) return true;
    if (smartMatch(e.comm, term)) return true;
    
    // Simple match for event_subtype (exec, exit, signal)
    if (simpleMatch(e.event_subtype, term)) return true;
    
    // Smart match for args array
    if (e.args?.some(arg => smartMatch(arg, term))) return true;
    
    // Exact match for PID
    if (e.pid?.toString() === term) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

  // File events - search in pod, namespace, file_path, comm, operation
  const fileMatchesSearch = useCallback((e: FileEvent, term: string): boolean => {
    if (!term || term.length < 3) return true;
    
    // Smart match for pod, namespace, file path, comm
    if (smartMatch(e.pod, term)) return true;
    if (smartMatch(e.namespace, term)) return true;
    if (smartMatch(e.file_path, term)) return true;
    if (smartMatch(e.comm, term)) return true;
    
    // Simple match for operation (read, write, open, etc.)
    if (simpleMatch(e.operation, term)) return true;
    
    // Exact match for PID
    if (e.pid?.toString() === term) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

  // Mount events - search in pod, namespace, source, target, fs_type
  const mountMatchesSearch = useCallback((e: MountEvent, term: string): boolean => {
    if (!term || term.length < 3) return true;
    
    // Smart match for pod, namespace, source path, target path
    if (smartMatch(e.pod, term)) return true;
    if (smartMatch(e.namespace, term)) return true;
    if (smartMatch(e.source, term)) return true;
    if (smartMatch(e.target, term)) return true;
    if (smartMatch(e.comm, term)) return true;
    
    // Simple match for operation, fs_type
    if (simpleMatch(e.operation, term)) return true;
    if (simpleMatch(e.fs_type, term)) return true;
    
    // Exact match for PID
    if (e.pid?.toString() === term) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

  // Network flows - search in pod, namespace, IPs, protocol
  const networkMatchesSearch = useCallback((e: NetworkFlowEvent, term: string): boolean => {
    if (!term || term.length < 3) return true;
    
    // Smart match for pod, namespace, IPs
    if (smartMatch(e.pod, term)) return true;
    if (smartMatch(e.namespace, term)) return true;
    if (smartMatch(e.source_ip, term)) return true;
    if (smartMatch(e.dest_ip, term)) return true;
    if (smartMatch(e.source_pod, term)) return true;
    if (smartMatch(e.dest_pod, term)) return true;
    if (smartMatch(e.comm, term)) return true;
    
    // Simple match for protocol, direction
    if (simpleMatch(e.protocol, term)) return true;
    if (simpleMatch(e.direction, term)) return true;
    
    // Exact match for ports
    if (e.source_port?.toString() === term) return true;
    if (e.dest_port?.toString() === term) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

  // Check if a process is suspicious (moved before filteredProcesses to avoid hoisting issue)
  const isSuspiciousProcess = useCallback((event: ProcessEvent): { suspicious: boolean; reason: string } => {
    const exe = (event.exe || '').toLowerCase();
    const comm = (event.comm || '').toLowerCase();
    const args = (event.args || []).join(' ').toLowerCase();
    const combined = `${exe} ${comm} ${args}`;
    
    // Check shells
    if (SUSPICIOUS_PATTERNS.shells.some(s => comm === s || exe.endsWith(`/${s}`))) {
      return { suspicious: true, reason: 'Shell execution' };
    }
    
    // Check privilege escalation
    if (SUSPICIOUS_PATTERNS.privesc.some(p => comm === p || exe.includes(p))) {
      return { suspicious: true, reason: 'Privilege escalation' };
    }
    
    // Check network tools
    if (SUSPICIOUS_PATTERNS.network.some(n => comm === n || exe.includes(n))) {
      return { suspicious: true, reason: 'Network tool' };
    }
    
    // Check recon tools
    if (SUSPICIOUS_PATTERNS.recon.some(r => comm === r || exe.includes(r))) {
      return { suspicious: true, reason: 'Reconnaissance tool' };
    }
    
    // Check miners
    if (SUSPICIOUS_PATTERNS.miners.some(m => combined.includes(m))) {
      return { suspicious: true, reason: 'Crypto miner' };
    }
    
    // Check sensitive file access
    if (SUSPICIOUS_PATTERNS.sensitive.some(s => combined.includes(s))) {
      return { suspicious: true, reason: 'Sensitive file access' };
    }
    
    // Check package managers
    if (SUSPICIOUS_PATTERNS.packageMgrs.some(p => comm === p || exe.endsWith(`/${p}`))) {
      return { suspicious: true, reason: 'Package manager in container' };
    }
    
    return { suspicious: false, reason: '' };
  }, []);

  // Filter process events
  const filteredProcesses = useMemo(() => {
    if (!processData?.events) return [];
    
    let filtered = processData.events
      .filter((e: ProcessEvent) => processMatchesSearch(e, debouncedSearchTerm))
      .map((e: ProcessEvent) => {
        const suspiciousCheck = isSuspiciousProcess(e);
        return {
        key: `${e.timestamp}-${e.pid}-${e.pod}`,
        ...e,
          isSuspicious: suspiciousCheck.suspicious,
          suspiciousReason: suspiciousCheck.reason,
        };
      });
    
    // Apply quick filters
    if (quickFilter !== 'all') {
      switch (quickFilter) {
        case 'suspicious':
          filtered = filtered.filter(e => e.isSuspicious);
          break;
        case 'shells':
          filtered = filtered.filter(e => {
            const comm = (e.comm || '').toLowerCase();
            const exe = (e.exe || '').toLowerCase();
            return SUSPICIOUS_PATTERNS.shells.some(s => comm === s || exe.endsWith(`/${s}`));
          });
          break;
        case 'network':
          filtered = filtered.filter(e => {
            const comm = (e.comm || '').toLowerCase();
            const exe = (e.exe || '').toLowerCase();
            return SUSPICIOUS_PATTERNS.network.some(n => comm === n || exe.includes(n));
          });
          break;
        case 'errors':
          filtered = filtered.filter(e => e.exit_code !== 0 && e.exit_code !== undefined);
          break;
        case 'high_activity':
          // Group by comm and filter those with > 10 occurrences
          const commCounts: Record<string, number> = {};
          filtered.forEach(e => {
            const key = e.comm || 'unknown';
            commCounts[key] = (commCounts[key] || 0) + 1;
          });
          const highActivityComms = Object.keys(commCounts).filter(k => commCounts[k] > 10);
          filtered = filtered.filter(e => highActivityComms.includes(e.comm || 'unknown'));
          break;
      }
    }
    
    // Group by process if enabled
    if (groupByProcess && filtered.length > 0) {
      const groupMap = new Map<string, any>();
      
      filtered.forEach((event) => {
        const key = `${event.pod}|${event.namespace}|${event.comm}|${event.exe}`;
        const existing = groupMap.get(key);
        
        if (existing) {
          existing.eventCount = (existing.eventCount || 1) + 1;
          // Keep latest timestamp
          if (event.timestamp > existing.timestamp) {
            existing.timestamp = event.timestamp;
            existing.exit_code = event.exit_code;
          }
        } else {
          groupMap.set(key, { ...event, eventCount: 1 });
        }
      });
      
      return Array.from(groupMap.values());
    }
    
    return filtered;
  }, [processData?.events, debouncedSearchTerm, processMatchesSearch, isSuspiciousProcess, quickFilter, groupByProcess]);

  // Count suspicious processes for badge
  const suspiciousCount = useMemo(() => {
    if (!processData?.events) return 0;
    return processData.events.filter((e: ProcessEvent) => isSuspiciousProcess(e).suspicious).length;
  }, [processData?.events, isSuspiciousProcess]);

  // Timeline data - aggregate events by time buckets (last 60 minutes, 1-minute buckets)
  // Timeline data - aggregate events from loaded data into buckets
  const timelineData = useMemo(() => {
    const buckets: { time: string; process: number; file: number; mount: number; network: number; total: number; startTime: dayjs.Dayjs; endTime: dayjs.Dayjs }[] = [];
    
    // Collect all timestamps from loaded events
    const allTimestamps: dayjs.Dayjs[] = [];
    
    processData?.events?.forEach((e: ProcessEvent) => {
      if (e.timestamp) allTimestamps.push(dayjs(e.timestamp));
    });
    fileData?.events?.forEach((e: FileEvent) => {
      if (e.timestamp) allTimestamps.push(dayjs(e.timestamp));
    });
    mountData?.events?.forEach((e: MountEvent) => {
      if (e.timestamp) allTimestamps.push(dayjs(e.timestamp));
    });
    networkData?.events?.forEach((e: NetworkFlowEvent) => {
      if (e.timestamp) allTimestamps.push(dayjs(e.timestamp));
    });
    
    if (allTimestamps.length === 0) {
      // No events, return empty buckets
      const now = dayjs();
      for (let i = 59; i >= 0; i--) {
        const bucketTime = now.subtract(i, 'minute');
        buckets.push({
          time: bucketTime.format('HH:mm'),
          process: 0, file: 0, mount: 0, network: 0, total: 0,
          startTime: bucketTime, endTime: bucketTime.add(1, 'minute')
        });
      }
      return buckets;
    }
    
    // Find min and max timestamps from loaded data
    const minTime = allTimestamps.reduce((min, t) => t.isBefore(min) ? t : min, allTimestamps[0]);
    const maxTime = allTimestamps.reduce((max, t) => t.isAfter(max) ? t : max, allTimestamps[0]);
    
    // Calculate bucket size based on time range
    const rangeMinutes = maxTime.diff(minTime, 'minute');
    const bucketCount = 60;
    const bucketSizeMinutes = Math.max(1, Math.ceil(rangeMinutes / bucketCount));
    
    // Create buckets spanning the data range
    const startTime = minTime.startOf('minute');
    for (let i = 0; i < bucketCount; i++) {
      const bucketStart = startTime.add(i * bucketSizeMinutes, 'minute');
      const bucketEnd = bucketStart.add(bucketSizeMinutes, 'minute');
      
      // Format label based on bucket size
      let timeLabel: string;
      if (bucketSizeMinutes <= 1) {
        timeLabel = bucketStart.format('HH:mm');
      } else if (bucketSizeMinutes < 60) {
        timeLabel = bucketStart.format('HH:mm');
      } else if (bucketSizeMinutes < 1440) {
        timeLabel = bucketStart.format('HH:mm');
      } else {
        timeLabel = bucketStart.format('MM/DD HH:mm');
      }
      
      buckets.push({
        time: timeLabel,
        process: 0, file: 0, mount: 0, network: 0, total: 0,
        startTime: bucketStart, endTime: bucketEnd
      });
    }
    
    // Count events in each bucket
    const countInBucket = (timestamp: string): number => {
      const eventTime = dayjs(timestamp);
      const eventUnix = eventTime.unix();
      for (let i = 0; i < buckets.length; i++) {
        const startUnix = buckets[i].startTime.unix();
        const endUnix = buckets[i].endTime.unix();
        if (eventUnix >= startUnix && eventUnix < endUnix) {
          return i;
        }
      }
      // Check last bucket (inclusive end)
      if (eventUnix >= buckets[buckets.length - 1].startTime.unix()) {
        return buckets.length - 1;
      }
      return -1;
    };
    
    processData?.events?.forEach((e: ProcessEvent) => {
      const idx = countInBucket(e.timestamp);
      if (idx >= 0) {
        buckets[idx].process++;
        buckets[idx].total++;
      }
    });
    
    fileData?.events?.forEach((e: FileEvent) => {
      const idx = countInBucket(e.timestamp);
      if (idx >= 0) {
        buckets[idx].file++;
        buckets[idx].total++;
      }
    });
    
    mountData?.events?.forEach((e: MountEvent) => {
      const idx = countInBucket(e.timestamp);
      if (idx >= 0) {
        buckets[idx].mount++;
        buckets[idx].total++;
      }
    });
    
    networkData?.events?.forEach((e: NetworkFlowEvent) => {
      const idx = countInBucket(e.timestamp);
      if (idx >= 0) {
        buckets[idx].network++;
        buckets[idx].total++;
      }
    });
    
    // Debug: log timeline data
    const totalEvents = buckets.reduce((sum, b) => sum + b.total, 0);
    if (totalEvents > 0) {
      console.log('[Timeline] Total events in buckets:', totalEvents, 'Bucket range:', buckets[0]?.time, '-', buckets[buckets.length - 1]?.time);
    }
    
    return buckets;
  }, [processData?.events, fileData?.events, mountData?.events, networkData?.events]);

  // Max value for timeline scaling
  const timelineMax = useMemo(() => {
    return Math.max(...timelineData.map(b => b.total), 1);
  }, [timelineData]);

  // Build process tree from parent-child relationships
  const buildProcessTree = useCallback(() => {
    if (!processData?.events || processData.events.length === 0) {
      setProcessTreeData([]);
      setProcessTreeVisible(true);
      return;
    }
    
    // Use all process events (not just exec), filter by valid PID
    const processes = processData.events.filter((e: ProcessEvent) => e.pid > 0);
    
    if (processes.length === 0) {
      setProcessTreeData([]);
      setProcessTreeVisible(true);
      return;
    }
    
    const pidMap = new Map<number, any>();
    const roots: any[] = [];
    
    // First pass: create nodes (use latest event for each PID)
    processes.forEach((p: ProcessEvent) => {
      const existingNode = pidMap.get(p.pid);
      // Keep the most recent event for each PID
      if (!existingNode || dayjs(p.timestamp).isAfter(dayjs(existingNode.timestamp))) {
        const suspCheck = isSuspiciousProcess(p);
        pidMap.set(p.pid, {
          ...p,
          key: `${p.pid}-${p.timestamp}`,
          children: [],
          isSuspicious: suspCheck.suspicious,
          suspiciousReason: suspCheck.reason
        });
      }
    });
    
    // Second pass: build tree based on PPID relationships
    pidMap.forEach((node) => {
      if (node.ppid > 0 && pidMap.has(node.ppid)) {
        const parent = pidMap.get(node.ppid);
        // Avoid adding duplicates
        if (!parent.children.find((c: any) => c.pid === node.pid)) {
          parent.children.push(node);
        }
      } else {
        roots.push(node);
      }
    });
    
    // Sort roots by timestamp (newest first)
    roots.sort((a, b) => dayjs(b.timestamp).unix() - dayjs(a.timestamp).unix());
    
    // Sort children by timestamp
    const sortChildren = (nodes: any[]) => {
      nodes.forEach(node => {
        if (node.children && node.children.length > 0) {
          node.children.sort((a: any, b: any) => dayjs(b.timestamp).unix() - dayjs(a.timestamp).unix());
          sortChildren(node.children);
        }
      });
    };
    sortChildren(roots);
    
    // Debug: log tree building results
    console.log('[ProcessTree] Total events:', processData?.events?.length, 
      'With valid PID:', processes.length, 
      'Unique PIDs:', pidMap.size, 
      'Root processes:', roots.length);
    
    // Sample first few events to check PID values
    if (processData?.events?.length > 0) {
      const sample = processData.events.slice(0, 3);
      console.log('[ProcessTree] Sample events PID/PPID:', sample.map((e: ProcessEvent) => ({ pid: e.pid, ppid: e.ppid, comm: e.comm })));
    }
    
    setProcessTreeData(roots.slice(0, 100)); // Limit to 100 root processes
    setProcessTreeVisible(true);
  }, [processData?.events, isSuspiciousProcess]);

  // Filter file events
  const filteredFileOps = useMemo(() => {
    if (!fileData?.events) return [];
    
    return fileData.events
      .filter((e: FileEvent) => fileMatchesSearch(e, debouncedSearchTerm))
      .map((e: FileEvent) => ({
        key: `${e.timestamp}-${e.pid}-${e.file_path}`,
        ...e,
      }));
  }, [fileData?.events, debouncedSearchTerm, fileMatchesSearch]);

  // Filter mount events
  const filteredMounts = useMemo(() => {
    if (!mountData?.events) return [];
    
    return mountData.events
      .filter((e: MountEvent) => mountMatchesSearch(e, debouncedSearchTerm))
      .map((e: MountEvent) => ({
        key: `${e.timestamp}-${e.pod}-${e.target}`,
        ...e,
      }));
  }, [mountData?.events, debouncedSearchTerm, mountMatchesSearch]);

  // Filter network flows
  const filteredNetworkFlows = useMemo(() => {
    if (!networkData?.events) return [];
    
    return networkData.events
      .filter((e: NetworkFlowEvent) => networkMatchesSearch(e, debouncedSearchTerm))
      .map((e: NetworkFlowEvent) => ({
        key: `${e.timestamp}-${e.source_ip}-${e.dest_ip}-${e.source_port}`,
        ...e,
        totalBytes: (e.bytes_sent || 0) + (e.bytes_received || 0),
      }));
  }, [networkData?.events, debouncedSearchTerm, networkMatchesSearch]);

  // Get unique namespaces from all data sources for filter dropdown
  const availableNamespaces = useMemo(() => {
    const namespaces = new Set<string>();
    
    processData?.events?.forEach((e: ProcessEvent) => e.namespace && namespaces.add(e.namespace));
    fileData?.events?.forEach((e: FileEvent) => e.namespace && namespaces.add(e.namespace));
    mountData?.events?.forEach((e: MountEvent) => e.namespace && namespaces.add(e.namespace));
    networkData?.events?.forEach((e: NetworkFlowEvent) => e.namespace && namespaces.add(e.namespace));
    
    return Array.from(namespaces).sort();
  }, [processData?.events, fileData?.events, mountData?.events, networkData?.events]);

  // Calculate total network bytes for stats
  const totalNetworkBytes = useMemo(() => {
    return filteredNetworkFlows.reduce((sum: number, f: any) => sum + (f.totalBytes || 0), 0);
  }, [filteredNetworkFlows]);

  // Refresh handler
  const handleRefresh = useCallback((silent = false) => {
    refetchProcess();
    refetchFile();
    refetchMount();
    refetchNetwork();
    refetchStats();
    if (!silent) message.success('Data refreshed');
  }, [refetchProcess, refetchFile, refetchMount, refetchNetwork, refetchStats]);

  // Auto-refresh effect
  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = null;
    }
    
    if (autoRefreshInterval > 0 && selectedAnalysisId) {
      autoRefreshTimerRef.current = setInterval(() => {
        handleRefresh(true); // Silent refresh
      }, autoRefreshInterval);
    }
    
    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [autoRefreshInterval, selectedAnalysisId, handleRefresh]);

  // Find related events for a process
  const findRelatedEvents = useCallback((processEvent: ProcessEvent) => {
    const pod = processEvent.pod;
    const namespace = processEvent.namespace;
    const pid = processEvent.pid;
    const comm = processEvent.comm;
    
    // Find related file operations
    const relatedFiles = (fileData?.events || []).filter((f: FileEvent) => 
      f.pod === pod && f.namespace === namespace && (f.pid === pid || f.comm === comm)
    ).slice(0, 20);
    
    // Find related network flows (NetworkFlowEvent doesn't have pid, match by pod/namespace/comm)
    const relatedNetwork = (networkData?.events || []).filter((n: NetworkFlowEvent) => 
      n.pod === pod && n.namespace === namespace && n.comm === comm
    ).slice(0, 20);
    
    setRelatedEventsData({
      process: processEvent,
      files: relatedFiles,
      network: relatedNetwork
    });
    setRelatedEventsVisible(true);
  }, [fileData?.events, networkData?.events]);

  // Copy event to clipboard
  const copyToClipboard = useCallback((event: any) => {
    const jsonStr = JSON.stringify(event, null, 2);
    navigator.clipboard.writeText(jsonStr).then(() => {
      message.success('Event copied to clipboard');
    }).catch(() => {
      message.error('Failed to copy');
    });
  }, []);

  // Export handler - exports current tab data to JSON with rich metadata
  const handleExport = useCallback(() => {
    if (!selectedAnalysisId) {
      message.warning('Please select an analysis first');
      return;
    }

    let data: any[] = [];
    let dataTypeLabel = '';
    const timestamp = dayjs().format('YYYYMMDD_HHmmss');

    // Get analysis and cluster info for metadata
    const analysisInfo = selectedAnalysis;
    const clusterInfo = selectedClusterId ? clusterInfoMap.get(selectedClusterId) : null;
    
    // Helper to enrich data with cluster names
    const enrichWithClusterName = (items: any[]) => {
      return items.map(item => {
        const cluster = clusterInfoMap.get(item.cluster_id);
        return {
          ...item,
          cluster_name: cluster?.name || `Cluster ${item.cluster_id}`
        };
      });
    };

    switch (activeTab) {
      case 'processes':
        data = enrichWithClusterName(filteredProcesses);
        dataTypeLabel = 'Process Events';
        break;
      case 'files':
        data = enrichWithClusterName(filteredFileOps);
        dataTypeLabel = 'File Operations';
        break;
      case 'mounts':
        data = enrichWithClusterName(filteredMounts);
        dataTypeLabel = 'Mount Events';
        break;
      case 'network':
        data = enrichWithClusterName(filteredNetworkFlows);
        dataTypeLabel = 'Network Flows';
        break;
      default:
        message.error('Unknown tab');
        return;
    }

    if (data.length === 0) {
      message.warning('No data to export');
      return;
    }

    // Build filename with analysis name if available
    const analysisName = analysisInfo?.name?.replace(/[^a-zA-Z0-9]/g, '_') || `analysis_${selectedAnalysisId}`;
    const filename = `flowfish_${activeTab}_${analysisName}_${timestamp}.json`;

    // Calculate summary statistics
    const uniqueNamespaces = Array.from(new Set(data.map(d => d.namespace).filter(Boolean)));
    const uniquePods = Array.from(new Set(data.map(d => d.pod).filter(Boolean)));
    const uniqueClusters = Array.from(new Set(data.map(d => d.cluster_id).filter(Boolean)));

    const exportData = {
      metadata: {
        format: 'Flowfish Activity Monitor Export',
        version: '1.0',
        export_time: dayjs().toISOString(),
        exported_by: 'Flowfish Platform'
      },
      analysis: {
        id: selectedAnalysisId,
        name: analysisInfo?.name || null,
        status: analysisInfo?.status || null,
        is_multi_cluster: isMultiClusterAnalysis,
        cluster_ids: analysisInfo?.cluster_ids || [selectedClusterId]
      },
      cluster: isMultiClusterAnalysis ? {
        type: 'multi-cluster',
        clusters: uniqueClusters.map(cid => {
          const c = clusterInfoMap.get(cid);
          return { id: cid, name: c?.name || `Cluster ${cid}` };
        })
      } : {
        type: 'single-cluster',
        id: selectedClusterId,
        name: clusterInfo?.name || `Cluster ${selectedClusterId}`,
        environment: clusterInfo?.environment || null
      },
      data_info: {
        type: activeTab,
        type_label: dataTypeLabel,
        total_records: data.length,
        unique_namespaces: uniqueNamespaces.length,
        unique_pods: uniquePods.length,
        namespaces: uniqueNamespaces.slice(0, 50), // Limit to 50 for readability
        pods_sample: uniquePods.slice(0, 20) // Sample of pods
      },
      filters: {
        search_term: searchTerm || null,
        date_range: dateRange ? {
          start: dateRange[0].toISOString(),
          end: dateRange[1].toISOString()
        } : null
      },
      statistics: {
        event_counts: eventStats?.event_counts || {},
        total_events: eventStats?.total_events || 0
      },
      data: data
    };

    const jsonContent = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonContent], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    
    message.success(`Exported ${data.length} ${dataTypeLabel.toLowerCase()} to ${filename}`);
  }, [activeTab, selectedAnalysisId, selectedClusterId, selectedAnalysis, isMultiClusterAnalysis, clusterInfoMap, searchTerm, dateRange, eventStats, filteredProcesses, filteredFileOps, filteredMounts, filteredNetworkFlows]);

  // Format bytes helper
  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  // Helper to add cluster column for multi-cluster analysis
  const addClusterColumn = useCallback((columns: any[], eventType: 'process' | 'file' | 'mount' | 'network') => {
    if (!isMultiClusterAnalysis) return columns;
    
    const clusterColumn = {
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
    };
    
    // Insert after timestamp column (index 1)
    const newColumns = [...columns];
    newColumns.splice(1, 0, clusterColumn);
    return newColumns;
  }, [isMultiClusterAnalysis, clusterInfoMap]);

  // Process table columns
  const processColumns = [
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 140,
      render: (ts: string, record: any) => (
        <Space>
          <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
          <Text type="secondary">{dayjs(ts).format('HH:mm:ss.SSS')}</Text>
          {record.eventCount > 1 && (
            <Tag color="purple" style={{ fontSize: 10 }}>×{record.eventCount}</Tag>
          )}
        </Space>
      ),
      sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
    },
    {
      title: 'Pod',
      key: 'pod',
      render: (_: any, record: any) => (
        <Space direction="vertical" size={0}>
          <Space>
          <Text strong>{record.pod}</Text>
            {record.isSuspicious && (
              <Tooltip title={record.suspiciousReason}>
                <Tag color="red" style={{ fontSize: 10, marginLeft: 4 }}>
                  <BugOutlined /> {record.suspiciousReason}
                </Tag>
              </Tooltip>
            )}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Process',
      key: 'process',
      render: (_: any, record: any) => {
        // Get process name from comm, or extract from exe/args
        let processName = record.comm;
        if (!processName && record.exe) {
          processName = record.exe.split('/').pop() || record.exe;
        }
        if (!processName && record.args?.length) {
          const firstArg = record.args[0] || '';
          processName = firstArg.split('/').pop() || firstArg;
        }
        
        return (
          <Space direction="vertical" size={0}>
            <Space>
              <ThunderboltOutlined style={{ color: record.isSuspicious ? '#c75450' : '#7c8eb5' }} />
              <Text strong style={{ color: record.isSuspicious ? '#c75450' : undefined }}>
                {processName || '-'}
              </Text>
              {record.pid > 0 && <Text type="secondary">({record.pid})</Text>}
            </Space>
            {record.ppid > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>Parent PID: {record.ppid}</Text>
            )}
          </Space>
        );
      },
    },
    {
      title: 'Command',
      key: 'command',
      ellipsis: true,
      render: (_: any, record: any) => {
        // Build command string from exe and/or args
        const argsStr = (record.args || []).join(' ');
        const command = record.exe 
          ? `${record.exe} ${argsStr}`.trim()
          : argsStr || record.comm || '-';
        
        return (
          <Tooltip title={command}>
            <Text code style={{ fontSize: 11, color: record.isSuspicious ? '#c75450' : undefined }}>
              {command.length > 80 ? `${command.slice(0, 80)}...` : command}
            </Text>
          </Tooltip>
        );
      },
    },
    {
      title: 'Event Type',
      dataIndex: 'event_subtype',
      key: 'event_subtype',
      width: 100,
      filters: [
        { text: 'Exec', value: 'exec' },
        { text: 'Exit', value: 'exit' },
        { text: 'Signal', value: 'signal' },
      ],
      onFilter: (value: any, record: any) => record.event_subtype === value,
      render: (subtype: string) => {
        const config = processSubtypeColors[subtype] || { color: '#8c8c8c', icon: null };
        return (
          <Tag color={config.color} icon={config.icon}>
            {subtype?.toUpperCase() || 'EXEC'}
          </Tag>
        );
      },
    },
    {
      title: 'Exit Code',
      key: 'exit_code',
      width: 90,
      render: (_: any, record: ProcessEvent) => {
        if (record.event_subtype !== 'exit') return '-';
        return (
          <Tag color={record.exit_code === 0 ? 'green' : 'red'}>
            {record.exit_code}
          </Tag>
        );
      },
    },
  ];

  // File operations columns
  const fileColumns = [
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
      render: (_: any, record: FileEvent) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.pod}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Path',
      dataIndex: 'file_path',
      key: 'path',
      ellipsis: true,
      render: (path: string) => (
        <Tooltip title={path}>
          <Space>
            <FileOutlined style={{ color: '#a67c9e' }} />
            <Text code style={{ fontSize: 11 }}>{path}</Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Operation',
      dataIndex: 'operation',
      key: 'operation',
      width: 100,
      filters: [
        { text: 'Read', value: 'read' },
        { text: 'Write', value: 'write' },
        { text: 'Open', value: 'open' },
        { text: 'Close', value: 'close' },
        { text: 'Delete', value: 'delete' },
      ],
      onFilter: (value: any, record: any) => record.operation === value,
      render: (op: string) => (
        <Tag color={fileOpColors[op] || '#8c8c8c'}>
          {op?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Bytes',
      dataIndex: 'bytes',
      key: 'bytes',
      width: 90,
      render: (bytes: number) => formatBytes(bytes),
      sorter: (a: any, b: any) => (a.bytes || 0) - (b.bytes || 0),
    },
    {
      title: 'Duration',
      dataIndex: 'duration_us',
      key: 'duration',
      width: 100,
      render: (us: number) => us ? `${(us / 1000).toFixed(2)} ms` : '-',
      sorter: (a: any, b: any) => (a.duration_us || 0) - (b.duration_us || 0),
    },
    {
      title: 'Process',
      key: 'process',
      width: 120,
      render: (_: any, record: FileEvent) => (
        <Text type="secondary">{record.comm} ({record.pid})</Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'error_code',
      key: 'status',
      width: 80,
      render: (error: number) => (
        error === 0 ? 
          <Tag color="green"><CheckCircleOutlined /> OK</Tag> : 
          <Tag color="red"><CloseCircleOutlined /> {error}</Tag>
      ),
    },
  ];

  // Mount columns
  const mountColumns = [
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
      render: (_: any, record: MountEvent) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.pod}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Operation',
      dataIndex: 'operation',
      key: 'operation',
      width: 100,
      filters: [
        { text: 'Mount', value: 'mount' },
        { text: 'Umount', value: 'umount' },
      ],
      onFilter: (value: any, record: any) => record.operation === value,
      render: (op: string) => (
        <Tag color={op === 'mount' ? 'green' : 'orange'}>
          {op?.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      ellipsis: true,
      render: (source: string) => (
        <Tooltip title={source}>
          <Space>
            <DatabaseOutlined style={{ color: '#8fa855' }} />
            <Text strong>{source}</Text>
          </Space>
        </Tooltip>
      ),
    },
    {
      title: 'Target',
      dataIndex: 'target',
      key: 'target',
      ellipsis: true,
      render: (target: string) => (
        <Tooltip title={target}>
          <Text code style={{ fontSize: 11 }}>{target}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'FS Type',
      dataIndex: 'fs_type',
      key: 'fs_type',
      width: 100,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: 'Options',
      dataIndex: 'options',
      key: 'options',
      width: 150,
      ellipsis: true,
      render: (opts: string) => (
        <Tooltip title={opts}>
          <Text type="secondary">{opts || '-'}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'error_code',
      key: 'status',
      width: 80,
      render: (error: number) => (
        error === 0 ? 
          <Tag color="green"><CheckCircleOutlined /> OK</Tag> : 
          <Tag color="red"><CloseCircleOutlined /> {error}</Tag>
      ),
    },
  ];

  // Network I/O columns
  const networkColumns = [
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
      render: (_: any, record: NetworkFlowEvent) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.pod || record.source_pod || '-'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace || record.source_namespace || '-'}</Text>
        </Space>
      ),
    },
    {
      title: 'Process',
      key: 'process',
      width: 120,
      render: (_: any, record: any) => {
        // Get process name from comm field in event_data_json
        let comm = record.comm;
        if (!comm && record.event_data_json) {
          try {
            const eventData = typeof record.event_data_json === 'string' 
              ? JSON.parse(record.event_data_json) 
              : record.event_data_json;
            comm = eventData.comm;
          } catch { /* ignore */ }
        }
        return comm ? (
          <Tag color="purple">{comm}</Tag>
        ) : (
          <Text type="secondary">-</Text>
        );
      },
    },
    {
      title: 'Source',
      key: 'source',
      render: (_: any, record: NetworkFlowEvent) => (
        <Text code style={{ fontSize: 11 }}>
          {record.source_ip || '-'}:{record.source_port || '-'}
        </Text>
      ),
    },
    {
      title: 'Destination',
      key: 'dest',
      render: (_: any, record: NetworkFlowEvent) => (
        <Text code style={{ fontSize: 11 }}>
          {record.dest_ip || '-'}:{record.dest_port || '-'}
        </Text>
      ),
    },
    {
      title: 'Sent',
      dataIndex: 'bytes_sent',
      key: 'bytes_sent',
      width: 90,
      sorter: (a: any, b: any) => (a.bytes_sent || 0) - (b.bytes_sent || 0),
      render: (bytes: number) => (
        <Text style={{ color: bytes > 0 ? '#0891b2' : undefined }}>
          {formatBytes(bytes)}
        </Text>
      ),
    },
    {
      title: 'Received',
      dataIndex: 'bytes_received',
      key: 'bytes_received',
      width: 90,
      sorter: (a: any, b: any) => (a.bytes_received || 0) - (b.bytes_received || 0),
      render: (bytes: number) => (
        <Text style={{ color: bytes > 0 ? '#4d9f7c' : undefined }}>
          {formatBytes(bytes)}
        </Text>
      ),
    },
    {
      title: 'Total',
      key: 'totalBytes',
      width: 90,
      sorter: (a: any, b: any) => (a.totalBytes || 0) - (b.totalBytes || 0),
      render: (_: any, record: any) => {
        const total = record.totalBytes || 0;
        return (
          <Text strong style={{ color: total > 0 ? '#7c8eb5' : undefined }}>
            {formatBytes(total)}
          </Text>
        );
      },
    },
    {
      title: 'Protocol',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 80,
      render: (protocol: string) => <Tag>{protocol || 'TCP'}</Tag>,
    },
  ];

  const isLoading = isProcessLoading || isFileLoading || isMountLoading || isNetworkLoading;

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center">
          <ThunderboltOutlined style={{ fontSize: 28, color: '#7c8eb5' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Activity Monitor</Title>
            <Text type="secondary">Monitor process execution, file operations, and volume mounts</Text>
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
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Time Range</Text>
            <RangePicker
              showTime
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
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
              placeholder="Search pods, processes, files..."
              prefix={<SearchOutlined />}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              style={{ width: 180 }}
              allowClear
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right', paddingTop: 22 }}>
            <Space size="middle">
              {/* Quick Filters */}
              <Tooltip title="Filter by event type">
                <Select
                  value={quickFilter}
                  onChange={setQuickFilter}
                  style={{ width: 140 }}
                  suffixIcon={<ExclamationCircleOutlined />}
                >
                  <Option value="all">All Events</Option>
                  <Option value="suspicious">
            <Space>
                      <BugOutlined style={{ color: '#c75450' }} />
                      Suspicious {suspiciousCount > 0 && <Badge count={suspiciousCount} size="small" />}
                    </Space>
                  </Option>
                  <Option value="shells">
                    <Space><ThunderboltOutlined style={{ color: '#b89b5d' }} /> Shells</Space>
                  </Option>
                  <Option value="network">
                    <Space><ApiOutlined style={{ color: '#0891b2' }} /> Network Tools</Space>
                  </Option>
                  <Option value="errors">
                    <Space><CloseCircleOutlined style={{ color: '#c75450' }} /> Errors</Space>
                  </Option>
                  <Option value="high_activity">
                    <Space><SwapOutlined style={{ color: '#7c8eb5' }} /> High Activity</Space>
                  </Option>
                </Select>
              </Tooltip>

              {/* Group By Toggle */}
              <Tooltip title={groupByProcess 
                ? "Showing grouped by process. Toggle off to see all events." 
                : "Showing all events. Toggle on to group by process."}>
                <Space>
                  <Switch
                    checked={groupByProcess}
                    onChange={setGroupByProcess}
                    checkedChildren={<GroupOutlined />}
                    unCheckedChildren={<UnorderedListOutlined />}
                    size="small"
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {groupByProcess ? 'Grouped' : 'All'}
                  </Text>
                </Space>
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
                loading={isLoading}
              >
                Refresh
              </Button>
              <Button icon={<DownloadOutlined />} disabled={!selectedClusterId} onClick={handleExport}>
                Export
              </Button>
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
              <ClockCircleOutlined style={{ color: '#0891b2' }} />
              <Text strong>Activity Timeline</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                ({timelineData.length > 0 && timelineData[0].startTime ? 
                  `${timelineData[0].startTime.format('HH:mm')} - ${timelineData[timelineData.length - 1].endTime?.format('HH:mm') || 'Now'}` : 
                  'No data'})
              </Text>
            </Space>
          }
          extra={
            <Space>
              <Button 
                size="small" 
                icon={<ApartmentOutlined />}
                onClick={buildProcessTree}
                disabled={!processData?.events?.length}
              >
                Process Tree
              </Button>
              <Button 
                size="small" 
                type="text" 
                icon={<CloseCircleOutlined />}
                onClick={() => setShowTimeline(false)}
              />
            </Space>
          }
          bodyStyle={{ padding: '12px 16px' }}
        >
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {/* Bars */}
            <div style={{ display: 'flex', alignItems: 'flex-end', height: 50, gap: 1 }}>
              {timelineData.map((bucket, idx) => {
                const height = bucket.total > 0 ? Math.max((bucket.total / timelineMax) * 45, 2) : 0;
                // Determine dominant event type for color
                const getDominantColor = () => {
                  if (bucket.total === 0) return '#f0f0f0';
                  const max = Math.max(bucket.process, bucket.file, bucket.network, bucket.mount);
                  if (max === bucket.process) return '#7c8eb5'; // Purple for process
                  if (max === bucket.file) return '#a67c9e'; // Pink for file
                  if (max === bucket.network) return '#4d9f7c'; // Green for network
                  if (max === bucket.mount) return '#c9a55a'; // Orange for mount
                  return '#0891b2'; // Default blue
                };
                return (
                  <Tooltip 
                    key={idx} 
                    title={
                      <div>
                        <div><strong>{bucket.time}</strong></div>
                        <div style={{ color: '#7c8eb5' }}>Process: {bucket.process}</div>
                        <div style={{ color: '#a67c9e' }}>File: {bucket.file}</div>
                        <div style={{ color: '#c9a55a' }}>Mount: {bucket.mount}</div>
                        <div style={{ color: '#4d9f7c' }}>Network: {bucket.network}</div>
                        <div><strong>Total: {bucket.total}</strong></div>
                      </div>
                    }
                  >
                    <div
                      style={{
                        flex: 1,
                        height: height,
                        minHeight: bucket.total > 0 ? 2 : 0,
                        backgroundColor: getDominantColor(),
                        borderRadius: 1,
                        transition: 'height 0.3s ease',
                        cursor: 'pointer',
                        opacity: bucket.total > 0 ? 1 : 0.3,
                      }}
                    />
                  </Tooltip>
                );
              })}
            </div>
            {/* Time labels under bars - only show start, middle, end */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, paddingLeft: 2, paddingRight: 2 }}>
              <Text type="secondary" style={{ fontSize: 10 }}>
                {timelineData.length > 0 ? timelineData[0].time : ''}
              </Text>
              <Text type="secondary" style={{ fontSize: 10 }}>
                {timelineData.length > 30 ? timelineData[Math.floor(timelineData.length / 2)].time : ''}
              </Text>
              <Text type="secondary" style={{ fontSize: 10 }}>
                {timelineData.length > 0 ? timelineData[timelineData.length - 1].time : ''}
              </Text>
            </div>
          </div>
          {/* Legend */}
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }}>
            <Space size={16}>
              <Space size={4}>
                <div style={{ width: 8, height: 8, backgroundColor: '#7c8eb5', borderRadius: 2 }} />
                <Text type="secondary" style={{ fontSize: 10 }}>Process</Text>
              </Space>
              <Space size={4}>
                <div style={{ width: 8, height: 8, backgroundColor: '#a67c9e', borderRadius: 2 }} />
                <Text type="secondary" style={{ fontSize: 10 }}>File</Text>
              </Space>
              <Space size={4}>
                <div style={{ width: 8, height: 8, backgroundColor: '#4d9f7c', borderRadius: 2 }} />
                <Text type="secondary" style={{ fontSize: 10 }}>Network</Text>
              </Space>
              <Space size={4}>
                <div style={{ width: 8, height: 8, backgroundColor: '#c9a55a', borderRadius: 2 }} />
                <Text type="secondary" style={{ fontSize: 10 }}>Mount</Text>
              </Space>
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
          Show Activity Timeline
        </Button>
      )}

      {/* Stats */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Tooltip title="Total process execution events (exec, exit, signal) captured by eBPF tracing">
          <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="Process Events"
                value={searchTerm ? filteredProcesses.length : (eventStats?.event_counts?.process_event || processData?.total || 0)}
              prefix={<ThunderboltOutlined style={{ color: '#7c8eb5' }} />}
              loading={isStatsLoading}
              valueStyle={{ fontSize: 22 }}
            />
          </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title="File system operations including read, write, open, close, delete tracked by eBPF">
          <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="File Operations"
                value={searchTerm ? filteredFileOps.length : (eventStats?.event_counts?.file_event || fileData?.total || 0)}
              prefix={<FileOutlined style={{ color: '#a67c9e' }} />}
              loading={isStatsLoading}
              valueStyle={{ fontSize: 22 }}
            />
          </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title="Volume mount and unmount events in pods">
          <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="Mount Events"
                value={searchTerm ? filteredMounts.length : (eventStats?.event_counts?.mount_event || mountData?.total || 0)}
              prefix={<DatabaseOutlined style={{ color: '#8fa855' }} />}
              loading={isStatsLoading}
              valueStyle={{ fontSize: 22 }}
            />
          </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          <Tooltip title="Network I/O events with byte transfer data. Requires 'TCP Throughput' (top_tcp) gadget enabled.">
            <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
              <Statistic
                title="Network I/O"
                value={filteredNetworkFlows.length}
                prefix={<SwapOutlined style={{ color: '#0891b2' }} />}
                loading={isNetworkLoading}
                valueStyle={{ fontSize: 22 }}
              />
            </Card>
          </Tooltip>
        </Col>
        <Col span={4}>
          {(() => {
            const hasData = totalNetworkBytes > 0;
            return (
              <Tooltip title={hasData 
                ? `Total data transferred: ${(totalNetworkBytes / (1024 * 1024)).toFixed(2)} MB (${totalNetworkBytes.toLocaleString()} bytes)`
                : "Byte transfer data requires 'TCP Throughput' (top_tcp) gadget. Enable it in your analysis to collect byte counts."
              }>
                <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
                  <Statistic
                    title="Data Transferred"
                    value={hasData ? (totalNetworkBytes / (1024 * 1024)).toFixed(2) : '—'}
                    suffix={hasData ? 'MB' : ''}
                    prefix={<ApiOutlined style={{ color: hasData ? '#22a6a6' : '#d9d9d9' }} />}
                    valueStyle={{ color: hasData ? undefined : '#d9d9d9', fontSize: 22 }}
                  />
                </Card>
              </Tooltip>
            );
          })()}
        </Col>
        <Col span={4}>
          <Tooltip title="Sum of all activity events across all categories">
          <Card bordered={false} style={{ height: 110 }} bodyStyle={{ padding: '16px 20px' }}>
            <Statistic
              title="Total Events"
              value={eventStats?.total_events || 0}
                prefix={<ClockCircleOutlined style={{ color: '#4d9f7c' }} />}
              loading={isStatsLoading}
              valueStyle={{ fontSize: 22 }}
            />
          </Card>
          </Tooltip>
        </Col>
      </Row>

      {/* Main Content */}
      <Card bordered={false}>
        {!selectedAnalysisId ? (
          <Empty description="Select an analysis to view activity data" />
        ) : isLoading && !processData && !fileData && !mountData ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading activity data...</Text>
          </div>
        ) : (
          <Tabs activeKey={activeTab} onChange={setActiveTab}>
            <Tabs.TabPane
              tab={<span><ThunderboltOutlined /> Processes ({filteredProcesses.length})</span>}
              key="processes"
            >
              <Table
                dataSource={filteredProcesses}
                columns={addClusterColumn(processColumns, 'process')}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} process events`
                }}
                size="middle"
                loading={isProcessLoading}
                locale={{ emptyText: <Empty description="No process events recorded" /> }}
                scroll={{ x: 1200 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedActivityEvent({ ...record, eventType: 'process' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><FileOutlined /> File Operations ({filteredFileOps.length})</span>}
              key="files"
            >
              <Table
                dataSource={filteredFileOps}
                columns={addClusterColumn(fileColumns, 'file')}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} file operations`
                }}
                size="middle"
                loading={isFileLoading}
                locale={{ emptyText: <Empty description="No file operations recorded" /> }}
                scroll={{ x: 1300 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedActivityEvent({ ...record, eventType: 'file' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><DatabaseOutlined /> Mounts ({filteredMounts.length})</span>}
              key="mounts"
            >
              <Table
                dataSource={filteredMounts}
                columns={addClusterColumn(mountColumns, 'mount')}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} mount events`
                }}
                size="middle"
                loading={isMountLoading}
                locale={{ emptyText: <Empty description="No mount events recorded" /> }}
                scroll={{ x: 1200 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedActivityEvent({ ...record, eventType: 'mount' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={
                <span>
                  <ApiOutlined /> Network I/O ({filteredNetworkFlows.length})
                  {filteredNetworkFlows.some((f: any) => f.totalBytes > 0) && (
                    <Tag color="blue" style={{ marginLeft: 8, fontSize: 10 }}>
                      {formatBytes(filteredNetworkFlows.reduce((sum: number, f: any) => sum + (f.totalBytes || 0), 0))}
                    </Tag>
                  )}
                </span>
              }
              key="network"
            >
              <Table
                dataSource={filteredNetworkFlows}
                columns={addClusterColumn(networkColumns, 'network')}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} network flows`
                }}
                size="middle"
                loading={isNetworkLoading}
                locale={{ 
                  emptyText: (
                    <Empty 
                      description={
                        <span>
                          No network I/O data recorded.
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Enable "TCP Throughput" (top_tcp) gadget in your analysis to collect byte transfer data.
                          </Text>
                        </span>
                      } 
                    />
                  )
                }}
                scroll={{ x: 1100 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedActivityEvent({ ...record, eventType: 'network' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
          </Tabs>
        )}
      </Card>

      {/* Activity Event Detail Modal */}
      <Modal
        title={
          <Space>
            {selectedActivityEvent?.eventType === 'process' && <ThunderboltOutlined style={{ color: '#7c8eb5' }} />}
            {selectedActivityEvent?.eventType === 'file' && <FileOutlined style={{ color: '#a67c9e' }} />}
            {selectedActivityEvent?.eventType === 'mount' && <DatabaseOutlined style={{ color: '#22a6a6' }} />}
            {selectedActivityEvent?.eventType === 'network' && <ApiOutlined style={{ color: '#0891b2' }} />}
            <span>
              {selectedActivityEvent?.eventType === 'process' && 'Process Event Details'}
              {selectedActivityEvent?.eventType === 'file' && 'File Operation Details'}
              {selectedActivityEvent?.eventType === 'mount' && 'Mount Event Details'}
              {selectedActivityEvent?.eventType === 'network' && 'Network I/O Details'}
            </span>
            {selectedActivityEvent?.isSuspicious && (
              <Tag color="red"><BugOutlined /> Suspicious</Tag>
            )}
          </Space>
        }
        open={eventDetailVisible}
        onCancel={() => {
          setEventDetailVisible(false);
          setSelectedActivityEvent(null);
        }}
        footer={[
          <Button 
            key="copy" 
            icon={<CopyOutlined />} 
            onClick={() => copyToClipboard(selectedActivityEvent)}
          >
            Copy JSON
          </Button>,
          selectedActivityEvent?.eventType === 'process' && (
            <Button 
              key="related" 
              icon={<LinkOutlined />} 
              onClick={() => {
                setEventDetailVisible(false);
                findRelatedEvents(selectedActivityEvent);
              }}
            >
              Related Events
            </Button>
          ),
          <Button key="close" type="primary" onClick={() => setEventDetailVisible(false)}>
            Close
          </Button>
        ].filter(Boolean)}
        width={700}
      >
        {selectedActivityEvent && (
          <div style={{ padding: '8px 0' }}>
            {/* Event Type Badge */}
            <div style={{ marginBottom: 16, textAlign: 'center' }}>
              <Tag 
                color={
                  selectedActivityEvent.eventType === 'process' ? 'purple' :
                  selectedActivityEvent.eventType === 'file' ? 'magenta' : 'cyan'
                }
                style={{ fontSize: 14, padding: '4px 12px' }}
              >
                {selectedActivityEvent.eventType?.toUpperCase()} EVENT
              </Tag>
              {selectedActivityEvent.event_subtype && (
                <Tag color={processSubtypeColors[selectedActivityEvent.event_subtype]?.color || 'default'} style={{ marginLeft: 8 }}>
                  {selectedActivityEvent.event_subtype?.toUpperCase()}
                </Tag>
              )}
              {selectedActivityEvent.operation && (
                <Tag color={fileOpColors[selectedActivityEvent.operation] || 'default'} style={{ marginLeft: 8 }}>
                  {selectedActivityEvent.operation?.toUpperCase()}
                </Tag>
              )}
            </div>

            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="Pod" span={2}>
                <Text strong>{selectedActivityEvent.pod || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Namespace">
                <Tag color="blue">{selectedActivityEvent.namespace || '-'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Container">
                {selectedActivityEvent.container || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Timestamp" span={2}>
                {selectedActivityEvent.timestamp 
                  ? new Date(selectedActivityEvent.timestamp).toLocaleString()
                  : '-'}
              </Descriptions.Item>

              {/* Process specific fields */}
              {selectedActivityEvent.eventType === 'process' && (
                <>
                  <Descriptions.Item label="Process Name">
                    <Text code>{selectedActivityEvent.comm || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Executable">
                    <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>
                      {selectedActivityEvent.exe || '-'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="PID">
                    {selectedActivityEvent.pid || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Parent PID">
                    {selectedActivityEvent.ppid || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="UID / GID">
                    {selectedActivityEvent.uid || 0} / {selectedActivityEvent.gid || 0}
                  </Descriptions.Item>
                  <Descriptions.Item label="Exit Code">
                    {selectedActivityEvent.exit_code !== undefined ? (
                      <Tag color={selectedActivityEvent.exit_code === 0 ? 'green' : 'red'}>
                        {selectedActivityEvent.exit_code}
                      </Tag>
                    ) : '-'}
                  </Descriptions.Item>
                  {selectedActivityEvent.args && selectedActivityEvent.args.length > 0 && (
                    <Descriptions.Item label="Arguments" span={2}>
                      <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>
                        {selectedActivityEvent.args.join(' ')}
                      </Text>
                    </Descriptions.Item>
                  )}
                </>
              )}

              {/* File specific fields */}
              {selectedActivityEvent.eventType === 'file' && (
                <>
                  <Descriptions.Item label="File Path" span={2}>
                    <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>
                      {selectedActivityEvent.file_path || '-'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Operation">
                    <Tag color={fileOpColors[selectedActivityEvent.operation] || 'default'}>
                      {selectedActivityEvent.operation?.toUpperCase() || '-'}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Process">
                    <Text code>{selectedActivityEvent.comm || '-'}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="PID">
                    {selectedActivityEvent.pid || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label="Bytes">
                    {selectedActivityEvent.bytes ? formatBytes(selectedActivityEvent.bytes) : '-'}
                  </Descriptions.Item>
                </>
              )}

              {/* Mount specific fields */}
              {selectedActivityEvent.eventType === 'mount' && (
                <>
                  <Descriptions.Item label="Source" span={2}>
                    <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>
                      {selectedActivityEvent.source || '-'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Target" span={2}>
                    <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>
                      {selectedActivityEvent.target || '-'}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Filesystem Type">
                    <Tag>{selectedActivityEvent.fs_type || '-'}</Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Options">
                    {selectedActivityEvent.options || '-'}
                  </Descriptions.Item>
                </>
              )}
            </Descriptions>

            {/* Additional JSON data if available */}
            {selectedActivityEvent.event_data_json && (
              <div style={{ marginTop: 16 }}>
                <Text strong>Raw Event Data:</Text>
                <pre style={{ 
                  background: '#f5f5f5', 
                  padding: 12, 
                  borderRadius: 4, 
                  fontSize: 11,
                  maxHeight: 200,
                  overflow: 'auto',
                  marginTop: 8
                }}>
                  {typeof selectedActivityEvent.event_data_json === 'string' 
                    ? JSON.stringify(JSON.parse(selectedActivityEvent.event_data_json), null, 2)
                    : JSON.stringify(selectedActivityEvent.event_data_json, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Related Events Modal */}
      <Modal
        title={
          <Space>
            <ApartmentOutlined style={{ color: '#0891b2' }} />
            <span>Related Events</span>
            {relatedEventsData?.process && (
              <Tag color="purple">{relatedEventsData.process.comm || relatedEventsData.process.pod}</Tag>
            )}
          </Space>
        }
        open={relatedEventsVisible}
        onCancel={() => {
          setRelatedEventsVisible(false);
          setRelatedEventsData(null);
        }}
        footer={[
          <Button key="close" type="primary" onClick={() => setRelatedEventsVisible(false)}>
            Close
          </Button>
        ]}
        width={900}
      >
        {relatedEventsData && (
          <div>
            {/* Process Info */}
            <Card size="small" title={<Space><ThunderboltOutlined /> Source Process</Space>} style={{ marginBottom: 16 }}>
              <Space wrap>
                <Tag color="blue">{relatedEventsData.process.pod}</Tag>
                <Tag>{relatedEventsData.process.namespace}</Tag>
                <Tag color="purple">{relatedEventsData.process.comm || '-'}</Tag>
                {relatedEventsData.process.pid > 0 && <Tag>PID: {relatedEventsData.process.pid}</Tag>}
              </Space>
            </Card>

            {/* Related File Operations */}
            <Card 
              size="small" 
              title={
                <Space>
                  <FileOutlined style={{ color: '#a67c9e' }} /> 
                  <span>Related File Operations</span>
                  <Badge count={relatedEventsData.files.length} style={{ backgroundColor: '#a67c9e' }} />
                </Space>
              } 
              style={{ marginBottom: 16 }}
              bodyStyle={{ padding: relatedEventsData.files.length > 0 ? 0 : undefined }}
            >
              {relatedEventsData.files.length > 0 ? (
                <Table
                  dataSource={relatedEventsData.files.map((f, i) => ({ ...f, key: i }))}
                  columns={[
                    { title: 'Time', dataIndex: 'timestamp', width: 100, render: (ts: string) => dayjs(ts).format('HH:mm:ss') },
                    { title: 'Operation', dataIndex: 'operation', width: 100, render: (op: string) => <Tag color={fileOpColors[op]}>{op?.toUpperCase()}</Tag> },
                    { title: 'Path', dataIndex: 'file_path', ellipsis: true, render: (path: string) => <Text code style={{ fontSize: 11 }}>{path}</Text> },
                    { title: 'Bytes', dataIndex: 'bytes', width: 80, render: (b: number) => b ? formatBytes(b) : '-' },
                  ]}
                  size="small"
                  pagination={false}
                  scroll={{ y: 200, x: 500 }}
                />
              ) : (
                <Empty description="No related file operations found" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>

            {/* Related Network Flows */}
            <Card 
              size="small" 
              title={
                <Space>
                  <ApiOutlined style={{ color: '#0891b2' }} /> 
                  <span>Related Network Flows</span>
                  <Badge count={relatedEventsData.network.length} style={{ backgroundColor: '#0891b2' }} />
                </Space>
              }
              bodyStyle={{ padding: relatedEventsData.network.length > 0 ? 0 : undefined }}
            >
              {relatedEventsData.network.length > 0 ? (
                <Table
                  dataSource={relatedEventsData.network.map((n, i) => ({ ...n, key: i }))}
                  columns={[
                    { title: 'Time', dataIndex: 'timestamp', width: 100, render: (ts: string) => dayjs(ts).format('HH:mm:ss') },
                    { title: 'Source', key: 'src', width: 150, render: (_: any, r: any) => <Text code style={{ fontSize: 11 }}>{r.source_ip}:{r.source_port}</Text> },
                    { title: 'Destination', key: 'dst', width: 150, render: (_: any, r: any) => <Text code style={{ fontSize: 11 }}>{r.dest_ip}:{r.dest_port}</Text> },
                    { title: 'Protocol', dataIndex: 'protocol', width: 80, render: (p: string) => <Tag>{p || 'TCP'}</Tag> },
                    { title: 'Bytes', key: 'bytes', width: 100, render: (_: any, r: any) => formatBytes((r.bytes_sent || 0) + (r.bytes_received || 0)) },
                  ]}
                  size="small"
                  pagination={false}
                  scroll={{ y: 200, x: 580 }}
                />
              ) : (
                <Empty 
                  description={
                    <Space direction="vertical" size={4}>
                      <span>No related network flows found</span>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Network flows are matched by pod, namespace and process name
                      </Text>
                    </Space>
                  } 
                  image={Empty.PRESENTED_IMAGE_SIMPLE} 
                />
              )}
            </Card>
          </div>
        )}
      </Modal>

      {/* Process Tree Modal */}
      <Modal
        title={
          <Space>
            <ApartmentOutlined style={{ color: '#7c8eb5' }} />
            <span>Process Tree</span>
            <Text type="secondary" style={{ fontSize: 12 }}>Parent → Child relationships</Text>
          </Space>
        }
        open={processTreeVisible}
        onCancel={() => {
          setProcessTreeVisible(false);
          setProcessTreeData([]);
        }}
        footer={[
          <Button key="close" type="primary" onClick={() => setProcessTreeVisible(false)}>
            Close
          </Button>
        ]}
        width={1000}
      >
        {processTreeData.length > 0 ? (
          <div style={{ maxHeight: 500, overflow: 'auto' }}>
            <Table
              dataSource={processTreeData}
              columns={[
                {
                  title: 'Process',
                  key: 'process',
                  render: (_: any, record: any) => (
                    <Space>
                      <ThunderboltOutlined style={{ color: record.isSuspicious ? '#c75450' : '#7c8eb5' }} />
                      <Text strong style={{ color: record.isSuspicious ? '#c75450' : undefined }}>
                        {record.comm || record.exe?.split('/').pop() || '-'}
                      </Text>
                      {record.isSuspicious && (
                        <Tag color="red" style={{ fontSize: 10 }}>
                          <BugOutlined /> {record.suspiciousReason}
                        </Tag>
                      )}
                    </Space>
                  ),
                },
                {
                  title: 'PID',
                  dataIndex: 'pid',
                  width: 80,
                  render: (pid: number) => <Tag>{pid}</Tag>,
                },
                {
                  title: 'PPID',
                  dataIndex: 'ppid',
                  width: 80,
                  render: (ppid: number) => ppid > 0 ? <Tag color="blue">{ppid}</Tag> : '-',
                },
                {
                  title: 'Pod',
                  key: 'pod',
                  render: (_: any, record: any) => (
                    <Space direction="vertical" size={0}>
                      <Text>{record.pod}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>{record.namespace}</Text>
                    </Space>
                  ),
                },
                {
                  title: 'Command',
                  key: 'command',
                  ellipsis: true,
                  render: (_: any, record: any) => {
                    const cmd = record.exe || (record.args || []).join(' ') || record.comm || '-';
                    return (
                      <Tooltip title={cmd}>
                        <Text code style={{ fontSize: 11 }}>{cmd.slice(0, 60)}{cmd.length > 60 ? '...' : ''}</Text>
                      </Tooltip>
                    );
                  },
                },
                {
                  title: 'Time',
                  dataIndex: 'timestamp',
                  width: 100,
                  render: (ts: string) => dayjs(ts).format('HH:mm:ss'),
                },
              ]}
              expandable={{
                childrenColumnName: 'children',
                defaultExpandAllRows: false,
                indentSize: 20,
              }}
              size="small"
              pagination={false}
              rowClassName={(record) => record.isSuspicious ? 'suspicious-row' : ''}
            />
            <style>{`
              .suspicious-row {
                background-color: ${token.colorErrorBg || 'rgba(255, 77, 79, 0.1)'} !important;
              }
              .suspicious-row:hover > td {
                background-color: ${token.colorErrorBgHover || 'rgba(255, 77, 79, 0.2)'} !important;
              }
            `}</style>
          </div>
        ) : (
          <Empty 
            description={
              <Space direction="vertical" size={8} align="center">
                <Text>Process tree requires PID/PPID information.</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  The current data source doesn't include process ID information needed for parent-child relationships.
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  This feature works with eBPF tracers that capture PID/PPID (e.g., Inspektor Gadget trace exec).
                </Text>
              </Space>
            } 
          />
        )}
      </Modal>
    </div>
  );
};

// Helper function to format bytes
function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ki', 'Mi', 'Gi', 'Ti'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default ActivityMonitor;
