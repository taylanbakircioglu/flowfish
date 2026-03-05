/**
 * useAnalysisWarnings Hook
 * 
 * Listens for WebSocket messages about analysis auto-stop warnings
 * and displays notifications to the user.
 */

import React, { useEffect, useRef, useCallback } from 'react';
import { notification, Button, Space } from 'antd';
import { WarningOutlined, EyeOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

interface AutoStopWarningMessage {
  type: 'analysis_auto_stop_warning';
  analysis_id: number;
  analysis_name: string;
  remaining_minutes: number;
  message: string;
  timestamp: string;
}

interface UseAnalysisWarningsOptions {
  /** Enable/disable the hook */
  enabled?: boolean;
}

export const useAnalysisWarnings = (options: UseAnalysisWarningsOptions = {}) => {
  const { enabled = true } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const navigate = useNavigate();
  
  const handleViewAnalysis = useCallback((analysisId: number) => {
    notification.destroy(`analysis-warning-${analysisId}`);
    navigate('/analyses');
  }, [navigate]);
  
  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data);
      
      // Handle auto-stop warning messages
      if (data.type === 'analysis_auto_stop_warning') {
        const warning = data as AutoStopWarningMessage;
        
        // Show notification
        notification.warning({
          key: `analysis-warning-${warning.analysis_id}`,
          message: `Analysis "${warning.analysis_name}" will stop soon`,
          description: (
            <div>
              <p style={{ marginBottom: 8 }}>
                Auto-stop in <strong>{warning.remaining_minutes}</strong> minute(s).
              </p>
              <p style={{ marginBottom: 0, color: '#8c8c8c', fontSize: 12 }}>
                The analysis data will be saved automatically.
              </p>
            </div>
          ),
          icon: <WarningOutlined style={{ color: '#c9a55a' }} />,
          duration: 0, // Don't auto-dismiss - user must acknowledge
          btn: (
            <Space>
              <Button 
                type="primary" 
                size="small"
                icon={<EyeOutlined />}
                onClick={() => handleViewAnalysis(warning.analysis_id)}
              >
                View Analyses
              </Button>
              <Button 
                size="small"
                onClick={() => notification.destroy(`analysis-warning-${warning.analysis_id}`)}
              >
                Dismiss
              </Button>
            </Space>
          ),
          placement: 'topRight',
          style: {
            borderLeft: '4px solid #c9a55a'
          }
        });
        
        console.log('[useAnalysisWarnings] Warning displayed:', warning);
      }
    } catch (e) {
      // Ignore parse errors for non-JSON messages
    }
  }, [handleViewAnalysis]);
  
  const connect = useCallback(() => {
    if (!enabled) return;
    
    // Get authentication token
    const token = localStorage.getItem('flowfish_token');
    if (!token) {
      console.log('[useAnalysisWarnings] No auth token, skipping WebSocket connection');
      return;
    }
    
    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/events?token=${token}`;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('[useAnalysisWarnings] WebSocket connected');
      };
      
      ws.onmessage = handleMessage;
      
      ws.onclose = (event) => {
        console.log('[useAnalysisWarnings] WebSocket closed:', event.code, event.reason);
        wsRef.current = null;
        
        // Reconnect after 5 seconds if not a deliberate close
        if (enabled && event.code !== 1000) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('[useAnalysisWarnings] Attempting reconnect...');
            connect();
          }, 5000);
        }
      };
      
      ws.onerror = (error) => {
        console.error('[useAnalysisWarnings] WebSocket error:', error);
      };
      
    } catch (error) {
      console.error('[useAnalysisWarnings] Failed to create WebSocket:', error);
    }
  }, [enabled, handleMessage]);
  
  useEffect(() => {
    connect();
    
    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounting');
        wsRef.current = null;
      }
    };
  }, [connect]);
  
  return {
    /** Current connection state */
    isConnected: wsRef.current?.readyState === WebSocket.OPEN
  };
};

export default useAnalysisWarnings;

