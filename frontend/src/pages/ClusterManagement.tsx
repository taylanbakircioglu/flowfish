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
  CopyOutlined,
  InfoCircleOutlined,
  RocketOutlined,
  KeyOutlined,
  LinkOutlined,
  CloudServerOutlined,
  FileOutlined,
  ApiOutlined,
  WarningOutlined,
  DownloadOutlined,
  SettingOutlined,
  ArrowUpOutlined,
  HddOutlined,
  ToolOutlined
} from '@ant-design/icons';
import { useGetClustersQuery, useCreateClusterMutation, useDeleteClusterMutation, useUpdateClusterMutation, useSyncClusterMutation, useTestConnectionMutation, useLazyGetGadgetInstallScriptQuery, useLazyGetGadgetUninstallScriptQuery, useLazyGetGadgetUpgradeScriptQuery, useLazyGetGadgetFixStorageScriptQuery, useLazyGetBeylaInstallScriptGeneralQuery, useLazyGetBeylaInstallScriptQuery, useLazyGetL7UninstallScriptQuery } from '../store/api/clusterApi';

const compareVersions = (a: string, b: string): number => {
  const pa = a.replace('v', '').split('.').map(Number);
  const pb = b.replace('v', '').split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) < (pb[i] || 0)) return -1;
    if ((pa[i] || 0) > (pb[i] || 0)) return 1;
  }
  return 0;
};

