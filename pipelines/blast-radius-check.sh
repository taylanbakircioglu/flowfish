#!/bin/bash
#
# Flowfish Blast Radius Check Script
# Add this to your release pipeline before deployment
#
# Required Environment Variables:
#   FLOWFISH_URL      - Flowfish API URL (e.g., https://flowfish.example.com)
#   FLOWFISH_API_KEY  - API Key (fk_xxx...)
#   CLUSTER_ID        - Target cluster ID
#   NAMESPACE         - Namespace being deployed
#
# Optional:
#   BLOCK_ON_CRITICAL - Set to "true" to fail pipeline on critical risk (default: false)
#

set -e

# Colors for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Validate required variables
if [ -z "$FLOWFISH_URL" ]; then
    echo -e "${RED}ERROR: FLOWFISH_URL is not set${NC}"
    exit 1
fi

if [ -z "$FLOWFISH_API_KEY" ]; then
    echo -e "${RED}ERROR: FLOWFISH_API_KEY is not set${NC}"
    exit 1
fi

if [ -z "$CLUSTER_ID" ]; then
    echo -e "${RED}ERROR: CLUSTER_ID is not set${NC}"
    exit 1
fi

if [ -z "$NAMESPACE" ]; then
    echo -e "${RED}ERROR: NAMESPACE is not set${NC}"
    exit 1
fi

BLOCK_ON_CRITICAL="${BLOCK_ON_CRITICAL:-false}"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}🐟 FLOWFISH BLAST RADIUS ASSESSMENT${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Call Flowfish API
echo -e "${BLUE}📡 Analyzing namespace: ${BOLD}$NAMESPACE${NC}"
echo ""

RESPONSE=$(curl -s -X POST "${FLOWFISH_URL}/api/v1/blast-radius/namespace" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: ${FLOWFISH_API_KEY}" \
    -d "{\"cluster_id\": ${CLUSTER_ID}, \"namespace\": \"${NAMESPACE}\"}" 2>&1)

# Check if curl failed
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Failed to connect to Flowfish API${NC}"
    echo "$RESPONSE"
    exit 1
fi

# Check for error in response
if echo "$RESPONSE" | grep -q '"detail"'; then
    ERROR=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail','Unknown error'))" 2>/dev/null || echo "$RESPONSE")
    echo -e "${RED}ERROR: $ERROR${NC}"
    exit 1
fi

# Parse response
RISK_SCORE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['risk_score'])" 2>/dev/null)
RISK_LEVEL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['risk_level'])" 2>/dev/null)
SERVICE_COUNT=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['service_count'])" 2>/dev/null)
INTERNAL_DEPS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['internal_dependencies'])" 2>/dev/null)
EXTERNAL_DEPS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['external_dependencies'])" 2>/dev/null)
TOTAL_DEPS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_dependencies'])" 2>/dev/null)
RECOMMENDATION=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['recommendation'])" 2>/dev/null)
ASSESSMENT_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['assessment_id'])" 2>/dev/null)

# Determine risk indicator
case "$RISK_LEVEL" in
    "low")
        RISK_ICON="✅"
        RISK_COLOR=$GREEN
        RISK_BAR="▓▓▓░░░░░░░"
        ;;
    "medium")
        RISK_ICON="⚠️"
        RISK_COLOR=$YELLOW
        RISK_BAR="▓▓▓▓▓░░░░░"
        ;;
    "high")
        RISK_ICON="🔶"
        RISK_COLOR=$YELLOW
        RISK_BAR="▓▓▓▓▓▓▓░░░"
        ;;
    "critical")
        RISK_ICON="🔴"
        RISK_COLOR=$RED
        RISK_BAR="▓▓▓▓▓▓▓▓▓▓"
        ;;
    *)
        RISK_ICON="❓"
        RISK_COLOR=$NC
        RISK_BAR="░░░░░░░░░░"
        ;;
esac

