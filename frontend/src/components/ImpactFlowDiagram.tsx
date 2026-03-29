import React, { useMemo } from 'react';
import { Card, Typography, Tag, Space, Tooltip, Empty, theme } from 'antd';
import {
  AimOutlined,
  ArrowRightOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ApiOutlined,
  GlobalOutlined,
  ContainerOutlined,
} from '@ant-design/icons';
import type { AffectedService, ImpactLevel } from '../store/api/simulationApi';

const { Text } = Typography;
const { useToken } = theme;

// =============================================================================
// Types
// =============================================================================

interface ImpactFlowDiagramProps {
  targetName: string;
  targetNamespace: string;
  targetKind: string;
  affectedServices: AffectedService[];
  maxDisplay?: number;
}

interface NodeProps {
  name: string;
  namespace: string;
  kind: string;
  impact?: ImpactLevel;
  isTarget?: boolean;
  dependency?: 'direct' | 'indirect';
  connectionInfo?: {
    protocol?: string;
    port?: number;
    requestCount?: number;
  };
  token: any; // Ant Design token for theming
}

// =============================================================================
// Constants
// =============================================================================

const impactColors: Record<ImpactLevel, string> = {
  high: '#c75450',
  medium: '#b89b5d',
  low: '#fadb14',
  none: '#4d9f7c',
};

const kindIcons: Record<string, React.ReactNode> = {
  Pod: <ContainerOutlined />,
  Deployment: <ApiOutlined />,
  Service: <ApiOutlined />,
  External: <GlobalOutlined />,
};

// =============================================================================
// Sub-Components
// =============================================================================

const FlowNode: React.FC<NodeProps> = ({
  name,
  namespace,
  kind,
  impact,
  isTarget,
  dependency,
  connectionInfo,
  token,
}) => {
  const borderColor = isTarget ? '#0891b2' : impact ? impactColors[impact] : token.colorBorder;
  
  // Use theme-aware background colors
  const getBgColor = () => {
    if (isTarget) {
      return token.colorInfoBg;
    }
    if (impact) {
      switch (impact) {
        case 'high': return token.colorErrorBg;
        case 'medium': return token.colorWarningBg;
        case 'low': return token.colorWarningBg;
        case 'none': return token.colorSuccessBg;
        default: return token.colorBgContainer;
      }
    }
    return token.colorBgContainer;
  };

  // Text color that works on both light and dark backgrounds
  const textColor = token.colorText;
  const secondaryTextColor = token.colorTextSecondary;

  return (
    <Tooltip
      title={
        <div>
          <div><strong>{name}</strong></div>
          <div>Namespace: {namespace}</div>
          <div>Kind: {kind}</div>
          {connectionInfo && (
            <>
              {connectionInfo.protocol && <div>Protocol: {connectionInfo.protocol}</div>}
              {connectionInfo.port && <div>Port: {connectionInfo.port}</div>}
              {connectionInfo.requestCount !== undefined && (
                <div>Requests: {connectionInfo.requestCount.toLocaleString()}</div>
              )}
            </>
          )}
        </div>
      }
    >
      <div
        style={{
          display: 'inline-flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '8px 12px',
          borderRadius: 8,
          border: `2px solid ${borderColor}`,
          backgroundColor: getBgColor(),
          minWidth: 100,
          maxWidth: 140,
          cursor: 'pointer',
          transition: 'all 0.2s',
        }}
      >
        <div style={{ fontSize: 18, color: borderColor, marginBottom: 4 }}>
          {isTarget ? <AimOutlined /> : kindIcons[kind] || <ApiOutlined />}
        </div>
        <Text
          strong
          style={{
            fontSize: 11,
            textAlign: 'center',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            width: '100%',
            color: textColor,
          }}
        >
          {name.length > 15 ? `${name.substring(0, 12)}...` : name}
        </Text>
        <Text style={{ fontSize: 9, color: secondaryTextColor }}>
          {namespace}
        </Text>
        {!isTarget && impact && (
          <Tag
            color={impactColors[impact]}
            style={{ fontSize: 9, marginTop: 4, padding: '0 4px' }}
          >
            {impact.toUpperCase()}
          </Tag>
        )}
        {isTarget && (
          <Tag color="blue" style={{ fontSize: 9, marginTop: 4, padding: '0 4px' }}>
            TARGET
          </Tag>
        )}
      </div>
    </Tooltip>
  );
};

const ConnectionArrow: React.FC<{ isDirect: boolean }> = ({ isDirect }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      padding: '0 8px',
      color: isDirect ? '#c75450' : '#b89b5d',
    }}
  >
    <div
      style={{
        width: isDirect ? 40 : 30,
        height: 2,
        backgroundColor: isDirect ? '#c75450' : '#b89b5d',
        position: 'relative',
      }}
    >
      <ArrowRightOutlined
        style={{
          position: 'absolute',
          right: -8,
          top: -7,
          fontSize: 14,
        }}
      />
    </div>
  </div>
);

// =============================================================================
// Main Component
// =============================================================================

