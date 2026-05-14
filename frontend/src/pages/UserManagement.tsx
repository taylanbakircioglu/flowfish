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
  Spin,
  DatePicker,
  Drawer,
  Descriptions,
  Pagination,
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
  resource_name?: string | null;
  details: Record<string, any>;
  ip_address: string;
  user_agent?: string | null;
  status?: string;
  error_message?: string | null;
  timestamp: string;
}

// Plan v3 Akış F m.10 — match the backend filter set 1:1 so the visible
// list and the CSV export always agree. `[Dayjs, Dayjs]` is converted to
// ISO strings before being sent to the API.
type DateRange = [import('dayjs').Dayjs | null, import('dayjs').Dayjs | null] | null;
interface ActivityFilters {
  action: string;
  resourceType: string;
  username: string;
  status: string;
  dateRange: DateRange;
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
  const [activityTotal, setActivityTotal] = useState(0);
  const [activityPage, setActivityPage] = useState(1);
  const [activityPageSize, setActivityPageSize] = useState(20);
  const [activityFilters, setActivityFilters] = useState<ActivityFilters>({
    action: '',
    resourceType: '',
    username: '',
    status: '',
    dateRange: null,
  });
  // Detail drawer state — drives the dedicated `<ActivityLogDetailDrawer>`
  // which renders the enriched JSONB `details` payload (client browser/OS,
  // ip address, optional error message) so operators don't have to read
  // truncated tooltip JSON.
  const [activityDrawerVisible, setActivityDrawerVisible] = useState(false);
  const [activityDrawerRecord, setActivityDrawerRecord] = useState<ActivityLog | null>(null);
  const [activityExporting, setActivityExporting] = useState(false);
  // Some installations don't yet have rows in `activity_logs`; the backend
  // falls back to `users.last_login_at` and marks every result with
  // `details.synthetic = true`. We disable deep-link / detail buttons on
  // those rows because their `id` (= row ordinal) isn't a stable key.
  const isSyntheticActivity = (a: ActivityLog | null | undefined) =>
    Boolean(a && a.details && (a.details as any).synthetic === true);

  // ================== EFFECTS ==================

  useEffect(() => {
    checkAdminRole();
    fetchUsers();
    fetchRoles();
    fetchActivityLogs();
  }, []);

  // Re-fetch when paging or filters change.
  useEffect(() => {
    fetchActivityLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activityPage, activityPageSize, activityFilters]);
  
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
  
