/**
 * Theme Context for dynamic dark/light mode switching
 */
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { ConfigProvider, theme as antTheme } from 'antd';
import type { ThemeConfig } from 'antd';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeContextType {
  themeMode: ThemeMode;
  isDark: boolean;
  setThemeMode: (mode: ThemeMode) => void;
  primaryColor: string;
  setPrimaryColor: (color: string) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

// Light theme configuration
const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: '#667eea',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorInfo: '#3b82f6',
    colorBgContainer: '#ffffff',
    colorBgLayout: '#f0f2f5',
    colorBgElevated: '#ffffff',
    colorText: 'rgba(0, 0, 0, 0.85)',
    colorTextSecondary: 'rgba(0, 0, 0, 0.45)',
    colorBorder: '#d9d9d9',
    borderRadius: 8,
  },
  components: {
    Layout: {
      headerBg: '#ffffff',
      siderBg: '#0f172a',
      bodyBg: '#f8fafc',
    },
    Menu: {
      darkItemBg: '#0f172a',
      darkItemSelectedBg: '#667eea',
      darkItemHoverBg: 'rgba(102, 126, 234, 0.1)',
    },
    Card: {
      colorBgContainer: '#ffffff',
    },
    Table: {
      headerBg: '#fafafa',
      colorBgContainer: '#ffffff',
    },
    Modal: {
      contentBg: '#ffffff',
      headerBg: '#ffffff',
    },
    Input: {
      colorBgContainer: '#ffffff',
    },
    Select: {
      colorBgContainer: '#ffffff',
      colorBgElevated: '#ffffff',
    },
  },
};

// Dark theme configuration
const darkTheme: ThemeConfig = {
  algorithm: antTheme.darkAlgorithm,
  token: {
    colorPrimary: '#667eea',
    colorSuccess: '#10b981',
    colorWarning: '#f59e0b',
    colorError: '#ef4444',
    colorInfo: '#3b82f6',
    colorBgContainer: '#1f1f1f',
    colorBgLayout: '#141414',
    colorBgElevated: '#262626',
    colorText: 'rgba(255, 255, 255, 0.85)',
    colorTextSecondary: 'rgba(255, 255, 255, 0.45)',
    colorBorder: '#434343',
    borderRadius: 8,
  },
  components: {
    Layout: {
      headerBg: '#1f1f1f',
      siderBg: '#141414',
      bodyBg: '#141414',
    },
    Menu: {
      darkItemBg: '#141414',
      darkItemSelectedBg: '#667eea',
      darkItemHoverBg: 'rgba(102, 126, 234, 0.2)',
    },
    Card: {
      colorBgContainer: '#1f1f1f',
    },
    Table: {
      headerBg: '#262626',
      colorBgContainer: '#1f1f1f',
      rowHoverBg: '#303030',
    },
    Modal: {
      contentBg: '#1f1f1f',
      headerBg: '#262626',
    },
    Input: {
      colorBgContainer: '#262626',
      activeBorderColor: '#667eea',
      hoverBorderColor: '#667eea',
    },
    Select: {
      colorBgContainer: '#262626',
      colorBgElevated: '#1f1f1f',
      optionSelectedBg: '#303030',
    },
    DatePicker: {
      colorBgContainer: '#262626',
      colorBgElevated: '#1f1f1f',
    },
    Dropdown: {
      colorBgElevated: '#1f1f1f',
    },
    Popover: {
      colorBgElevated: '#1f1f1f',
    },
    Tooltip: {
      colorBgSpotlight: '#262626',
    },
    Tabs: {
      cardBg: '#262626',
    },
    Collapse: {
      headerBg: '#262626',
      contentBg: '#1f1f1f',
    },
    Alert: {
      colorInfoBg: 'rgba(59, 130, 246, 0.1)',
      colorWarningBg: 'rgba(245, 158, 11, 0.1)',
      colorErrorBg: 'rgba(239, 68, 68, 0.1)',
      colorSuccessBg: 'rgba(16, 185, 129, 0.1)',
    },
    Statistic: {
      colorTextDescription: 'rgba(255, 255, 255, 0.45)',
    },
    Divider: {
      colorSplit: '#434343',
    },
    List: {
      colorBorder: '#434343',
    },
    Form: {
      labelColor: 'rgba(255, 255, 255, 0.85)',
    },
    Typography: {
      colorText: 'rgba(255, 255, 255, 0.85)',
      colorTextSecondary: 'rgba(255, 255, 255, 0.45)',
    },
  },
};

interface ThemeProviderProps {
  children: ReactNode;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [themeMode, setThemeModeState] = useState<ThemeMode>('light');
  const [primaryColor, setPrimaryColorState] = useState('#667eea');
  const [isDark, setIsDark] = useState(false);

  // Load saved theme on mount
  useEffect(() => {
    const savedTheme = localStorage.getItem('flowfish_theme_mode') as ThemeMode;
    const savedColor = localStorage.getItem('flowfish_primary_color');
    
    if (savedTheme) {
      setThemeModeState(savedTheme);
    }
    if (savedColor) {
      setPrimaryColorState(savedColor);
    }
  }, []);

  // Determine effective theme (handle 'system' mode)
  useEffect(() => {
    const updateEffectiveTheme = () => {
      let effectiveIsDark = false;
      
      if (themeMode === 'system') {
        effectiveIsDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      } else {
        effectiveIsDark = themeMode === 'dark';
      }
      
      setIsDark(effectiveIsDark);
      
      // Update document class for any CSS that needs it
      if (effectiveIsDark) {
        document.documentElement.classList.add('dark-theme');
      } else {
        document.documentElement.classList.remove('dark-theme');
      }
    };

    updateEffectiveTheme();

    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', updateEffectiveTheme);

    return () => mediaQuery.removeEventListener('change', updateEffectiveTheme);
  }, [themeMode]);

  const setThemeMode = (mode: ThemeMode) => {
    setThemeModeState(mode);
    localStorage.setItem('flowfish_theme_mode', mode);
  };

  const setPrimaryColor = (color: string) => {
    setPrimaryColorState(color);
    localStorage.setItem('flowfish_primary_color', color);
  };

  // Build the theme config with current primary color
  const currentTheme: ThemeConfig = isDark
    ? {
        ...darkTheme,
        token: {
          ...darkTheme.token,
          colorPrimary: primaryColor,
        },
      }
    : {
        ...lightTheme,
        token: {
          ...lightTheme.token,
          colorPrimary: primaryColor,
        },
      };

  return (
    <ThemeContext.Provider
      value={{
        themeMode,
        isDark,
        setThemeMode,
        primaryColor,
        setPrimaryColor,
      }}
    >
      <ConfigProvider theme={currentTheme}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextType => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export default ThemeContext;
