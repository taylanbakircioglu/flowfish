#!/bin/bash
# ==============================================================================
# Flowfish Change Detection - Classic Build Pipeline Task
# ==============================================================================
# Bu script ayrı bir agent job olarak çalışır ve hangi servislerin
# değiştiğini tespit eder. Sonraki build job'ları bu değişkenleri kullanır.
#
# Azure DevOps Classic Pipeline Yapısı:
#   Job 1: DetectChanges (bu script)
#   Job 2: BuildBackend (depends on DetectChanges)
#   Job 3: BuildFrontend (depends on DetectChanges)
#   Job 4: BuildMicroservices (depends on DetectChanges)
#   Job 5: Cleanup (depends on Build jobs)
#
# Output Variables (isOutput=true):
#   BACKEND_CHANGED, FRONTEND_CHANGED, SHARED_CHANGED
#   API_GATEWAY_CHANGED, CLUSTER_MANAGER_CHANGED, ANALYSIS_ORCHESTRATOR_CHANGED
#   GRAPH_WRITER_CHANGED, GRAPH_QUERY_CHANGED, TIMESERIES_WRITER_CHANGED
#   TIMESERIES_QUERY_CHANGED, INGESTION_SERVICE_CHANGED, CHANGE_WORKER_CHANGED
#
# Diğer job'lardan erişim:
#   $(DetectChanges.DetectChanges.BACKEND_CHANGED)
#   Format: $(JobName.TaskReferenceName.VARIABLE_NAME)
# ==============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 CHANGE DETECTION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ${BUILD_SOURCESDIRECTORY}

# ==============================================================================
# Git config cleanup - Azure DevOps checkout extraheader warning'i önlemek için
# ==============================================================================
echo "🧹 Git config temizleniyor..."
git config --unset-all http.extraheader 2>/dev/null || true
git config --unset-all http.https://dev.azure.com.extraheader 2>/dev/null || true
echo "   ✅ Git config temizlendi"
echo ""

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
        git ls-files 2>/dev/null || echo ""
    else
        git diff --name-only "$base_commit" "$current_commit" 2>/dev/null || git ls-files 2>/dev/null || echo ""
    fi
    return 0
}

# Belirli bir path pattern'ine sahip değişiklik var mı kontrol et
has_changes_in_path() {
    local pattern="$1"
    local changed_files="$2"
    
    local count=$(echo "$changed_files" | grep -E "$pattern" 2>/dev/null | wc -l | tr -d ' ' || echo "0")
    
    if [ -z "$count" ]; then
        count=0
    fi
    
    echo "$count"
    return 0
}

# Azure DevOps variable set etme fonksiyonu
# isOutput=true → diğer JOB'lardan erişim: $(JobName.TaskRefName.VAR)
# isOutput olmadan → aynı job içindeki sonraki task'lar ${VAR} ile erişebilir
set_variable() {
    local name="$1"
    local value="$2"
    echo "##vso[task.setvariable variable=$name;isOutput=true]$value"
    echo "##vso[task.setvariable variable=$name]$value"
    echo "   $name = $value"
}

# ========================================
# MAIN LOGIC
# ========================================

# Build-all flag kontrolü (pipeline variable: BUILD_ALL=true)
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
    set_variable "TIMESERIES_QUERY_CHANGED" "1"
    set_variable "INGESTION_SERVICE_CHANGED" "1"
    set_variable "CHANGE_WORKER_CHANGED" "1"
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
    set_variable "TIMESERIES_QUERY_CHANGED" "1"
    set_variable "INGESTION_SERVICE_CHANGED" "1"
    set_variable "CHANGE_WORKER_CHANGED" "1"
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

# DEBUG: Değişen frontend dosyalarını göster
frontend_files=$(echo "$changed_files" | grep -E "^frontend/" || echo "")
frontend_count=$(echo "$frontend_files" | grep -v '^$' | wc -l | tr -d ' ')
echo "🔍 DEBUG - Frontend değişen dosya sayısı: $frontend_count"
if [ -n "$frontend_files" ]; then
    echo "🔍 DEBUG - Frontend değişen dosyalar:"
    echo "$frontend_files" | head -10
fi
echo ""

# Değişiklikleri hesapla
SHARED_CHANGED=$(has_changes_in_path "^(proto/|shared/)" "$changed_files")
BACKEND_CHANGED=$(has_changes_in_path "^backend/" "$changed_files")
FRONTEND_CHANGED=$(has_changes_in_path "^frontend/" "$changed_files")

# Build marker değişiklikleri - her zaman rebuild tetikler
BUILD_MARKER_BACKEND=$(has_changes_in_path "^backend/\.build-marker" "$changed_files")
BUILD_MARKER_FRONTEND=$(has_changes_in_path "^frontend/\.build-marker" "$changed_files")

