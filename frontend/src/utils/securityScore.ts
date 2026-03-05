/**
 * Shared Security Score Calculation Utility
 * Used by both Dashboard SecurityTab and SecurityCenter pages
 */

// Capability risk mapping
export const capabilityRisk: Record<string, { risk: 'low' | 'medium' | 'high' | 'critical'; description: string }> = {
  'CAP_SYS_ADMIN': { risk: 'critical', description: 'Full administrative access' },
  'CAP_SYS_PTRACE': { risk: 'high', description: 'Can trace any process' },
  'CAP_NET_ADMIN': { risk: 'high', description: 'Network stack control' },
  'CAP_NET_RAW': { risk: 'medium', description: 'Raw network packets' },
  'CAP_NET_BIND_SERVICE': { risk: 'low', description: 'Bind to privileged ports' },
  'CAP_SYS_MODULE': { risk: 'critical', description: 'Can load kernel modules' },
  'CAP_SYS_RAWIO': { risk: 'critical', description: 'Raw I/O access' },
  'CAP_MKNOD': { risk: 'medium', description: 'Create device files' },
  'CAP_SETUID': { risk: 'high', description: 'Arbitrary UID changes' },
  'CAP_SETGID': { risk: 'high', description: 'Arbitrary GID changes' },
  'CAP_DAC_OVERRIDE': { risk: 'medium', description: 'Bypass file permissions' },
  'CAP_CHOWN': { risk: 'low', description: 'Change file ownership' },
  'CAP_KILL': { risk: 'low', description: 'Send signals to any process' },
};

// Risk score colors
export const riskColors = {
  critical: '#cf1322',
  high: '#e05252',
  medium: '#d4a844',
  low: '#4caf50',
};

export interface SecurityScoreInput {
  totalCapabilityChecks: number;
  totalOomEvents: number;
  violations: Array<{ severity: 'low' | 'medium' | 'high' | 'critical' }>;
  capabilities: Array<{ risk: 'low' | 'medium' | 'high' | 'critical' }>;
}

export interface SecurityScoreBreakdown {
  label: string;
  value: number;
  impact: number;
}

export interface SecurityScoreResult {
  score: number | null;
  status: 'no_selection' | 'loading' | 'no_data' | 'calculated';
  breakdown?: SecurityScoreBreakdown[];
  message?: string;
}

/**
 * Calculate security score based on violations, capabilities, and OOM events
 * This is the single source of truth for security score calculation
 */
export function calculateSecurityScore(input: SecurityScoreInput): SecurityScoreResult {
  const { totalCapabilityChecks, totalOomEvents, violations, capabilities } = input;

  // If no data collected yet, show N/A
  if (totalCapabilityChecks === 0 && totalOomEvents === 0 && capabilities.length === 0) {
    return { 
      score: null, 
      status: 'no_data',
      message: 'No security events collected yet. Start an analysis with security gadgets enabled.'
    };
  }

  // Calculate score starting from 100
  let score = 100;
  const breakdown: SecurityScoreBreakdown[] = [];

  // 1. VIOLATION RATIO - This is the most important metric
  if (totalCapabilityChecks > 0) {
    const violationCount = violations.length;
    const violationRatio = violationCount / totalCapabilityChecks;

    // Count violations by severity for weighted scoring
    const criticalViolations = violations.filter(v => v.severity === 'critical').length;
    const highViolations = violations.filter(v => v.severity === 'high').length;
    const mediumViolations = violations.filter(v => v.severity === 'medium').length;
    const lowViolations = violations.filter(v => v.severity === 'low').length;

    // Weighted deductions based on severity
    if (criticalViolations > 0) {
      const impact = Math.min(criticalViolations * 12, 40); // Cap at 40 points
      score -= impact;
      breakdown.push({ label: 'Critical Violations', value: criticalViolations, impact: -impact });
    }
    if (highViolations > 0) {
      const impact = Math.min(highViolations * 8, 30); // Cap at 30 points
      score -= impact;
      breakdown.push({ label: 'High Violations', value: highViolations, impact: -impact });
    }
    if (mediumViolations > 0) {
      const impact = Math.min(mediumViolations * 4, 20); // Cap at 20 points
      score -= impact;
      breakdown.push({ label: 'Medium Violations', value: mediumViolations, impact: -impact });
    }
    if (lowViolations > 0) {
      const impact = Math.min(lowViolations * 1, 5); // Cap at 5 points
      score -= impact;
      breakdown.push({ label: 'Low Violations', value: lowViolations, impact: -impact });
    }

    // Additional penalty for high violation ratio (>10% of checks are violations)
    if (violationRatio > 0.1 && violationCount > 5) {
      const ratioImpact = Math.round(violationRatio * 20);
      score -= ratioImpact;
      breakdown.push({ label: 'High Violation Ratio', value: Math.round(violationRatio * 100), impact: -ratioImpact });
    }
  }

  // 2. DANGEROUS CAPABILITIES IN USE
  const criticalCaps = capabilities.filter(c => c.risk === 'critical').length;
  const highCaps = capabilities.filter(c => c.risk === 'high').length;

  if (criticalCaps > 0) {
    const impact = Math.min(criticalCaps * 6, 25); // Cap at 25 points
    score -= impact;
    breakdown.push({ label: 'Critical Capabilities', value: criticalCaps, impact: -impact });
  }
  if (highCaps > 0) {
    const impact = Math.min(highCaps * 3, 15); // Cap at 15 points
    score -= impact;
    breakdown.push({ label: 'High-Risk Capabilities', value: highCaps, impact: -impact });
  }

  // 3. OOM EVENTS - Memory issues indicate resource problems
  if (totalOomEvents > 0) {
    const impact = Math.min(totalOomEvents * 4, 20); // Cap at 20 points
    score -= impact;
    breakdown.push({ label: 'OOM Events', value: totalOomEvents, impact: -impact });
  }

  // 4. BONUS POINTS - Reward good security posture
  // Only add bonus if we have meaningful data (at least some capability checks)
  if (totalCapabilityChecks >= 10) {
    // Bonus for no critical issues
    if (criticalCaps === 0 && violations.filter(v => v.severity === 'critical').length === 0) {
      const bonus = 5;
      score = Math.min(score + bonus, 100);
      breakdown.push({ label: 'No Critical Issues', value: 1, impact: bonus });
    }

    // Bonus for zero violations (perfect security)
    if (violations.length === 0) {
      const bonus = 5;
      score = Math.min(score + bonus, 100);
      breakdown.push({ label: 'Zero Violations', value: 1, impact: bonus });
    }

    // Bonus for no high-risk capabilities
    if (criticalCaps === 0 && highCaps === 0) {
      const bonus = 3;
      score = Math.min(score + bonus, 100);
      breakdown.push({ label: 'No High-Risk Capabilities', value: 1, impact: bonus });
    }
  }

  // Ensure score stays in valid range
  const finalScore = Math.max(0, Math.min(100, Math.round(score)));

  return {
    score: finalScore,
    status: 'calculated',
    breakdown
  };
}

/**
 * Get severity for a security event based on its capability
 */
export function getEventSeverity(capability: string | undefined): 'low' | 'medium' | 'high' | 'critical' {
  if (!capability) return 'high';
  return capabilityRisk[capability]?.risk || 'medium';
}

/**
 * API query limit for security events - must be same across all pages
 * for consistent score calculation
 */
export const SECURITY_EVENTS_LIMIT = 50;
export const OOM_EVENTS_LIMIT = 50;
