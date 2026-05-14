/**
 * L7 Service Dependency Map — independent from Map.tsx (L4).
 * React Flow + Ant Design + RTK Query (L7 graph, stats, events).
 */
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import dagre from 'dagre';
import {
  Card,
  Select,
  Input,
  Button,
  Drawer,
  Tabs,
  Tag,
  Space,
  Badge,
  Tooltip,
  Statistic,
  Empty,
  Spin,
  Slider,
  Descriptions,
  Table,
  Progress,
  Typography,
  Switch,
  Row,
  Col,
  Alert,
  theme,
  Divider,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  DownloadOutlined,
  FileTextOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  GlobalOutlined,
  ClusterOutlined,
  FilterOutlined,
  AimOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  InfoCircleOutlined,
  PartitionOutlined,
  ShareAltOutlined,
  DeploymentUnitOutlined,
  AlertOutlined,
  AppstoreOutlined,
  SwapRightOutlined,
  NodeExpandOutlined,
  RadarChartOutlined,
  ForkOutlined,
  CompressOutlined,
  ExpandOutlined,
  DatabaseOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
} from '@ant-design/icons';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  MarkerType,
  type Node,
  type Edge,
  type ReactFlowInstance,
} from '@xyflow/react';
// @ts-ignore -- Handle & Position are valid runtime exports; TS 4.9 fails to resolve the dual value+type re-export in @xyflow/react v12
import { Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useTheme } from '../contexts/ThemeContext';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import {
  useGetL7DependencyGraphQuery,
  useGetL7CommunicationStatsQuery,
  useGetL7ErrorStatsQuery,
} from '../store/api/l7CommunicationApi';
import {
  useGetL7HttpEventsQuery,
  useGetL7EventStatsQuery,
  useGetL7GrpcEventsQuery,
  useGetL7DnsEventsQuery,
  useGetL7EventHistogramQuery,
  useGetL7TraceQuery,
} from '../store/api/l7EventsApi';
import TraceWaterfall from '../components/trace/TraceWaterfall';
import type { Analysis } from '../types';
import { isL7Compatible, useL7AnalysisGuard } from '../utils/analysisFilters';
import { applyLayout, type L7LayoutType } from '../utils/l7LayoutEngine';
import {
  isSecondaryNamespace,
  classifyNamespace,
  type NamespaceCategory,
  statusClass,
  normalizeProtocol,
  healthFromErrorRate,
  healthColor,
  formatCount,
  NODE_W,
  NODE_H,
} from '../utils/serviceMapConstants';

const { Text, Title } = Typography;

// --- Types (aligned with graph-query Neo4j shape) ---
interface L7GraphNode {
  id: string;
  name: string;
  namespace: string;
  cluster: string;
  kind: string;
  analysis_id: string;
  network_type?: string;
  is_external?: boolean;
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  owner_kind?: string;
}

interface L7GraphEdge {
  source_id: string;
  target_id: string;
  protocol?: string | null;
  http_method?: string | null;
  http_path?: string | null;
  request_count: number;
  error_count: number;
  avg_latency_ms?: number | null;
  // W3C distributed trace tracking on this edge (Faz 2.1).
  // last_trace_id is the most recently observed trace for this edge; trace_count
  // is total number of traced requests since edge creation. Both are optional
  // because legacy graphs may not have these properties yet.
  last_trace_id?: string | null;
  last_span_id?: string | null;
  trace_count?: number | null;
}

interface L7NodeMetrics {
  protocols: Set<string>;
  totalRequests: number;
  totalErrors: number;
}

export interface L7WorkloadNodeData extends Record<string, unknown> {
  workloadName: string;
  namespace: string;
  kind: string;
  cluster: string;
  protocols: string[];
  health: 'healthy' | 'warning' | 'critical';
  requestTotal: number;
  errorRate: number;
  searchHighlight: boolean;
  focusDimmed: boolean;
  focusNeighbor: boolean;
  focusSelected: boolean;
  layoutDir: 'TB' | 'LR';
  networkType?: string;
  isExternal?: boolean;
  systemDimmed?: boolean;
  ownerKind?: string;
  // Backend-emitted synthetic namespaces (cluster-infra / sdn-infrastructure /
  // unknown / loopback) get a dedicated category badge so operators can tell
  // an unresolved or infrastructure node apart from a real workload at a
  // glance. See `classifyNamespace` in `utils/serviceMapConstants`.
  namespaceCategory?: NamespaceCategory;
}

const NETWORK_TYPE_INFO: Record<string, { color: string; icon: React.ReactNode; label: string; tagColor: string }> = {
  'Pod-Network':      { color: '#22c55e', icon: <ClusterOutlined />, label: 'Pod',             tagColor: 'green' },
  'Service-Network':  { color: '#6366f1', icon: <ApiOutlined />,     label: 'Service',         tagColor: 'purple' },
  'Node-Network':     { color: '#94a3b8', icon: <DatabaseOutlined />,label: 'Node',            tagColor: 'default' },
  'Internal-Network': { color: '#0ea5e9', icon: <ClusterOutlined />, label: 'Internal',        tagColor: 'blue' },
  'Private-Network':  { color: '#3b82f6', icon: <ClusterOutlined />, label: 'Private',         tagColor: 'geekblue' },
  'External-Network': { color: '#f97316', icon: <GlobalOutlined />,  label: 'External',        tagColor: 'orange' },
  'External-IP':      { color: '#ef4444', icon: <GlobalOutlined />,  label: 'External',        tagColor: 'red' },
  'SDN-Gateway':      { color: '#64748b', icon: <PartitionOutlined/>,label: 'SDN Gateway',     tagColor: 'default' },
  'OpenShift-SDN':    { color: '#64748b', icon: <PartitionOutlined/>,label: 'OpenShift SDN',   tagColor: 'default' },
};

const L7_LAYOUT_OPTIONS: { value: L7LayoutType; icon: React.ReactNode; title: string }[] = [
  { value: 'dagre-tb', icon: <PartitionOutlined />, title: 'Top → Bottom' },
  { value: 'dagre-lr', icon: <SwapRightOutlined />, title: 'Left → Right' },
  { value: 'hub', icon: <AimOutlined />, title: 'Hub (Centrality)' },
  { value: 'concentric', icon: <ShareAltOutlined />, title: 'Concentric' },
  { value: 'namespace-cluster', icon: <AppstoreOutlined />, title: 'Namespace Cluster' },
  { value: 'force', icon: <ApiOutlined />, title: 'Force-Directed' },
  { value: 'radial', icon: <NodeExpandOutlined />, title: 'Radial Rings' },
  { value: 'circle', icon: <RadarChartOutlined />, title: 'Circle' },
  { value: 'grid', icon: <AppstoreOutlined />, title: 'Grid' },
  { value: 'tree', icon: <ForkOutlined />, title: 'Tree (Hierarchical)' },
  { value: 'star', icon: <DeploymentUnitOutlined />, title: 'Star' },
  { value: 'mesh', icon: <CompressOutlined />, title: 'Mesh (Hexagonal)' },
  { value: 'layered', icon: <PartitionOutlined />, title: 'Layered (Bands)' },
  { value: 'organic', icon: <ExpandOutlined />, title: 'Organic / Spiral' },
  { value: 'error-centric', icon: <AlertOutlined />, title: 'Error-Centric' },
  { value: 'tier', icon: <DatabaseOutlined />, title: 'Tier (Layers)' },
  { value: 'flow', icon: <SwapRightOutlined />, title: 'Flow (L→R)' },
];

function layoutWithDagre(nodes: Node[], edges: Edge[], rankdir: 'TB' | 'LR'): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir,
    nodesep: 56,
    ranksep: 96,
    marginx: 32,
    marginy: 32,
  });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  const seen = new Set<string>();
  edges.forEach((e) => {
    const key = `${e.source}->${e.target}`;
    if (seen.has(key)) return;
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
      seen.add(key);
    }
  });
  dagre.layout(g);
  return nodes.map((n) => {
    const pos = g.node(n.id);
    if (!pos) return { ...n, position: n.position || { x: 0, y: 0 } };
    return {
      ...n,
      position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
    };
  });
}

function percentile(sorted: number[], p: number): number | null {
  if (!sorted.length) return null;
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, Math.min(sorted.length - 1, idx))];
}

