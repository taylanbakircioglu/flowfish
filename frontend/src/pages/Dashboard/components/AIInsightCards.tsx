import React, { useMemo, useState } from 'react';
import { Card, Space, Typography, Tag, Tooltip, Button, Badge, theme, Collapse, Progress, Divider } from 'antd';
import {
  BulbOutlined,
  RiseOutlined,
  FallOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ThunderboltOutlined,
  SecurityScanOutlined,
  ApiOutlined,
  ClockCircleOutlined,
  FireOutlined,
  ExclamationCircleOutlined,
  RocketOutlined,
  AlertOutlined,
  SafetyCertificateOutlined,
  LineChartOutlined,
  NodeIndexOutlined,
  AimOutlined,
  ExperimentOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  DownOutlined,
  LinkOutlined,
  InfoCircleOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { InsightEngine, SmartInsight, insightEngine } from './InsightEngine';

const { Text, Title, Paragraph } = Typography;
const { useToken } = theme;
const { Panel } = Collapse;

export interface InsightData {
  // Event stats
  totalEvents?: number;
  eventCounts?: Record<string, number>;
  // Communication stats
  totalCommunications?: number;
  totalErrors?: number;
  totalRetransmits?: number;
  avgLatencyMs?: number;
  // Workload stats
  activeWorkloads?: number;
  totalWorkloads?: number;
  failedPods?: number;
  // Security data
  securityEvents?: number;
  deniedEvents?: number;
  criticalCapabilities?: number;
  // Changes
  totalChanges?: number;
  criticalChanges?: number;
  highRiskChanges?: number;
  // OOM
  oomEvents?: number;
  // Historical comparison (optional)
  previousPeriod?: {
    totalEvents?: number;
    totalCommunications?: number;
    totalErrors?: number;
    securityEvents?: number;
  };
}

interface AIInsightCardsProps {
  data: InsightData;
  loading?: boolean;
  maxInsights?: number;
  showTechnicalDetails?: boolean;
  compact?: boolean;
}

// Insight type icon mapping
const getInsightIcon = (type: SmartInsight['type']) => {
  switch (type) {
    case 'anomaly': return <ExclamationCircleOutlined />;
    case 'trend': return <LineChartOutlined />;
    case 'correlation': return <NodeIndexOutlined />;
    case 'pattern': return <AimOutlined />;
    case 'prediction': return <ExperimentOutlined />;
    case 'root_cause': return <ToolOutlined />;
    case 'recommendation': return <BulbOutlined />;
    default: return <InfoCircleOutlined />;
  }
};

// Insight type label
const getInsightTypeLabel = (type: SmartInsight['type']) => {
  switch (type) {
    case 'anomaly': return 'Anomaly';
    case 'trend': return 'Trend';
    case 'correlation': return 'Correlation';
    case 'pattern': return 'Pattern';
    case 'prediction': return 'Prediction';
    case 'root_cause': return 'Root Cause';
    case 'recommendation': return 'Recommendation';
    default: return 'Insight';
  }
};

// Severity color mapping
const getSeverityColor = (severity: SmartInsight['severity'], token: any) => {
  switch (severity) {
    case 'critical': return '#cf1322';
    case 'high': return '#e05252';
    case 'medium': return '#d4a844';
    case 'low': return '#4caf50';
    case 'info': return token.colorPrimary;
    default: return token.colorTextSecondary;
  }
};

// Severity background
const getSeverityBackground = (severity: SmartInsight['severity'], token: any) => {
  const color = getSeverityColor(severity, token);
  return `linear-gradient(135deg, ${color}08 0%, ${token.colorBgContainer} 100%)`;
};

// Confidence indicator
const ConfidenceIndicator: React.FC<{ confidence: number }> = ({ confidence }) => {
  const { token } = useToken();
  const percent = Math.round(confidence * 100);
  
  let color = token.colorSuccess;
  if (percent < 50) color = token.colorWarning;
  if (percent < 30) color = token.colorError;

  return (
    <Tooltip title={`${percent}% confidence`}>
      <Progress
        type="circle"
        percent={percent}
        size={24}
        strokeColor={color}
        format={() => ''}
        strokeWidth={12}
      />
    </Tooltip>
  );
};

// Individual insight card component
const InsightCard: React.FC<{
  insight: SmartInsight;
  expanded?: boolean;
  onToggle?: () => void;
  showTechnicalDetails?: boolean;
}> = ({ insight, expanded, onToggle, showTechnicalDetails }) => {
  const { token } = useToken();
  const color = getSeverityColor(insight.severity, token);

  return (
    <Card
      size="small"
      bordered={false}
      style={{
        background: getSeverityBackground(insight.severity, token),
        borderLeft: `3px solid ${color}`,
        cursor: insight.suggestedActions.length > 0 || insight.technicalDetail ? 'pointer' : 'default',
        marginBottom: 12,
        transition: 'all 0.2s ease',
      }}
      bodyStyle={{ padding: '12px 16px' }}
      onClick={onToggle}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
        <Space align="start">
          <span style={{ color, fontSize: 18 }}>
            {getInsightIcon(insight.type)}
          </span>
          <div>
            <Text strong style={{ fontSize: 13, display: 'block', lineHeight: 1.3 }}>
              {insight.title}
            </Text>
            <Space size={4} style={{ marginTop: 4 }}>
              <Tag 
                color={color} 
                style={{ fontSize: 10, padding: '0 4px', margin: 0, lineHeight: '16px' }}
              >
                {insight.severity.toUpperCase()}
              </Tag>
              <Tag 
                style={{ 
                  fontSize: 10, 
                  padding: '0 4px', 
                  margin: 0, 
                  lineHeight: '16px',
                  background: token.colorBgLayout,
                  border: `1px solid ${token.colorBorderSecondary}`,
                }}
              >
                {getInsightTypeLabel(insight.type)}
              </Tag>
            </Space>
          </div>
        </Space>
        <Space size={8}>
          {insight.value && (
            <Tag 
              color={color} 
              style={{ fontSize: 12, fontWeight: 600, margin: 0 }}
            >
              {insight.value}
            </Tag>
          )}
          <ConfidenceIndicator confidence={insight.confidence} />
          {(insight.suggestedActions.length > 0 || insight.technicalDetail) && (
            <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>
              {expanded ? <DownOutlined /> : <RightOutlined />}
            </span>
          )}
        </Space>
      </div>

      {/* Description */}
      <Paragraph 
        style={{ 
          fontSize: 12, 
          color: token.colorTextSecondary, 
          margin: 0,
          lineHeight: 1.5,
        }}
        ellipsis={!expanded ? { rows: 2 } : false}
      >
        {insight.description}
      </Paragraph>

      {/* Trend indicator */}
      {insight.trend && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Tag 
            color={insight.trend.direction === 'increasing' ? 'red' : 
                   insight.trend.direction === 'decreasing' ? 'green' : 
                   insight.trend.direction === 'volatile' ? 'orange' : 'default'}
            style={{ fontSize: 10, margin: 0 }}
          >
            {insight.trend.direction === 'increasing' && <RiseOutlined style={{ marginRight: 4 }} />}
            {insight.trend.direction === 'decreasing' && <FallOutlined style={{ marginRight: 4 }} />}
            {insight.trend.direction === 'volatile' && <ThunderboltOutlined style={{ marginRight: 4 }} />}
            {insight.trend.direction.charAt(0).toUpperCase() + insight.trend.direction.slice(1)}
          </Tag>
          {insight.trend.prediction.confidence > 0.5 && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              Predicted in 1h: {typeof insight.trend.prediction.nextHour === 'number' 
                ? insight.trend.prediction.nextHour.toFixed(1) 
                : insight.trend.prediction.nextHour}
            </Text>
          )}
        </div>
      )}

      {/* Expanded content */}
      {expanded && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: `1px solid ${token.colorBorderSecondary}` }}>
          {/* Technical details */}
          {showTechnicalDetails && insight.technicalDetail && (
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>
                {insight.technicalDetail}
              </Text>
            </div>
          )}

          {/* Root cause candidates */}
          {insight.rootCause && insight.rootCause.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                Potential Causes:
              </Text>
              {insight.rootCause.slice(0, 3).map((cause, idx) => (
                <div 
                  key={idx}
                  style={{ 
                    padding: '6px 8px', 
                    background: token.colorBgLayout, 
                    borderRadius: 4,
                    marginBottom: 4,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text style={{ fontSize: 11 }}>{cause.metric}</Text>
                    <Tag style={{ fontSize: 10, margin: 0 }}>
                      {(cause.probability * 100).toFixed(0)}% likely
                    </Tag>
                  </div>
                  {cause.evidence.length > 0 && (
                    <Text type="secondary" style={{ fontSize: 10 }}>
                      {cause.evidence[0]}
                    </Text>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Correlation details */}
          {insight.correlation && (
            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                Correlation Details:
              </Text>
              <div style={{ padding: '6px 8px', background: token.colorBgLayout, borderRadius: 4 }}>
                <Space size={12}>
                  <Text style={{ fontSize: 11 }}>
                    <LinkOutlined style={{ marginRight: 4 }} />
                    r = {insight.correlation.coefficient.toFixed(2)}
                  </Text>
                  <Tag style={{ fontSize: 10, margin: 0 }}>
                    {insight.correlation.strength}
                  </Tag>
                  {insight.correlation.lagMinutes > 0 && (
                    <Text type="secondary" style={{ fontSize: 10 }}>
                      ~{insight.correlation.lagMinutes}min lag
                    </Text>
                  )}
                </Space>
              </div>
            </div>
          )}

          {/* Pattern details */}
          {insight.pattern && (
            <div style={{ marginBottom: 12 }}>
              <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                Pattern Details:
              </Text>
              <div style={{ padding: '6px 8px', background: token.colorBgLayout, borderRadius: 4 }}>
                <Space size={12}>
                  <Tag style={{ fontSize: 10, margin: 0 }}>
                    {insight.pattern.type.replace('_', ' ')}
                  </Tag>
                  <Text style={{ fontSize: 11 }}>
                    Magnitude: {insight.pattern.magnitude.toFixed(1)}σ
                  </Text>
                  {insight.pattern.isRecurring && (
                    <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>
                      Recurring {insight.pattern.recurringPattern || ''}
                    </Tag>
                  )}
                </Space>
              </div>
            </div>
          )}

          {/* Suggested actions */}
          {insight.suggestedActions.length > 0 && (
            <div>
              <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                Suggested Actions:
              </Text>
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {insight.suggestedActions.map((action, idx) => (
                  <li key={idx} style={{ fontSize: 11, color: token.colorTextSecondary, marginBottom: 2 }}>
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tags */}
          {insight.tags.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <Space size={4} wrap>
                {insight.tags.map((tag, idx) => (
                  <Tag 
                    key={idx} 
                    style={{ 
                      fontSize: 9, 
                      padding: '0 4px', 
                      margin: 0, 
                      background: 'transparent',
                      border: `1px dashed ${token.colorBorderSecondary}`,
                    }}
                  >
                    #{tag}
                  </Tag>
                ))}
              </Space>
            </div>
          )}
        </div>
      )}
    </Card>
  );
};

// Summary stats component
const InsightsSummary: React.FC<{ insights: SmartInsight[] }> = ({ insights }) => {
  const { token } = useToken();
  
  const stats = useMemo(() => {
    const critical = insights.filter(i => i.severity === 'critical').length;
    const high = insights.filter(i => i.severity === 'high').length;
    const medium = insights.filter(i => i.severity === 'medium').length;
    const anomalies = insights.filter(i => i.type === 'anomaly').length;
    const trends = insights.filter(i => i.type === 'trend').length;
    const predictions = insights.filter(i => i.type === 'prediction').length;
    
    return { critical, high, medium, anomalies, trends, predictions };
  }, [insights]);

  if (stats.critical === 0 && stats.high === 0 && stats.medium === 0) {
    return null;
  }

  return (
    <div style={{ 
      display: 'flex', 
      gap: 8, 
      marginBottom: 12,
      padding: '8px 12px',
      background: token.colorBgLayout,
      borderRadius: 8,
    }}>
      {stats.critical > 0 && (
        <Tooltip title="Critical issues requiring immediate attention">
          <Tag color="#cf1322" style={{ margin: 0 }}>
            {stats.critical} Critical
          </Tag>
        </Tooltip>
      )}
      {stats.high > 0 && (
        <Tooltip title="High priority issues">
          <Tag color="#e05252" style={{ margin: 0 }}>
            {stats.high} High
          </Tag>
        </Tooltip>
      )}
      {stats.medium > 0 && (
        <Tooltip title="Medium priority issues">
          <Tag color="#d4a844" style={{ margin: 0 }}>
            {stats.medium} Medium
          </Tag>
        </Tooltip>
      )}
      <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        {stats.anomalies > 0 && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            <ExclamationCircleOutlined style={{ marginRight: 4 }} />
            {stats.anomalies} anomalies
          </Text>
        )}
        {stats.trends > 0 && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            <LineChartOutlined style={{ marginRight: 4 }} />
            {stats.trends} trends
          </Text>
        )}
        {stats.predictions > 0 && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            <ExperimentOutlined style={{ marginRight: 4 }} />
            {stats.predictions} predictions
          </Text>
        )}
      </div>
    </div>
  );
};

// Main component
const AIInsightCards: React.FC<AIInsightCardsProps> = ({ 
  data, 
  loading,
  maxInsights = 6,
  showTechnicalDetails = false,
  compact = false,
}) => {
  const { token } = useToken();
  const [expandedInsight, setExpandedInsight] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  // Generate insights using the smart engine
  const insights = useMemo<SmartInsight[]>(() => {
    return insightEngine.analyzeSimple(data);
  }, [data]);

  // Visible insights
  const visibleInsights = showAll ? insights : insights.slice(0, maxInsights);
  const hasMore = insights.length > maxInsights;

  if (loading) {
    return (
      <Card bordered={false} style={{ height: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
          <Space direction="vertical" align="center">
            <ExperimentOutlined style={{ fontSize: 32, color: token.colorPrimary }} spin />
            <Text type="secondary">Analyzing data patterns...</Text>
          </Space>
        </div>
      </Card>
    );
  }

  if (compact) {
    // Compact mode: just show badges
    const criticalCount = insights.filter(i => i.severity === 'critical' || i.severity === 'high').length;
    const warningCount = insights.filter(i => i.severity === 'medium').length;
    
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <BulbOutlined style={{ color: '#d4a844', fontSize: 16 }} />
        <Text strong style={{ fontSize: 13 }}>AI Insights</Text>
        {criticalCount > 0 && (
          <Badge count={criticalCount} style={{ backgroundColor: '#e05252' }} />
        )}
        {warningCount > 0 && (
          <Badge count={warningCount} style={{ backgroundColor: '#d4a844' }} />
        )}
        {criticalCount === 0 && warningCount === 0 && (
          <Tag color="green" style={{ margin: 0 }}>
            <CheckCircleOutlined style={{ marginRight: 4 }} />
            Healthy
          </Tag>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <BulbOutlined style={{ color: '#d4a844', fontSize: 18 }} />
        <Text strong style={{ fontSize: 14 }}>AI Insights</Text>
        <Tooltip title="Insights are generated using statistical analysis, anomaly detection, and pattern recognition">
          <QuestionCircleOutlined style={{ color: token.colorTextTertiary, fontSize: 12 }} />
        </Tooltip>
        <Badge 
          count={insights.filter(i => i.severity === 'critical' || i.severity === 'high').length} 
          style={{ backgroundColor: '#e05252' }}
        />
      </div>

      {/* Summary */}
      <InsightsSummary insights={insights} />

      {/* Insight cards */}
      {visibleInsights.map((insight) => (
        <InsightCard
          key={insight.id}
          insight={insight}
          expanded={expandedInsight === insight.id}
          onToggle={() => setExpandedInsight(
            expandedInsight === insight.id ? null : insight.id
          )}
          showTechnicalDetails={showTechnicalDetails}
        />
      ))}

      {/* Show more/less */}
      {hasMore && (
        <Button 
          type="link" 
          size="small"
          onClick={() => setShowAll(!showAll)}
          style={{ alignSelf: 'center', marginTop: 4 }}
        >
          {showAll ? 'Show less' : `Show ${insights.length - maxInsights} more insights`}
        </Button>
      )}

      {/* No insights case (shouldn't happen due to healthy system insight) */}
      {insights.length === 0 && (
        <div style={{ textAlign: 'center', padding: 24, color: token.colorTextSecondary }}>
          <CheckCircleOutlined style={{ fontSize: 32, marginBottom: 8 }} />
          <div>No data available for analysis</div>
        </div>
      )}
    </div>
  );
};

export default AIInsightCards;
