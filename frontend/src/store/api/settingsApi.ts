import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

export interface BeylaSettingsRequest {
  default_protocols: string[];
  l7_sampling_rate: number;
  l7_enabled: boolean;
  beyla_version: string;
  max_events_per_second: number;
  default_beyla_mem_limit: string;
  default_collector_mem_limit: string;
  default_excluded_namespaces: string[];
}

export interface BeylaSettingsResponse extends BeylaSettingsRequest {
  updated_at?: string | null;
  updated_by?: number | null;
}

export const settingsApi = createApi({
  reducerPath: 'settingsApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['BeylaSettings'],
  endpoints: (builder) => ({
    getBeylaSettings: builder.query<BeylaSettingsResponse, void>({
      query: () => '/settings/beyla',
      providesTags: ['BeylaSettings'],
    }),
    updateBeylaSettings: builder.mutation<BeylaSettingsResponse, BeylaSettingsRequest>({
      query: (body) => ({ url: '/settings/beyla', method: 'PUT', body }),
      invalidatesTags: ['BeylaSettings'],
    }),
  }),
});

export const {
  useGetBeylaSettingsQuery,
  useLazyGetBeylaSettingsQuery,
  useUpdateBeylaSettingsMutation,
} = settingsApi;
