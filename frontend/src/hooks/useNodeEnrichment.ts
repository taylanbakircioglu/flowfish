/**
 * useNodeEnrichment - Custom hook for enriching map nodes with event data
 * 
 * This hook aggregates data from multiple event sources to provide
 * rich contextual information for each node in the dependency map.
 */

import { useMemo, useCallback } from 'react';
import {
  useGetDnsQueriesQuery,
  useGetSniEventsQuery,
  useGetSecurityEventsQuery,
  useGetProcessEventsQuery,
  useGetFileEventsQuery,
  useGetBindEventsQuery,
  useGetMountEventsQuery,
  useGetOomEventsQuery,
  DnsQueryEvent,
  SniEvent,
  SecurityEvent,
  ProcessEvent,
  FileEvent,
  BindEvent,
  MountEvent,
  OomEvent,
} from '../store/api/eventsApi';

// Enrichment data for a single node
export interface NodeEnrichmentData {
  // DNS data
  dnsQueryCount: number;
  dnsFailureCount: number;
  uniqueDnsQueries: string[];
  externalDomains: string[];
  
  // TLS/SNI data
  tlsConnectionCount: number;
  tlsServerNames: string[];
  tlsVersions: string[];
  
  // Security data
  securityEventCount: number;
  capabilityChecks: string[];
  deniedCapabilities: string[];
  hasSecurityViolations: boolean;
  
  // OOM data
  oomKillCount: number;
  lastOomTime?: string;
  
  // Process data
  processEventCount: number;
  uniqueProcesses: string[];
  execCount: number;
  
  // File I/O data
  fileEventCount: number;
  fileOperations: Record<string, number>; // operation -> count
  configFileAccess: boolean;
  
  // Bind data (listening ports)
  bindEventCount: number;
  listeningPorts: number[];
  
  // Mount data
  mountEventCount: number;
  volumeMounts: string[];
  
  // Calculated metrics
  activityLevel: 'low' | 'medium' | 'high' | 'critical';
  riskLevel: 'safe' | 'warning' | 'danger';
  
  // Raw events for detail view
  rawDnsEvents: DnsQueryEvent[];
  rawSniEvents: SniEvent[];
  rawSecurityEvents: SecurityEvent[];
  rawProcessEvents: ProcessEvent[];
  rawFileEvents: FileEvent[];
  rawBindEvents: BindEvent[];
  rawMountEvents: MountEvent[];
  rawOomEvents: OomEvent[];
}

// Aggregated enrichment data keyed by pod name or namespace:pod
export type NodeEnrichmentMap = Map<string, NodeEnrichmentData>;

