import React, { useState, useMemo } from 'react';
import { Card, Space, Typography, Tooltip, Empty, theme, Tag, Badge, Input, Row, Col, Progress, Statistic } from 'antd';
import { 
  CheckCircleOutlined, 
  CloseCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  SearchOutlined,
  ContainerOutlined,
  ReloadOutlined,
  CloudServerOutlined,
  AppstoreOutlined
} from '@ant-design/icons';

const { Text } = Typography;
const { useToken } = theme;

interface PodHealth {
  name: string;
  namespace: string;
  status: 'Running' | 'Pending' | 'Failed' | 'Succeeded' | 'Unknown' | 'Terminating';
  restarts?: number;
  age?: string;
  cpu?: number;
  memory?: number;
  oomKilled?: boolean;
  workload_type?: string;
}

interface PodHealthGridProps {
  pods: PodHealth[];
  loading?: boolean;
  title?: string;
  maxPods?: number;
}

const statusConfig = {
  Running: { color: '#4caf50', bgColor: 'rgba(82, 196, 26, 0.15)', label: 'Running', icon: <CheckCircleOutlined /> },
  Pending: { color: '#c9a55a', bgColor: 'rgba(250, 173, 20, 0.15)', label: 'Pending', icon: <ClockCircleOutlined /> },
  Failed: { color: '#e05252', bgColor: 'rgba(245, 34, 45, 0.15)', label: 'Failed', icon: <CloseCircleOutlined /> },
  Succeeded: { color: '#0891b2', bgColor: 'rgba(24, 144, 255, 0.15)', label: 'Succeeded', icon: <CheckCircleOutlined /> },
  Unknown: { color: '#8c8c8c', bgColor: 'rgba(140, 140, 140, 0.15)', label: 'Unknown', icon: <ExclamationCircleOutlined /> },
  Terminating: { color: '#d4a844', bgColor: 'rgba(250, 140, 22, 0.15)', label: 'Terminating', icon: <ClockCircleOutlined /> },
};