if [ "${BUILD_MARKER_BACKEND:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Backend build marker değişti - Backend rebuild gerekli"
    BACKEND_CHANGED=1
fi

if [ "${BUILD_MARKER_FRONTEND:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Frontend build marker değişti - Frontend rebuild gerekli"
    FRONTEND_CHANGED=1
fi

# Pipeline script değişiklikleri de ilgili servisleri etkiler
PIPELINE_FRONTEND_CHANGED=$(has_changes_in_path "^pipelines/.*(frontend|build-frontend)" "$changed_files")
if [ "${PIPELINE_FRONTEND_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Pipeline script değişikliği - Frontend rebuild gerekli"
    FRONTEND_CHANGED=1
fi

PIPELINE_BACKEND_CHANGED=$(has_changes_in_path "^pipelines/.*(backend|build-backend)" "$changed_files")
if [ "${PIPELINE_BACKEND_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Pipeline script değişikliği - Backend rebuild gerekli"
    BACKEND_CHANGED=1
fi

# version.json değişikliği - tüm ana servisleri etkiler
VERSION_CHANGED=$(has_changes_in_path "^version\.json" "$changed_files")
if [ "${VERSION_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  version.json değişti - Backend ve Frontend rebuild gerekli"
    BACKEND_CHANGED=1
    FRONTEND_CHANGED=1
fi

# Eğer has_changes_in_path çalışmadıysa, frontend_count ile kontrol et
if [ "${FRONTEND_CHANGED:-0}" -eq 0 ] && [ "${frontend_count:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Frontend değişikliği tespit edildi (fallback) - Frontend rebuild gerekli"
    FRONTEND_CHANGED=$frontend_count
fi
API_GATEWAY_CHANGED=$(has_changes_in_path "^services/api-gateway/" "$changed_files")
CLUSTER_MANAGER_CHANGED=$(has_changes_in_path "^services/cluster-manager/" "$changed_files")
ANALYSIS_ORCHESTRATOR_CHANGED=$(has_changes_in_path "^services/analysis-orchestrator/" "$changed_files")
GRAPH_WRITER_CHANGED=$(has_changes_in_path "^services/graph-writer/" "$changed_files")
GRAPH_QUERY_CHANGED=$(has_changes_in_path "^services/graph-query/" "$changed_files")
TIMESERIES_WRITER_CHANGED=$(has_changes_in_path "^services/timeseries-writer/" "$changed_files")
TIMESERIES_QUERY_CHANGED=$(has_changes_in_path "^services/timeseries-query/" "$changed_files")
INGESTION_SERVICE_CHANGED=$(has_changes_in_path "^services/ingestion-service/" "$changed_files")

# Change Detection Worker - backend içinde ama ayrı servis olarak deploy ediliyor
# Worker uses: worker_main, change_detection module, gRPC clients, connection managers, DB layer
CHANGE_WORKER_CHANGED=$(has_changes_in_path "^backend/(worker_main\.py|Dockerfile\.worker|workers/|services/change_detection/|services/change_detection_service\.py|services/change_event_publisher\.py|services/cluster_connection_manager\.py|services/connections/|grpc_clients/|database/|\.build-marker)" "$changed_files")

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
TIMESERIES_QUERY_CHANGED=${TIMESERIES_QUERY_CHANGED:-0}
INGESTION_SERVICE_CHANGED=${INGESTION_SERVICE_CHANGED:-0}
CHANGE_WORKER_CHANGED=${CHANGE_WORKER_CHANGED:-0}

# Backend değişikliği varsa Change Worker da etkilenir (aynı codebase)
if [ "${BACKEND_CHANGED:-0}" -gt 0 ] 2>/dev/null && [ "${CHANGE_WORKER_CHANGED:-0}" -eq 0 ] 2>/dev/null; then
    echo "⚠️  Backend değişikliği - Change Worker da rebuild edilecek"
    CHANGE_WORKER_CHANGED=1
fi

# Proto/shared değişikliği varsa tüm microservices'i etkiler
if [ "${SHARED_CHANGED:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠️  Proto/Shared değişikliği - Tüm microservices etkilenecek"
    API_GATEWAY_CHANGED=1
    CLUSTER_MANAGER_CHANGED=1
    ANALYSIS_ORCHESTRATOR_CHANGED=1
    GRAPH_WRITER_CHANGED=1
    GRAPH_QUERY_CHANGED=1
    TIMESERIES_WRITER_CHANGED=1
    TIMESERIES_QUERY_CHANGED=1
    INGESTION_SERVICE_CHANGED=1
    CHANGE_WORKER_CHANGED=1
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
set_variable "TIMESERIES_QUERY_CHANGED" "$TIMESERIES_QUERY_CHANGED"
set_variable "INGESTION_SERVICE_CHANGED" "$INGESTION_SERVICE_CHANGED"
set_variable "CHANGE_WORKER_CHANGED" "$CHANGE_WORKER_CHANGED"

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
print_status "Timeseries Query" "$TIMESERIES_QUERY_CHANGED"
print_status "Ingestion Service" "$INGESTION_SERVICE_CHANGED"
print_status "Change Worker" "$CHANGE_WORKER_CHANGED"

echo "└─────────────────────────────────────────────────┘"
echo ""
echo "✅ Change detection completed!"

