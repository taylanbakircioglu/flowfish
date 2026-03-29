import React, { useEffect, useRef, useState } from 'react';
import { Card, Space, Typography, Badge, Tag, Empty, theme, Tooltip } from 'antd';
import { 
  RadarChartOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
  InfoCircleOutlined
} from '@ant-design/icons';

const { Text } = Typography;
const { useToken } = theme;

interface ThreatItem {
  id: string;
  type: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  target: string;
  namespace: string;
  description: string;
  count: number;
  angle?: number;
  distance?: number;
}

interface ThreatRadarProps {
  threats: ThreatItem[];
  loading?: boolean;
  title?: string;
  onThreatClick?: (threat: ThreatItem) => void;
}

const severityConfig = {
  critical: { color: '#cf1322', ring: 0.2, icon: <ExclamationCircleOutlined /> },
  high: { color: '#e05252', ring: 0.4, icon: <WarningOutlined /> },
  medium: { color: '#d4a844', ring: 0.6, icon: <InfoCircleOutlined /> },
  low: { color: '#4caf50', ring: 0.8, icon: <InfoCircleOutlined /> },
};

const ThreatRadar: React.FC<ThreatRadarProps> = ({
  threats,
  loading = false,
  title = 'Threat Radar',
  onThreatClick,
}) => {
  const { token } = useToken();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredThreat, setHoveredThreat] = useState<string | null>(null);
  const [dimensions, setDimensions] = useState({ width: 300, height: 300 });
  const animationRef = useRef<number>();
  const angleRef = useRef(0);

  // Resize observer
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        const size = Math.min(width, 300);
        setDimensions({ width: size, height: size });
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Draw radar
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = dimensions;
    const centerX = width / 2;
    const centerY = height / 2;
    const maxRadius = Math.min(width, height) / 2 - 20;

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // Draw radar rings
      const rings = [0.25, 0.5, 0.75, 1];
      rings.forEach((ring, index) => {
        ctx.beginPath();
        ctx.arc(centerX, centerY, maxRadius * ring, 0, Math.PI * 2);
        ctx.strokeStyle = token.colorBorderSecondary;
        ctx.lineWidth = 1;
        ctx.stroke();

        // Ring labels
        if (index < 4) {
          const labels = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
          ctx.font = '9px sans-serif';
          ctx.fillStyle = token.colorTextSecondary;
          ctx.textAlign = 'center';
          ctx.fillText(labels[index], centerX, centerY - maxRadius * ring + 12);
        }
      });

      // Draw cross lines
      ctx.beginPath();
      ctx.moveTo(centerX, centerY - maxRadius);
      ctx.lineTo(centerX, centerY + maxRadius);
      ctx.moveTo(centerX - maxRadius, centerY);
      ctx.lineTo(centerX + maxRadius, centerY);
      ctx.strokeStyle = token.colorBorderSecondary;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Draw sweep line
      angleRef.current = (angleRef.current + 0.02) % (Math.PI * 2);
      const sweepGradient = ctx.createLinearGradient(
        centerX,
        centerY,
        centerX + Math.cos(angleRef.current) * maxRadius,
        centerY + Math.sin(angleRef.current) * maxRadius
      );
      sweepGradient.addColorStop(0, 'transparent');
      sweepGradient.addColorStop(0.5, `${token.colorPrimary}30`);
      sweepGradient.addColorStop(1, `${token.colorPrimary}60`);

      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, maxRadius, angleRef.current - 0.3, angleRef.current);
      ctx.closePath();
      ctx.fillStyle = sweepGradient;
      ctx.fill();

      // Draw sweep line
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(
        centerX + Math.cos(angleRef.current) * maxRadius,
        centerY + Math.sin(angleRef.current) * maxRadius
      );
      ctx.strokeStyle = token.colorPrimary;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Draw threats
      threats.forEach((threat) => {
        const config = severityConfig[threat.severity];
        const angle = threat.angle ?? Math.random() * Math.PI * 2;
        const distance = threat.distance ?? config.ring;
        const x = centerX + Math.cos(angle) * maxRadius * distance;
        const y = centerY + Math.sin(angle) * maxRadius * distance;

        const isHovered = hoveredThreat === threat.id;
        const size = isHovered ? 10 : 6 + Math.min(threat.count, 10);

        // Glow effect
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, size * 2);
        gradient.addColorStop(0, `${config.color}80`);
        gradient.addColorStop(1, 'transparent');
        ctx.beginPath();
        ctx.arc(x, y, size * 2, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Main dot
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = config.color;
        ctx.fill();

        // Pulse animation for critical
        if (threat.severity === 'critical') {
          const pulseSize = size + Math.sin(Date.now() / 200) * 3;
          ctx.beginPath();
          ctx.arc(x, y, pulseSize + 4, 0, Math.PI * 2);
          ctx.strokeStyle = `${config.color}50`;
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      });

      // Center dot
      ctx.beginPath();
      ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
      ctx.fillStyle = token.colorPrimary;
      ctx.fill();

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [threats, dimensions, hoveredThreat, token]);

  // Count by severity
  const severityCounts = threats.reduce((acc, t) => {
    acc[t.severity] = (acc[t.severity] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <Card
      title={
        <Space>
          <RadarChartOutlined style={{ color: '#e05252' }} />
          <span>{title}</span>
        </Space>
      }
      bordered={false}
      extra={
        <Space size={4}>
          {Object.entries(severityCounts).map(([severity, count]) => (
            <Tag 
              key={severity} 
              color={severityConfig[severity as keyof typeof severityConfig]?.color}
              style={{ fontSize: 10, margin: 0 }}
            >
              {count}
            </Tag>
          ))}
        </Space>
      }
    >
      <div ref={containerRef} style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        {threats.length === 0 ? (
          <Empty 
            description="No active threats" 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ padding: 40 }}
          />
        ) : (
          <>
            <canvas
              ref={canvasRef}
              width={dimensions.width}
              height={dimensions.height}
              style={{ 
                maxWidth: '100%',
                background: `radial-gradient(circle at center, ${token.colorBgContainer} 0%, ${token.colorBgLayout} 100%)`,
                borderRadius: '50%',
              }}
            />
            
            {/* Legend */}
            <div style={{ 
              marginTop: 16, 
              display: 'flex', 
              flexWrap: 'wrap', 
              gap: 8, 
              justifyContent: 'center' 
            }}>
              {threats.slice(0, 5).map((threat) => {
                const config = severityConfig[threat.severity];
                return (
                  <Tooltip key={threat.id} title={threat.description}>
                    <Tag
                      color={config.color}
                      style={{ 
                        cursor: 'pointer',
                        fontSize: 10,
                      }}
                      onClick={() => onThreatClick?.(threat)}
                      onMouseEnter={() => setHoveredThreat(threat.id)}
                      onMouseLeave={() => setHoveredThreat(null)}
                    >
                      {config.icon} {threat.target}
                      <Badge 
                        count={threat.count} 
                        size="small" 
                        style={{ marginLeft: 4, backgroundColor: config.color }} 
                      />
                    </Tag>
                  </Tooltip>
                );
              })}
            </div>
          </>
        )}
      </div>
    </Card>
  );
};

export default ThreatRadar;
