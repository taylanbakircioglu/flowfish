#!/bin/bash
# ==============================================================================
# Version Bump Task - Runs at the start of every build
# ==============================================================================
# Bu task her build'de çalışır ve versiyon bilgilerini günceller.
# Build marker dosyaları sayesinde backend ve frontend her zaman
# "değişmiş" olarak algılanır ve rebuild edilir.
# ==============================================================================

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 VERSION BUMP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd ${BUILD_SOURCESDIRECTORY}

VERSION_FILE="version.json"
BACKEND_VERSION_FILE="backend/__version__.py"

# Read current version
if [ ! -f "$VERSION_FILE" ]; then
    echo "Creating initial version.json..."
    echo '{"version": "1.0.0", "buildNumber": 0}' > "$VERSION_FILE"
fi

# Parse version using grep (jq may not be available)
CURRENT_VERSION=$(grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' "$VERSION_FILE" | head -1 | cut -d'"' -f4)
CURRENT_BUILD=$(grep -o '"buildNumber"[[:space:]]*:[[:space:]]*[0-9]*' "$VERSION_FILE" | head -1 | grep -o '[0-9]*$')

# Handle empty values
CURRENT_VERSION=${CURRENT_VERSION:-"1.0.0"}
CURRENT_BUILD=${CURRENT_BUILD:-0}

# Increment build number
NEW_BUILD=$((CURRENT_BUILD + 1))
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
FULL_VERSION="${CURRENT_VERSION}-build.${NEW_BUILD}"

echo "📌 Current: $CURRENT_VERSION (build $CURRENT_BUILD)"
echo "📌 New: $CURRENT_VERSION (build $NEW_BUILD)"
echo "📌 Full Version: $FULL_VERSION"
echo ""

# Update version.json
cat > "$VERSION_FILE" << EOF
{
  "version": "$CURRENT_VERSION",
  "buildNumber": $NEW_BUILD,
  "fullVersion": "$FULL_VERSION",
  "lastUpdated": "$TIMESTAMP"
}
EOF
echo "✅ Updated version.json"

# Update backend version
mkdir -p backend
cat > "$BACKEND_VERSION_FILE" << EOF
# Auto-generated version file - DO NOT EDIT MANUALLY
# Updated by pipelines/scripts/bump-version.sh

__version__ = "$CURRENT_VERSION"
__build__ = $NEW_BUILD
__full_version__ = "$FULL_VERSION"
__build_timestamp__ = "$TIMESTAMP"
EOF
echo "✅ Updated backend/__version__.py"

# Create build markers - these files change every build
# This ensures detect-changes sees backend and frontend as "changed"
echo "$FULL_VERSION - $TIMESTAMP - ${BUILD_BUILDID:-local}" > "backend/.build-marker"
echo "$FULL_VERSION - $TIMESTAMP - ${BUILD_BUILDID:-local}" > "frontend/.build-marker"
echo "✅ Created build markers"

# Set Azure DevOps variables for use in other tasks
echo "##vso[task.setvariable variable=APP_VERSION]$CURRENT_VERSION"
echo "##vso[task.setvariable variable=BUILD_NUMBER]$NEW_BUILD"
echo "##vso[task.setvariable variable=FULL_VERSION]$FULL_VERSION"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Version Info:"
echo "   APP_VERSION: $CURRENT_VERSION"
echo "   BUILD_NUMBER: $NEW_BUILD"  
echo "   FULL_VERSION: $FULL_VERSION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Version bump complete!"

