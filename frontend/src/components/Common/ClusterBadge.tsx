/**
 * ClusterBadge Component
 * 
 * Displays cluster information in a consistent, visually distinctive badge.
 * Used across all pages for multi-cluster visibility.
 * 
 * Features:
 * - Consistent color palette per cluster
 * - Environment indicator (PROD/STAGING/DEV)
 * - Provider icon (OpenShift/EKS/GKE/AKS)
 * - Tooltip with full details
 * - Copyable cluster name
 * - Responsive sizing
 */

import React, { useMemo } from 'react';
import { Tag, Tooltip, Space, Typography } from 'antd';
import { 
  ClusterOutlined, 
  CloudServerOutlined,
  CopyOutlined 
} from '@ant-design/icons';

const { Text } = Typography;

// Cluster color palette - muted, professional colors matching Ant Design
// Using softer tones that don't draw excessive attention
const CLUSTER_COLORS = [
  { id: 1, border: '#597ef7', bg: '#f0f5ff', text: '#69b1ff', name: 'Blue' },      // Soft geekblue
  { id: 2, border: '#73d13d', bg: '#f6ffed', text: '#389e0d', name: 'Green' },     // Soft green
  { id: 3, border: '#9254de', bg: '#f9f0ff', text: '#7c8eb5', name: 'Purple' },    // Soft purple
  { id: 4, border: '#ffc069', bg: '#fff7e6', text: '#d48806', name: 'Orange' },    // Soft orange
  { id: 5, border: '#85a5ff', bg: '#f0f5ff', text: '#1d39c4', name: 'Indigo' },    // Soft indigo
  { id: 6, border: '#5cdbd3', bg: '#e6fffb', text: '#08979c', name: 'Cyan' },      // Soft cyan
  { id: 7, border: '#ffd666', bg: '#fffbe6', text: '#ad8b00', name: 'Gold' },      // Soft gold
  { id: 8, border: '#95de64', bg: '#f6ffed', text: '#4d9f7c', name: 'Lime' },      // Soft lime
];

// Environment colors - muted, professional palette
// Colors are subtle and don't look like error/warning indicators
const ENVIRONMENT_CONFIG: Record<string, { color: string; label: string }> = {
  production: { color: '#597ef7', label: 'PROD' },  // Soft geekblue - calm, professional
  prod: { color: '#597ef7', label: 'PROD' },
  staging: { color: '#ffc069', label: 'STG' },      // Soft gold/orange
  stage: { color: '#ffc069', label: 'STG' },
  development: { color: '#95de64', label: 'DEV' }, // Soft lime green
  dev: { color: '#95de64', label: 'DEV' },
  test: { color: '#85a5ff', label: 'TEST' },       // Soft blue
  uat: { color: '#b37feb', label: 'UAT' },         // Soft purple
};

// Provider icons/labels - using neutral symbols, avoiding bright colors
const PROVIDER_CONFIG: Record<string, { icon: string; label: string }> = {
  openshift: { icon: '⬡', label: 'OpenShift' },   // Hexagon - OpenShift logo shape
  kubernetes: { icon: '☸', label: 'Kubernetes' }, // Helm wheel
  eks: { icon: '◈', label: 'AWS EKS' },           // Diamond - AWS style
  gke: { icon: '◉', label: 'GCP GKE' },           // Circle - Google style
  aks: { icon: '◇', label: 'Azure AKS' },         // Diamond outline - Azure style
  rancher: { icon: '⚙', label: 'Rancher' },       // Gear
  k3s: { icon: '▲', label: 'K3s' },               // Triangle - lightweight
};

export interface ClusterBadgeProps {
  /** Cluster ID for color assignment */
  clusterId: number | string;
  /** Cluster name to display */
  clusterName?: string;
  /** Environment (production, staging, dev) */
  environment?: string;
  /** Provider (openshift, eks, gke, aks) */
  provider?: string;
  /** Size variant */
  size?: 'small' | 'default' | 'large';
  /** Show environment tag */
  showEnvironment?: boolean;
  /** Show provider icon */
  showProvider?: boolean;
  /** Show full tooltip on hover */
  showTooltip?: boolean;
  /** Allow copying cluster name */
  copyable?: boolean;
  /** Custom style */
  style?: React.CSSProperties;
  /** Click handler */
  onClick?: () => void;
}

