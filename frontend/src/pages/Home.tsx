import React from 'react';
import { Row, Col, Card, Statistic, Typography, Space } from 'antd';
import { 
  ClusterOutlined, 
  ExperimentOutlined,
  WarningOutlined,
  SecurityScanOutlined 
} from '@ant-design/icons';

const { Title } = Typography;

const Home: React.FC = () => {
  return (
    <div>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Page Header */}
        <div>
          <Title level={2}>🐟 Flowfish Overview Dashboard</Title>
          <Typography.Text type="secondary">
            Real-time eBPF-based Kubernetes application communication and dependency mapping
          </Typography.Text>
        </div>

        {/* Metrics Cards */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Total Clusters"
                value={1}
                prefix={<ClusterOutlined style={{ color: '#0891b2' }} />}
                valueStyle={{ color: '#0891b2' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Active Analyses"
                value={0}
                prefix={<ExperimentOutlined style={{ color: '#4d9f7c' }} />}
                valueStyle={{ color: '#4d9f7c' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Active Anomalies"
                value={0}
                prefix={<WarningOutlined style={{ color: '#c9a55a' }} />}
                valueStyle={{ color: '#c9a55a' }}
              />
            </Card>
          </Col>
          
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="Risk Score"
                value={0}
                suffix="/ 100"
                prefix={<SecurityScanOutlined style={{ color: '#7c8eb5' }} />}
                valueStyle={{ color: '#7c8eb5' }}
              />
            </Card>
          </Col>
        </Row>

      </Space>
    </div>
  );
};

export default Home;
