// Constants for Flowfish frontend

// API endpoints
export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/api/v1/auth/login',
    LOGOUT: '/api/v1/auth/logout',
    ME: '/api/v1/auth/me',
    REFRESH: '/api/v1/auth/refresh',
  },
  CLUSTERS: '/api/v1/clusters',
  ANALYSES: '/api/v1/analyses', 
  WORKLOADS: '/api/v1/workloads',
  COMMUNICATIONS: '/api/v1/communications',
  DEPENDENCIES: '/api/v1/dependencies',
  HEALTH: '/api/v1/health',
} as const;

// Colors
export const COLORS = {
  PRIMARY: '#0891b2',
  SUCCESS: '#4d9f7c',
  WARNING: '#c9a55a',
  ERROR: '#c75450',
  PURPLE: '#7c8eb5',
  CYAN: '#22a6a6',
  
  RISK: {
    LOW: '#4d9f7c',
    MEDIUM: '#c9a55a', 
    HIGH: '#b89b5d',
    CRITICAL: '#c75450',
  },
  
  STATUS: {
    RUNNING: '#4d9f7c',
    PENDING: '#c9a55a',
    FAILED: '#c75450',
    UNKNOWN: '#8c8c8c',
  },
} as const;

// Local storage keys
export const STORAGE_KEYS = {
  TOKEN: 'flowfish_token',
  USER: 'flowfish_user',
  THEME: 'flowfish_theme',
  SELECTED_CLUSTER: 'flowfish_selected_cluster',
} as const;

// Routes
export const ROUTES = {
  LOGIN: '/login',
  DASHBOARD: '/dashboard',
  ANALYSIS_WIZARD: '/analysis/wizard',
  DEPENDENCY_MAP: '/discovery/map',
  CLUSTER_MANAGEMENT: '/management/clusters',
  AI_INTEGRATION_HUB: '/integration/ai-hub',
} as const;
