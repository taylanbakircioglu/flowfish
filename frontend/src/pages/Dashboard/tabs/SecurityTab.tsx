import React, { useMemo, useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Row, 
  Col, 
  Card, 
  Typography, 
  Tag, 
  Space, 
  List,
  Progress,
  Empty,
  Spin,
  Alert,
  Tooltip,
  theme,
  Badge,
  Button
} from 'antd';
import { 
  SecurityScanOutlined,
  WarningOutlined,
  SafetyCertificateOutlined,
  ExclamationCircleOutlined,
  LockOutlined,
  BugOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SafetyOutlined,
  RightOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useGetSecurityEventsQuery, useGetOomEventsQuery, SecurityEvent, OomEvent } from '../../../store/api/eventsApi';
import { useTheme } from '../../../contexts/ThemeContext';

// Import shared security score utilities
import { 
  calculateSecurityScore, 
  capabilityRisk, 
  riskColors,
  getEventSeverity,
  SECURITY_EVENTS_LIMIT,
  OOM_EVENTS_LIMIT
} from '../../../utils/securityScore';

// Import custom components
import AnimatedStatCard from '../components/AnimatedStatCard';

dayjs.extend(relativeTime);

const { Text } = Typography;
const { useToken } = theme;

interface SecurityTabProps {
  clusterId?: number;
  analysisId?: number;
}

// Animated counter hook for smooth number transitions
const useAnimatedCounter = (end: number, duration: number = 1000, loading?: boolean) => {
  const [count, setCount] = useState(0);
  const countRef = useRef(0);
  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (loading) return;
    
    const startValue = countRef.current;
    const difference = end - startValue;
    
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) startTimeRef.current = timestamp;
      const progress = Math.min((timestamp - startTimeRef.current) / duration, 1);
      
      // Easing function for smooth animation
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      const currentValue = Math.round(startValue + difference * easeOutQuart);
      
      setCount(currentValue);
      countRef.current = currentValue;
      
      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };
    
    startTimeRef.current = null;
    requestAnimationFrame(animate);
  }, [end, duration, loading]);

  return count;
};