# Display results
echo -e "${BOLD}📊 ASSESSMENT RESULTS${NC}"
echo ""
echo -e "   Namespace:     ${BOLD}$NAMESPACE${NC}"
echo -e "   Cluster ID:    $CLUSTER_ID"
echo -e "   Assessment:    $ASSESSMENT_ID"
echo ""
echo -e "   ┌──────────────────────────────────────────┐"
echo -e "   │  Risk Score:  ${RISK_COLOR}${BOLD}$RISK_SCORE / 100${NC}  $RISK_ICON"
echo -e "   │  Risk Level:  ${RISK_COLOR}${BOLD}$(echo $RISK_LEVEL | tr '[:lower:]' '[:upper:]')${NC}"
echo -e "   │              [${RISK_COLOR}${RISK_BAR}${NC}]"
echo -e "   └──────────────────────────────────────────┘"
echo ""
echo -e "   📦 Services:           $SERVICE_COUNT"
echo -e "   🔗 Internal Deps:      $INTERNAL_DEPS"
echo -e "   🌐 External Deps:      $EXTERNAL_DEPS"
echo -e "   📊 Total Dependencies: $TOTAL_DEPS"
echo ""

# Show services
echo -e "${BOLD}📦 SERVICES IN NAMESPACE${NC}"
SERVICES=$(echo "$RESPONSE" | python3 -c "import sys,json; print(', '.join(json.load(sys.stdin)['services']))" 2>/dev/null)
echo -e "   ${CYAN}$SERVICES${NC}"
echo ""

# Show external dependencies if any
if [ "$EXTERNAL_DEPS" -gt 0 ]; then
    echo -e "${BOLD}🌐 EXTERNAL DEPENDENCIES${NC}"
    echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for svc, deps in data.get('external_dependency_map', {}).items():
    for dep in deps:
        print(f'   {svc} → {dep}')
" 2>/dev/null
    echo ""
fi

# Show recommendation
echo -e "${BOLD}💡 RECOMMENDATION${NC}"
case "$RECOMMENDATION" in
    "proceed")
        echo -e "   ${GREEN}✅ Safe to proceed with standard deployment${NC}"
        ;;
    "review_required")
        echo -e "   ${YELLOW}⚠️ Review recommended before deployment${NC}"
        ;;
    "delay_suggested")
        echo -e "   ${RED}🔴 Consider delaying or scheduling for low-traffic window${NC}"
        ;;
esac
echo ""

# Show suggested actions
echo -e "${BOLD}📋 SUGGESTED ACTIONS${NC}"
echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
icons = {'critical': '🔴', 'high': '🔶', 'medium': '⚠️', 'low': '✅'}
for action in data.get('suggested_actions', []):
    icon = icons.get(action['priority'], '•')
    print(f\"   {icon} {action['action']}\")
" 2>/dev/null
echo ""

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Export variables for Azure DevOps
if [ -n "$BUILD_BUILDID" ] || [ -n "$SYSTEM_TEAMPROJECT" ]; then
    echo "##vso[task.setvariable variable=BLAST_RADIUS_SCORE]$RISK_SCORE"
    echo "##vso[task.setvariable variable=BLAST_RADIUS_LEVEL]$RISK_LEVEL"
    echo "##vso[task.setvariable variable=BLAST_RADIUS_SERVICES]$SERVICE_COUNT"
    
    if [ "$RISK_LEVEL" = "critical" ]; then
        echo "##vso[task.logissue type=warning]Blast Radius: CRITICAL risk detected (Score: $RISK_SCORE)"
    elif [ "$RISK_LEVEL" = "high" ]; then
        echo "##vso[task.logissue type=warning]Blast Radius: HIGH risk detected (Score: $RISK_SCORE)"
    fi
fi

# Block on critical if configured
if [ "$BLOCK_ON_CRITICAL" = "true" ] && [ "$RISK_LEVEL" = "critical" ]; then
    echo ""
    echo -e "${RED}${BOLD}❌ PIPELINE BLOCKED: Critical risk level detected${NC}"
    echo -e "${RED}   Set BLOCK_ON_CRITICAL=false to bypass this check${NC}"
    echo ""
    exit 1
fi

# Exit with appropriate code
case "$RISK_LEVEL" in
    "low"|"medium")
        exit 0
        ;;
    "high")
        # Warning but don't fail
        exit 0
        ;;
    "critical")
        # Don't fail by default, just warn
        exit 0
        ;;
esac
