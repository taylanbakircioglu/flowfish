import React, { useEffect, useState } from 'react';
import { Form, Input, Button, Card, Typography, message, Alert, Space, theme } from 'antd';
import { UserOutlined, LockOutlined, SafetyOutlined, MailOutlined } from '@ant-design/icons';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { RootState } from '../store';
import { loginStart, loginSuccess, loginFailure } from '../store/slices/authSlice';
import { apiClient } from '../utils/api';
import FlowfishLogo from '../components/FlowfishLogo';
import './Login.css';

const { useToken } = theme;

const { Title, Text } = Typography;

interface LoginForm {
  username: string;
  password: string;
  two_factor_code?: string;
}

const Login: React.FC = () => {
  const { token } = useToken();
  const isDark = token.colorBgContainer !== '#ffffff';
  const [form] = Form.useForm();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  
  const { loading, isAuthenticated, error } = useSelector((state: RootState) => state.auth);
  
  // 2FA state
  const [requires2FA, setRequires2FA] = useState(false);
  const [twoFASent, setTwoFASent] = useState(false);
  const [pendingUserId, setPendingUserId] = useState<number | null>(null);
  const [pendingUsername, setPendingUsername] = useState<string>('');
  const [clientIp, setClientIp] = useState<string | null>(null);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard');
    }
  }, [isAuthenticated, navigate]);
  
  // Fetch client IP once on mount
  useEffect(() => {
    const fetchIp = async () => {
      try {
        const ipResponse = await fetch('https://api.ipify.org?format=json', { 
          signal: AbortSignal.timeout(3000)
        });
        if (ipResponse.ok) {
          const ipData = await ipResponse.json();
          setClientIp(ipData.ip);
        }
      } catch {
        // IP detection failed
      }
    };
    fetchIp();
  }, []);

  const onFinish = async (values: LoginForm) => {
    dispatch(loginStart());
    
    try {
      const response = await apiClient.post('/api/v1/auth/login', {
        username: values.username,
        password: values.password,
        client_ip: clientIp,
        two_factor_code: values.two_factor_code || null
      });

      const { access_token, user, requires_2fa, two_fa_sent } = response.data;
      
      // Check if 2FA is required
      if (requires_2fa) {
        setRequires2FA(true);
        setTwoFASent(two_fa_sent);
        setPendingUserId(user.id);
        setPendingUsername(user.username);
        dispatch(loginFailure(''));
        
        if (two_fa_sent) {
          message.info('Verification code sent to your email');
        }
        return;
      }
      
      // Save to localStorage for session persistence
      localStorage.setItem('flowfish_token', access_token);
      localStorage.setItem('flowfish_user', JSON.stringify(user));
      
      dispatch(loginSuccess({ 
        token: access_token, 
        user: user 
      }));
      
      message.success('Welcome to Flowfish!');
      navigate('/dashboard');
      
    } catch (error) {
      const errorMessage = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Login failed';
      dispatch(loginFailure(errorMessage));
      message.error(errorMessage);
    }
  };
  
  const resend2FACode = async () => {
    if (!pendingUserId) return;
    
    try {
      const token = localStorage.getItem('flowfish_token');
      await apiClient.post(`/api/v1/settings/2fa/send-code?user_id=${pendingUserId}`, {}, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      message.success('New verification code sent');
    } catch {
      message.error('Failed to resend code');
    }
  };
  
  const cancelTwoFA = () => {
    setRequires2FA(false);
    setTwoFASent(false);
    setPendingUserId(null);
    setPendingUsername('');
    form.resetFields(['two_factor_code']);
  };

  // Dynamic theme styles
  const themeStyles = {
    card: {
      background: isDark ? '#1f1f1f' : '#ffffff',
      border: isDark ? '1px solid rgba(255, 255, 255, 0.1)' : '1px solid rgba(255, 255, 255, 0.8)',
    },
    title: {
      color: isDark ? '#22d3ee' : '#0891b2',
    },
    subtitle: {
      color: isDark ? '#94a3b8' : '#334155',
    },
    input: {
      background: isDark ? '#141414' : '#ffffff',
      borderColor: isDark ? '#374151' : '#e2e8f0',
      color: isDark ? '#e5e7eb' : '#1f2937',
    },
    footer: {
      background: isDark ? '#171717' : '#f0fdfa',
      borderColor: isDark ? '#374151' : '#e0f2fe',
      textColor: isDark ? '#9ca3af' : '#475569',
    },
  };

  return (
    <div className="login-container">
      <Card 
        className="login-card" 
        bordered={false}
        style={themeStyles.card}
      >
        {/* Modern Header with Flowfish Logo */}
        <div className="login-header">
          <div className="login-icon">
            <FlowfishLogo size={72} />
          </div>
          <Title level={2} className="login-title" style={themeStyles.title}>
            Flowfish
          </Title>
          <Text className="login-subtitle" style={themeStyles.subtitle}>
            eBPF-based Observability Platform
          </Text>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert
            message="Login Failed"
            description={error}
            type="error"
            showIcon
            closable
            className="error-alert"
            onClose={() => dispatch(loginFailure(''))}
          />
        )}

        {/* Login Form */}
        <Form
          form={form}
          name="login"
          onFinish={onFinish}
          layout="vertical"
          className="login-form"
        >
          {!requires2FA ? (
            <>
              <Form.Item
                name="username"
                rules={[{ required: true, message: 'Please enter your username' }]}
              >
                <Input 
                  prefix={<UserOutlined style={{ color: '#0891b2' }} />} 
                  placeholder="Username"
                  autoComplete="username"
                  size="large"
                  style={{
                    background: themeStyles.input.background,
                    borderColor: themeStyles.input.borderColor,
                    color: themeStyles.input.color,
                  }}
                />
              </Form.Item>

              <Form.Item
                name="password"
                rules={[{ required: true, message: 'Please enter your password' }]}
              >
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#0891b2' }} />}
                  placeholder="Password"
                  autoComplete="current-password"
                  size="large"
                  style={{
                    background: themeStyles.input.background,
                    borderColor: themeStyles.input.borderColor,
                    color: themeStyles.input.color,
                  }}
                />
              </Form.Item>

              <Form.Item style={{ marginBottom: 0 }}>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={loading}
                  block
                >
                  {loading ? 'Signing In...' : 'Sign In'}
                </Button>
              </Form.Item>
            </>
          ) : (
            <>
              {/* 2FA Verification */}
              <Alert
                message="Two-Factor Authentication"
                description={
                  <span>
                    <MailOutlined style={{ marginRight: 8 }} />
                    A verification code has been sent to your email.
                    Please enter the 6-digit code below.
                  </span>
                }
                type="info"
                showIcon
                icon={<SafetyOutlined />}
                style={{ marginBottom: 16 }}
              />
              
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <Text type="secondary">Logging in as: </Text>
                <Text strong>{pendingUsername}</Text>
              </div>
              
              <Form.Item
                name="two_factor_code"
                rules={[
                  { required: true, message: 'Please enter verification code' },
                  { len: 6, message: 'Code must be 6 digits' }
                ]}
              >
                <Input 
                  prefix={<SafetyOutlined style={{ color: '#0891b2' }} />} 
                  placeholder="Enter 6-digit code"
                  maxLength={6}
                  size="large"
                  style={{ 
                    textAlign: 'center', 
                    letterSpacing: '8px', 
                    fontSize: '20px',
                    fontWeight: 'bold'
                  }}
                />
              </Form.Item>

              <Form.Item style={{ marginBottom: 8 }}>
                <Button 
                  type="primary" 
                  htmlType="submit" 
                  loading={loading}
                  block
                >
                  {loading ? 'Verifying...' : 'Verify & Sign In'}
                </Button>
              </Form.Item>
              
              <Space style={{ width: '100%', justifyContent: 'center' }}>
                <Button type="link" onClick={resend2FACode}>
                  Resend Code
                </Button>
                <Button type="link" onClick={cancelTwoFA}>
                  Cancel
                </Button>
              </Space>
            </>
          )}
        </Form>

        {/* Default Credentials */}
        {/* Footer */}
        <div 
          className="login-footer"
          style={{
            background: themeStyles.footer.background,
            borderTopColor: themeStyles.footer.borderColor,
          }}
        >
          <Text className="login-footer-text" style={{ color: themeStyles.footer.textColor }}>
            Secure Enterprise Platform · Version 1.0.0
          </Text>
        </div>
      </Card>
    </div>
  );
};

export default Login;
