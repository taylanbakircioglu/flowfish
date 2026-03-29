#!/bin/bash
# ==============================================================================
# Flowfish Change Detection - Standalone Azure DevOps Task
# ==============================================================================
# Bu script ayrı bir bash task olarak çalışır ve değişkenleri set eder.
# Sonraki task'lar bu değişkenleri kullanabilir.
#
# Kullanım (Azure DevOps Classic Pipeline):
#   Task 1: Bu script'i çalıştır
#   Task 2: Build script (değişkenleri kullanır)
#
# Set edilen Azure DevOps değişkenleri:
#   BACKEND_CHANGED, FRONTEND_CHANGED, SHARED_CHANGED
#   API_GATEWAY_CHANGED, CLUSTER_MANAGER_CHANGED, ANALYSIS_ORCHESTRATOR_CHANGED
#   GRAPH_WRITER_CHANGED, GRAPH_QUERY_CHANGED, TIMESERIES_WRITER_CHANGED
#   INGESTION_SERVICE_CHANGED
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 CHANGE DETECTION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Son başarılı build'in commit hash'ini al
get_last_successful_commit() {
    # OAuth token kontrolü
    if [ -z "$SYSTEM_ACCESSTOKEN" ]; then
        echo ""
        return 0
    fi
    
    # jq yüklü mü kontrol et
    if ! command -v jq &> /dev/null; then
        echo ""
        return 0
    fi
    
    local api_url="${SYSTEM_COLLECTIONURI}${SYSTEM_TEAMPROJECT}/_apis/build/builds?definitions=${SYSTEM_DEFINITIONID}&statusFilter=completed&resultFilter=succeeded&\$top=1&api-version=6.0"
    
    local response=$(curl -s -u ":${SYSTEM_ACCESSTOKEN}" "$api_url" 2>/dev/null)
    
    if [ -z "$response" ]; then
        echo ""
        return 0
    fi
    
    local last_commit=$(echo "$response" | jq -r '.value[0].sourceVersion // empty' 2>/dev/null)
    
    echo "$last_commit"
    return 0
}

# İki commit arasındaki değişen dosyaları al
get_changed_files() {
    local base_commit="$1"
    local current_commit="${BUILD_SOURCEVERSION:-HEAD}"
    
    if [ -z "$base_commit" ]; then
        # İlk build - tüm dosyaları değişmiş kabul et
        git ls-files 2>/dev/null || echo ""
    else
        # Değişen dosyaları al
        git diff --name-only "$base_commit" "$current_commit" 2>/dev/null || git ls-files 2>/dev/null || echo ""
    fi
    return 0
}

