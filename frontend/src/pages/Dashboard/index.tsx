import React, { useState, Suspense, lazy, useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { 
  Tabs, 
  Select, 
  Space, 
  Typography, 
  Button, 
  Spin,
  Card,
  Badge,
  Tag,
  Tooltip,
  theme,
  Dropdown,
  Modal,
  message,
  DatePicker,
  Checkbox,
} from 'antd';
import type { MenuProps } from 'antd';
import { 
  DashboardOutlined,
  SecurityScanOutlined,
  ApiOutlined,
  SwapOutlined,
  AppstoreOutlined,
  ReloadOutlined,
  ClusterOutlined,
  GlobalOutlined,
  EyeOutlined,
  ThunderboltOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  FilePdfOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  KeyOutlined,
  StarOutlined,
  StarFilled,
  DeleteOutlined,
  HistoryOutlined,
  EditOutlined,
  PlusOutlined,
  MinusOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetClustersQuery } from '../../store/api/clusterApi';
import { useGetAnalysesQuery } from '../../store/api/analysisApi';
import { Analysis } from '../../types';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;
const { Option } = Select;
const { useToken } = theme;

// Lazy load tab components for performance
const OverviewTab = lazy(() => import('./tabs/OverviewTab'));
const OperationsTab = lazy(() => import('./tabs/OperationsTab'));
const SecurityTab = lazy(() => import('./tabs/SecurityTab'));
const NetworkTab = lazy(() => import('./tabs/NetworkTab'));
const ChangeTab = lazy(() => import('./tabs/ChangeTab'));
const WorkloadTab = lazy(() => import('./tabs/WorkloadTab'));

// Loading fallback component
const TabLoader: React.FC = () => {
  const { token } = useToken();
  return (
    <div style={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      minHeight: 400,
      background: token.colorBgLayout,
      borderRadius: 8
    }}>
      <Spin size="large" tip="Loading dashboard..." />
    </div>
  );
};

// Tab definitions
const dashboardTabs = [
  {
    key: 'overview',
    label: 'Overview',
    icon: <EyeOutlined />,
    color: '#2eb8b8', // Ocean teal - genel bakış
    description: 'Executive summary with key insights'
  },
  {
    key: 'operations',
    label: 'Operations',
    icon: <ThunderboltOutlined />,
    color: '#3cc9c4', // Sea foam - operasyonlar
    description: 'Real-time system health and activity'
  },
  {
    key: 'security',
    label: 'Security',
    icon: <SecurityScanOutlined />,
    color: '#e57373', // Soft coral - güvenlik
    description: 'Security posture and risk analysis'
  },
  {
    key: 'network',
    label: 'Network',
    icon: <ApiOutlined />,
    color: '#64b5f6', // Sky blue - ağ
    description: 'Network traffic and connections'
  },
  {
    key: 'changes',
    label: 'Changes',
    icon: <SwapOutlined />,
    color: '#e6b05a', // Beach sand - değişiklikler
    description: 'Infrastructure change tracking'
  },
  {
    key: 'workloads',
    label: 'Workloads',
    icon: <AppstoreOutlined />,
    color: '#8fa8b8', // Soft slate blue - iş yükleri
    description: 'Kubernetes resource health'
  },
];

// Auto-refresh intervals
const AUTO_REFRESH_OPTIONS = [
  { label: 'Off', value: 0 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: '1m', value: 60000 },
  { label: '5m', value: 300000 },
];

// Keyboard shortcuts
const KEYBOARD_SHORTCUTS = [
  { key: 'r', description: 'Refresh data' },
  { key: '1-6', description: 'Switch tabs (Overview, Operations, Security, Network, Changes, Workloads)' },
  { key: '/', description: 'Focus analysis selector' },
  { key: 'Escape', description: 'Close modals' },
];

const { RangePicker } = DatePicker;

