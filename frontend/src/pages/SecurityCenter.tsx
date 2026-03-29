import React, { useState, useMemo, useCallback, useEffect } from 'react';
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
  Badge,
  Empty,
  Alert,
  Progress,
  Spin,
  Button,
  Tooltip,
  message,
  Input,
  DatePicker,
  Modal,
  Descriptions
} from 'antd';
import { 
  SecurityScanOutlined,
  WarningOutlined,
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  LockOutlined,
  BugOutlined,
  ReloadOutlined,
  DownloadOutlined,
  SearchOutlined,
  ClockCircleOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { 
  useGetEventStatsQuery,
  useGetSecurityEventsQuery,
  useGetOomEventsQuery,
  SecurityEvent,
  OomEvent
} from '../store/api/eventsApi';
import { Analysis } from '../types';
import { ClusterBadge } from '../components/Common';

// Import shared security score utilities - single source of truth
import { 
  calculateSecurityScore, 
  capabilityRisk, 
  riskColors,
  getEventSeverity,
  SECURITY_EVENTS_LIMIT,
  OOM_EVENTS_LIMIT
} from '../utils/securityScore';

const { Title, Text } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;

const SecurityCenter: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedClusterIds, setSelectedClusterIds] = useState<number[]>([]); // Multi-cluster filter
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [activeTab, setActiveTab] = useState('capabilities');
  const [searchTerm, setSearchTerm] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  // Use shared constant for consistent score calculation across pages
  const [pagination, setPagination] = useState({ current: 1, pageSize: SECURITY_EVENTS_LIMIT });

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

  /**
   * Smart matching for pod names, namespaces, paths.
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
   * Exact match for capability names (CAP_NET_ADMIN, etc.)
   * These are specific identifiers that should match exactly or as prefix.
   */
  const capabilityMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    const valueLower = value.toLowerCase();
    const searchLower = search.toLowerCase();
    
    // Exact or prefix match (e.g., "CAP_NET" matches "CAP_NET_ADMIN")
    return valueLower === searchLower || valueLower.startsWith(searchLower);
  }, []);

  /**
   * Simple contains for short keywords (risk level, type, etc.)
   */
  const simpleMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    return value.toLowerCase().includes(search.toLowerCase());
  }, []);

  // Capability-specific search
  const capabilityMatchesSearch = useCallback((cap: any, term: string): boolean => {
    if (!term) return true;
    
    // Smart match for pod, namespace
    if (smartMatch(cap.pod, term)) return true;
    if (smartMatch(cap.namespace, term)) return true;
    
    // Exact/prefix match for capability names (CAP_NET_ADMIN)
    if (capabilityMatch(cap.capability, term)) return true;
    
    // Simple match for risk level, description
    if (simpleMatch(cap.risk, term)) return true;
    if (simpleMatch(cap.description, term)) return true;
    
    return false;
  }, [smartMatch, capabilityMatch, simpleMatch]);

  // Violation-specific search
  const violationMatchesSearch = useCallback((v: any, term: string): boolean => {
    if (!term) return true;
    
    // Smart match for pod, namespace, comm
    if (smartMatch(v.pod, term)) return true;
    if (smartMatch(v.namespace, term)) return true;
    if (smartMatch(v.comm, term)) return true;
    
    // Exact/prefix match for capability, syscall
    if (capabilityMatch(v.capability, term)) return true;
    if (capabilityMatch(v.syscall, term)) return true;
    
    // Simple match for type, severity
    if (simpleMatch(v.type, term)) return true;
    if (simpleMatch(v.severity, term)) return true;
    
    // Exact match for PID
    if (v.pid?.toString() === term) return true;
    
    return false;
  }, [smartMatch, capabilityMatch, simpleMatch]);

  // OOM-specific search
  const oomMatchesSearch = useCallback((o: any, term: string): boolean => {
    if (!term) return true;
    
    // Smart match for pod, namespace, container, comm, cgroupPath
    if (smartMatch(o.pod, term)) return true;
    if (smartMatch(o.namespace, term)) return true;
    if (smartMatch(o.container, term)) return true;
    if (smartMatch(o.comm, term)) return true;
    if (smartMatch(o.cgroupPath, term)) return true;
    
    // Simple match for memory values (e.g., "512Mi", "1Gi")
    if (simpleMatch(o.limit, term)) return true;
    if (simpleMatch(o.used, term)) return true;
    
    // Exact match for PID
    if (o.pid?.toString() === term) return true;
    
    return false;
  }, [smartMatch, simpleMatch]);

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

  const queryParams = useMemo(() => ({
    cluster_id: selectedClusterId!,
    analysis_id: selectedAnalysisId,
    start_time: dateRange?.[0]?.toISOString(),
    end_time: dateRange?.[1]?.toISOString(),
    limit: pagination.pageSize,
    offset: (pagination.current - 1) * pagination.pageSize,
  }), [selectedClusterId, selectedAnalysisId, dateRange, pagination]);

  const { data: eventStats, isLoading: isStatsLoading } = useGetEventStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: securityData, isLoading: isSecurityLoading, refetch: refetchSecurity } = useGetSecurityEventsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  const { data: oomData, isLoading: isOomLoading, refetch: refetchOom } = useGetOomEventsQuery(
    queryParams,
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Process security events to extract capabilities
  const capabilities = useMemo(() => {
    if (!securityData?.events) return [];
    
    const capMap = new Map<string, {
      key: string;
      pod: string;
      namespace: string;
      capability: string;
      usageCount: number;
      lastSeen: string;
      risk: 'low' | 'medium' | 'high' | 'critical';
      description: string;
      allowed: number;
      denied: number;
    }>();

    securityData.events
      .filter((e: SecurityEvent) => e.security_type === 'capability')
      .forEach((event: SecurityEvent) => {
        const key = `${event.pod}-${event.capability}`;
        const existing = capMap.get(key);
        const capInfo = capabilityRisk[event.capability || ''] || { risk: 'medium', description: 'Unknown capability' };
        
        if (existing) {
          existing.usageCount++;
          if (event.timestamp > existing.lastSeen) {
            existing.lastSeen = event.timestamp;
          }
          if (event.verdict === 'allowed') existing.allowed++;
          else existing.denied++;
        } else {
          capMap.set(key, {
            key,
            pod: event.pod,
            namespace: event.namespace,
            capability: event.capability || 'UNKNOWN',
            usageCount: 1,
            lastSeen: event.timestamp,
            risk: capInfo.risk,
            description: capInfo.description,
            allowed: event.verdict === 'allowed' ? 1 : 0,
            denied: event.verdict === 'denied' ? 1 : 0,
          });
        }
      });

    return Array.from(capMap.values()).sort((a, b) => {
      const riskOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      return riskOrder[a.risk] - riskOrder[b.risk];
    });
  }, [securityData?.events]);

  // Filter and extract violations (denied security events) using shared utility
  const violations = useMemo(() => {
    if (!securityData?.events) return [];
    
    return securityData.events
      .filter((e: SecurityEvent) => e.verdict === 'denied')
      .map((event: SecurityEvent) => ({
        key: `${event.timestamp}-${event.pod}-${event.security_type}`,
        pod: event.pod,
        namespace: event.namespace,
        type: event.security_type,
        capability: event.capability,
        syscall: event.syscall,
        action: 'blocked',
        timestamp: event.timestamp,
        severity: getEventSeverity(event.capability),
        pid: event.pid,
        comm: event.comm,
      }))
      .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  }, [securityData?.events]);

  // Process OOM events
  const oomEvents = useMemo(() => {
    if (!oomData?.events) return [];
    
    return oomData.events.map((event: OomEvent) => ({
      key: `${event.timestamp}-${event.pod}`,
      pod: event.pod,
      namespace: event.namespace,
      container: event.container || 'main',
      limit: formatBytes(event.memory_limit),
      used: formatBytes(event.memory_usage),
      timestamp: event.timestamp,
      pid: event.pid,
      comm: event.comm,
      cgroupPath: event.cgroup_path,
    }));
  }, [oomData?.events]);

  // Filter by search term - using specific search for each table type
  const filteredCapabilities = useMemo(() => {
    return capabilities.filter(c => capabilityMatchesSearch(c, searchTerm));
  }, [capabilities, searchTerm, capabilityMatchesSearch]);

  const filteredViolations = useMemo(() => {
    return violations.filter(v => violationMatchesSearch(v, searchTerm));
  }, [violations, searchTerm, violationMatchesSearch]);

  const filteredOomEvents = useMemo(() => {
    return oomEvents.filter(o => oomMatchesSearch(o, searchTerm));
  }, [oomEvents, searchTerm, oomMatchesSearch]);

  // Security Score calculation using shared utility function - single source of truth
  const securityScoreData = useMemo(() => {
    // If no analysis selected, return null (will show "-")
    if (!selectedAnalysisId || !selectedClusterId) {
      return { score: null, breakdown: undefined, status: 'no_selection' as const };
    }
    
    // If data is still loading, return loading status
    if (isSecurityLoading || isOomLoading) {
      return { score: null, breakdown: undefined, status: 'loading' as const };
    }
    
    // Use shared calculation function - ensures consistency with Dashboard
    const result = calculateSecurityScore({
      totalCapabilityChecks: securityData?.total || 0,
      totalOomEvents: oomData?.total || 0,
      violations: violations,
      capabilities: capabilities,
    });

    return {
      ...result,
      totalChecks: securityData?.total || 0
    };
  }, [selectedAnalysisId, selectedClusterId, isSecurityLoading, isOomLoading, 
      securityData?.total, oomData?.total, violations, capabilities]);

  const securityScore = securityScoreData.score;
  const securityStatus = 'status' in securityScoreData ? securityScoreData.status : 'loading';
  const securityMessage = 'message' in securityScoreData ? securityScoreData.message : undefined;
  
  // State for score info modal
  const [scoreInfoVisible, setScoreInfoVisible] = useState(false);
  const [eventDetailVisible, setEventDetailVisible] = useState(false);
  const [selectedSecurityEvent, setSelectedSecurityEvent] = useState<any>(null);

  // Refresh all data
  const handleRefresh = useCallback(() => {
    refetchSecurity();
    refetchOom();
    message.success('Data refreshed');
  }, [refetchSecurity, refetchOom]);

  // Helper to add cluster column for multi-cluster analysis
  const addClusterColumn = useCallback((columns: any[]) => {
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
    
    // Insert as first column
    return [clusterColumn, ...columns];
  }, [isMultiClusterAnalysis, clusterInfoMap]);

  // Capability columns
  const capabilityColumns = [
    {
      title: 'Pod',
      dataIndex: 'pod',
      key: 'pod',
      render: (pod: string, record: any) => (
        <Space direction="vertical" size={0}>
          <Space>
            <LockOutlined style={{ color: '#0891b2' }} />
            <Text strong>{pod}</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Capability',
      dataIndex: 'capability',
      key: 'capability',
      render: (cap: string, record: any) => (
        <Tooltip title={record.description}>
          <Text code>{cap}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Usage',
      dataIndex: 'usageCount',
      key: 'usage',
      width: 180,
      render: (count: number, record: any) => {
        const total = record.allowed + record.denied;
        const allowedPercent = total > 0 ? Math.round((record.allowed / total) * 100) : 0;
        return (
          <Space direction="vertical" size={0}>
            <Progress 
              percent={allowedPercent} 
              size="small" 
              strokeColor="#4d9f7c"
              trailColor={record.denied > 0 ? '#f76e6e' : undefined}
              format={() => `${count} calls`}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.allowed} allowed / {record.denied} denied
            </Text>
          </Space>
        );
      },
      sorter: (a: any, b: any) => a.usageCount - b.usageCount,
    },
    {
      title: 'Risk',
      dataIndex: 'risk',
      key: 'risk',
      width: 100,
      filters: [
        { text: 'Critical', value: 'critical' },
        { text: 'High', value: 'high' },
        { text: 'Medium', value: 'medium' },
        { text: 'Low', value: 'low' },
      ],
      onFilter: (value: any, record: any) => record.risk === value,
      render: (risk: string) => (
        <Tag color={riskColors[risk as keyof typeof riskColors]}>
          {risk.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Last Seen',
      dataIndex: 'lastSeen',
      key: 'lastSeen',
      width: 160,
      render: (ts: string) => dayjs(ts).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a: any, b: any) => dayjs(a.lastSeen).unix() - dayjs(b.lastSeen).unix(),
    },
  ];

  // Violations columns
  const violationColumns = [
    {
      title: 'Pod',
      dataIndex: 'pod',
      key: 'pod',
      render: (pod: string, record: any) => (
        <Space direction="vertical" size={0}>
          <Space>
            <ExclamationCircleOutlined style={{ color: '#c75450' }} />
            <Text strong>{pod}</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      filters: [
        { text: 'Capability', value: 'capability' },
        { text: 'Seccomp', value: 'seccomp' },
        { text: 'SELinux', value: 'selinux' },
      ],
      onFilter: (value: any, record: any) => record.type === value,
      render: (type: string) => <Tag>{type}</Tag>,
    },
    {
      title: 'Details',
      key: 'details',
      render: (_: any, record: any) => (
        <Space direction="vertical" size={0}>
          {record.capability && <Text code>{record.capability}</Text>}
          {record.syscall && <Text type="secondary">syscall: {record.syscall}</Text>}
          <Text type="secondary" style={{ fontSize: 12 }}>
            pid: {record.pid} | comm: {record.comm}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Action',
      dataIndex: 'action',
      key: 'action',
      width: 100,
      render: (action: string) => (
        <Tag color="red">{action}</Tag>
      ),
    },
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      filters: [
        { text: 'Critical', value: 'critical' },
        { text: 'High', value: 'high' },
        { text: 'Medium', value: 'medium' },
        { text: 'Low', value: 'low' },
      ],
      onFilter: (value: any, record: any) => record.severity === value,
      render: (severity: string) => (
        <Tag color={riskColors[severity as keyof typeof riskColors]}>
          {severity.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (ts: string) => dayjs(ts).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
    },
  ];

  // OOM columns
  const oomColumns = [
    {
      title: 'Pod',
      dataIndex: 'pod',
      key: 'pod',
      render: (pod: string, record: any) => (
        <Space direction="vertical" size={0}>
          <Space>
            <WarningOutlined style={{ color: '#f76e6e' }} />
            <Text strong>{pod}</Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{record.namespace}</Text>
        </Space>
      ),
    },
    {
      title: 'Container',
      dataIndex: 'container',
      key: 'container',
    },
    {
      title: 'Process',
      key: 'process',
      render: (_: any, record: any) => (
        <Space direction="vertical" size={0}>
          <Text code>{record.comm}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>PID: {record.pid}</Text>
        </Space>
      ),
    },
    {
      title: 'Memory Limit',
      dataIndex: 'limit',
      key: 'limit',
      width: 120,
    },
    {
      title: 'Memory Used',
      dataIndex: 'used',
      key: 'used',
      width: 120,
      render: (used: string) => <Text type="danger">{used}</Text>,
    },
    {
      title: 'Timestamp',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 160,
      render: (ts: string) => dayjs(ts).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a: any, b: any) => dayjs(a.timestamp).unix() - dayjs(b.timestamp).unix(),
    },
  ];

  const isLoading = isSecurityLoading || isOomLoading;
  const criticalViolationsCount = violations.filter(v => v.severity === 'critical').length;

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center">
          <SecurityScanOutlined style={{ fontSize: 28, color: '#c75450' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Security Center</Title>
            <Text type="secondary">Monitor security events, capabilities, and resource issues</Text>
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
                  style={{ width: 180 }}
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
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day'), dayjs()] },
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
            <Space>
              <Button 
                icon={<ReloadOutlined />} 
                onClick={handleRefresh}
                loading={isLoading}
              >
                Refresh
              </Button>
              <Button icon={<DownloadOutlined />} disabled={!selectedClusterId}>
                Export
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Stats & Security Score */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card bordered={false}>
            <div style={{ textAlign: 'center' }}>
              <Spin spinning={securityStatus === 'loading'}>
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <Progress
                    type="circle"
                    percent={securityScore ?? 0}
                    strokeColor={
                      securityScore === null ? '#d9d9d9' :
                      securityScore >= 80 ? '#4d9f7c' : 
                      securityScore >= 60 ? '#b89b5d' : '#c75450'
                    }
                    format={() => (
                      <div>
                        <div style={{ fontSize: 24, fontWeight: 'bold' }}>
                          {securityStatus === 'loading' ? '...' :
                           securityStatus === 'no_selection' ? '-' :
                           securityStatus === 'no_data' ? 'N/A' :
                           securityScore}
                        </div>
                        <div style={{ fontSize: 12, color: '#8c8c8c' }}>
                          {securityStatus === 'no_data' ? 'No Data' : 'Security Score'}
                        </div>
                      </div>
                    )}
                  />
                  {/* Info button */}
                  <Tooltip title={securityStatus === 'no_data' ? securityMessage : 'How is this score calculated?'}>
                    <Button
                      type="text"
                      size="small"
                      icon={<InfoCircleOutlined />}
                      onClick={() => setScoreInfoVisible(true)}
                      style={{ 
                        position: 'absolute', 
                        top: -5, 
                        right: -5,
                        color: securityStatus === 'no_data' ? '#c9a55a' : '#0891b2'
                      }}
                    />
                  </Tooltip>
                </div>
              </Spin>
              {/* Show message when no data */}
              {securityStatus === 'no_data' && (
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 8 }}>
                  Enable security gadgets in analysis
                </Text>
              )}
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Tooltip title="Total capability checks recorded (allowed + denied)">
              <Statistic
                title="Capability Checks"
                value={securityData?.total || 0}
                prefix={<SafetyCertificateOutlined style={{ color: '#0891b2' }} />}
                loading={isSecurityLoading}
              />
            </Tooltip>
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="OOM Events"
              value={eventStats?.event_counts?.oom_event || oomData?.total || 0}
              prefix={<WarningOutlined style={{ color: '#f76e6e' }} />}
              loading={isStatsLoading}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Violations"
              value={violations.length}
              prefix={<BugOutlined style={{ color: '#7c8eb5' }} />}
              loading={isSecurityLoading}
            />
          </Card>
        </Col>
      </Row>

      {/* Alerts */}
      {criticalViolationsCount > 0 && (
        <Alert
          message="Critical Security Violations Detected"
          description={`There are ${criticalViolationsCount} critical security violations that require immediate attention.`}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" type="primary" danger onClick={() => setActiveTab('violations')}>
              View Violations
            </Button>
          }
        />
      )}

      {/* Main Content */}
      <Card bordered={false}>
        {!selectedAnalysisId ? (
          <Empty description="Select an analysis to view security data" />
        ) : isLoading ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading security data...</Text>
          </div>
        ) : (
          <Tabs activeKey={activeTab} onChange={setActiveTab}>
            <Tabs.TabPane
              tab={<span><LockOutlined /> Capabilities ({filteredCapabilities.length})</span>}
              key="capabilities"
            >
              <Table
                dataSource={filteredCapabilities}
                columns={addClusterColumn(capabilityColumns)}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} capabilities`
                }}
                size="middle"
                locale={{ emptyText: <Empty description="No capability checks recorded" /> }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedSecurityEvent({ ...record, eventType: 'capability' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={
                <span>
                  <ExclamationCircleOutlined /> 
                  Violations 
                  <Badge 
                    count={filteredViolations.length} 
                    style={{ marginLeft: 8, backgroundColor: criticalViolationsCount > 0 ? '#cf1322' : undefined }} 
                  />
                </span>
              }
              key="violations"
            >
              <Table
                dataSource={filteredViolations}
                columns={addClusterColumn(violationColumns)}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} violations`
                }}
                size="middle"
                locale={{ emptyText: <Empty description="No security violations detected" image={<SafetyCertificateOutlined style={{ fontSize: 48, color: '#4d9f7c' }} />} /> }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedSecurityEvent({ ...record, eventType: 'violation' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
            <Tabs.TabPane
              tab={<span><WarningOutlined /> OOM Events ({filteredOomEvents.length})</span>}
              key="oom"
            >
              <Table
                dataSource={filteredOomEvents}
                columns={addClusterColumn(oomColumns)}
                pagination={{ 
                  pageSize: 20,
                  showSizeChanger: true,
                  showTotal: (total) => `Total ${total} OOM events`
                }}
                size="middle"
                locale={{ emptyText: <Empty description="No OOM events recorded" image={<ClockCircleOutlined style={{ fontSize: 48, color: '#4d9f7c' }} />} /> }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedSecurityEvent({ ...record, eventType: 'oom' });
                    setEventDetailVisible(true);
                  },
                  style: { cursor: 'pointer' }
                })}
              />
            </Tabs.TabPane>
          </Tabs>
        )}
      </Card>

      {/* Security Score Info Modal */}
      <Modal
        title={
          <Space>
            <InfoCircleOutlined style={{ color: '#0891b2' }} />
            <span>Security Score Calculation</span>
          </Space>
        }
        open={scoreInfoVisible}
        onCancel={() => setScoreInfoVisible(false)}
        footer={[
          <Button key="close" type="primary" onClick={() => setScoreInfoVisible(false)}>
            Got it
          </Button>
        ]}
        width={650}
      >
        <div style={{ padding: '16px 0' }}>
          {/* No data message */}
          {securityStatus === 'no_data' && (
            <Alert
              message="No Security Data Collected"
              description={securityMessage || "Start an analysis with security gadgets enabled to collect security events and calculate a score."}
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}
          
          {/* No selection message */}
          {securityStatus === 'no_selection' && (
            <Alert
              message="No Analysis Selected"
              description="Select an analysis to view security data and calculate a score."
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
          )}

          <Alert
            message="How Security Score is Calculated"
            description="The security score starts at 100 and reflects the security posture of your cluster based on capability checks, violations, and resource events."
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />
          
          <Title level={5}>Deductions (from 100)</Title>
          <Table
            dataSource={[
              { key: '1', category: 'Critical Violations', impact: '-12 pts each (max -40)', description: 'Blocked critical capability requests (e.g., CAP_SYS_ADMIN denied)' },
              { key: '2', category: 'High Violations', impact: '-8 pts each (max -30)', description: 'Blocked high-risk capability requests (e.g., CAP_SYS_PTRACE denied)' },
              { key: '3', category: 'Medium Violations', impact: '-4 pts each (max -20)', description: 'Blocked medium-risk capability requests' },
              { key: '4', category: 'Low Violations', impact: '-1 pt each (max -5)', description: 'Blocked low-risk capability requests' },
              { key: '5', category: 'High Violation Ratio', impact: 'Up to -20 pts', description: 'Additional penalty when >10% of capability checks are violations' },
              { key: '6', category: 'Critical Capabilities', impact: '-6 pts each (max -25)', description: 'Pods using critical capabilities (CAP_SYS_ADMIN, CAP_SYS_MODULE)' },
              { key: '7', category: 'High-Risk Capabilities', impact: '-3 pts each (max -15)', description: 'Pods using high-risk capabilities (CAP_SYS_PTRACE, CAP_NET_ADMIN)' },
              { key: '8', category: 'OOM Events', impact: '-4 pts each (max -20)', description: 'Out-of-memory kills detected in pods' },
            ]}
            columns={[
              { title: 'Category', dataIndex: 'category', key: 'category', width: 160 },
              { title: 'Impact', dataIndex: 'impact', key: 'impact', width: 140, render: (text) => <Tag color="red">{text}</Tag> },
              { title: 'Description', dataIndex: 'description', key: 'description' },
            ]}
            pagination={false}
            size="small"
          />
          
          <Title level={5} style={{ marginTop: 16 }}>Bonuses (requires ≥10 capability checks)</Title>
          <Table
            dataSource={[
              { key: '1', category: 'No Critical Issues', impact: '+5 points', description: 'No critical violations and no critical capabilities in use' },
              { key: '2', category: 'Zero Violations', impact: '+5 points', description: 'All capability checks were allowed (perfect security policy)' },
              { key: '3', category: 'No High-Risk Caps', impact: '+3 points', description: 'No critical or high-risk capabilities in use by any pod' },
            ]}
            columns={[
              { title: 'Category', dataIndex: 'category', key: 'category', width: 160 },
              { title: 'Impact', dataIndex: 'impact', key: 'impact', width: 140, render: (text) => <Tag color="green">{text}</Tag> },
              { title: 'Description', dataIndex: 'description', key: 'description' },
            ]}
            pagination={false}
            size="small"
          />

          {/* Current breakdown if available */}
          {securityScoreData.breakdown && securityScoreData.breakdown.length > 0 && (
            <>
              <Title level={5} style={{ marginTop: 16 }}>Your Current Score Breakdown</Title>
              <Table
                dataSource={securityScoreData.breakdown.map((item, idx) => ({ key: idx, ...item }))}
                columns={[
                  { title: 'Factor', dataIndex: 'label', key: 'label' },
                  { title: 'Count/Value', dataIndex: 'value', key: 'value', width: 90, render: (v: number, record: any) => 
                    record.label === 'High Violation Ratio' ? `${v}%` : v
                  },
                  { 
                    title: 'Impact', 
                    dataIndex: 'impact', 
                    key: 'impact', 
                    width: 100,
                    render: (impact: number) => (
                      <Tag color={impact > 0 ? 'green' : 'red'}>
                        {impact > 0 ? '+' : ''}{impact}
                      </Tag>
                    )
                  },
                ]}
                pagination={false}
                size="small"
                summary={() => (
                  <Table.Summary>
                    <Table.Summary.Row>
                      <Table.Summary.Cell index={0}><strong>Final Score</strong></Table.Summary.Cell>
                      <Table.Summary.Cell index={1}></Table.Summary.Cell>
                      <Table.Summary.Cell index={2}>
                        <Tag color={
                          securityScore === null ? 'default' :
                          securityScore >= 80 ? 'green' : 
                          securityScore >= 60 ? 'orange' : 'red'
                        }>
                          {securityScore ?? '-'} / 100
                        </Tag>
                      </Table.Summary.Cell>
                    </Table.Summary.Row>
                  </Table.Summary>
                )}
              />
            </>
          )}

          {/* Perfect score message */}
          {securityStatus === 'calculated' && securityScore === 100 && (
            <Alert
              message="Perfect Score!"
              description="No security issues detected. Your cluster has a perfect security score of 100."
              type="success"
              showIcon
              style={{ marginTop: 16 }}
            />
          )}
          
          {/* Good score but no breakdown (clean cluster) */}
          {securityStatus === 'calculated' && securityScore !== null && securityScore >= 80 && 
           (!securityScoreData.breakdown || securityScoreData.breakdown.length === 0) && (
            <Alert
              message="Excellent Security Posture"
              description={`Your cluster has a security score of ${securityScore}. No significant security issues were found.`}
              type="success"
              showIcon
              style={{ marginTop: 16 }}
            />
          )}
        </div>
      </Modal>

      {/* Security Event Detail Modal */}
      <Modal
        title={
          <Space>
            {selectedSecurityEvent?.eventType === 'capability' && <LockOutlined style={{ color: '#0891b2' }} />}
            {selectedSecurityEvent?.eventType === 'violation' && <ExclamationCircleOutlined style={{ color: '#c75450' }} />}
            {selectedSecurityEvent?.eventType === 'oom' && <WarningOutlined style={{ color: '#f76e6e' }} />}
            <span>
              {selectedSecurityEvent?.eventType === 'capability' && 'Capability Details'}
              {selectedSecurityEvent?.eventType === 'violation' && 'Security Violation Details'}
              {selectedSecurityEvent?.eventType === 'oom' && 'OOM Event Details'}
            </span>
          </Space>
        }
        open={eventDetailVisible}
        onCancel={() => {
          setEventDetailVisible(false);
          setSelectedSecurityEvent(null);
        }}
        footer={[
          <Button key="close" onClick={() => setEventDetailVisible(false)}>
            Close
          </Button>
        ]}
        width={650}
      >
        {selectedSecurityEvent && (
          <div style={{ padding: '8px 0' }}>
            {/* Event Type Badge */}
            <div style={{ marginBottom: 16, textAlign: 'center' }}>
              <Tag 
                color={
                  selectedSecurityEvent.eventType === 'violation' ? 'error' :
                  selectedSecurityEvent.eventType === 'oom' ? 'warning' : 'processing'
                }
                style={{ fontSize: 14, padding: '4px 12px' }}
              >
                {selectedSecurityEvent.eventType?.toUpperCase()}
              </Tag>
              {selectedSecurityEvent.risk && (
                <Tag color={riskColors[selectedSecurityEvent.risk as keyof typeof riskColors]} style={{ marginLeft: 8 }}>
                  {selectedSecurityEvent.risk?.toUpperCase()} RISK
                </Tag>
              )}
              {selectedSecurityEvent.severity && (
                <Tag color={riskColors[selectedSecurityEvent.severity as keyof typeof riskColors]} style={{ marginLeft: 8 }}>
                  {selectedSecurityEvent.severity?.toUpperCase()}
                </Tag>
              )}
            </div>

            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="Pod" span={2}>
                <Text strong>{selectedSecurityEvent.pod || '-'}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Namespace">
                <Tag color="blue">{selectedSecurityEvent.namespace || '-'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Container">
                {selectedSecurityEvent.container || '-'}
              </Descriptions.Item>
              
              {selectedSecurityEvent.capability && (
                <>
                  <Descriptions.Item label="Capability" span={2}>
                    <Text code style={{ fontSize: 13 }}>{selectedSecurityEvent.capability}</Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Description" span={2}>
                    {selectedSecurityEvent.description || capabilityRisk[selectedSecurityEvent.capability]?.description || 'No description available'}
                  </Descriptions.Item>
                </>
              )}
              
              {selectedSecurityEvent.syscall && (
                <Descriptions.Item label="Syscall">
                  <Text code>{selectedSecurityEvent.syscall}</Text>
                </Descriptions.Item>
              )}
              
              {selectedSecurityEvent.pid !== undefined && selectedSecurityEvent.pid > 0 && (
                <Descriptions.Item label="PID">
                  {selectedSecurityEvent.pid}
                </Descriptions.Item>
              )}
              
              {selectedSecurityEvent.comm && (
                <Descriptions.Item label="Command">
                  <Text code>{selectedSecurityEvent.comm}</Text>
                </Descriptions.Item>
              )}
              
              {selectedSecurityEvent.action && (
                <Descriptions.Item label="Action">
                  <Tag color={selectedSecurityEvent.action === 'blocked' ? 'red' : 'green'}>
                    {selectedSecurityEvent.action}
                  </Tag>
                </Descriptions.Item>
              )}
              
              {/* Capability specific */}
              {selectedSecurityEvent.usageCount !== undefined && (
                <>
                  <Descriptions.Item label="Total Calls">
                    {selectedSecurityEvent.usageCount}
                  </Descriptions.Item>
                  <Descriptions.Item label="Allowed / Denied">
                    <Text type="success">{selectedSecurityEvent.allowed || 0} allowed</Text>
                    {' / '}
                    <Text type="danger">{selectedSecurityEvent.denied || 0} denied</Text>
                  </Descriptions.Item>
                </>
              )}
              
              {/* OOM specific */}
              {selectedSecurityEvent.killedPid && (
                <Descriptions.Item label="Killed PID">
                  {selectedSecurityEvent.killedPid}
                </Descriptions.Item>
              )}
              
              {selectedSecurityEvent.pages !== undefined && (
                <Descriptions.Item label="Pages">
                  {selectedSecurityEvent.pages}
                </Descriptions.Item>
              )}
              
              {selectedSecurityEvent.oomScoreAdj !== undefined && (
                <Descriptions.Item label="OOM Score Adj">
                  {selectedSecurityEvent.oomScoreAdj}
                </Descriptions.Item>
              )}
              
              <Descriptions.Item label="Timestamp" span={2}>
                {selectedSecurityEvent.lastSeen 
                  ? dayjs(selectedSecurityEvent.lastSeen).format('YYYY-MM-DD HH:mm:ss')
                  : selectedSecurityEvent.timestamp 
                    ? dayjs(selectedSecurityEvent.timestamp).format('YYYY-MM-DD HH:mm:ss')
                    : '-'}
              </Descriptions.Item>
            </Descriptions>

            {/* Risk Explanation */}
            {selectedSecurityEvent.capability && capabilityRisk[selectedSecurityEvent.capability] && (
              <Alert
                message={`Why is ${selectedSecurityEvent.capability} ${capabilityRisk[selectedSecurityEvent.capability].risk} risk?`}
                description={capabilityRisk[selectedSecurityEvent.capability].description}
                type={
                  capabilityRisk[selectedSecurityEvent.capability].risk === 'critical' ? 'error' :
                  capabilityRisk[selectedSecurityEvent.capability].risk === 'high' ? 'warning' : 'info'
                }
                showIcon
                style={{ marginTop: 16 }}
              />
            )}

            {selectedSecurityEvent.eventType === 'oom' && (
              <Alert
                message="Out of Memory Kill"
                description="This pod was killed by the Linux OOM killer because it exceeded its memory limits. Consider increasing memory limits or optimizing memory usage."
                type="error"
                showIcon
                style={{ marginTop: 16 }}
              />
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

// Helper function to format bytes
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'Ki', 'Mi', 'Gi', 'Ti'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

export default SecurityCenter;
