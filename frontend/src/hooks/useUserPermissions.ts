/**
 * Hook for checking user permissions based on JWT token roles
 * 
 * Permission model:
 * - Super Admin, Admin, Platform Admin: Full access to all operations
 * - Operator, Analyst: Can create, start, stop, delete analyses
 * - Viewer, Read-Only: Can only view analyses (no modifications)
 */

import { useMemo } from 'react';

// Admin roles that have full access
const ADMIN_ROLES = ['super admin', 'admin', 'platform admin'];

// Viewer roles that have read-only access
const VIEWER_ROLES = ['viewer', 'read-only', 'readonly'];

// Operations that viewers cannot perform
const RESTRICTED_OPERATIONS = ['create', 'start', 'stop', 'delete', 'edit', 'update'];

interface UserPermissions {
  isAdmin: boolean;
  isViewer: boolean;
  canCreateAnalysis: boolean;
  canStartAnalysis: boolean;
  canStopAnalysis: boolean;
  canDeleteAnalysis: boolean;
  canEditSettings: boolean;
  canManageUsers: boolean;
  canManageRoles: boolean;
  roles: string[];
}

/**
 * Get user roles from JWT token stored in localStorage
 */
function getUserRolesFromToken(): string[] {
  try {
    const token = localStorage.getItem('access_token');
    if (!token) return [];
    
    // JWT format: header.payload.signature
    const parts = token.split('.');
    if (parts.length !== 3) return [];
    
    // Decode base64 payload
    const payload = JSON.parse(atob(parts[1]));
    return payload.roles || [];
  } catch (error) {
    console.warn('Failed to parse JWT token for roles:', error);
    return [];
  }
}

/**
 * Check if user has admin role
 */
function checkIsAdmin(roles: string[]): boolean {
  const lowerRoles = roles.map(r => r.toLowerCase());
  return ADMIN_ROLES.some(adminRole => lowerRoles.includes(adminRole));
}

/**
 * Check if user has viewer-only role
 */
function checkIsViewer(roles: string[]): boolean {
  const lowerRoles = roles.map(r => r.toLowerCase());
  // User is viewer if they have viewer role AND don't have admin role
  return VIEWER_ROLES.some(viewerRole => lowerRoles.includes(viewerRole)) && 
         !checkIsAdmin(roles);
}

/**
 * Hook to get current user's permissions
 */
export function useUserPermissions(): UserPermissions {
  const permissions = useMemo(() => {
    const roles = getUserRolesFromToken();
    const isAdmin = checkIsAdmin(roles);
    const isViewer = checkIsViewer(roles);
    
    return {
      isAdmin,
      isViewer,
      roles,
      // Viewers cannot perform these operations
      canCreateAnalysis: !isViewer,
      canStartAnalysis: !isViewer,
      canStopAnalysis: !isViewer,
      canDeleteAnalysis: !isViewer,
      canEditSettings: isAdmin,
      canManageUsers: isAdmin,
      canManageRoles: isAdmin,
    };
  }, []);
  
  return permissions;
}

/**
 * Check if a specific operation is allowed for the current user
 */
export function useCanPerformOperation(operation: string): boolean {
  const { isViewer } = useUserPermissions();
  
  return useMemo(() => {
    if (RESTRICTED_OPERATIONS.includes(operation.toLowerCase())) {
      return !isViewer;
    }
    return true;
  }, [isViewer, operation]);
}

export default useUserPermissions;
