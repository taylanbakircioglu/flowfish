/**
 * Redux store configuration
 */

import { configureStore } from '@reduxjs/toolkit';
import authSlice from './slices/authSlice';
import clusterSlice from './slices/clusterSlice';
import { authApi } from './api/authApi';
import { clusterApi } from './api/clusterApi';
import { workloadApi } from './api/workloadApi';
import { analysisApi } from './api/analysisApi';
import { eventTypeApi } from './api/eventTypeApi';
import { communicationApi } from './api/communicationApi';
import { eventsApi } from './api/eventsApi';
import { changesApi } from './api/changesApi';
import { devConsoleApi } from './api/devConsoleApi';
import { simulationApi } from './api/simulationApi';

export const store = configureStore({
  reducer: {
    auth: authSlice,
    cluster: clusterSlice,
    [authApi.reducerPath]: authApi.reducer,
    [clusterApi.reducerPath]: clusterApi.reducer,
    [workloadApi.reducerPath]: workloadApi.reducer,
    [analysisApi.reducerPath]: analysisApi.reducer,
    [eventTypeApi.reducerPath]: eventTypeApi.reducer,
    [communicationApi.reducerPath]: communicationApi.reducer,
    [eventsApi.reducerPath]: eventsApi.reducer,
    [changesApi.reducerPath]: changesApi.reducer,
    [devConsoleApi.reducerPath]: devConsoleApi.reducer,
    [simulationApi.reducerPath]: simulationApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['persist/PERSIST', 'persist/REHYDRATE'],
      },
    })
    .concat(authApi.middleware)
    .concat(clusterApi.middleware)
    .concat(workloadApi.middleware)
    .concat(analysisApi.middleware)
    .concat(eventTypeApi.middleware)
    .concat(communicationApi.middleware)
    .concat(eventsApi.middleware)
    .concat(changesApi.middleware)
    .concat(devConsoleApi.middleware)
    .concat(simulationApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;