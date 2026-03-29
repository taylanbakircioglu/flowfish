#!/bin/bash
# ============================================================
# FLOWFISH TAM TEMİZLİK SCRIPT'İ v5.0
# Tüm tabloları siler - Migration'lar pipeline ile çalışacak
# SADECE CLUSTER TANIMLARI KORUNUR
# 
# Kullanım:
#   1. NS ve şifre değerlerini ortamınıza göre güncelleyin
#   2. chmod +x cleanup-full-reset.sh
#   3. ./cleanup-full-reset.sh
#
# Tarih: 2025-01-08
# ============================================================

# ============================================================
# YAPILANDIRMA - Bu değerleri ortamınıza göre güncelleyin
# ============================================================
NS="your-namespace"                    # Örnek: flowfish-prod
NEO4J_PASSWORD="your-neo4j-password"   # Örnek: mySecureP@ssw0rd

# ============================================================
# SCRIPT BAŞLANGIÇ
# ============================================================

echo "============================================================"
echo "FLOWFISH TAM TEMİZLİK v5.0"
echo "Namespace: $NS"
echo "============================================================"

# Namespace kontrolü
if [ "$NS" == "your-namespace" ]; then
  echo "❌ HATA: NS değişkenini güncelleyin!"
  echo "   Örnek: NS=\"flowfish-prod\""
  exit 1
fi

# ============================================================
# STEP 1: Tüm Servisleri Durdur
# ============================================================
echo ""
echo "=== STEP 1: Tüm Servisleri Durduruyorum ==="
oc scale deployment/ingestion-service -n $NS --replicas=0
oc scale deployment/timeseries-writer -n $NS --replicas=0
oc scale deployment/graph-writer -n $NS --replicas=0
oc scale deployment/timeseries-query -n $NS --replicas=0
oc scale deployment/graph-query -n $NS --replicas=0
oc scale deployment/analysis-orchestrator -n $NS --replicas=0
oc scale deployment/backend -n $NS --replicas=0
oc scale deployment/change-detection-worker -n $NS --replicas=0
oc scale deployment/frontend -n $NS --replicas=0

echo "15 saniye bekleniyor..."
sleep 15

# ============================================================
# STEP 2: RabbitMQ Kuyrukları Temizle
# ============================================================
echo ""
echo "=== STEP 2: RabbitMQ Kuyrukları Temizleniyor ==="
RABBITMQ_POD="rabbitmq-0"

for queue in \
  flowfish.queue.network_flows.timeseries \
  flowfish.queue.network_flows.graph \
  flowfish.queue.dns_queries.timeseries \
  flowfish.queue.dns_queries.graph \
  flowfish.queue.tcp_connections.timeseries \
  flowfish.queue.tcp_connections.graph \
  flowfish.queue.process_events.timeseries \
  flowfish.queue.file_events.timeseries \
  flowfish.queue.security_events.timeseries \
  flowfish.queue.oom_events.timeseries \
  flowfish.queue.bind_events.timeseries \
  flowfish.queue.bind_events.graph \
  flowfish.queue.sni_events.timeseries \
  flowfish.queue.sni_events.graph \
  flowfish.queue.mount_events.timeseries \
  flowfish.queue.workload_metadata.timeseries \
  flowfish.queue.change_events.timeseries
do
  oc exec -n $NS $RABBITMQ_POD -- rabbitmqctl purge_queue $queue 2>/dev/null || true
done

echo "RabbitMQ kuyrukları temizlendi"

# ============================================================
# STEP 3: Neo4j Temizleme
# ============================================================
echo ""
echo "=== STEP 3: Neo4j Temizleniyor ==="

if [ "$NEO4J_PASSWORD" == "your-neo4j-password" ]; then
  echo "⚠️ UYARI: NEO4J_PASSWORD değişkenini güncelleyin!"
  echo "   Neo4j temizleme atlanıyor..."
else
  oc exec -n $NS neo4j-0 -- wget -q -O - \
    --header="Content-Type: application/json" \
    --http-user=neo4j --http-password="$NEO4J_PASSWORD" \
    --post-data='{"statements":[{"statement":"MATCH (n) DETACH DELETE n"}]}' \
    http://localhost:7474/db/neo4j/tx/commit
  echo ""
  echo "Neo4j temizlendi"
fi

# ============================================================
# STEP 4: ClickHouse - Tüm Tabloları DROP Et
# ============================================================
echo ""
echo "=== STEP 4: ClickHouse Tabloları Siliniyor ==="

# ClickHouse şifresini secret'tan al
CLICKHOUSE_PASS=$(oc get secret -n $NS flowfish-secrets -o jsonpath='{.data.clickhouse-password}' 2>/dev/null | base64 -d)

if [ -z "$CLICKHOUSE_PASS" ]; then
  echo "⚠️ UYARI: ClickHouse şifresi alınamadı, varsayılan deneniyor..."
  CLICKHOUSE_PASS="flowfish"
