/**
 * Golden Signals Component
 * Displays the 4 Golden Signals of SRE: Latency, Traffic, Errors, Saturation
 * Based on Google SRE best practices
 */

import React, { useMemo } from 'react';
import { Card, Row, Col, Statistic, Progress, Typography, Space, Tag, Tooltip, theme, Empty } from 'antd';
import {
  ClockCircleOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  DashboardOutlined,
  RiseOutlined,
  FallOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  AlertOutlined
} from '@ant-design/icons';
import { useTheme } from '../../../contexts/ThemeContext';

const { Text } = Typography;
const { useToken } = theme;

interface GoldenSignalsProps {
  // Latency metrics
  avgLatencyMs?: number;
  p50LatencyMs?: number;
  p95LatencyMs?: number;
  p99LatencyMs?: number;
  latencyTrend?: 'up' | 'down' | 'stable';
  
  // Traffic metrics
  requestsPerSecond?: number;
  totalRequests?: number;
  trafficTrend?: 'up' | 'down' | 'stable';
  
  // Error metrics (legacy - backward compatible)
  errorRate?: number;
  totalErrors?: number;
  errorsByType?: Record<string, number>;
  errorTrend?: 'up' | 'down' | 'stable';
  // Error anomaly info from Change Detection
  errorAnomalies?: {
    total: number;
    trend: 'increasing' | 'decreasing' | 'stable';
  };
  
  // NEW: Categorized error metrics
  criticalErrors?: number;
  warningErrors?: number;
  criticalByType?: Record<string, number>;
  warningsByType?: Record<string, number>;
  errorHealthStatus?: 'healthy' | 'good' | 'warning' | 'degraded' | 'critical';
  errorHealthMessage?: string;
  criticalRate?: number;  // Critical error rate percentage
  
  // Saturation metrics
  cpuUtilization?: number;
  memoryUtilization?: number;
  networkUtilization?: number;
  saturationTrend?: 'up' | 'down' | 'stable';
  
  // General
  loading?: boolean;
  compact?: boolean;
}

