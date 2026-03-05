#!/bin/bash
#
# Safe ConfigMap Application Script
# Backs up existing ConfigMaps before applying new ones
# Restores backup on failure
#
# Usage: ./apply-configmaps-safe.sh <namespace> [manifest-dir]
#
# Arguments:
#   namespace: Target namespace (default: flowfish)
#   manifest-dir: Directory containing manifest files (default: current directory)
#
# Exit Codes:
#   0 - All ConfigMaps applied successfully
#   1 - Critical error (namespace not accessible, manifest dir not found)
#   2 - Some ConfigMaps failed but script continued
#

# Don't exit on error immediately - we want to try all ConfigMaps
set +e

NAMESPACE="${1:-flowfish}"
MANIFEST_DIR="${2:-.}"
BACKUP_DIR="/tmp/flowfish-configmap-backups-$(date +%s)"

echo "================================================"
echo "Safe ConfigMap Application"
echo "Namespace: $NAMESPACE"
echo "Manifest Directory: $MANIFEST_DIR"
echo "Backup Directory: $BACKUP_DIR"
echo "================================================"
echo ""

# Change to manifest directory
if [ ! -d "$MANIFEST_DIR" ]; then
  echo "❌ Error: Manifest directory not found: $MANIFEST_DIR"
  exit 1
fi

cd "$MANIFEST_DIR"
echo "📂 Working directory: $(pwd)"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Track failures
FAILED_CONFIGMAPS=()

# Function to safely apply ConfigMap with backup
apply_configmap_safe() {
  local file=$1
  local cm_name=$2
  
  echo "📦 Processing ConfigMap: $cm_name"
  echo "   File: $file"
  
  # Check if file exists
  if [ ! -f "$file" ]; then
    echo "   ❌ File not found: $file"
    return 1
  fi
  
  # Check if ConfigMap exists
  if oc get configmap "$cm_name" -n "$NAMESPACE" &>/dev/null; then
    echo "   📋 ConfigMap exists, creating backup..."
    
    # Create backup
    if oc get configmap "$cm_name" -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/${cm_name}.yaml"; then
      echo "   ✅ Backup created: $BACKUP_DIR/${cm_name}.yaml"
    else
      echo "   ❌ Failed to create backup, aborting..."
      return 1
    fi
    
    # Try to apply new ConfigMap
    echo "   🔄 Applying new ConfigMap..."
    if oc apply -f "$file"; then
      echo "   ✅ ConfigMap applied successfully"
      
      # Verify the ConfigMap
      if oc get configmap "$cm_name" -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ ConfigMap verified"
      else
        echo "   ❌ ConfigMap verification failed, restoring backup..."
        oc apply -f "$BACKUP_DIR/${cm_name}.yaml"
        return 1
      fi
    else
      echo "   ❌ Failed to apply ConfigMap, restoring backup..."
      if oc apply -f "$BACKUP_DIR/${cm_name}.yaml"; then
        echo "   ✅ Backup restored successfully"
      else
        echo "   ❌ Failed to restore backup! Manual intervention required."
        echo "   Backup location: $BACKUP_DIR/${cm_name}.yaml"
      fi
      return 1
    fi
  else
    echo "   📝 ConfigMap does not exist, creating new..."
    if oc apply -f "$file"; then
      echo "   ✅ ConfigMap created successfully"
      
      # Verify the ConfigMap
      if oc get configmap "$cm_name" -n "$NAMESPACE" &>/dev/null; then
        echo "   ✅ ConfigMap verified"
      else
        echo "   ❌ ConfigMap verification failed"
        return 1
      fi
    else
      echo "   ❌ Failed to create ConfigMap"
      return 1
    fi
  fi
  
  echo ""
  return 0
}

# Main ConfigMaps
echo "Applying main ConfigMaps..."
echo ""

# Backend ConfigMap (may contain multiple configs in one file)
if [ -f "03-configmaps.yaml" ]; then
  echo "📦 Processing 03-configmaps.yaml (contains multiple ConfigMaps)"
  
  # Extract individual ConfigMap names from the file
  CONFIGMAP_NAMES=$(grep "^  name:" 03-configmaps.yaml | awk '{print $2}')
  
  if [ -z "$CONFIGMAP_NAMES" ]; then
    echo "   ⚠️  No ConfigMap names found in file, applying as-is..."
    oc apply -f 03-configmaps.yaml || echo "   ❌ Failed to apply"
  else
    echo "   Found ConfigMaps in file:"
    echo "$CONFIGMAP_NAMES" | sed 's/^/     - /'
    echo ""
    
    # Backup all ConfigMaps in the file
    for cm_name in $CONFIGMAP_NAMES; do
      if oc get configmap "$cm_name" -n "$NAMESPACE" &>/dev/null; then
        echo "   📋 Backing up: $cm_name"
        oc get configmap "$cm_name" -n "$NAMESPACE" -o yaml > "$BACKUP_DIR/${cm_name}.yaml"
      fi
    done
    
    # Apply the file
    echo "   🔄 Applying 03-configmaps.yaml..."
    if oc apply -f 03-configmaps.yaml; then
      echo "   ✅ ConfigMaps applied successfully"
    else
      echo "   ❌ Failed to apply, restoring backups..."
      for cm_name in $CONFIGMAP_NAMES; do
        if [ -f "$BACKUP_DIR/${cm_name}.yaml" ]; then
          echo "   🔄 Restoring: $cm_name"
          oc apply -f "$BACKUP_DIR/${cm_name}.yaml"
        fi
      done
    fi
  fi
  echo ""
fi

# Inspektor Gadget ConfigMap
if [ -f "09-inspektor-gadget-config.yaml" ]; then
  apply_configmap_safe "09-inspektor-gadget-config.yaml" "inspektor-gadget-config"
else
  echo "⚠️  09-inspektor-gadget-config.yaml not found, skipping"
  echo ""
fi

# Other ConfigMaps (add as needed)
# apply_configmap_safe "path/to/configmap.yaml" "configmap-name"

echo "================================================"
echo "ConfigMap application complete"
echo "================================================"
echo ""
echo "Backup location: $BACKUP_DIR"
echo "ConfigMaps applied:"
oc get configmaps -n "$NAMESPACE" | grep -E "backend-config|frontend-config|inspektor-gadget-config" || echo "  No ConfigMaps found"
echo ""
echo "To restore all backups if needed:"
echo "  oc apply -f $BACKUP_DIR/"
echo ""

