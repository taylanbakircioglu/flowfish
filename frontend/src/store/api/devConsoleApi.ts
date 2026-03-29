/**
 * Dev Console API - RTK Query slice for Developer Query Console
 * 
 * Supports ClickHouse (SQL) and Neo4j (Cypher) queries
 */

import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

// Types
export type DatabaseType = 'clickhouse' | 'neo4j';

export interface QueryRequest {
  database: DatabaseType;
  query: string;
  analysis_ids?: string[];
  limit?: number;
  timeout?: number;
}

export interface QueryError {
  code: string;
  message: string;
  line?: number;
  position?: number;
}

export interface QueryResponse {
  success: boolean;
  columns: string[];
  rows: any[][];
  row_count: number;
  execution_time_ms: number;
  truncated: boolean;
  error?: QueryError;
}

export interface ColumnSchema {
  name: string;
  type: string;
  description?: string;
}

export interface TableSchema {
  name: string;
  columns: ColumnSchema[];
}

export interface SchemaResponse {
  database: string;
  tables: TableSchema[];
}

// API slice
export const devConsoleApi = createApi({
  reducerPath: 'devConsoleApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['DevConsole'],
  endpoints: (builder) => ({
    // Execute query
    executeQuery: builder.mutation<QueryResponse, QueryRequest>({
      query: (body) => ({
        url: '/dev-console/query',
        method: 'POST',
        body,
      }),
    }),

    // Get database schema
    getSchema: builder.query<SchemaResponse, DatabaseType>({
      query: (database) => `/dev-console/schema/${database}`,
      providesTags: ['DevConsole'],
    }),

    // Health check
    getHealth: builder.query<{ status: string; databases: Record<string, string> }, void>({
      query: () => '/dev-console/health',
    }),
  }),
});

// Export hooks
export const {
  useExecuteQueryMutation,
  useGetSchemaQuery,
  useGetHealthQuery,
} = devConsoleApi;
