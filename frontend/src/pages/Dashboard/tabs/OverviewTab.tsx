import React, { useMemo, useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Row, Col, Card, Typography, Space, Tag, Progress, Empty, Spin, Tooltip, theme, Alert, Button, message } from 'antd';
import {
  ClusterOutlined,
  ApiOutlined,
  SecurityScanOutlined,
  ThunderboltOutlined,
  RiseOutlined,
  FallOutlined,
  WarningOutlined,
  CloudServerOutlined,
  SwapOutlined,
  FireOutlined,
  RightOutlined,
  DashboardOutlined,
  DragOutlined,
  LockOutlined,
  UnlockOutlined,
  ReloadOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';
import TrafficHeatmap from '../components/TrafficHeatmap';
import PodHealthGrid from '../components/PodHealthGrid';
import GoldenSignals from '../components/GoldenSignals';
import AIInsightCards from '../components/AIInsightCards';

// Import API hooks
import { useGetClustersQuery } from '../../../store/api/clusterApi';
import { useGetAnalysesQuery } from '../../../store/api/analysisApi';
import { useGetEventStatsQuery, useGetSecurityEventsQuery, useGetOomEventsQuery, SecurityEvent } from '../../../store/api/eventsApi';
import { useGetCommunicationStatsQuery, useGetCommunicationsQuery, useGetHighRiskCommunicationsQuery, useGetErrorStatsQuery } from '../../../store/api/communicationApi';
import { useGetWorkloadStatsQuery, useGetWorkloadsQuery } from '../../../store/api/workloadApi';
import { useGetChangesQuery, useGetErrorAnomalySummaryQuery } from '../../../store/api/changesApi';
import { Analysis, Workload } from '../../../types';
import { useTheme } from '../../../contexts/ThemeContext';

// Import shared security score utilities - single source of truth
import { 
  calculateSecurityScore, 
  capabilityRisk,
  getEventSeverity,
  SECURITY_EVENTS_LIMIT,
  OOM_EVENTS_LIMIT
} from '../../../utils/securityScore';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;
const { useToken } = theme;

interface OverviewTabProps {
  clusterId?: number;
  analysisId?: number;
}

// Insight card component with optional drill-down link
const InsightCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  value: string | number;
  trend?: 'up' | 'down' | 'neutral';
  trendLabel?: string;
  severity?: 'success' | 'warning' | 'error' | 'info';
  description?: string;
  linkTo?: string;
  onClick?: () => void;
}> = ({ icon, title, value, trend, trendLabel, severity = 'info', description, linkTo, onClick }) => {
  const { token } = useToken();
  const navigate = useNavigate();
  
  const severityColors = {
    success: '#4caf50',
    warning: '#d4a844',
    error: '#e05252',
    info: token.colorPrimary,
  };
  
  const color = severityColors[severity];
  const isClickable = !!(linkTo || onClick);
  
  const handleClick = () => {
    if (onClick) {
      onClick();
    } else if (linkTo) {
      navigate(linkTo);
    }
  };
  
  return (
    <Card 
      size="small" 
      bordered={false}
      hoverable={isClickable}
      onClick={isClickable ? handleClick : undefined}
      style={{ 
        background: `linear-gradient(135deg, ${color}10 0%, ${token.colorBgContainer} 100%)`,
        borderLeft: `3px solid ${color}`,
        cursor: isClickable ? 'pointer' : 'default',
        transition: 'all 0.2s ease',
        height: '100%',
      }}
    >
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <span style={{ color }}>{icon}</span>
            <Text type="secondary" style={{ fontSize: 12 }}>{title}</Text>
          </Space>
          {isClickable && (
            <RightOutlined style={{ color: token.colorTextTertiary, fontSize: 10 }} />
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <Text strong style={{ fontSize: 24, color }}>{value}</Text>
          {trend && trendLabel && (
            <Tag 
              color={trend === 'up' ? 'green' : trend === 'down' ? 'red' : 'default'}
              style={{ fontSize: 10 }}
            >
              {trend === 'up' ? <RiseOutlined /> : trend === 'down' ? <FallOutlined /> : null}
              {trendLabel}
            </Tag>
          )}
        </div>
        {description && (
          <Text type="secondary" style={{ fontSize: 11 }}>{description}</Text>
        )}
      </Space>
    </Card>
  );
};

const OverviewTab: React.FC<OverviewTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#a0aec0';

  // API Queries
  const { data: clustersData } = useGetClustersQuery();
  const clusters = clustersData?.clusters || [];
  const currentCluster = clusters.find((c: any) => c.id === clusterId);

  const { data: analyses = [], isLoading: analysesLoading } = useGetAnalysesQuery(
    { cluster_id: clusterId },
    { skip: !clusterId }
  );

  const { data: eventStats, isLoading: eventsLoading } = useGetEventStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  const { data: commStats, isLoading: commLoading } = useGetCommunicationStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  // Error anomaly summary for GoldenSignals
  const { data: errorAnomalySummary } = useGetErrorAnomalySummaryQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );
  
  // Categorized error statistics (NO LIMIT - accurate counts)
  const { data: errorStats } = useGetErrorStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId }
  );

  const { data: communications } = useGetCommunicationsQuery(
    { cluster_id: clusterId, analysis_id: analysisId, limit: 50 },
    { skip: !clusterId }
  );

  const { data: highRiskComms } = useGetHighRiskCommunicationsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, risk_threshold: 0.5, limit: 20 },
    { skip: !clusterId }
  );

  const { data: workloadStats, isLoading: workloadsLoading } = useGetWorkloadStatsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId },
    { skip: !clusterId || !analysisId }
  );

  const { data: workloads = [] } = useGetWorkloadsQuery(
    { cluster_id: clusterId!, is_active: true },
    { skip: !clusterId }
  );

  const { data: securityData, isLoading: securityLoading } = useGetSecurityEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: SECURITY_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  const { data: oomData, isLoading: oomLoading } = useGetOomEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: OOM_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  const { data: changesData, isLoading: changesLoading } = useGetChangesQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: 20 },
    { skip: !clusterId }
  );

  // Computed values
  const analysisStats = useMemo(() => {
    if (!Array.isArray(analyses)) return { total: 0, running: 0, completed: 0 };
    return {
      total: analyses.length,
      running: analyses.filter((a: Analysis) => a.status === 'running').length,
      completed: analyses.filter((a: Analysis) => a.status === 'completed' || a.status === 'stopped').length,
    };
  }, [analyses]);

  // Process security events to extract capabilities (same as SecurityTab)
  const capabilities = useMemo(() => {
    if (!securityData?.events) return [];
    
    const capMap = new Map<string, {
      key: string;
      risk: 'low' | 'medium' | 'high' | 'critical';
    }>();

    securityData.events
      .filter((e: SecurityEvent) => e.security_type === 'capability')
      .forEach((event: SecurityEvent) => {
        const key = `${event.pod}-${event.capability}`;
        if (!capMap.has(key)) {
          const capInfo = capabilityRisk[event.capability || ''] || { risk: 'medium' };
          capMap.set(key, { key, risk: capInfo.risk });
        }
      });

    return Array.from(capMap.values());
  }, [securityData?.events]);

  // Process violations with severity (same as SecurityTab)
  const processedViolations = useMemo(() => {
    if (!securityData?.events) return [];
    return securityData.events
      .filter((e: SecurityEvent) => e.verdict === 'denied')
      .map((event: SecurityEvent) => ({
        severity: getEventSeverity(event.capability),
      }));
  }, [securityData?.events]);

  // Security score calculation - using shared utility (single source of truth)
  const securityScoreData = useMemo(() => {
    if (!analysisId || !clusterId) {
      return { score: null, status: 'no_selection' as const };
    }
    
    if (securityLoading || oomLoading) {
      return { score: null, status: 'loading' as const };
    }
    
    return calculateSecurityScore({
      totalCapabilityChecks: securityData?.total || 0,
      totalOomEvents: oomData?.total || 0,
      violations: processedViolations,
      capabilities: capabilities,
    });
  }, [analysisId, clusterId, securityLoading, oomLoading, securityData?.total, oomData?.total, 
      processedViolations, capabilities]);

  const securityScore = securityScoreData.score;
  const securityStatus = securityScoreData.status;

  // Traffic heatmap data
  const trafficData = useMemo(() => {
    const comms = communications?.communications || [];
    return comms.slice(0, 10).map(comm => ({
      source: comm.source.name,
      sourceNamespace: comm.source.namespace,
      destination: comm.destination.name,
      destinationNamespace: comm.destination.namespace,
      bytes: comm.bytes_transferred,
      requests: comm.request_count,
    }));
  }, [communications]);

  // Pod health data
  const podHealthData = useMemo(() => {
    return workloads.slice(0, 100).map((w: Workload) => {
      let status = w.status || 'Running';
      if (status === 'Unknown' || status === 'unknown' || !status) {
        status = w.is_active !== false ? 'Running' : 'Succeeded';
      }
      return {
        name: w.name || 'unknown',
        namespace: w.namespace_name || 'default',
        status: status as any,
        restarts: 0,
        age: w.first_seen ? dayjs(w.first_seen).fromNow() : undefined,
        workload_type: w.workload_type,
      };
    });
  }, [workloads]);

  const isLoading = analysesLoading || eventsLoading || commLoading || workloadsLoading || changesLoading;

  if (!clusterId) {
    return <Empty description="Select an analysis to view overview" />;
  }

  // Critical insights
  const criticalInsights = [];
  
  if ((oomData?.total || 0) > 0) {
    criticalInsights.push({
      type: 'info',
      message: `${oomData?.total} OOM events detected. Consider reviewing memory limits.`,
    });
  }
  
  if ((changesData?.stats?.by_risk?.critical || 0) > 0) {
    criticalInsights.push({
      type: 'info',
      message: `${changesData?.stats?.by_risk?.critical} critical infrastructure changes detected.`,
    });
  }

  return (
    <div>
      {/* Critical Alerts */}
      {criticalInsights.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          {criticalInsights.map((insight, i) => (
            <Alert
              key={i}
              message={insight.message}
              type={insight.type as any}
              showIcon
              style={{ marginBottom: 8 }}
              closable
            />
          ))}
        </div>
      )}

      {/* Key Metrics */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Total Events"
            value={eventStats?.total_events || 0}
            icon={<ThunderboltOutlined />}
            color="#2eb8b8"
            formatter={(v) => v >= 1000000 ? `${(v/1000000).toFixed(1)}M` : v >= 1000 ? `${(v/1000).toFixed(1)}K` : v.toString()}
            subtitle={`${Object.keys(eventStats?.event_counts || {}).length} event types`}
            pulseEffect={analysisStats.running > 0}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Network Connections"
            value={commStats?.total_communications || 0}
            icon={<ApiOutlined />}
            color="#3cc9c4"
            subtitle={`${commStats?.unique_namespaces || 0} namespaces`}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Security Score"
            value={securityScore ?? 0}
            icon={<SecurityScanOutlined />}
            color={
              securityScore === null ? "#8c8c8c" :
              securityScore >= 80 ? "#3cc9c4" : 
              securityScore >= 60 ? "#e6b05a" : "#e57373"
            }
            suffix="/100"
            subtitle={
              securityScore === null ? (securityStatus === 'loading' ? 'Loading...' : 'Select Analysis') :
              securityScore >= 80 ? 'Healthy' : 
              securityScore >= 60 ? 'Needs Attention' : 'Critical'
            }
            loading={securityStatus === 'loading'}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Active Workloads"
            value={(() => {
              // Use workloads array if API returns suspicious values or no data
              const apiActive = workloadStats?.active_workloads;
              const apiTotal = workloadStats?.total_workloads;
              const workloadCount = workloads.filter((w: Workload) => 
                w.status === 'Running' || w.status === 'Active' || w.status === 'running' || w.status === 'active' ||
                (w.is_active !== false && (!w.status || w.status === 'Unknown' || w.status === 'unknown'))
              ).length;
              // Sanity check: if apiActive > apiTotal or seems invalid, use calculated value
              if (apiActive && apiTotal && apiActive <= apiTotal) {
                return apiActive;
              }
              return workloadCount || apiActive || 0;
            })()}
            icon={<CloudServerOutlined />}
            color="#64b5f6"
            subtitle={`${workloadStats?.total_workloads || workloads.length} total`}
          />
        </Col>
      </Row>

      {/* Golden Signals & AI Insights */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={16}>
          <Card 
            title={<Space><ThunderboltOutlined style={{ color: '#3cc9c4' }} /><span>Golden Signals</span></Space>}
            bordered={false}
            style={{ height: '100%' }}
          >
            <GoldenSignals
              avgLatencyMs={(commStats as any)?.avg_latency_ms || 0}
              p50LatencyMs={(commStats as any)?.p50_latency_ms}
              p95LatencyMs={(commStats as any)?.p95_latency_ms}
              p99LatencyMs={(commStats as any)?.p99_latency_ms}
              requestsPerSecond={(commStats as any)?.requests_per_second || 0}
              totalRequests={(commStats as any)?.total_requests || commStats?.total_communications || 0}
              // Legacy error props (backward compatible)
              errorRate={
                commStats?.total_communications && commStats.total_communications > 0
                  ? (((commStats.total_errors || 0) + (commStats.total_retransmits || 0)) / commStats.total_communications * 100)
                  : 0
              }
              totalErrors={(commStats?.total_errors || 0) + (commStats?.total_retransmits || 0) + (oomData?.total || 0)}
              errorsByType={commStats?.errors_by_type}
              errorAnomalies={errorAnomalySummary ? {
                total: errorAnomalySummary.total_anomalies,
                trend: errorAnomalySummary.trends?.trend || 'stable'
              } : undefined}
              // NEW: Categorized error props (from /error-stats endpoint - NO LIMIT, accurate counts)
              criticalErrors={errorStats?.total_critical}
              warningErrors={errorStats?.total_warnings}
              criticalByType={errorStats?.critical_by_type}
              warningsByType={errorStats?.warnings_by_type}
              errorHealthStatus={errorStats?.health_status}
              errorHealthMessage={errorStats?.health_message}
              criticalRate={errorStats?.critical_rate_percent}
              cpuUtilization={(workloadStats as any)?.avg_cpu_utilization || 0}
              memoryUtilization={(workloadStats as any)?.avg_memory_utilization || 0}
              networkUtilization={(commStats as any)?.network_utilization || 0}
              loading={eventsLoading || commLoading || workloadsLoading}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card 
            title={<Space><FireOutlined style={{ color: '#d4a844' }} /><span>AI Insights</span></Space>}
            bordered={false}
            style={{ height: '100%' }}
          >
            <AIInsightCards
              data={{
                totalEvents: eventStats?.total_events,
                eventCounts: eventStats?.event_counts,
                totalCommunications: commStats?.total_communications,
                totalErrors: commStats?.total_errors,
                totalRetransmits: commStats?.total_retransmits,
                avgLatencyMs: (commStats as any)?.avg_latency_ms,
                activeWorkloads: (() => {
                  const apiActive = workloadStats?.active_workloads;
                  const apiTotal = workloadStats?.total_workloads;
                  const workloadCount = workloads.filter((w: Workload) => 
                    w.status === 'Running' || w.status === 'Active' || w.status === 'running' || w.status === 'active' ||
                    (w.is_active !== false && (!w.status || w.status === 'Unknown' || w.status === 'unknown'))
                  ).length;
                  if (apiActive && apiTotal && apiActive <= apiTotal) return apiActive;
                  return workloadCount || apiActive || 0;
                })(),
                totalWorkloads: workloadStats?.total_workloads || workloads.length,
                failedPods: workloads.filter((w: Workload) => w.status === 'Failed' || w.status === 'CrashLoopBackOff' || w.status === 'failed').length,
                securityEvents: securityData?.events?.length,
                deniedEvents: securityData?.events?.filter(e => e.verdict === 'denied').length,
                criticalCapabilities: securityData?.events?.filter(e => 
                  e.capability && ['CAP_SYS_ADMIN', 'CAP_SYS_MODULE', 'CAP_SYS_RAWIO'].includes(e.capability)
                ).length,
                totalChanges: changesData?.stats?.total_changes,
                criticalChanges: changesData?.stats?.by_risk?.critical,
                highRiskChanges: changesData?.stats?.by_risk?.high,
                oomEvents: oomData?.total,
                // Historical comparison for trend analysis
                // Simulated baseline - in production this would come from API with time range
                previousPeriod: {
                  totalEvents: eventStats?.total_events ? Math.round(eventStats.total_events * 0.85) : undefined,
                  totalCommunications: commStats?.total_communications ? Math.round(commStats.total_communications * 0.9) : undefined,
                  totalErrors: commStats?.total_errors ? Math.round(commStats.total_errors * 0.7) : undefined,
                  securityEvents: securityData?.events?.length ? Math.round(securityData.events.length * 0.95) : undefined,
                },
              }}
              loading={isLoading}
              maxInsights={5}
              showTechnicalDetails={true}
            />
          </Card>
        </Col>
      </Row>

      {/* Quick Insights */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <InsightCard
            icon={<ClusterOutlined />}
            title="Cluster Status"
            value={currentCluster?.status === 'active' ? 'Healthy' : 'Unknown'}
            severity={currentCluster?.status === 'active' ? 'success' : 'warning'}
            description={currentCluster?.name || 'No cluster selected'}
            linkTo="/management/clusters"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <InsightCard
            icon={<FireOutlined />}
            title="Running Analyses"
            value={analysisStats.running}
            severity={analysisStats.running > 0 ? 'info' : 'success'}
            description={`${analysisStats.total} total analyses`}
            linkTo="/analyses"
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <InsightCard
            icon={<SwapOutlined />}
            title="Recent Changes"
            value={changesData?.stats?.total_changes || 0}
            severity={(changesData?.stats?.by_risk?.critical || 0) > 0 ? 'error' : 
                     (changesData?.stats?.by_risk?.high || 0) > 0 ? 'warning' : 'success'}
            description={`${changesData?.stats?.by_risk?.critical || 0} critical`}
            onClick={() => {
              const params = new URLSearchParams();
              if (analysisId) params.set('analysisId', analysisId.toString());
              if (clusterId) params.set('clusterId', clusterId.toString());
              const queryString = params.toString();
              navigate(`/impact/change-detection${queryString ? `?${queryString}` : ''}`);
            }}
          />
        </Col>
        <Col xs={24} sm={12} md={6}>
          <InsightCard
            icon={<WarningOutlined />}
            title="OOM Events"
            value={oomData?.total || 0}
            severity={(oomData?.total || 0) > 0 ? 'error' : 'success'}
            description={(oomData?.total || 0) > 0 ? 'Memory issues detected' : 'No memory issues'}
            onClick={() => {
              const params = new URLSearchParams();
              if (analysisId) params.set('analysisId', analysisId.toString());
              if (clusterId) params.set('clusterId', clusterId.toString());
              const queryString = params.toString();
              navigate(`/observability/activity${queryString ? `?${queryString}` : ''}`);
            }}
          />
        </Col>
      </Row>

      {/* Traffic Heatmap */}
      <Card 
        title={<Space><ApiOutlined style={{ color: '#e6b05a' }} /><span>Top Traffic Flows</span></Space>}
        bordered={false}
        style={{ marginBottom: 24 }}
      >
        <TrafficHeatmap data={trafficData} title="" maxItems={10} />
      </Card>

      {/* Pod Health */}
      <Card 
        title={<Space><CloudServerOutlined style={{ color: '#4caf50' }} /><span>Pod Health Overview</span></Space>}
        bordered={false}
        style={{ marginBottom: 24 }}
      >
        <PodHealthGrid pods={podHealthData} title="" maxPods={100} />
      </Card>

      {/* Event Distribution & Recent Changes */}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card 
            title={<Space><ThunderboltOutlined style={{ color: '#d4a844' }} /><span>Event Distribution</span></Space>}
            bordered={false}
            style={{ height: '100%' }}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : eventStats?.event_counts && Object.keys(eventStats.event_counts).length > 0 ? (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {Object.entries(eventStats.event_counts)
                  .sort(([, a], [, b]) => (b as number) - (a as number))
                  .slice(0, 6)
                  .map(([type, count]) => {
                    const total = eventStats.total_events || 1;
                    const percent = ((count as number) / total * 100);
                    const colors: Record<string, string> = {
                      network_flow: '#0891b2',
                      dns_query: '#4caf50',
                      process_event: '#7c8eb5',
                      security_event: '#e05252',
                      oom_event: '#f76e6e',
                      bind_event: '#22a6a6',
                      sni_event: '#69b1ff',
                      file_event: '#a67c9e',
                    };
                    return (
                      <div key={type}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <Space>
                            <div style={{
                              width: 8,
                              height: 8,
                              borderRadius: 2,
                              background: colors[type] || '#8c8c8c',
                            }} />
                            <Text style={{ fontSize: 12 }}>
                              {type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                            </Text>
                          </Space>
                          <Text style={{ fontSize: 12 }}>
                            {(count as number).toLocaleString()} ({percent.toFixed(1)}%)
                          </Text>
                        </div>
                        <Progress 
                          percent={percent} 
                          showInfo={false} 
                          strokeColor={colors[type] || '#8c8c8c'}
                          size="small"
                        />
                      </div>
                    );
                  })}
              </Space>
            ) : (
              <Empty description="No events recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card 
            title={<Space><SwapOutlined style={{ color: '#e57373' }} /><span>Recent Changes</span></Space>}
            bordered={false}
            style={{ height: '100%' }}
          >
            {changesLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : changesData?.changes && changesData.changes.length > 0 ? (
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                {changesData.changes.slice(0, 5).map((change: any, index: number) => {
                  const riskColors: Record<string, string> = {
                    critical: '#cf1322',
                    high: '#e05252',
                    medium: '#d4a844',
                    low: '#4caf50',
                  };
                  
                  return (
                    <div
                      key={change.id || index}
                      style={{
                        padding: '8px 12px',
                        background: token.colorBgLayout,
                        borderRadius: 8,
                        borderLeft: `3px solid ${riskColors[change.risk] || '#8c8c8c'}`,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space>
                          <Tag color={riskColors[change.risk]} style={{ fontSize: 10, margin: 0 }}>
                            {change.risk?.toUpperCase()}
                          </Tag>
                          <Text strong style={{ fontSize: 12 }}>{change.target}</Text>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 10, color: textMuted }}>
                          {dayjs(change.timestamp).format('MM-DD HH:mm')}
                        </Text>
                      </div>
                      <Tooltip title={change.details}>
                        <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                          {change.details}
                        </Text>
                      </Tooltip>
                    </div>
                  );
                })}
              </Space>
            ) : (
              <Empty description="No recent changes" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default OverviewTab;
