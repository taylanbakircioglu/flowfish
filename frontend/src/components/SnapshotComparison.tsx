/**
 * SnapshotComparison - Compare two analysis snapshots
 * 
 * Features:
 * - Side-by-side comparison of two analysis states
 * - Visual diff showing additions and removals
 * - Workload, connection, and namespace changes
 * - Summary statistics
 */

import React from 'react';
import {
  Card,
  Row,
  Col,
  Typography,
  Tag,
  Space,
  Statistic,
  Table,
  Empty,
  Spin,
  Alert,
  Badge,
  theme,
} from 'antd';
import {
  PlusCircleOutlined,
  MinusCircleOutlined,
  CloudServerOutlined,
  ApiOutlined,
  AppstoreOutlined,
  ArrowRightOutlined,
  DiffOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

// Types matching the API response
interface SnapshotComparisonProps {
  data?: SnapshotDiff;
  loading?: boolean;
  error?: string;
}

interface SnapshotDiff {
  cluster_id: number;
  analysis_before: {
    id: number;
    workloads: number;
    connections: number;
    namespaces: string[];
  };
  analysis_after: {
    id: number;
    workloads: number;
    connections: number;
    namespaces: string[];
  };
  diff: {
    workloads_added: string[];
    workloads_removed: string[];
    connections_added: Array<{ source: string; target: string; port: number }>;
    connections_removed: Array<{ source: string; target: string; port: number }>;
    namespaces_added: string[];
    namespaces_removed: string[];
  };
  summary: {
    total_changes: number;
    workload_changes: number;
    connection_changes: number;
    namespace_changes: number;
  };
  data_source?: string;
}

const { useToken } = theme;

const SnapshotComparison: React.FC<SnapshotComparisonProps> = ({
  data,
  loading = false,
  error,
}) => {
  const { token } = useToken();
  
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 50 }}>
        <Spin size="large" />
        <Text style={{ display: 'block', marginTop: 16 }}>Comparing snapshots...</Text>
      </div>
    );
  }

  if (error) {
    return (
      <Alert
        type="error"
        message="Comparison Failed"
        description={error}
        showIcon
      />
    );
  }

  if (!data) {
    return <Empty description="Select two analyses to compare" />;
  }

  const { analysis_before, analysis_after, diff, summary } = data;

  // Calculate deltas
  const workloadDelta = analysis_after.workloads - analysis_before.workloads;
  const connectionDelta = analysis_after.connections - analysis_before.connections;

  // Check if there are no changes
  const noChanges = summary.total_changes === 0;

  return (
    <div>
      {/* Header */}
      <Card bordered={false} style={{ marginBottom: 16, background: '#fafafa' }}>
        <Row align="middle" justify="center" gutter={24}>
          <Col>
            <Space direction="vertical" align="center">
              <Badge status="default" text={<Text type="secondary">Before</Text>} />
              <Text strong style={{ fontSize: 18 }}>Analysis #{analysis_before.id}</Text>
            </Space>
          </Col>
          <Col>
            <ArrowRightOutlined style={{ fontSize: 24, color: '#0891b2' }} />
          </Col>
          <Col>
            <Space direction="vertical" align="center">
              <Badge status="processing" text={<Text type="secondary">After</Text>} />
              <Text strong style={{ fontSize: 18 }}>Analysis #{analysis_after.id}</Text>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* No Changes Alert */}
      {noChanges && (
        <Alert
          type="success"
          message="No Changes Detected"
          description="The two snapshots are identical. No workloads, connections, or namespaces were added or removed."
          icon={<CheckCircleOutlined />}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Summary Statistics */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Total Changes"
              value={summary.total_changes}
              prefix={<DiffOutlined style={{ color: '#0891b2' }} />}
              valueStyle={{ color: summary.total_changes > 0 ? '#b89b5d' : '#4d9f7c' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Workload Changes"
              value={summary.workload_changes}
              prefix={<CloudServerOutlined />}
              suffix={
                workloadDelta !== 0 && (
                  <Text style={{ fontSize: 14, color: workloadDelta > 0 ? '#4d9f7c' : '#c75450' }}>
                    ({workloadDelta > 0 ? '+' : ''}{workloadDelta})
                  </Text>
                )
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Connection Changes"
              value={summary.connection_changes}
              prefix={<ApiOutlined />}
              suffix={
                connectionDelta !== 0 && (
                  <Text style={{ fontSize: 14, color: connectionDelta > 0 ? '#4d9f7c' : '#c75450' }}>
                    ({connectionDelta > 0 ? '+' : ''}{connectionDelta})
                  </Text>
                )
              }
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card bordered={false}>
            <Statistic
              title="Namespace Changes"
              value={summary.namespace_changes}
              prefix={<AppstoreOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Before/After Comparison */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card 
            title={<Space><Badge status="default" /> Before (Analysis #{analysis_before.id})</Space>}
            bordered={false}
            size="small"
          >
            <Row gutter={16}>
              <Col span={8}>
                <Statistic title="Workloads" value={analysis_before.workloads} prefix={<CloudServerOutlined />} />
              </Col>
              <Col span={8}>
                <Statistic title="Connections" value={analysis_before.connections} prefix={<ApiOutlined />} />
              </Col>
              <Col span={8}>
                <Statistic title="Namespaces" value={analysis_before.namespaces.length} />
              </Col>
            </Row>
          </Card>
        </Col>
        <Col span={12}>
          <Card 
            title={<Space><Badge status="processing" /> After (Analysis #{analysis_after.id})</Space>}
            bordered={false}
            size="small"
          >
            <Row gutter={16}>
              <Col span={8}>
                <Statistic 
                  title="Workloads" 
                  value={analysis_after.workloads} 
                  prefix={<CloudServerOutlined />}
                  valueStyle={{ color: workloadDelta > 0 ? '#4d9f7c' : workloadDelta < 0 ? '#c75450' : undefined }}
                />
              </Col>
              <Col span={8}>
                <Statistic 
                  title="Connections" 
                  value={analysis_after.connections} 
                  prefix={<ApiOutlined />}
                  valueStyle={{ color: connectionDelta > 0 ? '#4d9f7c' : connectionDelta < 0 ? '#c75450' : undefined }}
                />
              </Col>
              <Col span={8}>
                <Statistic title="Namespaces" value={analysis_after.namespaces.length} />
              </Col>
            </Row>
          </Card>
        </Col>
      </Row>

      {/* Workload Changes */}
      {(diff.workloads_added.length > 0 || diff.workloads_removed.length > 0) && (
        <Card 
          title={<Space><CloudServerOutlined /> Workload Changes</Space>}
          bordered={false}
          style={{ marginBottom: 16 }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <div style={{ background: '#f6ffed', padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <PlusCircleOutlined style={{ color: '#4d9f7c' }} />
                  <Text strong style={{ color: '#4d9f7c' }}>Added ({diff.workloads_added.length})</Text>
                </Space>
                <div>
                  {diff.workloads_added.length > 0 ? (
                    <Space wrap>
                      {diff.workloads_added.map((name, i) => (
                        <Tag key={i} color="success">{name}</Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">No workloads added</Text>
                  )}
                </div>
              </div>
            </Col>
            <Col span={12}>
              <div style={{ background: token.colorErrorBg, padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <MinusCircleOutlined style={{ color: token.colorError }} />
                  <Text strong style={{ color: token.colorError }}>Removed ({diff.workloads_removed.length})</Text>
                </Space>
                <div>
                  {diff.workloads_removed.length > 0 ? (
                    <Space wrap>
                      {diff.workloads_removed.map((name, i) => (
                        <Tag key={i} color="error">{name}</Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">No workloads removed</Text>
                  )}
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* Connection Changes */}
      {(diff.connections_added.length > 0 || diff.connections_removed.length > 0) && (
        <Card 
          title={<Space><ApiOutlined /> Connection Changes</Space>}
          bordered={false}
          style={{ marginBottom: 16 }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <div style={{ background: '#f6ffed', padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <PlusCircleOutlined style={{ color: '#4d9f7c' }} />
                  <Text strong style={{ color: '#4d9f7c' }}>Added ({diff.connections_added.length})</Text>
                </Space>
                <div>
                  {diff.connections_added.length > 0 ? (
                    <Table
                      dataSource={diff.connections_added.map((c, i) => ({ ...c, key: i }))}
                      columns={[
                        { title: 'Source', dataIndex: 'source', key: 'source' },
                        { 
                          title: '', 
                          key: 'arrow', 
                          width: 40, 
                          render: () => <ArrowRightOutlined style={{ color: '#4d9f7c' }} /> 
                        },
                        { title: 'Target', dataIndex: 'target', key: 'target' },
                        { title: 'Port', dataIndex: 'port', key: 'port', width: 80 },
                      ]}
                      pagination={false}
                      size="small"
                    />
                  ) : (
                    <Text type="secondary">No connections added</Text>
                  )}
                </div>
              </div>
            </Col>
            <Col span={12}>
              <div style={{ background: token.colorErrorBg, padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <MinusCircleOutlined style={{ color: token.colorError }} />
                  <Text strong style={{ color: token.colorError }}>Removed ({diff.connections_removed.length})</Text>
                </Space>
                <div>
                  {diff.connections_removed.length > 0 ? (
                    <Table
                      dataSource={diff.connections_removed.map((c, i) => ({ ...c, key: i }))}
                      columns={[
                        { title: 'Source', dataIndex: 'source', key: 'source' },
                        { 
                          title: '', 
                          key: 'arrow', 
                          width: 40, 
                          render: () => <ArrowRightOutlined style={{ color: '#c75450' }} /> 
                        },
                        { title: 'Target', dataIndex: 'target', key: 'target' },
                        { title: 'Port', dataIndex: 'port', key: 'port', width: 80 },
                      ]}
                      pagination={false}
                      size="small"
                    />
                  ) : (
                    <Text type="secondary">No connections removed</Text>
                  )}
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* Namespace Changes */}
      {(diff.namespaces_added.length > 0 || diff.namespaces_removed.length > 0) && (
        <Card 
          title={<Space><AppstoreOutlined /> Namespace Changes</Space>}
          bordered={false}
          style={{ marginBottom: 16 }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <div style={{ background: '#f6ffed', padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <PlusCircleOutlined style={{ color: '#4d9f7c' }} />
                  <Text strong style={{ color: '#4d9f7c' }}>Added ({diff.namespaces_added.length})</Text>
                </Space>
                <div>
                  {diff.namespaces_added.length > 0 ? (
                    <Space wrap>
                      {diff.namespaces_added.map((name, i) => (
                        <Tag key={i} color="success">{name}</Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">No namespaces added</Text>
                  )}
                </div>
              </div>
            </Col>
            <Col span={12}>
              <div style={{ background: token.colorErrorBg, padding: 12, borderRadius: 4 }}>
                <Space style={{ marginBottom: 8 }}>
                  <MinusCircleOutlined style={{ color: token.colorError }} />
                  <Text strong style={{ color: token.colorError }}>Removed ({diff.namespaces_removed.length})</Text>
                </Space>
                <div>
                  {diff.namespaces_removed.length > 0 ? (
                    <Space wrap>
                      {diff.namespaces_removed.map((name, i) => (
                        <Tag key={i} color="error">{name}</Tag>
                      ))}
                    </Space>
                  ) : (
                    <Text type="secondary">No namespaces removed</Text>
                  )}
                </div>
              </div>
            </Col>
          </Row>
        </Card>
      )}

      {/* Data Source Notice */}
      {data.data_source === 'mock' && (
        <Alert
          type="info"
          message="Demo Data"
          description="This comparison uses demo data. Enable real data mode for actual analysis comparison."
          showIcon
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
};

export default SnapshotComparison;