/**
 * Get consistent color for a cluster based on its ID
 */
export const getClusterColor = (clusterId: number | string): typeof CLUSTER_COLORS[0] => {
  const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) || 0 : clusterId;
  const index = (id - 1) % CLUSTER_COLORS.length;
  return CLUSTER_COLORS[index >= 0 ? index : 0];
};

/**
 * Get environment config
 */
export const getEnvironmentConfig = (environment?: string) => {
  if (!environment) return null;
  const key = environment.toLowerCase();
  return ENVIRONMENT_CONFIG[key] || { color: '#8c8c8c', label: environment.toUpperCase().slice(0, 4) };
};

/**
 * Get provider config
 */
export const getProviderConfig = (provider?: string) => {
  if (!provider) return null;
  const key = provider.toLowerCase();
  return PROVIDER_CONFIG[key] || { icon: '☸️', label: provider };
};

const ClusterBadge: React.FC<ClusterBadgeProps> = ({
  clusterId,
  clusterName,
  environment,
  provider,
  size = 'default',
  showEnvironment = true,
  showProvider = true,
  showTooltip = true,
  copyable = false,
  style,
  onClick,
}) => {
  const color = useMemo(() => getClusterColor(clusterId), [clusterId]);
  const envConfig = useMemo(() => getEnvironmentConfig(environment), [environment]);
  const providerConfig = useMemo(() => getProviderConfig(provider), [provider]);

  const displayName = clusterName || `Cluster ${clusterId}`;
  
  // Size configurations
  const sizeConfig = {
    small: { fontSize: 10, padding: '0 4px', iconSize: 10 },
    default: { fontSize: 12, padding: '2px 8px', iconSize: 12 },
    large: { fontSize: 14, padding: '4px 12px', iconSize: 14 },
  };
  const config = sizeConfig[size];

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(displayName);
  };

  const badge = (
    <Tag
      style={{
        background: color.bg,
        borderColor: color.border,
        color: color.text,
        fontSize: config.fontSize,
        padding: config.padding,
        margin: 0,
        cursor: onClick ? 'pointer' : 'default',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        ...style,
      }}
      onClick={onClick}
    >
      {/* Provider Icon */}
      {showProvider && providerConfig && (
        <span style={{ fontSize: config.iconSize }}>{providerConfig.icon}</span>
      )}
      
      {/* Cluster Icon (fallback) */}
      {(!showProvider || !providerConfig) && (
        <ClusterOutlined style={{ fontSize: config.iconSize }} />
      )}
      
      {/* Cluster Name */}
      <span>{displayName}</span>
      
      {/* Environment Badge */}
      {showEnvironment && envConfig && (
        <Tag
          style={{
            fontSize: config.fontSize - 2,
            padding: '0 3px',
            margin: 0,
            marginLeft: 2,
            lineHeight: '14px',
            background: envConfig.color,
            borderColor: envConfig.color,
            color: '#fff',
          }}
        >
          {envConfig.label}
        </Tag>
      )}
      
      {/* Copy Button */}
      {copyable && (
        <CopyOutlined 
          style={{ 
            fontSize: config.iconSize - 2, 
            opacity: 0.6,
            cursor: 'pointer',
          }} 
          onClick={handleCopy}
        />
      )}
    </Tag>
  );

  if (!showTooltip) {
    return badge;
  }

  // Tooltip content
  const tooltipContent = (
    <Space direction="vertical" size={4}>
      <Text strong style={{ color: '#fff' }}>{displayName}</Text>
      {environment && (
        <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 11 }}>
          Environment: {environment}
        </Text>
      )}
      {provider && (
        <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 11 }}>
          Provider: {providerConfig?.label || provider}
        </Text>
      )}
      <Text style={{ color: 'rgba(255,255,255,0.65)', fontSize: 10 }}>
        ID: {clusterId}
      </Text>
    </Space>
  );

  return (
    <Tooltip title={tooltipContent} placement="top">
      {badge}
    </Tooltip>
  );
};

export default ClusterBadge;

// Re-export utilities for use in other components
export { CLUSTER_COLORS, ENVIRONMENT_CONFIG, PROVIDER_CONFIG };