const { Title, Text } = Typography;
const { Option } = Select;
const { TextArea } = Input;

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
  clusterId?: number;
  clusterName?: string;
}> = ({ open, onClose, provider, clusterId, clusterName }) => {
  const isOpenshift = provider === 'openshift';
  const [activeTab, setActiveTab] = useState('install');
  const [imageRegistry, setImageRegistry] = useState('');
  const [collectorTag, setCollectorTag] = useState('');
  const [fetchInstallScript, { data: installScript, isLoading: installLoading, error: installError }] = useLazyGetGadgetInstallScriptQuery();
  const [fetchUninstallScript, { data: uninstallScript, isLoading: uninstallLoading, error: uninstallError }] = useLazyGetGadgetUninstallScriptQuery();
  const [fetchL7UninstallScript, { data: l7UninstallScript, isLoading: l7UninstallLoading, error: l7UninstallError }] = useLazyGetL7UninstallScriptQuery();
  const [fetchFixStorageScript, { data: fixStorageScript, isLoading: fixStorageLoading, error: fixStorageError }] = useLazyGetGadgetFixStorageScriptQuery();
  const [fetchBeylaInstallScriptGeneral, { data: beylaInstallScriptGeneral, isLoading: beylaInstallLoadingGeneral, error: beylaInstallErrorGeneral }] = useLazyGetBeylaInstallScriptGeneralQuery();
  const [fetchBeylaInstallScriptCluster, { data: beylaInstallScriptCluster, isLoading: beylaInstallLoadingCluster, error: beylaInstallErrorCluster }] = useLazyGetBeylaInstallScriptQuery();
  const beylaInstallScript = clusterId ? beylaInstallScriptCluster : beylaInstallScriptGeneral;
  const beylaInstallLoading = clusterId ? beylaInstallLoadingCluster : beylaInstallLoadingGeneral;
  const beylaInstallError = clusterId ? beylaInstallErrorCluster : beylaInstallErrorGeneral;

  // Fetch scripts when modal opens or tab changes
  useEffect(() => {
    if (open) {
      const providerParam = isOpenshift ? 'openshift' : 'kubernetes';
      const registryParam = imageRegistry ? { imageRegistry } : {};
      const tagParam = collectorTag ? { collectorTag } : {};
      if (activeTab === 'install') {
        fetchInstallScript({ provider: providerParam, ...registryParam });
      } else if (activeTab === 'uninstall-l4') {
        fetchUninstallScript({ provider: providerParam });
      } else if (activeTab === 'uninstall-l7') {
        fetchL7UninstallScript({ provider: providerParam });
      } else if (activeTab === 'beyla') {
        if (clusterId) {
          fetchBeylaInstallScriptCluster({ clusterId, provider: providerParam, ...registryParam, ...tagParam });
        } else {
          fetchBeylaInstallScriptGeneral({ provider: providerParam, ...registryParam, ...tagParam });
        }
      } else if (activeTab === 'fix-storage') {
        fetchFixStorageScript({ provider: providerParam });
      }
    }
  }, [open, activeTab, isOpenshift, fetchInstallScript, fetchUninstallScript, fetchL7UninstallScript, fetchBeylaInstallScriptGeneral, fetchBeylaInstallScriptCluster, fetchFixStorageScript, clusterId, imageRegistry, collectorTag]);
  
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

# Script will ask for confirmation before proceeding`
      } />
    </div>
  );

  const tabItems = [
    {
      key: 'install',
      label: (
        <span>
          <HddOutlined style={{ color: '#4d9f7c' }} />
          {' '}1. Network-Level (L4)
        </span>
      ),
      children: (
        <div>
          <Alert
            type="success"
            message="Complete Remote Cluster Setup"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>This script performs complete setup and outputs all connection details:</p>
                <Row gutter={16}>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>Inspector Gadget installation</li>
                      <li>Read-only ServiceAccount</li>
                      <li>RBAC authorization</li>
                    </ul>
                  </Col>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>1-year token generation</li>
                      <li>API Server URL</li>
                      <li>CA Certificate</li>
                    </ul>
                  </Col>
                </Row>
                <Divider style={{ margin: '12px 0' }} />
                <Text strong style={{ color: '#4d9f7c' }}>
                  All connection details will be printed at the end - copy them to the form below!
                </Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          
          {renderScriptContent(installScript, installLoading, installError, 'setup-flowfish-remote.sh', true)}
        </div>
      ),
    },
    {
      key: 'beyla',
      label: (
        <span>
          <ApiOutlined style={{ color: '#722ed1' }} />
          {' '}2. Application-Level (L7)
        </span>
      ),
      children: (
        <div>
          <Alert
            type="info"
            message="Application-Level Agent (L7) — Grafana Beyla"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>Installs Beyla eBPF agent and flowfish-l7-collector for HTTP/gRPC/DNS capture:</p>
                <Row gutter={16}>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>Beyla DaemonSet (eBPF L7 capture)</li>
                      <li>flowfish-l7-collector (OTLP bridge)</li>
                      <li>RBAC and ServiceAccounts</li>
                    </ul>
                  </Col>
                  <Col span={12}>
                    <ul style={{ marginBottom: 0, paddingLeft: 16 }}>
                      <li>HTTP, gRPC, DNS interception</li>
                      <li>Pull API for central ingestion</li>
                      <li>Production-safe resource limits</li>
                    </ul>
                  </Col>
                </Row>
                <Divider style={{ margin: '12px 0' }} />
                <Text type="secondary">
                  This step is <strong>optional</strong>. Skip if you only need L4 (network-level) analysis. You can set this up later from Cluster Management.
                </Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          {renderScriptContent(beylaInstallScript, beylaInstallLoading, beylaInstallError, 'install-beyla-l7.sh', true)}
        </div>
      ),
    },
    {
      key: 'uninstall-l4',
      label: (
        <span>
          <DeleteOutlined style={{ color: '#f76e6e' }} />
          {' '}L4 Cleanup
        </span>
      ),
      children: (
        <div>
          <Alert
            type="warning"
            message="L4 Agent Cleanup - Inspector Gadget"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>Removes only L4 (network-level) agent resources:</p>
                <ul style={{ marginBottom: 8, paddingLeft: 20 }}>
                  <li>Inspector Gadget DaemonSet, Service, ConfigMap</li>
                  <li>Flowfish ServiceAccount and RBAC</li>
                  <li>Gadget SCC (OpenShift, if not shared)</li>
                </ul>
                <Text type="secondary">Beyla (L7) and other workloads will NOT be affected.</Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          {renderScriptContent(uninstallScript, uninstallLoading, uninstallError, 'cleanup-l4-agent.sh', false)}
        </div>
      ),
    },
    {
      key: 'uninstall-l7',
      label: (
        <span>
          <DeleteOutlined style={{ color: '#cf1322' }} />
          {' '}L7 Cleanup
        </span>
      ),
      children: (
        <div>
          <Alert
            type="warning"
            message="L7 Agent Cleanup - Grafana Beyla + Collector"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>Removes only L7 (application-level) agent resources:</p>
                <ul style={{ marginBottom: 8, paddingLeft: 20 }}>
                  <li>Beyla DaemonSet, ConfigMap, ServiceAccount</li>
                  <li>flowfish-l7-collector Deployment, Service</li>
                  <li>Beyla SCC (OpenShift, if not shared)</li>
                </ul>
                <Text type="secondary">Inspector Gadget (L4) and other workloads will NOT be affected.</Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          {renderScriptContent(l7UninstallScript, l7UninstallLoading, l7UninstallError, 'cleanup-l7-agent.sh', false)}
        </div>
      ),
    },
    {
      key: 'fix-storage',
      label: (
        <span>
          <ToolOutlined style={{ color: '#fa8c16' }} />
          {' '}Fix Storage
        </span>
      ),
      children: (
        <div>
          <Alert
            type="warning"
            message="Gadget Storage Migration Script"
            description={
              <div>
                <p style={{ marginBottom: 8 }}>Migrates existing Gadget installations from PVC/ephemeral volumes to emptyDir with sizeLimit:</p>
                <ul style={{ marginBottom: 8, paddingLeft: 20 }}>
                  <li>Converts PVC/ephemeral volumes to emptyDir with sizeLimit</li>
                  <li>Adds sizeLimit to unlimited emptyDir volumes</li>
                  <li>Cleans up orphaned PVCs</li>
                  <li>Prevents node disk exhaustion</li>
                </ul>
                <Text type="secondary">Run this on clusters where Gadget was installed with persistent storage or without sizeLimit.</Text>
              </div>
            }
            style={{ marginBottom: 16 }}
            showIcon
          />
          {renderScriptContent(fixStorageScript, fixStorageLoading, fixStorageError, 'fix-gadget-storage.sh', false)}
        </div>
      ),
    },
  ];

  return (
    <Modal
      title={
        <Space>
          <SettingOutlined style={{ color: '#0891b2' }} />
          <span>{clusterName ? `Agent Scripts — ${clusterName}` : 'Flowfish Remote Cluster Setup'}</span>
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
      zIndex={1050}
      style={{ top: 20 }}
      styles={{ body: { maxHeight: 'calc(100vh - 180px)', overflow: 'auto', padding: '16px 24px' } }}
    >
      <Alert
        type="info"
        message={<Text strong>Quick setup — {isOpenshift ? 'OpenShift' : 'Kubernetes'} cluster</Text>}
        description={
          <div>
            <div style={{ display: 'flex', gap: 16, marginTop: 8 }}>
              <div style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: '#f6ffed', borderRadius: 6, border: '1px solid #d9f7be' }}>
                <HddOutlined style={{ fontSize: 18, color: '#4d9f7c' }} />
                <div style={{ fontWeight: 600, fontSize: 12, marginTop: 4 }}>1. L4 agent</div>
                <div style={{ fontSize: 11, color: '#666' }}>Inspector Gadget + service account</div>
              </div>
              <div style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: '#f9f0ff', borderRadius: 6, border: '1px solid #d3adf7' }}>
                <ApiOutlined style={{ fontSize: 18, color: '#722ed1' }} />
                <div style={{ fontWeight: 600, fontSize: 12, marginTop: 4 }}>2. L7 agent (optional)</div>
                <div style={{ fontSize: 11, color: '#666' }}>Grafana Beyla + collector</div>
              </div>
              <div style={{ flex: 1, textAlign: 'center', padding: '8px 4px', background: '#fff7e6', borderRadius: 6, border: '1px solid #ffd591' }}>
                <CheckCircleOutlined style={{ fontSize: 18, color: '#d48806' }} />
                <div style={{ fontWeight: 600, fontSize: 12, marginTop: 4 }}>3. Fill form</div>
                <div style={{ fontSize: 11, color: '#666' }}>Paste script output &amp; save</div>
              </div>
            </div>
            <div style={{ marginTop: 8, fontSize: 11, color: '#666', lineHeight: 1.5 }}>
              <Text type="secondary">
                Tip: scripts auto-detect OpenShift at runtime via the
                <Text code style={{ fontSize: 11 }}>security.openshift.io</Text> API and create the required
                SecurityContextConstraints automatically — they work with both
                <Text code style={{ fontSize: 11 }}>oc</Text> and
                <Text code style={{ fontSize: 11 }}>kubectl</Text>, regardless of the provider you picked above.
              </Text>
            </div>
          </div>
        }
        showIcon={false}
        style={{ marginBottom: 12 }}
      />

      {(activeTab === 'install' || activeTab === 'beyla') && (
        <div style={{ marginBottom: 12, padding: '10px 14px', background: '#fafafa', borderRadius: 6, border: '1px solid #e8e8e8' }}>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>Image Registry</label>
          <Input
            placeholder="your-registry.example.com/flowfish"
            value={imageRegistry}
            onChange={(e) => setImageRegistry(e.target.value)}
            allowClear
            style={{ maxWidth: 480 }}
          />
          <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
            Fill this if your cluster pulls images from a private registry instead of the public internet. Leave empty for official registries.
          </div>
          {activeTab === 'beyla' && (
            <div style={{ marginTop: 10 }}>
              <label style={{ display: 'block', marginBottom: 4, fontWeight: 500, fontSize: 13 }}>Collector Image Tag</label>
              <Input
                placeholder="e.g., 86451d5, v1.2.0"
                value={collectorTag}
                onChange={(e) => setCollectorTag(e.target.value)}
                allowClear
                style={{ maxWidth: 240 }}
              />
              <div style={{ fontSize: 11, color: '#999', marginTop: 2 }}>
                Image tag for flowfish-l7-collector. Leave empty to use the backend's default tag (auto-detected from deployment).
              </div>
            </div>
          )}
        </div>
      )}

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
  beyla_namespace?: string;
  beyla_health_status?: string;
  beyla_version?: string;
  l7_collector_endpoint?: string;
  beyla_last_check?: string;
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
  const [setupClusterId, setSetupClusterId] = useState<number | undefined>();
  const [setupClusterName, setSetupClusterName] = useState<string | undefined>();
  
  // Upgrade modal states
  const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
  const [upgradeCluster, setUpgradeCluster] = useState<ClusterData | null>(null);
  const [upgradeScript, setUpgradeScript] = useState<string>('');
  
  const { data, isLoading, refetch } = useGetClustersQuery();
  const supportedGadgetVersion = data?.supported_gadget_version || '';
  const supportedBeylaVersion = data?.supported_beyla_version || '';
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
    setEditTestResult(null);
    editForm.setFieldsValue({
      name: record.name,
      description: record.description,
      environment: record.environment,
      provider: record.provider,
      region: record.region,
      api_server_url: record.api_server_url,
      gadget_namespace: record.gadget_namespace,
      beyla_namespace: record.beyla_namespace,
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
      if (values.beyla_namespace !== undefined) updateData.beyla_namespace = values.beyla_namespace || '';
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
      setEditTestResult(null);
      editForm.resetFields();
    } catch (error: any) {
      console.error('Failed to update cluster:', error);
      message.error(error?.data?.detail || 'Failed to update cluster');
    }
  };

  const [editTestResult, setEditTestResult] = useState<any>(null);

  const handleEditTestConnection = async () => {
    if (!editingCluster) return;
    try {
      const values = await editForm.validateFields();
      const connType = editingCluster.connection_type || 'token';

      const testPayload = {
        connection_type: connType,
        gadget_namespace: values.gadget_namespace,
        cluster_id: editingCluster.id,
        api_server_url: connType !== 'in-cluster' ? values.api_server_url : undefined,
        skip_tls_verify: connType !== 'in-cluster' ? (values.skip_tls_verify || false) : undefined,
        token: (connType !== 'in-cluster' && values.token?.trim()) ? values.token : undefined,
        ca_cert: (connType !== 'in-cluster' && values.ca_cert?.trim()) ? values.ca_cert : undefined,
      };

      const result = await testConnection(testPayload).unwrap();
      setEditTestResult(result);

      if (result.overall_status === 'success') {
        message.success('Connection test successful!');
      } else if (result.overall_status === 'partial') {
        message.warning('Partial success. Check the results for details.');
      } else {
        message.error('Connection test failed. Check the results for details.');
      }
    } catch (error: any) {
      console.error('Edit connection test failed:', error);
      message.error(error?.data?.detail || 'Connection test failed');
      setEditTestResult({
        overall_status: 'failed',
        cluster_connection: { status: 'failed', error: error?.data?.detail || 'Unknown error', details: {} },
        gadget_connection: { status: 'failed', error: null, details: {} },
        recommendations: ['Please check your connection parameters.']
      });
    }
  };

  const handleSync = async (record: ClusterData) => {
    try {
      setSyncingClusterId(record.id);
      const result = await syncCluster(record.id).unwrap();
      
      const beylaInfo = result.beyla_health ? ` | Beyla: ${result.beyla_health}` : '';
      if (result.status === 'completed' && result.resources) {
        message.success(`Cluster synced: ${result.resources.nodes} nodes, ${result.resources.pods} pods, ${result.resources.namespaces} namespaces`);
      } else if (result.status === 'partial') {
        message.warning(`Partial sync: ${result.warning || 'Cluster info unavailable'}. Gadget: ${result.gadget_health}${beylaInfo}`);
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
        const s = status || 'not_installed';
        const colorMap: Record<string, string> = {
          healthy: 'green',
          degraded: 'orange', 
          unhealthy: 'red',
          unknown: 'gray',
          not_installed: 'default',
        };
        const clusterVersion = record.gadget_version || '';
        const needsUpgrade = clusterVersion && supportedGadgetVersion && 
          compareVersions(clusterVersion, supportedGadgetVersion) < 0;
        return (
          <Space direction="vertical" size={2} style={{ textAlign: 'center', width: '100%' }}>
            <Tag color={colorMap[s] || 'default'} icon={s === 'healthy' ? <CheckCircleOutlined /> : s === 'not_installed' ? undefined : <CloseCircleOutlined />}>
              {s === 'not_installed' ? 'NOT INSTALLED' : s.toUpperCase()}
            </Tag>
            {record.gadget_version && s !== 'not_installed' && (
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
      title: 'Beyla Health',
      dataIndex: 'beyla_health_status',
      key: 'beyla_health_status',
      render: (status: string, record: ClusterData) => {
        const s = status || 'not_installed';
        const colorMap: Record<string, string> = {
          healthy: 'green',
          degraded: 'orange',
          unhealthy: 'red',
          unknown: 'gray',
          not_installed: 'default',
        };
        const clusterBeylaVer = record.beyla_version || '';
        const needsUpgrade = supportedBeylaVersion && clusterBeylaVer && clusterBeylaVer !== supportedBeylaVersion;
        return (
          <Space direction="vertical" size={2} style={{ textAlign: 'center', width: '100%' }}>
            <Tag color={colorMap[s] || 'default'} icon={s === 'healthy' ? <CheckCircleOutlined /> : s === 'not_installed' ? undefined : <CloseCircleOutlined />}>
              {s === 'not_installed' ? 'NOT INSTALLED' : s.toUpperCase()}
            </Tag>
            {clusterBeylaVer && s !== 'not_installed' && (
              <Typography.Text type={needsUpgrade ? 'warning' : 'secondary'} style={{ fontSize: '11px' }}>
                {clusterBeylaVer}{needsUpgrade ? ` → ${supportedBeylaVersion}` : ''}
              </Typography.Text>
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
      fixed: 'right' as const,
      width: 150,
      render: (record: ClusterData) => (
        <Space size={4} wrap>
          <Tooltip title="Sync cluster resources">
            <Button 
              type="link" 
              size="small"
              icon={syncingClusterId === record.id ? <LoadingOutlined spin /> : <SyncOutlined />}
              onClick={() => handleSync(record)}
              disabled={syncingClusterId === record.id}
            />
          </Tooltip>
          <Tooltip title="Agent Scripts">
            <Button 
              type="link" 
              size="small"
              icon={<ToolOutlined />}
              onClick={() => {
                setSetupClusterId(record.id);
                setSetupClusterName(record.name);
                setSelectedProvider(record.provider || 'kubernetes');
                setIsSetupModalOpen(true);
              }}
              style={{ color: '#0891b2' }}
            />
          </Tooltip>
          <Tooltip title="Edit cluster">
            <Button 
              type="link" 
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip title="Delete cluster">
            <Button 
              type="link" 
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  const handleAdd = () => {
    form.resetFields();
    setConnectionType('token');
    setSetupClusterId(undefined);
    setSetupClusterName(undefined);
    setIsModalVisible(true);
  };

  // Test connection before creating cluster
  const handleTestConnection = async () => {
    try {
      const fieldsToValidate =
        connectionType === 'in-cluster'
          ? ['gadget_namespace']
          : ['api_server_url', 'token', 'ca_cert', 'skip_tls_verify', 'gadget_namespace'];
      const values = await form.validateFields(fieldsToValidate);
      
      const testPayload = {
        connection_type: connectionType,
        gadget_namespace: values.gadget_namespace,
        ...(connectionType !== 'in-cluster'
          ? {
              api_server_url: values.api_server_url,
              token: values.token,
              ca_cert: values.ca_cert,
              skip_tls_verify: values.skip_tls_verify || false,
            }
          : {}),
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
        gadget_namespace: values.gadget_namespace,
        gadget_auto_detect: connectionType === 'in-cluster' ? values.gadget_auto_detect !== false : false,
        skip_tls_verify: values.skip_tls_verify || false,
        ...(values.beyla_namespace ? { beyla_namespace: values.beyla_namespace } : {}),
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
          scroll={{ x: 1100 }}
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `Total ${total} clusters`,
          }}
        />
      </Card>

      {/* Add Cluster Modal */}
      <Modal
        title={<Space><PlusOutlined /> Add remote cluster</Space>}
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setTestResult(null);
        }}
        width={740}
        footer={[
          <Button key="cancel" onClick={() => {
            setIsModalVisible(false);
            setTestResult(null);
          }}>
            Cancel
          </Button>,
          <Button 
            key="test" 
            icon={<ApiOutlined />}
            onClick={handleTestConnection}
            loading={testing}
          >
            Test connection
          </Button>,
          <Button 
            key="submit" 
            type="primary" 
            onClick={handleSubmit}
            loading={creating}
          >
            Add cluster
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
          {/* Step 1: Remote cluster setup scripts (first) */}
          <div style={{ 
            background: 'linear-gradient(135deg, #e6f7ff 0%, #f0f5ff 100%)',
            border: '1px solid #91caff',
            borderRadius: 10,
            padding: '20px 24px',
            marginBottom: 24
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div style={{ 
                background: '#0891b2', borderRadius: 8, padding: '8px 12px',
                color: '#fff', fontWeight: 700, fontSize: 14, flexShrink: 0
              }}>
                Step 1
              </div>
              <div style={{ flex: 1 }}>
                <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 6 }}>
                  Remote cluster setup scripts
                </Text>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  Scripts install agents on the cluster and print <strong>API Server URL</strong>, <strong>token</strong>, and <strong>CA certificate</strong>.
                  Copy those values into Step 2 below.
                </Text>
                <Button 
                  type="primary" 
                  size="large"
                  icon={<RocketOutlined />}
                  onClick={() => {
                    setSetupClusterId(undefined);
                    setSetupClusterName(undefined);
                    setIsSetupModalOpen(true);
                  }}
                >
                  Get agent setup scripts
                </Button>
              </div>
            </div>
          </div>

          {/* Step 2: Connection details from script output */}
          <div style={{ 
            background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 10,
            padding: '20px 24px', marginBottom: 24
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div style={{ 
                background: '#4d9f7c', borderRadius: 8, padding: '8px 12px',
                color: '#fff', fontWeight: 700, fontSize: 14, flexShrink: 0
              }}>
                Step 2
              </div>
              <Text strong style={{ fontSize: 15 }}>Paste connection details from script output</Text>
            </div>

            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  label="Cluster name"
                  name="name"
                  rules={[{ required: true, message: 'Required' }]}
                >
                  <Input placeholder="e.g., production-ocp-01" />
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  label="Environment"
                  name="environment"
                  rules={[{ required: true }]}
                  initialValue="production"
                >
                  <Select>
                    <Option value="production">Production</Option>
                    <Option value="staging">Staging</Option>
                    <Option value="development">Development</Option>
                    <Option value="testing">Testing</Option>
                  </Select>
                </Form.Item>
              </Col>
              <Col span={6}>
                <Form.Item
                  label="Provider"
                  name="provider"
                  rules={[{ required: true }]}
                  initialValue="openshift"
                  tooltip="Selects the default CLI in the generated setup scripts (oc for OpenShift, kubectl for everything else). The scripts auto-detect OpenShift at runtime via the security.openshift.io API and create the required SCCs even when run with kubectl, so an incorrect choice here will not break installation."
                >
                  <Select onChange={(value) => setSelectedProvider(value)}>
                    <Option value="openshift">OpenShift</Option>
                    <Option value="kubernetes">Kubernetes</Option>
                    <Option value="eks">AWS EKS</Option>
                    <Option value="gke">Google GKE</Option>
                    <Option value="aks">Azure AKS</Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>

            <Form.Item
              label="Description"
              name="description"
              style={{ marginBottom: 12 }}
            >
              <Input placeholder="Optional — e.g., primary production cluster" />
            </Form.Item>

            <Form.Item
              label="Region"
              name="region"
              style={{ marginBottom: 16 }}
            >
              <Input placeholder="Optional — e.g., us-east-1, eu-west-1" />
            </Form.Item>

            <Divider style={{ margin: '8px 0 16px' }} />

            <Form.Item label="Connection type" style={{ marginBottom: 12 }}>
              <Select 
                value={connectionType} 
                onChange={(value) => {
                  setConnectionType(value);
                  if (value === 'in-cluster') {
                    form.setFieldValue('api_server_url', 'https://kubernetes.default.svc');
                  } else {
                    form.setFieldValue('api_server_url', '');
                  }
                }}
              >
                <Option value="token">
                  <Space>
                    <KeyOutlined style={{ color: '#0891b2' }} />
                    Service account token
                    <Tag color="blue" style={{ fontSize: 10 }}>Default</Tag>
                  </Space>
                </Option>
                <Option value="in-cluster">
                  <Space>
                    <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
                    In-cluster (Flowfish runs on this cluster)
                  </Space>
                </Option>
                <Option value="kubeconfig">
                  <Space>
                    <FileOutlined style={{ color: '#7c8eb5' }} />
                    Kubeconfig file
                  </Space>
                </Option>
              </Select>
            </Form.Item>

            <Form.Item
              label="API server URL"
              name="api_server_url"
              rules={[
                { required: true, message: 'Required — shown in setup script output' },
                { pattern: /^https?:\/\/.+/, message: 'Must start with http:// or https://' }
              ]}
              initialValue={connectionType === 'in-cluster' ? 'https://kubernetes.default.svc' : ''}
            >
              <Input 
                placeholder={connectionType === 'in-cluster' 
                  ? 'https://kubernetes.default.svc' 
                  : 'https://api.cluster-name.example.com:6443'
                }
                prefix={<CloudServerOutlined style={{ color: '#bfbfbf' }} />}
              />
            </Form.Item>

            {connectionType === 'kubeconfig' && (
              <Form.Item
                label="Kubeconfig content"
                name="kubeconfig"
                rules={[{ required: true, message: 'Required' }]}
              >
                <TextArea rows={6} placeholder="apiVersion: v1&#10;kind: Config&#10;clusters:..." />
              </Form.Item>
            )}

            {connectionType === 'token' && (
              <>
                <Form.Item
                  label="Service account token"
                  name="token"
                  rules={[{ required: true, message: 'Required — shown in setup script output' }]}
                >
                  <TextArea 
                    rows={3}
                    placeholder="Paste the token from setup script output"
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </Form.Item>

                <Form.Item
                  label={<Space><span>CA certificate</span><Tag color="default" style={{ fontSize: 10 }}>Optional</Tag></Space>}
                  name="ca_cert"
                >
                  <TextArea 
                    rows={3}
                    placeholder="Paste the CA cert from setup script output (optional)"
                    style={{ fontFamily: 'monospace', fontSize: 12 }}
                  />
                </Form.Item>
              </>
            )}

            <Form.Item name="skip_tls_verify" valuePropName="checked" style={{ marginBottom: 0 }}>
              <Checkbox>Skip TLS verification</Checkbox>
            </Form.Item>
          </div>

          {/* Step 3: Agent namespaces (L4 + optional L7 Beyla) */}
          <div style={{ 
            background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 10,
            padding: '20px 24px', marginBottom: 8
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div style={{ 
                background: '#722ed1', borderRadius: 8, padding: '8px 12px',
                color: '#fff', fontWeight: 700, fontSize: 14, flexShrink: 0
              }}>
                Step 3
              </div>
              <Text strong style={{ fontSize: 15 }}>Agent namespaces</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>(defaults match the setup scripts)</Text>
            </div>

            <Row gutter={16}>
              <Col span={12}>
                <div style={{ 
                  background: '#f6ffed', border: '1px solid #d9f7be', borderRadius: 8,
                  padding: '12px 16px 4px'
                }}>
                  <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                    <HddOutlined style={{ color: '#4d9f7c', marginRight: 4 }} />
                    Network-level (L4)
                  </Text>
                  <Form.Item
                    name="gadget_namespace"
                    initialValue="flowfish"
                    rules={[{ required: true, message: 'Required' }]}
                    style={{ marginBottom: 8 }}
                    label={<Text type="secondary" style={{ fontSize: 11 }}>Inspector Gadget namespace</Text>}
                  >
                    <Input placeholder="e.g., flowfish" prefix={<HddOutlined style={{ color: '#b7eb8f' }} />} />
                  </Form.Item>
                </div>
              </Col>
              <Col span={12}>
                <div style={{ 
                  background: '#f9f0ff', border: '1px solid #d3adf7', borderRadius: 8,
                  padding: '12px 16px 4px'
                }}>
                  <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
                    <ApiOutlined style={{ color: '#722ed1', marginRight: 4 }} />
                    Application-level (L7)
                    <Tag color="default" style={{ marginLeft: 6, fontSize: 9 }}>Optional</Tag>
                  </Text>
                  <Form.Item
                    name="beyla_namespace"
                    style={{ marginBottom: 8 }}
                    label={<Text type="secondary" style={{ fontSize: 11 }}>Beyla / L7 collector namespace</Text>}
                  >
                    <Input placeholder="e.g., flowfish-l7" prefix={<ApiOutlined style={{ color: '#d3adf7' }} />} />
                  </Form.Item>
                </div>
              </Col>
            </Row>

            {connectionType === 'in-cluster' && (
              <Form.Item
                name="gadget_auto_detect"
                valuePropName="checked"
                initialValue={true}
                style={{ marginTop: 12, marginBottom: 0 }}
              >
                <Checkbox>Auto-detect Inspector Gadget deployment</Checkbox>
              </Form.Item>
            )}
          </div>
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
        onCancel={() => {
          setIsEditModalVisible(false);
          setEditingCluster(null);
          setEditTestResult(null);
          editForm.resetFields();
        }}
        width={720}
        footer={[
          <Button key="cancel" onClick={() => {
            setIsEditModalVisible(false);
            setEditingCluster(null);
            setEditTestResult(null);
            editForm.resetFields();
          }}>
            Cancel
          </Button>,
          <Button
            key="test"
            icon={<ApiOutlined />}
            onClick={handleEditTestConnection}
            loading={testing}
          >
            Test Connection
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={handleEditSubmit}
            loading={updating}
          >
            Save Changes
          </Button>,
        ]}
      >
        {editTestResult && (
          <Alert
            type={editTestResult.overall_status === 'success' ? 'success' :
                  editTestResult.overall_status === 'partial' ? 'warning' : 'error'}
            message={
              <Space>
                {editTestResult.overall_status === 'success' ? (
                  <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
                ) : editTestResult.overall_status === 'partial' ? (
                  <WarningOutlined style={{ color: '#c9a55a' }} />
                ) : (
                  <CloseCircleOutlined style={{ color: '#f76e6e' }} />
                )}
                <Text strong>
                  Connection Test: {editTestResult.overall_status.toUpperCase()}
                </Text>
              </Space>
            }
            description={
              <div style={{ marginTop: 8 }}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <div>
                    <Text type="secondary">Cluster: </Text>
                    <Tag color={editTestResult.cluster_connection?.status === 'success' ? 'green' : 'red'}>
                      {editTestResult.cluster_connection?.status}
                    </Tag>
                    {editTestResult.cluster_connection?.details?.k8s_version && (
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        K8s {editTestResult.cluster_connection.details.k8s_version}
                      </Text>
                    )}
                    {editTestResult.cluster_connection?.error && (
                      <Text type="danger" style={{ display: 'block', fontSize: 12 }}>
                        {editTestResult.cluster_connection.error}
                      </Text>
                    )}
                  </div>
                  <div>
                    <Text type="secondary">Inspector Gadget: </Text>
                    <Tag color={
                      editTestResult.gadget_connection?.status === 'success' ? 'green' :
                      editTestResult.gadget_connection?.status === 'warning' ? 'orange' :
                      editTestResult.gadget_connection?.status === 'skipped' ? 'default' : 'red'
                    }>
                      {editTestResult.gadget_connection?.status}
                    </Tag>
                    {editTestResult.gadget_connection?.details?.version && (
                      <Text type="secondary" style={{ marginLeft: 8 }}>
                        v{editTestResult.gadget_connection.details.version}
                      </Text>
                    )}
                    {editTestResult.gadget_connection?.error && (
                      <Text type="danger" style={{ display: 'block', fontSize: 12 }}>
                        {editTestResult.gadget_connection.error}
                      </Text>
                    )}
                  </div>
                  {editTestResult.recommendations?.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text strong style={{ fontSize: 12 }}>Recommendations:</Text>
                      <ul style={{ margin: '4px 0 0 20px', padding: 0 }}>
                        {editTestResult.recommendations.map((rec: string, idx: number) => (
                          <li key={idx} style={{ fontSize: 12 }}>{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Space>
              </div>
            }
            showIcon={false}
            closable
            onClose={() => setEditTestResult(null)}
            style={{ marginBottom: 16 }}
          />
        )}
        <Form
          form={editForm}
          layout="vertical"
          style={{ marginTop: 16 }}
        >
          <div style={{ 
            background: 'linear-gradient(135deg, #e6f7ff 0%, #f0f5ff 100%)',
            border: '1px solid #91caff',
            borderRadius: 10,
            padding: '16px 20px',
            marginBottom: 20
          }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div style={{ 
                background: '#0891b2', borderRadius: 8, padding: '6px 10px',
                color: '#fff', fontWeight: 700, fontSize: 13, flexShrink: 0
              }}>
                Step 1
              </div>
              <div style={{ flex: 1 }}>
                <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 6 }}>
                  Remote cluster setup scripts
                </Text>
                <Text type="secondary" style={{ display: 'block', marginBottom: 10, fontSize: 13 }}>
                  Install or upgrade Inspector Gadget and Beyla (L7), or run uninstall scripts. Uses this cluster when generating scripts.
                </Text>
                <Button
                  type="primary"
                  icon={<RocketOutlined />}
                  onClick={() => {
                    if (editingCluster) {
                      setSetupClusterId(editingCluster.id);
                      setSetupClusterName(editingCluster.name);
                      setSelectedProvider(editingCluster.provider || 'kubernetes');
                    }
                    setIsSetupModalOpen(true);
                  }}
                >
                  Get agent setup scripts
                </Button>
              </div>
            </div>
          </div>

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
                tooltip="Selects the default CLI in the generated setup scripts (oc for OpenShift, kubectl for everything else). The scripts auto-detect OpenShift at runtime via the security.openshift.io API and create the required SCCs even when run with kubectl, so an incorrect choice here will not break installation."
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

          <Row gutter={16}>
            <Col span={12}>
              <div style={{ background: '#f6ffed', border: '1px solid #d9f7be', borderRadius: 8, padding: '10px 14px 2px' }}>
                <Text strong style={{ display: 'block', marginBottom: 6, fontSize: 12 }}>
                  <HddOutlined style={{ color: '#4d9f7c', marginRight: 4 }} />
                  Network-level (L4)
                </Text>
                <Form.Item
                  name="gadget_namespace"
                  rules={[{ required: true, message: 'Required' }]}
                  style={{ marginBottom: 6 }}
                  label={<Text type="secondary" style={{ fontSize: 11 }}>Inspector Gadget namespace</Text>}
                >
                  <Input placeholder="e.g., flowfish" prefix={<HddOutlined style={{ color: '#b7eb8f' }} />} />
                </Form.Item>
              </div>
            </Col>
            <Col span={12}>
              <div style={{ background: '#f9f0ff', border: '1px solid #d3adf7', borderRadius: 8, padding: '10px 14px 2px' }}>
                <Text strong style={{ display: 'block', marginBottom: 6, fontSize: 12 }}>
                  <ApiOutlined style={{ color: '#722ed1', marginRight: 4 }} />
                  Application-level (L7)
                  <Tag color="default" style={{ marginLeft: 6, fontSize: 9 }}>Optional</Tag>
                </Text>
                <Form.Item
                  name="beyla_namespace"
                  style={{ marginBottom: 6 }}
                  label={<Text type="secondary" style={{ fontSize: 11 }}>Beyla / L7 collector namespace</Text>}
                >
                  <Input placeholder="e.g., flowfish-l7" prefix={<ApiOutlined style={{ color: '#d3adf7' }} />} />
                </Form.Item>
              </div>
            </Col>
          </Row>

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
        onClose={() => {
          setIsSetupModalOpen(false);
          setSetupClusterId(undefined);
          setSetupClusterName(undefined);
        }}
        provider={selectedProvider}
        clusterId={setupClusterId}
        clusterName={setupClusterName}
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
