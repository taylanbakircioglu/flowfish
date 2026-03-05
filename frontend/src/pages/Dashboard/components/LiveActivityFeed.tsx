import React, { useState, useEffect, useRef } from 'react';
import { Card, Space, Tag, Typography, Badge, Empty, theme, Tooltip } from 'antd';
import { 
  ThunderboltOutlined, 
  ApiOutlined, 
  SecurityScanOutlined,
  DatabaseOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  LockOutlined,
  FileOutlined,
  WarningOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

dayjs.extend(relativeTime);

const { Text } = Typography;
const { useToken } = theme;

interface ActivityItem {
  id: string;
  timestamp: string;
  type: string;
  namespace: string;
  pod: string;
  details: string;
  severity?: 'info' | 'warning' | 'error';
}

interface LiveActivityFeedProps {
  activities: ActivityItem[];
  loading?: boolean;
  maxItems?: number;
  title?: string;
  autoScroll?: boolean;
}

const eventTypeConfig: Record<string, { icon: React.ReactNode; color: string }> = {
  network_flow: { icon: <ApiOutlined />, color: '#0891b2' },
  dns_query: { icon: <GlobalOutlined />, color: '#4caf50' },
  security_event: { icon: <SecurityScanOutlined />, color: '#e05252' },
  process_event: { icon: <CloudServerOutlined />, color: '#7c8eb5' },
  file_event: { icon: <FileOutlined />, color: '#d4a844' },
  oom_event: { icon: <WarningOutlined />, color: '#f76e6e' },
  bind_event: { icon: <DatabaseOutlined />, color: '#22a6a6' },
  sni_event: { icon: <LockOutlined />, color: '#69b1ff' },
};

const severityColors = {
  info: '#0891b2',
  warning: '#d4a844',
  error: '#e05252',
};

const LiveActivityFeed: React.FC<LiveActivityFeedProps> = ({
  activities,
  loading = false,
  maxItems = 10,
  title = 'Live Activity',
  autoScroll = true,
}) => {
  const { token } = useToken();
  const containerRef = useRef<HTMLDivElement>(null);
  const [animatingItems, setAnimatingItems] = useState<Set<string>>(new Set());
  const prevActivitiesRef = useRef<string[]>([]);

  // Track new items for animation
  useEffect(() => {
    const currentIds = activities.slice(0, maxItems).map(a => a.id);
    const prevIds = prevActivitiesRef.current;
    
    const newIds = currentIds.filter(id => !prevIds.includes(id));
    if (newIds.length > 0) {
      setAnimatingItems(new Set(newIds));
      setTimeout(() => setAnimatingItems(new Set()), 500);
    }
    
    prevActivitiesRef.current = currentIds;
  }, [activities, maxItems]);

  // Auto scroll to top on new items
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [activities, autoScroll]);

  const displayActivities = activities.slice(0, maxItems);

  return (
    <Card
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#d4a844' }} />
          <span>{title}</span>
          <Badge 
            count={activities.length} 
            style={{ backgroundColor: token.colorPrimary }} 
            overflowCount={999}
          />
        </Space>
      }
      bordered={false}
      bodyStyle={{ 
        padding: 0, 
        maxHeight: 400, 
        overflow: 'auto',
      }}
      extra={
        <div style={{ 
          width: 8, 
          height: 8, 
          borderRadius: '50%', 
          background: '#4caf50',
          animation: 'livePulse 1.5s ease-in-out infinite'
        }} />
      }
    >
      <div ref={containerRef} style={{ padding: '8px 0' }}>
        {displayActivities.length === 0 ? (
          <Empty 
            description="No recent activity" 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ padding: 40 }}
          />
        ) : (
          displayActivities.map((activity, index) => {
            const config = eventTypeConfig[activity.type] || { icon: <ThunderboltOutlined />, color: '#8c8c8c' };
            const isNew = animatingItems.has(activity.id);
            const severityColor = activity.severity ? severityColors[activity.severity] : undefined;
            
            return (
              <div
                key={activity.id}
                style={{
                  padding: '12px 16px',
                  borderBottom: index < displayActivities.length - 1 ? `1px solid ${token.colorBorderSecondary}` : 'none',
                  background: isNew ? `${config.color}10` : 'transparent',
                  transition: 'all 0.3s ease',
                  animation: isNew ? 'slideIn 0.3s ease-out' : undefined,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
                  {/* Icon */}
                  <div style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: `${config.color}15`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: config.color,
                    fontSize: 16,
                    flexShrink: 0,
                  }}>
                    {config.icon}
                  </div>
                  
                  {/* Content */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <Tag 
                        color={config.color} 
                        style={{ 
                          fontSize: 10, 
                          padding: '0 6px',
                          margin: 0,
                          textTransform: 'uppercase',
                          fontWeight: 600,
                        }}
                      >
                        {activity.type.replace(/_/g, ' ')}
                      </Tag>
                      {severityColor && (
                        <span style={{
                          width: 6,
                          height: 6,
                          borderRadius: '50%',
                          background: severityColor,
                        }} />
                      )}
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
                        {dayjs(activity.timestamp).fromNow()}
                      </Text>
                    </div>
                    
                    <div style={{ marginBottom: 4 }}>
                      <Tooltip title={`${activity.namespace}/${activity.pod}`}>
                        <Text strong style={{ fontSize: 12 }} ellipsis>
                          {activity.pod}
                        </Text>
                      </Tooltip>
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                        ({activity.namespace})
                      </Text>
                    </div>
                    
                    <Tooltip title={activity.details}>
                      <Text 
                        type="secondary" 
                        style={{ fontSize: 11, display: 'block' }} 
                        ellipsis
                      >
                        {activity.details}
                      </Text>
                    </Tooltip>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
      
      <style>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes livePulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.2); }
        }
      `}</style>
    </Card>
  );
};

export default LiveActivityFeed;
