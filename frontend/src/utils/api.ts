import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

// Client IP cache for activity logging
let cachedClientIP: string | null = null;

// Fetch public IP once on app load
const fetchClientIP = async (): Promise<string> => {
  if (cachedClientIP) return cachedClientIP;
  
  try {
    const response = await fetch('https://api.ipify.org?format=json', { 
      method: 'GET',
      cache: 'force-cache'
    });
    const data = await response.json();
    cachedClientIP = data.ip || '0.0.0.0';
  } catch {
    cachedClientIP = '0.0.0.0';
  }
  return cachedClientIP;
};

// Initialize IP fetch on module load
fetchClientIP();

// Create axios instance with base configuration
// In production (Kubernetes), API is accessible via /api path through ingress
// In development, use http://localhost:8000 directly
const getBaseURL = () => {
  // If REACT_APP_API_URL is set, use it
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // In production build (served from same origin), use relative path
  if (process.env.NODE_ENV === 'production') {
    return window.location.origin;
  }
  
  // In development, use direct backend URL
  return 'http://localhost:8000';
};

export const apiClient: AxiosInstance = axios.create({
  baseURL: getBaseURL(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token and client IP
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('flowfish_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Add client IP header for activity logging
    if (cachedClientIP) {
      config.headers['X-Client-IP'] = cachedClientIP;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle errors globally
apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response) {
      // Server responded with error
      const { status, data } = error.response;
      
      switch (status) {
        case 401:
          // Unauthorized - clear token and redirect to login
          localStorage.removeItem('flowfish_token');
          window.location.href = '/login';
          break;
        case 403:
          message.error('Access denied. Insufficient permissions.');
          break;
        case 404:
          message.error('Resource not found.');
          break;
        case 500:
          message.error('Internal server error. Please try again.');
          break;
        default:
          message.error(data?.detail || data?.message || 'An error occurred');
      }
    } else if (error.request) {
      // Network error
      message.error('Network error. Please check your connection.');
    } else {
      message.error('An unexpected error occurred.');
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
