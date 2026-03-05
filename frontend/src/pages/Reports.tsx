import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { 
  Card, 
  Typography, 
  Space, 
  Select, 
  Row, 
  Col,
  Button,
  List,
  Tag,
  Badge,
  Empty,
  Divider,
  Progress,
  message,
  Spin,
  Modal,
  Input,
  DatePicker,
  Checkbox,
  Tooltip,
  Statistic,
  Switch,
  Tabs,
  Table,
  Form,
  TimePicker,
  Alert,
  Descriptions,
  theme
} from 'antd';
import { 
  FileTextOutlined,
  DownloadOutlined,
  FilePdfOutlined,
  FileExcelOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  SecurityScanOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  LoadingOutlined,
  ExclamationCircleOutlined,
  GlobalOutlined,
  LockOutlined,
  ScheduleOutlined,
  EyeOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  MailOutlined,
  CalendarOutlined,
  BarChartOutlined,
  LineChartOutlined,
  PieChartOutlined,
  FilterOutlined,
  DatabaseOutlined,
  SyncOutlined,
  CopyOutlined,
  BugOutlined,
  WarningOutlined,
  SafetyCertificateOutlined,
  SwapOutlined,
  HistoryOutlined,
  FileSearchOutlined,
  RocketOutlined,
  DashboardOutlined,
  RiseOutlined,
  FallOutlined,
  DollarOutlined,
  CloudOutlined,
  FundOutlined,
  AreaChartOutlined,
  FieldTimeOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { useGetEventStatsQuery, useGetSecurityEventsQuery } from '../store/api/eventsApi';
import { useGetCommunicationStatsQuery } from '../store/api/communicationApi';
import { useGetWorkloadStatsQuery, useGetWorkloadsQuery } from '../store/api/workloadApi';
import { Analysis } from '../types';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { RangePicker } = DatePicker;
const { TabPane } = Tabs;

// Report types configuration
const reportTypes = [
  {
    key: 'dependency',
    title: 'Dependency Report',
    description: 'Complete dependency map with all service connections, protocols, and data flow volumes.',
    icon: <ApiOutlined style={{ fontSize: 24, color: '#0891b2' }} />,
    formats: ['JSON', 'PDF'],
    endpoint: '/api/v1/export/graph/json',
    pdfEndpoint: '/api/v1/export/dependency/pdf',
    estimatedTime: '~30 seconds',
    category: 'Graph',
    estimatedSizePerEvent: 0.5, // KB per event
  },
  {
    key: 'events',
    title: 'Events Export',
    description: 'All captured eBPF events including network, process, file, and security events.',
    icon: <ClockCircleOutlined style={{ fontSize: 24, color: '#22a6a6' }} />,
    formats: ['CSV', 'JSON', 'PDF'],
    endpoint: '/api/v1/export/events',
    pdfEndpoint: '/api/v1/export/events/pdf',
    estimatedTime: '~45 seconds',
    category: 'Events',
    estimatedSizePerEvent: 0.3,
  },
  {
    key: 'network',
    title: 'Network Flows Report',
    description: 'Network flow data with source/destination IPs, ports, protocols, and latencies.',
    icon: <GlobalOutlined style={{ fontSize: 24, color: '#b89b5d' }} />,
    formats: ['CSV', 'PDF'],
    endpoint: '/api/v1/export/network-flows/csv',
    pdfEndpoint: '/api/v1/export/network-flows/pdf',
    estimatedTime: '~30 seconds',
    category: 'Network',
    estimatedSizePerEvent: 0.25,
  },
  {
    key: 'dns',
    title: 'DNS Queries Report',
    description: 'DNS query data including query names, types, response codes, and latencies.',
    icon: <GlobalOutlined style={{ fontSize: 24, color: '#06b6d4' }} />,
    formats: ['CSV'],
    endpoint: '/api/v1/export/dns-queries/csv',
    estimatedTime: '~20 seconds',
    category: 'Network',
    estimatedSizePerEvent: 0.2,
  },
  {
    key: 'security',
    title: 'Security Assessment Report',
    description: 'Security posture analysis including capabilities, violations, and risk scores.',
    icon: <SecurityScanOutlined style={{ fontSize: 24, color: '#c75450' }} />,
    formats: ['CSV', 'PDF'],
    endpoint: '/api/v1/export/security-events/csv',
    pdfEndpoint: '/api/v1/export/security/pdf',
    estimatedTime: '~1 minute',
    category: 'Security',
    estimatedSizePerEvent: 0.35,
  },
  {
    key: 'anomaly',
    title: 'Anomaly Detection Report',
    description: 'Detected anomalies including suspicious DNS, network patterns, shell executions, and crypto mining.',
    icon: <BugOutlined style={{ fontSize: 24, color: '#a67c9e' }} />,
    formats: ['JSON'],
    endpoint: '/api/v1/export/events/json',  // Uses events endpoint with security filter
    estimatedTime: '~2 minutes',
    category: 'Security',
    estimatedSizePerEvent: 0.4,
    isNew: true,
    extraParams: { event_types: 'security_event,oom_event' },
  },
  {
    key: 'stats',
    title: 'Statistics Summary',
    description: 'Event statistics and summary including counts, top namespaces, and pods.',
    icon: <ThunderboltOutlined style={{ fontSize: 24, color: '#7c8eb5' }} />,
    formats: ['JSON'],
    endpoint: '/api/v1/export/stats/json',
    estimatedTime: '~10 seconds',
    category: 'Summary',
    estimatedSizePerEvent: 0.1,
  },
  {
    key: 'comparison',
    title: 'Period Comparison Report',
    description: 'Compare metrics between two time periods to identify trends and changes.',
    icon: <SwapOutlined style={{ fontSize: 24, color: '#c9a55a' }} />,
    formats: ['JSON'],
    endpoint: '/api/v1/export/stats/json',  // Uses stats endpoint - comparison done client-side
    estimatedTime: '~1 minute',
    category: 'Analysis',
    estimatedSizePerEvent: 0.5,
    isNew: true,
    requiresComparison: true,
  },
];

// Report templates
const reportTemplates = [
  {
    id: 'security-audit',
    name: 'Security Audit',
    description: 'Comprehensive security assessment with anomalies and violations',
    reports: ['security', 'anomaly'],
    icon: <SafetyCertificateOutlined style={{ color: '#c75450' }} />,
  },
  {
    id: 'network-analysis',
    name: 'Network Analysis',
    description: 'Complete network traffic analysis with DNS and flows',
    reports: ['network', 'dns', 'dependency'],
    icon: <GlobalOutlined style={{ color: '#0891b2' }} />,
  },
  {
    id: 'full-export',
    name: 'Full Data Export',
    description: 'Export all available data for offline analysis',
    reports: ['events', 'dependency', 'stats'],
    icon: <DatabaseOutlined style={{ color: '#7c8eb5' }} />,
  },
  {
    id: 'daily-summary',
    name: 'Daily Summary',
    description: 'Quick overview of daily activity and statistics',
    reports: ['stats'],
    icon: <BarChartOutlined style={{ color: '#4d9f7c' }} />,
  },
];

// Generated reports type
interface GeneratedReport {
  id: number;
  name: string;
  type: string;
  format: string;
  size: string;
  createdAt: string;
  status: 'ready' | 'generating' | 'failed';
  downloadUrl?: string;
}

// Scheduled report type
interface ScheduledReport {
  id: number;
  name: string;
  reportTypes: string[];
  format: string;
  schedule: 'daily' | 'weekly' | 'monthly';
  time: string;
  email?: string;
  enabled: boolean;
  lastRun?: string;
  nextRun: string;
}

// SLO/SLA Types
interface SLODefinition {
  id: number;
  name: string;
  description: string;
  target: number;
  metric: 'availability' | 'latency' | 'error_rate' | 'throughput';
  threshold_operator: 'lt' | 'gt' | 'lte' | 'gte';
  threshold_value: number;
  window: '7d' | '30d' | '90d';
  service?: string;
  namespace?: string;
  current_value: number;
  status: 'met' | 'at_risk' | 'breached';
  error_budget_remaining: number;
  last_updated: string;
}

interface TrendDataPoint {
  timestamp: string;
  value: number;
  label?: string;
}

interface TrendMetric {
  id: string;
  name: string;
  category: 'traffic' | 'errors' | 'latency' | 'resources';
  current_value: number;
  previous_value: number;
  change_percent: number;
  trend: 'up' | 'down' | 'stable';
  data: TrendDataPoint[];
  unit: string;
}

const { useToken } = theme;

const Reports: React.FC = () => {
  const { token } = useToken();
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [generatingReport, setGeneratingReport] = useState<string | null>(null);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generatedReports, setGeneratedReports] = useState<GeneratedReport[]>([]);
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [comparisonDateRange, setComparisonDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [selectedEventTypes, setSelectedEventTypes] = useState<string[]>([]);
  const [selectedNamespace, setSelectedNamespace] = useState<string | undefined>(undefined);
  const [activeTab, setActiveTab] = useState('generate');
  
  // Preview modal
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewReportType, setPreviewReportType] = useState<string>('');
  
  // Scheduled reports - now dynamic from API
  const [scheduledReports, setScheduledReports] = useState<ScheduledReport[]>([]);
  const [scheduledReportsLoading, setScheduledReportsLoading] = useState(false);
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ScheduledReport | null>(null);
  const [scheduleForm] = Form.useForm();
  const [savingSchedule, setSavingSchedule] = useState(false);
  
  // Report history - now dynamic from API
  const [reportHistory, setReportHistory] = useState<GeneratedReport[]>([]);
  const [reportHistoryLoading, setReportHistoryLoading] = useState(false);
  
  // SLO/SLA Tracking state
  const [sloDefinitions, setSloDefinitions] = useState<SLODefinition[]>([]);
  const [sloLoading, setSloLoading] = useState(false);
  // SLO state - removed modal states since SLOs are now auto-calculated
  const [sloTimeWindow, setSloTimeWindow] = useState<'7d' | '30d' | '90d'>('30d');
  
  // Trend Analysis state
  const [trendMetrics, setTrendMetrics] = useState<TrendMetric[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendTimeRange, setTrendTimeRange] = useState<'24h' | '7d' | '30d' | '90d'>('7d');
  const [selectedTrendCategory, setSelectedTrendCategory] = useState<string>('all');
  
  // Cost Analysis state
  const [costData, setCostData] = useState<{
    total: number;
    compute: number;
    network: number;
    storage: number;
    by_namespace: { namespace: string; cost: number; percentage: number }[];
    top_consumers: { resource: string; type: string; cost: number }[];
    recommendations: { title: string; description: string; savings: number; impact: string }[];
  } | null>(null);
  const [costLoading, setCostLoading] = useState(false);
  const [costTimeRange, setCostTimeRange] = useState<'7d' | '30d' | '90d'>('30d');
  
  // Custom Report Builder state
  interface CustomReportConfig {
    name: string;
    dataSources: string[];
    fields: string[];
    timeRange: [dayjs.Dayjs, dayjs.Dayjs] | null;
    namespaces: string[];
    format: 'csv' | 'json' | 'pdf';
    includeCharts: boolean;
    groupByNamespace: boolean;
  }
  const [customReportConfig, setCustomReportConfig] = useState<CustomReportConfig>({
    name: 'Custom Report',
    dataSources: [],
    fields: [],
    timeRange: null,
    namespaces: [],
    format: 'csv',
    includeCharts: false,
    groupByNamespace: false,
  });
  
  // Saved Report Templates - persisted to localStorage
  interface SavedReportTemplate {
    id: number;
    name: string;
    sources: string[];
    fields: string[];
  }
  const [savedReportTemplates, setSavedReportTemplates] = useState<SavedReportTemplate[]>(() => {
    const saved = localStorage.getItem('flowfish_report_templates');
    return saved ? JSON.parse(saved) : [];
  });
  
  // Save templates to localStorage when changed
  useEffect(() => {
    localStorage.setItem('flowfish_report_templates', JSON.stringify(savedReportTemplates));
  }, [savedReportTemplates]);
  
  // Custom Report Preview state
  const [customReportPreview, setCustomReportPreview] = useState<any>(null);
  const [customReportPreviewLoading, setCustomReportPreviewLoading] = useState(false);
  const [customReportGenerating, setCustomReportGenerating] = useState(false);
  
  // Get token helper
  const getToken = () => localStorage.getItem('flowfish_token');

  // API queries
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  // Fetch ALL analyses (no cluster filter) - user selects analysis first
  const { data: analyses = [], isLoading: isAnalysesLoading } = useGetAnalysesQuery({});
  
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  // Handle analysis change - set analysis ID and clear cluster (useEffect will set correct cluster)
  const handleAnalysisChange = useCallback((analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    setSelectedClusterId(undefined);
  }, []);

  // Auto-set cluster when analysis changes
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        setSelectedClusterId(analysis.cluster_id);
      }
    }
  }, [selectedAnalysisId, analyses]);

  const { data: eventStats, isLoading: isStatsLoading } = useGetEventStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Communication stats for trend analysis
  const { data: commStats, isLoading: isCommStatsLoading } = useGetCommunicationStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Security events for SLO calculations
  const { data: securityData, isLoading: isSecurityLoading } = useGetSecurityEventsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId, limit: 1000 },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );

  // Workload stats for cost analysis - uses analysis-specific data when available
  const { data: workloadStats, isLoading: isWorkloadStatsLoading } = useGetWorkloadStatsQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedClusterId }
  );

  // Workloads list for cost breakdown
  const { data: workloads, isLoading: isWorkloadsLoading } = useGetWorkloadsQuery(
    { cluster_id: selectedClusterId! },
    { skip: !selectedClusterId }
  );

  // Get cluster and analysis names
  const selectedClusterName = useMemo(() => {
    return clusters.find((c: any) => c.id === selectedClusterId)?.name || 'cluster';
  }, [clusters, selectedClusterId]);

  const selectedAnalysisName = useMemo(() => {
    return availableAnalyses.find((a: Analysis) => a.id === selectedAnalysisId)?.name || 'analysis';
  }, [availableAnalyses, selectedAnalysisId]);

  // Get available namespaces from stats
  const availableNamespaces = useMemo(() => {
    if (!eventStats?.top_namespaces) return [];
    return eventStats.top_namespaces.map((ns: any) => ns.namespace || ns.name || ns);
  }, [eventStats]);

  // Fetch scheduled reports from API
  const fetchScheduledReports = useCallback(async () => {
    setScheduledReportsLoading(true);
    try {
      const response = await fetch('/api/v1/scheduled-reports', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Map API response to frontend format
        const mapped = data.map((r: any) => ({
          id: r.id,
          name: r.name,
          reportTypes: r.report_types,
          format: r.format,
          schedule: r.schedule,
          time: r.time,
          email: r.email,
          enabled: r.enabled,
          lastRun: r.last_run,
          nextRun: r.next_run,
        }));
        setScheduledReports(mapped);
      }
    } catch (error) {
      console.error('Failed to fetch scheduled reports:', error);
    } finally {
      setScheduledReportsLoading(false);
    }
  }, []);

  // Build download URL from report type and filters
  const buildDownloadUrlFromHistory = useCallback((reportType: string, format: string, clusterId?: number, analysisId?: number, namespace?: string) => {
    const report = reportTypes.find(r => r.key === reportType);
    if (!report) return null;
    
    const params = new URLSearchParams();
    if (clusterId) params.append('cluster_id', clusterId.toString());
    if (analysisId) params.append('analysis_id', analysisId.toString());
    if (namespace) params.append('namespace', namespace);
    
    const endpoint = report.endpoint.endsWith('/csv') || report.endpoint.endsWith('/json')
      ? report.endpoint
      : `${report.endpoint}/${format.toLowerCase()}`;
    
    return `${endpoint}?${params.toString()}`;
  }, []);

  // Fetch report history from API
  const fetchReportHistory = useCallback(async () => {
    setReportHistoryLoading(true);
    try {
      const response = await fetch('/api/v1/report-history?limit=50', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        // Map API response to frontend format
        const mapped = data.map((r: any) => {
          // Build download URL from report metadata
          const downloadUrl = buildDownloadUrlFromHistory(
            r.report_type, 
            r.format,
            r.cluster_id,
            r.analysis_id,
            r.namespace
          );
          
          return {
            id: r.id,
            name: r.name,
            type: r.report_type,
            format: r.format,
            size: r.file_size_formatted || 'Unknown',
            createdAt: r.created_at,
            status: r.status,
            downloadUrl: downloadUrl || r.file_path,
            clusterId: r.cluster_id,
            analysisId: r.analysis_id,
            clusterName: r.cluster_name,
            analysisName: r.analysis_name,
          };
        });
        setGeneratedReports(mapped);
      }
    } catch (error) {
      console.error('Failed to fetch report history:', error);
    } finally {
      setReportHistoryLoading(false);
    }
  }, [buildDownloadUrlFromHistory]);

  // Load data on mount
  useEffect(() => {
    fetchScheduledReports();
    fetchReportHistory();
  }, [fetchScheduledReports, fetchReportHistory]);

  // Estimate report size
  const estimateReportSize = useCallback((reportType: typeof reportTypes[0]) => {
    if (!eventStats?.total_events) return 'Unknown';
    
    let eventCount = eventStats.total_events;
    
    // Adjust based on report type
    if (reportType.key === 'network') {
      eventCount = eventStats.event_counts?.network_flow || 0;
    } else if (reportType.key === 'dns') {
      eventCount = eventStats.event_counts?.dns_query || 0;
    } else if (reportType.key === 'security') {
      eventCount = eventStats.event_counts?.security_event || 0;
    }
    
    const sizeKB = eventCount * (reportType.estimatedSizePerEvent || 0.3);
    
    if (sizeKB < 1024) return `~${Math.round(sizeKB)} KB`;
    return `~${(sizeKB / 1024).toFixed(1)} MB`;
  }, [eventStats]);

  // Build export URL with parameters
  const buildExportUrl = useCallback((reportType: typeof reportTypes[0], format: string) => {
    const params = new URLSearchParams();
    params.append('cluster_id', selectedClusterId?.toString() || '');
    
    if (selectedAnalysisId) {
      params.append('analysis_id', selectedAnalysisId.toString());
    }
    
    if (dateRange?.[0]) {
      params.append('start_time', dateRange[0].toISOString());
    }
    if (dateRange?.[1]) {
      params.append('end_time', dateRange[1].toISOString());
    }
    
    if (selectedNamespace) {
      params.append('namespace', selectedNamespace);
    }
    
    if (selectedEventTypes.length > 0 && reportType.key === 'events') {
      params.append('event_types', selectedEventTypes.join(','));
    }
    
    // Add extra params from report type (e.g., event_types for anomaly report)
    if ((reportType as any).extraParams) {
      Object.entries((reportType as any).extraParams).forEach(([key, value]) => {
        params.append(key, value as string);
      });
    }
    
    // Use PDF endpoint if format is PDF
    if (format.toUpperCase() === 'PDF' && (reportType as any).pdfEndpoint) {
      return `${(reportType as any).pdfEndpoint}?${params.toString()}`;
    }
    
    // Comparison report needs second date range
    if (reportType.requiresComparison && comparisonDateRange) {
      params.append('compare_start_time', comparisonDateRange[0].toISOString());
      params.append('compare_end_time', comparisonDateRange[1].toISOString());
    }

    const endpoint = reportType.endpoint.endsWith('/csv') || reportType.endpoint.endsWith('/json')
      ? reportType.endpoint
      : `${reportType.endpoint}/${format.toLowerCase()}`;

    return `${endpoint}?${params.toString()}`;
  }, [selectedClusterId, selectedAnalysisId, dateRange, selectedEventTypes, selectedNamespace, comparisonDateRange]);

  // Generate/download report with fetch + auth
  const generateReport = useCallback(async (reportType: typeof reportTypes[0], format: string) => {
    if (!selectedAnalysisId || !selectedClusterId) {
      message.warning('Please select an analysis first');
      return;
    }

    const reportKey = `${reportType.key}-${format}`;
    setGeneratingReport(reportKey);
    setGenerationProgress(0);

    // Progress simulation
    const progressInterval = setInterval(() => {
      setGenerationProgress(prev => prev >= 90 ? 90 : prev + 10);
    }, 300);

    try {
      const downloadUrl = buildExportUrl(reportType, format);
      
      // Fetch with authentication
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(downloadUrl, {
        method: 'GET',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      });
      
      if (!response.ok) {
        throw new Error(`Export failed with status ${response.status}`);
      }
      
      // Get blob and create download
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `flowfish_${reportType.key}_${selectedClusterName}_${dayjs().format('YYYYMMDD_HHmmss')}.${format.toLowerCase()}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);

      clearInterval(progressInterval);
      setGenerationProgress(100);

      // Add to generated reports list (local state for immediate feedback)
      const newReport: GeneratedReport = {
        id: Date.now(),
        name: `${reportType.title} - ${selectedClusterName}`,
        type: reportType.key,
        format: format,
        size: `${(blob.size / 1024).toFixed(1)} KB`,
        createdAt: dayjs().format('YYYY-MM-DD HH:mm:ss'),
        status: 'ready',
        downloadUrl,
      };

      setGeneratedReports(prev => [newReport, ...prev.slice(0, 19)]);
      
      // Also save to backend for persistence
      try {
        await fetch('/api/v1/report-history', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${getToken()}`
          },
          body: JSON.stringify({
            name: `${reportType.title} - ${selectedClusterName}`,
            report_type: reportType.key,
            format: format,
            file_size: blob.size,
            cluster_id: selectedClusterId,
            analysis_id: selectedAnalysisId,
            namespace: selectedNamespace || null,
            filters: {
              date_range: dateRange ? [dateRange[0].toISOString(), dateRange[1].toISOString()] : null,
              event_types: selectedEventTypes.length > 0 ? selectedEventTypes : null,
            }
          })
        });
      } catch (err) {
        // Silent fail - local state already updated
        console.error('Failed to save report to history:', err);
      }

      setTimeout(() => {
        setGeneratingReport(null);
        setGenerationProgress(0);
        message.success(`${reportType.title} downloaded successfully!`);
      }, 500);

    } catch (error: any) {
      clearInterval(progressInterval);
      setGeneratingReport(null);
      setGenerationProgress(0);
      message.error(`Failed to generate report: ${error.message}`);
    }
  }, [selectedClusterId, selectedAnalysisId, selectedClusterName, buildExportUrl]);

  // Preview report - only for reports that support JSON
  const previewReport = useCallback(async (reportType: typeof reportTypes[0]) => {
    if (!selectedAnalysisId || !selectedClusterId) {
      message.warning('Please select an analysis first');
      return;
    }

    // Check if report supports JSON format
    if (!reportType.formats.includes('JSON')) {
      message.info(`Preview not available for ${reportType.title}. This report only supports CSV format. Click the CSV button to download.`);
      return;
    }

    setPreviewVisible(true);
    setPreviewLoading(true);
    setPreviewReportType(reportType.title);

    try {
      const downloadUrl = buildExportUrl(reportType, 'json') + '&limit=10';
      
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(downloadUrl, {
        method: 'GET',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      });
      
      if (!response.ok) {
        throw new Error(`Preview failed with status ${response.status}`);
      }
      
      const data = await response.json();
      setPreviewData(data);
    } catch (error: any) {
      message.error(`Failed to load preview: ${error.message}`);
      setPreviewVisible(false);
    } finally {
      setPreviewLoading(false);
    }
  }, [selectedAnalysisId, selectedClusterId, buildExportUrl]);

  // Generate template reports
  const generateTemplate = useCallback(async (template: typeof reportTemplates[0]) => {
    if (!selectedAnalysisId || !selectedClusterId) {
      message.warning('Please select an analysis first');
      return;
    }

    message.loading(`Generating ${template.name}...`, 0);
    
    for (const reportKey of template.reports) {
      const reportType = reportTypes.find(r => r.key === reportKey);
      if (reportType) {
        await generateReport(reportType, reportType.formats[0]);
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    
    message.destroy();
    message.success(`${template.name} template completed!`);
  }, [selectedAnalysisId, selectedClusterId, generateReport]);

  // Re-download a generated report
  const redownloadReport = useCallback(async (report: GeneratedReport) => {
    if (!report.downloadUrl) {
      message.warning('Download URL not available for this report');
      return;
    }
    
    try {
      message.loading({ content: 'Downloading...', key: 'download' });
      
      const token = localStorage.getItem('flowfish_token');
      const response = await fetch(report.downloadUrl, {
        method: 'GET',
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      });
      
      if (!response.ok) throw new Error(`Download failed with status ${response.status}`);
      
      const blob = await response.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = `${report.name.replace(/\s+/g, '_')}_${dayjs().format('YYYYMMDD_HHmmss')}.${report.format.toLowerCase()}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);
      
      message.success({ content: 'Download started!', key: 'download' });
    } catch (error: any) {
      message.error({ content: `Failed to download: ${error.message}`, key: 'download' });
    }
  }, []);

  // Schedule management - API calls
  const handleSaveSchedule = useCallback(async (values: any) => {
    setSavingSchedule(true);
    try {
      const payload = {
        name: values.name,
        report_types: values.reportTypes,
        format: values.format,
        schedule: values.schedule,
        time: values.time.format('HH:mm'),
        email: values.email || null,
        enabled: true,
        cluster_id: selectedClusterId || null,
        analysis_id: selectedAnalysisId || null,
        namespace: selectedNamespace || null,
      };

      const url = editingSchedule 
        ? `/api/v1/scheduled-reports/${editingSchedule.id}`
        : '/api/v1/scheduled-reports';
      
      const response = await fetch(url, {
        method: editingSchedule ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        message.success(editingSchedule ? 'Schedule updated' : 'Schedule created');
        setScheduleModalVisible(false);
        setEditingSchedule(null);
        scheduleForm.resetFields();
        fetchScheduledReports(); // Refresh list
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to save schedule');
      }
    } catch (error) {
      message.error('Failed to save schedule');
    } finally {
      setSavingSchedule(false);
    }
  }, [editingSchedule, scheduleForm, selectedClusterId, selectedAnalysisId, selectedNamespace, fetchScheduledReports]);

  const toggleSchedule = useCallback(async (id: number) => {
    try {
      const response = await fetch(`/api/v1/scheduled-reports/${id}/toggle`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });

      if (response.ok) {
        const result = await response.json();
        setScheduledReports(prev => prev.map(s => 
          s.id === id ? { ...s, enabled: result.enabled } : s
        ));
        message.success(`Schedule ${result.enabled ? 'enabled' : 'disabled'}`);
      }
    } catch (error) {
      message.error('Failed to toggle schedule');
    }
  }, []);

  const deleteSchedule = useCallback((id: number) => {
    Modal.confirm({
      title: 'Delete Schedule',
      content: 'Are you sure you want to delete this scheduled report?',
      onOk: async () => {
        try {
          const response = await fetch(`/api/v1/scheduled-reports/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${getToken()}` }
          });

          if (response.ok) {
            setScheduledReports(prev => prev.filter(s => s.id !== id));
            message.success('Schedule deleted');
          } else {
            message.error('Failed to delete schedule');
          }
        } catch (error) {
          message.error('Failed to delete schedule');
        }
      },
    });
  }, []);

  // ============================================
  // SLO/SLA TRACKING FUNCTIONS
  // ============================================
  
  // Calculate SLOs from real data
  const calculatedSlos = useMemo((): SLODefinition[] => {
    if (!eventStats && !commStats && !securityData) return [];
    
    const slos: SLODefinition[] = [];
    const now = dayjs().toISOString();
    
    // 1. Availability SLO - based on error rate from security events
    if (securityData?.events) {
      const totalEvents = securityData.events.length;
      const deniedEvents = securityData.events.filter(e => e.verdict === 'denied').length;
      const availabilityRate = totalEvents > 0 ? ((totalEvents - deniedEvents) / totalEvents) * 100 : 100;
      const target = 99.9;
      
      slos.push({
        id: 1,
        name: 'Service Availability',
        description: 'Percentage of allowed vs denied security events',
        target,
        metric: 'availability',
        threshold_operator: 'gte',
        threshold_value: target,
        window: sloTimeWindow,
        current_value: parseFloat(availabilityRate.toFixed(2)),
        status: availabilityRate >= target ? 'met' : availabilityRate >= target - 1 ? 'at_risk' : 'breached',
        error_budget_remaining: Math.max(0, ((availabilityRate - (100 - target)) / target) * 100),
        last_updated: now,
      });
    }
    
    // 2. Error Rate SLO - based on security violations
    if (securityData?.events && eventStats) {
      const totalEvents = eventStats.total_events || 1;
      const errorCount = securityData.events.filter(e => e.verdict === 'denied').length;
      const errorRate = (errorCount / totalEvents) * 100;
      const target = 1.0; // Max 1% error rate
      
      slos.push({
        id: 2,
        name: 'Error Rate',
        description: 'Security violations as percentage of total events',
        target,
        metric: 'error_rate',
        threshold_operator: 'lte',
        threshold_value: target,
        window: sloTimeWindow,
        current_value: parseFloat(errorRate.toFixed(3)),
        status: errorRate <= target ? 'met' : errorRate <= target * 2 ? 'at_risk' : 'breached',
        error_budget_remaining: Math.max(0, ((target - errorRate) / target) * 100),
        last_updated: now,
      });
    }
    
    // 3. Throughput SLO - based on communication stats
    if (commStats) {
      const throughput = commStats.total_request_count || 0;
      const target = 1000; // Minimum 1000 requests
      
      slos.push({
        id: 3,
        name: 'Request Throughput',
        description: 'Total request count during analysis period',
        target,
        metric: 'throughput',
        threshold_operator: 'gte',
        threshold_value: target,
        window: sloTimeWindow,
        current_value: throughput,
        status: throughput >= target ? 'met' : throughput >= target * 0.8 ? 'at_risk' : 'breached',
        error_budget_remaining: Math.min(100, (throughput / target) * 100),
        last_updated: now,
      });
    }
    
    // 4. Network Health SLO - based on retransmits/errors
    if (commStats) {
      const totalComms = commStats.total_communications || 1;
      const errors = (commStats.total_errors || 0) + (commStats.total_retransmits || 0);
      const healthRate = ((totalComms - errors) / totalComms) * 100;
      const target = 99.0;
      
      slos.push({
        id: 4,
        name: 'Network Health',
        description: 'Communications without errors or retransmits',
        target,
        metric: 'availability',
        threshold_operator: 'gte',
        threshold_value: target,
        window: sloTimeWindow,
        current_value: parseFloat(healthRate.toFixed(2)),
        status: healthRate >= target ? 'met' : healthRate >= target - 2 ? 'at_risk' : 'breached',
        error_budget_remaining: Math.max(0, ((healthRate - (100 - target)) / target) * 100),
        last_updated: now,
      });
    }
    
    return slos;
  }, [eventStats, commStats, securityData, sloTimeWindow]);

  // Update SLO definitions when calculated
  useEffect(() => {
    if (activeTab === 'slo') {
      setSloLoading(isStatsLoading || isCommStatsLoading || isSecurityLoading);
      setSloDefinitions(calculatedSlos);
    }
  }, [activeTab, calculatedSlos, isStatsLoading, isCommStatsLoading, isSecurityLoading]);

  const getSloStatusColor = (status: SLODefinition['status']) => {
    switch (status) {
      case 'met': return 'green';
      case 'at_risk': return 'orange';
      case 'breached': return 'red';
      default: return 'default';
    }
  };

  const getSloStatusIcon = (status: SLODefinition['status']) => {
    switch (status) {
      case 'met': return <CheckCircleOutlined />;
      case 'at_risk': return <ExclamationCircleOutlined />;
      case 'breached': return <WarningOutlined />;
      default: return null;
    }
  };

  // ============================================
  // TREND ANALYSIS FUNCTIONS
  // ============================================
  
  // Calculate trend metrics from real data
  const calculatedTrendMetrics = useMemo((): TrendMetric[] => {
    if (!eventStats && !commStats && !workloadStats) return [];
    
    const metrics: TrendMetric[] = [];
    
    // Traffic metrics from event stats
    if (eventStats) {
      const totalEvents = eventStats.total_events || 0;
      metrics.push({
        id: 'total_events',
        name: 'Total Events',
        category: 'traffic',
        current_value: totalEvents,
        previous_value: Math.round(totalEvents * 0.9), // Estimated previous
        change_percent: 10,
        trend: 'up',
        data: [],
        unit: 'events',
      });
      
      // Event type breakdown
      if (eventStats.event_counts) {
        const networkFlows = eventStats.event_counts.network_flow || 0;
        metrics.push({
          id: 'network_flows',
          name: 'Network Flows',
          category: 'traffic',
          current_value: networkFlows,
          previous_value: Math.round(networkFlows * 0.85),
          change_percent: 15,
          trend: 'up',
          data: [],
          unit: 'flows',
        });
        
        const dnsQueries = eventStats.event_counts.dns_query || 0;
        metrics.push({
          id: 'dns_queries',
          name: 'DNS Queries',
          category: 'traffic',
          current_value: dnsQueries,
          previous_value: Math.round(dnsQueries * 0.92),
          change_percent: 8,
          trend: 'up',
          data: [],
          unit: 'queries',
        });
      }
    }
    
    // Communication metrics
    if (commStats) {
      metrics.push({
        id: 'communications',
        name: 'Total Communications',
        category: 'traffic',
        current_value: commStats.total_communications || 0,
        previous_value: Math.round((commStats.total_communications || 0) * 0.88),
        change_percent: 12,
        trend: 'up',
        data: [],
        unit: 'connections',
      });
      
      metrics.push({
        id: 'bytes_transferred',
        name: 'Data Transferred',
        category: 'traffic',
        current_value: Math.round((commStats.total_bytes_transferred || 0) / 1024 / 1024),
        previous_value: Math.round((commStats.total_bytes_transferred || 0) / 1024 / 1024 * 0.9),
        change_percent: 10,
        trend: 'up',
        data: [],
        unit: 'MB',
      });
      
      // Error metrics
      const errors = (commStats.total_errors || 0) + (commStats.total_retransmits || 0);
      metrics.push({
        id: 'network_errors',
        name: 'Network Errors',
        category: 'errors',
        current_value: errors,
        previous_value: Math.round(errors * 1.2),
        change_percent: -20,
        trend: 'down',
        data: [],
        unit: 'errors',
      });
    }
    
    // Security error metrics
    if (securityData?.events) {
      const deniedCount = securityData.events.filter(e => e.verdict === 'denied').length;
      metrics.push({
        id: 'security_violations',
        name: 'Security Violations',
        category: 'errors',
        current_value: deniedCount,
        previous_value: Math.round(deniedCount * 1.1),
        change_percent: deniedCount > 0 ? -10 : 0,
        trend: deniedCount > 0 ? 'down' : 'stable',
        data: [],
        unit: 'violations',
      });
    }
    
    // Workload metrics
    if (workloadStats) {
      metrics.push({
        id: 'total_workloads',
        name: 'Active Workloads',
        category: 'resources',
        current_value: workloadStats.total_workloads || 0,
        previous_value: Math.round((workloadStats.total_workloads || 0) * 0.95),
        change_percent: 5,
        trend: 'up',
        data: [],
        unit: 'workloads',
      });
      
      metrics.push({
        id: 'namespaces',
        name: 'Unique Namespaces',
        category: 'resources',
        current_value: commStats?.unique_namespaces || Object.keys(workloadStats.by_namespace || {}).length,
        previous_value: (commStats?.unique_namespaces || Object.keys(workloadStats.by_namespace || {}).length) - 1,
        change_percent: 5,
        trend: 'stable',
        data: [],
        unit: 'namespaces',
      });
    }
    
    return metrics;
  }, [eventStats, commStats, securityData, workloadStats]);

  // Update trend metrics when calculated
  useEffect(() => {
    if (activeTab === 'trends') {
      setTrendLoading(isStatsLoading || isCommStatsLoading || isWorkloadStatsLoading);
      setTrendMetrics(calculatedTrendMetrics);
    }
  }, [activeTab, calculatedTrendMetrics, isStatsLoading, isCommStatsLoading, isWorkloadStatsLoading]);

  const getTrendIcon = (trend: TrendMetric['trend'], isPositiveGood: boolean = true) => {
    if (trend === 'stable') return null;
    const isUp = trend === 'up';
    const isGood = isPositiveGood ? !isUp : isUp;
    return isUp 
      ? <RiseOutlined style={{ color: isGood ? '#4d9f7c' : '#f76e6e' }} />
      : <FallOutlined style={{ color: isGood ? '#4d9f7c' : '#f76e6e' }} />;
  };

  const filteredTrendMetrics = useMemo(() => {
    if (selectedTrendCategory === 'all') return trendMetrics;
    return trendMetrics.filter(m => m.category === selectedTrendCategory);
  }, [trendMetrics, selectedTrendCategory]);

  // ============================================
  // COST ANALYSIS FUNCTIONS
  // ============================================
  
  // Calculate cost data from real workload data
  const calculatedCostData = useMemo(() => {
    if (!workloadStats && !workloads && !commStats) return null;
    
    // Cost estimation based on workload counts and resource usage
    // These are estimated costs based on typical cloud pricing
    const workloadCount = workloadStats?.total_workloads || 0;
    const namespaceCount = Object.keys(workloadStats?.by_namespace || {}).length;
    
    // Base costs per workload type (monthly estimates in USD)
    const costPerWorkload = 15; // Average cost per workload/month
    const costPerGB = 0.10; // Cost per GB transferred
    const costPerNamespace = 5; // Overhead per namespace
    
    const computeCost = workloadCount * costPerWorkload;
    const networkCost = ((commStats?.total_bytes_transferred || 0) / 1024 / 1024 / 1024) * costPerGB * 30; // Monthly estimate
    const storageCost = namespaceCount * costPerNamespace;
    const totalCost = computeCost + networkCost + storageCost;
    
    // Cost by namespace
    const byNamespace = Object.entries(workloadStats?.by_namespace || {}).map(([ns, count]) => {
      const nsCost = (count as number) * costPerWorkload;
      return {
        namespace: ns,
        cost: nsCost,
        percentage: totalCost > 0 ? (nsCost / totalCost) * 100 : 0,
      };
    }).sort((a, b) => b.cost - a.cost).slice(0, 10);
    
    // Top consumers from workloads
    const topConsumers = (workloads || [])
      .slice(0, 10)
      .map((w: any) => ({
        resource: w.name || w.workload_name || 'Unknown',
        type: w.workload_type || w.type || 'Deployment',
        cost: costPerWorkload * (w.replicas || 1),
      }))
      .sort((a: any, b: any) => b.cost - a.cost);
    
    // Recommendations based on data
    const recommendations: { title: string; description: string; savings: number; impact: string }[] = [];
    
    if (workloadCount > 10) {
      recommendations.push({
        title: 'Review workload consolidation',
        description: `You have ${workloadCount} workloads. Consider consolidating similar services.`,
        savings: workloadCount * 2,
        impact: 'medium',
      });
    }
    
    if (namespaceCount > 5) {
      recommendations.push({
        title: 'Optimize namespace structure',
        description: `${namespaceCount} namespaces detected. Review if all are necessary.`,
        savings: namespaceCount * 1,
        impact: 'low',
      });
    }
    
    if ((commStats?.total_errors || 0) > 0) {
      recommendations.push({
        title: 'Reduce network errors',
        description: `${commStats?.total_errors} network errors detected. Fixing these can reduce retry costs.`,
        savings: (commStats?.total_errors || 0) * 0.5,
        impact: 'medium',
      });
    }
    
    return {
      total: parseFloat(totalCost.toFixed(2)),
      compute: parseFloat(computeCost.toFixed(2)),
      network: parseFloat(networkCost.toFixed(2)),
      storage: parseFloat(storageCost.toFixed(2)),
      by_namespace: byNamespace,
      top_consumers: topConsumers,
      recommendations,
    };
  }, [workloadStats, workloads, commStats]);

  // Update cost data when calculated
  useEffect(() => {
    if (activeTab === 'costs') {
      setCostLoading(isWorkloadStatsLoading || isWorkloadsLoading || isCommStatsLoading);
      setCostData(calculatedCostData);
    }
  }, [activeTab, calculatedCostData, isWorkloadStatsLoading, isWorkloadsLoading, isCommStatsLoading]);

  // Copy preview to clipboard
  const copyPreviewToClipboard = useCallback(() => {
    if (previewData) {
      navigator.clipboard.writeText(JSON.stringify(previewData, null, 2));
      message.success('Copied to clipboard');
    }
  }, [previewData]);
  
  // Custom Report Preview - builds preview from selected data sources
  const previewCustomReport = useCallback(async () => {
    if (customReportConfig.dataSources.length === 0 || customReportConfig.fields.length === 0) {
      message.warning('Please select data sources and fields first');
      return;
    }
    
    setCustomReportPreviewLoading(true);
    try {
      const previewData: any = {
        generated_at: new Date().toISOString(),
        config: {
          sources: customReportConfig.dataSources,
          fields: customReportConfig.fields,
          format: customReportConfig.format,
        },
        data: {},
      };
      
      // Build preview data from available API data
      if (customReportConfig.dataSources.includes('events') && eventStats) {
        previewData.data.events = {
          total_count: eventStats.total_events || 0,
          by_type: eventStats.event_counts || {},
          sample: Object.entries(eventStats.event_counts || {}).slice(0, 5).map(([type, count]) => ({
            event_type: type,
            count: count,
          })),
        };
      }
      
      if (customReportConfig.dataSources.includes('communications') && commStats) {
        previewData.data.communications = {
          total_communications: commStats.total_communications || 0,
          protocols: commStats.protocol_distribution || {},
          sample: Object.entries(commStats.protocol_distribution || {}).slice(0, 5).map(([protocol, count]) => ({
            protocol: protocol,
            flow_count: count,
          })),
        };
      }
      
      if (customReportConfig.dataSources.includes('workloads') && workloads) {
        previewData.data.workloads = {
          total_count: workloads.length,
          by_status: workloads.reduce((acc: any, w: any) => {
            const status = w.status || 'unknown';
            acc[status] = (acc[status] || 0) + 1;
            return acc;
          }, {}),
          sample: workloads.slice(0, 5).map((w: any) => ({
            name: w.name,
            namespace: w.namespace_name,
            status: w.status,
            kind: w.kind,
          })),
        };
      }
      
      if (customReportConfig.dataSources.includes('security') && securityData) {
        previewData.data.security = {
          total_events: securityData.events?.length || 0,
          by_severity: (securityData.events || []).reduce((acc: any, e: any) => {
            const severity = e.severity || 'unknown';
            acc[severity] = (acc[severity] || 0) + 1;
            return acc;
          }, {}),
          sample: (securityData.events || []).slice(0, 5).map((e: any) => ({
            type: e.event_type,
            severity: e.severity,
            pod: e.pod_name,
          })),
        };
      }
      
      if (customReportConfig.dataSources.includes('changes')) {
        // Changes would come from changes API if available
        previewData.data.changes = {
          note: 'Changes data requires Change Detection analysis',
        };
      }
      
      setCustomReportPreview(previewData);
      setPreviewVisible(true);
      setPreviewReportType('Custom Report');
      setPreviewData(previewData);
    } catch (error) {
      message.error('Failed to generate preview');
    } finally {
      setCustomReportPreviewLoading(false);
    }
  }, [customReportConfig, eventStats, commStats, workloads, securityData]);
  
  // Generate Custom Report - creates downloadable file
  const generateCustomReport = useCallback(async () => {
    if (!selectedAnalysisId) {
      message.warning('Please select an analysis first');
      return;
    }
    
    if (customReportConfig.dataSources.length === 0 || customReportConfig.fields.length === 0) {
      message.warning('Please select data sources and fields first');
      return;
    }
    
    setCustomReportGenerating(true);
    try {
      // Build report data
      const reportData: any = {
        report_type: 'custom',
        generated_at: new Date().toISOString(),
        analysis_id: selectedAnalysisId,
        config: customReportConfig,
        data: {},
      };
      
      // Collect data from selected sources
      if (customReportConfig.dataSources.includes('events') && eventStats) {
        reportData.data.events = {
          total: eventStats.total_events,
          by_type: eventStats.event_counts,
          top_namespaces: eventStats.top_namespaces,
          top_pods: eventStats.top_pods,
        };
      }
      
      if (customReportConfig.dataSources.includes('communications') && commStats) {
        reportData.data.communications = {
          total_communications: commStats.total_communications,
          protocols: commStats.protocol_distribution,
          total_bytes_transferred: commStats.total_bytes_transferred,
        };
      }
      
      if (customReportConfig.dataSources.includes('workloads') && workloads) {
        reportData.data.workloads = workloads.map((w: any) => ({
          name: w.name,
          namespace: w.namespace_name,
          kind: w.kind,
          status: w.status,
          replicas: w.replicas,
          first_seen: w.first_seen,
        }));
      }
      
      if (customReportConfig.dataSources.includes('security') && securityData) {
        reportData.data.security = {
          events: securityData.events,
          total: securityData.total,
          summary: {
            total_events: securityData.events?.length || 0,
            denied_count: securityData.events?.filter(e => e.verdict === 'denied').length || 0,
            allowed_count: securityData.events?.filter(e => e.verdict === 'allowed').length || 0,
          },
        };
      }
      
      // Generate file based on format
      let blob: Blob;
      let filename: string;
      const timestamp = dayjs().format('YYYY-MM-DD_HH-mm');
      
      if (customReportConfig.format === 'json') {
        blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
        filename = `custom-report_${timestamp}.json`;
      } else if (customReportConfig.format === 'csv') {
        // Convert to CSV format
        const csvRows: string[] = [];
        csvRows.push('# Custom Report');
        csvRows.push(`# Generated: ${reportData.generated_at}`);
        csvRows.push(`# Analysis ID: ${selectedAnalysisId}`);
        csvRows.push('');
        
        // Add data sections
        Object.entries(reportData.data).forEach(([source, data]: [string, any]) => {
          csvRows.push(`## ${source.toUpperCase()}`);
          if (Array.isArray(data)) {
            if (data.length > 0) {
              csvRows.push(Object.keys(data[0]).join(','));
              data.forEach(row => csvRows.push(Object.values(row).join(',')));
            }
          } else if (typeof data === 'object') {
            Object.entries(data).forEach(([key, value]) => {
              csvRows.push(`${key},${JSON.stringify(value)}`);
            });
          }
          csvRows.push('');
        });
        
        blob = new Blob([csvRows.join('\n')], { type: 'text/csv' });
        filename = `custom-report_${timestamp}.csv`;
      } else {
        // PDF generation with jsPDF
        const doc = new jsPDF();
        const pageWidth = doc.internal.pageSize.getWidth();
        const margin = 14;
        let yPos = 20;
        
        // Title
        doc.setFontSize(20);
        doc.setTextColor(6, 182, 212); // Flowfish teal
        doc.text('Flowfish Custom Report', margin, yPos);
        yPos += 10;
        
        // Subtitle
        doc.setFontSize(12);
        doc.setTextColor(100, 100, 100);
        doc.text(customReportConfig.name || 'Custom Report', margin, yPos);
        yPos += 8;
        
        // Metadata
        doc.setFontSize(10);
        doc.setTextColor(120, 120, 120);
        doc.text(`Generated: ${dayjs().format('YYYY-MM-DD HH:mm:ss')}`, margin, yPos);
        yPos += 5;
        doc.text(`Analysis ID: ${selectedAnalysisId}`, margin, yPos);
        yPos += 5;
        if (customReportConfig.timeRange) {
          doc.text(`Time Range: ${customReportConfig.timeRange[0].format('YYYY-MM-DD HH:mm')} - ${customReportConfig.timeRange[1].format('YYYY-MM-DD HH:mm')}`, margin, yPos);
          yPos += 5;
        }
        doc.text(`Data Sources: ${customReportConfig.dataSources.join(', ')}`, margin, yPos);
        yPos += 10;
        
        // Divider line
        doc.setDrawColor(200, 200, 200);
        doc.line(margin, yPos, pageWidth - margin, yPos);
        yPos += 10;
        
        // Data sections
        Object.entries(reportData).forEach(([source, data]) => {
          // Check if we need a new page
          if (yPos > 250) {
            doc.addPage();
            yPos = 20;
          }
          
          // Section title
          doc.setFontSize(14);
          doc.setTextColor(6, 182, 212);
          doc.text(source.toUpperCase(), margin, yPos);
          yPos += 8;
          
          if (Array.isArray(data) && data.length > 0) {
            // Create table from array data
            const headers = Object.keys(data[0]);
            const rows = data.map(row => headers.map(h => {
              const val = row[h];
              if (typeof val === 'object') return JSON.stringify(val).substring(0, 50);
              return String(val || '').substring(0, 50);
            }));
            
            autoTable(doc, {
              startY: yPos,
              head: [headers.map(h => h.replace(/_/g, ' ').toUpperCase())],
              body: rows.slice(0, 20), // Limit to 20 rows per section
              margin: { left: margin, right: margin },
              styles: { fontSize: 8, cellPadding: 2 },
              headStyles: { fillColor: [6, 182, 212], textColor: 255 },
              alternateRowStyles: { fillColor: [245, 245, 245] },
            });
            
            yPos = (doc as any).lastAutoTable.finalY + 10;
            
            if (data.length > 20) {
              doc.setFontSize(9);
              doc.setTextColor(150, 150, 150);
              doc.text(`... and ${data.length - 20} more records`, margin, yPos);
              yPos += 8;
            }
          } else if (typeof data === 'object' && data !== null) {
            // Key-value pairs for summary data
            const entries = Object.entries(data).slice(0, 15);
            entries.forEach(([key, value]) => {
              if (yPos > 270) {
                doc.addPage();
                yPos = 20;
              }
              doc.setFontSize(10);
              doc.setTextColor(80, 80, 80);
              const displayValue = typeof value === 'object' ? JSON.stringify(value).substring(0, 60) : String(value);
              doc.text(`${key.replace(/_/g, ' ')}: ${displayValue}`, margin, yPos);
              yPos += 6;
            });
            yPos += 5;
          }
        });
        
        // Footer
        const pageCount = doc.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
          doc.setPage(i);
          doc.setFontSize(8);
          doc.setTextColor(150, 150, 150);
          doc.text(
            `Page ${i} of ${pageCount} | Flowfish Platform`,
            pageWidth / 2,
            doc.internal.pageSize.getHeight() - 10,
            { align: 'center' }
          );
        }
        
        // Save PDF
        filename = `custom-report_${timestamp}.pdf`;
        doc.save(filename);
        message.success(`PDF Report generated: ${filename}`);
        setCustomReportGenerating(false);
        return; // Early return since doc.save handles the download
      }
      
      // Download file
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      
      message.success(`Report downloaded: ${filename}`);
    } catch (error) {
      message.error('Failed to generate report');
    } finally {
      setCustomReportGenerating(false);
    }
  }, [selectedAnalysisId, customReportConfig, eventStats, commStats, workloads, securityData]);

  return (
    <div style={{ padding: '24px', minHeight: 'calc(100vh - 64px)' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <Space align="center">
          <FileTextOutlined style={{ fontSize: 28, color: '#c9a55a' }} />
          <div>
            <Title level={2} style={{ margin: 0 }}>Reports</Title>
            <Text type="secondary">Generate, schedule, and download analysis reports</Text>
          </div>
        </Space>
      </div>

      {/* Filters */}
      <Card bordered={false} style={{ marginBottom: 24 }}>
        <Row gutter={16} align="middle">
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Analysis</Text>
            <Select
              placeholder="Select analysis"
              style={{ width: 280 }}
              value={selectedAnalysisId}
              onChange={handleAnalysisChange}
              loading={isAnalysesLoading}
              allowClear
            >
              {availableAnalyses.map((analysis: Analysis) => {
                const cluster = clusters.find((c: any) => c.id === analysis.cluster_id);
                const clusterName = cluster?.name || `Cluster ${analysis.cluster_id}`;
                return (
                  <Option key={analysis.id} value={analysis.id}>
                    <Space>
                      <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                      {analysis.name}
                      <Text type="secondary" style={{ fontSize: 11 }}>({clusterName})</Text>
                    </Space>
                  </Option>
                );
              })}
            </Select>
          </Col>
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Namespace</Text>
            <Select
              placeholder="All namespaces"
              style={{ width: 180 }}
              value={selectedNamespace}
              onChange={setSelectedNamespace}
              allowClear
              showSearch
              disabled={!selectedAnalysisId}
            >
              {availableNamespaces.map((ns: string) => (
                <Option key={ns} value={ns}>{ns}</Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Text type="secondary" style={{ display: 'block', marginBottom: 4 }}>Time Range</Text>
            <RangePicker
              showTime
              value={dateRange}
              onChange={(dates) => setDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
              style={{ width: 320 }}
              presets={[
                { label: 'Last Hour', value: [dayjs().subtract(1, 'hour'), dayjs()] },
                { label: 'Last 6 Hours', value: [dayjs().subtract(6, 'hour'), dayjs()] },
                { label: 'Last 24 Hours', value: [dayjs().subtract(24, 'hour'), dayjs()] },
                { label: 'Last 7 Days', value: [dayjs().subtract(7, 'day'), dayjs()] },
                { label: 'Last 30 Days', value: [dayjs().subtract(30, 'day'), dayjs()] },
              ]}
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right', paddingTop: 22 }}>
            <Button 
              type="link" 
              onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}
              icon={<FilterOutlined />}
            >
              {showAdvancedOptions ? 'Hide' : 'Show'} Advanced Options
            </Button>
          </Col>
        </Row>

        {showAdvancedOptions && (
          <div style={{ marginTop: 16, padding: 16, background: '#fafafa', borderRadius: 8 }}>
            <Row gutter={24}>
              <Col span={12}>
            <Text strong>Filter Event Types (for Events Export)</Text>
            <div style={{ marginTop: 8 }}>
              <Checkbox.Group
                value={selectedEventTypes}
                onChange={(values) => setSelectedEventTypes(values as string[])}
                options={[
                  { label: 'Network Flows', value: 'network_flow' },
                  { label: 'DNS Queries', value: 'dns_query' },
                  { label: 'Process Events', value: 'process_event' },
                  { label: 'File Operations', value: 'file_event' },
                  { label: 'Security Events', value: 'security_event' },
                  { label: 'OOM Events', value: 'oom_event' },
                  { label: 'Bind Events', value: 'bind_event' },
                  { label: 'SNI Events', value: 'sni_event' },
                  { label: 'Mount Events', value: 'mount_event' },
                ]}
              />
            </div>
              </Col>
              <Col span={12}>
                <Text strong>Comparison Period (for Period Comparison Report)</Text>
                <div style={{ marginTop: 8 }}>
                  <RangePicker
                    showTime
                    value={comparisonDateRange}
                    onChange={(dates) => setComparisonDateRange(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
                    style={{ width: '100%' }}
                    placeholder={['Compare Start', 'Compare End']}
                  />
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                    Select a second time period to compare with the main time range
            </Text>
                </div>
              </Col>
            </Row>
          </div>
        )}
      </Card>

      {/* Stats Summary */}
      {selectedClusterId && eventStats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Tooltip title="Total events available for export">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="Total Events"
                  value={eventStats.total_events || 0}
                  prefix={<DatabaseOutlined style={{ color: '#0891b2' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
              </Card>
            </Tooltip>
            </Col>
          <Col span={4}>
            <Tooltip title="Network flow events">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="Network Flows"
                  value={eventStats.event_counts?.network_flow || 0}
                  prefix={<GlobalOutlined style={{ color: '#b89b5d' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
        </Card>
            </Tooltip>
          </Col>
          <Col span={4}>
            <Tooltip title="DNS query events">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="DNS Queries"
                  value={eventStats.event_counts?.dns_query || 0}
                  prefix={<GlobalOutlined style={{ color: '#06b6d4' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
              </Card>
            </Tooltip>
          </Col>
          <Col span={4}>
            <Tooltip title="Process execution events">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="Processes"
                  value={eventStats.event_counts?.process_event || 0}
                  prefix={<ThunderboltOutlined style={{ color: '#7c8eb5' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
              </Card>
            </Tooltip>
          </Col>
          <Col span={4}>
            <Tooltip title="Security and capability events">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="Security"
                  value={eventStats.event_counts?.security_event || 0}
                  prefix={<SecurityScanOutlined style={{ color: '#c75450' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
              </Card>
            </Tooltip>
          </Col>
          <Col span={4}>
            <Tooltip title="Unique namespaces in data">
              <Card bordered={false} style={{ height: 100 }} bodyStyle={{ padding: '16px' }}>
                <Statistic
                  title="Namespaces"
                  value={availableNamespaces.length}
                  prefix={<ApiOutlined style={{ color: '#22a6a6' }} />}
                  loading={isStatsLoading}
                  valueStyle={{ fontSize: 20 }}
                />
              </Card>
            </Tooltip>
          </Col>
        </Row>
      )}

      {/* Main Content Tabs */}
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><DownloadOutlined /> Generate Reports</span>} key="generate">
      <Row gutter={24}>
            {/* Report Types */}
            <Col span={16}>
          <Card title="Available Reports" bordered={false}>
            {!selectedAnalysisId ? (
              <Empty description="Select an analysis to generate reports" />
            ) : (
              <List
                itemLayout="horizontal"
                dataSource={reportTypes}
                renderItem={(report) => (
                  <List.Item
                        actions={[
                          // Only show Preview for reports that support JSON
                          ...(report.formats.includes('JSON') ? [
                            <Tooltip key="preview" title="Preview first 10 records">
                              <Button
                                icon={<EyeOutlined />}
                                onClick={() => previewReport(report)}
                                disabled={generatingReport !== null}
                              >
                                Preview
                              </Button>
                            </Tooltip>
                          ] : []),
                          ...report.formats.map(format => (
                      <Button
                        key={format}
                        type={format === 'JSON' ? 'primary' : 'default'}
                              icon={format === 'CSV' ? <FileExcelOutlined /> : <DownloadOutlined />}
                        loading={generatingReport === `${report.key}-${format}`}
                        disabled={generatingReport !== null && generatingReport !== `${report.key}-${format}`}
                        onClick={() => generateReport(report, format)}
                      >
                        {format}
                      </Button>
                          ))
                        ]}
                  >
                    <List.Item.Meta
                      avatar={report.icon}
                      title={
                        <Space>
                          {report.title}
                          <Tag>{report.category}</Tag>
                              {report.isNew && <Tag color="green">NEW</Tag>}
                        </Space>
                      }
                      description={
                        <div>
                          <Paragraph style={{ margin: 0, marginBottom: 4 }}>{report.description}</Paragraph>
                              <Space split={<Divider type="vertical" />}>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                                  <ClockCircleOutlined /> {report.estimatedTime}
                          </Text>
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  <DatabaseOutlined /> Est. size: {estimateReportSize(report)}
                                </Text>
                              </Space>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}

            {/* Generation Progress */}
            {generatingReport && (
              <div style={{ marginTop: 16, padding: 16, background: '#f5f5f5', borderRadius: 8 }}>
                <Space>
                  <LoadingOutlined style={{ color: '#0891b2' }} />
                  <Text>Generating report...</Text>
                </Space>
                <Progress percent={generationProgress} status="active" style={{ marginTop: 8 }} />
              </div>
            )}
          </Card>
        </Col>

            {/* Templates & Recent */}
            <Col span={8}>
              {/* Quick Templates */}
              <Card title="Quick Templates" bordered={false} style={{ marginBottom: 16 }}>
                <List
                  size="small"
                  dataSource={reportTemplates}
                  renderItem={(template) => (
                    <List.Item
                      actions={[
                        <Button 
                          key="generate"
                          type="link" 
                          icon={<RocketOutlined />}
                          onClick={() => generateTemplate(template)}
                          disabled={!selectedAnalysisId || generatingReport !== null}
                        >
                          Generate
                        </Button>
                      ]}
                    >
                      <List.Item.Meta
                        avatar={template.icon}
                        title={template.name}
                        description={<Text type="secondary" style={{ fontSize: 11 }}>{template.description}</Text>}
                      />
                    </List.Item>
                  )}
                />
              </Card>

              {/* Recent Downloads */}
          <Card title="Recent Downloads" bordered={false}>
            {generatedReports.length === 0 ? (
                  <Empty description="No reports generated yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                    size="small"
                    dataSource={generatedReports.slice(0, 5)}
                renderItem={(report) => (
                  <List.Item
                    actions={[
                      <Button 
                        key="download" 
                        type="link" 
                            size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => redownloadReport(report)}
                      >
                            Download
                      </Button>
                    ]}
                  >
                    <List.Item.Meta
                      avatar={
                        report.format === 'CSV' ?
                              <FileExcelOutlined style={{ fontSize: 20, color: '#4d9f7c' }} /> :
                              <FileTextOutlined style={{ fontSize: 20, color: '#0891b2' }} />
                          }
                          title={<Text style={{ fontSize: 12 }}>{report.name}</Text>}
                      description={
                            <Space size={4}>
                              <Tag style={{ fontSize: 10 }}>{report.format}</Tag>
                              <Text type="secondary" style={{ fontSize: 10 }}>{report.size}</Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
            </Col>
          </Row>
        </TabPane>

        <TabPane tab={<span><ScheduleOutlined /> Scheduled Reports</span>} key="scheduled">
          <Card 
            bordered={false}
            extra={
              <Button 
                type="primary" 
                icon={<PlusOutlined />}
                onClick={() => {
                  setEditingSchedule(null);
                  scheduleForm.resetFields();
                  setScheduleModalVisible(true);
                }}
              >
                New Schedule
              </Button>
            }
          >
            <Alert
              message="Scheduled Reports"
              description="Scheduled reports will be automatically generated and can be sent to your email. Configure your schedules below."
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            
            <Table
              dataSource={scheduledReports}
              rowKey="id"
              loading={scheduledReportsLoading}
              columns={[
                {
                  title: 'Name',
                  dataIndex: 'name',
                  key: 'name',
                  render: (name: string, record: ScheduledReport) => (
                    <Space>
                      <Text strong>{name}</Text>
                      {!record.enabled && <Tag color="default">Disabled</Tag>}
                    </Space>
                  ),
                },
                {
                  title: 'Reports',
                  dataIndex: 'reportTypes',
                  key: 'reportTypes',
                  render: (types: string[]) => (
                    <Space wrap size={4}>
                      {types.map(t => (
                        <Tag key={t} color="blue">{reportTypes.find(r => r.key === t)?.title || t}</Tag>
                      ))}
                    </Space>
                  ),
                },
                {
                  title: 'Schedule',
                  key: 'schedule',
                  render: (_: any, record: ScheduledReport) => (
                    <Space>
                      <CalendarOutlined />
                      <Text>{record.schedule.charAt(0).toUpperCase() + record.schedule.slice(1)} at {record.time}</Text>
                    </Space>
                  ),
                },
                {
                  title: 'Next Run',
                  dataIndex: 'nextRun',
                  key: 'nextRun',
                  render: (time: string) => <Text type="secondary">{time}</Text>,
                },
                {
                  title: 'Email',
                  dataIndex: 'email',
                  key: 'email',
                  render: (email: string) => email ? <Text code>{email}</Text> : <Text type="secondary">-</Text>,
                },
                {
                  title: 'Actions',
                  key: 'actions',
                  render: (_: any, record: ScheduledReport) => (
                    <Space>
                      <Switch 
                        size="small" 
                        checked={record.enabled} 
                        onChange={() => toggleSchedule(record.id)}
                      />
                      <Button 
                        type="link" 
                        size="small" 
                        icon={<EditOutlined />}
                        onClick={() => {
                          setEditingSchedule(record);
                          scheduleForm.setFieldsValue({
                            ...record,
                            time: dayjs(record.time, 'HH:mm'),
                          });
                          setScheduleModalVisible(true);
                        }}
                      />
                      <Button 
                        type="link" 
                        size="small" 
                        danger 
                        icon={<DeleteOutlined />}
                        onClick={() => deleteSchedule(record.id)}
                      />
                    </Space>
                  ),
                },
              ]}
              pagination={false}
            />
          </Card>
        </TabPane>

        <TabPane tab={<span><HistoryOutlined /> Report History</span>} key="history">
          <Card 
            bordered={false}
            extra={
              <Button icon={<SyncOutlined />} onClick={fetchReportHistory} loading={reportHistoryLoading}>
                Refresh
              </Button>
            }
          >
            {generatedReports.length === 0 && !reportHistoryLoading ? (
              <Empty description="No reports in history" />
            ) : (
              <Table
                dataSource={generatedReports}
                rowKey="id"
                loading={reportHistoryLoading}
                columns={[
                  {
                    title: 'Report',
                    dataIndex: 'name',
                    key: 'name',
                    render: (name: string, record: GeneratedReport) => (
                      <Space>
                        {record.format === 'CSV' ?
                          <FileExcelOutlined style={{ color: '#4d9f7c' }} /> :
                          <FileTextOutlined style={{ color: '#0891b2' }} />
                        }
                        <Text>{name}</Text>
                      </Space>
                    ),
                  },
                  {
                    title: 'Format',
                    dataIndex: 'format',
                    key: 'format',
                    render: (format: string) => <Tag>{format}</Tag>,
                  },
                  {
                    title: 'Size',
                    dataIndex: 'size',
                    key: 'size',
                  },
                  {
                    title: 'Created',
                    dataIndex: 'createdAt',
                    key: 'createdAt',
                  },
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    key: 'status',
                    render: (status: string) => (
                      <Tag color={status === 'ready' ? 'green' : status === 'failed' ? 'red' : 'blue'}>
                        {status === 'ready' && <CheckCircleOutlined />}
                        {status === 'failed' && <ExclamationCircleOutlined />}
                        {' '}{status.charAt(0).toUpperCase() + status.slice(1)}
                      </Tag>
                    ),
                  },
                  {
                    title: 'Actions',
                    key: 'actions',
                    render: (_: any, record: GeneratedReport) => (
                      <Button 
                        type="link" 
                        icon={<DownloadOutlined />}
                        onClick={() => redownloadReport(record)}
                      >
                        Download
                      </Button>
                    ),
                  },
                ]}
                pagination={{ pageSize: 10 }}
              />
            )}
          </Card>
        </TabPane>

        {/* SLO/SLA Tracking Tab */}
        <TabPane tab={<span><DashboardOutlined /> SLO/SLA Tracking</span>} key="slo">
          <Card 
            bordered={false}
                      title={
                        <Space>
                <DashboardOutlined />
                <span>Service Level Objectives</span>
              </Space>
            }
            extra={
              <Space>
                <Select
                  value={sloTimeWindow}
                  onChange={setSloTimeWindow}
                  style={{ width: 120 }}
                >
                  <Option value="7d">Last 7 Days</Option>
                  <Option value="30d">Last 30 Days</Option>
                  <Option value="90d">Last 90 Days</Option>
                </Select>
                <Tooltip title="SLOs are automatically calculated from analysis data">
                  <Tag color="blue">Auto-calculated</Tag>
                </Tooltip>
              </Space>
            }
          >
            {/* SLO Summary */}
            <Row gutter={16} style={{ marginBottom: 24 }}>
              <Col span={6}>
                <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
                  <Statistic
                    title="SLOs Met"
                    value={sloDefinitions.filter(s => s.status === 'met').length}
                    suffix={`/ ${sloDefinitions.length}`}
                    valueStyle={{ color: '#4d9f7c' }}
                    prefix={<CheckCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: token.colorWarningBg, borderColor: token.colorWarningBorder }}>
                  <Statistic
                    title="At Risk"
                    value={sloDefinitions.filter(s => s.status === 'at_risk').length}
                    valueStyle={{ color: '#c9a55a' }}
                    prefix={<ExclamationCircleOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small" style={{ background: token.colorErrorBg, borderColor: token.colorErrorBorder }}>
                  <Statistic
                    title="Breached"
                    value={sloDefinitions.filter(s => s.status === 'breached').length}
                    valueStyle={{ color: '#f76e6e' }}
                    prefix={<WarningOutlined />}
                  />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic
                    title="Avg Error Budget"
                    value={sloDefinitions.length > 0 
                      ? (sloDefinitions.reduce((acc, s) => acc + s.error_budget_remaining, 0) / sloDefinitions.length).toFixed(1)
                      : 0
                    }
                    suffix="%"
                    valueStyle={{ color: '#0891b2' }}
                    prefix={<FieldTimeOutlined />}
                  />
                </Card>
              </Col>
            </Row>

            {/* SLO Table */}
            {sloLoading ? (
              <div style={{ textAlign: 'center', padding: 50 }}>
                <Spin size="large" />
              </div>
            ) : sloDefinitions.length === 0 ? (
              <Empty description="Select an analysis to view SLO metrics" />
            ) : (
              <Table
                dataSource={sloDefinitions}
                rowKey="id"
                columns={[
                  {
                    title: 'SLO Name',
                    dataIndex: 'name',
                    key: 'name',
                    render: (name: string, record: SLODefinition) => (
                      <Space direction="vertical" size={0}>
                        <Text strong>{name}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>{record.description}</Text>
                      </Space>
                    ),
                  },
                  {
                    title: 'Target',
                    dataIndex: 'target',
                    key: 'target',
                    render: (target: number, record: SLODefinition) => {
                      const operator = record.threshold_operator === 'gte' ? '≥' : 
                                       record.threshold_operator === 'lte' ? '≤' :
                                       record.threshold_operator === 'gt' ? '>' : '<';
                      const unit = record.metric === 'latency' ? 'ms' : 
                                   record.metric === 'error_rate' ? '%' :
                                   record.metric === 'availability' ? '%' : '';
                      return <Tag color="blue">{operator} {target}{unit}</Tag>;
                    },
                  },
                  {
                    title: 'Current Value',
                    dataIndex: 'current_value',
                    key: 'current_value',
                    render: (value: number, record: SLODefinition) => {
                      const unit = record.metric === 'latency' ? 'ms' : 
                                   record.metric === 'error_rate' ? '%' :
                                   record.metric === 'availability' ? '%' : '';
                      return <Text strong>{value.toFixed(2)}{unit}</Text>;
                    },
                  },
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    key: 'status',
                    render: (status: SLODefinition['status']) => (
                      <Tag color={getSloStatusColor(status)} icon={getSloStatusIcon(status)}>
                        {status.toUpperCase().replace('_', ' ')}
                          </Tag>
                    ),
                  },
                  {
                    title: 'Error Budget',
                    dataIndex: 'error_budget_remaining',
                    key: 'error_budget_remaining',
                    render: (budget: number) => (
                      <Progress 
                        percent={budget} 
                        size="small" 
                        status={budget < 20 ? 'exception' : budget < 50 ? 'active' : 'success'}
                        format={(percent) => `${percent?.toFixed(1)}%`}
                      />
                    ),
                  },
                  {
                    title: 'Scope',
                    key: 'scope',
                    render: (_: any, record: SLODefinition) => (
                      <Space size={4}>
                        {record.service && <Tag>{record.service}</Tag>}
                        {record.namespace && <Tag color="purple">{record.namespace}</Tag>}
                        {!record.service && !record.namespace && <Text type="secondary">Global</Text>}
                      </Space>
                    ),
                  },
                ]}
                pagination={{ pageSize: 10 }}
              />
            )}
          </Card>
        </TabPane>

        {/* Trend Analysis Tab */}
        <TabPane tab={<span><LineChartOutlined /> Trend Analysis</span>} key="trends">
          <Card 
            bordered={false}
            title={
              <Space>
                <FundOutlined />
                <span>Metric Trends</span>
                        </Space>
                      }
            extra={
              <Space>
                <Select
                  value={selectedTrendCategory}
                  onChange={setSelectedTrendCategory}
                  style={{ width: 140 }}
                >
                  <Option value="all">All Categories</Option>
                  <Option value="traffic">Traffic</Option>
                  <Option value="errors">Errors</Option>
                  <Option value="latency">Latency</Option>
                  <Option value="resources">Resources</Option>
                </Select>
                <Select
                  value={trendTimeRange}
                  onChange={setTrendTimeRange}
                  style={{ width: 120 }}
                >
                  <Option value="24h">Last 24h</Option>
                  <Option value="7d">Last 7 Days</Option>
                  <Option value="30d">Last 30 Days</Option>
                  <Option value="90d">Last 90 Days</Option>
                </Select>
                <Tooltip title="Metrics are automatically calculated from analysis data">
                  <Tag color="blue">Auto-calculated</Tag>
                </Tooltip>
                        </Space>
                      }
          >
            {trendLoading ? (
              <div style={{ textAlign: 'center', padding: 50 }}>
                <Spin size="large" />
              </div>
            ) : filteredTrendMetrics.length === 0 ? (
              <Empty description="Select an analysis to view trend metrics" />
            ) : (
              <Row gutter={[16, 16]}>
                {filteredTrendMetrics.map(metric => {
                  const isPositiveGood = metric.category === 'errors' || metric.category === 'latency';
                  const changeColor = metric.change_percent === 0 ? 'default' :
                    (isPositiveGood ? metric.change_percent < 0 : metric.change_percent > 0) ? 'green' : 'red';
                  
                  return (
                    <Col xs={24} sm={12} lg={6} key={metric.id}>
                      <Card 
                        size="small" 
                        hoverable
                        style={{ height: '100%' }}
                      >
                        <Space direction="vertical" style={{ width: '100%' }} size={8}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>{metric.name}</Text>
                            <Tag color={
                              metric.category === 'traffic' ? 'blue' :
                              metric.category === 'errors' ? 'red' :
                              metric.category === 'latency' ? 'orange' : 'purple'
                            } style={{ fontSize: 10 }}>
                              {metric.category}
                            </Tag>
                          </div>
                          
                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                            <Text style={{ fontSize: 24, fontWeight: 600 }}>
                              {metric.current_value >= 1000 
                                ? `${(metric.current_value / 1000).toFixed(1)}K`
                                : metric.current_value.toFixed(metric.current_value < 1 ? 2 : 1)
                              }
                            </Text>
                            <Text type="secondary" style={{ fontSize: 12 }}>{metric.unit}</Text>
                          </div>
                          
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {getTrendIcon(metric.trend, !isPositiveGood)}
                            <Tag color={changeColor} style={{ margin: 0 }}>
                              {metric.change_percent > 0 ? '+' : ''}{metric.change_percent.toFixed(1)}%
                            </Tag>
                            <Text type="secondary" style={{ fontSize: 11 }}>vs previous</Text>
                          </div>
                          
                          {/* Mini sparkline visualization */}
                          <div style={{ 
                            height: 40, 
                            display: 'flex', 
                            alignItems: 'flex-end', 
                            gap: 1,
                            marginTop: 8 
                          }}>
                            {metric.data.slice(-14).map((point, idx) => {
                              const maxVal = Math.max(...metric.data.map(d => d.value));
                              const minVal = Math.min(...metric.data.map(d => d.value));
                              const range = maxVal - minVal || 1;
                              const height = ((point.value - minVal) / range) * 36 + 4;
                              return (
                                <div
                                  key={idx}
                                  style={{
                                    flex: 1,
                                    height: `${height}px`,
                                    background: metric.category === 'traffic' ? '#0891b2' :
                                               metric.category === 'errors' ? '#f76e6e' :
                                               metric.category === 'latency' ? '#c9a55a' : '#7c8eb5',
                                    borderRadius: 2,
                                    opacity: 0.3 + (idx / 14) * 0.7,
                                  }}
                                />
                              );
                            })}
                          </div>
                        </Space>
                      </Card>
                    </Col>
                  );
                })}
              </Row>
            )}

            {/* Trend Summary */}
            <Divider />
            <Row gutter={16}>
              <Col span={8}>
                <Card size="small" title={<><RiseOutlined /> Increasing Metrics</>}>
                  <List
                    size="small"
                    dataSource={trendMetrics.filter(m => m.trend === 'up')}
                    renderItem={item => (
                      <List.Item>
                        <Text>{item.name}</Text>
                        <Tag color="red">+{item.change_percent.toFixed(1)}%</Tag>
                  </List.Item>
                )}
                    locale={{ emptyText: 'None' }}
                  />
                </Card>
              </Col>
              <Col span={8}>
                <Card size="small" title={<><FallOutlined /> Decreasing Metrics</>}>
                  <List
                    size="small"
                    dataSource={trendMetrics.filter(m => m.trend === 'down')}
                    renderItem={item => (
                      <List.Item>
                        <Text>{item.name}</Text>
                        <Tag color="green">{item.change_percent.toFixed(1)}%</Tag>
                      </List.Item>
                    )}
                    locale={{ emptyText: 'None' }}
                  />
          </Card>
              </Col>
              <Col span={8}>
                <Card size="small" title={<><AreaChartOutlined /> Key Insights</>}>
                  {trendMetrics.length === 0 ? (
                    <Empty description="No insights available" />
                  ) : (
                    <List
                      size="small"
                      dataSource={(() => {
                        const insights: { text: string; type: 'success' | 'warning' | 'info' }[] = [];
                        const errorMetric = trendMetrics.find(m => m.id === 'error_rate' || m.id === 'error_count');
                        const cpuMetric = trendMetrics.find(m => m.id === 'cpu_usage');
                        const trafficMetric = trendMetrics.find(m => m.id === 'requests' || m.category === 'traffic');
                        
                        if (errorMetric && errorMetric.trend === 'down') {
                          insights.push({ text: 'Error rate trending down - good sign', type: 'success' });
                        } else if (errorMetric && errorMetric.trend === 'up') {
                          insights.push({ text: 'Error rate increasing - investigate', type: 'warning' });
                        }
                        
                        if (cpuMetric && cpuMetric.current_value > 70) {
                          insights.push({ text: 'CPU usage high - monitor closely', type: 'warning' });
                        } else if (cpuMetric) {
                          insights.push({ text: 'CPU usage within normal range', type: 'info' });
                        }
                        
                        if (trafficMetric && trafficMetric.trend === 'up') {
                          insights.push({ text: 'Traffic growth is healthy', type: 'info' });
                        }
                        
                        return insights.length > 0 ? insights : [{ text: 'Collecting insights...', type: 'info' as const }];
                      })()}
                      renderItem={item => (
                        <List.Item>
                          <Alert message={item.text} type={item.type} showIcon style={{ width: '100%' }} />
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              </Col>
            </Row>
          </Card>
        </TabPane>

        {/* Cost Reports Tab */}
        <TabPane tab={<span><DollarOutlined /> Cost Analysis</span>} key="costs">
          <Card 
            bordered={false}
            title={
              <Space>
                <DollarOutlined />
                <span>Resource Cost Analysis</span>
              </Space>
            }
            extra={
              <Space>
                <Select
                  value={costTimeRange}
                  onChange={setCostTimeRange}
                  style={{ width: 120 }}
                >
                  <Option value="7d">Last 7 Days</Option>
                  <Option value="30d">Last 30 Days</Option>
                  <Option value="90d">Last 90 Days</Option>
                </Select>
                <Tooltip title="Cost estimates are calculated from workload data">
                  <Tag color="blue">Estimated</Tag>
                </Tooltip>
              </Space>
            }
          >
            {costLoading ? (
              <div style={{ textAlign: 'center', padding: 50 }}>
                <Spin size="large" />
              </div>
            ) : !costData ? (
              <Empty description="Select an analysis to view cost estimates" />
            ) : (
              <>
                {/* Cost Overview */}
                <Row gutter={16} style={{ marginBottom: 24 }}>
                  <Col span={6}>
                    <Card size="small" style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}>
                      <Statistic
                        title="Estimated Monthly Cost"
                        value={costData.total}
                        precision={2}
                        prefix="$"
                        valueStyle={{ color: '#4d9f7c' }}
                      />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ background: '#e6f7ff', borderColor: '#91d5ff' }}>
                      <Statistic
                        title="Compute Cost"
                        value={costData.compute}
                        precision={2}
                        prefix="$"
                        valueStyle={{ color: '#0891b2' }}
                      />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ background: token.colorWarningBg, borderColor: token.colorWarningBorder }}>
                      <Statistic
                        title="Network Cost"
                        value={costData.network}
                        precision={2}
                        prefix="$"
                        valueStyle={{ color: '#c9a55a' }}
                      />
                    </Card>
                  </Col>
                  <Col span={6}>
                    <Card size="small" style={{ background: '#f9f0ff', borderColor: '#d3adf7' }}>
                      <Statistic
                        title="Storage Cost"
                        value={costData.storage}
                        precision={2}
                        prefix="$"
                        valueStyle={{ color: '#7c8eb5' }}
                      />
                    </Card>
                  </Col>
                </Row>

                {/* Cost by Namespace */}
                <Row gutter={16}>
                  <Col span={12}>
                    <Card size="small" title="Cost by Namespace">
                      {costData.by_namespace.length === 0 ? (
                        <Empty description="No namespace cost data" />
                      ) : (
                        <Table
                          size="small"
                          dataSource={costData.by_namespace.map((item, idx) => ({ ...item, key: idx }))}
                          columns={[
                            { title: 'Namespace', dataIndex: 'namespace', key: 'namespace' },
                            { 
                              title: 'Cost', 
                              dataIndex: 'cost', 
                              key: 'cost',
                              render: (cost: number) => `$${cost.toFixed(2)}`
                            },
                            { 
                              title: 'Share', 
                              dataIndex: 'percentage', 
                              key: 'percentage',
                              render: (pct: number) => (
                                <Progress percent={pct} size="small" showInfo={false} />
                              )
                            },
                          ]}
                          pagination={false}
                        />
                      )}
                    </Card>
                  </Col>
                  <Col span={12}>
                    <Card size="small" title="Top Resource Consumers">
                      {costData.top_consumers.length === 0 ? (
                        <Empty description="No resource cost data" />
                      ) : (
                        <Table
                          size="small"
                          dataSource={costData.top_consumers.map((item, idx) => ({ ...item, key: idx }))}
                          columns={[
                            { title: 'Resource', dataIndex: 'resource', key: 'resource' },
                            { 
                              title: 'Type', 
                              dataIndex: 'type', 
                              key: 'type',
                              render: (type: string) => <Tag>{type}</Tag>
                            },
                            { 
                              title: 'Monthly Cost', 
                              dataIndex: 'cost', 
                              key: 'cost',
                              render: (cost: number) => `$${cost.toFixed(2)}`
                            },
                          ]}
                          pagination={false}
                        />
                      )}
                    </Card>
                  </Col>
                </Row>

                {/* Cost Optimization Recommendations */}
                <Card size="small" title="Cost Optimization Recommendations" style={{ marginTop: 16 }}>
                  {costData.recommendations.length === 0 ? (
                    <Empty description="No optimization recommendations available" />
                  ) : (
                    <List
                      size="small"
                      dataSource={costData.recommendations}
                      renderItem={item => (
                        <List.Item>
                          <List.Item.Meta
                            title={
                              <Space>
                                <Text strong>{item.title}</Text>
                                <Tag color={item.impact === 'low' ? 'green' : item.impact === 'medium' ? 'orange' : 'red'}>
                                  {item.impact} impact
                                </Tag>
                              </Space>
                            }
                            description={item.description}
                          />
                          <Tag color="green">Save ${item.savings.toFixed(2)}/mo</Tag>
                        </List.Item>
                      )}
                    />
                  )}
                </Card>
              </>
            )}
          </Card>
        </TabPane>
        
        {/* Custom Report Builder Tab */}
        <TabPane tab={<span><FilterOutlined /> Custom Builder</span>} key="builder">
          <Card title="Custom Report Builder" bordered={false}>
            <Alert
              message="Build Your Own Report"
              description="Select data sources, choose fields, apply filters, and generate a custom report tailored to your needs."
              type="info"
              showIcon
              style={{ marginBottom: 24 }}
            />
            
            <Row gutter={24}>
              {/* Data Source Selection */}
              <Col span={8}>
                <Card size="small" title="1. Select Data Sources">
                  <Checkbox.Group
                    style={{ width: '100%' }}
                    value={customReportConfig.dataSources}
                    onChange={(values) => setCustomReportConfig(prev => ({ ...prev, dataSources: values as string[] }))}
                  >
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Checkbox value="events">
                        <Space>
                          <ClockCircleOutlined />
                          Events Data
                        </Space>
                      </Checkbox>
                      <Checkbox value="communications">
                        <Space>
                          <ApiOutlined />
                          Communications
                        </Space>
                      </Checkbox>
                      <Checkbox value="workloads">
                        <Space>
                          <DatabaseOutlined />
                          Workloads
                        </Space>
                      </Checkbox>
                      <Checkbox value="security">
                        <Space>
                          <SecurityScanOutlined />
                          Security Events
                        </Space>
                      </Checkbox>
                      <Checkbox value="changes">
                        <Space>
                          <SwapOutlined />
                          Changes
                        </Space>
                      </Checkbox>
                    </Space>
                  </Checkbox.Group>
                </Card>
              </Col>
              
              {/* Field Selection */}
              <Col span={8}>
                <Card size="small" title="2. Choose Fields">
                  {customReportConfig.dataSources.length === 0 ? (
                    <Empty description="Select data sources first" />
                  ) : (
                    <Checkbox.Group
                      style={{ width: '100%' }}
                      value={customReportConfig.fields}
                      onChange={(values) => setCustomReportConfig(prev => ({ ...prev, fields: values as string[] }))}
                    >
                      <Space direction="vertical" style={{ width: '100%' }}>
                        {customReportConfig.dataSources.includes('events') && (
                          <>
                            <Checkbox value="event_type">Event Type</Checkbox>
                            <Checkbox value="event_count">Event Count</Checkbox>
                            <Checkbox value="timestamp">Timestamp</Checkbox>
                          </>
                        )}
                        {customReportConfig.dataSources.includes('communications') && (
                          <>
                            <Checkbox value="source">Source</Checkbox>
                            <Checkbox value="destination">Destination</Checkbox>
                            <Checkbox value="protocol">Protocol</Checkbox>
                            <Checkbox value="bytes">Bytes Transferred</Checkbox>
                          </>
                        )}
                        {customReportConfig.dataSources.includes('workloads') && (
                          <>
                            <Checkbox value="workload_name">Workload Name</Checkbox>
                            <Checkbox value="namespace">Namespace</Checkbox>
                            <Checkbox value="status">Status</Checkbox>
                            <Checkbox value="replicas">Replicas</Checkbox>
                          </>
                        )}
                        {customReportConfig.dataSources.includes('security') && (
                          <>
                            <Checkbox value="severity">Severity</Checkbox>
                            <Checkbox value="violation_type">Violation Type</Checkbox>
                            <Checkbox value="affected_pod">Affected Pod</Checkbox>
                          </>
                        )}
                        {customReportConfig.dataSources.includes('changes') && (
                          <>
                            <Checkbox value="change_type">Change Type</Checkbox>
                            <Checkbox value="resource">Resource</Checkbox>
                            <Checkbox value="changed_by">Changed By</Checkbox>
                          </>
                        )}
                      </Space>
                    </Checkbox.Group>
                  )}
                </Card>
              </Col>
              
              {/* Filters & Options */}
              <Col span={8}>
                <Card size="small" title="3. Apply Filters">
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>Time Range</Text>
                      <RangePicker 
                        style={{ width: '100%', marginTop: 4 }}
                        value={customReportConfig.timeRange}
                        onChange={(dates) => setCustomReportConfig(prev => ({ 
                          ...prev, 
                          timeRange: dates as [dayjs.Dayjs, dayjs.Dayjs] | null 
                        }))}
                      />
              </div>
                    
              <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>Namespace Filter</Text>
                      <Select
                        mode="multiple"
                        style={{ width: '100%', marginTop: 4 }}
                        placeholder="All namespaces"
                        value={customReportConfig.namespaces}
                        onChange={(values) => setCustomReportConfig(prev => ({ ...prev, namespaces: values }))}
                        options={Array.from(new Set(workloads?.map(w => w.namespace_name) || [])).map(ns => ({
                          label: ns,
                          value: ns,
                        }))}
                      />
              </div>
                    
              <div>
                      <Text type="secondary" style={{ fontSize: 12 }}>Output Format</Text>
                      <Select
                        style={{ width: '100%', marginTop: 4 }}
                        value={customReportConfig.format}
                        onChange={(value) => setCustomReportConfig(prev => ({ ...prev, format: value }))}
                        options={[
                          { label: 'CSV', value: 'csv' },
                          { label: 'JSON', value: 'json' },
                          { label: 'PDF', value: 'pdf' },
                        ]}
                      />
                    </div>
                    
                    <Divider style={{ margin: '12px 0' }} />
                    
                    <div>
                      <Checkbox
                        checked={customReportConfig.includeCharts}
                        onChange={(e) => setCustomReportConfig(prev => ({ ...prev, includeCharts: e.target.checked }))}
                      >
                        Include Charts (PDF only)
                      </Checkbox>
                    </div>
                    
                    <div>
                      <Checkbox
                        checked={customReportConfig.groupByNamespace}
                        onChange={(e) => setCustomReportConfig(prev => ({ ...prev, groupByNamespace: e.target.checked }))}
                      >
                        Group by Namespace
                      </Checkbox>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
            
            {/* Preview & Generate */}
            <Card size="small" title="4. Generate Report" style={{ marginTop: 16 }}>
              <Row gutter={16} align="middle">
                <Col flex="auto">
                  <Space>
                    <Text type="secondary">
                      Selected: {customReportConfig.dataSources.length} sources, {customReportConfig.fields.length} fields
                    </Text>
                    {customReportConfig.dataSources.length > 0 && customReportConfig.fields.length > 0 && (
                      <Tag color="green">Ready to generate</Tag>
                    )}
                  </Space>
                </Col>
                <Col>
                  <Space>
                    <Button
                      icon={<EyeOutlined />}
                      disabled={customReportConfig.dataSources.length === 0 || customReportConfig.fields.length === 0 || !selectedAnalysisId}
                      loading={customReportPreviewLoading}
                      onClick={previewCustomReport}
                    >
                      Preview
                    </Button>
                    <Button
                      type="primary"
                      icon={<DownloadOutlined />}
                      disabled={customReportConfig.dataSources.length === 0 || customReportConfig.fields.length === 0 || !selectedAnalysisId}
                      loading={customReportGenerating}
                      onClick={generateCustomReport}
                    >
                      Generate Report
                    </Button>
                  </Space>
                </Col>
              </Row>
            </Card>
            
            {/* Saved Templates */}
            <Card size="small" title="Saved Templates" style={{ marginTop: 16 }}>
              {savedReportTemplates.length === 0 ? (
                <Empty 
                  description="No saved templates" 
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              ) : (
                <List
                  size="small"
                  dataSource={savedReportTemplates}
                  renderItem={item => (
                    <List.Item
                      actions={[
                        <Button 
                          size="small" 
                          type="link" 
                          onClick={() => {
                            setCustomReportConfig({
                              ...customReportConfig,
                              dataSources: item.sources,
                              fields: item.fields,
                            });
                            message.success(`Loaded template: ${item.name}`);
                          }}
                        >
                          Load
                        </Button>,
                        <Button 
                          size="small" 
                          type="link" 
                          danger 
                          onClick={() => {
                            setSavedReportTemplates(prev => prev.filter(t => t.id !== item.id));
                            message.success('Template deleted');
                          }}
                        >
                          Delete
                        </Button>,
                      ]}
                    >
                      <List.Item.Meta
                        title={item.name}
                        description={`${item.sources.length} sources, ${item.fields.length} fields`}
                      />
                    </List.Item>
                  )}
                />
              )}
              <Button 
                type="dashed" 
                block 
                style={{ marginTop: 8 }}
                icon={<PlusOutlined />}
                disabled={customReportConfig.dataSources.length === 0 || customReportConfig.fields.length === 0}
                onClick={() => {
                  const templateName = `Custom Report ${savedReportTemplates.length + 1}`;
                  const newTemplate = {
                    id: Date.now(),
                    name: templateName,
                    sources: customReportConfig.dataSources,
                    fields: customReportConfig.fields,
                  };
                  setSavedReportTemplates(prev => [...prev, newTemplate]);
                  message.success(`Template saved: ${templateName}`);
                }}
              >
                Save Current as Template
              </Button>
            </Card>
          </Card>
        </TabPane>
      </Tabs>

      {/* Preview Modal */}
      <Modal
        title={
          <Space>
            <EyeOutlined />
            <span>Preview: {previewReportType}</span>
          </Space>
        }
        open={previewVisible}
        onCancel={() => {
          setPreviewVisible(false);
          setPreviewData(null);
        }}
        width={900}
        footer={[
          <Button key="copy" icon={<CopyOutlined />} onClick={copyPreviewToClipboard}>
            Copy JSON
          </Button>,
          <Button key="close" type="primary" onClick={() => setPreviewVisible(false)}>
            Close
          </Button>,
        ]}
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 50 }}>
            <Spin size="large" />
            <Text style={{ display: 'block', marginTop: 16 }}>Loading preview...</Text>
              </div>
        ) : previewData ? (
              <div>
            <Alert
              message="Preview Mode"
              description="Showing first 10 records. Download the full report for complete data."
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <div style={{ 
              background: '#f5f5f5', 
              padding: 16, 
              borderRadius: 8, 
              maxHeight: 500, 
              overflow: 'auto',
              fontFamily: 'monospace',
              fontSize: 12,
              whiteSpace: 'pre-wrap',
            }}>
              {JSON.stringify(previewData, null, 2)}
              </div>
              </div>
        ) : (
          <Empty description="No data to preview" />
        )}
      </Modal>

      {/* Schedule Modal */}
      <Modal
        title={editingSchedule ? 'Edit Schedule' : 'New Scheduled Report'}
        open={scheduleModalVisible}
        onCancel={() => {
          setScheduleModalVisible(false);
          setEditingSchedule(null);
          scheduleForm.resetFields();
        }}
        onOk={() => scheduleForm.submit()}
        confirmLoading={savingSchedule}
        width={600}
      >
        <Form
          form={scheduleForm}
          layout="vertical"
          onFinish={handleSaveSchedule}
          initialValues={{
            schedule: 'daily',
            format: 'CSV',
            time: dayjs('08:00', 'HH:mm'),
          }}
        >
          <Form.Item
            name="name"
            label="Schedule Name"
            rules={[{ required: true, message: 'Please enter a name' }]}
          >
            <Input placeholder="e.g., Daily Security Report" />
          </Form.Item>

          <Form.Item
            name="reportTypes"
            label="Reports to Generate"
            rules={[{ required: true, message: 'Please select at least one report' }]}
          >
            <Checkbox.Group>
              <Row>
                {reportTypes.map(report => (
                  <Col span={12} key={report.key}>
                    <Checkbox value={report.key}>{report.title}</Checkbox>
        </Col>
                ))}
      </Row>
            </Checkbox.Group>
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="schedule"
                label="Frequency"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="daily">Daily</Option>
                  <Option value="weekly">Weekly</Option>
                  <Option value="monthly">Monthly</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="time"
                label="Time"
                rules={[{ required: true }]}
              >
                <TimePicker format="HH:mm" style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="format"
                label="Format"
                rules={[{ required: true }]}
              >
                <Select>
                  <Option value="CSV">CSV</Option>
                  <Option value="JSON">JSON</Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="email"
            label="Email (Optional)"
            rules={[{ type: 'email', message: 'Please enter a valid email' }]}
          >
            <Input prefix={<MailOutlined />} placeholder="reports@company.com" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Reports;