  const buildActivityQuery = (
    extraOverrides: Record<string, string | number | undefined> = {},
    includePagination = true,
  ) => {
    const params = new URLSearchParams();
    if (includePagination) {
      params.set('limit', String(activityPageSize));
      params.set('offset', String((activityPage - 1) * activityPageSize));
    }
    if (activityFilters.action) params.set('action', activityFilters.action);
    if (activityFilters.resourceType) params.set('resource_type', activityFilters.resourceType);
    if (activityFilters.username) params.set('username', activityFilters.username);
    if (activityFilters.status) params.set('status', activityFilters.status);
    if (activityFilters.dateRange?.[0]) {
      params.set('start_time', activityFilters.dateRange[0].toISOString());
    }
    if (activityFilters.dateRange?.[1]) {
      params.set('end_time', activityFilters.dateRange[1].toISOString());
    }
    Object.entries(extraOverrides).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
    });
    return params.toString();
  };

  const fetchActivityLogs = async () => {
    setActivitiesLoading(true);
    try {
      const response = await fetch(`/api/v1/user-activity?${buildActivityQuery()}`, {
        headers: { 'Authorization': `Bearer ${getToken()}` },
      });

      if (response.ok) {
        const data = await response.json();
        setActivities(data.activities || []);
        // Backend now returns a `total` field; keep a safe fallback for
        // legacy responses (and the synthetic fallback path which already
        // computes total = activities.length).
        setActivityTotal(
          typeof data.total === 'number'
            ? data.total
            : (data.activities || []).length,
        );
      }
    } catch (error) {
      console.error('Failed to fetch activity logs:', error);
    } finally {
      setActivitiesLoading(false);
    }
  };

  // Plan v3 Akış F m.10 (B1.6 fix): the backend `/user-activity/export`
  // endpoint streams a CSV that already neutralises formula-injection
  // payloads. Here we just download the blob with the same filter set the
  // operator is currently viewing — never duplicating the filter state so
  // visible rows == exported rows.
  const handleExportActivityCsv = async () => {
    setActivityExporting(true);
    try {
      const qs = buildActivityQuery({}, /*includePagination*/ false);
      const response = await fetch(`/api/v1/user-activity/export?${qs}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!response.ok) {
        message.error('Failed to export activity logs');
        return;
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      // Try to honour the server-provided filename, fall back to a sensible
      // local default. CD parsing is intentionally minimal to avoid pulling
      // in a dependency.
      const cd = response.headers.get('Content-Disposition') || '';
      const m = cd.match(/filename="?([^";]+)"?/i);
      a.download = m?.[1] || `activity-logs-${dayjs().format('YYYYMMDD-HHmmss')}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      const truncated = response.headers.get('X-Truncated') === 'true';
      if (truncated) {
        message.warning('Export truncated to the maximum row limit. Narrow your filters for the full set.');
      } else {
        message.success('Activity log CSV downloaded');
      }
    } catch (err) {
      console.error('Failed to export activity logs:', err);
      message.error('Failed to export activity logs');
    } finally {
      setActivityExporting(false);
    }
  };

  const openActivityDetail = (record: ActivityLog) => {
    if (isSyntheticActivity(record)) {
      // B2.4 — synthetic rows have no stable identity; we still let the
      // user open the drawer for read-only inspection but disable any
      // deep-link affordance there.
    }
    setActivityDrawerRecord(record);
    setActivityDrawerVisible(true);
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
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={fetchActivityLogs}
                    loading={activitiesLoading}
                  >
                    Refresh
                  </Button>
                  <Button
                    icon={<DownloadOutlined />}
                    onClick={handleExportActivityCsv}
                    loading={activityExporting}
                    disabled={activityTotal === 0}
                  >
                    Export CSV
                  </Button>
                </Space>
              }
            >
              {/* Filter bar — every input here matches a backend filter
                  parameter so the table view and the CSV export stay
                  consistent. Changing any input resets `activityPage` to 1
                  via the useEffect dependency on activityFilters. */}
              <Row gutter={[12, 12]} style={{ marginBottom: 16 }} align="middle">
                <Col>
                  <Select
                    placeholder="Action"
                    value={activityFilters.action || undefined}
                    onChange={(v) => {
                      setActivityPage(1);
                      setActivityFilters((f) => ({ ...f, action: v || '' }));
                    }}
                    allowClear
                    style={{ width: 140 }}
                    options={[
                      { value: 'login', label: 'login' },
                      { value: 'logout', label: 'logout' },
                      { value: 'create', label: 'create' },
                      { value: 'update', label: 'update' },
                      { value: 'delete', label: 'delete' },
                      { value: 'start', label: 'start' },
                      { value: 'stop', label: 'stop' },
                      { value: 'export', label: 'export' },
                      { value: 'generate', label: 'generate' },
                      { value: 'schedule', label: 'schedule' },
                    ]}
                  />
                </Col>
                <Col>
                  <Select
                    placeholder="Resource Type"
                    value={activityFilters.resourceType || undefined}
                    onChange={(v) => {
                      setActivityPage(1);
                      setActivityFilters((f) => ({ ...f, resourceType: v || '' }));
                    }}
                    allowClear
                    style={{ width: 160 }}
                    options={[
                      { value: 'analysis', label: 'analysis' },
                      { value: 'cluster', label: 'cluster' },
                      { value: 'user', label: 'user' },
                      { value: 'role', label: 'role' },
                      { value: 'report', label: 'report' },
                      { value: 'schedule', label: 'schedule' },
                      { value: 'session', label: 'session' },
                      { value: 'settings', label: 'settings' },
                    ]}
                  />
                </Col>
                <Col>
                  <Input
                    placeholder="Username contains"
                    value={activityFilters.username}
                    onChange={(e) => {
                      setActivityPage(1);
                      setActivityFilters((f) => ({ ...f, username: e.target.value }));
                    }}
                    allowClear
                    style={{ width: 200 }}
                    prefix={<SearchOutlined />}
                  />
                </Col>
                <Col>
                  <Select
                    placeholder="Status"
                    value={activityFilters.status || undefined}
                    onChange={(v) => {
                      setActivityPage(1);
                      setActivityFilters((f) => ({ ...f, status: v || '' }));
                    }}
                    allowClear
                    style={{ width: 130 }}
                    options={[
                      { value: 'success', label: 'success' },
                      { value: 'failed', label: 'failed' },
                    ]}
                  />
                </Col>
                <Col>
                  <DatePicker.RangePicker
                    showTime
                    value={activityFilters.dateRange as any}
                    onChange={(v) => {
                      setActivityPage(1);
                      setActivityFilters((f) => ({ ...f, dateRange: v as DateRange }));
                    }}
                    style={{ width: 320 }}
                  />
                </Col>
              </Row>

              {activities.length === 0 ? (
                <Empty description="No activity logs match your filters." />
              ) : (
                <>
                  <Table<ActivityLog>
                    dataSource={activities}
                    rowKey="id"
                    loading={activitiesLoading}
                    pagination={false}
                    columns={[
                      { title: 'User', dataIndex: 'username', key: 'username', width: 140 },
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
                            'generate': 'geekblue',
                            'schedule': 'gold',
                          };
                          return <Tag color={colors[a] || 'default'}>{a}</Tag>;
                        },
                      },
                      {
                        title: 'Resource',
                        key: 'resource',
                        width: 220,
                        render: (_: any, record: ActivityLog) => (
                          <Space direction="vertical" size={0}>
                            <Tag>{record.resource_type}</Tag>
                            {record.resource_name && (
                              <Text type="secondary" style={{ fontSize: 11 }}>{record.resource_name}</Text>
                            )}
                          </Space>
                        ),
                      },
                      {
                        title: 'Details',
                        dataIndex: 'details',
                        key: 'details',
                        render: (d: Record<string, any>, record: ActivityLog) => {
                          // Build a short "summary chip" line using the
                          // most informative keys; anything else lives in
                          // the detail drawer. We deliberately filter out
                          // the enriched `client` block here because it'd
                          // dominate the line.
                          const safe = d && typeof d === 'object' ? d : {};
                          const display = Object.entries(safe).filter(
                            ([k]) => k !== 'client' && k !== 'synthetic',
                          );
                          const summary = display.length === 0
                            ? <Text type="secondary">-</Text>
                            : (
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  {display.slice(0, 2)
                                    .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                                    .join(' · ')}
                                  {display.length > 2 && ` · +${display.length - 2}`}
                                </Text>
                              );
                          const synthetic = isSyntheticActivity(record);
                          return (
                            <Space>
                              {summary}
                              <Tooltip
                                title={
                                  synthetic
                                    ? 'Detailed view unavailable for legacy login records'
                                    : 'Open detail drawer'
                                }
                              >
                                <Button
                                  type="link"
                                  size="small"
                                  onClick={() => openActivityDetail(record)}
                                  disabled={synthetic}
                                >
                                  View
                                </Button>
                              </Tooltip>
                            </Space>
                          );
                        },
                      },
                      {
                        title: 'Status',
                        dataIndex: 'status',
                        key: 'status',
                        width: 90,
                        render: (s: string) => (
                          <Tag color={s === 'success' ? 'green' : 'red'}>{s || 'success'}</Tag>
                        ),
                      },
                      {
                        title: 'Time',
                        dataIndex: 'timestamp',
                        key: 'timestamp',
                        width: 170,
                        render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss'),
                      },
                      {
                        title: 'IP',
                        dataIndex: 'ip_address',
                        key: 'ip_address',
                        width: 130,
                      },
                    ]}
                    scroll={{ x: 1000 }}
                  />
                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Pagination
                      current={activityPage}
                      pageSize={activityPageSize}
                      total={activityTotal}
                      showSizeChanger
                      pageSizeOptions={['10', '20', '50', '100', '200']}
                      onChange={(p, ps) => {
                        setActivityPage(p);
                        setActivityPageSize(ps);
                      }}
                      showTotal={(t) => `${t} activity records`}
                    />
                  </div>
                </>
              )}
            </Card>
          </TabPane>
        </Tabs>
      </Space>

      {/* Activity Log Detail Drawer (Plan v3 Akış F m.10) — renders the
          enriched JSONB `details` payload. The backend writes a structured
          `client` block (browser, OS, device, IP, raw user agent) plus any
          domain-specific fields the call site provided (e.g. `cluster_id`,
          `run_id`). We split the drawer into "Activity", "Client", and
          "Raw details JSON" sections so operators can drill from the
          summary to the raw payload without leaving the page. */}
      <Drawer
        width={520}
        open={activityDrawerVisible}
        onClose={() => {
          setActivityDrawerVisible(false);
          setActivityDrawerRecord(null);
        }}
        title={
          activityDrawerRecord ? (
            <Space>
              <Tag>{activityDrawerRecord.action}</Tag>
              <Text>{activityDrawerRecord.resource_type}</Text>
              {activityDrawerRecord.resource_name && (
                <Text type="secondary">/ {activityDrawerRecord.resource_name}</Text>
              )}
            </Space>
          ) : (
            'Activity Detail'
          )
        }
        destroyOnClose
      >
        {activityDrawerRecord ? (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="ID">
                {isSyntheticActivity(activityDrawerRecord)
                  ? <Text type="secondary">(legacy login record)</Text>
                  : activityDrawerRecord.id}
              </Descriptions.Item>
              <Descriptions.Item label="User">
                {activityDrawerRecord.username || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Action">
                {activityDrawerRecord.action}
              </Descriptions.Item>
              <Descriptions.Item label="Resource">
                <Space direction="vertical" size={0}>
                  <Tag>{activityDrawerRecord.resource_type}</Tag>
                  {activityDrawerRecord.resource_name && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {activityDrawerRecord.resource_name}
                    </Text>
                  )}
                  {activityDrawerRecord.resource_id && (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      ID: {activityDrawerRecord.resource_id}
                    </Text>
                  )}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag color={activityDrawerRecord.status === 'failed' ? 'red' : 'green'}>
                  {activityDrawerRecord.status || 'success'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Time">
                {activityDrawerRecord.timestamp
                  ? dayjs(activityDrawerRecord.timestamp).format('YYYY-MM-DD HH:mm:ss')
                  : '-'}
              </Descriptions.Item>
              {activityDrawerRecord.error_message && (
                <Descriptions.Item label="Error">
                  <Text type="danger">{activityDrawerRecord.error_message}</Text>
                </Descriptions.Item>
              )}
            </Descriptions>

            {/* Client metadata — sourced from `details.client` (parsed by
                the backend) with the IP/User-Agent header as a forensic
                fallback. */}
            {(() => {
              const detail = activityDrawerRecord.details || {};
              const client: any = (detail as any).client || {};
              const hasClient =
                client.browser ||
                client.os ||
                client.device ||
                client.ip_address ||
                activityDrawerRecord.ip_address ||
                activityDrawerRecord.user_agent;
              if (!hasClient) return null;
              return (
                <Descriptions size="small" column={1} bordered title="Client">
                  {client.browser && (
                    <Descriptions.Item label="Browser">{client.browser}</Descriptions.Item>
                  )}
                  {client.os && (
                    <Descriptions.Item label="OS">{client.os}</Descriptions.Item>
                  )}
                  {client.device && (
                    <Descriptions.Item label="Device">{client.device}</Descriptions.Item>
                  )}
                  {(client.ip_address || activityDrawerRecord.ip_address) && (
                    <Descriptions.Item label="IP">
                      {client.ip_address || activityDrawerRecord.ip_address}
                    </Descriptions.Item>
                  )}
                  {(client.user_agent_raw || activityDrawerRecord.user_agent) && (
                    <Descriptions.Item label="User-Agent (raw)">
                      <Text style={{ fontSize: 11, wordBreak: 'break-all' }}>
                        {client.user_agent_raw || activityDrawerRecord.user_agent}
                      </Text>
                    </Descriptions.Item>
                  )}
                </Descriptions>
              );
            })()}

            {/* Raw details JSON — last-resort dump for fields we don't
                explicitly surface above. We strip the `client` block (it
                already has its own section) and `synthetic` flag. */}
            {(() => {
              const detail = { ...(activityDrawerRecord.details || {}) } as Record<string, any>;
              delete detail.client;
              delete detail.synthetic;
              if (Object.keys(detail).length === 0) return null;
              return (
                <Card
                  size="small"
                  title="Details"
                  bodyStyle={{ padding: 12 }}
                >
                  <pre
                    style={{
                      fontSize: 12,
                      margin: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {JSON.stringify(detail, null, 2)}
                  </pre>
                </Card>
              );
            })()}
          </Space>
        ) : (
          <Empty description="Select an activity to view details" />
        )}
      </Drawer>

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
