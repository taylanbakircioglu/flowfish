// Force rebuild - ReactFlowProvider key fix for namespace filtering (v1.0.1)
import React, { useCallback, useState, useMemo, useEffect, useRef } from 'react';
import JSZip from 'jszip';

// ============================================
// PERFORMANCE: Debug logging only in development
// Eliminates console.log overhead in production
// ============================================
const DEBUG = process.env.NODE_ENV === 'development';
const debugLog = (...args: unknown[]) => { if (DEBUG) console.log(...args); };
import { 
  Typography, 
  Select, 
  Input, 
  Button, 
  Space, 
  Row, 
  Col, 
  Card, 
  Statistic, 
  Spin, 
  Badge,
  Tooltip,
  Empty,
  Slider,
  Switch,
  Drawer,
  Descriptions,
  Tag,
  Divider,
  ConfigProvider,
  Dropdown,
  theme,
  message
} from 'antd';
import { useTheme } from '../contexts/ThemeContext';
import { 
  GlobalOutlined,
  ReloadOutlined,
  SearchOutlined,
  TagOutlined,
  ApartmentOutlined,
  NodeIndexOutlined,
  FilterOutlined,
  DatabaseOutlined,
  ClusterOutlined,
  SettingOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  AppstoreOutlined,
  RadarChartOutlined,
  PartitionOutlined,
  MenuUnfoldOutlined,
  NodeExpandOutlined,
  ForkOutlined,
  GatewayOutlined,
  DeploymentUnitOutlined,
  CompressOutlined,
  ExpandOutlined,
  AimOutlined,
  ShareAltOutlined,
  UpOutlined,
  DownOutlined,
  LeftOutlined,
  RightOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  ClusterOutlined as ClusterIcon,
  ApiOutlined,
  SafetyOutlined,
  LockOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  FileOutlined,
  TeamOutlined,
  SwapRightOutlined,
  DownloadOutlined,
  FolderOutlined,
  FileTextOutlined,
  BankOutlined,
  BlockOutlined,
  SecurityScanOutlined,
  ExclamationCircleOutlined,
  BarChartOutlined,
  CheckCircleOutlined,
  AlertOutlined,
  RobotOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
  type Node,
  type Edge,
  type OnConnect,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// API and type imports
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { useGetDependencyGraphQuery, useGetCommunicationStatsQuery, useGetErrorStatsQuery, DependencyNode, DependencyEdge } from '../store/api/communicationApi';
import { useGetEventStatsQuery, useGetSniEventsQuery, useGetNetworkFlowsQuery } from '../store/api/eventsApi';
import { useGetErrorAnomalySummaryQuery } from '../store/api/changesApi';
import { EventStatsPanel } from '../components/Graph/EventDetailPanel';
import { Analysis } from '../types';
import { useNodeEnrichment, detectKnownService } from '../hooks/useNodeEnrichment';
import { useAnimatedCounter } from '../hooks/useAnimatedCounter';
import { Tabs, List } from 'antd';
import { ClusterBadge } from '../components/Common';

// Type for aggregated node metadata
interface AggregatedNodeMetadata {
  _isAggregated: boolean;
  _originalNodes: DependencyNode[];
  _podCount: number;
  _podsByCluster: Record<number, DependencyNode[]>;
  _clusterIds: number[];
  _clusterCount: number;
}

// Type for aggregated edge metadata  
interface AggregatedEdgeMetadata {
  _isAggregated: boolean;
  _originalEdges: DependencyEdge[];
  _edgeCount: number;
}

// Custom CSS - disable transitions during drag for instant response
const customStyles = `
  .react-flow__node {
    cursor: grab !important;
  }
  
  .react-flow__node:active,
  .react-flow__node.dragging,
  .react-flow__node.draggable.dragging {
    cursor: grabbing !important;
    z-index: 1000 !important;
    transition: none !important;
  }
  
  /* Disable all transitions while any node is being dragged */
  .react-flow__nodes.dragging .react-flow__node {
    transition: none !important;
  }
  
  .react-flow__node.selected {
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.5), 0 4px 12px rgba(0,0,0,0.3) !important;
  }
  
  .react-flow__edge.animated path {
    stroke-dasharray: 5;
    animation: dashdraw 0.5s linear infinite;
  }
  
  @keyframes dashdraw {
    0% { stroke-dashoffset: 10; }
    100% { stroke-dashoffset: 0; }
  }
  
  /* Node enrichment badges */
  .node-badge {
    position: absolute;
    font-size: 10px;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    animation: badgePulse 2s ease-in-out infinite;
    z-index: 10;
  }
  
  .node-badge.danger {
    background: linear-gradient(135deg, #ff4d4f, #cf1322);
    animation: dangerPulse 1s ease-in-out infinite;
  }
  
  .node-badge.warning {
    background: linear-gradient(135deg, #faad14, #d48806);
  }
  
  .node-badge.security {
    background: linear-gradient(135deg, #722ed1, #531dab);
  }
  
  .node-badge.tls {
    background: linear-gradient(135deg, #52c41a, #389e0d);
  }
  
  .node-badge.dns {
    background: linear-gradient(135deg, #1890ff, #096dd9);
  }
  
  @keyframes badgePulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.1); }
  }
  
  @keyframes dangerPulse {
    0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.4); }
    50% { transform: scale(1.15); box-shadow: 0 0 0 8px rgba(255, 77, 79, 0); }
  }
  
  /* TLS edge indicator */
  .tls-edge-label {
    display: flex;
    align-items: center;
    gap: 4px;
    background: linear-gradient(135deg, rgba(82, 196, 26, 0.9), rgba(56, 158, 13, 0.9));
    color: white;
    padding: 2px 6px;
    border-radius: 10px;
    font-size: 9px;
    font-weight: 600;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
  }
  
  /* Activity ring animation */
  .activity-ring {
    position: absolute;
    inset: -4px;
    border-radius: 50%;
    border: 2px solid transparent;
    animation: activityRing 2s ease-in-out infinite;
  }
  
  .activity-ring.high {
    border-color: rgba(250, 173, 20, 0.6);
  }
  
  .activity-ring.critical {
    border-color: rgba(255, 77, 79, 0.6);
    animation: activityRingCritical 1s ease-in-out infinite;
  }
  
  @keyframes activityRing {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.1); opacity: 0.6; }
  }
  
  @keyframes activityRingCritical {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.15); opacity: 0.4; }
  }
  
  /* Drawer tab styling */
  .enriched-drawer .ant-tabs-tab {
    font-size: 12px !important;
    padding: 8px 12px !important;
  }
  
  .enriched-drawer .ant-tabs-content {
    max-height: calc(100vh - 250px);
    overflow-y: auto;
  }
  
  /* Event timeline styling */
  .event-timeline .ant-timeline-item {
    padding-bottom: 12px;
  }
  
  .event-timeline .ant-timeline-item-content {
    font-size: 11px;
  }
`;

const { Title, Text } = Typography;
const { Option } = Select;

// Modern color palette for namespaces
const namespaceColorPalette = [
  '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316',
  '#eab308', '#22c55e', '#14b8a6', '#06b6d4', '#3b82f6',
];

const nsColorMap: Record<string, string> = {};
let colorIndex = 0;

const getNamespaceColor = (namespace: string): string => {
  if (!nsColorMap[namespace]) {
    nsColorMap[namespace] = namespaceColorPalette[colorIndex % namespaceColorPalette.length];
    colorIndex++;
  }
  return nsColorMap[namespace] || '#64748b';
};

// Safe cluster_id parser - handles empty strings, NaN, undefined, null
// Returns 0 as default for invalid values instead of NaN
const safeParseClusterId = (val: string | number | undefined | null): number => {
  if (val === undefined || val === null || val === '') return 0;
  if (typeof val === 'number') return isNaN(val) ? 0 : val;
  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (trimmed === '') return 0;
    const parsed = parseInt(trimmed, 10);
    return isNaN(parsed) ? 0 : parsed;
  }
  return 0;
};

// Protocol colors
const protocolColors: Record<string, string> = {
  'HTTP': '#3b82f6',
  'HTTP2': '#3b82f6',
  'HTTPS': '#22c55e',
  'TLS': '#22c55e',
  'GRPC': '#8b5cf6',
  'GRPC-WEB': '#8b5cf6',
  'TCP': '#f97316',
  'UDP': '#ec4899',
  'DNS': '#06b6d4',
  'MYSQL': '#00758f',
  'POSTGRESQL': '#336791',
  'REDIS': '#dc382d',
  'MONGODB': '#47a248',
  'KAFKA': '#231f20',
  'AMQP': '#ff6600',
};

// Network type colors and icons for CIDR-based node classification
// Must match labels from pod_discovery.py _known_cidrs_ordered and _get_cidr_label
const NETWORK_TYPE_INFO: Record<string, { color: string; icon: string; label: string; borderRadius: string }> = {
  'Pod-Network': { color: '#22c55e', icon: '◆', label: 'Pod Network', borderRadius: '50%' },
  'Service-Network': { color: '#8b5cf6', icon: '◆', label: 'Service Network', borderRadius: '25%' },
  'Node-Network': { color: '#f97316', icon: '▣', label: 'Node IP', borderRadius: '15%' },
  'Internal-Network': { color: '#06b6d4', icon: '◎', label: 'Internal Network', borderRadius: '40%' },
  'Private-Network': { color: '#0ea5e9', icon: '◉', label: 'Private Network', borderRadius: '40%' },
  'External-IP': { color: '#f59e0b', icon: '◉', label: 'Public IP', borderRadius: '50%' },
  'External-Network': { color: '#f59e0b', icon: '◉', label: 'Public', borderRadius: '50%' },
  'SDN-Gateway': { color: '#ec4899', icon: '◐', label: 'SDN Gateway', borderRadius: '35%' },
  'OpenShift-SDN': { color: '#e11d48', icon: '⬡', label: 'OpenShift SDN', borderRadius: '35%' },
  'Unknown': { color: '#94a3b8', icon: '?', label: 'Unknown', borderRadius: '50%' },
};

// Get network type info for a node
const getNetworkTypeInfo = (networkType?: string): { color: string; icon: string; label: string; borderRadius: string } | null => {
  if (!networkType) return null;
  return NETWORK_TYPE_INFO[networkType] || null;
};

// Get effective protocol - prefer app_protocol (L7) over protocol (L4)
const getEffectiveProtocol = (edge: DependencyEdge): string => {
  return edge.app_protocol || edge.protocol || 'TCP';
};

// ============================================
// CSV EXPORT HELPERS
// ============================================

// UTF-8 BOM for Excel compatibility with Turkish characters
const UTF8_BOM = '\uFEFF';

// CSV escape - handles commas, quotes, newlines
const escapeCSV = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  const str = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
};

// Build node CSV row for nodes.csv (ZIP format)
const buildNodeRow = (node: any): string[] => [
  node?.id || '',
  node?.name || '',
  node?.namespace || '',
  String(node?.cluster_id || ''),
  node?.cluster_name || '',
  node?.network_type || '',
  node?.ip || '',
  node?.host_ip || '',
  node?.owner_kind || '',
  node?.owner_name || '',
  node?.kind || '',
  node?.status || '',
  String(node?.is_external || false),
  node?.resolution_source || '',
  JSON.stringify(node?.labels || {})
];

// Build flat node columns for flat CSV (source_ or target_ prefix)
const buildFlatNodeCols = (node: any): string[] => [
  node?.id || '',
  node?.name || '',
  node?.namespace || '',
  String(node?.cluster_id || ''),
  node?.cluster_name || '',
  node?.network_type || '',
  node?.ip || '',
  node?.owner_kind || '',
  node?.owner_name || '',
  String(node?.is_external || false)
];

// Build edge CSV row for edges.csv (ZIP format)
const buildEdgeRow = (edge: any): string[] => [
  edge?.source || '',
  edge?.target || '',
  edge?.data?.protocol || '',
  edge?.data?.app_protocol || '',
  String(edge?.data?.port || ''),
  String(edge?.data?.request_count || 0),
  String(edge?.data?.error_count || 0),
  String(edge?.data?.retransmit_count || 0),
  edge?.data?.last_error_type || ''
];

// Download blob as file
const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};

const getProtocolColor = (protocol?: string): string => {
  return protocolColors[protocol?.toUpperCase() || ''] || '#94a3b8';
};

// Check if node is internal/localhost traffic
const isInternalTraffic = (node: DependencyNode): boolean => {
  const name = node.name?.toLowerCase() || '';
  const ip = (node as any)?.ip || '';
  
  // Localhost addresses
  if (ip.startsWith('127.') || ip === '::1' || ip === 'localhost') return true;
  if (name.includes('localhost') || name.includes('127.0.0.1')) return true;
  
  // Internal Kubernetes DNS
  if (name.includes('.svc.cluster.local')) return true;
  if (name.includes('kube-dns') || name.includes('coredns')) return true;
  
  return false;
};

// Check if name looks like a domain (has dots and letters, not just IP)
const isDomainName = (name: string): boolean => {
  if (!name) return false;
  // Domain pattern: contains dot, has letters, doesn't start/end with dot
  // Examples: amazon.com, api.azure.com, srv-prod-01.company.local
  const domainPattern = /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)+$/;
  // Must have at least one letter (to distinguish from IP)
  const hasLetter = /[a-zA-Z]/.test(name);
  return hasLetter && (domainPattern.test(name) || name.includes('.'));
};

// Check if name is a server hostname (datacenter server, not domain)
// Examples: srv-prod-01, build-server-02, db-server-01
const isServerHostname = (name: string): boolean => {
  if (!name) return false;
  // Server hostname patterns:
  // - Contains letters and numbers but NO dots (short hostname)
  // - OR ends with .local, .internal, .corp, .lan
  const noDots = !name.includes('.');
  const hasLettersAndNumbers = /[a-zA-Z]/.test(name) && /[0-9]/.test(name);
  const isInternalDomain = /\.(local|internal|corp|lan|intra|priv)$/i.test(name);
  
  return (noDots && hasLettersAndNumbers) || isInternalDomain;
};

// Check if domain contains a public TLD (Top Level Domain)
// This helps identify DNS artifacts like "ghcr.io.cluster.local." which is actually "ghcr.io"
const hasPublicTLD = (domain: string): boolean => {
  if (!domain) return false;
  const d = domain.toLowerCase();
  
  // Common public TLDs - check if domain CONTAINS these (not just ends with)
  // This catches DNS search domain artifacts like "ghcr.io.cluster.local."
  const publicTLDs = [
    '.io.', '.com.', '.net.', '.org.', '.dev.', '.app.', '.cloud.', 
    '.co.', '.me.', '.tv.', '.ai.', '.xyz.', '.info.', '.biz.',
    '.edu.', '.gov.', '.mil.', '.int.',
    // ICANN gTLDs (financial, tech, etc.)
    '.bank.', '.finance.', '.insurance.',
    // Country TLDs
    '.us.', '.uk.', '.de.', '.fr.', '.jp.', '.cn.', '.in.', '.br.', 
    '.au.', '.ca.', '.ru.', '.it.', '.es.', '.nl.', '.se.', '.tr.',
    '.kr.', '.mx.', '.ar.', '.pl.', '.be.', '.ch.', '.at.', '.cz.',
    // Also check without trailing dot for domains that end with TLD
    '.io', '.com', '.net', '.org', '.dev', '.app', '.cloud',
    '.co', '.me', '.tv', '.ai', '.xyz', '.info', '.biz',
    '.bank', '.finance', '.insurance'
  ];
  
  // For TLDs without trailing dot, only match at end of domain
  for (const tld of publicTLDs) {
    if (tld.endsWith('.')) {
      // TLD with trailing dot - can be anywhere (DNS artifact)
      if (d.includes(tld)) return true;
    } else {
      // TLD without trailing dot - must be at end
      if (d.endsWith(tld) || d.endsWith(tld + '.')) return true;
    }
  }
  
  return false;
};

// Check if domain is a pure internal domain (not a public domain with DNS suffix artifact)
// Returns true ONLY for genuinely internal domains like "my-service.default.svc.cluster.local"
const isPureInternalDomain = (domain: string): boolean => {
  if (!domain) return false;
  const d = domain.toLowerCase();
  
  // If domain contains a public TLD, it's NOT a pure internal domain
  // Example: "ghcr.io.cluster.local." contains ".io." → NOT internal
  if (hasPublicTLD(d)) return false;
  
  // Enterprise internal domains (no public TLD)
  // Example: "app-server.apps.nonprod.internal.corp." → no public TLD → internal
  // NOTE: .bank is a PUBLIC gTLD (chase.bank, barclays.bank) - do NOT list here!
  if (d.includes('.internal.')) return true;
  if (d.endsWith('.corp') || d.endsWith('.corp.')) return true;
  if (d.endsWith('.local') || d.endsWith('.local.')) return true;
  if (d.endsWith('.lan') || d.endsWith('.lan.')) return true;
  if (d.endsWith('.intra') || d.endsWith('.intra.')) return true;
  if (d.endsWith('.priv') || d.endsWith('.priv.')) return true;
  
  // Pure Kubernetes internal names (no public TLD prefix)
  // Example: "my-service.default.svc.cluster.local" → no public TLD → internal
  if (d.endsWith('.svc.cluster.local') || d.endsWith('.svc.cluster.local.')) return true;
  if (d.endsWith('.cluster.local') || d.endsWith('.cluster.local.')) return true;
  
  // Kubernetes DNS
  if (d.includes('kube-dns') || d.includes('coredns')) return true;
  
  return false;
};

// Check if node is a PUBLIC endpoint (real internet, not datacenter)
// CRITICAL: Decision is based on IP ADDRESS, not hostname/domain name!
// DNS-enriched nodes have: name=domain, ip=original_ip
// We check the IP to determine if it's public internet or private datacenter
//
// SPECIAL CASE: DNS Artifact Detection
// When network_type is "Service-Network" or "Pod-Network" for an external domain,
// it means the IP field contains a cluster-internal IP instead of real destination IP.
// This happens because:
// - DNS queries go to CoreDNS (Service-Network IP like 172.30.0.10)
// - Or the IP captured is from a pod doing the DNS lookup (Pod-Network IP like 10.131.x.x)
// In these cases, we trust the domain name to classify as PUBLIC (unless it's an internal domain).
//
// Examples:
// - name="ghcr.io", ip="172.30.0.10", network_type="Service-Network" → PUBLIC ✓
// - name="quay.io.", ip="10.131.0.122", network_type="Pod-Network" → PUBLIC ✓
// - name="internal-api.corp", ip="10.194.1.5", network_type="Internal-Network" → NOT PUBLIC ✓
// - name="ec2-52-45-34-239.compute-1.amazonaws.com", ip="52.45.34.239" → PUBLIC ✓
// - name="app.nonprod.internal.corp.", ip="172.30.0.10" → NOT PUBLIC (internal domain) ✓
const isPublicEndpoint = (node: DependencyNode): boolean => {
  const name = node.name || '';
  // Check both ip and pod_ip fields (some nodes use pod_ip instead of ip)
  const ip = node.ip || (node as any).pod_ip || '';
  const networkType = node.network_type || '';
  const namespace = (node.namespace || '').toLowerCase();
  
  // 1. DNS-enriched node: Check original IP first (most reliable when IP is correct)
  //    Example: name="api.amazonaws.com", ip="52.216.100.5" → PUBLIC (52.x is public)
  //    Example: name="internal-api.corp", ip="10.194.1.5" → NOT PUBLIC (10.x is private)
  if (ip && isPublicIP(ip)) return true;
  
  // 2. CRITICAL: If IP is PRIVATE, this CANNOT be a public endpoint!
  //    Trust IP classification over domain name - private IP = internal network
  //    Example: name="api.example.local", ip="10.194.30.5" → NOT PUBLIC (private IP!)
  //    This prevents .bank gTLD domains with private IPs from being classified as public
  if (ip && isPrivateIP(ip)) return false;
  
  // 3. Raw IP node (name IS the IP address)
  //    Example: name="142.250.185.46" → PUBLIC
  //    Example: name="10.194.1.5" → NOT PUBLIC
  if (isPublicIP(name)) return true;
  
  // 4. If no IP info available but name is a public IP format
  if (isUnresolvedIP(name) && isPublicIP(name)) return true;
  
  // 5. DATACENTER namespace/network check - trust namespace and network_type over domain name
  //    If namespace is 'datacenter' (set by backend for internal corporate domains),
  //    or network_type indicates DATACENTER (Internal-Network or Private-Network),
  //    this is a private datacenter endpoint, NOT public internet.
  //    Even if domain looks external, trust namespace/network_type classification!
  if (namespace === 'datacenter' || namespace === 'internal-network' || namespace === 'private-network') {
    // Explicit datacenter namespace from backend - NOT PUBLIC
    return false;
  }
  const isDatacenterNetwork = networkType === 'Internal-Network' || networkType === 'Private-Network';
  if (isDatacenterNetwork) {
    // network_type explicitly says this is datacenter - NOT PUBLIC
    return false;
  }
  
  // 6. Domain-based PUBLIC detection for external namespace:
  //    If namespace is "external" AND name is a domain with PUBLIC TLD,
  //    AND it's NOT a pure internal domain (enterprise domains),
  //    AND network_type is NOT datacenter (checked above),
  //    then classify as PUBLIC.
  //
  //    This handles:
  //    - DNS artifacts with cluster-internal IPs (Service-Network, Pod-Network)
  //    - DNS artifacts with missing IP/network_type
  //    - DNS search domain suffixes (oauth-login.cloud.huawei.com.cluster.local.)
  //
  //    Examples:
  //    - "oauth-login.cloud.huawei.com" + network_type="" → PUBLIC ✓
  //    - "oauth-login.cloud.huawei.com.cluster.local." + network_type="" → PUBLIC ✓
  //    - "ghcr.io" + network_type="Service-Network" → PUBLIC ✓
  //    - "internal-api.corp" + network_type="Internal-Network" → NOT PUBLIC (step 4) ✓
  //    - "my-service.default.svc.cluster.local." → no public TLD → NOT PUBLIC ✓
  //    - "test.apps.nonprod.internal.corp." → isPureInternalDomain → NOT PUBLIC ✓
  if (namespace === 'external' && isDomainName(name) && hasPublicTLD(name) && !isPureInternalDomain(name)) {
    // External namespace + domain with public TLD + NOT datacenter network = PUBLIC
    return true;
  }
  
  return false;
};

// Check if IP is a public/external IP (real internet IP)
const isPublicIP = (ip: string): boolean => {
  if (!ip) return false;
  const parts = ip.split('.').map(Number);
  if (parts.length !== 4) return false;
  
  // CRITICAL: Validate that all parts are valid numbers (0-255)
  // This prevents domain names like "api.example.com" from being
  // incorrectly classified as public IPs (they split into 4 parts but are NaN)
  if (parts.some(p => isNaN(p) || p < 0 || p > 255)) return false;
  
  // Private/Reserved IP ranges - NOT public (real internet IPs)
  if (parts[0] === 10) return false;                              // 10.0.0.0/8 - Private
  if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return false; // 172.16.0.0/12 - Private
  if (parts[0] === 192 && parts[1] === 168) return false;         // 192.168.0.0/16 - Private
  if (parts[0] === 127) return false;                              // 127.0.0.0/8 - Loopback
  if (parts[0] === 169 && parts[1] === 254) return false;         // 169.254.0.0/16 - Link-local
  if (parts[0] === 0) return false;                                // 0.0.0.0/8
  if (parts[0] >= 224) return false;                               // 224.0.0.0+ - Multicast & Reserved
  
  // Carrier-Grade NAT (CGNAT) - RFC 6598 - NOT real public internet
  // 100.64.0.0/10 = 100.64.0.0 - 100.127.255.255
  if (parts[0] === 100 && parts[1] >= 64 && parts[1] <= 127) return false;
  
  // Documentation/Test ranges - NOT real public internet
  if (parts[0] === 198 && parts[1] >= 18 && parts[1] <= 19) return false;  // 198.18.0.0/15 - Benchmark
  if (parts[0] === 198 && parts[1] === 51 && parts[2] === 100) return false; // 198.51.100.0/24 - TEST-NET-2
  if (parts[0] === 203 && parts[1] === 0 && parts[2] === 113) return false;  // 203.0.113.0/24 - TEST-NET-3
  if (parts[0] === 192 && parts[1] === 0 && parts[2] === 2) return false;    // 192.0.2.0/24 - TEST-NET-1
  
  return true;
};

// Public IP color (orange/amber for external)
const PUBLIC_IP_COLOR = '#f59e0b';

// Check if node name is an unresolved IP address (DNS not resolved or hardcoded IP)
// This is used to identify dependencies that should be converted to FQDN
const isUnresolvedIP = (name: string): boolean => {
  if (!name) return false;
  // Check if name matches IPv4 pattern
  const ipv4Pattern = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
  return ipv4Pattern.test(name.trim());
};

// Check if IP is a private/datacenter IP (not public internet, not cluster pod)
// These are IPs in private ranges that are outside the Kubernetes cluster
// but inside the datacenter (e.g., databases, legacy systems, internal services)
const isPrivateIP = (ip: string): boolean => {
  if (!ip) return false;
  const parts = ip.split('.').map(Number);
  if (parts.length !== 4) return false;
  
  // Private IP ranges (RFC 1918)
  if (parts[0] === 10) return true;                              // 10.0.0.0/8
  if (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) return true; // 172.16.0.0/12
  if (parts[0] === 192 && parts[1] === 168) return true;         // 192.168.0.0/16
  
  return false;
};

const isNoiseNode = (name: string): boolean => {
  if (!name) return false;
  const trimmed = name.trim();
  if (trimmed === '0.0.0.0' || trimmed.startsWith('0.0.0.0:')) return true;
  if (trimmed.endsWith('.in-addr.arpa') || trimmed.endsWith('.in-addr.arpa.')) return true;
  return false;
};

// Check if node is a DATACENTER node (private, outside Kubernetes cluster)
// This is for the "DataCenter" filter - shows internal datacenter dependencies
// Includes: databases, legacy systems, internal APIs, private servers
// Check if IP is a cluster internal IP (pod network, service network, node network)
// These are NOT datacenter IPs - they are kubernetes cluster infrastructure
const isClusterInternalIP = (node: DependencyNode): boolean => {
  const namespace = node.namespace || '';
  const networkType = (node as any).network_type || '';
  
  // 1. Explicit network_type from backend = definitely cluster internal
  //    ONLY Pod-Network, Service-Network, SDN-Gateway, Node-Network are cluster internal
  //    Internal-Network and Private-Network are DATACENTER (not cluster internal)
  if (networkType === 'SDN-Gateway' || networkType === 'Node-Network' || 
      networkType === 'Pod-Network' || networkType === 'Service-Network') {
    return true;
  }
  
  // 2. Real Kubernetes namespace = cluster internal
  //    Cluster pods have namespaces like: kube-system, prod-xxx, openshift-xxx
  //    
  //    EXCLUDE pseudo-namespaces created by backend for CIDR classification:
  //    - 'external': External endpoints (internet, other clusters)
  //    - 'unknown': Unknown IPs
  //    - 'internal-network': Datacenter IPs (10.x.x.x not in pod/service range)
  //    - 'cluster-network': Could be either (ambiguous)
  //    - 'sdn-infrastructure': SDN gateways (handled by network_type above)
  const nsLower = namespace.toLowerCase();
  const isPseudoNamespace = 
    nsLower === 'external' || 
    nsLower === 'unknown' || 
    nsLower === '' ||
    nsLower === 'internal-network' ||   // Backend pseudo-namespace for datacenter IPs
    nsLower === 'private-network' ||    // Backend pseudo-namespace for datacenter IPs
    nsLower === 'cluster-network' ||    // Backend pseudo-namespace (ambiguous)
    nsLower === 'sdn-infrastructure' || // Backend pseudo-namespace for SDN
    namespace.match(/^\d+\.\d+\.\d+\.\d+$/);  // Not an IP as namespace
  
  // If it's a real K8s namespace (not pseudo), it's cluster internal
  if (!isPseudoNamespace) {
    return true;
  }
  
  return false;
};

const isDataCenterNode = (node: DependencyNode): boolean => {
  const name = node.name || '';
  const namespace = (node.namespace || '').toLowerCase();
  // Check both ip and pod_ip fields (some nodes use pod_ip instead of ip)
  const ip = node.ip || (node as any).pod_ip || '';
  
  // CRITICAL: DataCenter = Private IP that is NOT cluster internal
  // OR internal DNS endpoints (corporate domains like .corp, .internal, .local)
  
  // 0. Explicit DataCenter namespace from backend (for internal DNS endpoints)
  //    Backend sets namespace='datacenter' for internal corporate domains
  if (namespace === 'datacenter') {
    return true;
  }
  
  // 0b. Internal-network namespace with DNS name = DataCenter
  //     These are DNS endpoints pointing to internal/corporate services
  if ((namespace === 'internal-network' || namespace === 'private-network') && isDomainName(name)) {
    return true;
  }
  
  // Get the effective IP to check
  const effectiveIP = ip || (isUnresolvedIP(name) ? name : '');
  
  // 1. If it's a public IP → NOT datacenter (it's public internet)
  if (effectiveIP && isPublicIP(effectiveIP)) {
    return false;
  }
  if (isPublicIP(name)) {
    return false;
  }
  
  // 2. If it's a cluster internal IP → NOT datacenter
  if (isClusterInternalIP(node)) {
    return false;
  }
  
  // 3. If it's a private IP and NOT cluster internal → DataCenter
  if (effectiveIP && isPrivateIP(effectiveIP)) {
    return true;
  }
  
  // 4. No IP info → CANNOT determine if DataCenter
  //    Don't assume DataCenter without IP evidence
  //    This prevents showing all external nodes as DataCenter when ip field is missing
  //    NOTE: If ip field is empty in Neo4j, we can't categorize - this is a data issue
  
  return false;
};

// Clean node name and add emoji for public/datacenter IPs
const cleanNodeName = (name: string, id: string): { displayName: string; isPublicIP: boolean; isDataCenterIP: boolean; isSDNGateway: boolean } => {
  let baseName = name;
  
  if (!name || name === 'unknown') {
    const parts = id?.split(':') || [];
    if (parts.length >= 3) {
      baseName = parts[parts.length - 1].substring(0, 20);
    } else {
      baseName = id?.substring(0, 15) || 'unknown';
    }
  } else if (name.startsWith('{') || name.startsWith("{'")) {
    const nameMatch = name.match(/['"]?name['"]?\s*:\s*['"]([^'"]+)['"]/);
    if (nameMatch) baseName = nameMatch[1].substring(0, 25);
  }
  
  // Check if name is just an IP address
  const isIpOnlyName = baseName?.match(/^\d+\.\d+\.\d+\.\d+$/);
  
  if (isIpOnlyName) {
    const parts = baseName.split('.').map(Number);
    const lastOctet = parts[3];
    
    if (isPublicIP(baseName)) {
      // Real external/public IP (internet)
      return { 
        displayName: baseName, 
        isPublicIP: true,
        isDataCenterIP: false,
        isSDNGateway: false
      };
    } else if (isPrivateIP(baseName)) {
      // Check for SDN Gateway pattern: .1 addresses are typically subnet gateways
      // Common patterns: 10.x.x.1, 172.x.x.1, 192.168.x.1
      if (lastOctet === 1) {
        // SDN Gateway - subnet's first IP (gateway)
        return { 
          displayName: baseName, 
          isPublicIP: false,
          isDataCenterIP: false,
          isSDNGateway: true
        };
      }
      
      // Other private IPs - datacenter/internal network
      return { 
        displayName: baseName, 
        isPublicIP: false,
        isDataCenterIP: true,
        isSDNGateway: false
      };
    }
  }
  
  const truncated = baseName.length > 25 ? baseName.substring(0, 22) + '...' : baseName;
  return { displayName: truncated, isPublicIP: false, isDataCenterIP: false, isSDNGateway: false };
};

// Layout types - 18 unique options optimized for network/service maps
// Original 12 + 6 new smart layouts based on data characteristics
type LayoutType = 'hub' | 'cluster' | 'force' | 'radial' | 'circle' | 'concentric' | 'grid' | 'tree' | 'star' | 'mesh' | 'layered' | 'organic'
  | 'tier' | 'owner' | 'network' | 'port' | 'error' | 'flow';

const layoutOptions = [
  // Original 12 layouts
  { value: 'hub', icon: <AimOutlined />, title: 'Hub', desc: 'Most connected nodes in center' },
  { value: 'concentric', icon: <ShareAltOutlined />, title: 'Concentric', desc: 'Rings by connection count' },
  { value: 'cluster', icon: <GatewayOutlined />, title: 'Cluster', desc: 'Grouped by namespace' },
  { value: 'force', icon: <ApiOutlined />, title: 'Force', desc: 'Organic spread' },
  { value: 'radial', icon: <NodeExpandOutlined />, title: 'Radial', desc: 'Expanding rings' },
  { value: 'circle', icon: <RadarChartOutlined />, title: 'Circle', desc: 'Even distribution' },
  { value: 'grid', icon: <AppstoreOutlined />, title: 'Grid', desc: 'Matrix layout' },
  { value: 'tree', icon: <ForkOutlined />, title: 'Tree', desc: 'Hierarchical' },
  { value: 'star', icon: <DeploymentUnitOutlined />, title: 'Star', desc: 'Central hub pattern' },
  { value: 'mesh', icon: <CompressOutlined />, title: 'Mesh', desc: 'Hexagonal grid' },
  { value: 'layered', icon: <PartitionOutlined />, title: 'Layered', desc: 'Horizontal bands' },
  { value: 'organic', icon: <ExpandOutlined />, title: 'Organic' },
  // New 6 smart layouts based on data characteristics
  { value: 'tier', icon: <DatabaseOutlined />, title: 'Tier', desc: 'Frontend → Backend → DB layers' },
  { value: 'owner', icon: <TeamOutlined />, title: 'Owner', desc: 'Deployment/StatefulSet zones' },
  { value: 'network', icon: <GlobalOutlined />, title: 'Network', desc: 'Pod center, External outer' },
  { value: 'port', icon: <NodeIndexOutlined />, title: 'Port', desc: 'Same port grouped' },
  { value: 'error', icon: <WarningOutlined />, title: 'Error', desc: 'Error connections first' },
  { value: 'flow', icon: <SwapRightOutlined />, title: 'Flow', desc: 'Source left, target right' },
];

// Calculate connection degree for each node
const calculateNodeDegrees = (nodes: DependencyNode[], edges: DependencyEdge[]): Record<string, number> => {
  const degrees: Record<string, number> = {};
  nodes.forEach(n => { degrees[n.id] = 0; });
  
  edges.forEach(edge => {
    if (edge.source_id in degrees) {
      degrees[edge.source_id] = (degrees[edge.source_id] || 0) + 1;
    }
    if (edge.target_id in degrees) {
      degrees[edge.target_id] = (degrees[edge.target_id] || 0) + 1;
    }
  });
  
  return degrees;
};

// ============================================
// NAMESPACE-CENTRIC VIEW HELPERS
// ============================================

// Node classification for namespace-centric view
interface NodeClassification {
  primaryNodes: DependencyNode[];      // Nodes in selected namespace
  externalNodes: DependencyNode[];     // Nodes connected to primary but in different namespace
  primaryNodeIds: Set<string>;
  externalNodeIds: Set<string>;
}

// Classify nodes into primary and external based on selected namespaces (multi-select support)
const classifyNodes = (
  nodes: DependencyNode[], 
  edges: DependencyEdge[], 
  selectedNamespaces: string[] = []  // Changed from string to string[]
): NodeClassification => {
  if (selectedNamespaces.length === 0) {
    // No namespace filter - all nodes are primary
    return {
      primaryNodes: nodes,
      externalNodes: [],
      primaryNodeIds: new Set(nodes.map(n => n.id)),
      externalNodeIds: new Set()
    };
  }
  
  // Use Set for O(1) lookup performance
  const selectedNsSet = new Set(selectedNamespaces);
  
  // Primary: nodes in ANY of the selected namespaces
  const primaryNodes = nodes.filter(n => selectedNsSet.has(n.namespace || ''));
  const primaryNodeIds = new Set(primaryNodes.map(n => n.id));
  
  // Find external nodes connected to primary nodes (inclusive mode)
  // These are nodes that communicate with selected namespaces but are not in them
  const connectedExternalIds = new Set<string>();
  edges.forEach(edge => {
    if (primaryNodeIds.has(edge.source_id) && !primaryNodeIds.has(edge.target_id)) {
      connectedExternalIds.add(edge.target_id);
    }
    if (primaryNodeIds.has(edge.target_id) && !primaryNodeIds.has(edge.source_id)) {
      connectedExternalIds.add(edge.source_id);
    }
  });
  
  const externalNodes = nodes.filter(n => connectedExternalIds.has(n.id));
  
  return {
    primaryNodes,
    externalNodes,
    primaryNodeIds,
    externalNodeIds: connectedExternalIds
  };
};


// Apply layout to nodes with namespace-centric awareness (multi-namespace support)
const applyLayout = (
  nodes: DependencyNode[], 
  layout: LayoutType, 
  spacing: number = 180, 
  nodeSize: number = 40, 
  edges: DependencyEdge[] = [],
  selectedNamespaces: string[] = [],  // Changed from string to string[]
  externalNodeIds?: Set<string>
): Node[] => {
  const count = nodes.length;
  if (count === 0) return [];
  
  // Calculate degrees for hub/concentric layouts
  const degrees = calculateNodeDegrees(nodes, edges);
  const maxDegree = Math.max(...Object.values(degrees), 1);
  
  // ============================================
  // NAMESPACE-CENTRIC: Separate primary and external nodes
  // Multi-namespace support: Use Set for O(1) lookup
  // ============================================
  const selectedNsSet = new Set(selectedNamespaces);
  const hasNamespaceFilter = selectedNamespaces.length > 0;
  
  const isPrimaryNode = (n: DependencyNode) => !hasNamespaceFilter || selectedNsSet.has(n.namespace || '');
  const isExternalNodeCheck = (n: DependencyNode) => hasNamespaceFilter && externalNodeIds?.has(n.id);
  
  const primaryNodes = nodes.filter(isPrimaryNode);
  const externalNodes = nodes.filter(n => isExternalNodeCheck(n));
  const primaryCount = primaryNodes.length;
  const externalCount = externalNodes.length;
  
  // Center coordinates
  const centerX = 500;
  const centerY = 400;
  
  // ============================================
  // PERFORMANCE: Pre-calculate metrics ONLY for new smart layouts
  // This block only runs when tier/owner/network/port/error/flow layout is selected
  // For original 12 layouts, this is skipped entirely (zero overhead)
  // ============================================
  const needsPreCalculation = ['tier', 'owner', 'network', 'port', 'error', 'flow'].includes(layout);
  
  // Lazy-initialized maps (only populated if needed)
  const nodeTrafficMap: Record<string, number> = {};
  const nodeErrorMap: Record<string, number> = {};
  const nodeOutDegree: Record<string, number> = {};
  const nodeInDegree: Record<string, number> = {};
  const nodePortMap: Record<string, number> = {};
  let maxTraffic = 1;
  let maxErrorScore = 1;
  
  if (needsPreCalculation) {
    const nodePortCounts: Record<string, Record<number, number>> = {};
    
    // Initialize - O(n)
    nodes.forEach(n => { 
      nodeTrafficMap[n.id] = 0; 
      nodeErrorMap[n.id] = 0;
      nodeOutDegree[n.id] = 0;
      nodeInDegree[n.id] = 0;
      nodePortCounts[n.id] = {};
    });
    
    // Single pass through edges - O(e)
    edges.forEach(e => {
      const reqCount = e.request_count || 0;
      const errCount = e.error_count || 0;
      const port = e.port || 0;
      
      if (e.source_id in nodeTrafficMap) {
        nodeTrafficMap[e.source_id] += reqCount;
        nodeErrorMap[e.source_id] += errCount;
        nodeOutDegree[e.source_id]++;
        nodePortCounts[e.source_id][port] = (nodePortCounts[e.source_id][port] || 0) + 1;
      }
      if (e.target_id in nodeTrafficMap) {
        nodeTrafficMap[e.target_id] += reqCount;
        nodeErrorMap[e.target_id] += errCount;
        nodeInDegree[e.target_id]++;
        nodePortCounts[e.target_id][port] = (nodePortCounts[e.target_id][port] || 0) + 1;
      }
    });
    
    // Calculate most common port per node - O(n)
    nodes.forEach(n => {
      const ports = nodePortCounts[n.id];
      const sorted = Object.entries(ports).sort((a, b) => b[1] - a[1]);
      nodePortMap[n.id] = sorted.length > 0 ? parseInt(sorted[0][0]) : 0;
    });
    
    // Safe max calculation without spread (avoids stack overflow for 10K+ nodes)
    for (const id in nodeTrafficMap) {
      if (nodeTrafficMap[id] > maxTraffic) maxTraffic = nodeTrafficMap[id];
      if (nodeErrorMap[id] > maxErrorScore) maxErrorScore = nodeErrorMap[id];
    }
  }
  
  // ============================================
  // PERFORMANCE FIX: Pre-calculate groups & indexes for new layouts
  // Converts O(n²) filter+findIndex → O(n) single pass + O(1) lookup
  // ============================================
  
  // Helper functions for tier/owner/network classification
  const getTier = (n: DependencyNode): number => {
    const labels = (n as any).labels || {};
    const tier = (labels['tier'] || labels['app.kubernetes.io/component'] || '').toLowerCase();
    const name = (n.name || '').toLowerCase();
    if (tier === 'external' || n.network_type === 'External') return 4;
    if (tier === 'ingress' || tier === 'gateway' || tier === 'edge' ||
        /^(ingress|gateway|edge|envoy|istio|nginx|haproxy|traefik)/i.test(name)) return 0;
    if (tier === 'frontend' || tier === 'ui' || tier === 'web' ||
        /^(web|ui|frontend|react|angular|vue|next|nuxt)/i.test(name) ||
        name.includes('-ui') || name.includes('-web') || name.includes('-frontend')) return 1;
    if (tier === 'database' || tier === 'db' || tier === 'data' ||
        /^(db|database|postgres|mysql|mariadb|oracle|mssql|redis|mongo|kafka|elastic|rabbitmq|vault|consul)/i.test(name) ||
        name.includes('-db') || name.includes('-cache') || name.includes('-queue')) return 3;
    return 2;
  };
  
  const getOwnerZone = (n: DependencyNode): number => {
    const ownerKind = (n.owner_kind || '').toLowerCase();
    if (ownerKind === 'statefulset') return 0;
    if (ownerKind === 'daemonset') return 2;
    return 1;
  };
  
  const getNetworkRing = (n: DependencyNode): number => {
    const netType = n.network_type || '';
    if (netType === 'Pod-Network') return 0;
    if (netType === 'Service-Network') return 1;
    return 2;
  };
  
  const getPortGroup = (port: number): number => {
    if (port === 443 || port === 8443) return 0;
    if (port === 80 || port === 8080) return 1;
    if (port >= 5432 && port <= 5439) return 2;
    if (port >= 3306 && port <= 3309) return 3;
    if (port >= 6379 && port <= 6389) return 4;
    if (port >= 9090 && port <= 9099) return 5;
    return 6;
  };
  
  // Pre-calculated group maps (only for new layouts)
  const tierGroups: Record<number, { nodes: DependencyNode[], indexMap: Record<string, number> }> = {};
  const ownerGroups: Record<number, { nodes: DependencyNode[], indexMap: Record<string, number> }> = {};
  const networkGroups: Record<number, { nodes: DependencyNode[], indexMap: Record<string, number> }> = {};
  const portGroups: Record<number, { nodes: DependencyNode[], indexMap: Record<string, number> }> = {};
  const exactPortGroups: Record<number, { nodes: DependencyNode[], indexMap: Record<string, number> }> = {};
  let errorSortedNodes: DependencyNode[] = [];
  const errorIndexMap: Record<string, number> = {};
  let errorNodesCount = 0;  // Pre-calculated count
  let healthyNodesCount = 0;
  
  if (needsPreCalculation) {
    // Single pass to build all group maps - O(n)
    nodes.forEach(n => {
      const isPrimary = isPrimaryNode(n);
      
      // Tier groups (only primary nodes)
      if (isPrimary) {
        const tier = getTier(n);
        if (!tierGroups[tier]) tierGroups[tier] = { nodes: [], indexMap: {} };
        tierGroups[tier].indexMap[n.id] = tierGroups[tier].nodes.length;
        tierGroups[tier].nodes.push(n);
      }
      
      // Owner groups (only primary nodes)
      if (isPrimary) {
        const zone = getOwnerZone(n);
        if (!ownerGroups[zone]) ownerGroups[zone] = { nodes: [], indexMap: {} };
        ownerGroups[zone].indexMap[n.id] = ownerGroups[zone].nodes.length;
        ownerGroups[zone].nodes.push(n);
      }
      
      // Network groups (all nodes)
      const ring = getNetworkRing(n);
      if (!networkGroups[ring]) networkGroups[ring] = { nodes: [], indexMap: {} };
      networkGroups[ring].indexMap[n.id] = networkGroups[ring].nodes.length;
      networkGroups[ring].nodes.push(n);
      
      // Port groups (all nodes)
      const port = nodePortMap[n.id] || 0;
      const portGroup = getPortGroup(port);
      if (!portGroups[portGroup]) portGroups[portGroup] = { nodes: [], indexMap: {} };
      portGroups[portGroup].indexMap[n.id] = portGroups[portGroup].nodes.length;
      portGroups[portGroup].nodes.push(n);
      
      // Exact port groups
      if (!exactPortGroups[port]) exactPortGroups[port] = { nodes: [], indexMap: {} };
      exactPortGroups[port].indexMap[n.id] = exactPortGroups[port].nodes.length;
      exactPortGroups[port].nodes.push(n);
    });
    
    // Error sorted nodes - O(n log n)
    errorSortedNodes = [...nodes].sort((a, b) => 
      (nodeErrorMap[b.id] || 0) - (nodeErrorMap[a.id] || 0)
    );
    errorSortedNodes.forEach((n, idx) => { 
      errorIndexMap[n.id] = idx;
      if ((nodeErrorMap[n.id] || 0) > 0) errorNodesCount++;
    });
    healthyNodesCount = errorSortedNodes.length - errorNodesCount;
  }

  return nodes.map((node, idx) => {
    const nodeName = node.name || '';
    const { displayName, isPublicIP: isNodePublicIP, isDataCenterIP: isNodeDataCenterIP, isSDNGateway: isSDNGatewayByIP } = cleanNodeName(nodeName, node.id);
    
    // Check if this node is external (in namespace-centric view)
    const isExternal = isExternalNodeCheck(node);
    const primaryIdx = primaryNodes.findIndex(n => n.id === node.id);
    const externalIdx = externalNodes.findIndex(n => n.id === node.id);
    
    // Node type detection for consistent styling with incremental update
    const isServiceNode = node.owner_kind === 'Service';
    // SDN Gateway: from backend network_type, name pattern, OR IP ending with .1
    const isSDNGateway = nodeName.includes('SDN-Gateway') || node.network_type === 'SDN-Gateway' || isSDNGatewayByIP;
    
    // Get network type info from backend classification
    const networkTypeInfo = getNetworkTypeInfo(node.network_type);
    const hasNetworkType = !!networkTypeInfo && !isServiceNode && !isSDNGateway;
    
    // DataCenter IP color (cyan)
    const DATACENTER_IP_COLOR = '#06b6d4';
    
    // Color: consistent with incremental update (Service/SDN-Gateway/Network Types get special colors)
    let nsColor: string;
    if (isServiceNode) {
      nsColor = '#8b5cf6';  // Purple for Service nodes
    } else if (isSDNGateway) {
      nsColor = '#ec4899';  // Pink for SDN-Gateway
    } else if (hasNetworkType && networkTypeInfo) {
      nsColor = networkTypeInfo.color;  // Use network type color for CIDR-classified nodes
    } else if (isNodePublicIP) {
      nsColor = PUBLIC_IP_COLOR;  // Orange for public IPs
    } else if (isNodeDataCenterIP) {
      nsColor = DATACENTER_IP_COLOR;  // Cyan for datacenter IPs
    } else if (isExternal) {
      nsColor = getNamespaceColor(node.namespace || 'external');
    } else {
      nsColor = getNamespaceColor(node.namespace || 'default');
    }
    
    let x = 0, y = 0;

    switch (layout) {
      case 'grid': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: bottom rows
          const extCols = Math.ceil(Math.sqrt(externalCount));
          const extRow = Math.floor(externalIdx / extCols);
          const extCol = externalIdx % extCols;
          x = extCol * spacing + 100;
          y = (Math.ceil(primaryCount / Math.ceil(Math.sqrt(primaryCount))) + extRow + 1) * spacing + 150;
        } else {
          // Primary nodes: top rows
          const cols = Math.ceil(Math.sqrt(primaryCount || count));
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          x = (nodeIdx % cols) * spacing + 100;
          y = Math.floor(nodeIdx / cols) * spacing + 100;
        }
        break;
      }
      case 'circle': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outer circle
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          const radius = Math.max(350, primaryCount * 15 + 200);
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        } else {
          // Primary nodes: inner circle
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const nodeCount = primaryCount || count;
          const angle = (2 * Math.PI * nodeIdx) / nodeCount;
          const radius = Math.max(150, nodeCount * 10);
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        }
        break;
      }
      case 'radial': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outermost ring
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1) - Math.PI / 2;
          const radius = Math.max(400, primaryCount * 12 + 250);
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        } else {
          // Primary nodes: inner rings
          const nodesPerRing = 8;
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const ring = Math.floor(nodeIdx / nodesPerRing);
          const posInRing = nodeIdx % nodesPerRing;
          const angle = (2 * Math.PI * posInRing) / nodesPerRing + (ring * 0.3);
          const radius = (ring + 1) * spacing * 0.6;
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        }
        break;
      }
      case 'tree': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: separate tree on the right
          const level = Math.floor(Math.log2(externalIdx + 1));
          const nodesInLevel = Math.pow(2, level);
          const posInLevel = externalIdx - Math.pow(2, level) + 1;
          const levelWidth = nodesInLevel * spacing * 0.8;
          x = (posInLevel + 0.5) * (levelWidth / nodesInLevel) - levelWidth / 2 + 900;
          y = level * spacing * 0.7 + 100;
        } else {
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const level = Math.floor(Math.log2(nodeIdx + 1));
          const nodesInLevel = Math.pow(2, level);
          const posInLevel = nodeIdx - Math.pow(2, level) + 1;
          const levelWidth = nodesInLevel * spacing;
          x = (posInLevel + 0.5) * (levelWidth / nodesInLevel) - levelWidth / 2 + 400;
          y = level * spacing * 0.7 + 100;
        }
        break;
      }
      case 'cluster': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: grouped by their namespace on outer ring
          const extNamespaces = Array.from(new Set(externalNodes.map(n => n.namespace || 'external')));
          const extNsIdx = extNamespaces.indexOf(node.namespace || 'external');
          const nodesInExtNs = externalNodes.filter(n => (n.namespace || 'external') === (node.namespace || 'external'));
          const idxInExtNs = nodesInExtNs.findIndex(n => n.id === node.id);
          
          const extClusterAngle = (2 * Math.PI * extNsIdx) / Math.max(extNamespaces.length, 1);
          const extClusterRadius = 450;
          const extCenterX = extClusterRadius * Math.cos(extClusterAngle) + centerX;
          const extCenterY = extClusterRadius * Math.sin(extClusterAngle) + centerY;
          const extNodeAngle = (2 * Math.PI * idxInExtNs) / Math.max(nodesInExtNs.length, 1);
          const extNodeRadius = Math.min(80, nodesInExtNs.length * 6);
          x = extCenterX + extNodeRadius * Math.cos(extNodeAngle);
          y = extCenterY + extNodeRadius * Math.sin(extNodeAngle);
        } else {
          // Primary nodes: center cluster(s)
          // Multi-namespace: use selectedNamespaces array, fallback to all unique namespaces
          const primNamespaces = hasNamespaceFilter 
            ? selectedNamespaces 
            : Array.from(new Set(nodes.map(n => n.namespace || 'default')));
          const nsIdx = primNamespaces.indexOf(node.namespace || 'default');
          const nodesInNs = primaryNodes.filter(n => (n.namespace || 'default') === (node.namespace || 'default'));
          const idxInNs = nodesInNs.findIndex(n => n.id === node.id);
          
          if (hasNamespaceFilter && selectedNamespaces.length === 1) {
            // Single namespace selected: center cluster layout
            const nodeAngle = (2 * Math.PI * idxInNs) / Math.max(nodesInNs.length, 1);
            const nodeRadius = Math.min(200, Math.sqrt(nodesInNs.length) * 35);
            x = centerX + nodeRadius * Math.cos(nodeAngle);
            y = centerY + nodeRadius * Math.sin(nodeAngle);
          } else {
            // Multiple namespaces or no filter: distribute in clusters
            const clusterAngle = (2 * Math.PI * nsIdx) / primNamespaces.length;
            const clusterRadius = 300;
            const clusterCenterX = clusterRadius * Math.cos(clusterAngle) + centerX;
            const clusterCenterY = clusterRadius * Math.sin(clusterAngle) + centerY;
            const nodeAngle = (2 * Math.PI * idxInNs) / Math.max(nodesInNs.length, 1);
            const nodeRadius = Math.min(100, nodesInNs.length * 8);
            x = clusterCenterX + nodeRadius * Math.cos(nodeAngle);
            y = clusterCenterY + nodeRadius * Math.sin(nodeAngle);
          }
        }
        break;
      }
      case 'force': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outer positions grouped by namespace
          const extNamespaces = Array.from(new Set(externalNodes.map(n => n.namespace || 'external')));
          const extNsIdx = extNamespaces.indexOf(node.namespace || 'external');
          const nodesInExtNs = externalNodes.filter(n => (n.namespace || 'external') === (node.namespace || 'external'));
          const idxInExtNs = nodesInExtNs.findIndex(n => n.id === node.id);
          
          const extAngle = (2 * Math.PI * extNsIdx) / Math.max(extNamespaces.length, 1) - Math.PI / 4;
          const extBaseRadius = 400;
          const extCenterX = extBaseRadius * Math.cos(extAngle) + centerX;
          const extCenterY = extBaseRadius * Math.sin(extAngle) + centerY;
          const extNodeAngle = (2 * Math.PI * idxInExtNs) / Math.max(nodesInExtNs.length, 1);
          const extNodeRadius = Math.min(70, nodesInExtNs.length * 5);
          x = extCenterX + extNodeRadius * Math.cos(extNodeAngle);
          y = extCenterY + extNodeRadius * Math.sin(extNodeAngle);
        } else {
          // Primary nodes: center with force-directed feel
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const nodeCount = primaryCount || count;
          const goldenAngle = Math.PI * (3 - Math.sqrt(5));
          const angle = nodeIdx * goldenAngle;
          const radius = Math.sqrt(nodeIdx + 1) * spacing * 0.4;
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        }
        break;
      }
      case 'hub': {
        const nodeDegree = degrees[node.id] || 0;
        
        if (hasNamespaceFilter && isExternal) {
          // External nodes: always on outer ring, sorted by connection count
          const normalizedDegree = nodeDegree / maxDegree;
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          const baseRadius = 380 + (1 - normalizedDegree) * 80; // More connected = closer
          x = centerX + baseRadius * Math.cos(angle);
          y = centerY + baseRadius * Math.sin(angle);
        } else {
          // Primary nodes: hub layout with most connected in center
          const normalizedDegree = 1 - (nodeDegree / maxDegree);
          const baseRadius = normalizedDegree * spacing * 2;
          const jitter = ((primaryIdx >= 0 ? primaryIdx : idx) % 7) * 0.9;
          const radius = Math.max(20, baseRadius + jitter * 15);
          const angle = (2 * Math.PI * (primaryIdx >= 0 ? primaryIdx : idx)) / (primaryCount || count) + (normalizedDegree * 0.3);
          x = centerX + radius * Math.cos(angle);
          y = centerY + radius * Math.sin(angle);
        }
        break;
      }
      case 'concentric': {
        const nodeDegree = degrees[node.id] || 0;
        
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outermost ring
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          const ringRadius = spacing * 4;
          x = centerX + ringRadius * Math.cos(angle);
          y = centerY + ringRadius * Math.sin(angle);
        } else {
          // Primary nodes: concentric rings by degree
          const percentile = nodeDegree / maxDegree;
          const ring = percentile > 0.8 ? 0 : percentile > 0.6 ? 1 : percentile > 0.4 ? 2 : percentile > 0.2 ? 3 : 4;
          
          const nodesInSameRing = primaryNodes.filter((n, i) => {
            const d = degrees[n.id] || 0;
            const p = d / maxDegree;
            const r = p > 0.8 ? 0 : p > 0.6 ? 1 : p > 0.4 ? 2 : p > 0.2 ? 3 : 4;
            return r === ring && primaryNodes.indexOf(n) < primaryIdx;
          }).length;
          
          const totalInRing = primaryNodes.filter(n => {
            const d = degrees[n.id] || 0;
            const p = d / maxDegree;
            const r = p > 0.8 ? 0 : p > 0.6 ? 1 : p > 0.4 ? 2 : p > 0.2 ? 3 : 4;
            return r === ring;
          }).length;
          
          const ringRadius = (ring + 1) * spacing * 0.6;
          const angleStep = totalInRing > 0 ? (2 * Math.PI) / totalInRing : 0;
          const angle = nodesInSameRing * angleStep;
          x = centerX + ringRadius * Math.cos(angle);
          y = centerY + ringRadius * Math.sin(angle);
        }
        break;
      }
      case 'star': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: tips of outer star arms
          const armIdx = externalIdx % 8;
          const distFromCenter = Math.floor(externalIdx / 8) + 3;
          const angle = (2 * Math.PI * armIdx) / 8 + Math.PI / 8;
          const radius = distFromCenter * spacing * 0.5;
          x = centerX + radius * Math.cos(angle);
          y = centerY + radius * Math.sin(angle);
        } else {
          // Primary nodes: star pattern
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          if (nodeIdx === 0) {
            x = centerX; y = centerY;
          } else {
            const armIdx = (nodeIdx - 1) % 6;
            const distFromCenter = Math.floor((nodeIdx - 1) / 6) + 1;
            const angle = (2 * Math.PI * armIdx) / 6;
            const radius = distFromCenter * spacing * 0.6;
            x = centerX + radius * Math.cos(angle);
            y = centerY + radius * Math.sin(angle);
          }
        }
        break;
      }
      case 'mesh': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outer hex ring
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          const radius = 400;
          x = centerX + radius * Math.cos(angle);
          y = centerY + radius * Math.sin(angle);
        } else {
          // Primary nodes: hexagonal mesh
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const row = Math.floor(nodeIdx / 6);
          const col = nodeIdx % 6;
          const hexSpacing = spacing * 0.8;
          x = col * hexSpacing + (row % 2) * (hexSpacing / 2) + 200;
          y = row * hexSpacing * 0.866 + 200;
        }
        break;
      }
      case 'layered': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: right side, grouped by namespace
          const extNamespaces = Array.from(new Set(externalNodes.map(n => n.namespace || 'external')));
          const extNsIdx = extNamespaces.indexOf(node.namespace || 'external');
          const nodesInExtNs = externalNodes.filter(n => (n.namespace || 'external') === (node.namespace || 'external'));
          const idxInExtNs = nodesInExtNs.findIndex(n => n.id === node.id);
          
          const layerHeight = 150;
          x = 700 + idxInExtNs * spacing * 0.6;
          y = extNsIdx * layerHeight + 100;
        } else {
          // Primary nodes: left side
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const nodesPerRow = Math.ceil(Math.sqrt(primaryCount || count));
          const row = Math.floor(nodeIdx / nodesPerRow);
          const col = nodeIdx % nodesPerRow;
          x = col * spacing * 0.8 + 100;
          y = row * 150 + 100;
        }
        break;
      }
      case 'organic': {
        if (hasNamespaceFilter && isExternal) {
          // External nodes: outer organic ring
          const goldenAngle = Math.PI * (3 - Math.sqrt(5));
          const angle = externalIdx * goldenAngle + Math.PI;
          const radius = Math.sqrt(externalIdx + primaryCount + 10) * spacing * 0.5;
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        } else {
          // Primary nodes: center organic pattern
          const nodeIdx = primaryIdx >= 0 ? primaryIdx : idx;
          const goldenAngle = Math.PI * (3 - Math.sqrt(5));
          const angle = nodeIdx * goldenAngle;
          const radius = Math.sqrt(nodeIdx + 1) * spacing * 0.45;
          x = radius * Math.cos(angle) + centerX;
          y = radius * Math.sin(angle) + centerY;
        }
        break;
      }
      // ============================================
      // NEW SMART LAYOUTS - Data-driven positioning
      // ============================================
      case 'tier': {
        // Tier-Based Layered Layout: Frontend → Backend → Database
        // Uses pre-calculated tierGroups for O(1) lookup
        const nodeTier = getTier(node);
        const tierGroup = tierGroups[nodeTier] || { nodes: [], indexMap: {} };
        const tierIdx = tierGroup.indexMap[node.id] ?? -1;
        const tierCount = tierGroup.nodes.length;
        
        if (isExternal) {
          // External nodes: rightmost column
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          const extRadius = 80 + Math.min(externalCount, 20) * 8;
          x = 900 + extRadius * Math.cos(angle) * 0.3;
          y = centerY + extRadius * Math.sin(angle);
        } else if (tierIdx >= 0) {
          // Position by tier (left to right: 0→1→2→3)
          const tierX = 150 + nodeTier * 220;
          const tierHeight = Math.min(tierCount * 50, 500);
          const tierY = centerY - tierHeight / 2 + (tierIdx * tierHeight / Math.max(tierCount - 1, 1));
          x = tierX;
          y = tierCount === 1 ? centerY : tierY;
        } else {
          // Fallback for nodes not in any tier group
          x = centerX;
          y = centerY;
        }
        break;
      }
      case 'owner': {
        // Owner-Kind Zoning: Deployment, StatefulSet, DaemonSet in separate zones
        // Uses pre-calculated ownerGroups for O(1) lookup
        const ownerZone = getOwnerZone(node);
        const zoneGroup = ownerGroups[ownerZone] || { nodes: [], indexMap: {} };
        const zoneIdx = zoneGroup.indexMap[node.id] ?? -1;
        const zoneCount = zoneGroup.nodes.length;
        
        if (isExternal) {
          // External nodes: right side
          const extCols = Math.ceil(Math.sqrt(externalCount));
          const extRow = Math.floor(externalIdx / extCols);
          const extCol = externalIdx % extCols;
          x = 750 + extCol * spacing * 0.6;
          y = 100 + extRow * spacing * 0.6;
        } else if (zoneIdx >= 0) {
          // Zone positioning (vertical bands)
          const zoneY = 100 + ownerZone * 250;  // 0=100, 1=350, 2=600
          const zoneCols = Math.ceil(Math.sqrt(zoneCount));
          const zoneRow = Math.floor(zoneIdx / zoneCols);
          const zoneCol = zoneIdx % zoneCols;
          x = 100 + zoneCol * spacing * 0.8;
          y = zoneY + zoneRow * spacing * 0.6;
        } else {
          x = centerX;
          y = centerY;
        }
        break;
      }
      case 'network': {
        // Network-Type Concentric: Pod-Network center, External outer rings
        // Uses pre-calculated networkGroups for O(1) lookup
        const networkRing = getNetworkRing(node);
        const ringGroup = networkGroups[networkRing] || { nodes: [], indexMap: {} };
        const ringIdx = ringGroup.indexMap[node.id] ?? 0;
        const ringCount = ringGroup.nodes.length;
        
        // Concentric rings from center
        const ringRadius = 80 + networkRing * 100;
        const angle = (2 * Math.PI * ringIdx) / Math.max(ringCount, 1) - Math.PI / 2;
        x = centerX + ringRadius * Math.cos(angle);
        y = centerY + ringRadius * Math.sin(angle);
        break;
      }
      case 'port': {
        // Port-Based Clustering: Same destination port grouped together
        // Uses pre-calculated portGroups and exactPortGroups for O(1) lookup
        const nodePort = nodePortMap[node.id] || 0;
        const portGroup = getPortGroup(nodePort);
        
        // Get pre-calculated group data
        const group = portGroups[portGroup] || { nodes: [], indexMap: {} };
        const groupIdx = group.indexMap[node.id] ?? 0;
        const groupCount = group.nodes.length;
        
        // Position in port group cluster
        const groupAngle = (2 * Math.PI * portGroup) / 7;  // 7 groups (0-6)
        const groupCenterX = centerX + 200 * Math.cos(groupAngle);
        const groupCenterY = centerY + 200 * Math.sin(groupAngle);
        
        const nodeAngle = (2 * Math.PI * groupIdx) / Math.max(groupCount, 1);
        const nodeRadius = Math.min(80, groupCount * 8);
        x = groupCenterX + nodeRadius * Math.cos(nodeAngle);
        y = groupCenterY + nodeRadius * Math.sin(nodeAngle);
        break;
      }
      case 'error': {
        // Error-Centric Layout: Nodes with errors in center, healthy on outer
        // Uses pre-calculated errorSortedNodes, errorIndexMap, errorNodesCount for O(1) lookup
        const errorScore = nodeErrorMap[node.id] || 0;
        const hasErrors = errorScore > 0;
        const errorRank = errorIndexMap[node.id] ?? -1;
        
        if (isExternal) {
          // External nodes: outer ring
          const angle = (2 * Math.PI * externalIdx) / Math.max(externalCount, 1);
          x = centerX + 400 * Math.cos(angle);
          y = centerY + 400 * Math.sin(angle);
        } else if (hasErrors && errorRank >= 0) {
          // Error nodes: center cluster, position by rank
          const angle = (2 * Math.PI * errorRank) / Math.max(errorNodesCount, 1);
          const radius = 50 + (1 - errorScore / maxErrorScore) * 100;
          x = centerX + radius * Math.cos(angle);
          y = centerY + radius * Math.sin(angle);
        } else if (errorRank >= 0) {
          // Healthy nodes: outer rings
          const healthyIdx = errorRank - errorNodesCount;
          const angle = (2 * Math.PI * healthyIdx) / Math.max(healthyNodesCount, 1);
          const radius = 250 + (healthyIdx % 3) * 20;  // Slight variation for organic feel
          x = centerX + radius * Math.cos(angle);
          y = centerY + radius * Math.sin(angle);
        } else {
          x = centerX;
          y = centerY;
        }
        break;
      }
      case 'flow': {
        // Traffic Flow Direction: Source nodes left, target nodes right
        // Uses pre-calculated nodeInDegree/nodeOutDegree for O(1) lookup
        const outDeg = nodeOutDegree[node.id] || 0;
        const inDeg = nodeInDegree[node.id] || 0;
        const totalDeg = outDeg + inDeg;
        // Ratio: 0 = pure source (left), 1 = pure target (right)
        const flowPos = totalDeg === 0 ? 0.5 : inDeg / totalDeg;
        
        if (isExternal) {
          // External nodes: rightmost
          const extHeight = Math.min(externalCount * 40, 600);
          x = 900;
          y = centerY - extHeight / 2 + externalIdx * (extHeight / Math.max(externalCount - 1, 1));
        } else {
          // Position by flow ratio (left=source to right=target)
          // Simple O(1) positioning based on flow position and node hash
          const columnX = 100 + flowPos * 700;
          const nodeHash = node.id.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
          const rowOffset = (nodeHash % 15) * 35;  // Spread vertically based on hash
          x = columnX;
          y = 100 + rowOffset;
        }
        break;
      }
      default: {
        const cols = Math.ceil(Math.sqrt(count));
        x = (idx % cols) * spacing + 100;
        y = Math.floor(idx / cols) * spacing + 100;
      }
    }

    // Size: Dynamic sizing for new layouts, fixed for original layouts
    // Original layouts use fixed multiplier (no overhead)
    // New layouts use traffic-based dynamic sizing
    let size: number;
    if (needsPreCalculation) {
      const nodeTraffic = nodeTrafficMap[node.id] || 0;
      const trafficRatio = nodeTraffic > 0 
        ? Math.log10(nodeTraffic + 1) / Math.log10(maxTraffic + 1)
        : 0;
      const baseMultiplier = isExternal ? 1.0 : 1.2;
      const rangeMultiplier = isExternal ? 0.6 : 1.2;
      size = nodeSize * (baseMultiplier + trafficRatio * rangeMultiplier);
    } else {
      // Original fixed sizing (unchanged from before)
      size = nodeSize * (isExternal ? 1.5 : 1.8);
    }
    
    // Node shape: different shapes for different node types
    // Service: rounded square (25%), SDN-Gateway: hexagon-ish (35%), Network Types: custom, Pod: circle (50%)
    const nodeBorderRadius = isServiceNode ? '25%' 
      : isSDNGateway ? '35%' 
      : (hasNetworkType && networkTypeInfo) ? networkTypeInfo.borderRadius 
      : '50%';

    // Border: consistent with incremental update
    let borderStyle = isNodePublicIP ? '3px solid #fbbf24' : 'none';
    if (isExternal) {
      borderStyle = '2px dashed rgba(148, 163, 184, 0.7)';  // Slate dashed border for external
    }
    
    // Shadow: consistent with incremental update
    const boxShadow = isExternal 
      ? '0 2px 6px rgba(0,0,0,0.15)'  // Subtle shadow for external
      : (isNodePublicIP 
          ? '0 0 15px rgba(245, 158, 11, 0.5), 0 3px 10px rgba(0,0,0,0.2)' 
          : '0 3px 10px rgba(0,0,0,0.2)');

    return {
      id: node.id,
      position: { x, y },
      data: { 
        label: displayName,
        namespace: node.namespace,
        kind: node.kind,
        originalNode: node,
        isPublicIP: isNodePublicIP,
        isDataCenterIP: isNodeDataCenterIP,
        isExternal,
        isServiceNode,
        isSDNGateway,
        networkType: node.network_type,
        networkTypeInfo: networkTypeInfo,
        hasNetworkType: hasNetworkType,
      },
      draggable: true,
      style: {
        background: isExternal ? `${nsColor}99` : nsColor,  // Alpha for external nodes
        color: isExternal ? 'rgba(255,255,255,0.8)' : '#fff',
        border: borderStyle,
        borderRadius: nodeBorderRadius,
        width: size,
        height: size,
        padding: 0,
        fontSize: Math.max(9, nodeSize / 5),
        fontWeight: isExternal ? 400 : 500,
        boxShadow,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center' as const,
        opacity: isExternal ? 0.7 : 1,  // Slightly transparent for external
        overflow: 'hidden',
        lineHeight: 1.2,
        cursor: 'grab',
      },
    };
  });
};

// Extracted to module scope so React sees a stable component identity across parent re-renders,
// preventing unmount/remount that would reset the expanded state.
const AnnotationRow = React.memo(({ annKey, annValue, isDark, token }: {
  annKey: string; annValue: unknown; isDark: boolean; token: any;
}) => {
  const strVal = String(annValue);
  const isLong = strVal.length > 120;

  const { isJson, formattedJson } = React.useMemo(() => {
    const trimmed = strVal.trim();
    if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
      try {
        return { isJson: true, formattedJson: JSON.stringify(JSON.parse(trimmed), null, 2) };
      } catch { /* not valid json */ }
    }
    return { isJson: false, formattedJson: '' };
  }, [strVal]);

  const [expanded, setExpanded] = React.useState(false);
  const preRef = React.useRef<HTMLPreElement>(null);
  const overflowRef = React.useRef(false);
  const [, forceUpdate] = React.useState(0);

  // useLayoutEffect fires before browser paint, preventing "Show more" button flash
  React.useLayoutEffect(() => {
    if (isJson && preRef.current && !expanded) {
      const overflows = preRef.current.scrollHeight > preRef.current.clientHeight;
      if (overflows !== overflowRef.current) {
        overflowRef.current = overflows;
        forceUpdate(c => c + 1);
      }
    }
  }, [isJson, formattedJson, expanded]);

  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(strVal);
      message.success('Copied');
    } catch {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = strVal;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        const ok = document.execCommand('copy');
        document.body.removeChild(textarea);
        if (ok) {
          message.success('Copied');
        } else {
          message.error('Copy failed');
        }
      } catch {
        message.error('Copy failed');
      }
    }
  }, [strVal]);

  const jsonLineCount = isJson ? formattedJson.split('\n').length : 0;
  const needsShowMore = isJson ? (jsonLineCount > 4 || overflowRef.current) : isLong;

  return (
    <div style={{
      background: isDark ? token.colorBgContainer : '#fef9f0',
      borderRadius: 6,
      padding: '8px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong style={{ fontSize: 11, color: isDark ? '#ffc069' : '#d48806' }}>{annKey}</Text>
        <Tooltip title="Copy value">
          <Button
            type="text"
            size="small"
            icon={<CopyOutlined style={{ fontSize: 11 }} />}
            style={{ opacity: 0.5 }}
            onClick={handleCopy}
          />
        </Tooltip>
      </div>
      {isJson ? (
        <div>
          <pre ref={preRef} style={{
            fontSize: 10, margin: 0, padding: '4px 6px',
            background: isDark ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.03)',
            borderRadius: 4, maxHeight: expanded ? 'none' : 60, overflow: 'hidden',
            whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: isDark ? '#d9d9d9' : '#595959'
          }}>{formattedJson}</pre>
          {needsShowMore && (
            <Button type="link" size="small" style={{ padding: 0, fontSize: 10, height: 'auto' }}
              onClick={() => setExpanded(!expanded)}>{expanded ? 'Show less' : 'Show more'}</Button>
          )}
        </div>
      ) : isLong ? (
        <div>
          <Text type="secondary" style={{ fontSize: 11, wordBreak: 'break-all' }}>
            {expanded ? strVal : strVal.slice(0, 120) + '...'}
          </Text>
          <Button type="link" size="small" style={{ padding: 0, fontSize: 10, height: 'auto', marginLeft: 4 }}
            onClick={() => setExpanded(!expanded)}>{expanded ? 'Show less' : 'Show more'}</Button>
        </div>
      ) : (
        <Text type="secondary" style={{ fontSize: 11, wordBreak: 'break-all' }}>{strVal}</Text>
      )}
    </div>
  );
});

// Inner component
const MapInner: React.FC = () => {
  const { token } = theme.useToken();
  const { isDark } = useTheme();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null);

  // Filter states
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  // Multi-namespace support: Changed from string to string[] for multi-select
  const [selectedNamespaces, setSelectedNamespaces] = useState<string[]>([]);
  const [selectedPod, setSelectedPod] = useState<string | undefined>(undefined);
  
  // Backward compatibility helper - first selected namespace for API calls
  const selectedNamespace = selectedNamespaces.length > 0 ? selectedNamespaces[0] : undefined;
  const [labelSearchTerm, setLabelSearchTerm] = useState('');
  const [globalSearchTerm, setGlobalSearchTerm] = useState('');
  
  // Server-side search: debounced search term for API calls (min 3 chars)
  // This allows Neo4j to filter nodes before returning, solving the limit problem
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState('');
  
  // Debounce globalSearchTerm for search (300ms delay, min 3 chars)
  // This prevents filtering on every keystroke - only triggers after user stops typing
  useEffect(() => {
    const timer = setTimeout(() => {
      // Only search if 3+ characters (prevents expensive operations for short inputs)
      if (globalSearchTerm.length >= 3) {
        setDebouncedSearchTerm(globalSearchTerm);
      } else {
        setDebouncedSearchTerm('');
      }
    }, 300); // Reduced from 500ms for faster response
    return () => clearTimeout(timer);
  }, [globalSearchTerm]);
  
  // Multi-cluster support
  const [selectedClusterFilter, setSelectedClusterFilter] = useState<number[]>([]); // Filter by specific clusters in multi-cluster analysis
  const [showClusterBorders, setShowClusterBorders] = useState(true); // Show cluster boundaries in visualization
  
  // Error filter - when active, shows only error-containing edges and connected nodes
  const [filterErrorsOnly, setFilterErrorsOnly] = useState(false);
  
  // Namespace cache for dropdown - prevents losing other cluster namespaces when filtering
  // Cache stores ALL namespaces from initial load, dropdown uses cache instead of filtered data
  const [namespaceCache, setNamespaceCache] = useState<{
    analysisId: number | null;
    namespaces: Array<{ namespace: string; clusterId: number; clusterName: string }>;
  }>({
    analysisId: null,
    namespaces: []
  });
  
  // Cluster color palette for multi-cluster visualization
  const clusterColorPalette = useMemo(() => {
    const colors = [
      { border: '#1890ff', bg: 'rgba(24, 144, 255, 0.08)', name: 'Blue' },
      { border: '#52c41a', bg: 'rgba(82, 196, 26, 0.08)', name: 'Green' },
      { border: '#722ed1', bg: 'rgba(114, 46, 209, 0.08)', name: 'Purple' },
      { border: '#fa8c16', bg: 'rgba(250, 140, 22, 0.08)', name: 'Orange' },
      { border: '#eb2f96', bg: 'rgba(235, 47, 150, 0.08)', name: 'Magenta' },
      { border: '#13c2c2', bg: 'rgba(19, 194, 194, 0.08)', name: 'Cyan' },
      { border: '#faad14', bg: 'rgba(250, 173, 20, 0.08)', name: 'Gold' },
      { border: '#a0d911', bg: 'rgba(160, 217, 17, 0.08)', name: 'Lime' },
    ];
    return {
      colors,
      getColor: (clusterId: number, clusterIds: number[]) => {
        const index = clusterIds.indexOf(clusterId);
        if (index === -1) return { border: '#8c8c8c', bg: 'rgba(140, 140, 140, 0.08)', name: 'Gray' };
        return colors[index % colors.length];
      }
    };
  }, []);
  
  // UI states
  const [showControlPanel, setShowControlPanel] = useState(true);
  const [showFilterPanel, setShowFilterPanel] = useState(true);
  const [showHeader, setShowHeader] = useState(true);
  const [showStats, setShowStats] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [layout, setLayout] = useState<LayoutType>('cluster');
  const [nodeSize, setNodeSize] = useState(40);
  const [showLabels, setShowLabels] = useState(true);
  
  // Node detail drawer
  const [selectedNode, setSelectedNode] = useState<DependencyNode | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  
  // Filter toggles
  const [showInternalTraffic, setShowInternalTraffic] = useState(false);
  const [hideSystemNamespaces, setHideSystemNamespaces] = useState(true); // Hide openshift-*, kube-*, default by default
  const [focusPublicOnly, setFocusPublicOnly] = useState(false); // Public internet IPs and DNS-resolved external domains
  const [focusDataCenterOnly, setFocusDataCenterOnly] = useState(false); // DataCenter IPs (private, non-cluster)
  const [focusIPOnly, setFocusIPOnly] = useState(false); // Show only unresolved IP-based dependencies
  const [aggregatedView, setAggregatedView] = useState(false); // Group pods by workload name
  const [showNodeIP, setShowNodeIP] = useState(false);
  const [showProtocolLabel, setShowProtocolLabel] = useState(true);
  const [showFlowLabel, setShowFlowLabel] = useState(true);
  
  // Performance: Edge display limit - prevents browser freeze with 5000+ flows
  // Smart limit auto-adjusts based on analysis size (200/300/500)
  // User can override by selecting from dropdown - persists until page refresh
  // null = use smart limit, number = user's explicit choice, 'all' = show all
  const [userSelectedLimit, setUserSelectedLimit] = useState<number | 'all' | null>(null);
  
  // Namespace highlight
  const [highlightedNamespace, setHighlightedNamespace] = useState<string | null>(null);
  const [showNamespacePanel, setShowNamespacePanel] = useState(true);
  const [showLegendPanel, setShowLegendPanel] = useState(true);
  
  // Selected node focus (when drawer is open)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  
  // Event type filter for highlighting nodes with specific events
  const [highlightedEventType, setHighlightedEventType] = useState<string | null>(null);
  
  // Animation control
  const [isAnimationPaused, setIsAnimationPaused] = useState(false);
  
  // Enrichment toggles
  const [showEnrichmentBadges, setShowEnrichmentBadges] = useState(true);
  const [showTlsIndicators, setShowTlsIndicators] = useState(true);
  const [drawerTab, setDrawerTab] = useState<string>('overview');
  
  // Track layout changes
  const initialLayoutApplied = useRef(false);
  const previousNodeIds = useRef<Set<string>>(new Set());
  const prevNodesRef = useRef<Node[]>([]); // Track previous nodes for state sync
  
  // Deep search helper - searches all node fields including labels, IP, metadata
  /**
   * Smart matching for node identifiers (names, IPs, namespaces).
   * Matches if string starts with search term or term appears after delimiter.
   */
  const smartMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    const valueLower = value.toLowerCase();
    const searchLower = search.toLowerCase();
    
    if (valueLower === searchLower || valueLower.startsWith(searchLower)) return true;
    
    const delimiters = ['.', '-', ':', '/', '_'];
    for (const d of delimiters) {
      if (valueLower.includes(d + searchLower)) return true;
    }
    return false;
  }, []);

  /**
   * Simple contains for short keywords (status, kind, etc.)
   */
  const simpleMatch = useCallback((value: string | undefined | null, search: string): boolean => {
    if (!value || !search) return false;
    return value.toLowerCase().includes(search.toLowerCase());
  }, []);

  // Node search with smart matching for Map visualization
  const nodeMatchesSearch = useCallback((node: DependencyNode, searchTerm: string): boolean => {
    if (!searchTerm) return true;
    
    // Smart match for identifiers (name, namespace, IPs, node name)
    if (smartMatch(node.name, searchTerm)) return true;
    if (smartMatch(node.namespace, searchTerm)) return true;
    if (smartMatch(node.id, searchTerm)) return true;
    if (smartMatch(node.ip, searchTerm)) return true;
    if (smartMatch(node.host_ip, searchTerm)) return true;
    if (smartMatch(node.node, searchTerm)) return true;
    
    // Smart match for owner info
    if (smartMatch(node.owner_name, searchTerm)) return true;
    
    // Smart match for container/image info
    if (smartMatch(node.container, searchTerm)) return true;
    if (smartMatch(node.image, searchTerm)) return true;
    if (smartMatch(node.service_account, searchTerm)) return true;
    
    // Simple match for short keywords (kind, status, phase, owner_kind)
    if (simpleMatch(node.kind, searchTerm)) return true;
    if (simpleMatch(node.status, searchTerm)) return true;
    if (simpleMatch(node.phase, searchTerm)) return true;
    if (simpleMatch(node.owner_kind, searchTerm)) return true;
    
    // Labels: smart match for keys, simple for values
    if (node.labels) {
      for (const [key, value] of Object.entries(node.labels)) {
        if (smartMatch(key, searchTerm)) return true;
        if (simpleMatch(String(value), searchTerm)) return true;
        // Allow "key=value" format search
        if (`${key}=${value}`.toLowerCase().includes(searchTerm.toLowerCase())) return true;
      }
    }
    
    return false;
  }, [smartMatch, simpleMatch]);
  
  // React Flow states
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  // API Queries
  const { data: clustersResponse, isLoading: isClustersLoading } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  // Fetch ALL analyses (no cluster filter) - user selects analysis first, cluster is derived from it
  const { data: analyses = [], isLoading: isAnalysesLoading } = useGetAnalysesQuery({});
  
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  // Get selected analysis details
  const selectedAnalysis = useMemo(() => {
    if (!selectedAnalysisId || !analyses.length) return null;
    return (Array.isArray(analyses) ? analyses : []).find(
      (a: Analysis) => a.id === selectedAnalysisId
    ) || null;
  }, [selectedAnalysisId, analyses]);
  
  // Check if this is a multi-cluster analysis
  const isMultiClusterAnalysis = useMemo(() => {
    return selectedAnalysis?.is_multi_cluster || false;
  }, [selectedAnalysis]);
  
  // Check if analysis is currently running (for LIVE indicator and polling)
  const isAnalysisRunning = useMemo(() => {
    return selectedAnalysis?.status === 'running';
  }, [selectedAnalysis]);
  
  // Polling interval - only poll when analysis is running
  const pollingInterval = isAnalysisRunning ? 10000 : 0;
  
  // Get status badge info based on analysis status
  const statusBadgeInfo = useMemo(() => {
    if (!selectedAnalysis) return null;
    
    const status = selectedAnalysis.status;
    
    switch (status) {
      case 'running':
        return {
          badgeStatus: 'processing' as const,
          text: 'LIVE',
          tooltip: 'Analysis is running - auto-refreshes every 10 seconds'
        };
      case 'stopped':
        return {
          badgeStatus: 'default' as const,
          text: 'STOPPED',
          tooltip: 'Analysis was stopped - showing collected data'
        };
      case 'completed':
        return {
          badgeStatus: 'success' as const,
          text: 'COMPLETED',
          tooltip: 'Analysis completed successfully - showing final data'
        };
      case 'failed':
        return {
          badgeStatus: 'error' as const,
          text: 'FAILED',
          tooltip: 'Analysis failed - showing partial data'
        };
      case 'draft':
        return {
          badgeStatus: 'warning' as const,
          text: 'DRAFT',
          tooltip: 'Analysis not started yet - no data available'
        };
      default:
        // Exhaustive check - this should never happen with current type definitions
        // But provides fallback for future status values
        const unknownStatus: string = status;
        return {
          badgeStatus: 'default' as const,
          text: unknownStatus.toUpperCase(),
          tooltip: `Analysis status: ${unknownStatus}`
        };
    }
  }, [selectedAnalysis]);
  
  // Effective cluster ID for API calls:
  // - Multi-cluster: undefined (backend queries all clusters via analysis_id)
  // - Single-cluster: selectedClusterId (backend queries specific cluster)
  // This ensures multi-cluster analyses fetch data from ALL clusters, not just the primary one
  const effectiveClusterId = useMemo(() => {
    if (isMultiClusterAnalysis) {
      return undefined; // Backend will use analysis_id to resolve all cluster IDs
    }
    return selectedClusterId;
  }, [isMultiClusterAnalysis, selectedClusterId]);
  
  // Get all cluster IDs for multi-cluster analysis
  const analysisClusterIds = useMemo(() => {
    if (!selectedAnalysis) return [];
    if (selectedAnalysis.cluster_ids && selectedAnalysis.cluster_ids.length > 0) {
      return selectedAnalysis.cluster_ids;
    }
    return [selectedAnalysis.cluster_id];
  }, [selectedAnalysis]);
  
  // Get cluster info map for quick lookup
  const clusterInfoMap = useMemo(() => {
    const clusterMap: Record<number, any> = {};
    clusters.forEach((c: any) => { clusterMap[c.id] = c; });
    return {
      get: (id: number) => clusterMap[id],
      has: (id: number) => id in clusterMap
    };
  }, [clusters]);
  
  // Auto-set cluster when analysis changes (separate effect to avoid stale closure in onChange)
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        setSelectedClusterId(analysis.cluster_id);
        // Reset cluster filter for multi-cluster analysis
        if (analysis.is_multi_cluster && analysis.cluster_ids?.length) {
          setSelectedClusterFilter([]); // Show all clusters by default
        }
      }
    }
  }, [selectedAnalysisId, analyses]);
  
  // Reset namespace and pod selection when cluster filter changes
  // This prevents invalid state where selected namespace doesn't exist in filtered clusters
  useEffect(() => {
    // Only reset if cluster filter is actively being used (not empty = all clusters)
    if (selectedClusterFilter.length > 0) {
      // Check if current namespace(s) are still valid
      if (selectedNamespaces.length > 0) {
        // Will be validated when namespacesWithCluster updates
        // For now, reset to avoid stale selection
        setSelectedNamespaces([]);
        setSelectedPod(undefined);
      }
      // Also reset highlighted namespace for consistency
      if (highlightedNamespace) {
        setHighlightedNamespace(null);
      }
    }
  }, [selectedClusterFilter]); // Only trigger on cluster filter change
  
  // Fetch graph data only when analysis is selected - cluster_id comes from selected analysis
  // IMPORTANT: Multi-namespace strategy:
  // - 0 namespaces: No filter (all data)
  // - 1 namespace: Backend filters (efficient)
  // - 2+ namespaces: No backend filter, frontend filters (get all data)
  // highlightedNamespace (from right panel buttons) is ONLY for visual highlighting, NOT API filtering
  // This prevents floating edges when highlighting namespace from the right panel
  const effectiveNamespace = selectedNamespaces.length === 1 ? selectedNamespaces[0] : undefined;
  
  // DEBUG: Log API call parameters
  debugLog('[API_DEBUG] Graph query params:', {
    selectedNamespaces,
    selectedNamespacesCount: selectedNamespaces.length,
    effectiveNamespace,  // Only first namespace or undefined for multi-select
    highlightedNamespace,
    selectedClusterId,
    effectiveClusterId,
    isMultiClusterAnalysis,
    selectedAnalysisId
  });
  
  // Use currentData instead of data to prevent floating edges:
  // - data: Returns cached data even when args change (causes stale render)
  // - currentData: Returns undefined when args change, data only for current args
  // This ensures ReactFlow never renders with stale nodes from different namespace
  const { 
    currentData: graphData,  // Auto-undefined on args change, preserved on polling
    isLoading: isGraphLoading, 
    isFetching: isGraphFetching,
    refetch: refetchGraph,
    error: graphError
  } = useGetDependencyGraphQuery(
    { 
      // Multi-cluster: undefined (backend queries all clusters via analysis_id)
      // Single-cluster: cluster_id (backend queries specific cluster)
      cluster_id: effectiveClusterId, 
      analysis_id: selectedAnalysisId,
      namespace: effectiveNamespace,  // Backend will filter nodes AND edges properly
      // Server-side search: when 3+ chars, Neo4j filters nodes before returning
      // This solves the limit problem - low-traffic external connections are not cut off
      search: debouncedSearchTerm || undefined
    },
    // Skip only when no analysis selected - cluster_id is optional for multi-cluster
    // Only poll when analysis is running (LIVE mode)
    { skip: !selectedAnalysisId, pollingInterval }
  );
  
  // Use currentData instead of data to prevent stale cache:
  // When analysis changes, currentData becomes undefined until new stats load
  // This ensures smartEdgeLimit uses correct analysis size, not cached value
  // NOTE: Use selectedClusterId (not effectiveClusterId) for consistent error counts with Network Explorer
  const { currentData: stats, error: statsError } = useGetCommunicationStatsQuery(
    { cluster_id: selectedClusterId, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId, pollingInterval }
  );
  
  // Categorized error statistics (NO LIMIT - accurate counts)
  // Separates critical errors (connection failures) from warnings (retransmissions)
  const { data: errorStats } = useGetErrorStatsQuery(
    { cluster_id: selectedClusterId, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId, pollingInterval }
  );
  
  // Error anomaly summary from change detection
  const { data: errorAnomalySummary } = useGetErrorAnomalySummaryQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId || !selectedClusterId }
  );
  
  // ============================================
  // ERROR STATS: Dedicated query for Error card only
  // ISOLATED from other queries - does not affect animations, graph, or effects
  // Uses same approach as Network Explorer for consistency
  // This query uses limit: 1000 (backend max) to avoid 422 validation errors
  // FILTER-AWARE: Updates based on namespace and search filters
  // ============================================
  const { data: errorFlowsData } = useGetNetworkFlowsQuery(
    { 
      cluster_id: selectedClusterId, 
      analysis_id: selectedAnalysisId,
      namespace: effectiveNamespace,  // Respects namespace filter (single selection)
      search: debouncedSearchTerm || undefined,  // Respects search filter
      limit: 1000  // Backend max limit (le=1000 in events.py)
    },
    { 
      skip: !selectedAnalysisId || !selectedClusterId
      // No polling - error stats don't need frequent updates
    }
  );
  
  // Reset user limit selection when analysis changes (return to smart limit)
  // User's selection persists within same analysis (filters/search don't reset it)
  useEffect(() => {
    setUserSelectedLimit(null); // Return to smart limit for new analysis
    setFilterErrorsOnly(false); // Reset error filter for new analysis
  }, [selectedAnalysisId]);
  
  // =====================================================
  // SMART CONNECTION LIMIT: Computed value based on analysis size
  // Priority: User selection (within same analysis) > Smart calculation
  // Resets to smart limit when analysis changes
  // =====================================================
  const smartEdgeLimit = useMemo(() => {
    // Priority 1: If user explicitly selected a limit, use it (persists until page refresh)
    if (userSelectedLimit !== null) {
      return userSelectedLimit === 'all' ? Infinity : userSelectedLimit;
    }
    
    // Priority 2: Smart calculation based on analysis size
    const totalEdges = stats?.total_communications || 0;
    
    // If stats not loaded yet, use default
    if (totalEdges === 0) {
      return 300; // Default until stats load
    }
    
    // Auto-adjust based on analysis size
    if (totalEdges < 3000) {
      return 200; // Small analysis: fast loading
    } else if (totalEdges < 15000) {
      return 300; // Medium analysis: balanced
    } else {
      return 500; // Large analysis: more context
    }
  }, [stats?.total_communications, userSelectedLimit]);
  
  // Display value for dropdown (shows 'all' or number)
  const displayLimitValue = useMemo(() => {
    if (userSelectedLimit === 'all') return 'all';
    if (userSelectedLimit !== null) return userSelectedLimit;
    // Smart limit (not 'all', so return the number)
    const totalEdges = stats?.total_communications || 0;
    if (totalEdges === 0) return 300;
    if (totalEdges < 3000) return 200;
    if (totalEdges < 15000) return 300;
    return 500;
  }, [stats?.total_communications, userSelectedLimit]);
  
  // ============================================
  // CSV EXPORT FUNCTIONS
  // ============================================
  
  // Build filename with analysis info and timestamp
  const buildFilename = useCallback((ext: 'zip' | 'csv'): string => {
    const parts = ['flowfish'];
    
    if (selectedAnalysis?.name) {
      // Sanitize: replace non-alphanumeric with underscore, max 30 chars
      const safe = selectedAnalysis.name.replace(/[^a-zA-Z0-9-]/g, '_').slice(0, 30);
      parts.push(safe);
    }
    
    // View mode indicator
    parts.push(aggregatedView ? 'wl' : 'pod');
    
    // Timestamp: YYYYMMDD-HHmm
    const now = new Date();
    const ts = now.toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1-$2');
    parts.push(ts);
    
    return `${parts.join('-')}.${ext}`;
  }, [selectedAnalysis?.name, aggregatedView]);
  
  // Build metadata text for ZIP export
  const buildMetadata = useCallback((): string => {
    const lines = [
      '═'.repeat(65),
      'FLOWFISH MAP EXPORT',
      '═'.repeat(65),
      '',
      'ANALYSIS INFORMATION',
      '-'.repeat(20),
      `Name: ${selectedAnalysis?.name || 'N/A'}`,
      `ID: ${selectedAnalysisId || 'N/A'}`,
      `Type: ${isMultiClusterAnalysis ? 'Multi-cluster' : 'Single-cluster'}`,
      `Scope: ${selectedAnalysis?.scope_type || 'cluster'}`,
    ];
    
    // Cluster info
    if (isMultiClusterAnalysis && analysisClusterIds.length > 0) {
      const clusterNames = analysisClusterIds.map((id: number) => {
        const info = clusterInfoMap.get(id);
        return `${info?.name || 'Unknown'} (ID:${id})`;
      });
      lines.push(`Clusters: ${clusterNames.join(', ')}`);
    } else if (selectedClusterId) {
      const info = clusterInfoMap.get(selectedClusterId);
      lines.push(`Cluster: ${info?.name || 'Unknown'} (ID:${selectedClusterId})`);
    }
    
    lines.push('', 'EXPORT CONTEXT', '-'.repeat(20));
    lines.push(`Date: ${new Date().toLocaleString()}`);
    lines.push(`View Mode: ${aggregatedView ? 'Workload (Aggregated)' : 'Pod'}`);
    lines.push(`Connection Limit: ${smartEdgeLimit === Infinity ? 'Unlimited' : smartEdgeLimit}`);
    
    lines.push('', 'ACTIVE FILTERS', '-'.repeat(20));
    if (hideSystemNamespaces) lines.push('- Hide System Namespaces: ON');
    if (focusPublicOnly) lines.push('- Public Filter: ON');
    if (focusDataCenterOnly) lines.push('- DataCenter Filter: ON');
    if (focusIPOnly) lines.push('- Unresolved IP Filter: ON');
    if (debouncedSearchTerm) lines.push(`- Search Term: "${debouncedSearchTerm}"`);
    if (selectedNamespaces.length > 0) {
      lines.push(`- Selected Namespaces: ${selectedNamespaces.join(', ')}`);
    }
    if (selectedClusterFilter.length > 0) {
      const clusterNames = selectedClusterFilter.map((id: number) => {
        const info = clusterInfoMap.get(id);
        return info?.name || `Cluster ${id}`;
      });
      lines.push(`- Selected Clusters: ${clusterNames.join(', ')}`);
    }
    
    lines.push('', 'STATISTICS', '-'.repeat(20));
    lines.push(`Total Nodes: ${nodes.length}`);
    lines.push(`Total Connections: ${edges.length}`);
    
    // Count isolated nodes
    const connectedIds = new Set<string>();
    edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target); });
    const isolatedCount = nodes.filter(n => !connectedIds.has(n.id)).length;
    lines.push(`Isolated Nodes: ${isolatedCount}`);
    
    lines.push('', '═'.repeat(65));
    
    return lines.join('\n');
  }, [selectedAnalysis, selectedAnalysisId, isMultiClusterAnalysis, analysisClusterIds, 
      clusterInfoMap, selectedClusterId, aggregatedView, smartEdgeLimit, hideSystemNamespaces,
      focusPublicOnly, focusDataCenterOnly, focusIPOnly, debouncedSearchTerm, selectedNamespaces,
      selectedClusterFilter, nodes, edges]);
  
  const { data: eventStats, isLoading: isEventStatsLoading, error: eventStatsError } = useGetEventStatsQuery(
    { cluster_id: effectiveClusterId, analysis_id: selectedAnalysisId },
    { skip: !selectedAnalysisId, pollingInterval }
  );
  
  // Node enrichment - aggregates DNS, TLS, security, process, file, bind, mount, OOM events
  const { 
    enrichmentMap, 
    getNodeEnrichment,
    enrichedPods,
    summary: enrichmentSummary,
    isLoading: isEnrichmentLoading 
  } = useNodeEnrichment({
    // Multi-cluster: undefined (hook will use analysis_id to resolve clusters)
    // Single-cluster: cluster_id (hook will query specific cluster)
    clusterId: effectiveClusterId,
    analysisId: selectedAnalysisId,
    // Enable when analysis is selected - needed for drawer details even if badges are hidden
    // For multi-cluster, clusterId may be undefined but analysisId is sufficient
    enabled: !!selectedAnalysisId
  });
  
  // SNI events for TLS edge decoration
  const { data: sniData } = useGetSniEventsQuery(
    { cluster_id: effectiveClusterId, analysis_id: selectedAnalysisId, limit: 500 },
    // Skip only if no analysis or TLS indicators disabled - cluster_id is optional
    // Only poll when analysis is running (LIVE mode)
    { skip: !selectedAnalysisId || !showTlsIndicators, pollingInterval: isAnalysisRunning ? 30000 : 0 }
  );
  
  // Build TLS connection map (namespace -> pod prefix -> destination IPs) for edge decoration
  // Uses pod prefix matching to handle deployment name vs full pod name mismatch
  const tlsConnectionMap = useMemo(() => {
    const map: Record<string, { pods: string[]; destIps: string[] }> = {};
    if (sniData?.events) {
      for (const event of sniData.events) {
        const ns = event.namespace || '';
        if (!map[ns]) {
          map[ns] = { pods: [], destIps: [] };
        }
        // Store pod name
        if (event.pod && !map[ns].pods.includes(event.pod)) {
          map[ns].pods.push(event.pod);
        }
        // Store destination IP
        const destIp = event.dest_ip || event.dst_ip || '';
        if (destIp && !map[ns].destIps.includes(destIp)) {
          map[ns].destIps.push(destIp);
        }
      }
    }
    return map;
  }, [sniData]);
  
  // Helper function to check if a node has TLS connections
  const hasTlsConnection = useCallback((nodeName: string, namespace: string, targetIp?: string): boolean => {
    if (!showTlsIndicators) return false;
    
    const nsData = tlsConnectionMap[namespace];
    if (!nsData) return false;
    
    // Check if any pod in this namespace matches the node name (partial match)
    const hasMatchingPod = nsData.pods.some(pod => 
      pod.startsWith(nodeName) || nodeName.startsWith(pod) || pod === nodeName
    );
    
    if (!hasMatchingPod) return false;
    
    // If target IP provided, check if it's in destination list
    if (targetIp && nsData.destIps.length > 0) {
      return nsData.destIps.includes(targetIp);
    }
    
    // If no target IP, just return that source has TLS connections
    return true;
  }, [showTlsIndicators, tlsConnectionMap]);

  // =====================================================
  // NAMESPACE CACHE FOR DROPDOWN
  // Update cache when we have full data (no namespace filter active)
  // This ensures dropdown always shows ALL namespaces, not just filtered ones
  // =====================================================
  useEffect(() => {
    // Only update cache when:
    // 1. We have an analysis selected
    // 2. No namespace filter is active (API returns ALL data)
    // 3. We have graph data with nodes
    if (!selectedAnalysisId || !graphData?.nodes || graphData.nodes.length === 0) {
      return;
    }
    
    // Skip if namespace filter is active - API returns filtered data, not suitable for cache
    if (selectedNamespaces.length > 0) {
      return;
    }
    
    // Build namespace list from full graph data
    const nsClusterMap: Record<string, { namespace: string; clusterId: number; clusterName: string }> = {};
    
    graphData.nodes.forEach((node: DependencyNode) => {
      if (!node.namespace || node.namespace === 'external') return;
      
      const clusterId = safeParseClusterId(node.cluster_id);
      const key = `${clusterId}:${node.namespace}`;
      
      if (!nsClusterMap[key]) {
        const clusterInfo = clusterInfoMap.get(clusterId);
        nsClusterMap[key] = {
          namespace: node.namespace,
          clusterId: clusterId,
          clusterName: clusterInfo?.name || `Cluster ${clusterId}`
        };
      }
    });
    
    const extractedNamespaces = Object.values(nsClusterMap).sort((a, b) => {
      const nsCompare = a.namespace.localeCompare(b.namespace);
      if (nsCompare !== 0) return nsCompare;
      return a.clusterName.localeCompare(b.clusterName);
    });
    
    // Only update if we have namespaces and analysis matches
    if (extractedNamespaces.length > 0) {
      setNamespaceCache({
        analysisId: selectedAnalysisId,
        namespaces: extractedNamespaces
      });
      debugLog('[NAMESPACE_CACHE] Updated cache:', {
        analysisId: selectedAnalysisId,
        namespaceCount: extractedNamespaces.length,
        sample: extractedNamespaces.slice(0, 3).map(n => `${n.namespace}@${n.clusterName}`)
      });
    }
  }, [graphData, selectedAnalysisId, selectedNamespaces.length, clusterInfoMap]);

  // =====================================================
  // MULTI-CLUSTER FILTERING
  // Filter graph data by selected clusters when user filters
  // =====================================================
  const filteredGraphData = useMemo(() => {
    if (!graphData?.nodes || !graphData?.edges) return graphData;
    
    // If no cluster filter selected, show all (default behavior)
    if (!selectedClusterFilter || selectedClusterFilter.length === 0) {
      return graphData;
    }
    
    // Convert filter to string set for comparison (cluster_id is string in node)
    const filterSet = new Set(selectedClusterFilter.map(id => String(id)));
    
    // Filter nodes by selected clusters
    const filteredNodes = graphData.nodes.filter((node: DependencyNode) => {
      // External endpoints may not have cluster_id - always include them
      // Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly
      if (node.cluster_id === undefined || node.cluster_id === null || node.namespace === 'external') return true;
      return filterSet.has(String(node.cluster_id));
    });
    
    // Create set of filtered node IDs for edge filtering
    const filteredNodeIds = new Set(filteredNodes.map((n: DependencyNode) => n.id));
    
    // Filter edges - keep only edges where BOTH endpoints are in filtered nodes
    // Using AND (&&) prevents orphan edges when cluster filter is applied
    const filteredEdges = graphData.edges.filter((edge: DependencyEdge) => {
      return filteredNodeIds.has(edge.source_id) && filteredNodeIds.has(edge.target_id);
    });
    
    return {
      nodes: filteredNodes,
      edges: filteredEdges
    };
  }, [graphData, selectedClusterFilter]);

  // =====================================================
  // ANALYSIS SCOPE FILTERING
  // Filter by analysis scope configuration (per_cluster_scope support)
  // This ensures only nodes within the analysis scope are shown
  // =====================================================
  
  // Helper: Build allowed (cluster_id:namespace) pairs from scope_config
  // Returns empty Set if no scope restrictions (allow all)
  const buildAllowedScopePairs = useCallback((analysis: Analysis | null): Set<string> => {
    const pairs = new Set<string>();
    
    // No analysis or scope_type = 'cluster' means no namespace restrictions
    if (!analysis) return pairs;
    if (analysis.scope_type === 'cluster') return pairs;
    
    const scopeConfig = analysis.scope_config as any;
    if (!scopeConfig) return pairs;
    
    const perClusterScope = scopeConfig.per_cluster_scope;
    
    if (perClusterScope && Object.keys(perClusterScope).length > 0) {
      // Per-cluster scope: each cluster has specific namespaces
      Object.entries(perClusterScope).forEach(([clusterId, scope]: [string, any]) => {
        const namespaces = scope?.namespaces || [];
        namespaces.forEach((ns: string) => {
          pairs.add(`${clusterId}:${ns}`);
        });
      });
    } else {
      // Unified scope: all namespaces apply to all clusters
      const globalNamespaces = scopeConfig.namespaces || [];
      if (globalNamespaces.length === 0) return pairs; // No restrictions
      
      const clusterIds = analysis.cluster_ids || [analysis.cluster_id];
      clusterIds.forEach((clusterId: number) => {
        globalNamespaces.forEach((ns: string) => {
          pairs.add(`${String(clusterId)}:${ns}`);
        });
      });
    }
    
    return pairs;
  }, []);

  // Filter by analysis scope (per-cluster namespace restrictions)
  // ============================================================
  // INCLUSIVE SCOPE FILTERING:
  // For namespace-scoped analyses (e.g., prod-auth-service), we need to show:
  // 1. Nodes IN the target namespace (primary nodes)
  // 2. Nodes that CONNECT TO/FROM the target namespace (related nodes)
  //    - This includes incoming traffic sources like prod-api-gateway
  //    - This includes external endpoints
  // 
  // Strategy: Edge-based inclusion
  // - Find primary nodes (in scope)
  // - Find edges with at least one endpoint in scope
  // - Include ALL nodes from those edges (both endpoints)
  // ============================================================
  const scopeFilteredGraphData = useMemo(() => {
    if (!filteredGraphData?.nodes || !filteredGraphData?.edges) {
      return filteredGraphData;
    }
    
    // Build allowed pairs for O(1) lookup
    const allowedPairs = buildAllowedScopePairs(selectedAnalysis);
    
    // If no scope restriction (empty set), return as-is
    if (allowedPairs.size === 0) {
      return filteredGraphData;
    }
    
    // Step 1: Find primary nodes (nodes IN the target namespace scope)
    const primaryNodeIds = new Set<string>();
    filteredGraphData.nodes.forEach((node: DependencyNode) => {
      // External nodes will be included via edge connections
      if (node.namespace === 'external') return;
      
      const nodeClusterId = String(node.cluster_id);
      if (allowedPairs.has(`${nodeClusterId}:${node.namespace}`)) {
        primaryNodeIds.add(node.id);
      }
    });
    
    // Step 2: Find edges connected to primary nodes (at least one endpoint in scope)
    const connectedEdges = filteredGraphData.edges.filter((edge: DependencyEdge) => 
      primaryNodeIds.has(edge.source_id) || primaryNodeIds.has(edge.target_id)
    );
    
    // Step 3: Collect ALL node IDs from connected edges
    // This includes: primary nodes + incoming traffic sources + external endpoints
    const connectedNodeIds = new Set<string>();
    connectedEdges.forEach((edge: DependencyEdge) => {
      connectedNodeIds.add(edge.source_id);
      connectedNodeIds.add(edge.target_id);
    });
    
    // Step 4: Filter nodes - include all nodes that have edges to/from scope
    const scopedNodes = filteredGraphData.nodes.filter((node: DependencyNode) => {
      return connectedNodeIds.has(node.id);
    });
    
    debugLog('[SCOPE_FILTER_DEBUG]', {
      analysisId: selectedAnalysis?.id,
      scopeType: selectedAnalysis?.scope_type,
      allowedPairsCount: allowedPairs.size,
      allowedPairsSample: Array.from(allowedPairs).slice(0, 5),
      primaryNodesCount: primaryNodeIds.size,
      originalNodes: filteredGraphData.nodes.length,
      scopedNodes: scopedNodes.length,
      originalEdges: filteredGraphData.edges.length,
      connectedEdges: connectedEdges.length
    });
    
    return { nodes: scopedNodes, edges: connectedEdges };
  }, [filteredGraphData, selectedAnalysis, buildAllowedScopePairs]);

  // =====================================================
  // AGGREGATED VIEW: Group pods by workload name
  // This creates a simplified view where same-named workloads
  // across clusters or replica pods are shown as single nodes
  // =====================================================
  const aggregatedGraphData = useMemo(() => {
    // Toggle kapalıysa null döndür - normal flow devam eder
    if (!aggregatedView) {
      return null;
    }
    
    // Use scopeFilteredGraphData (includes analysis scope filtering)
    if (!scopeFilteredGraphData?.nodes || !scopeFilteredGraphData?.edges) {
      return null;
    }

    // Helper: Pod adından workload adını çıkar
    const getWorkloadName = (node: DependencyNode): string => {
      const ownerName = node.owner_name || node.name || 'unknown';
      // Pod suffix'lerini temizle: -abc123, -7fb889c6d4-xyz
      return ownerName
        .replace(/-[a-z0-9]{5,10}$/, '')     // ReplicaSet suffix
        .replace(/-[a-f0-9]{8,}$/, '')        // Hash suffix
        .replace(/-[a-f0-9]{4,}-[a-z0-9]{4,}$/, ''); // Combined suffix
    };

    // === NODE AGGREGATION ===
    // Type for node group
    interface NodeGroup {
      aggregationKey: string;
      workloadName: string;
      namespace: string;
      ownerKind: string;
      originalNodes: DependencyNode[];
      podsByCluster: Record<number, DependencyNode[]>;
      clusterIds: number[];
    }
    
    const nodeGroups: Record<string, NodeGroup> = {};

    scopeFilteredGraphData.nodes.forEach((node: DependencyNode) => {
      const workloadName = getWorkloadName(node);
      const namespace = node.namespace || 'unknown';
      const aggregationKey = `${namespace}:${workloadName}`;
      const clusterId = safeParseClusterId(node.cluster_id);
      
      if (!nodeGroups[aggregationKey]) {
        nodeGroups[aggregationKey] = {
          aggregationKey,
          workloadName,
          namespace,
          ownerKind: node.owner_kind || 'Pod',
          originalNodes: [node],
          podsByCluster: { [clusterId]: [node] },
          clusterIds: [clusterId],
        };
      } else {
        const group = nodeGroups[aggregationKey];
        group.originalNodes.push(node);
        
        if (!group.clusterIds.includes(clusterId)) {
          group.clusterIds.push(clusterId);
        }
        
        if (!group.podsByCluster[clusterId]) {
          group.podsByCluster[clusterId] = [];
        }
        group.podsByCluster[clusterId].push(node);
        
        // Owner kind güncelle (daha spesifik olan kazanır)
        if (node.owner_kind && node.owner_kind !== 'Pod') {
          group.ownerKind = node.owner_kind;
        }
      }
    });

    // Aggregated nodes oluştur
    const aggregatedNodes: (DependencyNode & AggregatedNodeMetadata)[] = Object.values(nodeGroups).map((group: NodeGroup) => {
      const firstNode = group.originalNodes[0];
      
      return {
        // DependencyNode uyumlu alanlar - mevcut kod çalışır
        id: group.aggregationKey,
        name: group.workloadName,
        namespace: group.namespace,
        kind: group.ownerKind,
        cluster_id: String(group.clusterIds[0]),
        cluster_name: firstNode.cluster_name || '',
        status: 'active',
        labels: firstNode.labels || {},
        annotations: firstNode.annotations || {},
        owner_kind: group.ownerKind,
        owner_name: group.workloadName,
        ip: firstNode.ip,
        host_ip: firstNode.host_ip,
        node: firstNode.node,
        network_type: firstNode.network_type || '',
        resolution_source: firstNode.resolution_source || '',
        is_external: firstNode.is_external || false,
        
        // Aggregation metadata
        _isAggregated: true as const,
        _originalNodes: group.originalNodes,
        _podCount: group.originalNodes.length,
        _podsByCluster: group.podsByCluster,
        _clusterIds: group.clusterIds,
        _clusterCount: group.clusterIds.length,
      };
    });

    // === EDGE AGGREGATION ===
    const nodeToAggKey: Record<string, string> = {};
    scopeFilteredGraphData.nodes.forEach((node: DependencyNode) => {
      const workloadName = getWorkloadName(node);
      nodeToAggKey[node.id] = `${node.namespace || 'unknown'}:${workloadName}`;
    });

    // Type for edge group
    interface EdgeGroup {
      sourceAggKey: string;
      targetAggKey: string;
      originalEdges: DependencyEdge[];
      totalRequestCount: number;
      protocols: string[];
    }

    const edgeGroups: Record<string, EdgeGroup> = {};

    scopeFilteredGraphData.edges.forEach((edge: DependencyEdge) => {
      const srcAggKey = nodeToAggKey[edge.source_id];
      const dstAggKey = nodeToAggKey[edge.target_id];
      
      if (!srcAggKey || !dstAggKey) return;
      if (srcAggKey === dstAggKey) return; // Self-loop'ları atla
      
      const edgeKey = `${srcAggKey}→${dstAggKey}`;
      
      if (!edgeGroups[edgeKey]) {
        edgeGroups[edgeKey] = {
          sourceAggKey: srcAggKey,
          targetAggKey: dstAggKey,
          originalEdges: [edge],
          totalRequestCount: edge.request_count || 0,
          protocols: [edge.protocol || 'TCP'],
        };
      } else {
        const group = edgeGroups[edgeKey];
        group.originalEdges.push(edge);
        group.totalRequestCount += edge.request_count || 0;
        if (edge.protocol && !group.protocols.includes(edge.protocol)) {
          group.protocols.push(edge.protocol);
        }
      }
    });

    const aggregatedEdges: (DependencyEdge & AggregatedEdgeMetadata)[] = Object.values(edgeGroups).map((group: EdgeGroup) => {
      // Aggregate error and retransmit counts from all original edges
      const totalErrorCount = group.originalEdges.reduce((sum, e) => sum + (e.error_count || 0), 0);
      const totalRetransmitCount = group.originalEdges.reduce((sum, e) => sum + (e.retransmit_count || 0), 0);
      // Get unique app protocols and last error types
      const appProtocols = Array.from(new Set(group.originalEdges.map(e => e.app_protocol).filter(Boolean)));
      const lastErrorTypes = Array.from(new Set(group.originalEdges.map(e => e.last_error_type).filter(Boolean)));
      
      return {
        source_id: group.sourceAggKey,
        target_id: group.targetAggKey,
        edge_type: 'COMMUNICATES_WITH',
        protocol: group.protocols.join('/'),
        app_protocol: appProtocols.join('/') || '',
        port: group.originalEdges[0].port,
        request_count: group.totalRequestCount,
        error_count: totalErrorCount,
        retransmit_count: totalRetransmitCount,
        last_error_type: lastErrorTypes.join('/') || '',
        _isAggregated: true as const,
        _originalEdges: group.originalEdges,
        _edgeCount: group.originalEdges.length,
      };
    });

    return {
      nodes: aggregatedNodes as DependencyNode[],
      edges: aggregatedEdges as DependencyEdge[],
    };
  }, [aggregatedView, scopeFilteredGraphData]);

  // Effective data: Use aggregated if toggle is on, otherwise use filtered
  const effectiveGraphData = useMemo(() => {
    if (aggregatedView && aggregatedGraphData) {
      return aggregatedGraphData;
    }
    // Use scopeFilteredGraphData which includes analysis scope filtering
    return scopeFilteredGraphData;
  }, [aggregatedView, aggregatedGraphData, scopeFilteredGraphData]);

  // Type for namespace with cluster info
  interface NamespaceClusterInfo {
    namespace: string;
    clusterId: number;
    clusterName: string;
  }
  
  // Extract namespaces with cluster info for dropdown
  // IMPORTANT: Uses cached namespaces when available to prevent losing namespaces
  // when API returns filtered data (single namespace selected)
  // Returns array of { namespace, clusterId, clusterName } for multi-cluster support
  const namespacesWithCluster: NamespaceClusterInfo[] = useMemo(() => {
    // Build cluster filter set for O(1) lookup
    const filterSet = selectedClusterFilter.length > 0 
      ? new Set(selectedClusterFilter.map(id => String(id)))
      : null;
    
    // Helper function to apply cluster filter
    const applyClusterFilter = (namespaces: NamespaceClusterInfo[]): NamespaceClusterInfo[] => {
      if (!filterSet) return namespaces;
      return namespaces.filter(ns => filterSet.has(String(ns.clusterId)));
    };
    
    // STRATEGY: Use cache if available and valid for current analysis
    // This prevents dropdown from losing namespaces when API returns filtered data
    if (namespaceCache.analysisId === selectedAnalysisId && 
        namespaceCache.namespaces.length > 0) {
      debugLog('[NAMESPACE_DROPDOWN] Using cached namespaces:', {
        analysisId: selectedAnalysisId,
        cacheSize: namespaceCache.namespaces.length,
        clusterFilterActive: !!filterSet
      });
      return applyClusterFilter(namespaceCache.namespaces);
    }
    
    // FALLBACK: Extract from effectiveGraphData (initial load or cache not ready)
    if (!effectiveGraphData?.nodes) return [];
    
    debugLog('[NAMESPACE_DROPDOWN] Extracting from effectiveGraphData (cache not ready)');
    
    // Use Map to track unique namespace:cluster pairs
    const nsClusterMap: Record<string, NamespaceClusterInfo> = {};
    
    effectiveGraphData.nodes.forEach((node: DependencyNode) => {
      if (!node.namespace || node.namespace === 'external') return;
      
      // Skip if cluster filter is active and this node is from a different cluster
      // Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly
      if (filterSet && node.cluster_id !== undefined && node.cluster_id !== null && !filterSet.has(String(node.cluster_id))) {
        return;
      }
      
      const clusterId = safeParseClusterId(node.cluster_id);
      const key = `${clusterId}:${node.namespace}`;
      
      if (!nsClusterMap[key]) {
        const clusterInfo = clusterInfoMap.get(clusterId);
        nsClusterMap[key] = {
          namespace: node.namespace,
          clusterId: clusterId,
          clusterName: clusterInfo?.name || `Cluster ${clusterId}`
        };
      }
    });
    
    return Object.values(nsClusterMap).sort((a, b) => {
      // Sort by namespace name, then by cluster
      const nsCompare = a.namespace.localeCompare(b.namespace);
      if (nsCompare !== 0) return nsCompare;
      return a.clusterName.localeCompare(b.clusterName);
    });
  }, [namespaceCache, selectedAnalysisId, effectiveGraphData, selectedClusterFilter, clusterInfoMap]);
  
  // Simple namespace list for backward compatibility (unique namespace names only)
  const namespaces = useMemo(() => {
    const nsSet = new Set<string>();
    namespacesWithCluster.forEach(item => nsSet.add(item.namespace));
    return Array.from(nsSet).sort();
  }, [namespacesWithCluster]);

  // Calculate total requests and errors from ANALYSIS SCOPE edges
  // Uses effectiveGraphData.edges (not ReactFlow edges) to prevent changes during focus mode
  // Stats should reflect the full analysis scope, not the currently focused/filtered view
  const { displayedRequests, displayedErrors } = useMemo(() => {
    const allEdges = effectiveGraphData?.edges || [];
    if (allEdges.length === 0) return { displayedRequests: 0, displayedErrors: 0 };
    let requests = 0;
    let errors = 0;
    allEdges.forEach((edge: DependencyEdge) => {
      // Access data directly from DependencyEdge (not ReactFlow Edge)
      requests += edge.request_count || 0;
      errors += edge.error_count || 0;
    });
    return { displayedRequests: requests, displayedErrors: errors };
  }, [effectiveGraphData?.edges]);

  // ============================================
  // ERROR CALCULATION for Stats Row (moved from render for animated counter)
  // FILTER-AWARE: Now respects all active filters (Public, DataCenter, Unresolved IP, etc.)
  // Uses new categorized error stats (critical vs warnings) for accurate counts
  // ============================================
  const { 
    totalErrors, 
    totalCritical, 
    totalWarnings, 
    criticalByType, 
    warningsByType, 
    errorHealthStatus, 
    errorHealthMessage, 
    hasErrors, 
    hasCriticalErrors 
  } = useMemo(() => {
    // Check if USER-ACTIVATED filters are active (Public, DataCenter, Unresolved IP)
    // NOTE: hideSystemNamespaces and showInternalTraffic are DEFAULT states, not user-activated filters
    // They should NOT affect error stats calculation - errorStats endpoint already returns accurate totals
    const hasUserActivatedFilters = focusPublicOnly || focusDataCenterOnly || focusIPOnly;
    
    // Helper to categorize error type
    const isCriticalError = (errorType: string): boolean => {
      const criticalPatterns = ['RESET', 'REFUSED', 'TIMEOUT', 'UNREACHABLE', 'ERROR', 'SOCKET'];
      return criticalPatterns.some(pattern => errorType.toUpperCase().includes(pattern));
    };
    
    // Known valid error type keywords (whitelist for safety)
    const VALID_ERROR_KEYWORDS = new Set([
      // TCP Retransmit types
      'LOSS', 'RETRANS', 'TIMEOUT', 'SPURIOUS', 'FAST', 'RTO', 'TLP',
      'SYNACK', 'SYN', 'FIN', 'PROBE', 'KEEPALIVE',
      // TCP states
      'ESTABLISHED', 'SYN_SENT', 'SYN_RECV', 'FIN_WAIT1', 'FIN_WAIT2',
      'TIME_WAIT', 'CLOSE', 'CLOSE_WAIT', 'LAST_ACK', 'LISTEN', 'CLOSING',
      // Critical error types
      'RESET', 'REFUSED', 'UNREACHABLE', 'ERROR', 'SOCKET', 'ABORT',
      'REJECTED', 'DROPPED', 'FAILED', 'DENIED',
    ]);
    
    // Helper to clean error type using whitelist approach
    const cleanErrorType = (errorType: string): string => {
      if (!errorType) return '';
      
      // Extract all words from the error type
      const words = errorType.toUpperCase().split(/[_/\s]+/);
      
      // Track base types and collect valid keywords
      let hasRetransmit = false;
      let hasConnection = false;
      const validWords: string[] = [];
      
      for (const word of words) {
        const trimmed = word.trim();
        if (!trimmed) continue;
        
        if (trimmed === 'RETRANSMIT') {
          hasRetransmit = true;
        } else if (trimmed === 'CONNECTION') {
          hasConnection = true;
        } else if (VALID_ERROR_KEYWORDS.has(trimmed)) {
          validWords.push(trimmed);
        }
      }
      
      // Build result
      if (validWords.length > 0) {
        const suffix = validWords.join(' ');
        if (hasConnection) return `CONNECTION ${suffix}`;
        if (hasRetransmit) return `RETRANSMIT ${suffix}`;
        return suffix;
      }
      
      // Default fallback
      if (hasConnection) return 'CONNECTION ERROR';
      return 'RETRANSMIT';
    };
    
    // When user-activated filters are active (Public, DataCenter, Unresolved IP),
    // calculate from DISPLAYED edges so Errors count matches what user sees
    // If no edges match the filter, return zeros (not fallback to errorStats)
    if (hasUserActivatedFilters) {
      // If filter is active but no edges match, return zeros
      if (edges.length === 0) {
        return {
          totalErrors: 0,
          totalCritical: 0,
          totalWarnings: 0,
          criticalByType: {},
          warningsByType: {},
          errorHealthStatus: 'healthy',
          errorHealthMessage: 'No matching connections for current filter',
          hasErrors: false,
          hasCriticalErrors: false
        };
      }
      
      // Calculate from displayed edges
      let total = 0;
      let critical = 0;
      let warnings = 0;
      const criticalTypes: Record<string, number> = {};
      const warningTypes: Record<string, number> = {};
      
      edges.forEach((edge: Edge) => {
        const errorCount = (edge.data as any)?.error_count || 0;
        const retransmitCount = (edge.data as any)?.retransmit_count || 0;
        const errorType = (edge.data as any)?.last_error_type || '';
        
        const combinedCount = errorCount + retransmitCount;
        total += combinedCount;
        
        if (combinedCount > 0 && errorType) {
          const cleanedType = cleanErrorType(errorType);
          if (isCriticalError(errorType)) {
            critical += combinedCount;
            criticalTypes[cleanedType] = (criticalTypes[cleanedType] || 0) + combinedCount;
          } else {
            warnings += combinedCount;
            warningTypes[cleanedType] = (warningTypes[cleanedType] || 0) + combinedCount;
          }
        } else if (combinedCount > 0) {
          // No type specified, count as warning (likely retransmit)
          warnings += combinedCount;
        }
      });
      
      return { 
        totalErrors: total, 
        totalCritical: critical,
        totalWarnings: warnings,
        criticalByType: criticalTypes,
        warningsByType: warningTypes,
        errorHealthStatus: critical === 0 ? 'healthy' : critical < 10 ? 'good' : 'warning',
        errorHealthMessage: '',
        hasErrors: total > 0,
        hasCriticalErrors: critical > 0
      };
    }
    
    // No visual filters active - use new errorStats endpoint (accurate counts, NO LIMIT)
    if (errorStats) {
      return {
        totalErrors: errorStats.total_errors,
        totalCritical: errorStats.total_critical,
        totalWarnings: errorStats.total_warnings,
        criticalByType: errorStats.critical_by_type || {},
        warningsByType: errorStats.warnings_by_type || {},
        errorHealthStatus: errorStats.health_status || 'healthy',
        errorHealthMessage: errorStats.health_message || '',
        hasErrors: errorStats.total_errors > 0,
        hasCriticalErrors: errorStats.total_critical > 0
      };
    }
    
    // Fallback to stats (limited sample) if errorStats not available
    if (stats) {
      return {
        totalErrors: stats.total_errors || 0,
        totalCritical: stats.total_critical || 0,
        totalWarnings: stats.total_warnings || 0,
        criticalByType: stats.critical_by_type || {},
        warningsByType: stats.warnings_by_type || {},
        errorHealthStatus: stats.error_health_status || 'healthy',
        errorHealthMessage: '',
        hasErrors: (stats.total_errors || 0) > 0,
        hasCriticalErrors: (stats.total_critical || 0) > 0
      };
    }
    
    // Final fallback to errorFlowsData (limited)
    const events = errorFlowsData?.events || [];
    let total = 0;
    let critical = 0;
    let warnings = 0;
    const criticalTypes: Record<string, number> = {};
    const warningTypes: Record<string, number> = {};
    
    events.forEach((flow: any) => {
      const errorCount = flow.error_count || 0;
      const retransmitCount = flow.retransmit_count || 0;
      const errorType = flow.error_type || '';
      
      const combinedCount = errorCount + retransmitCount;
      total += combinedCount;
      
      if (combinedCount > 0 && errorType) {
        const cleanedType = cleanErrorType(errorType);
        if (isCriticalError(errorType)) {
          critical += combinedCount;
          criticalTypes[cleanedType] = (criticalTypes[cleanedType] || 0) + combinedCount;
        } else {
          warnings += combinedCount;
          warningTypes[cleanedType] = (warningTypes[cleanedType] || 0) + combinedCount;
        }
      } else if (combinedCount > 0) {
        warnings += combinedCount;
      }
    });
    
    return { 
      totalErrors: total, 
      totalCritical: critical,
      totalWarnings: warnings,
      criticalByType: criticalTypes,
      warningsByType: warningTypes,
      errorHealthStatus: critical === 0 ? 'healthy' : critical < 10 ? 'good' : 'warning',
      errorHealthMessage: '',
      hasErrors: total > 0,
      hasCriticalErrors: critical > 0
    };
  }, [errorStats, stats, errorFlowsData?.events, edges, focusPublicOnly, focusDataCenterOnly, focusIPOnly, hideSystemNamespaces, showInternalTraffic]);
  
  // Animated counters for categorized errors
  const animatedCritical = useAnimatedCounter(totalCritical, 1200, !selectedAnalysisId);
  const animatedWarnings = useAnimatedCounter(totalWarnings, 1200, !selectedAnalysisId);

  // ============================================
  // ANIMATED COUNTERS for Stats Row
  // Provides smooth counting animation when values change
  // Skip animation when no analysis selected (show dash instead)
  // NOTE: Uses effectiveGraphData.edges.length (not ReactFlow edges.length) 
  // to prevent stats changes during focus mode
  // ============================================
  const animatedConnections = useAnimatedCounter(
    effectiveGraphData?.edges?.length || (stats?.total_communications ?? 0), 
    1200, 
    !selectedAnalysisId
  );
  const animatedWorkloads = useAnimatedCounter(nodes.length, 1200, !selectedAnalysisId);
  const animatedRequests = useAnimatedCounter(displayedRequests, 1200, !selectedAnalysisId);
  // Note: animatedCritical and animatedWarnings are defined above with the error calculation
  const animatedEvents = useAnimatedCounter(eventStats?.total_events ?? 0, 1200, !selectedAnalysisId);
  
  // Calculate unique namespaces for animated counter
  const uniqueNamespaceCount = useMemo(() => {
    const nodeNamespaces = new Set(nodes.map(n => (n.data as any)?.namespace).filter(Boolean));
    return nodeNamespaces.size || namespaces.length || 0;
  }, [nodes, namespaces.length]);
  const animatedNamespaces = useAnimatedCounter(uniqueNamespaceCount, 1200, !selectedAnalysisId);

  // Extract pods (from effective data, respects cluster filter)
  // In aggregated view, this returns workload names instead of pod names
  const pods = useMemo(() => {
    if (!effectiveGraphData?.nodes) return [];
    
    // Build cluster filter set for O(1) lookup
    const filterSet = selectedClusterFilter.length > 0 
      ? new Set(selectedClusterFilter.map(id => String(id)))
      : null;
    
    return effectiveGraphData.nodes
      .filter((node: DependencyNode) => {
        // Skip if cluster filter is active and this node is from a different cluster
        // Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly
        if (filterSet && node.cluster_id !== undefined && node.cluster_id !== null && !filterSet.has(String(node.cluster_id))) {
          return false;
        }
        // Apply namespace filter (multi-namespace support)
        const hasNsFilter = selectedNamespaces.length > 0;
        if (hasNsFilter) {
          const nsSet = new Set(selectedNamespaces);
          return nsSet.has(node.namespace || '');
        }
        return true;
      })
      .map((node: DependencyNode) => node.name)
      .filter((name): name is string => Boolean(name) && !isNoiseNode(name))
      .filter((name, idx, arr) => arr.indexOf(name) === idx)
      .sort();
  }, [effectiveGraphData, selectedNamespaces, selectedClusterFilter]);

  // Build IP -> Node lookup for resolving IP addresses to pod names (from filtered data)
  const ipToNodeLookup = useMemo(() => {
    const lookup: Record<string, DependencyNode> = {};
    if (!filteredGraphData?.nodes) return lookup;
    
    filteredGraphData.nodes.forEach((node: DependencyNode) => {
      // Map pod IP to node
      if (node.ip) {
        lookup[node.ip] = node;
      }
      // Also map host IP if different
      if (node.host_ip && node.host_ip !== node.ip) {
        lookup[node.host_ip] = node;
      }
      // If node name looks like an IP, also index it
      if (node.name?.match(/^\d+\.\d+\.\d+\.\d+$/)) {
        // This node IS an IP - don't overwrite if already mapped
        if (!lookup[node.name]) {
          lookup[node.name] = node;
        }
      }
    });
    
    return lookup;
  }, [filteredGraphData?.nodes]);

  // PERFORMANCE: O(1) node lookup by ID - replaces O(n) find() calls
  // Uses original graphData for raw lookups (IP resolution, enrichment)
  const nodeIdMap = useMemo((): Record<string, DependencyNode> => {
    const map: Record<string, DependencyNode> = {};
    if (!graphData?.nodes) return map;
    graphData.nodes.forEach((node: DependencyNode) => {
      map[node.id] = node;
    });
    return map;
  }, [graphData?.nodes]);

  // PERFORMANCE: O(1) node lookup for effective data (respects aggregatedView)
  // Used in drawer and connections tab for proper aggregated node lookups
  const effectiveNodeIdMap = useMemo((): Record<string, DependencyNode> => {
    const map: Record<string, DependencyNode> = {};
    if (!effectiveGraphData?.nodes) return map;
    effectiveGraphData.nodes.forEach((node: DependencyNode) => {
      map[node.id] = node;
    });
    return map;
  }, [effectiveGraphData?.nodes]);

  // ============================================
  // CSV EXPORT FUNCTIONS
  // Must be after effectiveNodeIdMap and effectiveGraphData
  // ============================================
  
  // Export as ZIP (nodes.csv + edges.csv + metadata.txt)
  const exportAsZip = useCallback(async () => {
    const zip = new JSZip();
    
    // Use effectiveNodeIdMap for reliable node data lookup
    // This contains original DependencyNode objects from effectiveGraphData
    // React Flow node.id -> effectiveNodeIdMap[id] -> DependencyNode
    
    // --- nodes.csv ---
    const nodeHeaders = ['id','name','namespace','cluster_id','cluster_name',
      'network_type','ip','host_ip','owner_kind','owner_name','kind',
      'status','is_external','resolution_source','labels'];
    const nodeRows = nodes.map(n => {
      // Look up original DependencyNode using React Flow node ID
      const originalNode = effectiveNodeIdMap[n.id] || {};
      return buildNodeRow(originalNode).map(escapeCSV).join(',');
    });
    const nodesCSV = UTF8_BOM + [nodeHeaders.join(','), ...nodeRows].join('\n');
    zip.file('nodes.csv', nodesCSV);
    
    // --- edges.csv ---
    // Use effectiveGraphData.edges for original edge data with protocol, port, etc.
    const visibleEdgeIds = new Set(edges.map(e => `${e.source}-${e.target}`));
    const originalEdges = (effectiveGraphData?.edges || []).filter((e: DependencyEdge) => 
      visibleEdgeIds.has(`${e.source_id}-${e.target_id}`)
    );
    const edgeHeaders = ['source_id','target_id','protocol','app_protocol',
      'port','request_count','error_count','retransmit_count','last_error_type'];
    const edgeRows = originalEdges.map((e: DependencyEdge) => [
      e.source_id || '',
      e.target_id || '',
      e.protocol || '',
      e.app_protocol || '',
      String(e.port || ''),
      String(e.request_count || 0),
      String(e.error_count || 0),
      String(e.retransmit_count || 0),
      e.last_error_type || ''
    ].map(escapeCSV).join(','));
    const edgesCSV = UTF8_BOM + [edgeHeaders.join(','), ...edgeRows].join('\n');
    zip.file('edges.csv', edgesCSV);
    
    // --- metadata.txt ---
    zip.file('metadata.txt', buildMetadata());
    
    // Generate and download
    const blob = await zip.generateAsync({ type: 'blob' });
    const filename = buildFilename('zip');
    downloadBlob(blob, filename);
  }, [nodes, edges, effectiveNodeIdMap, effectiveGraphData, buildMetadata, buildFilename]);
  
  // Export as Flat CSV (each row = one connection with full source/target info)
  const exportAsFlatCSV = useCallback(() => {
    // Use effectiveNodeIdMap for reliable node data lookup (same as drawer uses)
    
    // Find connected and isolated nodes
    const connectedIds = new Set<string>();
    edges.forEach(e => { connectedIds.add(e.source); connectedIds.add(e.target); });
    const isolatedNodes = nodes.filter(n => !connectedIds.has(n.id));
    
    // Compact metadata header (3 lines)
    const meta = [
      `# FLOWFISH MAP EXPORT | Analysis: ${selectedAnalysis?.name || 'N/A'} | Date: ${new Date().toLocaleString()}`,
      `# Type: ${isMultiClusterAnalysis ? 'Multi-cluster' : 'Single'} | Scope: ${selectedAnalysis?.scope_type || 'cluster'} | View: ${aggregatedView ? 'Workload' : 'Pod'}`,
      `# Nodes: ${nodes.length} | Connections: ${edges.length} | Isolated: ${isolatedNodes.length}`
    ];
    
    // Headers
    const headers = [
      'source_id','source_name','source_namespace','source_cluster_id','source_cluster_name',
      'source_network_type','source_ip','source_owner_kind','source_owner_name','source_is_external',
      'target_id','target_name','target_namespace','target_cluster_id','target_cluster_name',
      'target_network_type','target_ip','target_owner_kind','target_owner_name','target_is_external',
      'protocol','app_protocol','port','request_count','error_count','retransmit_count','last_error_type'
    ];
    
    // Use effectiveGraphData.edges for original edge data with protocol, port, etc.
    const visibleEdgeIds = new Set(edges.map(e => `${e.source}-${e.target}`));
    const originalEdges = (effectiveGraphData?.edges || []).filter((e: DependencyEdge) => 
      visibleEdgeIds.has(`${e.source_id}-${e.target_id}`)
    );
    
    // Edge rows - use effectiveNodeIdMap for node data, effectiveGraphData for edge data
    const edgeRows = originalEdges.map((edge: DependencyEdge) => {
      const src = effectiveNodeIdMap[edge.source_id] || {};
      const tgt = effectiveNodeIdMap[edge.target_id] || {};
      return [
        ...buildFlatNodeCols(src),
        ...buildFlatNodeCols(tgt),
        edge.protocol || '',
        edge.app_protocol || '',
        String(edge.port || ''),
        String(edge.request_count || 0),
        String(edge.error_count || 0),
        String(edge.retransmit_count || 0),
        edge.last_error_type || ''
      ].map(escapeCSV).join(',');
    });
    
    // Isolated node rows (source = target, no edge data)
    const isolatedRows = isolatedNodes.map(node => {
      const data = effectiveNodeIdMap[node.id] || {};
      return [
        ...buildFlatNodeCols(data),
        ...buildFlatNodeCols(data),  // same as source
        '','','','0','0','0',''      // empty edge data
      ].map(escapeCSV).join(',');
    });
    
    const csv = UTF8_BOM + [...meta, headers.join(','), ...edgeRows, ...isolatedRows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, buildFilename('csv'));
  }, [nodes, edges, effectiveNodeIdMap, effectiveGraphData, selectedAnalysis, isMultiClusterAnalysis, aggregatedView, buildFilename]);
  
  // Export menu items for dropdown
  const exportMenuItems = useMemo(() => [
    {
      key: 'zip',
      icon: <FolderOutlined />,
      label: 'ZIP (nodes + edges)',
      onClick: exportAsZip
    },
    {
      key: 'csv',
      icon: <FileTextOutlined />,
      label: 'Flat CSV',
      onClick: exportAsFlatCSV
    }
  ], [exportAsZip, exportAsFlatCSV]);

  // Resolve IP address to pod info if available
  const resolveIpToPod = useCallback((ipOrName: string): { 
    resolvedName: string; 
    resolvedNode: DependencyNode | null;
    isResolved: boolean;
  } => {
    // Check if it's an IP address
    if (!ipOrName?.match(/^\d+\.\d+\.\d+\.\d+$/)) {
      return { resolvedName: ipOrName, resolvedNode: null, isResolved: false };
    }
    
    // Try to find the actual pod for this IP
    const resolvedNode = ipToNodeLookup[ipOrName];
    if (resolvedNode && resolvedNode.name && resolvedNode.name !== ipOrName) {
      return { 
        resolvedName: resolvedNode.name, 
        resolvedNode, 
        isResolved: true 
      };
    }
    
    return { resolvedName: ipOrName, resolvedNode: null, isResolved: false };
  }, [ipToNodeLookup]);

  // Filter edges to only show those with valid source AND target nodes
  const safeEdges = useMemo(() => {
    const nodeIds = new Set(nodes.map(n => n.id));
    const filtered = edges.filter(edge => nodeIds.has(edge.source) && nodeIds.has(edge.target));
    
    // DEBUG: Log node and edge state
    debugLog('[STATE_DEBUG]', {
      nodesInState: nodes.length,
      edgesInState: edges.length,
      safeEdgesCount: filtered.length,
      nodeNamespaces: Array.from(new Set(nodes.map(n => (n.data as any)?.namespace || 'unknown'))),
      sampleNodeIds: nodes.slice(0, 3).map(n => n.id)
    });
    
    return filtered;
  }, [nodes, edges]);

  // ============================================
  // PERFORMANCE: Memoize classifyNodes result
  // Prevents re-computation on every render when deps haven't changed
  // ============================================
  const classificationResult = useMemo(() => {
    if (!effectiveGraphData?.nodes || !effectiveGraphData?.edges) {
      return { 
        primaryNodes: [] as DependencyNode[], 
        externalNodes: [] as DependencyNode[], 
        primaryNodeIds: new Set<string>(), 
        externalNodeIds: new Set<string>() 
      };
    }
    return classifyNodes(effectiveGraphData.nodes, effectiveGraphData.edges, selectedNamespaces);
  }, [effectiveGraphData?.nodes, effectiveGraphData?.edges, selectedNamespaces]);

  // Convert graph data to React Flow format with namespace-centric view
  // Uses effectiveGraphData which respects aggregatedView toggle
  useEffect(() => {
    if (!effectiveGraphData?.nodes || !effectiveGraphData?.edges) {
      // CRITICAL: Only clear if not already empty to prevent infinite loop
      // When analysis is cleared, getNodeEnrichment changes reference on every render
      // If we always call setNodes([]), it triggers re-render -> new getNodeEnrichment -> useEffect -> infinite loop
      setNodes(prevNodes => prevNodes.length === 0 ? prevNodes : []);
      setEdges(prevEdges => prevEdges.length === 0 ? prevEdges : []);
      previousNodeIds.current = new Set();
      initialLayoutApplied.current = false;
      return;
    }

    // ============================================
    // NAMESPACE-CENTRIC VIEW: Use pre-computed classification (memoized)
    // ============================================
    const hasNamespaceFilter = selectedNamespaces.length > 0;
    const { primaryNodes, externalNodes, primaryNodeIds, externalNodeIds } = classificationResult;
    
    // Combined nodes for display: primary + connected external (inclusive mode)
    let filteredNodes = hasNamespaceFilter 
      ? [...primaryNodes, ...externalNodes]  // Show primary + connected external
      : [...effectiveGraphData.nodes];       // No filter = show all
    
    // ============================================
    // SYSTEM NAMESPACE FILTER: Hide infrastructure namespaces by default
    // Patterns: openshift-*, kube-*, default (OpenShift/Kubernetes system namespaces)
    // Also includes SDN infrastructure namespaces (sdn-infrastructure, cluster-network, etc.)
    // ============================================
    const SYSTEM_NS_PATTERNS = [
      'openshift-', 'kube-',           // Prefix patterns (ends with -)
      'openshift', 'default',          // Exact matches
      'sdn-infrastructure',            // SDN gateway nodes
      'cluster-network', 'node-network', 'service-network'  // Network infrastructure
    ];
    const isSystemNamespace = (ns: string | undefined): boolean => {
      if (!ns) return false;
      return SYSTEM_NS_PATTERNS.some(pattern => 
        pattern.endsWith('-') ? ns.startsWith(pattern) : ns === pattern
      );
    };
    
    if (hideSystemNamespaces && !debouncedSearchTerm) {
      const beforeCount = filteredNodes.length;
      filteredNodes = filteredNodes.filter((node: DependencyNode) => 
        !isSystemNamespace(node.namespace)
      );
      const afterCount = filteredNodes.length;
      if (beforeCount !== afterCount) {
        debugLog(`[SYSTEM_FILTER] Hidden ${beforeCount - afterCount} system namespace nodes (${afterCount} remaining)`);
      }
    }
    
    // Filter noise nodes: 0.0.0.0 bind endpoints, reverse DNS (.in-addr.arpa)
    // These are listener metadata / PTR records, not real dependencies
    filteredNodes = filteredNodes.filter((node: DependencyNode) => 
      !isNoiseNode(node.name || '')
    );
    
    // DEBUG: Log node classification
    debugLog('[CLASSIFY_DEBUG]', {
      selectedNamespaces,
      selectedNamespacesCount: selectedNamespaces.length,
      hasNamespaceFilter,
      selectedClusterFilter,
      aggregatedView,
      graphDataNodes: effectiveGraphData.nodes.length,
      graphDataEdges: effectiveGraphData.edges.length,
      primaryNodesCount: primaryNodes.length,
      externalNodesCount: externalNodes.length,
      filteredNodesCount: filteredNodes.length,
      primaryNodesSample: primaryNodes.slice(0, 3).map(n => ({ id: n.id, name: n.name, ns: n.namespace }))
    });
    
    let connectedNodeIds = new Set<string>();
    
    // Apply search filter - supports IP, labels, metadata, enrichment data (DNS domains, TLS SNI), and resolved names
    // Uses debouncedSearchTerm (already 3+ char validated) to prevent filtering on every keystroke
    if (debouncedSearchTerm) {
      const searchLower = debouncedSearchTerm.toLowerCase();
      
      // ============================================
      // GLOBAL ENRICHMENT SEARCH: Find pods that queried matching domains
      // This is needed because external domains (like db-server.corp) are stored
      // in the QUERYING pod's enrichment data, not in the external IP node
      // ============================================
      const podsWithMatchingEnrichment = new Set<string>();
      enrichmentMap.forEach((enrichment, key) => {
        // key format is "namespace/podname"
        const [namespace, podName] = key.split('/');
        
        // Search in external domains (DNS lookups like db-server.corp)
        for (const domain of enrichment.externalDomains) {
          if (domain.toLowerCase().includes(searchLower)) {
            podsWithMatchingEnrichment.add(podName);
            break;
          }
        }
        // Search in TLS server names
        for (const sni of enrichment.tlsServerNames) {
          if (sni.toLowerCase().includes(searchLower)) {
            podsWithMatchingEnrichment.add(podName);
            break;
          }
        }
        // Search in unique DNS queries
        for (const query of enrichment.uniqueDnsQueries) {
          if (query.toLowerCase().includes(searchLower)) {
            podsWithMatchingEnrichment.add(podName);
            break;
          }
        }
      });
      
      // Enhanced search: check node fields + enrichment data + resolved names + global enrichment match
      const nodeMatchesSearchEnhanced = (node: DependencyNode): boolean => {
        // 1. Check basic node fields (uses debouncedSearchTerm for performance)
        if (nodeMatchesSearch(node, debouncedSearchTerm)) return true;
        
        // 2. Check if this node's name matches a pod with enrichment data containing the search term
        // This handles cases where a pod queried an external domain matching the search
        const nodeName = node.name || '';
        if (podsWithMatchingEnrichment.has(nodeName)) return true;
        
        // Also check if node name starts with any matching pod name (for ReplicaSet suffixes)
        const matchingPods = Array.from(podsWithMatchingEnrichment);
        for (let i = 0; i < matchingPods.length; i++) {
          const podName = matchingPods[i];
          if (nodeName.startsWith(podName) || podName.startsWith(nodeName)) return true;
        }
        
        // 3. Check node's own enrichment data (DNS domains, TLS server names, etc.)
        const enrichment = getNodeEnrichment(nodeName, node.namespace || '');
        if (enrichment) {
          // Search in external domains (DNS lookups like db-server.corp)
          for (const domain of enrichment.externalDomains) {
            if (domain.toLowerCase().includes(searchLower)) return true;
          }
          // Search in TLS server names
          for (const sni of enrichment.tlsServerNames) {
            if (sni.toLowerCase().includes(searchLower)) return true;
          }
          // Search in unique DNS queries
          for (const query of enrichment.uniqueDnsQueries) {
            if (query.toLowerCase().includes(searchLower)) return true;
          }
        }
        
        // 4. Check resolved name (IP resolved to pod name via nslookup enrichment)
        // For IP addresses, try to resolve to pod name
        const ipRegex = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/;
        if (ipRegex.test(nodeName) && ipToNodeLookup) {
          const resolvedNode = ipToNodeLookup[nodeName];
          if (resolvedNode) {
            // Search in resolved pod name
            if (resolvedNode.name?.toLowerCase().includes(searchLower)) return true;
            // Search in resolved namespace
            if (resolvedNode.namespace?.toLowerCase().includes(searchLower)) return true;
          }
        }
        
        return false;
      };
      
      const matchingNodes = filteredNodes.filter((node: DependencyNode) => 
        nodeMatchesSearchEnhanced(node)
      );
      
      const matchingNodeIds = new Set(matchingNodes.map(n => n.id));
      
      // Find connected nodes (neighbors) - IMPORTANT for showing external IPs connected to matching pods
      effectiveGraphData.edges.forEach((edge: DependencyEdge) => {
        if (matchingNodeIds.has(edge.source_id)) {
          connectedNodeIds.add(edge.target_id);
        }
        if (matchingNodeIds.has(edge.target_id)) {
          connectedNodeIds.add(edge.source_id);
        }
      });
      
      // CRITICAL FIX: Connected nodes might not be in filteredNodes (especially external IPs without namespace filter)
      // We need to ADD them from effectiveGraphData.nodes, not just filter existing ones
      const currentNodeIds = new Set(filteredNodes.map(n => n.id));
      const connectedNodesToAdd: DependencyNode[] = [];
      
      // Find connected nodes that are NOT already in filteredNodes
      effectiveGraphData.nodes.forEach((node: DependencyNode) => {
        if (connectedNodeIds.has(node.id) && !currentNodeIds.has(node.id)) {
          connectedNodesToAdd.push(node);
        }
      });
      
      // Filter existing nodes + add missing connected nodes
      filteredNodes = [
        ...filteredNodes.filter((node: DependencyNode) => 
          matchingNodeIds.has(node.id) || connectedNodeIds.has(node.id)
        ),
        ...connectedNodesToAdd
      ];
      
      // DEBUG: Comprehensive search diagnostics
      debugLog('[SEARCH_DEBUG]', {
        searchTerm: debouncedSearchTerm,
        selectedNamespaces,
        selectedClusterFilter,
        hasNamespaceFilter,
        graphDataNodesCount: effectiveGraphData.nodes.length,
        filteredNodesCount: filteredNodes.length,
        matchingNodesCount: matchingNodes.length,
        matchingNodesSample: matchingNodes.slice(0, 5).map(n => ({ id: n.id, name: n.name, ns: n.namespace })),
        connectedNodeIdsCount: connectedNodeIds.size,
        connectedNodesToAddCount: connectedNodesToAdd.length,
        connectedNodesToAddSample: connectedNodesToAdd.slice(0, 5).map(n => ({ id: n.id, name: n.name, ns: n.namespace })),
        podsWithMatchingEnrichmentCount: podsWithMatchingEnrichment.size,
        podsWithMatchingEnrichment: Array.from(podsWithMatchingEnrichment).slice(0, 10),
        // Check if search term matches any external node directly
        externalNodesInGraphData: effectiveGraphData.nodes.filter(n => n.namespace === 'external').slice(0, 10).map(n => ({ id: n.id, name: n.name })),
        // Check enrichmentMap for the search term
        enrichmentMapSize: enrichmentMap.size,
        enrichmentMapKeys: Array.from(enrichmentMap.keys()).slice(0, 10),
      });
    }
    
    // Apply pod filter
    if (selectedPod) {
      const selectedNodeIds = new Set([selectedPod]);
      effectiveGraphData.edges.forEach((edge: DependencyEdge) => {
        // PERFORMANCE: O(1) lookup instead of O(n) find()
        const sourceNode = nodeIdMap[edge.source_id];
        const targetNode = nodeIdMap[edge.target_id];
        if (sourceNode?.name === selectedPod) {
          connectedNodeIds.add(edge.target_id);
        }
        if (targetNode?.name === selectedPod) {
          connectedNodeIds.add(edge.source_id);
        }
      });
      
      filteredNodes = filteredNodes.filter((node: DependencyNode) => 
        node.name === selectedPod || connectedNodeIds.has(node.id)
      );
    }
    
    // Filter internal traffic
    if (!showInternalTraffic) {
      const internalNodeIds = new Set(
        filteredNodes.filter(n => isInternalTraffic(n)).map(n => n.id)
      );
      filteredNodes = filteredNodes.filter(n => !internalNodeIds.has(n.id));
    }
    
    // =====================================================
    // EXTERNAL FILTERS: PUBLIC, DATACENTER, UNRESOLVED IP
    // =====================================================
    // These filters use OR logic when multiple are enabled
    // Each filter selects specific external node types + their connections
    // When multiple enabled: Show Union of all selected types
    const hasExternalFilter = focusPublicOnly || focusDataCenterOnly || focusIPOnly;
    
    // Target node IDs for external filters (Public/DC/IP nodes)
    // Defined outside block so it can be used in edge filtering
    let targetNodeIds = new Set<string>();
    
    if (hasExternalFilter) {
      // Helper: Check if node is cluster infrastructure (should be excluded from Unresolved filter)
      const isClusterInfrastructure = (n: DependencyNode): boolean => {
        const networkType = (n as any).network_type || '';
        const name = n.name || '';
        
        // Explicit network type from backend
        if (networkType === 'SDN-Gateway' || networkType === 'Node-Network' || 
            networkType === 'Pod-Network' || networkType === 'Service-Network') {
          return true;
        }
        
        // SDN-Gateway IP pattern detection (fallback if network_type not set)
        // These are typically .1 or .2 addresses in pod network ranges
        if (isUnresolvedIP(name) && isPrivateIP(name)) {
          const parts = name.split('.').map(Number);
          // 10.194.x.1, 10.194.x.2 pattern (SDN Gateway in pod network)
          if (parts[0] === 10 && parts[1] === 194 && (parts[3] === 1 || parts[3] === 2)) {
            return true;
          }
          // 10.128.x.1, 10.128.x.2 pattern (common OpenShift SDN)
          if (parts[0] === 10 && parts[1] === 128 && (parts[3] === 1 || parts[3] === 2)) {
            return true;
          }
        }
        
        return false;
      };
      
      // Helper: Check if node has a real Kubernetes namespace
      const hasKubernetesNamespace = (n: DependencyNode): boolean => {
        const namespace = n.namespace || '';
        const nsLower = namespace.toLowerCase();
        return !!(namespace && 
          nsLower !== 'external' && 
          nsLower !== 'unknown' && 
          namespace !== '' &&
          !namespace.startsWith('10.') &&
          !namespace.startsWith('192.') &&
          !namespace.startsWith('172.'));
      };
      
      // Helper: Check if IP is unresolved and outside cluster
      const isUnresolvedExternalIP = (n: DependencyNode): boolean => {
        const name = n.name || '';
        if (!isUnresolvedIP(name)) return false;
        if (isClusterInfrastructure(n)) return false;
        if (hasKubernetesNamespace(n)) return false;
        return true;
      };
      
      // Collect target node IDs based on ALL enabled filters (OR logic)
      // (targetNodeIds is defined above the if block for use in edge filtering)
      
      // ============================================
      // PERFORMANCE: Pre-compute cluster pod lookup map - O(n) instead of O(edges * nodes)
      // Maps nodeId -> isClusterPod for O(1) lookup in edge iteration
      // Note: Using Record instead of Map to avoid conflict with Map component name
      // ============================================
      const clusterPodMap: Record<string, boolean> = {};
      filteredNodes.forEach(n => {
        const ns = (n.namespace || '').toLowerCase();
        const name = n.name || '';
        // Check if node name is an IP address - if so, it's NOT a cluster pod
        // This excludes SDN gateways, cluster-network IPs, etc.
        const isNameAnIP = /^\d+\.\d+\.\d+\.\d+$/.test(name);
        // Exclude infrastructure/system namespaces (not real application pods)
        const isSystemNamespace = ns.startsWith('openshift-') || 
                                   ns.startsWith('kube-') ||
                                   ns === 'sdn-infrastructure' || 
                                   ns === 'cluster-network' || 
                                   ns === 'node-network' || 
                                   ns === 'service-network' ||
                                   ns === 'default' ||
                                   ns === 'kasten-io';
        // Only include real application pods (not infra, not system, not IPs)
        const isCluster = !!(ns && ns !== 'external' && ns !== 'unknown' && 
                  !ns.startsWith('10.') && !ns.startsWith('192.') && !ns.startsWith('172.') &&
                  !isNameAnIP && !isSystemNamespace);
        clusterPodMap[n.id] = isCluster;
      });
      
      // Debug counters
      let publicCount = 0, dataCenterCount = 0, unresolvedCount = 0;
      
      filteredNodes.forEach(n => {
        // PUBLIC: Real internet IPs + DNS-resolved public domains (amazon.com, azure.com)
        if (focusPublicOnly) {
          const isPub = isPublicEndpoint(n);
          if (isPub) {
            targetNodeIds.add(n.id);
            publicCount++;
          }
          // Debug: Log all external namespace nodes to see what's being checked
          if (n.namespace?.toLowerCase() === 'external') {
            debugLog('[PUBLIC_DEBUG] External node:', {
              name: n.name,
              ip: n.ip,  // Original IP for DNS-enriched nodes
              namespace: n.namespace,
              isPublic: isPub,
              ipIsPublic: isPublicIP(n.ip || ''),
              nameIsPublicIP: isPublicIP(n.name || ''),
              ipIsPrivate: isPrivateIP(n.ip || ''),
              nameIsPrivateIP: isPrivateIP(n.name || '')
            });
          }
        }
        
        // DATACENTER: Private IPs/hostnames outside cluster (databases, legacy systems)
        if (focusDataCenterOnly) {
          const isDC = isDataCenterNode(n);
          if (isDC) {
            targetNodeIds.add(n.id);
            dataCenterCount++;
          }
          // Debug first 5 external nodes
          if (dataCenterCount < 5 || (n.namespace?.toLowerCase() === 'external' && dataCenterCount < 10)) {
            debugLog('[DC_DEBUG] Node check:', {
              name: n.name,
              namespace: n.namespace,
              networkType: (n as any).network_type,
              isDataCenter: isDC,
              isPrivateIP: isPrivateIP(n.name || ''),
              isUnresolvedIP: isUnresolvedIP(n.name || ''),
              isDomain: isDomainName(n.name || ''),
              isServerHost: isServerHostname(n.name || '')
            });
          }
        }
        
        // UNRESOLVED IP: Raw IP addresses that haven't been resolved (outside cluster only)
        if (focusIPOnly && isUnresolvedExternalIP(n)) {
          targetNodeIds.add(n.id);
          unresolvedCount++;
        }
      });
      
      // PERFORMANCE: O(1) lookup using pre-computed map
      const isClusterPod = (nodeId: string): boolean => clusterPodMap[nodeId] ?? false;
      
      // PERFORMANCE: Create node lookup map for O(1) access in debug logs
      // Note: Using Record instead of Map to avoid conflict with Map component name
      const filteredNodeLookup: Record<string, DependencyNode> = {};
      filteredNodes.forEach(n => { filteredNodeLookup[n.id] = n; });
      
      // Include nodes connected to target nodes
      // For Public/DataCenter filters: Only include cluster pods as connections
      // This prevents showing intermediate IPs when filtering for external endpoints
      const connectedNodes = new Set(targetNodeIds);
      let addedConnections = 0;
      effectiveGraphData.edges.forEach((edge: DependencyEdge) => {
        if (targetNodeIds.has(edge.source_id)) {
          // Target is source -> add target_id only if it's a cluster pod
          const targetIsClusterPod = isClusterPod(edge.target_id);
          if (targetIsClusterPod) {
            connectedNodes.add(edge.target_id);
            addedConnections++;
          } else if (addedConnections < 5) {
            const targetNode = filteredNodeLookup[edge.target_id];
            debugLog('[CONN_DEBUG] Skipped non-cluster target:', {
              targetId: edge.target_id,
              targetName: targetNode?.name,
              targetNs: targetNode?.namespace
            });
          }
        }
        if (targetNodeIds.has(edge.target_id)) {
          // Target is destination -> add source_id only if it's a cluster pod
          if (isClusterPod(edge.source_id)) {
            connectedNodes.add(edge.source_id);
          }
        }
      });
      
      debugLog('[FILTER_DEBUG] External filters (OR logic):', {
        publicEnabled: focusPublicOnly,
        dataCenterEnabled: focusDataCenterOnly,
        unresolvedEnabled: focusIPOnly,
        publicNodes: publicCount,
        dataCenterNodes: dataCenterCount,
        unresolvedNodes: unresolvedCount,
        totalTargets: targetNodeIds.size,
        withConnections: connectedNodes.size,
        sampleTargets: Array.from(targetNodeIds).slice(0, 10),
        sampleConnected: Array.from(connectedNodes).filter(id => !targetNodeIds.has(id)).slice(0, 5)
      });
      
      filteredNodes = filteredNodes.filter(n => connectedNodes.has(n.id));
    }

    // ============================================
    // ERROR FILTER: When active, show only nodes connected to error edges
    // CRITICAL: Must use filteredNodes context, not effectiveGraphData
    // This ensures error filter respects other active filters (namespace, etc.)
    // ============================================
    if (filterErrorsOnly) {
      // Step 1: Get current filtered node IDs
      const currentFilteredNodeIds = new Set(filteredNodes.map(n => n.id));
      
      // Step 2: Find error edges where BOTH endpoints are in current filtered nodes
      // This respects namespace/search/other filters
      const errorEdgeNodeIds = new Set<string>();
      effectiveGraphData.edges.forEach((edge: DependencyEdge) => {
        // Only consider edges where both endpoints pass current filters
        const sourceInFiltered = currentFilteredNodeIds.has(edge.source_id);
        const targetInFiltered = currentFilteredNodeIds.has(edge.target_id);
        
        if (sourceInFiltered && targetInFiltered && (edge.error_count || 0) > 0) {
          errorEdgeNodeIds.add(edge.source_id);
          errorEdgeNodeIds.add(edge.target_id);
        }
      });
      
      // Step 3: Keep only nodes that are part of error edges
      filteredNodes = filteredNodes.filter((node: DependencyNode) => 
        errorEdgeNodeIds.has(node.id)
      );
      
      debugLog(`[ERROR_FILTER] Found ${errorEdgeNodeIds.size} nodes from error edges (respecting other filters)`);
    }

    const currentNodeIds = new Set(filteredNodes.map((n: DependencyNode) => n.id));
    const nodeIdSet = currentNodeIds;
    
    // Track which nodes are external for styling (multi-namespace support)
    const isExternalNode = (nodeId: string) => hasNamespaceFilter && externalNodeIds.has(nodeId);
    
    // Filter edges to match filtered nodes (from effective data)
    // CRITICAL FIX: When Public/DataCenter/Unresolved filters are active,
    // only show edges where AT LEAST ONE endpoint is a target node (Public/DC/IP)
    // This prevents showing internal cluster traffic when filtering for external endpoints
    const relevantEdges = effectiveGraphData.edges.filter((e: DependencyEdge) => {
      // Basic check: both endpoints must be in filtered nodes
      if (!nodeIdSet.has(e.source_id) || !nodeIdSet.has(e.target_id)) {
        return false;
      }
      
      // When external filters are active, require at least one endpoint to be a target node
      // This excludes internal Pod-to-Pod traffic when filtering for Public/DataCenter/IP endpoints
      if (hasExternalFilter) {
        const sourceIsTarget = targetNodeIds.has(e.source_id);
        const targetIsTarget = targetNodeIds.has(e.target_id);
        return sourceIsTarget || targetIsTarget;
      }
      
      return true;
    });
    
    // PERFORMANCE: O(1) lookup map for filtered nodes - used in edge processing
    const filteredNodeMap: Record<string, DependencyNode> = {};
    filteredNodes.forEach(n => { filteredNodeMap[n.id] = n; });

    setNodes(prevNodes => {
      // If no nodes after filtering, show empty
      if (filteredNodes.length === 0) {
        initialLayoutApplied.current = false;
        previousNodeIds.current = new Set();
        (window as any).__lastLayout = null; // Reset so next layout applies
        return [];
      }
      
      // Check layout change inside callback to ensure correct comparison
      const lastLayout = (window as any).__lastLayout;
      const lastNodeSize = (window as any).__lastNodeSize;
      const layoutChanged = layout !== lastLayout;
      const nodeSizeChanged = nodeSize !== lastNodeSize;
      
      // ALWAYS reapply layout when layout type changes
      if (layoutChanged) {
        (window as any).__lastLayout = layout;
        (window as any).__lastNodeSize = nodeSize;
        initialLayoutApplied.current = true;
        previousNodeIds.current = currentNodeIds;
        return applyLayout(filteredNodes, layout, 180, nodeSize, relevantEdges, selectedNamespaces, externalNodeIds);
      }
      
      // Check if node set changed (filters applied, nodes added/removed)
      const addedNodes = Array.from(currentNodeIds).filter(id => !previousNodeIds.current.has(id));
      const removedNodes = Array.from(previousNodeIds.current).filter(id => !currentNodeIds.has(id));
      const nodeSetChanged = addedNodes.length > 0 || removedNodes.length > 0;
      
      // Calculate change percentage for smart relayout decision
      const totalPreviousNodes = previousNodeIds.current.size || 1;
      const changePercent = ((addedNodes.length + removedNodes.length) / totalPreviousNodes) * 100;
      
      // Smart relayout: only for significant changes (>25%) or when necessary
      // Small changes keep existing positions for better UX
      const significantChange = changePercent > 25 || prevNodes.length === 0;
      
      // Force full layout in these cases:
      // - Initial layout not applied
      // - Node size changed  
      // - Significant node set change (>25% of nodes changed)
      const needsFullLayout = !initialLayoutApplied.current || 
        nodeSizeChanged ||
        (nodeSetChanged && significantChange);
      
      if (needsFullLayout) {
        (window as any).__lastLayout = layout;
        (window as any).__lastNodeSize = nodeSize;
        initialLayoutApplied.current = true;
        previousNodeIds.current = currentNodeIds;
        return applyLayout(filteredNodes, layout, 180, nodeSize, relevantEdges, selectedNamespaces, externalNodeIds);
      }
      
      // Update tracking for incremental updates
      (window as any).__lastLayout = layout;
      (window as any).__lastNodeSize = nodeSize;
      
      // CRITICAL FIX: Only include nodes that are BOTH in prevNodes AND in currentNodeIds (filteredNodes)
      // This ensures that when filters change (e.g., Public filter), removed nodes are not kept
      const existingNodesMap: Record<string, Node> = {};
      prevNodes.forEach(n => { 
        // Only keep nodes that are still in the filtered set
        if (currentNodeIds.has(n.id)) {
          existingNodesMap[n.id] = n; 
        }
      });
      const newNodes: Node[] = [];
      const newNodeIds = filteredNodes.filter(n => !existingNodesMap[n.id]);
      // Use count of nodes that will be kept, not all prev nodes
      const existingCount = Object.keys(existingNodesMap).length;
      const cols = Math.ceil(Math.sqrt(existingCount + newNodeIds.length));
      
      // ============================================
      // PERFORMANCE: Pre-calculate connected node IDs for O(1) lookup
      // Instead of O(nodes × edges), now O(edges) + O(1) per node
      // ============================================
      const connectedToFocusedIds = new Set<string>();
      if (focusedNodeId) {
        relevantEdges.forEach(e => {
          if (e.source_id === focusedNodeId) connectedToFocusedIds.add(e.target_id);
          if (e.target_id === focusedNodeId) connectedToFocusedIds.add(e.source_id);
        });
      }
      
      // Pre-calculate nodes matching highlighted namespace for O(1) lookup
      // Also calculate nodes CONNECTED to highlighted namespace (1st degree neighbors)
      const nodesInHighlightedNamespace = new Set<string>();
      const connectedToHighlightedNamespace = new Set<string>();
      if (highlightedNamespace) {
        // First pass: find nodes in highlighted namespace
        filteredNodes.forEach(n => {
          if (n.namespace === highlightedNamespace) nodesInHighlightedNamespace.add(n.id);
        });
        // Second pass: find nodes connected to highlighted namespace (like focus mode)
        relevantEdges.forEach(e => {
          if (nodesInHighlightedNamespace.has(e.source_id) && !nodesInHighlightedNamespace.has(e.target_id)) {
            connectedToHighlightedNamespace.add(e.target_id);
          }
          if (nodesInHighlightedNamespace.has(e.target_id) && !nodesInHighlightedNamespace.has(e.source_id)) {
            connectedToHighlightedNamespace.add(e.source_id);
          }
        });
      }
      
      // Pre-calculate nodes with highlighted event type for O(1) lookup
      // Also calculate nodes CONNECTED to nodes with this event type (1st degree neighbors)
      const nodesWithHighlightedEventType = new Set<string>();
      const connectedToEventTypeNodes = new Set<string>();
      if (highlightedEventType) {
        // Helper function to check if node has the event type
        const nodeHasEventType = (n: DependencyNode): boolean => {
          const nodeEnrichment = getNodeEnrichment(n.name || '', n.namespace || '');
          if (!nodeEnrichment) return false;
          switch (highlightedEventType) {
            case 'dns_query': return nodeEnrichment.dnsQueryCount > 0;
            case 'sni_event': return nodeEnrichment.tlsConnectionCount > 0;
            case 'process_event': return nodeEnrichment.processEventCount > 0;
            case 'file_event': return nodeEnrichment.fileEventCount > 0;
            case 'security_event': return nodeEnrichment.securityEventCount > 0;
            case 'oom_event': return nodeEnrichment.oomKillCount > 0;
            case 'bind_event': return nodeEnrichment.bindEventCount > 0;
            case 'mount_event': return nodeEnrichment.mountEventCount > 0;
            case 'network_flow': return true;
            default: return true;
          }
        };
        
        // First pass: find nodes with the event type
        filteredNodes.forEach(n => {
          if (nodeHasEventType(n)) {
            nodesWithHighlightedEventType.add(n.id);
          }
        });
        
        // Second pass: find nodes connected to nodes with this event type (like namespace highlight)
        relevantEdges.forEach(e => {
          if (nodesWithHighlightedEventType.has(e.source_id) && !nodesWithHighlightedEventType.has(e.target_id)) {
            connectedToEventTypeNodes.add(e.target_id);
          }
          if (nodesWithHighlightedEventType.has(e.target_id) && !nodesWithHighlightedEventType.has(e.source_id)) {
            connectedToEventTypeNodes.add(e.source_id);
          }
        });
      }
      
      filteredNodes.forEach((node, idx) => {
        const existingNode = existingNodesMap[node.id];
        
        // ============================================
        // IP RESOLUTION: Try to resolve IP to actual pod name
        // ============================================
        const nodeName = node.name || '';
        const { resolvedName, resolvedNode, isResolved } = resolveIpToPod(nodeName);
        
        // Use resolved name for display, keep original for public IP check
        const { displayName, isPublicIP: isNodePublicIP, isDataCenterIP: isNodeDataCenterIP, isSDNGateway: isSDNGatewayByIP } = cleanNodeName(
          isResolved ? resolvedName : nodeName, 
          node.id
        );
        
        // ============================================
        // NAMESPACE-CENTRIC: Check if external node
        // ============================================
        const isExternal = isExternalNode(node.id);
        
        // ============================================
        // NODE TYPE DETECTION: Service, SDN-Gateway, Network Types, etc.
        // ============================================
        const isServiceNode = node.owner_kind === 'Service';
        // SDN Gateway: from backend network_type, name pattern, OR IP ending with .1
        const isSDNGateway = nodeName.includes('SDN-Gateway') || node.network_type === 'SDN-Gateway' || isSDNGatewayByIP;
        const isNodeIP = nodeName.match(/^worker|^master|^node/i) !== null || node.network_type === 'Node-Network';
        
        // Get network type info from backend classification
        const networkTypeInfo = getNetworkTypeInfo(node.network_type);
        const hasNetworkType = !!networkTypeInfo && !isServiceNode && !isSDNGateway && !isNodeIP;
        
        // Get enrichment data - try resolved node first, then original
        const enrichmentNode = resolvedNode || node;
        const enrichment = getNodeEnrichment(
          enrichmentNode.name || nodeName, 
          enrichmentNode.namespace || node.namespace || ''
        );
        
        // For external/public IPs, try to detect known service
        const knownService = isNodePublicIP ? detectKnownService(nodeName) : null;
        
        // DataCenter IP color (cyan)
        const DATACENTER_IP_COLOR = '#06b6d4';
        
        // Color logic: use resolved node's namespace color if available
        let nsColor: string;
        if (isServiceNode) {
          nsColor = '#8b5cf6';  // Purple for Service nodes
        } else if (isSDNGateway) {
          nsColor = '#ec4899';  // Pink for SDN-Gateway
        } else if (hasNetworkType && networkTypeInfo) {
          nsColor = networkTypeInfo.color;  // Use network type color for CIDR-classified nodes
        } else if (isNodePublicIP) {
          nsColor = knownService?.color || PUBLIC_IP_COLOR;  // Orange for public IPs
        } else if (isNodeDataCenterIP) {
          nsColor = DATACENTER_IP_COLOR;  // Cyan for datacenter IPs
        } else if (isResolved && resolvedNode?.namespace) {
          nsColor = getNamespaceColor(resolvedNode.namespace);
        } else if (isExternal) {
          nsColor = getNamespaceColor(node.namespace || 'external');
        } else {
          nsColor = getNamespaceColor(node.namespace || 'default');
        }
        
        // Base size - external nodes are slightly smaller
        let size = nodeSize * (isExternal ? 1.5 : 1.8);  // Increased external size slightly
        if (enrichment && enrichment.activityLevel === 'high') size *= 1.15;
        if (enrichment && enrichment.activityLevel === 'critical') size *= 1.25;
        
        // Build label with optional IP and known service
        const nodeIp = (node as any)?.ip || (node as any)?.pod_ip || (node as any)?.host_ip;
        let finalLabel = displayName;
        
        // Add type prefix for visual distinction
        if (isServiceNode) {
          finalLabel = `◇ ${displayName}`;  // Diamond for Service
        } else if (isSDNGateway) {
          finalLabel = `◐ ${displayName}`;  // Half-circle for SDN-Gateway
        } else if (isNodeIP) {
          finalLabel = `▢ ${displayName}`;  // Square for Node IP
        } else if (hasNetworkType && networkTypeInfo) {
          finalLabel = `${networkTypeInfo.icon} ${displayName}`;  // Network type icon
        }
        
        // For public IPs with known service, show service name instead
        if (isNodePublicIP && knownService) {
          finalLabel = `${knownService.icon} ${knownService.name}`;
        }
        
        // If resolved from IP, show pod name with IP indicator
        if (isResolved && !isNodePublicIP) {
          const shortName = resolvedName.length > 20 ? resolvedName.substring(0, 18) + '...' : resolvedName;
          finalLabel = `● ${shortName}`;
        }
        
        // Show IP if enabled and we have an IP that's different from the name
        if (showNodeIP && nodeIp) {
          const isNameAnIP = nodeName.match(/^\d+\.\d+\.\d+\.\d+$/);
          if (!isNameAnIP && nodeIp !== nodeName) {
            finalLabel = `${finalLabel}\n${nodeIp}`;
          }
        }
        
        // Show pod/cluster count for aggregated nodes
        if ((node as any)._isAggregated) {
          const podCount = (node as any)._podCount || 1;
          const clusterCount = (node as any)._clusterCount || 1;
          
          if (clusterCount > 1) {
            // Multi-cluster: show both pod and cluster count
            finalLabel = `${finalLabel} [${podCount}p/${clusterCount}c]`;
          } else if (podCount > 1) {
            // Single cluster: show only pod count
            finalLabel = `${finalLabel} [${podCount}]`;
          }
        }
        
        // ============================================
        // PERFORMANCE: O(1) lookups using pre-calculated Sets
        // ============================================
        
        // Highlight logic - O(1) Set lookup instead of property check
        const isInHighlightedNamespace = nodesInHighlightedNamespace.has(node.id);
        const isConnectedToHighlightedNs = connectedToHighlightedNamespace.has(node.id);
        const matchesNamespace = !highlightedNamespace || isInHighlightedNamespace || isConnectedToHighlightedNs;
        
        // Event type filter - O(1) Set lookup with 3-level hierarchy (like namespace)
        const hasHighlightedEventType = nodesWithHighlightedEventType.has(node.id);
        const isConnectedToEventType = connectedToEventTypeNodes.has(node.id);
        const matchesEventType = !highlightedEventType || hasHighlightedEventType || isConnectedToEventType;
        
        // ============================================
        // ENHANCED FOCUS SYSTEM: 3-level visual hierarchy
        // Level 1: Focused node (clicked) OR nodes in highlighted namespace
        // Level 2: Connected nodes (1st degree neighbors) - O(1) lookup
        // Level 3: Other nodes (faded)
        // ============================================
        const isFocusedNode = focusedNodeId === node.id;
        // PERFORMANCE: O(1) Set lookup instead of O(edges) .some() call
        const isFirstDegreeNeighbor = !isFocusedNode && connectedToFocusedIds.has(node.id);
        const isConnectedToFocused = isFocusedNode || isFirstDegreeNeighbor;
        
        const isHighlighted = matchesNamespace && matchesEventType;
        const hasAnyFilter = highlightedNamespace || highlightedEventType;
        const hasFocusFilter = !!focusedNodeId;
        const hasNamespaceHighlight = !!highlightedNamespace;
        const hasEventTypeHighlight = !!highlightedEventType;
        
        // Opacity: 3-level hierarchy for focus mode, namespace highlight, AND event type highlight
        let nodeOpacity = isExternal ? 0.7 : 1;
        if (hasFocusFilter) {
          // Node click focus takes priority
          if (isFocusedNode) {
            nodeOpacity = 1;  // Focused: fully visible
          } else if (isFirstDegreeNeighbor) {
            nodeOpacity = 0.95;  // Connected: almost fully visible
          } else {
            nodeOpacity = 0.08;  // Others: very faded
          }
        } else if (hasNamespaceHighlight) {
          // Namespace highlight: 3-level hierarchy like focus mode
          if (isInHighlightedNamespace) {
            nodeOpacity = 1;  // In namespace: fully visible
          } else if (isConnectedToHighlightedNs) {
            nodeOpacity = 0.7;  // Connected to namespace: visible but dimmed
          } else {
            nodeOpacity = 0.35;  // Others: faded but readable
          }
        } else if (hasEventTypeHighlight) {
          // Event type highlight: 3-level hierarchy like namespace
          if (hasHighlightedEventType) {
            nodeOpacity = 1;  // Has this event type: fully visible
          } else if (isConnectedToEventType) {
            nodeOpacity = 0.7;  // Connected to node with event type: visible but dimmed
          } else {
            nodeOpacity = 0.25;  // Others: faded but still visible
          }
        }
        
        // Scale: focused node bigger, connected nodes slightly bigger
        let nodeScale = 1;
        if (hasFocusFilter) {
          if (isFocusedNode) {
            nodeScale = 1.25;  // Focused: 25% bigger
          } else if (isFirstDegreeNeighbor) {
            nodeScale = 1.1;   // Connected: 10% bigger
          } else {
            nodeScale = 0.85;  // Others: slightly smaller
          }
        } else if (hasNamespaceHighlight) {
          // Namespace highlight: similar scale hierarchy
          if (isInHighlightedNamespace) {
            nodeScale = 1.15;  // In namespace: bigger
          } else if (isConnectedToHighlightedNs) {
            nodeScale = 1.05;  // Connected: slightly bigger
          } else {
            nodeScale = 0.85;  // Others: smaller
          }
        } else if (hasEventTypeHighlight) {
          // Event type highlight: similar scale hierarchy like namespace
          if (hasHighlightedEventType) {
            nodeScale = 1.15;  // Has event type: bigger
          } else if (isConnectedToEventType) {
            nodeScale = 1.05;  // Connected: slightly bigger
          } else {
            nodeScale = 0.85;  // Others: smaller
          }
        } else if (isExternal) {
          nodeScale = 0.9;
        }
        
        // Border style: external nodes get dashed border
        let borderStyle = isNodePublicIP ? '3px solid #fbbf24' : 'none';
        if (isExternal) {
          borderStyle = '2px dashed rgba(148, 163, 184, 0.7)';  // Slate dashed border
        }
        if (enrichment?.riskLevel === 'danger') {
          borderStyle = '3px solid #ff4d4f';
        } else if (enrichment?.riskLevel === 'warning') {
          borderStyle = '3px solid #faad14';
        }
        
        // Shadow effects
        const publicIPShadow = isNodePublicIP ? '0 0 15px rgba(245, 158, 11, 0.5), ' : '';
        const dangerShadow = enrichment?.riskLevel === 'danger' ? '0 0 15px rgba(255, 77, 79, 0.5), ' : '';
        const warningShadow = enrichment?.riskLevel === 'warning' ? '0 0 10px rgba(250, 173, 20, 0.4), ' : '';
        
        // Focus mode shadows - enhanced visual hierarchy
        const focusedGlow = isFocusedNode 
          ? `0 0 25px rgba(99, 102, 241, 0.8), 0 0 50px rgba(99, 102, 241, 0.4), ` // Indigo glow for focused
          : '';
        const connectedGlow = isFirstDegreeNeighbor 
          ? `0 0 12px rgba(34, 197, 94, 0.6), ` // Green subtle glow for connected
          : '';
        
        // Namespace highlight glow - similar to focus mode but with namespace color
        const namespaceHighlightGlow = (hasNamespaceHighlight && isInHighlightedNamespace)
          ? `0 0 20px ${nsColor}, 0 0 40px ${nsColor}66, ` // Glow with namespace color
          : '';
        const namespaceConnectedGlow = (hasNamespaceHighlight && isConnectedToHighlightedNs)
          ? `0 0 10px rgba(148, 163, 184, 0.5), ` // Subtle gray glow for connected
          : '';
        
        // Event type highlight glow - cyan/teal color for event type highlighting
        const eventTypeColor = '#06b6d4'; // Cyan for event type
        const eventTypeHighlightGlow = (hasEventTypeHighlight && hasHighlightedEventType)
          ? `0 0 20px ${eventTypeColor}, 0 0 40px ${eventTypeColor}66, ` // Cyan glow
          : '';
        const eventTypeConnectedGlow = (hasEventTypeHighlight && isConnectedToEventType)
          ? `0 0 10px rgba(6, 182, 212, 0.4), ` // Subtle cyan glow for connected
          : '';
        
        // Common node data
        const nodeData = { 
          label: finalLabel,
          namespace: resolvedNode?.namespace || node.namespace,
          kind: resolvedNode?.kind || node.kind,
          originalNode: node,
          resolvedNode: resolvedNode,  // The actual pod if IP was resolved
          isResolved: isResolved,      // True if IP was resolved to pod name
          originalIp: isResolved ? nodeName : null,  // Original IP if resolved
          isPublicIP: isNodePublicIP,
          isDataCenterIP: isNodeDataCenterIP,  // True if this is a datacenter IP (private, non-cluster)
          isExternal: isExternal,  // Namespace-centric: true if node is from different namespace
          isExternalConnection: isExternal && hasNamespaceFilter,  // For drawer context
          isServiceNode: isServiceNode,  // True if this is a Kubernetes Service
          isSDNGateway: isSDNGateway,    // True if this is SDN Gateway
          networkType: node.network_type,  // Network type classification from backend
          networkTypeInfo: networkTypeInfo,  // Color/icon info for network type
          hasNetworkType: hasNetworkType,  // True if has CIDR-based network type
          knownService,
          enrichment,
          showEnrichmentBadges,
          // Aggregation metadata (when aggregatedView is enabled)
          isAggregated: (node as any)._isAggregated || false,
          originalNodes: (node as any)._originalNodes || null,
          podCount: (node as any)._podCount || 1,
          podsByCluster: (node as any)._podsByCluster || null,
          clusterIds: (node as any)._clusterIds || null,
          clusterCount: (node as any)._clusterCount || 1,
        };
        
        // Shadow based on state - with focus mode enhancements
        const baseShadow = isExternal 
          ? '0 2px 6px rgba(0,0,0,0.15)'  // Subtle shadow for external
          : `${dangerShadow}${warningShadow}${publicIPShadow}0 3px 10px rgba(0,0,0,0.2)`;
        const highlightShadow = `${dangerShadow}${warningShadow}${publicIPShadow}0 0 20px ${nsColor}, 0 4px 12px rgba(0,0,0,0.3)`;
        
        // Focus mode shadow with glow effects
        const focusShadow = hasFocusFilter
          ? (isFocusedNode 
              ? `${focusedGlow}${dangerShadow}${warningShadow}0 0 30px ${nsColor}, 0 8px 20px rgba(0,0,0,0.4)` // Prominent glow for focused
              : (isFirstDegreeNeighbor 
                  ? `${connectedGlow}${dangerShadow}${warningShadow}0 0 15px ${nsColor}66, 0 4px 12px rgba(0,0,0,0.25)` // Subtle glow for connected
                  : '0 1px 3px rgba(0,0,0,0.1)')) // Minimal shadow for others
          : null;
        
        // Namespace highlight shadow - 3-level hierarchy like focus mode
        const namespaceHighlightShadow = hasNamespaceHighlight
          ? (isInHighlightedNamespace
              ? `${namespaceHighlightGlow}${dangerShadow}${warningShadow}0 0 25px ${nsColor}, 0 6px 16px rgba(0,0,0,0.35)` // Prominent glow
              : (isConnectedToHighlightedNs
                  ? `${namespaceConnectedGlow}${dangerShadow}${warningShadow}0 4px 10px rgba(0,0,0,0.2)` // Subtle shadow for connected
                  : '0 1px 2px rgba(0,0,0,0.08)')) // Minimal shadow for others
          : null;
        
        // Event type highlight shadow - 3-level hierarchy like namespace highlight
        const eventTypeHighlightShadow = hasEventTypeHighlight
          ? (hasHighlightedEventType
              ? `${eventTypeHighlightGlow}${dangerShadow}${warningShadow}0 0 25px ${eventTypeColor}, 0 6px 16px rgba(0,0,0,0.35)` // Prominent cyan glow
              : (isConnectedToEventType
                  ? `${eventTypeConnectedGlow}${dangerShadow}${warningShadow}0 4px 10px rgba(0,0,0,0.2)` // Subtle shadow for connected
                  : '0 1px 2px rgba(0,0,0,0.08)')) // Minimal shadow for others
          : null;
        
        // Node shape: different shapes for different node types
        // Service: rounded square (25%), SDN-Gateway: hexagon-ish (35%), Network Types: custom, Pod: circle (50%)
        const nodeBorderRadius = isServiceNode ? '25%' 
          : isSDNGateway ? '35%' 
          : (hasNetworkType && networkTypeInfo) ? networkTypeInfo.borderRadius 
          : '50%';
        
        if (existingNode) {
          // Determine final shadow: focus mode > namespace highlight > event type highlight > base
          const finalShadow = focusShadow ?? namespaceHighlightShadow ?? eventTypeHighlightShadow ?? baseShadow;
          
          // Determine zIndex: focused > ns-highlighted > event-type-highlighted > connected > danger > external > normal
          let finalZIndex = 1;
          if (isFocusedNode) finalZIndex = 100;
          else if (isFirstDegreeNeighbor && hasFocusFilter) finalZIndex = 50;
          else if (isInHighlightedNamespace) finalZIndex = 80;
          else if (isConnectedToHighlightedNs) finalZIndex = 40;
          else if (hasHighlightedEventType && hasEventTypeHighlight) finalZIndex = 75;
          else if (isConnectedToEventType && hasEventTypeHighlight) finalZIndex = 35;
          else if (enrichment?.riskLevel === 'danger') finalZIndex = 15;
          else if (isExternal) finalZIndex = 0;
          else if (isHighlighted) finalZIndex = 10;
          
          // Border: focus mode > namespace highlight > event type highlight > base
          let finalBorder = borderStyle;
          if (isFocusedNode) {
            finalBorder = '3px solid #6366f1';  // Indigo border for focused
          } else if (isFirstDegreeNeighbor && hasFocusFilter) {
            finalBorder = '2px solid rgba(34, 197, 94, 0.7)';  // Green border for connected
          } else if (isInHighlightedNamespace && hasNamespaceHighlight) {
            finalBorder = `3px solid ${nsColor}`;  // Namespace color border for highlighted
          } else if (isConnectedToHighlightedNs && hasNamespaceHighlight) {
            finalBorder = '2px solid rgba(148, 163, 184, 0.6)';  // Gray border for connected to namespace
          } else if (hasHighlightedEventType && hasEventTypeHighlight) {
            finalBorder = `3px solid ${eventTypeColor}`;  // Cyan border for event type
          } else if (isConnectedToEventType && hasEventTypeHighlight) {
            finalBorder = '2px solid rgba(6, 182, 212, 0.5)';  // Subtle cyan border for connected
          }
          
          newNodes.push({
            ...existingNode,
            data: nodeData,
            style: {
              ...existingNode.style,
              background: isExternal ? `${nsColor}99` : nsColor,
              border: finalBorder,
              width: size * nodeScale,
              height: size * nodeScale,
              opacity: nodeOpacity,
              boxShadow: finalShadow,
              zIndex: finalZIndex,
              fontSize: showNodeIP && nodeIp ? Math.max(7, nodeSize / 6) : Math.max(9, nodeSize / 5),
              borderRadius: nodeBorderRadius,
              transition: 'opacity 0.15s ease-out, box-shadow 0.15s ease-out, transform 0.15s ease-out',
            },
          });
        } else {
          const newIdx = existingCount + newNodeIds.findIndex(n => n.id === node.id);
          const row = Math.floor(newIdx / cols);
          const col = newIdx % cols;
          
          // Use same calculated values for new nodes (same logic as existing nodes)
          const finalShadow = focusShadow ?? namespaceHighlightShadow ?? eventTypeHighlightShadow ?? baseShadow;
          
          // Determine zIndex for new nodes
          let finalZIndex = 1;
          if (isFocusedNode) finalZIndex = 100;
          else if (isFirstDegreeNeighbor && hasFocusFilter) finalZIndex = 50;
          else if (isInHighlightedNamespace) finalZIndex = 80;
          else if (isConnectedToHighlightedNs) finalZIndex = 40;
          else if (hasHighlightedEventType && hasEventTypeHighlight) finalZIndex = 75;
          else if (isConnectedToEventType && hasEventTypeHighlight) finalZIndex = 35;
          else if (enrichment?.riskLevel === 'danger') finalZIndex = 15;
          else if (isExternal) finalZIndex = 0;
          else if (isHighlighted) finalZIndex = 10;
          
          // Border for new nodes
          let finalBorder = borderStyle;
          if (isFocusedNode) {
            finalBorder = '3px solid #6366f1';
          } else if (isFirstDegreeNeighbor && hasFocusFilter) {
            finalBorder = '2px solid rgba(34, 197, 94, 0.7)';
          } else if (isInHighlightedNamespace && hasNamespaceHighlight) {
            finalBorder = `3px solid ${nsColor}`;
          } else if (isConnectedToHighlightedNs && hasNamespaceHighlight) {
            finalBorder = '2px solid rgba(148, 163, 184, 0.6)';
          } else if (hasHighlightedEventType && hasEventTypeHighlight) {
            finalBorder = `3px solid ${eventTypeColor}`;
          } else if (isConnectedToEventType && hasEventTypeHighlight) {
            finalBorder = '2px solid rgba(6, 182, 212, 0.5)';
          }
          
          newNodes.push({
            id: node.id,
            position: { x: col * 180 + 100, y: row * 180 + 100 },
            data: { ...nodeData, isNew: true },
            draggable: true,
            style: {
              background: isExternal ? `${nsColor}99` : nsColor,
              color: isExternal ? 'rgba(255,255,255,0.8)' : '#fff',
              border: finalBorder,
              borderRadius: nodeBorderRadius,
              width: size * nodeScale,
              height: size * nodeScale,
              padding: 0,
              fontSize: showNodeIP && nodeIp ? Math.max(7, nodeSize / 6) : Math.max(9, nodeSize / 5),
              fontWeight: isFocusedNode ? 600 : (isExternal ? 400 : 500),
              boxShadow: finalShadow,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center' as const,
              opacity: nodeOpacity,
              overflow: 'hidden',
              lineHeight: 1.1,
              cursor: 'grab',
              zIndex: finalZIndex,
              transition: 'opacity 0.15s ease-out, box-shadow 0.15s ease-out, transform 0.15s ease-out',
            },
          });
        }
      });
      
      previousNodeIds.current = currentNodeIds;
      return newNodes;
    });
    
    // Note: Auto fitView removed - was blocking user zoom interactions

    // Pre-calculate nodes with highlighted event type for edge processing (O(1) lookup)
    // Use same filtered edges as node processing for consistency (from effective data)
    const edgeRelevantEdges = effectiveGraphData.edges.filter((e: DependencyEdge) => 
      nodeIdSet.has(e.source_id) && nodeIdSet.has(e.target_id)
    );
    
    const edgeNodesWithEventType = new Set<string>();
    const edgeNodesConnectedToEventType = new Set<string>();
    if (highlightedEventType && filteredNodes) {
      // Helper function to check if node has the event type
      const nodeHasEventTypeForEdge = (n: DependencyNode): boolean => {
        const nodeEnrichment = getNodeEnrichment(n.name || '', n.namespace || '');
        if (!nodeEnrichment) return false;
        switch (highlightedEventType) {
          case 'dns_query': return nodeEnrichment.dnsQueryCount > 0;
          case 'sni_event': return nodeEnrichment.tlsConnectionCount > 0;
          case 'process_event': return nodeEnrichment.processEventCount > 0;
          case 'file_event': return nodeEnrichment.fileEventCount > 0;
          case 'security_event': return nodeEnrichment.securityEventCount > 0;
          case 'oom_event': return nodeEnrichment.oomKillCount > 0;
          case 'bind_event': return nodeEnrichment.bindEventCount > 0;
          case 'mount_event': return nodeEnrichment.mountEventCount > 0;
          case 'network_flow': return true;
          default: return true;
        }
      };
      
      // First pass: find nodes with the event type
      filteredNodes.forEach(n => {
        if (nodeHasEventTypeForEdge(n)) {
          edgeNodesWithEventType.add(n.id);
        }
      });
      
      // Second pass: find nodes connected to nodes with this event type
      // Use filtered edges for consistency with node processing
      edgeRelevantEdges.forEach(e => {
        if (edgeNodesWithEventType.has(e.source_id) && !edgeNodesWithEventType.has(e.target_id)) {
          edgeNodesConnectedToEventType.add(e.target_id);
        }
        if (edgeNodesWithEventType.has(e.target_id) && !edgeNodesWithEventType.has(e.source_id)) {
          edgeNodesConnectedToEventType.add(e.source_id);
        }
      });
    }

    // CRITICAL: Filter edges - both source AND target must exist in filtered nodes
    // Double-check with both Set AND Map to prevent orphan edges (edges with missing nodes)
    // FIXED: Use relevantEdges (which respects hasExternalFilter) instead of effectiveGraphData.edges
    // This ensures Public/DataCenter/IP filters properly exclude internal traffic
    const validEdges = relevantEdges
      .filter((edge: DependencyEdge) => {
        // Extra safety: verify nodes exist in filteredNodeMap (for edge rendering)
        const sourceExists = !!filteredNodeMap[edge.source_id];
        const targetExists = !!filteredNodeMap[edge.target_id];
        return sourceExists && targetExists;
      });
    
    // PERFORMANCE: Sort by request_count DESC and limit edges to prevent browser freeze
    // High-traffic edges are more important to visualize
    // 
    // ENTERPRISE-GRADE FLOW LIMIT STRATEGY:
    // ┌─────────────────────────────────────────────────────────────────────┐
    // │ Filter Type          │ Limit    │ Reason                           │
    // ├─────────────────────────────────────────────────────────────────────┤
    // │ Search (3+ chars)    │ BYPASS   │ Find hidden nodes, targeted results│
    // │ Pod filter           │ BYPASS   │ Single pod = few connections      │
    // │ Namespace only       │ ACTIVE   │ Large NS can have 1000s of edges  │
    // │ No filter            │ ACTIVE   │ Full analysis = many edges        │
    // │ "Show All" selected  │ BYPASS   │ User explicitly requested         │
    // │ Focus mode (node)    │ SMART    │ All connected + 300 context edges │
    // └─────────────────────────────────────────────────────────────────────┘
    const totalValidEdges = validEdges.length;
    const isSearchActive = debouncedSearchTerm && debouncedSearchTerm.length >= 3;
    // FIX: Use focusedNodeId instead of selectedPod (selectedPod was never set!)
    const isFocusModeActive = !!focusedNodeId;
    const FOCUS_CONTEXT_LIMIT = 300; // Background context edges in focus mode
    
    // Calculate display edges based on mode
    const displayEdges = (() => {
      // ERROR FILTER MODE: Bypass limit, show only error edges
      // This ensures all error edges are visible regardless of smartEdgeLimit
      if (filterErrorsOnly) {
        const errorEdges = validEdges.filter((e: DependencyEdge) => (e.error_count || 0) > 0);
        debugLog(`[ERROR_FILTER] Showing ${errorEdges.length} error edges (bypassing limit)`);
        return errorEdges;
      }
      
      // Show All: no limit (user selected 'Max')
      if (smartEdgeLimit === Infinity) {
        return validEdges;
      }
      
      // Search mode: show all matching (already filtered by search)
      if (isSearchActive) {
        return validEdges;
      }
      
      // Focus mode (node clicked): Smart context-aware limit
      // - All edges connected to focused node (no limit)
      // - Plus top 300 context edges (for background visibility)
      if (isFocusModeActive) {
        const connectedEdges = validEdges.filter(e => 
          e.source_id === focusedNodeId || e.target_id === focusedNodeId
        );
        const otherEdges = validEdges
          .filter(e => e.source_id !== focusedNodeId && e.target_id !== focusedNodeId)
          .sort((a, b) => (b.request_count || 0) - (a.request_count || 0))
          .slice(0, FOCUS_CONTEXT_LIMIT);
        
        debugLog(`[FOCUS] Node '${focusedNodeId}': ${connectedEdges.length} connected + ${otherEdges.length} context = ${connectedEdges.length + otherEdges.length} edges (was ${totalValidEdges})`);
        return [...connectedEdges, ...otherEdges];
      }
      
      // Normal mode: apply smartEdgeLimit (auto-adjusted based on analysis size)
      if (totalValidEdges > smartEdgeLimit) {
        const context = selectedNamespaces.length > 0 ? `ns:${selectedNamespaces.join(',')}` : 'all';
        debugLog(`[PERF] Limiting edges: showing ${smartEdgeLimit} of ${totalValidEdges} (${context}, sorted by traffic)`);
        return [...validEdges]
          .sort((a, b) => (b.request_count || 0) - (a.request_count || 0))
          .slice(0, smartEdgeLimit);
      }
      
      return validEdges;
    })();
    
    // ============================================
    // ERROR FILTER: When active, show only edges with errors
    // This filter is applied AFTER all other filters (namespace, search, focus)
    // Connected nodes are automatically shown via edge connections
    // ============================================
    const filteredDisplayEdges = filterErrorsOnly 
      ? displayEdges.filter((edge: DependencyEdge) => (edge.error_count || 0) > 0)
      : displayEdges;
    
    const rfEdges: Edge[] = filteredDisplayEdges.map((edge: DependencyEdge) => {
        const flowCount = edge.request_count || 0;
        const errorCount = (edge as any).error_count || 0;
        const retransmitCount = (edge as any).retransmit_count || 0;
        const lastErrorType = (edge as any).last_error_type || '';
        const hasErrors = errorCount > 0;
        
        // Determine if error is critical or warning based on error type
        const criticalPatterns = ['RESET', 'REFUSED', 'TIMEOUT', 'UNREACHABLE', 'ERROR', 'SOCKET'];
        const isCritical = hasErrors && lastErrorType && criticalPatterns.some(p => lastErrorType.toUpperCase().includes(p));
        const isWarning = hasErrors && !isCritical; // Retransmits are warnings
        
        // Check if edge is connected to highlighted namespace/event type
        // PERFORMANCE: O(1) lookup instead of O(n) find() - critical for large graphs
        const sourceNode = filteredNodeMap[edge.source_id];
        const targetNode = filteredNodeMap[edge.target_id];
        
        // ============================================
        // NAMESPACE-CENTRIC: Check if cross-namespace edge (multi-namespace support)
        // ============================================
        const selectedNsSet = new Set(selectedNamespaces);
        const isCrossNamespace = hasNamespaceFilter && (
          !selectedNsSet.has(sourceNode?.namespace || '') || 
          !selectedNsSet.has(targetNode?.namespace || '')
        );
        const isExternalEdge = isExternalNode(edge.source_id) || isExternalNode(edge.target_id);
        
        // Get enrichment for source and target nodes
        const sourceEnrichment = sourceNode ? getNodeEnrichment(sourceNode.name || '', sourceNode.namespace || '') : null;
        const targetEnrichment = targetNode ? getNodeEnrichment(targetNode.name || '', targetNode.namespace || '') : null;
        
        // Check namespace filter - 3-level hierarchy for edges
        const sourceInHighlightedNs = sourceNode?.namespace === highlightedNamespace;
        const targetInHighlightedNs = targetNode?.namespace === highlightedNamespace;
        const bothEndpointsInHighlightedNs = sourceInHighlightedNs && targetInHighlightedNs;
        const oneEndpointInHighlightedNs = sourceInHighlightedNs || targetInHighlightedNs;
        const matchesNamespaceFilter = !highlightedNamespace || oneEndpointInHighlightedNs;
        
        // Check event type filter - 3-level hierarchy for edges (like namespace)
        // Use pre-calculated Sets for O(1) lookup
        const sourceHasEventType = edgeNodesWithEventType.has(edge.source_id);
        const targetHasEventType = edgeNodesWithEventType.has(edge.target_id);
        const bothEndpointsHaveEventType = sourceHasEventType && targetHasEventType;
        const oneEndpointHasEventType = sourceHasEventType || targetHasEventType;
        // Also check if connected to nodes with event type (2nd level)
        const sourceConnectedToEventType = edgeNodesConnectedToEventType.has(edge.source_id);
        const targetConnectedToEventType = edgeNodesConnectedToEventType.has(edge.target_id);
        const edgeConnectedToEventTypeNode = oneEndpointHasEventType || sourceConnectedToEventType || targetConnectedToEventType;
        const matchesEventTypeFilter = !highlightedEventType || edgeConnectedToEventTypeNode;
        
        // Check if edge is connected to focused node
        const isConnectedToFocused = focusedNodeId && (
          edge.source_id === focusedNodeId || edge.target_id === focusedNodeId
        );
        
        const isEdgeHighlighted = matchesNamespaceFilter && matchesEventTypeFilter;
        const hasAnyFilter = highlightedNamespace || highlightedEventType;
        const hasFocusFilter = !!focusedNodeId;
        const hasNamespaceHighlight = !!highlightedNamespace;
        const hasEventTypeHighlight = !!highlightedEventType;
        
        // Opacity: 3-level hierarchy for focus mode, namespace highlight, AND event type highlight
        let edgeOpacity = 1;
        if (hasFocusFilter) {
          edgeOpacity = isConnectedToFocused ? 1 : 0.06;
        } else if (hasNamespaceHighlight) {
          // 3-level edge hierarchy for namespace highlight
          if (bothEndpointsInHighlightedNs) {
            edgeOpacity = 1;  // Both endpoints in namespace: fully visible
          } else if (oneEndpointInHighlightedNs) {
            edgeOpacity = 0.6;  // One endpoint in namespace: visible but dimmed
          } else {
            edgeOpacity = 0.25;  // Neither endpoint: faded but readable
          }
        } else if (hasEventTypeHighlight) {
          // 3-level edge hierarchy for event type highlight (like namespace)
          if (bothEndpointsHaveEventType) {
            edgeOpacity = 1;  // Both endpoints have event type: fully visible
          } else if (oneEndpointHasEventType) {
            edgeOpacity = 0.7;  // One endpoint has event type: visible but dimmed
          } else if (sourceConnectedToEventType || targetConnectedToEventType) {
            edgeOpacity = 0.4;  // Connected to node with event type: more dimmed
          } else {
            edgeOpacity = 0.15;  // Neither endpoint: faded but still visible
          }
        }
        
        // Focus mode edge color - special highlight for connected edges
        const focusedEdgeColor = isConnectedToFocused ? '#6366f1' : null;  // Indigo for connected edges
        
        // Check if this edge uses TLS (source pod has TLS connection to target)
        const targetIp = (targetNode as any)?.ip || '';
        const hasTls = hasTlsConnection(
          sourceNode?.name || '', 
          sourceNode?.namespace || '', 
          targetIp
        );
        
        // Color based on TLS status - use app_protocol (L7) if available
        const effectiveProtocol = getEffectiveProtocol(edge);
        const baseEdgeColor = getProtocolColor(effectiveProtocol);
        const edgeColor = hasTls ? '#52c41a' : baseEdgeColor; // Green for TLS
        
        // Build edge label based on toggles with error count
        const labelParts: string[] = [];
        
        // Add TLS indicator
        if (showTlsIndicators && hasTls) {
          labelParts.push('●');
        }
        
        if (showProtocolLabel) {
          labelParts.push(effectiveProtocol);
        }
        if (showFlowLabel && flowCount > 0) {
          let flowPart = `${flowCount} flow${flowCount > 1 ? 's' : ''}`;
          if (hasErrors) {
            // Show error count with indicator: critical (!) or warning (~)
            const errorIndicator = isCritical ? '!' : '~';
            flowPart += ` (${errorIndicator}${errorCount})`;
          }
          labelParts.push(flowPart);
        }
        const edgeLabel = labelParts.join(' ') || undefined;
        
        // Label styling - Critical: red, Warning: orange
        const labelColor = isCritical ? '#ef4444' : (isWarning ? '#f59e0b' : (hasTls ? '#389e0d' : '#475569'));
        const labelBgColor = isCritical 
          ? 'rgba(254, 226, 226, 0.85)'  // Light red for critical
          : (isWarning 
            ? 'rgba(255, 237, 213, 0.85)'  // Light orange for warning
            : (hasTls ? 'rgba(220, 252, 231, 0.85)' : 'rgba(255, 255, 255, 0.75)'));
        const labelBorderColor = isCritical 
          ? 'rgba(252, 165, 165, 0.6)'  // Red border for critical
          : (isWarning 
            ? 'rgba(253, 186, 116, 0.6)'  // Orange border for warning
            : (hasTls ? 'rgba(134, 239, 172, 0.6)' : 'rgba(226, 232, 240, 0.6)'));
        
        // TLS edges get special styling - thicker, animated, with glow
        // External/cross-namespace edges are thinner and dashed
        const baseStrokeWidth = isExternalEdge 
          ? Math.min(Math.max(flowCount / 15, 1), 3)  // Thinner for external
          : (hasTls 
            ? Math.min(Math.max(flowCount / 10, 3), 7) 
            : Math.min(Math.max(flowCount / 10, 1.5), 5));
        
        // Focus mode makes connected edges thicker
        const focusedStrokeWidth = isConnectedToFocused 
          ? Math.max(baseStrokeWidth * 1.8, 4)  // Thicker for connected edges in focus mode
          : baseStrokeWidth;
        
        // Namespace highlight stroke width - 3-level hierarchy
        let namespaceHighlightStrokeWidth = baseStrokeWidth;
        if (hasNamespaceHighlight) {
          if (bothEndpointsInHighlightedNs) {
            namespaceHighlightStrokeWidth = Math.max(baseStrokeWidth * 1.6, 3);  // Both endpoints: thick
          } else if (oneEndpointInHighlightedNs) {
            namespaceHighlightStrokeWidth = Math.max(baseStrokeWidth * 1.2, 2);  // One endpoint: medium
          } else {
            namespaceHighlightStrokeWidth = Math.max(baseStrokeWidth * 0.6, 1);  // Neither: thin
          }
        }
        
        // Event type highlight stroke width - 3-level hierarchy (like namespace)
        let eventTypeHighlightStrokeWidth = baseStrokeWidth;
        if (hasEventTypeHighlight) {
          if (bothEndpointsHaveEventType) {
            eventTypeHighlightStrokeWidth = Math.max(baseStrokeWidth * 1.6, 3);  // Both endpoints: thick
          } else if (oneEndpointHasEventType) {
            eventTypeHighlightStrokeWidth = Math.max(baseStrokeWidth * 1.3, 2.5);  // One endpoint: medium
          } else if (sourceConnectedToEventType || targetConnectedToEventType) {
            eventTypeHighlightStrokeWidth = Math.max(baseStrokeWidth * 1.0, 1.5);  // Connected: normal
          } else {
            eventTypeHighlightStrokeWidth = Math.max(baseStrokeWidth * 0.5, 1);  // Neither: thin
          }
        }
        
        const highlightStrokeWidth = hasFocusFilter
          ? focusedStrokeWidth
          : (hasNamespaceHighlight
              ? namespaceHighlightStrokeWidth
              : (hasEventTypeHighlight
                  ? eventTypeHighlightStrokeWidth
                  : baseStrokeWidth));
        
        // External edges use muted color, unless in focus mode with connection
        // Error edges: Critical = red (#ef4444), Warning = orange (#f59e0b)
        const errorEdgeColor = isCritical ? '#ef4444' : (isWarning ? '#f59e0b' : null);
        const finalEdgeColor = focusedEdgeColor ?? (isExternalEdge 
          ? '#94a3b8'  // Slate gray for external connections
          : (errorEdgeColor ?? edgeColor));
        
        return {
          id: `${edge.source_id}-${edge.target_id}`,
          source: edge.source_id,
          target: edge.target_id,
          // Store original edge data for header stats calculation and CSV export
          data: {
            request_count: flowCount,
            error_count: errorCount,
            protocol: edge.protocol,
            app_protocol: edge.app_protocol,
            port: edge.port,
            retransmit_count: edge.retransmit_count,
            last_error_type: edge.last_error_type,
          },
          animated: !isAnimationPaused && !isExternalEdge && (isConnectedToFocused || isEdgeHighlighted || hasTls),
          style: { 
            stroke: finalEdgeColor, 
            strokeWidth: highlightStrokeWidth,
            strokeDasharray: isExternalEdge ? '5,5' : undefined,  // Dashed for external
            opacity: isExternalEdge ? 0.5 : edgeOpacity,
            filter: isConnectedToFocused 
              ? 'drop-shadow(0 0 6px rgba(99, 102, 241, 0.7))'  // Indigo glow for focused edges
              : (hasNamespaceHighlight && bothEndpointsInHighlightedNs
                  ? 'drop-shadow(0 0 4px rgba(99, 102, 241, 0.5))'  // Subtle glow for namespace highlight
                  : (hasEventTypeHighlight && bothEndpointsHaveEventType
                      ? 'drop-shadow(0 0 4px rgba(6, 182, 212, 0.6))'  // Cyan glow for event type highlight
                      : (hasTls && !isExternalEdge ? 'drop-shadow(0 0 3px rgba(82, 196, 26, 0.6))' : undefined))),
            transition: 'opacity 0.15s ease-out, stroke-width 0.15s ease-out',
          },
          markerEnd: {
            type: 'arrowclosed' as const,
            color: finalEdgeColor,
            width: isExternalEdge ? 12 : (hasTls ? 18 : 15),
            height: isExternalEdge ? 12 : (hasTls ? 18 : 15),
          },
          // Label visibility: Only show label for highlighted/focused edges
          // - Focus mode: Only show label for edges connected to focused node
          // - Namespace highlight: Only show label for edges with at least one endpoint in namespace
          // - Event type highlight: Only show label for edges with at least one endpoint having event type
          // - No filter: Show all labels
          label: (hasFocusFilter 
            ? (isConnectedToFocused ? edgeLabel : undefined)
            : (hasNamespaceHighlight 
                ? (oneEndpointInHighlightedNs ? edgeLabel : undefined)
                : (hasEventTypeHighlight
                    ? (oneEndpointHasEventType ? edgeLabel : undefined)
                    : edgeLabel))),
          labelStyle: { 
            fontSize: hasTls ? 11 : 10, 
            fontWeight: hasTls ? 700 : 600,
            fill: labelColor,
            // Dim label for connected-but-not-primary edges
            opacity: (hasFocusFilter && !isConnectedToFocused) ? 0 
              : (hasNamespaceHighlight && !bothEndpointsInHighlightedNs && oneEndpointInHighlightedNs) ? 0.7 
              : (hasEventTypeHighlight && !bothEndpointsHaveEventType && oneEndpointHasEventType) ? 0.7
              : 1,
          },
          labelBgStyle: { 
            fill: labelBgColor,
            stroke: labelBorderColor,
            strokeWidth: hasTls ? 2 : 1,
            rx: 6,
            ry: 6,
            // Dim label background for connected-but-not-primary edges
            opacity: (hasFocusFilter && !isConnectedToFocused) ? 0 
              : (hasNamespaceHighlight && !bothEndpointsInHighlightedNs && oneEndpointInHighlightedNs) ? 0.7 
              : (hasEventTypeHighlight && !bothEndpointsHaveEventType && oneEndpointHasEventType) ? 0.7
              : 1,
          },
        };
      });

    setEdges(rfEdges);
  // NOTE: focusedNodeId MUST be in deps for edge filtering to work correctly
  // Edge filtering uses focusedNodeId to determine which edges to show (connected + 300 context)
  // NOTE: Using debouncedSearchTerm (not globalSearchTerm) prevents filtering on every keystroke
  }, [effectiveGraphData, aggregatedView, selectedClusterFilter, debouncedSearchTerm, selectedPod, selectedNamespaces, layout, nodeSize, showInternalTraffic, hideSystemNamespaces, focusPublicOnly, focusDataCenterOnly, focusIPOnly, showProtocolLabel, showFlowLabel, showNodeIP, highlightedNamespace, highlightedEventType, focusedNodeId, isAnimationPaused, setNodes, setEdges, hasTlsConnection, getNodeEnrichment, showEnrichmentBadges, enrichmentMap, nodeIdMap, resolveIpToPod, ipToNodeLookup, nodeMatchesSearch, smartEdgeLimit, filterErrorsOnly]);

  // ============================================
  // PERFORMANCE OPTIMIZATION: Memoized drawer computed values
  // Prevents expensive calculations on every render
  // Only recalculates when selectedNode changes
  // ============================================
  const drawerComputedValues = useMemo(() => {
    if (!selectedNode) return null;
    
    const nodeName = selectedNode.name || '';
    const { resolvedName, resolvedNode, isResolved } = resolveIpToPod(nodeName);
    const displayNode = resolvedNode || selectedNode;
    const displayNamespace = displayNode?.namespace || selectedNode.namespace || '';
    const displayName = isResolved ? resolvedName : nodeName;
    const isNodePublicIP = nodeName ? isPublicIP(nodeName) : false;
    const knownSvc = isNodePublicIP ? detectKnownService(nodeName) : null;
    const nodeEnrichment = getNodeEnrichment(displayName, displayNamespace);
    
    // Check if external node (multi-namespace support)
    const hasNsFilter = selectedNamespaces.length > 0;
    const selectedNsSet = new Set(selectedNamespaces);
    const isExternalSelectedNode = hasNsFilter && !selectedNsSet.has(displayNamespace);
    
    return {
      nodeName,
      resolvedName,
      resolvedNode,
      isResolved,
      displayNode,
      displayNamespace,
      displayName,
      isNodePublicIP,
      knownSvc,
      nodeEnrichment,
      hasNsFilter,
      isExternalSelectedNode,
    };
  }, [selectedNode, selectedNamespaces, resolveIpToPod, getNodeEnrichment]);

  const onConnect: OnConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // Fullscreen handlers
  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    
    if (!isFullscreen) {
      containerRef.current.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  }, [isFullscreen]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      const isNowFullscreen = !!document.fullscreenElement;
      setIsFullscreen(isNowFullscreen);
      
      // When exiting fullscreen (ESC or button), restore header visibility
      if (!isNowFullscreen) {
        setShowHeader(true);
        setShowStats(true);
      }
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);
  
  // ESC key handler: first close drawer, then exit fullscreen
  useEffect(() => {
    const handleEscKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Don't interfere with default fullscreen exit if no drawer is open
        if (drawerVisible) {
          e.preventDefault();
          e.stopPropagation();
          setDrawerVisible(false);
          setSelectedNode(null);
          setFocusedNodeId(null);
          setDrawerTab('overview');
        }
        // If drawer is not visible but fullscreen is active, let browser handle ESC to exit fullscreen
      }
    };
    
    document.addEventListener('keydown', handleEscKey, true);
    return () => document.removeEventListener('keydown', handleEscKey, true);
  }, [drawerVisible]);

  const handleFitView = useCallback(() => {
    reactFlowInstance.current?.fitView({ padding: 0.2 });
  }, []);

  // Auto fit view when layout changes to ensure all nodes are visible
  useEffect(() => {
    if (reactFlowInstance.current && nodes.length > 0) {
      // Small delay to allow node positions to update before fitting
      setTimeout(() => {
        reactFlowInstance.current?.fitView({ padding: 0.2, duration: 150 });
      }, 50);
    }
  }, [layout]);

  // Node click handler - also sets focus for blur effect
  const handleNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    const originalNode = node.data?.originalNode as DependencyNode;
    const isAggregatedNode = node.data?.isAggregated || false;
    
    if (originalNode) {
      // For aggregated nodes, enrich originalNode with aggregation metadata
      // This allows drawer to show aggregated workload info
      if (isAggregatedNode) {
        const enrichedNode = {
          ...originalNode,
          _isAggregated: true,
          _originalNodes: node.data?.originalNodes,
          _podCount: node.data?.podCount,
          _podsByCluster: node.data?.podsByCluster,
          _clusterIds: node.data?.clusterIds,
          _clusterCount: node.data?.clusterCount,
        };
        setSelectedNode(enrichedNode as DependencyNode);
        // Use the aggregated node's ID for focus (aggregation key)
        setFocusedNodeId(node.id);
      } else {
        setSelectedNode(originalNode);
        setFocusedNodeId(originalNode.id);
      }
      setDrawerVisible(true);
    }
  }, []);

  // AGGRESSIVE FLOATING EDGE FIX:
  // React key changes alone don't reliably clear ReactFlow's internal edge cache.
  // Solution: Temporarily unmount ReactFlow when filters change, then remount.
  // This forces complete DOM cleanup and eliminates floating edges.
  //
  // Trade-off: Brief visual flash when filter changes, but no floating edges.
  // NOTE: highlightedNamespace is NOT included because it's only visual (opacity change),
  // not a data filter. Including it would cause unnecessary remounts.
  // NOTE: layout IS included because layout changes during live polling can cause floating edges
  // when ReactFlow's internal cache doesn't sync with new node positions.
  // NOTE: aggregatedView is included to force remount when switching between pod and workload view
  // Multi-namespace support: serialize namespace array for filterKey
  const namespacesKey = selectedNamespaces.length > 0 ? selectedNamespaces.sort().join(',') : 'all';
  const filterKey = `namespaces:${namespacesKey}-${debouncedSearchTerm || 'none'}-${selectedPod || 'none'}-${focusPublicOnly}-${focusDataCenterOnly}-${focusIPOnly}-${showInternalTraffic}-${layout}-${aggregatedView}-clusters:${selectedClusterFilter.join(',') || 'all'}`;
  const providerKey = `provider-${selectedAnalysisId || 'none'}`;
  
  // Track filter changes and force ReactFlow remount
  const [isReactFlowMounted, setIsReactFlowMounted] = useState(true);
  const prevFilterKeyRef = useRef(filterKey);
  const rafIdRef = useRef<number | null>(null);
  
  useEffect(() => {
    if (prevFilterKeyRef.current !== filterKey) {
      // Cancel any pending remount to prevent race conditions
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
      
      // Unmount ReactFlow
      setIsReactFlowMounted(false);
      
      // Remount after TWO frames for reliable DOM cleanup
      // Single frame sometimes isn't enough for React to fully unmount
      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = requestAnimationFrame(() => {
          setIsReactFlowMounted(true);
          rafIdRef.current = null;
        });
      });
      
      prevFilterKeyRef.current = filterKey;
    }
    
    // Cleanup on component unmount to prevent memory leaks
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
      }
    };
  }, [filterKey]);
  
  // ConfigProvider getPopupContainer for fullscreen mode - ensures all popups render inside fullscreen container
  const getPopupContainer = useCallback(() => {
    return isFullscreen && containerRef.current ? containerRef.current : document.body;
  }, [isFullscreen]);

  return (
    <ConfigProvider getPopupContainer={getPopupContainer}>
    <ReactFlowProvider key={providerKey}>
      <style>{customStyles}</style>
      <div 
        ref={containerRef}
        style={{ 
          height: 'calc(100vh - 64px)', 
          display: 'flex', 
          flexDirection: 'column',
          overflow: 'hidden',
          padding: isFullscreen ? 8 : 16,
          gap: 8,
          background: isFullscreen ? (isDark ? '#1a1a1a' : '#f0f0f0') : undefined
        }}
      >
        {/* Header Toggle for Fullscreen */}
      {isFullscreen && !showHeader && (
        <div style={{ position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)', zIndex: 20 }}>
          <Button size="small" icon={<DownOutlined />} onClick={() => setShowHeader(true)}>Show Header</Button>
        </div>
      )}

      {/* Header with Filters */}
      {showHeader && (
        <div style={{ 
          padding: '8px 16px', 
          background: isDark ? token.colorBgContainer : '#fff',
          borderRadius: '8px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: isDark ? '0 1px 3px rgba(0,0,0,0.3)' : '0 1px 3px rgba(0,0,0,0.1)',
          flexShrink: 0,
          border: `1px solid ${isDark ? token.colorBorderSecondary : '#f0f0f0'}`,
          gap: 12,
          flexWrap: 'nowrap',
          minHeight: 48
        }}>
          {/* Left side - Title (fixed width, no shrink) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, whiteSpace: 'nowrap' }}>
            <GlobalOutlined style={{ color: '#1890ff', fontSize: 18 }} />
            <Title level={5} style={{ margin: 0, fontWeight: 600 }}>Map</Title>
            {/* Show status badge based on analysis state */}
            {statusBadgeInfo && (
              <Tooltip title={statusBadgeInfo.tooltip} mouseEnterDelay={0.5}>
                <Badge 
                  status={statusBadgeInfo.badgeStatus} 
                  text={<Text type="secondary" style={{ fontSize: 10 }}>{statusBadgeInfo.text}</Text>} 
                />
              </Tooltip>
            )}
          </div>
          
          {/* Right side - Filters (scrollable if needed) */}
          <Space size="small" style={{ flexShrink: 1, flexWrap: 'nowrap', overflow: 'hidden' }}>
            <Select
              placeholder="Select Analysis"
              style={{ width: 240, minWidth: 180, maxWidth: 280 }}
              allowClear
              showSearch
              getPopupContainer={() => isFullscreen && containerRef.current ? containerRef.current : document.body}
              filterOption={(input, option) => {
                // Search by analysis name
                const analysisName = option?.children?.toString().toLowerCase() || '';
                return analysisName.includes(input.toLowerCase());
              }}
              value={selectedAnalysisId}
              onChange={(value) => {
                const isNewAnalysis = value !== selectedAnalysisId;
                setSelectedAnalysisId(value);
                
                if (value) {
                  // Find cluster_id directly - check both availableAnalyses and full analyses list
                  // This handles cases where cache might not be updated yet
                  let analysis = availableAnalyses.find((a: Analysis) => a.id === value);
                  if (!analysis) {
                    // Fallback to full analyses list (might include new analyses not yet in filtered list)
                    analysis = (Array.isArray(analyses) ? analyses : []).find((a: Analysis) => a.id === value);
                  }
                  if (analysis) {
                    setSelectedClusterId(analysis.cluster_id);
                  } else {
                    // Last resort: clear and let useEffect handle it when analyses refresh
                    console.warn('[Map] Analysis not found in list, waiting for useEffect:', value);
                    setSelectedClusterId(undefined);
                  }
                  
                  // Reset namespace/pod when switching to a different analysis
                  // Different analysis = different scope, old namespace selection is invalid
                  if (isNewAnalysis) {
                    setSelectedNamespaces([]);
                    setSelectedPod(undefined);
                    // Reset namespace cache - will be populated with new analysis data
                    setNamespaceCache({ analysisId: null, namespaces: [] });
                  }
                } else {
                  // Cleared - reset all related filters
                  setSelectedClusterId(undefined);
                  setSelectedNamespaces([]);
                  setSelectedPod(undefined);
                  // Clear namespace cache when analysis is cleared
                  setNamespaceCache({ analysisId: null, namespaces: [] });
                }
              }}
              loading={isAnalysesLoading}
              listHeight={320}
              dropdownStyle={{ maxHeight: 400 }}
            >
              {availableAnalyses.map((analysis: Analysis) => {
                // Find cluster name for display
                const cluster = clusters.find((c: any) => c.id === analysis.cluster_id);
                const clusterName = cluster?.name || `Cluster ${analysis.cluster_id}`;
                const isMulti = analysis.is_multi_cluster && analysis.cluster_ids?.length > 1;
                const clusterCount = analysis.cluster_ids?.length || 1;
                return (
                  <Option key={analysis.id} value={analysis.id}>
                    <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                    <span style={{ marginLeft: 4 }}>{analysis.name}</span>
                    {isMulti ? (
                      <Tag color="blue" style={{ marginLeft: 8, fontSize: 10 }}>
                        <GlobalOutlined /> {clusterCount} Clusters
                      </Tag>
                    ) : (
                      <span style={{ marginLeft: 8, color: isDark ? '#a0a0a0' : '#8c8c8c', fontSize: 11 }}>({clusterName})</span>
                    )}
                  </Option>
                );
              })}
            </Select>
            
            {/* Multi-cluster indicator - compact version, full list in tooltip */}
            {isMultiClusterAnalysis && analysisClusterIds.length > 1 && (
              <Tooltip title={`${analysisClusterIds.length} clusters: ${analysisClusterIds.map(id => clusterInfoMap.get(id)?.name || `Cluster ${id}`).join(', ')}. Use namespace filter to narrow down.`} mouseEnterDelay={0.5}>
                <Tag 
                  color="geekblue" 
                  style={{ 
                    padding: '2px 8px', 
                    fontSize: 11,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    flexShrink: 0
                  }}
                >
                  <ClusterOutlined />
                  {analysisClusterIds.length} Clusters
                </Tag>
              </Tooltip>
            )}
            
            <Tooltip title={selectedNamespaces.length > 0 ? `Filtering: ${selectedNamespaces.join(', ')}` : "Filter by namespace(s) - multi-select enabled"} mouseEnterDelay={0.5}>
              <Select
                mode="multiple"
                placeholder="Namespaces"
                style={{ width: 200, minWidth: 140, maxWidth: 280 }}
                allowClear
                showSearch
                maxTagCount={2}
                maxTagTextLength={15}
                maxTagPlaceholder={(omittedValues) => `+${omittedValues.length} more`}
                filterOption={(input, option) => {
                  // Search both namespace and cluster name
                  const nsItem = namespacesWithCluster.find(item => item.namespace === option?.value);
                  const searchText = `${nsItem?.namespace || ''} ${nsItem?.clusterName || ''}`.toLowerCase();
                  return searchText.includes(input.toLowerCase());
                }}
                listHeight={320}
                dropdownStyle={{ maxHeight: 400 }}
                getPopupContainer={() => isFullscreen && containerRef.current ? containerRef.current : document.body}
                value={selectedNamespaces}
                onChange={(values) => {
                  debugLog('[NAMESPACE_SELECT] Multi-select onChange:', { 
                    newValues: values, 
                    previousValues: selectedNamespaces,
                    analysisId: selectedAnalysisId
                  });
                  setSelectedNamespaces(values || []);
                  // Clear pod filter when namespace changes
                  if (values?.length !== selectedNamespaces.length) {
                    setSelectedPod(undefined);
                  }
                }}
                size="small"
                disabled={!selectedAnalysisId}
                optionLabelProp="label"
              >
                {(() => {
                  // Group namespaces by name to check for duplicates across clusters
                  const nsGroups: Record<string, NamespaceClusterInfo[]> = {};
                  namespacesWithCluster.forEach(item => {
                    if (!nsGroups[item.namespace]) {
                      nsGroups[item.namespace] = [];
                    }
                    nsGroups[item.namespace].push(item);
                  });
                  
                  // Check if we need to show cluster info (when same namespace exists in multiple clusters)
                  const showClusterInfo = isMultiClusterAnalysis && 
                    Object.values(nsGroups).some(group => group.length > 1);
                  
                  return namespaces.map((ns) => {
                    const nsItems = nsGroups[ns] || [];
                    const clusterNames = nsItems.map(item => item.clusterName).join(', ');
                    const colorInfo = nsItems.length > 0 && nsItems[0].clusterId
                      ? clusterColorPalette.getColor(nsItems[0].clusterId, analysisClusterIds)
                      : null;
                    
                    return (
                      <Option key={ns} value={ns} label={ns}>
                        <Tooltip title={showClusterInfo ? `${ns} (${clusterNames})` : ns} placement="right" mouseEnterDelay={0.5}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                            <div style={{ display: 'flex', alignItems: 'center', minWidth: 0, flex: 1 }}>
                              <span style={{ 
                                display: 'inline-block', 
                                width: 8, 
                                height: 8, 
                                borderRadius: '50%', 
                                background: colorInfo?.border || getNamespaceColor(ns), 
                                marginRight: 6, 
                                flexShrink: 0 
                              }} />
                              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ns}</span>
                            </div>
                            {showClusterInfo && nsItems.length > 1 && (
                              <Tag 
                                color="default" 
                                style={{ fontSize: 9, padding: '0 4px', marginLeft: 4, flexShrink: 0 }}
                              >
                                {nsItems.length} clusters
                              </Tag>
                            )}
                          </div>
                        </Tooltip>
                      </Option>
                    );
                  });
                })()}
              </Select>
            </Tooltip>
            
            <Tooltip title={aggregatedView ? "Pod filter disabled in Workload View. Switch to normal view to filter by pod." : "Filter by specific pod"} mouseEnterDelay={0.5}>
              <Select
                placeholder={aggregatedView ? "Workload" : "Pod"}
                style={{ width: 140 }}
                allowClear
                showSearch
                filterOption={(input, option) =>
                  (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
                }
                value={selectedPod}
                onChange={setSelectedPod}
                size="small"
                disabled={!selectedAnalysisId || aggregatedView}
                getPopupContainer={() => isFullscreen && containerRef.current ? containerRef.current : document.body}
              >
                {pods.map((pod: string) => (
                  <Option key={pod} value={pod}>{pod}</Option>
                ))}
              </Select>
            </Tooltip>
            
            <Tooltip title="Search by name, IP, namespace, labels, owner, image, or any metadata" mouseEnterDelay={0.5}>
              <Input
                placeholder="Search..."
                prefix={<SearchOutlined style={{ color: isDark ? '#6a6a8a' : '#94a3b8' }} />}
                value={globalSearchTerm}
                onChange={(e) => setGlobalSearchTerm(e.target.value)}
                style={{ width: 140, minWidth: 100 }}
                size="small"
                allowClear
              />
            </Tooltip>
            
            {/* Action buttons - always visible, no shrink */}
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              <Button icon={<ReloadOutlined />} onClick={() => refetchGraph()} loading={isGraphLoading} size="small" type="primary" />
              
              {/* Export dropdown */}
              <Dropdown 
                menu={{ items: exportMenuItems }} 
                trigger={['click']}
                disabled={nodes.length === 0}
              >
                <Tooltip title={nodes.length > 0 ? `Export ${nodes.length} nodes, ${edges.length} connections` : 'No data to export'} mouseEnterDelay={0.5}>
                  <Button size="small" icon={<DownloadOutlined />}>
                    Export
                  </Button>
                </Tooltip>
              </Dropdown>
              
              <Button icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />} onClick={toggleFullscreen} size="small" />
              {isFullscreen && (
                <Button icon={<UpOutlined />} onClick={() => setShowHeader(false)} size="small" />
              )}
            </div>
          </Space>
        </div>
      )}
      
      {/* Stats Row - Shows filtered values based on current view */}
      {/* Uses animated counters for smooth number transitions like Dashboard */}
      {showStats && showHeader && (
        <Row gutter={8} style={{ flexShrink: 0 }}>
          <Col flex="1">
            <Tooltip title="Unique connections (different source, destination, port combinations)" mouseEnterDelay={0.5}>
              <Card size="small" bordered={false} bodyStyle={{ padding: '6px 10px' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Connections</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ApartmentOutlined style={{ color: '#6366f1', fontSize: 16 }} />
                    <span style={{ fontSize: 20, fontWeight: 600 }}>
                      {!selectedAnalysisId ? '-' : animatedConnections.toLocaleString()}
                    </span>
                  </div>
                </div>
              </Card>
            </Tooltip>
          </Col>
          <Col flex="1">
            <Tooltip title="Visible workloads in current view" mouseEnterDelay={0.5}>
              <Card size="small" bordered={false} bodyStyle={{ padding: '6px 10px' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Workloads</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <DeploymentUnitOutlined style={{ color: '#8b5cf6', fontSize: 16 }} />
                    <span style={{ fontSize: 20, fontWeight: 600 }}>
                      {!selectedAnalysisId ? '-' : animatedWorkloads.toLocaleString()}
                    </span>
                  </div>
                </div>
              </Card>
            </Tooltip>
          </Col>
          <Col flex="1">
            <Tooltip 
              title="Total request count for displayed connections (updates with filters)"
              mouseEnterDelay={0.5}
            >
              <Card size="small" bordered={false} bodyStyle={{ padding: '6px 10px' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Requests</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ThunderboltOutlined style={{ color: '#06b6d4', fontSize: 16 }} />
                    <span style={{ fontSize: 20, fontWeight: 600 }}>
                      {!selectedAnalysisId ? '-' : animatedRequests.toLocaleString()}
                    </span>
                  </div>
                </div>
              </Card>
            </Tooltip>
          </Col>
          <Col flex="1">
            {/* Error card - uses pre-calculated values from useMemo with Critical/Warning split */}
            <Tooltip 
              title={
                <div style={{ minWidth: 220, fontFamily: 'inherit' }}>
                  {/* Header with health status */}
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: 10, 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    paddingBottom: 8,
                    borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`
                  }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: isDark ? 'rgba(255,255,255,0.85)' : 'rgba(0,0,0,0.85)' }}>
                      {errorHealthStatus === 'healthy' || errorHealthStatus === 'good' ? (
                        <CheckCircleOutlined style={{ color: '#10b981' }} />
                      ) : errorHealthStatus === 'warning' ? (
                        <ExclamationCircleOutlined style={{ color: '#f59e0b' }} />
                      ) : (
                        <ExclamationCircleOutlined style={{ color: '#ef4444' }} />
                      )}
                      Network Health
                    </span>
                    <span style={{ 
                      fontSize: 11, 
                      padding: '2px 8px', 
                      borderRadius: 4,
                      fontWeight: 500,
                      background: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                        ? 'rgba(16, 185, 129, 0.15)' 
                        : errorHealthStatus === 'warning' 
                          ? 'rgba(245, 158, 11, 0.15)' 
                          : 'rgba(239, 68, 68, 0.15)',
                      color: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                        ? '#10b981' 
                        : errorHealthStatus === 'warning' 
                          ? '#f59e0b' 
                          : '#ef4444'
                    }}>
                      {(errorHealthStatus || 'healthy').charAt(0).toUpperCase() + (errorHealthStatus || 'healthy').slice(1)}
                    </span>
                  </div>
                  
                  {/* Critical/Warning split display */}
                  <div style={{ display: 'flex', gap: 20, marginBottom: 10 }}>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#ef4444' }} />
                        Critical
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: totalCritical > 0 ? '#ef4444' : '#10b981' }}>
                        {totalCritical.toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#f59e0b' }} />
                        Warnings
                      </div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: totalWarnings > 0 ? '#f59e0b' : '#10b981' }}>
                        {totalWarnings.toLocaleString()}
                      </div>
                    </div>
                  </div>
                  
                  {/* Critical errors breakdown */}
                  {Object.keys(criticalByType).length > 0 && (
                    <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(239, 68, 68, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                      <div style={{ marginBottom: 4, color: '#ef4444', fontWeight: 500, fontSize: 11 }}>Critical Errors</div>
                      {Object.entries(criticalByType).map(([type, count]) => (
                        <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(239, 68, 68, 0.9)' : 'rgba(239, 68, 68, 0.85)' }}>
                          <span>{type.replace(/_/g, ' ')}</span>
                          <span style={{ fontWeight: 500 }}>{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {/* Warnings breakdown */}
                  {Object.keys(warningsByType).length > 0 && (
                    <div style={{ fontSize: 12, marginBottom: 8, background: 'rgba(245, 158, 11, 0.08)', padding: '6px 8px', borderRadius: 4 }}>
                      <div style={{ marginBottom: 4, color: '#f59e0b', fontWeight: 500, fontSize: 11 }}>Retransmits (Normal)</div>
                      {Object.entries(warningsByType).map(([type, count]) => (
                        <div key={type} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, color: isDark ? 'rgba(245, 158, 11, 0.9)' : 'rgba(245, 158, 11, 0.85)' }}>
                          <span>{type.replace(/_/g, ' ')}</span>
                          <span style={{ fontWeight: 500 }}>{count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {/* Health message */}
                  {errorHealthMessage && (
                    <div style={{ 
                      fontSize: 11, 
                      color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', 
                      borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`, 
                      paddingTop: 6,
                      marginTop: 4
                    }}>
                      {errorHealthMessage}
                    </div>
                  )}
                  
                  {/* Error anomaly alert */}
                  {errorAnomalySummary && errorAnomalySummary.total_anomalies > 0 && (
                    <div style={{ marginTop: 8, padding: '6px 8px', background: 'rgba(102, 126, 234, 0.1)', borderRadius: 4, border: '1px solid rgba(102, 126, 234, 0.2)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#667eea', fontWeight: 500 }}>
                        <AlertOutlined style={{ fontSize: 12 }} />
                        {errorAnomalySummary.total_anomalies} Anomal{errorAnomalySummary.total_anomalies === 1 ? 'y' : 'ies'} Detected
                      </div>
                      <div style={{ fontSize: 11, marginTop: 2, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)' }}>Trend: {errorAnomalySummary.trends?.trend || 'stable'}</div>
                    </div>
                  )}
                  
                  {/* No errors state */}
                  {!hasErrors && !filterErrorsOnly && (
                    <div style={{ color: '#10b981', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <CheckCircleOutlined style={{ fontSize: 14 }} />
                      No network errors detected
                    </div>
                  )}
                  
                  {/* Filter hint */}
                  {!hasErrors && filterErrorsOnly && (
                    <div style={{ marginTop: 8, fontSize: 11, color: '#f59e0b', borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`, paddingTop: 6 }}>
                      No errors match current filters. Click to disable error filter.
                    </div>
                  )}
                  {hasErrors && (
                    <div style={{ marginTop: 8, fontSize: 11, color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)', borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)'}`, paddingTop: 6 }}>
                      {filterErrorsOnly ? 'Showing only error connections. Click to show all.' : 'Click to filter error connections'}
                    </div>
                  )}
                </div>
              } 
              mouseEnterDelay={0.3}
              color={isDark ? token.colorBgElevated : '#fff'}
              overlayInnerStyle={{ 
                padding: 12,
                boxShadow: isDark ? '0 6px 16px rgba(0,0,0,0.4)' : '0 6px 16px rgba(0,0,0,0.08)',
                borderRadius: 8
              }}
            >
              <Card 
                size="small" 
                bordered={false} 
                onClick={() => (hasErrors || filterErrorsOnly) && setFilterErrorsOnly(!filterErrorsOnly)}
                style={{ 
                  cursor: (hasErrors || filterErrorsOnly) ? 'pointer' : 'default',
                  border: filterErrorsOnly ? '2px solid #667eea' : hasCriticalErrors ? '1px solid rgba(239, 68, 68, 0.3)' : undefined,
                  background: filterErrorsOnly ? (isDark ? 'rgba(102, 126, 234, 0.1)' : 'rgba(102, 126, 234, 0.05)') : undefined
                }}
                bodyStyle={{ padding: '6px 10px', position: 'relative' }}
              >
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                    {filterErrorsOnly ? 'Errors (filtered)' : 'Network Health'}
                  </Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    {/* Critical errors count */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <ExclamationCircleOutlined style={{ 
                        color: selectedAnalysisId && hasCriticalErrors ? '#ef4444' : (isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)'), 
                        fontSize: 14 
                      }} />
                      <span style={{ 
                        fontSize: 18, 
                        fontWeight: 600, 
                        color: selectedAnalysisId && hasCriticalErrors ? '#ef4444' : undefined 
                      }}>
                        {!selectedAnalysisId ? '-' : animatedCritical.toLocaleString()}
                      </span>
                    </div>
                    {/* Separator */}
                    <span style={{ color: isDark ? 'rgba(255,255,255,0.35)' : 'rgba(0,0,0,0.35)', fontSize: 12 }}>/</span>
                    {/* Warnings count */}
                    <span style={{ 
                      fontSize: 14, 
                      fontWeight: 500, 
                      color: selectedAnalysisId && totalWarnings > 0 ? '#f59e0b' : (isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)')
                    }}>
                      {!selectedAnalysisId ? '-' : animatedWarnings.toLocaleString()}
                    </span>
                  </div>
                </div>
                {/* Anomaly badge */}
                {errorAnomalySummary && errorAnomalySummary.total_anomalies > 0 && (
                  <Tag 
                    style={{ 
                      position: 'absolute', 
                      top: 4, 
                      right: 4, 
                      fontSize: 9,
                      padding: '0 4px',
                      background: 'rgba(102, 126, 234, 0.15)',
                      color: '#667eea',
                      border: '1px solid rgba(102, 126, 234, 0.3)'
                    }}
                  >
                    {errorAnomalySummary.total_anomalies}
                  </Tag>
                )}
                {/* Health status indicator */}
                {selectedAnalysisId && !filterErrorsOnly && (
                  <div 
                    style={{ 
                      position: 'absolute', 
                      bottom: 4, 
                      right: 4, 
                      width: 8, 
                      height: 8, 
                      borderRadius: '50%',
                      background: errorHealthStatus === 'healthy' || errorHealthStatus === 'good' 
                        ? '#10b981' 
                        : errorHealthStatus === 'warning' 
                          ? '#f59e0b' 
                          : '#ef4444'
                    }} 
                  />
                )}
              </Card>
            </Tooltip>
          </Col>
          <Col flex="1">
            <Tooltip title="Total events from all event types" mouseEnterDelay={0.5}>
              <Card size="small" bordered={false} bodyStyle={{ padding: '6px 10px' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Events</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <NodeIndexOutlined style={{ color: '#22c55e', fontSize: 16 }} />
                    <span style={{ fontSize: 20, fontWeight: 600 }}>
                      {!selectedAnalysisId ? '-' : (eventStatsError ? '-' : animatedEvents.toLocaleString())}
                    </span>
                  </div>
                </div>
              </Card>
            </Tooltip>
          </Col>
          <Col flex="1">
            <Tooltip title="Unique namespaces in current view" mouseEnterDelay={0.5}>
              <Card size="small" bordered={false} bodyStyle={{ padding: '6px 10px' }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Namespaces</Text>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FilterOutlined style={{ color: '#f97316', fontSize: 16 }} />
                    <span style={{ fontSize: 20, fontWeight: 600 }}>
                      {!selectedAnalysisId ? '-' : animatedNamespaces.toLocaleString()}
                    </span>
                  </div>
                </div>
              </Card>
            </Tooltip>
          </Col>
        </Row>
      )}

      {/* Main Content */}
      <div style={{ flex: 1, display: 'flex', gap: 8, minHeight: 0, position: 'relative' }}>
        {/* Left Panel */}
        {showFilterPanel && (
          <div style={{ width: 220, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto' }}>
            {/* Filter Toggles - at top for quick access */}
            <Card 
              title={<Space><FilterOutlined /><Text strong style={{ fontSize: 12 }}>Filters</Text></Space>}
              size="small"
              bordered={false}
              bodyStyle={{ padding: '8px 12px' }}
              extra={<Tooltip title="Hide panel" mouseEnterDelay={0.5}><Button type="text" size="small" icon={<LeftOutlined />} onClick={() => setShowFilterPanel(false)} /></Tooltip>}
            >
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Tooltip title="Show localhost/internal traffic (127.0.0.1, etc.)" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Internal</Text>
                    <Switch size="small" checked={showInternalTraffic} onChange={setShowInternalTraffic} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Hide system namespaces (openshift-*, kube-*, default, sdn-infrastructure). Turn off to see infrastructure pods." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Hide System</Text>
                    <Switch size="small" checked={hideSystemNamespaces} onChange={setHideSystemNamespaces} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Public: Show only REAL PUBLIC internet IPs (like 142.x.x.x), DNS-enriched external endpoints (namespace='external'), and ingress/gateway nodes. Private datacenter IPs are NOT shown." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11, color: '#f59e0b' }}><GlobalOutlined style={{ marginRight: 4 }} />Public</Text>
                    <Switch size="small" checked={focusPublicOnly} onChange={setFocusPublicOnly} />
                  </div>
                </Tooltip>
                
                <Tooltip title="DataCenter: Show private IPs (10.x, 172.x, 192.168.x) that are OUTSIDE the Kubernetes cluster. These are datacenter systems like databases, legacy apps, and internal services." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11, color: '#06b6d4' }}><BankOutlined style={{ marginRight: 4 }} />DataCenter</Text>
                    <Switch size="small" checked={focusDataCenterOnly} onChange={setFocusDataCenterOnly} />
                  </div>
                </Tooltip>
                
                <Tooltip title="IP Focus: Show nodes with unresolved IP addresses as names (e.g., 10.194.x.x). Includes ALL IPs (both public and private). Useful for identifying dependencies that should use FQDN or Service names." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11, color: '#722ed1' }}><AimOutlined style={{ marginRight: 4 }} />Unresolved IP</Text>
                    <Switch size="small" checked={focusIPOnly} onChange={setFocusIPOnly} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Workload View: Group pods by deployment/workload name. Shows simplified view where replica pods and same workloads across clusters are merged into single nodes." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11, color: '#8b5cf6' }}><BlockOutlined style={{ marginRight: 4 }} />Workload View</Text>
                    <Switch size="small" checked={aggregatedView} onChange={setAggregatedView} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Show IP address in node details" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Show IP</Text>
                    <Switch size="small" checked={showNodeIP} onChange={setShowNodeIP} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Show protocol name on connections (e.g. TCP, HTTP)" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Protocol</Text>
                    <Switch size="small" checked={showProtocolLabel} onChange={setShowProtocolLabel} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Show request count on connections" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Requests</Text>
                    <Switch size="small" checked={showFlowLabel} onChange={setShowFlowLabel} />
                  </div>
                </Tooltip>
                
                <Divider style={{ margin: '8px 0' }} />
                
                <Tooltip title="Connection limit for performance. Auto-adjusts based on analysis size (small: 200, medium: 300, large: 500). Your selection persists until page refresh. Focus/Search modes show all relevant edges." mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      <ApartmentOutlined style={{ marginRight: 4 }} />Connection Limit
                      {userSelectedLimit === null && (
                        <Tooltip title="Smart limit: Auto-calculated based on analysis size" mouseEnterDelay={0.5}>
                          <span style={{ 
                            color: '#8b5cf6', 
                            marginLeft: 4, 
                            fontSize: 14, 
                            fontWeight: 'bold',
                            textShadow: '0 0 4px #8b5cf6'
                          }}>•</span>
                        </Tooltip>
                      )}
                    </Text>
                    <Select
                      size="small"
                      value={displayLimitValue}
                      onChange={(value) => {
                        // User explicitly selected a limit - persists until page refresh
                        setUserSelectedLimit(value as number | 'all');
                      }}
                      style={{ width: 80 }}
                      options={[
                        { value: 100, label: '100' },
                        { value: 200, label: '200' },
                        { value: 300, label: '300' },
                        { value: 500, label: '500' },
                        { value: 1000, label: '1K' },
                        { value: 2000, label: '2K' },
                        { value: 5000, label: '5K' },
                        { value: 'all', label: 'Max' },
                      ]}
                    />
                  </div>
                </Tooltip>
                
                <Divider style={{ margin: '8px 0' }} />
                
                <Tooltip title="Show DNS, security, OOM badges on nodes" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      <ThunderboltOutlined style={{ marginRight: 4 }} />Enrichment
                    </Text>
                    <Switch size="small" checked={showEnrichmentBadges} onChange={setShowEnrichmentBadges} />
                  </div>
                </Tooltip>
                
                <Tooltip title="Show TLS/encrypted connection indicators" mouseEnterDelay={0.5}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      <LockOutlined style={{ marginRight: 4, color: '#52c41a' }} />TLS
                    </Text>
                    <Switch size="small" checked={showTlsIndicators} onChange={setShowTlsIndicators} />
                  </div>
                </Tooltip>
              </Space>
            </Card>
            
            {/* Enrichment Summary */}
            {showEnrichmentBadges && enrichmentSummary && enrichmentSummary.enrichedNodeCount > 0 && (
              <Card 
                title={<Space><ThunderboltOutlined /><Text strong style={{ fontSize: 12 }}>Enrichment</Text></Space>}
                size="small"
                bordered={false}
                bodyStyle={{ padding: '8px 12px' }}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Tooltip title={enrichmentSummary.actualDnsTotal ? `Total: ${enrichmentSummary.actualDnsTotal.toLocaleString()}` : undefined} mouseEnterDelay={0.5}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 10 }}><GlobalOutlined style={{ marginRight: 4 }} />DNS Queries</Text>
                      <Space size={2}>
                        <Text strong style={{ fontSize: 10 }}>
                          {enrichmentSummary.dnsLimitReached ? '1,000+' : enrichmentSummary.totalDnsQueries.toLocaleString()}
                        </Text>
                        {enrichmentSummary.dnsLimitReached && <ThunderboltOutlined style={{ fontSize: 8, color: '#faad14' }} />}
                      </Space>
                    </div>
                  </Tooltip>
                  <Tooltip 
                    title={
                      enrichmentSummary.actualTlsTotal 
                        ? `Total SNI events: ${enrichmentSummary.actualTlsTotal.toLocaleString()}. Pods with TLS: ${Object.keys(tlsConnectionMap).length}` 
                        : `Pods with TLS: ${Object.keys(tlsConnectionMap).length}`
                    }
                    mouseEnterDelay={0.5}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 10 }}><LockOutlined style={{ marginRight: 4, color: '#52c41a' }} />TLS Connections</Text>
                        {Object.keys(tlsConnectionMap).length > 0 && (
                          <div style={{ 
                            width: 8, 
                            height: 8, 
                            borderRadius: '50%', 
                            background: '#52c41a',
                            boxShadow: '0 0 4px rgba(82, 196, 26, 0.8)'
                          }} />
                        )}
                      </Space>
                      <Space size={2}>
                        <Text strong style={{ fontSize: 10 }}>
                          {enrichmentSummary.tlsLimitReached ? '1,000+' : enrichmentSummary.totalTlsConnections.toLocaleString()}
                        </Text>
                        {enrichmentSummary.tlsLimitReached && <ThunderboltOutlined style={{ fontSize: 8, color: '#faad14' }} />}
                      </Space>
                    </div>
                  </Tooltip>
                  <Tooltip title={enrichmentSummary.actualSecurityTotal ? `Total: ${enrichmentSummary.actualSecurityTotal.toLocaleString()}` : undefined} mouseEnterDelay={0.5}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 10 }}><SecurityScanOutlined style={{ marginRight: 4, color: '#1890ff' }} />Security Events</Text>
                      <Space size={2}>
                        <Text strong style={{ fontSize: 10 }}>
                          {enrichmentSummary.securityLimitReached ? '1,000+' : enrichmentSummary.totalSecurityEvents.toLocaleString()}
                        </Text>
                        {enrichmentSummary.securityLimitReached && <ThunderboltOutlined style={{ fontSize: 8, color: '#faad14' }} />}
                      </Space>
                    </div>
                  </Tooltip>
                  {enrichmentSummary.totalOomKills > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Text type="secondary" style={{ fontSize: 10, color: '#ff4d4f' }}><WarningOutlined style={{ marginRight: 4 }} />OOM Kills</Text>
                      <Text strong style={{ fontSize: 10, color: '#ff4d4f' }}>{enrichmentSummary.totalOomKills}</Text>
                    </div>
                  )}
                  {enrichmentSummary.nodesWithIssues > 0 && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 10 }}><ExclamationCircleOutlined style={{ marginRight: 4, color: '#faad14' }} />Nodes with Issues</Text>
                      <Tag color="orange" style={{ fontSize: 9, lineHeight: '14px' }}>{enrichmentSummary.nodesWithIssues}</Tag>
                    </div>
                  )}
                </Space>
              </Card>
            )}
            
            {/* Event Statistics - at bottom */}
            <Card 
              title={<Text strong style={{ fontSize: 12 }}>Event Statistics</Text>}
              size="small"
              bordered={false}
              bodyStyle={{ padding: '4px 8px' }}
            >
              {!selectedAnalysisId ? (
                <Empty description="Select analysis" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
              ) : isEventStatsLoading ? (
                <div style={{ textAlign: 'center', padding: 12 }}><Spin size="small" /></div>
              ) : eventStatsError ? (
                <Empty description="Failed to load" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
              ) : (
                <EventStatsPanel 
                  stats={eventStats} 
                  isLoading={isEventStatsLoading}
                  selectedEventType={highlightedEventType}
                  onEventTypeClick={setHighlightedEventType}
                />
              )}
            </Card>
          </div>
        )}
        
        {/* Map Container - Only apply map canvas background when analysis is selected */}
        <div style={{ flex: 1, borderRadius: 8, overflow: 'hidden', boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.3)' : '0 2px 8px rgba(0,0,0,0.1)', background: selectedAnalysisId ? (isDark ? '#1a1a2e' : '#f8fafc') : (isDark ? token.colorBgContainer : '#f8fafc'), position: 'relative', minHeight: 0 }}>
          {/* Left Panel Toggle - Always visible in fullscreen or when panel is hidden */}
          {(!showFilterPanel || isFullscreen) && (
            <div style={{ position: 'absolute', left: 8, top: 8, zIndex: 10 }}>
              <Tooltip title={showFilterPanel ? "Hide Left Panel" : "Show Left Panel"} mouseEnterDelay={0.5}>
                <Button 
                  type={showFilterPanel ? "default" : "primary"} 
                  size="small" 
                  icon={showFilterPanel ? <LeftOutlined /> : <RightOutlined />} 
                  onClick={() => setShowFilterPanel(!showFilterPanel)}
                  style={{ 
                    boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.3)' : '0 2px 8px rgba(0,0,0,0.15)',
                    background: showFilterPanel ? (isDark ? token.colorBgContainer : '#fff') : undefined
                  }}
                />
              </Tooltip>
            </div>
          )}
          
          {!selectedAnalysisId ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
              <GlobalOutlined style={{ fontSize: 64, color: isDark ? '#4a4a6a' : '#cbd5e1' }} />
              <Text type="secondary">Select an analysis to view the map</Text>
            </div>
          ) : isGraphLoading && !graphData ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Spin size="large" />
            </div>
          ) : graphError ? (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
              <Text type="danger">Failed to load</Text>
              <Button onClick={() => refetchGraph()} icon={<ReloadOutlined />}>Retry</Button>
            </div>
          ) : !isReactFlowMounted ? (
            // Brief unmount during filter transition to clear ReactFlow internal cache
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Spin size="small" />
            </div>
          ) : (
            <ReactFlow
              // KEY forces ReactFlow to completely remount and clear internal edge cache
              // This is needed because useNodesState/useEdgesState are OUTSIDE ReactFlowProvider
              // Key changes on EVERY filter change to prevent floating edges
              key={`rf-${filterKey}`}
              nodes={nodes}
              edges={safeEdges}
              onNodesChange={onNodesChange}
              // CRITICAL: Do NOT use onEdgesChange - it causes ReactFlow to manage its own
              // internal edge state which bypasses our safeEdges filtering and causes floating edges
              // onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={handleNodeClick}
              onInit={(instance) => { 
                reactFlowInstance.current = instance;
                // Fit view only on first load with smooth animation
                setTimeout(() => instance.fitView({ padding: 0.2, duration: 150 }), 50);
              }}
              minZoom={0.01}
              maxZoom={4}
              nodesDraggable={true}
              nodesConnectable={false}
              nodesFocusable={true}
              elementsSelectable={true}
              selectNodesOnDrag={false}
              panOnDrag={true}
              panOnScroll={false}
              zoomOnScroll={true}
              zoomOnPinch={true}
              zoomOnDoubleClick={true}
              preventScrolling={true}
              autoPanOnNodeDrag={true}
              autoPanSpeed={15}
              elevateNodesOnSelect={true}
              nodeDragThreshold={0}
              proOptions={{ hideAttribution: true }}
              style={{ background: isDark ? '#1a1a2e' : '#f8fafc', width: '100%', height: '100%' }}
            >
              <Background color={isDark ? '#3a3a5c' : '#94a3b8'} gap={20} variant="dots" />
              <Controls 
                style={{ bottom: 16, left: 8 }} 
                showZoom={true}
                showFitView={true}
                showInteractive={true}
              />
              <MiniMap 
                nodeColor={(node) => node.style?.background as string || '#6366f1'}
                maskColor={isDark ? 'rgba(26, 26, 46, 0.8)' : 'rgba(255, 255, 255, 0.8)'}
                style={{ 
                  background: isDark ? 'rgba(30, 30, 50, 0.95)' : 'rgba(255, 255, 255, 0.95)', 
                  border: `1px solid ${isDark ? '#3a3a5c' : '#e2e8f0'}`, 
                  borderRadius: 8 
                }}
                pannable={true}
                zoomable={true}
                zoomStep={5}
              />
              
              {/* Focus Mode Legend - shows when a node is focused */}
              {focusedNodeId && (
                <Panel position="bottom-left" style={{ marginLeft: 60, marginBottom: 16 }}>
                  <div style={{ 
                    background: isDark ? 'rgba(30, 30, 50, 0.95)' : 'rgba(255, 255, 255, 0.95)', 
                    backdropFilter: 'blur(8px)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    borderRadius: 10,
                    padding: '10px 14px',
                    boxShadow: isDark ? '0 4px 12px rgba(0, 0, 0, 0.3)' : '0 4px 12px rgba(0, 0, 0, 0.1)',
                    minWidth: 160
                  }}>
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: 6, 
                      marginBottom: 8,
                      borderBottom: `1px solid ${isDark ? '#3a3a5c' : '#e5e7eb'}`,
                      paddingBottom: 6
                    }}>
                      <AimOutlined style={{ color: '#6366f1', fontSize: 12 }} />
                      <Text strong style={{ fontSize: 10, color: '#6366f1' }}>FOCUS MODE</Text>
                    </div>
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ 
                          width: 14, 
                          height: 14, 
                          borderRadius: '50%', 
                          background: '#6366f1',
                          border: '2px solid #6366f1',
                          boxShadow: '0 0 8px rgba(99, 102, 241, 0.6)'
                        }} />
                        <Text style={{ fontSize: 10 }}>Focused Node</Text>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ 
                          width: 14, 
                          height: 14, 
                          borderRadius: '50%', 
                          background: '#22c55e',
                          border: '2px solid rgba(34, 197, 94, 0.7)',
                          boxShadow: '0 0 6px rgba(34, 197, 94, 0.4)'
                        }} />
                        <Text style={{ fontSize: 10 }}>Connected Nodes</Text>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ 
                          width: 14, 
                          height: 14, 
                          borderRadius: '50%', 
                          background: '#d1d5db',
                          opacity: 0.4
                        }} />
                        <Text style={{ fontSize: 10 }}>Other Nodes</Text>
                      </div>
                    </Space>
                    <Button 
                      type="text" 
                      size="small" 
                      block
                      onClick={() => setFocusedNodeId(null)}
                      style={{ marginTop: 8, fontSize: 10, height: 24 }}
                    >
                      Clear Focus
                    </Button>
                  </div>
                </Panel>
              )}
              
            </ReactFlow>
          )}
        </div>
        
        {/* Right Panel - Control Panel & Namespaces */}
        {showControlPanel && (
          <div style={{ width: 180, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 8, overflowY: 'auto', maxHeight: '100%' }}>
            <Card 
              title={<Space><SettingOutlined /><Text strong style={{ fontSize: 11 }}>Controls</Text></Space>}
              size="small"
              bordered={false}
              bodyStyle={{ padding: '8px' }}
              extra={<Tooltip title="Close" mouseEnterDelay={0.5}><Button type="text" size="small" icon={<MenuUnfoldOutlined />} onClick={() => setShowControlPanel(false)} /></Tooltip>}
            >
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                <div>
                  <Text type="secondary" style={{ fontSize: 10, display: 'block', marginBottom: 4 }}>Layout</Text>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 2 }}>
                    {layoutOptions.map(opt => (
                      <Tooltip key={opt.value} title={opt.title} mouseEnterDelay={0.5}>
                        <Button
                          size="small"
                          type={layout === opt.value ? 'primary' : 'default'}
                          icon={opt.icon}
                          onClick={() => setLayout(opt.value as LayoutType)}
                          style={{ padding: '2px 4px', fontSize: 10 }}
                        />
                      </Tooltip>
                    ))}
                  </div>
                </div>
                
                <div>
                  <Text type="secondary" style={{ fontSize: 10 }}>Node Size: {nodeSize}</Text>
                  <Slider min={20} max={80} value={nodeSize} onChange={setNodeSize} />
                </div>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 10 }}>Labels</Text>
                  <Switch size="small" checked={showLabels} onChange={setShowLabels} />
                </div>
                
                <Divider style={{ margin: '8px 0' }} />
                
                {/* Animation Control */}
                <Button 
                  block 
                  size="small" 
                  onClick={() => setIsAnimationPaused(!isAnimationPaused)}
                  icon={isAnimationPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                  type={isAnimationPaused ? 'primary' : 'default'}
                >
                  {isAnimationPaused ? 'Resume Flow' : 'Pause Flow'}
                </Button>
                
                <Button block size="small" onClick={handleFitView} icon={<FullscreenOutlined />}>
                  Fit View
                </Button>
              </Space>
            </Card>
            
            {/* Namespaces Legend */}
            {showNamespacePanel && namespaces.length > 0 && (
              <Card 
                title={<Text strong style={{ fontSize: 11 }}>NAMESPACES</Text>}
                size="small"
                bordered={false}
                bodyStyle={{ padding: '8px', maxHeight: 250, overflowY: 'auto' }}
                extra={
                  <Button 
                    type="text" 
                    size="small" 
                    icon={<UpOutlined />} 
                    onClick={() => setShowNamespacePanel(false)} 
                  />
                }
              >
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {highlightedNamespace && (
                    <Tag 
                      style={{ 
                        cursor: 'pointer',
                        background: isDark ? '#2a2a3e' : '#f0f0f0',
                        border: `1px dashed ${isDark ? '#4a4a6a' : '#d9d9d9'}`,
                        fontSize: 10,
                        margin: 0,
                      }}
                      onClick={() => setHighlightedNamespace(null)}
                    >
                      Clear ✕
                    </Tag>
                  )}
                  {namespaces.map(ns => {
                    const nsColor = getNamespaceColor(ns);
                    const isActive = highlightedNamespace === ns;
                    // Uses effectiveGraphData for correct count in both normal and aggregated views
                    const nodeCount = effectiveGraphData?.nodes?.filter((n: DependencyNode) => n.namespace === ns).length || 0;
                    
                    return (
                      <Tooltip key={ns} title={`${nodeCount} nodes - Click to ${isActive ? 'clear' : 'highlight'}`} mouseEnterDelay={0.5}>
                        <Tag 
                          style={{ 
                            cursor: 'pointer',
                            background: nsColor,
                            color: '#fff',
                            border: isActive ? `2px solid ${isDark ? '#fff' : '#000'}` : 'none',
                            fontSize: 10,
                            margin: 0,
                            transform: isActive ? 'scale(1.05)' : 'scale(1)',
                            transition: 'all 0.2s ease',
                            boxShadow: isActive ? `0 0 8px ${nsColor}` : 'none',
                          }}
                          onClick={() => setHighlightedNamespace(isActive ? null : ns)}
                        >
                          {ns}
                        </Tag>
                      </Tooltip>
                    );
                  })}
                </div>
              </Card>
            )}
            
            {/* Show Namespace Panel Button */}
            {!showNamespacePanel && namespaces.length > 0 && (
              <Button 
                size="small" 
                block
                icon={<TagOutlined />}
                onClick={() => setShowNamespacePanel(true)}
              >
                Namespaces ({namespaces.length})
              </Button>
            )}
            
            {/* Connection Legend Panel */}
            {showLegendPanel && (
              <Card 
                title={<Text strong style={{ fontSize: 11 }}>LEGEND</Text>}
                size="small"
                bordered={false}
                bodyStyle={{ padding: '8px 12px', maxHeight: 280, overflowY: 'auto' }}
                style={{ flexShrink: 0 }}
                extra={
                  <Button 
                    type="text" 
                    size="small" 
                    icon={<UpOutlined />} 
                    onClick={() => setShowLegendPanel(false)} 
                  />
                }
              >
                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                  <Text type="secondary" style={{ fontSize: 9, fontWeight: 600 }}>CONNECTIONS</Text>
                  
                  {/* TLS/Encrypted */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 28, 
                      height: 3, 
                      background: '#52c41a',
                      borderRadius: 2,
                      boxShadow: '0 0 4px rgba(82, 196, 26, 0.6)'
                    }} />
                    <LockOutlined style={{ fontSize: 11, color: '#52c41a' }} />
                    <Text style={{ fontSize: 10 }}>TLS/Encrypted</Text>
                  </div>
                  
                  {/* Regular/Animated */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 28, 
                      height: 2, 
                      background: 'linear-gradient(90deg, #faad14 0%, #faad14 40%, transparent 40%, transparent 60%, #faad14 60%)',
                      borderRadius: 2,
                    }} />
                    <Text style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>Animated Flow</Text>
                  </div>
                  
                  {/* Static */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 28, 
                      height: 2, 
                      background: '#6366f1',
                      borderRadius: 2,
                    }} />
                    <Text style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>Static</Text>
                  </div>
                  
                  {/* Error */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 28, 
                      height: 2, 
                      background: '#ef4444',
                      borderRadius: 2,
                    }} />
                    <Text style={{ fontSize: 10, color: '#ef4444' }}>Has Errors</Text>
                  </div>
                  
                  <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
                  <Text type="secondary" style={{ fontSize: 9, fontWeight: 600 }}>PROTOCOLS</Text>
                  
                  {/* HTTP */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#3b82f6', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>HTTP</Text>
                  </div>
                  
                  {/* HTTPS/TLS */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#22c55e', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>HTTPS/TLS</Text>
                  </div>
                  
                  {/* GRPC */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#8b5cf6', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>GRPC</Text>
                  </div>
                  
                  {/* TCP */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#f97316', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>TCP</Text>
                  </div>
                  
                  {/* UDP */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#ec4899', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>UDP</Text>
                  </div>
                  
                  {/* DNS */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 28, height: 2, background: '#06b6d4', borderRadius: 2 }} />
                    <Text style={{ fontSize: 10 }}>DNS</Text>
                  </div>
                  
                  <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
                  <Text type="secondary" style={{ fontSize: 9, fontWeight: 600 }}>NODES</Text>
                  
                  {/* Public IP (Internet) */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '50%',
                      background: '#f59e0b',
                      border: '2px solid #fbbf24',
                    }} />
                    <Text style={{ fontSize: 10 }}><GlobalOutlined style={{ marginRight: 4, color: '#f59e0b' }} />Public IP</Text>
                  </div>

                  {/* DataCenter IP (Private, non-cluster) */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{
                      width: 14,
                      height: 14,
                      borderRadius: '50%',
                      background: '#06b6d4',
                      border: '2px solid #22d3ee',
                    }} />
                    <Text style={{ fontSize: 10 }}><BankOutlined style={{ marginRight: 4, color: '#06b6d4' }} />DataCenter IP</Text>
                  </div>
                  
                  {/* Risk Node */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '50%',
                      background: '#6366f1',
                      border: '2px solid #ff4d4f',
                    }} />
                    <Text style={{ fontSize: 10, color: '#ff4d4f' }}><ExclamationCircleOutlined style={{ marginRight: 4 }} />Has Issues</Text>
                  </div>
                  
                  {/* Service Node */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '25%',
                      background: '#8b5cf6',
                    }} />
                    <Text style={{ fontSize: 10 }}>◇ Service</Text>
                  </div>
                  
                  {/* SDN Gateway */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '35%',
                      background: '#ec4899',
                    }} />
                    <Text style={{ fontSize: 10 }}>◐ SDN Gateway</Text>
                  </div>
                  
                  <div style={{ borderTop: '1px solid #f0f0f0', margin: '4px 0' }} />
                  <Text type="secondary" style={{ fontSize: 9, fontWeight: 600 }}>NETWORK TYPES</Text>
                  
                  {/* Pod Network */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '50%',
                      background: '#22c55e',
                    }} />
                    <Text style={{ fontSize: 10 }}>◆ Pod Network</Text>
                  </div>
                  
                  {/* Service Network */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '25%',
                      background: '#8b5cf6',
                    }} />
                    <Text style={{ fontSize: 10 }}>◆ Service Network</Text>
                  </div>
                  
                  {/* Internal Network */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '40%',
                      background: '#06b6d4',
                    }} />
                    <Text style={{ fontSize: 10 }}>◎ Internal Network</Text>
                  </div>
                  
                  {/* Node Network */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '15%',
                      background: '#f97316',
                    }} />
                    <Text style={{ fontSize: 10 }}>▣ Node IP</Text>
                  </div>
                  
                  {/* Public IP (Internet) */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '50%',
                      background: '#f59e0b',
                    }} />
                    <Text style={{ fontSize: 10 }}><GlobalOutlined style={{ marginRight: 4, color: '#f59e0b' }} />Public IP</Text>
                  </div>
                  
                  {/* DataCenter IP */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ 
                      width: 14, 
                      height: 14, 
                      borderRadius: '50%',
                      background: '#06b6d4',
                    }} />
                    <Text style={{ fontSize: 10 }}><BankOutlined style={{ marginRight: 4, color: '#06b6d4' }} />DataCenter</Text>
                  </div>
                </Space>
              </Card>
            )}
            
            {/* Show Legend Button */}
            {!showLegendPanel && (
              <Button 
                size="small" 
                block
                icon={<InfoCircleOutlined />}
                onClick={() => setShowLegendPanel(true)}
              >
                Legend
              </Button>
            )}
          </div>
        )}
        
        {/* Right Panel Toggle - Always visible in fullscreen or when panel is hidden */}
        {(!showControlPanel || isFullscreen) && (
          <div style={{ position: 'absolute', right: 8, top: 8, zIndex: 10 }}>
            <Tooltip title={showControlPanel ? "Hide Right Panel" : "Show Right Panel"} mouseEnterDelay={0.5}>
              <Button 
                type={showControlPanel ? "default" : "primary"} 
                size="small" 
                icon={showControlPanel ? <RightOutlined /> : <LeftOutlined />} 
                onClick={() => setShowControlPanel(!showControlPanel)}
                style={{ 
                  boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.3)' : '0 2px 8px rgba(0,0,0,0.15)',
                  background: showControlPanel ? (isDark ? token.colorBgContainer : '#fff') : undefined
                }}
              />
            </Tooltip>
          </div>
        )}
      </div>
    </div>
    
    {/* Enhanced Node Detail Drawer */}
    {/* PERFORMANCE: Memoized drawer computed values - prevents recalculation on every render */}
    {drawerComputedValues && (
    <Drawer
      className="enriched-drawer"
      getContainer={isFullscreen ? (containerRef.current || document.body) : document.body}
      title={(() => {
        // Use memoized values for drawer title - no recalculation needed
        const { nodeName, isResolved, displayNode, displayNamespace, displayName, isNodePublicIP, knownSvc } = drawerComputedValues;
        
        return (
          <Space align="start">
            <div style={{ 
              width: 14, 
              height: 14, 
              borderRadius: '50%', 
              background: isNodePublicIP 
                ? (knownSvc?.color || PUBLIC_IP_COLOR)
                : getNamespaceColor(displayNamespace),
              border: isNodePublicIP ? '2px solid #fbbf24' : (isResolved ? '2px solid #22c55e' : 'none'),
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
            }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>
                {isNodePublicIP && (knownSvc?.icon || <GlobalOutlined style={{ color: '#f59e0b', marginRight: 4 }} />)}
                {isResolved && !isNodePublicIP && <AimOutlined style={{ color: '#22c55e', marginRight: 4 }} />}
                {isNodePublicIP && knownSvc ? knownSvc.name : displayName}
              </div>
              {isResolved && (
                <div style={{ fontSize: 10, color: isDark ? '#94a3b8' : '#64748b', marginBottom: 2 }}>
                  IP: {nodeName}
                </div>
              )}
              <Space size={4} style={{ marginTop: 2 }}>
                <Tag style={{ 
                  background: getNamespaceColor(displayNamespace), 
                  color: '#fff', 
                  border: 'none',
                  fontSize: 9,
                  lineHeight: '14px'
                }}>
                  {displayNamespace || 'unknown'}
                </Tag>
                {isResolved && (
                  <Tag color="green" style={{ fontSize: 9, lineHeight: '14px' }}>Resolved</Tag>
                )}
                {isNodePublicIP && (
                  <Tag color="orange" icon={<GlobalOutlined />} style={{ fontSize: 9, lineHeight: '14px' }}>Public</Tag>
                )}
                {(displayNode as any)?.isDataCenterIP && (
                  <Tag color="cyan" icon={<BankOutlined />} style={{ fontSize: 9, lineHeight: '14px' }}>DataCenter</Tag>
                )}
                {(() => {
                  const networkType = (displayNode as any)?.network_type || selectedNode?.network_type;
                  const ntInfo = getNetworkTypeInfo(networkType);
                  if (ntInfo) {
                    return <Tag style={{ background: ntInfo.color, color: '#fff', border: 'none', fontSize: 9, lineHeight: '14px' }}>{ntInfo.icon} {ntInfo.label}</Tag>;
                  }
                  return null;
                })()}
                {/* Use memoized nodeEnrichment instead of recalculating */}
                {drawerComputedValues?.nodeEnrichment?.riskLevel === 'danger' && (
                  <Tag color="error" icon={<ExclamationCircleOutlined />} style={{ fontSize: 9, lineHeight: '14px' }}>Issues</Tag>
                )}
                {drawerComputedValues?.nodeEnrichment?.riskLevel === 'warning' && (
                  <Tag color="warning" style={{ fontSize: 9, lineHeight: '14px' }}>Warning</Tag>
                )}
              </Space>
            </div>
          </Space>
        );
      })()}
      placement="right"
      width={420}
      open={drawerVisible}
      onClose={() => {
        setDrawerVisible(false);
        setSelectedNode(null);
        setFocusedNodeId(null);
        setDrawerTab('overview');
      }}
    >
      {selectedNode && drawerComputedValues && (() => {
        // Use memoized computed values for better performance
        // All values pre-calculated in drawerComputedValues useMemo
        const { nodeName, resolvedName, resolvedNode, isResolved, displayNode, displayNamespace, displayName, isNodePublicIP, knownSvc, nodeEnrichment, hasNsFilter, isExternalSelectedNode } = drawerComputedValues;
        // knownService alias for backward compatibility
        const knownService = knownSvc;
        
        return (
          <>
            {/* IP Resolution Info Banner */}
            {isResolved && (
              <div style={{ 
                background: isDark ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.15) 0%, rgba(34, 197, 94, 0.08) 100%)' : 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
                border: `1px solid ${isDark ? 'rgba(34, 197, 94, 0.3)' : '#86efac'}`,
                borderRadius: 8,
                padding: 12,
                marginBottom: 16
              }}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space>
                    <NodeIndexOutlined style={{ color: '#16a34a' }} />
                    <Text strong style={{ color: '#15803d' }}>IP Resolved to Pod</Text>
                  </Space>
                  <div>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      IP Address: <Tag color="default">{nodeName}</Tag>
                    </Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Resolved Pod: <Tag color="green">{displayName}</Tag>
                    </Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      Namespace: <Tag color="blue">{displayNamespace}</Tag>
                    </Text>
                  </div>
                </Space>
              </div>
            )}
            
            {/* External Node Banner - shows when viewing node from different namespace */}
            {isExternalSelectedNode && (
              <div style={{ 
                background: isDark ? 'linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(14, 165, 233, 0.08) 100%)' : 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)',
                border: `1px solid ${isDark ? 'rgba(14, 165, 233, 0.3)' : '#7dd3fc'}`,
                borderRadius: 8,
                padding: 12,
                marginBottom: 16
              }}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space>
                    <ApiOutlined style={{ color: '#0284c7' }} />
                    <Text strong style={{ color: '#0369a1' }}>External Connection</Text>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    This node is from <Tag color="blue">{displayNamespace}</Tag> namespace 
                    and communicates with your selected namespace{selectedNamespaces.length > 1 ? 's' : ''}: {selectedNamespaces.map(ns => (
                      <Tag key={ns} color="green" style={{ marginRight: 4 }}>{ns}</Tag>
                    ))}
                  </Text>
                  <Button 
                    type="primary" 
                    size="small"
                    icon={<AimOutlined />}
                    onClick={() => {
                      // Add this namespace to selected namespaces (switch focus)
                      setSelectedNamespaces([displayNamespace]);
                      setDrawerVisible(false);
                      setSelectedNode(null);
                    }}
                  >
                    View in {displayNamespace} namespace
                  </Button>
                </Space>
              </div>
            )}
            
            <Tabs 
              activeKey={drawerTab} 
              onChange={setDrawerTab}
              size="small"
              destroyInactiveTabPane  // PERFORMANCE: Don't keep inactive tabs in DOM
              items={[
                {
                  key: 'overview',
                  label: <span><InfoCircleOutlined /> Overview</span>,
                  // PERFORMANCE: Lazy render - only compute when tab is active
                  children: drawerTab === 'overview' ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {/* Debug info - shows why enrichment might be missing */}
                      {!nodeEnrichment && enrichedPods.length > 0 && (
                      <div style={{ 
                        background: isDark ? 'rgba(250, 173, 20, 0.1)' : '#fff7e6', 
                        border: `1px solid ${isDark ? 'rgba(250, 173, 20, 0.3)' : '#ffd591'}`, 
                        borderRadius: 6, 
                        padding: 8,
                        fontSize: 10
                      }}>
                        <Text type="warning" style={{ fontSize: 10 }}>
                          <ExclamationCircleOutlined style={{ marginRight: 4 }} />No exact enrichment match for "{selectedNode.namespace}/{selectedNode.name}"
                        </Text>
                        <div style={{ marginTop: 4 }}>
                          <Text type="secondary" style={{ fontSize: 9 }}>
                            Available pods in this namespace: {enrichedPods
                              .filter(p => p.startsWith(`${selectedNode.namespace}/`))
                              .slice(0, 3)
                              .map(p => p.split('/')[1])
                              .join(', ') || 'none'}
                            {enrichedPods.filter(p => p.startsWith(`${selectedNode.namespace}/`)).length > 3 && '...'}
                          </Text>
                        </div>
                      </div>
                    )}
                    
                    {!nodeEnrichment && enrichedPods.length === 0 && !isEnrichmentLoading && (
                      <div style={{ 
                        background: isDark ? token.colorBgContainer : '#f0f0f0', 
                        borderRadius: 6, 
                        padding: 12,
                        textAlign: 'center'
                      }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          No event data collected yet. Start an analysis to collect events.
                        </Text>
                      </div>
                    )}
                    
                    {isEnrichmentLoading && (
                      <div style={{ textAlign: 'center', padding: 12 }}>
                        <Spin size="small" />
                        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 10 }}>
                          Loading event data...
                        </Text>
                      </div>
                    )}
                    
                    {/* Aggregated Workload Info */}
                    {aggregatedView && (selectedNode as any)?._isAggregated && (
                      <div style={{ 
                        background: isDark ? 'linear-gradient(135deg, rgba(139, 92, 246, 0.15), rgba(139, 92, 246, 0.08))' : 'linear-gradient(135deg, #f5f3ff, #ede9fe)',
                        border: `1px solid ${isDark ? 'rgba(139, 92, 246, 0.3)' : '#c4b5fd'}`,
                        borderRadius: 8,
                        padding: 12,
                        marginBottom: 16
                      }}>
                        <Space direction="vertical" style={{ width: '100%' }} size={8}>
                          <Space>
                            <ClusterIcon style={{ color: '#7c3aed' }} />
                            <Text strong style={{ color: '#5b21b6' }}>Aggregated Workload</Text>
                          </Space>
                          
                          <Space wrap>
                            <Tag color="purple">{(selectedNode as any)._podCount || 1} pods</Tag>
                            {((selectedNode as any)._clusterCount || 1) > 1 && (
                              <Tag color="blue">{(selectedNode as any)._clusterCount} clusters</Tag>
                            )}
                          </Space>
                          
                          {/* Cluster bazlı pod dağılımı */}
                          {(selectedNode as any)._podsByCluster && Object.keys((selectedNode as any)._podsByCluster).length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <Text type="secondary" style={{ fontSize: 10, display: 'block', marginBottom: 6 }}>
                                Pod Distribution:
                              </Text>
                              {Object.entries((selectedNode as any)._podsByCluster).map(([clusterId, podsList]) => {
                                const cid = parseInt(clusterId, 10);
                                const cluster = clusterInfoMap.get(cid);
                                const pods = podsList as DependencyNode[];
                                
                                return (
                                  <div key={clusterId} style={{ marginBottom: 8 }}>
                                    <ClusterBadge
                                      clusterId={cid}
                                      clusterName={cluster?.name || `Cluster ${cid}`}
                                      environment={cluster?.environment}
                                      provider={cluster?.provider}
                                      size="small"
                                      showTooltip={true}
                                    />
                                    <div style={{ marginLeft: 16, marginTop: 4 }}>
                                      {pods.slice(0, 5).map((pod: DependencyNode) => (
                                        <Tag key={pod.id} style={{ fontSize: 9, marginBottom: 2 }}>
                                          {pod.name}
                                        </Tag>
                                      ))}
                                      {pods.length > 5 && (
                                        <Tag style={{ fontSize: 9, color: isDark ? '#a0a0a0' : '#8c8c8c' }}>+{pods.length - 5} more</Tag>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </Space>
                      </div>
                    )}
                    
                    {/* Quick Stats */}
                    {nodeEnrichment && (
                      <div style={{ 
                        background: isDark ? 'linear-gradient(135deg, rgba(24, 144, 255, 0.12), rgba(24, 144, 255, 0.06))' : 'linear-gradient(135deg, #f0f5ff, #e6f7ff)', 
                        borderRadius: 8, 
                        padding: 12,
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: 8
                      }}>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#1890ff' }}>
                            {nodeEnrichment.dnsQueryCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>DNS Queries</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#52c41a' }}>
                            {nodeEnrichment.tlsConnectionCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>TLS Connections</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#722ed1' }}>
                            {nodeEnrichment.processEventCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>Processes</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: '#eb2f96' }}>
                            {nodeEnrichment.fileEventCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>File I/O</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: nodeEnrichment.securityEventCount > 0 ? '#faad14' : '#389e0d' }}>
                            {nodeEnrichment.securityEventCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>Security</div>
                        </div>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 18, fontWeight: 600, color: nodeEnrichment.oomKillCount > 0 ? '#ff4d4f' : '#389e0d' }}>
                            {nodeEnrichment.oomKillCount}
                          </div>
                          <div style={{ fontSize: 10, color: isDark ? '#a0a0a0' : '#666' }}>OOM Kills</div>
                        </div>
                      </div>
                    )}
                    
                    {/* Known Service Info for External IPs */}
                    {knownService && (
                      <div style={{ 
                        background: `linear-gradient(135deg, ${knownService.color}15, ${knownService.color}30)`,
                        border: `1px solid ${knownService.color}50`,
                        borderRadius: 8, 
                        padding: 12 
                      }}>
                        <Space>
                          <span style={{ fontSize: 24 }}>{knownService.icon}</span>
                          <div>
                            <Text strong>{knownService.name}</Text>
                            <br />
                            <Text type="secondary" style={{ fontSize: 11 }}>{selectedNode.name}</Text>
                          </div>
                        </Space>
                      </div>
                    )}
                    
                    {/* Basic Info */}
                    <Descriptions column={1} bordered size="small" title="Pod Information">
                      <Descriptions.Item label="Pod Name">
                        <Text strong copyable style={{ fontSize: 11 }}>{selectedNode.name}</Text>
                      </Descriptions.Item>
                      <Descriptions.Item label="Namespace">
                        <Tag color="geekblue">{selectedNode.namespace || 'unknown'}</Tag>
                      </Descriptions.Item>
                      {/* Pod IP - show if available (for search correlation and network debugging) */}
                      {((selectedNode as any)?.ip || (selectedNode as any)?.pod_ip) && (
                        <Descriptions.Item label="Pod IP">
                          <Text code copyable style={{ fontSize: 11 }}>
                            {(selectedNode as any)?.ip || (selectedNode as any)?.pod_ip}
                          </Text>
                        </Descriptions.Item>
                      )}
                      {/* Host IP - show if different from Pod IP */}
                      {(selectedNode as any)?.host_ip && 
                       (selectedNode as any)?.host_ip !== ((selectedNode as any)?.ip || (selectedNode as any)?.pod_ip) && (
                        <Descriptions.Item label="Host IP">
                          <Text code copyable style={{ fontSize: 11 }}>
                            {(selectedNode as any)?.host_ip}
                          </Text>
                        </Descriptions.Item>
                      )}
                      {/* Cluster info for multi-cluster visibility */}
                      {/* Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly */}
                      {(selectedNode.cluster_id !== undefined && selectedNode.cluster_id !== null && selectedNode.cluster_id !== '') && (
                        <Descriptions.Item label="Cluster">
                          {(() => {
                            const clusterId = safeParseClusterId(selectedNode.cluster_id);
                            const cluster = clusterInfoMap.get(clusterId);
                            return cluster ? (
                              <ClusterBadge
                                clusterId={clusterId}
                                clusterName={cluster.name}
                                environment={cluster.environment}
                                provider={cluster.provider}
                                size="small"
                                showTooltip={true}
                              />
                            ) : (
                              <Tag color="default">Cluster {selectedNode.cluster_id}</Tag>
                            );
                          })()}
                        </Descriptions.Item>
                      )}
                      {/* Multi-Cluster Connections - Show which other clusters have connections to/from this node */}
                      {/* Uses effectiveGraphData to work correctly with both normal and aggregated views */}
                      {selectedAnalysis?.is_multi_cluster && effectiveGraphData?.edges && (
                        <Descriptions.Item label="Cross-Cluster">
                          {(() => {
                            // Find all edges connected to this node
                            const connectedEdges = effectiveGraphData.edges.filter(
                              (e: DependencyEdge) => e.source_id === selectedNode.id || e.target_id === selectedNode.id
                            );
                            
                            // Collect cluster IDs from connected nodes
                            const connectedClusterIds = new Set<number>();
                            const thisNodeClusterId = safeParseClusterId(selectedNode.cluster_id);
                            
                            connectedEdges.forEach((edge: DependencyEdge) => {
                              // Find the other node in this edge using effectiveNodeIdMap for O(1) lookup
                              const otherNodeId = edge.source_id === selectedNode.id ? edge.target_id : edge.source_id;
                              const otherNode = effectiveNodeIdMap[otherNodeId];
                              // Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly
                              if (otherNode?.cluster_id !== undefined && otherNode?.cluster_id !== null) {
                                const cid = safeParseClusterId(otherNode.cluster_id);
                                if (cid !== thisNodeClusterId) {
                                  connectedClusterIds.add(cid);
                                }
                              }
                            });
                            
                            if (connectedClusterIds.size === 0) {
                              return <Text type="secondary" style={{ fontSize: 10 }}>No cross-cluster connections</Text>;
                            }
                            
                            return (
                              <Space wrap size={4}>
                                {Array.from(connectedClusterIds).map(cid => {
                                  const cluster = clusterInfoMap.get(cid);
                                  return cluster ? (
                                    <ClusterBadge
                                      key={cid}
                                      clusterId={cid}
                                      clusterName={cluster.name}
                                      environment={cluster.environment}
                                      provider={cluster.provider}
                                      size="small"
                                      showTooltip={true}
                                    />
                                  ) : (
                                    <Tag key={cid} color="purple" style={{ fontSize: 10 }}>
                                      Cluster {cid}
                                    </Tag>
                                  );
                                })}
                              </Space>
                            );
                          })()}
                        </Descriptions.Item>
                      )}
                      {/* Same Node in Other Clusters - Check if node with same name/namespace exists in other clusters */}
                      {/* Skip for aggregated nodes - they already show cluster distribution in Aggregated Workload Info section */}
                      {/* Uses filteredGraphData (original) to find actual pods, not aggregated nodes */}
                      {selectedAnalysis?.is_multi_cluster && filteredGraphData?.nodes && !(selectedNode as any)?._isAggregated && (
                        <Descriptions.Item label="Also In">
                          {(() => {
                            const thisNodeClusterId = safeParseClusterId(selectedNode.cluster_id);
                            
                            // Find nodes with same name and namespace but different cluster
                            // Note: Uses filteredGraphData (not effectiveGraphData) because we want to find actual pods
                            // Note: cluster_id can be 0 which is valid, so check for undefined/null explicitly
                            const sameNodeInOtherClusters = filteredGraphData.nodes.filter((n: DependencyNode) => {
                              if (n.cluster_id === undefined || n.cluster_id === null) return false;
                              const nClusterId = safeParseClusterId(n.cluster_id);
                              return n.name === selectedNode.name 
                                && n.namespace === selectedNode.namespace 
                                && nClusterId !== thisNodeClusterId;
                            });
                            
                            if (sameNodeInOtherClusters.length === 0) {
                              return <Text type="secondary" style={{ fontSize: 10 }}>Unique to this cluster</Text>;
                            }
                            
                            const clusterIdSet = new Set(sameNodeInOtherClusters.map((n: DependencyNode) => {
                              return safeParseClusterId(n.cluster_id);
                            }));
                            const clusterIds = Array.from(clusterIdSet);
                            
                            return (
                              <Space wrap size={4}>
                                <Tooltip title="Same workload exists in these clusters" mouseEnterDelay={0.5}>
                                  <Tag color="green" icon={<CheckCircleOutlined />} style={{ fontSize: 10 }}>Deployed</Tag>
                                </Tooltip>
                                {clusterIds.map(cid => {
                                  const cluster = clusterInfoMap.get(cid);
                                  return cluster ? (
                                    <ClusterBadge
                                      key={cid}
                                      clusterId={cid}
                                      clusterName={cluster.name}
                                      environment={cluster.environment}
                                      provider={cluster.provider}
                                      size="small"
                                      showTooltip={true}
                                    />
                                  ) : (
                                    <Tag key={cid} color="cyan" style={{ fontSize: 10 }}>
                                      Cluster {cid}
                                    </Tag>
                                  );
                                })}
                              </Space>
                            );
                          })()}
                        </Descriptions.Item>
                      )}
                      <Descriptions.Item label="Kind">
                        <Tag color="blue">{selectedNode.kind || 'Pod'}</Tag>
                      </Descriptions.Item>
                      <Descriptions.Item label="Status">
                        <Badge 
                          status={selectedNode.status === 'active' || selectedNode.status === 'running' ? 'success' : 'warning'} 
                          text={selectedNode.status || 'unknown'}
                        />
                      </Descriptions.Item>
                    </Descriptions>
                    
                    {/* Network Info - detailed network information */}
                    {/* Note: Pod IP and Host IP also shown in basic info above for quick access */}
                    <Descriptions column={1} bordered size="small" title="Network">
                      {((selectedNode as any)?.ip || (selectedNode as any)?.pod_ip) && (
                        <Descriptions.Item label="Pod IP">
                          <Text copyable style={{ fontFamily: 'monospace', fontSize: 11 }}>
                            {(selectedNode as any)?.ip || (selectedNode as any)?.pod_ip}
                          </Text>
                        </Descriptions.Item>
                      )}
                      {(selectedNode as any)?.host_ip && (
                        <Descriptions.Item label="Host IP">
                          <Text copyable style={{ fontFamily: 'monospace', fontSize: 11 }}>{(selectedNode as any).host_ip}</Text>
                        </Descriptions.Item>
                      )}
                      {(selectedNode as any)?.node && (
                        <Descriptions.Item label="Node">
                          <Text style={{ fontSize: 11 }}>{(selectedNode as any).node}</Text>
                        </Descriptions.Item>
                      )}
                      {nodeEnrichment && nodeEnrichment.listeningPorts.length > 0 && (
                        <Descriptions.Item label="Listening Ports">
                          <Space wrap size={4}>
                            {nodeEnrichment.listeningPorts.slice(0, 10).map(port => (
                              <Tag key={port} color="cyan" style={{ fontSize: 10 }}>{port}</Tag>
                            ))}
                            {nodeEnrichment.listeningPorts.length > 10 && (
                              <Tag style={{ fontSize: 10 }}>+{nodeEnrichment.listeningPorts.length - 10}</Tag>
                            )}
                          </Space>
                        </Descriptions.Item>
                      )}
                    </Descriptions>
                    
                    {/* Owner & Container */}
                    {((selectedNode as any)?.owner_kind || (selectedNode as any)?.container) && (
                      <Descriptions column={1} bordered size="small" title="Workload">
                        {(selectedNode as any)?.owner_kind && (
                          <Descriptions.Item label="Owner">
                            <Tag color={
                              (selectedNode as any).owner_kind === 'Deployment' ? 'blue' :
                              (selectedNode as any).owner_kind === 'StatefulSet' ? 'purple' :
                              (selectedNode as any).owner_kind === 'DaemonSet' ? 'orange' : 'default'
                            }>
                              {(selectedNode as any).owner_kind}
                            </Tag>
                            <Text style={{ fontSize: 11, marginLeft: 4 }}>{(selectedNode as any).owner_name}</Text>
                          </Descriptions.Item>
                        )}
                        {(selectedNode as any)?.container && (
                          <Descriptions.Item label="Container">
                            <Text style={{ fontSize: 11 }}>{(selectedNode as any).container}</Text>
                          </Descriptions.Item>
                        )}
                        {(selectedNode as any)?.service_account && (
                          <Descriptions.Item label="Service Account">
                            <Tag color="geekblue" style={{ fontSize: 10 }}>{(selectedNode as any).service_account}</Tag>
                          </Descriptions.Item>
                        )}
                      </Descriptions>
                    )}
                  </div>
                ) : null,  // End lazy render for overview tab
              },
              {
                key: 'dns',
                label: <span><GlobalOutlined /> DNS ({nodeEnrichment?.dnsQueryCount || 0})</span>,
                children: nodeEnrichment && nodeEnrichment.rawDnsEvents.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* External Domains Summary */}
                    {nodeEnrichment.externalDomains.length > 0 && (
                      <div style={{ background: isDark ? 'rgba(82, 196, 26, 0.1)' : '#f6ffed', border: `1px solid ${isDark ? 'rgba(82, 196, 26, 0.3)' : '#b7eb8f'}`, borderRadius: 8, padding: 10 }}>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          <GlobalOutlined style={{ marginRight: 4, color: '#52c41a' }} />External Domains ({nodeEnrichment.externalDomains.length})
                        </Text>
                        <Space wrap size={4}>
                          {nodeEnrichment.externalDomains.slice(0, 15).map(domain => (
                            <Tag key={domain} color="green" style={{ fontSize: 9 }}>{domain}</Tag>
                          ))}
                          {nodeEnrichment.externalDomains.length > 15 && (
                            <Tag style={{ fontSize: 9 }}>+{nodeEnrichment.externalDomains.length - 15} more</Tag>
                          )}
                        </Space>
                      </div>
                    )}
                    
                    {/* DNS Failure Alert */}
                    {nodeEnrichment.dnsFailureCount > 0 && (
                      <div style={{ background: isDark ? 'rgba(250, 140, 22, 0.1)' : '#fff2e8', border: `1px solid ${isDark ? 'rgba(250, 140, 22, 0.3)' : '#ffbb96'}`, borderRadius: 8, padding: 10 }}>
                        <Text type="warning" style={{ fontSize: 11 }}>
                          <WarningOutlined /> {nodeEnrichment.dnsFailureCount} DNS failures detected
                        </Text>
                      </div>
                    )}
                    
                    {/* Recent DNS Queries */}
                    <List
                      size="small"
                      header={<Text strong style={{ fontSize: 11 }}>Recent Queries</Text>}
                      dataSource={nodeEnrichment.rawDnsEvents.slice(0, 20)}
                      renderItem={(event) => (
                        <List.Item style={{ padding: '6px 0' }}>
                          <div style={{ width: '100%' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                              <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{event.query_name}</Text>
                              <Tag color={event.response_code === 'NOERROR' || event.response_code === '0' ? 'success' : 'error'} 
                                   style={{ fontSize: 9 }}>
                                {event.response_code}
                              </Tag>
                            </div>
                            <Text type="secondary" style={{ fontSize: 9 }}>
                              {event.query_type} • {event.latency_ms}ms • {new Date(event.timestamp).toLocaleTimeString()}
                            </Text>
                          </div>
                        </List.Item>
                      )}
                    />
                  </div>
                ) : (
                  <Empty description="No DNS queries recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
              },
              {
                key: 'tls',
                label: <span><LockOutlined /> TLS ({nodeEnrichment?.tlsConnectionCount || 0})</span>,
                children: nodeEnrichment && nodeEnrichment.rawSniEvents.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* TLS Versions */}
                    {nodeEnrichment.tlsVersions.length > 0 && (
                      <div style={{ background: isDark ? 'rgba(82, 196, 26, 0.1)' : '#f6ffed', border: `1px solid ${isDark ? 'rgba(82, 196, 26, 0.3)' : '#b7eb8f'}`, borderRadius: 8, padding: 10 }}>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          <LockOutlined style={{ marginRight: 4, color: '#52c41a' }} />TLS Versions Used
                        </Text>
                        <Space wrap size={4}>
                          {nodeEnrichment.tlsVersions.map(v => (
                            <Tag key={v} color={v.includes('1.3') ? 'green' : v.includes('1.2') ? 'blue' : 'orange'} 
                                 style={{ fontSize: 10 }}>
                              {v}
                            </Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                    
                    {/* Server Names */}
                    <List
                      size="small"
                      header={<Text strong style={{ fontSize: 11 }}>TLS Server Names (SNI)</Text>}
                      dataSource={nodeEnrichment.rawSniEvents.slice(0, 20)}
                      renderItem={(event) => (
                        <List.Item style={{ padding: '6px 0' }}>
                          <div style={{ width: '100%' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>
                                <LockOutlined style={{ marginRight: 4, color: '#52c41a' }} />{event.server_name || event.sni_name || 'N/A'}
                              </Text>
                              <Tag color="cyan" style={{ fontSize: 9 }}>{event.tls_version}</Tag>
                            </div>
                            <Text type="secondary" style={{ fontSize: 9 }}>
                              → {event.dest_ip || event.dst_ip}:{event.dest_port || event.dst_port} • {new Date(event.timestamp).toLocaleTimeString()}
                            </Text>
                          </div>
                        </List.Item>
                      )}
                    />
                  </div>
                ) : (
                  <Empty description="No TLS connections recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
              },
              {
                key: 'security',
                label: <span><SafetyOutlined /> Security ({(nodeEnrichment?.securityEventCount || 0) + (nodeEnrichment?.oomKillCount || 0)})</span>,
                children: (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* OOM Kills Alert */}
                    {nodeEnrichment && nodeEnrichment.oomKillCount > 0 && (
                      <div style={{ background: isDark ? 'rgba(255, 77, 79, 0.1)' : '#fff1f0', border: `1px solid ${isDark ? 'rgba(255, 77, 79, 0.3)' : '#ffa39e'}`, borderRadius: 8, padding: 12 }}>
                        <Space>
                          <WarningOutlined style={{ fontSize: 24, color: '#ff4d4f' }} />
                          <div>
                            <Text strong type="danger">OOM Killed {nodeEnrichment.oomKillCount} times</Text>
                            <br />
                            <Text type="secondary" style={{ fontSize: 10 }}>
                              Last: {nodeEnrichment.lastOomTime ? new Date(nodeEnrichment.lastOomTime).toLocaleString() : 'Unknown'}
                            </Text>
                          </div>
                        </Space>
                      </div>
                    )}
                    
                    {/* Denied Capabilities */}
                    {nodeEnrichment && nodeEnrichment.deniedCapabilities.length > 0 && (
                      <div style={{ background: isDark ? 'rgba(250, 173, 20, 0.1)' : '#fff7e6', border: `1px solid ${isDark ? 'rgba(250, 173, 20, 0.3)' : '#ffd591'}`, borderRadius: 8, padding: 10 }}>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6, color: '#d46b08' }}>
                          <WarningOutlined style={{ marginRight: 4 }} />Denied Capabilities
                        </Text>
                        <Space wrap size={4}>
                          {nodeEnrichment.deniedCapabilities.map(cap => (
                            <Tag key={cap} color="error" style={{ fontSize: 9 }}>{cap}</Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                    
                    {/* Capability Checks */}
                    {nodeEnrichment && nodeEnrichment.capabilityChecks.length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          <SafetyOutlined style={{ marginRight: 4, color: '#1890ff' }} />Capability Checks
                        </Text>
                        <Space wrap size={4}>
                          {nodeEnrichment.capabilityChecks.map(cap => (
                            <Tag key={cap} color={nodeEnrichment.deniedCapabilities.includes(cap) ? 'error' : 'success'} 
                                 style={{ fontSize: 9 }}>
                              {cap}
                            </Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                    
                    {/* Security Events List */}
                    {nodeEnrichment && nodeEnrichment.rawSecurityEvents.length > 0 && (
                      <List
                        size="small"
                        header={<Text strong style={{ fontSize: 11 }}>Recent Security Events</Text>}
                        dataSource={nodeEnrichment.rawSecurityEvents.slice(0, 15)}
                        renderItem={(event) => (
                          <List.Item style={{ padding: '6px 0' }}>
                            <div style={{ width: '100%' }}>
                              <Space>
                                <Tag color={event.verdict === 'allowed' ? 'success' : 'error'} style={{ fontSize: 9 }}>
                                  {event.verdict}
                                </Tag>
                                <Text style={{ fontSize: 11 }}>{event.capability || event.syscall}</Text>
                              </Space>
                              <br />
                              <Text type="secondary" style={{ fontSize: 9 }}>
                                {event.comm} (pid: {event.pid}) • {new Date(event.timestamp).toLocaleTimeString()}
                              </Text>
                            </div>
                          </List.Item>
                        )}
                      />
                    )}
                    
                    {(!nodeEnrichment || (nodeEnrichment.securityEventCount === 0 && nodeEnrichment.oomKillCount === 0)) && (
                      <Empty description="No security events recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </div>
                ),
              },
              {
                key: 'fileio',
                label: <span><FileOutlined /> File I/O ({nodeEnrichment?.fileEventCount || 0})</span>,
                children: nodeEnrichment && nodeEnrichment.fileEventCount > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* File Operations Summary */}
                    {Object.keys(nodeEnrichment.fileOperations).length > 0 && (
                      <div style={{ background: isDark ? 'rgba(250, 173, 20, 0.1)' : '#fff7e6', border: `1px solid ${isDark ? 'rgba(250, 173, 20, 0.3)' : '#ffd591'}`, borderRadius: 8, padding: 10 }}>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          📁 Operations Summary
                        </Text>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {Object.entries(nodeEnrichment.fileOperations).map(([op, count]) => (
                            <div key={op} style={{ 
                              background: isDark ? token.colorBgContainer : '#fff', 
                              borderRadius: 4, 
                              padding: '4px 8px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              border: `1px solid ${isDark ? 'rgba(250, 173, 20, 0.4)' : '#ffe7ba'}`
                            }}>
                              <Text style={{ fontSize: 10, fontWeight: 500 }}>{op}</Text>
                              <Tag color="orange" style={{ fontSize: 9, margin: 0 }}>{count}</Tag>
                            </div>
                          ))}
                        </div>
                        {nodeEnrichment.configFileAccess && (
                          <div style={{ marginTop: 8 }}>
                            <Tag color="warning" icon={<SettingOutlined />} style={{ fontSize: 9 }}>Config file access detected</Tag>
                          </div>
                        )}
                      </div>
                    )}
                    
                    {/* Recent File Events */}
                    {nodeEnrichment.rawFileEvents.length > 0 && (
                      <List
                        size="small"
                        header={<Text strong style={{ fontSize: 11 }}>Recent File Events</Text>}
                        dataSource={nodeEnrichment.rawFileEvents.slice(0, 20)}
                        renderItem={(event) => (
                          <List.Item style={{ padding: '6px 0' }}>
                            <div style={{ width: '100%' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <Tag color={event.operation === 'write' ? 'orange' : event.operation === 'read' ? 'blue' : 'default'} 
                                     style={{ fontSize: 9 }}>
                                  {event.operation}
                                </Tag>
                                <Text type="secondary" style={{ fontSize: 9 }}>
                                  {new Date(event.timestamp).toLocaleTimeString()}
                                </Text>
                              </div>
                              <Text style={{ fontSize: 10, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                                {event.file_path}
                              </Text>
                              <div style={{ marginTop: 2 }}>
                                <Text type="secondary" style={{ fontSize: 9 }}>
                                  {event.comm} • {event.bytes > 0 ? `${event.bytes} bytes` : ''}
                                </Text>
                              </div>
                            </div>
                          </List.Item>
                        )}
                      />
                    )}
                  </div>
                ) : (
                  <Empty description="No file I/O events recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ),
              },
              {
                key: 'activity',
                label: <span><ThunderboltOutlined /> Process ({nodeEnrichment?.processEventCount || 0})</span>,
                children: (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* Process Activity */}
                    {nodeEnrichment && nodeEnrichment.uniqueProcesses.length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          <ThunderboltOutlined style={{ marginRight: 4, color: '#faad14' }} />Unique Processes ({nodeEnrichment.uniqueProcesses.length})
                        </Text>
                        <Space wrap size={4}>
                          {nodeEnrichment.uniqueProcesses.slice(0, 20).map(proc => (
                            <Tag key={proc} color="purple" style={{ fontSize: 9 }}>{proc}</Tag>
                          ))}
                          {nodeEnrichment.uniqueProcesses.length > 20 && (
                            <Tag style={{ fontSize: 9 }}>+{nodeEnrichment.uniqueProcesses.length - 20}</Tag>
                          )}
                        </Space>
                      </div>
                    )}
                    
                    {/* Recent Process Events */}
                    {nodeEnrichment && nodeEnrichment.rawProcessEvents.length > 0 && (
                      <List
                        size="small"
                        header={<Text strong style={{ fontSize: 11 }}>Recent Process Events</Text>}
                        dataSource={nodeEnrichment.rawProcessEvents.slice(0, 15)}
                        renderItem={(event) => {
                          // Extract command from exe or args
                          const exe = event.exe || '';
                          const args = Array.isArray(event.args) ? event.args : [];
                          const argsStr = args.join(' ');
                          const command = exe || argsStr || event.comm || '-';
                          const hasCommand = command && command !== '-';
                          
                          return (
                            <List.Item style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                              <div style={{ width: '100%' }}>
                                {/* Header: Type + Process Name + Time */}
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                  <Space size={4}>
                                    <Tag color={event.event_subtype === 'exec' ? 'green' : event.event_subtype === 'exit' ? 'red' : 'blue'} 
                                         style={{ fontSize: 9 }}>
                                      {event.event_subtype}
                                    </Tag>
                                    <Text strong style={{ fontSize: 11 }}>{event.comm || 'unknown'}</Text>
                                  </Space>
                                  <Text type="secondary" style={{ fontSize: 9 }}>
                                    {new Date(event.timestamp).toLocaleTimeString()}
                                  </Text>
                                </div>
                                
                                {/* Command Line - the main enhancement */}
                                {hasCommand && (
                                  <div style={{ 
                                    background: '#1e293b', 
                                    borderRadius: 4, 
                                    padding: '6px 8px', 
                                    marginBottom: 4,
                                    maxHeight: 60,
                                    overflow: 'auto'
                                  }}>
                                    <Text style={{ 
                                      fontSize: 10, 
                                      fontFamily: 'monospace', 
                                      color: '#22c55e',
                                      wordBreak: 'break-all',
                                      whiteSpace: 'pre-wrap'
                                    }}>
                                      $ {command}
                                    </Text>
                                  </div>
                                )}
                                
                                {/* PID Info */}
                                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                  {event.pid > 0 && (
                                    <Text type="secondary" style={{ fontSize: 9 }}>
                                      PID: <Text code style={{ fontSize: 9 }}>{event.pid}</Text>
                                    </Text>
                                  )}
                                  {event.ppid > 0 && (
                                    <Text type="secondary" style={{ fontSize: 9 }}>
                                      PPID: <Text code style={{ fontSize: 9 }}>{event.ppid}</Text>
                                    </Text>
                                  )}
                                  {event.exit_code !== undefined && event.exit_code !== 0 && (
                                    <Tag color={event.exit_code === 0 ? 'success' : 'error'} style={{ fontSize: 8 }}>
                                      Exit: {event.exit_code}
                                    </Tag>
                                  )}
                                  {event.uid !== undefined && event.uid > 0 && (
                                    <Text type="secondary" style={{ fontSize: 9 }}>
                                      UID: {event.uid}
                                    </Text>
                                  )}
                                </div>
                              </div>
                            </List.Item>
                          );
                        }}
                      />
                    )}
                    
                    {/* Volume Mounts */}
                    {nodeEnrichment && nodeEnrichment.volumeMounts.length > 0 && (
                      <div>
                        <Text strong style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                          💾 Volume Mounts
                        </Text>
                        <List
                          size="small"
                          dataSource={nodeEnrichment.volumeMounts.slice(0, 10)}
                          renderItem={(mount) => (
                            <List.Item style={{ padding: '4px 0' }}>
                              <Text style={{ fontSize: 10, fontFamily: 'monospace' }}>{mount}</Text>
                            </List.Item>
                          )}
                        />
                      </div>
                    )}
                    
                    {(!nodeEnrichment || nodeEnrichment.processEventCount === 0) && (
                      <Empty description="No process activity recorded" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </div>
                ),
              },
              {
                key: 'labels',
                label: <span><TagOutlined /> Labels</span>,
                // PERFORMANCE: Lazy render - only compute when tab is active
                children: drawerTab === 'labels' ? (
                  (selectedNode as any)?.labels && Object.keys((selectedNode as any).labels || {}).length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {Object.entries((selectedNode as any).labels || {}).map(([key, value]) => (
                      <div key={key} style={{ 
                        background: isDark ? token.colorBgContainer : '#f8fafc', 
                        borderRadius: 4, 
                        padding: '6px 10px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <Text strong style={{ fontSize: 10, color: isDark ? '#69b1ff' : '#1890ff' }}>{key}</Text>
                        <Text type="secondary" style={{ fontSize: 10 }}>{String(value)}</Text>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty description="No labels" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
                ) : null,  // End lazy render for labels tab
              },
              {
                key: 'annotations',
                label: <span><TagOutlined /> Annotations</span>,
                children: drawerTab === 'annotations' ? (() => {
                  const allAnnotations = Object.entries((selectedNode as any)?.annotations || {});
                  if (allAnnotations.length === 0) {
                    return <Empty description="No annotations" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
                  }

                  const INFRA_PREFIXES = ['k8s.ovn.org/', 'k8s.v1.cni.cncf.io/', 'seccomp.security', 'openshift.openshift.io/'];
                  const userAnns = allAnnotations.filter(([k]) => !INFRA_PREFIXES.some(p => k.startsWith(p)));
                  const infraAnns = allAnnotations.filter(([k]) => INFRA_PREFIXES.some(p => k.startsWith(p)));

                  return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {userAnns.map(([k, v]) => <AnnotationRow key={k} annKey={k} annValue={v} isDark={isDark} token={token} />)}
                      {infraAnns.length > 0 && (
                        <details style={{ marginTop: userAnns.length > 0 ? 4 : 0 }}>
                          <summary style={{
                            cursor: 'pointer', fontSize: 11, color: isDark ? '#8c8c8c' : '#8c8c8c',
                            padding: '4px 0', userSelect: 'none'
                          }}>
                            Infrastructure ({infraAnns.length})
                          </summary>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                            {infraAnns.map(([k, v]) => <AnnotationRow key={k} annKey={k} annValue={v} isDark={isDark} token={token} />)}
                          </div>
                        </details>
                      )}
                    </div>
                  );
                })() : null,
              },
              {
                key: 'ai-hub',
                label: <span><RobotOutlined /> AI Hub</span>,
                children: drawerTab === 'ai-hub' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <Typography.Text type="secondary">
                      Analyze this service's dependencies, impact radius, and generate integration snippets for AI Agents and CI/CD pipelines.
                    </Typography.Text>
                    <Button
                      type="primary"
                      icon={<RobotOutlined />}
                      onClick={() => {
                        const node = selectedNode as any;
                        const params = new URLSearchParams();
                        if (node?.name) params.set('owner_name', node.owner_name || node.name);
                        if (node?.namespace && node.namespace !== 'external') params.set('namespace', node.namespace);
                        navigate(`/integration/ai-hub?${params.toString()}`);
                      }}
                    >
                      Open AI Integration Hub
                    </Button>
                  </div>
                ) : null,
              },
              {
                key: 'connections',
                label: <span><ApiOutlined /> Connections ({(() => {
                  // Uses effectiveGraphData to work correctly with both normal and aggregated views
                  if (!selectedNode || !effectiveGraphData?.edges) return 0;
                  const nodeId = selectedNode.id;
                  return effectiveGraphData.edges.filter((e: DependencyEdge) => 
                    e.source_id === nodeId || e.target_id === nodeId
                  ).length;
                })()})</span>,
                // PERFORMANCE: Lazy render - only compute when tab is active (most expensive tab!)
                children: drawerTab === 'connections' ? (() => {
                  // Uses effectiveGraphData and effectiveNodeIdMap for proper aggregated view support
                  if (!selectedNode || !effectiveGraphData?.edges) {
                    return <Empty description="No connections found" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
                  }
                  
                  const nodeId = selectedNode.id;
                  const connectedEdges = effectiveGraphData.edges.filter((e: DependencyEdge) => 
                    e.source_id === nodeId || e.target_id === nodeId
                  );
                  
                  if (connectedEdges.length === 0) {
                    return <Empty description="No connections found" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
                  }
                  
                  // Group by outgoing and incoming
                  const outgoing = connectedEdges.filter((e: DependencyEdge) => e.source_id === nodeId);
                  const incoming = connectedEdges.filter((e: DependencyEdge) => e.target_id === nodeId);
                  
                  // Get connected node details - PERFORMANCE: O(1) lookup via effectiveNodeIdMap
                  // Uses effectiveNodeIdMap to correctly resolve aggregated node IDs
                  const getNodeDetails = (id: string) => {
                    const node = effectiveNodeIdMap[id];
                    if (!node) return { name: 'Unknown', namespace: '', color: '#6b7280' };
                    const { resolvedName, resolvedNode } = resolveIpToPod(node.name || '');
                    const ns = resolvedNode?.namespace || node.namespace || '';
                    return { 
                      name: resolvedName, 
                      namespace: ns, 
                      color: getNamespaceColor(ns),
                      isExternal: selectedNamespaces.length > 0 ? !new Set(selectedNamespaces).has(ns) : false
                    };
                  };
                  
                  return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                      {/* Outgoing Connections */}
                      {outgoing.length > 0 && (
                        <div>
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: 8, 
                            marginBottom: 8,
                            padding: '6px 10px',
                            background: 'linear-gradient(135deg, #f0fdf4, #dcfce7)',
                            borderRadius: 6
                          }}>
                            <span style={{ fontSize: 14 }}>→</span>
                            <Text strong style={{ fontSize: 12, color: '#16a34a' }}>
                              Outgoing ({outgoing.length})
                            </Text>
                          </div>
                          <List
                            size="small"
                            dataSource={outgoing.slice(0, 20)}
                            renderItem={(edge: DependencyEdge) => {
                              const target = getNodeDetails(edge.target_id);
                              return (
                                <List.Item 
                                  style={{ 
                                    padding: '8px 10px', 
                                    cursor: 'pointer',
                                    background: isDark ? token.colorBgContainer : '#fafafa',
                                    marginBottom: 4,
                                    borderRadius: 6,
                                    border: `1px solid ${isDark ? token.colorBorderSecondary : '#f0f0f0'}`
                                  }}
                                  onClick={() => {
                                    // PERFORMANCE: O(1) lookup via effectiveNodeIdMap for aggregated view support
                                    const targetNode = effectiveNodeIdMap[edge.target_id];
                                    if (targetNode) {
                                      setSelectedNode(targetNode);
                                      setFocusedNodeId(edge.target_id);
                                      setDrawerTab('overview');
                                    }
                                  }}
                                >
                                  <div style={{ width: '100%' }}>
                                    <Space>
                                      <div style={{ 
                                        width: 10, 
                                        height: 10, 
                                        borderRadius: '50%', 
                                        background: target.color 
                                      }} />
                                      <Text strong style={{ fontSize: 11 }}>{target.name}</Text>
                                      {target.isExternal && (
                                        <Tag color="blue" style={{ fontSize: 8, lineHeight: '12px' }}>ext</Tag>
                                      )}
                                    </Space>
                                    <div style={{ marginTop: 4 }}>
                                      <Tag style={{ fontSize: 9, background: target.color, color: '#fff', border: 'none' }}>
                                        {target.namespace || 'external'}
                                      </Tag>
                                      <Text type="secondary" style={{ fontSize: 9, marginLeft: 8 }}>
                                        {edge.request_count || 0} flows • {getEffectiveProtocol(edge)}
                                      </Text>
                                    </div>
                                  </div>
                                </List.Item>
                              );
                            }}
                          />
                          {outgoing.length > 20 && (
                            <Text type="secondary" style={{ fontSize: 10, display: 'block', textAlign: 'center', marginTop: 8 }}>
                              +{outgoing.length - 20} more outgoing connections
                            </Text>
                          )}
                        </div>
                      )}
                      
                      {/* Incoming Connections */}
                      {incoming.length > 0 && (
                        <div>
                          <div style={{ 
                            display: 'flex', 
                            alignItems: 'center', 
                            gap: 8, 
                            marginBottom: 8,
                            padding: '6px 10px',
                            background: 'linear-gradient(135deg, #eff6ff, #dbeafe)',
                            borderRadius: 6
                          }}>
                            <span style={{ fontSize: 14 }}>←</span>
                            <Text strong style={{ fontSize: 12, color: '#2563eb' }}>
                              Incoming ({incoming.length})
                            </Text>
                          </div>
                          <List
                            size="small"
                            dataSource={incoming.slice(0, 20)}
                            renderItem={(edge: DependencyEdge) => {
                              const source = getNodeDetails(edge.source_id);
                              return (
                                <List.Item 
                                  style={{ 
                                    padding: '8px 10px', 
                                    cursor: 'pointer',
                                    background: isDark ? token.colorBgContainer : '#fafafa',
                                    marginBottom: 4,
                                    borderRadius: 6,
                                    border: `1px solid ${isDark ? token.colorBorderSecondary : '#f0f0f0'}`
                                  }}
                                  onClick={() => {
                                    // PERFORMANCE: O(1) lookup via effectiveNodeIdMap for aggregated view support
                                    const sourceNode = effectiveNodeIdMap[edge.source_id];
                                    if (sourceNode) {
                                      setSelectedNode(sourceNode);
                                      setFocusedNodeId(edge.source_id);
                                      setDrawerTab('overview');
                                    }
                                  }}
                                >
                                  <div style={{ width: '100%' }}>
                                    <Space>
                                      <div style={{ 
                                        width: 10, 
                                        height: 10, 
                                        borderRadius: '50%', 
                                        background: source.color 
                                      }} />
                                      <Text strong style={{ fontSize: 11 }}>{source.name}</Text>
                                      {source.isExternal && (
                                        <Tag color="blue" style={{ fontSize: 8, lineHeight: '12px' }}>ext</Tag>
                                      )}
                                    </Space>
                                    <div style={{ marginTop: 4 }}>
                                      <Tag style={{ fontSize: 9, background: source.color, color: '#fff', border: 'none' }}>
                                        {source.namespace || 'external'}
                                      </Tag>
                                      <Text type="secondary" style={{ fontSize: 9, marginLeft: 8 }}>
                                        {edge.request_count || 0} flows • {getEffectiveProtocol(edge)}
                                      </Text>
                                    </div>
                                  </div>
                                </List.Item>
                              );
                            }}
                          />
                          {incoming.length > 20 && (
                            <Text type="secondary" style={{ fontSize: 10, display: 'block', textAlign: 'center', marginTop: 8 }}>
                              +{incoming.length - 20} more incoming connections
                            </Text>
                          )}
                        </div>
                      )}
                      
                      {/* Summary */}
                      <div style={{ 
                        background: 'linear-gradient(135deg, #f5f3ff, #ede9fe)', 
                        borderRadius: 8, 
                        padding: 12,
                        marginTop: 8
                      }}>
                        <Text strong style={{ fontSize: 11, color: '#6d28d9', display: 'block', marginBottom: 8 }}>
                          <BarChartOutlined style={{ marginRight: 4 }} />Connection Summary
                        </Text>
                        <div style={{ display: 'flex', justifyContent: 'space-around' }}>
                          <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 16, fontWeight: 600, color: '#16a34a' }}>{outgoing.length}</div>
                            <div style={{ fontSize: 9, color: isDark ? '#a0a0a0' : '#666' }}>Outgoing</div>
                          </div>
                          <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 16, fontWeight: 600, color: '#2563eb' }}>{incoming.length}</div>
                            <div style={{ fontSize: 9, color: isDark ? '#a0a0a0' : '#666' }}>Incoming</div>
                          </div>
                          <div style={{ textAlign: 'center' }}>
                            <div style={{ fontSize: 16, fontWeight: 600, color: '#6d28d9' }}>
                              {new Set([
                                ...outgoing.map((e: DependencyEdge) => getNodeDetails(e.target_id).namespace),
                                ...incoming.map((e: DependencyEdge) => getNodeDetails(e.source_id).namespace)
                              ].filter(Boolean)).size}
                            </div>
                            <div style={{ fontSize: 9, color: isDark ? '#a0a0a0' : '#666' }}>Namespaces</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })() : null,  // End lazy render for connections tab
              },
            ]}
          />
          </>
        );
      })()}
    </Drawer>
    )}
    </ReactFlowProvider>
    </ConfigProvider>
  );
};

// Main component - ReactFlowProvider is now inside MapInner with key
const Map: React.FC = () => {
  return <MapInner />;
};

export default Map;
