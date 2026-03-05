import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { 
  Card, 
  Typography, 
  Space, 
  Select, 
  Button, 
  Radio, 
  Row, 
  Col,
  Table,
  Tag,
  Alert,
  Spin,
  Empty,
  Divider,
  Statistic,
  Badge,
  Switch,
  Tooltip,
  Modal,
  Collapse,
  Timeline,
  List,
  Progress,
  message,
  Tabs,
  theme,
  Form,
  Input,
  DatePicker,
  TimePicker,
  Popconfirm,
  InputNumber,
  Checkbox,
} from 'antd';
import { 
  ThunderboltOutlined,
  AimOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  DownloadOutlined,
  PlayCircleOutlined,
  ClusterOutlined,
  ApiOutlined,
  GlobalOutlined,
  AppstoreOutlined,
  ContainerOutlined,
  CloudServerOutlined,
  InfoCircleOutlined,
  SafetyCertificateOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  RollbackOutlined,
  ExpandOutlined,
  CodeOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  FireOutlined,
  HddOutlined,
  LinkOutlined,
  SettingOutlined,
  SyncOutlined,
  LockOutlined,
  DashboardOutlined,
  ScheduleOutlined,
  PlusOutlined,
  EditOutlined,
  PauseCircleOutlined,
  CalendarOutlined,
  BellOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import { useGetClustersQuery } from '../store/api/clusterApi';
import { useGetAnalysesQuery } from '../store/api/analysisApi';
import { useGetDependencyGraphQuery } from '../store/api/communicationApi';
// Note: We now use graph data (discovered resources) instead of direct cluster queries
// This ensures we only show resources that were actually discovered during the analysis
import { 
  useGenerateNetworkPolicyMutation,
  useRunImpactSimulationMutation,
  useGetScheduledSimulationsQuery,
  useCreateScheduledSimulationMutation,
  useCancelScheduledSimulationMutation,
  useRunScheduledSimulationNowMutation,
  useGetSimulationHistoryQuery,
  useDeleteSimulationHistoryEntryMutation,
  type AffectedService,
  type ImpactLevel,
  type ImpactCategory,
  type NoDependencyInfo,
  type ChangeType,
  type ScheduledSimulation,
  type SimulationHistoryEntry,
} from '../store/api/simulationApi';
import { Analysis } from '../types';
import NetworkPolicyBuilder from '../components/NetworkPolicyBuilder';
import ImpactFlowDiagram from '../components/ImpactFlowDiagram';
import { colors } from '../styles/colors';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;
const { TabPane } = Tabs;
const { useToken } = theme;

// =============================================================================
// Constants
// =============================================================================

// Change types for simulation
const changeTypes = [
  { key: 'delete', label: 'Delete / Remove', description: 'Completely remove the target from cluster', icon: '🗑️', category: 'destructive' },
  { key: 'scale_down', label: 'Scale Down (replicas: 0)', description: 'Scale deployment to zero replicas', icon: '📉', category: 'scaling' },
  { key: 'network_isolate', label: 'Network Isolation', description: 'Apply network policy to isolate target', icon: '🔒', category: 'network' },
  { key: 'resource_change', label: 'Resource Limit Change', description: 'Modify CPU/Memory limits', icon: '📊', category: 'resource' },
  { key: 'port_change', label: 'Port Change', description: 'Change exposed ports', icon: '🔌', category: 'network' },
  { key: 'config_change', label: 'Configuration Change', description: 'Modify ConfigMap/Secret/Environment', icon: '⚙️', category: 'configuration' },
  { key: 'image_update', label: 'Image Update', description: 'Update container image version', icon: '📦', category: 'deployment' },
  { key: 'network_policy_apply', label: 'Apply Network Policy', description: 'Simulate applying a new network policy', icon: '🛡️', category: 'network', advanced: true },
  { key: 'network_policy_remove', label: 'Remove Network Policy', description: 'Simulate removing an existing network policy', icon: '🔓', category: 'network', advanced: true },
];

// =============================================================================
// Chaos Engineering Templates
// Pre-configured scenarios for common chaos experiments
// =============================================================================
interface ChaosTemplate {
  id: string;
  name: string;
  description: string;
  icon: 'pod-kill' | 'network' | 'fire' | 'memory' | 'chain' | 'config' | 'dns' | 'sync';
  category: 'availability' | 'network' | 'resource' | 'security';
  severity: 'low' | 'medium' | 'high';
  changeType: string;
  targetType: string;
  estimatedImpact: string;
  rollbackTime: string;
  prerequisites: string[];
  steps: string[];
}

// Icon renderer for chaos templates - uses Flowfish theme colors
const chaosTemplateIcons: Record<string, React.ReactNode> = {
  'pod-kill': <DeleteOutlined style={{ color: '#e57373' }} />,
  'network': <DisconnectOutlined style={{ color: '#2eb8b8' }} />,
  'fire': <FireOutlined style={{ color: '#d4a844' }} />,
  'memory': <HddOutlined style={{ color: '#e57373' }} />,
  'chain': <LinkOutlined style={{ color: '#3cc9c4' }} />,
  'config': <SettingOutlined style={{ color: '#64b5f6' }} />,
  'dns': <GlobalOutlined style={{ color: '#2eb8b8' }} />,
  'sync': <SyncOutlined style={{ color: '#4caf50' }} />,
};

const chaosTemplates: ChaosTemplate[] = [
  {
    id: 'pod-kill',
    name: 'Pod Termination',
    description: 'Simulate sudden pod failure to test self-healing and resilience',
    icon: 'pod-kill',
    category: 'availability',
    severity: 'high',
    changeType: 'delete',
    targetType: 'pod',
    estimatedImpact: 'Service may experience brief downtime until pod restarts',
    rollbackTime: 'Automatic (Pod restart)',
    prerequisites: ['Deployment with replicas > 1', 'Health checks configured'],
    steps: [
      'Select target pod',
      'Verify replica count > 1',
      'Execute pod deletion',
      'Monitor pod recreation',
      'Verify service continuity'
    ]
  },
  {
    id: 'network-partition',
    name: 'Network Partition',
    description: 'Isolate service from network to test circuit breaker patterns',
    icon: 'network',
    category: 'network',
    severity: 'high',
    changeType: 'network_isolate',
    targetType: 'deployment',
    estimatedImpact: 'All network traffic to/from target will be blocked',
    rollbackTime: '~30 seconds (Policy removal)',
    prerequisites: ['Network Policy support in cluster', 'Circuit breakers configured'],
    steps: [
      'Select target deployment',
      'Apply deny-all network policy',
      'Monitor upstream service behavior',
      'Verify circuit breaker activation',
      'Remove network policy'
    ]
  },
  {
    id: 'cpu-stress',
    name: 'CPU Stress Test',
    description: 'Simulate high CPU utilization to test resource limits and throttling',
    icon: 'fire',
    category: 'resource',
    severity: 'medium',
    changeType: 'resource_change',
    targetType: 'deployment',
    estimatedImpact: 'Performance degradation, potential throttling',
    rollbackTime: '~1 minute (Resource restore)',
    prerequisites: ['Resource limits defined', 'HPA configured (optional)'],
    steps: [
      'Select target deployment',
      'Reduce CPU limits significantly',
      'Monitor pod performance',
      'Check HPA scaling behavior',
      'Restore original limits'
    ]
  },
  {
    id: 'memory-pressure',
    name: 'Memory Pressure',
    description: 'Simulate memory exhaustion to test OOM handling',
    icon: 'memory',
    category: 'resource',
    severity: 'high',
    changeType: 'resource_change',
    targetType: 'deployment',
    estimatedImpact: 'OOM kills possible, service restart',
    rollbackTime: '~2 minutes (Pod restart + resource restore)',
    prerequisites: ['Memory limits defined', 'OOM kill handling'],
    steps: [
      'Select target deployment',
      'Reduce memory limits below current usage',
      'Monitor for OOM events',
      'Verify graceful degradation',
      'Restore original limits'
    ]
  },
  {
    id: 'dependency-failure',
    name: 'Dependency Failure',
    description: 'Simulate downstream service failure to test fallback mechanisms',
    icon: 'chain',
    category: 'availability',
    severity: 'medium',
    changeType: 'scale_down',
    targetType: 'deployment',
    estimatedImpact: 'Upstream services may fail or degrade',
    rollbackTime: '~30 seconds (Scale up)',
    prerequisites: ['Fallback mechanisms in place', 'Timeout configurations'],
    steps: [
      'Identify critical dependency',
      'Scale dependency to 0 replicas',
      'Monitor upstream service behavior',
      'Verify fallback activation',
      'Scale dependency back up'
    ]
  },
  {
    id: 'config-drift',
    name: 'Configuration Drift',
    description: 'Simulate misconfiguration to test error handling',
    icon: 'config',
    category: 'availability',
    severity: 'low',
    changeType: 'config_change',
    targetType: 'deployment',
    estimatedImpact: 'Application behavior change, potential errors',
    rollbackTime: '~1 minute (Config restore)',
    prerequisites: ['Configuration backup', 'Error monitoring'],
    steps: [
      'Select target deployment',
      'Modify environment variable',
      'Monitor application logs',
      'Verify error handling',
      'Restore original configuration'
    ]
  },
  {
    id: 'dns-failure',
    name: 'DNS Resolution Failure',
    description: 'Simulate DNS issues to test service discovery resilience',
    icon: 'dns',
    category: 'network',
    severity: 'medium',
    changeType: 'network_policy_apply',
    targetType: 'deployment',
    estimatedImpact: 'Service discovery failures, connection timeouts',
    rollbackTime: '~30 seconds (Policy removal)',
    prerequisites: ['DNS caching configured', 'Retry mechanisms'],
    steps: [
      'Select target deployment',
      'Block DNS traffic (port 53)',
      'Monitor service discovery',
      'Verify retry behavior',
      'Remove DNS block'
    ]
  },
  {
    id: 'rolling-restart',
    name: 'Rolling Restart Chaos',
    description: 'Test deployment stability during rolling updates',
    icon: 'sync',
    category: 'availability',
    severity: 'low',
    changeType: 'image_update',
    targetType: 'deployment',
    estimatedImpact: 'Brief service disruption during rollout',
    rollbackTime: '~2 minutes (Rollback deployment)',
    prerequisites: ['Rolling update strategy', 'Readiness probes'],
    steps: [
      'Select target deployment',
      'Trigger image update',
      'Monitor rolling update progress',
      'Verify zero-downtime',
      'Rollback if needed'
    ]
  },
];

// =============================================================================
// Chaos Engineering Score Calculation
// Inspired by Gremlin's Reliability Score & LitmusChaos Resilience Probes
// Enhanced with intelligent analysis and contextual recommendations
// =============================================================================

interface ChaosScoreResult {
  score: number; // 0-100, higher = more risky
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  gradeColor: string;
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  factors: {
    name: string;
    impact: number;
    description: string;
    category: 'severity' | 'blast_radius' | 'dependency' | 'timing' | 'resilience';
  }[];
  recommendations: ChaosRecommendation[];
  insights: ChaosInsight[];
  readinessScore: number; // 0-100, how ready is the system for this chaos
  estimatedRecoveryTime: string;
}

interface ChaosRecommendation {
  id: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  category: 'pre-execution' | 'during-execution' | 'post-execution' | 'alternative';
  title: string;
  description: string;
  actionable: boolean;
  automatable: boolean;
}

interface ChaosInsight {
  id: string;
  type: 'risk' | 'opportunity' | 'warning' | 'info';
  title: string;
  description: string;
  relatedServices?: string[];
  confidence: number;
}

interface PrerequisiteCheckResult {
  id: string;
  name: string;
  status: 'passed' | 'failed' | 'warning' | 'unknown';
  message: string;
  critical: boolean;
}

// Intelligent Chaos Analysis Engine
class ChaosAnalysisEngine {
  private template: ChaosTemplate | null;
  private affectedServices: AffectedService[];
  private stats: { total: number; high: number; medium: number; low: number };
  private graphData: any;

  constructor(
    template: ChaosTemplate | null,
    affectedServices: AffectedService[],
    stats: { total: number; high: number; medium: number; low: number },
    graphData: any
  ) {
    this.template = template;
    this.affectedServices = affectedServices;
    this.stats = stats;
    this.graphData = graphData;
  }

  // Analyze service criticality based on dependency patterns
  private analyzeServiceCriticality(): { 
    criticalPaths: string[]; 
    singlePointsOfFailure: string[];
    highFanOutServices: string[];
  } {
    const criticalPaths: string[] = [];
    const singlePointsOfFailure: string[] = [];
    const highFanOutServices: string[] = [];

    // Identify services with many dependents (high fan-out = critical)
    const dependentCounts = new Map<string, number>();
    this.affectedServices.forEach(svc => {
      const key = `${svc.namespace}/${svc.name}`;
      dependentCounts.set(key, (dependentCounts.get(key) || 0) + 1);
    });

    dependentCounts.forEach((count, service) => {
      if (count >= 3) {
        highFanOutServices.push(service);
        if (count >= 5) {
          criticalPaths.push(service);
        }
      }
    });

    // Identify potential single points of failure
    const highImpactServices = this.affectedServices.filter(s => s.impact === 'high');
    highImpactServices.forEach(svc => {
      const hasFallback = this.affectedServices.some(
        other => other.name !== svc.name && 
                 other.namespace === svc.namespace && 
                 other.kind === svc.kind
      );
      if (!hasFallback) {
        singlePointsOfFailure.push(`${svc.namespace}/${svc.name}`);
      }
    });

    return { criticalPaths, singlePointsOfFailure, highFanOutServices };
  }

  // Analyze timing risk factors
  private analyzeTimingRisk(): { 
    isBusinessHours: boolean; 
    isWeekend: boolean;
    timingRiskScore: number;
    suggestedWindow: string;
  } {
    const now = new Date();
    const hour = now.getHours();
    const day = now.getDay();
    
    const isBusinessHours = hour >= 9 && hour <= 18;
    const isWeekend = day === 0 || day === 6;
    
    let timingRiskScore = 0;
    if (isBusinessHours && !isWeekend) {
      timingRiskScore = 30; // Peak risk during business hours
    } else if (!isWeekend && (hour >= 7 && hour <= 20)) {
      timingRiskScore = 20; // Moderate risk during extended hours
    } else {
      timingRiskScore = 5; // Low risk during off-hours
    }

    let suggestedWindow = 'Current time is acceptable';
    if (timingRiskScore > 20) {
      suggestedWindow = isWeekend 
        ? 'Consider waiting for early morning (2-6 AM)' 
        : 'Recommend scheduling for weekend or off-hours (10 PM - 6 AM)';
    }

    return { isBusinessHours, isWeekend, timingRiskScore, suggestedWindow };
  }

  // Analyze resilience patterns in affected services
  private analyzeResiliencePatterns(): {
    hasCircuitBreakers: boolean;
    hasRetryLogic: boolean;
    hasHealthChecks: boolean;
    resilienceScore: number;
    gaps: string[];
  } {
    const gaps: string[] = [];
    let resilienceScore = 50; // Base score

    // Check for common resilience patterns (simulated based on service metadata)
    const hasHealthChecks = this.affectedServices.some(s => 
      s.kind === 'Deployment' || s.kind === 'StatefulSet'
    );
    
    // Estimate based on service types and protocols
    const hasGrpcServices = this.affectedServices.some(s => 
      s.connection_details?.protocol?.toLowerCase().includes('grpc')
    );
    const hasHttpServices = this.affectedServices.some(s => 
      s.connection_details?.protocol?.toLowerCase().includes('http')
    );

    // Adjust score based on patterns
    if (hasHealthChecks) {
      resilienceScore += 15;
    } else {
      gaps.push('Health checks not detected on all services');
    }

    if (hasGrpcServices || hasHttpServices) {
      resilienceScore += 10; // Standard protocols usually have retry support
    }

    // Penalize for high-impact services without apparent redundancy
    const highImpactCount = this.stats.high;
    if (highImpactCount > 3) {
      resilienceScore -= 15;
      gaps.push(`${highImpactCount} high-impact services may lack redundancy`);
    }

    return {
      hasCircuitBreakers: resilienceScore > 60, // Estimate
      hasRetryLogic: hasGrpcServices || hasHttpServices,
      hasHealthChecks,
      resilienceScore: Math.max(0, Math.min(100, resilienceScore)),
      gaps,
    };
  }

  // Generate intelligent recommendations
  generateRecommendations(): ChaosRecommendation[] {
    const recommendations: ChaosRecommendation[] = [];
    const criticality = this.analyzeServiceCriticality();
    const timing = this.analyzeTimingRisk();
    const resilience = this.analyzeResiliencePatterns();

    // Pre-execution recommendations
    if (this.stats.high > 2) {
      recommendations.push({
        id: 'staging-first',
        priority: 'critical',
        category: 'pre-execution',
        title: 'Test in staging environment first',
        description: `With ${this.stats.high} high-impact services affected, validate the experiment in a non-production environment to understand failure modes.`,
        actionable: true,
        automatable: false,
      });
    }

    if (criticality.singlePointsOfFailure.length > 0) {
      recommendations.push({
        id: 'spof-warning',
        priority: 'critical',
        category: 'pre-execution',
        title: 'Address single points of failure',
        description: `Identified ${criticality.singlePointsOfFailure.length} potential single points of failure: ${criticality.singlePointsOfFailure.slice(0, 3).join(', ')}${criticality.singlePointsOfFailure.length > 3 ? '...' : ''}. Consider adding redundancy before chaos testing.`,
        actionable: true,
        automatable: false,
      });
    }

    if (timing.timingRiskScore > 20) {
      recommendations.push({
        id: 'timing-window',
        priority: 'high',
        category: 'pre-execution',
        title: 'Schedule for low-traffic window',
        description: timing.suggestedWindow,
        actionable: true,
        automatable: true,
      });
    }

    if (this.template?.severity === 'high') {
      recommendations.push({
        id: 'rollback-plan',
        priority: 'critical',
        category: 'pre-execution',
        title: 'Verify rollback procedure',
        description: `High-severity experiment requires tested rollback. Expected rollback time: ${this.template.rollbackTime}. Ensure team is familiar with the procedure.`,
        actionable: true,
        automatable: false,
      });
    }

    // During-execution recommendations
    if (this.stats.total > 5) {
      recommendations.push({
        id: 'incremental-rollout',
        priority: 'high',
        category: 'during-execution',
        title: 'Use incremental rollout',
        description: `With ${this.stats.total} affected services, consider targeting a subset first (canary approach) to limit blast radius.`,
        actionable: true,
        automatable: true,
      });
    }

    if (criticality.highFanOutServices.length > 0) {
      recommendations.push({
        id: 'monitor-hub-services',
        priority: 'high',
        category: 'during-execution',
        title: 'Monitor hub services closely',
        description: `Services with high fan-out (${criticality.highFanOutServices.slice(0, 2).join(', ')}) are critical paths. Set up dedicated monitoring dashboards.`,
        actionable: true,
        automatable: true,
      });
    }

    recommendations.push({
      id: 'real-time-metrics',
      priority: 'medium',
      category: 'during-execution',
      title: 'Enable real-time metrics collection',
      description: 'Ensure Prometheus/metrics endpoints are scraped at higher frequency during the experiment for accurate impact measurement.',
      actionable: true,
      automatable: true,
    });

    // Post-execution recommendations
    if (resilience.gaps.length > 0) {
      recommendations.push({
        id: 'address-gaps',
        priority: 'medium',
        category: 'post-execution',
        title: 'Address resilience gaps',
        description: `Identified gaps to address: ${resilience.gaps.join('; ')}`,
        actionable: true,
        automatable: false,
      });
    }

    recommendations.push({
      id: 'document-findings',
      priority: 'low',
      category: 'post-execution',
      title: 'Document findings and update runbooks',
      description: 'Record actual vs expected behavior, recovery time, and any unexpected cascading failures for future reference.',
      actionable: true,
      automatable: false,
    });

    // Alternative recommendations
    if (this.template?.severity === 'high' && this.stats.high > 3) {
      recommendations.push({
        id: 'alternative-approach',
        priority: 'medium',
        category: 'alternative',
        title: 'Consider a less aggressive experiment',
        description: 'Given the high blast radius, consider starting with a lower-severity variant (e.g., increased latency instead of complete failure).',
        actionable: true,
        automatable: false,
      });
    }

    if (this.stats.medium > 10) {
      recommendations.push({
        id: 'scope-reduction',
        priority: 'medium',
        category: 'alternative',
        title: 'Reduce experiment scope',
        description: `${this.stats.medium} indirectly affected services suggest wide cascade potential. Consider targeting a smaller subset or single namespace.`,
        actionable: true,
        automatable: false,
      });
    }

    // Sort by priority
    const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
    return recommendations.sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority]);
  }

  // Generate insights about the chaos experiment
  generateInsights(): ChaosInsight[] {
    const insights: ChaosInsight[] = [];
    const criticality = this.analyzeServiceCriticality();
    const resilience = this.analyzeResiliencePatterns();

    // Risk insights
    if (criticality.criticalPaths.length > 0) {
      insights.push({
        id: 'critical-path-risk',
        type: 'risk',
        title: 'Critical path services in blast radius',
        description: `${criticality.criticalPaths.length} services are on critical paths with multiple dependents. Failure will cascade.`,
        relatedServices: criticality.criticalPaths,
        confidence: 0.85,
      });
    }

    if (this.stats.high / Math.max(this.stats.total, 1) > 0.5) {
      insights.push({
        id: 'high-impact-ratio',
        type: 'risk',
        title: 'High proportion of direct dependencies',
        description: `${Math.round((this.stats.high / this.stats.total) * 100)}% of affected services have direct dependencies. Impact will be immediate and significant.`,
        confidence: 0.9,
      });
    }

    // Opportunity insights
    if (resilience.resilienceScore < 60) {
      insights.push({
        id: 'resilience-opportunity',
        type: 'opportunity',
        title: 'Opportunity to improve resilience',
        description: 'This experiment can reveal resilience gaps. Prepare to document failure modes for future hardening.',
        confidence: 0.75,
      });
    }

    if (this.template?.category === 'network') {
      insights.push({
        id: 'network-policy-validation',
        type: 'opportunity',
        title: 'Network policy validation opportunity',
        description: 'Network chaos can validate that fallback paths and timeouts are correctly configured.',
        confidence: 0.8,
      });
    }

    // Warning insights
    const namespaces = new Set(this.affectedServices.map(s => s.namespace));
    if (namespaces.size > 3) {
      insights.push({
        id: 'cross-namespace-impact',
        type: 'warning',
        title: 'Cross-namespace impact detected',
        description: `Experiment affects ${namespaces.size} namespaces. Coordinate with all team owners before execution.`,
        confidence: 0.95,
      });
    }

    // Info insights
    if (this.template) {
      insights.push({
        id: 'template-info',
        type: 'info',
        title: `${this.template.name} experiment characteristics`,
        description: `Category: ${this.template.category}, Estimated Impact: ${this.template.estimatedImpact}, Automated rollback: ${this.template.rollbackTime}`,
        confidence: 1,
      });
    }

    return insights;
  }

  // Calculate readiness score
  calculateReadinessScore(): number {
    const resilience = this.analyzeResiliencePatterns();
    const timing = this.analyzeTimingRisk();
    
    let score = 50; // Base readiness

    // Resilience contributes 40%
    score += (resilience.resilienceScore / 100) * 40;

    // Timing contributes 20%
    score += ((100 - timing.timingRiskScore) / 100) * 20;

    // Blast radius penalty (up to -20%)
    const blastRadiusPenalty = Math.min(20, this.stats.total * 2);
    score -= blastRadiusPenalty;

    // High impact services penalty (up to -15%)
    const highImpactPenalty = Math.min(15, this.stats.high * 5);
    score -= highImpactPenalty;

    return Math.max(0, Math.min(100, Math.round(score)));
  }

  // Estimate recovery time
  estimateRecoveryTime(): string {
    if (!this.template) return 'Unknown';

    const baseTime = this.template.rollbackTime;
    
    // Adjust based on affected services
    if (this.stats.high > 5) {
      return `${baseTime} + 5-10 min (cascade recovery)`;
    }
    if (this.stats.total > 10) {
      return `${baseTime} + 2-5 min (propagation delay)`;
    }
    
    return baseTime;
  }
}

