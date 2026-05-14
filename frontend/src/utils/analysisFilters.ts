import { useEffect, useMemo } from 'react';
import type { Analysis } from '../types';

export function isL4Compatible(analysis: Analysis): boolean {
  const level = (analysis.analysis_level || 'l4').toLowerCase();
  return level === 'l4' || level === 'both';
}

export function isL7Compatible(analysis: Analysis): boolean {
  const level = (analysis.analysis_level || 'l4').toLowerCase();
  return level === 'l7' || level === 'both';
}

/**
 * Returns a stable, memoized list of L4-compatible analyses.
 * Prevents useEffect deps from firing every render due to
 * Array.filter() creating a new array reference each time.
 */
export function useL4Analyses(analyses: Analysis[]): Analysis[] {
  return useMemo(
    () =>
      Array.isArray(analyses)
        ? analyses.filter(
            (a) =>
              (a.status === 'running' || a.status === 'completed' || a.status === 'stopped') &&
              isL4Compatible(a),
          )
        : [],
    [analyses],
  );
}

/**
 * Returns a stable, memoized list of L7-compatible analyses
 * (analysis_level is 'l7' or 'both').
 */
export function useL7Analyses(analyses: Analysis[]): Analysis[] {
  return useMemo(
    () =>
      Array.isArray(analyses)
        ? analyses.filter(
            (a) =>
              (a.status === 'running' || a.status === 'completed' || a.status === 'stopped') &&
              isL7Compatible(a),
          )
        : [],
    [analyses],
  );
}

export function useL7AnalysisGuard(
  selectedId: number | undefined,
  clearSelection: (id: undefined) => void,
  availableAnalyses: Analysis[],
): void {
  useEffect(() => {
    if (
      selectedId != null &&
      availableAnalyses.length > 0 &&
      !availableAnalyses.some((a) => a.id === selectedId)
    ) {
      clearSelection(undefined);
    }
  }, [selectedId, availableAnalyses, clearSelection]);
}

export function useL4AnalysisGuard(
  selectedId: number | undefined,
  clearSelection: (id: undefined) => void,
  availableAnalyses: Analysis[],
): void {
  useEffect(() => {
    if (
      selectedId != null &&
      availableAnalyses.length > 0 &&
      !availableAnalyses.some((a) => a.id === selectedId)
    ) {
      clearSelection(undefined);
    }
  }, [selectedId, availableAnalyses, clearSelection]);
}