const PodHealthGrid: React.FC<PodHealthGridProps> = ({
  pods,
  loading = false,
  title = 'Pod Health Overview',
  maxPods = 100,
}) => {
  const { token } = useToken();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string | null>(null);
  const [selectedNamespace, setSelectedNamespace] = useState<string | null>(null);

  // Status counts
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {
      Running: 0,
      Pending: 0,
      Failed: 0,
      Succeeded: 0,
      Unknown: 0,
      Terminating: 0,
    };
    pods.forEach(pod => {
      const status = pod.status || 'Unknown';
      counts[status] = (counts[status] || 0) + 1;
    });
    return counts;
  }, [pods]);

  // Namespace counts
  const namespaceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    pods.forEach(pod => {
      const ns = pod.namespace || 'default';
      counts[ns] = (counts[ns] || 0) + 1;
    });
    return counts;
  }, [pods]);

  // Get sorted namespaces
  const sortedNamespaces = useMemo(() => {
    return Object.entries(namespaceCounts)
      .sort(([, a], [, b]) => b - a)
      .map(([ns]) => ns);
  }, [namespaceCounts]);

  // Filter pods
  const filteredPods = useMemo(() => {
    return pods
      .filter(pod => {
        const matchesSearch = !searchTerm || 
          pod.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (pod.namespace || '').toLowerCase().includes(searchTerm.toLowerCase());
        const matchesStatus = !selectedStatus || pod.status === selectedStatus;
        const matchesNamespace = !selectedNamespace || pod.namespace === selectedNamespace;
        return matchesSearch && matchesStatus && matchesNamespace;
      })
      .slice(0, maxPods);
  }, [pods, searchTerm, selectedStatus, selectedNamespace, maxPods]);

  // Health metrics
  const healthMetrics = useMemo(() => {
    const total = pods.length;
    if (total === 0) return { percentage: 100, healthy: 0, unhealthy: 0, pending: 0 };
    
    const healthy = statusCounts.Running + statusCounts.Succeeded;
    const unhealthy = statusCounts.Failed;
    const pending = statusCounts.Pending + statusCounts.Terminating;
    
    return {
      percentage: Math.round((healthy / total) * 100),
      healthy,
      unhealthy,
      pending,
    };
  }, [pods.length, statusCounts]);

  // Group filtered pods by namespace
  const groupedPods = useMemo(() => {
    const groups: Record<string, PodHealth[]> = {};
    filteredPods.forEach(pod => {
      const ns = pod.namespace || 'default';
      if (!groups[ns]) groups[ns] = [];
      groups[ns].push(pod);
    });
    return groups;
  }, [filteredPods]);

  if (pods.length === 0) {
    return (
      <Card 
        title={
          <Space>
            <CloudServerOutlined style={{ color: token.colorPrimary }} />
            <span>{title}</span>
          </Space>
        } 
        bordered={false}
      >
        <Empty 
          description="No workloads found" 
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <CloudServerOutlined style={{ color: token.colorPrimary }} />
          <span>{title}</span>
          <Badge 
            count={pods.length} 
            style={{ backgroundColor: token.colorPrimary }} 
            overflowCount={999}
          />
        </Space>
      }
      bordered={false}
    >
      {/* Health Summary Row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        {/* Health Score */}
        <Col xs={24} sm={8} md={6}>
          <div style={{
            textAlign: 'center',
            padding: '16px',
            background: token.colorBgLayout,
            borderRadius: 12,
          }}>
            <Progress
              type="dashboard"
              percent={healthMetrics.percentage}
              size={100}
              strokeColor={
                healthMetrics.percentage >= 80 ? '#4caf50' : 
                healthMetrics.percentage >= 50 ? '#c9a55a' : '#e05252'
              }
              format={(p) => (
                <div>
                  <div style={{ fontSize: 24, fontWeight: 700, color: token.colorText }}>{p}%</div>
                  <div style={{ fontSize: 11, color: token.colorTextSecondary }}>Healthy</div>
                </div>
              )}
            />
          </div>
        </Col>

        {/* Status Cards */}
        <Col xs={24} sm={16} md={18}>
          <Row gutter={[12, 12]}>
            {Object.entries(statusConfig).map(([status, config]) => {
              const count = statusCounts[status] || 0;
              const isSelected = selectedStatus === status;
              
              return (
                <Col xs={12} sm={8} md={4} key={status}>
                  <div
                    onClick={() => setSelectedStatus(isSelected ? null : status)}
                    style={{
                      padding: '12px 8px',
                      background: isSelected ? config.bgColor : token.colorBgLayout,
                      borderRadius: 8,
                      border: `2px solid ${isSelected ? config.color : 'transparent'}`,
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                      textAlign: 'center',
                    }}
                  >
                    <div style={{ 
                      color: config.color, 
                      fontSize: 20,
                      marginBottom: 4,
                    }}>
                      {config.icon}
                    </div>
                    <div style={{ 
                      fontSize: 20, 
                      fontWeight: 700, 
                      color: count > 0 ? config.color : token.colorTextSecondary,
                    }}>
                      {count}
                    </div>
                    <div style={{ 
                      fontSize: 10, 
                      color: token.colorTextSecondary,
                      marginTop: 2,
                    }}>
                      {config.label}
                    </div>
                  </div>
                </Col>
              );
            })}
          </Row>
        </Col>
      </Row>

      {/* Namespace Filter Pills */}
      {sortedNamespaces.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 11, marginRight: 8 }}>Namespaces:</Text>
          <Space size={[4, 4]} wrap>
            <Tag
              color={!selectedNamespace ? token.colorPrimary : undefined}
              style={{ cursor: 'pointer', margin: 0 }}
              onClick={() => setSelectedNamespace(null)}
            >
              All ({pods.length})
            </Tag>
            {sortedNamespaces.slice(0, 8).map(ns => (
              <Tag
                key={ns}
                color={selectedNamespace === ns ? token.colorPrimary : undefined}
                style={{ cursor: 'pointer', margin: 0 }}
                onClick={() => setSelectedNamespace(selectedNamespace === ns ? null : ns)}
              >
                {ns} ({namespaceCounts[ns]})
              </Tag>
            ))}
            {sortedNamespaces.length > 8 && (
              <Tag style={{ margin: 0 }}>+{sortedNamespaces.length - 8} more</Tag>
            )}
          </Space>
        </div>
      )}

      {/* Search */}
      <Input
        placeholder="Search workloads..."
        prefix={<SearchOutlined style={{ color: token.colorTextSecondary }} />}
        size="small"
        style={{ marginBottom: 16 }}
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        allowClear
      />

      {/* Workload Grid */}
      <div style={{ 
        maxHeight: 300, 
        overflow: 'auto',
        background: token.colorBgLayout,
        borderRadius: 8,
        padding: 16,
      }}>
        {Object.keys(groupedPods).length === 0 ? (
          <Empty 
            description="No workloads match your filters" 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          Object.entries(groupedPods).map(([namespace, nsPods]) => (
            <div key={namespace} style={{ marginBottom: 20 }}>
              {/* Namespace Header */}
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                marginBottom: 10,
                gap: 8,
              }}>
                <AppstoreOutlined style={{ color: token.colorPrimary, fontSize: 14 }} />
                <Text strong style={{ color: token.colorPrimary, fontSize: 13 }}>
                  {namespace}
                </Text>
                <Badge 
                  count={nsPods.length} 
                  style={{ backgroundColor: token.colorPrimary }}
                  size="small"
                />
              </div>

              {/* Pods Grid */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
                gap: 8,
              }}>
                {nsPods.map((pod, index) => {
                  const config = statusConfig[pod.status] || statusConfig.Unknown;
                  const hasIssue = (pod.restarts && pod.restarts > 3) || pod.oomKilled;
                  
                  return (
                    <Tooltip
                      key={`${namespace}-${pod.name}-${index}`}
                      title={
                        <div>
                          <div style={{ fontWeight: 600, marginBottom: 4 }}>{pod.name}</div>
                          <Space size={4} wrap>
                            <Tag color={config.color} style={{ margin: 0, fontSize: 10 }}>{pod.status}</Tag>
                            {pod.age && <Tag style={{ margin: 0, fontSize: 10 }}>{pod.age}</Tag>}
                            {pod.workload_type && (
                              <Tag style={{ margin: 0, fontSize: 10 }}>{pod.workload_type}</Tag>
                            )}
                          </Space>
                          {pod.restarts !== undefined && pod.restarts > 0 && (
                            <div style={{ marginTop: 6, color: pod.restarts > 3 ? '#e05252' : '#c9a55a', fontSize: 11 }}>
                              <ReloadOutlined /> {pod.restarts} restarts
                            </div>
                          )}
                          {pod.oomKilled && (
                            <div style={{ marginTop: 4, color: '#e05252', fontSize: 11 }}>⚠️ OOM Killed</div>
                          )}
                        </div>
                      }
                    >
                      <div
                        style={{
                          padding: '8px 10px',
                          background: token.colorBgContainer,
                          borderRadius: 6,
                          borderLeft: `3px solid ${config.color}`,
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                          position: 'relative',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = `0 4px 12px ${config.color}30`;
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = 'none';
                        }}
                      >
                        {/* Issue Indicator */}
                        {hasIssue && (
                          <div style={{
                            position: 'absolute',
                            top: 4,
                            right: 4,
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            background: '#e05252',
                            animation: 'pulse 1.5s infinite',
                          }} />
                        )}
                        
                        {/* Pod Info */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ color: config.color, fontSize: 14 }}>
                            {config.icon}
                          </span>
                          <Text 
                            ellipsis 
                            style={{ 
                              fontSize: 11, 
                              fontWeight: 500,
                              flex: 1,
                              color: token.colorText,
                            }}
                          >
                            {pod.name.length > 18 ? pod.name.substring(0, 18) + '...' : pod.name}
                          </Text>
                        </div>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Legend */}
      <div style={{ 
        marginTop: 16, 
        paddingTop: 12,
        borderTop: `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        justifyContent: 'center',
        flexWrap: 'wrap',
        gap: 16,
      }}>
        {Object.entries(statusConfig).map(([status, config]) => (
          <Space key={status} size={4}>
            <div style={{
              width: 12,
              height: 12,
              borderRadius: 3,
              background: config.bgColor,
              borderLeft: `3px solid ${config.color}`,
            }} />
            <Text type="secondary" style={{ fontSize: 11 }}>{config.label}</Text>
          </Space>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </Card>
  );
};

export default PodHealthGrid;
