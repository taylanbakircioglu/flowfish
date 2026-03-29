import type { ThemeConfig } from 'antd';
import { theme as antTheme } from 'antd';
import { modernThemeTokens } from './colors';

// Flowfish Modern Theme Configuration
export const theme: ThemeConfig = {
  token: {
    // Modern Brand Colors
    colorPrimary: '#667eea',        // Modern purple-blue
    colorSuccess: '#10b981',        // Modern green  
    colorWarning: '#f59e0b',        // Modern orange
    colorError: '#ef4444',          // Modern red
    colorInfo: '#3b82f6',           // Modern blue
    
    // Layout colors
    colorBgContainer: '#ffffff',    // Container background
    colorBgLayout: '#f0f2f5',       // Layout background
    colorBgElevated: '#ffffff',     // Elevated background (cards, modals)
    
    // Text colors
    colorText: '#000000d9',         // Primary text
    colorTextSecondary: '#00000073', // Secondary text
    colorTextTertiary: '#00000040',  // Tertiary text
    
    // Border
    colorBorder: '#d9d9d9',         // Default border
    colorBorderSecondary: '#f0f0f0', // Secondary border
    
    // Typography
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSize: 14,
    fontSizeLG: 16,
    fontSizeSM: 12,
    
    // Spacing
    padding: 16,
    paddingLG: 24,
    paddingSM: 12,
    margin: 16,
    marginLG: 24,
    marginSM: 12,
    
    // Border radius - More modern
    borderRadius: 8,
    borderRadiusLG: 12,
    borderRadiusSM: 6,
    
    // Shadows - Modern depth
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    boxShadowSecondary: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      headerHeight: 64,
      siderBg: '#0f172a',           // Modern dark blue
      bodyBg: '#f8fafc',            // Modern light gray
    },
    Menu: {
      darkItemBg: '#0f172a',
      darkItemSelectedBg: '#667eea',
      darkItemHoverBg: 'rgba(102, 126, 234, 0.1)',
      itemBorderRadius: 8,
    },
    Card: {
      paddingLG: 24,
      borderRadiusLG: 12,
      boxShadowTertiary: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
    },
    Button: {
      primaryColor: '#ffffff',
      borderRadius: 8,
      controlHeight: 40,
      controlHeightLG: 48,
      fontWeight: 500,
      primaryShadow: '0 4px 6px -1px rgba(102, 126, 234, 0.3)',
    },
    Input: {
      borderRadius: 8,
      controlHeight: 40,
      controlHeightLG: 48,
    },
    Table: {
      borderRadius: 8,
      headerBg: '#f8fafc',
    },
    Statistic: {
      titleFontSize: 14,
      contentFontSize: 28,
    },
  },
};

// Dark theme variant
export const darkTheme: ThemeConfig = {
  ...theme,
  algorithm: antTheme.darkAlgorithm,
  token: {
    ...theme.token,
    colorBgContainer: '#141414',
    colorBgLayout: '#000000',
    colorBgElevated: '#1f1f1f',
  },
};
