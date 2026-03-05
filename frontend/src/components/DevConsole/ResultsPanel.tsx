/**
 * ResultsPanel Component - Query results display with Table/JSON/Raw views
 * 
 * Features:
 * - Table view with pagination
 * - JSON view with syntax highlighting
 * - Raw text view
 * - Copy and export functionality
 * - Error display
 */

import React, { useState, useMemo } from 'react';
import { 
  Table, 
  Tabs, 
  Button, 
  Space, 
  Typography, 
  Alert, 
  Dropdown, 
  message,
  Empty,
  Spin,
  Tag,
  Tooltip,
  theme,
} from 'antd';
import { 
  TableOutlined, 
  CodeOutlined, 
  FileTextOutlined,
  CopyOutlined,
  DownloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';
import { QueryResponse } from '../../store/api/devConsoleApi';

const { Text, Paragraph } = Typography;

// Security: Maximum characters to display in a single cell
const MAX_CELL_DISPLAY_LENGTH = 500;
// Security: Maximum rows to render in table (for performance)
const MAX_RENDER_ROWS = 5000;

interface ResultsPanelProps {
  result: QueryResponse | null;
  loading?: boolean;
}

/**
 * Safely truncate and sanitize a value for display
 */
const sanitizeDisplayValue = (value: any): string => {
  if (value === null || value === undefined) {
    return '';
  }
  
  let strValue: string;
  if (typeof value === 'object') {
    try {
      strValue = JSON.stringify(value);
    } catch {
      strValue = '[Object]';
    }
  } else {
    strValue = String(value);
  }
  
  // Truncate long values
  if (strValue.length > MAX_CELL_DISPLAY_LENGTH) {
    strValue = strValue.substring(0, MAX_CELL_DISPLAY_LENGTH) + '...';
  }
  
  return strValue;
};

const { useToken } = theme;

const ResultsPanel: React.FC<ResultsPanelProps> = ({ result, loading = false }) => {
  const { token } = useToken();
  const [activeTab, setActiveTab] = useState<string>('table');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 50;

  // Convert rows to table data with safety limit
  const tableData = useMemo(() => {
    if (!result?.rows) return [];
    // Limit rows for rendering performance
    const safeRows = result.rows.slice(0, MAX_RENDER_ROWS);
    return safeRows.map((row, index) => {
      const record: Record<string, any> = { _key: index };
      result.columns.forEach((col, colIndex) => {
        record[col] = row[colIndex];
      });
      return record;
    });
  }, [result]);

  // Generate table columns with safe rendering
  const tableColumns = useMemo(() => {
    if (!result?.columns) return [];
    return [
      {
        title: '#',
        key: '_index',
        width: 60,
        render: (_: any, __: any, index: number) => (currentPage - 1) * pageSize + index + 1,
      },
      ...result.columns.map((col) => ({
        title: col,
        dataIndex: col,
        key: col,
        ellipsis: true,
        render: (value: any) => {
          if (value === null || value === undefined) {
            return <Text type="secondary" italic>null</Text>;
          }
          if (typeof value === 'boolean') {
            return value ? <Tag color="green">true</Tag> : <Tag color="red">false</Tag>;
          }
          if (typeof value === 'object') {
            const sanitized = sanitizeDisplayValue(value);
            return <Text code style={{ wordBreak: 'break-all' }}>{sanitized}</Text>;
          }
          // Sanitize string values
          const sanitized = sanitizeDisplayValue(value);
          if (sanitized.length > 100) {
            return (
              <Tooltip title={sanitized.substring(0, 500) + (sanitized.length > 500 ? '...' : '')}>
                <Text style={{ wordBreak: 'break-all' }}>{sanitized.substring(0, 100)}...</Text>
              </Tooltip>
            );
          }
          return <Text style={{ wordBreak: 'break-all' }}>{sanitized}</Text>;
        },
      })),
    ];
  }, [result?.columns, currentPage]);

  // JSON formatted data (with size limit for display)
  const jsonData = useMemo(() => {
    if (!result?.rows || !result?.columns) return '[]';
    // Limit for display
    const displayRows = result.rows.slice(0, MAX_RENDER_ROWS);
    const data = displayRows.map((row) => {
      const obj: Record<string, any> = {};
      result.columns.forEach((col, index) => {
        obj[col] = row[index];
      });
      return obj;
    });
    try {
      const json = JSON.stringify(data, null, 2);
      // Limit JSON size for rendering
      if (json.length > 2_000_000) {
        return json.substring(0, 2_000_000) + '\n\n... [Output truncated for display]';
      }
      return json;
    } catch {
      return '{"error": "Failed to serialize data"}';
    }
  }, [result]);

  // Raw data (tab-separated) with size limit
  const rawData = useMemo(() => {
    if (!result?.rows || !result?.columns) return '';
    const header = result.columns.join('\t');
    // Limit for display
    const displayRows = result.rows.slice(0, MAX_RENDER_ROWS);
    const rows = displayRows.map((row) => 
      row.map((val) => sanitizeDisplayValue(val)).join('\t')
    );
    const output = [header, ...rows].join('\n');
    // Limit output size
    if (output.length > 2_000_000) {
      return output.substring(0, 2_000_000) + '\n\n... [Output truncated for display]';
    }
    return output;
  }, [result]);

  // Copy to clipboard
  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success('Copied to clipboard');
    } catch {
      message.error('Failed to copy');
    }
  };

  // Export menu
  const exportMenuItems: MenuProps['items'] = [
    {
      key: 'csv',
      label: 'Export as CSV',
      onClick: () => exportData('csv'),
    },
    {
      key: 'json',
      label: 'Export as JSON',
      onClick: () => exportData('json'),
    },
    {
      key: 'tsv',
      label: 'Export as TSV',
      onClick: () => exportData('tsv'),
    },
  ];

  // Export data
  const exportData = (format: 'csv' | 'json' | 'tsv') => {
    if (!result?.rows || !result?.columns) return;

    let content = '';
    let filename = `query_result_${Date.now()}`;
    let mimeType = 'text/plain';

    switch (format) {
      case 'csv':
        const csvHeader = result.columns.map(col => `"${col}"`).join(',');
        const csvRows = result.rows.map(row => 
          row.map(val => `"${String(val ?? '').replace(/"/g, '""')}"`).join(',')
        );
        content = [csvHeader, ...csvRows].join('\n');
        filename += '.csv';
        mimeType = 'text/csv';
        break;
      case 'json':
        content = jsonData;
        filename += '.json';
        mimeType = 'application/json';
        break;
      case 'tsv':
        content = rawData;
        filename += '.tsv';
        mimeType = 'text/tab-separated-values';
        break;
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    message.success(`Exported as ${format.toUpperCase()}`);
  };

  // Render status bar
  const renderStatusBar = () => {
    if (!result) return null;

    return (
      <div style={{
        padding: '8px 12px',
        borderTop: `1px solid ${token.colorBorderSecondary}`,
        background: token.colorBgLayout,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: 12,
      }}>
        <Space size="large">
          <Space size="small">
            {result.success ? (
              <CheckCircleOutlined style={{ color: '#4d9f7c' }} />
            ) : (
              <CloseCircleOutlined style={{ color: '#f76e6e' }} />
            )}
            <Text type={result.success ? 'success' : 'danger'}>
              {result.success ? 'Success' : 'Error'}
            </Text>
          </Space>
          <Space size="small">
            <TableOutlined />
            <Text>Rows: {result.row_count.toLocaleString()}</Text>
            {result.truncated && <Tag color="orange">Truncated</Tag>}
          </Space>
          <Space size="small">
            <ClockCircleOutlined />
            <Text>Time: {result.execution_time_ms}ms</Text>
          </Space>
        </Space>
      </div>
    );
  };

  // Loading state
  if (loading) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: token.colorBgContainer,
      }}>
        <Spin size="large" tip="Executing query..." />
      </div>
    );
  }

  // Empty state
  if (!result) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: token.colorBgContainer,
      }}>
        <Empty
          description={
            <Text type="secondary">
              Run a query to see results
              <br />
              <Text keyboard>Ctrl+Enter</Text> to execute
            </Text>
          }
        />
      </div>
    );
  }

  // Error state
  if (!result.success && result.error) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgContainer }}>
        <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
          <Alert
            type="error"
            showIcon
            message={
              <Space>
                <Text strong>Query Error</Text>
                {result.error.code && <Tag color="red">{result.error.code}</Tag>}
              </Space>
            }
            description={
              <div>
                <Paragraph style={{ marginBottom: 8 }}>
                  {result.error.message}
                </Paragraph>
                {result.error.line && (
                  <Text type="secondary">
                    Line {result.error.line}
                    {result.error.position && `, Position ${result.error.position}`}
                  </Text>
                )}
              </div>
            }
          />
        </div>
        {renderStatusBar()}
      </div>
    );
  }

  // Success with no rows
  if (result.row_count === 0) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgContainer }}>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Empty description="Query executed successfully but returned no rows" />
        </div>
        {renderStatusBar()}
      </div>
    );
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgContainer }}>
      {/* Toolbar */}
      <div style={{
        padding: '8px 12px',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          size="small"
          style={{ marginBottom: 0 }}
          items={[
            {
              key: 'table',
              label: (
                <Space size={4}>
                  <TableOutlined />
                  Table
                </Space>
              ),
            },
            {
              key: 'json',
              label: (
                <Space size={4}>
                  <CodeOutlined />
                  JSON
                </Space>
              ),
            },
            {
              key: 'raw',
              label: (
                <Space size={4}>
                  <FileTextOutlined />
                  Raw
                </Space>
              ),
            },
          ]}
        />
        <Space>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => handleCopy(activeTab === 'json' ? jsonData : rawData)}
          >
            Copy
          </Button>
          <Dropdown menu={{ items: exportMenuItems }} placement="bottomRight">
            <Button size="small" icon={<DownloadOutlined />}>
              Export
            </Button>
          </Dropdown>
        </Space>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {activeTab === 'table' && (
          <Table
            dataSource={tableData}
            columns={tableColumns}
            rowKey="_key"
            size="small"
            pagination={{
              current: currentPage,
              pageSize,
              total: result.row_count,
              showSizeChanger: false,
              showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} rows`,
              onChange: (page) => setCurrentPage(page),
            }}
            scroll={{ x: 'max-content' }}
          />
        )}

        {activeTab === 'json' && (
          <pre style={{
            margin: 0,
            padding: 16,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontSize: 13,
            lineHeight: 1.6,
            color: token.colorText,
            overflow: 'auto',
            height: '100%',
            background: token.colorBgLayout,
          }}>
            {jsonData}
          </pre>
        )}

        {activeTab === 'raw' && (
          <pre style={{
            margin: 0,
            padding: 16,
            fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
            fontSize: 13,
            lineHeight: 1.6,
            color: '#333',
            overflow: 'auto',
            height: '100%',
            whiteSpace: 'pre',
            background: token.colorBgLayout,
          }}>
            {rawData}
          </pre>
        )}
      </div>

      {/* Status Bar */}
      {renderStatusBar()}
    </div>
  );
};

export default ResultsPanel;
