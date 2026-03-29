/**
 * Custom base query with automatic 401 handling
 * Redirects to login page when token expires
 */

import { fetchBaseQuery, BaseQueryFn, FetchArgs, FetchBaseQueryError } from '@reduxjs/toolkit/query/react';

interface RootState {
  auth: {
    token: string | null;
  };
}

// Client IP cache for activity logging
let cachedClientIP: string | null = null;

// Fetch public IP once on module load
const fetchClientIP = async (): Promise<void> => {
  if (cachedClientIP) return;
  
  try {
    const response = await fetch('https://api.ipify.org?format=json', { 
      method: 'GET',
      cache: 'force-cache'
    });
    const data = await response.json();
    cachedClientIP = data.ip || null;
  } catch {
    cachedClientIP = null;
  }
};

// Initialize IP fetch
fetchClientIP();

// Create base query with auth header and client IP
const rawBaseQuery = fetchBaseQuery({
  baseUrl: '/api/v1',
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as RootState).auth.token;
    if (token) {
      headers.set('authorization', `Bearer ${token}`);
    }
    // Add client IP for activity logging
    if (cachedClientIP) {
      headers.set('X-Client-IP', cachedClientIP);
    }
    return headers;
  },
});

// Wrapper that handles 401 errors
export const baseQueryWithReauth: BaseQueryFn<
  string | FetchArgs,
  unknown,
  FetchBaseQueryError
> = async (args, api, extraOptions) => {
  const result = await rawBaseQuery(args, api, extraOptions);

  // Check for 401 Unauthorized
  if (result.error && result.error.status === 401) {
    // Clear auth data from localStorage
    localStorage.removeItem('flowfish_token');
    localStorage.removeItem('flowfish_user');

    // Dispatch logout action to clear Redux state
    api.dispatch({ type: 'auth/logout' });

    // Redirect to login page
    window.location.href = '/login';
  }

  return result;
};

// Auth-specific base query (doesn't redirect on 401 for login endpoint)
const rawAuthBaseQuery = fetchBaseQuery({
  baseUrl: '/api/v1/auth',
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as RootState).auth.token;
    if (token) {
      headers.set('authorization', `Bearer ${token}`);
    }
    // Add client IP for activity logging
    if (cachedClientIP) {
      headers.set('X-Client-IP', cachedClientIP);
    }
    return headers;
  },
});

export const authBaseQuery: BaseQueryFn<
  string | FetchArgs,
  unknown,
  FetchBaseQueryError
> = async (args, api, extraOptions) => {
  const result = await rawAuthBaseQuery(args, api, extraOptions);

  // Only handle 401 for non-login endpoints
  const url = typeof args === 'string' ? args : args.url;
  if (result.error && result.error.status === 401 && !url.includes('/login')) {
    localStorage.removeItem('flowfish_token');
    localStorage.removeItem('flowfish_user');
    api.dispatch({ type: 'auth/logout' });
    window.location.href = '/login';
  }

  return result;
};

