import React, { useMemo } from 'react';
import { Card, Space, Typography, Tooltip, Empty, theme, Tag } from 'antd';
import { HeatMapOutlined, ArrowRightOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { useToken } = theme;

interface TrafficData {
  source: string;
  sourceNamespace: string;
  destination: string;
  destinationNamespace: string;
  bytes: number;
  requests: number;
}

interface TrafficHeatmapProps {
  data: TrafficData[];
  loading?: boolean;
  title?: string;
  maxItems?: number;
}

const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
};

const getHeatColor = (intensity: number): string => {
  // Intensity from 0 to 1
  if (intensity > 0.8) return '#e05252';
  if (intensity > 0.6) return '#d4756a';
  if (intensity > 0.4) return '#b89b5d';
  if (intensity > 0.2) return '#c9a55a';
  return '#4d9f7c';
};

const TrafficHeatmap: React.FC<TrafficHeatmapProps> = ({
  data,
  loading = false,
  title = 'Traffic Heatmap',
  maxItems = 10,
}) => {
  const { token } = useToken();

  // Process data for heatmap
  const heatmapData = useMemo(() => {
    if (!data || data.length === 0) return [];

    const maxBytes = Math.max(...data.map(d => d.bytes));
    const maxRequests = Math.max(...data.map(d => d.requests));

    return data
      .slice(0, maxItems)
      .map(item => ({
        ...item,
        bytesIntensity: maxBytes > 0 ? item.bytes / maxBytes : 0,
        requestsIntensity: maxRequests > 0 ? item.requests / maxRequests : 0,
        combinedIntensity: maxBytes > 0 ? (item.bytes / maxBytes * 0.7 + item.requests / maxRequests * 0.3) : 0,
      }))
      .sort((a, b) => b.combinedIntensity - a.combinedIntensity);
  }, [data, maxItems]);

  // Get unique namespaces for legend
  const namespaces = useMemo(() => {
    const nsSet = new Set<string>();
    data.forEach(d => {
      nsSet.add(d.sourceNamespace);
      nsSet.add(d.destinationNamespace);
    });
    return Array.from(nsSet).slice(0, 6);
  }, [data]);

  const namespaceColors: Record<string, string> = {};
  const colorPalette = ['#0891b2', '#4d9f7c', '#7c8eb5', '#b89b5d', '#22a6a6', '#a67c9e'];
  namespaces.forEach((ns, i) => {
    namespaceColors[ns] = colorPalette[i % colorPalette.length];
  });

  return (
    <Card
      title={
        <Space>
          <HeatMapOutlined style={{ color: '#b89b5d' }} />
          <span>{title}</span>
        </Space>
      }
      bordered={false}
      extra={
        <Space size={4}>
          {namespaces.slice(0, 4).map(ns => (
            <Tag key={ns} color={namespaceColors[ns]} style={{ fontSize: 10, margin: 0 }}>
              {ns.length > 10 ? ns.substring(0, 10) + '...' : ns}
            </Tag>
          ))}
        </Space>
      }
    >
      {heatmapData.length === 0 ? (
        <Empty 
          description="No traffic data" 
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ padding: 40 }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {heatmapData.map((item, index) => {
            const heatColor = getHeatColor(item.combinedIntensity);
            const barWidth = Math.max(item.combinedIntensity * 100, 5);
            
            return (
              <Tooltip
                key={`${item.source}-${item.destination}-${index}`}
                title={
                  <div>
                    <div><strong>{item.source}</strong> → <strong>{item.destination}</strong></div>
                    <div>Traffic: {formatBytes(item.bytes)}</div>
                    <div>Requests: {item.requests.toLocaleString()}</div>
                  </div>
                }
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 12px',
                    background: token.colorBgLayout,
                    borderRadius: 8,
                    position: 'relative',
                    overflow: 'hidden',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateX(4px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateX(0)';
                  }}
                >
                  {/* Heat bar background */}
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 0,
                      bottom: 0,
                      width: `${barWidth}%`,
                      background: `linear-gradient(90deg, ${heatColor}30 0%, ${heatColor}10 100%)`,
                      transition: 'width 0.5s ease',
                    }}
                  />
                  
                  {/* Content */}
                  <div style={{ 
                    flex: 1, 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 8,
                    position: 'relative',
                    zIndex: 1,
                  }}>
                    {/* Rank */}
                    <div style={{
                      width: 20,
                      height: 20,
                      borderRadius: 4,
                      background: heatColor,
                      color: token.colorTextLightSolid,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 11,
                      fontWeight: 600,
                    }}>
                      {index + 1}
                    </div>
                    
                    {/* Source */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text strong style={{ fontSize: 12 }} ellipsis>
                        {item.source}
                      </Text>
                      <br />
                      <Tag 
                        color={namespaceColors[item.sourceNamespace]} 
                        style={{ fontSize: 9, padding: '0 4px', margin: 0 }}
                      >
                        {item.sourceNamespace}
                      </Tag>
                    </div>
                    
                    {/* Arrow */}
                    <ArrowRightOutlined style={{ color: heatColor, fontSize: 16 }} />
                    
                    {/* Destination */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text strong style={{ fontSize: 12 }} ellipsis>
                        {item.destination}
                      </Text>
                      <br />
                      <Tag 
                        color={namespaceColors[item.destinationNamespace]} 
                        style={{ fontSize: 9, padding: '0 4px', margin: 0 }}
                      >
                        {item.destinationNamespace}
                      </Tag>
                    </div>
                    
                    {/* Stats */}
                    <div style={{ textAlign: 'right', minWidth: 70 }}>
                      <Text strong style={{ fontSize: 13, color: heatColor }}>
                        {formatBytes(item.bytes)}
                      </Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 10 }}>
                        {item.requests.toLocaleString()} req
                      </Text>
                    </div>
                  </div>
                </div>
              </Tooltip>
            );
          })}
          
          {/* Heat scale legend */}
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            gap: 8,
            marginTop: 8,
            padding: '8px 0',
          }}>
            <Text type="secondary" style={{ fontSize: 10 }}>Low</Text>
            <div style={{
              display: 'flex',
              height: 8,
              borderRadius: 4,
              overflow: 'hidden',
            }}>
              {['#4d9f7c', '#c9a55a', '#b89b5d', '#d4756a', '#e05252'].map((color, i) => (
                <div 
                  key={i} 
                  style={{ 
                    width: 24, 
                    height: '100%', 
                    background: color 
                  }} 
                />
              ))}
            </div>
            <Text type="secondary" style={{ fontSize: 10 }}>High</Text>
          </div>
        </div>
      )}
    </Card>
  );
};

export default TrafficHeatmap;