# Belirli bir path pattern'ine sahip değişiklik var mı kontrol et
has_changes_in_path() {
    local pattern="$1"
    local changed_files="$2"
    
    local count=$(echo "$changed_files" | grep -E "$pattern" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    
    # Boş string kontrolü
    if [ -z "$count" ]; then
        count=0
    fi
    
    echo "$count"
    return 0
}

# Azure DevOps variable set etme fonksiyonu
# Aynı job içindeki sonraki task'lar bu değişkenlere erişebilir
set_variable() {
    local name="$1"
    local value="$2"
    echo "##vso[task.setvariable variable=$name]$value"
    echo "   $name = $value"
}

# ========================================
# MAIN LOGIC
# ========================================

# Build-all flag kontrolü
if [ "${BUILD_ALL}" = "true" ]; then
    echo "⚠️  BUILD_ALL=true - Tüm servisler derlenecek"
    echo ""
    echo "📋 Setting Azure DevOps Variables:"
    set_variable "BACKEND_CHANGED" "1"
    set_variable "FRONTEND_CHANGED" "1"
    set_variable "SHARED_CHANGED" "1"
    set_variable "API_GATEWAY_CHANGED" "1"
    set_variable "CLUSTER_MANAGER_CHANGED" "1"
    set_variable "ANALYSIS_ORCHESTRATOR_CHANGED" "1"
    set_variable "GRAPH_WRITER_CHANGED" "1"
    set_variable "GRAPH_QUERY_CHANGED" "1"
    set_variable "TIMESERIES_WRITER_CHANGED" "1"
    set_variable "INGESTION_SERVICE_CHANGED" "1"
    echo ""
    echo "✅ Change detection completed!"
    exit 0
fi

# Son başarılı build commit'ini al
last_commit=$(get_last_successful_commit)

if [ -z "$last_commit" ]; then
    echo "⚠️  İlk build veya API erişimi yok - Tüm servisler derlenecek"
    echo ""
    echo "📋 Setting Azure DevOps Variables:"
    set_variable "BACKEND_CHANGED" "1"
    set_variable "FRONTEND_CHANGED" "1"
    set_variable "SHARED_CHANGED" "1"
    set_variable "API_GATEWAY_CHANGED" "1"
    set_variable "CLUSTER_MANAGER_CHANGED" "1"
    set_variable "ANALYSIS_ORCHESTRATOR_CHANGED" "1"
    set_variable "GRAPH_WRITER_CHANGED" "1"
    set_variable "GRAPH_QUERY_CHANGED" "1"
    set_variable "TIMESERIES_WRITER_CHANGED" "1"
    set_variable "INGESTION_SERVICE_CHANGED" "1"
    echo ""
    echo "✅ Change detection completed!"
    exit 0
fi

echo "📌 Son başarılı build: ${last_commit:0:7}"
echo "📌 Mevcut commit: ${BUILD_SOURCEVERSION:0:7}"

# Değişen dosyaları al
changed_files=$(get_changed_files "$last_commit")

total_changes=$(echo "$changed_files" | grep -v '^$' | wc -l | tr -d ' ')
total_changes=${total_changes:-0}

echo "📊 Toplam değişen dosya: $total_changes"
echo ""

# Değişiklikleri hesapla
SHARED_CHANGED=$(has_changes_in_path "^(proto/|shared/)" "$changed_files")
BACKEND_CHANGED=$(has_changes_in_path "^backend/" "$changed_files")
FRONTEND_CHANGED=$(has_changes_in_path "^frontend/" "$changed_files")
API_GATEWAY_CHANGED=$(has_changes_in_path "^services/api-gateway/" "$changed_files")
CLUSTER_MANAGER_CHANGED=$(has_changes_in_path "^services/cluster-manager/" "$changed_files")
ANALYSIS_ORCHESTRATOR_CHANGED=$(has_changes_in_path "^services/analysis-orchestrator/" "$changed_files")
GRAPH_WRITER_CHANGED=$(has_changes_in_path "^services/graph-writer/" "$changed_files")
GRAPH_QUERY_CHANGED=$(has_changes_in_path "^services/graph-query/" "$changed_files")
TIMESERIES_WRITER_CHANGED=$(has_changes_in_path "^services/timeseries-writer/" "$changed_files")
INGESTION_SERVICE_CHANGED=$(has_changes_in_path "^services/ingestion-service/" "$changed_files")

# Varsayılan değer ataması
SHARED_CHANGED=${SHARED_CHANGED:-0}
BACKEND_CHANGED=${BACKEND_CHANGED:-0}
FRONTEND_CHANGED=${FRONTEND_CHANGED:-0}
API_GATEWAY_CHANGED=${API_GATEWAY_CHANGED:-0}
CLUSTER_MANAGER_CHANGED=${CLUSTER_MANAGER_CHANGED:-0}
ANALYSIS_ORCHESTRATOR_CHANGED=${ANALYSIS_ORCHESTRATOR_CHANGED:-0}
GRAPH_WRITER_CHANGED=${GRAPH_WRITER_CHANGED:-0}
GRAPH_QUERY_CHANGED=${GRAPH_QUERY_CHANGED:-0}
TIMESERIES_WRITER_CHANGED=${TIMESERIES_WRITER_CHANGED:-0}
INGESTION_SERVICE_CHANGED=${INGESTION_SERVICE_CHANGED:-0}

# Proto/shared değişikliği varsa tüm microservices'i etkiler
if [ "${SHARED_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Proto/Shared değişikliği - Tüm microservices etkilenecek"
    API_GATEWAY_CHANGED=1
    CLUSTER_MANAGER_CHANGED=1
    ANALYSIS_ORCHESTRATOR_CHANGED=1
    GRAPH_WRITER_CHANGED=1
    GRAPH_QUERY_CHANGED=1
    TIMESERIES_WRITER_CHANGED=1
    INGESTION_SERVICE_CHANGED=1
    # Backend de proto kullanıyor
    BACKEND_CHANGED=1
fi

# Azure DevOps değişkenlerini set et
echo "📋 Setting Azure DevOps Variables:"
set_variable "BACKEND_CHANGED" "$BACKEND_CHANGED"
set_variable "FRONTEND_CHANGED" "$FRONTEND_CHANGED"
set_variable "SHARED_CHANGED" "$SHARED_CHANGED"
set_variable "API_GATEWAY_CHANGED" "$API_GATEWAY_CHANGED"
set_variable "CLUSTER_MANAGER_CHANGED" "$CLUSTER_MANAGER_CHANGED"
set_variable "ANALYSIS_ORCHESTRATOR_CHANGED" "$ANALYSIS_ORCHESTRATOR_CHANGED"
set_variable "GRAPH_WRITER_CHANGED" "$GRAPH_WRITER_CHANGED"
set_variable "GRAPH_QUERY_CHANGED" "$GRAPH_QUERY_CHANGED"
set_variable "TIMESERIES_WRITER_CHANGED" "$TIMESERIES_WRITER_CHANGED"
set_variable "INGESTION_SERVICE_CHANGED" "$INGESTION_SERVICE_CHANGED"

# Özet yazdır
echo ""
echo "┌─────────────────────────────────────────────────┐"
echo "│              DEĞİŞİKLİK ÖZETİ                   │"
echo "├─────────────────────────────────────────────────┤"

print_status() {
    local name="$1"
    local value="${2:-0}"
    if [ "$value" -gt 0 ] 2>/dev/null; then
        printf "│ %-25s ✅ BUILD             │\n" "$name"
    else
        printf "│ %-25s ⏭️  SKIP              │\n" "$name"
    fi
}

print_status "Backend" "$BACKEND_CHANGED"
print_status "Frontend" "$FRONTEND_CHANGED"
print_status "API Gateway" "$API_GATEWAY_CHANGED"
print_status "Cluster Manager" "$CLUSTER_MANAGER_CHANGED"
print_status "Analysis Orchestrator" "$ANALYSIS_ORCHESTRATOR_CHANGED"
print_status "Graph Writer" "$GRAPH_WRITER_CHANGED"
print_status "Graph Query" "$GRAPH_QUERY_CHANGED"
print_status "Timeseries Writer" "$TIMESERIES_WRITER_CHANGED"
print_status "Ingestion Service" "$INGESTION_SERVICE_CHANGED"

echo "└─────────────────────────────────────────────────┘"
echo ""
echo "✅ Change detection completed!"
