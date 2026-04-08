import React, { useState, useEffect } from 'react';
import { 
  Card, 
  Table, 
  Button, 
  Space, 
  Typography, 
  Tag, 
  Modal, 
  Form,
  Input,
  Select,
  Checkbox,
  message,
  Alert,
  Steps,
  Divider,
  Tooltip,
  Row,
  Col,
  Tabs
} from 'antd';
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  ReloadOutlined, 
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  QuestionCircleOutlined,
  CopyOutlined,
  InfoCircleOutlined,
  RocketOutlined,
  SafetyOutlined,
  KeyOutlined,
  LinkOutlined,
  CloudServerOutlined,
  FileOutlined,
  ApiOutlined,
  WarningOutlined,
  BookOutlined,
  DownloadOutlined,
  SettingOutlined,
  ArrowUpOutlined
} from '@ant-design/icons';
import { useGetClustersQuery, useCreateClusterMutation, useDeleteClusterMutation, useUpdateClusterMutation, useSyncClusterMutation, useTestConnectionMutation, useLazyGetGadgetInstallScriptQuery, useLazyGetGadgetUpgradeScriptQuery } from '../store/api/clusterApi';

const compareVersions = (a: string, b: string): number => {
  const pa = a.replace('v', '').split('.').map(Number);
  const pb = b.replace('v', '').split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) < (pb[i] || 0)) return -1;
    if ((pa[i] || 0) > (pb[i] || 0)) return 1;
  }
  return 0;
};

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { TextArea } = Input;
const { Step } = Steps;

// Helper component for copyable code blocks
const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language = 'bash' }) => {
  const copyToClipboard = () => {
    navigator.clipboard.writeText(code);
    message.success('Copied to clipboard!');
  };

  return (
    <div style={{ 
      position: 'relative', 
      background: '#1e1e1e', 
      borderRadius: 8, 
      padding: '12px 16px',
      marginTop: 8,
      marginBottom: 8 
    }}>
      <Button
        type="text"
        icon={<CopyOutlined />}
        size="small"
        onClick={copyToClipboard}
        style={{ 
          position: 'absolute', 
          top: 8, 
          right: 8, 
          color: '#aaa',
          zIndex: 1
        }}
      />
      <pre style={{ 
        margin: 0, 
        color: '#d4d4d4', 
        fontSize: 12, 
        fontFamily: 'Monaco, Consolas, monospace',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all'
      }}>
        {code}
      </pre>
    </div>
  );
};