fi

oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.network_flows"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.dns_queries"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.tcp_lifecycle"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.process_events"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.file_operations"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.capability_checks"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.oom_kills"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.bind_events"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.sni_events"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.mount_events"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.workload_metadata"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.communication_edges"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.change_events"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.network_flows_5min_mv" 2>/dev/null || true
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "DROP TABLE IF EXISTS flowfish.dns_queries_hourly_mv" 2>/dev/null || true

echo "ClickHouse tabloları silindi"

# ============================================================
# STEP 5: Redis Cache Temizleme
# ============================================================
echo ""
echo "=== STEP 5: Redis Cache Temizleniyor ==="
oc exec -n $NS redis-0 -- redis-cli FLUSHALL

echo "Redis cache temizlendi"

# ============================================================
# STEP 6: PostgreSQL - CLUSTER VERİLERİNİ YEDEKLE
# ============================================================
echo ""
echo "=== STEP 6: PostgreSQL Cluster Verileri Yedekleniyor ==="

oc exec -n $NS postgresql-0 -- psql -U flowfish -d flowfish -c "SELECT id, name, api_url, status FROM clusters;"
oc exec -n $NS postgresql-0 -- psql -U flowfish -d flowfish -c "COPY clusters TO '/tmp/clusters_backup.csv' WITH CSV HEADER;"

echo "Cluster verileri yedeklendi"

# ============================================================
# STEP 7: PostgreSQL - TÜM TABLOLARI SİL (clusters HARİÇ)
# ============================================================
echo ""
echo "=== STEP 7: PostgreSQL Tüm Tablolar Siliniyor (clusters HARİÇ) ==="

oc exec -n $NS postgresql-0 -- psql -U flowfish -d flowfish -c "
-- Bağımlı tabloları sil
DROP TABLE IF EXISTS analysis_runs CASCADE;
DROP TABLE IF EXISTS analyses CASCADE;
DROP TABLE IF EXISTS workloads CASCADE;
DROP TABLE IF EXISTS communications CASCADE;
DROP TABLE IF EXISTS namespaces CASCADE;
DROP TABLE IF EXISTS notification_hooks CASCADE;
DROP TABLE IF EXISTS baselines CASCADE;
DROP TABLE IF EXISTS risk_scores CASCADE;
DROP TABLE IF EXISTS graph_snapshots CASCADE;
DROP TABLE IF EXISTS import_jobs CASCADE;
DROP TABLE IF EXISTS export_jobs CASCADE;
DROP TABLE IF EXISTS oauth_providers CASCADE;
DROP TABLE IF EXISTS system_settings CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Migration tablosunu sil
DROP TABLE IF EXISTS schema_migrations CASCADE;

-- CLUSTER TABLOSU KORUNUYOR!

SELECT 'PostgreSQL tabloları silindi' as status;
"

echo "PostgreSQL tabloları silindi (clusters KORUNDU)"

# ============================================================
# STEP 8: Doğrulama
# ============================================================
echo ""
echo "============================================================"
echo "=== DOĞRULAMA ==="
echo "============================================================"

echo ""
echo "--- KORUNAN CLUSTER BİLGİLERİ ---"
oc exec -n $NS postgresql-0 -- psql -U flowfish -d flowfish -c "SELECT id, name, api_url, status FROM clusters;"

echo ""
echo "--- PostgreSQL Kalan Tablolar ---"
oc exec -n $NS postgresql-0 -- psql -U flowfish -d flowfish -c "\dt"

echo ""
echo "--- Neo4j Node Sayısı (0 olmalı) ---"
if [ "$NEO4J_PASSWORD" != "your-neo4j-password" ]; then
  oc exec -n $NS neo4j-0 -- wget -q -O - \
    --header="Content-Type: application/json" \
    --http-user=neo4j --http-password="$NEO4J_PASSWORD" \
    --post-data='{"statements":[{"statement":"MATCH (n) RETURN count(n) as node_count"}]}' \
    http://localhost:7474/db/neo4j/tx/commit
  echo ""
fi

echo ""
echo "--- ClickHouse Tablo Listesi (boş olmalı) ---"
oc exec -n $NS clickhouse-0 -- clickhouse-client --user flowfish --password "$CLICKHOUSE_PASS" --query "SHOW TABLES FROM flowfish" 2>/dev/null || echo "(Tablolar silindi)"

echo ""
echo "============================================================"
echo "🎉 TEMİZLİK TAMAMLANDI!"
echo "============================================================"
echo ""
echo "Sonraki adım:"
echo "  → Pipeline'ı çalıştırın"
echo "  → Migration pod'u tabloları oluşturacak"
echo "  → Servisler otomatik başlayacak"
echo ""
echo "Cluster tanımlarınız KORUNDU - yeni analiz başlatabilirsiniz!"
echo ""
