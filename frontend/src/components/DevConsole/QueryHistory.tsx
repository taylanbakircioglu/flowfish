/**
 * QueryHistory Component - LocalStorage based query history
 * 
 * Features:
 * - Persist queries in localStorage
 * - Favorite queries
 * - Search and filter
 * - Run/Edit/Delete actions
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  List,
  Input,
  Button,
  Space,
  Typography,
  Tag,
  Tooltip,
  Popconfirm,
  Empty,
  Select,
  theme,
} from 'antd';
import {
  SearchOutlined,
  StarOutlined,
  StarFilled,
  PlayCircleOutlined,
  EditOutlined,
  DeleteOutlined,
  ClearOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { DatabaseType } from '../../store/api/devConsoleApi';

const { Text, Paragraph } = Typography;

// Types
export interface QueryHistoryItem {
  id: string;
  query: string;
  database: DatabaseType;
  analysis_ids?: string[];
  executed_at: string;
  execution_time_ms: number;
  row_count: number;
  success: boolean;
  error_message?: string;
  is_favorite: boolean;
}

interface QueryHistoryProps {
  onSelect: (item: QueryHistoryItem) => void;
  onRun: (item: QueryHistoryItem) => void;
}

// LocalStorage key
const STORAGE_KEY = 'flowfish_query_history';
const MAX_HISTORY_ITEMS = 100;

// Helper functions
export const loadHistory = (): QueryHistoryItem[] => {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
};

export const saveHistory = (items: QueryHistoryItem[]) => {
  try {
    // Keep only latest MAX_HISTORY_ITEMS
    const trimmed = items.slice(0, MAX_HISTORY_ITEMS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch (e) {
    console.error('Failed to save query history:', e);
  }
};

export const addToHistory = (item: Omit<QueryHistoryItem, 'id' | 'executed_at' | 'is_favorite'>): QueryHistoryItem => {
  const newItem: QueryHistoryItem = {
    ...item,
    id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
    executed_at: new Date().toISOString(),
    is_favorite: false,
  };

  const history = loadHistory();
  // Add to beginning
  history.unshift(newItem);
  saveHistory(history);
  return newItem;
};

export const toggleFavorite = (id: string): QueryHistoryItem[] => {
  const history = loadHistory();
  const index = history.findIndex(item => item.id === id);
  if (index !== -1) {
    history[index].is_favorite = !history[index].is_favorite;
    saveHistory(history);
  }
  return history;
};

export const deleteHistoryItem = (id: string): QueryHistoryItem[] => {
  const history = loadHistory().filter(item => item.id !== id);
  saveHistory(history);
  return history;
};

export const clearHistory = (): void => {
  localStorage.removeItem(STORAGE_KEY);
};

// Format relative time
const formatRelativeTime = (dateString: string): string => {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return 'Just now';
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? 's' : ''} ago`;
  if (diffDay < 7) return `${diffDay} day${diffDay > 1 ? 's' : ''} ago`;
  return date.toLocaleDateString();
};

// Truncate query for display
const truncateQuery = (query: string, maxLength: number = 120): string => {
  const cleaned = query.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= maxLength) return cleaned;
  return cleaned.substring(0, maxLength) + '...';
};

const QueryHistory: React.FC<QueryHistoryProps> = ({ onSelect, onRun }) => {
  const { token } = theme.useToken();
  const [history, setHistory] = useState<QueryHistoryItem[]>(() => loadHistory());
  const [searchText, setSearchText] = useState('');
  const [filterDb, setFilterDb] = useState<DatabaseType | 'all'>('all');
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);

  // Refresh history from localStorage
  const refreshHistory = useCallback(() => {
    setHistory(loadHistory());
  }, []);

  // Filtered history
  const filteredHistory = useMemo(() => {
    return history.filter(item => {
      // Filter by search text
      if (searchText && !item.query.toLowerCase().includes(searchText.toLowerCase())) {
        return false;
      }
      // Filter by database
      if (filterDb !== 'all' && item.database !== filterDb) {
        return false;
      }
      // Filter by favorites
      if (showFavoritesOnly && !item.is_favorite) {
        return false;
      }
      return true;
    });
  }, [history, searchText, filterDb, showFavoritesOnly]);

  // Handlers
  const handleToggleFavorite = (id: string) => {
    setHistory(toggleFavorite(id));
  };

  const handleDelete = (id: string) => {
    setHistory(deleteHistoryItem(id));
  };

  const handleClearAll = () => {
    clearHistory();
    setHistory([]);
  };

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column',
      background: token.colorBgContainer,
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center',
          marginBottom: 12,
        }}>
          <Text strong>Query History</Text>
          <Popconfirm
            title="Clear all history?"
            description="This action cannot be undone."
            onConfirm={handleClearAll}
            okText="Clear"
            cancelText="Cancel"
          >
            <Button 
              size="small" 
              type="text" 
              danger
              icon={<ClearOutlined />}
              disabled={history.length === 0}
            >
              Clear All
            </Button>
          </Popconfirm>
        </div>

        <Space direction="vertical" style={{ width: '100%' }} size={8}>
          <Input
            placeholder="Search queries..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            allowClear
            size="small"
          />
          <Space>
            <Select
              size="small"
              value={filterDb}
              onChange={setFilterDb}
              style={{ width: 120 }}
              options={[
                { value: 'all', label: 'All Databases' },
                { value: 'clickhouse', label: 'ClickHouse' },
                { value: 'neo4j', label: 'Neo4j' },
              ]}
            />
            <Button
              size="small"
              type={showFavoritesOnly ? 'primary' : 'default'}
              icon={showFavoritesOnly ? <StarFilled /> : <StarOutlined />}
              onClick={() => setShowFavoritesOnly(!showFavoritesOnly)}
            >
              Favorites
            </Button>
          </Space>
        </Space>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {filteredHistory.length === 0 ? (
          <Empty 
            description={
              history.length === 0 
                ? "No queries in history" 
                : "No matching queries"
            }
            style={{ marginTop: 40 }}
          />
        ) : (
          <List
            dataSource={filteredHistory}
            renderItem={(item) => (
              <List.Item
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  borderBottom: `1px solid ${token.colorBorderSecondary}`,
                }}
                onClick={() => onSelect(item)}
              >
                <div style={{ width: '100%' }}>
                  <div style={{ 
                    display: 'flex', 
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: 4,
                  }}>
                    <Space size={4}>
                      <Tooltip title={item.is_favorite ? 'Remove from favorites' : 'Add to favorites'}>
                        <Button
                          type="text"
                          size="small"
                          icon={item.is_favorite ? <StarFilled style={{ color: '#c9a55a' }} /> : <StarOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleFavorite(item.id);
                          }}
                        />
                      </Tooltip>
                      <Tag color={item.database === 'clickhouse' ? 'blue' : 'green'}>
                        {item.database === 'clickhouse' ? 'ClickHouse' : 'Neo4j'}
                      </Tag>
                      {item.success ? (
                        <CheckCircleOutlined style={{ color: '#4d9f7c', fontSize: 12 }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#f76e6e', fontSize: 12 }} />
                      )}
                      {item.analysis_ids && item.analysis_ids.length > 0 && (
                        <Tag>{item.analysis_ids.length} analysis</Tag>
                      )}
                    </Space>
                    <Space size={0}>
                      <Tooltip title="Run query">
                        <Button
                          type="text"
                          size="small"
                          icon={<PlayCircleOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            onRun(item);
                          }}
                        />
                      </Tooltip>
                      <Tooltip title="Load to editor">
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelect(item);
                          }}
                        />
                      </Tooltip>
                      <Popconfirm
                        title="Delete this query?"
                        onConfirm={(e) => {
                          e?.stopPropagation();
                          handleDelete(item.id);
                        }}
                        onCancel={(e) => e?.stopPropagation()}
                        okText="Delete"
                        cancelText="Cancel"
                      >
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
                    </Space>
                  </div>

                  <Paragraph
                    style={{
                      marginBottom: 4,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontSize: 12,
                      color: token.colorText,
                    }}
                    ellipsis={{ rows: 2 }}
                  >
                    {truncateQuery(item.query)}
                  </Paragraph>

                  <Space size="large" style={{ fontSize: 11 }}>
                    <Text type="secondary">
                      <ClockCircleOutlined style={{ marginRight: 4 }} />
                      {formatRelativeTime(item.executed_at)}
                    </Text>
                    <Text type="secondary">
                      {item.row_count} rows
                    </Text>
                    <Text type="secondary">
                      {item.execution_time_ms}ms
                    </Text>
                  </Space>
                </div>
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  );
};

export default QueryHistory;