// Known cloud service IP ranges and domains for external node enrichment
const KNOWN_SERVICES: Record<string, { name: string; icon: string; color: string }> = {
  // AWS
  'amazonaws.com': { name: 'AWS', icon: '☁️', color: '#FF9900' },
  's3.': { name: 'S3', icon: '🪣', color: '#569A31' },
  'ec2.': { name: 'EC2', icon: '🖥️', color: '#FF9900' },
  'rds.': { name: 'RDS', icon: '🗄️', color: '#527FFF' },
  'elasticache': { name: 'ElastiCache', icon: '⚡', color: '#C925D1' },
  'sqs.': { name: 'SQS', icon: '📬', color: '#FF4F8B' },
  'sns.': { name: 'SNS', icon: '📢', color: '#FF4F8B' },
  'lambda': { name: 'Lambda', icon: '⚡', color: '#FF9900' },
  
  // Google Cloud
  'googleapis.com': { name: 'Google Cloud', icon: '🌐', color: '#4285F4' },
  'google.com': { name: 'Google', icon: '🔍', color: '#4285F4' },
  'gstatic.com': { name: 'Google Static', icon: '📦', color: '#4285F4' },
  
  // Azure
  'azure.com': { name: 'Azure', icon: '☁️', color: '#0078D4' },
  'microsoft.com': { name: 'Microsoft', icon: '🪟', color: '#0078D4' },
  'windows.net': { name: 'Azure', icon: '☁️', color: '#0078D4' },
  
  // Other common services
  'cloudflare': { name: 'Cloudflare', icon: '🛡️', color: '#F38020' },
  'github.com': { name: 'GitHub', icon: '🐙', color: '#24292E' },
  'docker.io': { name: 'Docker Hub', icon: '🐳', color: '#2496ED' },
  'docker.com': { name: 'Docker', icon: '🐳', color: '#2496ED' },
  'gcr.io': { name: 'GCR', icon: '📦', color: '#4285F4' },
  'quay.io': { name: 'Quay', icon: '📦', color: '#40B4E5' },
  'k8s.io': { name: 'Kubernetes', icon: '☸️', color: '#326CE5' },
  'kubernetes': { name: 'Kubernetes', icon: '☸️', color: '#326CE5' },
  'datadog': { name: 'Datadog', icon: '🐕', color: '#632CA6' },
  'newrelic': { name: 'New Relic', icon: '📊', color: '#008C99' },
  'grafana': { name: 'Grafana', icon: '📈', color: '#F46800' },
  'prometheus': { name: 'Prometheus', icon: '🔥', color: '#E6522C' },
  'elastic': { name: 'Elasticsearch', icon: '🔍', color: '#FEC514' },
  'mongodb': { name: 'MongoDB', icon: '🍃', color: '#47A248' },
  'postgres': { name: 'PostgreSQL', icon: '🐘', color: '#336791' },
  'mysql': { name: 'MySQL', icon: '🐬', color: '#4479A1' },
  'redis': { name: 'Redis', icon: '🔴', color: '#DC382D' },
  'rabbitmq': { name: 'RabbitMQ', icon: '🐰', color: '#FF6600' },
  'kafka': { name: 'Kafka', icon: '📨', color: '#231F20' },
};

// Detect known service from domain or IP
export function detectKnownService(domain: string): { name: string; icon: string; color: string } | null {
  const lowerDomain = domain.toLowerCase();
  
  for (const [pattern, service] of Object.entries(KNOWN_SERVICES)) {
    if (lowerDomain.includes(pattern)) {
      return service;
    }
  }
  
  return null;
}

// Create empty enrichment data
function createEmptyEnrichment(): NodeEnrichmentData {
  return {
    dnsQueryCount: 0,
    dnsFailureCount: 0,
    uniqueDnsQueries: [],
    externalDomains: [],
    tlsConnectionCount: 0,
    tlsServerNames: [],
    tlsVersions: [],
    securityEventCount: 0,
    capabilityChecks: [],
    deniedCapabilities: [],
    hasSecurityViolations: false,
    oomKillCount: 0,
    processEventCount: 0,
    uniqueProcesses: [],
    execCount: 0,
    fileEventCount: 0,
    fileOperations: {},
    configFileAccess: false,
    bindEventCount: 0,
    listeningPorts: [],
    mountEventCount: 0,
    volumeMounts: [],
    activityLevel: 'low',
    riskLevel: 'safe',
    rawDnsEvents: [],
    rawSniEvents: [],
    rawSecurityEvents: [],
    rawProcessEvents: [],
    rawFileEvents: [],
    rawBindEvents: [],
    rawMountEvents: [],
    rawOomEvents: [],
  };
}

// Calculate activity level based on event counts
function calculateActivityLevel(data: NodeEnrichmentData): 'low' | 'medium' | 'high' | 'critical' {
  const totalEvents = 
    data.dnsQueryCount + 
    data.tlsConnectionCount + 
    data.processEventCount + 
    data.fileEventCount + 
    data.securityEventCount;
  
  if (totalEvents > 1000) return 'critical';
  if (totalEvents > 100) return 'high';
  if (totalEvents > 10) return 'medium';
  return 'low';
}