// Calculate Chaos Score based on template, affected services, and system state
const calculateChaosScore = (
  template: ChaosTemplate | null,
  affectedServices: AffectedService[],
  stats: { total: number; high: number; medium: number; low: number },
  graphData: any
): ChaosScoreResult => {
  const engine = new ChaosAnalysisEngine(template, affectedServices, stats, graphData);
  
  const factors: ChaosScoreResult['factors'] = [];
  let totalScore = 0;

  // Factor 1: Template Severity (0-25 points)
  if (template) {
    const severityScores = { low: 8, medium: 16, high: 25 };
    const severityScore = severityScores[template.severity];
    totalScore += severityScore;
    factors.push({
      name: 'Template Severity',
      impact: severityScore,
      description: `${template.name} is classified as ${template.severity} severity`,
      category: 'severity',
    });
  }

  // Factor 2: Blast Radius - affected services count (0-30 points)
  const blastRadiusScore = Math.min(30, stats.total * 3);
  totalScore += blastRadiusScore;
  factors.push({
    name: 'Blast Radius',
    impact: blastRadiusScore,
    description: `${stats.total} services in impact zone`,
    category: 'blast_radius',
  });

  // Factor 3: High Impact Services (0-25 points)
  const highImpactScore = Math.min(25, stats.high * 8);
  totalScore += highImpactScore;
  factors.push({
    name: 'Critical Services',
    impact: highImpactScore,
    description: `${stats.high} services with direct dependency (high impact)`,
    category: 'dependency',
  });

  // Factor 4: Cascade Depth - indirect dependencies (0-20 points)
  const cascadeScore = Math.min(20, stats.medium * 4);
  totalScore += cascadeScore;
  factors.push({
    name: 'Cascade Potential',
    impact: cascadeScore,
    description: `${stats.medium} services with indirect dependency (cascade risk)`,
    category: 'dependency',
  });

  // Factor 5: Timing Risk (new)
  const now = new Date();
  const hour = now.getHours();
  const isBusinessHours = hour >= 9 && hour <= 18 && now.getDay() !== 0 && now.getDay() !== 6;
  if (isBusinessHours && stats.high > 0) {
    const timingScore = 10;
    totalScore += timingScore;
    factors.push({
      name: 'Timing Risk',
      impact: timingScore,
      description: 'Executing during business hours increases user impact',
      category: 'timing',
    });
  }

  // Normalize to 0-100
  const normalizedScore = Math.min(100, totalScore);

  // Determine grade
  let grade: ChaosScoreResult['grade'];
  let gradeColor: string;
  let riskLevel: ChaosScoreResult['riskLevel'];

  if (normalizedScore <= 20) {
    grade = 'A'; gradeColor = colors.status.success; riskLevel = 'low';
  } else if (normalizedScore <= 40) {
    grade = 'B'; gradeColor = colors.charts.teal; riskLevel = 'low';
  } else if (normalizedScore <= 60) {
    grade = 'C'; gradeColor = colors.status.warning; riskLevel = 'medium';
  } else if (normalizedScore <= 80) {
    grade = 'D'; gradeColor = colors.charts.orange; riskLevel = 'high';
  } else {
    grade = 'F'; gradeColor = colors.status.error; riskLevel = 'critical';
  }

  // Generate intelligent recommendations and insights
  const recommendations = engine.generateRecommendations();
  const insights = engine.generateInsights();
  const readinessScore = engine.calculateReadinessScore();
  const estimatedRecoveryTime = engine.estimateRecoveryTime();

  return {
    score: normalizedScore,
    grade,
    gradeColor,
    riskLevel,
    factors,
    recommendations,
    insights,
    readinessScore,
    estimatedRecoveryTime,
  };
};

// Check prerequisites based on template and current system state
const checkPrerequisites = (
  template: ChaosTemplate | null,
  selectedTarget: any,
  graphData: any
): PrerequisiteCheckResult[] => {
  if (!template || !selectedTarget) return [];

  const results: PrerequisiteCheckResult[] = [];

  // Check each prerequisite from template
  template.prerequisites.forEach((prereq, index) => {
    const prereqLower = prereq.toLowerCase();
    let status: PrerequisiteCheckResult['status'] = 'unknown';
    let message = prereq;
    let critical = false;

    // Check replica count
    if (prereqLower.includes('replica') && prereqLower.includes('>')) {
      const replicas = selectedTarget.replicas || selectedTarget.spec?.replicas || 1;
      if (replicas > 1) {
        status = 'passed';
        message = `Replica count: ${replicas} (> 1)`;
      } else {
        status = 'failed';
        message = `Replica count: ${replicas} - Single point of failure!`;
        critical = true;
      }
    }
    // Check health checks
    else if (prereqLower.includes('health') || prereqLower.includes('probe')) {
      // Assume we check from graph data or target metadata
      const hasHealthChecks = selectedTarget.healthChecks || 
                              selectedTarget.spec?.template?.spec?.containers?.[0]?.readinessProbe;
      if (hasHealthChecks) {
        status = 'passed';
        message = 'Health checks configured';
      } else {
        status = 'warning';
        message = 'Health checks not detected - recovery monitoring may be limited';
      }
    }
    // Check circuit breaker
    else if (prereqLower.includes('circuit breaker')) {
      status = 'warning';
      message = 'Circuit breaker configuration - verify in service mesh settings';
    }
    // Check network policy support
    else if (prereqLower.includes('network policy')) {
      status = 'passed';
      message = 'Network Policy support available in cluster';
    }
    // Check fallback mechanisms
    else if (prereqLower.includes('fallback')) {
      status = 'warning';
      message = 'Fallback mechanisms - verify in application code';
    }
    // Check timeout configurations
    else if (prereqLower.includes('timeout')) {
      status = 'warning';
      message = 'Timeout configurations - verify client settings';
    }
    // Check resource limits
    else if (prereqLower.includes('resource') || prereqLower.includes('limit')) {
      const hasLimits = selectedTarget.resources?.limits || 
                        selectedTarget.spec?.template?.spec?.containers?.[0]?.resources?.limits;
      if (hasLimits) {
        status = 'passed';
        message = 'Resource limits defined';
      } else {
        status = 'warning';
        message = 'Resource limits not detected - OOM behavior may vary';
      }
    }
    // Check HPA
    else if (prereqLower.includes('hpa') || prereqLower.includes('autoscal')) {
      status = 'unknown';
      message = 'HPA status - check cluster autoscaling configuration';
    }
    // Default: unknown
    else {
      status = 'unknown';
      message = prereq;
    }

    results.push({
      id: `prereq-${index}`,
      name: prereq,
      status,
      message,
      critical,
    });
  });

  return results;
};

// =============================================================================
// Theme-aligned Color Constants
// Using Flowfish brand colors from styles/colors.ts
// =============================================================================

// Impact level colors - aligned with theme status colors
const impactColors: Record<string, string> = {
  high: colors.status.error,      // #ef4444 - Modern red
  medium: colors.status.warning,  // #f59e0b - Modern orange  
  low: colors.charts.yellow,      // #f59e0b - Yellow (lighter)
  none: colors.status.success,    // #10b981 - Modern green
};

// Impact category configurations - using theme-consistent colors
// IMPORTANT: Category and Impact Level must be consistent:
// - service_outage, connectivity_loss → Always shown with HIGH impact
// - cascade_risk → Shown with MEDIUM impact (potential, not actual outage)
// - performance_degradation → Shown with MEDIUM/LOW impact
const impactCategoryConfig: Record<string, { 
  color: string; 
  bgColor: string;  // Light background for cards
  iconType: 'exclamation' | 'api' | 'warning' | 'thunderbolt' | 'code' | 'safety' | 'appstore' | 'clock';
  label: string; 
  description: string;
  severity: 'critical' | 'warning' | 'info';
  expectedLevel: 'high' | 'medium' | 'low';
}> = {
  service_outage: {
    color: colors.status.error,
    bgColor: `${colors.status.error}08`,
    iconType: 'exclamation',
    label: 'Service Outage',
    description: 'Complete service unavailability - connections will fail',
    severity: 'critical',
    expectedLevel: 'high',
  },
  connectivity_loss: {
    color: colors.charts.orange,
    bgColor: `${colors.charts.orange}08`,
    iconType: 'api',
    label: 'Connectivity Loss',
    description: 'Network connectivity blocked - service running but unreachable',
    severity: 'critical',
    expectedLevel: 'high',
  },
  cascade_risk: {
    color: colors.status.warning,
    bgColor: `${colors.status.warning}08`,
    iconType: 'warning',
    label: 'Cascade Risk',
    description: 'Potential impact from upstream service failure - not a direct outage',
    severity: 'warning',
    expectedLevel: 'medium',
  },
  performance_degradation: {
    color: colors.status.warning,
    bgColor: `${colors.status.warning}08`,
    iconType: 'thunderbolt',
    label: 'Performance Impact',
    description: 'Slower responses, potential timeouts - no complete outage',
    severity: 'warning',
    expectedLevel: 'medium',
  },
  configuration_drift: {
    color: colors.charts.yellow,
    bgColor: `${colors.charts.yellow}06`,
    iconType: 'code',
    label: 'Configuration Change',
    description: 'Behavior changes - functionality may be affected',
    severity: 'warning',
    expectedLevel: 'medium',
  },
  security_exposure: {
    color: colors.charts.purple,
    bgColor: `${colors.charts.purple}08`,
    iconType: 'safety',
    label: 'Security Impact',
    description: 'Security posture change - no operational impact',
    severity: 'info',
    expectedLevel: 'low',
  },
  compatibility_risk: {
    color: colors.charts.blue,
    bgColor: `${colors.charts.blue}08`,
    iconType: 'appstore',
    label: 'Compatibility Risk',
    description: 'Version/API changes - may affect integrations',
    severity: 'warning',
    expectedLevel: 'medium',
  },
  transient_disruption: {
    color: colors.primary.main,
    bgColor: `${colors.primary.main}08`,
    iconType: 'clock',
    label: 'Transient Disruption',
    description: 'Brief interruption during rollout - auto-recovers',
    severity: 'info',
    expectedLevel: 'low',
  },
};

// Helper function to get icon component for category
const getCategoryIcon = (iconType: string, color: string): React.ReactNode => {
  const iconStyle = { color, fontSize: 14 };
  switch (iconType) {
    case 'exclamation': return <ExclamationCircleOutlined style={iconStyle} />;
    case 'api': return <ApiOutlined style={iconStyle} />;
    case 'warning': return <WarningOutlined style={iconStyle} />;
    case 'thunderbolt': return <ThunderboltOutlined style={iconStyle} />;
    case 'code': return <CodeOutlined style={iconStyle} />;
    case 'safety': return <SafetyCertificateOutlined style={iconStyle} />;
    case 'appstore': return <AppstoreOutlined style={iconStyle} />;
    case 'clock': return <ClockCircleOutlined style={iconStyle} />;
    default: return <InfoCircleOutlined style={iconStyle} />;
  }
};

// Change type to impact category mapping for frontend display
// IMPORTANT: Indirect dependencies should NEVER show "Service Outage" - they have CASCADE_RISK
const changeTypeImpactInfo: Record<string, {
  primaryCategory: string;       // For DIRECT dependencies
  indirectCategory: string;      // For INDIRECT dependencies (usually cascade_risk)
  headline: string;
  whatHappens: string;
  affectsIndirect: boolean;
}> = {
  delete: {
    primaryCategory: 'service_outage',
    indirectCategory: 'cascade_risk',  // Indirect = potential cascade, NOT outage
    headline: 'Complete Service Removal',
    whatHappens: 'All connections to this service will fail immediately. No automatic recovery.',
    affectsIndirect: true,
  },
  scale_down: {
    primaryCategory: 'service_outage',
    indirectCategory: 'cascade_risk',
    headline: '📉 Service Unavailable',
    whatHappens: 'Service will be unavailable until scaled back up. Queued requests may timeout.',
    affectsIndirect: true,
  },
  network_isolate: {
    primaryCategory: 'connectivity_loss',
    indirectCategory: 'cascade_risk',
    headline: '🔒 Network Isolation',
    whatHappens: 'Network traffic blocked. Service is running but unreachable from blocked sources.',
    affectsIndirect: false,
  },
  resource_change: {
    primaryCategory: 'performance_degradation',
    indirectCategory: 'performance_degradation',  // Same - just lower severity
    headline: '⚡ Performance Impact Only',
    whatHappens: 'May experience slower responses or resource constraints. NOT a complete outage.',
    affectsIndirect: false,
  },
  port_change: {
    primaryCategory: 'connectivity_loss',
    indirectCategory: 'cascade_risk',
    headline: '🔌 Port Configuration Change',
    whatHappens: 'Existing connections will fail until clients update their configuration.',
    affectsIndirect: false,
  },
  config_change: {
    primaryCategory: 'configuration_drift',
    indirectCategory: 'configuration_drift',
    headline: '⚙️ Behavior Change',
    whatHappens: 'Application behavior may change. Watch for feature flags and environment dependencies.',
    affectsIndirect: false,
  },
  image_update: {
    primaryCategory: 'compatibility_risk',
    indirectCategory: 'cascade_risk',
    headline: '📦 Version Update',
    whatHappens: 'Brief disruption during rollout. Check for API compatibility changes.',
    affectsIndirect: true,
  },
  network_policy_apply: {
    primaryCategory: 'connectivity_loss',
    indirectCategory: 'cascade_risk',
    headline: '🛡️ Network Policy Enforcement',
    whatHappens: 'Traffic not matching policy rules will be blocked.',
    affectsIndirect: false,
  },
  network_policy_remove: {
    primaryCategory: 'security_exposure',
    indirectCategory: 'security_exposure',
    headline: '🔓 Security Policy Removed',
    whatHappens: 'No connectivity impact. Security posture changed - previously blocked traffic now allowed.',
    affectsIndirect: false,
  },
};

// Target type definitions with icons
const targetTypes = [
  { key: 'deployment', label: 'Deployment', icon: <AppstoreOutlined />, description: 'Kubernetes Deployments' },
  { key: 'pod', label: 'Pod', icon: <ContainerOutlined />, description: 'Individual Pods' },
  { key: 'service', label: 'Service', icon: <CloudServerOutlined />, description: 'Kubernetes Services' },
  { key: 'external', label: 'External', icon: <GlobalOutlined />, description: 'External endpoints & IPs' },
];

// Kind type configurations for display - maps backend kinds to display info
const kindConfig: Record<string, { 
  icon: React.ReactNode; 
  color: string; 
  label: string;
  description: string;
}> = {
  Pod: {
    icon: <ContainerOutlined />,
    color: colors.charts.green,
    label: 'Pod',
    description: 'Kubernetes Pod',
  },
  Service: {
    icon: <CloudServerOutlined />,
    color: colors.charts.purple,
    label: 'Service',
    description: 'Kubernetes Service',
  },
  Deployment: {
    icon: <AppstoreOutlined />,
    color: colors.charts.blue,
    label: 'Deployment',
    description: 'Kubernetes Deployment',
  },
  ExternalIP: {
    icon: <GlobalOutlined />,
    color: colors.charts.orange,
    label: 'External IP',
    description: 'External IP address (outside cluster)',
  },
  ClusterIP: {
    icon: <ApiOutlined />,
    color: colors.charts.cyan,
    label: 'Cluster IP',
    description: 'Internal cluster IP (pod network)',
  },
  ServiceIP: {
    icon: <CloudServerOutlined />,
    color: colors.charts.purple,
    label: 'Service IP',
    description: 'Kubernetes Service IP',
  },
  ExternalDNS: {
    icon: <GlobalOutlined />,
    color: colors.charts.red,
    label: 'External DNS',
    description: 'External DNS hostname',
  },
  ClusterService: {
    icon: <ClusterOutlined />,
    color: colors.primary.main,
    label: 'Cluster Service',
    description: 'Internal cluster service (*.svc.cluster.local)',
  },
  Localhost: {
    icon: <ContainerOutlined />,
    color: colors.charts.yellow,
    label: 'Localhost',
    description: 'Local loopback connection',
  },
  'SDN-IP': {
    icon: <ApiOutlined />,
    color: colors.charts.teal,
    label: 'SDN IP',
    description: 'Software-Defined Network infrastructure IP',
  },
  External: {
    icon: <GlobalOutlined />,
    color: colors.charts.orange,
    label: 'External',
    description: 'External endpoint',
  },
};

// No dependency scenarios
const noDependencyScenarios: Record<string, NoDependencyInfo> = {
  NO_GRAPH_MATCH: {
    scenario: 'NO_GRAPH_MATCH',
    title: 'Target Not Found in Dependency Graph',
    description: 'This resource was not observed communicating during the analysis period.',
    suggestions: [
      'Verify the analysis is still running or has captured data',
      'Check if the target has any network activity',
      'Consider extending the analysis duration',
      'Ensure the target workload is in the analysis scope'
    ],
    alert_type: 'info'
  },
  ISOLATED_WORKLOAD: {
    scenario: 'ISOLATED_WORKLOAD',
    title: 'Isolated Workload Detected',
    description: 'This workload has no incoming or outgoing connections to other cluster resources.',
    suggestions: [
      'This may be intentional (batch jobs, init containers, cron jobs)',
      'Verify network policies are not blocking traffic',
      'Check if the workload is functioning correctly',
      'Review pod logs for connection errors'
    ],
    alert_type: 'success'
  },
  EXTERNAL_ONLY: {
    scenario: 'EXTERNAL_ONLY',
    title: 'External Connections Only',
    description: 'This target only communicates with external endpoints outside the cluster.',
    suggestions: [
      'External services may still be affected by this change',
      'Consider DNS resolution dependencies',
      'Review egress network policies',
      'Check for external service health monitoring'
    ],
    alert_type: 'warning'
  }
};

// =============================================================================
// Styled Alert Component - Theme Aligned
// =============================================================================

interface ThemedAlertProps {
  type: 'success' | 'info' | 'warning' | 'error';
  message: React.ReactNode;
  description?: React.ReactNode;
  icon?: React.ReactNode;
  style?: React.CSSProperties;
  showIcon?: boolean;
}

