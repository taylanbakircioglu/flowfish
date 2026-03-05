# Flowfish - UI Sayfa Yapısı ve Organizasyon

## 📋 İçindekiler

- [Genel Layout](#genel-layout)
- [Sayfa Listesi](#sayfa-listesi)
- [Sayfa Detayları](#sayfa-detayları)
- [Component Hiyerarşisi](#component-hiyerarşisi)
- [Navigation Flow](#navigation-flow)
- [Responsive Design](#responsive-design)

---

## Genel Layout

Tüm sayfalar aynı layout yapısını kullanır:

```
┌─────────────────────────────────────────────────────────────────┐
│ Header (Fixed Top)                                              │
│ - Logo - Cluster Selector - User Menu - Notifications          │
├─────────┬───────────────────────────────────────────────────────┤
│         │                                                         │
│ Sidebar │                                                         │
│ (Fixed  │                                                         │
│  Left)  │                Main Content Area                        │
│         │              (Scrollable)                               │
│ - Menu  │                                                         │
│   Items │                                                         │
│         │                                                         │
│         │                                                         │
│         │                                                         │
│         │                                                         │
│         │                                                         │
│         │                                                         │
└─────────┴───────────────────────────────────────────────────────┘
```

### Layout Components

**1. Header (Top Bar)**
- **Logo**: Flowfish logosu (sol üst), tıklanabilir (Home'a gider)
- **Cluster Selector**: Dropdown - aktif cluster seçimi
- **Search Bar**: Global arama (workload, namespace arama)
- **Notifications**: Bell icon + badge (yeni anomali/change sayısı)
- **User Menu**: Avatar + dropdown (Profile, Settings, Logout)

**2. Sidebar (Sol Navigasyon)**
- Collapsible (küçültülebilir)
- Icon + Text mod (küçültüldüğünde sadece icon)
- Menu grupları:
  - Dashboard
  - Analysis
  - Discovery
  - Security
  - Management
  - Settings

**3. Main Content**
- Breadcrumb navigation
- Page title + action buttons
- Content area (varies by page)
- Footer (optional)

---

## Sayfa Listesi

### 1. Authentication Pages
- Login
- OAuth Callback
- Password Reset
- Registration (optional)

### 2. Dashboard Pages
- Home / Overview Dashboard
- Application Dependency Dashboard
- Traffic & Behavior Dashboard
- Security & Risk Dashboard
- Change Timeline Dashboard
- Audit & Activity Dashboard

### 3. Analysis Pages
- Analysis Wizard (4 steps)
- Analysis List
- Analysis Detail
- Analysis Run History

### 4. Discovery Pages
- Live Map (Graph View)
- Historical Map / Timeline
- Application Inventory
- Workload Explorer

### 5. Security Pages
- Anomaly Detection
- Anomaly Details
- Change Detection
- Risk Scores

### 6. Data Pages
- Import / Export
- Baseline Management
- Graph Snapshots

### 7. Simulation Pages
- Policy Simulation (What-If)
- Change Simulation (CAP)
- Change Request Details
- Simulation Results
- Change History & Analytics

### 8. Management Pages
- Cluster Management
- Namespace Management
- User Management
- Role Management
- Integration Settings
- Webhook Configuration
- LLM Configuration

### 9. Settings Pages
- System Settings
- Profile Settings
- Notification Preferences

---

## Sayfa Detayları

### 1. Login Page

**Layout**: Centered, no header/sidebar

```
┌─────────────────────────────────────────────┐
│                                             │
│         ┌─────────────────┐                 │
│         │  Flowfish Logo  │                 │
│         │      🐟🌊       │                 │
│         └─────────────────┘                 │
│                                             │
│     ┌───────────────────────────┐           │
│     │   Username:               │           │
│     │   [___________________]   │           │
│     │                           │           │
│     │   Password:               │           │
│     │   [___________________]   │           │
│     │                           │           │
│     │   [ ] Remember me         │           │
│     │                           │           │
│     │   [     Login     ]       │           │
│     │                           │           │
│     │   Or sign in with:        │           │
│     │   [Google] [Azure] [Okta] │           │
│     │                           │           │
│     │   Forgot password?        │           │
│     └───────────────────────────┘           │
│                                             │
└─────────────────────────────────────────────┘
```

**Components**:
- Logo (centered, animated)
- Login form (Ant Design Form)
- OAuth buttons (optional)
- Password reset link
- Loading spinner (on submit)

**Behavior**:
- Submit → API call → Store JWT → Redirect to Dashboard
- OAuth button → Redirect to provider → Callback → Store JWT
- Validation: Real-time field validation
- Error handling: Toast notification

---

### 2. Home / Overview Dashboard

**Layout**: Grid-based dashboard

```
┌────────────────────────────────────────────────────────┐
│ Home / Overview Dashboard                              │
├────────────────────────────────────────────────────────┤
│                                                        │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│ │  Total   │ │  Active  │ │  Active  │ │   Risk   │  │
│ │ Clusters │ │Analyses  │ │Anomalies │ │  Score   │  │
│ │    5     │ │    12    │ │    3     │ │    65    │  │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                        │
│ ┌────────────────────────┐ ┌──────────────────────┐   │
│ │  Top Communicating     │ │  Risk Distribution   │   │
│ │  Services (Table)      │ │  (Pie Chart)         │   │
│ │                        │ │                      │   │
│ │  Service     | Req/s   │ │      [Chart]         │   │
│ │  ──────────────────    │ │                      │   │
│ │  api-gateway | 1250   │ │  ● Critical: 5       │   │
│ │  auth-svc    | 850    │ │  ● High: 12          │   │
│ │  db-proxy    | 650    │ │  ● Medium: 45        │   │
│ └────────────────────────┘ └──────────────────────┘   │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │  Recent Anomalies (Timeline)                     │  │
│ │                                                  │  │
│ │  ● [15:30] Unusual traffic spike - api-service  │  │
│ │  ● [14:20] New external connection - web-app    │  │
│ │  ● [12:45] Cross-namespace violation - auth-svc │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌─────────────────────────┐ ┌─────────────────────┐   │
│ │  Cluster Health         │ │  Top Namespaces     │   │
│ │  (Status Cards)         │ │  (Bar Chart)        │   │
│ │                         │ │                     │   │
│ │  ✓ Cluster-Prod (5/5)  │ │     [Chart]         │   │
│ │  ✓ Cluster-Stage (3/3) │ │                     │   │
│ │  ⚠ Cluster-Dev (2/3)   │ │                     │   │
│ └─────────────────────────┘ └─────────────────────┘   │
└────────────────────────────────────────────────────────┘
```

**Components**:
- Metric Cards (4x): Total clusters, analyses, anomalies, risk score
- Top Communicating Services Table
- Risk Distribution Pie Chart
- Recent Anomalies Timeline
- Cluster Health Status Cards
- Top Namespaces Bar Chart
- Refresh button (auto-refresh toggle)

**Data Refresh**: Real-time (WebSocket) + manual refresh button

---

### 3. Analysis Wizard

**Layout**: Multi-step wizard (horizontal stepper)

```
┌────────────────────────────────────────────────────────┐
│ Create New Analysis                                    │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Step 1   →   Step 2   →   Step 3   →   Step 4       │
│  Scope        Gadgets      Time         Output        │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Step 1: Scope Selection                          │  │
│ │                                                  │  │
│ │ Select scope type:                               │  │
│ │ ○ Cluster-wide                                   │  │
│ │ ● Namespace(s)  [Select: ▼]                     │  │
│ │ ○ Deployment(s) [Select: ▼]                     │  │
│ │ ○ Pod(s)        [Select: ▼]                     │  │
│ │ ○ Label selector [Key: ___ Value: ___]          │  │
│ │                                                  │  │
│ │ Selected items:                                  │  │
│ │ [✓ frontend] [✓ backend] [✓ database]           │  │
│ │                                                  │  │
│ │                        [ Cancel ] [ Next → ]     │  │
│ └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Step 2: Gadget Selection**

```
┌──────────────────────────────────────────────────┐
│ Step 2: Gadget Modules                           │
│                                                  │
│ Select modules to enable:                        │
│                                                  │
│ ☑ Network Traffic (TCP/UDP)    [Configure...]   │
│ ☑ DNS Queries                  [Configure...]   │
│ ☑ TCP Connection State         [Configure...]   │
│ ☐ Process Events                [Configure...]   │
│ ☐ Syscall Tracking              [Configure...]   │
│ ☐ File Access                   [Configure...]   │
│                                                  │
│ Estimated resource usage: Medium (2-5% CPU)      │
│                                                  │
│                        [ ← Back ] [ Next → ]     │
└──────────────────────────────────────────────────┘
```

**Step 3: Time Configuration**

```
┌──────────────────────────────────────────────────┐
│ Step 3: Time & Profile Settings                  │
│                                                  │
│ Analysis mode:                                   │
│ ● Continuous (until manually stopped)           │
│ ○ Time-bound                                     │
│   Duration: [___] minutes                        │
│ ○ Scheduled                                      │
│   Cron: [_______________]                        │
│ ○ Baseline creation                              │
│   Duration: [7] days                             │
│                                                  │
│ Baseline profile:                                │
│ [Select existing baseline ▼] or [Create new]    │
│                                                  │
│                        [ ← Back ] [ Next → ]     │
└──────────────────────────────────────────────────┘
```

**Step 4: Output Configuration**

```
┌──────────────────────────────────────────────────┐
│ Step 4: Output & Integration                     │
│                                                  │
│ Dashboards:                                      │
│ ☑ Application Dependency                        │
│ ☑ Traffic & Behavior                            │
│ ☑ Security & Risk                               │
│ ☐ Change Timeline                               │
│                                                  │
│ LLM Analysis:                                    │
│ ☑ Enable anomaly detection                      │
│   Provider: [OpenAI GPT-4 ▼]                    │
│   Frequency: [Every 15 minutes ▼]               │
│                                                  │
│ Alerts & Webhooks:                               │
│ ☑ Enable alerting                               │
│   Webhook: [Select ▼] or [Add new]              │
│                                                  │
│                 [ ← Back ] [ Create Analysis ]   │
└──────────────────────────────────────────────────┘
```

**Wizard Behavior**:
- Step validation before next
- Progress saved (draft)
- Back button enabled
- Summary preview before submit
- Success message + redirect to analysis list

---

### 4. Live Map (Graph View)

**Layout**: Full-screen graph with controls

```
┌────────────────────────────────────────────────────────┐
│ Live Dependency Map - Cluster: prod-01                │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Filters: [Namespace ▼] [Type ▼] [Risk ▼] [Search...]  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │                                                  │  │
│ │                  Graph Canvas                    │  │
│ │                                                  │  │
│ │        ○ web-app                                │  │
│ │          ↓                                      │  │
│ │        ○ api-gateway                            │  │
│ │         ↓        ↓                              │  │
│ │     ○ auth-svc  ○ data-svc                     │  │
│ │          ↓          ↓                          │  │
│ │        ○ database-pg                            │  │
│ │                                                  │  │
│ │  Legend:                                        │  │
│ │  ○ Running  ○ Warning  ○ Critical               │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ Controls: [Layout ▼] [Zoom +/-] [Fit] [Export PNG]    │
│                                                        │
│ ┌─ Detail Panel (Right Sidebar) ─────────────────┐    │
│ │ Selected: api-gateway                          │    │
│ │ Type: Deployment                               │    │
│ │ Namespace: backend                             │    │
│ │                                                │    │
│ │ Incoming: 3 connections                        │    │
│ │ - web-app:8080 (HTTP)                          │    │
│ │ - admin-panel:8080 (HTTP)                      │    │
│ │ - monitoring:9090 (Metrics)                    │    │
│ │                                                │    │
│ │ Outgoing: 5 connections                        │    │
│ │ - auth-svc:8080 (HTTP)                         │    │
│ │ - data-svc:8080 (HTTP)                         │    │
│ │ ...                                            │    │
│ │                                                │    │
│ │ [ View Logs ] [ View Metrics ] [ Edit ]        │    │
│ └────────────────────────────────────────────────┘    │
└────────────────────────────────────────────────────────┘
```

**Graph Features**:
- **Node Rendering**:
  - Shape: Pod (circle), Deployment (square), Service (diamond)
  - Color: Namespace-based or status-based
  - Size: Based on importance score
  - Icon: Service type icon (web, database, cache, etc.)
- **Edge Rendering**:
  - Thickness: Request count
  - Color: Protocol (HTTP=blue, gRPC=green, TCP=gray)
  - Animation: Live traffic flow
  - Label: Port number (on hover)
- **Interactions**:
  - Click node → Show detail panel
  - Double-click node → Zoom to neighbors
  - Drag node → Manual positioning
  - Mouse wheel → Zoom in/out
  - Right-click → Context menu
- **Layouts**:
  - Hierarchical (tier-based)
  - Force-directed (physics simulation)
  - Circular
  - Grid
  - Manual (drag & drop)

**Real-time Updates**:
- WebSocket connection for live updates
- New connections animate in
- Lost connections fade out
- Traffic pulses on edges

---

### 5. Anomaly Detection Page

**Layout**: List + detail split view

```
┌────────────────────────────────────────────────────────┐
│ Anomaly Detection                                      │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Filters: [Severity ▼] [Status ▼] [Date Range]  [🔍]  │
│                                                        │
│ ┌──────────────────────┐  ┌────────────────────────┐  │
│ │ Anomaly List         │  │ Anomaly Details        │  │
│ │                      │  │                        │  │
│ │ ┌──────────────────┐ │  │ Severity: ● Critical   │  │
│ │ │🔴 Unusual traffic │ │  │ Score: 95/100          │  │
│ │ │   spike           │ │  │ Detected: 15:30 Today  │  │
│ │ │ api-service       │ │  │                        │  │
│ │ │ 15:30 - Critical  │ │  │ Description:           │  │
│ │ └──────────────────┘ │  │ Detected unusual       │  │
│ │                      │  │ traffic pattern...     │  │
│ │ ┌──────────────────┐ │  │                        │  │
│ │ │🟠 New external   │ │  │ Affected Workloads:    │  │
│ │ │   connection     │ │  │ - api-service          │  │
│ │ │ web-app          │ │  │ - auth-service         │  │
│ │ │ 14:20 - High     │ │  │                        │  │
│ │ └──────────────────┘ │  │ Recommended Action:    │  │
│ │                      │  │ • Block external IP    │  │
│ │ ┌──────────────────┐ │  │ • Review logs          │  │
│ │ │🟡 Cross-namespace│ │  │ • Update policy        │  │
│ │ │   violation      │ │  │                        │  │
│ │ │ auth-svc         │ │  │ LLM Analysis:          │  │
│ │ │ 12:45 - Medium   │ │  │ [Show full analysis]   │  │
│ │ └──────────────────┘ │  │                        │  │
│ │                      │  │ Status: Investigating  │  │
│ │ ... (12 more)        │  │ Assigned: John Doe     │  │
│ │                      │  │                        │  │
│ │ [Load More]          │  │ Actions:               │  │
│ │                      │  │ [Resolve] [False +]    │  │
│ └──────────────────────┘  └────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Components**:
- **Anomaly List** (Left):
  - Sortable by severity, time
  - Filter by status
  - Severity badge (Critical, High, Medium, Low)
  - Click to show details
  - Pagination
- **Anomaly Details** (Right):
  - Severity indicator
  - Score (0-100)
  - Detection time
  - AI-generated description
  - Affected workloads (clickable)
  - Recommended actions
  - LLM analysis (expandable)
  - Status dropdown
  - Assign to user
  - Action buttons
  - Comments section

---

### 6. Import / Export Page

**Layout**: Tab-based interface

```
┌────────────────────────────────────────────────────────┐
│ Import / Export Data                                   │
├────────────────────────────────────────────────────────┤
│                                                        │
│ [ Export ] [ Import ] [ Job History ]                  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Export Data                                      │  │
│ │                                                  │  │
│ │ Format:                                          │  │
│ │ ○ CSV (Human-readable)                           │  │
│ │ ● Graph JSON (Re-importable)                     │  │
│ │                                                  │  │
│ │ Scope:                                           │  │
│ │ Cluster: [prod-01 ▼]                             │  │
│ │ Namespace: [All ▼] or [Select specific...]      │  │
│ │                                                  │  │
│ │ Time Range:                                      │  │
│ │ From: [2024-01-01 00:00]                         │  │
│ │ To:   [2024-01-31 23:59]                         │  │
│ │                                                  │  │
│ │ Include:                                         │  │
│ │ ☑ Workloads                                      │  │
│ │ ☑ Communications                                 │  │
│ │ ☑ Metadata                                       │  │
│ │ ☐ Anomalies                                      │  │
│ │                                                  │  │
│ │ Estimated size: ~5.2 MB                          │  │
│ │                                                  │  │
│ │               [ Export & Download ]              │  │
│ └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Import Tab**:

```
┌──────────────────────────────────────────────────┐
│ Import Data                                      │
│                                                  │
│ ┌────────────────────────────────────────────┐  │
│ │  Drag & Drop File Here                     │  │
│ │  or [ Browse Files ]                       │  │
│ │                                            │  │
│ │  Supported: CSV, JSON                      │  │
│ │  Max size: 100 MB                          │  │
│ └────────────────────────────────────────────┘  │
│                                                  │
│ Selected file: dependencies_export.json (2.3 MB) │
│                                                  │
│ Target Cluster: [prod-01 ▼]                     │
│                                                  │
│ Import Mode:                                     │
│ ○ Merge with existing data                      │
│ ● Overwrite existing data                       │
│ ○ Create new snapshot                           │
│                                                  │
│ Validation: ✓ Schema valid                      │
│             ✓ No conflicts                       │
│             ⚠ 3 warnings (optional fields)       │
│                                                  │
│                     [ Import ]                   │
└──────────────────────────────────────────────────┘
```

### 7. Change Simulation Page (CAP Integration)

**Layout**: Multi-step wizard + impact dashboard

```
┌────────────────────────────────────────────────────────┐
│ Change Simulation - CAP Integration                   │
├────────────────────────────────────────────────────────┤
│                                                        │
│ [ Create Change Request ]  [ View History ]           │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Step 1: Define Change                            │  │
│ │                                                  │  │
│ │ Change Type:                                     │  │
│ │ ● Application Update (image version)            │  │
│ │ ○ Configuration Change                           │  │
│ │ ○ Scaling Change                                 │  │
│ │ ○ Infrastructure Change                          │  │
│ │                                                  │  │
│ │ Target Service:                                  │  │
│ │ Cluster: [prod-01 ▼]                             │  │
│ │ Namespace: [payments ▼]                          │  │
│ │ Workload: [payment-service ▼]                    │  │
│ │                                                  │  │
│ │ Current State:                                   │  │
│ │ - Image: payment-service:v2.3.1                  │  │
│ │ - Replicas: 5                                    │  │
│ │ - CPU/Memory: 500m/1Gi                           │  │
│ │                                                  │  │
│ │ Proposed Change:                                 │  │
│ │ New Image: [payment-service:v2.5.0___]          │  │
│ │ Replicas: [5___] (no change)                     │  │
│ │ Resources: [Keep current] [Update ▼]            │  │
│ │                                                  │  │
│ │ Deployment Strategy:                             │  │
│ │ ● RollingUpdate  ○ Recreate  ○ BlueGreen        │  │
│ │ ○ Canary (10% traffic)                           │  │
│ │                                                  │  │
│ │                        [ Cancel ] [ Next → ]     │  │
│ └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Step 2: Schedule Change**

```
┌──────────────────────────────────────────────────┐
│ Step 2: Schedule & Metadata                      │
│                                                  │
│ Change Title:                                    │
│ [Update payment-service to v2.5.0___________]   │
│                                                  │
│ Description:                                     │
│ [Upgrade to fix critical security vulnerability] │
│ [and add new payment gateway support.________] │
│                                                  │
│ Priority:                                        │
│ ○ Low  ● Normal  ○ High  ○ Emergency            │
│                                                  │
│ Scheduled Window:                                │
│ Date: [2024-01-20 ▼]                             │
│ Start Time: [02:00 ▼] UTC                        │
│ Duration: [2 hours ▼]                            │
│                                                  │
│ ⚠️ Note: Conflicts with backup window (03:00)    │
│    Consider rescheduling to 04:00               │
│                                                  │
│ Rollback Plan:                                   │
│ ☑ Automated rollback enabled                    │
│ Trigger: [Error rate > 5%] OR [Manual]          │
│ Rollback to: [payment-service:v2.3.1]           │
│                                                  │
│ Notifications:                                   │
│ ☑ Notify stakeholders                           │
│ ☑ Create ServiceNow Change Request              │
│ ☑ Post to Slack #platform-changes               │
│                                                  │
│                        [ ← Back ] [ Next → ]     │
└──────────────────────────────────────────────────┘
```

**Step 3: Impact Analysis**

```
┌────────────────────────────────────────────────────────┐
│ Step 3: Impact Analysis                                │
├────────────────────────────────────────────────────────┤
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 🎯 Change Summary                                │  │
│ │                                                  │  │
│ │ Service: payment-service                        │  │
│ │ Change: v2.3.1 → v2.5.0                        │  │
│ │ Risk Score: 65 🟠 (High Risk)                   │  │
│ │ Blast Radius: 35 services affected              │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 📊 Impact Dimensions                             │  │
│ │                                                  │  │
│ │ Dependency Impact:       [▓▓▓▓▓▓▓▓░░] 75%       │  │
│ │ Traffic Impact:          [▓▓▓▓▓▓░░░░] 60%       │  │
│ │ Data Impact:             [▓▓░░░░░░░░] 20%       │  │
│ │ Complexity:              [▓▓▓▓▓▓▓░░░] 70%       │  │
│ │ Rollback Difficulty:     [▓▓▓░░░░░░░] 30%       │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 🔗 Affected Services                             │  │
│ │                                                  │  │
│ │ Direct Dependencies (12):                       │  │
│ │ 🔴 checkout-service          Critical           │  │
│ │    ⚠️ Breaking API change detected!             │  │
│ │    Action Required: Update to v3.2+             │  │
│ │                                                  │  │
│ │ 🟡 order-service             Medium              │  │
│ │    ⚠️ Latency increase expected (+15%)          │  │
│ │                                                  │  │
│ │ 🟢 notification-service      Low                 │  │
│ │    ✓ No breaking changes                        │  │
│ │                                                  │  │
│ │ ... [View all 12 services]                       │  │
│ │                                                  │  │
│ │ Indirect Dependencies (23):                     │  │
│ │ [View dependency graph →]                        │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 🚨 Risk Factors                                  │  │
│ │                                                  │  │
│ │ ✓ Breaking API changes (checkout-service)       │  │
│ │ ✓ Production environment                        │  │
│ │ ✓ High traffic service (15K req/min)            │  │
│ │ ⚠ Scheduled during business hours               │  │
│ │ ✓ Multiple critical dependencies                │  │
│ │ ✓ Rollback plan validated                       │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 💡 Recommendations                               │  │
│ │                                                  │  │
│ │ 1. 🔸 Update checkout-service first (v3.2+)     │  │
│ │ 2. 🔸 Deploy to staging for 24h validation      │  │
│ │ 3. 🔸 Use canary deployment (10% → 50% → 100%)  │  │
│ │ 4. 🔸 Reschedule to 04:00 (avoid backup window) │  │
│ │ 5. 🔸 Enable enhanced monitoring                │  │
│ │ 6. 🔸 Notify on-call engineer                   │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│                 [ ← Back ] [ Create Change Request ]  │
└────────────────────────────────────────────────────────┘
```

**Step 4: Approval Workflow**

```
┌────────────────────────────────────────────────────────┐
│ Change Request: CR-2024-001234                         │
│ Status: Pending Approvals                              │
├────────────────────────────────────────────────────────┤
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 📋 Approval Matrix (High Risk)                   │  │
│ │                                                  │  │
│ │ ✅ Technical Lead                                │  │
│ │    John Smith - Approved                        │  │
│ │    Comment: "Looks good, but update checkout    │  │
│ │              service first"                      │  │
│ │    Approved: 2024-01-15 14:30                    │  │
│ │                                                  │  │
│ │ ⏳ Security Lead                                 │  │
│ │    Sarah Johnson - Review In Progress           │  │
│ │    [ Request Expedited Review ]                 │  │
│ │                                                  │  │
│ │ ⏳ Change Manager                                │  │
│ │    Michael Brown - Pending                      │  │
│ │    (Waiting for Security approval)              │  │
│ │                                                  │  │
│ │ Required: 3/3 approvals                         │  │
│ │ Current: 1/3 approved                           │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 📢 Stakeholder Notifications                     │  │
│ │                                                  │  │
│ │ ✅ Sent to 12 service owners                     │  │
│ │ ✅ ServiceNow CR created: CHG0001234             │  │
│ │ ✅ Slack notification posted                     │  │
│ │ ⏳ Waiting for feedback (0 responses)            │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 📝 Comments & Discussion                         │  │
│ │                                                  │  │
│ │ John Smith (Tech Lead) - 14:30                  │  │
│ │ "Confirmed with checkout team, they'll upgrade  │  │
│ │  to v3.2 by tomorrow morning."                  │  │
│ │                                                  │  │
│ │ [Add comment_____________________________]       │  │
│ │                                                  │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ [ View Full Impact Report ] [ Export to PDF ]         │
│ [ Cancel Change Request ] [ Edit ]                    │
└────────────────────────────────────────────────────────┘
```

**Change History Page**

```
┌────────────────────────────────────────────────────────┐
│ Change History & Analytics                             │
├────────────────────────────────────────────────────────┤
│                                                        │
│ Filters: [Last 30 days ▼] [All Status ▼] [All Risk ▼]│
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ 📊 Change Statistics                             │  │
│ │                                                  │  │
│ │ Total Changes: 45                                │  │
│ │ Success Rate: 93% (42 successful, 3 rolled back)│  │
│ │ Avg Approval Time: 6.5 hours                     │  │
│ │ Emergency Changes: 2                             │  │
│ └──────────────────────────────────────────────────┘  │
│                                                        │
│ ┌──────────────────────────────────────────────────┐  │
│ │ Recent Changes                                   │  │
│ │                                                  │  │
│ │ CR-2024-001234  payment-service v2.5.0          │  │
│ │ 🟠 High Risk | ⏳ Pending | Scheduled: Jan 20    │  │
│ │                                                  │  │
│ │ CR-2024-001233  auth-service config update      │  │
│ │ 🟢 Low Risk | ✅ Completed | Jan 15 02:15        │  │
│ │                                                  │  │
│ │ CR-2024-001232  frontend v3.1.0                 │  │
│ │ 🟡 Medium Risk | ✅ Completed | Jan 14 03:00     │  │
│ │                                                  │  │
│ │ CR-2024-001231  database scaling                │  │
│ │ 🔴 Critical | 🔄 Rolled Back | Jan 13 22:45     │  │
│ │    Reason: Error rate exceeded threshold        │  │
│ │                                                  │  │
│ │ ... [Load More]                                  │  │
│ └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

**Components**:
- **Change Request Wizard**: 4-step guided creation
- **Impact Analysis Dashboard**: Visual impact representation
- **Dependency Graph**: Interactive graph showing affected services
- **Risk Meter**: Visual risk score indicator
- **Approval Workflow**: Track approval status
- **Timeline**: Change execution timeline
- **Rollback Controls**: Manual rollback trigger
- **Comparison View**: Before/after state comparison
- **Analytics Dashboard**: Change metrics and trends

**Real-time Updates**:
- Approval status changes
- Stakeholder comments
- Pre/post-change validation results
- Execution progress

---

## Component Hiyerarşisi

```
App
├── AuthProvider
├── ThemeProvider
├── Router
    ├── PublicRoutes
    │   └── Login
    └── PrivateRoutes (RequireAuth)
        ├── Layout
        │   ├── Header
        │   │   ├── Logo
        │   │   ├── ClusterSelector
        │   │   ├── SearchBar
        │   │   ├── NotificationBell
        │   │   └── UserMenu
        │   ├── Sidebar
        │   │   └── MenuItems
        │   └── Content
        │       ├── Breadcrumb
        │       └── PageContent
        └── Routes
            ├── Dashboard
            │   ├── OverviewDashboard
            │   ├── DependencyDashboard
            │   ├── TrafficDashboard
            │   ├── SecurityDashboard
            │   ├── ChangeTimelineDashboard
            │   └── AuditDashboard
            ├── Analysis
            │   ├── AnalysisWizard
            │   ├── AnalysisList
            │   └── AnalysisDetail
            ├── Discovery
            │   ├── LiveMap
            │   ├── HistoricalMap
            │   ├── ApplicationInventory
            │   └── WorkloadExplorer
            ├── Security
            │   ├── AnomalyDetection
            │   ├── AnomalyDetail
            │   ├── ChangeDetection
            │   └── RiskScores
            ├── Data
            │   ├── ImportExport
            │   ├── BaselineManagement
            │   └── GraphSnapshots
            ├── Simulation
            │   ├── PolicySimulator
            │   ├── ChangeSimulator
            │   ├── ChangeRequestDetails
            │   ├── ChangeHistory
            │   └── SimulationResults
            ├── Management
            │   ├── ClusterManagement
            │   ├── UserManagement
            │   ├── RoleManagement
            │   └── IntegrationSettings
            └── Settings
                ├── SystemSettings
                ├── ProfileSettings
                └── NotificationPreferences
```

---

## Navigation Flow

### Primary Navigation (Sidebar)

```
📊 Dashboard
   - Overview
   - Dependencies
   - Traffic
   - Security
   - Timeline
   - Audit

🔬 Analysis
   - Create New (Wizard)
   - Analysis List
   - Active Analyses

🗺️ Discovery
   - Live Map
   - Historical View
   - Inventory
   - Workload Explorer

🛡️ Security
   - Anomalies
   - Changes
   - Risk Scores

💾 Data
   - Import/Export
   - Baselines
   - Snapshots

🧪 Simulation
   - Policy Tester
   - Change Simulator (CAP)
   - Change History
   - Results

⚙️ Management
   - Clusters
   - Users
   - Roles
   - Integrations

🔧 Settings
   - System
   - Profile
   - Notifications
```

### Breadcrumb Examples

- Home
- Dashboard > Traffic & Behavior
- Analysis > Create New > Step 2
- Security > Anomalies > Anomaly #123
- Management > Clusters > prod-01

---

## Responsive Design

### Breakpoints

- **Mobile**: < 768px
- **Tablet**: 768px - 1024px
- **Desktop**: > 1024px

### Mobile Adaptations

**Sidebar**:
- Collapsed by default
- Hamburger menu icon
- Overlay on content (not push)

**Header**:
- Simplified layout
- Dropdown menus instead of inline
- Search icon (expands to full-width)

**Tables**:
- Horizontal scroll
- Card view option
- Pagination controls larger

**Graph**:
- Touch gestures (pinch to zoom)
- Simplified controls
- Detail panel as bottom sheet

---

## Renk Paleti ve Tema

### Renk Şeması (haproxy-openmanager bazlı)

**Primary Colors**:
- Primary Blue: `#1890ff`
- Success Green: `#52c41a`
- Warning Orange: `#fa8c16`
- Error Red: `#f5222d`
- Purple: `#722ed1`
- Cyan: `#13c2c2`

**Neutral Colors**:
- Dark Gray: `#262626`
- Medium Gray: `#8c8c8c`
- Light Gray: `#f0f0f0`
- White: `#ffffff`

**Status Colors**:
- Running/OK: `#52c41a` (green)
- Warning: `#faad14` (amber)
- Error/Critical: `#f5222d` (red)
- Unknown: `#8c8c8c` (gray)

**Risk Level Colors**:
- Low: `#52c41a` (green)
- Medium: `#faad14` (yellow)
- High: `#fa8c16` (orange)
- Critical: `#f5222d` (red)

### Dark Mode

- Background: `#141414`
- Surface: `#1f1f1f`
- Text: `#e8e8e8`
- Border: `#303030`

**Toggle**: User menu → Dark mode switch

---

**Versiyon**: 1.0.0  
**Son Güncelleme**: Ocak 2025  
**Durum**: Tasarım Dokümantasyonu

