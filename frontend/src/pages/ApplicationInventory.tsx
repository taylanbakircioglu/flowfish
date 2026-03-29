import React, { useState, useCallback, useMemo } from 'react';
import { 
  Card, 
  Table, 
  Button, 
  Space, 
  Typography, 
  Tag, 
  Select,
  Row,
  Col,
  Statistic,
  Input,
  message
} from 'antd';
import { 
  AppstoreOutlined, 
  ReloadOutlined, 
  SearchOutlined,
  SyncOutlined,
  DatabaseOutlined,
  GlobalOutlined,
  ContainerOutlined
} from '@ant-design/icons';
import { useSelector } from 'react-redux';
import { RootState } from '../store';
import { 
  useGetWorkloadsQuery, 
  useGetNamespacesQuery, 
  useTriggerDiscoveryMutation,
  useGetWorkloadStatsQuery 
} from '../store/api/workloadApi';
import { Workload, Namespace } from '../types';

const { Title, Text } = Typography;
const { Option } = Select;
const { Search } = Input;

const ApplicationInventory: React.FC = () => {
  const [selectedNamespace, setSelectedNamespace] = useState<string | undefined>();
  const [selectedWorkloadType, setSelectedWorkloadType] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  
  const { selectedCluster } = useSelector((state: RootState) => state.cluster);
  const clusterId = selectedCluster?.id;
  
  const { 
    data: workloads = [], 
    isLoading: workloadsLoading, 
    refetch: refetchWorkloads 
  } = useGetWorkloadsQuery(
    { 
      cluster_id: clusterId!, 
      namespace: selectedNamespace,
      workload_type: selectedWorkloadType 
    },
    { skip: !clusterId }
  );
  
  const { 
    data: namespaces = [], 
    isLoading: namespacesLoading 
  } = useGetNamespacesQuery(clusterId!, { skip: !clusterId });
  
  const {
    data: stats,
    isLoading: statsLoading 
  } = useGetWorkloadStatsQuery({ cluster_id: clusterId! }, { skip: !clusterId });
  
  const [triggerDiscovery, { isLoading: discovering }] = useTriggerDiscoveryMutation();

  /**
   * Smart matching for workload names, namespaces, IPs.
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
   * Simple contains for short keywords (type, status, protocol)
   */
  const simpleMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    return value.toLowerCase().includes(search.toLowerCase());
  }, []);

  // Workload-specific search with smart matching
  const workloadMatchesSearch = useCallback((w: Workload, term: string): boolean => {
    if (!term) return true;
    
    // Smart match for name, namespace, IP (structured identifiers)
    if (smartMatch(w.name, term)) return true;
    if (smartMatch(w.namespace_name, term)) return true;
    if (smartMatch(w.ip_address, term)) return true;
    
    // Simple match for type, status (short keywords)
    if (simpleMatch(w.workload_type, term)) return true;
    if (simpleMatch(w.status, term)) return true;
    
    // Labels: smart match for keys, simple match for values
    if (w.labels) {
      for (const [key, value] of Object.entries(w.labels)) {
        if (smartMatch(key, term)) return true;
        if (simpleMatch(String(value), term)) return true;
      }
    }
    
    // Ports: exact match for port numbers, simple for protocol
    if (w.ports) {
      for (const p of w.ports) {
        if (p.port?.toString() === term) return true;
        if (simpleMatch(p.protocol, term)) return true;
      }
    }
    
    return false;
  }, [smartMatch, simpleMatch]);

  // Filter workloads using specific search
  const filteredWorkloads = useMemo(() => {
    return workloads.filter((workload: Workload) => workloadMatchesSearch(workload, searchText));
  }, [workloads, searchText, workloadMatchesSearch]);

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Workload) => (
        <Space>
          {getWorkloadIcon(record.workload_type)}
          <strong>{text}</strong>
        </Space>
      ),
      sorter: (a: Workload, b: Workload) => a.name.localeCompare(b.name),
    },
    {
      title: 'Type',
      dataIndex: 'workload_type',
      key: 'workload_type',
      render: (type: string) => (
        <Tag color={getWorkloadColor(type)}>
          {type.toUpperCase()}
        </Tag>
      ),
      filters: [
        { text: 'Pod', value: 'pod' },
        { text: 'Deployment', value: 'deployment' },
        { text: 'Service', value: 'service' },
        { text: 'StatefulSet', value: 'statefulset' },
      ],
      onFilter: (value: any, record: Workload) => record.workload_type === value,
    },
    {
      title: 'Namespace',
      dataIndex: 'namespace_name',
      key: 'namespace',
      render: (namespace_name: string) => <Tag>{namespace_name || 'N/A'}</Tag>,
      sorter: (a: Workload, b: Workload) => 
        (a.namespace_name || '').localeCompare(b.namespace_name || ''),
    },
    {
      title: 'IP Address',
      dataIndex: 'ip_address',
      key: 'ip_address',
      render: (ip: string) => ip || '-',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          'Running': 'green',
          'Pending': 'orange',
          'Failed': 'red',
          'Succeeded': 'green',
          'Unknown': 'gray',
          'Active': 'green',
        };
        return (
          <Tag color={colorMap[status] || 'gray'}>
            {status}
          </Tag>
        );
      },
      filters: [
        { text: 'Running', value: 'Running' },
        { text: 'Pending', value: 'Pending' },
        { text: 'Failed', value: 'Failed' },
        { text: 'Active', value: 'Active' },
      ],
      onFilter: (value: any, record: Workload) => record.status === value,
    },
    {
      title: 'Labels',
      dataIndex: 'labels',
      key: 'labels',
      render: (labels: Record<string, string>) => (
        <Space wrap>
          {Object.entries(labels).slice(0, 3).map(([key, value]) => (
            <Tag key={key} style={{ fontSize: '11px' }}>
              {key}={value}
            </Tag>
          ))}
          {Object.keys(labels).length > 3 && (
            <Tag style={{ fontSize: '11px' }}>
              +{Object.keys(labels).length - 3} more
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'Last Seen',
      dataIndex: 'last_seen',
      key: 'last_seen',
      render: (date: string) => new Date(date).toLocaleString(),
      sorter: (a: Workload, b: Workload) => new Date(a.last_seen).getTime() - new Date(b.last_seen).getTime(),
    },
  ];

  const handleDiscovery = async () => {
    if (!clusterId) {
      message.error('No cluster selected');
      return;
    }

    try {
      await triggerDiscovery(clusterId).unwrap();
      message.success('Workload discovery completed successfully');
    } catch (error) {
      message.error('Discovery failed');
    }
  };

  const getWorkloadIcon = (type: string) => {
    switch (type) {
      case 'pod':
        return <ContainerOutlined style={{ color: '#0891b2' }} />;
      case 'deployment':
        return <AppstoreOutlined style={{ color: '#4d9f7c' }} />;
      case 'service':
        return <GlobalOutlined style={{ color: '#7c8eb5' }} />;
      case 'statefulset':
        return <DatabaseOutlined style={{ color: '#b89b5d' }} />;
      default:
        return <AppstoreOutlined />;
    }
  };

  const getWorkloadColor = (type: string) => {
    switch (type) {
      case 'pod':
        return 'blue';
      case 'deployment':
        return 'green';
      case 'service':
        return 'purple';
      case 'statefulset':
        return 'orange';
      default:
        return 'gray';
    }
  };

  if (!selectedCluster) {
    return (
      <Card>
        <Text type="secondary">Please select a cluster first</Text>
      </Card>
    );
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2}>
            <AppstoreOutlined /> Application Inventory
          </Title>
          <Text type="secondary">
            Kubernetes workloads in {selectedCluster.name}
          </Text>
        </div>
        
        <Space>
          <Button 
            icon={<SyncOutlined />} 
            onClick={handleDiscovery}
            loading={discovering}
          >
            Discover Workloads
          </Button>
          <Button 
            icon={<ReloadOutlined />} 
            onClick={() => refetchWorkloads()}
          >
            Refresh
          </Button>
        </Space>
      </div>

      {/* Statistics Cards */}
      <Row gutter={[16, 16]}>
        {stats && Object.entries(stats.by_type).map(([workloadType, count]) => (
          <Col xs={24} sm={12} lg={6} key={workloadType}>
            <Card>
              <Statistic
                title={workloadType.toUpperCase()}
                value={count}
                suffix={`/ ${stats.total_workloads}`}
                prefix={getWorkloadIcon(workloadType)}
                valueStyle={{ color: count > 0 ? '#4d9f7c' : '#8c8c8c' }}
              />
            </Card>
          </Col>
        ))}
        
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="NAMESPACES"
              value={namespaces.length}
              prefix={<GlobalOutlined style={{ color: '#22a6a6' }} />}
              valueStyle={{ color: '#22a6a6' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Card>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={8} md={6}>
            <Search
              placeholder="Search all fields (name, IP, labels...)"
              allowClear
              onChange={(e) => setSearchText(e.target.value)}
              style={{ width: '100%' }}
              prefix={<SearchOutlined />}
            />
          </Col>
          
          <Col xs={24} sm={8} md={6}>
            <Select
              placeholder="All Namespaces"
              allowClear
              style={{ width: '100%' }}
              loading={namespacesLoading}
              onChange={setSelectedNamespace}
            >
              {namespaces.map((ns: Namespace) => (
                <Option key={ns.id} value={ns.name}>
                  <Space>
                    {ns.name}
                    <Text type="secondary">({ns.workload_count})</Text>
                  </Space>
                </Option>
              ))}
            </Select>
          </Col>
          
          <Col xs={24} sm={8} md={6}>
            <Select
              placeholder="All Types"
              allowClear
              style={{ width: '100%' }}
              onChange={setSelectedWorkloadType}
            >
              <Option value="pod">Pod</Option>
              <Option value="deployment">Deployment</Option>
              <Option value="service">Service</Option>
              <Option value="statefulset">StatefulSet</Option>
            </Select>
          </Col>

          <Col xs={24} sm={24} md={6}>
            <Text type="secondary">
              {filteredWorkloads.length} of {workloads.length} workloads
            </Text>
          </Col>
        </Row>
      </Card>

      {/* Workloads Table */}
      <Card>
        <Table<Workload>
          columns={columns}
          dataSource={filteredWorkloads}
          loading={workloadsLoading}
          rowKey="id"
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total, range) => 
              `${range[0]}-${range[1]} of ${total} workloads`,
            pageSize: 20,
          }}
          size="small"
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ padding: '16px', background: '#fafafa' }}>
                <Row gutter={[16, 8]}>
                  <Col span={8}>
                    <Text strong>Full Name:</Text><br />
                    <Text code>{record.namespace_name || 'N/A'}/{record.name}</Text>
                  </Col>
                  <Col span={8}>
                    <Text strong>IP Address:</Text><br />
                    <Text>{record.ip_address || 'N/A'}</Text>
                  </Col>
                  <Col span={8}>
                    <Text strong>First Seen:</Text><br />
                    <Text>{new Date(record.first_seen).toLocaleString()}</Text>
                  </Col>
                </Row>
                
                <Row gutter={[16, 8]} style={{ marginTop: 8 }}>
                  <Col span={24}>
                    <Text strong>Labels:</Text><br />
                    <Space wrap>
                      {Object.entries(record.labels).map(([key, value]) => (
                        <Tag key={key}>{key}={value}</Tag>
                      ))}
                    </Space>
                  </Col>
                </Row>
                
                {record.ports && record.ports.length > 0 && (
                  <Row style={{ marginTop: 8 }}>
                    <Col span={24}>
                      <Text strong>Ports:</Text><br />
                      <Space wrap>
                        {record.ports.map((port, index) => (
                          <Tag key={index} color="blue">
                            {port.port}/{port.protocol}
                          </Tag>
                        ))}
                      </Space>
                    </Col>
                  </Row>
                )}
              </div>
            ),
            rowExpandable: () => true,
          }}
        />
      </Card>
    </Space>
  );
};

export default ApplicationInventory;