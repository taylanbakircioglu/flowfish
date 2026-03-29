/**
 * QueryEditor Component - Monaco Editor wrapper for SQL/Cypher queries
 * 
 * Features:
 * - SQL syntax highlighting for ClickHouse
 * - Cypher syntax highlighting for Neo4j
 * - Autocomplete for keywords and table names
 * - Dark theme (vs-dark)
 * - Keyboard shortcuts (Ctrl+Enter to run)
 */

import React, { useRef, useCallback, useEffect } from 'react';
import Editor, { OnMount, Monaco } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { theme } from 'antd';
import { DatabaseType } from '../../store/api/devConsoleApi';

const { useToken } = theme;

interface QueryEditorProps {
  value: string;
  onChange: (value: string) => void;
  database: DatabaseType;
  onExecute: () => void;
  disabled?: boolean;
}

// SQL Keywords for ClickHouse
const SQL_KEYWORDS = [
  // Basic SELECT
  'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'IN', 'BETWEEN', 'LIKE', 'ILIKE',
  'GROUP BY', 'ORDER BY', 'LIMIT', 'OFFSET', 'HAVING',
  'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN', 'CROSS JOIN',
  'ON', 'AS', 'DISTINCT', 'ALL', 'UNION', 'UNION ALL', 'INTERSECT', 'EXCEPT',
  'WITH', // CTEs
  
  // Schema exploration (read-only)
  'SHOW', 'SHOW TABLES', 'SHOW DATABASES', 'SHOW CREATE TABLE', 'SHOW COLUMNS',
  'DESCRIBE', 'DESC',
  'EXPLAIN', 'EXPLAIN SYNTAX', 'EXPLAIN PLAN', 'EXPLAIN PIPELINE',
  
  // Aggregate functions
  'SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'ANY', 'SOME',
  'countIf', 'sumIf', 'avgIf', 'minIf', 'maxIf',
  'uniq', 'uniqExact', 'uniqCombined', 'uniqHLL12',
  'groupArray', 'groupUniqArray', 'groupArrayInsertAt',
  'argMin', 'argMax', 'topK', 'topKWeighted',
  'quantile', 'quantiles', 'quantileExact', 'quantileTiming',
  'median', 'stddevPop', 'stddevSamp', 'varPop', 'varSamp',
  
  // Date/Time functions
  'NOW', 'TODAY', 'YESTERDAY', 'INTERVAL', 'HOUR', 'DAY', 'WEEK', 'MONTH', 'YEAR', 'MINUTE', 'SECOND',
  'toDateTime', 'toDate', 'toTime',
  'toStartOfHour', 'toStartOfDay', 'toStartOfMinute', 'toStartOfFiveMinute',
  'toStartOfWeek', 'toStartOfMonth', 'toStartOfYear',
  'toYYYYMMDD', 'toYYYYMM', 'formatDateTime',
  'dateDiff', 'dateAdd', 'dateSub', 'addDays', 'addHours', 'addMinutes',
  
  // String functions
  'toString', 'toStringCutToZero',
  'concat', 'substring', 'substringUTF8',
  'lower', 'upper', 'trim', 'trimLeft', 'trimRight',
  'length', 'lengthUTF8', 'empty', 'notEmpty',
  'startsWith', 'endsWith', 'contains',
  'splitByChar', 'splitByString', 'arrayStringConcat',
  'match', 'extract', 'replaceAll', 'replaceOne',
  
  // Type conversion
  'toInt8', 'toInt16', 'toInt32', 'toInt64',
  'toUInt8', 'toUInt16', 'toUInt32', 'toUInt64',
  'toFloat32', 'toFloat64', 'toDecimal32', 'toDecimal64',
  'CAST', 'reinterpretAsString', 'reinterpretAsUInt64',
  
  // Array functions
  'ARRAY', 'arrayJoin', 'arrayElement', 'arrayConcat',
  'arrayDistinct', 'arrayEnumerate', 'arrayFilter', 'arrayMap',
  'arrayReduce', 'arrayReverse', 'arraySlice', 'arraySort',
  'has', 'hasAll', 'hasAny', 'indexOf', 'countEqual',
  
  // Conditional
  'IF', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  'multiIf', 'nullIf', 'ifNull', 'coalesce',
  
  // Misc
  'NULL', 'IS', 'IS NOT', 'TRUE', 'FALSE',
  'ASC', 'DESC', 'NULLS', 'FIRST', 'LAST',
  'FORMAT', 'SETTINGS', 'FINAL', 'SAMPLE', 'PREWHERE',
  'TUPLE', 'GLOBAL', 'ANY', 'ALL',
  
  // Window functions
  'OVER', 'PARTITION BY', 'ROWS', 'RANGE',
  'row_number', 'rank', 'dense_rank', 'ntile',
  'lead', 'lag', 'first_value', 'last_value',
  
  // IP functions (useful for network analysis)
  'IPv4NumToString', 'IPv4StringToNum',
  'IPv6NumToString', 'IPv6StringToNum',
  'toIPv4', 'toIPv6',
];

