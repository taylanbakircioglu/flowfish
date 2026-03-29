import React from 'react';
import { Card, Typography, Alert, theme } from 'antd';
import { ApiOutlined, BookOutlined, CodeOutlined } from '@ant-design/icons';

const { Title, Paragraph, Text, Link } = Typography;

const APIDocumentation: React.FC = () => {
  const { token } = theme.useToken();

  const baseUrl = window.location.origin;
  const apiDocsUrl = `${baseUrl}/api/docs`;
  const redocUrl = `${baseUrl}/api/redoc`;
  const openApiUrl = `${baseUrl}/api/openapi.json`;

  const codeBlockStyle: React.CSSProperties = {
    background: '#1e1e1e',
    padding: '16px',
    borderRadius: '4px',
    marginBottom: '16px',
    overflow: 'auto',
  };

  const urlBoxStyle: React.CSSProperties = {
    background: token.colorFillAlter,
    padding: '16px',
    borderRadius: '4px',
    marginTop: '16px',
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <Title level={2}>
        <ApiOutlined /> API Documentation
      </Title>

      <Alert
        message="Interactive API Documentation Available"
        description="Flowfish provides comprehensive, interactive API documentation via Swagger UI and ReDoc. You can test API endpoints directly from the documentation interface."
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Card
        title={<><CodeOutlined /> Swagger UI - Interactive API Explorer</>}
        style={{ marginBottom: 24 }}
        extra={
          <Link href={apiDocsUrl} target="_blank" rel="noopener noreferrer">
            Open Swagger UI →
          </Link>
        }
      >
        <Paragraph>
          <Text strong>Swagger UI</Text> provides an interactive interface where you can:
        </Paragraph>
        <ul>
          <li>Browse all available API endpoints</li>
          <li>View detailed request/response schemas</li>
          <li>Execute API calls directly from the browser</li>
          <li>Test authentication and authorization</li>
          <li>See real-time examples and responses</li>
        </ul>

        <div style={urlBoxStyle}>
          <Text code>{apiDocsUrl}</Text>
        </div>

        <Paragraph style={{ marginTop: 16 }}>
          <Text type="secondary">
            Click "Authorize" button in Swagger UI and enter your JWT token to test authenticated endpoints.
          </Text>
        </Paragraph>
      </Card>

      <Card
        title={<><BookOutlined /> ReDoc - Clean API Reference</>}
        style={{ marginBottom: 24 }}
        extra={
          <Link href={redocUrl} target="_blank" rel="noopener noreferrer">
            Open ReDoc →
          </Link>
        }
      >
        <Paragraph>
          <Text strong>ReDoc</Text> provides a clean, three-panel API reference with:
        </Paragraph>
        <ul>
          <li>Beautiful, easy-to-read documentation</li>
          <li>Comprehensive endpoint descriptions</li>
          <li>Request/response examples</li>
          <li>Schema definitions</li>
          <li>Searchable interface</li>
        </ul>

        <div style={urlBoxStyle}>
          <Text code>{redocUrl}</Text>
        </div>
      </Card>

      <Card
        title="OpenAPI Specification (JSON)"
        style={{ marginBottom: 24 }}
        extra={
          <Link href={openApiUrl} target="_blank" rel="noopener noreferrer">
            Download OpenAPI JSON →
          </Link>
        }
      >
        <Paragraph>
          Download the raw OpenAPI 3.0 specification in JSON format for:
        </Paragraph>
        <ul>
          <li>API client code generation (Postman, Insomnia, etc.)</li>
          <li>Custom documentation generation</li>
          <li>CI/CD integration and testing</li>
          <li>Third-party tool integration</li>
        </ul>

        <div style={urlBoxStyle}>
          <Text code>{openApiUrl}</Text>
        </div>
      </Card>

      <Card title="Quick Start Guide">
        <Title level={4}>1. Authentication</Title>
        <Paragraph>
          All API endpoints (except <Text code>/api/v1/auth/login</Text>) require JWT authentication.
        </Paragraph>

        <div style={codeBlockStyle}>
          <pre style={{ margin: 0, color: '#e6e6e6' }}>
{`# Login to get access token
curl -X POST "${baseUrl}/api/v1/auth/login" \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "admin",
    "password": "your_password"
  }'

# Response
{
  "access_token": "eyJhbGciOiJIUz...",
  "token_type": "bearer",
  "expires_in": 28800,
  "user": {
    "id": 1,
    "username": "admin",
    "email": "admin@example.com",
    "roles": ["Super Admin"]
  },
  "requires_2fa": false,
  "two_fa_sent": false
}`}
          </pre>
        </div>

        <Title level={4}>2. Using the Token</Title>
        <Paragraph>
          Include the access token in the <Text code>Authorization</Text> header:
        </Paragraph>

        <div style={codeBlockStyle}>
          <pre style={{ margin: 0, color: '#e6e6e6' }}>
{`# Example: List all clusters
curl -X GET "${baseUrl}/api/v1/clusters" \\
  -H "Authorization: Bearer eyJhbGciOiJIUz..."

# Example: Get a specific cluster
curl -X GET "${baseUrl}/api/v1/clusters/1" \\
  -H "Authorization: Bearer eyJhbGciOiJIUz..."

# Example: Get dependency graph
curl -X GET "${baseUrl}/api/v1/communications/graph?cluster_id=1" \\
  -H "Authorization: Bearer eyJhbGciOiJIUz..."`}
          </pre>
        </div>

        <Title level={4}>3. API Categories</Title>
        <Paragraph>
          The API is organized into the following categories:
        </Paragraph>
        <ul>
          <li><Text strong>Authentication</Text> - Login, logout, 2FA, token management</li>
          <li><Text strong>Users & Roles</Text> - User management and role-based access control</li>
          <li><Text strong>API Keys</Text> - API key creation and management</li>
          <li><Text strong>Clusters</Text> - Kubernetes cluster CRUD, validation, and connection testing</li>
          <li><Text strong>Cluster Resources</Text> - Namespace inventory and management</li>
          <li><Text strong>Workloads</Text> - Kubernetes workload inventory and metadata</li>
          <li><Text strong>Analyses</Text> - Traffic analysis creation, scheduling, and lifecycle</li>
          <li><Text strong>Communications</Text> - Service-to-service communication and dependency graphs</li>
          <li><Text strong>Events & Event Types</Text> - eBPF event statistics, queries, and type definitions</li>
          <li><Text strong>Changes</Text> - Change detection and infrastructure drift tracking</li>
          <li><Text strong>Simulation & Blast Radius</Text> - Impact simulation and pre-deployment assessment</li>
          <li><Text strong>Export & Reports</Text> - Data export, scheduled reports, and report history</li>
          <li><Text strong>Dev Console</Text> - Developer query interface</li>
          <li><Text strong>Settings</Text> - System configuration</li>
          <li><Text strong>WebSocket</Text> - Real-time updates</li>
          <li><Text strong>Health</Text> - Service health and readiness probes</li>
        </ul>
      </Card>

      <Card
        title="Architecture Overview"
        style={{ marginTop: 24 }}
      >
        <Title level={4}>Microservices Architecture</Title>
        <Paragraph>
          Flowfish uses a <Text strong>microservices architecture</Text> with the following components:
        </Paragraph>
        <ol>
          <li>
            <Text strong>Backend API</Text> - Central REST API (FastAPI)
            <ul>
              <li>Public-facing HTTP endpoint behind Kubernetes Ingress</li>
              <li>Handles authentication, authorization (JWT), and RBAC</li>
              <li>Connects to databases (PostgreSQL, Neo4j, Redis, ClickHouse)</li>
              <li>Serves Swagger UI and ReDoc documentation</li>
            </ul>
          </li>
          <li>
            <Text strong>Cluster Manager</Text> - Kubernetes cluster operations (gRPC)
            <ul>
              <li>Manages cluster connections and credentials</li>
              <li>Validates cluster accessibility and permissions</li>
            </ul>
          </li>
          <li>
            <Text strong>Ingestion Service</Text> - Network traffic capture (gRPC)
            <ul>
              <li>Processes eBPF-based events via Inspector Gadget</li>
              <li>Dispatches data to TimeSeries and Graph writers</li>
            </ul>
          </li>
          <li>
            <Text strong>Analysis Orchestrator</Text> - Analysis lifecycle (gRPC)
            <ul>
              <li>Coordinates traffic capture sessions</li>
              <li>Manages scheduling and result aggregation</li>
            </ul>
          </li>
          <li>
            <Text strong>Graph Writer / Graph Query</Text> - Neo4j-based dependency mapping
            <ul>
              <li>Writes service-to-service communication edges</li>
              <li>Queries topology, dependencies, and impact analysis</li>
            </ul>
          </li>
          <li>
            <Text strong>TimeSeries Writer / TimeSeries Query</Text> - ClickHouse-based metrics
            <ul>
              <li>Writes time-series network event data</li>
              <li>Queries aggregations, trends, and event history</li>
            </ul>
          </li>
        </ol>

        <Alert
          message="Important"
          description="The Backend API is the only public-facing HTTP endpoint. Internal microservices communicate via gRPC for high performance and are not directly accessible from outside the cluster."
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
        />
      </Card>
    </div>
  );
};

export default APIDocumentation;
