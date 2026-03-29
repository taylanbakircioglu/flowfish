import React from 'react';
import { Card, Table, Tag, Row, Col, Statistic, Tooltip, Empty, Typography, theme } from 'antd';
import type { DependencySummaryService, DependencySummaryGroup } from '../../store/api/communicationApi';

const { Text } = Typography;

const CATEGORY_COLORS: Record<string, string> = {
  database: 'blue',
  cache: 'green',
  message_broker: 'purple',
};

interface DependencyCategoryGroupProps {
  group: DependencySummaryGroup;
  title: string;
}

const DependencyCategoryGroup: React.FC<DependencyCategoryGroupProps> = ({ group, title }) => {
  const { token } = theme.useToken();
  if (!group || group.total === 0) {
    return <Empty description={`No ${title.toLowerCase()}`} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const hasMultiHop = Object.values(group.by_category || {})
    .flat()
    .some((s: DependencySummaryService) => (s.hop_count ?? 1) > 1);

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 12 }}>
        <Col><Statistic title="Total" value={group.total} valueStyle={{ fontSize: 20 }} /></Col>
        {(group.critical_count ?? 0) > 0 && (
          <Col><Statistic title="Critical" value={group.critical_count} valueStyle={{ fontSize: 20, color: token.colorError }} /></Col>
        )}
        <Col><Statistic title="Categories" value={Object.keys(group.by_category || {}).length} valueStyle={{ fontSize: 20 }} /></Col>
      </Row>
      {Object.entries(group.by_category || {}).map(([cat, services]: [string, DependencySummaryService[]]) => (
        <Card
          key={cat}
          size="small"
          title={
            <>
              <Tag color={CATEGORY_COLORS[cat] || 'default'}>{cat}</Tag>
              <Text type="secondary">({services.length})</Text>
            </>
          }
          style={{ marginBottom: 8 }}
        >
          <Table
            dataSource={services}
            rowKey={(r) => `${r.namespace}/${r.name}`}
            size="small"
            pagination={false}
            columns={[
              {
                title: 'Name',
                dataIndex: 'name',
                key: 'name',
                render: (v: string, r: DependencySummaryService) => (
                  <>
                    <Text strong>{v}</Text>
                    {r.is_critical && <Tag color="red" style={{ marginLeft: 4 }}>critical</Tag>}
                  </>
                ),
              },
              { title: 'Namespace', dataIndex: 'namespace', key: 'ns' },
              { title: 'Kind', dataIndex: 'kind', key: 'kind', render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: 'Port', dataIndex: 'port', key: 'port', render: (v: number) => v ?? '-' },
              ...(hasMultiHop ? [{
                title: 'Hops',
                dataIndex: 'hop_count' as const,
                key: 'hops',
                width: 80,
                render: (v: number) => (v ?? 1) > 1
                  ? <Tag color="orange">{v} hops</Tag>
                  : <Tag color="green">direct</Tag>,
              }] : []),
              {
                title: 'Annotations',
                key: 'ann',
                render: (_: unknown, r: DependencySummaryService) => {
                  const entries = Object.entries(r.annotations || {});
                  if (!entries.length) return <Text type="secondary">-</Text>;
                  const gitRepo = r.annotations['git-repo'] || r.annotations['gitRepo'] || r.annotations['source-repo'];
                  if (gitRepo) return <Tooltip title={gitRepo}><Tag color="geekblue">git-repo</Tag></Tooltip>;
                  return (
                    <Tooltip title={entries.map(([k, v]) => `${k}=${v}`).join(', ')}>
                      <Tag>{entries.length} annotations</Tag>
                    </Tooltip>
                  );
                },
              },
            ]}
          />
        </Card>
      ))}
    </div>
  );
};

export default DependencyCategoryGroup;
