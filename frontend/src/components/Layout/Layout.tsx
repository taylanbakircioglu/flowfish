import React, { useState, useEffect } from 'react';
import { Layout as AntLayout, theme } from 'antd';
import { Outlet } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import { useAnalysisWarnings } from '../../hooks/useAnalysisWarnings';

const { Content } = AntLayout;

const Layout: React.FC = () => {
  // Auto-collapse on smaller screens (< 1400px, typical for 14" laptops)
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1400);
  
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1400 && !collapsed) {
        setCollapsed(true);
      }
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [collapsed]);
  const {
    token: { colorBgContainer },
  } = theme.useToken();
  
  // Listen for analysis auto-stop warnings and display notifications
  useAnalysisWarnings();

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Sidebar collapsed={collapsed} />
      <AntLayout style={{ marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>
        <Header collapsed={collapsed} setCollapsed={setCollapsed} />
        <Content
          style={{
            margin: '24px 16px',
            padding: 24,
            minHeight: 280,
            background: colorBgContainer,
            borderRadius: 8,
          }}
        >
          <Outlet />
        </Content>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;
