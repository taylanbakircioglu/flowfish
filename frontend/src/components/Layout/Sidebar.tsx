import React from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ExperimentOutlined,
  GlobalOutlined,
  AppstoreOutlined,
  SecurityScanOutlined,
  SettingOutlined,
  CloudServerOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ApiOutlined,
  SwapOutlined,
  CodeOutlined,
  RadarChartOutlined,
  AlertOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import FlowfishLogo from '../FlowfishLogo';
import type { MenuProps } from 'antd';

const { Sider } = Layout;

interface SidebarProps {
  collapsed: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems: MenuProps['items'] = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: 'Dashboard',
      onClick: () => navigate('/dashboard'),
    },
    {
      key: 'analysis',
      icon: <ExperimentOutlined />,
      label: 'Analysis',
      children: [
        {
          key: '/analysis/wizard',
          label: 'New Analysis',
          onClick: () => navigate('/analysis/wizard'),
        },
        {
          key: '/analyses',
          label: 'My Analyses',
          onClick: () => navigate('/analyses'),
        },
      ],
    },
    {
      key: 'discovery',
      icon: <GlobalOutlined />,
      label: 'Discovery',
      children: [
        {
          key: '/discovery/map',
          label: 'Dependency Map',
          onClick: () => navigate('/discovery/map'),
        },
        {
          key: '/discovery/network-explorer',
          label: 'Network Explorer',
          onClick: () => navigate('/discovery/network-explorer'),
        },
      ],
    },
    {
      key: 'impact',
      icon: <ThunderboltOutlined />,
      label: 'Impact',
      children: [
        {
          key: '/impact/simulation',
          label: 'Impact Simulation',
          onClick: () => navigate('/impact/simulation'),
        },
        {
          key: '/impact/blast-radius',
          label: 'Blast Radius',
          onClick: () => navigate('/impact/blast-radius'),
        },
        {
          key: '/impact/change-detection',
          label: 'Change Detection',
          onClick: () => navigate('/impact/change-detection'),
        },
      ],
    },
    {
      key: 'observability',
      icon: <ClockCircleOutlined />,
      label: 'Observability',
      children: [
        {
          key: '/observability/activity',
          label: 'Activity Monitor',
          onClick: () => navigate('/observability/activity'),
        },
        {
          key: '/observability/events',
          label: 'Events Timeline',
          onClick: () => navigate('/observability/events'),
        },
      ],
    },
    {
      key: 'security',
      icon: <SecurityScanOutlined />,
      label: 'Security',
      children: [
        {
          key: '/security/center',
          label: 'Security Center',
          onClick: () => navigate('/security/center'),
        },
      ],
    },
    {
      key: '/reports',
      icon: <FileTextOutlined />,
      label: 'Reports',
      onClick: () => navigate('/reports'),
    },
    {
      key: 'dev',
      icon: <CodeOutlined />,
      label: 'Developer',
      children: [
        {
          key: '/dev/console',
          label: 'Query Console',
          onClick: () => navigate('/dev/console'),
        },
        {
          key: '/dev/api-docs',
          label: 'APIs',
          onClick: () => navigate('/dev/api-docs'),
        },
      ],
    },
    {
      key: 'management',
      icon: <CloudServerOutlined />,
      label: 'Management',
      children: [
        {
          key: '/management/clusters',
          label: 'Clusters',
          onClick: () => navigate('/management/clusters'),
        },
        {
          key: '/management/users',
          label: 'Users & Roles',
          onClick: () => navigate('/management/users'),
        },
      ],
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: 'Settings',
      onClick: () => navigate('/settings'),
    },
  ];

  // Find current selected keys from location
  const getSelectedKeys = (): string[] => {
    // For nested routes like /analysis/wizard, also select parent
    const path = location.pathname;
    const keys: string[] = [path];
    
    // Add parent keys for nested routes
    if (path.startsWith('/analysis') || path.startsWith('/analyses')) keys.push('analysis');
    if (path.startsWith('/discovery')) keys.push('discovery');
    if (path.startsWith('/impact')) keys.push('impact');
    if (path.startsWith('/observability')) keys.push('observability');
    if (path.startsWith('/security')) keys.push('security');
    if (path.startsWith('/dev')) keys.push('dev');
    if (path.startsWith('/management')) keys.push('management');
    
    return keys;
  };

  return (
    <Sider
      trigger={null}
      collapsible
      collapsed={collapsed}
      breakpoint="lg"
      collapsedWidth={80}
      width={220}
      style={{
        overflow: 'auto',
        height: '100vh',
        position: 'fixed',
        left: 0,
        top: 0,
        bottom: 0,
      }}
    >
      {/* Logo */}
      <div
        style={{
          height: 64,
          margin: '0 12px',
          background: 'rgba(6, 182, 212, 0.1)',
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontWeight: 'bold',
          fontSize: collapsed ? '14px' : '18px',
          transition: 'all 0.2s',
          overflow: 'hidden',
          cursor: 'pointer',
        }}
        onClick={() => navigate('/dashboard')}
      >
        <div style={{ filter: 'drop-shadow(0 2px 4px rgba(6, 182, 212, 0.3))' }}>
          <FlowfishLogo
            size={collapsed ? 32 : 40}
            showText={!collapsed}
            textSize={18}
          />
        </div>
      </div>

      {/* Menu */}
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={getSelectedKeys()}
        defaultOpenKeys={['analysis', 'discovery', 'impact', 'observability', 'security', 'dev', 'management']}
        items={menuItems}
        style={{
          borderRight: 0,
        }}
      />
      
      {/* Fix for text wrapping issue on smaller screens */}
      <style>{`
        .ant-menu-item,
        .ant-menu-submenu-title {
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
        }
        .ant-menu-title-content {
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
        }
        .ant-layout-sider {
          min-width: 0 !important;
        }
      `}</style>
    </Sider>
  );
};

export default Sidebar;
