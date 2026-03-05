import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { User } from '../../types';

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
  loading: boolean;
  error: string | null;
  initialized: boolean;
}

// Check if we have stored auth data
const storedToken = localStorage.getItem('flowfish_token');
const storedUser = localStorage.getItem('flowfish_user');
let parsedUser: User | null = null;

if (storedUser) {
  try {
    parsedUser = JSON.parse(storedUser);
  } catch {
    localStorage.removeItem('flowfish_user');
    localStorage.removeItem('flowfish_token');
  }
}

const initialState: AuthState = {
  isAuthenticated: !!(storedToken && parsedUser),
  user: parsedUser,
  token: storedToken,
  loading: false,
  error: null,
  initialized: true,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginStart: (state) => {
      state.loading = true;
      state.error = null;
    },
    loginSuccess: (state, action: PayloadAction<{ user: User; token: string }>) => {
      state.loading = false;
      state.isAuthenticated = true;
      state.user = action.payload.user;
      state.token = action.payload.token;
      state.error = null;
      // Save both token and user to localStorage for persistence
      localStorage.setItem('flowfish_token', action.payload.token);
      localStorage.setItem('flowfish_user', JSON.stringify(action.payload.user));
    },
    loginFailure: (state, action: PayloadAction<string>) => {
      state.loading = false;
      state.isAuthenticated = false;
      state.user = null;
      state.token = null;
      state.error = action.payload;
      localStorage.removeItem('flowfish_token');
      localStorage.removeItem('flowfish_user');
    },
    logout: (state) => {
      state.isAuthenticated = false;
      state.user = null;
      state.token = null;
      state.error = null;
      localStorage.removeItem('flowfish_token');
      localStorage.removeItem('flowfish_user');
    },
    setUser: (state, action: PayloadAction<User>) => {
      state.user = action.payload;
      state.isAuthenticated = true;
    },
  },
});

export const { loginStart, loginSuccess, loginFailure, logout, setUser } = authSlice.actions;
export default authSlice.reducer;