const ImpactFlowDiagram: React.FC<ImpactFlowDiagramProps> = ({
  targetName,
  targetNamespace,
  targetKind,
  affectedServices,
  maxDisplay = 8,
}) => {
  const { token } = useToken();
  
  // Group services by dependency type
  const { directServices, indirectServices } = useMemo(() => {
    const direct = affectedServices.filter(s => s.dependency === 'direct');
    const indirect = affectedServices.filter(s => s.dependency === 'indirect');
    return {
      directServices: direct.slice(0, Math.ceil(maxDisplay / 2)),
      indirectServices: indirect.slice(0, Math.floor(maxDisplay / 2)),
    };
  }, [affectedServices, maxDisplay]);

  const hiddenCount = affectedServices.length - directServices.length - indirectServices.length;

  if (affectedServices.length === 0) {
    return (
      <Card size="small" bordered={false}>
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No affected services to visualize"
        />
      </Card>
    );
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <WarningOutlined style={{ color: '#b89b5d' }} />
          <Text strong>Impact Flow</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            ({affectedServices.length} affected)
          </Text>
        </Space>
      }
      bordered={false}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '16px 0',
          overflowX: 'auto',
        }}
      >
        {/* Direct Dependencies Row */}
        {directServices.length > 0 && (
          <>
            <div style={{ marginBottom: 8 }}>
              <Tag color="red" icon={<ExclamationCircleOutlined />}>
                Direct Dependencies (1-hop)
              </Tag>
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexWrap: 'wrap',
                gap: 8,
                marginBottom: 16,
              }}
            >
              {directServices.map((service, index) => (
                <React.Fragment key={service.id}>
                  <FlowNode
                    name={service.name}
                    namespace={service.namespace}
                    kind={service.kind}
                    impact={service.impact}
                    dependency="direct"
                    connectionInfo={{
                      protocol: service.connection_details?.protocol,
                      port: service.connection_details?.port,
                      requestCount: service.connection_details?.request_count,
                    }}
                    token={token}
                  />
                  {index < directServices.length - 1 && (
                    <div style={{ width: 8 }} />
                  )}
                </React.Fragment>
              ))}
            </div>

            {/* Arrows to Target */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                marginBottom: 8,
              }}
            >
              {directServices.map((_, index) => (
                <div
                  key={index}
                  style={{
                    width: 2,
                    height: 24,
                    backgroundColor: '#c75450',
                    margin: '0 30px',
                  }}
                />
              ))}
            </div>
          </>
        )}

        {/* Target Node */}
        <div style={{ margin: '8px 0' }}>
          <FlowNode
            name={targetName}
            namespace={targetNamespace}
            kind={targetKind}
            isTarget
            token={token}
          />
        </div>

        {/* Indirect Dependencies */}
        {indirectServices.length > 0 && (
          <>
            {/* Arrows from Target */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                marginTop: 8,
              }}
            >
              {indirectServices.map((_, index) => (
                <div
                  key={index}
                  style={{
                    width: 2,
                    height: 24,
                    backgroundColor: '#b89b5d',
                    margin: '0 30px',
                  }}
                />
              ))}
            </div>

            <div style={{ marginTop: 8, marginBottom: 8 }}>
              <Tag color="orange" icon={<WarningOutlined />}>
                Indirect Dependencies (2-hop)
              </Tag>
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexWrap: 'wrap',
                gap: 8,
              }}
            >
              {indirectServices.map((service, index) => (
                <React.Fragment key={service.id}>
                  <FlowNode
                    name={service.name}
                    namespace={service.namespace}
                    kind={service.kind}
                    impact={service.impact}
                    dependency="indirect"
                    connectionInfo={{
                      protocol: service.connection_details?.protocol,
                      port: service.connection_details?.port,
                      requestCount: service.connection_details?.request_count,
                    }}
                    token={token}
                  />
                  {index < indirectServices.length - 1 && (
                    <div style={{ width: 8 }} />
                  )}
                </React.Fragment>
              ))}
            </div>
          </>
        )}

        {/* Hidden count indicator */}
        {hiddenCount > 0 && (
          <div style={{ marginTop: 16 }}>
            <Tag color="default">
              +{hiddenCount} more services not shown
            </Tag>
          </div>
        )}
      </div>

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          gap: 16,
          marginTop: 16,
          paddingTop: 12,
          borderTop: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Space size={4}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: 2,
              backgroundColor: impactColors.high,
            }}
          />
          <Text type="secondary" style={{ fontSize: 10 }}>High</Text>
        </Space>
        <Space size={4}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: 2,
              backgroundColor: impactColors.medium,
            }}
          />
          <Text type="secondary" style={{ fontSize: 10 }}>Medium</Text>
        </Space>
        <Space size={4}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: 2,
              backgroundColor: impactColors.low,
            }}
          />
          <Text type="secondary" style={{ fontSize: 10 }}>Low</Text>
        </Space>
        <Space size={4}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: 2,
              backgroundColor: '#0891b2',
            }}
          />
          <Text type="secondary" style={{ fontSize: 10 }}>Target</Text>
        </Space>
      </div>
    </Card>
  );
};

export default ImpactFlowDiagram;

