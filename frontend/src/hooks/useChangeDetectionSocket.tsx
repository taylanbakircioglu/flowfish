/**
 * useChangeDetectionSocket Hook
 * 
 * Provides real-time updates for change detection via WebSocket.
 * Connects to /ws/changes endpoint and broadcasts new changes to the UI.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { notification, Button, Space, Tag } from 'antd';
import { 
  ExclamationCircleOutlined, 
  SwapOutlined, 
  EyeOutlined,
  WarningOutlined 
} from '@ant-design/icons';

// Message types from WebSocket
interface ChangeDetectedMessage {
  type: 'change_detected';
  analysis_id: number;
  change_type: string;
  target: string;
  namespace: string;
  risk_level: string;
  details: string;
  affected_services: number;
  timestamp: string;
}

interface CriticalChangeMessage {
  type: 'critical_change';
  analysis_id: number;
  change: {
    change_type: string;
    target: string;
    namespace: string;
    risk_level: string;
    details: string;
    timestamp: string;
  };
}

interface StatsUpdateMessage {
  type: 'change_stats_update';
  analysis_id: number;
  stats: {
    total_changes: number;
    by_type: Record<string, number>;
    by_risk: Record<string, number>;
  };
}

type WebSocketMessage = 
  | ChangeDetectedMessage 
  | CriticalChangeMessage 
  | StatsUpdateMessage 
  | { type: 'connected' | 'pong'; [key: string]: any };

// Risk level colors
const riskColors: Record<string, string> = {
  critical: '#cf1322',
  high: '#c75450',
  medium: '#b89b5d',
  low: '#4d9f7c',
};

// Change type labels
const changeTypeLabels: Record<string, string> = {
  workload_added: 'Workload Added',
  workload_removed: 'Workload Removed',
  connection_added: 'Connection Added',
  connection_removed: 'Connection Anomaly',
  port_changed: 'Port Changed',
  config_changed: 'Config Changed',
  namespace_changed: 'Namespace Changed',
  replica_changed: 'Replica Changed',
};

interface UseChangeDetectionSocketOptions {
  /** Whether the socket should be connected */
  enabled?: boolean;
  /** Analysis ID to filter changes (optional) */
  analysisId?: number;
  /** Callback when a new change is detected */
  onChangeDetected?: (change: ChangeDetectedMessage) => void;
  /** Callback when a critical change is detected */
  onCriticalChange?: (change: CriticalChangeMessage) => void;
  /** Callback when stats are updated */
  onStatsUpdate?: (stats: StatsUpdateMessage) => void;
  /** Whether to show notifications for new changes */
  showNotifications?: boolean;
  /** Callback to view change details */
  onViewChange?: (changeId: number) => void;
}

