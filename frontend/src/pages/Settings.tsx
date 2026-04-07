/**
 * System Settings Page
 * Enterprise configuration with multiple settings categories
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTheme } from '../contexts/ThemeContext';
import { 
  Card, 
  Form, 
  InputNumber, 
  Switch, 
  Button, 
  message, 
  Spin, 
  Alert, 
  Select, 
  Divider, 
  Typography,
  Space,
  Row,
  Col,
  Tooltip,
  Input,
  Tabs,
  Tag,
  Badge,
  Collapse,
  Statistic,
  Progress,
  List,
  Modal,
  Table,
  Popconfirm,
  Checkbox
} from 'antd';
import { 
  SettingOutlined, 
  ClockCircleOutlined, 
  SaveOutlined,
  InfoCircleOutlined,
  LockOutlined,
  MailOutlined,
  BellOutlined,
  DatabaseOutlined,
  SafetyOutlined,
  ApiOutlined,
  CloudServerOutlined,
  DeleteOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ThunderboltOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  SendOutlined,
  HistoryOutlined,
  SecurityScanOutlined,
  GlobalOutlined,
  TeamOutlined,
  BgColorsOutlined,
  BulbOutlined,
  BulbFilled,
  FormatPainterOutlined,
  FontSizeOutlined,
  LayoutOutlined,
  AlertOutlined,
  PlusOutlined,
  EditOutlined,
  WarningOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  SlackOutlined,
  MessageOutlined,
  DownloadOutlined,
  RollbackOutlined,
  KeyOutlined,
  CopyOutlined
} from '@ant-design/icons';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { TabPane } = Tabs;
const { Panel } = Collapse;
const { Password } = Input;

// ================== INTERFACES ==================

interface AnalysisLimits {
  continuous_auto_stop_enabled: boolean;
  default_continuous_duration_minutes: number;
  max_allowed_duration_minutes: number;
  warning_before_minutes: number;
  ingestion_rate_limit_per_second: number;
  updated_at?: string;
  updated_by?: number;
}

interface SMTPSettings {
  enabled: boolean;
  host: string;
  port: number;
  username: string;
  password: string;
  from_email: string;
  from_name: string;
  use_tls: boolean;
  use_ssl: boolean;
}

interface NotificationSettings {
  email_enabled: boolean;
  email_on_analysis_complete: boolean;
  email_on_analysis_error: boolean;
  email_on_anomaly_detected: boolean;
  email_on_scheduled_report: boolean;
  slack_enabled: boolean;
  slack_webhook_url: string;
  slack_channel: string;
  in_app_enabled: boolean;
}

interface DataRetentionSettings {
  events_retention_days: number;
  network_flows_retention_days: number;
  dns_queries_retention_days: number;
  process_events_retention_days: number;
  analysis_retention_days: number;
  auto_cleanup_enabled: boolean;
  cleanup_schedule: string;
}

interface SecuritySettings {
  session_timeout_minutes: number;
  max_login_attempts: number;
  lockout_duration_minutes: number;
  password_min_length: number;
  password_require_uppercase: boolean;
  password_require_numbers: boolean;
  password_require_special: boolean;
  two_factor_enabled: boolean;
  two_factor_required_for_all: boolean;
  two_factor_code_expiry_minutes: number;
  allowed_ip_ranges: string;
  api_rate_limit_per_minute: number;
}

interface SystemInfo {
  version: string;
  database_size: string;
  events_count: number;
  uptime: string;
  last_backup: string;
  clickhouse_status: string;
  rabbitmq_status: string;
  neo4j_status: string;
}

interface AppearanceSettings {
  theme: 'light' | 'dark' | 'system';
  primaryColor: string;
  fontSize: 'small' | 'medium' | 'large';
  compactMode: boolean;
  sidebarCollapsed: boolean;
}

interface AlertRule {
  id: number;
  name: string;
  description: string;
  condition_type: 'threshold' | 'anomaly' | 'pattern' | 'absence';
  metric: string;
  operator: 'gt' | 'lt' | 'eq' | 'gte' | 'lte' | 'contains';
  threshold: number;
  duration_minutes: number;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  enabled: boolean;
  notification_channels: string[];
  cooldown_minutes: number;
  created_at?: string;
  last_triggered?: string;
  trigger_count?: number;
}

interface APIToken {
  id: number;
  key_id: string;
  key_prefix: string;
  name: string;
  description?: string;
  scopes: string[];
  cluster_ids?: number[] | null;
  expires_at: string | null;
  created_at: string;
  last_used_at: string | null;
  last_used_ip?: string | null;
  usage_count: number;
  is_active: boolean;
  created_by: string;
}

interface PipelineCluster {
  id: number;
  name: string;
  environment: string;
  status: string;
}

interface IntegrationSettings {
  slack_enabled: boolean;
  slack_webhook_url: string;
  slack_channel: string;
  teams_enabled: boolean;
  teams_webhook_url: string;
  pagerduty_enabled: boolean;
  pagerduty_api_key: string;
  pagerduty_service_id: string;
  webhook_enabled: boolean;
  webhook_url: string;
  webhook_secret: string;
}

// ================== MAIN COMPONENT ==================

const Settings: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(() => searchParams.get('tab') || 'general');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const tab = searchParams.get('tab') || 'general';
    setActiveTab(prev => prev !== tab ? tab : prev);
  }, [searchParams]);
  const [saving, setSaving] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);
  
  // Theme context
  const { themeMode, isDark, setThemeMode, primaryColor, setPrimaryColor } = useTheme();
  
  // Appearance settings (non-theme related)
  const [appearanceSettings, setAppearanceSettings] = useState<AppearanceSettings>({
    theme: 'light',
    primaryColor: '#667eea',
    fontSize: 'medium',
    compactMode: false,
    sidebarCollapsed: false
  });
  
  // Forms
  const [analysisForm] = Form.useForm();
  const [smtpForm] = Form.useForm();
  const [notificationForm] = Form.useForm();
  const [retentionForm] = Form.useForm();
  const [securityForm] = Form.useForm();
  const [alertRuleForm] = Form.useForm();
  const [integrationForm] = Form.useForm();
  
  // Alert Rules State
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertRulesLoading, setAlertRulesLoading] = useState(false);
  const [alertRuleModalVisible, setAlertRuleModalVisible] = useState(false);
  const [editingAlertRule, setEditingAlertRule] = useState<AlertRule | null>(null);
  const [savingAlertRule, setSavingAlertRule] = useState(false);
  
  // API Token State
  const [apiTokens, setApiTokens] = useState<APIToken[]>([]);
  const [apiTokensLoading, setApiTokensLoading] = useState(false);
  const [apiTokenModalVisible, setApiTokenModalVisible] = useState(false);
  const [newlyCreatedToken, setNewlyCreatedToken] = useState<string | null>(null);
  
  // Pipeline Clusters State
  const [pipelineClusters, setPipelineClusters] = useState<PipelineCluster[]>([]);
  const [pipelineClustersLoading, setPipelineClustersLoading] = useState(false);
  const [creatingToken, setCreatingToken] = useState(false);
  const [apiTokenForm] = Form.useForm();
  
  // Audit Logs State
  interface AuditLog {
    id: string;
    timestamp: string;
    user: string;
    action: string;
    resource_type: string;
    resource_id: string;
    details: string;
    ip_address: string;
    status: 'success' | 'failure';
  }
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [auditLogsLoading, setAuditLogsLoading] = useState(false);
  const [auditLogFilter, setAuditLogFilter] = useState<string>('all');
  const [auditLogSearch, setAuditLogSearch] = useState<string>('');
  
  // Backup/Restore State
  interface BackupInfo {
    id: string;
    name: string;
    created_at: string;
    size: string;
    type: 'full' | 'config' | 'data';
    status: 'completed' | 'in_progress' | 'failed';
  }
  const [backups, setBackups] = useState<BackupInfo[]>([]);
  const [backupsLoading, setBackupsLoading] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [restoringBackup, setRestoringBackup] = useState<string | null>(null);
  
  // System Info
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({
    version: '1.0.0',
    database_size: '0 GB',
    events_count: 0,
    uptime: '0 days',
    last_backup: 'Never',
    clickhouse_status: 'unknown',
    rabbitmq_status: 'unknown',
    neo4j_status: 'unknown'
  });
  
  // ================== EFFECTS ==================
  
  useEffect(() => {
    checkAdminRole();
    fetchAllSettings();
    fetchSystemInfo();
    loadAppearanceSettings();
    fetchApiTokens();
    fetchPipelineClusters();
  }, []);
  
  // Load appearance settings from localStorage
  const loadAppearanceSettings = () => {
    try {
      const saved = localStorage.getItem('flowfish_appearance');
      if (saved) {
        const parsed = JSON.parse(saved);
        setAppearanceSettings(parsed);
      }
    } catch {
      // Use defaults
    }
  };
  
  // Handle theme change - uses context
  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setThemeMode(newTheme);
    const updated = { ...appearanceSettings, theme: newTheme };
    setAppearanceSettings(updated);
    localStorage.setItem('flowfish_appearance', JSON.stringify(updated));
    message.success(`Theme changed to ${newTheme}`);
  };
  
  // Handle color change - uses context
  const handleColorChange = (color: string) => {
    setPrimaryColor(color);
    const updated = { ...appearanceSettings, primaryColor: color };
    setAppearanceSettings(updated);
    localStorage.setItem('flowfish_appearance', JSON.stringify(updated));
    message.success('Accent color updated');
  };
  
  // Save other appearance settings (non-theme)
  const saveAppearanceSettings = (newSettings: Partial<AppearanceSettings>) => {
    const updated = { ...appearanceSettings, ...newSettings };
    setAppearanceSettings(updated);
    localStorage.setItem('flowfish_appearance', JSON.stringify(updated));
    message.success('Settings saved');
  };
  
  // ================== API CALLS ==================
  
  const getToken = () => localStorage.getItem('flowfish_token');
  
  const checkAdminRole = () => {
    try {
      const token = getToken();
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const roles = payload.roles || [];
        setIsAdmin(roles.includes('Super Admin') || roles.includes('Admin'));
      }
    } catch {
      setIsAdmin(false);
    }
  };
  
  const fetchAllSettings = async () => {
    setLoading(true);
    try {
      await Promise.all([
        fetchAnalysisSettings(),
        fetchSMTPSettings(),
        fetchNotificationSettings(),
        fetchRetentionSettings(),
        fetchSecuritySettings(),
        fetchAlertRules(),
        fetchIntegrationSettings(),
        fetchAuditLogs(),
        fetchBackups()
      ]);
    } finally {
      setLoading(false);
    }
  };
  
  // ================== ALERT RULES API ==================
  
  const fetchAlertRules = async () => {
    setAlertRulesLoading(true);
    try {
      const response = await fetch('/api/v1/settings/alert-rules', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAlertRules(data.rules || []);
      } else {
        // No rules available from API
        setAlertRules([]);
      }
    } catch (error) {
      console.error('Failed to fetch alert rules:', error);
      setAlertRules([]);
    } finally {
      setAlertRulesLoading(false);
    }
  };
  
  const handleSaveAlertRule = async (values: any) => {
    setSavingAlertRule(true);
    try {
      const url = editingAlertRule 
        ? `/api/v1/settings/alert-rules/${editingAlertRule.id}`
        : '/api/v1/settings/alert-rules';
      
      const response = await fetch(url, {
        method: editingAlertRule ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success(editingAlertRule ? 'Alert rule updated' : 'Alert rule created');
        setAlertRuleModalVisible(false);
        setEditingAlertRule(null);
        alertRuleForm.resetFields();
        fetchAlertRules();
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to save alert rule');
      }
    } catch (error) {
      message.error('Failed to save alert rule');
    } finally {
      setSavingAlertRule(false);
    }
  };
  
  const toggleAlertRule = async (id: number) => {
    try {
      const response = await fetch(`/api/v1/settings/alert-rules/${id}/toggle`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const result = await response.json();
        setAlertRules(prev => prev.map(rule => 
          rule.id === id ? { ...rule, enabled: result.enabled } : rule
        ));
        message.success(`Alert rule ${result.enabled ? 'enabled' : 'disabled'}`);
      }
    } catch (error) {
      message.error('Failed to toggle alert rule');
    }
  };
  
  const deleteAlertRule = (id: number) => {
    Modal.confirm({
      title: 'Delete Alert Rule',
      content: 'Are you sure you want to delete this alert rule?',
      onOk: async () => {
        try {
          const response = await fetch(`/api/v1/settings/alert-rules/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });
          
          if (response.ok) {
            setAlertRules(prev => prev.filter(rule => rule.id !== id));
            message.success('Alert rule deleted');
          }
        } catch (error) {
          message.error('Failed to delete alert rule');
        }
      },
    });
  };
  
  // ================== API KEY MANAGEMENT ==================
  
  const fetchApiTokens = async () => {
    setApiTokensLoading(true);
    try {
      const response = await fetch('/api/v1/api-keys', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setApiTokens(data || []);
      } else {
        setApiTokens([]);
      }
    } catch (error) {
      console.error('Failed to fetch API keys:', error);
      setApiTokens([]);
    } finally {
      setApiTokensLoading(false);
    }
  };
  
  const fetchPipelineClusters = async () => {
    setPipelineClustersLoading(true);
    try {
      const response = await fetch('/api/v1/clusters', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setPipelineClusters(data.clusters || []);
      } else {
        setPipelineClusters([]);
      }
    } catch (error) {
      console.error('Failed to fetch clusters:', error);
      setPipelineClusters([]);
    } finally {
      setPipelineClustersLoading(false);
    }
  };
  
  const createApiToken = async (values: { name: string; scopes: string[]; expires_in_days: number | null }) => {
    setCreatingToken(true);
    try {
      const response = await fetch('/api/v1/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({
          name: values.name,
          scopes: values.scopes,
          expires_in_days: values.expires_in_days,
          description: `Created from Flowfish UI for ${values.scopes.join(', ')}`
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        // Store the newly created API key to show it once
        setNewlyCreatedToken(data.api_key);
        // Refresh the list
        fetchApiTokens();
        setApiTokenModalVisible(false);
        apiTokenForm.resetFields();
        message.success('API key created successfully! Copy it now - it won\'t be shown again.');
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to create API key');
      }
    } catch (error) {
      message.error('Failed to create API key');
    } finally {
      setCreatingToken(false);
    }
  };
  
  const revokeApiToken = (keyId: string, tokenName: string) => {
    Modal.confirm({
      title: 'Revoke API Key',
      content: `Are you sure you want to revoke the API key "${tokenName}"? This action cannot be undone and any pipelines using this key will stop working.`,
      okText: 'Revoke',
      okType: 'danger',
      onOk: async () => {
        try {
          const response = await fetch(`/api/v1/api-keys/${keyId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });
          
          if (response.ok) {
            setApiTokens(prev => prev.filter(t => t.key_id !== keyId));
            message.success('API key revoked');
          } else {
            message.error('Failed to revoke token');
          }
        } catch (error) {
          message.error('Failed to revoke token');
        }
      },
    });
  };
  
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success('Copied to clipboard');
  };
  
  // ================== INTEGRATIONS API ==================
  
  const fetchIntegrationSettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/integrations', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        integrationForm.setFieldsValue(data);
      } else {
        // Initialize with empty values - user will configure
        integrationForm.setFieldsValue({
          slack_enabled: false,
          slack_webhook_url: '',
          slack_channel: '',
          teams_enabled: false,
          teams_webhook_url: '',
          pagerduty_enabled: false,
          pagerduty_integration_key: '',
          pagerduty_service_id: '',
          webhook_enabled: false,
          webhook_url: '',
          webhook_secret: '',
          webhook_events: [],
        });
      }
    } catch (error) {
      console.error('Failed to fetch integration settings:', error);
      // Initialize with empty values
      integrationForm.setFieldsValue({
        slack_enabled: false,
        slack_webhook_url: '',
        slack_channel: '',
        teams_enabled: false,
        teams_webhook_url: '',
        pagerduty_enabled: false,
        pagerduty_integration_key: '',
        pagerduty_service_id: '',
        webhook_enabled: false,
        webhook_url: '',
        webhook_secret: '',
        webhook_events: [],
      });
    }
  };
  
  const saveIntegrationSettings = async (values: any) => {
    try {
      const response = await fetch('/api/v1/settings/integrations', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Integration settings saved');
      } else {
        message.error('Failed to save integration settings');
      }
    } catch (error) {
      message.error('Failed to save integration settings');
    }
  };
  
  const testIntegration = async (type: 'slack' | 'teams' | 'pagerduty') => {
    const values = integrationForm.getFieldsValue();
    let webhookUrl = '';
    
    if (type === 'slack') webhookUrl = values.slack_webhook_url;
    else if (type === 'teams') webhookUrl = values.teams_webhook_url;
    else if (type === 'pagerduty') webhookUrl = values.pagerduty_integration_key;
    
    if (!webhookUrl) {
      message.warning(`Please configure ${type} settings first`);
      return;
    }
    
    try {
      const response = await fetch(`/api/v1/settings/integrations/test/${type}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success(`${type} connection test successful`);
      } else {
        message.error(`${type} connection test failed`);
      }
    } catch (error) {
      message.error(`Failed to test ${type} connection`);
    }
  };
  
  // ================== AUDIT LOGS API ==================
  
  const fetchAuditLogs = async () => {
    setAuditLogsLoading(true);
    try {
      // First try the dedicated audit-logs endpoint
      let response = await fetch('/api/v1/settings/audit-logs', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAuditLogs(data.logs || []);
        return;
      }
      
      // Fallback to user-activity endpoint (same data, different endpoint)
      response = await fetch('/api/v1/user-activity?limit=100', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Transform user-activity format to audit log format
        const logs: AuditLog[] = (data.activities || []).map((activity: any) => ({
          id: `log-${activity.id}`,
          timestamp: activity.timestamp,
          user: activity.username || 'system',
          action: activity.action,
          resource_type: activity.resource_type || 'unknown',
          resource_id: activity.resource_id || '',
          details: typeof activity.details === 'object' ? JSON.stringify(activity.details) : (activity.details || ''),
          ip_address: activity.ip_address || '0.0.0.0',
          status: 'success', // Activity logs are typically successful actions
        }));
        setAuditLogs(logs);
      } else {
        // No audit data available
        setAuditLogs([]);
      }
    } catch (error) {
      console.error('Failed to fetch audit logs:', error);
      setAuditLogs([]);
    } finally {
      setAuditLogsLoading(false);
    }
  };
  
  const filteredAuditLogs = auditLogs.filter(log => {
    if (auditLogFilter !== 'all' && log.action !== auditLogFilter) return false;
    if (auditLogSearch && !log.user.toLowerCase().includes(auditLogSearch.toLowerCase()) && 
        !log.action.toLowerCase().includes(auditLogSearch.toLowerCase()) &&
        !log.resource_type.toLowerCase().includes(auditLogSearch.toLowerCase())) return false;
    return true;
  });
  
  const exportAuditLogs = () => {
    const csv = [
      ['Timestamp', 'User', 'Action', 'Resource Type', 'Resource ID', 'Details', 'IP Address', 'Status'].join(','),
      ...filteredAuditLogs.map(log => [
        log.timestamp,
        log.user,
        log.action,
        log.resource_type,
        log.resource_id,
        `"${log.details}"`,
        log.ip_address,
        log.status
      ].join(','))
    ].join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit-logs-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success('Audit logs exported');
  };
  
  // ================== BACKUP/RESTORE API ==================
  
  const fetchBackups = async () => {
    setBackupsLoading(true);
    try {
      const response = await fetch('/api/v1/settings/backups', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setBackups(data.backups || []);
      } else {
        // No backups available from API
        setBackups([]);
      }
    } catch (error) {
      console.error('Failed to fetch backups:', error);
      setBackups([]);
    } finally {
      setBackupsLoading(false);
    }
  };
  
  const createBackup = async (type: 'full' | 'config' | 'data') => {
    setCreatingBackup(true);
    try {
      const response = await fetch('/api/v1/settings/backups', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({ type })
      });
      
      if (response.ok) {
        message.success(`${type} backup started`);
        fetchBackups();
      } else {
        message.error('Failed to create backup');
      }
    } catch (error) {
      message.error('Failed to create backup');
    } finally {
      setCreatingBackup(false);
    }
  };
  
  const restoreBackup = async (backupId: string) => {
    Modal.confirm({
      title: 'Restore Backup',
      content: 'This will restore the system to the selected backup point. All changes after this backup will be lost. Are you sure?',
      okText: 'Restore',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        setRestoringBackup(backupId);
        try {
          const response = await fetch(`/api/v1/settings/backups/${backupId}/restore`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });
          
          if (response.ok) {
            message.success('Backup restored successfully');
          } else {
            message.error('Failed to restore backup');
          }
        } catch (error) {
          message.error('Failed to restore backup');
        } finally {
          setRestoringBackup(null);
        }
      },
    });
  };
  
  const deleteBackup = (backupId: string) => {
    Modal.confirm({
      title: 'Delete Backup',
      content: 'Are you sure you want to delete this backup? This action cannot be undone.',
      okText: 'Delete',
      okType: 'danger',
      onOk: async () => {
        try {
          const response = await fetch(`/api/v1/settings/backups/${backupId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });
          
          if (response.ok) {
            message.success('Backup deleted');
            fetchBackups();
          } else {
            message.error('Failed to delete backup');
          }
        } catch (error) {
          message.error('Failed to delete backup');
        }
      },
    });
  };
  
  const downloadBackup = (backup: BackupInfo) => {
    message.info(`Downloading ${backup.name}...`);
    // In real implementation, this would trigger a download from the API
  };
  
  const fetchAnalysisSettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/analysis-limits', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data: AnalysisLimits = await response.json();
        analysisForm.setFieldsValue(data);
        if (data.updated_at) {
          setLastUpdated(new Date(data.updated_at).toLocaleString());
        }
      }
    } catch (error) {
      console.error('Failed to load analysis settings:', error);
    }
  };
  
  const fetchSMTPSettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/smtp', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        smtpForm.setFieldsValue(data);
      } else {
        // Initialize with empty values - user will configure
        smtpForm.setFieldsValue({
          enabled: false,
          host: '',
          port: 587,
          username: '',
          password: '',
          from_email: '',
          from_name: '',
          use_tls: true,
          use_ssl: false
        });
      }
    } catch (error) {
      console.error('Failed to fetch SMTP settings:', error);
      // Initialize with empty values
      smtpForm.setFieldsValue({
        enabled: false,
        host: '',
        port: 587,
        username: '',
        password: '',
        from_email: '',
        from_name: '',
        use_tls: true,
        use_ssl: false
      });
    }
  };
  
  const fetchNotificationSettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/notifications', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        notificationForm.setFieldsValue(data);
      } else {
        // Initialize with empty/default values - user will configure
        notificationForm.setFieldsValue({
          email_enabled: false,
          email_on_analysis_complete: false,
          email_on_analysis_error: false,
          email_on_anomaly_detected: false,
          email_on_scheduled_report: false,
          slack_enabled: false,
          slack_webhook_url: '',
          slack_channel: '',
          in_app_enabled: true
        });
      }
    } catch (error) {
      console.error('Failed to fetch notification settings:', error);
      notificationForm.setFieldsValue({
        email_enabled: false,
        email_on_analysis_complete: false,
        email_on_analysis_error: false,
        email_on_anomaly_detected: false,
        email_on_scheduled_report: false,
        slack_enabled: false,
        slack_webhook_url: '',
        slack_channel: '',
        in_app_enabled: true
      });
    }
  };
  
  const fetchRetentionSettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/retention', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        retentionForm.setFieldsValue(data);
      } else {
        // Initialize with system defaults - these are reasonable defaults
        retentionForm.setFieldsValue({
          events_retention_days: 30,
          network_flows_retention_days: 30,
          dns_queries_retention_days: 30,
          process_events_retention_days: 30,
          analysis_retention_days: 90,
          auto_cleanup_enabled: false,
          cleanup_schedule: 'daily'
        });
      }
    } catch (error) {
      console.error('Failed to fetch retention settings:', error);
      retentionForm.setFieldsValue({
        events_retention_days: 30,
        network_flows_retention_days: 30,
        dns_queries_retention_days: 30,
        process_events_retention_days: 30,
        analysis_retention_days: 90,
        auto_cleanup_enabled: false,
        cleanup_schedule: 'daily'
      });
    }
  };
  
  const fetchSecuritySettings = async () => {
    try {
      const response = await fetch('/api/v1/settings/security', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        securityForm.setFieldsValue(data);
      } else {
        // Initialize with secure defaults
        securityForm.setFieldsValue({
          session_timeout_minutes: 480,
          max_login_attempts: 5,
          lockout_duration_minutes: 30,
          password_min_length: 8,
          password_require_uppercase: true,
          password_require_numbers: true,
          password_require_special: false,
          two_factor_enabled: false,
          two_factor_required_for_all: false,
          two_factor_code_expiry_minutes: 5,
          allowed_ip_ranges: '',
          api_rate_limit_per_minute: 100
        });
      }
    } catch (error) {
      console.error('Failed to fetch security settings:', error);
      securityForm.setFieldsValue({
        session_timeout_minutes: 480,
        max_login_attempts: 5,
        lockout_duration_minutes: 30,
        password_min_length: 8,
        password_require_uppercase: true,
        password_require_numbers: true,
        password_require_special: false,
        two_factor_enabled: false,
        two_factor_required_for_all: false,
        two_factor_code_expiry_minutes: 5,
        allowed_ip_ranges: '',
        api_rate_limit_per_minute: 100
      });
    }
  };
  
  const fetchSystemInfo = async () => {
    try {
      const response = await fetch('/api/v1/settings/system-info', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setSystemInfo(data);
      }
    } catch (error) {
      // Use defaults
    }
  };
  
  // ================== SAVE HANDLERS ==================
  
  const saveAnalysisSettings = async (values: AnalysisLimits) => {
    if (values.default_continuous_duration_minutes > values.max_allowed_duration_minutes) {
      message.error('Default duration cannot exceed maximum allowed duration');
      return;
    }
    
    setSaving('analysis');
    try {
      const response = await fetch('/api/v1/settings/analysis-limits', {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        const data = await response.json();
        message.success('Analysis settings saved');
        if (data.updated_at) {
          setLastUpdated(new Date(data.updated_at).toLocaleString());
        }
      } else {
        handleSaveError(response);
      }
    } catch (error) {
      message.error('Failed to save settings');
    } finally {
      setSaving(null);
    }
  };
  
  const saveSMTPSettings = async (values: SMTPSettings) => {
    setSaving('smtp');
    try {
      const response = await fetch('/api/v1/settings/smtp', {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('SMTP settings saved');
      } else {
        handleSaveError(response);
      }
    } catch (error) {
      message.error('Failed to save SMTP settings');
    } finally {
      setSaving(null);
    }
  };
  
  const saveNotificationSettings = async (values: NotificationSettings) => {
    setSaving('notification');
    try {
      const response = await fetch('/api/v1/settings/notifications', {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Notification settings saved');
      } else {
        handleSaveError(response);
      }
    } catch (error) {
      message.error('Failed to save notification settings');
    } finally {
      setSaving(null);
    }
  };
  
  const saveRetentionSettings = async (values: DataRetentionSettings) => {
    setSaving('retention');
    try {
      const response = await fetch('/api/v1/settings/retention', {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Data retention settings saved');
      } else {
        handleSaveError(response);
      }
    } catch (error) {
      message.error('Failed to save retention settings');
    } finally {
      setSaving(null);
    }
  };
  
  const saveSecuritySettings = async (values: SecuritySettings) => {
    setSaving('security');
    try {
      const response = await fetch('/api/v1/settings/security', {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Security settings saved');
      } else {
        handleSaveError(response);
      }
    } catch (error) {
      message.error('Failed to save security settings');
    } finally {
      setSaving(null);
    }
  };
  
  const handleSaveError = async (response: Response) => {
    if (response.status === 403) {
      message.error('Admin permission required');
    } else {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      message.error(error.detail || 'Failed to save');
    }
  };
  
  // ================== UTILITY FUNCTIONS ==================
  
  const testSMTPConnection = async () => {
    setTestingEmail(true);
    try {
      const values = smtpForm.getFieldsValue();
      const response = await fetch('/api/v1/settings/smtp/test', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Test email sent successfully! Check your inbox.');
      } else {
        const error = await response.json().catch(() => ({ detail: 'Connection failed' }));
        message.error(`SMTP Test Failed: ${error.detail}`);
      }
    } catch (error) {
      message.error('Failed to test SMTP connection');
    } finally {
      setTestingEmail(false);
    }
  };
  
  const runDataCleanup = async () => {
    Modal.confirm({
      title: 'Run Data Cleanup Now?',
      icon: <ExclamationCircleOutlined />,
      content: 'This will delete data older than the retention period. This action cannot be undone.',
      okText: 'Run Cleanup',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          const response = await fetch('/api/v1/settings/retention/cleanup', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });
          
          if (response.ok) {
            const result = await response.json();
            message.success(`Cleanup complete: ${result.deleted_count || 0} records removed`);
            fetchSystemInfo();
          } else {
            message.error('Cleanup failed');
          }
        } catch (error) {
          message.error('Failed to run cleanup');
        }
      }
    });
  };
  
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'connected':
        return <Badge status="success" text="Healthy" />;
      case 'degraded':
        return <Badge status="warning" text="Degraded" />;
      case 'error':
      case 'disconnected':
        return <Badge status="error" text="Error" />;
      case 'disabled':
      case 'not_configured':
        return <Badge status="default" text="Disabled" />;
      default:
        return <Badge status="default" text="Unknown" />;
    }
  };
  
  // ================== RENDER ==================
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="Loading settings..." />
      </div>
    );
  }
  
  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <Title level={2} style={{ marginBottom: 8 }}>
            <SettingOutlined style={{ marginRight: 12 }} />
            System Settings
          </Title>
          <Paragraph type="secondary">
            Configure system behavior, notifications, data retention, and security policies.
            {lastUpdated && <Text type="secondary" style={{ marginLeft: 16 }}>Last updated: {lastUpdated}</Text>}
          </Paragraph>
        </div>
        
        {/* Admin Warning - not shown for API Keys tab (users can manage their own keys) */}
        {!isAdmin && activeTab !== 'api-tokens' && (
          <Alert
            message="Read-Only Mode"
            description="Admin privileges required to make changes."
            type="info"
            showIcon
            icon={<LockOutlined />}
          />
        )}
        
        {/* Settings Tabs */}
        <Tabs 
          activeKey={activeTab} 
          onChange={(key) => {
            setActiveTab(key);
            setSearchParams(key === 'general' ? {} : { tab: key }, { replace: true });
          }}
          type="card"
          size="large"
        >
          {/* ================== GENERAL TAB ================== */}
          <TabPane 
            tab={<span><ClockCircleOutlined /> Analysis</span>} 
            key="general"
          >
            <Card title="Analysis Time Limits" bordered={false}>
          <Alert
            message="Continuous Analysis Protection"
                description="These settings prevent analyses from running indefinitely and consuming resources."
            type="info"
            showIcon
            style={{ marginBottom: 24 }}
          />
          
          <Form
                form={analysisForm}
            layout="vertical"
                onFinish={saveAnalysisSettings}
                disabled={!isAdmin}
            initialValues={{
              continuous_auto_stop_enabled: true,
              default_continuous_duration_minutes: 10,
              max_allowed_duration_minutes: 1440,
              warning_before_minutes: 2,
              ingestion_rate_limit_per_second: 5000
            }}
          >
            <Row gutter={24}>
              <Col xs={24} md={12}>
                <Form.Item
                  name="continuous_auto_stop_enabled"
                      label="Enable Auto-Stop"
                  valuePropName="checked"
                >
                      <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                    <Form.Item name="warning_before_minutes" label="Warning Before Auto-Stop">
                      <Select>
                        <Option value={1}>1 minute</Option>
                        <Option value={2}>2 minutes</Option>
                        <Option value={5}>5 minutes</Option>
                        <Option value={10}>10 minutes</Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            
            <Divider />
            
            <Row gutter={24}>
              <Col xs={24} md={12}>
                <Form.Item
                  name="default_continuous_duration_minutes"
                      label="Default Duration (Continuous Mode)"
                      rules={[{ required: true }]}
                      extra="Recommended: 10-30 minutes"
                    >
                      <InputNumber min={1} max={1440} addonAfter="minutes" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="max_allowed_duration_minutes"
                      label="Maximum Allowed Duration"
                      rules={[{ required: true }]}
                      extra="Maximum: 7 days (10080 min)"
                    >
                      <InputNumber min={10} max={10080} addonAfter="minutes" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Form.Item label="Quick Presets">
                  <Space wrap>
                    {[5, 10, 15, 30, 60].map(min => (
                      <Button 
                        key={min}
                        size="small" 
                        onClick={() => analysisForm.setFieldValue('default_continuous_duration_minutes', min)}
                        disabled={!isAdmin}
                      >
                        {min < 60 ? `${min} min` : `${min/60} hour`}
                      </Button>
                    ))}
                    </Space>
                </Form.Item>
                
                <Divider />

                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="ingestion_rate_limit_per_second"
                      label="Event Collection Rate Limit"
                      rules={[{ required: true }]}
                      extra="Maximum events per second per collection session. Set 0 for unlimited."
                    >
                      <InputNumber min={0} max={50000} addonAfter="events/sec" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item label="Rate Limit Presets">
                      <Space wrap>
                        {[
                          { label: 'Unlimited', value: 0 },
                          { label: '1,000', value: 1000 },
                          { label: '5,000', value: 5000 },
                          { label: '10,000', value: 10000 },
                          { label: '25,000', value: 25000 },
                        ].map(preset => (
                          <Button
                            key={preset.value}
                            size="small"
                            onClick={() => analysisForm.setFieldValue('ingestion_rate_limit_per_second', preset.value)}
                            disabled={!isAdmin}
                          >
                            {preset.label}
                          </Button>
                        ))}
                      </Space>
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider />
                
                <Form.Item>
                  <Button 
                    type="primary" 
                    htmlType="submit" 
                    loading={saving === 'analysis'} 
                    icon={<SaveOutlined />}
                    disabled={!isAdmin}
                  >
                    Save Analysis Settings
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </TabPane>
          
          {/* ================== EMAIL/SMTP TAB ================== */}
          <TabPane 
            tab={<span><MailOutlined /> Email (SMTP)</span>} 
            key="smtp"
          >
            <Card title="SMTP Configuration" bordered={false}>
              <Alert
                message="Email Server Settings"
                description="Configure SMTP server for sending email notifications and scheduled reports."
                type="info"
                showIcon
                style={{ marginBottom: 24 }}
              />
              
              <Form
                form={smtpForm}
                layout="vertical"
                onFinish={saveSMTPSettings}
                disabled={!isAdmin}
              >
                <Form.Item name="enabled" label="Enable Email Notifications" valuePropName="checked">
                  <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                </Form.Item>
                
                <Divider>Server Settings</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={16}>
                    <Form.Item
                      name="host"
                      label="SMTP Host"
                      rules={[{ required: true, message: 'SMTP host is required' }]}
                    >
                      <Input placeholder="smtp.example.com" prefix={<CloudServerOutlined />} />
                </Form.Item>
              </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="port"
                      label="Port"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="587" />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item name="username" label="Username">
                      <Input placeholder="user@example.com" prefix={<TeamOutlined />} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="password" label="Password">
                      <Input.Password 
                        placeholder="••••••••" 
                        visibilityToggle={{ visible: showPassword, onVisibleChange: setShowPassword }}
                      />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item name="use_tls" label="Use TLS (STARTTLS)" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="use_ssl" label="Use SSL/TLS (Direct)" valuePropName="checked">
                      <Switch />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider>Sender Settings</Divider>
                
                <Row gutter={24}>
              <Col xs={24} md={12}>
                <Form.Item
                      name="from_email"
                      label="From Email"
                      rules={[{ required: true, type: 'email', message: 'Valid email required' }]}
                    >
                      <Input placeholder="noreply@flowfish.io" prefix={<MailOutlined />} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="from_name" label="From Name">
                      <Input placeholder="Flowfish" />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider />
                
                <Form.Item>
                    <Space>
                    <Button 
                      type="primary" 
                      htmlType="submit" 
                      loading={saving === 'smtp'} 
                      icon={<SaveOutlined />}
                      disabled={!isAdmin}
                    >
                      Save SMTP Settings
                    </Button>
                    <Button 
                      icon={<SendOutlined />} 
                      onClick={testSMTPConnection}
                      loading={testingEmail}
                      disabled={!isAdmin}
                    >
                      Send Test Email
                    </Button>
                    </Space>
                </Form.Item>
              </Form>
              
              {/* Common SMTP Presets */}
              <Collapse ghost style={{ marginTop: 16 }}>
                <Panel header="Common SMTP Presets" key="presets">
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button 
                      block 
                      onClick={() => smtpForm.setFieldsValue({ host: 'smtp.gmail.com', port: 587, use_tls: true, use_ssl: false })}
                      disabled={!isAdmin}
                    >
                      Gmail (smtp.gmail.com:587)
                    </Button>
                    <Button 
                      block 
                      onClick={() => smtpForm.setFieldsValue({ host: 'smtp.office365.com', port: 587, use_tls: true, use_ssl: false })}
                      disabled={!isAdmin}
                    >
                      Office 365 (smtp.office365.com:587)
                    </Button>
                    <Button 
                      block 
                      onClick={() => smtpForm.setFieldsValue({ host: 'smtp-mail.outlook.com', port: 587, use_tls: true, use_ssl: false })}
                      disabled={!isAdmin}
                    >
                      Outlook (smtp-mail.outlook.com:587)
                    </Button>
                    <Button 
                      block 
                      onClick={() => smtpForm.setFieldsValue({ host: 'email-smtp.eu-west-1.amazonaws.com', port: 587, use_tls: true, use_ssl: false })}
                      disabled={!isAdmin}
                    >
                      AWS SES (eu-west-1)
                    </Button>
                  </Space>
                </Panel>
              </Collapse>
            </Card>
          </TabPane>
          
          {/* ================== NOTIFICATIONS TAB ================== */}
          <TabPane 
            tab={<span><BellOutlined /> Notifications</span>} 
            key="notifications"
          >
            <Card title="Notification Preferences" bordered={false}>
              <Form
                form={notificationForm}
                layout="vertical"
                onFinish={saveNotificationSettings}
                disabled={!isAdmin}
              >
                <Divider orientation="left"><MailOutlined /> Email Notifications</Divider>
                
                <Form.Item name="email_enabled" label="Enable Email Notifications" valuePropName="checked">
                  <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                </Form.Item>
                
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item name="email_on_analysis_complete" label="Analysis Completed" valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="email_on_analysis_error" label="Analysis Error" valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="email_on_anomaly_detected" label="Anomaly Detected" valuePropName="checked">
                      <Switch size="small" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="email_on_scheduled_report" label="Scheduled Report Ready" valuePropName="checked">
                      <Switch size="small" />
                </Form.Item>
              </Col>
            </Row>
                
                <Divider orientation="left"><GlobalOutlined /> Slack Integration</Divider>
                
                <Form.Item name="slack_enabled" label="Enable Slack Notifications" valuePropName="checked">
                  <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                </Form.Item>
                
                <Row gutter={24}>
                  <Col xs={24} md={16}>
                    <Form.Item 
                      name="slack_webhook_url" 
                      label="Webhook URL"
                      extra="Create a webhook at api.slack.com/apps"
                    >
                      <Input placeholder="https://hooks.slack.com/services/..." prefix={<ApiOutlined />} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item name="slack_channel" label="Channel">
                      <Input placeholder="#flowfish-alerts" />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider orientation="left"><ThunderboltOutlined /> In-App Notifications</Divider>
                
                <Form.Item name="in_app_enabled" label="Enable In-App Notifications" valuePropName="checked">
                  <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                </Form.Item>
            
            <Divider />
            
                <Form.Item>
                  <Button 
                    type="primary" 
                    htmlType="submit" 
                    loading={saving === 'notification'} 
                    icon={<SaveOutlined />}
                    disabled={!isAdmin}
                  >
                    Save Notification Settings
                  </Button>
                </Form.Item>
              </Form>
            </Card>
          </TabPane>
          
          {/* ================== DATA RETENTION TAB ================== */}
          <TabPane 
            tab={<span><DatabaseOutlined /> Data Retention</span>} 
            key="retention"
          >
            <Card title="Data Retention Policies" bordered={false}>
              <Alert
                message="Storage Management"
                description="Configure how long data is retained. Older data will be automatically deleted based on these settings."
                type="warning"
                showIcon
                style={{ marginBottom: 24 }}
              />
              
              <Form
                form={retentionForm}
                layout="vertical"
                onFinish={saveRetentionSettings}
                disabled={!isAdmin}
              >
                <Divider orientation="left">Retention Periods</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="events_retention_days"
                      label="eBPF Events"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={365} addonAfter="days" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="network_flows_retention_days"
                      label="Network Flows"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={365} addonAfter="days" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="dns_queries_retention_days"
                      label="DNS Queries"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={365} addonAfter="days" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Row gutter={24}>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="process_events_retention_days"
                      label="Process Events"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={365} addonAfter="days" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="analysis_retention_days"
                      label="Analysis Records"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={365} addonAfter="days" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Form.Item label="Quick Presets">
              <Space wrap>
                <Button 
                  size="small" 
                      onClick={() => {
                        retentionForm.setFieldsValue({
                          events_retention_days: 7,
                          network_flows_retention_days: 7,
                          dns_queries_retention_days: 7,
                          process_events_retention_days: 7,
                          analysis_retention_days: 30
                        });
                      }}
                  disabled={!isAdmin}
                >
                      7 Days (Minimal)
                </Button>
                <Button 
                  size="small" 
                      onClick={() => {
                        retentionForm.setFieldsValue({
                          events_retention_days: 30,
                          network_flows_retention_days: 30,
                          dns_queries_retention_days: 30,
                          process_events_retention_days: 30,
                          analysis_retention_days: 90
                        });
                      }}
                  disabled={!isAdmin}
                >
                      30 Days (Standard)
                </Button>
                <Button 
                  size="small" 
                      onClick={() => {
                        retentionForm.setFieldsValue({
                          events_retention_days: 90,
                          network_flows_retention_days: 90,
                          dns_queries_retention_days: 90,
                          process_events_retention_days: 90,
                          analysis_retention_days: 180
                        });
                      }}
                  disabled={!isAdmin}
                >
                      90 Days (Extended)
                </Button>
                  </Space>
                </Form.Item>
                
                <Divider orientation="left">Automatic Cleanup</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item name="auto_cleanup_enabled" label="Enable Auto Cleanup" valuePropName="checked">
                      <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={12}>
                    <Form.Item name="cleanup_schedule" label="Cleanup Schedule">
                      <Select>
                        <Option value="hourly">Hourly</Option>
                        <Option value="daily">Daily (Recommended)</Option>
                        <Option value="weekly">Weekly</Option>
                      </Select>
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider />
                
                <Form.Item>
                  <Space>
                <Button 
                      type="primary" 
                      htmlType="submit" 
                      loading={saving === 'retention'} 
                      icon={<SaveOutlined />}
                  disabled={!isAdmin}
                >
                      Save Retention Settings
                </Button>
                <Button 
                      danger
                      icon={<DeleteOutlined />} 
                      onClick={runDataCleanup}
                  disabled={!isAdmin}
                >
                      Run Cleanup Now
                </Button>
              </Space>
            </Form.Item>
              </Form>
            </Card>
          </TabPane>
          
          {/* ================== SECURITY TAB ================== */}
          <TabPane 
            tab={<span><SafetyOutlined /> Security</span>} 
            key="security"
          >
            <Card title="Security Settings" bordered={false}>
              <Form
                form={securityForm}
                layout="vertical"
                onFinish={saveSecuritySettings}
                disabled={!isAdmin}
              >
                <Divider orientation="left"><LockOutlined /> Session Settings</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="session_timeout_minutes"
                      label="Session Timeout"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={5} max={1440} addonAfter="minutes" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="max_login_attempts"
                      label="Max Login Attempts"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={3} max={10} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="lockout_duration_minutes"
                      label="Lockout Duration"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={5} max={1440} addonAfter="minutes" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider orientation="left"><SecurityScanOutlined /> Password Policy</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="password_min_length"
                      label="Minimum Length"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={6} max={32} addonAfter="chars" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={16}>
                    <Form.Item label="Password Requirements">
                      <Space>
                        <Form.Item name="password_require_uppercase" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                        <Text>Uppercase</Text>
                        
                        <Form.Item name="password_require_numbers" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                        <Text>Numbers</Text>
                        
                        <Form.Item name="password_require_special" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                        <Text>Special (!@#$)</Text>
                      </Space>
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider orientation="left"><SafetyOutlined /> Two-Factor Authentication (2FA)</Divider>
                
                <Alert
                  message="Email-Based 2FA"
                  description="When enabled, users will receive a verification code via email during login. Make sure SMTP is configured in the Email tab."
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
                
                <Row gutter={24}>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="two_factor_enabled"
                      label="Enable 2FA"
                      valuePropName="checked"
                      extra="Allow users to enable 2FA"
                    >
                      <Switch checkedChildren="Enabled" unCheckedChildren="Disabled" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="two_factor_required_for_all"
                      label="Require for All Users"
                      valuePropName="checked"
                      extra="Force 2FA for everyone"
                    >
                      <Switch checkedChildren="Required" unCheckedChildren="Optional" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={8}>
                    <Form.Item
                      name="two_factor_code_expiry_minutes"
                      label="Code Expiry"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={1} max={30} addonAfter="minutes" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Divider orientation="left"><ApiOutlined /> API & Access Control</Divider>
                
                <Row gutter={24}>
                  <Col xs={24} md={12}>
                    <Form.Item
                      name="api_rate_limit_per_minute"
                      label="API Rate Limit"
                      rules={[{ required: true }]}
                      extra="Requests per minute per user"
                    >
                      <InputNumber min={10} max={1000} addonAfter="req/min" style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                </Row>
                
                <Form.Item
                  name="allowed_ip_ranges"
                  label="Allowed IP Ranges"
                  extra="Comma-separated CIDR ranges (leave empty to allow all). Example: 10.0.0.0/8, 192.168.0.0/16"
                >
                  <Input.TextArea 
                    rows={2} 
                    placeholder="10.0.0.0/8, 192.168.0.0/16, 172.16.0.0/12"
                  />
            </Form.Item>
            
            <Divider />
            
            <Form.Item>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                    loading={saving === 'security'} 
                  icon={<SaveOutlined />}
                  disabled={!isAdmin}
                >
                    Save Security Settings
                </Button>
                </Form.Item>
              </Form>
            </Card>
          </TabPane>
          
          {/* ================== APPEARANCE TAB ================== */}
          <TabPane 
            tab={<span><BgColorsOutlined /> Appearance</span>} 
            key="appearance"
          >
            <Row gutter={24}>
              <Col xs={24} lg={12}>
                <Card title="Theme Settings" bordered={false}>
                  <div style={{ marginBottom: 24 }}>
                    <Text strong style={{ display: 'block', marginBottom: 12 }}>Color Theme</Text>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Card 
                          hoverable
                          onClick={() => handleThemeChange('light')}
                          style={{ 
                            textAlign: 'center',
                            border: themeMode === 'light' ? `2px solid ${primaryColor}` : `1px solid ${isDark ? '#434343' : '#d9d9d9'}`,
                            background: '#ffffff'
                          }}
                          bodyStyle={{ padding: 16 }}
                        >
                          <BulbOutlined style={{ fontSize: 32, color: '#c9a55a' }} />
                          <div style={{ marginTop: 8 }}>
                            <Text strong style={{ color: '#000' }}>Light</Text>
                          </div>
                          {themeMode === 'light' && (
                            <Tag color={primaryColor} style={{ marginTop: 8 }}>Active</Tag>
                          )}
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card 
                          hoverable
                          onClick={() => handleThemeChange('dark')}
                          style={{ 
                            textAlign: 'center',
                            border: themeMode === 'dark' ? `2px solid ${primaryColor}` : `1px solid ${isDark ? '#434343' : '#d9d9d9'}`,
                            background: '#141414'
                          }}
                          bodyStyle={{ padding: 16 }}
                        >
                          <BulbFilled style={{ fontSize: 32, color: primaryColor }} />
                          <div style={{ marginTop: 8 }}>
                            <Text strong style={{ color: '#fff' }}>Dark</Text>
                          </div>
                          {themeMode === 'dark' && (
                            <Tag color={primaryColor} style={{ marginTop: 8 }}>Active</Tag>
                          )}
                        </Card>
                      </Col>
                      <Col span={8}>
                        <Card 
                          hoverable
                          onClick={() => handleThemeChange('system')}
                          style={{ 
                            textAlign: 'center',
                            border: themeMode === 'system' ? `2px solid ${primaryColor}` : `1px solid ${isDark ? '#434343' : '#d9d9d9'}`,
                            background: 'linear-gradient(135deg, #ffffff 50%, #141414 50%)'
                          }}
                          bodyStyle={{ padding: 16 }}
                        >
                          <SettingOutlined style={{ fontSize: 32, color: '#7c8eb5' }} />
                          <div style={{ marginTop: 8 }}>
                            <Text strong>System</Text>
                          </div>
                          {themeMode === 'system' && (
                            <Tag color={primaryColor} style={{ marginTop: 8 }}>Active</Tag>
                          )}
                        </Card>
                      </Col>
                    </Row>
                    <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
                      {themeMode === 'system' 
                        ? `Following system preference (currently ${isDark ? 'dark' : 'light'})`
                        : `${themeMode === 'dark' ? 'Dark' : 'Light'} theme is active`}
                  </Text>
                  </div>
                  
                  <Divider />
                  
                  <div style={{ marginBottom: 24 }}>
                    <Text strong style={{ display: 'block', marginBottom: 12 }}>
                      <FormatPainterOutlined style={{ marginRight: 8 }} />
                      Accent Color
                    </Text>
                    <Space wrap>
                      {[
                        { color: '#667eea', name: 'Purple Blue (Default)' },
                        { color: '#0891b2', name: 'Blue' },
                        { color: '#4d9f7c', name: 'Green' },
                        { color: '#7c8eb5', name: 'Purple' },
                        { color: '#a67c9e', name: 'Pink' },
                        { color: '#b89b5d', name: 'Orange' },
                        { color: '#22a6a6', name: 'Cyan' },
                        { color: '#c75450', name: 'Red' },
                      ].map(({ color, name }) => (
                        <Tooltip title={name} key={color}>
                          <div
                            onClick={() => handleColorChange(color)}
                            style={{
                              width: 40,
                              height: 40,
                              borderRadius: 8,
                              backgroundColor: color,
                              cursor: 'pointer',
                              border: primaryColor === color 
                                ? `3px solid ${isDark ? '#fff' : '#000'}` 
                                : '2px solid transparent',
                              boxShadow: primaryColor === color 
                                ? `0 0 0 2px ${isDark ? '#1f1f1f' : '#fff'}, 0 0 0 4px ${color}` 
                                : 'none',
                              transition: 'all 0.2s',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center'
                            }}
                          >
                            {primaryColor === color && (
                              <CheckCircleOutlined style={{ color: '#fff', fontSize: 18 }} />
                            )}
                          </div>
                        </Tooltip>
                      ))}
              </Space>
                  </div>
        </Card>
              </Col>
              
              <Col xs={24} lg={12}>
                <Card title="Display Settings" bordered={false}>
                  <div style={{ marginBottom: 24 }}>
                    <Text strong style={{ display: 'block', marginBottom: 12 }}>
                      <FontSizeOutlined style={{ marginRight: 8 }} />
                      Font Size
                    </Text>
                    <Select
                      value={appearanceSettings.fontSize}
                      onChange={(value) => saveAppearanceSettings({ fontSize: value })}
                      style={{ width: '100%' }}
                    >
                      <Option value="small">
                        <Space>
                          <span style={{ fontSize: 12 }}>Aa</span>
                          Small
                        </Space>
                      </Option>
                      <Option value="medium">
                        <Space>
                          <span style={{ fontSize: 14 }}>Aa</span>
                          Medium (Default)
                        </Space>
                      </Option>
                      <Option value="large">
                        <Space>
                          <span style={{ fontSize: 16 }}>Aa</span>
                          Large
                        </Space>
                      </Option>
                    </Select>
                  </div>
                  
                  <Divider />
                  
                  <div style={{ marginBottom: 24 }}>
                    <Text strong style={{ display: 'block', marginBottom: 12 }}>
                      <LayoutOutlined style={{ marginRight: 8 }} />
                      Layout Options
                    </Text>
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text>Compact Mode</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>Reduce spacing for more content</Text>
                        </div>
                        <Switch
                          checked={appearanceSettings.compactMode}
                          onChange={(checked) => saveAppearanceSettings({ compactMode: checked })}
                        />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text>Collapsed Sidebar</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>Start with sidebar collapsed</Text>
                        </div>
                        <Switch
                          checked={appearanceSettings.sidebarCollapsed}
                          onChange={(checked) => saveAppearanceSettings({ sidebarCollapsed: checked })}
                        />
                      </div>
                    </Space>
                  </div>
                </Card>
                
                <Card title="Live Preview" bordered={false} style={{ marginTop: 16 }}>
                  <div 
                    style={{ 
                      padding: 20, 
                      borderRadius: 12,
                      background: isDark ? '#262626' : '#fafafa',
                      border: `1px solid ${isDark ? '#434343' : '#d9d9d9'}`
                    }}
                  >
                    <div style={{ marginBottom: 12 }}>
                      <Text strong>Sample Dashboard Card</Text>
                    </div>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                      <Tag color={primaryColor}>Active</Tag>
                      <Tag color="default">Inactive</Tag>
                      <Tag color="success">Success</Tag>
                      <Tag color="error">Error</Tag>
                    </div>
                    <Space>
                      <Button type="primary">
                        Primary Button
                      </Button>
                      <Button>
                        Default Button
                      </Button>
                    </Space>
                  </div>
                </Card>
              </Col>
            </Row>
            
            <Card style={{ marginTop: 16 }}>
          <Alert
                message="Theme Settings"
                description="Theme preferences are stored locally in your browser. They will persist across sessions but are not synced across devices. Changes apply immediately to all pages."
                type="info"
            showIcon
          />
        </Card>
          </TabPane>
          
          {/* ================== ALERT RULES TAB ================== */}
          <TabPane 
            tab={<span><AlertOutlined /> Alert Rules</span>} 
            key="alerts"
          >
            <Card 
              title="Alert Rules Configuration" 
              bordered={false}
              extra={
                <Button 
                  type="primary" 
                  icon={<PlusOutlined />}
                  onClick={() => {
                    setEditingAlertRule(null);
                    alertRuleForm.resetFields();
                    alertRuleForm.setFieldsValue({
                      enabled: true,
                      severity: 'medium',
                      condition_type: 'threshold',
                      operator: 'gt',
                      duration_minutes: 5,
                      cooldown_minutes: 15,
                      notification_channels: ['email'],
                    });
                    setAlertRuleModalVisible(true);
                  }}
                  disabled={!isAdmin}
                >
                  New Alert Rule
                </Button>
              }
            >
              <Alert
                message="Alert Rules"
                description="Configure alert rules to get notified when specific conditions are met. Alerts can be sent via email, Slack, Teams, or webhooks."
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
              
              <Table
                dataSource={alertRules}
                rowKey="id"
                loading={alertRulesLoading}
                columns={[
                  {
                    title: 'Status',
                    dataIndex: 'enabled',
                    key: 'enabled',
                    width: 80,
                    render: (enabled: boolean) => (
                      enabled ? (
                        <Tag color="green"><PlayCircleOutlined /> Active</Tag>
                      ) : (
                        <Tag color="default"><PauseCircleOutlined /> Paused</Tag>
                      )
                    ),
                  },
                  {
                    title: 'Name',
                    dataIndex: 'name',
                    key: 'name',
                    render: (name: string, record: AlertRule) => (
                      <Space direction="vertical" size={0}>
                        <Text strong>{name}</Text>
                        <Text type="secondary" style={{ fontSize: 11 }}>{record.description}</Text>
                      </Space>
                    ),
                  },
                  {
                    title: 'Condition',
                    key: 'condition',
                    render: (_: any, record: AlertRule) => {
                      const operators: Record<string, string> = {
                        gt: '>',
                        lt: '<',
                        eq: '=',
                        gte: '>=',
                        lte: '<=',
                        contains: 'contains',
                      };
                      return (
                        <Space>
                          <Tag color="blue">{record.metric}</Tag>
                          <Text code>{operators[record.operator]} {record.threshold}</Text>
                          <Text type="secondary">for {record.duration_minutes}m</Text>
                        </Space>
                      );
                    },
                  },
                  {
                    title: 'Severity',
                    dataIndex: 'severity',
                    key: 'severity',
                    width: 100,
                    render: (severity: string) => {
                      const colors: Record<string, string> = {
                        critical: '#cf1322',
                        high: '#c75450',
                        medium: '#b89b5d',
                        low: '#4d9f7c',
                        info: '#0891b2',
                      };
                      return (
                        <Tag color={colors[severity]}>
                          {severity.toUpperCase()}
                        </Tag>
                      );
                    },
                  },
                  {
                    title: 'Channels',
                    dataIndex: 'notification_channels',
                    key: 'channels',
                    render: (channels: string[]) => (
                      <Space size={4}>
                        {channels?.map(ch => (
                          <Tag key={ch} style={{ fontSize: 10 }}>{ch}</Tag>
                        ))}
                      </Space>
                    ),
                  },
                  {
                    title: 'Last Triggered',
                    dataIndex: 'last_triggered',
                    key: 'last_triggered',
                    width: 140,
                    render: (time: string, record: AlertRule) => (
                      <Space direction="vertical" size={0}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {time ? new Date(time).toLocaleString() : 'Never'}
                        </Text>
                        {record.trigger_count !== undefined && record.trigger_count > 0 && (
                          <Tag color="orange" style={{ fontSize: 10 }}>
                            {record.trigger_count} triggers
                          </Tag>
                        )}
                      </Space>
                    ),
                  },
                  {
                    title: 'Actions',
                    key: 'actions',
                    width: 150,
                    render: (_: any, record: AlertRule) => (
                      <Space>
                        <Tooltip title={record.enabled ? 'Pause' : 'Enable'}>
                          <Button 
                            type="text" 
                            size="small"
                            icon={record.enabled ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                            onClick={() => {
                              // Toggle alert rule
                              setAlertRules(prev => prev.map(r => 
                                r.id === record.id ? { ...r, enabled: !r.enabled } : r
                              ));
                              message.success(`Alert ${record.enabled ? 'paused' : 'enabled'}`);
                            }}
                            disabled={!isAdmin}
                          />
                        </Tooltip>
                        <Tooltip title="Edit">
                          <Button 
                            type="text" 
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => {
                              setEditingAlertRule(record);
                              alertRuleForm.setFieldsValue(record);
                              setAlertRuleModalVisible(true);
                            }}
                            disabled={!isAdmin}
                          />
                        </Tooltip>
                        <Popconfirm
                          title="Delete this alert rule?"
                          onConfirm={() => {
                            setAlertRules(prev => prev.filter(r => r.id !== record.id));
                            message.success('Alert rule deleted');
                          }}
                          disabled={!isAdmin}
                        >
                          <Button 
                            type="text" 
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            disabled={!isAdmin}
                          />
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]}
                pagination={{ pageSize: 10 }}
                locale={{
                  emptyText: (
                    <div style={{ padding: 40, textAlign: 'center' }}>
                      <AlertOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
                      <div>
                        <Text type="secondary">No alert rules configured</Text>
                      </div>
                      <Button 
                        type="primary" 
                        icon={<PlusOutlined />} 
                        style={{ marginTop: 16 }}
                        onClick={() => {
                          setEditingAlertRule(null);
                          alertRuleForm.resetFields();
                          setAlertRuleModalVisible(true);
                        }}
                        disabled={!isAdmin}
                      >
                        Create First Alert Rule
                      </Button>
                    </div>
                  ),
                }}
              />
            </Card>
            
            {/* Integrations Card */}
            <Card 
              title="Notification Integrations" 
              bordered={false} 
              style={{ marginTop: 16 }}
              extra={
                <Button 
                  type="primary" 
                  icon={<SaveOutlined />} 
                  onClick={() => saveIntegrationSettings(integrationForm.getFieldsValue())}
                  disabled={!isAdmin}
                >
                  Save All Integrations
                </Button>
              }
            >
              <Form form={integrationForm} layout="vertical" disabled={!isAdmin}>
                <Row gutter={[16, 16]}>
                  <Col xs={24} md={12}>
                    <Card 
                      size="small" 
                      title={<Space><SlackOutlined style={{ color: '#4A154B' }} /> Slack</Space>}
                      bordered
                      extra={
                        <Form.Item name="slack_enabled" valuePropName="checked" noStyle>
                          <Switch size="small" />
            </Form.Item>
                      }
                    >
                      <Form.Item 
                        name="slack_webhook_url" 
                        label="Webhook URL" 
                        extra="Create an incoming webhook in Slack"
                      >
                        <Input placeholder="https://hooks.slack.com/services/..." />
                      </Form.Item>
                      <Form.Item name="slack_channel" label="Default Channel">
                        <Input placeholder="#alerts" />
                      </Form.Item>
                      <Button 
                        type="primary" 
                        size="small" 
                        icon={<SendOutlined />}
                        onClick={() => testIntegration('slack')}
                      >
                        Test Connection
                      </Button>
                    </Card>
                  </Col>
                  
                  <Col xs={24} md={12}>
                    <Card 
                      size="small" 
                      title={<Space><MessageOutlined style={{ color: '#6264A7' }} /> Microsoft Teams</Space>}
                      bordered
                      extra={
                        <Form.Item name="teams_enabled" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                      }
                    >
                      <Form.Item 
                        name="teams_webhook_url" 
                        label="Webhook URL" 
                        extra="Create an incoming webhook in Teams"
                      >
                        <Input placeholder="https://outlook.office.com/webhook/..." />
                      </Form.Item>
                      <Button 
                        type="primary" 
                        size="small" 
                        icon={<SendOutlined />}
                        onClick={() => testIntegration('teams')}
                      >
                        Test Connection
                      </Button>
                    </Card>
                  </Col>
                  
                  <Col xs={24} md={12}>
                    <Card 
                      size="small" 
                      title={<Space><ApiOutlined style={{ color: '#06AC38' }} /> Custom Webhook</Space>}
                      bordered
                      extra={
                        <Form.Item name="webhook_enabled" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                      }
                    >
                      <Form.Item name="webhook_url" label="Webhook URL">
                        <Input placeholder="https://your-service.com/webhook" />
                      </Form.Item>
                      <Form.Item name="webhook_secret" label="Secret Token" extra="Used for request signing">
                        <Input.Password placeholder="Optional secret" />
                      </Form.Item>
                      <Form.Item name="webhook_events" label="Events to Send">
                        <Select mode="multiple" placeholder="Select events">
                          <Option value="security_violation">Security Violations</Option>
                          <Option value="oom_event">OOM Events</Option>
                          <Option value="analysis_complete">Analysis Complete</Option>
                          <Option value="alert_triggered">Alert Triggered</Option>
                        </Select>
                      </Form.Item>
                      <Button 
                        type="primary" 
                        size="small" 
                        icon={<SendOutlined />}
                        onClick={async () => {
                          const values = integrationForm.getFieldsValue();
                          if (!values.webhook_url) {
                            message.warning('Please configure webhook URL first');
                            return;
                          }
                          try {
                            const response = await fetch('/api/v1/settings/integrations/test/webhook', {
                              method: 'POST',
                              headers: {
                                'Content-Type': 'application/json',
                                'Authorization': `Bearer ${getToken()}`
                              },
                              body: JSON.stringify({ url: values.webhook_url, secret: values.webhook_secret })
                            });
                            if (response.ok) {
                              message.success('Webhook test successful');
                            } else {
                              message.error('Webhook test failed');
                            }
                          } catch {
                            message.error('Webhook test failed');
                          }
                        }}
                      >
                        Test Connection
                      </Button>
                    </Card>
                  </Col>
                  
                  <Col xs={24} md={12}>
                    <Card 
                      size="small" 
                      title={<Space><BellOutlined style={{ color: '#25C151' }} /> PagerDuty</Space>}
                      bordered
                      extra={
                        <Form.Item name="pagerduty_enabled" valuePropName="checked" noStyle>
                          <Switch size="small" />
                        </Form.Item>
                      }
                    >
                      <Form.Item name="pagerduty_integration_key" label="Integration Key">
                        <Input.Password placeholder="PagerDuty Integration Key" />
                      </Form.Item>
                      <Form.Item name="pagerduty_service_id" label="Service ID">
                        <Input placeholder="Service ID" />
                      </Form.Item>
                      <Button 
                        type="primary" 
                        size="small" 
                        icon={<SendOutlined />}
                        onClick={() => testIntegration('pagerduty')}
                      >
                        Test Connection
                      </Button>
                    </Card>
                  </Col>
                </Row>
          </Form>
        </Card>
          </TabPane>
          
          {/* ================== SYSTEM INFO TAB ================== */}
          <TabPane 
            tab={<span><CloudServerOutlined /> System</span>} 
            key="system"
          >
            <Row gutter={24}>
              <Col xs={24} lg={12}>
                <Card title="System Information" bordered={false}>
                  <Row gutter={[16, 16]}>
                    <Col span={12}>
                      <Statistic title="Version" value={systemInfo.version} prefix={<InfoCircleOutlined />} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="Uptime" value={systemInfo.uptime} prefix={<ClockCircleOutlined />} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="Database Size" value={systemInfo.database_size} prefix={<DatabaseOutlined />} />
                    </Col>
                    <Col span={12}>
                      <Statistic 
                        title="Total Events" 
                        value={systemInfo.events_count} 
                        prefix={<ThunderboltOutlined />}
                        formatter={(value) => value?.toLocaleString()}
                      />
                    </Col>
                  </Row>
                  
                  <Divider />
                  
                  <List
                    header={<Text strong>Service Status</Text>}
                    dataSource={[
                      { name: 'ClickHouse', status: systemInfo.clickhouse_status },
                      { name: 'RabbitMQ', status: systemInfo.rabbitmq_status },
                      { name: 'Neo4j', status: systemInfo.neo4j_status }
                    ]}
                    renderItem={(item) => (
                      <List.Item>
                        <Text>{item.name}</Text>
                        {getStatusBadge(item.status)}
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
              
              <Col xs={24} lg={12}>
                <Card title="Maintenance" bordered={false}>
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
                    <Alert
                      message="Last Backup"
                      description={systemInfo.last_backup || 'No backup recorded'}
                      type="info"
                      showIcon
                      icon={<HistoryOutlined />}
                    />
                    
                    <Button 
                      icon={<ReloadOutlined />} 
                      onClick={fetchSystemInfo}
                      block
                    >
                      Refresh System Info
                    </Button>
                    
                    <Button 
                      icon={<DeleteOutlined />} 
                      onClick={runDataCleanup}
                      disabled={!isAdmin}
                      block
                    >
                      Run Data Cleanup
                    </Button>
                  </Space>
                </Card>
                
                <Card title="About Flowfish" bordered={false} style={{ marginTop: 16 }}>
          <Paragraph>
                    <Text strong>Flowfish</Text> is an enterprise Kubernetes observability platform 
                    powered by eBPF technology.
          </Paragraph>
                  <Paragraph type="secondary">
                    © 2026 Flowfish. All rights reserved.
                  </Paragraph>
                  <Space>
                    <Tag color="blue">eBPF</Tag>
                    <Tag color="green">Kubernetes</Tag>
                    <Tag color="purple">Observability</Tag>
                  </Space>
                </Card>
              </Col>
            </Row>
          </TabPane>
          
          {/* ================== AUDIT LOGS TAB ================== */}
          <TabPane 
            tab={<span><HistoryOutlined /> Audit Logs</span>} 
            key="audit"
          >
            <Card 
              title="System Audit Logs" 
              bordered={false}
              extra={
                <Space>
                  <Input.Search
                    placeholder="Search logs..."
                    value={auditLogSearch}
                    onChange={(e) => setAuditLogSearch(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                  />
                  <Select
                    value={auditLogFilter}
                    onChange={setAuditLogFilter}
                    style={{ width: 150 }}
                  >
                    <Option value="all">All Actions</Option>
                    <Option value="login">Login</Option>
                    <Option value="logout">Logout</Option>
                    <Option value="create_analysis">Create Analysis</Option>
                    <Option value="start_analysis">Start Analysis</Option>
                    <Option value="stop_analysis">Stop Analysis</Option>
                    <Option value="update_settings">Update Settings</Option>
                    <Option value="create_user">Create User</Option>
                  </Select>
                  <Button 
                    icon={<DownloadOutlined />} 
                    onClick={exportAuditLogs}
                  >
                    Export CSV
                  </Button>
                  <Button 
                    icon={<ReloadOutlined />} 
                    onClick={fetchAuditLogs}
                    loading={auditLogsLoading}
                  >
                    Refresh
                  </Button>
                </Space>
              }
            >
              <Table
                dataSource={filteredAuditLogs}
                rowKey="id"
                loading={auditLogsLoading}
                pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `Total ${total} logs` }}
                columns={[
                  {
                    title: 'Timestamp',
                    dataIndex: 'timestamp',
                    key: 'timestamp',
                    width: 180,
                    render: (ts: string) => new Date(ts).toLocaleString(),
                    sorter: (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
                    defaultSortOrder: 'descend',
                  },
                  {
                    title: 'User',
                    dataIndex: 'user',
                    key: 'user',
                    width: 120,
                    render: (user: string) => (
                      <Tag icon={<TeamOutlined />}>{user}</Tag>
                    ),
                  },
                  {
                    title: 'Action',
                    dataIndex: 'action',
                    key: 'action',
                    width: 150,
                    render: (action: string) => {
                      const colors: Record<string, string> = {
                        login: 'green',
                        logout: 'default',
                        create_analysis: 'blue',
                        start_analysis: 'cyan',
                        stop_analysis: 'orange',
                        delete_analysis: 'red',
                        update_settings: 'purple',
                        create_user: 'geekblue',
                        update_role: 'magenta',
                      };
                      return <Tag color={colors[action] || 'default'}>{action.replace(/_/g, ' ')}</Tag>;
                    },
                  },
                  {
                    title: 'Resource',
                    key: 'resource',
                    width: 150,
                    render: (_: any, record: AuditLog) => (
                      <Text type="secondary">{record.resource_type} #{record.resource_id}</Text>
                    ),
                  },
                  {
                    title: 'IP Address',
                    dataIndex: 'ip_address',
                    key: 'ip_address',
                    width: 130,
                  },
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    key: 'status',
                    width: 100,
                    render: (status: string) => (
                      <Badge 
                        status={status === 'success' ? 'success' : 'error'} 
                        text={status}
                      />
                    ),
                  },
                ]}
              />
            </Card>
          </TabPane>
          
          {/* ================== BACKUP/RESTORE TAB ================== */}
          <TabPane 
            tab={<span><DatabaseOutlined /> Backup</span>} 
            key="backup"
          >
            <Row gutter={24}>
              <Col xs={24} lg={8}>
                <Card title="Create Backup" bordered={false}>
                  <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Alert
                      message="Backup Options"
                      description="Choose the type of backup to create. Full backups include all data and configurations."
                      type="info"
            showIcon
                    />
                    
                    <Button 
                      type="primary"
                      icon={<DatabaseOutlined />}
                      onClick={() => createBackup('full')}
                      loading={creatingBackup}
                      block
                      size="large"
                    >
                      Full System Backup
                    </Button>
                    
                    <Button 
                      icon={<SettingOutlined />}
                      onClick={() => createBackup('config')}
                      loading={creatingBackup}
                      block
                    >
                      Configuration Only
                    </Button>
                    
                    <Button 
                      icon={<ThunderboltOutlined />}
                      onClick={() => createBackup('data')}
                      loading={creatingBackup}
                      block
                    >
                      Data Only
                    </Button>
                    
                    <Divider />
                    
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <InfoCircleOutlined style={{ marginRight: 4 }} />
                      Backups are stored securely and can be used to restore the system to a previous state.
                    </Text>
                  </Space>
        </Card>
              </Col>
              
              <Col xs={24} lg={16}>
                <Card 
                  title="Available Backups" 
                  bordered={false}
                  extra={
                    <Button 
                      icon={<ReloadOutlined />} 
                      onClick={fetchBackups}
                      loading={backupsLoading}
                    >
                      Refresh
                    </Button>
                  }
                >
                  <Table
                    dataSource={backups}
                    rowKey="id"
                    loading={backupsLoading}
                    pagination={false}
                    columns={[
                      {
                        title: 'Name',
                        dataIndex: 'name',
                        key: 'name',
                        render: (name: string, record: BackupInfo) => (
                          <Space>
                            <DatabaseOutlined style={{ 
                              color: record.type === 'full' ? '#0891b2' : 
                                     record.type === 'config' ? '#7c8eb5' : '#4d9f7c' 
                            }} />
                            <div>
                              <Text strong>{name}</Text>
                              <br />
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {new Date(record.created_at).toLocaleString()}
                              </Text>
                            </div>
      </Space>
                        ),
                      },
                      {
                        title: 'Type',
                        dataIndex: 'type',
                        key: 'type',
                        width: 100,
                        render: (type: string) => (
                          <Tag color={
                            type === 'full' ? 'blue' : 
                            type === 'config' ? 'purple' : 'green'
                          }>
                            {type.toUpperCase()}
                          </Tag>
                        ),
                      },
                      {
                        title: 'Size',
                        dataIndex: 'size',
                        key: 'size',
                        width: 100,
                      },
                      {
                        title: 'Status',
                        dataIndex: 'status',
                        key: 'status',
                        width: 120,
                        render: (status: string) => (
                          <Badge 
                            status={
                              status === 'completed' ? 'success' : 
                              status === 'in_progress' ? 'processing' : 'error'
                            } 
                            text={status.replace(/_/g, ' ')}
                          />
                        ),
                      },
                      {
                        title: 'Actions',
                        key: 'actions',
                        width: 200,
                        render: (_: any, record: BackupInfo) => (
                          <Space>
                            <Tooltip title="Download backup">
                              <Button 
                                size="small" 
                                icon={<DownloadOutlined />}
                                onClick={() => downloadBackup(record)}
                                disabled={record.status !== 'completed'}
                              />
                            </Tooltip>
                            <Tooltip title="Restore from this backup">
                              <Button 
                                size="small" 
                                icon={<RollbackOutlined />}
                                onClick={() => restoreBackup(record.id)}
                                loading={restoringBackup === record.id}
                                disabled={record.status !== 'completed' || !isAdmin}
                              />
                            </Tooltip>
                            <Tooltip title="Delete backup">
                              <Button 
                                size="small" 
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => deleteBackup(record.id)}
                                disabled={!isAdmin}
                              />
                            </Tooltip>
                          </Space>
                        ),
                      },
                    ]}
                  />
                  
                  {backups.length === 0 && !backupsLoading && (
                    <div style={{ textAlign: 'center', padding: 32 }}>
                      <DatabaseOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
                      <br />
                      <Text type="secondary">No backups available</Text>
    </div>
                  )}
                </Card>
              </Col>
            </Row>
          </TabPane>
          
          {/* ================== API KEYS TAB ================== */}
          <TabPane 
            tab={<span><KeyOutlined /> API Keys</span>} 
            key="api-tokens"
          >
            <Row gutter={[24, 24]}>
              <Col span={24}>
                <Card 
                  bordered={false}
                  title={
                    <Space>
                      <KeyOutlined style={{ color: '#d4a844' }} />
                      <span>API Keys for CI/CD Pipelines</span>
                      <Badge count={apiTokens.filter(t => t.is_active).length} style={{ backgroundColor: '#52c41a' }} />
                    </Space>
                  }
                  extra={
                    <Button 
                      type="primary" 
                      icon={<PlusOutlined />}
                      onClick={() => setApiTokenModalVisible(true)}
                    >
                      Generate New API Key
                    </Button>
                  }
                >
                  <Alert
                    message="API Keys for CI/CD Pipelines"
                    description={
                      <div>
                        <Text>API keys provide programmatic access to Flowfish APIs (e.g., Blast Radius assessment). Use them in your Azure DevOps, Jenkins, or GitHub Actions pipelines.</Text>
                        <br /><br />
                        <Text strong>Usage:</Text> <Text code>X-API-Key: fk_your_key_here</Text>
                        <br />
                        <Text type="secondary">Keys are only shown once when created - store them securely!</Text>
                      </div>
                    }
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  
                  {/* Pipeline Integration Guide */}
                  <Collapse 
                    ghost 
                    style={{ marginBottom: 16, background: isDark ? '#1f1f1f' : '#fafafa', borderRadius: 8 }}
                  >
                    <Panel 
                      header={
                        <Space>
                          <ThunderboltOutlined style={{ color: '#faad14' }} />
                          <Text strong>Pipeline Integration Guide</Text>
                          <Tag color="orange">Blast Radius API</Tag>
                        </Space>
                      } 
                      key="pipeline-guide"
                    >
                      <div style={{ padding: '8px 0' }}>
                        {/* Available Clusters */}
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>
                          <CloudServerOutlined /> Available Clusters
                        </Text>
                        {pipelineClustersLoading ? (
                          <Spin size="small" />
                        ) : pipelineClusters.length > 0 ? (
                          <Table
                            dataSource={pipelineClusters}
                            rowKey="id"
                            size="small"
                            pagination={false}
                            style={{ marginBottom: 16 }}
                            columns={[
                              {
                                title: 'Cluster ID',
                                dataIndex: 'id',
                                key: 'id',
                                width: 100,
                                render: (id: number) => (
                                  <Space>
                                    <Text code style={{ fontSize: 14, fontWeight: 'bold' }}>{id}</Text>
                                    <Button 
                                      type="text" 
                                      size="small" 
                                      icon={<CopyOutlined />} 
                                      onClick={() => copyToClipboard(String(id))}
                                    />
                                  </Space>
                                ),
                              },
                              {
                                title: 'Name',
                                dataIndex: 'name',
                                key: 'name',
                              },
                              {
                                title: 'Environment',
                                dataIndex: 'environment',
                                key: 'environment',
                                render: (env: string) => (
                                  <Tag color={env === 'production' ? 'red' : env === 'staging' ? 'orange' : 'blue'}>
                                    {env}
                                  </Tag>
                                ),
                              },
                              {
                                title: 'Status',
                                dataIndex: 'status',
                                key: 'status',
                                render: (status: string) => (
                                  <Badge status={status === 'active' ? 'success' : 'default'} text={status} />
                                ),
                              },
                            ]}
                          />
                        ) : (
                          <Text type="secondary">No clusters available</Text>
                        )}
                        
                        <Divider style={{ margin: '12px 0' }} />
                        
                        {/* Example Curl Commands */}
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>
                          <ApiOutlined /> Example: Namespace Blast Radius
                        </Text>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                          Assess the blast radius for an entire namespace (recommended for CI/CD):
                        </Text>
                        <Input.TextArea
                          value={`curl -X POST "${window.location.origin}/api/v1/blast-radius/namespace" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -d '{
    "cluster_id": ${pipelineClusters[0]?.id || 2},
    "namespace": "your-namespace"
  }'`}
                          readOnly
                          autoSize={{ minRows: 6 }}
                          style={{ fontFamily: 'monospace', fontSize: 12, marginBottom: 8 }}
                        />
                        <Button 
                          size="small" 
                          icon={<CopyOutlined />} 
                          onClick={() => copyToClipboard(`curl -X POST "${window.location.origin}/api/v1/blast-radius/namespace" -H "Content-Type: application/json" -H "X-API-Key: YOUR_API_KEY" -d '{"cluster_id": ${pipelineClusters[0]?.id || 2}, "namespace": "your-namespace"}'`)}
                        >
                          Copy Command
                        </Button>
                        
                        <Divider style={{ margin: '12px 0' }} />
                        
                        <Text strong style={{ display: 'block', marginBottom: 8 }}>
                          <ApiOutlined /> Example: Service Blast Radius
                        </Text>
                        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                          Assess the blast radius for a specific service change:
                        </Text>
                        <Input.TextArea
                          value={`curl -X POST "${window.location.origin}/api/v1/blast-radius/assess" \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -d '{
    "cluster_id": ${pipelineClusters[0]?.id || 2},
    "change": {
      "target": "your-service",
      "namespace": "your-namespace",
      "type": "image_update"
    }
  }'`}
                          readOnly
                          autoSize={{ minRows: 9 }}
                          style={{ fontFamily: 'monospace', fontSize: 12, marginBottom: 8 }}
                        />
                        <Button 
                          size="small" 
                          icon={<CopyOutlined />} 
                          onClick={() => copyToClipboard(`curl -X POST "${window.location.origin}/api/v1/blast-radius/assess" -H "Content-Type: application/json" -H "X-API-Key: YOUR_API_KEY" -d '{"cluster_id": ${pipelineClusters[0]?.id || 2}, "change": {"target": "your-service", "namespace": "your-namespace", "type": "image_update"}}'`)}
                        >
                          Copy Command
                        </Button>
                      </div>
                    </Panel>
                  </Collapse>
                  
                  {/* Newly Created Token Display */}
                  {newlyCreatedToken && (
                    <Alert
                      message="New Token Created - Copy it now!"
                      description={
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Text>This is the only time you'll see this token. Make sure to copy it now.</Text>
                          <Input.Group compact style={{ display: 'flex' }}>
                            <Input 
                              value={newlyCreatedToken} 
                              readOnly 
                              style={{ flex: 1, fontFamily: 'monospace' }}
                            />
                            <Button 
                              icon={<CopyOutlined />} 
                              onClick={() => copyToClipboard(newlyCreatedToken)}
                            >
                              Copy
                            </Button>
                          </Input.Group>
                        </Space>
                      }
                      type="success"
                      showIcon
                      closable
                      onClose={() => setNewlyCreatedToken(null)}
                      style={{ marginBottom: 16 }}
                    />
                  )}
                  
                  <Table
                    dataSource={apiTokens}
                    rowKey="key_id"
                    loading={apiTokensLoading}
                    pagination={false}
                    columns={[
                      {
                        title: 'Name',
                        dataIndex: 'name',
                        key: 'name',
                        render: (name: string, record: APIToken) => (
                          <Space>
                            <KeyOutlined style={{ color: record.is_active ? '#52c41a' : '#d9d9d9' }} />
                            <div>
                              <Text strong>{name}</Text>
                              <br />
                              <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                                {record.key_prefix}...
                              </Text>
                            </div>
                          </Space>
                        ),
                      },
                      {
                        title: 'Scopes',
                        dataIndex: 'scopes',
                        key: 'scopes',
                        render: (scopes: string[]) => (
                          <Space wrap size={4}>
                            {(scopes || []).map(scope => (
                              <Tag key={scope} color={scope === 'blast-radius' ? 'orange' : 'blue'} style={{ fontSize: 10 }}>
                                {scope}
                              </Tag>
                            ))}
                          </Space>
                        ),
                      },
                      {
                        title: 'Usage',
                        dataIndex: 'usage_count',
                        key: 'usage_count',
                        render: (count: number, record: APIToken) => (
                          <Tooltip title={record.last_used_ip ? `Last IP: ${record.last_used_ip}` : 'Never used'}>
                            <Text style={{ fontSize: 12 }}>
                              {count || 0} calls
                            </Text>
                          </Tooltip>
                        ),
                      },
                      {
                        title: 'Expires',
                        dataIndex: 'expires_at',
                        key: 'expires_at',
                        render: (date: string | null) => {
                          if (!date) return <Tag color="green">Never</Tag>;
                          const isExpired = new Date(date) < new Date();
                          return (
                            <Tag color={isExpired ? 'red' : 'default'}>
                              {isExpired ? 'Expired' : new Date(date).toLocaleDateString()}
                            </Tag>
                          );
                        },
                      },
                      {
                        title: 'Last Used',
                        dataIndex: 'last_used_at',
                        key: 'last_used_at',
                        render: (date: string | null) => (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {date ? new Date(date).toLocaleString() : 'Never'}
                          </Text>
                        ),
                      },
                      {
                        title: 'Status',
                        dataIndex: 'is_active',
                        key: 'is_active',
                        render: (active: boolean) => (
                          <Badge 
                            status={active ? 'success' : 'error'} 
                            text={active ? 'Active' : 'Revoked'} 
                          />
                        ),
                      },
                      {
                        title: 'Actions',
                        key: 'actions',
                        render: (_: any, record: APIToken) => (
                          <Popconfirm
                            title="Revoke this API key?"
                            description="Pipelines using this key will stop working."
                            onConfirm={() => revokeApiToken(record.key_id, record.name)}
                            okText="Revoke"
                            okType="danger"
                            disabled={!record.is_active}
                          >
                            <Button 
                              size="small" 
                              danger 
                              disabled={!record.is_active}
                            >
                              Revoke
                            </Button>
                          </Popconfirm>
                        ),
                      },
                    ]}
                  />
                  
                  {apiTokens.length === 0 && !apiTokensLoading && (
                    <div style={{ textAlign: 'center', padding: 32 }}>
                      <KeyOutlined style={{ fontSize: 48, color: '#d9d9d9', marginBottom: 16 }} />
                      <br />
                      <Text type="secondary">No API keys created yet</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>Generate an API key to integrate Flowfish with your CI/CD pipelines</Text>
                      <br /><br />
                      <Button 
                        type="link" 
                        onClick={() => setApiTokenModalVisible(true)}
                      >
                        Create your first token
                      </Button>
                    </div>
                  )}
                </Card>
              </Col>
              
              {/* API Documentation */}
              <Col span={24}>
                <Card 
                  bordered={false}
                  title={
                    <Space>
                      <ApiOutlined style={{ color: '#1890ff' }} />
                      <span>API Usage</span>
                    </Space>
                  }
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Text>Use your API token in the Authorization header:</Text>
                    <Input.TextArea
                      value={`curl -H "Authorization: Bearer YOUR_TOKEN" \\
     https://api.flowfish.io/api/v1/clusters`}
                      readOnly
                      autoSize={{ minRows: 2 }}
                      style={{ fontFamily: 'monospace', fontSize: 12 }}
                    />
                    
                    <Divider />
                    
                    <Title level={5}>Available Scopes</Title>
                    <Row gutter={[16, 8]}>
                      <Col span={8}>
                        <Tag color="blue">read:clusters</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          View cluster information
                        </Text>
                      </Col>
                      <Col span={8}>
                        <Tag color="blue">read:analyses</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          View analysis data
                        </Text>
                      </Col>
                      <Col span={8}>
                        <Tag color="blue">write:analyses</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          Create/manage analyses
                        </Text>
                      </Col>
                      <Col span={8}>
                        <Tag color="blue">read:events</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          View event data
                        </Text>
                      </Col>
                      <Col span={8}>
                        <Tag color="blue">read:reports</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          Generate reports
                        </Text>
                      </Col>
                      <Col span={8}>
                        <Tag color="gold">admin</Tag>
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                          Full administrative access
                        </Text>
                      </Col>
                    </Row>
                  </Space>
                </Card>
              </Col>
            </Row>
          </TabPane>
        </Tabs>
      </Space>
      
      {/* API Key Modal */}
      <Modal
        title="Generate New API Key"
        open={apiTokenModalVisible}
        onCancel={() => {
          setApiTokenModalVisible(false);
          apiTokenForm.resetFields();
        }}
        onOk={() => apiTokenForm.submit()}
        confirmLoading={creatingToken}
        width={500}
      >
        <Form
          form={apiTokenForm}
          layout="vertical"
          onFinish={createApiToken}
          initialValues={{
            scopes: ['blast-radius'],
            expires_in_days: null,
          }}
        >
          <Form.Item
            name="name"
            label="API Key Name"
            rules={[{ required: true, message: 'Please enter a name for this key' }]}
          >
            <Input placeholder="e.g., prod-deploy-pipeline, jenkins-blast-radius" />
          </Form.Item>
          
          <Form.Item
            name="scopes"
            label="Scopes (Permissions)"
            rules={[{ required: true, message: 'Please select at least one scope' }]}
            tooltip="Select which APIs this key can access"
          >
            <Checkbox.Group style={{ width: '100%' }}>
              <Row gutter={[8, 16]}>
                <Col span={24}>
                  <Checkbox value="blast-radius">
                    <Space>
                      <Tag color="orange">blast-radius</Tag>
                      <Text type="secondary">Access Blast Radius assessment API (CI/CD)</Text>
                    </Space>
                  </Checkbox>
                </Col>
                <Col span={24}>
                  <Checkbox value="read">
                    <Space>
                      <Tag color="blue">read</Tag>
                      <Text type="secondary">Read-only access to clusters and analyses</Text>
                    </Space>
                  </Checkbox>
                </Col>
                <Col span={24}>
                  <Checkbox value="write">
                    <Space>
                      <Tag color="green">write</Tag>
                      <Text type="secondary">Create and modify analyses</Text>
                    </Space>
                  </Checkbox>
                </Col>
              </Row>
            </Checkbox.Group>
          </Form.Item>
          
          <Form.Item
            name="expires_in_days"
            label="Expiration"
            tooltip="For security, consider setting an expiration date"
          >
            <Select>
              <Option value={null}>Never expire (use for permanent pipelines)</Option>
              <Option value={30}>30 days</Option>
              <Option value={90}>90 days</Option>
              <Option value={180}>180 days</Option>
              <Option value={365}>1 year</Option>
            </Select>
          </Form.Item>
          
          <Alert
            message="Important: Copy Your Key!"
            description="The API key will be shown only once after creation. Store it securely in your pipeline's secret variables (e.g., Azure DevOps variable group, Jenkins credentials)."
            type="warning"
            showIcon
          />
        </Form>
      </Modal>
      
      {/* Alert Rule Modal */}
      <Modal
        title={editingAlertRule ? 'Edit Alert Rule' : 'New Alert Rule'}
        open={alertRuleModalVisible}
        onCancel={() => {
          setAlertRuleModalVisible(false);
          setEditingAlertRule(null);
          alertRuleForm.resetFields();
        }}
        onOk={() => alertRuleForm.submit()}
        confirmLoading={savingAlertRule}
        width={700}
      >
        <Form
          form={alertRuleForm}
          layout="vertical"
          onFinish={(values) => {
            setSavingAlertRule(true);
            setTimeout(() => {
              if (editingAlertRule) {
                setAlertRules(prev => prev.map(r => 
                  r.id === editingAlertRule.id ? { ...r, ...values } : r
                ));
                message.success('Alert rule updated');
              } else {
                const newRule: AlertRule = {
                  id: Date.now(),
                  ...values,
                  created_at: new Date().toISOString(),
                  trigger_count: 0,
                };
                setAlertRules(prev => [...prev, newRule]);
                message.success('Alert rule created');
              }
              setAlertRuleModalVisible(false);
              setEditingAlertRule(null);
              alertRuleForm.resetFields();
              setSavingAlertRule(false);
            }, 500);
          }}
          initialValues={{
            enabled: true,
            severity: 'medium',
            condition_type: 'threshold',
            operator: 'gt',
            duration_minutes: 5,
            cooldown_minutes: 15,
            notification_channels: ['email'],
          }}
        >
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item
                name="name"
                label="Rule Name"
                rules={[{ required: true, message: 'Please enter a name' }]}
              >
                <Input placeholder="e.g., High CPU Usage Alert" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="enabled" label="Status" valuePropName="checked">
                <Switch checkedChildren="Active" unCheckedChildren="Paused" />
              </Form.Item>
            </Col>
          </Row>
          
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} placeholder="Describe what this alert monitors..." />
          </Form.Item>
          
          <Divider orientation="left">Condition</Divider>
          
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="condition_type"
                label="Condition Type"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="threshold">Threshold</Option>
                  <Option value="anomaly">Anomaly Detection</Option>
                  <Option value="pattern">Pattern Match</Option>
                  <Option value="absence">Absence of Data</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="metric"
                label="Metric"
                rules={[{ required: true, message: 'Select a metric' }]}
              >
                <Select showSearch placeholder="Select metric">
                  <Option value="cpu_utilization">CPU Utilization (%)</Option>
                  <Option value="memory_utilization">Memory Utilization (%)</Option>
                  <Option value="error_rate">Error Rate (%)</Option>
                  <Option value="request_latency_p95">Request Latency p95 (ms)</Option>
                  <Option value="request_latency_p99">Request Latency p99 (ms)</Option>
                  <Option value="requests_per_second">Requests per Second</Option>
                  <Option value="security_violations">Security Violations</Option>
                  <Option value="oom_events">OOM Events</Option>
                  <Option value="pod_restarts">Pod Restarts</Option>
                  <Option value="network_errors">Network Errors</Option>
                  <Option value="dns_failures">DNS Failures</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="severity"
                label="Severity"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="critical">
                    <Tag color="#cf1322">Critical</Tag>
                  </Option>
                  <Option value="high">
                    <Tag color="#c75450">High</Tag>
                  </Option>
                  <Option value="medium">
                    <Tag color="#b89b5d">Medium</Tag>
                  </Option>
                  <Option value="low">
                    <Tag color="#4d9f7c">Low</Tag>
                  </Option>
                  <Option value="info">
                    <Tag color="#0891b2">Info</Tag>
                  </Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>
          
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="operator"
                label="Operator"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="gt">&gt; Greater than</Option>
                  <Option value="gte">&ge; Greater or equal</Option>
                  <Option value="lt">&lt; Less than</Option>
                  <Option value="lte">&le; Less or equal</Option>
                  <Option value="eq">= Equal to</Option>
                  <Option value="contains">Contains</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="threshold"
                label="Threshold Value"
                rules={[{ required: true, message: 'Enter threshold' }]}
              >
                <InputNumber style={{ width: '100%' }} placeholder="80" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="duration_minutes"
                label="Duration"
                rules={[{ required: true }]}
                extra="Condition must persist for this duration"
              >
                <InputNumber min={1} max={60} addonAfter="minutes" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          
          <Divider orientation="left">Notifications</Divider>
          
          <Row gutter={16}>
            <Col span={16}>
              <Form.Item
                name="notification_channels"
                label="Notification Channels"
                rules={[{ required: true, message: 'Select at least one channel' }]}
              >
                <Select mode="multiple" placeholder="Select channels">
                  <Option value="email">Email</Option>
                  <Option value="slack">Slack</Option>
                  <Option value="teams">Microsoft Teams</Option>
                  <Option value="pagerduty">PagerDuty</Option>
                  <Option value="webhook">Custom Webhook</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="cooldown_minutes"
                label="Cooldown"
                rules={[{ required: true }]}
                extra="Time between repeated alerts"
              >
                <InputNumber min={1} max={1440} addonAfter="minutes" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  );
};

export default Settings;
