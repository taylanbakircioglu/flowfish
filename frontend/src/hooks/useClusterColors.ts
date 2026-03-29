/**
 * useClusterColors Hook
 * 
 * Provides consistent cluster color mapping across all pages.
 * Uses the same color palette as ClusterBadge for visual consistency.
 */

import { useMemo, useCallback } from 'react';
import { useGetClustersQuery } from '../store/api/clusterApi';

// Same color palette as ClusterBadge - muted, professional colors
const CLUSTER_COLORS = [
  { border: '#597ef7', bg: 'rgba(89, 126, 247, 0.08)', text: '#69b1ff', name: 'Blue' },
  { border: '#73d13d', bg: 'rgba(115, 209, 61, 0.08)', text: '#389e0d', name: 'Green' },
  { border: '#9254de', bg: 'rgba(146, 84, 222, 0.08)', text: '#7c8eb5', name: 'Purple' },
  { border: '#ffc069', bg: 'rgba(255, 192, 105, 0.08)', text: '#d48806', name: 'Orange' },
  { border: '#85a5ff', bg: 'rgba(133, 165, 255, 0.08)', text: '#1d39c4', name: 'Indigo' },
  { border: '#5cdbd3', bg: 'rgba(92, 219, 211, 0.08)', text: '#08979c', name: 'Cyan' },
  { border: '#ffd666', bg: 'rgba(255, 214, 102, 0.08)', text: '#ad8b00', name: 'Gold' },
  { border: '#95de64', bg: 'rgba(149, 222, 100, 0.08)', text: '#4d9f7c', name: 'Lime' },
];

// Environment short labels
const ENVIRONMENT_LABELS: Record<string, string> = {
  production: 'PROD',
  prod: 'PROD',
  staging: 'STG',
  stage: 'STG',
  development: 'DEV',
  dev: 'DEV',
  test: 'TEST',
  uat: 'UAT',
};

export interface ClusterColorInfo {
  border: string;
  bg: string;
  text: string;
  name: string;
}

export interface ClusterInfo {
  id: number;
  name: string;
  environment?: string;
  provider?: string;
  color: ClusterColorInfo;
  shortLabel: string;  // e.g., "[PROD]" or cluster abbreviation
}

/**
 * Hook for consistent cluster colors and information
 */
export const useClusterColors = () => {
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];

  /**
   * Get color for a cluster ID
   */
  const getColor = useCallback((clusterId: number | string): ClusterColorInfo => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) || 0 : clusterId;
    const index = (id - 1) % CLUSTER_COLORS.length;
    return CLUSTER_COLORS[index >= 0 ? index : 0];
  }, []);

  /**
   * Get cluster name from ID
   */
  const getClusterName = useCallback((clusterId: number | string): string => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) : clusterId;
    const cluster = clusters.find((c: any) => c.id === id);
    return cluster?.name || `Cluster ${clusterId}`;
  }, [clusters]);

  /**
   * Get cluster environment from ID
   */
  const getClusterEnvironment = useCallback((clusterId: number | string): string | undefined => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) : clusterId;
    const cluster = clusters.find((c: any) => c.id === id);
    return cluster?.environment;
  }, [clusters]);

  /**
   * Get cluster provider from ID
   */
  const getClusterProvider = useCallback((clusterId: number | string): string | undefined => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) : clusterId;
    const cluster = clusters.find((c: any) => c.id === id);
    return cluster?.provider;
  }, [clusters]);

  /**
   * Get short label for multi-cluster display (e.g., "[PROD]" or "int-prod")
   */
  const getShortLabel = useCallback((clusterId: number | string): string => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) : clusterId;
    const cluster = clusters.find((c: any) => c.id === id);
    
    if (!cluster) return `C${clusterId}`;
    
    // Prefer environment label if available
    if (cluster.environment) {
      const envLabel = ENVIRONMENT_LABELS[cluster.environment.toLowerCase()];
      if (envLabel) return envLabel;
    }
    
    // Otherwise abbreviate cluster name (first 8 chars)
    const name = cluster.name || `Cluster ${clusterId}`;
    if (name.length <= 8) return name;
    return name.substring(0, 8) + '…';
  }, [clusters]);

  /**
   * Get full cluster info
   */
  const getClusterInfo = useCallback((clusterId: number | string): ClusterInfo | null => {
    const id = typeof clusterId === 'string' ? parseInt(clusterId, 10) : clusterId;
    const cluster = clusters.find((c: any) => c.id === id);
    
    if (!cluster) return null;
    
    return {
      id: cluster.id,
      name: cluster.name,
      environment: cluster.environment,
      provider: cluster.provider,
      color: getColor(clusterId),
      shortLabel: getShortLabel(clusterId),
    };
  }, [clusters, getColor, getShortLabel]);

  /**
   * Build cluster ID to info map for O(1) lookups
   */
  const clusterMap = useMemo(() => {
    const map: Record<number, ClusterInfo> = {};
    clusters.forEach((c: any) => {
      map[c.id] = {
        id: c.id,
        name: c.name,
        environment: c.environment,
        provider: c.provider,
        color: getColor(c.id),
        shortLabel: getShortLabel(c.id),
      };
    });
    return map;
  }, [clusters, getColor, getShortLabel]);

  return {
    // Data
    clusters,
    clusterMap,
    
    // Functions
    getColor,
    getClusterName,
    getClusterEnvironment,
    getClusterProvider,
    getShortLabel,
    getClusterInfo,
    
    // Constants
    CLUSTER_COLORS,
    ENVIRONMENT_LABELS,
  };
};

export default useClusterColors;

