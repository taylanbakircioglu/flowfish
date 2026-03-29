/**
 * DatabaseSelector Component - Database, Analysis, and Cluster selection
 * 
 * Features:
 * - Database type selection (ClickHouse / Neo4j)
 * - Multi-select Analysis filter
 * - Optional Cluster filter (shows clusters from selected analyses)
 */

import React, { useMemo, useEffect } from 'react';
import { Select, Space, Typography, Tag, Tooltip } from 'antd';
import { DatabaseOutlined, ExperimentOutlined, ClusterOutlined } from '@ant-design/icons';
import { DatabaseType } from '../../store/api/devConsoleApi';
import { useGetAnalysesQuery } from '../../store/api/analysisApi';
import { useGetClustersQuery } from '../../store/api/clusterApi';

const { Text } = Typography;

// Analysis type from API (local definition to avoid conflicts)
interface AnalysisItem {
  id: number;
  name: string;
  cluster_id: number;
  cluster_name?: string;
  cluster_ids?: number[];
  is_multi_cluster?: boolean;
}

// Cluster type from API
interface ClusterItem {
  id: number;
  name: string;
}

interface DatabaseSelectorProps {
  database: DatabaseType;
  onDatabaseChange: (db: DatabaseType) => void;
  analysisIds: string[];
  onAnalysisChange: (ids: string[]) => void;
  clusterIds: string[];
  onClusterChange: (ids: string[]) => void;
}

const DatabaseSelector: React.FC<DatabaseSelectorProps> = ({
  database,
  onDatabaseChange,
  analysisIds,
  onAnalysisChange,
  clusterIds,
  onClusterChange,
}) => {
  // Fetch all analyses
  const { data: analyses = [], isLoading: analysesLoading } = useGetAnalysesQuery({});
  
  // Fetch all clusters
  const { data: clusters = [], isLoading: clustersLoading } = useGetClustersQuery();

  // Get available clusters based on selected analyses
  const availableClusters = useMemo(() => {
    if (analysisIds.length === 0) {
      return [];
    }

    // Collect all cluster IDs from selected analyses
    const clusterIdSet = new Set<number>();
    const analysisList = analyses as AnalysisItem[];
    
    analysisIds.forEach(analysisId => {
      const analysis = analysisList.find((a) => String(a.id) === analysisId);
      if (analysis) {
        // Add primary cluster
        clusterIdSet.add(analysis.cluster_id);
        
        // Add multi-cluster IDs if present
        if (analysis.cluster_ids && analysis.cluster_ids.length > 0) {
          analysis.cluster_ids.forEach((cid: number) => clusterIdSet.add(cid));
        }
      }
    });

    // Filter clusters that are in the set
    const clusterList = (Array.isArray(clusters) ? clusters : []) as ClusterItem[];
    return clusterList.filter((c) => clusterIdSet.has(c.id));
  }, [analysisIds, analyses, clusters]);

  // Clear cluster selection when no clusters available
  useEffect(() => {
    if (availableClusters.length === 0 && clusterIds.length > 0) {
      onClusterChange([]);
    }
  }, [availableClusters.length, clusterIds.length, onClusterChange]);

  // Clear cluster selection if selected clusters are no longer available
  useEffect(() => {
    if (clusterIds.length > 0) {
      const availableClusterIdSet = new Set(availableClusters.map((c) => String(c.id)));
      const validClusterIds = clusterIds.filter(id => availableClusterIdSet.has(id));
      if (validClusterIds.length !== clusterIds.length) {
        onClusterChange(validClusterIds);
      }
    }
  }, [availableClusters, clusterIds, onClusterChange]);

  return (
    <Space size="middle" wrap>
      {/* Database Selection */}
      <Space size={4}>
        <DatabaseOutlined style={{ color: '#8c8c8c' }} />
        <Text type="secondary">Database:</Text>
        <Select
          value={database}
          onChange={onDatabaseChange}
          style={{ width: 140 }}
          options={[
            { 
              value: 'clickhouse', 
              label: (
                <Space>
                  <span style={{ 
                    width: 8, 
                    height: 8, 
                    borderRadius: '50%', 
                    background: '#0891b2',
                    display: 'inline-block',
                  }} />
                  TimeSeries
                </Space>
              ),
            },
            { 
              value: 'neo4j', 
              label: (
                <Space>
                  <span style={{ 
                    width: 8, 
                    height: 8, 
                    borderRadius: '50%', 
                    background: '#4d9f7c',
                    display: 'inline-block',
                  }} />
                  Graph
                </Space>
              ),
            },
          ]}
        />
      </Space>

      {/* Multi-select Analysis Filter */}
      <Space size={4}>
        <ExperimentOutlined style={{ color: '#8c8c8c' }} />
        <Text type="secondary">Analysis:</Text>
        <Select
          mode="multiple"
          value={analysisIds}
          onChange={onAnalysisChange}
          style={{ minWidth: 280, maxWidth: 500 }}
          placeholder="Select analysis..."
          loading={analysesLoading}
          showSearch
          optionFilterProp="label"
          maxTagCount={2}
          maxTagPlaceholder={(omittedValues) => (
            <Tag>+{omittedValues.length} more</Tag>
          )}
          options={(analyses as AnalysisItem[]).map((analysis) => ({
            value: String(analysis.id),
            label: `${analysis.name} (${analysis.cluster_name || 'Unknown'})`,
          }))}
        />
      </Space>

      {/* Optional Cluster Filter - Only shown when analyses are selected */}
      {availableClusters.length > 0 && (
        <Space size={4}>
          <ClusterOutlined style={{ color: '#8c8c8c' }} />
          <Text type="secondary">Cluster:</Text>
          <Tooltip title="Filter by specific cluster(s). Leave empty to query all clusters.">
            <Select
              mode="multiple"
              value={clusterIds}
              onChange={onClusterChange}
              style={{ minWidth: 200, maxWidth: 400 }}
              placeholder="All clusters"
              loading={clustersLoading}
              showSearch
              optionFilterProp="label"
              allowClear
              maxTagCount={2}
              maxTagPlaceholder={(omittedValues) => (
                <Tag>+{omittedValues.length} more</Tag>
              )}
              options={availableClusters.map((cluster) => ({
                value: String(cluster.id),
                label: cluster.name,
              }))}
            />
          </Tooltip>
        </Space>
      )}
    </Space>
  );
};

export default DatabaseSelector;
