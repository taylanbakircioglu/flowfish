import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  Select,
  Button,
  Space,
  Typography,
  Divider,
  Tag,
  Collapse,
  Switch,
  InputNumber,
  Row,
  Col,
  Alert,
  Tooltip,
  Badge,
  message,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  SafetyCertificateOutlined,
  GlobalOutlined,
  LockOutlined,
  UnlockOutlined,
  CopyOutlined,
  DownloadOutlined,
  EyeOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import type {
  NetworkPolicySpec,
  NetworkPolicyRule,
  NetworkPolicyPeer,
  NetworkPolicyPort,
  LabelSelector,
} from '../store/api/simulationApi';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;
const { TextArea } = Input;

// =============================================================================
// Types
// =============================================================================

interface NetworkPolicyBuilderProps {
  targetNamespace: string;
  targetWorkload: string;
  initialSpec?: NetworkPolicySpec;
  onSpecChange?: (spec: NetworkPolicySpec) => void;
  onPreview?: (spec: NetworkPolicySpec) => void;
  onGenerate?: () => void;
  generatedYaml?: string;
  isLoading?: boolean;
  showYamlPreview?: boolean;
}

interface RuleFormData {
  id: string;
  type: 'ingress' | 'egress';
  namespaceLabels: Record<string, string>;
  podLabels: Record<string, string>;
  ipBlock?: string;
  ipExcept?: string[];
  ports: Array<{ protocol: string; port?: number }>;
}

// =============================================================================
// Helper Functions
// =============================================================================

