#!/bin/bash
set -e

NAMESPACE="flowfish-local"
GITHUB_RAW="https://raw.githubusercontent.com/taylanbakircioglu/flowfish/main/deployment/local-test"

MANIFESTS=(
  "00-namespace.yaml"
  "01-rbac.yaml"
  "02-databases.yaml"
  "03-migrations.yaml"
  "04-backend.yaml"
  "05-cluster-manager.yaml"
  "06-analysis-orchestrator.yaml"
  "07-ingestion-service.yaml"
  "08-graph-query.yaml"
  "09-timeseries-query.yaml"
  "10-graph-writer.yaml"
  "11-timeseries-writer.yaml"
  "12-change-detection-worker.yaml"
  "13-frontend.yaml"
  "14-nginx-proxy.yaml"
)

GADGET_MANIFEST="15-inspektor-gadget.yaml"

usage() {
  echo "Flowfish Local Deployment Script"
  echo ""
  echo "Usage: $0 [install|install-with-gadget|uninstall|status|restart]"
  echo ""
  echo "Commands:"
  echo "  install              Deploy Flowfish (without eBPF data collection)"
  echo "  install-with-gadget  Deploy Flowfish + Inspektor Gadget DaemonSet"
  echo "                       Enables local cluster analysis with eBPF events"
  echo "                       Requires: amd64 Linux, kernel 5.4+, privileged access"
  echo "  uninstall            Remove Flowfish from the local Kubernetes cluster"
  echo "  status               Show pod and service status"
  echo "  restart              Restart all Flowfish deployments (re-pull images)"
  echo ""
  echo "Prerequisites: kubectl configured with a running Kubernetes cluster"
}

check_kubectl() {
  if ! command -v kubectl &> /dev/null; then
    echo "ERROR: kubectl is not installed or not in PATH"
    exit 1
  fi
  if ! kubectl cluster-info &> /dev/null; then
    echo "ERROR: Cannot connect to Kubernetes cluster"
    echo "Make sure your cluster is running and kubectl is configured."
    exit 1
  fi
}

install() {
  local with_gadget="${1:-false}"

  echo "============================================="
  echo "  Flowfish Platform - Local Deployment"
  if [ "$with_gadget" = "true" ]; then
    echo "  (with Inspektor Gadget eBPF collection)"
  fi
  echo "============================================="
  echo ""

  check_kubectl

  if [ "$with_gadget" = "true" ]; then
    ARCH=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.architecture}' 2>/dev/null || echo "unknown")
    if [ "$ARCH" != "amd64" ]; then
      echo "WARNING: Node architecture is '${ARCH}', not amd64."
      echo "Inspektor Gadget requires amd64 (x86_64) Linux."
      echo "The DaemonSet will be applied but pods may fail to start."
      echo ""
    fi
  fi

  echo "Applying manifests from GitHub..."
  echo ""

  # Delete old migration job if exists (completed Jobs don't re-run on apply)
  kubectl delete job flowfish-migrations -n "${NAMESPACE}" --ignore-not-found 2>/dev/null || true

  for manifest in "${MANIFESTS[@]}"; do
    echo "  Applying ${manifest}..."
    kubectl apply -f "${GITHUB_RAW}/${manifest}"
  done

  if [ "$with_gadget" = "true" ]; then
    echo "  Applying ${GADGET_MANIFEST}..."
    kubectl apply -f "${GITHUB_RAW}/${GADGET_MANIFEST}"
  fi

  echo ""
  echo "Waiting for migrations job to complete..."
  kubectl wait --for=condition=complete job/flowfish-migrations -n "${NAMESPACE}" --timeout=180s 2>/dev/null || {
    echo "  Migrations job still running or waiting for databases."
    echo "  Check status with: kubectl get jobs -n ${NAMESPACE}"
  }

  echo ""
  echo "Waiting for core pods to be ready..."
  kubectl wait --for=condition=ready pod -l app=backend -n "${NAMESPACE}" --timeout=300s 2>/dev/null || true
  kubectl wait --for=condition=ready pod -l app=frontend -n "${NAMESPACE}" --timeout=120s 2>/dev/null || true

  if [ "$with_gadget" = "true" ]; then
    echo ""
    echo "Waiting for Inspektor Gadget pods..."
    kubectl wait --for=condition=ready pod -l app=inspektor-gadget -n "${NAMESPACE}" --timeout=120s 2>/dev/null || {
      echo "  Gadget pods not ready yet. Check: kubectl get pods -l app=inspektor-gadget -n ${NAMESPACE}"
    }
  fi

  echo ""
  echo "============================================="
  echo "  Deployment Complete!"
  echo "============================================="
  echo ""
  echo "  UI:  http://localhost:30080"
  echo "  API: http://localhost:30080/api/v1/health"
  echo ""
  echo "  Login: admin / admin123"
  echo ""
  if [ "$with_gadget" = "true" ]; then
    echo "  Inspektor Gadget: ENABLED (eBPF data collection active)"
    echo "  You can add this cluster as In-Cluster and run analyses."
  else
    echo "  Inspektor Gadget: NOT installed"
    echo "  To analyze a cluster, add a remote cluster via Token method,"
    echo "  or re-deploy with: $0 install-with-gadget"
  fi
  echo ""
  echo "  Check status: $0 status"
  echo "============================================="
}

uninstall() {
  echo "Removing Flowfish from namespace ${NAMESPACE}..."

  for (( i=${#MANIFESTS[@]}-1; i>=0; i-- )); do
    manifest="${MANIFESTS[$i]}"
    echo "  Deleting ${manifest}..."
    kubectl delete -f "${GITHUB_RAW}/${manifest}" --ignore-not-found 2>/dev/null || true
  done

  echo "  Deleting ${GADGET_MANIFEST}..."
  kubectl delete -f "${GITHUB_RAW}/${GADGET_MANIFEST}" --ignore-not-found 2>/dev/null || true

  kubectl delete clusterrole flowfish-cluster-reader --ignore-not-found 2>/dev/null || true
  kubectl delete clusterrolebinding flowfish-cluster-reader-binding --ignore-not-found 2>/dev/null || true
  kubectl delete clusterrole inspektor-gadget --ignore-not-found 2>/dev/null || true
  kubectl delete clusterrolebinding inspektor-gadget --ignore-not-found 2>/dev/null || true
  kubectl delete crd traces.gadget.kinvolk.io --ignore-not-found 2>/dev/null || true

  echo ""
  echo "Flowfish has been removed."
}

status() {
  echo "Flowfish Platform Status (namespace: ${NAMESPACE})"
  echo ""
  echo "--- Pods ---"
  kubectl get pods -n "${NAMESPACE}" -o wide 2>/dev/null || echo "Namespace not found"
  echo ""
  echo "--- Services ---"
  kubectl get svc -n "${NAMESPACE}" 2>/dev/null || true
  echo ""
  echo "--- Jobs ---"
  kubectl get jobs -n "${NAMESPACE}" 2>/dev/null || true
}

restart() {
  echo "Restarting all Flowfish deployments..."
  kubectl rollout restart deployment -n "${NAMESPACE}" 2>/dev/null || true
  echo "Rollout restart initiated. Pods will re-pull images."
  echo "Monitor with: $0 status"
}

case "${1:-}" in
  install)              install false ;;
  install-with-gadget)  install true ;;
  uninstall)            uninstall ;;
  status)               status ;;
  restart)              restart ;;
  *)                    usage ;;
esac
