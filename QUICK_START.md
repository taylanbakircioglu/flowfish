# Flowfish - Quick Start Guide

Get Flowfish up and running in 10 minutes!

## ⚡ Prerequisites

- Kubernetes 1.27+ or OpenShift 4.13+
- kubectl/oc configured and connected to your cluster
- 16GB RAM, 4 CPU cores available
- (Optional) Helm 3.x for Helm installation

## 🚀 Installation Steps

### Step 1: Deploy Flowfish (2 minutes)

```bash
# Clone repository
git clone https://github.com/yourusername/flowfish.git
cd flowfish

# Deploy to Kubernetes
kubectl apply -f deployment/kubernetes-manifests/
```

### Step 2: Wait for Pods (3-5 minutes)

```bash
# Watch pods starting
kubectl get pods -n flowfish -w

# All pods should be "Running" and "Ready"
# Expected pods:
# - frontend (2 replicas)
# - backend (3 replicas)
# - postgresql (1 replica)
# - redis (1 replica)
# - clickhouse (3 replicas)
# - neo4j (1 replica)
# - inspektor-gadget (DaemonSet, 1 per node)
```

### Step 3: Access UI (1 minute)

```bash
# Port-forward frontend service
kubectl port-forward svc/frontend -n flowfish 3000:3000

# Open browser
open http://localhost:3000
```

**Login Credentials**:
- Username: `admin`
- Password: `admin123`

⚠️ **Important**: Change password after first login!

## 🎯 First Steps After Login

### 1. Add Your First Cluster (2 minutes)

**Prerequisites**:
- The `cluster-manager` service must be running (included in Docker Compose by default)
- For **remote clusters** (not the cluster Flowfish is deployed on): run the **Setup Script** on the target cluster first. Navigate to **Add Cluster** → **Setup Script** tab to generate the script for your provider. This installs Inspektor Gadget and creates the required ServiceAccount/RBAC.

Navigate to **Management** → **Cluster Management** → **Add Cluster**

**Fill in details**:
- **Name**: `my-first-cluster`
- **Type**: `kubernetes` or `openshift`
- **API URL**: Your cluster API URL (e.g., `https://api.cluster.example.com:6443`)
- **Authentication**: Upload kubeconfig or paste service account token

**Click Save**. Flowfish will connect and start discovering workloads.

**Troubleshooting**: If pods/nodes/namespaces show 0 after adding a cluster:
- Check cluster-manager logs: `docker logs flowfish-cluster-manager` (Docker Compose) or `kubectl logs -l app=cluster-manager -n flowfish` (Kubernetes)
- Verify the Setup Script was run on the target cluster
- Ensure `FLOWFISH_ENCRYPTION_KEY` is the same for both `backend` and `cluster-manager` services

### 2. Create Your First Analysis (3 minutes)

Navigate to **Analysis** → **Create New**

**Step 1: Scope**
- Select: **Namespace**
- Choose 1-2 namespaces to analyze (start small!)

**Step 2: Gadgets**
- ✅ Network Traffic (TCP/UDP)
- ✅ DNS Queries
- ☐ Leave others unchecked for now

**Step 3: Time**
- Select: **Continuous** (runs until you stop it)

**Step 4: Output**
- ✅ Application Dependency Dashboard
- ☐ LLM Analysis (skip for now)

**Click "Create Analysis"**

### 3. Start Analysis (< 1 minute)

- Go to **Analysis List**
- Find your analysis
- Click **Start** button
- Wait 30-60 seconds for data collection to begin

### 4. View Live Map (Instant!)

Navigate to **Discovery** → **Live Map**

You should see:
- **Nodes**: Your pods, deployments, services
- **Edges**: Communication flows between them
- **Live updates**: New connections appearing in real-time

**Try This**:
- Click a node → See details in right panel
- Drag nodes → Reposition manually
- Use filters → Filter by namespace or risk level
- Change layout → Try "Hierarchical" or "Force-directed"

## 🎉 Success!

You now have Flowfish running and analyzing your cluster!

## 🚀 Next Steps

### Explore Dashboards

1. **Overview Dashboard** - See system metrics, top services, risk distribution
2. **Traffic Dashboard** - Analyze traffic patterns and protocols
3. **Security Dashboard** - View risk scores and security alerts

### Enable Advanced Features

#### Add LLM for Anomaly Detection

1. Go to **Management** → **Integration Settings** → **LLM Configuration**
2. Add your OpenAI API key
3. Enable anomaly detection
4. Set frequency (e.g., every 15 minutes)

#### Configure Webhooks

1. Go to **Management** → **Integration Settings** → **Webhooks**
2. Add webhook URL (Slack, Teams, or custom)
3. Select event types (anomaly detected, change detected)
4. Test webhook

### Create a Baseline

Creating a baseline helps detect anomalies by learning "normal" traffic.

1. Go to **Analysis** → **Create New**
2. Step 3: Select **Baseline Creation Mode**
3. Duration: 7 days recommended
4. Start analysis and let it run for a week

After 7 days:
- Go to **Data** → **Baseline Management**
- View your baseline
- Enable anomaly detection (compares current traffic to baseline)

## 📚 Learn More

- **User Manual**: [docs/user-manual.md](docs/user-manual.md)
- **Analysis Wizard Guide**: [docs/analysis-wizard.md](docs/analysis-wizard.md)
- **Dashboard Guide**: [docs/dashboards.md](docs/dashboards.md)
- **API Documentation**: http://localhost:8000/api/docs

## 🐛 Troubleshooting

**UI not loading?**
```bash
# Check frontend pod
kubectl logs -l app=frontend -n flowfish
```

**No data in Live Map?**
```bash
# Check if analysis is running
kubectl logs -l app=backend -n flowfish | grep "analysis"

# Check Inspektor Gadget
kubectl logs -l app=inspektor-gadget -n gadget
```

**Can't connect to cluster?**
- Verify API URL is correct
- Check kubeconfig/token has proper permissions
- Test with: `kubectl cluster-info`

## 💡 Tips

1. **Start Small**: Analyze 1-2 namespaces first, then expand
2. **Watch Live Map**: Keep it open to see real-time updates
3. **Check Anomalies Daily**: Review anomaly detection page regularly
4. **Export Data**: Backup your dependency maps regularly
5. **Use Filters**: Leverage namespace/type/risk filters for clarity

## 🎓 Training Resources

- **Video Tutorial**: [YouTube: Flowfish Getting Started](https://youtube.com/flowfish)
- **Webinar**: Join our weekly community webinar
- **Slack**: Ask questions in [#flowfish-support](https://flowfish-community.slack.com)

---

**Happy analyzing! 🐟🌊**

Need help? Open an issue: [GitHub Issues](https://github.com/yourusername/flowfish/issues)

