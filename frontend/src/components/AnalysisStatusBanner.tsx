/**
 * Analysis Status Banner Component
 * 
 * Displays the current status of the selected analysis prominently.
 * Shows whether analysis is running, stopped, or paused.
 * 
 * Feature flag controlled: RUN_BASED_FILTERING_ENABLED
 */

import React from 'react';
import { Alert, Space, Typography, Tag, Button, Tooltip } from 'antd';
import {
  PlayCircleOutlined,
  PauseCircleOutlined,
  StopOutlined,
  ClockCircleOutlined,
  InfoCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

const { Text } = Typography;

interface AnalysisStatusBannerProps {
  analysisId?: number;
  analysisName?: string;
  status?: 'running' | 'stopped' | 'paused' | 'completed' | 'draft';
  startedAt?: string;
  stoppedAt?: string;
  currentRunNumber?: number;
  totalRuns?: number;
  onStartAnalysis?: () => void;
  onStopAnalysis?: () => void;
  compact?: boolean;
}

const statusConfig: Record<string, { 
  type: 'success' | 'warning' | 'info' | 'error';
  icon: React.ReactNode;
  label: string;
  description: string;
}> = {
  running: {
    type: 'success',
    icon: <PlayCircleOutlined />,
    label: 'Analysis Running',
    description: 'Changes are being detected in real-time',
  },
  stopped: {
    type: 'warning',
    icon: <StopOutlined />,
    label: 'Analysis Stopped',
    description: 'No new changes are being detected',
  },
  paused: {
    type: 'info',
    icon: <PauseCircleOutlined />,
    label: 'Analysis Paused',
    description: 'Analysis temporarily paused',
  },
  completed: {
    type: 'info',
    icon: <ClockCircleOutlined />,
    label: 'Analysis Completed',
    description: 'Fixed duration analysis has completed',
  },
  draft: {
    type: 'info',
    icon: <InfoCircleOutlined />,
    label: 'Analysis Draft',
    description: 'Analysis has not been started yet',
  },
};

const AnalysisStatusBanner: React.FC<AnalysisStatusBannerProps> = ({
  analysisId,
  analysisName,
  status = 'stopped',
  startedAt,
  stoppedAt,
  currentRunNumber,
  totalRuns,
  onStartAnalysis,
  onStopAnalysis,
  compact = false,
}) => {
  if (!analysisId) {
    return (
      <Alert
        message="No Analysis Selected"
        description="Select an analysis to view change detection status"
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        style={{ marginBottom: 16 }}
      />
    );
  }

  const config = statusConfig[status] || statusConfig.stopped;
  
  // Format time
  const formatTime = (time?: string): string => {
    if (!time) return '-';
    return dayjs(time).format('MMM D, YYYY HH:mm:ss');
  };

  // Calculate duration
  const getDuration = (): string => {
    if (!startedAt) return '-';
    const start = dayjs(startedAt);
    const end = stoppedAt ? dayjs(stoppedAt) : dayjs();
    const duration = end.diff(start, 'second');
    
    if (duration < 60) return `${duration}s`;
    if (duration < 3600) return `${Math.floor(duration / 60)}m ${duration % 60}s`;
    return `${Math.floor(duration / 3600)}h ${Math.floor((duration % 3600) / 60)}m`;
  };

  if (compact) {
    return (
      <Space style={{ marginBottom: 8 }}>
        <Tag 
          color={config.type === 'success' ? 'green' : config.type === 'warning' ? 'orange' : 'blue'}
          icon={config.icon}
        >
          {config.label}
        </Tag>
        {currentRunNumber && (
          <Text type="secondary">
            Run #{currentRunNumber} {totalRuns && `of ${totalRuns}`}
          </Text>
        )}
      </Space>
    );
  }

  return (
    <Alert
      message={
        <Space>
          {config.icon}
          <Text strong>{config.label}</Text>
          {analysisName && (
            <Text type="secondary">- {analysisName}</Text>
          )}
        </Space>
      }
      description={
        <div style={{ marginTop: 8 }}>
          <Space direction="vertical" size={4}>
            <Text type="secondary">{config.description}</Text>
            
            <Space split={<Text type="secondary">|</Text>}>
              {startedAt && (
                <Tooltip title="Started at">
                  <Space>
                    <ClockCircleOutlined />
                    <Text type="secondary">Started: {formatTime(startedAt)}</Text>
                  </Space>
                </Tooltip>
              )}
              
              {status === 'running' && (
                <Tooltip title="Current run duration">
                  <Space>
                    <ThunderboltOutlined />
                    <Text type="secondary">Duration: {getDuration()}</Text>
                  </Space>
                </Tooltip>
              )}
              
              {currentRunNumber && (
                <Tooltip title="Current run number">
                  <Text type="secondary">
                    Run #{currentRunNumber} {totalRuns && `(${totalRuns} total)`}
                  </Text>
                </Tooltip>
              )}
            </Space>
          </Space>
        </div>
      }
      type={config.type}
      showIcon
      icon={config.icon}
      style={{ marginBottom: 16 }}
      action={
        <Space>
          {status === 'running' && onStopAnalysis && (
            <Button size="small" onClick={onStopAnalysis}>
              Stop Analysis
            </Button>
          )}
          {(status === 'stopped' || status === 'paused') && onStartAnalysis && (
            <Button size="small" type="primary" onClick={onStartAnalysis}>
              Start Analysis
            </Button>
          )}
        </Space>
      }
    />
  );
};

export default AnalysisStatusBanner;
