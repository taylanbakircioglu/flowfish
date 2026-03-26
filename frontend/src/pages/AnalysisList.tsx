import React, { useState } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Typography,
  Tag,
  Popconfirm,
  message,
  Row,
  Col,
  Statistic,
  Modal,
  Progress,
  Descriptions,
  Spin,
  Tooltip,
  Divider,
  Drawer,
  Badge,
  Alert,
  theme
} from 'antd';
import {
  PlusOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  DeleteOutlined,
  EyeOutlined,
  ExperimentOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FieldTimeOutlined,
  DatabaseOutlined,
  NodeIndexOutlined,
  WarningOutlined,
  SyncOutlined,
  HistoryOutlined,
  GlobalOutlined,
  ClusterOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  HddOutlined,
  DashboardOutlined,
  CalendarOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import {
  useGetAnalysesQuery,
  useStartAnalysisMutation,
  useStopAnalysisMutation,
  useDeleteAnalysisMutation,
  useUnscheduleAnalysisMutation,
  useGetAnalysisRunsQuery,
  DeleteAnalysisResponse,
  StopAnalysisResponse,
  AnalysisRun,
  analysisApi
} from '../store/api/analysisApi';
import { eventsApi } from '../store/api/eventsApi';
import { communicationApi } from '../store/api/communicationApi';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { Analysis, Cluster } from '../types';
import { useAnimatedCounter } from '../hooks/useAnimatedCounter';
import { useUserPermissions } from '../hooks/useUserPermissions';

const { Title, Text } = Typography;
const { useToken } = theme;

// Component to show expanded row with analysis run details
const ExpandedAnalysisRow: React.FC<{ analysisId: number }> = ({ analysisId }) => {
  const { token } = useToken();
  const { data: runs = [], isLoading } = useGetAnalysisRunsQuery(analysisId);
  
  // Calculate totals (must be before hooks for consistent ordering)
  const totalEvents = runs.reduce((sum, run) => sum + (run.events_collected || 0), 0);
  const totalConnections = runs.reduce((sum, run) => sum + (run.communications_discovered || 0), 0);
  const totalDuration = runs.reduce((sum, run) => {
    if (run.start_time && run.end_time) {
      return sum + (new Date(run.end_time).getTime() - new Date(run.start_time).getTime());
    }
    return sum;
  }, 0);
  
  // Animated counters
  const animatedRuns = useAnimatedCounter(runs.length, 1200, isLoading);
  const animatedEvents = useAnimatedCounter(totalEvents, 1200, isLoading);
  const animatedConns = useAnimatedCounter(totalConnections, 1200, isLoading);
  
  if (isLoading) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        <Spin size="small" />
        <Text type="secondary" style={{ marginLeft: 8 }}>Loading run history...</Text>
      </div>
    );
  }
  
  if (runs.length === 0) {
    return (
      <div style={{ padding: 16, textAlign: 'center' }}>
        <Text type="secondary">
          <HistoryOutlined style={{ marginRight: 8 }} />
          This analysis has not been run yet
        </Text>
      </div>
    );
  }
  
  // Get the latest run
  const latestRun = runs[0];
  
  const formatDuration = (ms: number) => {
    if (ms === 0) return '-';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };
  
  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString();
  };
  
  const getRunStatusColor = (status: string) => {
    const colorMap: Record<string, string> = {
      'running': 'processing',
      'completed': 'success',
      'stopped': 'warning',
      'failed': 'error',
    };
    return colorMap[status] || 'default';
  };
  
  return (
    <div style={{ padding: '12px 16px', background: token.colorBgLayout, borderRadius: 6 }}>
      {/* Summary Statistics with animated counters */}
      <Row gutter={[16, 8]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              <HistoryOutlined /> Total Runs
            </Text>
            <span style={{ fontSize: 18, fontWeight: 600, color: '#0891b2' }}>
              {animatedRuns.toLocaleString()}
            </span>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              <DatabaseOutlined /> Total Events
            </Text>
            <span style={{ fontSize: 18, fontWeight: 600, color: '#4d9f7c' }}>
              {animatedEvents.toLocaleString()}
            </span>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              <NodeIndexOutlined /> Connections
            </Text>
            <span style={{ fontSize: 18, fontWeight: 600, color: '#7c8eb5' }}>
              {animatedConns.toLocaleString()}
            </span>
          </div>
        </Col>
        <Col xs={12} sm={6}>
          <div>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
              <FieldTimeOutlined /> Total Duration
            </Text>
            <span style={{ fontSize: 18, fontWeight: 600, color: '#b89b5d' }}>
              {formatDuration(totalDuration)}
            </span>
          </div>
        </Col>
      </Row>
      
      <Divider style={{ margin: '12px 0' }} />
      
      {/* Latest Run Info */}
      <div style={{ marginBottom: 12 }}>
        <Text strong style={{ fontSize: 13 }}>Latest Run Details</Text>
      </div>
      
      <Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }} bordered>
        <Descriptions.Item label="Status">
          <Tag color={getRunStatusColor(latestRun.status)}>
            {latestRun.status === 'running' && <SyncOutlined spin style={{ marginRight: 4 }} />}
            {latestRun.status.toUpperCase()}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Start Time">
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {formatDate(latestRun.start_time)}
        </Descriptions.Item>
        <Descriptions.Item label="End Time">
          {latestRun.end_time ? (
            <>
              <ClockCircleOutlined style={{ marginRight: 4 }} />
              {formatDate(latestRun.end_time)}
            </>
          ) : (
            <Text type="secondary">-</Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Events">
          <Tag color="blue">{(latestRun.events_collected || 0).toLocaleString()}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Connections">
          <Tag color="purple">{(latestRun.communications_discovered || 0).toLocaleString()}</Tag>
        </Descriptions.Item>
        {latestRun.error_message && (
          <Descriptions.Item label="Error" span={3}>
            <Tag color="error" icon={<WarningOutlined />}>
              {latestRun.error_message}
            </Tag>
          </Descriptions.Item>
        )}
      </Descriptions>
      
      {/* Run History (if more than 1 run) */}
      {runs.length > 1 && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          <div style={{ marginBottom: 8 }}>
            <Text strong style={{ fontSize: 13 }}>Run History (Last 5)</Text>
          </div>
          <Table
            size="small"
            pagination={false}
            dataSource={runs.slice(0, 5)}
            rowKey="id"
            columns={[
              {
                title: 'Status',
                dataIndex: 'status',
                width: 100,
                render: (status: string) => (
                  <Tag color={getRunStatusColor(status)} style={{ fontSize: 11 }}>
                    {status.toUpperCase()}
                  </Tag>
                ),
              },
              {
                title: 'Started',
                dataIndex: 'start_time',
                render: (date: string) => (
                  <Text style={{ fontSize: 11 }}>
                    {new Date(date).toLocaleString()}
                  </Text>
                ),
              },
              {
                title: 'Events',
                dataIndex: 'events_collected',
                align: 'right' as const,
                render: (count: number) => (
                  <Text style={{ fontSize: 11 }}>
                    {(count || 0).toLocaleString()}
                  </Text>
                ),
              },
              {
                title: 'Conns',
                dataIndex: 'communications_discovered',
                align: 'right' as const,
                render: (count: number) => (
                  <Text style={{ fontSize: 11 }}>
                    {(count || 0).toLocaleString()}
                  </Text>
                ),
              },
            ]}
          />
        </>
      )}
    </div>
  );
};