const generateRuleId = () => `rule-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

const defaultRule = (type: 'ingress' | 'egress'): RuleFormData => ({
  id: generateRuleId(),
  type,
  namespaceLabels: {},
  podLabels: {},
  ports: [{ protocol: 'TCP', port: undefined }],
});

const rulesToSpec = (rules: RuleFormData[], targetNamespace: string, targetWorkload: string): NetworkPolicySpec => {
  const ingressRules: NetworkPolicyRule[] = [];
  const egressRules: NetworkPolicyRule[] = [];

  rules.forEach(rule => {
    const peers: NetworkPolicyPeer[] = [];
    
    // Add namespace/pod selector peer
    if (Object.keys(rule.namespaceLabels).length > 0 || Object.keys(rule.podLabels).length > 0) {
      const peer: NetworkPolicyPeer = {};
      if (Object.keys(rule.namespaceLabels).length > 0) {
        peer.namespace_selector = { match_labels: rule.namespaceLabels };
      }
      if (Object.keys(rule.podLabels).length > 0) {
        peer.pod_selector = { match_labels: rule.podLabels };
      }
      peers.push(peer);
    }
    
    // Add IP block peer
    if (rule.ipBlock) {
      peers.push({
        ip_block: {
          cidr: rule.ipBlock,
          except: rule.ipExcept?.filter(ip => ip.trim()) || undefined,
        },
      });
    }

    const ports: NetworkPolicyPort[] = rule.ports
      .filter(p => p.port !== undefined)
      .map(p => ({
        protocol: p.protocol,
        port: p.port,
      }));

    const policyRule: NetworkPolicyRule = {
      rule_type: rule.type,
      action: 'allow',
      peers: peers.length > 0 ? peers : undefined,
      ports: ports.length > 0 ? ports : undefined,
    };

    if (rule.type === 'ingress') {
      ingressRules.push(policyRule);
    } else {
      egressRules.push(policyRule);
    }
  });

  return {
    policy_name: `${targetWorkload}-network-policy`,
    target_namespace: targetNamespace,
    target_pod_selector: {
      match_labels: { app: targetWorkload },
    },
    policy_types: [
      ...(ingressRules.length > 0 ? ['ingress' as const] : []),
      ...(egressRules.length > 0 ? ['egress' as const] : []),
    ],
    ingress_rules: ingressRules.length > 0 ? ingressRules : undefined,
    egress_rules: egressRules.length > 0 ? egressRules : undefined,
  };
};

// =============================================================================
// Sub-Components
// =============================================================================

interface LabelEditorProps {
  labels: Record<string, string>;
  onChange: (labels: Record<string, string>) => void;
  placeholder?: string;
}

const LabelEditor: React.FC<LabelEditorProps> = ({ labels, onChange, placeholder }) => {
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  const addLabel = () => {
    if (newKey.trim() && newValue.trim()) {
      onChange({ ...labels, [newKey.trim()]: newValue.trim() });
      setNewKey('');
      setNewValue('');
    }
  };

  const removeLabel = (key: string) => {
    const newLabels = { ...labels };
    delete newLabels[key];
    onChange(newLabels);
  };

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        {Object.entries(labels).map(([key, value]) => (
          <Tag
            key={key}
            closable
            onClose={() => removeLabel(key)}
            color="blue"
          >
            {key}: {value}
          </Tag>
        ))}
      </Space>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          placeholder="Key"
          value={newKey}
          onChange={e => setNewKey(e.target.value)}
          style={{ width: '40%' }}
          size="small"
        />
        <Input
          placeholder="Value"
          value={newValue}
          onChange={e => setNewValue(e.target.value)}
          style={{ width: '40%' }}
          size="small"
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={addLabel}
          size="small"
          disabled={!newKey.trim() || !newValue.trim()}
        />
      </Space.Compact>
      {placeholder && Object.keys(labels).length === 0 && (
        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
          {placeholder}
        </Text>
      )}
    </div>
  );
};

interface RuleEditorProps {
  rule: RuleFormData;
  onChange: (rule: RuleFormData) => void;
  onDelete: () => void;
}

const RuleEditor: React.FC<RuleEditorProps> = ({ rule, onChange, onDelete }) => {
  const updateRule = (updates: Partial<RuleFormData>) => {
    onChange({ ...rule, ...updates });
  };

  const addPort = () => {
    updateRule({
      ports: [...rule.ports, { protocol: 'TCP', port: undefined }],
    });
  };

  const updatePort = (index: number, updates: Partial<{ protocol: string; port?: number }>) => {
    const newPorts = [...rule.ports];
    newPorts[index] = { ...newPorts[index], ...updates };
    updateRule({ ports: newPorts });
  };

  const removePort = (index: number) => {
    updateRule({
      ports: rule.ports.filter((_, i) => i !== index),
    });
  };

  return (
    <Card
      size="small"
      style={{ marginBottom: 12, borderLeft: `3px solid ${rule.type === 'ingress' ? '#4d9f7c' : '#0891b2'}` }}
      extra={
        <Button
          type="text"
          danger
          icon={<DeleteOutlined />}
          onClick={onDelete}
          size="small"
        />
      }
      title={
        <Space>
          {rule.type === 'ingress' ? (
            <Tag color="green" icon={<LockOutlined />}>INGRESS</Tag>
          ) : (
            <Tag color="blue" icon={<UnlockOutlined />}>EGRESS</Tag>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            {rule.type === 'ingress' ? 'Allow traffic FROM' : 'Allow traffic TO'}
          </Text>
        </Space>
      }
    >
      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Namespace Selector</Text>
          <LabelEditor
            labels={rule.namespaceLabels}
            onChange={labels => updateRule({ namespaceLabels: labels })}
            placeholder="e.g., kubernetes.io/metadata.name: production"
          />
        </Col>
        <Col span={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Pod Selector</Text>
          <LabelEditor
            labels={rule.podLabels}
            onChange={labels => updateRule({ podLabels: labels })}
            placeholder="e.g., app: frontend"
          />
        </Col>
      </Row>

      <Divider style={{ margin: '12px 0' }} />

      <Row gutter={[16, 16]}>
        <Col span={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>IP Block (CIDR)</Text>
          <Input
            placeholder="e.g., 10.0.0.0/24"
            value={rule.ipBlock || ''}
            onChange={e => updateRule({ ipBlock: e.target.value || undefined })}
            size="small"
          />
        </Col>
        <Col span={12}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Ports</Text>
          <Space direction="vertical" style={{ width: '100%' }}>
            {rule.ports.map((port, index) => (
              <Space.Compact key={index} style={{ width: '100%' }}>
                <Select
                  value={port.protocol}
                  onChange={value => updatePort(index, { protocol: value })}
                  style={{ width: 80 }}
                  size="small"
                >
                  <Option value="TCP">TCP</Option>
                  <Option value="UDP">UDP</Option>
                  <Option value="SCTP">SCTP</Option>
                </Select>
                <InputNumber
                  placeholder="Port"
                  value={port.port}
                  onChange={value => updatePort(index, { port: value || undefined })}
                  min={1}
                  max={65535}
                  style={{ width: 100 }}
                  size="small"
                />
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => removePort(index)}
                  size="small"
                  disabled={rule.ports.length <= 1}
                />
              </Space.Compact>
            ))}
            <Button
              type="dashed"
              icon={<PlusOutlined />}
              onClick={addPort}
              size="small"
              block
            >
              Add Port
            </Button>
          </Space>
        </Col>
      </Row>
    </Card>
  );
};

// =============================================================================
// Main Component
// =============================================================================

const NetworkPolicyBuilder: React.FC<NetworkPolicyBuilderProps> = ({
  targetNamespace,
  targetWorkload,
  initialSpec,
  onSpecChange,
  onPreview,
  onGenerate,
  generatedYaml,
  isLoading = false,
  showYamlPreview = true,
}) => {
  const [rules, setRules] = useState<RuleFormData[]>([]);
  const [includeDns, setIncludeDns] = useState(true);
  const [strictMode, setStrictMode] = useState(false);
  const [activeTab, setActiveTab] = useState<'builder' | 'yaml'>('builder');

  // Initialize rules from initial spec
  useEffect(() => {
    if (initialSpec) {
      const loadedRules: RuleFormData[] = [];
      
      initialSpec.ingress_rules?.forEach(rule => {
        const ruleData: RuleFormData = {
          id: generateRuleId(),
          type: 'ingress',
          namespaceLabels: rule.peers?.[0]?.namespace_selector?.match_labels || {},
          podLabels: rule.peers?.[0]?.pod_selector?.match_labels || {},
          ipBlock: rule.peers?.find(p => p.ip_block)?.ip_block?.cidr,
          ports: rule.ports?.map(p => ({ protocol: p.protocol, port: p.port })) || [{ protocol: 'TCP' }],
        };
        loadedRules.push(ruleData);
      });

      initialSpec.egress_rules?.forEach(rule => {
        const ruleData: RuleFormData = {
          id: generateRuleId(),
          type: 'egress',
          namespaceLabels: rule.peers?.[0]?.namespace_selector?.match_labels || {},
          podLabels: rule.peers?.[0]?.pod_selector?.match_labels || {},
          ipBlock: rule.peers?.find(p => p.ip_block)?.ip_block?.cidr,
          ports: rule.ports?.map(p => ({ protocol: p.protocol, port: p.port })) || [{ protocol: 'TCP' }],
        };
        loadedRules.push(ruleData);
      });

      setRules(loadedRules);
    }
  }, [initialSpec]);

  // Build spec from rules
  const currentSpec = useMemo(() => {
    return rulesToSpec(rules, targetNamespace, targetWorkload);
  }, [rules, targetNamespace, targetWorkload]);

  // Notify parent of spec changes
  useEffect(() => {
    onSpecChange?.(currentSpec);
  }, [currentSpec, onSpecChange]);

  const addRule = (type: 'ingress' | 'egress') => {
    setRules([...rules, defaultRule(type)]);
  };

  const updateRule = (id: string, updatedRule: RuleFormData) => {
    setRules(rules.map(r => r.id === id ? updatedRule : r));
  };

  const deleteRule = (id: string) => {
    setRules(rules.filter(r => r.id !== id));
  };

  const copyYaml = () => {
    if (generatedYaml) {
      navigator.clipboard.writeText(generatedYaml);
      message.success('YAML copied to clipboard');
    }
  };

  const downloadYaml = () => {
    if (generatedYaml) {
      const blob = new Blob([generatedYaml], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${targetWorkload}-network-policy.yaml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('YAML downloaded');
    }
  };

  const ingressRules = rules.filter(r => r.type === 'ingress');
  const egressRules = rules.filter(r => r.type === 'egress');

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <SafetyCertificateOutlined style={{ fontSize: 20, color: '#0891b2' }} />
          <div>
            <Text strong>Network Policy Builder</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Target: <Tag color="blue">{targetNamespace}/{targetWorkload}</Tag>
            </Text>
          </div>
        </Space>
      </div>

      {/* Options */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={24}>
          <Col span={12}>
            <Space>
              <Switch
                checked={includeDns}
                onChange={setIncludeDns}
                size="small"
              />
              <Text>Include DNS egress (kube-dns:53)</Text>
              <Tooltip title="Automatically allow DNS queries to kube-dns">
                <GlobalOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          </Col>
          <Col span={12}>
            <Space>
              <Switch
                checked={strictMode}
                onChange={setStrictMode}
                size="small"
              />
              <Text>Strict mode (deny by default)</Text>
              <Tooltip title="Generate deny-all rules for traffic not explicitly allowed">
                <LockOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* Tab Buttons */}
      <Space style={{ marginBottom: 16 }}>
        <Button
          type={activeTab === 'builder' ? 'primary' : 'default'}
          onClick={() => setActiveTab('builder')}
          icon={<SafetyCertificateOutlined />}
        >
          Rule Builder
        </Button>
        <Button
          type={activeTab === 'yaml' ? 'primary' : 'default'}
          onClick={() => setActiveTab('yaml')}
          icon={<CodeOutlined />}
          disabled={!generatedYaml}
        >
          YAML Preview
        </Button>
      </Space>

      {activeTab === 'builder' && (
        <>
          {/* Ingress Rules */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Space>
                <Badge count={ingressRules.length} style={{ backgroundColor: '#4d9f7c' }}>
                  <Tag color="green" icon={<LockOutlined />}>Ingress Rules</Tag>
                </Badge>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Control incoming traffic
                </Text>
              </Space>
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => addRule('ingress')}
                size="small"
              >
                Add Ingress Rule
              </Button>
            </div>
            
            {ingressRules.length === 0 ? (
              <Alert
                message="No ingress rules defined"
                description="All incoming traffic will be allowed unless you add rules."
                type="info"
                showIcon
              />
            ) : (
              ingressRules.map(rule => (
                <RuleEditor
                  key={rule.id}
                  rule={rule}
                  onChange={updated => updateRule(rule.id, updated)}
                  onDelete={() => deleteRule(rule.id)}
                />
              ))
            )}
          </div>

          {/* Egress Rules */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <Space>
                <Badge count={egressRules.length} style={{ backgroundColor: '#0891b2' }}>
                  <Tag color="blue" icon={<UnlockOutlined />}>Egress Rules</Tag>
                </Badge>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Control outgoing traffic
                </Text>
              </Space>
              <Button
                type="dashed"
                icon={<PlusOutlined />}
                onClick={() => addRule('egress')}
                size="small"
              >
                Add Egress Rule
              </Button>
            </div>
            
            {egressRules.length === 0 ? (
              <Alert
                message="No egress rules defined"
                description="All outgoing traffic will be allowed unless you add rules."
                type="info"
                showIcon
              />
            ) : (
              egressRules.map(rule => (
                <RuleEditor
                  key={rule.id}
                  rule={rule}
                  onChange={updated => updateRule(rule.id, updated)}
                  onDelete={() => deleteRule(rule.id)}
                />
              ))
            )}
          </div>

          {/* Action Buttons */}
          <Space>
            {onGenerate && (
              <Button
                type="primary"
                icon={<SafetyCertificateOutlined />}
                onClick={onGenerate}
                loading={isLoading}
              >
                Generate from Traffic
              </Button>
            )}
            {onPreview && rules.length > 0 && (
              <Button
                icon={<EyeOutlined />}
                onClick={() => onPreview(currentSpec)}
                loading={isLoading}
              >
                Preview Impact
              </Button>
            )}
          </Space>
        </>
      )}

      {activeTab === 'yaml' && generatedYaml && (
        <Card
          title="Generated NetworkPolicy YAML"
          extra={
            <Space>
              <Button
                icon={<CopyOutlined />}
                onClick={copyYaml}
                size="small"
              >
                Copy
              </Button>
              <Button
                icon={<DownloadOutlined />}
                onClick={downloadYaml}
                size="small"
              >
                Download
              </Button>
            </Space>
          }
        >
          <pre
            style={{
              backgroundColor: '#1e1e1e',
              color: '#d4d4d4',
              padding: 16,
              borderRadius: 4,
              overflow: 'auto',
              maxHeight: 400,
              fontSize: 12,
              fontFamily: 'Monaco, Menlo, monospace',
            }}
          >
            {generatedYaml}
          </pre>
        </Card>
      )}
    </div>
  );
};

export default NetworkPolicyBuilder;

