#!/bin/bash
set -e

echo "================================================"
echo "Fetching OpenShift Credentials from Vault"
echo "================================================"

if [ -z "$VAULT_GATEWAY_URL" ] || [ -z "$VAULT_TOKEN" ]; then
  echo "ERROR: Vault credentials not set"
  echo "Required variables: VAULT_GATEWAY_URL, VAULT_TOKEN"
  exit 1
fi

if [ -z "$OPENSHIFT_USER" ]; then
  echo "ERROR: OPENSHIFT_USER not set"
  echo "Required variable: OPENSHIFT_USER (from variable group)"
  exit 1
fi

echo "Vault Gateway URL: $VAULT_GATEWAY_URL"
echo "OpenShift User: $OPENSHIFT_USER"

# Fetch OpenShift user password from Vault
echo "Fetching OpenShift password from Vault..."
VAULT_RESPONSE=$(curl -s -w "\n%{http_code}" --location --request GET "${VAULT_GATEWAY_URL}/api/TFSUsers" \
  --header "Authorization: Basic ${VAULT_TOKEN}")

HTTP_CODE=$(echo "$VAULT_RESPONSE" | tail -n1)
BODY=$(echo "$VAULT_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ne 200 ]; then
  echo "ERROR: Vault gateway returned HTTP $HTTP_CODE"
  echo "Response: $BODY"
  echo "Check if VAULT_TOKEN is expired in the FlowfishVaultENV variable group"
  exit 1
fi

if ! echo "$BODY" | jq empty 2>/dev/null; then
  echo "ERROR: Vault gateway returned invalid JSON"
  echo "Response (first 500 chars): $(echo "$BODY" | head -c 500)"
  exit 1
fi

echo "Vault response type: $(echo "$BODY" | jq -r 'type')"

OPENSHIFT_PASSWORD=$(echo "$BODY" | jq -r '
  if type == "array" then
    (.[] | if type == "object" then .tfsservice else empty end)
  elif type == "object" then
    .tfsservice
  else
    empty
  end
')

if [ -z "$OPENSHIFT_PASSWORD" ] || [ "$OPENSHIFT_PASSWORD" = "null" ]; then
  echo "ERROR: Could not extract tfsservice from Vault response"
  echo "Response structure: $(echo "$BODY" | jq 'if type == "array" then map(type) else type end')"
  exit 1
fi

echo "OpenShift password retrieved successfully"

# Export OpenShift credentials as pipeline variables for deployment tasks
echo "##vso[task.setvariable variable=OPENSHIFT_USER;issecret=false]${OPENSHIFT_USER}"
echo "##vso[task.setvariable variable=OPENSHIFT_PASSWORD;issecret=true]$OPENSHIFT_PASSWORD"

echo ""
echo "================================================"
echo "Credentials ready for OpenShift deployment"
echo "================================================"
echo "OpenShift User: $OPENSHIFT_USER"
echo "OpenShift Password:  (fetched from Vault)"
echo "================================================"
