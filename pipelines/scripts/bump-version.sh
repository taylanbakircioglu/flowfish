#!/bin/bash
# ==============================================================================
# Automatic Version Bump Script
# ==============================================================================
# Bu script her build'de çalışır ve:
# 1. version.json'daki buildNumber'ı artırır
# 2. Backend ve Frontend'deki versiyon bilgilerini günceller
# 3. Değişiklikleri commit eder (opsiyonel)
#
# Kullanım:
#   ./bump-version.sh [--commit]
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

VERSION_FILE="$ROOT_DIR/version.json"
BACKEND_VERSION_FILE="$ROOT_DIR/backend/__version__.py"
FRONTEND_PACKAGE="$ROOT_DIR/frontend/package.json"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 AUTOMATIC VERSION BUMP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Read current version
if [ ! -f "$VERSION_FILE" ]; then
    echo "Creating initial version.json..."
    echo '{"version": "1.0.0", "buildNumber": 0}' > "$VERSION_FILE"
fi

# Parse version.json
CURRENT_VERSION=$(cat "$VERSION_FILE" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
CURRENT_BUILD=$(cat "$VERSION_FILE" | grep -o '"buildNumber"[[:space:]]*:[[:space:]]*[0-9]*' | grep -o '[0-9]*$')

# Increment build number
NEW_BUILD=$((CURRENT_BUILD + 1))
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Full version string
FULL_VERSION="${CURRENT_VERSION}-build.${NEW_BUILD}"

echo "📌 Current Version: $CURRENT_VERSION (build $CURRENT_BUILD)"
echo "📌 New Version: $CURRENT_VERSION (build $NEW_BUILD)"
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
mkdir -p "$(dirname "$BACKEND_VERSION_FILE")"
cat > "$BACKEND_VERSION_FILE" << EOF
# Auto-generated version file - DO NOT EDIT MANUALLY
# Updated by pipelines/scripts/bump-version.sh

__version__ = "$CURRENT_VERSION"
__build__ = $NEW_BUILD
__full_version__ = "$FULL_VERSION"
__build_timestamp__ = "$TIMESTAMP"
EOF
echo "✅ Updated backend/__version__.py"

# Update frontend package.json version
if [ -f "$FRONTEND_PACKAGE" ]; then
    # Use sed to update version in package.json
    sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$CURRENT_VERSION\"/" "$FRONTEND_PACKAGE"
    echo "✅ Updated frontend/package.json"
fi

# Create a build marker file that changes every build
# This ensures the service is always rebuilt
BACKEND_BUILD_MARKER="$ROOT_DIR/backend/.build-marker"
FRONTEND_BUILD_MARKER="$ROOT_DIR/frontend/.build-marker"

echo "$FULL_VERSION - $TIMESTAMP" > "$BACKEND_BUILD_MARKER"
echo "$FULL_VERSION - $TIMESTAMP" > "$FRONTEND_BUILD_MARKER"
echo "✅ Created build markers"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Version Summary:"
echo "   Version: $CURRENT_VERSION"
echo "   Build: $NEW_BUILD"
echo "   Full: $FULL_VERSION"
echo "   Timestamp: $TIMESTAMP"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Optionally commit changes
if [ "$1" = "--commit" ]; then
    echo ""
    echo "📝 Committing version changes..."
    cd "$ROOT_DIR"
    git add version.json backend/__version__.py frontend/package.json backend/.build-marker frontend/.build-marker 2>/dev/null || true
    git commit -m "chore: Auto-bump version to $FULL_VERSION [skip ci]" 2>/dev/null || echo "No changes to commit"
fi

echo ""
echo "✅ Version bump complete!"

