/**
 * Custom hook for persisting filters in localStorage
 * 
 * Saves filter state to localStorage and restores on page load.
 * Each page has its own storage key to maintain independent filter states.
 */

import { useState, useEffect, useCallback } from 'react';
import dayjs from 'dayjs';

// Storage key prefix
const STORAGE_PREFIX = 'flowfish_filters_';

// Filter state interface (generic for all pages)
export interface PersistedFilters {
  clusterId?: number;
  analysisId?: number;
  namespace?: string;
  searchTerm?: string;
  dateRange?: [string, string] | null;
  selectedTypes?: string[];
  layout?: string;
  // Add more filter types as needed
  [key: string]: any;
}

/**
 * Hook to persist and restore filters from localStorage
 * 
 * @param pageKey - Unique key for the page (e.g., 'map', 'network-explorer', 'events-timeline')
 * @param defaultFilters - Default filter values
 * @returns [filters, setFilters, clearFilters]
 */
export function usePersistedFilters<T extends PersistedFilters>(
  pageKey: string,
  defaultFilters: T
): [T, (filters: Partial<T>) => void, () => void] {
  
  const storageKey = `${STORAGE_PREFIX}${pageKey}`;
  
  // Initialize state from localStorage or defaults
  const [filters, setFiltersState] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        // Don't restore dateRange - it should always be fresh
        // User can re-select if needed
        return { ...defaultFilters, ...parsed, dateRange: defaultFilters.dateRange };
      }
    } catch (e) {
      console.warn('Failed to parse stored filters:', e);
    }
    return defaultFilters;
  });
  
  // Save to localStorage whenever filters change
  useEffect(() => {
    try {
      // Don't persist dateRange to avoid stale time filters
      const { dateRange, ...persistable } = filters;
      localStorage.setItem(storageKey, JSON.stringify(persistable));
    } catch (e) {
      console.warn('Failed to save filters:', e);
    }
  }, [filters, storageKey]);
  
  // Update filters (merge with existing)
  const setFilters = useCallback((newFilters: Partial<T>) => {
    setFiltersState(prev => ({ ...prev, ...newFilters }));
  }, []);
  
  // Clear all filters
  const clearFilters = useCallback(() => {
    localStorage.removeItem(storageKey);
    setFiltersState(defaultFilters);
  }, [storageKey, defaultFilters]);
  
  return [filters, setFilters, clearFilters];
}

/**
 * Hook specifically for cluster and analysis selection
 * These are commonly used across all pages
 */
export function usePersistedClusterSelection() {
  const [selection, setSelection, clearSelection] = usePersistedFilters('global_cluster', {
    clusterId: undefined as number | undefined,
    analysisId: undefined as number | undefined,
  });
  
  return {
    selectedClusterId: selection.clusterId,
    selectedAnalysisId: selection.analysisId,
    setSelectedClusterId: (id: number | undefined) => setSelection({ clusterId: id, analysisId: undefined }),
    setSelectedAnalysisId: (id: number | undefined) => setSelection({ analysisId: id }),
    clearSelection,
  };
}

export default usePersistedFilters;