// Animated Security Score Gauge - Using Progress component with animated number
const SecurityScoreGauge: React.FC<{ score: number | null; status: string; loading?: boolean }> = ({ 
  score, 
  status, 
  loading 
}) => {
  const { token } = useToken();
  const animatedScore = useAnimatedCounter(score ?? 0, 1200, loading || score === null);

  const getColor = (s: number) => {
    if (s >= 80) return '#4caf50';
    if (s >= 60) return '#d4a844';
    return '#e05252';
  };

  if (loading) {
    return (
      <div style={{ width: 180, height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (score === null) {
    return (
      <div style={{ 
        width: 180, 
        height: 180, 
        display: 'flex', 
        flexDirection: 'column',
        alignItems: 'center', 
        justifyContent: 'center',
        color: token.colorTextSecondary,
      }}>
        <SafetyOutlined style={{ fontSize: 48, opacity: 0.3 }} />
        <Text type="secondary" style={{ marginTop: 8 }}>
          {status === 'no_data' ? 'No Data' : 'Select Analysis'}
        </Text>
      </div>
    );
  }

  const color = getColor(score);
  const displayScore = animatedScore;

  return (
    <div style={{ width: 180, height: 180, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <Progress
        type="dashboard"
        percent={displayScore}
        strokeColor={color}
        trailColor={token.colorBorderSecondary}
        strokeWidth={10}
        size={160}
        format={() => (
          <div style={{ textAlign: 'center' }}>
            <span style={{ 
              fontSize: 36, 
              fontWeight: 600, 
              color,
              fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
              letterSpacing: '-0.02em'
            }}>
              {displayScore}
            </span>
          </div>
        )}
      />
      <Text type="secondary" style={{ marginTop: -8, fontSize: 12 }}>Security Score</Text>
    </div>
  );
};

const SecurityTab: React.FC<SecurityTabProps> = ({ clusterId, analysisId }) => {
  const { token } = useToken();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const textMuted = isDark ? 'rgba(255,255,255,0.35)' : '#a0aec0';
  
  // API Queries - use shared constants for consistent limits across all pages
  const { data: securityData, isLoading: securityLoading } = useGetSecurityEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: SECURITY_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  const { data: oomData, isLoading: oomLoading } = useGetOomEventsQuery(
    { cluster_id: clusterId!, analysis_id: analysisId, limit: OOM_EVENTS_LIMIT },
    { skip: !clusterId || !analysisId }
  );

  // Process security events to extract capabilities
  const capabilities = useMemo(() => {
    if (!securityData?.events) return [];
    
    const capMap = new Map<string, {
      key: string;
      pod: string;
      namespace: string;
      capability: string;
      usageCount: number;
      lastSeen: string;
      risk: 'low' | 'medium' | 'high' | 'critical';
      allowed: number;
      denied: number;
    }>();

    securityData.events
      .filter((e: SecurityEvent) => e.security_type === 'capability')
      .forEach((event: SecurityEvent) => {
        const key = `${event.pod}-${event.capability}`;
        const existing = capMap.get(key);
        const capInfo = capabilityRisk[event.capability || ''] || { risk: 'medium', description: 'Unknown capability' };
        
        if (existing) {
          existing.usageCount++;
          if (event.timestamp > existing.lastSeen) {
            existing.lastSeen = event.timestamp;
          }
          if (event.verdict === 'allowed') existing.allowed++;
          else existing.denied++;
        } else {
          capMap.set(key, {
            key,
            pod: event.pod,
            namespace: event.namespace,
            capability: event.capability || 'UNKNOWN',
            usageCount: 1,
            lastSeen: event.timestamp,
            risk: capInfo.risk,
            allowed: event.verdict === 'allowed' ? 1 : 0,
            denied: event.verdict === 'denied' ? 1 : 0,
          });
        }
      });

    return Array.from(capMap.values()).sort((a, b) => {
      const riskOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      return riskOrder[a.risk] - riskOrder[b.risk];
    });
  }, [securityData?.events]);

  // Process violations with severity using shared utility
  const processedViolations = useMemo(() => {
    if (!securityData?.events) return [];
    return securityData.events
      .filter((e: SecurityEvent) => e.verdict === 'denied')
      .map((event: SecurityEvent) => ({
        ...event,
        severity: getEventSeverity(event.capability),
      }));
  }, [securityData?.events]);

  // Violations for display (sliced to 10)
  const violations = useMemo(() => {
    return processedViolations.slice(0, 10);
  }, [processedViolations]);

  // OOM events
  const oomEvents = useMemo(() => {
    return (oomData?.events || []).slice(0, 10);
  }, [oomData?.events]);

  // Security Score calculation using shared utility function
  const securityScoreData = useMemo(() => {
    // If no analysis or cluster selected, return null
    if (!analysisId || !clusterId) {
      return { score: null, status: 'no_selection' as const };
    }
    
    // If loading, return loading state
    if (securityLoading || oomLoading) {
      return { score: null, status: 'loading' as const };
    }
    
    // Use shared calculation function - single source of truth
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

  const isLoading = securityLoading || oomLoading;

  // Stats - use processedViolations for accurate count (consistent with SecurityCenter)
  const stats = useMemo(() => ({
    totalChecks: securityData?.total || 0,
    violations: processedViolations.length,
    oomEvents: oomData?.total || 0,
    criticalCapabilities: capabilities.filter(c => c.risk === 'critical').length,
    highRiskCapabilities: capabilities.filter(c => c.risk === 'high').length,
  }), [securityData, processedViolations, oomData, capabilities]);

  if (!clusterId) {
    return <Empty description="Select a cluster to view security data" />;
  }

  return (
    <div>
      {/* Security Score & Stats - Enhanced */}
      <Row gutter={[16, 16]}>
        {/* Animated Security Score */}
        <Col xs={24} sm={12} lg={6}>
          <Card 
            bordered={false} 
            style={{ 
              height: '100%', 
              textAlign: 'center',
              background: securityScore !== null && securityScore < 60 
                ? `linear-gradient(135deg, ${token.colorBgContainer} 0%, #e0525210 100%)`
                : token.colorBgContainer,
            }}
          >
            <SecurityScoreGauge 
              score={securityScore} 
              status={securityStatus} 
              loading={securityStatus === 'loading'}
            />
            <div style={{ marginTop: 8 }}>
              <Tag 
                color={
                  securityScore === null ? 'default' :
                  securityScore >= 80 ? 'success' : 
                  securityScore >= 60 ? 'warning' : 'error'
                }
              >
                {securityScore === null ? 'N/A' :
                 securityScore >= 80 ? 'Healthy' : 
                 securityScore >= 60 ? 'Needs Attention' : 'Critical'}
              </Tag>
            </div>
          </Card>
        </Col>

        {/* Capability Checks - Animated */}
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Capability Checks"
            value={stats.totalChecks}
            icon={<SafetyCertificateOutlined />}
            color="#0891b2"
            subtitle={`${capabilities.length} unique capabilities`}
            loading={isLoading}
          />
        </Col>

        {/* Violations - Animated */}
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="Security Violations"
            value={stats.violations}
            icon={<BugOutlined />}
            color={stats.violations > 0 ? '#e57373' : '#2eb8b8'}
            subtitle={stats.violations > 0 ? 'Requires attention' : 'All clear'}
            loading={isLoading}
            pulseEffect={stats.violations > 5}
          />
        </Col>

        {/* OOM Events - Animated */}
        <Col xs={24} sm={12} lg={6}>
          <AnimatedStatCard
            title="OOM Events"
            value={stats.oomEvents}
            icon={<WarningOutlined />}
            color={stats.oomEvents > 0 ? '#e6b05a' : '#8fa8b8'}
            subtitle={stats.oomEvents > 0 ? 'Memory pressure detected' : 'No memory issues'}
            loading={isLoading}
          />
        </Col>
      </Row>

      {/* Alerts */}
      {stats.criticalCapabilities > 0 && (
        <Alert
          message="Critical Capabilities Detected"
          description={`${stats.criticalCapabilities} pod(s) are using critical capabilities like CAP_SYS_ADMIN. Review immediately.`}
          type="error"
          showIcon
          style={{ marginTop: 16 }}
        />
      )}

      {/* Risk Distribution & Capabilities */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Risk Distribution - Enhanced */}
        <Col xs={24} lg={10}>
          <Card 
            title={
              <Space>
                <SecurityScanOutlined style={{ color: '#e05252' }} />
                <span>Risk Distribution</span>
              </Space>
            }
            bordered={false}
            style={{ height: '100%' }}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {['critical', 'high', 'medium', 'low'].map(risk => {
                  const count = capabilities.filter(c => c.risk === risk).length;
                  const total = capabilities.length || 1;
                  const percent = (count / total) * 100;
                  const riskColor = riskColors[risk as keyof typeof riskColors];
                  
                  return (
                    <div 
                      key={risk}
                      style={{
                        padding: '8px 12px',
                        background: count > 0 ? `${riskColor}10` : 'transparent',
                        borderRadius: 8,
                        borderLeft: `3px solid ${riskColor}`,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <Tag color={riskColor} style={{ margin: 0, textTransform: 'uppercase', fontSize: 10 }}>
                          {risk}
                        </Tag>
                        <Text strong style={{ fontSize: 16, color: count > 0 ? riskColor : undefined }}>
                          {count}
                        </Text>
                      </div>
                      <Progress 
                        percent={percent} 
                        showInfo={false}
                        strokeColor={riskColor}
                        size="small"
                        style={{ marginBottom: 0 }}
                      />
                    </div>
                  );
                })}
              </Space>
            )}
          </Card>
        </Col>

        {/* Top Risky Capabilities - Enhanced Cards */}
        <Col xs={24} lg={14}>
          <Card 
            title={
              <Space>
                <LockOutlined style={{ color: '#7c8eb5' }} />
                <span>Risky Capabilities</span>
              </Space>
            }
            bordered={false}
            extra={
              <Badge count={capabilities.filter(c => c.risk === 'critical' || c.risk === 'high').length} style={{ backgroundColor: '#e05252' }} />
            }
            bodyStyle={{ maxHeight: 350, overflow: 'auto' }}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : capabilities.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {capabilities.slice(0, 6).map((cap, index) => {
                  const riskColor = riskColors[cap.risk as keyof typeof riskColors];
                  return (
                    <div
                      key={cap.key}
                      style={{
                        padding: '10px 12px',
                        background: `linear-gradient(90deg, ${riskColor}10 0%, ${token.colorBgLayout} 100%)`,
                        borderRadius: 8,
                        borderLeft: `3px solid ${riskColor}`,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong style={{ fontSize: 12 }}>{cap.pod}</Text>
                          <br />
                          <Text type="secondary" style={{ fontSize: 10 }}>{cap.namespace}</Text>
                        </div>
                        <Tag color={riskColor} style={{ fontSize: 9, margin: 0 }}>
                          {cap.risk.toUpperCase()}
                        </Tag>
                      </div>
                      <div style={{ marginTop: 8 }}>
                        <Tooltip title={capabilityRisk[cap.capability]?.description || 'Unknown capability'}>
                          <Tag style={{ fontSize: 10, fontFamily: 'monospace' }}>{cap.capability}</Tag>
                        </Tooltip>
                      </div>
                      <div style={{ marginTop: 8, display: 'flex', gap: 12 }}>
                        <Space size={4}>
                          <CheckCircleOutlined style={{ color: '#4caf50', fontSize: 11 }} />
                          <Text style={{ fontSize: 11 }}>{cap.allowed}</Text>
                        </Space>
                        <Space size={4}>
                          <CloseCircleOutlined style={{ color: '#e05252', fontSize: 11 }} />
                          <Text style={{ fontSize: 11 }}>{cap.denied}</Text>
                        </Space>
                        <Text type="secondary" style={{ fontSize: 10, marginLeft: 'auto' }}>
                          {cap.usageCount} total
                        </Text>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty description="No capabilities detected" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Violations & OOM Events */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Recent Violations */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <ExclamationCircleOutlined style={{ color: '#e05252' }} />
                <span>Recent Violations</span>
                {violations.length > 0 && (
                  <Tag color="red">{violations.length}</Tag>
                )}
              </Space>
            }
            bordered={false}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : violations.length > 0 ? (
              <List
                dataSource={violations}
                size="small"
                renderItem={(event: SecurityEvent) => (
                  <List.Item>
                    <List.Item.Meta
                      avatar={<ExclamationCircleOutlined style={{ color: '#e05252' }} />}
                      title={
                        <Space>
                          <Text strong style={{ fontSize: 12 }}>{event.pod}</Text>
                          <Text code style={{ fontSize: 10 }}>{event.capability || event.syscall}</Text>
                        </Space>
                      }
                      description={
                        <Space>
                          <Tag style={{ fontSize: 10 }}>{event.namespace}</Tag>
                          <Text type="secondary" style={{ fontSize: 10, color: textMuted }}>
                            {dayjs(event.timestamp).format('MM-DD HH:mm')}
                          </Text>
                        </Space>
                      }
                    />
                    <Tag color="red" style={{ fontSize: 10 }}>BLOCKED</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty 
                description="No violations detected" 
                image={<SafetyCertificateOutlined style={{ fontSize: 48, color: '#4caf50' }} />}
              />
            )}
          </Card>
        </Col>

        {/* OOM Events */}
        <Col xs={24} lg={12}>
          <Card 
            title={
              <Space>
                <WarningOutlined style={{ color: '#f76e6e' }} />
                <span>OOM Events</span>
                {oomEvents.length > 0 && (
                  <Tag color="error">{oomEvents.length}</Tag>
                )}
              </Space>
            }
            bordered={false}
          >
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
            ) : oomEvents.length > 0 ? (
              <List
                dataSource={oomEvents}
                size="small"
                renderItem={(event: OomEvent) => {
                  const formatBytes = (bytes: number) => {
                    if (bytes === 0) return '0 B';
                    const k = 1024;
                    const sizes = ['B', 'Ki', 'Mi', 'Gi'];
                    const i = Math.floor(Math.log(bytes) / Math.log(k));
                    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
                  };
                  
                  return (
                    <List.Item>
                      <List.Item.Meta
                        avatar={<WarningOutlined style={{ color: '#f76e6e' }} />}
                        title={
                          <Space>
                            <Text strong style={{ fontSize: 12 }}>{event.pod}</Text>
                            <Text code style={{ fontSize: 10 }}>{event.comm}</Text>
                          </Space>
                        }
                        description={
                          <Space>
                            <Text type="secondary" style={{ fontSize: 10 }}>
                              Limit: {formatBytes(event.memory_limit)} | Used: {formatBytes(event.memory_usage)}
                            </Text>
                          </Space>
                        }
                      />
                      <Text type="secondary" style={{ fontSize: 10, color: textMuted }}>
                        {dayjs(event.timestamp).format('MM-DD HH:mm')}
                      </Text>
                    </List.Item>
                  );
                }}
              />
            ) : (
              <Empty 
                description="No OOM events" 
                image={<CheckCircleOutlined style={{ fontSize: 48, color: '#4caf50' }} />}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* Drill-down Link */}
      <div style={{ marginTop: 16, textAlign: 'center' }}>
        <Button 
          type="link" 
          onClick={() => {
            const params = new URLSearchParams();
            if (analysisId) params.set('analysisId', analysisId.toString());
            if (clusterId) params.set('clusterId', clusterId.toString());
            const queryString = params.toString();
            navigate(`/security/center${queryString ? `?${queryString}` : ''}`);
          }}
          icon={<RightOutlined />}
          iconPosition="end"
        >
          View Full Security Center
        </Button>
      </div>
    </div>
  );
};

export default SecurityTab;

