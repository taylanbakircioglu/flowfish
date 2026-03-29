import React from 'react';
import { Layout, Button, Dropdown, Avatar, theme, Tooltip } from 'antd';
import {
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  DownOutlined,
  BulbOutlined,
  BulbFilled,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '../../store';
import { logout } from '../../store/slices/authSlice';
import { useTheme } from '../../contexts/ThemeContext';
import FlowfishLogo from '../FlowfishLogo';
import type { MenuProps } from 'antd';

const { Header: AntHeader } = Layout;

interface HeaderProps {
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
}

const Header: React.FC<HeaderProps> = ({ collapsed, setCollapsed }) => {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const {
    token: { colorBgContainer, colorText },
  } = theme.useToken();
  
  const user = useSelector((state: RootState) => state.auth.user);
  const { isDark, setThemeMode } = useTheme();
  
  const toggleTheme = () => {
    setThemeMode(isDark ? 'light' : 'dark');
  };

  const handleLogout = () => {
    // Clear localStorage
    localStorage.removeItem('flowfish_token');
    localStorage.removeItem('flowfish_user');
    
    dispatch(logout());
    navigate('/login');
  };

  const userMenuItems: MenuProps['items'] = [
    {
      key: 'profile',
      label: (
        <div style={{ padding: '8px 0' }}>
          <div style={{ fontWeight: 500 }}>{user?.username}</div>
          <div style={{ fontSize: '12px', color: '#666' }}>
            {user?.roles?.join(', ') || 'User'}
          </div>
        </div>
      ),
      disabled: true,
    },
    {
      type: 'divider',
    },
    {
      key: 'settings',
      label: 'Settings',
      icon: <SettingOutlined />,
      onClick: () => navigate('/settings'),
    },
    {
      key: 'logout',
      label: 'Logout',
      icon: <LogoutOutlined />,
      danger: true,
      onClick: handleLogout,
    },
  ];

  return (
    <AntHeader
      style={{
        padding: 0,
        background: colorBgContainer,
        boxShadow: '0 1px 4px rgba(0,21,41,.08)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      {/* Left: Menu Toggle - positioned at sidebar edge */}
      <div style={{ display: 'flex', alignItems: 'center', width: collapsed ? 80 : 220 }}>
        <Button
          type="text"
          icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          onClick={() => setCollapsed(!collapsed)}
          style={{
            fontSize: '18px',
            width: 64,
            height: 64,
            color: '#0891b2',
            marginLeft: collapsed ? 8 : 16,
          }}
        />
        {!collapsed && (
          <FlowfishLogo size={28} showText textSize={16} style={{ marginLeft: 8 }} />
        )}
      </div>

      {/* Center: Empty spacer */}
      <div style={{ flex: 1 }} />

      {/* Right: Theme Toggle & User Menu */}
      <div style={{ padding: '0 24px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Tooltip title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}>
          <Button
            type="text"
            icon={isDark ? <BulbFilled style={{ color: '#c9a55a' }} /> : <BulbOutlined />}
            onClick={toggleTheme}
            style={{
              fontSize: '18px',
              width: 40,
              height: 40,
              color: colorText,
            }}
          />
        </Tooltip>
        <Dropdown
          menu={{ items: userMenuItems }}
          trigger={['click']}
          placement="bottomRight"
        >
          <Button
            type="text"
            style={{
              height: '40px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              fontWeight: 500,
            }}
          >
            <Avatar
              size="small"
              icon={<UserOutlined />}
              style={{
                background: 'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',
              }}
            />
            <span>{user?.username || 'User'}</span>
            <DownOutlined style={{ fontSize: '10px' }} />
          </Button>
        </Dropdown>
      </div>
    </AntHeader>
  );
};

export default Header;