// Inline component to show run stats in table cell
const RunStatsCell: React.FC<{ analysisId: number; field: 'events' | 'communications' | 'duration' | 'lastRun' }> = ({ analysisId, field }) => {
  const { data: runs = [], isLoading } = useGetAnalysisRunsQuery(analysisId);
  
  if (isLoading) {
    return <Spin size="small" />;
  }
  
  if (runs.length === 0) {
    return <Text type="secondary">-</Text>;
  }
  
  const latestRun = runs[0];
  const totalEvents = runs.reduce((sum, run) => sum + (run.events_collected || 0), 0);
  const totalConnections = runs.reduce((sum, run) => sum + (run.communications_discovered || 0), 0);
  
  // Calculate total duration from all runs
  const totalDurationMs = runs.reduce((sum, run) => {
    if (run.start_time && run.end_time) {
      return sum + (new Date(run.end_time).getTime() - new Date(run.start_time).getTime());
    } else if (run.start_time && !run.end_time) {
      // Running analysis - calculate from start to now
      return sum + (Date.now() - new Date(run.start_time).getTime());
    }
    return sum;
  }, 0);
  
  const formatDuration = (ms: number) => {
    if (ms === 0) return '-';
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };
  
  switch (field) {
    case 'events':
      return (
        <Tooltip title={`Total: ${totalEvents.toLocaleString()} events from ${runs.length} run(s)`}>
          <Tag color="blue" style={{ minWidth: 50, textAlign: 'center' }}>
            <DatabaseOutlined style={{ marginRight: 4 }} />
            {totalEvents.toLocaleString()}
          </Tag>
        </Tooltip>
      );
    case 'communications':
      return (
        <Tooltip title={`Total: ${totalConnections.toLocaleString()} connections from ${runs.length} run(s)`}>
          <Tag color="purple" style={{ minWidth: 50, textAlign: 'center' }}>
            <NodeIndexOutlined style={{ marginRight: 4 }} />
            {totalConnections.toLocaleString()}
          </Tag>
        </Tooltip>
      );
    case 'duration':
      return (
        <Tooltip title={`Total runtime from ${runs.length} run(s)`}>
          <Tag color="orange" style={{ minWidth: 50, textAlign: 'center' }}>
            <FieldTimeOutlined style={{ marginRight: 4 }} />
            {formatDuration(totalDurationMs)}
          </Tag>
        </Tooltip>
      );
    case 'lastRun':
      const runDate = latestRun.start_time ? new Date(latestRun.start_time) : null;
      // Compact date format: "31 Dec" or "31 Dec 24" if not current year
      const formatDate = (d: Date) => {
        const day = d.getDate();
        const month = d.toLocaleString('en', { month: 'short' });
        const year = d.getFullYear();
        const currentYear = new Date().getFullYear();
        return year === currentYear ? `${day} ${month}` : `${day} ${month} ${String(year).slice(-2)}`;
      };
      return (
        <Tooltip title={runDate?.toLocaleString() || 'No runs yet'}>
          <Text style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
            {runDate ? formatDate(runDate) : '-'}
          </Text>
        </Tooltip>
      );
    default:
      return <Text type="secondary">-</Text>;
  }
};

