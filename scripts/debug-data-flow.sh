#!/bin/bash
# Flowfish Data Flow Debug Script
# Run each section to identify where data flow breaks

NS="${NS:-pilot-flowfish}"
echo "🔍 Debugging Flowfish Data Flow in namespace: $NS"
echo "=================================================="

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "1️⃣  INSPEKTOR GADGET - eBPF Events Collection"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Gadget Pod Status:"
oc get pods -n $NS -l app=inspektor-gadget -o wide

echo ""
echo "📌 Quick test - run trace_network for 5 seconds:"
echo "   (If this shows events, Gadget is working)"
echo ""
# Check if kubectl-gadget works from one of the pods
INGESTION_POD=$(oc get pods -n $NS -l app=ingestion-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$INGESTION_POD" ]; then
    echo "Testing from ingestion-service pod: $INGESTION_POD"
    oc exec -n $NS $INGESTION_POD -- timeout 5 kubectl gadget run trace_network:latest --gadget-namespace $NS -o json 2>&1 | head -20
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "2️⃣  INGESTION SERVICE - Event Processing"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Ingestion Service Pod Status:"
oc get pods -n $NS -l app=ingestion-service

echo ""
echo "📌 Recent Ingestion Logs (last 50 lines):"
oc logs -n $NS -l app=ingestion-service --tail=50 2>&1 | grep -E "(Starting|Collection|Event|Error|trace|published)" | tail -20

echo ""
echo "📌 Active trace sessions:"
oc logs -n $NS -l app=ingestion-service --tail=200 2>&1 | grep -E "Starting kubectl gadget trace|Collection session started|trace_count" | tail -10

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "3️⃣  RABBITMQ - Message Queues"
echo "═══════════════════════════════════════════════════════════════"

RABBITMQ_POD=$(oc get pods -n $NS -l app=rabbitmq -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$RABBITMQ_POD" ]; then
    echo ""
    echo "📌 Queue message counts:"
    oc exec -n $NS $RABBITMQ_POD -- rabbitmqctl list_queues name messages messages_ready messages_unacknowledged 2>/dev/null | grep flowfish
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "4️⃣  TIMESERIES WRITER - ClickHouse Writing"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Timeseries Writer Pod Status:"
oc get pods -n $NS -l app=timeseries-writer

echo ""
echo "📌 Recent Timeseries Writer Logs:"
oc logs -n $NS -l app=timeseries-writer --tail=30 2>&1 | grep -E "(Consuming|Written|Error|event)" | tail -10

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "5️⃣  CLICKHOUSE - Event Storage"
echo "═══════════════════════════════════════════════════════════════"

CLICKHOUSE_POD=$(oc get pods -n $NS -l app=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$CLICKHOUSE_POD" ]; then
    echo ""
    echo "📌 Event counts per table:"
    oc exec -n $NS $CLICKHOUSE_POD -- clickhouse-client --query "SELECT 'network_flows' as table, count() FROM flowfish.network_flows UNION ALL SELECT 'dns_queries', count() FROM flowfish.dns_queries UNION ALL SELECT 'tcp_connections', count() FROM flowfish.tcp_connections UNION ALL SELECT 'process_events', count() FROM flowfish.process_events" 2>/dev/null
    
    echo ""
    echo "📌 Recent events (last 5):"
    oc exec -n $NS $CLICKHOUSE_POD -- clickhouse-client --query "SELECT timestamp, event_type, namespace, pod FROM flowfish.network_flows ORDER BY timestamp DESC LIMIT 5" 2>/dev/null
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "6️⃣  GRAPH WRITER - Neo4j Writing"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Graph Writer Pod Status:"
oc get pods -n $NS -l app=graph-writer

echo ""
echo "📌 Recent Graph Writer Logs:"
oc logs -n $NS -l app=graph-writer --tail=30 2>&1 | grep -E "(Consuming|Created|Error|node|edge)" | tail -10

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "7️⃣  NEO4J - Communication Graph Storage"
echo "═══════════════════════════════════════════════════════════════"

NEO4J_POD=$(oc get pods -n $NS -l app=neo4j -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$NEO4J_POD" ]; then
    echo ""
    echo "📌 Node and Relationship counts:"
    oc exec -n $NS $NEO4J_POD -- cypher-shell -u neo4j -p flowfish123 "MATCH (n) RETURN labels(n)[0] as label, count(n) as count" 2>/dev/null
    
    echo ""
    echo "📌 Communication edges count:"
    oc exec -n $NS $NEO4J_POD -- cypher-shell -u neo4j -p flowfish123 "MATCH ()-[r:COMMUNICATES_WITH]->() RETURN count(r) as communications" 2>/dev/null
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "8️⃣  GRAPH QUERY SERVICE - API"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Graph Query Pod Status:"
oc get pods -n $NS -l app=graph-query

echo ""
echo "📌 Recent Graph Query Logs:"
oc logs -n $NS -l app=graph-query --tail=20 2>&1 | tail -10

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "9️⃣  BACKEND - API Responses"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Backend Pod Status:"
oc get pods -n $NS -l app=backend

echo ""
echo "📌 Test communications endpoint (from backend pod):"
BACKEND_POD=$(oc get pods -n $NS -l app=backend -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
if [ -n "$BACKEND_POD" ]; then
    oc exec -n $NS $BACKEND_POD -- curl -s "http://localhost:8000/api/v1/communications?cluster_id=1&limit=5" 2>/dev/null | head -20
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "🔟 ANALYSIS STATUS"
echo "═══════════════════════════════════════════════════════════════"

echo ""
echo "📌 Analysis Orchestrator Logs:"
oc logs -n $NS -l app=analysis-orchestrator --tail=30 2>&1 | grep -E "(Analysis|Started|Running|Error)" | tail -10

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ Debug Complete"
echo "═══════════════════════════════════════════════════════════════"

