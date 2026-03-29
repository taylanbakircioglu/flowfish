#!/bin/bash
set -e

# Post-Deployment Health Check

ns=$OPENSHIFT_NAMESPACE

echo " Running Post-Deployment Health Checks..."
echo "Namespace: $ns"

# Login to OpenShift
oc login -u $OPENSHIFT_USER -p $OPENSHIFT_PASSWORD $OPENSHIFT_API_URL --insecure-skip-tls-verify=true
oc project $ns

# Cleanup failed pods
echo " Cleanup failed pods..."
oc delete pod --field-selector=status.phase=Failed -n $ns 2>/dev/null || true
oc get pods -n $ns | grep -E "(ImagePullBackOff|Error|CrashLoopBackOff)" | awk '{print $1}' | xargs -r oc delete pod -n $ns 2>/dev/null || true

echo ""
echo ""
echo " POD STATUS"
echo ""
oc get pods -n $ns

echo ""
echo ""
echo "ROUTES & URLS"
echo ""

FR=$(oc get route frontend -n $ns -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
BR=$(oc get route backend -n $ns -o jsonpath='{.spec.host}' 2>/dev/null || echo "")

[ "$FR" != "" ] && echo "Frontend: https://$FR"
[ "$BR" != "" ] && echo "Backend:  https://$BR"

echo ""
echo ""
echo " HEALTH CHECKS"
echo ""

# Backend Health Check
if [ "$BR" != "" ]; then
    HC=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://$BR/api/v1/health" 2>/dev/null || echo "000")
    if [ "$HC" = "200" ]; then
        echo "Backend Health: OK ($HC)"
    else
        echo " Backend Health: $HC"
    fi
else
    echo " Backend route not found"
fi

# Frontend Check
if [ "$FR" != "" ]; then
    FC=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://$FR" 2>/dev/null || echo "000")
    if [ "$FC" = "200" ]; then
        echo "Frontend: OK ($FC)"
    else
        echo " Frontend: $FC"
    fi
else
    echo " Frontend route not found"
fi

echo ""
echo ""
echo "DEPLOYMENT SUMMARY"
echo ""

# Count running pods
TOTAL=$(oc get pods -n $ns --no-headers | wc -l)
RUNNING=$(oc get pods -n $ns --no-headers | grep -c "Running" || echo "0")
FAILED=$(oc get pods -n $ns --no-headers | grep -cE "Error|CrashLoopBackOff|ImagePullBackOff" || echo "0")

echo "Total Pods:   $TOTAL"
echo "Running:      $RUNNING"
echo "Failed:       $FAILED"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo " WARNING: $FAILED pod(s) in failed state"
    oc get pods -n $ns | grep -E "Error|CrashLoopBackOff|ImagePullBackOff" || true
fi

echo ""
echo "Health check completed!"