export const useChangeDetectionSocket = (options: UseChangeDetectionSocketOptions = {}) => {
  const {
    enabled = true,
    analysisId,
    onChangeDetected,
    onCriticalChange,
    onStatsUpdate,
    showNotifications = true,
    onViewChange,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  // Show notification for critical changes
  const showCriticalNotification = useCallback((change: CriticalChangeMessage) => {
    const { change: changeData, analysis_id } = change;
    
    notification.error({
      key: `critical-change-${Date.now()}`,
      message: (
        <Space>
          <ExclamationCircleOutlined style={{ color: riskColors.critical }} />
          <span>Critical Change Detected</span>
        </Space>
      ),
      description: (
        <div>
          <div style={{ marginBottom: 8 }}>
            <Tag color={riskColors.critical}>
              {changeTypeLabels[changeData.change_type] || changeData.change_type}
            </Tag>
          </div>
          <div><strong>Target:</strong> {changeData.target}</div>
          <div><strong>Namespace:</strong> {changeData.namespace}</div>
          <div style={{ marginTop: 4, color: '#8c8c8c', fontSize: 12 }}>
            {changeData.details}
          </div>
        </div>
      ),
      duration: 0, // Don't auto-close critical notifications
      placement: 'topRight',
      btn: onViewChange ? (
        <Button 
          type="primary" 
          danger 
          size="small"
          icon={<EyeOutlined />}
          onClick={() => {
            notification.destroy(`critical-change-${Date.now()}`);
            // Note: We don't have change ID here, might need to navigate to changes page
            onViewChange?.(0);
          }}
        >
          Review Now
        </Button>
      ) : undefined,
    });
  }, [onViewChange]);

  // Show notification for regular changes
  const showChangeNotification = useCallback((change: ChangeDetectedMessage) => {
    // Only show notifications for high-risk changes (not critical - those get special treatment)
    if (change.risk_level !== 'high') return;

    notification.warning({
      key: `change-${Date.now()}`,
      message: (
        <Space>
          <WarningOutlined style={{ color: riskColors.high }} />
          <span>New Change Detected</span>
        </Space>
      ),
      description: (
        <div>
          <div style={{ marginBottom: 8 }}>
            <Tag color={riskColors[change.risk_level]}>
              {changeTypeLabels[change.change_type] || change.change_type}
            </Tag>
          </div>
          <div><strong>{change.target}</strong> in {change.namespace}</div>
        </div>
      ),
      duration: 5,
      placement: 'topRight',
    });
  }, []);

  // Handle incoming messages
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data) as WebSocketMessage;
      setLastMessage(data);

      switch (data.type) {
        case 'change_detected':
          onChangeDetected?.(data as ChangeDetectedMessage);
          if (showNotifications) {
            showChangeNotification(data as ChangeDetectedMessage);
          }
          break;

        case 'critical_change':
          onCriticalChange?.(data as CriticalChangeMessage);
          if (showNotifications) {
            showCriticalNotification(data as CriticalChangeMessage);
          }
          break;

        case 'change_stats_update':
          onStatsUpdate?.(data as StatsUpdateMessage);
          break;

        case 'connected':
          console.log('[ChangeDetectionSocket] Connected to WebSocket');
          break;

        case 'pong':
          // Heartbeat response received
          break;

        default:
          // Handle unknown message types
          console.log('[ChangeDetectionSocket] Unknown message type:', (data as { type: string }).type);
      }
    } catch (error) {
      console.error('[ChangeDetectionSocket] Failed to parse message:', error);
    }
  }, [onChangeDetected, onCriticalChange, onStatsUpdate, showNotifications, showChangeNotification, showCriticalNotification]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!enabled) return;

    // Get authentication token
    const token = localStorage.getItem('flowfish_token');
    if (!token) {
      console.log('[ChangeDetectionSocket] No auth token, skipping connection');
      return;
    }

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let wsUrl = `${protocol}//${window.location.host}/api/v1/ws/changes?token=${token}`;
    
    if (analysisId) {
      wsUrl += `&analysis_id=${analysisId}`;
    }

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[ChangeDetectionSocket] WebSocket connected');
        setIsConnected(true);

        // Start ping interval to keep connection alive
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25000); // Ping every 25 seconds
      };

      ws.onmessage = handleMessage;

      ws.onclose = (event) => {
        console.log('[ChangeDetectionSocket] WebSocket closed:', event.code, event.reason);
        setIsConnected(false);
        wsRef.current = null;

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        // Reconnect after 5 seconds if not a deliberate close
        if (enabled && event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[ChangeDetectionSocket] Attempting reconnect...');
            connect();
          }, 5000);
        }
      };

      ws.onerror = (error) => {
        console.error('[ChangeDetectionSocket] WebSocket error:', error);
      };

    } catch (error) {
      console.error('[ChangeDetectionSocket] Failed to create WebSocket:', error);
    }
  }, [enabled, analysisId, handleMessage]);

  // Subscribe to a different analysis
  const subscribe = useCallback((newAnalysisId: number | undefined) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        analysis_id: newAnalysisId,
      }));
    }
  }, []);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close(1000, 'Disconnecting');
      wsRef.current = null;
    }

    setIsConnected(false);
  }, []);

  // Effect to manage connection lifecycle
  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  // Effect to update subscription when analysisId changes
  useEffect(() => {
    if (isConnected && analysisId !== undefined) {
      subscribe(analysisId);
    }
  }, [analysisId, isConnected, subscribe]);

  return {
    /** Whether the WebSocket is currently connected */
    isConnected,
    /** Last message received from the WebSocket */
    lastMessage,
    /** Subscribe to a specific analysis */
    subscribe,
    /** Manually disconnect from WebSocket */
    disconnect,
    /** Manually reconnect to WebSocket */
    reconnect: connect,
  };
};

export default useChangeDetectionSocket;