const ThemedAlert: React.FC<ThemedAlertProps> = ({ type, message, description, icon, style, showIcon = true }) => {
  const alertStyles: Record<string, { bg: string; border: string; iconColor: string }> = {
    error: {
      bg: `${colors.status.error}08`,
      border: `${colors.status.error}30`,
      iconColor: colors.status.error,
    },
    warning: {
      bg: `${colors.status.warning}08`,
      border: `${colors.status.warning}30`,
      iconColor: colors.status.warning,
    },
    info: {
      bg: `${colors.status.info}08`,
      border: `${colors.status.info}30`,
      iconColor: colors.status.info,
    },
    success: {
      bg: `${colors.status.success}08`,
      border: `${colors.status.success}30`,
      iconColor: colors.status.success,
    },
  };

  const alertStyle = alertStyles[type];

  return (
    <Alert
      type={type}
      message={message}
      description={description}
      icon={icon}
      showIcon={showIcon}
      style={{
        background: alertStyle.bg,
        border: `1px solid ${alertStyle.border}`,
        borderRadius: 8,
        ...style,
      }}
    />
  );
};

// =============================================================================
// Helper Functions
// =============================================================================

const getRecommendation = (impact: string, change: string): string => {
  const recommendations: Record<string, Record<string, string>> = {
    high: {
      delete: 'Add fallback service or circuit breaker before deletion',
      scale_down: 'Implement graceful degradation and health checks',
      network_isolate: 'Update network policies for allowed traffic paths',
      network_policy_apply: 'Test policy in audit mode before enforcement',
      config_change: 'Test configuration in staging environment first',
      default: 'Coordinate with dependent teams before proceeding',
    },
    medium: {
      delete: 'Monitor for cascading failures after deletion',
      scale_down: 'Verify auto-scaling policies are configured',
      network_isolate: 'Verify indirect communication paths remain open',
      network_policy_apply: 'Review policy rules for completeness',
      config_change: 'Validate configuration propagation timing',
      default: 'Review connection retry logic in clients',
    },
    low: {
      default: 'No immediate action required, monitor after change',
    },
  };
  return recommendations[impact]?.[change] || recommendations[impact]?.default || 'Review impact carefully';
};

// =============================================================================
// Types
// =============================================================================

interface TargetItem {
  id: string;
  name: string;
  namespace: string;
  kind: string;
  status?: string;
  replicas?: number;
  available_replicas?: number;
}

interface ScheduledSimulationType {
  id: string;
  name: string;
  description: string;
  template_id: string;
  analysis_id: number;
  cluster_id: number;
  target_type: string;
  target_id: string;
  change_type: string;
  schedule: {
    type: 'once' | 'recurring';
    cron?: string;
    scheduled_time?: string;
    timezone: string;
  };
  notification_channels: string[];
  auto_rollback: boolean;
  rollback_threshold: number;
  status: 'scheduled' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  last_run_at?: string;
  next_run_at?: string;
  run_count: number;
}

// =============================================================================
// Main Component
// =============================================================================