// ClickHouse tables (aligned with clickhouse-events-schema.sql)
const CLICKHOUSE_TABLES = [
  'network_flows', 'dns_queries', 'sni_events', 'tcp_lifecycle',
  'process_events', 'file_operations', 'capability_checks',
  'oom_kills', 'bind_events', 'mount_events', 'workload_metadata',
];

// ClickHouse columns (most common ones) - aligned with clickhouse-events-schema.sql
const CLICKHOUSE_COLUMNS = [
  // Common
  'timestamp', 'event_id', 'cluster_id', 'cluster_name', 'analysis_id',
  // network_flows
  'source_namespace', 'source_pod', 'source_container', 'source_node', 'source_ip', 'source_port',
  'dest_namespace', 'dest_pod', 'dest_container', 'dest_ip', 'dest_port', 'dest_hostname',
  'protocol', 'direction', 'connection_state',
  'bytes_sent', 'bytes_received', 'packets_sent', 'packets_received', 'duration_ms', 'latency_ms',
  'error_count', 'retransmit_count', 'error_type',
  // dns_queries (uses source_ prefix)
  'query_name', 'query_type', 'query_class', 'response_code', 'response_ips', 'response_cnames', 'response_ttl',
  'dns_server_ip', 'dns_server_port',
  // sni_events (uses namespace, pod without prefix)
  'namespace', 'pod', 'container', 'node',
  'sni_name', 'src_ip', 'src_port', 'dst_ip', 'dst_port', 'tls_version', 'cipher_suite',
  // process_events
  'pid', 'ppid', 'uid', 'gid', 'comm', 'exe', 'args', 'cwd', 'event_type', 'exit_code', 'signal',
  // file_operations
  'operation', 'file_path', 'file_flags', 'file_mode', 'bytes',
  // capability_checks
  'capability', 'syscall', 'verdict',
  // oom_kills
  'memory_limit', 'memory_usage', 'memory_pages_total', 'memory_pages_free', 'cgroup_path',
  // bind_events
  'bind_addr', 'bind_port', 'interface',
  // workload_metadata
  'workload_name', 'workload_type', 'pod_name', 'pod_uid', 'container_name', 'container_id', 'node_name', 'pod_ip',
  'owner_kind', 'owner_name', 'first_seen', 'last_seen',
];

// Cypher keywords for Neo4j
const CYPHER_KEYWORDS = [
  // Query clauses
  'MATCH', 'OPTIONAL MATCH', 'WHERE', 'RETURN', 'WITH',
  'ORDER BY', 'LIMIT', 'SKIP', 'UNION', 'UNION ALL',
  'UNWIND', 'FOREACH', 'CALL', 'YIELD',
  
  // Schema exploration (read-only)
  'SHOW', 'SHOW DATABASES', 'SHOW CONSTRAINTS', 'SHOW INDEXES',
  
  // Operators
  'AND', 'OR', 'NOT', 'XOR', 'IN', 
  'STARTS WITH', 'ENDS WITH', 'CONTAINS', 'IS NULL', 'IS NOT NULL',
  
  // Pattern
  'AS', 'DISTINCT', 'ALL', 'ANY', 'NONE', 'SINGLE',
  
  // Conditional
  'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
  
  // Literals
  'NULL', 'TRUE', 'FALSE',
  
  // Aggregate functions
  'count', 'sum', 'avg', 'min', 'max', 'stDev', 'stDevP',
  'collect', 'percentileCont', 'percentileDisc',
  
  // List functions
  'size', 'length', 'head', 'last', 'tail',
  'range', 'reverse', 'reduce', 'filter',
  'extract', 'all', 'any', 'none', 'single',
  
  // String functions
  'toString', 'toUpper', 'toLower', 'trim', 'ltrim', 'rtrim',
  'replace', 'substring', 'left', 'right', 'split',
  
  // Math functions
  'abs', 'ceil', 'floor', 'round', 'sign', 'rand',
  'log', 'log10', 'exp', 'sqrt', 'sin', 'cos', 'tan',
  'toInteger', 'toFloat',
  
  // Node/Relationship functions
  'id', 'elementId', 'labels', 'type', 'properties', 'keys',
  'nodes', 'relationships', 'startNode', 'endNode',
  
  // Path functions
  'shortestPath', 'allShortestPaths', 'length', 'nodes', 'relationships',
  
  // Utility
  'coalesce', 'exists', 'isEmpty',
  'timestamp', 'date', 'datetime', 'time', 'duration',
  'point', 'distance',
  
  // Procedures
  'db.labels', 'db.relationshipTypes', 'db.propertyKeys',
  'db.schema.visualization', 'db.indexes', 'db.constraints',
];

