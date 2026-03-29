/**
 * User & Role Management Page
 * Enterprise RBAC (Role-Based Access Control) management
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  Space,
  message,
  Tabs,
  Tag,
  Popconfirm,
  Tooltip,
  Row,
  Col,
  Badge,
  Tree,
  Typography,
  Divider,
  Avatar,
  Statistic,
  Alert,
  Empty,
  Spin
} from 'antd';
import {
  UserOutlined,
  TeamOutlined,
  SecurityScanOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  HistoryOutlined,
  UserAddOutlined,
  KeyOutlined,
  DownloadOutlined,
  SearchOutlined,
  ReloadOutlined,
  SafetyOutlined,
  LockOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MailOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { DataNode } from 'antd/es/tree';
import dayjs from 'dayjs';

const { TabPane } = Tabs;
const { Option } = Select;
const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;

// ================== PERMISSION TREE ==================

// Permission keys must match database permissions table (resource.action format)
const PERMISSION_TREE: DataNode[] = [
  {
    title: '📊 Dashboard',
    key: 'dashboard',
    children: [
      { title: 'View Dashboard', key: 'dashboard.view' },
      { title: 'View Statistics', key: 'dashboard.stats' },
    ]
  },
  {
    title: '🔬 Analysis',
    key: 'analysis',
    children: [
      { title: 'View Analyses', key: 'analysis.view' },
      { title: 'Create Analysis', key: 'analysis.create' },
      { title: 'Start/Stop Analysis', key: 'analysis.start' },
      { title: 'Delete Analysis', key: 'analysis.delete' },
    ]
  },
  {
    title: '🏢 Cluster Management',
    key: 'clusters',
    children: [
      { title: 'View Clusters', key: 'clusters.view' },
      { title: 'Create Cluster', key: 'clusters.create' },
      { title: 'Edit Cluster', key: 'clusters.edit' },
      { title: 'Delete Cluster', key: 'clusters.delete' },
    ]
  },
  {
    title: '📈 Events',
    key: 'events',
    children: [
      { title: 'View Events', key: 'events.view' },
      { title: 'Export Events', key: 'events.export' },
    ]
  },
  {
    title: '📋 Reports',
    key: 'reports',
    children: [
      { title: 'View Reports', key: 'reports.view' },
      { title: 'Generate Reports', key: 'reports.generate' },
      { title: 'Schedule Reports', key: 'reports.schedule' },
      { title: 'Report History', key: 'reports.history' },
    ]
  },
  {
    title: '🔒 Security',
    key: 'security',
    children: [
      { title: 'View Security', key: 'security.view' },
      { title: 'Manage Security', key: 'security.manage' },
    ]
  },
  {
    title: '👥 User Management',
    key: 'users',
    children: [
      { title: 'View Users', key: 'users.view' },
      { title: 'Create User', key: 'users.create' },
      { title: 'Edit User', key: 'users.edit' },
      { title: 'Delete User', key: 'users.delete' },
    ]
  },
  {
    title: '🎭 Role Management',
    key: 'roles',
    children: [
      { title: 'View Roles', key: 'roles.view' },
      { title: 'Create Role', key: 'roles.create' },
      { title: 'Edit Role', key: 'roles.edit' },
      { title: 'Delete Role', key: 'roles.delete' },
    ]
  },
  {
    title: '⚙️ Settings',
    key: 'settings',
    children: [
      { title: 'View Settings', key: 'settings.view' },
      { title: 'Edit Settings', key: 'settings.edit' },
    ]
  },
];

// ================== INTERFACES ==================

interface User {
  id: number;
  username: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  full_name: string;
  is_active: boolean;
  roles: string[];
  last_login_at: string | null;
  created_at: string;
}

interface Role {
  id: number;
  name: string;
  description: string | null;
  permissions?: string[];
  permission_count?: number;
  is_system_role: boolean;
  user_count: number;
  created_at?: string;
  updated_at?: string;
}

interface ActivityLog {
  id: number;
  user_id: number;
  username: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, any>;
  ip_address: string;
  timestamp: string;
}

// ================== MAIN COMPONENT ==================

const UserManagement: React.FC = () => {
  const [activeTab, setActiveTab] = useState('users');
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  
  // Users state
  const [users, setUsers] = useState<User[]>([]);
  const [filteredUsers, setFilteredUsers] = useState<User[]>([]);
  const [userSearchText, setUserSearchText] = useState('');
  const [userModalVisible, setUserModalVisible] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [userForm] = Form.useForm();
  
  // Roles state
  const [roles, setRoles] = useState<Role[]>([]);
  const [filteredRoles, setFilteredRoles] = useState<Role[]>([]);
  const [roleSearchText, setRoleSearchText] = useState('');
  const [roleModalVisible, setRoleModalVisible] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [roleForm] = Form.useForm();
  const [checkedPermissions, setCheckedPermissions] = useState<React.Key[]>([]);
  
  // Password modal
  const [passwordModalVisible, setPasswordModalVisible] = useState(false);
  const [passwordForm] = Form.useForm();
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  
  // Role assignment modal
  const [roleAssignmentModalVisible, setRoleAssignmentModalVisible] = useState(false);
  const [assignmentForm] = Form.useForm();
  
  // Activity logs
  const [activities, setActivities] = useState<ActivityLog[]>([]);
  const [activitiesLoading, setActivitiesLoading] = useState(false);
  
  // ================== EFFECTS ==================
  
  useEffect(() => {
    checkAdminRole();
    fetchUsers();
    fetchRoles();
    fetchActivityLogs();
  }, []);
  
  useEffect(() => {
    setFilteredUsers(users);
  }, [users]);
  
  useEffect(() => {
    setFilteredRoles(roles);
  }, [roles]);
  
  // ================== API HELPERS ==================
  
  const getToken = () => localStorage.getItem('flowfish_token');
  
  const checkAdminRole = () => {
    try {
      const token = getToken();
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const roles = payload.roles || [];
        // Case-insensitive role check
        const lowerRoles = roles.map((r: string) => r.toLowerCase());
        setIsAdmin(
          lowerRoles.includes('super admin') || 
          lowerRoles.includes('admin') ||
          lowerRoles.includes('platform admin')
        );
      }
    } catch {
      setIsAdmin(false);
    }
  };
  
  // ================== FETCH DATA ==================
  
  const fetchUsers = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/users', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setUsers(data);
      } else if (response.status === 403) {
        message.warning('You do not have permission to view users');
      }
    } catch (error) {
      console.error('Failed to fetch users:', error);
    } finally {
      setLoading(false);
    }
  };
  
  const fetchRoles = async () => {
    try {
      const response = await fetch('/api/v1/roles', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setRoles(data.roles || data);
      }
    } catch (error) {
      console.error('Failed to fetch roles:', error);
    }
  };
  
  const fetchActivityLogs = async () => {
    setActivitiesLoading(true);
    try {
      const response = await fetch('/api/v1/user-activity?limit=100', {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setActivities(data.activities || []);
      }
    } catch (error) {
      console.error('Failed to fetch activity logs:', error);
    } finally {
      setActivitiesLoading(false);
    }
  };
  
  // ================== SEARCH HANDLERS ==================
  
  const handleUserSearch = (value: string) => {
    setUserSearchText(value);
    if (!value) {
      setFilteredUsers(users);
    } else {
      const filtered = users.filter(user =>
        user.username.toLowerCase().includes(value.toLowerCase()) ||
        user.email.toLowerCase().includes(value.toLowerCase()) ||
        user.full_name?.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredUsers(filtered);
    }
  };
  
  const handleRoleSearch = (value: string) => {
    setRoleSearchText(value);
    if (!value) {
      setFilteredRoles(roles);
    } else {
      const filtered = roles.filter(role =>
        role.name.toLowerCase().includes(value.toLowerCase()) ||
        role.description?.toLowerCase().includes(value.toLowerCase())
      );
      setFilteredRoles(filtered);
    }
  };
  
  // ================== USER HANDLERS ==================
  
  const handleCreateUser = () => {
    setEditingUser(null);
    userForm.resetFields();
    userForm.setFieldsValue({ is_active: true });
    setUserModalVisible(true);
  };
  
  const handleEditUser = (user: User) => {
    setEditingUser(user);
    userForm.setFieldsValue({
      username: user.username,
      email: user.email,
      first_name: user.first_name,
      last_name: user.last_name,
      is_active: user.is_active,
      roles: user.roles
    });
    setUserModalVisible(true);
  };
  
  const handleUserSubmit = async (values: any) => {
    try {
      const url = editingUser 
        ? `/api/v1/users/${editingUser.id}` 
        : '/api/v1/users';
      
      const response = await fetch(url, {
        method: editingUser ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success(editingUser ? 'User updated successfully' : 'User created successfully');
        setUserModalVisible(false);
        fetchUsers();
        fetchRoles(); // Refresh role user counts
      } else {
        const error = await response.json();
        message.error(error.detail || 'Operation failed');
      }
    } catch (error) {
      message.error('Operation failed');
    }
  };
  
  const handleDeleteUser = async (user: User) => {
    try {
      const response = await fetch(`/api/v1/users/${user.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        message.success(`User '${user.username}' deleted`);
        fetchUsers();
        fetchRoles(); // Refresh role user counts
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to delete user');
      }
    } catch (error) {
      message.error('Failed to delete user');
    }
  };
  
  const handleChangePassword = (user: User) => {
    setSelectedUser(user);
    passwordForm.resetFields();
    setPasswordModalVisible(true);
  };
  
  const handlePasswordSubmit = async (values: any) => {
    try {
      const response = await fetch(`/api/v1/users/${selectedUser?.id}/password`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(values)
      });
      
      if (response.ok) {
        message.success('Password changed successfully');
        setPasswordModalVisible(false);
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to change password');
      }
    } catch (error) {
      message.error('Failed to change password');
    }
  };
  
  const handleAssignRoles = (user: User) => {
    setSelectedUser(user);
    assignmentForm.setFieldsValue({ roles: user.roles });
    setRoleAssignmentModalVisible(true);
  };
  
  const handleRoleAssignmentSubmit = async (values: any) => {
    try {
      const response = await fetch(`/api/v1/users/${selectedUser?.id}/roles`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify({ roles: values.roles })
      });
      
      if (response.ok) {
        message.success('Roles assigned successfully');
        setRoleAssignmentModalVisible(false);
        fetchUsers();
        fetchRoles(); // Refresh role user counts
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to assign roles');
      }
    } catch (error) {
      message.error('Failed to assign roles');
    }
  };
  
  // ================== ROLE HANDLERS ==================
  
  const handleCreateRole = () => {
    setEditingRole(null);
    roleForm.resetFields();
    roleForm.setFieldsValue({ is_active: true });
    setCheckedPermissions([]);
    setRoleModalVisible(true);
  };
  
  const handleEditRole = async (role: Role) => {
    setEditingRole(role);
    roleForm.setFieldsValue({
      name: role.name,
      description: role.description
    });
    
    // Fetch role details with permissions
    try {
      const response = await fetch(`/api/v1/roles/${role.id}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        const roleDetails = await response.json();
        setCheckedPermissions(roleDetails.permissions || []);
      } else {
        setCheckedPermissions([]);
      }
    } catch (error) {
      console.error('Failed to fetch role details:', error);
      setCheckedPermissions([]);
    }
    
    setRoleModalVisible(true);
  };
  
  const handleRoleSubmit = async (values: any) => {
    // Filter out parent keys (like 'dashboard', 'analysis') and keep only leaf permissions
    const leafPermissions = (checkedPermissions as string[]).filter(key => key.includes('.'));
    
    const roleData = {
      ...values,
      permissions: leafPermissions
    };
    
    try {
      const url = editingRole 
        ? `/api/v1/roles/${editingRole.id}` 
        : '/api/v1/roles';
      
      const response = await fetch(url, {
        method: editingRole ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`
        },
        body: JSON.stringify(roleData)
      });
      
      if (response.ok) {
        message.success(editingRole ? 'Role updated successfully' : 'Role created successfully');
        setRoleModalVisible(false);
        fetchRoles();
      } else {
        const error = await response.json();
        message.error(error.detail || 'Operation failed');
      }
    } catch (error) {
      message.error('Operation failed');
    }
  };
  
  const handleDeleteRole = async (role: Role) => {
    try {
      const response = await fetch(`/api/v1/roles/${role.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${getToken()}` }
      });
      
      if (response.ok) {
        message.success(`Role '${role.name}' deleted`);
        fetchRoles();
      } else {
        const error = await response.json();
        message.error(error.detail || 'Failed to delete role');
      }
    } catch (error) {
      message.error('Failed to delete role');
    }
  };
  
  // ================== TABLE COLUMNS ==================
  
  const userColumns: ColumnsType<User> = [
    {
      title: 'User',
      dataIndex: 'username',
      key: 'username',
      render: (text, record) => (
        <Space>
          <Avatar icon={<UserOutlined />} style={{ backgroundColor: record.is_active ? '#0891b2' : '#d9d9d9' }} />
          <div>
            <Text strong>{record.full_name || text}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 12 }}>{record.email}</Text>
          </div>
        </Space>
      )
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (is_active) => (
        is_active 
          ? <Tag icon={<CheckCircleOutlined />} color="success">Active</Tag>
          : <Tag icon={<CloseCircleOutlined />} color="default">Inactive</Tag>
      )
    },
    {
      title: 'Roles',
      dataIndex: 'roles',
      key: 'roles',
      render: (roles: string[]) => (
        <Space wrap>
          {roles?.map(role => (
            <Tag key={role} color="blue">{role}</Tag>
          ))}
          {(!roles || roles.length === 0) && <Text type="secondary">No roles</Text>}
        </Space>
      )
    },
    {
      title: 'Last Login',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      width: 150,
      render: (date) => date ? dayjs(date).format('YYYY-MM-DD HH:mm') : <Text type="secondary">Never</Text>
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_, record) => (
        <Space>
          {isAdmin ? (
            <>
              <Tooltip title="Edit">
                <Button icon={<EditOutlined />} size="small" onClick={() => handleEditUser(record)} />
              </Tooltip>
              <Tooltip title="Assign Roles">
                <Button icon={<TeamOutlined />} size="small" onClick={() => handleAssignRoles(record)} />
              </Tooltip>
              <Tooltip title="Change Password">
                <Button icon={<KeyOutlined />} size="small" onClick={() => handleChangePassword(record)} />
              </Tooltip>
              <Popconfirm
                title="Delete this user?"
                onConfirm={() => handleDeleteUser(record)}
                okText="Yes"
                cancelText="No"
              >
                <Tooltip title="Delete">
                  <Button icon={<DeleteOutlined />} danger size="small" />
                </Tooltip>
              </Popconfirm>
            </>
          ) : (
            <Text type="secondary">View Only</Text>
          )}
        </Space>
      )
    }
  ];
  
  const roleColumns: ColumnsType<Role> = [
    {
      title: 'Role',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space>
          <SecurityScanOutlined style={{ color: '#0891b2' }} />
          <div>
            <Text strong style={{ fontSize: 14 }}>{text || 'Unnamed Role'}</Text>
            {record.is_system_role && <Tag color="orange" style={{ marginLeft: 8 }}>System</Tag>}
            {record.description && (
              <>
                <br />
                <Text type="secondary" style={{ fontSize: 12 }}>{record.description}</Text>
              </>
            )}
          </div>
        </Space>
      )
    },
    {
      title: 'Users',
      dataIndex: 'user_count',
      key: 'user_count',
      width: 100,
      align: 'center' as const,
      render: (count) => <Badge count={count || 0} color="blue" showZero />
    },
    {
      title: 'Permissions',
      dataIndex: 'permission_count',
      key: 'permission_count',
      width: 120,
      align: 'center' as const,
      render: (count: number) => (
        <Badge count={count || 0} color="green" showZero />
      )
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 150,
      render: (_, record) => (
        <Space>
          {isAdmin ? (
            <>
              <Tooltip title="Edit Permissions">
                <Button icon={<EditOutlined />} size="small" onClick={() => handleEditRole(record)} />
              </Tooltip>
              {!record.is_system_role && (
                <Popconfirm
                  title="Delete this role?"
                  onConfirm={() => handleDeleteRole(record)}
                  okText="Yes"
                  cancelText="No"
                  disabled={record.user_count > 0}
                >
                  <Tooltip title={record.user_count > 0 ? "Cannot delete role with users" : "Delete"}>
                    <Button 
                      icon={<DeleteOutlined />} 
                      danger 
                      size="small" 
                      disabled={record.user_count > 0}
                    />
                  </Tooltip>
                </Popconfirm>
              )}
              {record.is_system_role && (
                <Tooltip title="System roles cannot be deleted">
                  <Tag color="blue">System</Tag>
                </Tooltip>
              )}
            </>
          ) : (
            <Text type="secondary">View Only</Text>
          )}
        </Space>
      )
    }
  ];
  
  // ================== RENDER ==================
  
  if (loading && users.length === 0) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="Loading users..." />
      </div>
    );
  }
  
  return (
    <div style={{ padding: 24 }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* Header */}
        <div>
          <Title level={2} style={{ marginBottom: 8 }}>
            <TeamOutlined style={{ marginRight: 12 }} />
            User & Role Management
          </Title>
          <Paragraph type="secondary">
            Manage users, roles, and permissions for your organization.
          </Paragraph>
        </div>
        
        {/* Stats */}
        <Row gutter={16}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic 
                title="Total Users" 
                value={users.length} 
                prefix={<UserOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic 
                title="Active Users" 
                value={users.filter(u => u.is_active).length} 
                prefix={<CheckCircleOutlined style={{ color: '#4d9f7c' }} />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic 
                title="Total Roles" 
                value={roles.length} 
                prefix={<SecurityScanOutlined />}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic 
                title="System Roles" 
                value={roles.filter(r => r.is_system_role).length} 
                prefix={<SafetyOutlined />}
              />
            </Card>
          </Col>
        </Row>
        
        {/* Admin Warning */}
        {!isAdmin && (
          <Alert
            message="Read-Only Mode"
            description="Admin privileges required to manage users and roles."
            type="info"
            showIcon
            icon={<LockOutlined />}
          />
        )}
        
        {/* Tabs */}
        <Tabs activeKey={activeTab} onChange={setActiveTab} type="card" size="large">
          {/* Users Tab */}
          <TabPane tab={<span><UserOutlined /> Users ({users.length})</span>} key="users">
            <Card 
              bordered={false}
              extra={
                <Space>
                  <Input
                    placeholder="Search users..."
                    prefix={<SearchOutlined />}
                    value={userSearchText}
                    onChange={(e) => handleUserSearch(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                  />
                  <Button icon={<ReloadOutlined />} onClick={fetchUsers}>Refresh</Button>
                  {isAdmin && (
                    <Button type="primary" icon={<UserAddOutlined />} onClick={handleCreateUser}>
                      Add User
                    </Button>
                  )}
                </Space>
              }
            >
              <Table
                columns={userColumns}
                dataSource={filteredUsers}
                rowKey="id"
                loading={loading}
                pagination={{ pageSize: 10, showSizeChanger: true }}
              />
            </Card>
          </TabPane>
          
          {/* Roles Tab */}
          <TabPane tab={<span><SecurityScanOutlined /> Roles ({roles.length})</span>} key="roles">
            <Card 
              bordered={false}
              extra={
                <Space>
                  <Input
                    placeholder="Search roles..."
                    prefix={<SearchOutlined />}
                    value={roleSearchText}
                    onChange={(e) => handleRoleSearch(e.target.value)}
                    style={{ width: 200 }}
                    allowClear
                  />
                  <Button icon={<ReloadOutlined />} onClick={fetchRoles}>Refresh</Button>
                  {isAdmin && (
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateRole}>
                      Add Role
                    </Button>
                  )}
                </Space>
              }
            >
              <Table
                columns={roleColumns}
                dataSource={filteredRoles}
                rowKey="id"
                pagination={{ pageSize: 10 }}
              />
            </Card>
          </TabPane>
          
          {/* Activity Logs Tab */}
          <TabPane tab={<span><HistoryOutlined /> Activity Logs</span>} key="activity">
            <Card 
              bordered={false}
              extra={
                <Space>
                  <Button icon={<ReloadOutlined />} onClick={fetchActivityLogs}>Refresh</Button>
                  <Button icon={<DownloadOutlined />}>Export CSV</Button>
                </Space>
              }
            >
              {activities.length === 0 ? (
                <Empty description="No activity logs available. Activities will appear here as users perform actions." />
              ) : (
                <Table
                  dataSource={activities}
                  rowKey="id"
                  loading={activitiesLoading}
                  pagination={{ pageSize: 20 }}
                  columns={[
                    { title: 'User', dataIndex: 'username', key: 'username', width: 120 },
                    { 
                      title: 'Action', 
                      dataIndex: 'action', 
                      key: 'action',
                      width: 100,
                      render: (a: string) => {
                        const colors: Record<string, string> = {
                          'login': 'green',
                          'logout': 'default',
                          'create': 'blue',
                          'update': 'orange',
                          'delete': 'red',
                          'start': 'cyan',
                          'stop': 'volcano',
                          'export': 'purple',
                          'generate': 'geekblue'
                        };
                        return <Tag color={colors[a] || 'default'}>{a}</Tag>;
                      }
                    },
                    { 
                      title: 'Resource', 
                      key: 'resource',
                      width: 200,
                      render: (_: any, record: any) => (
                        <Space direction="vertical" size={0}>
                          <Tag>{record.resource_type}</Tag>
                          {record.resource_name && (
                            <Text type="secondary" style={{ fontSize: 11 }}>{record.resource_name}</Text>
                          )}
                        </Space>
                      )
                    },
                    { 
                      title: 'Details', 
                      dataIndex: 'details', 
                      key: 'details',
                      width: 200,
                      render: (d: any) => {
                        if (!d || Object.keys(d).length === 0) return '-';
                        return (
                          <Tooltip title={JSON.stringify(d, null, 2)}>
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {Object.entries(d).slice(0, 2).map(([k, v]) => `${k}: ${v}`).join(', ')}
                              {Object.keys(d).length > 2 && '...'}
                            </Text>
                          </Tooltip>
                        );
                      }
                    },
                    { 
                      title: 'Status', 
                      dataIndex: 'status', 
                      key: 'status',
                      width: 80,
                      render: (s: string) => (
                        <Tag color={s === 'success' ? 'green' : 'red'}>{s}</Tag>
                      )
                    },
                    { 
                      title: 'Time', 
                      dataIndex: 'timestamp', 
                      key: 'timestamp',
                      width: 150,
                      render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss') 
                    },
                    { 
                      title: 'IP', 
                      dataIndex: 'ip_address', 
                      key: 'ip_address',
                      width: 120
                    },
                  ]}
                  scroll={{ x: 1000 }}
                />
              )}
            </Card>
          </TabPane>
        </Tabs>
      </Space>
      
      {/* User Modal */}
      <Modal
        title={editingUser ? 'Edit User' : 'Create User'}
        open={userModalVisible}
        onCancel={() => setUserModalVisible(false)}
        footer={null}
        width={600}
      >
        <Form form={userForm} layout="vertical" onFinish={handleUserSubmit}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="username"
                label="Username"
                rules={[{ required: true, message: 'Username is required' }]}
              >
                <Input prefix={<UserOutlined />} disabled={!!editingUser} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="email"
                label="Email"
                rules={[
                  { required: true, message: 'Email is required' },
                  { type: 'email', message: 'Invalid email' }
                ]}
              >
                <Input prefix={<MailOutlined />} />
              </Form.Item>
            </Col>
          </Row>
          
          {!editingUser && (
            <Form.Item
              name="password"
              label="Password"
              rules={[
                { required: true, message: 'Password is required' },
                { min: 8, message: 'Password must be at least 8 characters' }
              ]}
            >
              <Input.Password />
            </Form.Item>
          )}
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="first_name" label="First Name">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="last_name" label="Last Name">
                <Input />
              </Form.Item>
            </Col>
          </Row>
          
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
          </Form.Item>
          
          <Form.Item name="roles" label="Roles">
            <Select mode="multiple" placeholder="Select roles">
              {roles.map(role => (
                <Option key={role.name} value={role.name}>
                  <Space>
                    <Text strong>{role.name}</Text>
                    {role.description && <Text type="secondary">- {role.description}</Text>}
                  </Space>
                </Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                {editingUser ? 'Update' : 'Create'}
              </Button>
              <Button onClick={() => setUserModalVisible(false)}>Cancel</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
      
      {/* Role Modal */}
      <Modal
        title={editingRole ? 'Edit Role' : 'Create Role'}
        open={roleModalVisible}
        onCancel={() => setRoleModalVisible(false)}
        footer={null}
        width={800}
      >
        <Form form={roleForm} layout="vertical" onFinish={handleRoleSubmit}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="name"
                label="Role Name (System ID)"
                rules={[{ required: true, message: 'Role name is required' }]}
              >
                <Input disabled={!!editingRole} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="description" label="Description">
                <TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
          
          <Divider>Permissions</Divider>
          
          <div style={{ border: '1px solid #d9d9d9', borderRadius: 8, padding: 16, maxHeight: 300, overflow: 'auto' }}>
            <Tree
              checkable
              checkedKeys={checkedPermissions}
              onCheck={(checked) => setCheckedPermissions(checked as React.Key[])}
              treeData={PERMISSION_TREE}
              defaultExpandAll
            />
          </div>
          
          <Form.Item style={{ marginTop: 24 }}>
            <Space>
              <Button type="primary" htmlType="submit">
                {editingRole ? 'Update' : 'Create'}
              </Button>
              <Button onClick={() => setRoleModalVisible(false)}>Cancel</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
      
      {/* Password Change Modal */}
      <Modal
        title={`Change Password - ${selectedUser?.username}`}
        open={passwordModalVisible}
        onCancel={() => setPasswordModalVisible(false)}
        footer={null}
      >
        <Form form={passwordForm} layout="vertical" onFinish={handlePasswordSubmit}>
          <Form.Item
            name="new_password"
            label="New Password"
            rules={[
              { required: true, message: 'Password is required' },
              { min: 8, message: 'Password must be at least 8 characters' }
            ]}
          >
            <Input.Password />
          </Form.Item>
          
          <Form.Item
            name="confirm_password"
            label="Confirm Password"
            dependencies={['new_password']}
            rules={[
              { required: true, message: 'Please confirm password' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('Passwords do not match'));
                },
              }),
            ]}
          >
            <Input.Password />
          </Form.Item>
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">Change Password</Button>
              <Button onClick={() => setPasswordModalVisible(false)}>Cancel</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
      
      {/* Role Assignment Modal */}
      <Modal
        title={`Assign Roles - ${selectedUser?.username}`}
        open={roleAssignmentModalVisible}
        onCancel={() => setRoleAssignmentModalVisible(false)}
        footer={null}
      >
        <Form form={assignmentForm} layout="vertical" onFinish={handleRoleAssignmentSubmit}>
          <Form.Item name="roles" label="Select Roles">
            <Select mode="multiple" placeholder="Select roles" style={{ width: '100%' }}>
              {roles.map(role => (
                <Option key={role.name} value={role.name}>
                  <Space>
                    <SecurityScanOutlined />
                    <div>
                      <Text strong>{role.name}</Text>
                      {role.is_system_role && <Tag color="orange" style={{ fontSize: 10, marginLeft: 4 }}>System</Tag>}
                      {role.description && (
                        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>{role.description}</Text>
                      )}
                    </div>
                  </Space>
                </Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">Assign Roles</Button>
              <Button onClick={() => setRoleAssignmentModalVisible(false)}>Cancel</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UserManagement;