const ImpactSimulation: React.FC = () => {
  // Get theme tokens for consistent styling
  const { token } = useToken();
  
  // URL parameters for navigation from other pages
  const [searchParams] = useSearchParams();
  
  // State
  const [selectedClusterId, setSelectedClusterId] = useState<number | undefined>(undefined);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<number | undefined>(undefined);
  const [targetType, setTargetType] = useState<string>('deployment');
  const [targetId, setTargetId] = useState<string | undefined>(undefined);
  const [changeType, setChangeType] = useState<string>('delete');
  const [simulationRun, setSimulationRun] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [includeAllNamespaces, setIncludeAllNamespaces] = useState(false);
  const [selectedNamespace, setSelectedNamespace] = useState<string | undefined>(undefined);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(false);
  const [exportModalVisible, setExportModalVisible] = useState(false);
  const [networkPolicyModalVisible, setNetworkPolicyModalVisible] = useState(false);
  const [generatedPolicyYaml, setGeneratedPolicyYaml] = useState<string>('');
  const [activeResultTab, setActiveResultTab] = useState<string>('summary');
  
  // Chaos Engineering Templates state
  const [showChaosTemplates, setShowChaosTemplates] = useState(false);
  const [selectedChaosTemplate, setSelectedChaosTemplate] = useState<ChaosTemplate | null>(null);
  const [chaosTemplateFilter, setChaosTemplateFilter] = useState<string>('all');
  
  // Scheduled Simulations state
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ScheduledSimulation | null>(null);
  const [activeMainTab, setActiveMainTab] = useState<string>('simulation');

  // API mutations
  const [generateNetworkPolicy, { isLoading: isGeneratingPolicy }] = useGenerateNetworkPolicyMutation();
  const [runImpactSimulation, { isLoading: isRunningSimulation }] = useRunImpactSimulationMutation();
  
  // Scheduled Simulations API
  const { data: scheduledSimsData, isLoading: scheduledSimsLoading, refetch: refetchScheduledSims } = useGetScheduledSimulationsQuery({});
  const scheduledSimulations = scheduledSimsData?.simulations || [];
  const [createScheduledSimulationApi, { isLoading: savingSchedule }] = useCreateScheduledSimulationMutation();
  const [cancelScheduledSimulationApi] = useCancelScheduledSimulationMutation();
  const [runScheduledNowApi] = useRunScheduledSimulationNowMutation();
  
  // Simulation History API
  const { data: historyData, isLoading: historyLoading, refetch: refetchHistory } = useGetSimulationHistoryQuery({ limit: 50 });
  const simulationHistory = historyData?.history || [];
  const [deleteHistoryEntryApi] = useDeleteSimulationHistoryEntryMutation();
  
  // Backend simulation response
  const [backendSimulationResponse, setBackendSimulationResponse] = useState<any>(null);

  // API queries
  const { data: clustersResponse } = useGetClustersQuery();
  const clusters = clustersResponse?.clusters || [];
  
  const { data: analyses = [], isLoading: isAnalysesLoading } = useGetAnalysesQuery({});
  
  const availableAnalyses = Array.isArray(analyses) 
    ? analyses.filter((a: Analysis) => a.status === 'running' || a.status === 'completed' || a.status === 'stopped')
    : [];

  // Initialize from URL parameters (when navigating from Change Detection)
  useEffect(() => {
    const urlAnalysisId = searchParams.get('analysisId');
    const urlClusterId = searchParams.get('clusterId');
    const urlTarget = searchParams.get('target');
    const urlNamespace = searchParams.get('namespace');
    
    // Only apply URL params on initial load (when no analysis is selected)
    if (!selectedAnalysisId) {
      if (urlAnalysisId) {
        const parsedId = parseInt(urlAnalysisId, 10);
        if (!isNaN(parsedId)) {
          setSelectedAnalysisId(parsedId);
        }
      }
      if (urlClusterId) {
        const parsedId = parseInt(urlClusterId, 10);
        if (!isNaN(parsedId)) {
          setSelectedClusterId(parsedId);
        }
      }
      if (urlTarget) {
        setTargetId(urlTarget);
      }
      if (urlNamespace) {
        setSelectedNamespace(urlNamespace);
      }
    }
  }, [searchParams]); // Run when searchParams change

  // Handle analysis change - preserve template settings
  const handleAnalysisChange = (analysisId: number | undefined) => {
    setSelectedAnalysisId(analysisId);
    setSelectedClusterId(undefined);
    setTargetId(undefined);
    setSimulationRun(false);
    setBackendSimulationResponse(null);
    // NOTE: We intentionally DO NOT reset these when analysis changes:
    // - selectedChaosTemplate (template should persist across analysis changes)
    // - changeType (set by template or user, should persist)
    // - targetType (set by template or user, should persist)
    // This allows users to apply a template once and test it across multiple analyses
  };

  // Auto-set cluster when analysis changes
  useEffect(() => {
    if (selectedAnalysisId && analyses.length > 0) {
      const analysis = (Array.isArray(analyses) ? analyses : []).find(
        (a: Analysis) => a.id === selectedAnalysisId
      );
      if (analysis) {
        setSelectedClusterId(analysis.cluster_id);
      }
    }
  }, [selectedAnalysisId, analyses]);

  const { data: graphData, isLoading: isGraphLoading } = useGetDependencyGraphQuery(
    { cluster_id: selectedClusterId!, analysis_id: selectedAnalysisId },
    { skip: !selectedClusterId || !selectedAnalysisId }
  );

  // Extract discovered resources from graph data (analysis scope only)
  // This ensures we only show resources that were actually discovered during the analysis
  const discoveredResources = useMemo(() => {
    if (!graphData?.nodes) return { namespaces: [], deployments: [], pods: [], services: [] };
    
    const namespaceSet = new Set<string>();
    const deploymentMap = new Map<string, TargetItem>();
    const podMap = new Map<string, TargetItem>();
    const serviceMap = new Map<string, TargetItem>();
    
    // Helper function to extract deployment name from pod name
    // Kubernetes pod names follow pattern: deployment-name-replicaset-hash-pod-hash
    // Example: backend-5f79dbdb4d-kzwm6 → backend
    // Example: api-gateway-787d8cdf65-n7hjx → api-gateway
    const extractDeploymentName = (podName: string): string | null => {
      // Skip if it looks like a standalone pod (no hash suffix)
      if (!podName.includes('-')) return null;
      
      // Pattern: name-hash-hash (deployment) or name-number (statefulset)
      // Try to match deployment pattern: remove last two segments (replicaset-hash and pod-hash)
      const parts = podName.split('-');
      if (parts.length >= 3) {
        // Check if last two parts look like hashes (alphanumeric, 5-10 chars)
        const lastPart = parts[parts.length - 1];
        const secondLastPart = parts[parts.length - 2];
        
        const isHash = (s: string) => /^[a-z0-9]{4,10}$/.test(s);
        
        if (isHash(lastPart) && isHash(secondLastPart)) {
          // Deployment pattern: remove last 2 parts
          return parts.slice(0, -2).join('-');
        } else if (isHash(lastPart) && /^\d+$/.test(secondLastPart)) {
          // StatefulSet pattern: name-0, name-1 etc - keep as is but extract base name
          return parts.slice(0, -1).join('-');
        } else if (isHash(lastPart)) {
          // DaemonSet or other pattern: remove last part only
          return parts.slice(0, -1).join('-');
        }
      }
      return null;
    };
    
    graphData.nodes.forEach(node => {
      // Skip external endpoints for resource extraction
      if (node.is_external || node.namespace === 'external') return;
      
      // Collect namespaces
      if (node.namespace) {
        namespaceSet.add(node.namespace);
      }
      
      const ns = node.namespace || 'default';
      
      // Try to get owner info from node properties first
      // Use type assertion for optional properties that may exist at runtime
      const nodeAny = node as any;
      const ownerKind = node.owner_kind || nodeAny.ownerKind || nodeAny.workload_type;
      const ownerName = node.owner_name || nodeAny.ownerName || nodeAny.workload_name;
      
      // If we have explicit owner info, use it
      if (ownerKind && ownerName && 
          (ownerKind === 'Deployment' || ownerKind === 'StatefulSet' || ownerKind === 'DaemonSet' || ownerKind === 'ReplicaSet')) {
        const key = `deployment-${ns}-${ownerName}`;
        if (!deploymentMap.has(key)) {
          deploymentMap.set(key, {
            id: key,
            name: ownerName,
            namespace: ns,
            kind: ownerKind === 'ReplicaSet' ? 'Deployment' : ownerKind,
            status: node.status,
          });
        }
      }
      
      // For pods, also try to extract deployment name from pod name
      if (node.kind === 'Pod' || nodeAny.type === 'pod' || !node.kind) {
        const podName = node.name || nodeAny.pod_name || '';
        const key = `pod-${ns}-${podName}`;
        
        if (podName && !podMap.has(key)) {
          podMap.set(key, {
            id: key,
            name: podName,
            namespace: ns,
            kind: 'Pod',
            status: node.status,
          });
        }
        
        // Extract deployment name from pod name if we don't have owner info
        if (podName && !ownerName) {
          const deploymentName = extractDeploymentName(podName);
          if (deploymentName) {
            const depKey = `deployment-${ns}-${deploymentName}`;
            if (!deploymentMap.has(depKey)) {
              deploymentMap.set(depKey, {
                id: depKey,
                name: deploymentName,
                namespace: ns,
                kind: 'Deployment',
                status: node.status,
              });
            }
          }
        }
      }
      
      // Services (from owner_kind or Service nodes or type)
      if (node.owner_kind === 'Service' || node.kind === 'Service' || nodeAny.type === 'service') {
        const serviceName = node.owner_name || node.name || nodeAny.service_name;
        if (serviceName) {
          const key = `service-${ns}-${serviceName}`;
          if (!serviceMap.has(key)) {
            serviceMap.set(key, {
              id: key,
              name: serviceName,
              namespace: ns,
              kind: 'Service',
              status: node.status,
            });
          }
        }
      }
      
      // Also create service entries from deployments (most deployments have a matching service)
      // This ensures services are available even if not explicitly marked in graph
      if (node.kind === 'Pod' || nodeAny.type === 'pod' || !node.kind) {
        const podName = node.name || nodeAny.pod_name || '';
        if (podName) {
          const deploymentName = extractDeploymentName(podName);
          if (deploymentName) {
            // Create a service entry with the same name as deployment
            const svcKey = `service-${ns}-${deploymentName}`;
            if (!serviceMap.has(svcKey)) {
              serviceMap.set(svcKey, {
                id: svcKey,
                name: deploymentName,
                namespace: ns,
                kind: 'Service',
                status: node.status,
              });
            }
          }
        }
      }
    });
    
    return {
      namespaces: Array.from(namespaceSet).sort(),
      deployments: Array.from(deploymentMap.values()).sort((a, b) => `${a.namespace}-${a.name}`.localeCompare(`${b.namespace}-${b.name}`)),
      pods: Array.from(podMap.values()).sort((a, b) => `${a.namespace}-${a.name}`.localeCompare(`${b.namespace}-${b.name}`)),
      services: Array.from(serviceMap.values()).sort((a, b) => `${a.namespace}-${a.name}`.localeCompare(`${b.namespace}-${b.name}`)),
    };
  }, [graphData]);

  // Use discovered namespaces from analysis (not cluster-wide)
  const namespaces = discoveredResources.namespaces;
  const isNamespacesLoading = isGraphLoading;

  // Debug log to verify analysis-scoped filtering
  useEffect(() => {
    if (graphData?.nodes && selectedAnalysisId) {
      console.log('%c=== IMPACT SIMULATION: DISCOVERED RESOURCES ===', 'color: #00d4aa; font-weight: bold; font-size: 14px;');
      console.log(`%cAnalysis ID: ${selectedAnalysisId}`, 'color: #00d4aa;');
      console.log(`%cTotal graph nodes: ${graphData.nodes.length}`, 'color: #00d4aa;');
      console.log(`%cNamespaces (${discoveredResources.namespaces.length}):`, 'color: #00d4aa;', discoveredResources.namespaces);
      console.log(`%cDeployments (${discoveredResources.deployments.length}):`, 'color: #00d4aa;', discoveredResources.deployments.map(d => `${d.namespace}/${d.name}`));
      console.log(`%cPods (${discoveredResources.pods.length}):`, 'color: #00d4aa;', discoveredResources.pods.slice(0, 10).map(p => `${p.namespace}/${p.name}`));
      console.log(`%cServices (${discoveredResources.services.length}):`, 'color: #00d4aa;', discoveredResources.services.map(s => `${s.namespace}/${s.name}`));
      console.log('%c===============================================', 'color: #00d4aa; font-weight: bold;');
    }
  }, [graphData, selectedAnalysisId, discoveredResources]);


  // Reset target when type changes
  useEffect(() => {
    setTargetId(undefined);
    setSimulationRun(false);
  }, [targetType, selectedNamespace, includeAllNamespaces]);

  // Extract external endpoints from graph data
  const externalEndpoints = useMemo((): TargetItem[] => {
    if (!graphData?.nodes) return [];
    return graphData.nodes
      .filter(node => node.is_external || node.namespace === 'external' || node.name?.includes('.') || /^\d+\.\d+\.\d+\.\d+/.test(node.name || ''))
      .map(node => ({
        id: node.id,
        name: node.name,
        namespace: 'external',
        kind: 'External',
      }));
  }, [graphData]);

  // Build targets list based on target type - using discovered resources from analysis
  const targets = useMemo((): TargetItem[] => {
    // Filter by selected namespace if not including all
    const filterByNamespace = (items: TargetItem[]) => {
      if (includeAllNamespaces || !selectedNamespace) return items;
      return items.filter(item => item.namespace === selectedNamespace);
    };

    switch (targetType) {
      case 'deployment':
        return filterByNamespace(discoveredResources.deployments);
      case 'pod':
        return filterByNamespace(discoveredResources.pods);
      case 'service':
        return filterByNamespace(discoveredResources.services);
      case 'external':
        return externalEndpoints;
      default:
        return [];
    }
  }, [targetType, discoveredResources, externalEndpoints, includeAllNamespaces, selectedNamespace]);

  // All targets use graph data now, so loading state is unified
  const isTargetsLoading = isGraphLoading;

  // Find the selected target
  const selectedTarget = useMemo(() => {
    return targets.find(t => t.id === targetId);
  }, [targets, targetId]);

  // Find matching graph nodes for the selected target
  const matchingGraphNodeIds = useMemo((): string[] => {
    if (!graphData?.nodes || !selectedTarget) return [];
    
    const targetName = selectedTarget.name;
    const targetNamespace = selectedTarget.namespace;
    
    if (targetType === 'external') {
      const node = graphData.nodes.find(n => n.id === targetId);
      return node ? [node.id] : [];
    }
    
    const exactMatches = graphData.nodes.filter(node => 
      node.name === targetName && 
      node.namespace === targetNamespace
    );
    
    if (exactMatches.length > 0) {
      return exactMatches.map(n => n.id);
    }
    
    if (targetType === 'deployment' || targetType === 'service') {
      const relatedPods = graphData.nodes.filter(node => {
        if (node.namespace !== targetNamespace) return false;
        const podNamePattern = new RegExp(`^${targetName}(-[a-z0-9]+)*$`, 'i');
        return podNamePattern.test(node.name);
      });
      
      if (relatedPods.length > 0) {
        return relatedPods.map(n => n.id);
      }
    }
    
    const fuzzyMatches = graphData.nodes.filter(node =>
      node.namespace === targetNamespace &&
      (node.name.startsWith(targetName) || node.name.includes(targetName))
    );
    
    return fuzzyMatches.map(n => n.id);
  }, [graphData, selectedTarget, targetType, targetId]);

  // Use backend simulation response for affected services
  const affectedServices = useMemo((): AffectedService[] => {
    if (!simulationRun || !backendSimulationResponse) return [];
    
    // Use backend's affected_services directly - it has proper kind classification,
    // risk_factors, deduplication, and filtering applied
    return backendSimulationResponse.affected_services || [];
  }, [simulationRun, backendSimulationResponse]);

  // Determine no dependency scenario
  // Use backend's no_dependency_info if available
  const noDependencyInfo = useMemo((): NoDependencyInfo | null => {
    if (!simulationRun || affectedServices.length > 0) return null;
    
    // Use backend's no_dependency_info if available
    if (backendSimulationResponse?.no_dependency_info) {
      return backendSimulationResponse.no_dependency_info;
      }
    
    // Fallback to frontend logic if backend doesn't provide it
    if (matchingGraphNodeIds.length === 0) {
      return noDependencyScenarios.NO_GRAPH_MATCH;
      }
    
    // Check if target has any external connections
    const hasExternal = graphData?.nodes.some(n => 
      matchingGraphNodeIds.includes(n.id) && 
      (n.namespace === 'external' || n.name?.includes('.'))
    );
    
    if (hasExternal) {
      return noDependencyScenarios.EXTERNAL_ONLY;
      }

    return noDependencyScenarios.ISOLATED_WORKLOAD;
  }, [simulationRun, affectedServices, matchingGraphNodeIds, graphData, backendSimulationResponse]);

  // Run simulation
  const runSimulation = useCallback(async () => {
    if (!selectedTarget || !selectedClusterId) {
      message.error('Please select a target first');
      return;
    }
    
    setIsSimulating(true);
    setBackendSimulationResponse(null);
    
    try {
      const response = await runImpactSimulation({
        cluster_id: selectedClusterId,
        analysis_id: selectedAnalysisId,
        target_id: targetId || `${selectedTarget.kind.toLowerCase()}-${selectedTarget.namespace}-${selectedTarget.name}`,
        target_name: selectedTarget.name,
        target_namespace: selectedTarget.namespace,
        target_kind: selectedTarget.kind,
        change_type: changeType as ChangeType,
      }).unwrap();
      
      setBackendSimulationResponse(response);
      setSimulationRun(true);
      message.success('Impact simulation completed');
      
      // Debug log simulation results
      console.log('%c=== IMPACT SIMULATION RESULTS ===', 'color: #f59e0b; font-weight: bold; font-size: 14px;');
      console.log('%cTarget:', 'color: #f59e0b;', `${selectedTarget.namespace}/${selectedTarget.name} (${selectedTarget.kind})`);
      console.log('%cChange Type:', 'color: #f59e0b;', changeType);
      console.log('%cAffected Services:', 'color: #f59e0b;', response.affected_services?.length || 0);
      console.log('%cResponse:', 'color: #f59e0b;', response);
      console.log('%c=================================', 'color: #f59e0b; font-weight: bold;');
    } catch (error: any) {
      console.error('Simulation failed:', error);
      message.error(error?.data?.detail || 'Failed to run impact simulation');
      setSimulationRun(false);
    } finally {
      setIsSimulating(false);
    }
  }, [selectedTarget, selectedClusterId, selectedAnalysisId, changeType, runImpactSimulation]);

  // Reset simulation - preserves template and change type settings
  const resetSimulation = useCallback(() => {
    setSimulationRun(false);
    setTargetId(undefined);
    setBackendSimulationResponse(null);
    // NOTE: Template, changeType, and targetType are preserved intentionally
    // User can click the X on template banner to clear it manually
  }, []);

  // Full reset - clears everything including template
  const fullReset = useCallback(() => {
    setSimulationRun(false);
    setTargetId(undefined);
    setBackendSimulationResponse(null);
    setSelectedChaosTemplate(null);
    setChangeType('delete');
    setTargetType('deployment');
  }, []);
  
  // Apply Chaos Template
  const applyChaosTemplate = useCallback((template: ChaosTemplate) => {
    setChangeType(template.changeType);
    setTargetType(template.targetType);
    setSelectedChaosTemplate(template);
    setShowChaosTemplates(false);
    // Show info about what was set
    message.success({
      content: (
        <span>
          Template applied: <strong>{template.name}</strong>
          <br />
          <span style={{ fontSize: 12, opacity: 0.8 }}>
            Change Type: {template.changeType} | Target Type: {template.targetType}
          </span>
        </span>
      ),
      duration: 3,
    });
  }, []);
  
  // Get filtered chaos templates
  const filteredChaosTemplates = useMemo(() => {
    if (chaosTemplateFilter === 'all') return chaosTemplates;
    return chaosTemplates.filter(t => t.category === chaosTemplateFilter);
  }, [chaosTemplateFilter]);
  
  // ================== SCHEDULED SIMULATIONS API ==================
  
  const [scheduleForm] = Form.useForm();
  
  const createScheduledSimulation = useCallback(async (values: any) => {
    try {
      // Parse the target info
      const targetParts = targetId?.split('/') || [];
      const targetName = targetParts.length > 1 ? targetParts[1] : (targetId || '');
      const targetNamespace = targetParts.length > 1 ? targetParts[0] : selectedNamespace || 'default';
      
      await createScheduledSimulationApi({
        name: values.name,
        description: values.description || '',
        cluster_id: String(selectedClusterId),
        analysis_id: selectedAnalysisId ? String(selectedAnalysisId) : undefined,
        target_name: targetName,
        target_namespace: targetNamespace,
        target_kind: targetType.charAt(0).toUpperCase() + targetType.slice(1),
        change_type: changeType,
        schedule_type: values.schedule_type,
        scheduled_time: values.scheduled_time?.toISOString() || new Date().toISOString(),
        notify_before_minutes: values.notify_before_minutes || 15,
        auto_rollback: values.auto_rollback || false,
        rollback_on_failure: values.rollback_on_failure !== false,
      }).unwrap();
      
      setScheduleModalVisible(false);
      scheduleForm.resetFields();
      message.success('Simulation scheduled successfully');
    } catch (error: any) {
      message.error(error?.data?.detail || 'Failed to schedule simulation');
    }
  }, [selectedAnalysisId, selectedClusterId, targetType, targetId, changeType, selectedNamespace, createScheduledSimulationApi, scheduleForm]);
  
  const cancelScheduledSimulation = useCallback(async (id: string) => {
    try {
      await cancelScheduledSimulationApi(id).unwrap();
      message.success('Scheduled simulation cancelled');
    } catch (error: any) {
      message.error(error?.data?.detail || 'Failed to cancel simulation');
    }
  }, [cancelScheduledSimulationApi]);
  
  const runScheduledSimulationNow = useCallback(async (schedule: ScheduledSimulation) => {
    try {
      // Run via API
      const result = await runScheduledNowApi(schedule.id).unwrap();
      message.success('Simulation executed successfully');
      
      // Switch to simulation tab and show results
      setActiveMainTab('simulation');
      if (result.result) {
        setBackendSimulationResponse(result.result);
        setSimulationRun(true);
      }
      
      // Refetch history to show the new entry
      refetchHistory();
    } catch (error: any) {
      message.error(error?.data?.detail || 'Failed to run simulation');
    }
  }, [runScheduledNowApi, refetchHistory]);
  
  // Delete history entry
  const deleteHistoryEntry = useCallback(async (id: string) => {
    try {
      await deleteHistoryEntryApi(id).unwrap();
      message.success('History entry deleted');
    } catch (error: any) {
      message.error(error?.data?.detail || 'Failed to delete history entry');
    }
  }, [deleteHistoryEntryApi]);

  // Export functions
  const exportToJson = useCallback(() => {
    if (!selectedTarget || !simulationRun) return;
    
    // Get change type info for context
    const changeInfo = changeTypeImpactInfo[changeType];
    
    // Calculate impact category counts
    const impactCategoryCounts: Record<string, number> = {};
    affectedServices.forEach(s => {
      const category = s.impact_category || 
        (s.dependency === 'indirect' ? changeInfo?.indirectCategory : changeInfo?.primaryCategory) ||
        'unknown';
      impactCategoryCounts[category] = (impactCategoryCounts[category] || 0) + 1;
    });
    
    const report = {
      metadata: {
        generated_at: new Date().toISOString(),
        analysis_id: selectedAnalysisId,
        cluster_id: selectedClusterId,
        cluster_name: clusters.find(c => c.id === selectedClusterId)?.name,
        export_format: 'json',
        version: '2.0', // Indicate enhanced report format
      },
      simulation: {
        target_name: selectedTarget.name,
        target_namespace: selectedTarget.namespace,
        target_kind: selectedTarget.kind,
        change_type: changeType,
        change_type_description: changeInfo?.whatHappens || '',
        primary_impact_category: backendSimulationResponse?.summary?.primary_impact_category || changeInfo?.primaryCategory || 'unknown',
        graph_matches: backendSimulationResponse?.details?.graph_matches || matchingGraphNodeIds.length,
      },
      impact_summary: {
        total_affected: affectedServices.length,
        high_impact: affectedServices.filter(s => s.impact === 'high').length,
        medium_impact: affectedServices.filter(s => s.impact === 'medium').length,
        low_impact: affectedServices.filter(s => s.impact === 'low').length,
        blast_radius: affectedServices.length,
        direct_dependencies: affectedServices.filter(s => s.dependency === 'direct').length,
        indirect_dependencies: affectedServices.filter(s => s.dependency === 'indirect').length,
        impact_category_breakdown: impactCategoryCounts,
      },
      affected_services: affectedServices.map(s => {
        // Determine the correct category for this service
        const category = s.impact_category || 
          (s.dependency === 'indirect' ? changeInfo?.indirectCategory : changeInfo?.primaryCategory) ||
          'unknown';
        const categoryConfig = impactCategoryConfig[category];
        
        return {
          name: s.name,
          namespace: s.namespace,
          kind: s.kind,
          impact_level: s.impact,
          impact_category: category,
          impact_category_label: categoryConfig?.label || category,
          impact_category_description: categoryConfig?.description || '',
          dependency_type: s.dependency,
          recommendation: s.recommendation,
          connection_details: {
            protocol: s.connection_details?.protocol || 'TCP',
            port: s.connection_details?.port || 0,
            request_count: s.connection_details?.request_count || 0,
            hop_distance: s.connection_details?.hop_distance,
          },
          risk_score: s.risk_score,
          risk_factors: s.risk_factors || [],
          recovery_info: s.recovery_info,
        };
      }),
      recommendations: Array.from(new Set(affectedServices.map(s => s.recommendation))),
      interpretation_guide: {
        impact_levels: {
          high: 'Direct service outage or connectivity loss expected',
          medium: 'Potential for cascading failures or performance degradation',
          low: 'Minimal impact, mostly informational',
        },
        impact_categories: {
          service_outage: 'Complete service unavailability - connections will fail immediately',
          cascade_risk: 'Indirect dependency - potential for cascading failures, not direct outage',
          connectivity_loss: 'Network connectivity will be disrupted',
          performance_degradation: 'Service will experience slowdowns or resource constraints',
          configuration_drift: 'Configuration inconsistencies may occur',
          security_exposure: 'Security posture may change',
          compatibility_risk: 'Version or API compatibility issues possible',
          transient_disruption: 'Temporary disruption during rollout',
        },
        dependency_types: {
          direct: 'Services that directly connect to the target',
          indirect: 'Services that depend on direct dependencies (2-hop)',
        },
      },
    };
    
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `impact_simulation_${selectedTarget.name}_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success('Report exported as JSON');
    setExportModalVisible(false);
  }, [selectedTarget, simulationRun, selectedAnalysisId, selectedClusterId, clusters, changeType, matchingGraphNodeIds, affectedServices, backendSimulationResponse]);

  const exportToCsv = useCallback(() => {
    if (!selectedTarget || !simulationRun) return;
    
    // Get change type info for context
    const changeInfo = changeTypeImpactInfo[changeType];
    
    const rows = [
      ['# Impact Simulation Report v2.0'],
      ['Generated At', new Date().toISOString()],
      ['Cluster ID', String(selectedClusterId)],
      ['Analysis ID', String(selectedAnalysisId || '')],
      [],
      ['# Simulation Target'],
      ['Target Name', selectedTarget.name],
      ['Target Namespace', selectedTarget.namespace],
      ['Target Kind', selectedTarget.kind],
      ['Change Type', changeType],
      ['Change Type Description', changeInfo?.whatHappens || ''],
      ['Primary Impact Category', backendSimulationResponse?.summary?.primary_impact_category || changeInfo?.primaryCategory || 'unknown'],
      ['Graph Matches', String(backendSimulationResponse?.details?.graph_matches || matchingGraphNodeIds.length)],
      [],
      ['# Impact Summary'],
      ['Total Affected', String(affectedServices.length)],
      ['High Impact', String(affectedServices.filter(s => s.impact === 'high').length)],
      ['Medium Impact', String(affectedServices.filter(s => s.impact === 'medium').length)],
      ['Low Impact', String(affectedServices.filter(s => s.impact === 'low').length)],
      ['Direct Dependencies', String(affectedServices.filter(s => s.dependency === 'direct').length)],
      ['Indirect Dependencies', String(affectedServices.filter(s => s.dependency === 'indirect').length)],
      [],
      ['# Affected Services'],
      ['Name', 'Namespace', 'Kind', 'Impact Level', 'Impact Category', 'Dependency Type', 'Protocol', 'Port', 'Request Count', 'Risk Score', 'Risk Factors', 'Recommendation'],
      ...affectedServices.map(s => {
        // Determine the correct category for this service
        const category = s.impact_category || 
          (s.dependency === 'indirect' ? changeInfo?.indirectCategory : changeInfo?.primaryCategory) ||
          'unknown';
        const categoryConfig = impactCategoryConfig[category];
        
        return [
          s.name,
          s.namespace,
          s.kind,
          s.impact,
          categoryConfig?.label || category,
          s.dependency,
          s.connection_details?.protocol || '',
          String(s.connection_details?.port || ''),
          String(s.connection_details?.request_count || ''),
          String(s.risk_score),
          (s.risk_factors || []).join('; '),
          s.recommendation,
        ];
      }),
      [],
      ['# Interpretation Guide'],
      ['HIGH impact', 'Direct service outage or connectivity loss expected'],
      ['MEDIUM impact', 'Potential for cascading failures or performance degradation'],
      ['LOW impact', 'Minimal impact - mostly informational'],
      ['Direct dependency', 'Services that directly connect to the target'],
      ['Indirect dependency', 'Services that depend on direct dependencies (2-hop) - risk of cascade'],
    ];
    
    const csv = rows.map(row => row.map(cell => `"${cell}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `impact_simulation_${selectedTarget.name}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    message.success('Report exported as CSV');
    setExportModalVisible(false);
  }, [selectedTarget, simulationRun, selectedClusterId, selectedAnalysisId, changeType, matchingGraphNodeIds, affectedServices, backendSimulationResponse]);

  // Generate network policy
  const handleGenerateNetworkPolicy = useCallback(async () => {
    if (!selectedTarget || !selectedClusterId) return;
    
    try {
      const result = await generateNetworkPolicy({
        cluster_id: selectedClusterId,
        analysis_id: selectedAnalysisId,
        target_namespace: selectedTarget.namespace,
        target_workload: selectedTarget.name,
        target_kind: selectedTarget.kind,
        policy_types: ['both'],
        include_dns: true,
        strict_mode: false,
      }).unwrap();
      
      setGeneratedPolicyYaml(result.generated_yaml);
      setNetworkPolicyModalVisible(true);
      message.success('Network policy generated successfully');
    } catch (error) {
      message.error('Failed to generate network policy');
    }
  }, [selectedTarget, selectedClusterId, selectedAnalysisId, generateNetworkPolicy]);

  // Stats
  const stats = useMemo(() => {
    const high = affectedServices.filter(s => s.impact === 'high').length;
    const medium = affectedServices.filter(s => s.impact === 'medium').length;
    const low = affectedServices.filter(s => s.impact === 'low').length;
    return { high, medium, low, total: high + medium + low };
  }, [affectedServices]);

  // Table columns with expandable rows
  const columns = [
    {
      title: 'Service',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: AffectedService) => {
        const kindInfo = kindConfig[record.kind] || kindConfig['Pod'];
        return (
        <Space>
            <Tooltip title={kindInfo.description}>
              <span style={{ color: kindInfo.color }}>{kindInfo.icon}</span>
            </Tooltip>
          <div>
            <Text strong>{name}</Text>
            <br />
              <Space size={4}>
            <Text type="secondary" style={{ fontSize: 11 }}>{record.namespace}</Text>
                <Tag 
                  style={{ 
                    fontSize: 9, 
                    padding: '0 4px', 
                    lineHeight: '14px',
                    background: `${kindInfo.color}15`,
                    border: `1px solid ${kindInfo.color}30`,
                    color: kindInfo.color,
                  }}
                >
                  {kindInfo.label}
                </Tag>
              </Space>
          </div>
        </Space>
        );
      },
    },
    {
      title: 'Impact',
      dataIndex: 'impact',
      key: 'impact',
      width: 140,
      render: (impact: ImpactLevel, record: AffectedService) => {
        // Use backend-provided category, or fallback based on dependency type
        // IMPORTANT: Indirect dependencies should NEVER show "Service Outage"
        const changeInfo = changeTypeImpactInfo[changeType];
        let category: string | undefined = record.impact_category;
        
        // Fallback: if no category from backend, determine based on dependency type
        if (!category && changeInfo) {
          category = record.dependency === 'indirect' 
            ? changeInfo.indirectCategory  // Use indirect category (cascade_risk)
            : changeInfo.primaryCategory;   // Use primary category (service_outage, etc.)
        }
        
        const categoryConfig = category ? impactCategoryConfig[category] : null;
        
        return (
          <Space direction="vertical" size={0}>
            <Tag color={impactColors[impact]}>
          {impact.toUpperCase()}
        </Tag>
            {categoryConfig && (
              <Tooltip title={categoryConfig.description}>
                <Text style={{ fontSize: 10, color: categoryConfig.color }}>
                  {getCategoryIcon(categoryConfig.iconType, categoryConfig.color)} {categoryConfig.label}
                </Text>
              </Tooltip>
            )}
          </Space>
        );
      },
      sorter: (a: AffectedService, b: AffectedService) => {
        const order = { high: 3, medium: 2, low: 1, none: 0 };
        return order[b.impact] - order[a.impact];
      },
    },
    {
      title: 'Dependency',
      dataIndex: 'dependency',
      key: 'dependency',
      width: 100,
      render: (dep: string) => (
        <Tag color={dep === 'direct' ? 'red' : 'orange'}>{dep}</Tag>
      ),
    },
    {
      title: 'Connection',
      key: 'connection',
      width: 150,
      render: (_: any, record: AffectedService) => (
        record.connection_details ? (
          <Space direction="vertical" size={0}>
            <Text style={{ fontSize: 12 }}>
              {record.connection_details.protocol}:{record.connection_details.port}
            </Text>
            {record.connection_details.request_count !== undefined && (
              <Text type="secondary" style={{ fontSize: 10 }}>
                {record.connection_details.request_count.toLocaleString()} requests
              </Text>
            )}
          </Space>
        ) : (
          <Text type="secondary">-</Text>
        )
      ),
    },
    {
      title: 'Risk',
      dataIndex: 'risk_score',
      key: 'risk_score',
      width: 80,
      render: (score: number) => (
        <Progress
          percent={Math.round(score * 100)}
          size="small"
          strokeColor={score > 0.7 ? '#c75450' : score > 0.4 ? '#b89b5d' : '#4d9f7c'}
          format={percent => `${percent}%`}
        />
      ),
    },
    {
      title: 'Recommendation',
      dataIndex: 'recommendation',
      key: 'recommendation',
      render: (rec: string) => <Text type="secondary" style={{ fontSize: 12 }}>{rec}</Text>,
    },
  ];

  // Filtered change types based on advanced toggle
  const visibleChangeTypes = showAdvancedOptions 
    ? changeTypes 
    : changeTypes.filter(ct => !ct.advanced);

  return (
    <div style={{ 
      padding: '24px', 
      minHeight: 'calc(100vh - 64px)'
    }}>
      {/* Header - Theme aligned */}
      <div style={{ 
        marginBottom: 24,
        padding: '20px 24px',
        background: `linear-gradient(135deg, ${colors.primary.main}08 0%, ${colors.primary.light}05 100%)`,
        borderRadius: token.borderRadiusLG,
        border: `1px solid ${colors.primary.main}15`,
      }}>
        <Space align="center" size={16}>
          <div style={{
            width: 48,
            height: 48,
            borderRadius: token.borderRadius,
            background: colors.gradients.primary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: `0 4px 12px ${colors.primary.main}30`,
          }}>
            <ThunderboltOutlined style={{ fontSize: 24, color: '#ffffff' }} />
          </div>
          <div>
            <Title level={2} style={{ margin: 0, color: token.colorText }}>Impact Simulation</Title>
            <Text style={{ color: token.colorTextSecondary }}>
              Analyze the impact of changes before implementation
            </Text>
          </div>
        </Space>
      </div>

      {/* Main Tabs */}
      <Tabs
        activeKey={activeMainTab}
        onChange={setActiveMainTab}
        type="card"
        size="large"
        tabBarStyle={{ marginBottom: 16 }}
        items={[
          {
            key: 'simulation',
            label: (
              <Space>
                <ThunderboltOutlined />
                <span>Run Simulation</span>
              </Space>
            ),
          },
          {
            key: 'scheduled',
            label: (
              <Space>
                <ScheduleOutlined />
                <span>Scheduled</span>
                {scheduledSimulations.filter(s => s.status === 'scheduled').length > 0 && (
                  <Badge 
                    count={scheduledSimulations.filter(s => s.status === 'scheduled').length} 
                    style={{ backgroundColor: colors.primary.main }}
                  />
                )}
              </Space>
            ),
          },
          {
            key: 'history',
            label: (
              <Space>
                <HistoryOutlined />
                <span>History</span>
              </Space>
            ),
          },
        ]}
      />

      {/* Simulation Tab Content */}
      {activeMainTab === 'simulation' && (
      <Row gutter={24}>
        {/* Left Panel - Configuration */}
        <Col span={8}>
          <Card 
            title="Simulation Configuration" 
            bordered={false}
            extra={
              <Space>
                {selectedAnalysisId && targetId && (
                  <Tooltip title="Schedule this simulation">
                    <Button 
                      icon={<ScheduleOutlined />}
                      onClick={() => setScheduleModalVisible(true)}
                    >
                      Schedule
                    </Button>
                  </Tooltip>
                )}
                <Button 
                  type="primary" 
                  ghost 
                  icon={<BulbOutlined />}
                  onClick={() => setShowChaosTemplates(true)}
                >
                  Chaos Templates
                </Button>
              </Space>
            }
          >
            {/* Active Chaos Template Banner - Enhanced */}
            {selectedChaosTemplate && (
              <Alert
                message={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Space>
                      <span style={{ fontSize: 16 }}>{chaosTemplateIcons[selectedChaosTemplate.icon]}</span>
                      <span style={{ fontWeight: 600 }}>Template: {selectedChaosTemplate.name}</span>
                      <Tag 
                        color={
                          selectedChaosTemplate.severity === 'high' ? 'red' : 
                          selectedChaosTemplate.severity === 'medium' ? 'orange' : 'green'
                        }
                      >
                        {selectedChaosTemplate.severity.toUpperCase()}
                      </Tag>
                    </Space>
                    <Space size="small">
                      <Tooltip title="Template settings persist when you change analysis">
                        <Tag color="blue" style={{ margin: 0 }}>
                          <SyncOutlined style={{ marginRight: 4 }} />
                          Persistent
                        </Tag>
                      </Tooltip>
                    </Space>
                  </div>
                }
                description={
                  <div>
                    <div style={{ marginBottom: 8 }}>{selectedChaosTemplate.description}</div>
                    <Space size="middle">
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <SettingOutlined style={{ marginRight: 4 }} />
                        Change Type: <Text code style={{ fontSize: 11 }}>{changeType}</Text>
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <AimOutlined style={{ marginRight: 4 }} />
                        Target Type: <Text code style={{ fontSize: 11 }}>{targetType}</Text>
                      </Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        <ClockCircleOutlined style={{ marginRight: 4 }} />
                        Rollback: <Text style={{ fontSize: 11, color: colors.status.success }}>{selectedChaosTemplate.rollbackTime}</Text>
                      </Text>
                    </Space>
                  </div>
                }
                type="info"
                showIcon={false}
                closable
                onClose={() => {
                  setSelectedChaosTemplate(null);
                  message.info('Template cleared. Change type and target type preserved.');
                }}
                style={{ 
                  marginBottom: 16,
                  background: `${colors.primary.main}08`,
                  border: `1px solid ${colors.primary.main}30`,
                }}
                action={
                  <Button 
                    size="small" 
                    type="link" 
                    danger
                    onClick={fullReset}
                    style={{ marginRight: 8 }}
                  >
                    Clear All
                  </Button>
                }
              />
            )}
            
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {/* Analysis Selection */}
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>Analysis</Text>
                <Select
                  placeholder="Select analysis"
                  style={{ width: '100%' }}
                  value={selectedAnalysisId}
                  onChange={(value) => {
                    handleAnalysisChange(value);
                    resetSimulation();
                  }}
                  loading={isAnalysesLoading}
                >
                  {availableAnalyses.map((analysis: Analysis) => {
                    const cluster = clusters.find((c: any) => c.id === analysis.cluster_id);
                    const clusterName = cluster?.name || `Cluster ${analysis.cluster_id}`;
                    return (
                      <Option key={analysis.id} value={analysis.id}>
                        <Space>
                          <Badge status={analysis.status === 'running' ? 'processing' : 'success'} />
                          {analysis.name}
                          <Text type="secondary" style={{ fontSize: 11 }}>({clusterName})</Text>
                        </Space>
                      </Option>
                    );
                  })}
                </Select>
              </div>

              <Divider>Target Selection</Divider>

              {/* Show message if no analysis selected */}
              {!selectedAnalysisId && (
                <Alert
                  message="Select an Analysis First"
                  description="Please select an analysis above to enable target selection and simulation options."
                  type="info"
                  showIcon
                  style={{
                    background: `${colors.status.info}08`,
                    border: `1px solid ${colors.status.info}30`,
                    borderRadius: 8,
                  }}
                />
              )}

              {/* Target Type */}
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8, color: !selectedAnalysisId ? token.colorTextDisabled : token.colorText }}>
                  <AimOutlined /> Target Type
                </Text>
                <Select
                  style={{ width: '100%' }}
                  value={targetType}
                  onChange={(value) => {
                    setTargetType(value);
                    setTargetId(undefined);
                  }}
                  disabled={!selectedAnalysisId}
                >
                  {targetTypes.map(tt => (
                    <Option key={tt.key} value={tt.key}>
                      <Space>
                        {tt.icon}
                        <span>{tt.label}</span>
                      </Space>
                    </Option>
                  ))}
                </Select>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                  {targetTypes.find(tt => tt.key === targetType)?.description}
                </Text>
              </div>

              {/* Namespace filter */}
              {targetType !== 'external' && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <Text strong style={{ color: !selectedAnalysisId ? token.colorTextDisabled : token.colorText }}>Namespace</Text>
                    <Tooltip title="Include resources from all namespaces">
                      <Space size="small">
                        <Text type="secondary" style={{ fontSize: 11 }}>All namespaces</Text>
                        <Switch 
                          size="small"
                          checked={includeAllNamespaces}
                          onChange={(checked) => {
                            setIncludeAllNamespaces(checked);
                            if (checked) setSelectedNamespace(undefined);
                          }}
                          disabled={!selectedAnalysisId}
                        />
                      </Space>
                    </Tooltip>
                  </div>
                  <Select
                    placeholder="Select namespace"
                    style={{ width: '100%' }}
                    value={selectedNamespace}
                    onChange={setSelectedNamespace}
                    loading={isNamespacesLoading}
                    disabled={!selectedAnalysisId || !selectedClusterId || includeAllNamespaces}
                    allowClear
                    showSearch
                  >
                    {namespaces.map((ns: string) => (
                      <Option key={ns} value={ns}>{ns}</Option>
                    ))}
                  </Select>
                </div>
              )}

              {/* Target Selection */}
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8, color: !selectedAnalysisId ? token.colorTextDisabled : token.colorText }}>
                  Select Target
                  {selectedAnalysisId && targets.length > 0 && (
                    <Tag color="blue" style={{ marginLeft: 8 }}>{targets.length}</Tag>
                  )}
                </Text>
                <Select
                  placeholder={!selectedAnalysisId ? "Select analysis first" : `Select ${targetType} to simulate`}
                  style={{ width: '100%' }}
                  value={targetId}
                  onChange={(value) => {
                    setTargetId(value);
                    setSimulationRun(false);
                  }}
                  loading={isTargetsLoading}
                  disabled={!selectedAnalysisId || !selectedClusterId || (targetType !== 'external' && targets.length === 0)}
                  showSearch
                  filterOption={(input, option) => {
                    const label = option?.label as string || '';
                    return label.toLowerCase().includes(input.toLowerCase());
                  }}
                  optionLabelProp="label"
                  notFoundContent={
                    isTargetsLoading ? (
                      <Spin size="small" />
                    ) : (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={`No ${targetType}s found`} />
                    )
                  }
                >
                  {targets.map((target) => (
                    <Option key={target.id} value={target.id} label={`${target.name} (${target.namespace})`}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Space>
                          {targetType === 'deployment' && <AppstoreOutlined style={{ color: '#0891b2' }} />}
                          {targetType === 'pod' && <ContainerOutlined style={{ color: '#4d9f7c' }} />}
                          {targetType === 'service' && <CloudServerOutlined style={{ color: '#7c8eb5' }} />}
                          {targetType === 'external' && <GlobalOutlined style={{ color: '#b89b5d' }} />}
                          <div>
                            <Text strong style={{ fontSize: 13 }}>{target.name}</Text>
                            <br />
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {target.namespace}
                              {target.replicas !== undefined && ` • ${target.available_replicas || 0}/${target.replicas} replicas`}
                            </Text>
                          </div>
                        </Space>
                        <Tag color={targetType === 'external' ? 'orange' : 'default'} style={{ fontSize: 10 }}>
                          {target.kind}
                        </Tag>
                      </div>
                    </Option>
                  ))}
                </Select>
              </div>

              <Divider>
                <Space>
                  <span style={{ color: !selectedAnalysisId ? token.colorTextDisabled : token.colorText }}>Change Type</span>
                  <Switch
                    size="small"
                    checked={showAdvancedOptions}
                    onChange={setShowAdvancedOptions}
                    disabled={!selectedAnalysisId}
                  />
                  <Text type="secondary" style={{ fontSize: 11 }}>Advanced</Text>
                </Space>
              </Divider>

              {/* Change Type Selection */}
              <div style={{ opacity: !selectedAnalysisId ? 0.5 : 1, pointerEvents: !selectedAnalysisId ? 'none' : 'auto' }}>
                <Radio.Group
                  value={changeType}
                  onChange={(e) => {
                    setChangeType(e.target.value);
                    setSimulationRun(false);
                  }}
                  style={{ width: '100%' }}
                  disabled={!selectedAnalysisId}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {visibleChangeTypes.map((ct) => (
                      <Radio key={ct.key} value={ct.key} style={{ width: '100%' }} disabled={!selectedAnalysisId}>
                        <Space>
                          <span>{ct.icon}</span>
                          <div>
                            <Text strong>{ct.label}</Text>
                            {ct.advanced && <Tag color="purple" style={{ marginLeft: 4, fontSize: 9 }}>Advanced</Tag>}
                            <br />
                            <Text type="secondary" style={{ fontSize: 11 }}>{ct.description}</Text>
                          </div>
                        </Space>
                      </Radio>
                    ))}
                  </Space>
                </Radio.Group>
              </div>

              {/* Action Buttons */}
              <Space direction="vertical" style={{ width: '100%' }}>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                size="large"
                block
                onClick={runSimulation}
                loading={isSimulating}
                disabled={!targetId}
              >
                Run Simulation
              </Button>
                
                {(changeType === 'network_isolate' || changeType === 'network_policy_apply') && selectedTarget && (
                  <Button
                    icon={<SafetyCertificateOutlined />}
                    block
                    onClick={handleGenerateNetworkPolicy}
                    loading={isGeneratingPolicy}
                  >
                    Generate Network Policy
                  </Button>
                )}
              </Space>
            </Space>
          </Card>
        </Col>

        {/* Right Panel - Results */}
        <Col span={16}>
          {!simulationRun && !isSimulating && (
            <Card bordered={false} style={{ minHeight: 500 }}>
              <Empty
                image={<ClusterOutlined style={{ fontSize: 64, color: '#bfbfbf' }} />}
                description={
                  <Space direction="vertical">
                    <Text strong>No Simulation Results</Text>
                    <Text type="secondary">
                      Select a target and change type, then run simulation to see impact analysis
                    </Text>
                  </Space>
                }
              />
            </Card>
          )}

          {isSimulating && (
            <Card bordered={false} style={{ minHeight: 500, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Space direction="vertical" align="center">
                <Spin size="large" />
                <Text>Analyzing dependencies and calculating impact...</Text>
              </Space>
            </Card>
          )}

          {simulationRun && !isSimulating && (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {/* Impact Summary */}
              <Card 
                bordered={false}
                title={
                  <Space>
                    <AimOutlined style={{ color: colors.primary.main }} />
                    <span>Impact Summary</span>
                  </Space>
                }
                style={{ borderRadius: token.borderRadiusLG }}
              >
                <Row gutter={16}>
                  <Col span={6}>
                    <Statistic
                      title={<Text style={{ color: token.colorTextSecondary }}>Total Affected</Text>}
                      value={stats.total}
                      valueStyle={{ color: colors.primary.main, fontWeight: 600 }}
                      prefix={<ClusterOutlined style={{ color: colors.primary.main }} />}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title={<Text style={{ color: token.colorTextSecondary }}>High Impact</Text>}
                      value={stats.high}
                      valueStyle={{ color: colors.status.error, fontWeight: 600 }}
                      prefix={<ExclamationCircleOutlined style={{ color: colors.status.error }} />}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title={<Text style={{ color: token.colorTextSecondary }}>Medium Impact</Text>}
                      value={stats.medium}
                      valueStyle={{ color: colors.status.warning, fontWeight: 600 }}
                      prefix={<WarningOutlined style={{ color: colors.status.warning }} />}
                    />
                  </Col>
                  <Col span={6}>
                    <Statistic
                      title={<Text style={{ color: token.colorTextSecondary }}>Low Impact</Text>}
                      value={stats.low}
                      valueStyle={{ color: colors.status.success, fontWeight: 600 }}
                      prefix={<CheckCircleOutlined style={{ color: colors.status.success }} />}
                    />
                  </Col>
                </Row>
              </Card>

              {/* Chaos Engineering Analysis Panel - Only show when template is selected */}
              {selectedChaosTemplate && (() => {
                const chaosScore = calculateChaosScore(selectedChaosTemplate, affectedServices, stats, graphData);
                const prerequisites = checkPrerequisites(selectedChaosTemplate, selectedTarget, graphData);
                const passedCount = prerequisites.filter(p => p.status === 'passed').length;
                const failedCount = prerequisites.filter(p => p.status === 'failed').length;
                const warningCount = prerequisites.filter(p => p.status === 'warning').length;

                return (
                  <Card
                    bordered={false}
                    style={{ borderRadius: token.borderRadiusLG }}
                    title={
                      <Space>
                        <BulbOutlined style={{ color: colors.primary.main }} />
                        <span>Chaos Engineering Analysis</span>
                        <Tag color="blue">{selectedChaosTemplate.name}</Tag>
                      </Space>
                    }
                    extra={
                      <Space>
                        <Tooltip title="Based on Gremlin Reliability Score methodology">
                          <Tag style={{ cursor: 'help' }}>
                            <InfoCircleOutlined /> Methodology
                          </Tag>
                        </Tooltip>
                      </Space>
                    }
                  >
                    <Row gutter={24}>
                      {/* Chaos Score - Left Side */}
                      <Col span={8}>
                        <div style={{ textAlign: 'center', padding: '16px 0' }}>
                          <div style={{ position: 'relative', display: 'inline-block' }}>
                            <Progress
                              type="dashboard"
                              percent={chaosScore.score}
                              strokeColor={chaosScore.gradeColor}
                              strokeWidth={8}
                              width={140}
                              format={() => (
                                <div>
                                  <div style={{ 
                                    fontSize: 36, 
                                    fontWeight: 700, 
                                    color: chaosScore.gradeColor,
                                    lineHeight: 1,
                                  }}>
                                    {chaosScore.grade}
                                  </div>
                                  <div style={{ 
                                    fontSize: 12, 
                                    color: token.colorTextSecondary,
                                    marginTop: 4,
                                  }}>
                                    Risk Score: {chaosScore.score}
                                  </div>
                                </div>
                              )}
                            />
                          </div>
                          <div style={{ marginTop: 12 }}>
                            <Tag 
                              color={
                                chaosScore.riskLevel === 'critical' ? 'red' :
                                chaosScore.riskLevel === 'high' ? 'orange' :
                                chaosScore.riskLevel === 'medium' ? 'gold' : 'green'
                              }
                              style={{ fontSize: 12, padding: '2px 12px' }}
                            >
                              {chaosScore.riskLevel.toUpperCase()} RISK
                            </Tag>
                          </div>
                          <div style={{ marginTop: 16 }}>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              Rollback Time: <Text strong style={{ color: colors.status.success }}>{selectedChaosTemplate.rollbackTime}</Text>
                            </Text>
                          </div>
                        </div>
                      </Col>

                      {/* Score Factors - Middle */}
                      <Col span={8}>
                        <Text strong style={{ display: 'block', marginBottom: 12 }}>
                          <ThunderboltOutlined style={{ marginRight: 6, color: colors.status.warning }} />
                          Risk Factors
                        </Text>
                        {chaosScore.factors.map((factor, idx) => (
                          <div key={idx} style={{ marginBottom: 8 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                              <Text style={{ fontSize: 12 }}>{factor.name}</Text>
                              <Text style={{ fontSize: 12, color: factor.impact > 15 ? colors.status.error : colors.status.warning }}>
                                +{factor.impact}
                              </Text>
                            </div>
                            <Progress 
                              percent={factor.impact * 3.33} 
                              showInfo={false} 
                              strokeColor={factor.impact > 20 ? colors.status.error : factor.impact > 10 ? colors.status.warning : colors.status.success}
                              trailColor={token.colorBgLayout}
                              size="small"
                            />
                            <Text type="secondary" style={{ fontSize: 10 }}>{factor.description}</Text>
                          </div>
                        ))}
                      </Col>

                      {/* Prerequisites Check - Right Side */}
                      <Col span={8}>
                        <Text strong style={{ display: 'block', marginBottom: 12 }}>
                          <SafetyCertificateOutlined style={{ marginRight: 6, color: colors.primary.main }} />
                          Prerequisites Check
                          <span style={{ fontWeight: 400, marginLeft: 8 }}>
                            <Tag color="green" style={{ fontSize: 10 }}>{passedCount} passed</Tag>
                            {failedCount > 0 && <Tag color="red" style={{ fontSize: 10 }}>{failedCount} failed</Tag>}
                            {warningCount > 0 && <Tag color="orange" style={{ fontSize: 10 }}>{warningCount} warning</Tag>}
                          </span>
                        </Text>
                        <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                          {prerequisites.map((prereq) => (
                            <div 
                              key={prereq.id} 
                              style={{ 
                                display: 'flex', 
                                alignItems: 'flex-start', 
                                gap: 8, 
                                marginBottom: 8,
                                padding: '6px 8px',
                                borderRadius: 6,
                                background: prereq.status === 'failed' ? `${colors.status.error}08` :
                                           prereq.status === 'warning' ? `${colors.status.warning}08` :
                                           prereq.status === 'passed' ? `${colors.status.success}08` :
                                           token.colorBgLayout,
                              }}
                            >
                              {prereq.status === 'passed' && <CheckCircleOutlined style={{ color: colors.status.success, marginTop: 2 }} />}
                              {prereq.status === 'failed' && <ExclamationCircleOutlined style={{ color: colors.status.error, marginTop: 2 }} />}
                              {prereq.status === 'warning' && <WarningOutlined style={{ color: colors.status.warning, marginTop: 2 }} />}
                              {prereq.status === 'unknown' && <QuestionCircleOutlined style={{ color: token.colorTextSecondary, marginTop: 2 }} />}
                              <div>
                                <Text style={{ fontSize: 12, display: 'block' }}>{prereq.message}</Text>
                                {prereq.critical && prereq.status === 'failed' && (
                                  <Text type="danger" style={{ fontSize: 10 }}>⚠️ Critical - may cause extended downtime</Text>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </Col>
                    </Row>

                    <Divider style={{ margin: '16px 0' }} />

                    {/* Execution Steps Timeline & Recommendations */}
                    <Row gutter={24}>
                      <Col span={14}>
                        <Text strong style={{ display: 'block', marginBottom: 12 }}>
                          <ClockCircleOutlined style={{ marginRight: 6, color: colors.primary.main }} />
                          Execution Steps
                        </Text>
                        <Timeline
                          items={selectedChaosTemplate.steps.map((step, idx) => ({
                            color: idx === 0 ? colors.status.success : 
                                   idx === selectedChaosTemplate.steps.length - 1 ? colors.primary.main : 
                                   token.colorTextSecondary,
                            children: (
                              <div>
                                <Text style={{ fontSize: 12 }}>
                                  <Tag style={{ fontSize: 10, marginRight: 6 }}>{idx + 1}</Tag>
                                  {step}
                                </Text>
                              </div>
                            ),
                          }))}
                        />
                      </Col>
                      <Col span={10}>
                        <Text strong style={{ display: 'block', marginBottom: 12 }}>
                          <BulbOutlined style={{ marginRight: 6, color: colors.status.warning }} />
                          AI Recommendations
                          <Tag style={{ marginLeft: 8, fontSize: 10 }} color="blue">
                            {chaosScore.recommendations.length} suggestions
                          </Tag>
                        </Text>
                        
                        {/* Readiness Score */}
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: 12, 
                          marginBottom: 12,
                          padding: '8px 12px',
                          background: token.colorBgLayout,
                          borderRadius: 8,
                        }}>
                          <Progress
                            type="circle"
                            percent={chaosScore.readinessScore}
                            size={48}
                            strokeColor={
                              chaosScore.readinessScore >= 70 ? colors.status.success :
                              chaosScore.readinessScore >= 40 ? colors.status.warning :
                              colors.status.error
                            }
                            format={(percent) => (
                              <span style={{ fontSize: 12, fontWeight: 600 }}>{percent}</span>
                            )}
                          />
                          <div>
                            <Text strong style={{ fontSize: 12, display: 'block' }}>System Readiness</Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {chaosScore.readinessScore >= 70 ? 'Good to proceed' :
                               chaosScore.readinessScore >= 40 ? 'Proceed with caution' :
                               'Address issues first'}
                            </Text>
                          </div>
                          <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
                            <Text type="secondary" style={{ fontSize: 10, display: 'block' }}>Est. Recovery</Text>
                            <Text strong style={{ fontSize: 11, color: colors.status.success }}>
                              {chaosScore.estimatedRecoveryTime}
                            </Text>
                          </div>
                        </div>

                        {/* Categorized Recommendations */}
                        <div style={{ 
                          background: `${colors.status.warning}08`, 
                          borderRadius: 8, 
                          padding: 12,
                          border: `1px solid ${colors.status.warning}20`,
                          maxHeight: 280,
                          overflow: 'auto',
                        }}>
                          {/* Critical Recommendations */}
                          {chaosScore.recommendations.filter(r => r.priority === 'critical').length > 0 && (
                            <div style={{ marginBottom: 12 }}>
                              <Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                Critical
                              </Text>
                              {chaosScore.recommendations.filter(r => r.priority === 'critical').map((rec) => (
                                <div key={rec.id} style={{ 
                                  display: 'flex', 
                                  gap: 8, 
                                  marginTop: 6,
                                  padding: '6px 8px',
                                  background: `${colors.status.error}10`,
                                  borderRadius: 4,
                                  borderLeft: `3px solid ${colors.status.error}`,
                                }}>
                                  <ExclamationCircleOutlined style={{ color: colors.status.error, marginTop: 2, flexShrink: 0 }} />
                                  <div>
                                    <Text strong style={{ fontSize: 11, display: 'block' }}>{rec.title}</Text>
                                    <Text type="secondary" style={{ fontSize: 10 }}>{rec.description}</Text>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* High Priority Recommendations */}
                          {chaosScore.recommendations.filter(r => r.priority === 'high').length > 0 && (
                            <div style={{ marginBottom: 12 }}>
                              <Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                High Priority
                              </Text>
                              {chaosScore.recommendations.filter(r => r.priority === 'high').map((rec) => (
                                <div key={rec.id} style={{ 
                                  display: 'flex', 
                                  gap: 8, 
                                  marginTop: 6,
                                  padding: '6px 8px',
                                  background: `${colors.status.warning}10`,
                                  borderRadius: 4,
                                  borderLeft: `3px solid ${colors.status.warning}`,
                                }}>
                                  <WarningOutlined style={{ color: colors.status.warning, marginTop: 2, flexShrink: 0 }} />
                                  <div>
                                    <Text strong style={{ fontSize: 11, display: 'block' }}>{rec.title}</Text>
                                    <Text type="secondary" style={{ fontSize: 10 }}>{rec.description}</Text>
                                    {rec.automatable && (
                                      <Tag style={{ fontSize: 9, marginTop: 4 }} color="blue">Automatable</Tag>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Medium & Low Priority */}
                          {chaosScore.recommendations.filter(r => r.priority === 'medium' || r.priority === 'low').length > 0 && (
                            <div>
                              <Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                Suggestions
                              </Text>
                              {chaosScore.recommendations.filter(r => r.priority === 'medium' || r.priority === 'low').slice(0, 3).map((rec) => (
                                <div key={rec.id} style={{ 
                                  display: 'flex', 
                                  gap: 8, 
                                  marginTop: 6,
                                }}>
                                  <CheckCircleOutlined style={{ color: colors.status.info, marginTop: 2, flexShrink: 0 }} />
                                  <div>
                                    <Text style={{ fontSize: 11 }}>{rec.title}</Text>
                                    <Tag style={{ fontSize: 9, marginLeft: 6 }}>{rec.category}</Tag>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* AI Insights */}
                        {chaosScore.insights && chaosScore.insights.length > 0 && (
                          <div style={{ marginTop: 12 }}>
                            <Text type="secondary" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                              Insights
                            </Text>
                            {chaosScore.insights.slice(0, 2).map((insight) => (
                              <div key={insight.id} style={{ 
                                display: 'flex', 
                                gap: 8, 
                                marginTop: 6,
                                padding: '6px 8px',
                                background: token.colorBgLayout,
                                borderRadius: 4,
                              }}>
                                {insight.type === 'risk' && <WarningOutlined style={{ color: colors.status.error, marginTop: 2 }} />}
                                {insight.type === 'opportunity' && <BulbOutlined style={{ color: colors.status.success, marginTop: 2 }} />}
                                {insight.type === 'warning' && <ExclamationCircleOutlined style={{ color: colors.status.warning, marginTop: 2 }} />}
                                {insight.type === 'info' && <InfoCircleOutlined style={{ color: colors.status.info, marginTop: 2 }} />}
                                <div>
                                  <Text strong style={{ fontSize: 11, display: 'block' }}>{insight.title}</Text>
                                  <Text type="secondary" style={{ fontSize: 10 }}>{insight.description}</Text>
                                  {insight.confidence < 1 && (
                                    <Text type="secondary" style={{ fontSize: 9, marginLeft: 4 }}>
                                      ({Math.round(insight.confidence * 100)}% confidence)
                                    </Text>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                        
                        {/* Estimated Impact from Template */}
                        <div style={{ marginTop: 12 }}>
                          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                            Expected Outcome:
                          </Text>
                          <Alert
                            message={selectedChaosTemplate.estimatedImpact}
                            type={selectedChaosTemplate.severity === 'high' ? 'error' : 
                                  selectedChaosTemplate.severity === 'medium' ? 'warning' : 'info'}
                            showIcon={false}
                            style={{ 
                              padding: '8px 12px',
                              fontSize: 12,
                            }}
                          />
                        </div>
                      </Col>
                    </Row>
                  </Card>
                );
              })()}

              {/* Change Type Specific Alert - Only show when there are affected services with HIGH impact */}
              {stats.high > 0 && changeTypeImpactInfo[changeType] && (() => {
                const categoryConfig = impactCategoryConfig[changeTypeImpactInfo[changeType].primaryCategory];
                const alertType = categoryConfig?.severity === 'critical' ? 'error' 
                  : categoryConfig?.severity === 'warning' ? 'warning' : 'info';
                const alertColor = alertType === 'error' ? colors.status.error 
                  : alertType === 'warning' ? colors.status.warning : colors.status.info;
                
                return (
                <Alert
                    message={
                      <Space>
                        {categoryConfig && getCategoryIcon(categoryConfig.iconType, categoryConfig.color)}
                        <span style={{ fontWeight: 500 }}>{changeTypeImpactInfo[changeType].headline}</span>
                        {categoryConfig && (
                          <Tag 
                            style={{ 
                              background: categoryConfig.bgColor,
                              border: `1px solid ${categoryConfig.color}40`,
                              color: categoryConfig.color,
                              fontWeight: 500,
                            }}
                          >
                            {categoryConfig.label}
                          </Tag>
                        )}
                      </Space>
                    }
                    description={
                      <div>
                        <Paragraph style={{ marginBottom: 8, color: token.colorTextSecondary }}>
                          {changeTypeImpactInfo[changeType].whatHappens}
                        </Paragraph>
                        {!changeTypeImpactInfo[changeType].affectsIndirect && stats.medium > 0 && (
                          <Text style={{ fontSize: 12, color: token.colorTextTertiary }}>
                            <InfoCircleOutlined style={{ marginRight: 4 }} />
                            Note: {stats.medium} indirect dependencies shown for awareness only - they won't be affected by this change type.
                          </Text>
                        )}
                      </div>
                    }
                    type={alertType}
                    showIcon={false}
                    style={{
                      background: `${alertColor}08`,
                      border: `1px solid ${alertColor}30`,
                      borderRadius: 8,
                    }}
                  />
                );
              })()}

              {/* Additional alert for high impact count */}
              {stats.high > 0 && changeTypeImpactInfo[changeType]?.primaryCategory !== 'security_exposure' && (
                <Alert
                  message={`${stats.high} High Impact Service(s) Detected`}
                  description={`These services have direct dependencies and will be immediately affected. Review recommendations before proceeding.`}
                  type="error"
                  showIcon
                  style={{ 
                    marginTop: 8,
                    background: `${colors.status.error}08`,
                    border: `1px solid ${colors.status.error}30`,
                    borderRadius: 8,
                  }}
                />
              )}

              {/* Performance-only change notice */}
              {changeType === 'resource_change' && stats.total > 0 && (
                <Alert
                  message={
                    <Space>
                      <ThunderboltOutlined style={{ color: colors.status.warning }} />
                      <span style={{ fontWeight: 500 }}>Performance Impact - Not an Outage</span>
                    </Space>
                  }
                  description={
                    <div>
                      <Paragraph style={{ marginBottom: 4, color: token.colorTextSecondary }}>
                        Resource changes typically cause performance degradation, not complete service outages:
                      </Paragraph>
                      <ul style={{ margin: 0, paddingLeft: 20, color: token.colorTextSecondary }}>
                        <li>Increased response latency</li>
                        <li>Potential CPU throttling</li>
                        <li>Possible OOM kills if memory reduced significantly</li>
                      </ul>
                    </div>
                  }
                  type="warning"
                  showIcon={false}
                  style={{ 
                    marginTop: 8,
                    background: `${colors.status.warning}08`,
                    border: `1px solid ${colors.status.warning}30`,
                    borderRadius: 8,
                  }}
                />
              )}

              {/* No Dependencies Alert with detailed info */}
              {stats.total === 0 && noDependencyInfo && (
                <Alert
                  message={
                    <Space>
                      {noDependencyInfo.scenario === 'NO_GRAPH_MATCH' ? 
                        <QuestionCircleOutlined style={{ color: colors.status.info }} /> :
                        noDependencyInfo.scenario === 'EXTERNAL_ONLY' ? 
                        <GlobalOutlined style={{ color: colors.status.warning }} /> :
                        <CheckCircleOutlined style={{ color: colors.status.success }} />
                      }
                      <span style={{ fontWeight: 500 }}>{noDependencyInfo.title}</span>
                    </Space>
                  }
                  description={
                    <div>
                      <Paragraph style={{ marginBottom: 12, color: token.colorTextSecondary }}>
                        {noDependencyInfo.description}
                      </Paragraph>
                      <Text strong style={{ color: token.colorText }}>Suggestions:</Text>
                      <List
                        size="small"
                        dataSource={noDependencyInfo.suggestions}
                        renderItem={(item) => (
                          <List.Item style={{ padding: '4px 0', border: 'none' }}>
                            <Space>
                              <BulbOutlined style={{ color: colors.status.warning }} />
                              <Text style={{ fontSize: 12, color: token.colorTextSecondary }}>{item}</Text>
                            </Space>
                          </List.Item>
                        )}
                      />
                    </div>
                  }
                  type={noDependencyInfo.alert_type as any}
                  showIcon={false}
                  style={{
                    background: noDependencyInfo.alert_type === 'success' ? `${colors.status.success}08` :
                               noDependencyInfo.alert_type === 'warning' ? `${colors.status.warning}08` :
                               noDependencyInfo.alert_type === 'error' ? `${colors.status.error}08` :
                               `${colors.status.info}08`,
                    border: `1px solid ${
                      noDependencyInfo.alert_type === 'success' ? `${colors.status.success}30` :
                      noDependencyInfo.alert_type === 'warning' ? `${colors.status.warning}30` :
                      noDependencyInfo.alert_type === 'error' ? `${colors.status.error}30` :
                      `${colors.status.info}30`
                    }`,
                    borderRadius: 8,
                  }}
                />
              )}

              {/* Results Tabs */}
              <Card bordered={false}>
                <Tabs activeKey={activeResultTab} onChange={setActiveResultTab}>
                  <TabPane tab={<span><FileTextOutlined /> Affected Services</span>} key="summary">
                <Table
                  dataSource={affectedServices}
                  columns={columns}
                  rowKey="id"
                  pagination={{ pageSize: 10 }}
                  locale={{ emptyText: 'No affected services detected' }}
                      expandable={{
                        expandedRowRender: (record: AffectedService) => {
                          const changeInfo = changeTypeImpactInfo[changeType];
                          // Use correct category based on dependency type
                          let category: string | undefined = record.impact_category;
                          if (!category && changeInfo) {
                            category = record.dependency === 'indirect' 
                              ? changeInfo.indirectCategory 
                              : changeInfo.primaryCategory;
                          }
                          const categoryConfig = category ? impactCategoryConfig[category] : null;
                          
                          return (
                            <div style={{ padding: '12px 16px', backgroundColor: '#fafafa' }}>
                              {/* Impact Description Banner */}
                              {record.impact_description && (
                                <Alert
                                  message={record.impact_description}
                                  type={record.impact === 'high' ? 'error' : record.impact === 'medium' ? 'warning' : 'info'}
                                  style={{ marginBottom: 12 }}
                                  showIcon
                                />
                              )}
                              
                              <Row gutter={24}>
                                <Col span={6}>
                                  <Text strong>Connection Details</Text>
                                  <div style={{ marginTop: 8 }}>
                                    <Text type="secondary">Protocol: </Text>
                                    <Text>{record.connection_details?.protocol || 'Unknown'}</Text>
                                    <br />
                                    <Text type="secondary">Port: </Text>
                                    <Text>{record.connection_details?.port || 'Unknown'}</Text>
                                    <br />
                                    <Text type="secondary">Request Count: </Text>
                                    <Text>{record.connection_details?.request_count?.toLocaleString() || '0'}</Text>
                                  </div>
                                </Col>
                                <Col span={6}>
                                  <Text strong>Impact Analysis</Text>
                                  <div style={{ marginTop: 8 }}>
                                    <Text type="secondary">Dependency: </Text>
                                    <Tag color={record.dependency === 'direct' ? 'red' : 'orange'}>
                                      {record.dependency === 'direct' ? '1-hop (Direct)' : '2-hop (Indirect)'}
                                    </Tag>
                                    <br />
                                    {categoryConfig && (
                                      <>
                                        <Text type="secondary">Impact Type: </Text>
                                        <Tag color={categoryConfig.color}>{categoryConfig.label}</Tag>
                                        <br />
                                      </>
                                    )}
                                    <Text type="secondary">Risk Score: </Text>
                                    <Text>{Math.round(record.risk_score * 100)}%</Text>
                                  </div>
                                </Col>
                                <Col span={6}>
                                  <Text strong>Recovery Info</Text>
                                  <div style={{ marginTop: 8 }}>
                                    {record.recovery_info ? (
                                      <>
                                        <Text type="secondary">Recovery Time: </Text>
                                        <Text>{record.recovery_info.recovery_time || 'Unknown'}</Text>
                                        <br />
                                        <Text type="secondary">Reversible: </Text>
                                        <Tag color={record.recovery_info.reversible ? 'green' : 'red'}>
                                          {record.recovery_info.reversible ? 'Yes' : 'No'}
                                        </Tag>
                                      </>
                                    ) : (
                                      <Text type="secondary">Not available</Text>
                                    )}
                                    {record.risk_factors && record.risk_factors.length > 0 && (
                                      <>
                                        <br />
                                        <Text type="secondary">Risk Factors: </Text>
                                        <div>
                                          {record.risk_factors.map((factor, idx) => (
                                            <Tag key={idx} color="orange" style={{ margin: '2px' }}>
                                              {factor}
                                            </Tag>
                                          ))}
                                        </div>
                                      </>
                                    )}
                                  </div>
                                </Col>
                                <Col span={6}>
                                  <Text strong>Recommendation</Text>
                                  <div style={{ marginTop: 8 }}>
                                    <Text>{record.recommendation}</Text>
                                    {/* Show note if indirect dependency won't be affected */}
                                    {record.dependency === 'indirect' && changeInfo && !changeInfo.affectsIndirect && (
                                      <Alert
                                        message="Note: Indirect dependencies not affected by this change type"
                                        type="info"
                                        style={{ marginTop: 8, fontSize: 11 }}
                                        showIcon
                                      />
                                    )}
                                  </div>
                                </Col>
                              </Row>
                            </div>
                          );
                        },
                      }}
                    />
                  </TabPane>

                  <TabPane tab={<span><ExpandOutlined /> Impact Flow</span>} key="flow">
                    {selectedTarget && (
                      <ImpactFlowDiagram
                        targetName={selectedTarget.name}
                        targetNamespace={selectedTarget.namespace}
                        targetKind={selectedTarget.kind}
                        affectedServices={affectedServices}
                        maxDisplay={10}
                      />
                    )}
                  </TabPane>

                  <TabPane tab={<span><ClockCircleOutlined /> Timeline</span>} key="timeline">
                    <Timeline mode="left">
                      <Timeline.Item color="red" label="Immediate (0-5 min)">
                        <Text strong>Immediate Effects</Text>
                        <br />
                        <Text type="secondary">
                          {stats.high} high-impact services will be affected immediately
                        </Text>
                      </Timeline.Item>
                      <Timeline.Item color="orange" label="Short-term (5-30 min)">
                        <Text strong>Cascading Effects</Text>
                        <br />
                        <Text type="secondary">
                          {stats.medium} medium-impact services may experience degradation
                        </Text>
                      </Timeline.Item>
                      <Timeline.Item color="green" label="Long-term (30+ min)">
                        <Text strong>System Adaptation</Text>
                        <br />
                        <Text type="secondary">
                          {stats.low} low-impact services will adapt to the change
                        </Text>
                      </Timeline.Item>
                    </Timeline>
                  </TabPane>

                  <TabPane tab={<span><RollbackOutlined /> Rollback</span>} key="rollback">
                    {(() => {
                      // Calculate dynamic rollback metrics
                      const directCount = affectedServices.filter(s => s.dependency === 'direct').length;
                      const indirectCount = affectedServices.filter(s => s.dependency === 'indirect').length;
                      const totalAffected = stats.total;
                      
                      // Feasibility based on change type and affected services
                      let feasibility: 'high' | 'medium' | 'low' = 'high';
                      let feasibilityColor = 'green';
                      let feasibilityReason = '';
                      
                      if (changeType === 'delete') {
                        feasibility = totalAffected > 20 ? 'low' : totalAffected > 5 ? 'medium' : 'high';
                        feasibilityReason = 'Deleted resources require re-deployment from manifests';
                      } else if (changeType === 'scale_down') {
                        feasibility = 'high';
                        feasibilityReason = 'Simply scale back up to restore service';
                      } else if (changeType === 'network_isolate' || changeType === 'network_policy_apply') {
                        feasibility = 'high';
                        feasibilityReason = 'Remove or modify network policy to restore connectivity';
                      } else if (changeType === 'config_change') {
                        feasibility = totalAffected > 10 ? 'medium' : 'high';
                        feasibilityReason = 'Revert ConfigMap/Secret and restart affected pods';
                      } else if (changeType === 'image_update') {
                        feasibility = 'high';
                        feasibilityReason = 'Rollback to previous image tag';
                      } else {
                        feasibility = totalAffected > 15 ? 'medium' : 'high';
                      }
                      
                      feasibilityColor = feasibility === 'high' ? 'green' : feasibility === 'medium' ? 'orange' : 'red';
                      
                      // Estimated time based on affected services
                      let estimatedTime = '';
                      if (totalAffected === 0) {
                        estimatedTime = '< 1 minute';
                      } else if (totalAffected <= 5) {
                        estimatedTime = '2-5 minutes';
                      } else if (totalAffected <= 15) {
                        estimatedTime = '5-15 minutes';
                      } else if (totalAffected <= 30) {
                        estimatedTime = '15-30 minutes';
                      } else {
                        estimatedTime = '30+ minutes';
                      }
                      
                      // Risk score
                      const avgRiskScore = affectedServices.length > 0 
                        ? affectedServices.reduce((sum, s) => sum + (s.risk_score || 0), 0) / affectedServices.length
                        : 0;
                      
                      // Dynamic rollback steps based on change type
                      const baseSteps = [
                        { step: 'Identify affected services', detail: `${totalAffected} services identified in blast radius` },
                      ];
                      
                      const changeSpecificSteps: Record<string, { step: string; detail: string }[]> = {
                        delete: [
                          { step: 'Locate original manifests', detail: 'Find deployment YAML from Git or backup' },
                          { step: 'Re-apply deleted resources', detail: `kubectl apply -f <manifest> for ${selectedTarget?.name}` },
                          { step: 'Wait for pods to be ready', detail: 'Monitor pod status until Running' },
                        ],
                        scale_down: [
                          { step: 'Scale deployment back up', detail: `kubectl scale deployment/${selectedTarget?.name} --replicas=<original>` },
                          { step: 'Wait for pods to be ready', detail: 'Monitor rollout status' },
                        ],
                        network_isolate: [
                          { step: 'Remove network policy', detail: `kubectl delete networkpolicy <policy-name> -n ${selectedTarget?.namespace}` },
                          { step: 'Verify connectivity restored', detail: 'Test network connectivity between services' },
                        ],
                        network_policy_apply: [
                          { step: 'Delete applied network policy', detail: `kubectl delete networkpolicy <policy-name> -n ${selectedTarget?.namespace}` },
                          { step: 'Verify connectivity restored', detail: 'Test network connectivity between services' },
                        ],
                        config_change: [
                          { step: 'Revert ConfigMap/Secret', detail: 'Apply previous version from Git history' },
                          { step: 'Restart affected pods', detail: `kubectl rollout restart deployment/${selectedTarget?.name}` },
                        ],
                        image_update: [
                          { step: 'Rollback deployment', detail: `kubectl rollout undo deployment/${selectedTarget?.name}` },
                          { step: 'Verify rollback status', detail: 'kubectl rollout status' },
                        ],
                        resource_change: [
                          { step: 'Revert resource limits', detail: 'Apply original CPU/Memory limits' },
                          { step: 'Restart affected pods', detail: 'Pods will restart with new limits' },
                        ],
                        port_change: [
                          { step: 'Revert port configuration', detail: 'Update service/deployment to original ports' },
                          { step: 'Update client configurations', detail: 'Notify dependent services of port change' },
                        ],
                      };
                      
                      const specificSteps = changeSpecificSteps[changeType] || [
                        { step: 'Revert changes', detail: 'Apply original configuration' },
                      ];
                      
                      const verifySteps = [
                        { step: 'Verify service health', detail: `Check health endpoints for ${directCount} direct dependencies` },
                        { step: 'Monitor for cascading issues', detail: `Watch ${indirectCount} indirect dependencies for errors` },
                      ];
                      
                      const allSteps = [...baseSteps, ...specificSteps, ...verifySteps];
                      
                      // High impact services that need priority attention
                      const highPriorityServices = affectedServices
                        .filter(s => s.impact === 'high' || s.dependency === 'direct')
                        .slice(0, 5);
                      
                      return (
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                          {/* Rollback Overview */}
                          <Row gutter={16}>
                            <Col span={8}>
                              <Card size="small" style={{ textAlign: 'center' }}>
                                <Statistic
                                  title="Feasibility"
                                  value={feasibility.toUpperCase()}
                                  valueStyle={{ 
                                    color: feasibilityColor === 'green' ? '#4d9f7c' : 
                                           feasibilityColor === 'orange' ? '#b89b5d' : '#c75450',
                                    fontSize: 20
                                  }}
                                />
                                <Text type="secondary" style={{ fontSize: 11 }}>{feasibilityReason}</Text>
              </Card>
                            </Col>
                            <Col span={8}>
                              <Card size="small" style={{ textAlign: 'center' }}>
                                <Statistic
                                  title="Estimated Time"
                                  value={estimatedTime}
                                  valueStyle={{ fontSize: 20 }}
                                  prefix={<ClockCircleOutlined />}
                                />
                                <Text type="secondary" style={{ fontSize: 11 }}>Based on {totalAffected} affected services</Text>
                              </Card>
                            </Col>
                            <Col span={8}>
                              <Card size="small" style={{ textAlign: 'center' }}>
                                <Statistic
                                  title="Risk Score"
                                  value={Math.round(avgRiskScore * 100)}
                                  suffix="%"
                                  valueStyle={{ 
                                    color: avgRiskScore > 0.7 ? '#c75450' : avgRiskScore > 0.4 ? '#b89b5d' : '#4d9f7c',
                                    fontSize: 20
                                  }}
                                />
                                <Text type="secondary" style={{ fontSize: 11 }}>Average rollback complexity</Text>
                              </Card>
                            </Col>
                          </Row>

                          {/* Rollback Steps */}
                          <Card 
                            size="small" 
                            title={
                              <Space>
                                <RollbackOutlined style={{ color: '#0891b2' }} />
                                <span>Rollback Steps for "{changeTypes.find(c => c.key === changeType)?.label}"</span>
                              </Space>
                            }
                          >
                            <Timeline>
                              {allSteps.map((item, index) => (
                                <Timeline.Item 
                                  key={index}
                                  color={index === 0 ? 'blue' : index === allSteps.length - 1 ? 'green' : 'gray'}
                                >
                                  <Text strong>{index + 1}. {item.step}</Text>
                                  <br />
                                  <Text type="secondary" style={{ fontSize: 12 }}>{item.detail}</Text>
                                </Timeline.Item>
                              ))}
                            </Timeline>
                          </Card>

                          {/* Priority Services */}
                          {highPriorityServices.length > 0 && (
                            <Card 
                              size="small" 
                              title={
                                <Space>
                                  <ExclamationCircleOutlined style={{ color: '#b89b5d' }} />
                                  <span>Priority Services to Monitor After Rollback</span>
                                  <Tag color="orange">{highPriorityServices.length}</Tag>
                                </Space>
                              }
                            >
                              <List
                                size="small"
                                dataSource={highPriorityServices}
                                renderItem={(service) => (
                                  <List.Item>
                                    <Space>
                                      <Tag color={service.impact === 'high' ? 'red' : 'orange'}>
                                        {service.impact?.toUpperCase()}
                                      </Tag>
                                      <Text strong>{service.name}</Text>
                                      <Text type="secondary">({service.namespace})</Text>
                                      <Tag>{service.dependency}</Tag>
                                    </Space>
                                  </List.Item>
                                )}
                              />
                            </Card>
                          )}

                          {/* Quick Commands */}
                          <Card 
                            size="small" 
                            title={
                              <Space>
                                <CodeOutlined style={{ color: '#7c8eb5' }} />
                                <span>Quick Rollback Commands</span>
                              </Space>
                            }
                          >
                            <pre style={{ 
                              background: '#1e1e1e', 
                              color: '#d4d4d4', 
                              padding: 12, 
                              borderRadius: 4,
                              fontSize: 11,
                              overflow: 'auto',
                              margin: 0
                            }}>
{changeType === 'delete' ? `# Re-apply deleted resource
kubectl apply -f <manifest-file>.yaml -n ${selectedTarget?.namespace}

# Or restore from Git
git checkout HEAD~1 -- k8s/${selectedTarget?.name}.yaml
kubectl apply -f k8s/${selectedTarget?.name}.yaml` :
changeType === 'scale_down' ? `# Scale back up
kubectl scale deployment/${selectedTarget?.name} --replicas=<original-count> -n ${selectedTarget?.namespace}

# Check rollout status
kubectl rollout status deployment/${selectedTarget?.name} -n ${selectedTarget?.namespace}` :
changeType === 'network_isolate' || changeType === 'network_policy_apply' ? `# Remove network policy
kubectl delete networkpolicy ${selectedTarget?.name}-policy -n ${selectedTarget?.namespace}

# Verify connectivity
kubectl exec -it <test-pod> -- curl http://${selectedTarget?.name}:80/health` :
changeType === 'image_update' ? `# Rollback to previous revision
kubectl rollout undo deployment/${selectedTarget?.name} -n ${selectedTarget?.namespace}

# Or rollback to specific revision
kubectl rollout undo deployment/${selectedTarget?.name} --to-revision=<revision-number>` :
changeType === 'config_change' ? `# Revert ConfigMap from Git
git checkout HEAD~1 -- configmaps/${selectedTarget?.name}-config.yaml
kubectl apply -f configmaps/${selectedTarget?.name}-config.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment/${selectedTarget?.name} -n ${selectedTarget?.namespace}` :
`# Generic rollback
kubectl rollout undo deployment/${selectedTarget?.name} -n ${selectedTarget?.namespace}

# Check status
kubectl get pods -n ${selectedTarget?.namespace} -l app=${selectedTarget?.name}`}
                            </pre>
                          </Card>
                        </Space>
                      );
                    })()}
                  </TabPane>
                </Tabs>

                {/* Export Button */}
                <div style={{ marginTop: 16, textAlign: 'right' }}>
                  <Button
                    icon={<DownloadOutlined />}
                    onClick={() => setExportModalVisible(true)}
                    disabled={stats.total === 0 && !noDependencyInfo}
                  >
                    Export Report
                  </Button>
                </div>
              </Card>

              {/* Simulation Details */}
              <Card title="Simulation Details" bordered={false} size="small">
                <Row gutter={16}>
                  <Col span={12}>
                <Paragraph>
                  <Text strong>Target: </Text>
                  <Tag color="blue">{selectedTarget?.name}</Tag>
                  <Tag>{selectedTarget?.namespace}</Tag>
                  <Tag color="cyan">{selectedTarget?.kind}</Tag>
                </Paragraph>
                <Paragraph>
                  <Text strong>Change Type: </Text>
                  <Tag>{changeTypes.find(c => c.key === changeType)?.label}</Tag>
                </Paragraph>
                  </Col>
                  <Col span={12}>
                <Paragraph>
                  <Text strong>Graph Matches: </Text>
                  <Tag color={matchingGraphNodeIds.length > 0 ? 'green' : 'red'}>
                    {matchingGraphNodeIds.length} node(s)
                  </Tag>
                  {matchingGraphNodeIds.length === 0 && (
                    <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                      Target not found in dependency graph
                    </Text>
                  )}
                </Paragraph>
                <Paragraph>
                  <Text strong>Blast Radius: </Text>
                  {stats.total} services within 2-hop dependency chain
                </Paragraph>
                  </Col>
                </Row>
              </Card>
            </Space>
          )}
        </Col>
      </Row>
      )}

      {/* Scheduled Simulations Tab Content */}
      {activeMainTab === 'scheduled' && (
        <Card bordered={false}>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <ScheduleOutlined style={{ fontSize: 20, color: colors.primary.main }} />
              <Title level={4} style={{ margin: 0 }}>Scheduled Simulations</Title>
            </Space>
            <Button 
              type="primary" 
              icon={<PlusOutlined />}
              onClick={() => {
                setActiveMainTab('simulation');
                message.info('Configure a simulation first, then click "Schedule" to schedule it.');
              }}
            >
              New Schedule
            </Button>
          </div>
          
          {scheduledSimsLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">Loading scheduled simulations...</Text>
              </div>
            </div>
          ) : scheduledSimulations.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="No scheduled simulations"
            >
              <Button type="primary" onClick={() => setActiveMainTab('simulation')}>
                Create Your First Schedule
              </Button>
            </Empty>
          ) : (
            <Table
              dataSource={scheduledSimulations}
              rowKey="id"
              columns={[
                {
                  title: 'Name',
                  dataIndex: 'name',
                  key: 'name',
                  render: (name: string, record: ScheduledSimulation) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>{record.description}</Text>
                    </Space>
                  ),
                },
                {
                  title: 'Target',
                  key: 'target',
                  render: (_: any, record: ScheduledSimulation) => (
                    <Space direction="vertical" size={0}>
                      <Text>{record.target_namespace}/{record.target_name}</Text>
                      <Space size={4}>
                        <Tag>{record.target_kind}</Tag>
                        <Tag color="blue">{record.change_type}</Tag>
                      </Space>
                    </Space>
                  ),
                },
                {
                  title: 'Schedule',
                  key: 'schedule',
                  render: (_: any, record: ScheduledSimulation) => (
                    <Space direction="vertical" size={0}>
                      <Tag color={record.schedule_type === 'once' ? 'green' : 'blue'}>
                        {record.schedule_type === 'once' ? 'Once' : record.schedule_type}
                      </Tag>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {record.scheduled_time 
                          ? new Date(record.scheduled_time).toLocaleString()
                          : 'Not scheduled'}
                      </Text>
                    </Space>
                  ),
                },
                {
                  title: 'Status',
                  dataIndex: 'status',
                  key: 'status',
                  render: (status: string) => {
                    const statusConfig: Record<string, { color: string; icon: React.ReactNode }> = {
                      scheduled: { color: 'blue', icon: <ClockCircleOutlined /> },
                      running: { color: 'processing', icon: <SyncOutlined spin /> },
                      completed: { color: 'success', icon: <CheckCircleOutlined /> },
                      failed: { color: 'error', icon: <ExclamationCircleOutlined /> },
                      cancelled: { color: 'default', icon: <DeleteOutlined /> },
                    };
                    const config = statusConfig[status] || statusConfig.scheduled;
                    return (
                      <Tag color={config.color} icon={config.icon}>
                        {status.toUpperCase()}
                      </Tag>
                    );
                  },
                },
                {
                  title: 'Last Run',
                  key: 'last_run',
                  render: (_: any, record: ScheduledSimulation) => (
                    <Space direction="vertical" size={0}>
                      {record.last_run_at ? (
                        <>
                          <Text style={{ fontSize: 12 }}>{new Date(record.last_run_at).toLocaleString()}</Text>
                          <Tag color={record.last_run_result === 'success' ? 'green' : 'red'}>
                            {record.last_run_result || 'unknown'}
                          </Tag>
                        </>
                      ) : (
                        <Text type="secondary">Never</Text>
                      )}
                    </Space>
                  ),
                },
                {
                  title: 'Actions',
                  key: 'actions',
                  width: 220,
                  render: (_: any, record: ScheduledSimulation) => (
                    <Space size="small" wrap>
                      <Tooltip title={record.status === 'scheduled' 
                        ? "Execute this simulation immediately without waiting for the scheduled time" 
                        : "Simulation is not in scheduled state"}>
                        <Button 
                          size="small"
                          type="primary"
                          ghost
                          icon={<PlayCircleOutlined />}
                          onClick={() => runScheduledSimulationNow(record)}
                          disabled={record.status !== 'scheduled'}
                        >
                          Run Now
                        </Button>
                      </Tooltip>
                      
                      <Tooltip title="View simulation configuration details">
                        <Button
                          size="small"
                          icon={<FileTextOutlined />}
                          onClick={() => {
                            const changeInfo = changeTypes.find(c => c.key === record.change_type);
                            const isCompleted = record.status === 'completed';
                            const isPending = record.status === 'scheduled';
                            
                            Modal.info({
                              title: (
                                <Space>
                                  <ScheduleOutlined style={{ color: colors.primary.main }} />
                                  <Text strong style={{ fontSize: 16 }}>{record.name}</Text>
                                  <Tag color={
                                    record.status === 'completed' ? 'success' :
                                    record.status === 'scheduled' ? 'processing' :
                                    record.status === 'failed' ? 'error' : 'default'
                                  }>
                                    {record.status.toUpperCase()}
                                  </Tag>
                                </Space>
                              ),
                              width: 600,
                              content: (
                                <div>
                                  {/* What is this? */}
                                  <Alert 
                                    message={<Text strong>What is this?</Text>}
                                    description={
                                      <Text>
                                        This is a scheduled <Text strong>impact simulation</Text>. 
                                        It will automatically run at the specified time and analyze how 
                                        the proposed change to the target resource would affect other services.
                                        <br/><br/>
                                        <Text strong>Note:</Text> This is a simulation only - no actual changes 
                                        will be made. It helps you preview potential impacts before implementation.
                                      </Text>
                                    }
                                    type="info" 
                                    showIcon
                                    icon={<BulbOutlined />}
                                    style={{ marginBottom: 16 }}
                                  />
                                  
                                  {record.description && (
                                    <Paragraph type="secondary" style={{ marginBottom: 16, fontStyle: 'italic' }}>
                                      "{record.description}"
                                    </Paragraph>
                                  )}
                                  
                                  {/* What will be simulated? */}
                                  <div style={{ 
                                    background: 'rgba(46, 184, 184, 0.1)', 
                                    padding: 16, 
                                    borderRadius: 8, 
                                    marginBottom: 16 
                                  }}>
                                    <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                      <AimOutlined /> What Will Be Simulated?
                                    </Text>
                                    <Row gutter={[16, 12]}>
                                      <Col span={24}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Target Resource</Text>
                                        <div>
                                          <Text strong style={{ fontSize: 15 }}>
                                            {record.target_namespace}/{record.target_name}
                                          </Text>
                                        </div>
                                        <Tag color="cyan" style={{ marginTop: 4 }}>{record.target_kind}</Tag>
                                      </Col>
                                      <Col span={24}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Change to Simulate</Text>
                                        <div style={{ marginTop: 4 }}>
                                          <Tag color="blue" style={{ fontSize: 13 }}>
                                            {changeInfo?.icon} {changeInfo?.label || record.change_type}
                                          </Tag>
                                        </div>
                                        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                                          {changeInfo?.description || 'This change will be simulated'}
                                        </Text>
                                      </Col>
                                    </Row>
                                  </div>
                                  
                                  {/* When will it run? */}
                                  <div style={{ 
                                    background: 'rgba(100, 181, 246, 0.1)', 
                                    padding: 16, 
                                    borderRadius: 8, 
                                    marginBottom: 16 
                                  }}>
                                    <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                      <CalendarOutlined /> When Will It Run?
                                    </Text>
                                    <Row gutter={[16, 12]}>
                                      <Col span={24}>
                                        <div style={{ 
                                          background: 'rgba(46, 184, 184, 0.2)', 
                                          padding: 12, 
                                          borderRadius: 6,
                                          textAlign: 'center'
                                        }}>
                                          <Text strong style={{ fontSize: 18, color: colors.primary.main }}>
                                            {record.scheduled_time 
                                              ? new Date(record.scheduled_time).toLocaleString('en-US', {
                                                  weekday: 'long',
                                                  year: 'numeric',
                                                  month: 'long',
                                                  day: 'numeric',
                                                  hour: '2-digit',
                                                  minute: '2-digit'
                                                })
                                              : 'Not scheduled'}
                                          </Text>
                                        </div>
                                      </Col>
                                      <Col span={12}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Schedule Type</Text>
                                        <div style={{ marginTop: 4 }}>
                                          <Tag color={record.schedule_type === 'once' ? 'green' : 'blue'}>
                                            {record.schedule_type === 'once' ? '🔂 One-time' : 
                                             record.schedule_type === 'daily' ? '📅 Daily' : 
                                             record.schedule_type === 'weekly' ? '📆 Weekly' : record.schedule_type}
                                          </Tag>
                                        </div>
                                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                                          {record.schedule_type === 'once' 
                                            ? 'Will run once and complete' 
                                            : record.schedule_type === 'daily'
                                            ? 'Will repeat at the same time every day'
                                            : 'Will repeat at the same time every week'}
                                        </Text>
                                      </Col>
                                      <Col span={12}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Notification</Text>
                                        <div style={{ marginTop: 4 }}>
                                          <Tag icon={<BellOutlined />}>
                                            {record.notify_before_minutes || 15} min before
                                          </Tag>
                                        </div>
                                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                                          You will receive a WebSocket notification {record.notify_before_minutes || 15} minutes 
                                          before the simulation starts
                                        </Text>
                                      </Col>
                                    </Row>
                                  </div>
                                  
                                  {/* What happens after? - Only show for recurring */}
                                  {record.schedule_type !== 'once' && (
                                    <div style={{ 
                                      background: 'rgba(156, 39, 176, 0.1)', 
                                      padding: 16, 
                                      borderRadius: 8, 
                                      marginBottom: 16 
                                    }}>
                                      <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
                                        <SyncOutlined /> Recurring Schedule
                                      </Text>
                                      <Text>
                                        This simulation will automatically repeat <strong>{record.schedule_type === 'daily' ? 'every day' : 'every week'}</strong>. 
                                        Results from each run can be viewed in the History tab.
                                      </Text>
                                    </div>
                                  )}
                                  
                                  {/* Last Execution */}
                                  {record.last_run_at ? (
                                    <div style={{ 
                                      background: record.last_run_result === 'success' 
                                        ? 'rgba(76, 175, 80, 0.1)' 
                                        : 'rgba(244, 67, 54, 0.1)', 
                                      padding: 16, 
                                      borderRadius: 8 
                                    }}>
                                      <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                        <HistoryOutlined /> Last Execution
                                      </Text>
                                      <Row gutter={[16, 8]}>
                                        <Col span={14}>
                                          <Text type="secondary" style={{ fontSize: 11 }}>Executed At</Text>
                                          <div>
                                            <Text strong>
                                              {new Date(record.last_run_at).toLocaleString()}
                                            </Text>
                                          </div>
                                        </Col>
                                        <Col span={10}>
                                          <Text type="secondary" style={{ fontSize: 11 }}>Result</Text>
                                          <div>
                                            <Tag 
                                              color={record.last_run_result === 'success' ? 'success' : 'error'}
                                              icon={record.last_run_result === 'success' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                                            >
                                              {record.last_run_result === 'success' ? 'Success' : 'Failed'}
                                            </Tag>
                                          </div>
                                        </Col>
                                        <Col span={24}>
                                          <Text type="secondary" style={{ fontSize: 11 }}>
                                            {record.last_run_result === 'success' 
                                              ? '✓ Simulation completed successfully. View results in the History tab.'
                                              : '✗ An error occurred during simulation. Check the logs for details.'}
                                          </Text>
                                        </Col>
                                      </Row>
                                    </div>
                                  ) : isPending && (
                                    <div style={{ 
                                      background: 'rgba(33, 150, 243, 0.1)', 
                                      padding: 16, 
                                      borderRadius: 8 
                                    }}>
                                      <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
                                        <ClockCircleOutlined /> Status
                                      </Text>
                                      <Text>
                                        This simulation has not run yet. It will automatically execute at the scheduled time, 
                                        or you can click "Run Now" to start it manually.
                                      </Text>
                                    </div>
                                  )}
                                </div>
                              ),
                            });
                          }}
                        >
                          Details
                        </Button>
                      </Tooltip>
                      
                      <Popconfirm
                        title="Cancel this scheduled simulation?"
                        description="This will permanently delete the schedule."
                        onConfirm={() => cancelScheduledSimulation(record.id)}
                        okText="Cancel Schedule"
                        cancelText="Keep"
                        okButtonProps={{ danger: true }}
                        disabled={record.status === 'running'}
                      >
                        <Tooltip title={record.status === 'running' 
                          ? "Cannot cancel while simulation is running" 
                          : "Cancel and delete this scheduled simulation"}>
                          <Button 
                            size="small" 
                            danger 
                            icon={<DeleteOutlined />}
                            disabled={record.status === 'running'}
                          >
                            Cancel
                          </Button>
                        </Tooltip>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* History Tab Content */}
      {activeMainTab === 'history' && (
        <Card bordered={false}>
          <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Space>
              <HistoryOutlined style={{ fontSize: 20, color: colors.primary.main }} />
              <Title level={4} style={{ margin: 0 }}>Simulation History</Title>
            </Space>
            <Button 
              icon={<SyncOutlined />} 
              onClick={() => refetchHistory()}
              loading={historyLoading}
            >
              Refresh
            </Button>
          </div>
          
          {historyLoading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin size="large" />
              <div style={{ marginTop: 16 }}>
                <Text type="secondary">Loading history...</Text>
              </div>
            </div>
          ) : simulationHistory.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="No simulation history yet"
            >
              <Text type="secondary">Run a simulation to see history here</Text>
            </Empty>
          ) : (
            <Table
              dataSource={simulationHistory}
              rowKey="id"
              pagination={{ pageSize: 10 }}
              columns={[
                {
                  title: 'Target',
                  key: 'target',
                  render: (_: any, record: SimulationHistoryEntry) => (
                    <Space direction="vertical" size={0}>
                      <Text strong>{record.target_name}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>{record.target_namespace}</Text>
                      <Tag>{record.target_kind}</Tag>
                    </Space>
                  ),
                },
                {
                  title: 'Change Type',
                  dataIndex: 'change_type',
                  key: 'change_type',
                  render: (changeType: string) => {
                    const changeInfo = changeTypes.find(c => c.key === changeType);
                    return (
                      <Tag color="blue">
                        {changeInfo?.icon} {changeInfo?.label || changeType}
                      </Tag>
                    );
                  },
                },
                {
                  title: 'Impact Summary',
                  key: 'impact',
                  render: (_: any, record: SimulationHistoryEntry) => {
                    if (record.total_affected === 0) {
                      return (
                        <Space direction="vertical" size={0}>
                          <Tag color="success" icon={<CheckCircleOutlined />}>
                            No Impact Detected
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            No dependent services affected
                          </Text>
                        </Space>
                      );
                    }
                    return (
                      <Space direction="vertical" size={4}>
                        <Space>
                          <Text strong style={{ color: colors.primary.main, fontSize: 16 }}>
                            {record.total_affected}
                          </Text>
                          <Text type="secondary">affected</Text>
                        </Space>
                        <Space size={4} wrap>
                          {record.high_impact > 0 && (
                            <Tag color="red" icon={<ExclamationCircleOutlined />}>
                              {record.high_impact} high
                            </Tag>
                          )}
                          {record.medium_impact > 0 && (
                            <Tag color="orange" icon={<WarningOutlined />}>
                              {record.medium_impact} medium
                            </Tag>
                          )}
                          {record.low_impact > 0 && (
                            <Tag color="green" icon={<CheckCircleOutlined />}>
                              {record.low_impact} low
                            </Tag>
                          )}
                        </Space>
                      </Space>
                    );
                  },
                },
                {
                  title: 'Status',
                  dataIndex: 'status',
                  key: 'status',
                  render: (status: string) => (
                    <Tag color={status === 'completed' ? 'green' : 'red'}>
                      {status === 'completed' ? <CheckCircleOutlined /> : <ExclamationCircleOutlined />}
                      {' '}{status}
                    </Tag>
                  ),
                },
                {
                  title: 'Date',
                  dataIndex: 'created_at',
                  key: 'created_at',
                  render: (date: string) => (
                    <Space direction="vertical" size={0}>
                      <Text>{new Date(date).toLocaleDateString()}</Text>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {new Date(date).toLocaleTimeString()}
                      </Text>
                    </Space>
                  ),
                  sorter: (a: SimulationHistoryEntry, b: SimulationHistoryEntry) => 
                    new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
                  defaultSortOrder: 'ascend' as const,
                },
                {
                  title: 'Actions',
                  key: 'actions',
                  width: 280,
                  render: (_: any, record: SimulationHistoryEntry) => (
                    <Space size="small" wrap>
                      <Tooltip title="View full simulation results and affected services">
                        <Button 
                          size="small" 
                          icon={<FileTextOutlined />}
                          onClick={() => {
                            const changeInfo = changeTypes.find(c => c.key === record.change_type);
                            const hasAffectedServices = (record.result_summary?.affected_services?.length || 0) > 0;
                            
                            Modal.info({
                              title: (
                                <Space>
                                  <ThunderboltOutlined style={{ color: colors.primary.main }} />
                                  <Text strong style={{ fontSize: 16 }}>Simulation Results</Text>
                                  <Tag color={record.status === 'completed' ? 'success' : 'error'}>
                                    {record.status === 'completed' ? 'Completed' : 'Failed'}
                                  </Tag>
                                </Space>
                              ),
                              width: 700,
                              content: (
                                <div style={{ maxHeight: 600, overflow: 'auto' }}>
                                  {/* What was simulated? */}
                                  <div style={{ 
                                    background: 'rgba(46, 184, 184, 0.1)', 
                                    padding: 16, 
                                    borderRadius: 8, 
                                    marginBottom: 16 
                                  }}>
                                    <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                      <AimOutlined /> What Was Simulated?
                                    </Text>
                                    <Row gutter={[16, 8]}>
                                      <Col span={24}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Target Resource</Text>
                                        <div>
                                          <Text strong style={{ fontSize: 15 }}>
                                            {record.target_namespace}/{record.target_name}
                                          </Text>
                                        </div>
                                        <Space style={{ marginTop: 8 }}>
                                          <Tag color="cyan">{record.target_kind}</Tag>
                                          <Tag color="blue">
                                            {changeInfo?.icon} {changeInfo?.label || record.change_type}
                                          </Tag>
                                        </Space>
                                      </Col>
                                      <Col span={24}>
                                        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                                          {changeInfo?.description || 'This change was simulated'}
                                        </Text>
                                      </Col>
                                    </Row>
                                  </div>
                                  
                                  {/* Impact Summary - Visual */}
                                  <div style={{ 
                                    background: record.total_affected > 0 
                                      ? 'rgba(250, 173, 20, 0.1)' 
                                      : 'rgba(76, 175, 80, 0.1)', 
                                    padding: 16, 
                                    borderRadius: 8, 
                                    marginBottom: 16 
                                  }}>
                                    <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                      <WarningOutlined /> Impact Analysis
                                    </Text>
                                    
                                    {record.total_affected === 0 ? (
                                      <div style={{ textAlign: 'center', padding: 16 }}>
                                        <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a', marginBottom: 12 }} />
                                        <Title level={4} style={{ margin: 0, color: '#52c41a' }}>
                                          No Services Affected
                                        </Title>
                                        <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                                          This change would not impact any other services. 
                                          The resource appears to be isolated or has no detected dependencies.
                                        </Text>
                                      </div>
                                    ) : (
                                      <>
                                        <Row gutter={16}>
                                          <Col span={6}>
                                            <div style={{ textAlign: 'center' }}>
                                              <div style={{ fontSize: 32, fontWeight: 'bold', color: colors.primary.main }}>
                                                {record.total_affected}
                                              </div>
                                              <Text type="secondary" style={{ fontSize: 11 }}>Total Affected</Text>
                                            </div>
                                          </Col>
                                          <Col span={6}>
                                            <div style={{ textAlign: 'center' }}>
                                              <div style={{ fontSize: 32, fontWeight: 'bold', color: '#ff4d4f' }}>
                                                {record.high_impact}
                                              </div>
                                              <Text type="secondary" style={{ fontSize: 11 }}>
                                                <ExclamationCircleOutlined /> High Risk
                                              </Text>
                                            </div>
                                          </Col>
                                          <Col span={6}>
                                            <div style={{ textAlign: 'center' }}>
                                              <div style={{ fontSize: 32, fontWeight: 'bold', color: '#faad14' }}>
                                                {record.medium_impact}
                                              </div>
                                              <Text type="secondary" style={{ fontSize: 11 }}>
                                                <WarningOutlined /> Medium Risk
                                              </Text>
                                            </div>
                                          </Col>
                                          <Col span={6}>
                                            <div style={{ textAlign: 'center' }}>
                                              <div style={{ fontSize: 32, fontWeight: 'bold', color: '#52c41a' }}>
                                                {record.low_impact}
                                              </div>
                                              <Text type="secondary" style={{ fontSize: 11 }}>
                                                <CheckCircleOutlined /> Low Risk
                                              </Text>
                                            </div>
                                          </Col>
                                        </Row>
                                        <Alert
                                          message={
                                            record.high_impact > 0 
                                              ? `⚠️ Warning: ${record.high_impact} high-risk service(s) will be affected!`
                                              : record.medium_impact > 0
                                              ? `ℹ️ ${record.medium_impact} medium-risk service(s) will be affected.`
                                              : `✓ Only low-risk services will be affected.`
                                          }
                                          type={record.high_impact > 0 ? 'error' : record.medium_impact > 0 ? 'warning' : 'success'}
                                          style={{ marginTop: 12 }}
                                          showIcon
                                        />
                                      </>
                                    )}
                                  </div>
                                  
                                  {/* Blast Radius & Confidence */}
                                  <Row gutter={16} style={{ marginBottom: 16 }}>
                                    <Col span={12}>
                                      <div style={{ 
                                        background: 'rgba(244, 67, 54, 0.1)', 
                                        padding: 16, 
                                        borderRadius: 8,
                                        height: '100%'
                                      }}>
                                        <Text strong style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>
                                          <FireOutlined /> Blast Radius
                                        </Text>
                                        <div style={{ fontSize: 28, fontWeight: 'bold', textAlign: 'center', margin: '8px 0' }}>
                                          {record.blast_radius} <Text type="secondary" style={{ fontSize: 14 }}>services</Text>
                                        </div>
                                        <Text type="secondary" style={{ fontSize: 11 }}>
                                          Total number of services that could be directly or indirectly impacted by this change
                                        </Text>
                                      </div>
                                    </Col>
                                    <Col span={12}>
                                      <div style={{ 
                                        background: 'rgba(76, 175, 80, 0.1)', 
                                        padding: 16, 
                                        borderRadius: 8,
                                        height: '100%'
                                      }}>
                                        <Text strong style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>
                                          <SafetyCertificateOutlined /> Confidence Score
                                        </Text>
                                        <div style={{ 
                                          fontSize: 28, 
                                          fontWeight: 'bold',
                                          textAlign: 'center',
                                          margin: '8px 0',
                                          color: (record.confidence_score || 0) > 0.7 ? '#52c41a' : '#faad14'
                                        }}>
                                          {Math.round((record.confidence_score || 0) * 100)}%
                                        </div>
                                        <Text type="secondary" style={{ fontSize: 11 }}>
                                          {(record.confidence_score || 0) > 0.7 
                                            ? 'High confidence - sufficient traffic data available'
                                            : 'Medium confidence - more traffic data may be needed'}
                                        </Text>
                                      </div>
                                    </Col>
                                  </Row>
                                  
                                  {/* Affected Services */}
                                  {hasAffectedServices && (
                                    <div style={{ 
                                      background: 'rgba(100, 181, 246, 0.1)', 
                                      padding: 16, 
                                      borderRadius: 8, 
                                      marginBottom: 16 
                                    }}>
                                      <Text strong style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
                                        <ClusterOutlined /> Affected Services ({record.result_summary?.affected_services?.length || 0})
                                      </Text>
                                      <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 11 }}>
                                        The following services would be affected if this change is implemented:
                                      </Text>
                                      <div style={{ maxHeight: 200, overflow: 'auto' }}>
                                        <List
                                          size="small"
                                          dataSource={record.result_summary?.affected_services || []}
                                          renderItem={(svc: any, idx: number) => (
                                            <List.Item style={{ padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                                              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                                                <Space>
                                                  <Text type="secondary" style={{ width: 24 }}>{idx + 1}.</Text>
                                                  <Tag color={
                                                    svc.impact === 'high' ? 'red' : 
                                                    svc.impact === 'medium' ? 'orange' : 'green'
                                                  }>
                                                    {svc.impact?.toUpperCase()}
                                                  </Tag>
                                                  <Text>{svc.namespace}/{svc.name}</Text>
                                                </Space>
                                                {svc.kind && <Tag>{svc.kind}</Tag>}
                                              </Space>
                                            </List.Item>
                                          )}
                                        />
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Metadata */}
                                  <div style={{ 
                                    background: 'rgba(158, 158, 158, 0.1)', 
                                    padding: 12, 
                                    borderRadius: 8 
                                  }}>
                                    <Row gutter={16}>
                                      <Col span={8}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Executed By</Text>
                                        <div><Text strong>{record.created_by || 'System'}</Text></div>
                                      </Col>
                                      <Col span={8}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Duration</Text>
                                        <div><Text strong>{record.duration_ms ? `${record.duration_ms}ms` : 'N/A'}</Text></div>
                                      </Col>
                                      <Col span={8}>
                                        <Text type="secondary" style={{ fontSize: 11 }}>Date</Text>
                                        <div><Text strong>{new Date(record.created_at).toLocaleString()}</Text></div>
                                      </Col>
                                    </Row>
                                  </div>
                                </div>
                              ),
                            });
                          }}
                        >
                          Details
                        </Button>
                      </Tooltip>
                      
                      <Tooltip title="Re-run this exact simulation with the same parameters">
                        <Button 
                          size="small"
                          type="primary"
                          ghost
                          icon={<PlayCircleOutlined />}
                          onClick={() => {
                            // Set the simulation parameters from history
                            setSelectedClusterId(record.cluster_id ? parseInt(record.cluster_id) : null);
                            setSelectedAnalysisId(record.analysis_id ? parseInt(record.analysis_id) : null);
                            setSelectedNamespace(record.target_namespace);
                            setTargetId(record.target_name);
                            setTargetType(record.target_kind.toLowerCase() as any);
                            setChangeType(record.change_type as any);
                            setActiveMainTab('simulation');
                            message.info('Simulation parameters loaded. Click "Run Simulation" to execute.');
                          }}
                        >
                          Re-run
                        </Button>
                      </Tooltip>
                      
                      <Popconfirm
                        title="Delete this history entry?"
                        description="This action cannot be undone."
                        onConfirm={() => deleteHistoryEntry(record.id)}
                        okText="Delete"
                        cancelText="Cancel"
                        okButtonProps={{ danger: true }}
                      >
                        <Tooltip title="Permanently delete this history entry">
                          <Button size="small" danger icon={<DeleteOutlined />}>
                            Delete
                          </Button>
                        </Tooltip>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          )}
        </Card>
      )}

      {/* Export Modal */}
      <Modal
        title="Export Simulation Report"
        open={exportModalVisible}
        onCancel={() => setExportModalVisible(false)}
        footer={null}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Text>Choose export format:</Text>
          <Button
            icon={<FileTextOutlined />}
            block
            onClick={exportToJson}
          >
            Export as JSON
          </Button>
          <Button
            icon={<FileTextOutlined />}
            block
            onClick={exportToCsv}
          >
            Export as CSV
          </Button>
        </Space>
      </Modal>

      {/* Network Policy Modal */}
      <Modal
        title={
          <Space>
            <SafetyCertificateOutlined />
            Generated Network Policy
          </Space>
        }
        open={networkPolicyModalVisible}
        onCancel={() => setNetworkPolicyModalVisible(false)}
        width={800}
        footer={[
          <Button key="close" onClick={() => setNetworkPolicyModalVisible(false)}>
            Close
          </Button>,
          <Button
            key="copy"
            icon={<CodeOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(generatedPolicyYaml);
              message.success('YAML copied to clipboard');
            }}
          >
            Copy YAML
          </Button>,
          <Button
            key="download"
            type="primary"
            icon={<DownloadOutlined />}
            onClick={() => {
              const blob = new Blob([generatedPolicyYaml], { type: 'text/yaml' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${selectedTarget?.name}-network-policy.yaml`;
              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);
              URL.revokeObjectURL(url);
              message.success('YAML downloaded');
            }}
          >
            Download YAML
          </Button>,
        ]}
      >
        <pre
          style={{
            backgroundColor: '#1e1e1e',
            color: '#d4d4d4',
            padding: 16,
            borderRadius: 4,
            overflow: 'auto',
            maxHeight: 500,
            fontSize: 12,
            fontFamily: 'Monaco, Menlo, monospace',
          }}
        >
          {generatedPolicyYaml}
        </pre>
      </Modal>
      
      {/* Chaos Engineering Templates Modal */}
      <Modal
        title={
          <Space>
            <BulbOutlined style={{ color: colors.primary.main }} />
            <span>Chaos Engineering Templates</span>
          </Space>
        }
        open={showChaosTemplates}
        onCancel={() => setShowChaosTemplates(false)}
        footer={null}
        width={800}
      >
        {/* Category Filter */}
        <div style={{ marginBottom: 16 }}>
          <Radio.Group 
            value={chaosTemplateFilter} 
            onChange={(e) => setChaosTemplateFilter(e.target.value)}
            buttonStyle="solid"
          >
            <Radio.Button value="all">All</Radio.Button>
            <Radio.Button value="availability"><CloudServerOutlined style={{ marginRight: 4, color: '#e57373' }} />Availability</Radio.Button>
            <Radio.Button value="network"><ApiOutlined style={{ marginRight: 4, color: '#2eb8b8' }} />Network</Radio.Button>
            <Radio.Button value="resource"><DashboardOutlined style={{ marginRight: 4, color: '#d4a844' }} />Resource</Radio.Button>
            <Radio.Button value="security"><LockOutlined style={{ marginRight: 4, color: '#64b5f6' }} />Security</Radio.Button>
          </Radio.Group>
        </div>
        
        {/* Templates Grid */}
        <Row gutter={[16, 16]}>
          {filteredChaosTemplates.map((template) => (
            <Col span={12} key={template.id}>
              <Card
                hoverable
                size="small"
                style={{
                  borderColor: selectedChaosTemplate?.id === template.id ? colors.primary.main : undefined,
                  background: selectedChaosTemplate?.id === template.id ? `${colors.primary.main}08` : undefined,
                }}
                onClick={() => applyChaosTemplate(template)}
              >
                <div style={{ display: 'flex', gap: 12 }}>
                  <div style={{ 
                    fontSize: 28,
                    width: 50,
                    height: 50,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: token.colorBgLayout,
                    borderRadius: 8,
                  }}>
                    {chaosTemplateIcons[template.icon]}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong>{template.name}</Text>
                      <Tag 
                        color={
                          template.severity === 'high' ? 'red' : 
                          template.severity === 'medium' ? 'orange' : 'green'
                        }
                      >
                        {template.severity.toUpperCase()}
                      </Tag>
                    </div>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
                      {template.description}
                    </Text>
                    <div style={{ marginTop: 8 }}>
                      <Tag color="blue" style={{ fontSize: 10 }}>{template.category}</Tag>
                      <Tag style={{ fontSize: 10 }}><ClockCircleOutlined style={{ marginRight: 2 }} />{template.rollbackTime}</Tag>
                    </div>
                  </div>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
        
        {/* Selected Template Details */}
        {selectedChaosTemplate && (
          <Card 
            title={
              <Space>
                <span style={{ fontSize: 18 }}>{chaosTemplateIcons[selectedChaosTemplate.icon]}</span>
                <span>{selectedChaosTemplate.name} - Details</span>
              </Space>
            }
            size="small" 
            style={{ marginTop: 16 }}
          >
            <Row gutter={16}>
              <Col span={12}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>Prerequisites</Text>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {selectedChaosTemplate.prerequisites.map((p, i) => (
                    <li key={i}><Text type="secondary">{p}</Text></li>
                  ))}
                </ul>
              </Col>
              <Col span={12}>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>Steps</Text>
                <Timeline
                  items={selectedChaosTemplate.steps.map((step, i) => ({
                    color: i === 0 ? 'green' : 'gray',
                    children: <Text type="secondary" style={{ fontSize: 12 }}>{step}</Text>,
                  }))}
                />
              </Col>
            </Row>
            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={16}>
              <Col span={12}>
                <Statistic 
                  title="Estimated Impact" 
                  value={selectedChaosTemplate.estimatedImpact}
                  valueStyle={{ fontSize: 12 }}
                />
              </Col>
              <Col span={12}>
                <Statistic 
                  title="Rollback Time" 
                  value={selectedChaosTemplate.rollbackTime}
                  valueStyle={{ fontSize: 12, color: colors.status.success }}
                />
              </Col>
            </Row>
          </Card>
        )}
      </Modal>

      {/* Schedule Simulation Modal */}
      <Modal
        title={
          <Space>
            <ScheduleOutlined style={{ color: colors.primary.main }} />
            <span>Schedule Simulation</span>
          </Space>
        }
        open={scheduleModalVisible}
        onCancel={() => {
          setScheduleModalVisible(false);
          scheduleForm.resetFields();
        }}
        onOk={() => scheduleForm.submit()}
        confirmLoading={savingSchedule}
        width={600}
      >
        <Form
          form={scheduleForm}
          layout="vertical"
          onFinish={createScheduledSimulation}
          initialValues={{
            schedule_type: 'once',
            auto_rollback: false,
            rollback_threshold: 5,
            notification_channels: [],
          }}
        >
          <Form.Item
            name="name"
            label="Schedule Name"
            rules={[{ required: true, message: 'Please enter a name' }]}
          >
            <Input placeholder="e.g., Weekly Pod Failure Test" />
          </Form.Item>
          
          <Form.Item
            name="description"
            label="Description"
          >
            <Input.TextArea rows={2} placeholder="Optional description" />
          </Form.Item>
          
          <Form.Item
            name="schedule_type"
            label="Schedule Type"
            rules={[{ required: true }]}
          >
            <Radio.Group>
              <Radio.Button value="once">Run Once</Radio.Button>
              <Radio.Button value="recurring">Recurring</Radio.Button>
            </Radio.Group>
          </Form.Item>
          
          <Form.Item
            noStyle
            shouldUpdate={(prev, curr) => prev.schedule_type !== curr.schedule_type}
          >
            {({ getFieldValue }) => 
              getFieldValue('schedule_type') === 'once' ? (
                <Form.Item
                  name="scheduled_time"
                  label="Scheduled Time"
                  rules={[{ required: true, message: 'Please select a time' }]}
                >
                  <DatePicker 
                    showTime 
                    format="YYYY-MM-DD HH:mm"
                    style={{ width: '100%' }}
                    disabledDate={(current) => current && current.valueOf() < Date.now()}
                  />
                </Form.Item>
              ) : (
                <Form.Item
                  name="cron_expression"
                  label="Cron Expression"
                  rules={[{ required: true, message: 'Please enter a cron expression' }]}
                  extra="Examples: 0 0 * * 1 (weekly on Monday), 0 */6 * * * (every 6 hours)"
                >
                  <Input placeholder="0 0 * * *" />
                </Form.Item>
              )
            }
          </Form.Item>
          
          <Divider>Options</Divider>
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="auto_rollback"
                valuePropName="checked"
              >
                <Checkbox>
                  <Space>
                    <RollbackOutlined />
                    Auto-rollback on failure
                  </Space>
                </Checkbox>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="rollback_threshold"
                label="Error Threshold (%)"
              >
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          
          <Form.Item
            name="notification_channels"
            label="Notifications"
          >
            <Checkbox.Group style={{ width: '100%' }}>
              <Row>
                <Col span={8}><Checkbox value="email">Email</Checkbox></Col>
                <Col span={8}><Checkbox value="slack">Slack</Checkbox></Col>
                <Col span={8}><Checkbox value="in_app">In-App</Checkbox></Col>
              </Row>
            </Checkbox.Group>
          </Form.Item>
          
          <Alert
            message="Current Configuration"
            description={
              <Space direction="vertical" size={0}>
                <Text type="secondary">Target: {targetId || 'Not selected'}</Text>
                <Text type="secondary">Change Type: {changeType}</Text>
                <Text type="secondary">Template: {selectedChaosTemplate?.name || 'None'}</Text>
              </Space>
            }
            type="info"
            showIcon
          />
        </Form>
      </Modal>
    </div>
  );
};

export default ImpactSimulation;
