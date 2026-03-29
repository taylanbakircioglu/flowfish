import React, { useState, useMemo } from 'react';
import { theme, Tooltip, Typography } from 'antd';

const { useToken } = theme;
const { Text } = Typography;

interface DonutSegment {
  label: string;
  value: number;
  color?: string;
}

interface DonutChartProps {
  data: DonutSegment[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
  animated?: boolean;
  showLegend?: boolean;
}

const defaultColors = [
  '#0891b2', '#4d9f7c', '#7c8eb5', '#b89b5d', '#22a6a6',
  '#c75450', '#a67c9e', '#c9a55a', '#69b1ff', '#8fa855',
];

const DonutChart: React.FC<DonutChartProps> = ({
  data,
  size = 160,
  thickness = 20,
  centerLabel,
  centerValue,
  animated = true,
  showLegend = true,
}) => {
  const { token } = useToken();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const chartData = useMemo(() => {
    const total = data.reduce((sum, d) => sum + d.value, 0);
    if (total === 0) return [];

    let currentAngle = -90; // Start from top
    
    return data.map((segment, index) => {
      const percentage = (segment.value / total) * 100;
      const angle = (percentage / 100) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angle;
      currentAngle = endAngle;

      const color = segment.color || defaultColors[index % defaultColors.length];

      // Calculate arc path
      const radius = (size - thickness) / 2;
      const centerX = size / 2;
      const centerY = size / 2;

      const startRad = (startAngle * Math.PI) / 180;
      const endRad = (endAngle * Math.PI) / 180;

      const x1 = centerX + radius * Math.cos(startRad);
      const y1 = centerY + radius * Math.sin(startRad);
      const x2 = centerX + radius * Math.cos(endRad);
      const y2 = centerY + radius * Math.sin(endRad);

      const largeArc = angle > 180 ? 1 : 0;

      const path = `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`;

      return {
        ...segment,
        percentage,
        color,
        path,
        startAngle,
        endAngle,
      };
    });
  }, [data, size, thickness]);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  if (chartData.length === 0) {
    return (
      <div style={{ 
        width: size, 
        height: size, 
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
      <svg 
        width={size} 
        height={size} 
        style={{ overflow: 'visible' }}
      >
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={(size - thickness) / 2}
          fill="none"
          stroke={token.colorBorderSecondary}
          strokeWidth={thickness}
        />

        {/* Segments */}
        {chartData.map((segment, index) => {
          const isHovered = hoveredIndex === index;
          const scale = isHovered ? 1.05 : 1;
          
          return (
            <Tooltip
              key={index}
              title={
                <div>
                  <div style={{ fontWeight: 600 }}>{segment.label}</div>
                  <div>{segment.value.toLocaleString()} ({segment.percentage.toFixed(1)}%)</div>
                </div>
              }
            >
              <path
                d={segment.path}
                fill="none"
                stroke={segment.color}
                strokeWidth={isHovered ? thickness + 4 : thickness}
                strokeLinecap="round"
                style={{
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  transform: `scale(${scale})`,
                  transformOrigin: 'center',
                  animation: animated ? `drawArc 0.8s ease-out ${index * 0.1}s forwards` : undefined,
                  strokeDasharray: animated ? 1000 : undefined,
                  strokeDashoffset: animated ? 1000 : undefined,
                  filter: isHovered ? `drop-shadow(0 0 8px ${segment.color})` : undefined,
                }}
                onMouseEnter={() => setHoveredIndex(index)}
                onMouseLeave={() => setHoveredIndex(null)}
              />
            </Tooltip>
          );
        })}

        {/* Center content */}
        <g>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={(size - thickness * 2) / 2 - 5}
            fill={token.colorBgContainer}
          />
          {centerValue !== undefined && (
            <text
              x={size / 2}
              y={size / 2 - 5}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={token.colorText}
              fontSize={24}
              fontWeight={700}
            >
              {centerValue}
            </text>
          )}
          {centerLabel && (
            <text
              x={size / 2}
              y={size / 2 + 15}
              textAnchor="middle"
              dominantBaseline="middle"
              fill={token.colorTextSecondary}
              fontSize={11}
            >
              {centerLabel}
            </text>
          )}
        </g>

        <style>{`
          @keyframes drawArc {
            to {
              stroke-dashoffset: 0;
            }
          }
        `}</style>
      </svg>

      {/* Legend */}
      {showLegend && (
        <div style={{ 
          display: 'flex', 
          flexWrap: 'wrap', 
          gap: 8, 
          justifyContent: 'center',
          maxWidth: size + 40,
        }}>
          {chartData.slice(0, 6).map((segment, index) => (
            <div
              key={index}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 6px',
                borderRadius: 4,
                background: hoveredIndex === index ? `${segment.color}15` : 'transparent',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
            >
              <div style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: segment.color,
              }} />
              <Text style={{ fontSize: 10 }} ellipsis>
                {segment.label}
              </Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default DonutChart;