// Unified Flowfish Setup Modal - Install & Uninstall Scripts
const FlowfishSetupModal: React.FC<{ 
  open: boolean; 
  onClose: () => void; 
  provider: string;
}> = ({ open, onClose, provider }) => {
  const isOpenshift = provider === 'openshift';
  const [activeTab, setActiveTab] = useState('install');
  const [storageClass, setStorageClass] = useState('');
  const [fetchInstallScript, { data: installScript, isLoading: installLoading, error: installError }] = useLazyGetGadgetInstallScriptQuery();
  const [fetchUninstallScript, { data: uninstallScript, isLoading: uninstallLoading, error: uninstallError }] = useLazyGetGadgetInstallScriptQuery();
  
  // Fetch scripts when modal opens or tab changes
  useEffect(() => {
    if (open) {
      const providerParam = isOpenshift ? 'openshift' : 'kubernetes';
      if (activeTab === 'install') {
        fetchInstallScript({ provider: providerParam, mode: 'install', storageClass });
      } else if (activeTab === 'uninstall') {
        fetchUninstallScript({ provider: providerParam, mode: 'uninstall' });
      }
    }
  }, [open, activeTab, isOpenshift, fetchInstallScript, fetchUninstallScript, storageClass]);
  
  // Refetch install script when storage class changes
  const handleStorageClassChange = (value: string) => {
    setStorageClass(value);
    if (open && activeTab === 'install') {
      const providerParam = isOpenshift ? 'openshift' : 'kubernetes';
      fetchInstallScript({ provider: providerParam, mode: 'install', storageClass: value });
    }
  };
  
  const copyToClipboard = (script: string | undefined, filename: string) => {
    if (script) {
      navigator.clipboard.writeText(script);
      message.success(`${filename} copied to clipboard!`);
    }
  };
  
  const downloadScript = (script: string | undefined, filename: string) => {
    if (script) {
      const blob = new Blob([script], { type: 'text/x-sh' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success(`${filename} downloaded!`);
    }
  };
  
  const renderScriptContent = (
    script: string | undefined, 
    loading: boolean, 
    error: unknown, 
    filename: string,
    isInstall: boolean
  ) => (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button 
            type="primary" 
            icon={<CopyOutlined />} 
            onClick={() => copyToClipboard(script, filename)} 
            disabled={!script || loading} 
            size="large"
          >
            Copy Script
          </Button>
          <Button 
            icon={<DownloadOutlined />} 
            onClick={() => downloadScript(script, filename)} 
            disabled={!script || loading} 
            size="large"
          >
            Download
          </Button>
        </Space>
      </div>
      
      {loading && (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <LoadingOutlined style={{ fontSize: 24 }} />
          <div style={{ marginTop: 8 }}>Generating script...</div>
        </div>
      )}
      
      {error && (
        <Alert
          type="error"
          message="Failed to generate script"
          description="Could not fetch the script from the server."
          style={{ marginBottom: 16 }}
        />
      )}
      
      {script && !loading && (
        <div style={{ 
          background: '#1e1e1e', 
          borderRadius: 8, 
          padding: '12px 16px',
          maxHeight: 350,
          overflow: 'auto'
        }}>
          <pre style={{ 
            margin: 0, 
            color: '#d4d4d4', 
            fontSize: 11, 
            fontFamily: 'Monaco, Consolas, monospace',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all'
          }}>
            {script}
          </pre>
        </div>
      )}
      
      <Divider />
      
      <Text strong>How to Run:</Text>
      <CodeBlock code={isInstall 
        ? `# Save script and run:
chmod +x ${filename}
./${filename} YOUR_NAMESPACE

# Or run without parameter (script will prompt):
./${filename}`
        : `# Save script and run:
chmod +x ${filename}
./${filename} YOUR_NAMESPACE

# Script will ask for confirmation before deleting`
      } />
    </div>
  );

  const tabItems = [
    {
      key: 'install',
      label: (
        <span>
          <RocketOutlined style={{ color: '#4d9f7c' }} />
          {' '}Install Script
        </span>
      ),
      children: (
        <div>
          <Alert
            type="success"
            message="🚀 Complete Remote Cluster Setup"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>This script performs complete setup and outputs all connection details:</p>
                <Row gutter={16}>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>✅ Inspector Gadget installation</li>
                      <li>✅ Read-only ServiceAccount</li>
                      <li>✅ RBAC authorization</li>
                    </ul>
                  </Col>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>✅ 1-year token generation</li>
                      <li>✅ API Server URL</li>
                      <li>✅ CA Certificate</li>
                    </ul>
                  </Col>
                </Row>
                <Divider style={{ margin: '12px 0' }} />
                <Text strong style={{ color: '#4d9f7c' }}>
                  📋 All connection details will be printed at the end - copy them to the form below!
                </Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          
          {/* Storage Class Configuration */}
          <div style={{ 
            background: '#f6ffed', 
            border: '1px solid #b7eb8f', 
            borderRadius: 8, 
            padding: 16, 
            marginBottom: 16 
          }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <Text strong>
                <CloudServerOutlined style={{ marginRight: 8 }} />
                Storage Configuration (Optional)
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Configure persistent storage to prevent gadget from filling up node's local disk (emptyDir).
                Leave empty to use default emptyDir storage (data lost on pod restart).
              </Text>
              <Input
                placeholder="Enter StorageClass name (e.g., standard, gp2, managed-premium)"
                value={storageClass}
                onChange={(e) => handleStorageClassChange(e.target.value)}
                style={{ maxWidth: 400 }}
                prefix={<CloudServerOutlined style={{ color: '#52c41a' }} />}
                allowClear
              />
              {storageClass && (
                <Alert
                  type="info"
                  message={`Persistent storage will be configured with StorageClass: ${storageClass}`}
                  description={
                    <ul style={{ marginBottom: 0, paddingLeft: 20, marginTop: 8 }}>
                      <li>OCI volume: 10Gi per node (gadget programs)</li>
                      <li>WASM cache: 5Gi per node</li>
                      <li>Ephemeral PVCs created automatically per pod</li>
                    </ul>
                  }
                  showIcon
                  style={{ marginTop: 8 }}
                />
              )}
            </Space>
          </div>
          
          {renderScriptContent(installScript, installLoading, installError, 'setup-flowfish-remote.sh', true)}
        </div>
      ),
    },
    {
      key: 'uninstall',
      label: (
        <span>
          <DeleteOutlined style={{ color: '#f76e6e' }} />
          {' '}Uninstall Script
        </span>
      ),
      children: (
        <div>
          <Alert
            type="warning"
            message="⚠️ Safe Uninstall Script"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>This script safely removes only Flowfish resources:</p>
                <ul style={{ marginBottom: 8, paddingLeft: 20 }}>
                  <li>🔒 Only removes Flowfish/Inspector Gadget resources</li>
                  <li>🔒 Does not affect other namespaces</li>
                  <li>🔒 Requires confirmation before deletion</li>
                  <li>🔒 Preserves other installations</li>
                </ul>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          {renderScriptContent(uninstallScript, uninstallLoading, uninstallError, 'uninstall-flowfish-remote.sh', false)}
        </div>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <SettingOutlined style={{ color: '#0891b2' }} />
          <span>Flowfish Remote Cluster Setup</span>
          <Tag color={isOpenshift ? 'red' : 'blue'}>{isOpenshift ? 'OpenShift' : 'Kubernetes'}</Tag>
        </Space>
      }
      open={open}
      onCancel={onClose}
      footer={[
        <Button key="close" type="primary" onClick={onClose}>
          Close
        </Button>
      ]}
      width={950}
      style={{ top: 20 }}
      styles={{ body: { maxHeight: 'calc(100vh - 180px)', overflow: 'auto', padding: '16px 24px' } }}
    >
      <Alert
        type="info"
        message="Remote Cluster Connection Setup"
        description={
          <span>
            To connect a remote {isOpenshift ? 'OpenShift' : 'Kubernetes'} cluster to Flowfish:
            <ol style={{ marginBottom: 0, paddingLeft: 20, marginTop: 8 }}>
              <li>Run the <strong>Install Script</strong> on the remote cluster</li>
              <li>Copy the output values to the form below</li>
              <li>Test the connection</li>
            </ol>
          </span>
        }
        style={{ marginBottom: 16 }}
      />
      
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab} 
        items={tabItems}
        type="card"
      />
    </Modal>
  );
};

// Define Cluster interface to match API response
interface ClusterData {
  id: number;
  name: string;
  description?: string;
  environment: string;
  provider: string;
  region?: string;
  connection_type: string;
  api_server_url: string;
  gadget_namespace?: string;
  gadget_health_status?: string;
  gadget_version?: string;
  status: string;
  total_namespaces?: number;
  total_pods?: number;
  total_nodes?: number;
  k8s_version?: string;
  skip_tls_verify?: boolean;
  created_at?: string;
}

const ClusterManagement: React.FC = () => {
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [editingCluster, setEditingCluster] = useState<ClusterData | null>(null);
  const [syncingClusterId, setSyncingClusterId] = useState<number | null>(null);
  const [connectionType, setConnectionType] = useState<string>('kubeconfig');
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  
  // Guide modal states
  const [isSetupModalOpen, setIsSetupModalOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string>('kubernetes');
  
  // Upgrade modal states
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeCluster, setUpgradeCluster] = useState<ClusterData | null>(null);
  const [upgradeScript, setUpgradeScript] = useState<string>('');
  
  const { data, isLoading, refetch } = useGetClustersQuery();
  const supportedGadgetVersion = data?.supported_gadget_version || '';
  const [createCluster, { isLoading: creating }] = useCreateClusterMutation();
  const [deleteCluster] = useDeleteClusterMutation();
  const [updateCluster, { isLoading: updating }] = useUpdateClusterMutation();
  const [syncCluster] = useSyncClusterMutation();
  const [testConnection, { isLoading: testing }] = useTestConnectionMutation();
  const [fetchUpgradeScript] = useLazyGetGadgetUpgradeScriptQuery();
  const [testResult, setTestResult] = useState<any>(null);
  
  // Update selectedProvider when form changes
  useEffect(() => {
    const provider = form.getFieldValue('provider');
    if (provider) {
      setSelectedProvider(provider);
    }
  }, [form]);

  // Extract clusters array from response
  const clusters = data?.clusters || [];

  const handleEdit = (record: ClusterData) => {
    setEditingCluster(record);
    editForm.setFieldsValue({
      name: record.name,
      description: record.description,
      environment: record.environment,
      provider: record.provider,
      region: record.region,
      api_server_url: record.api_server_url,
      gadget_namespace: record.gadget_namespace,
      status: record.status,
      skip_tls_verify: record.skip_tls_verify || false,
      // Sensitive fields - leave empty, user can optionally update
      token: '',
      kubeconfig: '',
      ca_cert: '',
    });
    setIsEditModalVisible(true);
  };

  const handleEditSubmit = async () => {
    try {
      const values = await editForm.validateFields();
      if (!editingCluster) return;

      // Build update data - only include non-empty values
      const updateData: Record<string, any> = {};
      
      // Basic fields - always include if changed
      if (values.name) updateData.name = values.name;
      if (values.description !== undefined) updateData.description = values.description;
      if (values.environment) updateData.environment = values.environment;
      if (values.provider) updateData.provider = values.provider;
      if (values.region) updateData.region = values.region;
      if (values.api_server_url) updateData.api_server_url = values.api_server_url;
      if (values.gadget_namespace) updateData.gadget_namespace = values.gadget_namespace;
      if (values.status) updateData.status = values.status;
      if (values.skip_tls_verify !== undefined) updateData.skip_tls_verify = values.skip_tls_verify;
      
      // Sensitive fields - only include if user provided a new value (not empty)
      if (values.token && values.token.trim()) updateData.token = values.token;
      if (values.kubeconfig && values.kubeconfig.trim()) updateData.kubeconfig = values.kubeconfig;
      if (values.ca_cert && values.ca_cert.trim()) updateData.ca_cert = values.ca_cert;

      await updateCluster({
        id: editingCluster.id,
        data: updateData
      }).unwrap();
      
      message.success('Cluster updated successfully');
      setIsEditModalVisible(false);
      setEditingCluster(null);
      editForm.resetFields();
    } catch (error: any) {
      console.error('Failed to update cluster:', error);
      message.error(error?.data?.detail || 'Failed to update cluster');
    }
  };

  const handleSync = async (record: ClusterData) => {
    try {
      setSyncingClusterId(record.id);
      const result = await syncCluster(record.id).unwrap();
      
      // Handle both full and partial sync results
      if (result.status === 'completed' && result.resources) {
        message.success(`Cluster synced: ${result.resources.nodes} nodes, ${result.resources.pods} pods, ${result.resources.namespaces} namespaces`);
      } else if (result.status === 'partial') {
        // Partial sync - cluster info couldn't be fetched but gadget health was updated
        message.warning(`Partial sync: ${result.warning || 'Cluster info unavailable'}. Gadget health: ${result.gadget_health}`);
      } else {
        message.info(`Cluster sync completed: ${result.message}`);
      }
    } catch (error: any) {
      console.error('Failed to sync cluster:', error);
      message.error(error?.data?.detail || 'Failed to sync cluster');
    } finally {
      setSyncingClusterId(null);
    }
  };

  const handleDelete = (record: ClusterData) => {
    Modal.confirm({
      title: 'Delete Cluster',
      content: `Are you sure you want to delete cluster "${record.name}"?`,
      okText: 'Yes, Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await deleteCluster(record.id).unwrap();
          message.success('Cluster deleted successfully');
        } catch (error) {
          message.error('Failed to delete cluster');
        }
      },
    });
  };

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: ClusterData) => (
        <Space direction="vertical" size={0}>
          <strong>{text}</strong>
          {record.description && (
            <Typography.Text type="secondary" style={{ fontSize: '12px' }}>
              {record.description}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: 'Environment',
      dataIndex: 'environment',
      key: 'environment',
      render: (env: string) => (
        <Tag color={env === 'production' ? 'red' : env === 'staging' ? 'orange' : 'blue'}>
          {env.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string) => provider?.toUpperCase() || '-',
    },
    {
      title: 'Gadget Health',
      dataIndex: 'gadget_health_status',
      key: 'gadget_health_status',
      render: (status: string, record: ClusterData) => {
        const colorMap: Record<string, string> = {
          healthy: 'green',
          degraded: 'orange', 
          unhealthy: 'red',
          unknown: 'gray'
        };
        const clusterVersion = record.gadget_version || '';
        const needsUpgrade = clusterVersion && supportedGadgetVersion && 
          compareVersions(clusterVersion, supportedGadgetVersion) < 0;
        return (
          <Space direction="vertical" size={2} style={{ textAlign: 'center', width: '100%' }}>
            <Tag color={colorMap[status || 'unknown']} icon={status === 'healthy' ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
              {(status || 'unknown').toUpperCase()}
            </Tag>
            {record.gadget_version && (
              needsUpgrade ? (
                <Tooltip title={`Upgrade available: ${supportedGadgetVersion}. Click to view upgrade script.`}>
                  <span
                    style={{
                      fontSize: '11px',
                      color: '#fa8c16',
                      cursor: 'pointer',
                      border: '1px solid #ffd591',
                      borderRadius: '10px',
                      padding: '1px 8px',
                      background: '#fff7e6',
                      display: 'inline-block',
                      lineHeight: '18px',
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setUpgradeCluster(record);
                      fetchUpgradeScript({ clusterId: record.id })
                        .unwrap()
                        .then(script => {
                          setUpgradeScript(script);
                          setUpgradeModalOpen(true);
                        })
                        .catch(() => {
                          message.error('Failed to generate upgrade script');
                        });
                    }}
                  >
                    {record.gadget_version} <ArrowUpOutlined style={{ fontSize: '9px' }} />
                  </span>
                </Tooltip>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: '11px' }}>
                  {record.gadget_version}
                </Typography.Text>
              )
            )}
          </Space>
        );
      },
    },
    {
      title: 'Resources',
      key: 'resources',
      render: (record: ClusterData) => (
        <Space direction="vertical" size={0}>
          <Typography.Text style={{ fontSize: '12px' }}>
            Nodes: {record.total_nodes || 0}
          </Typography.Text>
          <Typography.Text style={{ fontSize: '12px' }}>
            Pods: {record.total_pods || 0}
          </Typography.Text>
          <Typography.Text style={{ fontSize: '12px' }}>
            Namespaces: {record.total_namespaces || 0}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'red'}>
          {status.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (record: ClusterData) => (
        <Space>
          <Button 
            type="link" 
            size="small"
            icon={syncingClusterId === record.id ? <LoadingOutlined spin /> : <SyncOutlined />}
            onClick={() => handleSync(record)}
            disabled={syncingClusterId === record.id}
            title="Sync cluster resources"
          />
          <Button 
            type="link" 
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
            title="Edit cluster"
          />
          <Button 
            type="link" 
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record)}
            title="Delete cluster"
          />
        </Space>
      ),
    },
  ];

  const handleAdd = () => {
    form.resetFields();
    setConnectionType('kubeconfig');
    setIsModalVisible(true);
  };

  // Test connection before creating cluster
  const handleTestConnection = async () => {
    try {
      const values = await form.validateFields(['api_server_url', 'token', 'ca_cert', 'skip_tls_verify', 'gadget_namespace']);
      
      const testPayload = {
        connection_type: connectionType,
        api_server_url: values.api_server_url,
        token: values.token,
        ca_cert: values.ca_cert,
        skip_tls_verify: values.skip_tls_verify || false,
        gadget_namespace: values.gadget_namespace,  // Required from UI
      };
      
      const result = await testConnection(testPayload).unwrap();
      setTestResult(result);
      
      if (result.overall_status === 'success') {
        message.success('Connection test successful! All systems are reachable.');
      } else if (result.overall_status === 'partial') {
        message.warning('Partial success. Check the results for details.');
      } else {
        message.error('Connection test failed. Check the results for details.');
      }
    } catch (error: any) {
      console.error('Connection test failed:', error);
      message.error(error?.data?.detail || 'Connection test failed');
      setTestResult({
        overall_status: 'failed',
        cluster_connection: { status: 'failed', error: error?.data?.detail || 'Unknown error', details: {} },
        gadget_connection: { status: 'failed', error: null, details: {} },
        recommendations: ['Please check your connection parameters.']
      });
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      // Build the cluster payload according to new API
      const clusterPayload: any = {
        name: values.name,
        description: values.description,
        environment: values.environment,
        provider: values.provider,
        region: values.region,
        connection_type: connectionType,
        api_server_url: values.api_server_url,
        gadget_namespace: values.gadget_namespace,  // Required from UI
        gadget_auto_detect: values.gadget_auto_detect !== false,
        skip_tls_verify: values.skip_tls_verify || false,
      };

      // Add connection details based on type
      if (connectionType === 'kubeconfig' && values.kubeconfig) {
        clusterPayload.kubeconfig = values.kubeconfig;
      } else if (connectionType === 'token') {
        clusterPayload.token = values.token;
        if (values.ca_cert) {
          clusterPayload.ca_cert = values.ca_cert;
        }
      }

      await createCluster(clusterPayload).unwrap();
      message.success('Cluster added successfully');
      setIsModalVisible(false);
      form.resetFields();
      setTestResult(null);
    } catch (error: any) {
      console.error('Failed to add cluster:', error);
      message.error(error?.data?.detail || 'Failed to add cluster');
    }
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={2}>Cluster Management</Title>
          <Typography.Text type="secondary">
            Manage Kubernetes and OpenShift clusters for analysis
          </Typography.Text>
        </div>
        
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            Refresh
          </Button>
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={handleAdd}
          >
            Add Cluster
          </Button>
        </Space>
      </div>

      {/* Clusters Table */}
      <Card>
        <Table<ClusterData>
          columns={columns}
          dataSource={clusters as unknown as ClusterData[]}
          loading={isLoading}
          rowKey="id"
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `Total ${total} clusters`,
          }}
        />
      </Card>

      {/* Add Cluster Modal */}
      <Modal
        title="Add New Cluster"
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setTestResult(null);
        }}
        width={700}
        footer={[
          <Button key="cancel" onClick={() => {
            setIsModalVisible(false);
            setTestResult(null);
          }}>
            Cancel
          </Button>,
          connectionType !== 'in-cluster' && (
            <Button 
              key="test" 
              icon={<ApiOutlined />}
              onClick={handleTestConnection}
              loading={testing}
            >
              Test Connection
            </Button>
          ),
          <Button 
            key="submit" 
            type="primary" 
            onClick={handleSubmit}
            loading={creating}
          >
            Add Cluster
          </Button>
        ]}
      >
        {/* Test Connection Results */}
        {testResult && (
          <Alert
            type={testResult.overall_status === 'success' ? 'success' : 
                  testResult.overall_status === 'partial' ? 'warning' : 'error'}
            message={
              <Space>
                {testResult.overall_status === 'success' ? (
                  <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
                ) : testResult.overall_status === 'partial' ? (
                  <WarningOutlined style={{ color: '#c9a55a' }} />
                ) : (
                  <CloseCircleOutlined style={{ color: '#f76e6e' }} />
                )}
                <Text strong>
                  Connection Test: {testResult.overall_status.toUpperCase()}
                </Text>
              </Space>
            }
            description={
              <div style={{ marginTop: 8 }}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary">Cluster: </Text>
                    <Tag color={testResult.cluster_connection?.status === 'success' ? 'green' : 'red'}>
                      {testResult.cluster_connection?.status}
                    </Tag>
                    {testResult.cluster_connection?.details?.k8s_version && (
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        K8s {testResult.cluster_connection.details.k8s_version}
                      </Text>
                    )}
                    {testResult.cluster_connection?.error && (
                      <Text type="danger" style={{ display: 'block', fontSize: 12 }}>
                        {testResult.cluster_connection.error}
                      </Text>
                    )}
                  </div>
                  <div>
                    <Text type="secondary">Inspector Gadget: </Text>
                    <Tag color={
                      testResult.gadget_connection?.status === 'success' ? 'green' : 
                      testResult.gadget_connection?.status === 'warning' ? 'orange' :
                      testResult.gadget_connection?.status === 'skipped' ? 'default' : 'red'
                    }>
                      {testResult.gadget_connection?.status}
                    </Tag>
                    {testResult.gadget_connection?.details?.version && (
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        v{testResult.gadget_connection.details.version}
                      </Text>
                    )}
                    {testResult.gadget_connection?.error && (
                      <Text type="danger" style={{ display: 'block', fontSize: 12 }}>
                        {testResult.gadget_connection.error}
                      </Text>
                    )}
                  </div>
                  {testResult.recommendations?.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text strong style={{ fontSize: 12 }}>Recommendations:</Text>
                      <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
                        {testResult.recommendations.map((rec: string, idx: number) => (
                          <li key={idx} style={{ fontSize: 12 }}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Space>
              </div>
            }
            showIcon={false}
            style={{ marginBottom: 16 }}
          />
        )}
        
        <Form
          form={form}
          layout="vertical"
          style={{ marginTop: 16 }}
        >
          {/* Basic Information */}
          <Title level={5}>Basic Information</Title>
          
          <Form.Item
            label="Cluster Name"
            name="name"
            rules={[{ required: true, message: 'Please enter cluster name' }]}
          >
            <Input placeholder="e.g., production-cluster" />
          </Form.Item>

          <Form.Item
            label="Description"
            name="description"
          >
            <TextArea 
              placeholder="Optional description"
              rows={2}
            />
          </Form.Item>

          <Form.Item
            label="Environment"
            name="environment"
            rules={[{ required: true, message: 'Please select environment' }]}
            initialValue="development"
          >
            <Select>
              <Option value="development">Development</Option>
              <Option value="staging">Staging</Option>
              <Option value="production">Production</Option>
              <Option value="testing">Testing</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="Provider"
            name="provider"
            rules={[{ required: true, message: 'Please select provider' }]}
            initialValue="kubernetes"
          >
            <Select onChange={(value) => setSelectedProvider(value)}>
              <Option value="kubernetes">Kubernetes</Option>
              <Option value="openshift">OpenShift</Option>
              <Option value="eks">Amazon EKS</Option>
              <Option value="gke">Google GKE</Option>
              <Option value="aks">Azure AKS</Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="Region (Optional)"
            name="region"
          >
            <Input placeholder="e.g., us-east-1, eu-west-1" />
          </Form.Item>

          {/* Connection Configuration */}
          <Title level={5} style={{ marginTop: 24 }}>Connection Configuration</Title>
          
          {/* Setup Scripts - Always visible at the top */}
          <div style={{ marginBottom: 24 }}>
            <Alert
              type="info"
              message={
                <Space>
                  <RocketOutlined style={{ color: '#0891b2' }} />
                  <span style={{ fontWeight: 600 }}>Remote Cluster Setup Scripts</span>
                </Space>
              }
              description={
                <div>
                  <Text>
                    Get install and uninstall scripts for remote cluster setup. The install script will output all connection details needed for this form.
                  </Text>
                  <div style={{ marginTop: 12 }}>
                    <Button 
                      type="primary" 
                      size="large"
                      icon={<SettingOutlined />}
                      onClick={() => setIsSetupModalOpen(true)}
                    >
                      🚀 Get Setup Scripts
                    </Button>
                  </div>
                </div>
              }
              showIcon={false}
              style={{ 
                background: 'linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%)',
                border: '1px solid #91d5ff'
              }}
            />
          </div>
          
          <Form.Item 
            label={
              <Space>
                <span>Connection Type</span>
                <Tooltip title="Choose how Flowfish will authenticate to this cluster">
                  <QuestionCircleOutlined style={{ color: '#0891b2' }} />
                </Tooltip>
              </Space>
            }
          >
            <Select 
              value={connectionType} 
              onChange={(value) => {
                setConnectionType(value);
                // Reset API URL based on connection type
                if (value === 'in-cluster') {
                  form.setFieldValue('api_server_url', 'https://kubernetes.default.svc');
                } else {
                  form.setFieldValue('api_server_url', '');
                }
              }}
            >
              <Option value="in-cluster">
                <Space>
                  <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
                  <span>In-Cluster</span>
                  <Text type="secondary" style={{ fontSize: 11 }}>(Flowfish is deployed in this cluster)</Text>
                </Space>
              </Option>
              <Option value="token">
                <Space>
                  <KeyOutlined style={{ color: '#0891b2' }} />
                  <span>Service Account Token</span>
                  <Tag color="blue" style={{ fontSize: 10 }}>Recommended for Remote</Tag>
                </Space>
              </Option>
              <Option value="kubeconfig">
                <Space>
                  <FileOutlined style={{ color: '#7c8eb5' }} />
                  <span>Kubeconfig File</span>
                </Space>
              </Option>
            </Select>
          </Form.Item>

          <Form.Item
            label={
              <Space>
                <span>API Server URL</span>
                <Tooltip title={
                  connectionType === 'in-cluster' 
                    ? "For in-cluster deployment, use the internal Kubernetes service URL" 
                    : "The external API server endpoint of the remote cluster"
                }>
                  <QuestionCircleOutlined style={{ color: '#0891b2' }} />
                </Tooltip>
              </Space>
            }
            name="api_server_url"
            rules={[
              { required: true, message: 'Please enter API server URL' },
              { 
                pattern: /^https?:\/\/.+/,
                message: 'URL must start with http:// or https://'
              }
            ]}
            initialValue={connectionType === 'in-cluster' ? "https://kubernetes.default.svc" : ""}
            extra={
              connectionType === 'token' ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  <InfoCircleOutlined /> Run <code>kubectl config view --minify -o jsonpath='&#123;.clusters[0].cluster.server&#125;'</code> to get this value
                </Text>
              ) : undefined
            }
          >
            <Input 
              placeholder={connectionType === 'in-cluster' 
                ? "https://kubernetes.default.svc" 
                : "https://api.cluster-name.example.com:6443"
              }
              prefix={<CloudServerOutlined style={{ color: '#bfbfbf' }} />}
            />
          </Form.Item>

          {connectionType === 'kubeconfig' && (
            <Form.Item
              label="Kubeconfig Content"
              name="kubeconfig"
              rules={[{ required: true, message: 'Please provide kubeconfig' }]}
              extra="Paste the content of your kubeconfig file"
            >
              <TextArea 
                rows={6}
                placeholder="apiVersion: v1&#10;kind: Config&#10;clusters:..."
              />
            </Form.Item>
          )}

          {connectionType === 'token' && (
            <>
              <Form.Item
                label={
                  <Space>
                    <span>Service Account Token</span>
                    <Tooltip title="Long-lived token from a Kubernetes ServiceAccount with cluster-reader permissions. See setup guide below for instructions.">
                      <QuestionCircleOutlined style={{ color: '#0891b2' }} />
                    </Tooltip>
                  </Space>
                }
                name="token"
                rules={[{ required: true, message: 'Please enter token' }]}
                extra={
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    <InfoCircleOutlined /> Token format: eyJhbGciOiJSUzI1NiIsImtpZCI6...
                  </Text>
                }
              >
                <TextArea 
                  rows={4}
                  placeholder="eyJhbGciOiJSUzI1NiIsImtpZCI6..."
                />
              </Form.Item>

              <Form.Item
                label={
                  <Space>
                    <span>CA Certificate</span>
                    <Tag color="default">Optional</Tag>
                    <Tooltip title="The cluster's CA certificate for TLS verification. Required if you want secure connections without skipping TLS verification.">
                      <QuestionCircleOutlined style={{ color: '#0891b2' }} />
                    </Tooltip>
                  </Space>
                }
                name="ca_cert"
                extra={
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    <InfoCircleOutlined /> Base64-encoded or PEM format certificate
                  </Text>
                }
              >
                <TextArea 
                  rows={4}
                  placeholder="-----BEGIN CERTIFICATE-----&#10;MIIC...&#10;-----END CERTIFICATE-----"
                />
              </Form.Item>
            </>
          )}

          <Form.Item
            name="skip_tls_verify"
            valuePropName="checked"
          >
            <Checkbox>Skip TLS verification (not recommended for production)</Checkbox>
          </Form.Item>

          {/* Inspector Gadget Configuration */}
          <Divider />
          <Title level={5}>
            <Space>
              <RocketOutlined style={{ color: '#4d9f7c' }} />
              Inspector Gadget Configuration
            </Space>
          </Title>
          
          {connectionType === 'token' && (
            <Alert
              type="info"
              message="Inspector Gadget Endpoint"
              description="The Inspector Gadget endpoint will be shown in the setup script output."
              style={{ marginBottom: 16 }}
            />
          )}
          
          <Form.Item
            label={
              <Space>
                <span>Inspector Gadget Namespace</span>
                <Tooltip title="The namespace where Inspector Gadget is deployed. Health checks use K8s API to check pod status in this namespace.">
                  <QuestionCircleOutlined style={{ color: '#0891b2' }} />
                </Tooltip>
              </Space>
            }
            name="gadget_namespace"
            initialValue="flowfish"
            extra={
              <Text type="secondary" style={{ fontSize: 11 }}>
                <InfoCircleOutlined /> Namespace where gadget DaemonSet is deployed (default: flowfish)
              </Text>
            }
            rules={[
              { 
                required: true, 
                message: 'Gadget namespace is required' 
              }
            ]}
          >
            <Input 
              placeholder="flowfish"
              prefix={<CloudServerOutlined style={{ color: '#bfbfbf' }} />}
            />
          </Form.Item>

          <Form.Item
            name="gadget_auto_detect"
            valuePropName="checked"
            initialValue={connectionType === 'in-cluster'}
          >
            <Checkbox disabled={connectionType === 'token'}>
              Auto-detect Inspector Gadget deployment
              {connectionType === 'token' && (
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
                  (Not available for remote clusters)
                </Text>
              )}
            </Checkbox>
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Cluster Modal */}
      <Modal
        title={
          <Space>
            <EditOutlined />
            {`Edit Cluster: ${editingCluster?.name || ''}`}
          </Space>
        }
        open={isEditModalVisible}
        onOk={handleEditSubmit}
        onCancel={() => {
          setIsEditModalVisible(false);
          setEditingCluster(null);
          editForm.resetFields();
        }}
        okText="Save Changes"
        cancelText="Cancel"
        confirmLoading={updating}
        width={720}
      >
        <Form
          form={editForm}
          layout="vertical"
          style={{ marginTop: 16 }}
        >
          {/* Basic Information */}
          <Divider orientation="left" style={{ marginTop: 0 }}>
            <Space><InfoCircleOutlined /> Basic Information</Space>
          </Divider>
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label="Cluster Name"
                name="name"
                rules={[{ required: true, message: 'Please enter cluster name' }]}
              >
                <Input placeholder="Cluster name" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="Status"
                name="status"
                rules={[{ required: true, message: 'Please select status' }]}
              >
                <Select>
                  <Option value="active">
                    <Space><CheckCircleOutlined style={{ color: '#4d9f7c' }} />Active</Space>
                  </Option>
                  <Option value="inactive">
                    <Space><CloseCircleOutlined style={{ color: '#f76e6e' }} />Inactive</Space>
                  </Option>
                  <Option value="maintenance">
                    <Space><SettingOutlined style={{ color: '#c9a55a' }} />Maintenance</Space>
                  </Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            label="Description"
            name="description"
          >
            <TextArea 
              placeholder="Optional description"
              rows={2}
            />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label="Environment"
                name="environment"
              >
                <Select>
                  <Option value="development">Development</Option>
                  <Option value="staging">Staging</Option>
                  <Option value="production">Production</Option>
                  <Option value="testing">Testing</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="Provider"
                name="provider"
              >
                <Select>
                  <Option value="kubernetes">Kubernetes</Option>
                  <Option value="openshift">OpenShift</Option>
                  <Option value="eks">AWS EKS</Option>
                  <Option value="gke">Google GKE</Option>
                  <Option value="aks">Azure AKS</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="Region"
                name="region"
              >
                <Input placeholder="e.g., us-west-2" />
              </Form.Item>
            </Col>
          </Row>

          {/* Connection Settings */}
          <Divider orientation="left">
            <Space><LinkOutlined /> Connection Settings</Space>
          </Divider>

          <Form.Item
            label="API Server URL"
            name="api_server_url"
            extra="Kubernetes API server endpoint"
          >
            <Input 
              placeholder="https://api.cluster.example.com:6443" 
              prefix={<ApiOutlined />}
            />
          </Form.Item>

          <Form.Item
            label="Inspector Gadget Namespace"
            name="gadget_namespace"
            extra="Namespace where Inspector Gadget is deployed"
            rules={[{ required: true, message: 'Gadget namespace is required' }]}
          >
            <Input placeholder="flowfish" />
          </Form.Item>

          <Form.Item
            name="skip_tls_verify"
            valuePropName="checked"
          >
            <Checkbox>
              <Space>
                <WarningOutlined style={{ color: '#c9a55a' }} />
                Skip TLS Verification (not recommended for production)
              </Space>
            </Checkbox>
          </Form.Item>

          {/* Credential Update Section */}
          {editingCluster?.connection_type === 'token' && (
            <>
              <Divider orientation="left">
                <Space><KeyOutlined /> Update Credentials (Optional)</Space>
              </Divider>
              
              <Alert
                type="info"
                message="Leave empty to keep existing credentials"
                style={{ marginBottom: 16 }}
                showIcon
              />

              <Form.Item
                label="Service Account Token"
                name="token"
                extra="Only fill if you want to update the token"
              >
                <TextArea 
                  placeholder="Enter new token to update (leave empty to keep current)"
                  rows={3}
                  style={{ fontFamily: 'monospace' }}
                />
              </Form.Item>

              <Form.Item
                label="CA Certificate"
                name="ca_cert"
                extra="Only fill if you want to update the CA certificate"
              >
                <TextArea 
                  placeholder="Enter new CA certificate to update (leave empty to keep current)"
                  rows={3}
                  style={{ fontFamily: 'monospace' }}
                />
              </Form.Item>
            </>
          )}

          {editingCluster?.connection_type === 'kubeconfig' && (
            <>
              <Divider orientation="left">
                <Space><FileOutlined /> Update Kubeconfig (Optional)</Space>
              </Divider>
              
              <Alert
                type="info"
                message="Leave empty to keep existing kubeconfig"
                style={{ marginBottom: 16 }}
                showIcon
              />

              <Form.Item
                label="Kubeconfig"
                name="kubeconfig"
                extra="Only fill if you want to update the kubeconfig"
              >
                <TextArea 
                  placeholder="Paste new kubeconfig content to update (leave empty to keep current)"
                  rows={6}
                  style={{ fontFamily: 'monospace' }}
                />
              </Form.Item>
            </>
          )}

          {/* Connection Type Display (Read-only) */}
          <Form.Item label="Connection Type">
            <Tag color="blue" icon={<CloudServerOutlined />}>
              {editingCluster?.connection_type || 'Unknown'}
            </Tag>
            <Text type="secondary" style={{ marginLeft: 8 }}>
              (Connection type cannot be changed after creation)
            </Text>
          </Form.Item>
        </Form>
      </Modal>

      {/* Unified Flowfish Setup Modal */}
      <FlowfishSetupModal
        open={isSetupModalOpen}
        onClose={() => setIsSetupModalOpen(false)}
        provider={selectedProvider}
      />

      {/* Gadget Upgrade Modal */}
      <Modal
        title={`Upgrade Inspektor Gadget - ${upgradeCluster?.name || ''}`}
        open={upgradeModalOpen}
        onCancel={() => { setUpgradeModalOpen(false); setUpgradeCluster(null); }}
        footer={null}
        width={800}
      >
        <Alert
          message="Gadget Upgrade Available"
          description={
            <span>
              Current version: <strong>{upgradeCluster?.gadget_version || 'unknown'}</strong> &rarr; Target: <strong>{supportedGadgetVersion}</strong>
              <br />
              Run the script below on a machine with <code>kubectl</code>/<code>oc</code> access to the cluster.
              Ensure no active analyses are running before upgrading.
            </span>
          }
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <CodeBlock code={upgradeScript} />
        <Space style={{ marginTop: 12 }}>
          <Button
            icon={<CopyOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(upgradeScript);
              message.success('Script copied to clipboard!');
            }}
          >
            Copy Script
          </Button>
          <Button
            icon={<DownloadOutlined />}
            onClick={() => {
              const blob = new Blob([upgradeScript], { type: 'text/plain' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `upgrade-gadget-${upgradeCluster?.name || 'cluster'}.sh`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download Script
          </Button>
        </Space>
      </Modal>
    </Space>
  );
};

export default ClusterManagement;