// Neo4j labels
const NEO4J_LABELS = [
  'Workload', 'Pod', 'Deployment', 'StatefulSet', 'Service',
  'Namespace', 'Cluster', 'ExternalEndpoint',
];

// Neo4j relationship types
const NEO4J_RELATIONSHIPS = [
  'COMMUNICATES_WITH', 'PART_OF', 'EXPOSES', 'DEPENDS_ON', 'RUNS_ON', 'RESOLVES_TO',
];

// Default query placeholders - shown when no analysis is selected
const DEFAULT_SQL_QUERY = `-- Select an analysis to start querying
-- Or use Templates for ready-to-use queries
`;

const DEFAULT_CYPHER_QUERY = `// Select an analysis to start querying
// Or use Templates for ready-to-use queries
`;

export const getDefaultQuery = (database: DatabaseType): string => {
  return database === 'clickhouse' ? DEFAULT_SQL_QUERY : DEFAULT_CYPHER_QUERY;
};

const QueryEditor: React.FC<QueryEditorProps> = ({
  value,
  onChange,
  database,
  onExecute,
  disabled = false,
}) => {
  const { token } = useToken();
  const isDark = token.colorBgContainer !== '#ffffff';
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);

  // Register Cypher language if not exists
  const registerCypherLanguage = useCallback((monaco: Monaco) => {
    // Check if cypher is already registered
    const languages = monaco.languages.getLanguages();
    if (languages.some(lang => lang.id === 'cypher')) {
      return;
    }

    // Register Cypher language
    monaco.languages.register({ id: 'cypher' });

    // Set token provider
    monaco.languages.setMonarchTokensProvider('cypher', {
      defaultToken: '',
      tokenPostfix: '.cypher',
      ignoreCase: true,

      keywords: CYPHER_KEYWORDS,
      labels: NEO4J_LABELS,
      relationships: NEO4J_RELATIONSHIPS,

      operators: [
        '=', '>', '<', '!', '~', '?', ':',
        '==', '<=', '>=', '!=', '<>',
        '+', '-', '*', '/', '%', '^',
      ],

      symbols: /[=><!~?:&|+\-*\/\^%]+/,

      tokenizer: {
        root: [
          // Comments
          [/\/\/.*$/, 'comment'],
          [/\/\*/, 'comment', '@comment'],

          // Strings
          [/"([^"\\]|\\.)*$/, 'string.invalid'],
          [/'([^'\\]|\\.)*$/, 'string.invalid'],
          [/"/, 'string', '@string_double'],
          [/'/, 'string', '@string_single'],

          // Numbers
          [/\d*\.\d+([eE][\-+]?\d+)?/, 'number.float'],
          [/\d+/, 'number'],

          // Labels (e.g., :Workload)
          [/:[A-Za-z_]\w*/, 'type.identifier'],

          // Relationship types in brackets
          [/\[:[A-Za-z_]\w*\]/, 'type.identifier'],

          // Variables and properties
          [/\$[A-Za-z_]\w*/, 'variable'],
          [/[a-zA-Z_]\w*(?=\s*\()/, 'function'],
          [/[a-zA-Z_]\w*/, {
            cases: {
              '@keywords': 'keyword',
              '@labels': 'type.identifier',
              '@relationships': 'type.identifier',
              '@default': 'identifier',
            },
          }],

          // Operators
          [/@symbols/, {
            cases: {
              '@operators': 'operator',
              '@default': '',
            },
          }],

          // Delimiters
          [/[{}()\[\]]/, '@brackets'],
          [/[;,.]/, 'delimiter'],
        ],

        comment: [
          [/[^\/*]+/, 'comment'],
          [/\*\//, 'comment', '@pop'],
          [/[\/*]/, 'comment'],
        ],

        string_double: [
          [/[^\\"]+/, 'string'],
          [/\\./, 'string.escape'],
          [/"/, 'string', '@pop'],
        ],

        string_single: [
          [/[^\\']+/, 'string'],
          [/\\./, 'string.escape'],
          [/'/, 'string', '@pop'],
        ],
      },
    });
  }, []);

  // Setup autocomplete
  const setupAutocomplete = useCallback((monaco: Monaco) => {
    // SQL autocomplete
    monaco.languages.registerCompletionItemProvider('sql', {
      provideCompletionItems: (model, position) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };

        const suggestions = [
          ...SQL_KEYWORDS.map(kw => ({
            label: kw,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: kw,
            range,
          })),
          ...CLICKHOUSE_TABLES.map(table => ({
            label: table,
            kind: monaco.languages.CompletionItemKind.Class,
            insertText: table,
            detail: 'ClickHouse Table',
            range,
          })),
          ...CLICKHOUSE_COLUMNS.map(col => ({
            label: col,
            kind: monaco.languages.CompletionItemKind.Field,
            insertText: col,
            detail: 'Column',
            range,
          })),
        ];

        return { suggestions };
      },
    });

    // Cypher autocomplete
    monaco.languages.registerCompletionItemProvider('cypher', {
      provideCompletionItems: (model, position) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };

        const suggestions = [
          ...CYPHER_KEYWORDS.map(kw => ({
            label: kw,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: kw,
            range,
          })),
          ...NEO4J_LABELS.map(label => ({
            label: label,
            kind: monaco.languages.CompletionItemKind.Class,
            insertText: label,
            detail: 'Node Label',
            range,
          })),
          ...NEO4J_RELATIONSHIPS.map(rel => ({
            label: rel,
            kind: monaco.languages.CompletionItemKind.Interface,
            insertText: rel,
            detail: 'Relationship Type',
            range,
          })),
        ];

        return { suggestions };
      },
    });
  }, []);

  // Handle editor mount
  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    // Register Cypher language
    registerCypherLanguage(monaco);

    // Setup autocomplete
    setupAutocomplete(monaco);

    // Add keyboard shortcuts
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      if (!disabled) {
        onExecute();
      }
    });

    // Focus editor
    editor.focus();
  };

  // Update language when database changes
  useEffect(() => {
    if (editorRef.current && monacoRef.current) {
      const model = editorRef.current.getModel();
      if (model) {
        const language = database === 'neo4j' ? 'cypher' : 'sql';
        monacoRef.current.editor.setModelLanguage(model, language);
      }
    }
  }, [database]);

  return (
    <div style={{ 
      height: '100%', 
      border: `1px solid ${token.colorBorder}`,
      borderRadius: 4,
      overflow: 'hidden',
    }}>
      <Editor
        height="100%"
        language={database === 'neo4j' ? 'cypher' : 'sql'}
        value={value}
        onChange={(val) => onChange(val || '')}
        onMount={handleEditorMount}
        theme={isDark ? 'vs-dark' : 'light'}
        options={{
          minimap: { enabled: false },
          lineNumbers: 'on',
          fontSize: 14,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          tabSize: 2,
          wordWrap: 'on',
          automaticLayout: true,
          scrollBeyondLastLine: false,
          quickSuggestions: true,
          suggestOnTriggerCharacters: true,
          readOnly: disabled,
          renderLineHighlight: 'all',
          cursorBlinking: 'smooth',
          smoothScrolling: true,
          padding: { top: 8, bottom: 8 },
          scrollbar: {
            verticalScrollbarSize: 10,
            horizontalScrollbarSize: 10,
          },
        }}
      />
    </div>
  );
};

export default QueryEditor;