const Dashboard: React.FC = () => {
  const { token } = useToken();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  
  // New states for enhanced features
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<number>(0);
  const [lastRefreshTime, setLastRefreshTime] = useState<Date>(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showKeyboardShortcuts, setShowKeyboardShortcuts] = useState(false);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  
  // Favorites state
  interface FavoriteAnalysis {
    id: number;
    name: string;
    cluster_id: number;
    cluster_name: string;
    added_at: string;
  }
  const [favorites, setFavorites] = useState<FavoriteAnalysis[]>(() => {
    const saved = localStorage.getItem('flowfish_favorite_analyses');
    return saved ? JSON.parse(saved) : [];
  });
  const [showFavorites, setShowFavorites] = useState(false);
  
  const autoRefreshTimerRef = useRef<NodeJS.Timeout | null>(null);
  const analysisSelectRef = useRef<any>(null);

  // Fetch clusters (for display in analysis dropdown)
  const { data: clustersData, refetch: refetchClusters, isFetching: isFetchingClusters } = useGetClustersQuery();
  const clusters = clustersData?.clusters || [];

  // Fetch ALL analyses (no cluster filter) - user selects analysis first
  const { data: analyses = [], isLoading: isAnalysesLoading, refetch: refetchAnalyses, isFetching: isFetchingAnalyses } = useGetAnalysesQuery({});

  // Initialize analysis from URL parameter (e.g., /dashboard?analysisId=123)
  useEffect(() => {
    const urlAnalysisId = searchParams.get('analysisId');
    if (urlAnalysisId && !selectedAnalysisId) {
      const parsedId = parseInt(urlAnalysisId, 10);
      if (!isNaN(parsedId)) {
        setSelectedAnalysisId(parsedId);
      }
    }
  }, [searchParams, selectedAnalysisId]);

  // Filter to running/completed analyses
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  const runningAnalysesCount = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running').length 
    : 0;
  
  // Save favorites to localStorage
  useEffect(() => {
    localStorage.setItem('flowfish_favorite_analyses', JSON.stringify(favorites));
  }, [favorites]);
  
  // Check if current analysis is favorite
  const isCurrentFavorite = selectedAnalysisId ? favorites.some(f => f.id === selectedAnalysisId) : false;
  
  // Toggle favorite
  const toggleFavorite = useCallback(() => {
    if (!selectedAnalysisId) return;
    
    const analysis = availableAnalyses.find((a: Analysis) => a.id === selectedAnalysisId);
    if (!analysis) return;
    
    const cluster = clusters.find(c => c.id === analysis.cluster_id);
    
    if (isCurrentFavorite) {
      setFavorites(prev => prev.filter(f => f.id !== selectedAnalysisId));
      message.success('Removed from favorites');
    } else {
      const newFavorite: FavoriteAnalysis = {
        id: analysis.id,
        name: analysis.name,
        cluster_id: analysis.cluster_id,
        cluster_name: cluster?.name || 'Unknown Cluster',
        added_at: new Date().toISOString(),
      };
      setFavorites(prev => [...prev, newFavorite]);
      message.success('Added to favorites');
    }
  }, [selectedAnalysisId, availableAnalyses, clusters, isCurrentFavorite]);
  
  // Remove from favorites
  const removeFavorite = useCallback((id: number) => {
    setFavorites(prev => prev.filter(f => f.id !== id));
    message.success('Removed from favorites');
  }, []);
  
  // Load favorite analysis
  const loadFavorite = useCallback((fav: FavoriteAnalysis) => {
    setSelectedAnalysisId(fav.id);
    setShowFavorites(false);
    message.success(`Loaded: ${fav.name}`);
  }, []);

  // Handle analysis change - set analysis ID and clear cluster (useEffect will set correct cluster)
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    // Always clear clusterId immediately - useEffect will set the correct one
    // This prevents race condition where old clusterId is used with new analysisId
    setSelectedClusterId(undefined);
    
    // Update URL to reflect selected analysis (enables bookmarking and refresh persistence)
    if (analysisId) {
      setSearchParams({ analysisId: String(analysisId) });
    } else {
      setSearchParams({});
    }
  }, [setSearchParams]);

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

  // Refresh all data
  const handleRefresh = useCallback(async (silent = false) => {
    setIsRefreshing(true);
    try {
      await Promise.all([refetchClusters(), refetchAnalyses()]);
      setLastRefreshTime(new Date());
      if (!silent) {
        message.success('Data refreshed');
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [refetchClusters, refetchAnalyses]);

  // Auto-refresh effect
  useEffect(() => {
    if (autoRefreshTimerRef.current) {
      clearInterval(autoRefreshTimerRef.current);
      autoRefreshTimerRef.current = null;
    }
    
    if (autoRefreshInterval > 0) {
      autoRefreshTimerRef.current = setInterval(() => {
        handleRefresh(true); // Silent refresh
      }, autoRefreshInterval);
    }
    
    return () => {
      if (autoRefreshTimerRef.current) {
        clearInterval(autoRefreshTimerRef.current);
      }
    };
  }, [autoRefreshInterval, handleRefresh]);

  // Keyboard shortcuts handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      
      switch (e.key.toLowerCase()) {
        case 'r':
          if (!e.metaKey && !e.ctrlKey) {
            e.preventDefault();
            handleRefresh();
          }
          break;
        case '1':
          setActiveTab('overview');
          break;
        case '2':
          setActiveTab('operations');
          break;
        case '3':
          setActiveTab('security');
          break;
        case '4':
          setActiveTab('network');
          break;
        case '5':
          setActiveTab('changes');
          break;
        case '6':
          setActiveTab('workloads');
          break;
        case '/':
          e.preventDefault();
          analysisSelectRef.current?.focus();
          break;
        case '?':
          setShowKeyboardShortcuts(true);
          break;
        case 'escape':
          setShowKeyboardShortcuts(false);
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleRefresh]);

  // Data freshness indicator
  const getDataFreshness = useCallback(() => {
    const now = new Date();
    const diff = now.getTime() - lastRefreshTime.getTime();
    const seconds = Math.floor(diff / 1000);
    
    if (seconds < 30) {
      return { status: 'fresh', color: '#4caf50', label: 'Just now' };
    } else if (seconds < 120) {
      return { status: 'recent', color: '#4caf50', label: `${seconds}s ago` };
    } else if (seconds < 300) {
      return { status: 'stale', color: '#d4a844', label: dayjs(lastRefreshTime).fromNow() };
    } else {
      return { status: 'old', color: '#e05252', label: dayjs(lastRefreshTime).fromNow() };
    }
  }, [lastRefreshTime]);

  // Export dashboard as PDF (placeholder - would need backend implementation)
  const handleExportPDF = useCallback(() => {
    message.info('PDF export will capture current dashboard view. This feature requires backend support.');
    // In a real implementation, this would call a backend endpoint to generate PDF
  }, []);

  // Auto-refresh dropdown menu
  const autoRefreshMenu: MenuProps = {
    items: AUTO_REFRESH_OPTIONS.map(opt => ({
      key: opt.value.toString(),
      label: (
        <Space>
          {autoRefreshInterval === opt.value && <CheckCircleOutlined style={{ color: '#4caf50' }} />}
          {opt.label}
        </Space>
      ),
      onClick: () => setAutoRefreshInterval(opt.value),
    })),
  };

  // Render tab content
  const renderTabContent = () => {
    const commonProps = {
      clusterId: selectedClusterId,
      analysisId: selectedAnalysisId,
    };

    switch (activeTab) {
      case 'overview':
        return <OverviewTab {...commonProps} />;
      case 'operations':
        return <OperationsTab {...commonProps} />;
      case 'security':
        return <SecurityTab {...commonProps} />;
      case 'network':
        return <NetworkTab {...commonProps} />;
      case 'changes':
        return <ChangeTab {...commonProps} />;
      case 'workloads':
        return <WorkloadTab {...commonProps} />;
      default:
        return <OverviewTab {...commonProps} />;
    }
  };

  return (
    <div style={{ padding: '24px', minHeight: 'calc(100vh - 64px)', background: token.colorBgLayout }}>
      {/* Header */}
      <div style={{ 
        display: 'flex', 
        flexWrap: 'wrap',
        justifyContent: 'space-between', 
        alignItems: 'flex-start',
        marginBottom: 16,
        gap: 16
      }}>
        <div style={{ minWidth: 200, flexShrink: 0 }}>
          <Title level={2} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 12, whiteSpace: 'nowrap' }}>
            <DashboardOutlined style={{ color: token.colorPrimary }} />
            Dashboard
          </Title>
          <Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
            Comprehensive monitoring and analytics for your Kubernetes infrastructure
          </Text>
        </div>

        {/* Global Filters */}
        <Space size="middle" align="start" wrap>
          {/* Analysis Selector */}
          <div>
            <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
              Analysis {runningAnalysesCount > 0 && <Badge count={runningAnalysesCount} size="small" style={{ marginLeft: 4 }} />}
            </Text>
            <Select
              ref={analysisSelectRef}
              placeholder="Select analysis (press /)"
              style={{ width: 280 }}
              value={selectedAnalysisId}
              onChange={handleAnalysisChange}
              loading={isAnalysesLoading}
              allowClear
              showSearch
              optionFilterProp="children"
              filterOption={(input, option) => {
                const analysis = availableAnalyses.find((a: Analysis) => a.id === option?.value);
                return analysis?.name?.toLowerCase().includes(input.toLowerCase()) || false;
              }}
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
                          <GlobalOutlined /> {clusterCount} Clusters
                        </Tag>
                      ) : (
                        <Text type="secondary" style={{ fontSize: 11 }}>({clusterName})</Text>
                      )}
                    </Space>
                  </Option>
                );
              })}
            </Select>
            {/* Favorite Toggle & View */}
            <Space style={{ marginTop: 4 }}>
              <Tooltip title={isCurrentFavorite ? 'Remove from favorites' : 'Add to favorites'}>
                <Button
                  type="text"
                  size="small"
                  icon={isCurrentFavorite ? <StarFilled style={{ color: '#c9a55a' }} /> : <StarOutlined />}
                  onClick={toggleFavorite}
                  disabled={!selectedAnalysisId}
                />
              </Tooltip>
              <Tooltip title="View favorites">
                <Button
                  type="text"
                  size="small"
                  icon={<HistoryOutlined />}
                  onClick={() => setShowFavorites(true)}
                >
                  {favorites.length > 0 && (
                    <Badge count={favorites.length} size="small" style={{ marginLeft: 4, backgroundColor: '#c9a55a' }} />
                  )}
                </Button>
              </Tooltip>
            </Space>
          </div>

          {/* Time Range Picker */}
          <div>
            <Text type="secondary" style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
              <CalendarOutlined style={{ marginRight: 4 }} />
              Time Range
            </Text>
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
              ]}
              placeholder={['Start Time', 'End Time']}
            />
          </div>

          {/* Data Freshness & Actions */}
          <div style={{ paddingTop: 22 }}>
            <Space>
              {/* Data Freshness Indicator */}
              <Tooltip title={`Last updated: ${lastRefreshTime.toLocaleTimeString()}`}>
                <Tag 
                  color={getDataFreshness().color}
                  style={{ cursor: 'default' }}
                >
                  <ClockCircleOutlined style={{ marginRight: 4 }} />
                  {getDataFreshness().label}
                </Tag>
              </Tooltip>

              {/* Auto Refresh Dropdown */}
              <Dropdown menu={autoRefreshMenu} trigger={['click']}>
                <Tooltip title="Auto-refresh interval">
                  <Button 
                    icon={autoRefreshInterval > 0 ? <SyncOutlined spin style={{ color: '#4caf50' }} /> : <SyncOutlined />}
                  >
                    {autoRefreshInterval > 0 ? `${autoRefreshInterval / 1000}s` : 'Auto'}
                  </Button>
                </Tooltip>
              </Dropdown>

              {/* Manual Refresh */}
              <Tooltip title="Refresh data (R)">
                <Button 
                  icon={<ReloadOutlined spin={isRefreshing} />} 
                  onClick={() => handleRefresh()}
                  loading={isRefreshing || isFetchingClusters || isFetchingAnalyses}
                >
                  Refresh
                </Button>
              </Tooltip>

              {/* PDF Export */}
              <Tooltip title="Export dashboard as PDF">
                <Button 
                  icon={<FilePdfOutlined />} 
                  onClick={handleExportPDF}
                  disabled={!selectedAnalysisId}
                />
              </Tooltip>

              {/* Keyboard Shortcuts */}
              <Tooltip title="Keyboard shortcuts (?)">
                <Button 
                  icon={<KeyOutlined />} 
                  onClick={() => setShowKeyboardShortcuts(true)}
                />
              </Tooltip>
            </Space>
          </div>
        </Space>
      </div>

      {/* Dashboard Tabs */}
      <Card 
        bordered={false} 
        bodyStyle={{ padding: 0 }}
        style={{ 
          borderRadius: 8,
          boxShadow: '0 1px 2px rgba(0,0,0,0.03)'
        }}
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          type="card"
          size="large"
          tabBarStyle={{ 
            marginBottom: 0, 
            padding: '12px 16px 0',
            background: token.colorBgContainer,
            borderRadius: '8px 8px 0 0'
          }}
          items={dashboardTabs.map(tab => ({
            key: tab.key,
            label: (
              <Space>
                <span style={{ color: activeTab === tab.key ? tab.color : undefined }}>
                  {tab.icon}
                </span>
                <span>{tab.label}</span>
              </Space>
            ),
          }))}
        />
        
        {/* Tab Content */}
        <div style={{ 
          padding: 24, 
          background: token.colorBgContainer,
          borderRadius: '0 0 8px 8px',
          minHeight: 500
        }}>
          {!selectedAnalysisId ? (
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column',
              justifyContent: 'center', 
              alignItems: 'center', 
              minHeight: 400,
              color: token.colorTextSecondary
            }}>
              <DashboardOutlined style={{ fontSize: 64, marginBottom: 16, opacity: 0.3 }} />
              <Title level={4} style={{ color: token.colorTextSecondary, margin: 0 }}>
                Select an Analysis
              </Title>
              <Text type="secondary">
                Choose an analysis from the dropdown above to view dashboard metrics
              </Text>
            </div>
          ) : (
            <Suspense fallback={<TabLoader />}>
              {renderTabContent()}
            </Suspense>
          )}
        </div>
      </Card>

      {/* Keyboard Shortcuts Modal */}
      <KeyboardShortcutsModal 
        visible={showKeyboardShortcuts} 
        onClose={() => setShowKeyboardShortcuts(false)} 
      />
      
      {/* Favorites Modal */}
      <Modal
        title={
          <Space>
            <StarFilled style={{ color: '#c9a55a' }} />
            <span>Favorite Analyses</span>
          </Space>
        }
        open={showFavorites}
        onCancel={() => setShowFavorites(false)}
        footer={null}
        width={500}
      >
        {favorites.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: token.colorTextSecondary }}>
            <StarOutlined style={{ fontSize: 48, opacity: 0.3, marginBottom: 16 }} />
            <div>No favorite analyses yet</div>
            <Text type="secondary">
              Click the star icon next to an analysis to add it to favorites
            </Text>
          </div>
        ) : (
          <div style={{ maxHeight: 400, overflow: 'auto' }}>
            {favorites.map((fav) => {
              const isActive = selectedAnalysisId === fav.id;
              const analysisExists = availableAnalyses.some((a: Analysis) => a.id === fav.id);
              
              return (
                <div
                  key={fav.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '12px 16px',
                    marginBottom: 8,
                    background: isActive ? `${token.colorPrimary}10` : token.colorBgContainer,
                    border: `1px solid ${isActive ? token.colorPrimary : token.colorBorderSecondary}`,
                    borderRadius: 8,
                    cursor: analysisExists ? 'pointer' : 'not-allowed',
                    opacity: analysisExists ? 1 : 0.5,
                    transition: 'all 0.2s',
                  }}
                  onClick={() => analysisExists && loadFavorite(fav)}
                >
                  <div>
                    <div style={{ fontWeight: 500, marginBottom: 4 }}>
                      <StarFilled style={{ color: '#c9a55a', marginRight: 8 }} />
                      {fav.name}
                      {isActive && <Tag color="blue" style={{ marginLeft: 8 }}>Active</Tag>}
                      {!analysisExists && <Tag color="red" style={{ marginLeft: 8 }}>Not Found</Tag>}
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <ClusterOutlined style={{ marginRight: 4 }} />
                      {fav.cluster_name}
                      <span style={{ margin: '0 8px' }}>•</span>
                      Added {dayjs(fav.added_at).fromNow()}
                    </Text>
                  </div>
                  <Tooltip title="Remove from favorites">
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        removeFavorite(fav.id);
                      }}
                    />
                  </Tooltip>
                </div>
              );
            })}
          </div>
        )}
      </Modal>
    </div>
  );
};

// Keyboard Shortcuts Modal
const KeyboardShortcutsModal: React.FC<{ visible: boolean; onClose: () => void }> = ({ visible, onClose }) => {
  const { token } = useToken();
  
  return (
    <Modal
      title={
        <Space>
          <KeyOutlined style={{ color: token.colorPrimary }} />
          <span>Keyboard Shortcuts</span>
        </Space>
      }
      open={visible}
      onCancel={onClose}
      footer={[
        <Button key="close" type="primary" onClick={onClose}>
          Close
        </Button>
      ]}
      width={400}
    >
      <div style={{ padding: '8px 0' }}>
        {KEYBOARD_SHORTCUTS.map((shortcut, index) => (
          <div
            key={index}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '8px 0',
              borderBottom: index < KEYBOARD_SHORTCUTS.length - 1 ? `1px solid ${token.colorBorderSecondary}` : 'none',
            }}
          >
            <Text>{shortcut.description}</Text>
            <Tag style={{ fontFamily: 'monospace', fontWeight: 600 }}>
              {shortcut.key}
            </Tag>
          </div>
        ))}
      </div>
    </Modal>
  );
};

export default Dashboard;