// --- Custom node (handles via sourcePosition / targetPosition on Node) ---
const L7WorkloadNode = memo(function L7WorkloadNode(props: { data: L7WorkloadNodeData }) {
  const { data } = props;
  const ntInfo = data.networkType ? NETWORK_TYPE_INFO[data.networkType] : null;
  const border = ntInfo && data.isExternal ? ntInfo.color : healthColor(data.health);
  const isDimmed = data.focusDimmed || data.systemDimmed;
  const opacity = isDimmed ? 0.15 : 1;
  const scale = data.focusSelected ? 1.05 : data.focusNeighbor ? 0.95 : isDimmed ? 0.85 : 1;
  const ring =
    data.focusSelected || data.focusNeighbor
      ? data.focusSelected
        ? '0 0 0 3px rgba(99,102,241,0.65)'
        : '0 0 0 2px rgba(34,197,94,0.45)'
      : data.searchHighlight
        ? '0 0 0 3px rgba(250,204,21,0.7)'
        : undefined;

  const kindLabel = data.ownerKind || data.kind || 'Workload';

  return (
    <div
      style={{
        width: NODE_W,
        minHeight: NODE_H,
        padding: 10,
        borderRadius: 10,
        border: `2px solid ${border}`,
        background: 'var(--l7-node-bg, #fff)',
        boxShadow: ring || '0 2px 8px rgba(0,0,0,0.08)',
        opacity,
        transform: `scale(${scale})`,
        transition: 'opacity 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease',
        position: 'relative',
      }}
    >
      <Handle type="target" position={data.layoutDir === 'LR' ? Position.Left : Position.Top} style={{ background: border, width: 8, height: 8, border: '2px solid #fff' }} />
      <Handle type="source" position={data.layoutDir === 'LR' ? Position.Right : Position.Bottom} style={{ background: border, width: 8, height: 8, border: '2px solid #fff' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <Text strong ellipsis style={{ display: 'block', fontSize: 13 }} title={data.workloadName}>
            {ntInfo ? <span style={{ marginRight: 4, color: ntInfo.color }}>{ntInfo.icon}</span> : null}
            {data.workloadName}
          </Text>
          <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
            <Tag color="geekblue" style={{ maxWidth: '100%', margin: 0 }} title={data.namespace}>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{data.namespace}</span>
            </Tag>
            {ntInfo && (
              <Tag color={ntInfo.tagColor} style={{ margin: 0, fontSize: 10 }}>{ntInfo.label}</Tag>
            )}
            {/* Category badge for synthetic namespaces. Application nodes get
                no extra tag (the geekblue namespace tag is enough); the other
                three categories make it obvious that the node is either part
                of cluster infrastructure (kubelet probes / SDN gateways) or
                an unresolved endpoint, so operators don't mistake them for
                real application dependencies. */}
            {data.namespaceCategory === 'system' && (
              <Tag color="default" style={{ margin: 0, fontSize: 10 }} title="Kubernetes / OpenShift control-plane namespace">
                System
              </Tag>
            )}
            {data.namespaceCategory === 'infrastructure' && (
              <Tag color="cyan" style={{ margin: 0, fontSize: 10 }} title="Cluster infrastructure (kubelet probes, SDN gateways)">
                Infra
              </Tag>
            )}
            {data.namespaceCategory === 'unresolved' && (
              <Tag color="warning" style={{ margin: 0, fontSize: 10 }} title="Beyla / collector could not resolve this endpoint to a Kubernetes object">
                Unresolved
              </Tag>
            )}
            {/* Cluster badge — critical for multi-cluster scenarios so a service
                map showing the same workload name across clusters is visually
                disambiguated. Suppressed for synthetic external placeholders
                (cluster='unknown'/'') where it would be misleading. */}
            {data.cluster && data.cluster !== 'unknown' && !data.isExternal && (
              <Tag
                color="purple"
                style={{ margin: 0, fontSize: 10 }}
                title={`Cluster: ${data.cluster}`}
              >
                {data.cluster.length > 14 ? `${data.cluster.slice(0, 14)}…` : data.cluster}
              </Tag>
            )}
          </div>
        </div>
        <Badge count={data.requestTotal > 0 ? formatCount(data.requestTotal) : 0} showZero color="#6366f1" />
      </div>
      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {data.protocols.map((p) => {
          const low = p.toLowerCase();
          if (low === 'grpc')
            return (
              <Tooltip key={p + 'grpc'} title="gRPC">
                <Tag icon={<ThunderboltOutlined />} color="purple">
                  gRPC
                </Tag>
              </Tooltip>
            );
          if (low === 'dns')
            return (
              <Tooltip key={p + 'dns'} title="DNS">
                <Tag icon={<GlobalOutlined />} color="cyan">
                  DNS
                </Tag>
              </Tooltip>
            );
          return (
            <Tooltip key={p + 'http'} title="HTTP">
              <Tag icon={<ApiOutlined />} color="blue">
                HTTP
              </Tag>
            </Tooltip>
          );
        })}
        <Text type="secondary" style={{ fontSize: 11 }}>
          {kindLabel}
        </Text>
      </div>
    </div>
  );
});



const CONNECTION_TABLE_COLUMNS = [
  { title: 'Peer', dataIndex: 'peer', key: 'peer', ellipsis: true },
  { title: 'Proto', dataIndex: 'protocol', width: 64 },
  { title: 'Path', dataIndex: 'path', width: 140, ellipsis: true },
  { title: 'Req', dataIndex: 'requests', width: 56 },
  { title: 'Err', dataIndex: 'errors', width: 48 },
  {
    title: 'Avg ms',
    dataIndex: 'avg_latency_ms',
    width: 68,
    render: (v: unknown) => Number(v || 0).toFixed(1),
  },
];

const l7NodeTypes = { l7Workload: L7WorkloadNode };

const ServiceMapPage: React.FC = () => {
  const { token } = theme.useToken();
  const { isDark } = useTheme();
  const [searchParams, setSearchParams] = useSearchParams();

  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(() => {
    const p = searchParams.get('analysis_id');
    return p ? Number(p) : undefined;
  });
  const [clusterFilter, setClusterFilter] = useState<number | 'all'>(() => {
    const p = searchParams.get('cluster_id');
    return p ? Number(p) : 'all';
  });

  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [showHeader, setShowHeader] = useState(true);
  const [showStats, setShowStats] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [namespaceFilter, setNamespaceFilter] = useState<string[]>(() => {
    const ns = searchParams.get('ns');
    return ns ? ns.split(',').filter(Boolean) : [];
  });
  const [protocols, setProtocols] = useState<string[]>(['http', 'grpc']);
  const [status2xx, setStatus2xx] = useState(true);
  const [status3xx, setStatus3xx] = useState(true);
  const [status4xx, setStatus4xx] = useState(true);
  const [status5xx, setStatus5xx] = useState(true);
  const [minRequests, setMinRequests] = useState(0);
  const [latencyFloorMs, setLatencyFloorMs] = useState(0);
  const [hideSystemNs, setHideSystemNs] = useState(false);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [edgeLimitValue, setEdgeLimitValue] = useState(500);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [layoutType, setLayoutType] = useState<L7LayoutType>(() => {
    try { return (localStorage.getItem('l7-layout') as L7LayoutType) || 'dagre-tb'; } catch { return 'dagre-tb'; }
  });
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [drawerNodeId, setDrawerNodeId] = useState<string | null>(null);
  // Trace drawer state (Faz 4.1). Edge click on a traced edge surfaces the
  // most recent trace; closing returns to the map without losing zoom/pan.
  const [traceDrawerTraceId, setTraceDrawerTraceId] = useState<string | null>(null);
  const [connFilteredOnly, setConnFilteredOnly] = useState(true);
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[]);
  const flowRef = useRef<ReactFlowInstance | null>(null);
  const namespaceCacheRef = useRef<Set<string>>(new Set());
  const edgeLimitInfoRef = useRef<{ shown: number; total: number } | null>(null);
  const [edgeLimitDismissed, setEdgeLimitDismissed] = useState(false);

  const { data: clustersRes } = useGetClustersQuery();
  const clusters = clustersRes?.clusters ?? [];

  const { data: analyses = [], isLoading: analysesLoading } = useGetAnalysesQuery({});

  const availableAnalyses = useMemo(
    () =>
      Array.isArray(analyses)
        ? analyses.filter((a: Analysis) =>
            ['running', 'completed', 'stopped'].includes(a.status),
          )
        : [],
    [analyses],
  );

  const l7Analyses = useMemo(
    () =>
      availableAnalyses.filter((a: Analysis) => isL7Compatible(a)),
    [availableAnalyses],
  );

  const selectedAnalysis = useMemo(() => {
    if (!selectedAnalysisId) return null;
    return l7Analyses.find((a) => a.id === selectedAnalysisId) || null;
  }, [l7Analyses, selectedAnalysisId]);

  useL7AnalysisGuard(selectedAnalysisId, setSelectedAnalysisId, l7Analyses);

  // Belt-and-suspenders: when selectedAnalysisId changes for any reason (manual
  // change, guard auto-clear, hash route change), close the trace drawer so we
  // never show a trace from a different analysis (Bulgu 26.5b).
  useEffect(() => {
    setTraceDrawerTraceId(null);
  }, [selectedAnalysisId]);

  const isMultiCluster = selectedAnalysis?.is_multi_cluster ?? false;
  const analysisClusterIds = useMemo(() => {
    if (!selectedAnalysis) return [];
    if (selectedAnalysis.cluster_ids?.length) return selectedAnalysis.cluster_ids;
    return [selectedAnalysis.cluster_id];
  }, [selectedAnalysis]);

  const effectiveClusterId = useMemo(() => {
    if (!selectedAnalysis) return undefined;
    if (isMultiCluster) {
      if (clusterFilter === 'all') return undefined;
      return clusterFilter as number;
    }
    return selectedAnalysis.cluster_id;
  }, [selectedAnalysis, isMultiCluster, clusterFilter]);

  useEffect(() => {
    const h = window.setTimeout(() => setDebouncedSearch(search.trim().toLowerCase()), 280);
    return () => window.clearTimeout(h);
  }, [search]);

  useEffect(() => {
    namespaceCacheRef.current = new Set();
    if (selectedAnalysisId && l7Analyses.length) {
      const a = l7Analyses.find((x) => x.id === selectedAnalysisId);
      if (a?.is_multi_cluster) setClusterFilter('all');
    }
  }, [selectedAnalysisId, l7Analyses]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isFullscreen) {
          document.exitFullscreen?.();
        } else {
          setFocusNodeId(null);
          setDrawerNodeId(null);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isFullscreen]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const nowFs = !!document.fullscreenElement;
      setIsFullscreen(nowFs);
      if (!nowFs) {
        setShowHeader(true);
        setShowStats(true);
      }
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!isFullscreen) {
      containerRef.current?.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  }, [isFullscreen]);

  useEffect(() => {
    const next = new URLSearchParams();
    if (selectedAnalysisId) next.set('analysis_id', String(selectedAnalysisId));
    if (clusterFilter !== 'all') next.set('cluster_id', String(clusterFilter));
    if (namespaceFilter.length) next.set('ns', namespaceFilter.join(','));
    setSearchParams(next, { replace: true });
  }, [selectedAnalysisId, clusterFilter, namespaceFilter, setSearchParams]);

  const pollingInterval = autoRefresh ? 30000 : 0;

  const baseParams = useMemo(() => {
    if (!selectedAnalysisId) return null;
    const p: Record<string, string | number> = { analysis_id: selectedAnalysisId };
    if (effectiveClusterId !== undefined) p.cluster_id = effectiveClusterId;
    const allProtos = ['http', 'grpc'];
    if (protocols.length > 0 && protocols.length < allProtos.length) {
      p.protocols = protocols.map((x) => x.toUpperCase()).join(',');
    }
    return p;
  }, [selectedAnalysisId, effectiveClusterId, protocols]);

  const graphParams = useMemo(() => {
    if (!baseParams) return null;
    if (namespaceFilter.length === 0) return baseParams;
    return { ...baseParams, namespaces: namespaceFilter.join(',') };
  }, [baseParams, namespaceFilter]);

  const {
    data: graphRaw,
    isLoading: graphLoading,
    isFetching: graphFetching,
    error: graphError,
    refetch: refetchGraph,
  } = useGetL7DependencyGraphQuery(graphParams as Record<string, string | number>, {
    skip: !graphParams,
    pollingInterval,
  });

  const { data: commStats, error: commStatsError } = useGetL7CommunicationStatsQuery(
    baseParams as Record<string, string | number>,
    { skip: !baseParams, pollingInterval },
  );

  const { data: errorStats } = useGetL7ErrorStatsQuery(
    { analysis_id: selectedAnalysisId, cluster_id: effectiveClusterId },
    { skip: !selectedAnalysisId, pollingInterval },
  );

  const { data: eventStats, error: eventStatsError } = useGetL7EventStatsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
    },
    { skip: !selectedAnalysisId, pollingInterval },
  );

  const allStatusesActive = status2xx && status3xx && status4xx && status5xx;
  const { data: httpSample } = useGetL7HttpEventsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      limit: 8000,
      offset: 0,
    },
    {
      skip: !selectedAnalysisId || allStatusesActive,
      pollingInterval: allStatusesActive ? 0 : pollingInterval,
    },
  );

  const drawerNode = useMemo(() => {
    if (!drawerNodeId || !graphRaw?.nodes) return null;
    return (graphRaw.nodes as L7GraphNode[]).find((n) => n.id === drawerNodeId) || null;
  }, [drawerNodeId, graphRaw]);

  const { data: drawerHttp } = useGetL7HttpEventsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      namespace: drawerNode?.namespace,
      limit: 2000,
      offset: 0,
    },
    { skip: !selectedAnalysisId || !drawerNode },
  );

  const { data: drawerGrpc } = useGetL7GrpcEventsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      namespace: drawerNode?.namespace,
      limit: 1000,
      offset: 0,
    },
    { skip: !selectedAnalysisId || !drawerNode },
  );

  const { data: drawerDns } = useGetL7DnsEventsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      namespace: drawerNode?.namespace,
      limit: 1000,
      offset: 0,
    },
    { skip: !selectedAnalysisId || !drawerNode },
  );

  const { data: drawerNsStats } = useGetL7EventStatsQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      namespace: drawerNode?.namespace,
    },
    { skip: !selectedAnalysisId || !drawerNode },
  );

  const { data: latencyHistogram } = useGetL7EventHistogramQuery(
    {
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId,
      namespace: drawerNode?.namespace,
      bucket_count: 48,
    },
    { skip: !selectedAnalysisId || !drawerNode },
  );

  const edgeStatusAllowList = useMemo(() => {
    const s = new Set<string>();
    if (status2xx) s.add('2xx');
    if (status3xx) s.add('3xx');
    if (status4xx) s.add('4xx');
    if (status5xx) s.add('5xx');
    return s;
  }, [status2xx, status3xx, status4xx, status5xx]);

  const pairStatusMap = useMemo(() => {
    const m = new Map<string, Set<string>>();
    const events = httpSample?.events as Record<string, unknown>[] | undefined;
    if (!events) return m;
    for (const ev of events) {
      const code = Number(ev.http_status_code || ev.response_status || 0);
      const cls = statusClass(code);
      if (!cls) continue;
      const srcNs = String(ev.src_namespace || '').toLowerCase();
      const srcWl = String(ev.src_workload || ev.src_workload_name || '').toLowerCase();
      const dstNs = String(ev.dst_namespace || '').toLowerCase();
      const dstWl = String(ev.dst_workload || ev.dst_workload_name || '').toLowerCase();
      const key = `${srcNs}|${srcWl}|${dstNs}|${dstWl}`;
      if (!m.has(key)) m.set(key, new Set());
      m.get(key)!.add(cls);
    }
    return m;
  }, [httpSample]);

  const rawNodes = useMemo(
    () => (graphRaw?.nodes as L7GraphNode[]) || [],
    [graphRaw?.nodes],
  );
  const rawEdges = useMemo(
    () => (graphRaw?.edges as L7GraphEdge[]) || [],
    [graphRaw?.edges],
  );

  const allNamespaces = useMemo(() => {
    rawNodes.forEach((n) => {
      if (n.namespace) namespaceCacheRef.current.add(n.namespace);
    });
    return Array.from(namespaceCacheRef.current).sort();
  }, [rawNodes]);

  const rebuildGraph = useCallback(() => {
    if (!graphRaw || !selectedAnalysisId) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const protocolFilterSet = new Set(protocols.length ? protocols : ['http', 'grpc']);
    const rawNodeMap = new Map(rawNodes.map((n) => [n.id, n]));
    let edgesWorking = rawEdges.filter((e) => {
      const pRaw = normalizeProtocol(e.protocol);
      const edgeProtos = pRaw.split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
      if (!edgeProtos.some((p) => protocolFilterSet.has(p))) return false;
      const req = Number(e.request_count || 0);
      const err = Number(e.error_count || 0);
      if (req < minRequests) return false;
      const lat = Number(e.avg_latency_ms ?? 0);
      if (latencyFloorMs > 0 && lat < latencyFloorMs) return false;
      if (errorsOnly && err <= 0) return false;
      if (!allStatusesActive && pairStatusMap.size > 0) {
        const src = rawNodeMap.get(e.source_id);
        const dst = rawNodeMap.get(e.target_id);
        if (src && dst) {
          const srcNs = (src.namespace || '').toLowerCase();
          const srcName = (src.name || '').toLowerCase();
          const dstNs = (dst.namespace || '').toLowerCase();
          const dstName = (dst.name || '').toLowerCase();
          const key = `${srcNs}|${srcName}|${dstNs}|${dstName}`;
          const classes = pairStatusMap.get(key);
          if (classes && classes.size > 0) {
            const ok = Array.from(classes).some((c) => edgeStatusAllowList.has(c));
            if (!ok) return false;
          } else {
            const edgeProtos = normalizeProtocol(e.protocol).split(',').map((s) => s.trim());
            const hasNonHttp = edgeProtos.some((p) => p && p !== 'http');
            if (!hasNonHttp) return false;
          }
        }
      }
      return true;
    });

    const nodeIds = new Set<string>();
    edgesWorking.forEach((e) => {
      nodeIds.add(e.source_id);
      nodeIds.add(e.target_id);
    });

    let nodesWorking = rawNodes.filter((n) => nodeIds.has(n.id));
    // `systemDimmedIds` is a misnomer kept for code-history continuity: it
    // now covers system + infrastructure (cluster-infra, sdn-infrastructure)
    // + unresolved (unknown, loopback) namespaces so the existing
    // "Hide noisy namespaces" toggle de-emphasizes all of them at once.
    // Application-namespace nodes are never added here.
    const systemDimmedIds = new Set<string>();
    if (hideSystemNs) {
      nodesWorking.forEach((n) => {
        if (isSecondaryNamespace(n.namespace)) systemDimmedIds.add(n.id);
      });
    }
    if (namespaceFilter.length) {
      const allow = new Set(namespaceFilter.map((ns) => ns.toLowerCase()));
      const nsNodeIds = new Set(nodesWorking.filter((n) => allow.has((n.namespace || '').toLowerCase())).map((n) => n.id));
      edgesWorking = edgesWorking.filter(
        (e) => nsNodeIds.has(e.source_id) || nsNodeIds.has(e.target_id),
      );
      const edgeNodeIds = new Set<string>();
      edgesWorking.forEach((e) => { edgeNodeIds.add(e.source_id); edgeNodeIds.add(e.target_id); });
      nodesWorking = nodesWorking.filter((n) => edgeNodeIds.has(n.id));
    }

    const EDGE_LIMIT = edgeLimitValue;
    const totalEdgesBeforeLimit = edgesWorking.length;
    let edgeLimitApplied = false;
    if (edgesWorking.length > EDGE_LIMIT) {
      edgeLimitApplied = true;
      const focusIds = new Set<string>();
      if (focusNodeId) focusIds.add(focusNodeId);
      edgesWorking.sort((a, b) => {
        const errA = Number(a.error_count || 0) > 0 ? 1 : 0;
        const errB = Number(b.error_count || 0) > 0 ? 1 : 0;
        if (errA !== errB) return errB - errA;
        return Number(b.request_count || 0) - Number(a.request_count || 0);
      });
      const kept: typeof edgesWorking = [];
      edgesWorking.forEach((e) => {
        if (kept.length < EDGE_LIMIT || focusIds.has(e.source_id) || focusIds.has(e.target_id) || Number(e.error_count || 0) > 0) {
          kept.push(e);
        }
      });
      edgesWorking = kept;
      const keptNodeIds = new Set<string>();
      edgesWorking.forEach((e) => { keptNodeIds.add(e.source_id); keptNodeIds.add(e.target_id); });
      nodesWorking = nodesWorking.filter((n) => keptNodeIds.has(n.id));
    }
    const newLimitInfo = edgeLimitApplied ? { shown: edgesWorking.length, total: totalEdgesBeforeLimit } : null;
    const prev = edgeLimitInfoRef.current;
    if (newLimitInfo?.total !== prev?.total || newLimitInfo?.shown !== prev?.shown) {
      setEdgeLimitDismissed(false);
    }
    edgeLimitInfoRef.current = newLimitInfo;

    const metrics = new Map<string, L7NodeMetrics>();
    edgesWorking.forEach((e) => {
      const req = Number(e.request_count || 0);
      const err = Number(e.error_count || 0);
      const proto = e.protocol || 'http';
      [e.source_id, e.target_id].forEach((id) => {
        if (!metrics.has(id)) {
          metrics.set(id, { protocols: new Set(), totalRequests: 0, totalErrors: 0 });
        }
        const m = metrics.get(id)!;
        m.protocols.add(proto);
        m.totalRequests += req;
        m.totalErrors += err;
      });
    });

    const q = debouncedSearch;
    const searchNodeIds = new Set<string>();
    const searchEdgeIds = new Set<string>();
    if (q && q.length >= 2) {
      nodesWorking.forEach((n) => {
        if (
          (n.name || '').toLowerCase().includes(q) ||
          (n.namespace || '').toLowerCase().includes(q) ||
          (n.kind || '').toLowerCase().includes(q)
        ) {
          searchNodeIds.add(n.id);
        }
      });
      edgesWorking.forEach((e, idx) => {
        const path = (e.http_path || '').toLowerCase();
        const method = (e.http_method || '').toLowerCase();
        const proto = (e.protocol || '').toLowerCase();
        if (path.includes(q) || method.includes(q) || proto.includes(q)) {
          searchEdgeIds.add(`${e.source_id}-${e.target_id}-${idx}`);
          searchNodeIds.add(e.source_id);
          searchNodeIds.add(e.target_id);
        }
      });

      if (searchNodeIds.size > 0) {
        const directMatches = new Set(searchNodeIds);
        edgesWorking.forEach((e) => {
          if (directMatches.has(e.source_id)) searchNodeIds.add(e.target_id);
          if (directMatches.has(e.target_id)) searchNodeIds.add(e.source_id);
        });
        nodesWorking = nodesWorking.filter((n) => searchNodeIds.has(n.id));
        edgesWorking = edgesWorking.filter(
          (e) => searchNodeIds.has(e.source_id) && searchNodeIds.has(e.target_id),
        );
      } else {
        nodesWorking = [];
        edgesWorking = [];
      }
    }

    const nodeIdSet = new Set(nodesWorking.map((n) => n.id));
    const effectiveFocus = focusNodeId && nodeIdSet.has(focusNodeId) ? focusNodeId : null;

    const neighbor = new Set<string>();
    if (effectiveFocus) {
      neighbor.add(effectiveFocus);
      edgesWorking.forEach((e) => {
        if (e.source_id === effectiveFocus) neighbor.add(e.target_id);
        if (e.target_id === effectiveFocus) neighbor.add(e.source_id);
      });
    }

    const rfNodes: Node[] = nodesWorking.map((n) => {
      const m = metrics.get(n.id);
      const reqT = m?.totalRequests ?? 0;
      const errT = m?.totalErrors ?? 0;
      const rate = reqT > 0 ? errT / reqT : 0;
      const protos = m ? Array.from(m.protocols) : [];
      const focusDimmed = Boolean(effectiveFocus && !neighbor.has(n.id));
      const focusNeighbor = Boolean(effectiveFocus && neighbor.has(n.id) && n.id !== effectiveFocus);
      const focusSelected = effectiveFocus === n.id;
      const systemDimmedNode = systemDimmedIds.has(n.id);
      return {
        id: n.id,
        type: 'l7Workload',
        position: { x: 0, y: 0 },
        sourcePosition: layoutType === 'dagre-lr' ? Position.Right : Position.Bottom,
        targetPosition: layoutType === 'dagre-lr' ? Position.Left : Position.Top,
        data: {
          workloadName: n.name,
          namespace: n.namespace,
          kind: n.kind || 'Workload',
          cluster: String(n.cluster || ''),
          protocols: protos.length ? protos : ['http'],
          health: healthFromErrorRate(rate),
          requestTotal: reqT,
          errorRate: rate,
          searchHighlight: Boolean(q && searchNodeIds.has(n.id)),
          focusDimmed,
          focusNeighbor,
          focusSelected,
          systemDimmed: systemDimmedNode,
          layoutDir: layoutType.startsWith('dagre') ? (layoutType === 'dagre-lr' ? 'LR' : 'TB') : 'TB',
          networkType: n.network_type || '',
          isExternal: n.is_external || false,
          ownerKind: n.owner_kind || '',
          namespaceCategory: classifyNamespace(n.namespace),
        } as L7WorkloadNodeData,
      };
    });

    const maxReq = Math.max(1, ...edgesWorking.map((e) => Number(e.request_count || 0)));
    const rfEdges: Edge[] = edgesWorking.map((e, idx) => {
      const req = Number(e.request_count || 0);
      const err = Number(e.error_count || 0);
      const rate = req > 0 ? err / req : 0;
      const edgeId = `e-${e.source_id}-${e.target_id}-${idx}`;
      const focusDim =
        Boolean(effectiveFocus) &&
        !(e.source_id === effectiveFocus || e.target_id === effectiveFocus);
      const sysDim = systemDimmedIds.has(e.source_id) && systemDimmedIds.has(e.target_id);
      const dim = focusDim || sysDim;
      const edgeSearch =
        Boolean(q) &&
        (searchEdgeIds.has(`${e.source_id}-${e.target_id}-${idx}`) ||
          (searchNodeIds.has(e.source_id) && searchNodeIds.has(e.target_id)));
      const stroke = rate > 0.2 ? '#ef4444' : rate > 0.05 ? '#ca8a04' : '#22c55e';
      const width = 1 + Math.min(8, Math.log10(req + 1) * 2.2);
      const proto = e.protocol ? String(e.protocol) : '';
      const labelText = `${formatCount(req)} · ${Number(e.avg_latency_ms ?? 0).toFixed(1)} ms${proto ? ` · ${proto}` : ''}`;
      return {
        id: edgeId,
        source: e.source_id,
        target: e.target_id,
        animated: req / maxReq > 0.15,
        label: dim ? undefined : labelText,
        labelStyle: {
          fill: isDark ? '#e2e8f0' : '#0f172a',
          fontSize: 10,
          fontWeight: 600,
        },
        labelBgStyle: { fill: isDark ? 'rgba(30,30,46,0.92)' : 'rgba(255,255,255,0.95)' },
        labelBgPadding: [4, 6] as [number, number],
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: stroke,
          width: 16,
          height: 16,
        },
        style: {
          stroke,
          strokeWidth: width,
          opacity: dim ? 0.14 : edgeSearch ? 1 : 0.9,
        },
        data: {
          protocol: e.protocol,
          httpMethod: e.http_method,
          httpPath: e.http_path,
          requestCount: req,
          errorCount: err,
          avgLatencyMs: Number(e.avg_latency_ms ?? 0),
          errorRate: rate,
          // Distributed tracing context — empty for non-traced edges.
          // ServiceMap onEdgeClick checks traceCount > 0 to decide whether
          // to open the trace drawer.
          lastTraceId: String(e.last_trace_id || ''),
          traceCount: Number(e.trace_count || 0),
        },
      };
    });

    // SAME_WORKLOAD bridges — visually connect cross-cluster identity pairs.
    // Rendered as dashed gray edges (no arrow, no animation) so they don't
    // compete with real traffic edges. Skipped when either endpoint is filtered
    // out or when both endpoints already share a real L7_COMMUNICATES_WITH edge.
    type BridgeRow = {
      a_id: string;
      b_id: string;
      confidence: string;
      matched_by: string;
      last_trace_id: string;
    };
    const bridges: BridgeRow[] = ((graphRaw as any)?.same_workload_bridges ?? []) as BridgeRow[];
    const realEdgeKeys = new Set(rfEdges.map((e) => `${e.source}|${e.target}`));
    const renderedNodeIds = new Set(rfNodes.map((n) => n.id));
    const bridgeEdges: Edge[] = bridges
      .filter(
        (b) =>
          b.a_id &&
          b.b_id &&
          renderedNodeIds.has(b.a_id) &&
          renderedNodeIds.has(b.b_id) &&
          !realEdgeKeys.has(`${b.a_id}|${b.b_id}`) &&
          !realEdgeKeys.has(`${b.b_id}|${b.a_id}`),
      )
      .map((b, i) => ({
        id: `sw-${b.a_id}-${b.b_id}-${i}`,
        source: b.a_id,
        target: b.b_id,
        animated: false,
        style: {
          stroke: '#94a3b8',
          strokeWidth: 1.5,
          strokeDasharray: '6 4',
          opacity: 0.7,
        },
        // No arrow — bridges are conceptually undirected (same workload).
        data: {
          isSameWorkloadBridge: true,
          confidence: b.confidence,
          matchedBy: b.matched_by,
          lastTraceId: b.last_trace_id,
        },
      }));
    const allEdges = [...rfEdges, ...bridgeEdges];

    const altLayout = applyLayout(layoutType, rfNodes, allEdges);
    const laid = altLayout ?? layoutWithDagre(rfNodes, allEdges, layoutType === 'dagre-lr' ? 'LR' : 'TB');
    setNodes(laid);
    setEdges(allEdges);
  }, [
    graphRaw,
    selectedAnalysisId,
    rawEdges,
    rawNodes,
    protocols,
    minRequests,
    latencyFloorMs,
    errorsOnly,
    edgeLimitValue,
    hideSystemNs,
    namespaceFilter,
    debouncedSearch,
    focusNodeId,
    layoutType,
    allStatusesActive,
    pairStatusMap,
    edgeStatusAllowList,
    setNodes,
    setEdges,
    isDark,
  ]);

  useEffect(() => {
    rebuildGraph();
  }, [rebuildGraph]);

  // Auto-fit view when filters change the visible node set
  const prevNamespaceRef = useRef(namespaceFilter);
  const prevProtocolsRef = useRef(protocols);
  useEffect(() => {
    const nsChanged = prevNamespaceRef.current !== namespaceFilter;
    const protoChanged = prevProtocolsRef.current !== protocols;
    prevNamespaceRef.current = namespaceFilter;
    prevProtocolsRef.current = protocols;
    if ((nsChanged || protoChanged) && flowRef.current && nodes.length > 0) {
      requestAnimationFrame(() =>
        flowRef.current?.fitView({ padding: 0.18, duration: 250 }),
      );
    }
  }, [namespaceFilter, protocols, nodes]);

  useEffect(() => {
    if (focusNodeId && rawNodes.length > 0) {
      const exists = rawNodes.some((n) => n.id === focusNodeId);
      if (!exists) setFocusNodeId(null);
    }
  }, [focusNodeId, rawNodes]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    // Close trace drawer when switching to a node — only one drawer at a time.
    setTraceDrawerTraceId(null);
    setDrawerNodeId(node.id);
    setFocusNodeId(node.id);
  }, []);

  // Edge click handler — opens trace drawer for edges that have a recent
  // distributed trace. Edges without trace data are non-interactive (only the
  // tooltip/label shows protocol+latency); we still close any open node drawer
  // to keep the UI consistent (Bulgu 13.15).
  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const data = (edge.data as any) || {};
    setDrawerNodeId(null);
    setFocusNodeId(null);
    // SAME_WORKLOAD bridge edges carry no traffic data — clicking them is a
    // no-op beyond the drawer-close above. Real traffic edges may carry a
    // trace context if any request observed propagated W3C headers.
    if (data.isSameWorkloadBridge) {
      return;
    }
    const traceCount = Number(data.traceCount || 0);
    const lastTraceId = String(data.lastTraceId || '');
    if (traceCount > 0 && lastTraceId) {
      setTraceDrawerTraceId(lastTraceId);
    }
  }, []);

  const analysisDurationSec = useMemo(() => {
    if (!selectedAnalysis) return 0;
    const start = selectedAnalysis.started_at
      ? new Date(selectedAnalysis.started_at).getTime()
      : null;
    const end = selectedAnalysis.stopped_at
      ? new Date(selectedAnalysis.stopped_at).getTime()
      : selectedAnalysis.status === 'running'
        ? Date.now()
        : null;
    if (!start || !end) return 0;
    return Math.max(1, (end - start) / 1000);
  }, [selectedAnalysis]);

  const reqPerSec = useMemo(() => {
    const total = commStats?.total_request_count ?? 0;
    if (analysisDurationSec <= 0) return null;
    return total / analysisDurationSec;
  }, [commStats, analysisDurationSec]);

  const filteredWorkloadRows = useMemo(() => {
    return nodes.map((n) => {
      const d = n.data as L7WorkloadNodeData;
      return {
        id: n.id,
        name: d.workloadName,
        namespace: d.namespace,
        kind: d.kind,
        cluster: d.cluster,
        requests: d.requestTotal,
        error_rate_pct: (d.errorRate * 100).toFixed(2),
        protocols: d.protocols.join(';'),
        health: d.health,
      };
    });
  }, [nodes]);

  const exportCsv = useCallback(() => {
    const headers = [
      'id',
      'name',
      'namespace',
      'kind',
      'cluster',
      'requests',
      'error_rate_pct',
      'protocols',
      'health',
    ];
    const lines = [
      headers.join(','),
      ...filteredWorkloadRows.map((r) =>
        headers
          .map((h) => {
            const v = String((r as Record<string, unknown>)[h] ?? '');
            return `"${v.replace(/"/g, '""')}"`;
          })
          .join(','),
      ),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `l7-service-map-workloads-${selectedAnalysisId || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [filteredWorkloadRows, selectedAnalysisId]);

  const exportEdgeCsv = useCallback(() => {
    const headers = ['source', 'target', 'protocol', 'http_path', 'request_count', 'error_count', 'avg_latency_ms'];
    const nodeMap = new Map(nodes.map((n) => [n.id, (n.data as L7WorkloadNodeData).workloadName || n.id]));
    const lines = [
      headers.join(','),
      ...edges.map((e) => {
        const d = (e.data || {}) as Record<string, any>;
        return [
          `"${nodeMap.get(e.source) ?? e.source}"`,
          `"${nodeMap.get(e.target) ?? e.target}"`,
          `"${d.protocol ?? ''}"`,
          `"${(d.httpPath ?? '').replace(/"/g, '""')}"`,
          String(d.requestCount || 0),
          String(d.errorCount || 0),
          String(d.avgLatencyMs ?? 0),
        ].join(',');
      }),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `l7-service-map-edges-${selectedAnalysisId || 'export'}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [edges, nodes, selectedAnalysisId]);

  const exportJson = useCallback(() => {
    const payload = {
      exported_at: new Date().toISOString(),
      analysis_id: selectedAnalysisId,
      cluster_id: effectiveClusterId ?? null,
      filters: {
        namespaces: namespaceFilter,
        protocols,
        minRequests,
        latencyFloorMs,
        hideSystemNs,
        errorsOnly,
        status_classes: {
          '2xx': status2xx,
          '3xx': status3xx,
          '4xx': status4xx,
          '5xx': status5xx,
        },
      },
      nodes: filteredWorkloadRows,
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        ...e.data,
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `l7-service-map-graph-${selectedAnalysisId || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [
    selectedAnalysisId,
    effectiveClusterId,
    namespaceFilter,
    protocols,
    minRequests,
    latencyFloorMs,
    hideSystemNs,
    errorsOnly,
    status2xx,
    status3xx,
    status4xx,
    status5xx,
    filteredWorkloadRows,
    edges,
  ]);

  const httpAggRows = useMemo(() => {
    if (!drawerNode) return [];
    const events = (drawerHttp?.events as Record<string, unknown>[]) || [];
    const name = drawerNode.name;
    const ns = drawerNode.namespace;
    const map = new Map<
      string,
      { method: string; path: string; status: number; count: number; latSum: number }
    >();
    for (const ev of events) {
      const sn = String(ev.src_namespace || '');
      const dn = String(ev.dst_namespace || '');
      const sw = String(ev.src_workload || '');
      const dw = String(ev.dst_workload || '');
      const hit =
        (sn === ns && sw === name) || (dn === ns && dw === name);
      if (!hit) continue;
      const method = String(ev.http_method || '');
      const path = String(ev.http_path || '');
      const status = Number(ev.http_status_code || 0);
      const lat = Number(ev.latency_ms || 0);
      const key = `${method}|${path}|${status}`;
      if (!map.has(key)) {
        map.set(key, { method, path, status, count: 0, latSum: 0 });
      }
      const row = map.get(key)!;
      row.count += 1;
      row.latSum += lat;
    }
    return Array.from(map.values()).map((r) => ({
      key: `${r.method}-${r.path}-${r.status}`,
      method: r.method,
      path: r.path,
      status: r.status,
      count: r.count,
      avg_latency: r.count ? r.latSum / r.count : 0,
    }));
  }, [drawerHttp, drawerNode]);

  const grpcAggRows = useMemo(() => {
    if (!drawerNode) return [];
    const events = (drawerGrpc?.events as Record<string, unknown>[]) || [];
    const name = drawerNode.name;
    const ns = drawerNode.namespace;
    const map = new Map<
      string,
      { service: string; method: string; status: number; count: number; latSum: number }
    >();
    for (const ev of events) {
      const sn = String(ev.src_namespace || '');
      const dn = String(ev.dst_namespace || '');
      const sw = String(ev.src_workload || '');
      const dw = String(ev.dst_workload || '');
      const hit =
        (sn === ns && sw === name) || (dn === ns && dw === name);
      if (!hit) continue;
      const svc = String(ev.grpc_service || '');
      const meth = String(ev.grpc_method || '');
      const st = Number(ev.grpc_status_code ?? 0);
      const lat = Number(ev.latency_ms || 0);
      const key = `${svc}|${meth}|${st}`;
      if (!map.has(key)) {
        map.set(key, { service: svc, method: meth, status: st, count: 0, latSum: 0 });
      }
      const row = map.get(key)!;
      row.count += 1;
      row.latSum += lat;
    }
    return Array.from(map.values()).map((r) => ({
      key: `${r.service}-${r.method}-${r.status}`,
      service: r.service,
      method: r.method,
      status: r.status,
      count: r.count,
      avg_latency: r.count ? r.latSum / r.count : 0,
    }));
  }, [drawerGrpc, drawerNode]);

  const latenciesFromHttp = useMemo(() => {
    if (!drawerNode) return [];
    const events = (drawerHttp?.events as Record<string, unknown>[]) || [];
    const name = drawerNode.name;
    const ns = drawerNode.namespace;
    const out: number[] = [];
    for (const ev of events) {
      const sn = String(ev.src_namespace || '');
      const dn = String(ev.dst_namespace || '');
      const sw = String(ev.src_workload || '');
      const dw = String(ev.dst_workload || '');
      const hit =
        (sn === ns && sw === name) || (dn === ns && dw === name);
      if (!hit) continue;
      out.push(Number(ev.latency_ms || 0));
    }
    out.sort((a, b) => a - b);
    return out;
  }, [drawerHttp, drawerNode]);

  const p95 = percentile(latenciesFromHttp, 95);
  const p99 = percentile(latenciesFromHttp, 99);

  const connectionRows = useMemo(() => {
    if (!drawerNodeId) return { inb: [] as Record<string, unknown>[], out: [] as Record<string, unknown>[] };
    const inb: Record<string, unknown>[] = [];
    const out: Record<string, unknown>[] = [];
    const nodeById = new Map(rawNodes.map((n) => [n.id, n]));
    const edgeSource = connFilteredOnly
      ? rawEdges.filter((e) => e.source_id === drawerNodeId || e.target_id === drawerNodeId)
      : rawEdges;
    edgeSource.forEach((e, idx) => {
      const src = nodeById.get(e.source_id);
      const dst = nodeById.get(e.target_id);
      if (!src || !dst) return;
      if (e.target_id === drawerNodeId) {
        inb.push({
          key: `in-${idx}`,
          peer: `${src.name} (${src.namespace})`,
          protocol: e.protocol,
          requests: e.request_count,
          errors: e.error_count,
          avg_latency_ms: e.avg_latency_ms,
          path: e.http_path,
        });
      }
      if (e.source_id === drawerNodeId) {
        out.push({
          key: `out-${idx}`,
          peer: `${dst.name} (${dst.namespace})`,
          protocol: e.protocol,
          requests: e.request_count,
          errors: e.error_count,
          avg_latency_ms: e.avg_latency_ms,
          path: e.http_path,
        });
      }
    });
    return { inb, out };
  }, [drawerNodeId, rawEdges, rawNodes, connFilteredOnly]);

  const histogramMax = useMemo(() => {
    const buckets = (latencyHistogram?.buckets as { request_count?: number }[]) || [];
    return Math.max(1, ...buckets.map((b) => Number(b.request_count || 0)));
  }, [latencyHistogram]);

  const errAny = graphError || commStatsError || eventStatsError;

  const flowStyles = useMemo(
    () =>
      ({
        '--l7-node-bg': isDark ? 'rgba(30,30,46,0.95)' : '#ffffff',
      }) as React.CSSProperties,
    [isDark],
  );

  const flowBg = useMemo(
    () => ({
      background: isDark ? '#13131f' : '#f8fafc',
      width: '100%',
      height: '100%',
    }),
    [isDark],
  );

  const popupContainer = useCallback(() => {
    if (isFullscreen && containerRef.current) return containerRef.current;
    return document.body;
  }, [isFullscreen]);

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 480,
        background: isFullscreen ? (isDark ? '#0d0d1a' : '#f0f2f5') : undefined,
      }}
    >
      <style>{`
        @keyframes l7-dash {
          0% { stroke-dashoffset: 10; }
          100% { stroke-dashoffset: 0; }
        }
        .react-flow__edge.animated path {
          stroke-dasharray: 5;
          animation: l7-dash 0.5s linear infinite;
        }
      `}</style>

      {/* Top bar */}
      {showHeader && (
      <Card size="small" bordered={false} style={{ marginBottom: 8, flexShrink: 0 }} styles={{ body: { padding: '10px 12px' } }}>
        <Row gutter={[12, 8]} align="middle">
          <Col flex="none">
            <Space align="center">
              <ClusterOutlined style={{ color: token.colorPrimary, fontSize: 18 }} />
              <Title level={5} style={{ margin: 0 }}>
                L7 Service Map
              </Title>
              <Badge
                status={selectedAnalysis?.status === 'running' ? 'processing' : 'default'}
                text={selectedAnalysis?.status?.toUpperCase() || '—'}
              />
            </Space>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Select
              showSearch
              placeholder="Select L7 analysis"
              style={{ width: '100%' }}
              loading={analysesLoading}
              value={selectedAnalysisId}
              onChange={(v) => setSelectedAnalysisId(v)}
              optionFilterProp="label"
              getPopupContainer={popupContainer}
              options={l7Analyses.map((a) => ({
                value: a.id,
                label: `${a.name} (#${a.id})`,
              }))}
              notFoundContent={
                l7Analyses.length ? undefined : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No L7 analyses" />
                )
              }
            />
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Select
              placeholder="Cluster"
              style={{ width: '100%' }}
              disabled={!selectedAnalysis || !isMultiCluster}
              value={isMultiCluster ? clusterFilter : selectedAnalysis?.cluster_id}
              onChange={(v) => setClusterFilter(v as number | 'all')}
              getPopupContainer={popupContainer}
              options={[
                { value: 'all', label: 'All clusters' },
                ...analysisClusterIds.map((id) => {
                  const c = clusters.find((x: { id: number }) => x.id === id);
                  return { value: id, label: c?.name ? `${c.name} (#${id})` : `Cluster #${id}` };
                }),
              ]}
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right' }}>
            <Space wrap>
              <Tooltip title="Poll graph & stats every 30s">
                <Space>
                  <Text type="secondary">Auto-refresh</Text>
                  <Switch checked={autoRefresh} onChange={setAutoRefresh} />
                </Space>
              </Tooltip>
              <Input
                allowClear
                prefix={<SearchOutlined />}
                placeholder="Search workloads, paths… (min 2 chars)"
                style={{ width: 240 }}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Tooltip title="Show or hide filter panel">
                <Button
                  icon={filterCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                  type={filterCollapsed ? 'default' : 'primary'}
                  onClick={() => setFilterCollapsed((c) => !c)}
                />
              </Tooltip>
              <Tooltip title="Fit graph to screen">
                <Button
                  icon={<AimOutlined />}
                  onClick={() => flowRef.current?.fitView({ padding: 0.2, duration: 220 })}
                >
                  Fit
                </Button>
              </Tooltip>
              <Tooltip title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
                <Button
                  icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={toggleFullscreen}
                />
              </Tooltip>
              {isFullscreen && (
                <Tooltip title="Hide header bar">
                  <Button icon={<EyeInvisibleOutlined />} onClick={() => setShowHeader(false)} />
                </Tooltip>
              )}
              <Button icon={<ReloadOutlined />} onClick={() => refetchGraph()} disabled={!selectedAnalysisId}>
                Refresh
              </Button>
              <Button icon={<DownloadOutlined />} onClick={exportCsv} disabled={!nodes.length}>
                Nodes CSV
              </Button>
              <Button icon={<DownloadOutlined />} onClick={exportEdgeCsv} disabled={!edges.length}>
                Edges CSV
              </Button>
              <Button icon={<FileTextOutlined />} onClick={exportJson} disabled={!nodes.length}>
                JSON
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>
      )}

      {errAny ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 8 }}
          message="Some L7 data could not be loaded"
          description={
            <Text type="secondary">
              Graph or stats may be partial. Check that the analysis collected L7 traffic and services are reachable.
            </Text>
          }
        />
      ) : null}

      <div style={{ flex: 1, display: 'flex', gap: 8, minHeight: 0 }}>
        {/* Filter sidebar */}
        <div
          style={{
            width: filterCollapsed ? 0 : 280,
            flexShrink: 0,
            transition: 'width 0.2s ease',
            overflow: 'hidden',
          }}
        >
          <Card
            size="small"
            title={
              <Space>
                <FilterOutlined />
                <span>Filters</span>
              </Space>
            }
            styles={{ body: { padding: '12px 14px' } }}
            style={{ height: '100%', overflow: 'auto' }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Namespaces */}
              <div>
                <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Namespaces
                </Text>
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="All namespaces"
                  style={{ width: '100%', marginTop: 6 }}
                  value={namespaceFilter}
                  onChange={setNamespaceFilter}
                  getPopupContainer={popupContainer}
                  options={allNamespaces.map((ns) => ({ label: ns, value: ns }))}
                />
              </div>

              <Divider style={{ margin: 0 }} />

              {/* Protocols — toggle pills */}
              <div>
                <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                  Protocols
                </Text>
                <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                  {([
                    { key: 'http', label: 'HTTP', bg: isDark ? 'rgba(8,145,178,0.2)' : 'rgba(8,145,178,0.12)', border: isDark ? 'rgba(8,145,178,0.45)' : 'rgba(8,145,178,0.35)', text: isDark ? '#67d5ef' : '#0e7490' },
                    { key: 'grpc', label: 'gRPC', bg: isDark ? 'rgba(124,58,237,0.18)' : 'rgba(124,58,237,0.10)', border: isDark ? 'rgba(124,58,237,0.4)' : 'rgba(124,58,237,0.3)', text: isDark ? '#b69aef' : '#6d28d9' },
                  ] as const).map((p) => {
                    const active = protocols.includes(p.key);
                    return (
                      <div
                        key={p.key}
                        onClick={() => {
                          const next = active
                            ? protocols.filter((x) => x !== p.key)
                            : [...protocols, p.key];
                          if (next.length > 0) setProtocols(next);
                        }}
                        style={{
                          flex: 1,
                          padding: '5px 0',
                          textAlign: 'center',
                          borderRadius: 6,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                          background: active ? p.bg : isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                          color: active ? p.text : isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.3)',
                          border: `1px solid ${active ? p.border : isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
                          userSelect: 'none',
                        }}
                      >
                        {p.label}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* HTTP Status Classes — compact row of pills */}
              <div>
                <Space size={4} style={{ marginBottom: 8 }}>
                  <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    HTTP Status
                  </Text>
                  <Tooltip title="Deselect a status class to filter edges. Only affects HTTP edges with status code data. gRPC edges are unaffected.">
                    <InfoCircleOutlined style={{ fontSize: 10, color: token.colorTextTertiary }} />
                  </Tooltip>
                </Space>
                <div style={{ display: 'flex', gap: 4 }}>
                  {([
                    { label: '2xx', active: status2xx, set: setStatus2xx,
                      bg: isDark ? 'rgba(34,197,94,0.15)' : 'rgba(34,197,94,0.10)', border: isDark ? 'rgba(34,197,94,0.35)' : 'rgba(34,197,94,0.30)', text: isDark ? '#86efac' : '#16a34a' },
                    { label: '3xx', active: status3xx, set: setStatus3xx,
                      bg: isDark ? 'rgba(59,130,246,0.15)' : 'rgba(59,130,246,0.10)', border: isDark ? 'rgba(59,130,246,0.35)' : 'rgba(59,130,246,0.30)', text: isDark ? '#93bbfd' : '#2563eb' },
                    { label: '4xx', active: status4xx, set: setStatus4xx,
                      bg: isDark ? 'rgba(245,158,11,0.15)' : 'rgba(245,158,11,0.10)', border: isDark ? 'rgba(245,158,11,0.35)' : 'rgba(245,158,11,0.30)', text: isDark ? '#fcd34d' : '#d97706' },
                    { label: '5xx', active: status5xx, set: setStatus5xx,
                      bg: isDark ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.10)', border: isDark ? 'rgba(239,68,68,0.35)' : 'rgba(239,68,68,0.30)', text: isDark ? '#fca5a5' : '#dc2626' },
                  ] as const).map((s) => (
                    <div
                      key={s.label}
                      onClick={() => s.set(!s.active)}
                      style={{
                        flex: 1,
                        padding: '4px 0',
                        textAlign: 'center',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                        background: s.active ? s.bg : isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)',
                        color: s.active ? s.text : isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.25)',
                        border: `1px solid ${s.active ? s.border : isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
                        userSelect: 'none',
                      }}
                    >
                      {s.label}
                    </div>
                  ))}
                </div>
              </div>

              <Divider style={{ margin: 0 }} />

              {/* Thresholds */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Min requests
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {minRequests > 0 ? `≥ ${minRequests}` : 'off'}
                  </Text>
                </div>
                <Slider
                  min={0}
                  max={5000}
                  step={10}
                  value={minRequests}
                  onChange={setMinRequests}
                  tooltip={{ formatter: (v) => `≥ ${v} requests` }}
                  style={{ margin: '4px 0 0' }}
                />
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    Min latency
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {latencyFloorMs > 0 ? `≥ ${latencyFloorMs} ms` : 'off'}
                  </Text>
                </div>
                <Slider
                  min={0}
                  max={2000}
                  step={10}
                  value={latencyFloorMs}
                  onChange={setLatencyFloorMs}
                  tooltip={{ formatter: (v) => `≥ ${v} ms` }}
                  style={{ margin: '4px 0 0' }}
                />
              </div>

              <Divider style={{ margin: 0 }} />

              {/* Display toggles */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Tooltip title="Visually de-emphasizes system (kube-* / openshift-*), cluster infrastructure (kubelet probes, SDN gateways) and unresolved (unknown / loopback) nodes so application dependencies stand out.">
                    <Text style={{ fontSize: 12 }}>Dim non-application namespaces</Text>
                  </Tooltip>
                  <Switch size="small" checked={hideSystemNs} onChange={setHideSystemNs} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12 }}>Errors only</Text>
                  <Switch size="small" checked={errorsOnly} onChange={setErrorsOnly} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12 }}>Edge limit</Text>
                  <Select
                    size="small"
                    value={edgeLimitValue}
                    onChange={setEdgeLimitValue}
                    style={{ width: 80 }}
                    options={[
                      { value: 200, label: '200' },
                      { value: 500, label: '500' },
                      { value: 1000, label: '1k' },
                      { value: 2000, label: '2k' },
                      { value: 5000, label: '5k' },
                    ]}
                  />
                </div>
              </div>

              <Divider style={{ margin: 0 }} />

              {/* Graph Layout — icon grid */}
              <div>
                <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', marginBottom: 8 }}>
                  Layout
                </Text>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 3 }}>
                  {L7_LAYOUT_OPTIONS.map((opt) => (
                    <Tooltip key={opt.value} title={opt.title} mouseEnterDelay={0.4} getPopupContainer={popupContainer}>
                      <Button
                        size="small"
                        type={layoutType === opt.value ? 'primary' : 'default'}
                        icon={opt.icon}
                        onClick={() => { setLayoutType(opt.value); try { localStorage.setItem('l7-layout', opt.value); } catch { /* noop */ } }}
                        style={{
                          width: '100%',
                          fontSize: 12,
                          height: 28,
                          padding: '2px 4px',
                        }}
                      />
                    </Tooltip>
                  ))}
                </div>
              </div>
            </div>
          </Card>
        </div>

        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ flex: 1, minHeight: 320, borderRadius: 8, overflow: 'hidden', border: `1px solid ${token.colorBorder}` }}>
            {!l7Analyses.length ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={
                    <Space direction="vertical" align="center">
                      <Text>No analyses with L7 collection (level L7 or Both).</Text>
                      <Text type="secondary">
                        Create an analysis with L7 enabled to populate this map.
                      </Text>
                      <Link to="/analysis/wizard">
                        <Button type="primary">Open analysis wizard</Button>
                      </Link>
                    </Space>
                  }
                />
              </div>
            ) : !selectedAnalysisId ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty description="Select an L7 analysis to load the dependency graph" />
              </div>
            ) : graphLoading && !graphRaw ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Spin size="large" />
              </div>
            ) : graphError ? (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
                <Text type="danger">Failed to load L7 graph</Text>
                <Button type="primary" icon={<ReloadOutlined />} onClick={() => refetchGraph()}>
                  Retry
                </Button>
              </div>
            ) : (graphRaw as any)?.error ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <Alert
                  type="error"
                  showIcon
                  message="Graph Query Error"
                  description={(graphRaw as any).error}
                  action={
                    <Button size="small" icon={<ReloadOutlined />} onClick={() => refetchGraph()}>
                      Retry
                    </Button>
                  }
                />
              </div>
            ) : !rawNodes.length ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
                <Empty
                  description={
                    <Space direction="vertical" align="center">
                      <Text>No L7 workload dependencies for this analysis yet.</Text>
                      <Text type="secondary">
                        Run an L7-capable analysis and generate traffic, or relax filters on the left.
                      </Text>
                      <Link to="/analysis/wizard">
                        <Button>Create L7 analysis</Button>
                      </Link>
                    </Space>
                  }
                />
              </div>
            ) : !nodes.length ? (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Empty description={
                  protocols.length < 2 && protocols.length > 0
                    ? `No ${protocols.map(p => p.toUpperCase()).join(' / ')} traffic found for this analysis. Try selecting additional protocols.`
                    : 'No nodes match the current filters — adjust the filter panel.'
                } />
              </div>
            ) : (
              <ReactFlowProvider>
                <div style={{ width: '100%', height: '100%', ...flowStyles }}>
                  <ReactFlow
                    key={`l7-rf-${selectedAnalysisId}-${layoutType}`}
                    {...({
                      nodes,
                      edges,
                      onNodesChange,
                      onEdgesChange,
                      onNodeClick,
                      onEdgeClick,
                      onInit: (inst: ReactFlowInstance) => {
                        flowRef.current = inst;
                        requestAnimationFrame(() =>
                          inst.fitView({ padding: 0.18, duration: 200 }),
                        );
                      },
                      nodeTypes: l7NodeTypes,
                      minZoom: 0.04,
                      maxZoom: 2,
                      proOptions: { hideAttribution: true },
                      style: flowBg,
                    } as React.ComponentProps<typeof ReactFlow>)}
                  >
                    <Background gap={20} color={isDark ? '#3a3a5c' : '#94a3b8'} variant="dots" />
                    <Controls showInteractive={false} />
                    <MiniMap
                      nodeStrokeWidth={2}
                      zoomable
                      pannable
                      style={{
                        background: isDark ? 'rgba(30,30,46,0.92)' : 'rgba(255,255,255,0.92)',
                        borderRadius: 8,
                      }}
                    />
                    {edgeLimitInfoRef.current && !edgeLimitDismissed && (
                      <Panel position="top-center" style={{ margin: 12 }}>
                        <Tag
                          color="warning"
                          closable
                          onClose={() => setEdgeLimitDismissed(true)}
                          style={{ borderRadius: 6, fontSize: 11, padding: '2px 10px' }}
                        >
                          Showing {edgeLimitInfoRef.current.shown} of {edgeLimitInfoRef.current.total} edges — use filters to narrow
                        </Tag>
                      </Panel>
                    )}
                    {focusNodeId ? (() => {
                      const focusNode = rawNodes.find((n) => n.id === focusNodeId);
                      const neighborCount = edges.filter(
                        (e) => e.source === focusNodeId || e.target === focusNodeId,
                      ).length;
                      return (
                        <Panel position="top-left" style={{ margin: 12 }}>
                          <Card size="small" styles={{ body: { padding: 8 } }}>
                            <Space direction="vertical" size={4}>
                              <Text strong style={{ fontSize: 12 }}>
                                <AimOutlined /> Focus: {focusNode?.name || focusNodeId}
                              </Text>
                              <Text type="secondary" style={{ fontSize: 11 }}>
                                {focusNode?.namespace ? `${focusNode.namespace} · ` : ''}
                                {neighborCount} connection{neighborCount !== 1 ? 's' : ''} · Press Esc to exit
                              </Text>
                              <Button size="small" onClick={() => setFocusNodeId(null)}>
                                Clear focus
                              </Button>
                            </Space>
                          </Card>
                        </Panel>
                      );
                    })() : null}
                    {graphFetching ? (
                      <Panel position="top-right" style={{ margin: 12 }}>
                        <Tag icon={<Spin size="small" />} color="processing">
                          Updating…
                        </Tag>
                      </Panel>
                    ) : null}
                    {/* Floating restore controls in fullscreen */}
                    {isFullscreen && (!showHeader || !showStats) && (
                      <Panel position="bottom-right" style={{ margin: 12 }}>
                        <Space direction="vertical" size={4}>
                          {!showHeader && (
                            <Tooltip title="Show header">
                              <Button size="small" icon={<EyeOutlined />} onClick={() => setShowHeader(true)}>
                                Header
                              </Button>
                            </Tooltip>
                          )}
                          {!showStats && (
                            <Tooltip title="Show stats bar">
                              <Button size="small" icon={<EyeOutlined />} onClick={() => setShowStats(true)}>
                                Stats
                              </Button>
                            </Tooltip>
                          )}
                        </Space>
                      </Panel>
                    )}
                    {/* Floating fullscreen toggle when header is hidden */}
                    {isFullscreen && !showHeader && (
                      <Panel position="top-right" style={{ margin: 12 }}>
                        <Space>
                          <Tooltip title="Exit fullscreen">
                            <Button size="small" icon={<FullscreenExitOutlined />} onClick={toggleFullscreen} />
                          </Tooltip>
                        </Space>
                      </Panel>
                    )}
                  </ReactFlow>
                </div>
              </ReactFlowProvider>
            )}
          </div>

          {/* Bottom stats bar */}
          {showStats && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              padding: '8px 16px',
              borderRadius: 8,
              background: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.02)',
              border: `1px solid ${token.colorBorderSecondary}`,
              flexWrap: 'wrap',
              fontSize: 12,
            }}
          >
            {namespaceFilter.length > 0 && (
              <Tag color="blue" style={{ margin: 0 }}>
                Scope: {namespaceFilter.join(', ')}
              </Tag>
            )}
            <Statistic
              title={<Text type="secondary" style={{ fontSize: 11 }}>Workloads{namespaceFilter.length ? ' (scoped)' : ''}</Text>}
              value={nodes.length}
              valueStyle={{ fontSize: 16, fontWeight: 600 }}
            />
            <div style={{ width: 1, height: 28, background: token.colorBorderSecondary }} />
            <Statistic
              title={<Text type="secondary" style={{ fontSize: 11 }}>{reqPerSec != null ? 'Req/s' : 'Total req'}</Text>}
              value={
                reqPerSec != null
                  ? reqPerSec.toFixed(2)
                  : commStats?.total_request_count ?? eventStats?.total_requests ?? 0
              }
              valueStyle={{ fontSize: 16, fontWeight: 600 }}
            />
            <div style={{ width: 1, height: 28, background: token.colorBorderSecondary }} />
            <Statistic
              title={<Text type="secondary" style={{ fontSize: 11 }}>Avg latency</Text>}
              value={(commStats?.avg_latency_ms ?? eventStats?.avg_latency_ms ?? 0).toFixed(2)}
              suffix="ms"
              valueStyle={{ fontSize: 16, fontWeight: 600 }}
            />
            <div style={{ width: 1, height: 28, background: token.colorBorderSecondary }} />
            <Tooltip
              title={
                errorStats ? (
                  <div style={{ fontSize: 11 }}>
                    <div style={{ fontWeight: 600, marginBottom: 4 }}>Error Breakdown</div>
                    {errorStats.by_protocol && Object.entries(errorStats.by_protocol as Record<string, { error_count: number; request_count: number }>)
                      .filter(([, v]) => v.error_count > 0)
                      .sort(([, a], [, b]) => b.error_count - a.error_count)
                      .map(([proto, v]) => (
                        <div key={proto}>{proto}: {v.error_count} / {v.request_count} req</div>
                      ))}
                    {errorStats.total_errors != null && (
                      <div style={{ marginTop: 4, fontWeight: 600 }}>
                        Total: {errorStats.total_errors} / {errorStats.total_requests ?? 0} req
                        {errorStats.error_rate_percent != null && ` (${Number(errorStats.error_rate_percent).toFixed(2)}%)`}
                      </div>
                    )}
                  </div>
                ) : 'Loading error details...'
              }
            >
              <div style={{ cursor: 'pointer' }}>
                <Statistic
                  title={<Text type="secondary" style={{ fontSize: 11 }}>Error rate</Text>}
                  value={
                    commStats && commStats.total_request_count > 0
                      ? (
                          (100 * (commStats.total_error_count || 0)) /
                          commStats.total_request_count
                        ).toFixed(2)
                      : (eventStats?.error_rate_percent ?? 0).toFixed(2)
                  }
                  suffix="%"
                  valueStyle={{
                    fontSize: 16,
                    fontWeight: 600,
                    color: (() => {
                      const r = commStats && commStats.total_request_count > 0
                        ? (100 * (commStats.total_error_count || 0)) / commStats.total_request_count
                        : (eventStats?.error_rate_percent ?? 0);
                      return r > 5 ? '#ef4444' : r > 1 ? '#f59e0b' : undefined;
                    })(),
                  }}
                />
              </div>
            </Tooltip>
            <div style={{ flex: 1 }} />
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 11 }}>Protocol mix</Text>
              <Tag color="blue" style={{ margin: 0, fontWeight: 600 }}>HTTP {(eventStats as { http?: { total_requests?: number } })?.http?.total_requests ?? 0}</Tag>
              <Tag color="purple" style={{ margin: 0, fontWeight: 600 }}>gRPC {(eventStats as { grpc?: { total_requests?: number } })?.grpc?.total_requests ?? 0}</Tag>
            </Space>
            {isFullscreen && (
              <Tooltip title="Hide stats bar">
                <Button size="small" icon={<EyeInvisibleOutlined />} type="text" onClick={() => setShowStats(false)} />
              </Tooltip>
            )}
          </div>
          )}
        </div>
      </div>

      <Drawer
        title={
          drawerNode ? (
            <Space direction="vertical" size={0}>
              <Text strong>{drawerNode.name}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {drawerNode.namespace} · {drawerNode.owner_kind || drawerNode.kind || 'Workload'}
              </Text>
            </Space>
          ) : (
            'Workload'
          )
        }
        width={560}
        open={Boolean(drawerNode)}
        onClose={() => { setDrawerNodeId(null); setFocusNodeId(null); }}
        destroyOnClose
        getContainer={isFullscreen && containerRef.current ? containerRef.current : document.body}
      >
        {drawerNode ? (
          <Tabs
            items={[
              {
                key: 'overview',
                label: 'Overview',
                children: (
                  <Descriptions bordered size="small" column={1}>
                    <Descriptions.Item label="Name">{drawerNode.name}</Descriptions.Item>
                    <Descriptions.Item label="Namespace">{drawerNode.namespace}</Descriptions.Item>
                    <Descriptions.Item label="Kind">
                      <Tag color="blue">{drawerNode.owner_kind || drawerNode.kind || 'Workload'}</Tag>
                    </Descriptions.Item>
                    <Descriptions.Item label="Cluster">
                      {(() => {
                        const cId = Number(drawerNode.cluster);
                        const c = clusters.find((x: { id: number; name?: string }) => x.id === cId);
                        return c?.name ? `${c.name} (#${cId})` : String(drawerNode.cluster || '—');
                      })()}
                    </Descriptions.Item>
                    <Descriptions.Item label="Analysis">
                      {(() => {
                        const aId = Number(drawerNode.analysis_id);
                        const a = l7Analyses.find((x: { id: number; name?: string }) => x.id === aId);
                        return a?.name ? `${a.name} (#${aId})` : String(drawerNode.analysis_id || '—');
                      })()}
                    </Descriptions.Item>
                    <Descriptions.Item label="Owner Kind">{drawerNode.owner_kind || '—'}</Descriptions.Item>
                    {(drawerNode.network_type || drawerNode.is_external) && (
                      <Descriptions.Item label="Network Type">
                        {(() => {
                          const nt = drawerNode.network_type ? NETWORK_TYPE_INFO[drawerNode.network_type] : null;
                          if (nt) return <Tag color={nt.tagColor} icon={nt.icon}>{nt.label}</Tag>;
                          if (drawerNode.is_external) return <Tag color="orange" icon={<GlobalOutlined />}>External</Tag>;
                          return <Tag>{drawerNode.network_type}</Tag>;
                        })()}
                      </Descriptions.Item>
                    )}
                    <Descriptions.Item label="Namespace L7 totals (ClickHouse)">
                      <Space direction="vertical">
                        <Text>
                          Requests: {drawerNsStats?.total_requests ?? '—'} · Errors:{' '}
                          {drawerNsStats?.total_errors ?? '—'}
                        </Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          Scoped to workload namespace (not single-pod isolation).
                        </Text>
                      </Space>
                    </Descriptions.Item>
                    {/* Error Breakdown for this workload's namespace */}
                    {drawerHttp?.events && (() => {
                      const events = drawerHttp.events as Record<string, unknown>[];
                      const wlName = drawerNode.name.toLowerCase();
                      const wlEvents = events.filter(
                        (ev) => String(ev.src_workload || ev.src_workload_name || '').toLowerCase() === wlName ||
                                String(ev.dst_workload || ev.dst_workload_name || '').toLowerCase() === wlName,
                      );
                      if (!wlEvents.length) return null;
                      const statusCounts: Record<string, number> = {};
                      wlEvents.forEach((ev) => {
                        const code = Number(ev.http_status_code || ev.response_status || 0);
                        if (code >= 400) {
                          const cls = code >= 500 ? `5xx (${code})` : `4xx (${code})`;
                          statusCounts[cls] = (statusCounts[cls] || 0) + 1;
                        }
                      });
                      const sorted = Object.entries(statusCounts).sort(([, a], [, b]) => b - a);
                      if (!sorted.length) return null;
                      return (
                        <Descriptions.Item label="Error Breakdown">
                          <Space direction="vertical" size={2}>
                            {sorted.map(([code, count]) => (
                              <Text key={code} style={{ fontSize: 12 }}>
                                <Tag color={code.startsWith('5') ? 'red' : 'orange'} style={{ margin: 0, fontSize: 11 }}>{code}</Tag> × {count}
                              </Text>
                            ))}
                          </Space>
                        </Descriptions.Item>
                      );
                    })()}
                    {drawerNode.labels && Object.keys(drawerNode.labels).length > 0 && (
                      <Descriptions.Item label="Labels">
                        <Space wrap size={4}>
                          {Object.entries(drawerNode.labels).map(([k, v]) => (
                            <Tag key={k} style={{ fontSize: 11, margin: 0 }}>{k}={String(v)}</Tag>
                          ))}
                        </Space>
                      </Descriptions.Item>
                    )}
                    {drawerNode.annotations && Object.keys(drawerNode.annotations).length > 0 && (
                      <Descriptions.Item label="Annotations">
                        <Space wrap size={4}>
                          {Object.entries(drawerNode.annotations).map(([k, v]) => (
                            <Tag key={k} color="blue" style={{ fontSize: 11, margin: 0 }}>{k}={String(v)}</Tag>
                          ))}
                        </Space>
                      </Descriptions.Item>
                    )}
                  </Descriptions>
                ),
              },
              {
                key: 'http',
                label: 'HTTP requests',
                children: (
                  <Table
                    size="small"
                    pagination={{ pageSize: 8 }}
                    dataSource={httpAggRows}
                    columns={[
                      { title: 'Method', dataIndex: 'method', width: 90 },
                      { title: 'Path', dataIndex: 'path', ellipsis: true },
                      { title: 'Status', dataIndex: 'status', width: 72 },
                      { title: 'Count', dataIndex: 'count', width: 72 },
                      {
                        title: 'Avg ms',
                        dataIndex: 'avg_latency',
                        width: 88,
                        render: (v: number) => v.toFixed(2),
                      },
                    ]}
                  />
                ),
              },
              {
                key: 'grpc',
                label: 'gRPC',
                children:
                  grpcAggRows.length > 0 ? (
                    <Table
                      size="small"
                      pagination={{ pageSize: 8 }}
                      dataSource={grpcAggRows}
                      columns={[
                        { title: 'Service', dataIndex: 'service', ellipsis: true },
                        { title: 'Method', dataIndex: 'method', ellipsis: true },
                        { title: 'Status', dataIndex: 'status', width: 80 },
                        { title: 'Count', dataIndex: 'count', width: 72 },
                        {
                          title: 'Avg ms',
                          dataIndex: 'avg_latency',
                          width: 88,
                          render: (v: number) => v.toFixed(2),
                        },
                      ]}
                    />
                  ) : (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No gRPC samples for this workload in the current fetch window" />
                  ),
              },
              {
                key: 'dns',
                label: 'DNS',
                children: (() => {
                  const dnsRows = (drawerDns as any)?.events
                    ?.filter((e: any) =>
                      drawerNode
                        ? (e.src_workload === drawerNode.name && e.src_namespace === drawerNode.namespace) ||
                          (e.dst_workload === drawerNode.name && e.dst_namespace === drawerNode.namespace)
                        : true,
                    )
                    ?.slice(0, 200)
                    ?.map((e: any, i: number) => ({
                      key: i,
                      query_name: e.query_name || e.dns_query_name || '-',
                      query_type: e.query_type || e.dns_query_type || 'A',
                      response_code: e.response_code ?? e.dns_response_code ?? '-',
                      src: `${e.src_namespace || ''}/${e.src_workload || ''}`,
                      latency: (e.latency_ms ?? e.duration_ms ?? 0),
                    })) || [];
                  return dnsRows.length > 0 ? (
                    <Table
                      size="small"
                      pagination={{ pageSize: 8 }}
                      dataSource={dnsRows}
                      columns={[
                        { title: 'Query', dataIndex: 'query_name', ellipsis: true },
                        { title: 'Type', dataIndex: 'query_type', width: 60 },
                        { title: 'Status', dataIndex: 'response_code', width: 70 },
                        { title: 'Source', dataIndex: 'src', ellipsis: true },
                        {
                          title: 'ms',
                          dataIndex: 'latency',
                          width: 72,
                          render: (v: number) => (v ?? 0).toFixed(2),
                        },
                      ]}
                    />
                  ) : (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <Space direction="vertical" align="center" size={4}>
                          <Text type="secondary">DNS resolution is monitored at the network level (L4).</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Check the <strong>Network Map</strong> for DNS queries captured by the L4 agent.
                          </Text>
                        </Space>
                      }
                    />
                  );
                })(),
              },
              {
                key: 'latency',
                label: 'Latency',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size={16}>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Statistic
                          title="Avg (sample)"
                          value={
                            latenciesFromHttp.length
                              ? (
                                  latenciesFromHttp.reduce((a, b) => a + b, 0) /
                                  latenciesFromHttp.length
                                ).toFixed(2)
                              : '—'
                          }
                          suffix="ms"
                        />
                      </Col>
                      <Col span={8}>
                        <Statistic title="p95" value={p95 != null ? p95.toFixed(2) : '—'} suffix="ms" />
                      </Col>
                      <Col span={8}>
                        <Statistic title="p99" value={p99 != null ? p99.toFixed(2) : '—'} suffix="ms" />
                      </Col>
                    </Row>
                    <div>
                      <Text type="secondary">HTTP latency distribution (namespace histogram)</Text>
                      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {((latencyHistogram?.buckets as { time?: string; request_count?: number; avg_latency_ms?: number }[]) || []).map(
                          (b, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <div style={{ width: 140, fontSize: 11, color: token.colorTextSecondary }}>
                                {b.time?.slice(11, 16) || i}
                              </div>
                              <Progress
                                percent={Math.round((100 * Number(b.request_count || 0)) / histogramMax)}
                                showInfo={false}
                                strokeColor={token.colorPrimary}
                                style={{ flex: 1 }}
                              />
                              <div style={{ width: 120, textAlign: 'right', fontSize: 11 }}>
                                {b.request_count} · {Number(b.avg_latency_ms || 0).toFixed(1)} ms
                              </div>
                            </div>
                          ),
                        )}
                        {!((latencyHistogram?.buckets as unknown[]) || []).length ? (
                          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No histogram buckets" />
                        ) : null}
                      </div>
                    </div>
                  </Space>
                ),
              },
              {
                key: 'connections',
                label: 'Connections',
                children: (
                  <Space direction="vertical" style={{ width: '100%' }} size={16}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Switch size="small" checked={connFilteredOnly} onChange={setConnFilteredOnly} />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {connFilteredOnly ? 'Filtered edges only' : 'All edges (unfiltered)'}
                      </Text>
                    </div>
                    <div>
                      <Text strong>Inbound</Text>
                      <Table
                        size="small"
                        style={{ marginTop: 8 }}
                        pagination={false}
                        dataSource={connectionRows.inb}
                        rowKey="key"
                        columns={CONNECTION_TABLE_COLUMNS}
                      />
                    </div>
                    <div>
                      <Text strong>Outbound</Text>
                      <Table
                        size="small"
                        style={{ marginTop: 8 }}
                        pagination={false}
                        dataSource={connectionRows.out}
                        rowKey="key"
                        columns={CONNECTION_TABLE_COLUMNS}
                      />
                    </div>
                  </Space>
                ),
              },
            ]}
          />
        ) : null}
      </Drawer>

      {/* Trace drawer — opens when an edge with traceCount > 0 is clicked */}
      <TraceDrawer
        traceId={traceDrawerTraceId}
        analysisId={String(selectedAnalysisId || '')}
        onClose={() => setTraceDrawerTraceId(null)}
        container={isFullscreen && containerRef.current ? containerRef.current : undefined}
      />
    </div>
  );
};

