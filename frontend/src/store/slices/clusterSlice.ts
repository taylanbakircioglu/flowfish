import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Cluster } from '../../types';

interface ClusterState {
  clusters: Cluster[];
  selectedCluster: Cluster | null;
  loading: boolean;
  error: string | null;
}

const initialState: ClusterState = {
  clusters: [],
  selectedCluster: null,
  loading: false,
  error: null,
};

const clusterSlice = createSlice({
  name: 'cluster',
  initialState,
  reducers: {
    setClusters: (state, action: PayloadAction<Cluster[]>) => {
      state.clusters = action.payload;
      // Auto-select first cluster if none selected
      if (!state.selectedCluster && action.payload.length > 0) {
        state.selectedCluster = action.payload[0];
      }
    },
    setSelectedCluster: (state, action: PayloadAction<Cluster>) => {
      state.selectedCluster = action.payload;
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
  },
});

export const { setClusters, setSelectedCluster, setLoading, setError } = clusterSlice.actions;
export default clusterSlice.reducer;
