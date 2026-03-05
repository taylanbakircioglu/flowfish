import React from 'react';
import { 
  Card, 
  Tabs, 
  Table, 
  Tag, 
  Space, 
  Statistic, 
  Row, 
  Col, 
  Typography,
  Progress,
  Empty,
  Tooltip
} from 'antd';
import {
  ApiOutlined,
  GlobalOutlined,
  SafetyCertificateOutlined,
  FileOutlined,
  ThunderboltOutlined,
  CloudServerOutlined,
  LockOutlined,
  DatabaseOutlined,
  WarningOutlined,
  DashboardOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { EventType } from '../../store/api/eventsApi';

const { Text, Title } = Typography;

// Event type configuration
export const eventTypeConfig: Record<EventType, { 
  label: string; 
  color: string; 
  icon: React.ReactNode;
  description: string;
}> = {
  network_flow: { 
    label: 'Network Flow', 
    color: '#0891b2', 
    icon: <ApiOutlined />,
    description: 'TCP/UDP network communications between workloads'
  },
  dns_query: { 
    label: 'DNS Query', 
    color: '#4d9f7c', 
    icon: <GlobalOutlined />,
    description: 'Domain name resolution queries'
  },
  tcp_throughput: { 
    label: 'TCP Throughput', 
    color: '#13c2c2', 
    icon: <DashboardOutlined />,
    description: 'TCP connection throughput with bytes sent/received'
  },
  tcp_retransmit: { 
    label: 'TCP Retransmit', 
    color: '#fa8c16', 
    icon: <WarningOutlined />,
    description: 'TCP retransmission events indicating network errors'
  },
  process_event: { 
    label: 'Process', 
    color: '#7c8eb5', 
    icon: <ThunderboltOutlined />,
    description: 'Process execution, exit, and signals'
  },
  file_event: { 
    label: 'File I/O', 
    color: '#a67c9e', 
    icon: <FileOutlined />,
    description: 'File read/write operations'
  },
  security_event: { 
    label: 'Security', 
    color: '#c75450', 
    icon: <SafetyCertificateOutlined />,
    description: 'Linux capability and seccomp events'
  },
  oom_event: { 
    label: 'OOM Kill', 
    color: '#f76e6e', 
    icon: <WarningOutlined />,
    description: 'Out of memory kills'
  },
  bind_event: { 
    label: 'Socket Bind', 
    color: '#22a6a6', 
    icon: <CloudServerOutlined />,
    description: 'Services listening on ports'
  },
  sni_event: { 
    label: 'TLS/SNI', 
    color: '#69b1ff', 
    icon: <LockOutlined />,
    description: 'TLS/SSL connections with SNI hostname'
  },
  mount_event: { 
    label: 'Mount', 
    color: '#8fa855', 
    icon: <DatabaseOutlined />,
    description: 'Filesystem mount operations'
  },
};

interface EventStatsProps {
  stats: {
    total_events: number;
    event_counts: Record<EventType, number>;
    top_namespaces?: { namespace: string; count: number }[];
    top_pods?: { pod: string; namespace: string; count: number }[];
  } | undefined;
  isLoading?: boolean;
  selectedEventType?: string | null;
  onEventTypeClick?: (eventType: string | null) => void;
}

export const EventStatsPanel: React.FC<EventStatsProps> = ({ stats, isLoading, selectedEventType, onEventTypeClick }) => {
  if (isLoading) {
    return <div style={{ textAlign: 'center', padding: 8 }}><Text type="secondary">Loading...</Text></div>;
  }

  if (!stats) {
    return <Empty description="No event data" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />;
  }

  const eventTypes = Object.entries(stats.event_counts || {})
    .filter(([_, count]) => count > 0)
    .sort(([_, a], [__, b]) => b - a);

  const totalEvents = stats.total_events || 0;

  return (
    <Tabs
      size="small"
      tabBarStyle={{ marginBottom: 4 }}
      items={[
        {
          key: 'by-type',
          label: 'Type',
          children: (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {eventTypes.map(([type, count]) => {
                const config = eventTypeConfig[type as EventType];
                const percentage = totalEvents > 0 ? (count / totalEvents) * 100 : 0;
                const isSelected = selectedEventType === type;
                
                return (
                  <Tooltip 
                    key={type} 
                    title={onEventTypeClick ? (isSelected ? 'Click to clear filter' : `Click to highlight nodes with ${config?.label || type} events`) : undefined}
                    placement="right"
                  >
                    <div 
                      onClick={() => onEventTypeClick?.(isSelected ? null : type)}
                      style={{ 
                        cursor: onEventTypeClick ? 'pointer' : 'default',
                        padding: '4px 6px',
                        marginLeft: -6,
                        marginRight: -6,
                        borderRadius: 4,
                        background: isSelected ? `${config?.color}15` : 'transparent',
                        border: isSelected ? `1px solid ${config?.color}40` : '1px solid transparent',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                        <Space size={4}>
                          <span style={{ color: config?.color, fontSize: 12 }}>{config?.icon}</span>
                          <Text style={{ fontSize: 11, fontWeight: isSelected ? 600 : 400 }}>{config?.label || type}</Text>
                        </Space>
                        <Text strong style={{ fontSize: 11 }}>{count.toLocaleString()}</Text>
                      </div>
                      <Progress 
                        percent={percentage} 
                        showInfo={false}
                        strokeColor={config?.color}
                        size="small"
                        style={{ marginBottom: 0 }}
                      />
                    </div>
                  </Tooltip>
                );
              })}
              {eventTypes.length === 0 && (
                <Empty description="No events yet" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
              )}
            </div>
          ),
        },
        {
          key: 'by-namespace',
          label: 'NS',
          children: (
            <Table
              size="small"
              pagination={false}
              dataSource={stats.top_namespaces?.slice(0, 8) || []}
              columns={[
                { 
                  title: 'Namespace', 
                  dataIndex: 'namespace', 
                  key: 'namespace',
                  ellipsis: true,
                  render: (ns: string) => (
                    <Tooltip title={ns}>
                      <Text style={{ fontSize: 11 }}>{ns}</Text>
                    </Tooltip>
                  )
                },
                { 
                  title: 'Events', 
                  dataIndex: 'count', 
                  key: 'count',
                  width: 70,
                  render: (count: number) => <Text style={{ fontSize: 11 }}>{count.toLocaleString()}</Text>
                },
              ]}
              rowKey="namespace"
              style={{ fontSize: 11 }}
            />
          ),
        },
        {
          key: 'by-pod',
          label: 'Pod',
          children: (
            <Table
              size="small"
              pagination={false}
              dataSource={stats.top_pods?.slice(0, 8) || []}
              columns={[
                { 
                  title: 'Pod', 
                  dataIndex: 'pod', 
                  key: 'pod',
                  ellipsis: true,
                  render: (pod: string, record: any) => (
                    <Tooltip title={`${record.namespace}/${pod}`}>
                      <Text ellipsis style={{ fontSize: 11, maxWidth: 120 }}>{pod}</Text>
                    </Tooltip>
                  )
                },
                { 
                  title: 'Events', 
                  dataIndex: 'count', 
                  key: 'count',
                  width: 70,
                  render: (count: number) => <Text style={{ fontSize: 11 }}>{count.toLocaleString()}</Text>
                },
              ]}
              rowKey={(record) => `${record.namespace}/${record.pod}`}
              style={{ fontSize: 11 }}
            />
          ),
        },
      ]}
    />
  );
};

// Event type legend component with optional hover and click callbacks
export const EventTypeLegend: React.FC<{ 
  compact?: boolean;
  onHover?: (eventType: string | null) => void;
  onClick?: (eventType: string) => void;
  selectedTypes?: string[];
}> = ({ compact, onHover, onClick, selectedTypes = [] }) => {
  const types = Object.entries(eventTypeConfig);
  const hasInteraction = onHover || onClick;
  
  if (compact) {
    return (
      <Space wrap size={[4, 4]}>
        {types.map(([type, config]) => {
          const isSelected = selectedTypes.length === 0 || selectedTypes.includes(type);
          return (
            <Tooltip key={type} title={config.description}>
              <Tag 
                color={isSelected ? config.color : 'default'} 
                icon={config.icon}
                style={{ 
                  cursor: hasInteraction ? 'pointer' : 'default',
                  opacity: selectedTypes.length > 0 && !isSelected ? 0.5 : 1,
                  transition: 'all 0.3s ease',
                }}
                onMouseEnter={() => onHover?.(type)}
                onMouseLeave={() => onHover?.(null)}
                onClick={() => onClick?.(type)}
              >
                {config.label}
              </Tag>
            </Tooltip>
          );
        })}
      </Space>
    );
  }

  return (
    <Card title="Event Types" size="small">
      <Row gutter={[8, 8]}>
        {types.map(([type, config]) => (
          <Col span={12} key={type}>
            <Space>
              <span style={{ color: config.color }}>{config.icon}</span>
              <div>
                <Text strong>{config.label}</Text>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>{config.description}</Text>
              </div>
            </Space>
          </Col>
        ))}
      </Row>
    </Card>
  );
};

// Format bytes helper
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
};

// Event details component for drawer
interface EventDetailsProps {
  event: any;
  eventType: EventType;
}

export const EventDetails: React.FC<EventDetailsProps> = ({ event, eventType }) => {
  const config = eventTypeConfig[eventType];
  
  const renderEventSpecificDetails = () => {
    switch (eventType) {
      case 'network_flow':
        return (
          <>
            <Statistic title="Source" value={`${event.src_ip}:${event.src_port}`} />
            <Statistic title="Destination" value={`${event.dst_ip}:${event.dst_port}`} />
            <Statistic title="Protocol" value={event.protocol} />
            <Statistic title="Bytes Sent" value={formatBytes(event.bytes_sent || 0)} />
            <Statistic title="Bytes Received" value={formatBytes(event.bytes_received || 0)} />
            <Statistic title="Latency" value={`${event.latency_ms?.toFixed(2) || 0} ms`} />
          </>
        );
      
      case 'dns_query':
        return (
          <>
            <Statistic title="Query Name" value={event.query_name} />
            <Statistic title="Query Type" value={event.query_type} />
            <Statistic title="Response Code" value={event.response_code} />
            <Statistic title="DNS Server" value={event.dns_server_ip} />
            <Statistic title="Latency" value={`${event.latency_ms?.toFixed(2) || 0} ms`} />
          </>
        );
      
      case 'sni_event':
        return (
          <>
            <Statistic title="SNI Hostname" value={event.sni_name} />
            <Statistic title="Destination" value={`${event.dst_ip}:${event.dst_port}`} />
            <Statistic title="TLS Version" value={event.tls_version || 'Unknown'} />
            <Statistic title="Cipher Suite" value={event.cipher_suite || 'Unknown'} />
          </>
        );
      
      case 'bind_event':
        return (
          <>
            <Statistic title="Bind Address" value={`${event.bind_addr}:${event.bind_port}`} />
            <Statistic title="Protocol" value={event.protocol} />
            <Statistic title="Interface" value={event.interface || 'all'} />
            <Statistic title="Process" value={`${event.comm} (PID: ${event.pid})`} />
          </>
        );
      
      case 'process_event':
        return (
          <>
            <Statistic title="Command" value={event.comm} />
            <Statistic title="Executable" value={event.exe} />
            <Statistic title="PID / PPID" value={`${event.pid} / ${event.ppid}`} />
            <Statistic title="Event Type" value={event.event_subtype} />
            {event.exit_code !== undefined && (
              <Statistic title="Exit Code" value={event.exit_code} />
            )}
          </>
        );
      
      case 'file_event':
        return (
          <>
            <Statistic title="Operation" value={event.operation} />
            <Statistic title="File Path" value={event.file_path} />
            <Statistic title="Bytes" value={formatBytes(event.bytes || 0)} />
            <Statistic title="Duration" value={`${(event.duration_us || 0) / 1000} ms`} />
            <Statistic title="Process" value={`${event.comm} (PID: ${event.pid})`} />
          </>
        );
      
      case 'security_event':
        return (
          <>
            <Statistic title="Type" value={event.security_type} />
            <Statistic title="Capability" value={event.capability || 'N/A'} />
            <Statistic title="Syscall" value={event.syscall || 'N/A'} />
            <Statistic 
              title="Verdict" 
              value={event.verdict}
              valueStyle={{ color: event.verdict === 'allowed' ? '#4d9f7c' : '#c75450' }}
            />
            <Statistic title="Process" value={`${event.comm} (PID: ${event.pid})`} />
          </>
        );
      
      case 'mount_event':
        return (
          <>
            <Statistic title="Operation" value={event.operation} />
            <Statistic title="Source" value={event.source || 'N/A'} />
            <Statistic title="Target" value={event.target} />
            <Statistic title="Filesystem Type" value={event.fs_type} />
            <Statistic title="Process" value={`${event.comm} (PID: ${event.pid})`} />
          </>
        );
      
      case 'oom_event':
        return (
          <>
            <Statistic title="Process" value={`${event.comm} (PID: ${event.pid})`} />
            <Statistic title="Memory Limit" value={formatBytes(event.memory_limit || 0)} />
            <Statistic title="Memory Usage" value={formatBytes(event.memory_usage || 0)} />
            <Statistic title="Cgroup" value={event.cgroup_path} />
          </>
        );
      
      default:
        return null;
    }
  };

  return (
    <Card 
      title={
        <Space>
          <span style={{ color: config.color }}>{config.icon}</span>
          <span>{config.label}</span>
        </Space>
      }
      size="small"
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Row gutter={[16, 16]}>
          <Col span={12}>
            <Statistic 
              title="Timestamp" 
              value={dayjs(event.timestamp).format('HH:mm:ss.SSS')} 
              valueStyle={{ fontSize: 14 }}
            />
          </Col>
          <Col span={12}>
            <Statistic 
              title="Namespace/Pod" 
              value={`${event.namespace}/${event.pod}`}
              valueStyle={{ fontSize: 12 }}
            />
          </Col>
        </Row>
        <Row gutter={[16, 16]}>
          {renderEventSpecificDetails()}
        </Row>
      </Space>
    </Card>
  );
};

export default EventStatsPanel;