// Calculate risk level based on security events
function calculateRiskLevel(data: NodeEnrichmentData): 'safe' | 'warning' | 'danger' {
  if (data.oomKillCount > 0 || data.hasSecurityViolations) return 'danger';
  if (data.deniedCapabilities.length > 0 || data.dnsFailureCount > 5) return 'warning';
  return 'safe';
}

// Hook parameters
interface UseNodeEnrichmentParams {
  clusterId?: number;
  analysisId?: number;
  enabled?: boolean;
}

// Main hook
export function useNodeEnrichment({ clusterId, analysisId, enabled = true }: UseNodeEnrichmentParams) {
  // Fetch all event types in parallel
  // For multi-cluster analysis: clusterId may be undefined, backend uses analysisId to resolve clusters
  // For single-cluster analysis: clusterId is provided
  const queryParams = { 
    cluster_id: clusterId, // Optional: undefined for multi-cluster 
    analysis_id: analysisId, 
    limit: 1000 // Get up to 1000 events for aggregation
  };
  
  // Skip if not enabled OR if neither clusterId nor analysisId is provided
  // Multi-cluster: clusterId undefined, analysisId provided -> OK
  // Single-cluster: clusterId provided -> OK
  const skip = !enabled || (!clusterId && !analysisId);
  
  const { data: dnsData, isLoading: dnsLoading } = useGetDnsQueriesQuery(queryParams, { skip });
  const { data: sniData, isLoading: sniLoading } = useGetSniEventsQuery(queryParams, { skip });
  const { data: securityData, isLoading: securityLoading } = useGetSecurityEventsQuery(queryParams, { skip });
  const { data: processData, isLoading: processLoading } = useGetProcessEventsQuery(queryParams, { skip });
  const { data: fileData, isLoading: fileLoading } = useGetFileEventsQuery(queryParams, { skip });
  const { data: bindData, isLoading: bindLoading } = useGetBindEventsQuery(queryParams, { skip });
  const { data: mountData, isLoading: mountLoading } = useGetMountEventsQuery(queryParams, { skip });
  const { data: oomData, isLoading: oomLoading } = useGetOomEventsQuery(queryParams, { skip });
  
  const isLoading = dnsLoading || sniLoading || securityLoading || processLoading || 
                    fileLoading || bindLoading || mountLoading || oomLoading;
  
  // Aggregate data by pod
  const enrichmentMap = useMemo<NodeEnrichmentMap>(() => {
    const map = new Map<string, NodeEnrichmentData>();
    
    // Helper to get or create enrichment data for a pod
    const getOrCreate = (pod: string, namespace: string): NodeEnrichmentData => {
      const key = `${namespace}/${pod}`;
      if (!map.has(key)) {
        map.set(key, createEmptyEnrichment());
      }
      return map.get(key)!;
    };
    
    // Process DNS queries
    if (dnsData?.queries) {
      for (const event of dnsData.queries) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.dnsQueryCount++;
        enrichment.rawDnsEvents.push(event);
        
        if (event.response_code !== 'NOERROR' && event.response_code !== '0') {
          enrichment.dnsFailureCount++;
        }
        
        if (!enrichment.uniqueDnsQueries.includes(event.query_name)) {
          enrichment.uniqueDnsQueries.push(event.query_name);
          
          // Check if it's an external domain (not .svc.cluster.local)
          if (!event.query_name.includes('.svc.cluster.local') && 
              !event.query_name.includes('.local') &&
              event.query_name.includes('.')) {
            enrichment.externalDomains.push(event.query_name);
          }
        }
      }
    }
    
    // Process SNI events
    if (sniData?.events) {
      for (const event of sniData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.tlsConnectionCount++;
        enrichment.rawSniEvents.push(event);
        
        const serverName = event.server_name || event.sni_name || '';
        if (serverName && !enrichment.tlsServerNames.includes(serverName)) {
          enrichment.tlsServerNames.push(serverName);
        }
        
        if (event.tls_version && !enrichment.tlsVersions.includes(event.tls_version)) {
          enrichment.tlsVersions.push(event.tls_version);
        }
      }
    }
    
    // Process security events
    if (securityData?.events) {
      for (const event of securityData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.securityEventCount++;
        enrichment.rawSecurityEvents.push(event);
        
        if (event.capability && !enrichment.capabilityChecks.includes(event.capability)) {
          enrichment.capabilityChecks.push(event.capability);
          
          if (event.verdict === 'denied' && !enrichment.deniedCapabilities.includes(event.capability)) {
            enrichment.deniedCapabilities.push(event.capability);
            enrichment.hasSecurityViolations = true;
          }
        }
      }
    }
    
    // Process process events
    if (processData?.events) {
      for (const event of processData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.processEventCount++;
        enrichment.rawProcessEvents.push(event);
        
        if (event.comm && !enrichment.uniqueProcesses.includes(event.comm)) {
          enrichment.uniqueProcesses.push(event.comm);
        }
        
        if (event.event_subtype === 'exec') {
          enrichment.execCount++;
        }
      }
    }
    
    // Process file events
    if (fileData?.events) {
      for (const event of fileData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.fileEventCount++;
        enrichment.rawFileEvents.push(event);
        
        enrichment.fileOperations[event.operation] = 
          (enrichment.fileOperations[event.operation] || 0) + 1;
        
        // Check for config file access
        if (event.file_path.includes('/etc/') || 
            event.file_path.includes('/config') ||
            event.file_path.endsWith('.conf') ||
            event.file_path.endsWith('.yaml') ||
            event.file_path.endsWith('.yml') ||
            event.file_path.endsWith('.json')) {
          enrichment.configFileAccess = true;
        }
      }
    }
    
    // Process bind events
    if (bindData?.events) {
      for (const event of bindData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.bindEventCount++;
        enrichment.rawBindEvents.push(event);
        
        if (!enrichment.listeningPorts.includes(event.bind_port)) {
          enrichment.listeningPorts.push(event.bind_port);
        }
      }
    }
    
    // Process mount events
    if (mountData?.events) {
      for (const event of mountData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.mountEventCount++;
        enrichment.rawMountEvents.push(event);
        
        if (!enrichment.volumeMounts.includes(event.target)) {
          enrichment.volumeMounts.push(event.target);
        }
      }
    }
    
    // Process OOM events
    if (oomData?.events) {
      for (const event of oomData.events) {
        const enrichment = getOrCreate(event.pod, event.namespace);
        enrichment.oomKillCount++;
        enrichment.rawOomEvents.push(event);
        enrichment.lastOomTime = event.timestamp;
      }
    }
    
    // Calculate metrics for each node
    map.forEach((data) => {
      data.activityLevel = calculateActivityLevel(data);
      data.riskLevel = calculateRiskLevel(data);
    });
    
    return map;
  }, [dnsData, sniData, securityData, processData, fileData, bindData, mountData, oomData]);
  
  // Helper to get enrichment for a specific node
  // Supports both exact match and partial match (for deployment names vs full pod names)
  // CRITICAL: useCallback to prevent infinite re-renders in dependent useEffects
  const getNodeEnrichment = useCallback((nodeName: string, namespace: string): NodeEnrichmentData | undefined => {
    if (!nodeName || !namespace) return undefined;
    
    // Try exact match first
    const exactKey = `${namespace}/${nodeName}`;
    if (enrichmentMap.has(exactKey)) {
      return enrichmentMap.get(exactKey);
    }
    
    // Extract base name by removing common suffixes:
    // - ReplicaSet suffix: deployment-abc123de-xyz
    // - StatefulSet suffix: sts-0, sts-1
    // - Job suffix: job-12345-abc
    const getBaseName = (name: string): string => {
      // Remove random hash suffix (e.g., -abc123de-xyz or -abc123de)
      let base = name.replace(/-[a-z0-9]{8,10}-[a-z0-9]{5}$/, '');
      base = base.replace(/-[a-z0-9]{8,10}$/, '');
      // Keep StatefulSet indices but remove them for matching (-0, -1, etc)
      base = base.replace(/-\d+$/, '');
      return base;
    };
    
    const nodeBaseName = getBaseName(nodeName);
    
    // Try partial match - node name might be deployment name, pods have random suffixes
    // e.g., nodeName="api-gateway", actual pod="api-gateway-5d8f9b-xyz"
    let matchingKeys: string[] = [];
    
    enrichmentMap.forEach((_, key) => {
      const [keyNamespace, keyPod] = key.split('/');
      
      // Must be same namespace
      if (keyNamespace !== namespace) return;
      
      const keyBaseName = getBaseName(keyPod);
      
      // Match if:
      // 1. Exact pod match
      // 2. Base names match
      // 3. One starts with the other (handles partial names)
      if (keyPod === nodeName || 
          keyBaseName === nodeBaseName ||
          keyPod.startsWith(nodeName) || 
          nodeName.startsWith(keyPod) ||
          keyBaseName.startsWith(nodeBaseName) ||
          nodeBaseName.startsWith(keyBaseName)) {
        matchingKeys.push(key);
      }
    });
    
    // If we found partial matches, aggregate them into one result
    if (matchingKeys.length > 0) {
      // Aggregate all matching pods into one result
      const aggregated = createEmptyEnrichment();
      
      for (const key of matchingKeys) {
        const data = enrichmentMap.get(key);
        if (!data) continue;
        
        // Aggregate all matching data
        {
          // Aggregate counts
          aggregated.dnsQueryCount += data.dnsQueryCount;
          aggregated.dnsFailureCount += data.dnsFailureCount;
          aggregated.tlsConnectionCount += data.tlsConnectionCount;
          aggregated.securityEventCount += data.securityEventCount;
          aggregated.processEventCount += data.processEventCount;
          aggregated.fileEventCount += data.fileEventCount;
          aggregated.bindEventCount += data.bindEventCount;
          aggregated.mountEventCount += data.mountEventCount;
          aggregated.oomKillCount += data.oomKillCount;
          aggregated.execCount += data.execCount;
          
          // Merge arrays (avoiding duplicates for important ones)
          data.uniqueDnsQueries.forEach(q => {
            if (!aggregated.uniqueDnsQueries.includes(q)) aggregated.uniqueDnsQueries.push(q);
          });
          data.externalDomains.forEach(d => {
            if (!aggregated.externalDomains.includes(d)) aggregated.externalDomains.push(d);
          });
          data.tlsServerNames.forEach(s => {
            if (!aggregated.tlsServerNames.includes(s)) aggregated.tlsServerNames.push(s);
          });
          data.tlsVersions.forEach(v => {
            if (!aggregated.tlsVersions.includes(v)) aggregated.tlsVersions.push(v);
          });
          data.capabilityChecks.forEach(c => {
            if (!aggregated.capabilityChecks.includes(c)) aggregated.capabilityChecks.push(c);
          });
          data.deniedCapabilities.forEach(c => {
            if (!aggregated.deniedCapabilities.includes(c)) aggregated.deniedCapabilities.push(c);
          });
          data.uniqueProcesses.forEach(p => {
            if (!aggregated.uniqueProcesses.includes(p)) aggregated.uniqueProcesses.push(p);
          });
          data.listeningPorts.forEach(p => {
            if (!aggregated.listeningPorts.includes(p)) aggregated.listeningPorts.push(p);
          });
          data.volumeMounts.forEach(m => {
            if (!aggregated.volumeMounts.includes(m)) aggregated.volumeMounts.push(m);
          });
          
          // Merge file operations
          Object.entries(data.fileOperations).forEach(([op, count]) => {
            aggregated.fileOperations[op] = (aggregated.fileOperations[op] || 0) + count;
          });
          
          // Merge raw events (limit to avoid memory issues)
          if (aggregated.rawDnsEvents.length < 50) {
            aggregated.rawDnsEvents.push(...data.rawDnsEvents.slice(0, 50 - aggregated.rawDnsEvents.length));
          }
          if (aggregated.rawSniEvents.length < 50) {
            aggregated.rawSniEvents.push(...data.rawSniEvents.slice(0, 50 - aggregated.rawSniEvents.length));
          }
          if (aggregated.rawSecurityEvents.length < 50) {
            aggregated.rawSecurityEvents.push(...data.rawSecurityEvents.slice(0, 50 - aggregated.rawSecurityEvents.length));
          }
          if (aggregated.rawProcessEvents.length < 50) {
            aggregated.rawProcessEvents.push(...data.rawProcessEvents.slice(0, 50 - aggregated.rawProcessEvents.length));
          }
          if (aggregated.rawFileEvents.length < 50) {
            aggregated.rawFileEvents.push(...data.rawFileEvents.slice(0, 50 - aggregated.rawFileEvents.length));
          }
          if (aggregated.rawBindEvents.length < 50) {
            aggregated.rawBindEvents.push(...data.rawBindEvents.slice(0, 50 - aggregated.rawBindEvents.length));
          }
          if (aggregated.rawMountEvents.length < 50) {
            aggregated.rawMountEvents.push(...data.rawMountEvents.slice(0, 50 - aggregated.rawMountEvents.length));
          }
          if (aggregated.rawOomEvents.length < 20) {
            aggregated.rawOomEvents.push(...data.rawOomEvents.slice(0, 20 - aggregated.rawOomEvents.length));
          }
          
          // Update flags
          if (data.hasSecurityViolations) aggregated.hasSecurityViolations = true;
          if (data.configFileAccess) aggregated.configFileAccess = true;
          if (data.lastOomTime) aggregated.lastOomTime = data.lastOomTime;
        }
      }
      
      // Calculate metrics
      aggregated.activityLevel = calculateActivityLevel(aggregated);
      aggregated.riskLevel = calculateRiskLevel(aggregated);
      
      return aggregated;
    }
    
    return undefined;
  }, [enrichmentMap]);
  
  // Get all pods with any enrichment data
  const enrichedPods = useMemo(() => Array.from(enrichmentMap.keys()), [enrichmentMap]);
  
  // Summary statistics with limit awareness
  const summary = useMemo(() => {
    let totalDns = 0;
    let totalTls = 0;
    let totalSecurity = 0;
    let totalOom = 0;
    let nodesWithIssues = 0;
    
    enrichmentMap.forEach((data) => {
      totalDns += data.dnsQueryCount;
      totalTls += data.tlsConnectionCount;
      totalSecurity += data.securityEventCount;
      totalOom += data.oomKillCount;
      if (data.riskLevel !== 'safe') nodesWithIssues++;
    });
    
    // Check if we hit the limit (1000 events per type)
    const LIMIT = 1000;
    const dnsLimitReached = (dnsData?.queries?.length ?? 0) >= LIMIT;
    const tlsLimitReached = (sniData?.events?.length ?? 0) >= LIMIT;
    const securityLimitReached = (securityData?.events?.length ?? 0) >= LIMIT;
    
    return {
      totalDnsQueries: totalDns,
      totalTlsConnections: totalTls,
      totalSecurityEvents: totalSecurity,
      totalOomKills: totalOom,
      nodesWithIssues,
      enrichedNodeCount: enrichmentMap.size,
      // Limit info for display
      dnsLimitReached,
      tlsLimitReached,
      securityLimitReached,
      // Actual totals from API (if available)
      actualDnsTotal: dnsData?.total,
      actualTlsTotal: sniData?.total,
      actualSecurityTotal: securityData?.total,
    };
  }, [enrichmentMap, dnsData, sniData, securityData]);
  
  return {
    enrichmentMap,
    getNodeEnrichment,
    enrichedPods,
    summary,
    isLoading,
  };
}

export default useNodeEnrichment;

