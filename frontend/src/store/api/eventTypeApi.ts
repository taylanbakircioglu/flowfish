import { createApi } from '@reduxjs/toolkit/query/react';
import { baseQueryWithReauth } from './baseQuery';

export interface EventType {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  gadget_name: string;
  performance_impact: string;
  data_volume: string;
  recommended_duration: string;
  use_cases: string[];
  collected_metrics: string[];
  status: string;
}

export interface EventTypeCategory {
  category: string;
  display_name: string;
  event_types: string[];
}

export const eventTypeApi = createApi({
  reducerPath: 'eventTypeApi',
  baseQuery: baseQueryWithReauth,
  tagTypes: ['EventType'],
  endpoints: (builder) => ({
    getEventTypes: builder.query<EventType[], void>({
      query: () => '/event-types',
      providesTags: ['EventType'],
    }),
    getEventType: builder.query<EventType, string>({
      query: (id) => `/event-types/${id}`,
      providesTags: (result, error, id) => [{ type: 'EventType', id }],
    }),
    getEventTypeCategories: builder.query<EventTypeCategory[], void>({
      query: () => '/event-types/categories/list',
      providesTags: ['EventType'],
    }),
  }),
});

export const {
  useGetEventTypesQuery,
  useGetEventTypeQuery,
  useGetEventTypeCategoriesQuery,
} = eventTypeApi;