const GoldenSignals: React.FC<GoldenSignalsProps> = ({
  avgLatencyMs = 0,
  p50LatencyMs,
  p95LatencyMs,
  p99LatencyMs,
  latencyTrend,
  requestsPerSecond = 0,
  totalRequests = 0,
  trafficTrend,
  errorRate = 0,
  totalErrors = 0,
  errorsByType = {},
  errorTrend,
  errorAnomalies,
  // New categorized error props
  criticalErrors,
  warningErrors,
  criticalByType,
  warningsByType,
  errorHealthStatus,
  errorHealthMessage,
  criticalRate,
  cpuUtilization = 0,
  memoryUtilization = 0,
  networkUtilization = 0,
  saturationTrend,
  loading = false,
  compact = false,
}) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  
  // Use new categorized errors if available, otherwise fall back to legacy
  const hasCategorizedErrors = criticalErrors !== undefined || warningErrors !== undefined;
  const displayCritical = criticalErrors ?? 0;
  const displayWarnings = warningErrors ?? 0;
  const displayCriticalByType = criticalByType ?? {};
  const displayWarningsByType = warningsByType ?? {};

  // Calculate health status based on thresholds
  const getLatencyHealth = useMemo(() => {
    if (avgLatencyMs < 100) return { status: 'healthy', color: '#4caf50', label: 'Excellent' };
    if (avgLatencyMs < 300) return { status: 'good', color: '#4caf50', label: 'Good' };
    if (avgLatencyMs < 500) return { status: 'warning', color: '#b89b5d', label: 'Acceptable' };
    if (avgLatencyMs < 1000) return { status: 'degraded', color: '#b89b5d', label: 'Degraded' };
    return { status: 'critical', color: '#c75450', label: 'Critical' };
  }, [avgLatencyMs]);

  const getErrorHealth = useMemo(() => {
    // If we have the new errorHealthStatus, use it directly - Flowfish theme colors
    if (errorHealthStatus) {
      const statusMap: Record<string, { status: string; color: string; label: string }> = {
        healthy: { status: 'healthy', color: '#10b981', label: 'Healthy' },
        good: { status: 'good', color: '#10b981', label: 'Good' },
        warning: { status: 'warning', color: '#f59e0b', label: 'Warning' },
        degraded: { status: 'degraded', color: '#f59e0b', label: 'Degraded' },
        critical: { status: 'critical', color: '#ef4444', label: 'Critical' },
      };
      return statusMap[errorHealthStatus] || statusMap.healthy;
    }
    
    // If we have categorized errors, base health on critical error rate
    if (hasCategorizedErrors && criticalRate !== undefined) {
      if (criticalRate < 0.1) return { status: 'healthy', color: '#10b981', label: 'Healthy' };
      if (criticalRate < 0.5) return { status: 'good', color: '#10b981', label: 'Good' };
      if (criticalRate < 1) return { status: 'warning', color: '#f59e0b', label: 'Warning' };
      if (criticalRate < 5) return { status: 'degraded', color: '#f59e0b', label: 'Degraded' };
      return { status: 'critical', color: '#ef4444', label: 'Critical' };
    }
    
    // Fallback to legacy error rate calculation
    if (errorRate < 0.1) return { status: 'healthy', color: '#10b981', label: 'Healthy' };
    if (errorRate < 1) return { status: 'good', color: '#10b981', label: 'Good' };
    if (errorRate < 5) return { status: 'warning', color: '#f59e0b', label: 'Elevated' };
    if (errorRate < 10) return { status: 'degraded', color: '#f59e0b', label: 'High' };
    return { status: 'critical', color: '#ef4444', label: 'Critical' };
  }, [errorRate, errorHealthStatus, hasCategorizedErrors, criticalRate]);

  const getSaturationHealth = useMemo(() => {
    const maxUtil = Math.max(cpuUtilization, memoryUtilization, networkUtilization);
    if (maxUtil < 50) return { status: 'healthy', color: '#4caf50', label: 'Low' };
    if (maxUtil < 70) return { status: 'good', color: '#4caf50', label: 'Normal' };
    if (maxUtil < 85) return { status: 'warning', color: '#b89b5d', label: 'Elevated' };
    if (maxUtil < 95) return { status: 'degraded', color: '#b89b5d', label: 'High' };
    return { status: 'critical', color: '#c75450', label: 'Critical' };
  }, [cpuUtilization, memoryUtilization, networkUtilization]);

  const getTrendIcon = (trend?: 'up' | 'down' | 'stable') => {
    if (!trend) return null;
    if (trend === 'up') return <RiseOutlined style={{ color: '#4caf50' }} />;
    if (trend === 'down') return <FallOutlined style={{ color: '#c75450' }} />;
    return <span style={{ color: '#8c8c8c' }}>—</span>;
  };

  const formatLatency = (ms: number) => {
    if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`;
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  if (!totalRequests && !avgLatencyMs && !errorRate && !cpuUtilization) {
    return (
      <Card
        title={
          <Space>
            <DashboardOutlined style={{ color: token.colorPrimary }} />
            <span>Golden Signals</span>
          </Space>
        }
        bordered={false}
      >
        <Empty 
          description="No metrics data available. Start an analysis to collect golden signals."
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  const SignalCard: React.FC<{
    title: React.ReactNode;
    icon: React.ReactNode;
    color: string;
    mainValue: string | number;
    mainSuffix?: string;
    health: { status: string; color: string; label: string };
    trend?: 'up' | 'down' | 'stable';
    details?: React.ReactNode;
  }> = ({ title, icon, color, mainValue, mainSuffix, health, trend, details }) => (
    <Card
      size="small"
      bordered={false}
      style={{
        background: `linear-gradient(135deg, ${color}10 0%, ${token.colorBgContainer} 100%)`,
        borderTop: `3px solid ${color}`,
        height: '100%',
      }}
    >
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Space style={{ minWidth: 0, overflow: 'hidden' }}>
            <span style={{ color, fontSize: 16, flexShrink: 0 }}>{icon}</span>
            <Text strong style={{ fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</Text>
          </Space>
          <Tag color={health.color} style={{ margin: 0, fontSize: 10, flexShrink: 0 }}>
            {health.label}
          </Tag>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
          <Text style={{ fontSize: 28, fontWeight: 700, color }}>{mainValue}</Text>
          {mainSuffix && <Text type="secondary" style={{ fontSize: 14 }}>{mainSuffix}</Text>}
          {trend && <span style={{ marginLeft: 8 }}>{getTrendIcon(trend)}</span>}
        </div>
        
        {details && (
          <div style={{ marginTop: 4 }}>
            {details}
          </div>
        )}
      </Space>
    </Card>
  );

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined style={{ color: token.colorPrimary }} />
          <span>Golden Signals</span>
          <Tooltip title="The 4 Golden Signals of SRE: Latency, Traffic, Errors, Saturation">
            <ExclamationCircleOutlined style={{ color: token.colorTextSecondary, fontSize: 12 }} />
          </Tooltip>
        </Space>
      }
      bordered={false}
      loading={loading}
    >
      <Row gutter={[16, 16]}>
        {/* Latency */}
        <Col xs={24} sm={12} lg={6}>
          <SignalCard
            title="Latency"
            icon={<ClockCircleOutlined />}
            color="#0891b2"
            mainValue={formatLatency(avgLatencyMs)}
            health={getLatencyHealth}
            trend={latencyTrend}
            details={
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                {p50LatencyMs !== undefined && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>p50</Text>
                    <Text style={{ fontSize: 11 }}>{formatLatency(p50LatencyMs)}</Text>
                  </div>
                )}
                {p95LatencyMs !== undefined && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>p95</Text>
                    <Text style={{ fontSize: 11 }}>{formatLatency(p95LatencyMs)}</Text>
                  </div>
                )}
                {p99LatencyMs !== undefined && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>p99</Text>
                    <Text style={{ fontSize: 11, color: p99LatencyMs > 1000 ? '#c75450' : undefined }}>
                      {formatLatency(p99LatencyMs)}
                    </Text>
                  </div>
                )}
              </Space>
            }
          />
        </Col>

        {/* Traffic */}
        <Col xs={24} sm={12} lg={6}>
          <SignalCard
            title="Traffic"
            icon={<ThunderboltOutlined />}
            color="#4caf50"
            mainValue={requestsPerSecond.toFixed(1)}
            mainSuffix="req/s"
            health={{ 
              status: 'info', 
              color: '#0891b2', 
              label: requestsPerSecond > 100 ? 'High' : requestsPerSecond > 10 ? 'Normal' : 'Low' 
            }}
            trend={trafficTrend}
            details={
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="secondary" style={{ fontSize: 11 }}>Total Requests</Text>
                <Text style={{ fontSize: 11 }}>{formatNumber(totalRequests)}</Text>
              </div>
            }
          />
        </Col>

        {/* Errors - with Critical/Warning split */}
        <Col xs={24} sm={12} lg={6}>
          <Tooltip
            title={
              <div style={{ minWidth: 220, fontFamily: 'inherit' }}>
                {/* Header with health status */}
                <div style={{ 
                  fontWeight: 600, 
                  marginBottom: 10, 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'space-between',
                  paddingBottom: 8,
                  borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`
                }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                    {getErrorHealth.status === 'healthy' || getErrorHealth.status === 'good' ? (
                      <CheckCircleOutlined style={{ color: '#10b981' }} />
                    ) : getErrorHealth.status === 'warning' || getErrorHealth.status === 'degraded' ? (
                      <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />
                    ) : (
                      <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
                    )}
                    Network Health
                  </span>
                  <span style={{ 
                    fontSize: 11, 
                    padding: '2px 8px', 
                    borderRadius: 4,
                    fontWeight: 500,
                    background: getErrorHealth.status === 'healthy' || getErrorHealth.status === 'good' 
                      ? 'rgba(16, 185, 129, 0.15)' 
                      : getErrorHealth.status === 'warning' || getErrorHealth.status === 'degraded'
                        ? 'rgba(245, 158, 11, 0.15)' 
                        : 'rgba(239, 68, 68, 0.15)',
                    color: getErrorHealth.status === 'healthy' || getErrorHealth.status === 'good' 
                      ? '#10b981' 
                      : getErrorHealth.status === 'warning' || getErrorHealth.status === 'degraded'
                        ? '#f59e0b' 
                        : '#ef4444'
                  }}>
                    {getErrorHealth.label}
                  </span>
                </div>
                
                {/* Critical/Warning split display */}
                {hasCategorizedErrors ? (
                  <div style={{ display: 'flex', gap: 20, marginBottom: 10 }}>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444' }} />
                        Critical
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: displayCritical > 0 ? '#ef4444' : '#10b981' }}>
                        {formatNumber(displayCritical)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b' }} />
                        Warnings
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: displayWarnings > 0 ? '#f59e0b' : '#10b981' }}>
                        {formatNumber(displayWarnings)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div style={{ marginBottom: 8, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                    <div style={{ fontWeight: 'bold' }}>Network Errors: {formatNumber(totalErrors)}</div>
                    <div>Error Rate: {errorRate.toFixed(2)}%</div>
                  </div>
                )}
                
                {/* Critical errors breakdown */}
                {Object.keys(displayCriticalByType).length > 0 && (
                  <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(239, 68, 68, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                    <div style={{ marginBottom: 4, color: '#ef4444', fontWeight: 500, fontSize: 11 }}>Critical Errors</div>
                    {Object.entries(displayCriticalByType).map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(239, 68, 68, 0.9)' : 'rgba(239, 68, 68, 0.85)' }}>
                        <span>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 500 }}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Warnings breakdown */}
                {Object.keys(displayWarningsByType).length > 0 && (
                  <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(245, 158, 11, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                    <div style={{ marginBottom: 4, color: '#f59e0b', fontWeight: 500, fontSize: 11 }}>Retransmits (Normal)</div>
                    {Object.entries(displayWarningsByType).slice(0, 3).map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(245, 158, 11, 0.9)' : 'rgba(245, 158, 11, 0.85)' }}>
                        <span>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 500 }}>{count}</span>
                      </div>
                    ))}
                    {Object.keys(displayWarningsByType).length > 3 && (
                      <div style={{ color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', fontSize: 11 }}>
                        +{Object.keys(displayWarningsByType).length - 3} more types
                      </div>
                    )}
                  </div>
                )}
                
                {/* Legacy error type breakdown (fallback) */}
                {!hasCategorizedErrors && Object.keys(errorsByType).length > 0 && (
                  <div style={{ marginBottom: 4 }}>
                    <div style={{ marginBottom: 2, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)' }}>By Type:</div>
                    {Object.entries(errorsByType).map(([type, count]) => (
                      <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                        <span>{type.replace(/_/g, ' ')}</span>
                        <span style={{ fontWeight: 500 }}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Health message */}
                {errorHealthMessage && (
                  <div style={{ 
                    fontSize: 11, 
                    color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', 
                    borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`, 
                    paddingTop: 6,
                    marginTop: 4
                  }}>
                    {errorHealthMessage}
                  </div>
                )}
                
                {/* Error anomaly alert */}
                {errorAnomalies && errorAnomalies.total > 0 && (
                  <div style={{ marginTop: 8, padding: '6px 8px', background: 'rgba(102, 126, 234, 0.1)', borderRadius: 4, border: '1px solid rgba(102, 126, 234, 0.2)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#667eea', fontWeight: 500 }}>
                      <AlertOutlined style={{ fontSize: 12 }} />
                      {errorAnomalies.total} Anomal{errorAnomalies.total === 1 ? 'y' : 'ies'} Detected
                    </div>
                    <div style={{ fontSize: 11, marginTop: 2, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)' }}>Trend: {errorAnomalies.trend}</div>
                  </div>
                )}
                
                {/* No errors state */}
                {totalErrors === 0 && displayCritical === 0 && displayWarnings === 0 && (
                  <div style={{ color: '#10b981', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <CheckCircleOutlined style={{ fontSize: 14 }} />
                    No network errors detected
                  </div>
                )}
              </div>
            }
            mouseEnterDelay={0.3}
            color={isDark ? token.colorBgElevated : '#fff'}
            overlayInnerStyle={{ 
              padding: 12,
              boxShadow: isDark ? '0 6px 16px rgba(0,0,0,0.4)' : '0 6px 16px rgba(0,0,0,0.08)',
              borderRadius: 8
            }}
          >
            <div>
              <SignalCard
                title={
                  <Space>
                    {hasCategorizedErrors ? 'Network Health' : 'Errors'}
                    {errorAnomalies && errorAnomalies.total > 0 && (
                      <Tag style={{ fontSize: 9, marginLeft: 4, background: 'rgba(102, 126, 234, 0.15)', color: '#667eea', border: '1px solid rgba(102, 126, 234, 0.3)' }}>
                        {errorAnomalies.total} Anomal{errorAnomalies.total === 1 ? 'y' : 'ies'}
                      </Tag>
                    )}
                  </Space>
                }
                icon={<ExclamationCircleOutlined />}
                color={getErrorHealth.color}
                mainValue={hasCategorizedErrors 
                  ? `${formatNumber(displayCritical)}/${formatNumber(displayWarnings)}`
                  : errorRate.toFixed(2)
                }
                mainSuffix={hasCategorizedErrors ? '' : '%'}
                health={getErrorHealth}
                trend={errorTrend}
                details={
                  <Space direction="vertical" size={2} style={{ width: '100%' }}>
                    {hasCategorizedErrors ? (
                      <>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>Critical</Text>
                          <Text style={{ fontSize: 11, color: displayCritical > 0 ? '#ef4444' : '#10b981' }}>
                            {formatNumber(displayCritical)}
                          </Text>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>Warnings</Text>
                          <Text style={{ fontSize: 11, color: displayWarnings > 0 ? '#f59e0b' : '#10b981' }}>
                            {formatNumber(displayWarnings)}
                          </Text>
                        </div>
                      </>
                    ) : (
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>Total Errors</Text>
                        <Text style={{ fontSize: 11, color: totalErrors > 0 ? '#ef4444' : undefined }}>
                          {formatNumber(totalErrors)}
                        </Text>
                      </div>
                    )}
                    
                    {/* Critical error types */}
                    {Object.keys(displayCriticalByType).length > 0 && (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                        {Object.entries(displayCriticalByType).slice(0, 2).map(([type, count]) => (
                          <Tag key={type} style={{ fontSize: 9, margin: 0, background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                            {type.replace(/_/g, ' ')}: {count}
                          </Tag>
                        ))}
                        {Object.keys(displayCriticalByType).length > 2 && (
                          <Tag color="default" style={{ fontSize: 9, margin: 0 }}>
                            +{Object.keys(displayCriticalByType).length - 2}
                          </Tag>
                        )}
                      </div>
                    )}
                    
                    {/* Legacy error types (fallback) */}
                    {!hasCategorizedErrors && Object.keys(errorsByType).length > 0 && (
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                        {Object.entries(errorsByType).slice(0, 3).map(([type, count]) => (
                          <Tag key={type} color="red" style={{ fontSize: 9, margin: 0 }}>
                            {type.replace(/_/g, ' ')}: {count}
                          </Tag>
                        ))}
                        {Object.keys(errorsByType).length > 3 && (
                          <Tag color="default" style={{ fontSize: 9, margin: 0 }}>
                            +{Object.keys(errorsByType).length - 3} more
                          </Tag>
                        )}
                      </div>
                    )}
                    
                    {errorAnomalies && errorAnomalies.total > 0 && (
                      <div style={{ 
                        marginTop: 4, 
                        padding: '2px 6px', 
                        background: 'rgba(239, 68, 68, 0.1)', 
                        borderRadius: 4,
                        fontSize: 10 
                      }}>
                        <ExclamationCircleOutlined style={{ marginRight: 4, color: '#ef4444' }} />
                        {errorAnomalies.total} anomal{errorAnomalies.total === 1 ? 'y' : 'ies'} ({errorAnomalies.trend})
                      </div>
                    )}
                  </Space>
                }
              />
            </div>
          </Tooltip>
        </Col>

        {/* Saturation */}
        <Col xs={24} sm={12} lg={6}>
          <SignalCard
            title="Saturation"
            icon={<DashboardOutlined />}
            color={getSaturationHealth.color}
            mainValue={Math.max(cpuUtilization, memoryUtilization, networkUtilization).toFixed(0)}
            mainSuffix="%"
            health={getSaturationHealth}
            trend={saturationTrend}
            details={
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                    <Text type="secondary" style={{ fontSize: 10 }}>CPU</Text>
                    <Text style={{ fontSize: 10 }}>{cpuUtilization.toFixed(0)}%</Text>
                  </div>
                  <Progress 
                    percent={cpuUtilization} 
                    showInfo={false} 
                    size="small"
                    strokeColor={cpuUtilization > 85 ? '#c75450' : cpuUtilization > 70 ? '#b89b5d' : '#4caf50'}
                  />
                </div>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                    <Text type="secondary" style={{ fontSize: 10 }}>Memory</Text>
                    <Text style={{ fontSize: 10 }}>{memoryUtilization.toFixed(0)}%</Text>
                  </div>
                  <Progress 
                    percent={memoryUtilization} 
                    showInfo={false} 
                    size="small"
                    strokeColor={memoryUtilization > 85 ? '#c75450' : memoryUtilization > 70 ? '#b89b5d' : '#4caf50'}
                  />
                </div>
              </Space>
            }
          />
        </Col>
      </Row>
    </Card>
  );
};

export default GoldenSignals;
