import React from 'react';
import { Layout, Menu } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  ExperimentOutlined,
  GlobalOutlined,
  SecurityScanOutlined,
  SettingOutlined,
  CloudServerOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ApiOutlined,
  CodeOutlined,
  LineChartOutlined,
} from '@ant-design/icons';
import FlowfishLogo from '../FlowfishLogo';
import type { MenuProps } from 'antd';
import { APP_VERSION } from '../../version';

const { Sider } = Layout;

interface SidebarProps {
  collapsed: boolean;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const link = (path: string, text: string) => (
    <a
      href={path}
      onClick={(e) => {
        if (!e.ctrlKey && !e.metaKey && !e.shiftKey && e.button === 0) {
          e.preventDefault();
          navigate(path);
        }
      }}
      style={{ color: 'inherit', textDecoration: 'none' }}
    >
      {text}
    </a>
  );

  const menuItems: MenuProps['items'] = [
    {
      key: '/dashboard',
      icon: <DashboardOutlined />,
      label: link('/dashboard', 'Dashboard'),
    },
    {
      key: 'analysis',
      icon: <ExperimentOutlined />,
      label: 'Analysis',
      children: [
        { key: '/analysis/wizard', label: link('/analysis/wizard', 'New Analysis') },
        { key: '/analyses', label: link('/analyses', 'My Analyses') },
      ],
    },
    {
      key: 'discovery',
      icon: <GlobalOutlined />,
      label: 'Discovery',
      children: [
        { key: '/discovery/map', label: link('/discovery/map', 'Network Map') },
        { key: '/discovery/service-map', label: link('/discovery/service-map', 'Service Map') },
        { key: '/discovery/trace-explorer', label: link('/discovery/trace-explorer', 'Trace Explorer') },
        { key: '/discovery/network-explorer', label: link('/discovery/network-explorer', 'Network Explorer') },
      ],
    },
    {
      // APM section (Phase 2). Lives next to Discovery because operators
      // typically pivot between Service Map (topology) and APM Services
      // (golden signals). Trace Explorer stays under Discovery for
      // bookmark continuity but is also reachable via APM Service Detail.
      // LineChartOutlined chosen to avoid icon collision with Impact section
      // (which already uses ThunderboltOutlined).
      key: 'apm',
      icon: <LineChartOutlined />,
      label: 'APM',
      children: [
        { key: '/apm/services', label: link('/apm/services', 'Services') },
      ],
    },
    {
      key: 'impact',
      icon: <ThunderboltOutlined />,
      label: 'Impact',
      children: [
        { key: '/impact/simulation', label: link('/impact/simulation', 'Impact Simulation') },
        { key: '/impact/blast-radius', label: link('/impact/blast-radius', 'Blast Radius') },
        { key: '/impact/change-detection', label: link('/impact/change-detection', 'Change Detection') },
      ],
    },
    {
      key: 'integration',
      icon: <ApiOutlined />,
      label: 'Integration',
      children: [
        { key: '/integration/hub', label: link('/integration/hub', 'Integration Hub') },
      ],
    },
    {
      key: 'observability',
      icon: <ClockCircleOutlined />,
      label: 'Observability',
      children: [
        { key: '/observability/activity', label: link('/observability/activity', 'Activity Monitor') },
        { key: '/observability/events', label: link('/observability/events', 'Events Timeline') },
      ],
    },
    {
      key: 'security',
      icon: <SecurityScanOutlined />,
      label: 'Security',
      children: [
        { key: '/security/center', label: link('/security/center', 'Security Center') },
      ],
    },
    {
      key: '/reports',
      icon: <FileTextOutlined />,
      label: link('/reports', 'Reports'),
    },
    {
      key: 'dev',
      icon: <CodeOutlined />,
      label: 'Developer',
      children: [
        { key: '/dev/console', label: link('/dev/console', 'Query Console') },
        { key: '/dev/api-docs', label: link('/dev/api-docs', 'APIs') },
      ],
    },
    {
      key: 'management',
      icon: <CloudServerOutlined />,
      label: 'Management',
      children: [
        { key: '/management/clusters', label: link('/management/clusters', 'Clusters') },
        { key: '/management/users', label: link('/management/users', 'Users & Roles') },
      ],
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: link('/settings', 'Settings'),
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
    if (path.startsWith('/apm')) keys.push('apm');
    if (path.startsWith('/impact')) keys.push('impact');
    if (path.startsWith('/integration')) keys.push('integration');
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
        display: 'flex',
        flexDirection: 'column',
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
        defaultOpenKeys={['analysis', 'discovery', 'apm', 'impact', 'integration', 'observability', 'security', 'dev', 'management']}
        items={menuItems}
        style={{
          borderRight: 0,
          flex: 1,
        }}
      />

      <div
        style={{
          padding: collapsed ? '8px 0' : '8px 16px',
          textAlign: 'center',
          fontSize: 11,
          color: 'rgba(255,255,255,0.25)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          flexShrink: 0,
        }}
      >
        {collapsed ? `v${APP_VERSION}` : `Flowfish v${APP_VERSION}`}
      </div>

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
