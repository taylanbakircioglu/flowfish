#!/bin/bash
set -e

# Get Credentials from External Gateway API
# Fetches service account password from credential management system

echo "Fetching credentials from gateway API..."

RESPONSE=$(curl -s -w "\n%{http_code}" --location --request GET "${VAULT_GATEWAY_URL}/api/TFSUsers" \
  --header "Authorization: Basic ${VAULT_TOKEN}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 200 ]; then
    echo "ERROR: Gateway API returned HTTP $HTTP_CODE"
    echo "Response body: $BODY"
    echo "Possible causes: expired VAULT_TOKEN, incorrect VAULT_GATEWAY_URL, or service unavailable"
    exit 1
fi

if ! echo "$BODY" | jq empty 2>/dev/null; then
    echo "ERROR: Gateway API returned invalid JSON"
    echo "Response body (first 500 chars): $(echo "$BODY" | head -c 500)"
    exit 1
fi

servicePassword=$(echo "$BODY" | jq -r '
  if type == "array" then
    (.[] | if type == "object" then .tfsservice else empty end)
  elif type == "object" then
    .tfsservice
  else
    empty
  end
')

if [ -z "$servicePassword" ] || [ "$servicePassword" = "null" ]; then
    echo "ERROR: Could not extract tfsservice from response"
    echo "Response structure: $(echo "$BODY" | jq 'type, if type == "array" then (.[0] | type) else empty end')"
    exit 1
fi

echo "Credentials retrieved successfully"
echo "##vso[task.setvariable variable=User;isOutput=true]${OPENSHIFT_USER}"
echo "##vso[task.setvariable variable=Password;isOutput=true;issecret=true]$servicePassword"
