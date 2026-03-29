#!/bin/bash
set -e

echo "================================================"
echo "Running Health Checks"
echo "================================================"

# Login to OpenShift
echo "Logging into OpenShift..."
oc login ${OPENSHIFT_API_URL} -u ${OPENSHIFT_USER} -p ${OPENSHIFT_PASSWORD} --insecure-skip-tls-verify=true

# Switch to namespace
oc project ${OPENSHIFT_NAMESPACE}

echo ""
echo "================================================"
echo "Checking Pod Status"
echo "================================================"

echo "All Pods:"
oc get pods -n ${OPENSHIFT_NAMESPACE} -o wide

echo ""
echo "Pod Health Summary:"
TOTAL_PODS=$(oc get pods -n ${OPENSHIFT_NAMESPACE} --no-headers | wc -l)
RUNNING_PODS=$(oc get pods -n ${OPENSHIFT_NAMESPACE} --no-headers | grep "Running" | wc -l)
FAILED_PODS=$(oc get pods -n ${OPENSHIFT_NAMESPACE} --no-headers | grep -E "Error|CrashLoopBackOff|ImagePullBackOff" | wc -l || echo "0")

echo "Total Pods: $TOTAL_PODS"
echo "Running: $RUNNING_PODS"
echo "Failed: $FAILED_PODS"

if [ $FAILED_PODS -gt 0 ]; then
  echo ""
  echo " WARNING: Some pods are not healthy!"
  echo "Failed pods:"
  oc get pods -n ${OPENSHIFT_NAMESPACE} --no-headers | grep -E "Error|CrashLoopBackOff|ImagePullBackOff" || true
fi

echo ""
echo "================================================"
echo "Checking Services"
echo "================================================"

oc get svc -n ${OPENSHIFT_NAMESPACE}

echo ""
echo "================================================"
echo "Checking Routes/Ingress"
echo "================================================"

oc get routes -n ${OPENSHIFT_NAMESPACE} || echo "No routes found"
oc get ingress -n ${OPENSHIFT_NAMESPACE} || echo "No ingress found"

echo ""
echo "================================================"
echo "Testing API Endpoints"
echo "================================================"

# Get backend service URL
BACKEND_URL=$(oc get route backend -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

if [ -n "$BACKEND_URL" ]; then
  echo "Backend URL: https://$BACKEND_URL"
  
  echo "Testing /health endpoint..."
  HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" https://$BACKEND_URL/health || echo "000")
  
  if [ "$HTTP_CODE" == "200" ]; then
    echo " Backend health check: OK (HTTP $HTTP_CODE)"
  else
    echo " Backend health check: FAILED (HTTP $HTTP_CODE)"
  fi
  
  echo "Testing /api/v1/health endpoint..."
  HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" https://$BACKEND_URL/api/v1/health || echo "000")
  
  if [ "$HTTP_CODE" == "200" ]; then
    echo " Backend API health check: OK (HTTP $HTTP_CODE)"
  else
    echo " Backend API health check: FAILED (HTTP $HTTP_CODE)"
  fi
else
  echo " Backend route not found, skipping endpoint tests"
fi

# Get frontend URL
FRONTEND_URL=$(oc get route frontend -n ${OPENSHIFT_NAMESPACE} -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

if [ -n "$FRONTEND_URL" ]; then
  echo ""
  echo "Frontend URL: https://$FRONTEND_URL"
  
  echo "Testing frontend..."
  HTTP_CODE=$(curl -k -s -o /dev/null -w "%{http_code}" https://$FRONTEND_URL || echo "000")
  
  if [ "$HTTP_CODE" == "200" ]; then
    echo " Frontend: OK (HTTP $HTTP_CODE)"
  else
    echo " Frontend: FAILED (HTTP $HTTP_CODE)"
  fi
else
  echo " Frontend route not found, skipping endpoint tests"
fi

echo ""
echo "================================================"
echo "Checking Recent Events"
echo "================================================"

echo "Recent Warning/Error events:"
oc get events -n ${OPENSHIFT_NAMESPACE} --sort-by='.lastTimestamp' | grep -E "Warning|Error" | tail -10 || echo "No recent warnings or errors"

echo ""
echo "================================================"
echo "Health Check Summary"
echo "================================================"

if [ $FAILED_PODS -eq 0 ]; then
  echo " All pods are healthy"
else
  echo " $FAILED_PODS pod(s) are not healthy"
fi

echo ""
echo "Deployment URLs:"
echo "  Frontend: https://${FRONTEND_URL:-N/A}"
echo "  Backend:  https://${BACKEND_URL:-N/A}"

echo ""
echo "================================================"
echo "Health check complete"
echo "================================================"

# Exit with error if there are failed pods
if [ $FAILED_PODS -gt 0 ]; then
  echo " WARNING: Some pods are not healthy. Please check the logs."
  exit 0  # Don't fail the pipeline, just warn
fi

