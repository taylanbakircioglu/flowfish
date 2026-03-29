import React, { useEffect, useRef } from 'react';
import { Card, Space, Typography, theme, Row, Col, Tooltip } from 'antd';
import { DashboardOutlined } from '@ant-design/icons';

const { Text } = Typography;
const { useToken } = theme;

interface GaugeData {
  label: string;
  value: number;
  max: number;
  unit?: string;
  color?: string;
  warning?: number;
  critical?: number;
}

interface ResourceGaugeProps {
  gauges: GaugeData[];
  title?: string;
  columns?: number;
}

const SingleGauge: React.FC<{ data: GaugeData }> = ({ data }) => {
  const { token } = useToken();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  const percentage = Math.min((data.value / data.max) * 100, 100);
  const isWarning = data.warning && percentage >= data.warning;
  const isCritical = data.critical && percentage >= data.critical;
  
  const gaugeColor = data.color || (
    isCritical ? '#e05252' : 
    isWarning ? '#d4a844' : 
    '#4caf50'
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height - 10;
    const radius = Math.min(width, height) - 20;

    ctx.clearRect(0, 0, width, height);

    // Background arc
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, 0);
    ctx.strokeStyle = token.colorBorderSecondary;
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Value arc with gradient
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, `${gaugeColor}80`);
    gradient.addColorStop(1, gaugeColor);

    const endAngle = Math.PI + (Math.PI * percentage / 100);
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, endAngle);
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 12;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Glow effect
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, Math.PI, endAngle);
    ctx.strokeStyle = `${gaugeColor}30`;
    ctx.lineWidth = 20;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Tick marks
    for (let i = 0; i <= 10; i++) {
      const angle = Math.PI + (Math.PI * i / 10);
      const innerRadius = radius - 20;
      const outerRadius = radius - 8;
      
      ctx.beginPath();
      ctx.moveTo(
        centerX + Math.cos(angle) * innerRadius,
        centerY + Math.sin(angle) * innerRadius
      );
      ctx.lineTo(
        centerX + Math.cos(angle) * outerRadius,
        centerY + Math.sin(angle) * outerRadius
      );
      ctx.strokeStyle = token.colorTextSecondary;
      ctx.lineWidth = i % 5 === 0 ? 2 : 1;
      ctx.stroke();
    }

    // Needle
    const needleAngle = Math.PI + (Math.PI * percentage / 100);
    const needleLength = radius - 25;
    
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(
      centerX + Math.cos(needleAngle) * needleLength,
      centerY + Math.sin(needleAngle) * needleLength
    );
    ctx.strokeStyle = gaugeColor;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    ctx.stroke();

    // Center circle
    ctx.beginPath();
    ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
    ctx.fillStyle = gaugeColor;
    ctx.fill();

  }, [data, percentage, gaugeColor, token]);

  return (
    <div style={{ textAlign: 'center', padding: '8px 0' }}>
      <canvas
        ref={canvasRef}
        width={120}
        height={70}
        style={{ maxWidth: '100%' }}
      />
      <div style={{ marginTop: 4 }}>
        <Text strong style={{ fontSize: 18, color: gaugeColor }}>
          {data.value.toLocaleString()}
          {data.unit && <span style={{ fontSize: 12, color: token.colorTextSecondary }}> {data.unit}</span>}
        </Text>
        <Text type="secondary" style={{ fontSize: 10, display: 'block' }}>
          / {data.max.toLocaleString()} ({percentage.toFixed(0)}%)
        </Text>
      </div>
      <Text type="secondary" style={{ fontSize: 11 }}>{data.label}</Text>
    </div>
  );
};

const ResourceGauge: React.FC<ResourceGaugeProps> = ({
  gauges,
  title = 'Resource Utilization',
  columns = 4,
}) => {
  const { token } = useToken();

  return (
    <Card
      title={
        <Space>
          <DashboardOutlined style={{ color: '#7c8eb5' }} />
          <span>{title}</span>
        </Space>
      }
      bordered={false}
    >
      <Row gutter={[16, 16]}>
        {gauges.map((gauge, index) => (
          <Col key={index} xs={24} sm={12} md={24 / columns}>
            <Tooltip title={`${gauge.label}: ${gauge.value}${gauge.unit || ''} / ${gauge.max}${gauge.unit || ''}`}>
              <div style={{ 
                background: token.colorBgLayout, 
                borderRadius: 8, 
                padding: 8,
              }}>
                <SingleGauge data={gauge} />
              </div>
            </Tooltip>
          </Col>
        ))}
      </Row>
    </Card>
  );
};

export default ResourceGauge;
