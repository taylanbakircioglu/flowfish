import React, { useEffect, useState, useRef } from 'react';
import { Card, Tooltip, theme } from 'antd';
import { RiseOutlined, FallOutlined } from '@ant-design/icons';

const { useToken } = theme;

interface AnimatedStatCardProps {
  title: string;
  value: number;
  previousValue?: number;
  suffix?: string;
  prefix?: React.ReactNode;
  icon?: React.ReactNode;
  color?: string;
  gradient?: string;
  loading?: boolean;
  formatter?: (value: number) => string;
  subtitle?: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: number;
  sparklineData?: number[];
  pulseEffect?: boolean;
  onClick?: () => void;
}

// Animated counter hook
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

// Mini sparkline component
const Sparkline: React.FC<{ data: number[]; color: string; height?: number }> = ({ 
  data, 
  color, 
  height = 30 
}) => {
  if (!data || data.length < 2) return null;
  
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const width = 80;
  const points = data.map((value, index) => {
    const x = (index / (data.length - 1)) * width;
    const y = height - ((value - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} style={{ marginLeft: 8 }}>
      <defs>
        <linearGradient id={`sparkline-gradient-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Area fill */}
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#sparkline-gradient-${color.replace('#', '')})`}
      />
    </svg>
  );
};

const AnimatedStatCard: React.FC<AnimatedStatCardProps> = ({
  title,
  value,
  previousValue,
  suffix,
  prefix,
  icon,
  color = '#0891b2',
  gradient,
  loading = false,
  formatter,
  subtitle,
  trend,
  trendValue,
  sparklineData,
  pulseEffect = false,
  onClick,
}) => {
  const { token } = useToken();
  const animatedValue = useAnimatedCounter(value, 1200, loading);
  
  const displayValue = formatter ? formatter(animatedValue) : animatedValue.toLocaleString();
  
  const computedTrend = trend || (previousValue !== undefined ? 
    (value > previousValue ? 'up' : value < previousValue ? 'down' : 'neutral') : undefined);
  
  const computedTrendValue = trendValue ?? (previousValue !== undefined && previousValue !== 0 ? 
    Math.round(((value - previousValue) / previousValue) * 100) : undefined);

  const cardStyle: React.CSSProperties = {
    background: gradient || token.colorBgContainer,
    borderRadius: 12,
    border: gradient ? 'none' : `1px solid ${token.colorBorderSecondary}`,
    cursor: onClick ? 'pointer' : 'default',
    transition: 'all 0.3s ease',
    overflow: 'hidden',
    position: 'relative',
  };

  const isGradient = !!gradient;
  const textColor = isGradient ? 'rgba(255,255,255,0.85)' : token.colorTextSecondary;
  const valueColor = isGradient ? token.colorTextLightSolid : color;

  return (
    <Card
      bordered={false}
      style={cardStyle}
      bodyStyle={{ padding: '20px 24px' }}
      onClick={onClick}
      hoverable={!!onClick}
    >
      {/* Pulse effect overlay */}
      {pulseEffect && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: `radial-gradient(circle at center, ${color}20 0%, transparent 70%)`,
            animation: 'pulse 2s ease-in-out infinite',
          }}
        />
      )}
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          {/* Title */}
          <div style={{ 
            color: textColor, 
            fontSize: 13, 
            fontWeight: 500,
            marginBottom: 8,
            display: 'flex',
            alignItems: 'center',
            gap: 6
          }}>
            {icon && <span style={{ fontSize: 14 }}>{icon}</span>}
            {title}
          </div>
          
          {/* Value */}
          <div style={{ 
            display: 'flex', 
            alignItems: 'baseline', 
            gap: 4,
            marginBottom: 4
          }}>
            {prefix && <span style={{ color: valueColor, fontSize: 20 }}>{prefix}</span>}
            <span style={{ 
              color: valueColor, 
              fontSize: 32, 
              fontWeight: 600,
              fontFamily: "'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
              letterSpacing: '-0.02em'
            }}>
              {loading ? '—' : displayValue}
            </span>
            {suffix && (
              <span style={{ color: textColor, fontSize: 14, marginLeft: 4 }}>
                {suffix}
              </span>
            )}
          </div>
          
          {/* Subtitle or Trend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minHeight: 20 }}>
            {computedTrend && computedTrendValue !== undefined && (
              <Tooltip title={`${computedTrendValue > 0 ? '+' : ''}${computedTrendValue}% from previous`}>
                <span style={{ 
                  display: 'flex',
                  alignItems: 'center',
                  gap: 2,
                  fontSize: 12,
                  fontWeight: 500,
                  color: isGradient ? 'rgba(255,255,255,0.85)' : 
                    (computedTrend === 'up' ? '#4caf50' : computedTrend === 'down' ? '#e05252' : token.colorTextSecondary),
                  background: isGradient ? 'rgba(255,255,255,0.15)' : 
                    (computedTrend === 'up' ? '#4caf5015' : computedTrend === 'down' ? '#e0525215' : 'transparent'),
                  padding: '2px 6px',
                  borderRadius: 4,
                }}>
                  {computedTrend === 'up' ? <RiseOutlined /> : computedTrend === 'down' ? <FallOutlined /> : null}
                  {computedTrendValue > 0 ? '+' : ''}{computedTrendValue}%
                </span>
              </Tooltip>
            )}
            {subtitle && (
              <span style={{ color: textColor, fontSize: 12 }}>
                {subtitle}
              </span>
            )}
          </div>
        </div>
        
        {/* Sparkline */}
        {sparklineData && sparklineData.length > 1 && (
          <Sparkline data={sparklineData} color={isGradient ? 'rgba(255,255,255,0.8)' : color} />
        )}
      </div>
      
      {/* CSS Animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
      `}</style>
    </Card>
  );
};

export default AnimatedStatCard;
