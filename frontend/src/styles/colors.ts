/**
 * Flowfish Modern Color Palette
 * Ocean-inspired theme with modern aesthetics
 */

export const colors = {
  // Primary Brand Colors - Ocean Blue Theme
  primary: {
    main: '#0891b2',        // Cyan-600 - Ocean blue
    light: '#06b6d4',       // Cyan-500 - Light ocean
    lighter: '#22d3ee',     // Cyan-400 - Bright cyan
    dark: '#0e7490',        // Cyan-700 - Deep ocean
    darker: '#155e75',      // Cyan-800 - Very deep ocean
    gradient: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',
  },
  
  // Secondary Colors - Sea Theme
  secondary: {
    aqua: '#22d3ee',        // Bright cyan
    turquoise: '#14b8a6',   // Teal-500
    seafoam: '#5eead4',     // Teal-300
    coral: '#f97316',       // Orange-500
    pearl: '#f0fdfa',       // Teal-50
  },
  
  // Status Colors - Modern Palette
  status: {
    success: '#10b981',     // Modern green
    warning: '#f59e0b',     // Modern orange
    error: '#ef4444',       // Modern red
    info: '#0ea5e9',        // Sky blue
  },
  
  // Neutral Colors - Modern Grays
  neutral: {
    50: '#fafafa',
    100: '#f5f5f5',
    200: '#e5e5e5',
    300: '#d4d4d4',
    400: '#a3a3a3',
    500: '#737373',
    600: '#525252',
    700: '#404040',
    800: '#262626',
    900: '#171717',
  },
  
  // Background Gradients - Ocean Theme
  gradients: {
    primary: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',        // Ocean gradient
    secondary: 'linear-gradient(135deg, #22d3ee 0%, #0ea5e9 100%)',      // Light ocean
    ocean: 'linear-gradient(135deg, #0891b2 0%, #155e75 100%)',          // Deep ocean
    tropical: 'linear-gradient(135deg, #14b8a6 0%, #06b6d4 100%)',       // Tropical sea
    success: 'linear-gradient(135deg, #10b981 0%, #14b8a6 100%)',
    danger: 'linear-gradient(135deg, #ef4444 0%, #ec4899 100%)',
    light: 'linear-gradient(135deg, #ecfeff 0%, #cffafe 100%)',          // Light cyan
    dark: 'linear-gradient(135deg, #164e63 0%, #0e7490 100%)',           // Dark ocean
  },
  
  // Chart Colors - Modern Palette
  charts: {
    blue: '#3b82f6',
    cyan: '#06b6d4',
    green: '#10b981',
    yellow: '#f59e0b',
    red: '#ef4444',
    purple: '#a855f7',
    pink: '#ec4899',
    indigo: '#6366f1',
    teal: '#14b8a6',
    orange: '#f97316',
  },
  
  // Glass Morphism
  glass: {
    light: 'rgba(255, 255, 255, 0.1)',
    medium: 'rgba(255, 255, 255, 0.2)',
    dark: 'rgba(0, 0, 0, 0.2)',
  },
};

// Ant Design Theme Token Override
export const modernThemeTokens = {
  colorPrimary: colors.primary.main,
  colorSuccess: colors.status.success,
  colorWarning: colors.status.warning,
  colorError: colors.status.error,
  colorInfo: colors.status.info,
  colorLink: colors.primary.main,
  
  borderRadius: 8,
  borderRadiusLG: 12,
  borderRadiusSM: 6,
  
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Inter", "Helvetica Neue", Arial, sans-serif',
  fontSize: 14,
  fontSizeLG: 16,
  fontSizeHeading1: 38,
  fontSizeHeading2: 30,
  fontSizeHeading3: 24,
  
  lineHeight: 1.5,
  lineHeightLG: 1.6,
  
  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
  boxShadowSecondary: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
};

// Component Specific Colors
export const componentColors = {
  sidebar: {
    bg: colors.neutral[900],
    bgLight: '#1e293b',
    activeBg: colors.primary.main,
    hoverBg: 'rgba(102, 126, 234, 0.1)',
    text: colors.neutral[300],
    activeText: '#ffffff',
  },
  
  header: {
    bg: '#ffffff',
    bgDark: colors.neutral[900],
    borderBottom: colors.neutral[200],
    text: colors.neutral[700],
  },
  
  card: {
    bg: '#ffffff',
    bgDark: colors.neutral[800],
    border: colors.neutral[200],
    shadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
  },
};

export default colors;