const AnalysisList: React.FC = () => {
  const { token } = useToken();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  
  // Get user permissions for role-based access control
  const { isViewer, canCreateAnalysis, canStartAnalysis, canStopAnalysis, canDeleteAnalysis } = useUserPermissions();
  
  const { data: analyses = [], isLoading, isFetching, refetch } = useGetAnalysesQuery({});
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  const [startAnalysis] = useStartAnalysisMutation();
  const [stopAnalysis] = useStopAnalysisMutation();
  const [deleteAnalysis] = useDeleteAnalysisMutation();
  const [unscheduleAnalysis] = useUnscheduleAnalysisMutation();
  
  // Helper to get cluster name by ID
  const getClusterName = (clusterId: number): string => {
    const cluster = clusters.find((c: Cluster) => c.id === clusterId);
    return cluster?.name || `Cluster ${clusterId}`;
  };
  
  // Helper to get cluster info for multi-cluster display
  const getClusterInfo = (analysis: Analysis): { names: string[]; count: number; isMulti: boolean } => {
    const clusterIds = analysis.cluster_ids || [analysis.cluster_id];
    const isMulti = analysis.is_multi_cluster || clusterIds.length > 1;
    const names = clusterIds.map(id => getClusterName(id));
    return { names, count: clusterIds.length, isMulti };
  };
  
  // Loading state for Start/Stop operations
  const [loadingAnalysisId, setLoadingAnalysisId] = useState<number | null>(null);
  const [loadingAction, setLoadingAction] = useState<'start' | 'stop' | null>(null);
  
  // Delete progress state
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [deleteProgress, setDeleteProgress] = useState<'idle' | 'deleting' | 'done'>('idle');
  const [deleteResult, setDeleteResult] = useState<DeleteAnalysisResponse | null>(null);
  const [deletingAnalysisName, setDeletingAnalysisName] = useState('');
  
  // Analysis detail drawer state
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [selectedAnalysis, setSelectedAnalysis] = useState<Analysis | null>(null);
  
  // Pagination state
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  
  const openDetailDrawer = (analysis: Analysis) => {
    setSelectedAnalysis(analysis);
    setDetailDrawerVisible(true);
  };
  
  const closeDetailDrawer = () => {
    setDetailDrawerVisible(false);
    setSelectedAnalysis(null);
  };

  const handleStart = (analysisId: number) => {
    // Set loading state for UI feedback
    setLoadingAnalysisId(analysisId);
    setLoadingAction('start');
    
    // Show global loading message (survives page navigation)
    const hideLoading = message.loading('Starting analysis...', 0);
    
    // Fire and forget - operation continues even if user navigates away
    startAnalysis(analysisId).unwrap()
      .then(() => {
        hideLoading();
        message.success('Analysis started successfully');
        // Refresh page data after successful start
        dispatch(analysisApi.util.invalidateTags(['Analysis', 'AnalysisRun']));
      })
      .catch(() => {
        hideLoading();
        message.error('Failed to start analysis');
      })
      .finally(() => {
        setLoadingAnalysisId(null);
        setLoadingAction(null);
      });
  };

  const handleStop = (analysisId: number) => {
    // Set loading state for UI feedback
    setLoadingAnalysisId(analysisId);
    setLoadingAction('stop');
    
    // Show global loading message (survives page navigation)
    const hideLoading = message.loading('Stopping analysis...', 0);
    
    // Fire and forget - operation continues even if user navigates away
    stopAnalysis(analysisId).unwrap()
      .then((result: StopAnalysisResponse) => {
        hideLoading();
        // Check orchestrator status - backend verifies actual stop status
        if (result.orchestrator_status === 'warning') {
          message.warning('Analysis stop command sent but could not verify. Please check cluster status.', 6);
        } else {
          message.success(`Analysis stopped successfully. ${result.events_collected?.toLocaleString() || 0} events collected.`, 4);
        }
        // Refresh page data after successful stop
        dispatch(analysisApi.util.invalidateTags(['Analysis', 'AnalysisRun']));
      })
      .catch(() => {
        hideLoading();
        message.error('Failed to stop analysis');
      })
      .finally(() => {
        setLoadingAnalysisId(null);
        setLoadingAction(null);
      });
  };

  const handleDelete = async (analysisId: number, analysisName: string) => {
    // Show progress modal
    setDeletingAnalysisName(analysisName);
    setDeleteProgress('deleting');
    setDeleteResult(null);
    setDeleteModalVisible(true);
    
    try {
      const result = await deleteAnalysis(analysisId).unwrap();
      setDeleteResult(result);
      setDeleteProgress('done');
      
      // Clear related caches - events and communications for deleted analysis
      dispatch(eventsApi.util.resetApiState());
      dispatch(communicationApi.util.resetApiState());
      
      refetch();
    } catch (error: any) {
      setDeleteProgress('done');
      setDeleteResult({
        analysis_id: analysisId,
        deleted: false,
        neo4j: {},
        clickhouse: {},
        duration_ms: 0,
        message: `Error: ${error?.data?.detail || error?.message || 'Unknown error'}`
      });
    }
  };
  
  const closeDeleteModal = () => {
    setDeleteModalVisible(false);
    setDeleteProgress('idle');
    setDeleteResult(null);
  };

  const getStatusColor = (status: string) => {
    const colorMap: Record<string, string> = {
      'draft': 'default',
      'running': 'processing',
      'running_with_errors': 'warning',  // Running but some gadgets failed
      'stopped': 'warning',
      'completed': 'success',
      'failed': 'error',
    };
    return colorMap[status] || 'default';
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      width: 220,
      ellipsis: true,
      render: (text: string, record: Analysis) => {
        const clusterInfo = getClusterInfo(record);
        const clusterDisplay = clusterInfo.isMulti 
          ? `${clusterInfo.count} clusters` 
          : clusterInfo.names[0] || 'Unknown';
        
        return (
          <Tooltip title={
            <div>
              <div><strong>{text}</strong></div>
              {record.description && <div style={{ marginTop: 4 }}>{record.description}</div>}
              <div style={{ marginTop: 4 }}>Cluster(s): {clusterInfo.names.join(', ')}</div>
            </div>
          }>
            <div>
              <div style={{ fontWeight: 500, marginBottom: 2 }}>{text}</div>
              <Tag 
                color={clusterInfo.isMulti ? "purple" : "blue"} 
                style={{ fontSize: 10, margin: 0 }}
              >
                {clusterInfo.isMulti && <GlobalOutlined style={{ marginRight: 2 }} />}
                {!clusterInfo.isMulti && <ClusterOutlined style={{ marginRight: 2 }} />}
                {clusterDisplay}
              </Tag>
            </div>
          </Tooltip>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string, record: Analysis) => {
        const isAutoStopped = record.output_config?.auto_stopped === true;
        const autoStopReason = record.output_config?.auto_stop_reason as string | undefined;
        const hasGadgetWarnings = record.output_config?.has_gadget_warnings === true;
        const gadgetErrors = (record.output_config?.gadget_errors as Array<{gadget: string; error: string}>) || [];
        
        // Build tooltip content
        let tooltipContent = '';
        if (isAutoStopped) {
          tooltipContent = `Auto-stopped: ${autoStopReason || 'limit reached'}`;
        }
        if (hasGadgetWarnings && gadgetErrors.length > 0) {
          const failedGadgets = gadgetErrors.map(e => e.gadget).join(', ');
          tooltipContent += tooltipContent ? '\n' : '';
          tooltipContent += `Gadget errors: ${failedGadgets}`;
        }
        
        return (
          <Space size={4}>
            <Tooltip title={tooltipContent || undefined}>
              <Tag color={getStatusColor(status)}>
                {status === 'running' && <SyncOutlined spin style={{ marginRight: 4 }} />}
                {isAutoStopped && <ClockCircleOutlined style={{ marginRight: 4 }} />}
                {status.toUpperCase()}
                {isAutoStopped && ' *'}
              </Tag>
            </Tooltip>
            {hasGadgetWarnings && (
              <Tooltip title={`Some gadgets failed to start. Click View for details.`}>
                <WarningOutlined style={{ color: '#c9a55a', fontSize: 14 }} />
              </Tooltip>
            )}
          </Space>
        );
      },
      filters: [
        { text: 'Draft', value: 'draft' },
        { text: 'Running', value: 'running' },
        { text: 'Stopped', value: 'stopped' },
        { text: 'Completed', value: 'completed' },
        { text: 'Failed', value: 'failed' },
      ],
      onFilter: (value: string | number | boolean, record: Analysis) => record.status === value,
    },
    {
      title: 'Scope',
      dataIndex: 'scope_type',
      key: 'scope_type',
      width: 85,
      render: (scopeType: string) => <Tag style={{ fontSize: 11 }}>{scopeType}</Tag>,
    },
    {
      title: 'Events',
      key: 'gadgets',
      width: 80,
      align: 'center' as const,
      render: (record: Analysis) => {
        const gadgets = (record.gadget_config?.enabled_gadgets as string[]) || [];
        if (gadgets.length === 0) {
          return <Typography.Text type="secondary">-</Typography.Text>;
        }
        return (
          <Tooltip title={gadgets.map(g => g.replace(/_/g, ' ')).join(', ')}>
            <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>
              {gadgets.length} types
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: 'Mode',
      key: 'time_mode',
      width: 85,
      render: (record: Analysis) => {
        const mode = (record.time_config?.mode as string) || 'continuous';
        const modeLabels: Record<string, { label: string; color: string }> = {
          'continuous': { label: 'Continuous', color: 'green' },
          'timed': { label: 'Timed', color: 'blue' },
          'time_range': { label: 'Scheduled', color: 'purple' },
          'scheduled': { label: 'Scheduled', color: 'purple' },
          'periodic': { label: 'Periodic', color: 'orange' },
          'baseline': { label: 'Baseline', color: 'cyan' },
          'recurring': { label: 'Recurring', color: 'gold' },
        };
        const modeInfo = modeLabels[mode] || { label: mode, color: 'default' };
        return (
          <Tooltip title={`Run mode: ${modeInfo.label}`}>
            <Tag color={modeInfo.color} style={{ fontSize: 11 }}>
              {modeInfo.label}
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: 'Events',
      key: 'events',
      width: 80,
      align: 'center' as const,
      render: (record: Analysis) => <RunStatsCell analysisId={record.id} field="events" />,
    },
    {
      title: 'Conns',
      key: 'connections',
      width: 75,
      align: 'center' as const,
      render: (record: Analysis) => <RunStatsCell analysisId={record.id} field="communications" />,
    },
    {
      title: 'Duration',
      key: 'duration',
      width: 75,
      align: 'center' as const,
      render: (record: Analysis) => <RunStatsCell analysisId={record.id} field="duration" />,
    },
    {
      title: 'Last Run',
      key: 'lastRun',
      width: 70,
      render: (record: Analysis) => <RunStatsCell analysisId={record.id} field="lastRun" />,
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 70,
      render: (date: string) => {
        const d = new Date(date);
        const day = d.getDate();
        const month = d.toLocaleString('en', { month: 'short' });
        const year = d.getFullYear();
        const currentYear = new Date().getFullYear();
        const display = year === currentYear ? `${day} ${month}` : `${day} ${month} ${String(year).slice(-2)}`;
        return (
          <Tooltip title={d.toLocaleString()}>
            <span style={{ fontSize: 11, whiteSpace: 'nowrap' }}>{display}</span>
          </Tooltip>
        );
      },
      sorter: (a: Analysis, b: Analysis) => 
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (record: Analysis) => {
        const isLoadingThis = loadingAnalysisId === record.id;
        const isStarting = isLoadingThis && loadingAction === 'start';
        const isStopping = isLoadingThis && loadingAction === 'stop';
        
        return (
        <Space size={4}>
          {/* Start/Stop Button */}
          {record.status === 'draft' || record.status === 'stopped' || record.status === 'completed' || record.status === 'failed' ? (
            <Tooltip title={!canStartAnalysis ? "You don't have permission to start analyses (Viewer role)" : "Start Analysis"}>
              <Button
                type="primary"
                size="small"
                icon={isStarting ? <LoadingOutlined spin /> : <PlayCircleOutlined />}
                onClick={() => handleStart(record.id)}
                disabled={isLoadingThis || !canStartAnalysis}
              >
                Start
              </Button>
            </Tooltip>
          ) : record.status === 'running' ? (
            <Tooltip title={!canStopAnalysis ? "You don't have permission to stop analyses (Viewer role)" : "Stop Analysis"}>
              <Button
                type="primary"
                danger
                size="small"
                icon={isStopping ? <LoadingOutlined spin /> : <PauseCircleOutlined />}
                onClick={() => handleStop(record.id)}
                disabled={isLoadingThis || !canStopAnalysis}
              >
                Stop
              </Button>
            </Tooltip>
          ) : null}
          
          {/* View Details */}
          <Tooltip title="View Details">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => openDetailDrawer(record)}
            />
          </Tooltip>
          
          {/* Delete */}
          {record.status !== 'running' && (
            canDeleteAnalysis ? (
              <Popconfirm
                title={
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>Delete Analysis?</div>
                    <div style={{ fontSize: 12, color: '#666' }}>
                      This will permanently delete this analysis's data.
                    </div>
                  </div>
                }
                onConfirm={() => handleDelete(record.id, record.name)}
                okText="Delete"
                cancelText="Cancel"
                okType="danger"
              >
                <Tooltip title="Delete">
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                  />
                </Tooltip>
              </Popconfirm>
            ) : (
              <Tooltip title="You don't have permission to delete analyses (Viewer role)">
                <Button
                  type="text"
                  danger
                  size="small"
                  icon={<DeleteOutlined />}
                  disabled
                />
              </Tooltip>
            )
          )}
        </Space>
        );
      },
    },
  ];

  // Calculate statistics
  const stats = {
    total: analyses.length,
    running: analyses.filter((a) => a.status === 'running').length,
    draft: analyses.filter((a) => a.status === 'draft').length,
    completed: analyses.filter((a) => a.status === 'completed').length,
  };

  // Animated counters for stats cards
  const animatedTotal = useAnimatedCounter(stats.total, 1200, isLoading);
  const animatedRunning = useAnimatedCounter(stats.running, 1200, isLoading);
  const animatedDraft = useAnimatedCounter(stats.draft, 1200, isLoading);
  const animatedCompleted = useAnimatedCounter(stats.completed, 1200, isLoading);

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Row justify="space-between" align="middle" gutter={[16, 16]}>
          <Col xs={24} sm={12}>
            <Title level={2} style={{ margin: 0 }}>
              <ExperimentOutlined /> Analyses
            </Title>
          </Col>
          <Col xs={24} sm={12} style={{ textAlign: 'right' }}>
            <Space wrap>
              <Button
                icon={<SyncOutlined spin={isFetching} />}
                onClick={() => {
                  dispatch(analysisApi.util.invalidateTags(['Analysis', 'AnalysisRun']));
                }}
                disabled={isFetching}
              >
                {isFetching ? 'Refreshing...' : 'Refresh'}
              </Button>
              <Tooltip title={!canCreateAnalysis ? "You don't have permission to create analyses (Viewer role)" : ""}>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/analysis/wizard')}
                  disabled={!canCreateAnalysis}
                >
                  New Analysis
                </Button>
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </div>

      {/* Viewer Role Warning */}
      {isViewer && (
        <Alert
          message="Read-Only Mode"
          description="You are logged in with Viewer role. You can view analyses but cannot create, start, stop, or delete them."
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}
      
      {/* Statistics Cards with animated counters */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div>
              <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Total Analyses</Text>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ExperimentOutlined style={{ color: '#0891b2', fontSize: 20 }} />
                <span style={{ fontSize: 24, fontWeight: 600 }}>
                  {animatedTotal.toLocaleString()}
                </span>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div>
              <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Running</Text>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <PlayCircleOutlined style={{ color: '#4d9f7c', fontSize: 20 }} />
                <span style={{ fontSize: 24, fontWeight: 600, color: '#4d9f7c' }}>
                  {animatedRunning.toLocaleString()}
                </span>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div>
              <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Draft</Text>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ExperimentOutlined style={{ color: '#c9a55a', fontSize: 20 }} />
                <span style={{ fontSize: 24, fontWeight: 600, color: '#c9a55a' }}>
                  {animatedDraft.toLocaleString()}
                </span>
              </div>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <div>
              <Text type="secondary" style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>Completed</Text>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircleOutlined style={{ color: '#7c8eb5', fontSize: 20 }} />
                <span style={{ fontSize: 24, fontWeight: 600, color: '#7c8eb5' }}>
                  {animatedCompleted.toLocaleString()}
                </span>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      {/* Analyses Table */}
      <Card>
        <Table
          size="small"
          columns={columns}
          dataSource={analyses}
          rowKey="id"
          loading={isLoading}
          scroll={{ x: 1000 }}
          expandable={{
            expandedRowRender: (record: Analysis) => (
              <ExpandedAnalysisRow analysisId={record.id} />
            ),
            rowExpandable: () => true,
            expandRowByClick: false,
          }}
          pagination={{
            current: currentPage,
            pageSize: pageSize,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} analyses`,
            onChange: (page, size) => {
              setCurrentPage(page);
              if (size !== pageSize) {
                setPageSize(size);
                setCurrentPage(1); // Reset to first page when page size changes
              }
            },
          }}
        />
      </Card>
      
      {/* Delete Progress Modal */}
      <Modal
        title={
          <Space>
            {deleteProgress === 'deleting' ? (
              <LoadingOutlined spin style={{ color: '#0891b2' }} />
            ) : deleteResult?.deleted ? (
              <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
            ) : (
              <DeleteOutlined style={{ color: '#f76e6e' }} />
            )}
            <span>
              {deleteProgress === 'deleting' 
                ? `Deleting "${deletingAnalysisName}"...` 
                : deleteResult?.deleted 
                  ? 'Deletion Complete' 
                  : 'Deletion Failed'}
            </span>
          </Space>
        }
        open={deleteModalVisible}
        onCancel={closeDeleteModal}
        footer={
          deleteProgress === 'done' ? (
            <Button type="primary" onClick={closeDeleteModal}>
              Close
            </Button>
          ) : null
        }
        closable={deleteProgress === 'done'}
        maskClosable={false}
        width={500}
      >
        {deleteProgress === 'deleting' && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <Progress 
              type="circle" 
              percent={99} 
              status="active"
              format={() => <LoadingOutlined style={{ fontSize: 24 }} />}
            />
            <div style={{ marginTop: 16 }}>
              <Text type="secondary">
                Cleaning up Neo4j graph data and ClickHouse events...
              </Text>
            </div>
          </div>
        )}
        
        {deleteProgress === 'done' && deleteResult && (
          <div>
            {deleteResult.deleted ? (
              <div style={{ 
                background: '#f6ffed', 
                border: '1px solid #b7eb8f', 
                borderRadius: 6, 
                padding: 16,
                textAlign: 'center'
              }}>
                <CheckCircleOutlined style={{ fontSize: 32, color: '#4d9f7c', marginBottom: 12 }} />
                <div>
                  <Text strong style={{ fontSize: 16 }}>
                    Analysis deleted successfully
                  </Text>
                </div>
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary">
                    {(deleteResult.clickhouse?.total_deleted || 0).toLocaleString()} events removed
                  </Text>
                </div>
                <div style={{ marginTop: 4 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Completed in {(deleteResult.duration_ms / 1000).toFixed(1)}s
                  </Text>
                </div>
              </div>
            ) : (
              <div style={{ 
                background: token.colorErrorBg, 
                border: `1px solid ${token.colorErrorBorder}`, 
                borderRadius: 6, 
                padding: 12 
              }}>
                <Text type="danger">{deleteResult.message}</Text>
              </div>
            )}
          </div>
        )}
      </Modal>
      
      {/* Analysis Detail Drawer */}
      <Drawer
        title={
          <Space wrap size="small">
            <SettingOutlined />
            <span>Analysis Configuration</span>
            {selectedAnalysis && (
              <Tag color={
                selectedAnalysis.status === 'running' ? 'processing' :
                selectedAnalysis.status === 'completed' ? 'success' :
                selectedAnalysis.status === 'stopped' ? 'warning' :
                selectedAnalysis.status === 'failed' ? 'error' : 'default'
              }>
                {selectedAnalysis.status?.toUpperCase()}
              </Tag>
            )}
          </Space>
        }
        placement="right"
        width={Math.min(600, typeof window !== 'undefined' ? window.innerWidth - 48 : 600)}
        open={detailDrawerVisible}
        onClose={closeDetailDrawer}
        extra={
          selectedAnalysis && (
            <Space>
              {(selectedAnalysis.status === 'running' || selectedAnalysis.status === 'stopped' || selectedAnalysis.status === 'completed') && (
                <Button 
                  type="primary"
                  icon={<DashboardOutlined />}
                  onClick={() => {
                    closeDetailDrawer();
                    navigate(`/dashboard?analysisId=${selectedAnalysis.id}`);
                  }}
                >
                  Dashboard
                </Button>
              )}
            </Space>
          )
        }
      >
        {selectedAnalysis && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* Basic Info */}
            <Card size="small" title={<><ExperimentOutlined /> Basic Information</>}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Name">
                  <Text strong>{selectedAnalysis.name}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Description">
                  {selectedAnalysis.description || <Text type="secondary">No description</Text>}
                </Descriptions.Item>
                <Descriptions.Item label="ID">
                  <Text code>#{selectedAnalysis.id}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="Created">
                  {new Date(selectedAnalysis.created_at).toLocaleString()}
                </Descriptions.Item>
              </Descriptions>
            </Card>
            
            {/* Cluster & Scope */}
            <Card size="small" title={<><ClusterOutlined /> Cluster & Scope</>}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Mode">
                  {selectedAnalysis.is_multi_cluster ? (
                    <Tag color="purple"><GlobalOutlined /> Multi-Cluster</Tag>
                  ) : (
                    <Tag color="blue"><ClusterOutlined /> Single Cluster</Tag>
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="Cluster(s)">
                  <Space wrap>
                    {(selectedAnalysis.cluster_ids || [selectedAnalysis.cluster_id]).map((id: number) => (
                      <Tag key={id} color="cyan">{getClusterName(id)}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="Scope Type">
                  <Tag>{selectedAnalysis.scope_type || 'cluster'}</Tag>
                </Descriptions.Item>
                {selectedAnalysis.scope_type === 'namespace' && selectedAnalysis.scope_config?.namespaces && (
                  <Descriptions.Item label="Namespaces">
                    <Space wrap>
                      {(selectedAnalysis.scope_config.namespaces as string[]).map((ns: string) => (
                        <Tag key={ns}>{ns}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                )}
                {selectedAnalysis.scope_config?.exclude_strategy && (
                  <Descriptions.Item label="Exclusion Strategy">
                    <Tag color={selectedAnalysis.scope_config.exclude_strategy === 'aggressive' ? 'red' : 'orange'}>
                      {selectedAnalysis.scope_config.exclude_strategy as string}
                    </Tag>
                  </Descriptions.Item>
                )}
                {selectedAnalysis.scope_config?.exclude_namespaces && (selectedAnalysis.scope_config.exclude_namespaces as string[]).length > 0 && (
                  <Descriptions.Item label="Excluded Namespaces">
                    <Space wrap>
                      {(selectedAnalysis.scope_config.exclude_namespaces as string[]).map((ns: string) => (
                        <Tag key={ns} color="red">{ns}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                )}
                {selectedAnalysis.scope_config?.exclude_pod_patterns && (selectedAnalysis.scope_config.exclude_pod_patterns as string[]).length > 0 && (
                  <Descriptions.Item label="Excluded Pods">
                    <Space wrap>
                      {(selectedAnalysis.scope_config.exclude_pod_patterns as string[]).map((p: string) => (
                        <Tag key={p} color="red">{p}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>
            
            {/* Gadgets / Event Types */}
            <Card size="small" title={<><ThunderboltOutlined /> Event Types (Gadgets)</>}>
              <Space wrap>
                {((selectedAnalysis.gadget_config?.enabled_gadgets as string[]) || []).map((gadget: string) => (
                  <Tag key={gadget} color="geekblue">{gadget.replace(/_/g, ' ')}</Tag>
                ))}
                {(!selectedAnalysis.gadget_config?.enabled_gadgets || 
                  (selectedAnalysis.gadget_config?.enabled_gadgets as string[]).length === 0) && (
                  <Text type="secondary">No gadgets configured</Text>
                )}
              </Space>
            </Card>
            
            {/* Time & Data Configuration */}
            <Card size="small" title={<><ClockCircleOutlined /> Time & Data Configuration</>}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Execution Mode">
                  <Tag color={
                    selectedAnalysis.time_config?.mode === 'continuous' ? 'green' :
                    selectedAnalysis.time_config?.mode === 'timed' ? 'blue' :
                    selectedAnalysis.time_config?.mode === 'time_range' ? 'purple' : 'default'
                  }>
                    {(selectedAnalysis.time_config?.mode as string) || 'continuous'}
                  </Tag>
                </Descriptions.Item>
                {selectedAnalysis.time_config?.duration_seconds && (
                  <Descriptions.Item label="Duration">
                    {Math.round((selectedAnalysis.time_config.duration_seconds as number) / 60)} minutes
                  </Descriptions.Item>
                )}
                <Descriptions.Item label="Data Retention">
                  <Tag color={
                    selectedAnalysis.time_config?.data_retention_policy === 'unlimited' ? 'green' :
                    selectedAnalysis.time_config?.data_retention_policy === 'stop_on_limit' ? 'orange' :
                    selectedAnalysis.time_config?.data_retention_policy === 'rolling_window' ? 'blue' : 'default'
                  }>
                    {(selectedAnalysis.time_config?.data_retention_policy as string) || 'unlimited'}
                  </Tag>
                </Descriptions.Item>
                {selectedAnalysis.time_config?.max_data_size_mb && (
                  <Descriptions.Item label="Max Data Size">
                    <Tag color="purple">
                      <HddOutlined /> {selectedAnalysis.time_config.max_data_size_mb as number} MB
                    </Tag>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>
            
            {/* Schedule Info */}
            {selectedAnalysis.is_scheduled && (
              <Card size="small" title={<><CalendarOutlined /> Schedule</>} extra={
                <Popconfirm
                  title="Remove this schedule?"
                  description="The analysis will no longer run automatically. Any currently running execution will continue."
                  onConfirm={async () => {
                    try {
                      await unscheduleAnalysis(selectedAnalysis.id).unwrap();
                      message.success('Schedule removed');
                    } catch {
                      message.error('Failed to remove schedule');
                    }
                  }}
                  okText="Remove"
                  cancelText="Cancel"
                  okType="danger"
                >
                  <Button type="link" danger size="small">Unschedule</Button>
                </Popconfirm>
              }>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="Cron Expression">
                    <Tag color="gold">{selectedAnalysis.schedule_expression}</Tag>
                  </Descriptions.Item>
                  {selectedAnalysis.schedule_duration_seconds && (
                    <Descriptions.Item label="Per-Run Duration">
                      {Math.round(selectedAnalysis.schedule_duration_seconds / 60)} minutes
                    </Descriptions.Item>
                  )}
                  {selectedAnalysis.next_run_at && (
                    <Descriptions.Item label="Next Run">
                      {new Date(selectedAnalysis.next_run_at).toLocaleString()}
                    </Descriptions.Item>
                  )}
                  {selectedAnalysis.last_run_at && (
                    <Descriptions.Item label="Last Run">
                      {new Date(selectedAnalysis.last_run_at).toLocaleString()}
                    </Descriptions.Item>
                  )}
                  <Descriptions.Item label="Runs Completed">
                    {selectedAnalysis.schedule_run_count || 0}
                    {selectedAnalysis.max_scheduled_runs ? ` / ${selectedAnalysis.max_scheduled_runs}` : ' (unlimited)'}
                  </Descriptions.Item>
                </Descriptions>
              </Card>
            )}
            
            {/* Auto-Stop Info */}
            {selectedAnalysis.output_config?.auto_stopped && (
              <Alert
                message="Auto-Stopped"
                description={
                  <div>
                    <p><strong>Reason:</strong> {selectedAnalysis.output_config.auto_stop_reason as string}</p>
                    <p><strong>Stopped at:</strong> {new Date(selectedAnalysis.output_config.auto_stopped_at as string).toLocaleString()}</p>
                  </div>
                }
                type="info"
                showIcon
                icon={<ClockCircleOutlined />}
              />
            )}
            
            {/* Gadget Errors Warning */}
            {selectedAnalysis.output_config?.has_gadget_warnings && (
              <Alert
                message="Some Gadgets Failed to Start"
                description={
                  <div>
                    <p style={{ marginBottom: 8 }}>
                      The following gadgets could not be initialized. Events from these gadgets are not being collected:
                    </p>
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {(selectedAnalysis.output_config.gadget_errors as Array<{gadget: string; error: string}>)?.map((err, idx) => (
                        <li key={idx} style={{ marginBottom: 4 }}>
                          <strong>{err.gadget}:</strong> {err.error}
                        </li>
                      ))}
                    </ul>
                    <p style={{ marginTop: 12, color: '#8c8c8c', fontSize: 12 }}>
                      This is usually caused by network connectivity issues (cluster cannot reach ghcr.io) 
                      or missing registry configuration. Contact your administrator.
                    </p>
                  </div>
                }
                type="warning"
                showIcon
                icon={<WarningOutlined />}
                style={{ marginBottom: 16 }}
              />
            )}
            
            {/* Quick Actions */}
            <Card size="small" title="Quick Actions">
              <Space wrap>
                {(selectedAnalysis.status === 'draft' || selectedAnalysis.status === 'stopped' || selectedAnalysis.status === 'completed' || selectedAnalysis.status === 'failed') && (
                  <Tooltip title={!canStartAnalysis ? "You don't have permission to start analyses (Viewer role)" : ""}>
                    <Button 
                      type="primary" 
                      icon={<PlayCircleOutlined />}
                      onClick={() => {
                        handleStart(selectedAnalysis.id);
                        closeDetailDrawer();
                      }}
                      disabled={!canStartAnalysis}
                    >
                      Start Analysis
                    </Button>
                  </Tooltip>
                )}
                {selectedAnalysis.status === 'running' && (
                  <Tooltip title={!canStopAnalysis ? "You don't have permission to stop analyses (Viewer role)" : ""}>
                    <Button 
                      type="primary" 
                      danger
                      icon={<PauseCircleOutlined />}
                      onClick={() => {
                        handleStop(selectedAnalysis.id);
                        closeDetailDrawer();
                      }}
                      disabled={!canStopAnalysis}
                    >
                      Stop Analysis
                    </Button>
                  </Tooltip>
                )}
                {(selectedAnalysis.status === 'running' || selectedAnalysis.status === 'stopped' || selectedAnalysis.status === 'completed') && (
                  <Button 
                    icon={<DashboardOutlined />}
                    onClick={() => {
                      closeDetailDrawer();
                      navigate(`/dashboard?analysisId=${selectedAnalysis.id}`);
                    }}
                  >
                    Open Dashboard
                  </Button>
                )}
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
};

export default AnalysisList;

