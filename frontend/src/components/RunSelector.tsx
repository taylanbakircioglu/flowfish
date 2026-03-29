/**
 * Run Selector Component
 * 
 * Allows users to filter change events by analysis run.
 * Feature flag controlled: RUN_BASED_FILTERING_ENABLED
 * 
 * Features:
 * - Select all runs or specific runs
 * - Shows run status (running, completed, stopped)
 * - Shows changes count per run
 */

import React, { useMemo } from 'react';
import { Select, Tag, Space, Typography, Tooltip, Badge, Spin } from 'antd';
import {
  PlayCircleOutlined,
  CheckCircleOutlined,
  StopOutlined,
  ClockCircleOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;

interface AnalysisRun {
  run_id: number;
  run_number: number;
  status: 'running' | 'completed' | 'stopped' | 'failed';
  start_time: string;
  end_time?: string;
  changes_detected?: number;
  duration_seconds?: number;
}

interface RunSelectorProps {
  analysisId: number;
  runs: AnalysisRun[];
  selectedRunIds: number[];
  onRunSelect: (runIds: number[]) => void;
  loading?: boolean;
  showAll?: boolean;
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  running: { color: '#0891b2', icon: <PlayCircleOutlined />, label: 'Running' },
  completed: { color: '#4d9f7c', icon: <CheckCircleOutlined />, label: 'Completed' },
  stopped: { color: '#c9a55a', icon: <StopOutlined />, label: 'Stopped' },
  failed: { color: '#c75450', icon: <StopOutlined />, label: 'Failed' },
};

const RunSelector: React.FC<RunSelectorProps> = ({
  analysisId,
  runs,
  selectedRunIds,
  onRunSelect,
  loading = false,
  showAll = true,
}) => {
  // Format duration
  const formatDuration = (seconds?: number): string => {
    if (!seconds) return '-';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  // Sort runs by run_number descending (newest first)
  const sortedRuns = useMemo(() => {
    return [...runs].sort((a, b) => b.run_number - a.run_number);
  }, [runs]);

  // Handle selection change - uses any[] to avoid Ant Design typing issues
  const handleChange = (values: any[]) => {
    if (values.includes('all')) {
      // If "all" is selected, clear specific selections
      onRunSelect([]);
    } else {
      onRunSelect(values.filter((v: any): v is number => typeof v === 'number'));
    }
  };

  // Build current value for Select - uses any[] to avoid Ant Design typing issues
  const currentValue: any[] = useMemo(() => {
    if (selectedRunIds.length === 0) {
      return ['all'];
    }
    return selectedRunIds;
  }, [selectedRunIds]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <HistoryOutlined />
        <Text>Run Filter:</Text>
        <Spin size="small" />
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <HistoryOutlined />
        <Text type="secondary">No runs available</Text>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <HistoryOutlined />
      <Text>Run Filter:</Text>
      <Select
        mode="multiple"
        style={{ minWidth: 250 }}
        placeholder="Select runs..."
        value={currentValue}
        onChange={handleChange}
        maxTagCount={2}
        maxTagPlaceholder={(omittedValues) => `+${omittedValues.length} more`}
        optionLabelProp="label"
      >
        {showAll && (
          <Select.Option value="all" label="All Runs">
            <Space>
              <ClockCircleOutlined />
              <Text strong>All Runs</Text>
              <Text type="secondary">({runs.length} total)</Text>
            </Space>
          </Select.Option>
        )}
        
        {sortedRuns.map((run) => {
          const status = statusConfig[run.status] || statusConfig.completed;
          const startTime = dayjs(run.start_time);
          
          return (
            <Select.Option 
              key={run.run_id} 
              value={run.run_id}
              label={`Run #${run.run_number}`}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <Tag color={status.color} icon={status.icon}>
                    Run #{run.run_number}
                  </Tag>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {startTime.format('MMM D, HH:mm')}
                  </Text>
                </Space>
                <Space>
                  {run.changes_detected !== undefined && (
                    <Tooltip title="Changes detected">
                      <Badge 
                        count={run.changes_detected} 
                        style={{ backgroundColor: run.changes_detected > 0 ? '#0891b2' : '#d9d9d9' }}
                        showZero
                      />
                    </Tooltip>
                  )}
                  {run.duration_seconds && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {formatDuration(run.duration_seconds)}
                    </Text>
                  )}
                </Space>
              </div>
            </Select.Option>
          );
        })}
      </Select>
    </div>
  );
};

export default RunSelector;
