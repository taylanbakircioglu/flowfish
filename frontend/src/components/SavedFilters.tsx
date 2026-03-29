/**
 * SavedFilters - Advanced Filtering with Saved Presets
 * 
 * Features:
 * - Save current filter configuration
 * - Load saved filter presets
 * - Quick filter presets (Critical, Recent, etc.)
 * - Filter by changed_by, affected_services range
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Card,
  Space,
  Button,
  Select,
  Slider,
  Input,
  Popover,
  List,
  Tag,
  Tooltip,
  message,
  Divider,
  Typography,
  Badge,
  InputNumber,
} from 'antd';
import {
  FilterOutlined,
  SaveOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
  PlusOutlined,
  WarningOutlined,
  ClockCircleOutlined,
  UserOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ChangeType, RiskLevel } from '../store/api/changesApi';

const { Text } = Typography;
const { Option } = Select;

// Filter configuration type
export interface FilterConfig {
  id?: string;
  name: string;
  changeTypes?: ChangeType[];
  riskLevels?: RiskLevel[];
  changedBy?: string;
  minAffectedServices?: number;
  maxAffectedServices?: number;
  namespaces?: string[];
  isDefault?: boolean;
  createdAt?: string;
}

// Storage key for localStorage
const STORAGE_KEY = 'flowfish_change_filters';

// Quick filter presets
const quickFilters: FilterConfig[] = [
  {
    id: 'critical-only',
    name: 'Critical Changes',
    riskLevels: ['critical'],
    isDefault: true,
  },
  {
    id: 'high-risk',
    name: 'High Risk',
    riskLevels: ['critical', 'high'],
    isDefault: true,
  },
  {
    id: 'removals',
    name: 'Removals Only',
    changeTypes: ['workload_removed', 'service_removed'],
    isDefault: true,
  },
  {
    id: 'additions',
    name: 'Additions Only',
    changeTypes: ['workload_added', 'connection_added'],
    isDefault: true,
  },
  {
    id: 'high-impact',
    name: 'High Impact (5+ services)',
    minAffectedServices: 5,
    isDefault: true,
  },
  {
    id: 'config-changes',
    name: 'Config & Port Changes',
    changeTypes: ['config_changed', 'port_changed'],
    isDefault: true,
  },
];

// Change type options - organized by category
const changeTypeOptions: { value: ChangeType; label: string; color: string }[] = [
  // Legacy types
  { value: 'workload_added', label: 'Workload Added', color: '#4d9f7c' },
  { value: 'workload_removed', label: 'Workload Removed', color: '#c75450' },
  { value: 'namespace_changed', label: 'Namespace Changed', color: '#a67c9e' },
  // Infrastructure changes (K8s API)
  { value: 'replica_changed', label: 'Replica Changed', color: '#c9a55a' },
  { value: 'config_changed', label: 'Config Changed', color: '#22a6a6' },
  { value: 'image_changed', label: 'Image Changed', color: '#9254de' },
  { value: 'label_changed', label: 'Label Changed', color: '#597ef7' },
  // Connection changes (eBPF)
  { value: 'connection_added', label: 'Connection Added', color: '#0891b2' },
  { value: 'port_changed', label: 'Port Changed', color: '#7c8eb5' },
  // Anomaly detection (eBPF)
  { value: 'connection_removed', label: 'Connection Anomaly', color: '#c75450' },
  { value: 'traffic_anomaly', label: 'Traffic Anomaly', color: '#d4756a' },
  { value: 'dns_anomaly', label: 'DNS Anomaly', color: '#0891b2' },
  { value: 'process_anomaly', label: 'Process Anomaly', color: '#7c8eb5' },
  { value: 'error_anomaly', label: 'Error Anomaly', color: '#cf1322' },
];

// Risk level options
const riskLevelOptions: { value: RiskLevel; label: string; color: string }[] = [
  { value: 'critical', label: 'Critical', color: '#cf1322' },
  { value: 'high', label: 'High', color: '#c75450' },
  { value: 'medium', label: 'Medium', color: '#b89b5d' },
  { value: 'low', label: 'Low', color: '#4d9f7c' },
];

interface SavedFiltersProps {
  onApplyFilter: (filter: FilterConfig) => void;
  currentFilter?: Partial<FilterConfig>;
  availableNamespaces?: string[];
  availableChangedBy?: string[];
}

const SavedFilters: React.FC<SavedFiltersProps> = ({
  onApplyFilter,
  currentFilter,
  availableNamespaces = [],
  availableChangedBy = [],
}) => {
  const [savedFilters, setSavedFilters] = useState<FilterConfig[]>([]);
  const [newFilterName, setNewFilterName] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [saveOpen, setSaveOpen] = useState(false);
  
  // Quick filter active state for toggle behavior
  const [activeQuickFilter, setActiveQuickFilter] = useState<string | null>(null);
  
  // Advanced filter state
  const [advancedFilter, setAdvancedFilter] = useState<FilterConfig>({
    name: '',
    changeTypes: [],
    riskLevels: [],
    changedBy: undefined,
    minAffectedServices: undefined,
    maxAffectedServices: undefined,
    namespaces: [],
  });

  // Load saved filters from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setSavedFilters(JSON.parse(stored));
      }
    } catch (e) {
      console.error('Failed to load saved filters:', e);
    }
  }, []);

  // Save filters to localStorage
  const saveFiltersToStorage = useCallback((filters: FilterConfig[]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
      setSavedFilters(filters);
    } catch (e) {
      console.error('Failed to save filters:', e);
    }
  }, []);

  // Handle save current filter
  const handleSaveFilter = useCallback(() => {
    if (!newFilterName.trim()) {
      message.warning('Please enter a filter name');
      return;
    }
    
    const newFilter: FilterConfig = {
      id: `custom-${Date.now()}`,
      name: newFilterName.trim(),
      ...advancedFilter,
      createdAt: dayjs().toISOString(),
    };
    
    saveFiltersToStorage([...savedFilters, newFilter]);
    setNewFilterName('');
    setSaveOpen(false);
    message.success('Filter saved');
  }, [newFilterName, advancedFilter, savedFilters, saveFiltersToStorage]);

  // Handle delete filter
  const handleDeleteFilter = useCallback((filterId: string) => {
    saveFiltersToStorage(savedFilters.filter(f => f.id !== filterId));
    message.success('Filter deleted');
  }, [savedFilters, saveFiltersToStorage]);

  // Handle apply filter
  const handleApplyFilter = useCallback((filter: FilterConfig) => {
    onApplyFilter(filter);
    setAdvancedOpen(false);
  }, [onApplyFilter]);

  // Handle quick filter click with toggle behavior
  const handleQuickFilterClick = useCallback((filter: FilterConfig) => {
    if (activeQuickFilter === filter.id) {
      // Same filter clicked - toggle off (clear filters)
      setActiveQuickFilter(null);
      onApplyFilter({ name: 'Clear' });
    } else {
      // Different filter clicked - apply it
      setActiveQuickFilter(filter.id || null);
      onApplyFilter(filter);
    }
  }, [activeQuickFilter, onApplyFilter]);

  // Apply advanced filter
  const handleApplyAdvanced = useCallback(() => {
    setActiveQuickFilter(null); // Clear quick filter selection when applying advanced filter
    handleApplyFilter(advancedFilter);
  }, [advancedFilter, handleApplyFilter]);

  // Clear all filters
  const handleClearFilters = useCallback(() => {
    setActiveQuickFilter(null);
    setAdvancedFilter({
      name: '',
      changeTypes: [],
      riskLevels: [],
      changedBy: undefined,
      minAffectedServices: undefined,
      maxAffectedServices: undefined,
      namespaces: [],
    });
    onApplyFilter({ name: 'Clear' });
  }, [onApplyFilter]);

  // Count active filters
  const activeFilterCount = [
    advancedFilter.changeTypes?.length || 0,
    advancedFilter.riskLevels?.length || 0,
    advancedFilter.changedBy ? 1 : 0,
    advancedFilter.minAffectedServices !== undefined ? 1 : 0,
    advancedFilter.namespaces?.length || 0,
  ].reduce((a, b) => a + (b > 0 ? 1 : 0), 0);

  // Advanced filter content
  const advancedFilterContent = (
    <div style={{ width: 400 }}>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* Change Types */}
        <div>
          <Text strong>Change Types</Text>
          <Select
            mode="multiple"
            placeholder="All types"
            style={{ width: '100%', marginTop: 4 }}
            value={advancedFilter.changeTypes}
            onChange={(types) => setAdvancedFilter({ ...advancedFilter, changeTypes: types })}
            maxTagCount={2}
          >
            {changeTypeOptions.map(opt => (
              <Option key={opt.value} value={opt.value}>
                <Tag color={opt.color}>{opt.label}</Tag>
              </Option>
            ))}
          </Select>
        </div>

        {/* Risk Levels */}
        <div>
          <Text strong>Risk Levels</Text>
          <Select
            mode="multiple"
            placeholder="All levels"
            style={{ width: '100%', marginTop: 4 }}
            value={advancedFilter.riskLevels}
            onChange={(levels) => setAdvancedFilter({ ...advancedFilter, riskLevels: levels })}
          >
            {riskLevelOptions.map(opt => (
              <Option key={opt.value} value={opt.value}>
                <Tag color={opt.color}>{opt.label}</Tag>
              </Option>
            ))}
          </Select>
        </div>

        {/* Changed By */}
        <div>
          <Text strong><UserOutlined /> Changed By</Text>
          <Select
            placeholder="Any user/system"
            style={{ width: '100%', marginTop: 4 }}
            value={advancedFilter.changedBy}
            onChange={(value) => setAdvancedFilter({ ...advancedFilter, changedBy: value })}
            allowClear
            showSearch
          >
            {availableChangedBy.length > 0 ? (
              availableChangedBy.map(user => (
                <Option key={user} value={user}>{user}</Option>
              ))
            ) : (
              <>
                <Option value="auto-discovery">auto-discovery</Option>
                <Option value="hpa-controller">hpa-controller</Option>
                <Option value="ci-pipeline">ci-pipeline</Option>
              </>
            )}
          </Select>
        </div>

        {/* Affected Services Range */}
        <div>
          <Text strong><TeamOutlined /> Affected Services</Text>
          <Space style={{ width: '100%', marginTop: 4 }}>
            <InputNumber
              placeholder="Min"
              min={0}
              max={100}
              value={advancedFilter.minAffectedServices}
              onChange={(value) => setAdvancedFilter({ 
                ...advancedFilter, 
                minAffectedServices: value || undefined 
              })}
              style={{ width: '100%' }}
            />
            <Text type="secondary">to</Text>
            <InputNumber
              placeholder="Max"
              min={0}
              max={100}
              value={advancedFilter.maxAffectedServices}
              onChange={(value) => setAdvancedFilter({ 
                ...advancedFilter, 
                maxAffectedServices: value || undefined 
              })}
              style={{ width: '100%' }}
            />
          </Space>
        </div>

        {/* Namespaces */}
        {availableNamespaces.length > 0 && (
          <div>
            <Text strong>Namespaces</Text>
            <Select
              mode="multiple"
              placeholder="All namespaces"
              style={{ width: '100%', marginTop: 4 }}
              value={advancedFilter.namespaces}
              onChange={(ns) => setAdvancedFilter({ ...advancedFilter, namespaces: ns })}
              maxTagCount={2}
            >
              {availableNamespaces.map(ns => (
                <Option key={ns} value={ns}>{ns}</Option>
              ))}
            </Select>
          </div>
        )}

        <Divider style={{ margin: '8px 0' }} />

        {/* Actions */}
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button onClick={handleClearFilters}>Clear All</Button>
          <Space>
            <Popover
              open={saveOpen}
              onOpenChange={setSaveOpen}
              trigger="click"
              content={
                <Space direction="vertical" style={{ width: 200 }}>
                  <Input
                    placeholder="Filter name"
                    value={newFilterName}
                    onChange={(e) => setNewFilterName(e.target.value)}
                    onPressEnter={handleSaveFilter}
                  />
                  <Button type="primary" block onClick={handleSaveFilter}>
                    <SaveOutlined /> Save Filter
                  </Button>
                </Space>
              }
            >
              <Button icon={<SaveOutlined />}>Save</Button>
            </Popover>
            <Button type="primary" onClick={handleApplyAdvanced}>
              Apply Filters
            </Button>
          </Space>
        </Space>
      </Space>
    </div>
  );

  return (
    <Space wrap>
      {/* Quick Filters with toggle behavior */}
      {quickFilters.slice(0, 4).map(filter => {
        const isActive = activeQuickFilter === filter.id;
        const baseColor = filter.riskLevels?.includes('critical') ? 'error' :
          filter.riskLevels?.includes('high') ? 'warning' :
          filter.changeTypes?.includes('workload_removed' as ChangeType) ? 'red' :
          filter.changeTypes?.includes('workload_added' as ChangeType) ? 'green' :
          'default';
        
        return (
          <Tooltip key={filter.id} title={isActive ? 'Click to remove filter' : filter.name}>
            <Tag
              style={{ 
                cursor: 'pointer', 
                padding: '4px 8px',
                border: isActive ? '2px solid #1890ff' : undefined,
                fontWeight: isActive ? 600 : undefined,
                boxShadow: isActive ? '0 0 0 2px rgba(24, 144, 255, 0.2)' : undefined,
              }}
              color={isActive ? 'blue' : baseColor}
              onClick={() => handleQuickFilterClick(filter)}
            >
              {filter.name}
            </Tag>
          </Tooltip>
        );
      })}

      {/* Saved Filters Dropdown */}
      {savedFilters.length > 0 && (
        <Popover
          trigger="click"
          content={
            <List
              size="small"
              dataSource={savedFilters}
              style={{ width: 200 }}
              renderItem={(filter) => (
                <List.Item
                  style={{ cursor: 'pointer' }}
                  onClick={() => handleApplyFilter(filter)}
                  actions={[
                    <Tooltip title="Delete" key="delete">
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteFilter(filter.id!);
                        }}
                      />
                    </Tooltip>
                  ]}
                >
                  <Space>
                    <StarFilled style={{ color: '#c9a55a' }} />
                    <Text>{filter.name}</Text>
                  </Space>
                </List.Item>
              )}
            />
          }
        >
          <Button icon={<StarOutlined />}>
            Saved ({savedFilters.length})
          </Button>
        </Popover>
      )}

      {/* Advanced Filters */}
      <Popover
        open={advancedOpen}
        onOpenChange={setAdvancedOpen}
        trigger="click"
        content={advancedFilterContent}
        placement="bottomRight"
      >
        <Badge count={activeFilterCount} size="small">
          <Button icon={<FilterOutlined />}>
            Advanced
          </Button>
        </Badge>
      </Popover>
    </Space>
  );
};

export default SavedFilters;
