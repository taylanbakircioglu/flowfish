/**
 * DevConsole Page - Developer Query Console
 * 
 * Elastic DevTools benzeri bir developer console sayfası.
 * ClickHouse (SQL) ve Neo4j (Cypher) sorgularını çalıştırma ve sonuçları görüntüleme.
 * 
 * Features:
 * - Monaco Editor ile SQL/Cypher yazma
 * - Sorgu sonuçlarını Table/JSON/Raw formatında görüntüleme
 * - Query history (localStorage)
 * - Örnek sorgular
 * - Analysis filtreleme (çoklu seçim)
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { 
  Layout, 
  Button, 
  Space, 
  Typography, 
  Tooltip,
  Drawer,
  message,
  theme,
} from 'antd';
import {
  PlayCircleOutlined,
  FormatPainterOutlined,
  ClearOutlined,
  HistoryOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import {
  QueryEditor,
  getDefaultQuery,
  ResultsPanel,
  QueryHistory,
  QueryHistoryItem,
  addToHistory,
  DatabaseSelector,
  ExamplesDropdown,
} from '../components/DevConsole';
import {
  useExecuteQueryMutation,
  DatabaseType,
  QueryResponse,
} from '../store/api/devConsoleApi';

const { Header, Content } = Layout;
const { Title, Text } = Typography;
const { useToken } = theme;

const DevConsole: React.FC = () => {
  const { token } = useToken();
  
  // State
  const [database, setDatabase] = useState<DatabaseType>('clickhouse');
  const [analysisIds, setAnalysisIds] = useState<string[]>([]);
  const [clusterIds, setClusterIds] = useState<string[]>([]);
  const [query, setQuery] = useState<string>(getDefaultQuery('clickhouse'));
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  
  // Resizable panel state
  const [editorWidth, setEditorWidth] = useState(45); // percentage
  const [isDragging, setIsDragging] = useState(false);

  // RTK Query
  const [executeQuery, { isLoading }] = useExecuteQueryMutation();

  // Refs
  const containerRef = useRef<HTMLDivElement>(null);

  // Build analysis_id filter condition for ClickHouse
  // Format in ClickHouse: '{analysis_id}-{cluster_id}'
  const buildAnalysisFilter = useCallback((analysisIds: string[], clusterIds: string[]): string => {
    if (clusterIds.length > 0) {
      // Specific clusters selected - exact match
      const conditions: string[] = [];
      analysisIds.forEach(aid => {
        clusterIds.forEach(cid => {
          conditions.push(`analysis_id = '${aid}-${cid}'`);
        });
      });
      return conditions.join(' OR ');
    } else {
      // No cluster filter - match any cluster for selected analyses
      return analysisIds.map(id => `analysis_id LIKE '${id}-%'`).join(' OR ');
    }
  }, []);

  // Update query placeholder when analysis or cluster changes
  useEffect(() => {
    if (analysisIds.length > 0) {
      if (database === 'clickhouse') {
        const filterCondition = buildAnalysisFilter(analysisIds, clusterIds);
        const clusterInfo = clusterIds.length > 0 ? `, clusters: ${clusterIds.join(', ')}` : '';
        setQuery(`-- Query for analysis: ${analysisIds.join(', ')}${clusterInfo}
SELECT 
    source_namespace,
    source_pod,
    dest_pod,
    dest_port,
    protocol,
    count(*) as flow_count,
    sum(bytes_sent) as total_bytes
FROM network_flows
WHERE (${filterCondition})
GROUP BY source_namespace, source_pod, dest_pod, dest_port, protocol
ORDER BY flow_count DESC
LIMIT 100`);
      } else {
        setQuery(`// Query for analysis: ${analysisIds.join(', ')}
MATCH (src:Workload)-[c:COMMUNICATES_WITH]->(dst:Workload)
WHERE c.is_active = true
RETURN 
    src.name as source,
    src.namespace as src_namespace,
    dst.name as destination,
    dst.namespace as dst_namespace,
    c.protocol,
    c.request_count
ORDER BY c.request_count DESC
LIMIT 100`);
      }
    }
  }, [analysisIds, clusterIds, database, buildAnalysisFilter]);

  // Handle database change
  const handleDatabaseChange = useCallback((db: DatabaseType) => {
    setDatabase(db);
    if (analysisIds.length === 0) {
      setQuery(getDefaultQuery(db));
    }
    setResult(null);
  }, [analysisIds]);

  // Execute query
  const handleExecute = useCallback(async () => {
    if (!query.trim()) {
      message.warning('Please enter a query');
      return;
    }

    try {
      const response = await executeQuery({
        database,
        query,
        analysis_ids: analysisIds.length > 0 ? analysisIds : undefined,
        limit: 1000,
        timeout: 30,
      }).unwrap();

      setResult(response);

      // Add to history
      addToHistory({
        query,
        database,
        analysis_ids: analysisIds,
        execution_time_ms: response.execution_time_ms,
        row_count: response.row_count,
        success: response.success,
        error_message: response.error?.message,
      });

      if (response.success) {
        message.success(`Query executed: ${response.row_count} rows in ${response.execution_time_ms}ms`);
      }
    } catch (error: any) {
      message.error('Query execution failed');
      setResult({
        success: false,
        columns: [],
        rows: [],
        row_count: 0,
        execution_time_ms: 0,
        truncated: false,
        error: {
          code: 'EXECUTION_ERROR',
          message: error.message || 'Unknown error',
        },
      });
    }
  }, [query, database, analysisIds, executeQuery]);

  // Format query (basic formatting)
  const handleFormat = useCallback(() => {
    // Basic SQL/Cypher formatting
    let formatted = query;
    
    if (database === 'clickhouse') {
      // SQL formatting
      const keywords = ['SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'GROUP BY', 'ORDER BY', 'LIMIT', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'ON', 'HAVING', 'UNION'];
      keywords.forEach(kw => {
        formatted = formatted.replace(new RegExp(`\\b${kw}\\b`, 'gi'), `\n${kw}`);
      });
    } else {
      // Cypher formatting
      const keywords = ['MATCH', 'WHERE', 'RETURN', 'ORDER BY', 'LIMIT', 'WITH', 'OPTIONAL MATCH', 'CREATE', 'MERGE', 'SET', 'DELETE'];
      keywords.forEach(kw => {
        formatted = formatted.replace(new RegExp(`\\b${kw}\\b`, 'gi'), `\n${kw}`);
      });
    }
    
    // Clean up extra newlines
    formatted = formatted.replace(/^\n+/, '').replace(/\n{3,}/g, '\n\n');
    setQuery(formatted);
    message.success('Query formatted');
  }, [query, database]);

  // Clear editor
  const handleClear = useCallback(() => {
    setQuery(getDefaultQuery(database));
    setResult(null);
  }, [database]);

  // Load from history
  const handleHistorySelect = useCallback((item: QueryHistoryItem) => {
    setDatabase(item.database);
    setQuery(item.query);
    if (item.analysis_ids) setAnalysisIds(item.analysis_ids);
    setHistoryDrawerOpen(false);
  }, []);

  // Run from history
  const handleHistoryRun = useCallback((item: QueryHistoryItem) => {
    setDatabase(item.database);
    setQuery(item.query);
    if (item.analysis_ids) setAnalysisIds(item.analysis_ids);
    setHistoryDrawerOpen(false);
    // Execute after state update
    setTimeout(() => handleExecute(), 100);
  }, [handleExecute]);

  // Select example
  const handleSelectExample = useCallback((exampleQuery: string) => {
    // If analysis is selected, inject the filter
    // NOTE: ClickHouse stores analysis_id as '{analysis_id}-{cluster_id}' format
    if (analysisIds.length > 0) {
      if (database === 'clickhouse') {
        const filterCondition = buildAnalysisFilter(analysisIds, clusterIds);
        const filterClause = `(${filterCondition})`;
        
        // Add comment with context
        const clusterInfo = clusterIds.length > 0 ? `, clusters: ${clusterIds.join(', ')}` : '';
        const commentLine = `-- Filtered by analysis: ${analysisIds.join(', ')}${clusterInfo}\n`;
        
        // Add WHERE clause for analysis_id
        if (exampleQuery.toLowerCase().includes('where')) {
          exampleQuery = commentLine + exampleQuery.replace(
            /WHERE/gi, 
            `WHERE ${filterClause} AND`
          );
        } else {
          exampleQuery = commentLine + exampleQuery.replace(
            /FROM\s+(\w+)/gi,
            `FROM $1\nWHERE ${filterClause}`
          );
        }
      }
      // Neo4j doesn't use analysis_id in graph - just use the example as is
    }
    setQuery(exampleQuery);
  }, [analysisIds, clusterIds, database, buildAnalysisFilter]);

  // Toggle fullscreen
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      containerRef.current?.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  }, []);

  // Handle splitter drag
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;
    
    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;
    
    // Clamp between 20% and 80%
    const clampedWidth = Math.min(Math.max(newWidth, 20), 80);
    setEditorWidth(clampedWidth);
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Add/remove mouse event listeners for drag
  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }
    
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <div 
      ref={containerRef}
      style={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        background: token.colorBgContainer,
      }}
    >
      {/* Header */}
      <Header style={{
        background: token.colorBgContainer,
        padding: '0 24px',
        height: 'auto',
        lineHeight: 'normal',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
      }}>
        {/* Title Row */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 0',
        }}>
          <Space>
            <CodeOutlined style={{ fontSize: 24, color: '#0891b2' }} />
            <Title level={4} style={{ margin: 0 }}>
              Dev Console
            </Title>
            <Text type="secondary" style={{ marginLeft: 8 }}>
              Query TimeSeries & Graph
            </Text>
          </Space>

          <Space>
            <Tooltip title="Query History">
              <Button
                icon={<HistoryOutlined />}
                onClick={() => setHistoryDrawerOpen(true)}
              >
                History
              </Button>
            </Tooltip>
            <Tooltip title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}>
              <Button
                icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                onClick={toggleFullscreen}
              />
            </Tooltip>
          </Space>
        </div>

        {/* Controls Row */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 0',
          borderTop: `1px solid ${token.colorBorderSecondary}`,
        }}>
          {/* Database & Filters */}
          <DatabaseSelector
            database={database}
            onDatabaseChange={handleDatabaseChange}
            analysisIds={analysisIds}
            onAnalysisChange={setAnalysisIds}
            clusterIds={clusterIds}
            onClusterChange={setClusterIds}
          />

          {/* Actions */}
          <Space>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleExecute}
              loading={isLoading}
              size="large"
            >
              Run Query
            </Button>
            <Tooltip title="Format Query (Ctrl+Shift+F)">
              <Button icon={<FormatPainterOutlined />} onClick={handleFormat}>
                Format
              </Button>
            </Tooltip>
            <Tooltip title="Clear Editor">
              <Button icon={<ClearOutlined />} onClick={handleClear}>
                Clear
              </Button>
            </Tooltip>
            <ExamplesDropdown
              database={database}
              onSelectExample={handleSelectExample}
              onDatabaseChange={handleDatabaseChange}
            />
          </Space>
        </div>
      </Header>

      {/* Main Content - Resizable Horizontal Split */}
      <Content style={{ flex: 1, overflow: 'hidden', display: 'flex', position: 'relative' }}>
        {/* Query Editor Panel */}
        <div style={{ 
          width: `${editorWidth}%`,
          minWidth: '20%',
          maxWidth: '80%',
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          background: token.colorBgContainer,
        }}>
          {/* Editor Header */}
          <div style={{
            padding: '8px 12px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: token.colorBgLayout,
          }}>
            <Text style={{ color: token.colorTextSecondary, fontSize: 12 }}>
              {database === 'clickhouse' ? 'TimeSeries SQL' : 'Graph Cypher'}
            </Text>
            <Text keyboard style={{ fontSize: 11 }}>
              Ctrl+Enter to run
            </Text>
          </div>

          {/* Monaco Editor */}
          <div style={{ flex: 1 }}>
            <QueryEditor
              value={query}
              onChange={setQuery}
              database={database}
              onExecute={handleExecute}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Resizable Splitter */}
        <div
          onMouseDown={handleMouseDown}
          style={{
            width: 6,
            cursor: 'col-resize',
            background: isDragging ? '#0891b2' : '#f0f0f0',
            transition: isDragging ? 'none' : 'background 0.2s',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            zIndex: 10,
          }}
          onMouseEnter={(e) => {
            if (!isDragging) {
              (e.target as HTMLElement).style.background = '#d9d9d9';
            }
          }}
          onMouseLeave={(e) => {
            if (!isDragging) {
              (e.target as HTMLElement).style.background = '#f0f0f0';
            }
          }}
        >
          {/* Grip dots */}
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 2,
          }}>
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                style={{
                  width: 2,
                  height: 2,
                  borderRadius: '50%',
                  background: '#8c8c8c',
                }}
              />
            ))}
          </div>
        </div>

        {/* Results Panel */}
        <div style={{ flex: 1, height: '100%', overflow: 'hidden' }}>
          <ResultsPanel result={result} loading={isLoading} />
        </div>
      </Content>

      {/* History Drawer */}
      <Drawer
        title="Query History"
        placement="right"
        width={480}
        onClose={() => setHistoryDrawerOpen(false)}
        open={historyDrawerOpen}
        styles={{ body: { padding: 0 } }}
      >
        <QueryHistory
          onSelect={handleHistorySelect}
          onRun={handleHistoryRun}
        />
      </Drawer>
    </div>
  );
};

export default DevConsole;
