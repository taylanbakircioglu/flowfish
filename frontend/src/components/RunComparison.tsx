/**
 * Run Comparison Component
 * 
 * Compares changes between two selected analysis runs.
 * Shows what changed uniquely in each run vs common changes.
 * 
 * Feature flag controlled: RUN_BASED_FILTERING_ENABLED
 */

import React, { useMemo } from 'react';
import { Card, Row, Col, Statistic, Typography, Tag, Space, Table, Empty, Spin, Tooltip, theme } from 'antd';
import {
  SwapOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  MinusOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text, Title } = Typography;

interface RunStats {
  run_id: number;
  run_number: number;
  total_changes: number;
  by_risk: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  by_type: Record<string, number>;
  first_change_at?: string;
  last_change_at?: string;
}

interface RunComparisonProps {
  run1?: RunStats;
  run2?: RunStats;
  loading?: boolean;
  onSelectRun?: (position: 'left' | 'right') => void;
}

const riskColors: Record<string, string> = {
  critical: '#cf1322',
  high: '#c75450',
  medium: '#b89b5d',
  low: '#4d9f7c',
};

const { useToken } = theme;

const RunComparison: React.FC<RunComparisonProps> = ({
  run1,
  run2,
  loading = false,
  onSelectRun,
}) => {
  const { token } = useToken();
  // Calculate comparison metrics
  const comparison = useMemo(() => {
    if (!run1 || !run2) return null;
    
    const totalDiff = run2.total_changes - run1.total_changes;
    const criticalDiff = (run2.by_risk?.critical || 0) - (run1.by_risk?.critical || 0);
    const highDiff = (run2.by_risk?.high || 0) - (run1.by_risk?.high || 0);
    
    return {
      totalDiff,
      criticalDiff,
      highDiff,
      trend: totalDiff > 0 ? 'increase' : totalDiff < 0 ? 'decrease' : 'stable',
    };
  }, [run1, run2]);

  // Build comparison table data
  const tableData = useMemo(() => {
    if (!run1 || !run2) return [];
    
    const metrics = [
      { 
        key: 'total', 
        metric: 'Total Changes',
        run1Value: run1.total_changes,
        run2Value: run2.total_changes,
      },
      {
        key: 'critical',
        metric: 'Critical Changes',
        run1Value: run1.by_risk?.critical || 0,
        run2Value: run2.by_risk?.critical || 0,
        color: riskColors.critical,
      },
      {
        key: 'high',
        metric: 'High Risk Changes',
        run1Value: run1.by_risk?.high || 0,
        run2Value: run2.by_risk?.high || 0,
        color: riskColors.high,
      },
      {
        key: 'medium',
        metric: 'Medium Risk Changes',
        run1Value: run1.by_risk?.medium || 0,
        run2Value: run2.by_risk?.medium || 0,
        color: riskColors.medium,
      },
      {
        key: 'low',
        metric: 'Low Risk Changes',
        run1Value: run1.by_risk?.low || 0,
        run2Value: run2.by_risk?.low || 0,
        color: riskColors.low,
      },
    ];
    
    return metrics;
  }, [run1, run2]);

  const columns = [
    {
      title: 'Metric',
      dataIndex: 'metric',
      key: 'metric',
      render: (text: string, record: any) => (
        <Text style={{ color: record.color }}>{text}</Text>
      ),
    },
    {
      title: run1 ? `Run #${run1.run_number}` : 'Run 1',
      dataIndex: 'run1Value',
      key: 'run1Value',
      align: 'center' as const,
      render: (value: number) => <Text strong>{value}</Text>,
    },
    {
      title: 'Difference',
      key: 'diff',
      align: 'center' as const,
      render: (_: any, record: any) => {
        const diff = record.run2Value - record.run1Value;
        if (diff === 0) return <MinusOutlined style={{ color: '#d9d9d9' }} />;
        const color = diff > 0 ? '#c75450' : '#4d9f7c';
        const icon = diff > 0 ? <ArrowRightOutlined /> : <ArrowLeftOutlined />;
        return (
          <Space style={{ color }}>
            {icon}
            <Text style={{ color }}>{Math.abs(diff)}</Text>
          </Space>
        );
      },
    },
    {
      title: run2 ? `Run #${run2.run_number}` : 'Run 2',
      dataIndex: 'run2Value',
      key: 'run2Value',
      align: 'center' as const,
      render: (value: number) => <Text strong>{value}</Text>,
    },
  ];

  if (loading) {
    return (
      <Card size="small">
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
          <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            Loading comparison...
          </Text>
        </div>
      </Card>
    );
  }

  if (!run1 || !run2) {
    return (
      <Card 
        size="small"
        title={
          <Space>
            <SwapOutlined />
            <Text strong>Run Comparison</Text>
          </Space>
        }
      >
        <Empty
          description={
            <Space direction="vertical">
              <Text>Select two runs to compare</Text>
              <Text type="secondary">
                Use the run selector to choose runs for comparison
              </Text>
            </Space>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <SwapOutlined />
          <Text strong>Run Comparison</Text>
          <Tag>Run #{run1.run_number}</Tag>
          <ArrowRightOutlined />
          <Tag>Run #{run2.run_number}</Tag>
        </Space>
      }
    >
      {/* Summary Stats */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={`Run #${run1.run_number}`}
              value={run1.total_changes}
              suffix="changes"
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card 
            size="small" 
            style={{ 
              textAlign: 'center',
              backgroundColor: comparison?.trend === 'increase' ? token.colorErrorBg : 
                             comparison?.trend === 'decrease' ? token.colorSuccessBg : token.colorBgLayout
            }}
          >
            <Statistic
              title="Difference"
              value={comparison?.totalDiff || 0}
              prefix={comparison?.totalDiff && comparison.totalDiff > 0 ? '+' : ''}
              valueStyle={{ 
                color: comparison?.trend === 'increase' ? '#cf1322' : 
                       comparison?.trend === 'decrease' ? '#3f8600' : undefined 
              }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic
              title={`Run #${run2.run_number}`}
              value={run2.total_changes}
              suffix="changes"
            />
          </Card>
        </Col>
      </Row>

      {/* Alert for significant changes */}
      {comparison && comparison.criticalDiff > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Tag color="error" icon={<ExclamationCircleOutlined />}>
            {comparison.criticalDiff} more critical changes in Run #{run2.run_number}
          </Tag>
        </div>
      )}

      {/* Detailed Comparison Table */}
      <Table
        columns={columns}
        dataSource={tableData}
        pagination={false}
        size="small"
        rowKey="key"
      />

      {/* Time Range Info */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Run #{run1.run_number}: {run1.first_change_at ? dayjs(run1.first_change_at).format('MMM D, HH:mm') : '-'} - {run1.last_change_at ? dayjs(run1.last_change_at).format('HH:mm') : 'ongoing'}
          </Text>
        </Col>
        <Col span={12} style={{ textAlign: 'right' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Run #{run2.run_number}: {run2.first_change_at ? dayjs(run2.first_change_at).format('MMM D, HH:mm') : '-'} - {run2.last_change_at ? dayjs(run2.last_change_at).format('HH:mm') : 'ongoing'}
          </Text>
        </Col>
      </Row>
    </Card>
  );
};

export default RunComparison;
