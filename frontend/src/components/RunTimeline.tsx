/**
 * Run Timeline Component
 * 
 * Visualizes analysis run periods and detected changes over time.
 * Shows when analysis was running vs stopped (gaps).
 * 
 * Feature flag controlled: RUN_BASED_FILTERING_ENABLED
 */

import React, { useMemo } from 'react';
import { Timeline, Card, Typography, Tag, Space, Tooltip, Badge, Empty } from 'antd';
import {
  PlayCircleOutlined,
  StopOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text, Title } = Typography;

interface RunPeriod {
  run_id: number;
  run_number: number;
  status: 'running' | 'completed' | 'stopped' | 'failed';
  start_time: string;
  end_time?: string;
  changes_detected?: number;
  critical_count?: number;
  high_count?: number;
}

interface RunTimelineProps {
  runs: RunPeriod[];
  onRunSelect?: (runId: number) => void;
  selectedRunId?: number;
  showGaps?: boolean;
  maxRuns?: number;
}

const statusColors: Record<string, string> = {
  running: 'green',
  completed: 'blue',
  stopped: 'orange',
  failed: 'red',
};

const statusIcons: Record<string, React.ReactNode> = {
  running: <PlayCircleOutlined />,
  completed: <CheckCircleOutlined />,
  stopped: <StopOutlined />,
  failed: <ExclamationCircleOutlined />,
};

const RunTimeline: React.FC<RunTimelineProps> = ({
  runs,
  onRunSelect,
  selectedRunId,
  showGaps = true,
  maxRuns = 10,
}) => {
  // Sort runs by start time descending
  const sortedRuns = useMemo(() => {
    return [...runs]
      .sort((a, b) => dayjs(b.start_time).valueOf() - dayjs(a.start_time).valueOf())
      .slice(0, maxRuns);
  }, [runs, maxRuns]);

  // Build timeline items with optional gaps
  const timelineItems = useMemo(() => {
    const items: React.ReactNode[] = [];
    
    sortedRuns.forEach((run, index) => {
      const startTime = dayjs(run.start_time);
      const endTime = run.end_time ? dayjs(run.end_time) : null;
      const isSelected = selectedRunId === run.run_id;
      
      // Calculate duration
      const duration = endTime 
        ? endTime.diff(startTime, 'minute')
        : dayjs().diff(startTime, 'minute');
      
      // Format duration
      const formatDuration = (minutes: number): string => {
        if (minutes < 60) return `${minutes}m`;
        return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
      };

      // Check for gap before this run
      if (showGaps && index < sortedRuns.length - 1) {
        const prevRun = sortedRuns[index + 1];
        const prevEnd = prevRun.end_time ? dayjs(prevRun.end_time) : dayjs(prevRun.start_time);
        const gapMinutes = startTime.diff(prevEnd, 'minute');
        
        if (gapMinutes > 5) {
          items.push(
            <Timeline.Item 
              key={`gap-${run.run_id}`}
              color="gray"
              dot={<ClockCircleOutlined style={{ color: '#d9d9d9' }} />}
            >
              <Text type="secondary" style={{ fontSize: 12 }}>
                Analysis paused for {formatDuration(gapMinutes)}
              </Text>
            </Timeline.Item>
          );
        }
      }

      // Add run item
      items.push(
        <Timeline.Item
          key={run.run_id}
          color={statusColors[run.status]}
          dot={statusIcons[run.status]}
        >
          <Card
            size="small"
            style={{
              cursor: onRunSelect ? 'pointer' : 'default',
              borderColor: isSelected ? '#0891b2' : undefined,
              backgroundColor: isSelected ? '#f0f7ff' : undefined,
            }}
            onClick={() => onRunSelect?.(run.run_id)}
          >
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space>
                  <Tag color={statusColors[run.status]}>
                    Run #{run.run_number}
                  </Tag>
                  <Tag color="default">{run.status}</Tag>
                </Space>
                
                {run.changes_detected !== undefined && run.changes_detected > 0 && (
                  <Tooltip title={`${run.changes_detected} changes detected`}>
                    <Badge 
                      count={run.changes_detected}
                      style={{ backgroundColor: '#0891b2' }}
                    />
                  </Tooltip>
                )}
              </Space>
              
              <Space split={<Text type="secondary">|</Text>}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {startTime.format('MMM D, HH:mm')}
                </Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {formatDuration(duration)}
                </Text>
              </Space>
              
              {(run.critical_count || run.high_count) && (
                <Space>
                  {run.critical_count && run.critical_count > 0 && (
                    <Tooltip title="Critical changes">
                      <Tag color="red" icon={<ExclamationCircleOutlined />}>
                        {run.critical_count} Critical
                      </Tag>
                    </Tooltip>
                  )}
                  {run.high_count && run.high_count > 0 && (
                    <Tooltip title="High risk changes">
                      <Tag color="orange" icon={<WarningOutlined />}>
                        {run.high_count} High
                      </Tag>
                    </Tooltip>
                  )}
                </Space>
              )}
            </Space>
          </Card>
        </Timeline.Item>
      );
    });
    
    return items;
  }, [sortedRuns, selectedRunId, onRunSelect, showGaps]);

  if (runs.length === 0) {
    return (
      <Card size="small">
        <Empty 
          description="No analysis runs available"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  return (
    <Card 
      size="small"
      title={
        <Space>
          <ClockCircleOutlined />
          <Text strong>Analysis Run Timeline</Text>
          <Text type="secondary">({runs.length} runs)</Text>
        </Space>
      }
    >
      <Timeline mode="left" style={{ marginTop: 16 }}>
        {timelineItems}
      </Timeline>
      
      {runs.length > maxRuns && (
        <Text type="secondary" style={{ display: 'block', textAlign: 'center', marginTop: 8 }}>
          Showing {maxRuns} of {runs.length} runs
        </Text>
      )}
    </Card>
  );
};

export default RunTimeline;
