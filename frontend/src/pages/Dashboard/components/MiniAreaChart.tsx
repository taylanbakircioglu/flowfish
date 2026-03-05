import React, { useMemo } from 'react';
import { theme } from 'antd';

const { useToken } = theme;

interface DataPoint {
  label: string;
  value: number;
}

interface MiniAreaChartProps {
  data: DataPoint[];
  color?: string;
  height?: number;
  showLabels?: boolean;
  showDots?: boolean;
  animated?: boolean;
}

const MiniAreaChart: React.FC<MiniAreaChartProps> = ({
  data,
  color,
  height = 60,
  showLabels = false,
  showDots = true,
  animated = true,
}) => {
  const { token } = useToken();
  const chartColor = color || token.colorPrimary;

  const chartData = useMemo(() => {
    if (!data || data.length < 2) return null;

    const values = data.map(d => d.value);
    const max = Math.max(...values);
    const min = Math.min(...values);
    const range = max - min || 1;
    
    const width = 200;
    const padding = 10;
    const chartWidth = width - padding * 2;
    const chartHeight = height - (showLabels ? 20 : 0) - padding;

    const points = data.map((d, i) => ({
      x: padding + (i / (data.length - 1)) * chartWidth,
      y: padding + chartHeight - ((d.value - min) / range) * chartHeight,
      value: d.value,
      label: d.label,
    }));

    const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    
    const areaPath = `${linePath} L ${points[points.length - 1].x} ${padding + chartHeight} L ${points[0].x} ${padding + chartHeight} Z`;

    return { points, linePath, areaPath, max, min };
  }, [data, height, showLabels]);

  if (!chartData) {
    return (
      <div style={{ 
        width: '100%', 
        height, 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        color: token.colorTextSecondary,
        fontSize: 12,
      }}>
        No data
      </div>
    );
  }

  const gradientId = `area-gradient-${chartColor.replace('#', '')}`;

  return (
    <svg width="100%" height={height} viewBox={`0 0 200 ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={chartColor} stopOpacity={0.4} />
          <stop offset="100%" stopColor={chartColor} stopOpacity={0.05} />
        </linearGradient>
      </defs>

      {/* Area fill */}
      <path
        d={chartData.areaPath}
        fill={`url(#${gradientId})`}
        style={{
          animation: animated ? 'fadeIn 0.5s ease-out' : undefined,
        }}
      />

      {/* Line */}
      <path
        d={chartData.linePath}
        fill="none"
        stroke={chartColor}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{
          animation: animated ? 'drawLine 1s ease-out forwards' : undefined,
          strokeDasharray: animated ? 500 : undefined,
          strokeDashoffset: animated ? 500 : undefined,
        }}
      />

      {/* Dots */}
      {showDots && chartData.points.map((point, i) => (
        <g key={i}>
          {/* Glow */}
          <circle
            cx={point.x}
            cy={point.y}
            r={6}
            fill={chartColor}
            opacity={0.2}
          />
          {/* Dot */}
          <circle
            cx={point.x}
            cy={point.y}
            r={3}
            fill={chartColor}
            style={{
              animation: animated ? `popIn 0.3s ease-out ${i * 0.05}s forwards` : undefined,
              opacity: animated ? 0 : 1,
            }}
          />
        </g>
      ))}

      {/* Labels */}
      {showLabels && chartData.points.filter((_, i) => i === 0 || i === chartData.points.length - 1).map((point, i) => (
        <text
          key={i}
          x={point.x}
          y={height - 5}
          textAnchor={i === 0 ? 'start' : 'end'}
          fill={token.colorTextSecondary}
          fontSize={9}
        >
          {point.label}
        </text>
      ))}

      <style>{`
        @keyframes drawLine {
          to {
            stroke-dashoffset: 0;
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes popIn {
          from { 
            opacity: 0; 
            transform: scale(0);
          }
          to { 
            opacity: 1; 
            transform: scale(1);
          }
        }
      `}</style>
    </svg>
  );
};

export default MiniAreaChart;