interface TraceDrawerProps {
  traceId: string | null;
  analysisId: string;
  onClose: () => void;
  container?: HTMLElement;
}

// Lazy fetch: query only fires when traceId is non-null and analysis is set.
// Uses skip pattern so closing the drawer doesn't trigger a stale request.
const TraceDrawer: React.FC<TraceDrawerProps> = ({ traceId, analysisId, onClose, container }) => {
  const skip = !traceId || !analysisId;
  const { data, isFetching, error } = useGetL7TraceQuery(
    { trace_id: traceId || '', analysis_id: analysisId },
    { skip },
  );
  return (
    <Drawer
      title={
        <Space direction="vertical" size={0}>
          <Text strong>Distributed Trace</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {traceId ? <span>trace_id: <code>{traceId}</code></span> : 'select an edge'}
          </Text>
        </Space>
      }
      width={920}
      open={Boolean(traceId)}
      onClose={onClose}
      destroyOnClose
      getContainer={container || document.body}
    >
      {isFetching ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : error ? (
        <Alert
          type="error"
          showIcon
          message="Trace yuklenemedi"
          description={(error as any)?.data?.detail || (error as any)?.error || 'Beklenmeyen hata'}
        />
      ) : data && data.spans?.length ? (
        <Space direction="vertical" style={{ width: '100%' }} size={16}>
          {data.summary && (
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="Span sayisi">{data.summary.span_count}</Descriptions.Item>
              <Descriptions.Item label="Toplam sure">
                {(data.summary.duration_ms || 0).toFixed(2)} ms
              </Descriptions.Item>
              <Descriptions.Item label="Hatali span">{data.summary.error_count}</Descriptions.Item>
              <Descriptions.Item label="Cluster'lar">
                {(data.summary.clusters || []).join(', ') || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Servisler" span={2}>
                {(data.summary.services || []).join(', ') || '-'}
              </Descriptions.Item>
            </Descriptions>
          )}
          <TraceWaterfall spans={data.spans} />
        </Space>
      ) : (
        <Empty description="Bu trace icin span bulunamadi" />
      )}
    </Drawer>
  );
};

const ServiceMap: React.FC = () => <ServiceMapPage />;

export default ServiceMap;
