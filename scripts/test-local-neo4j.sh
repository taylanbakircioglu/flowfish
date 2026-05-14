#!/bin/bash
set -e

echo "================================================"
echo "Testing Neo4j on Local Kubernetes"
echo "================================================"

# Test namespace
NAMESPACE="test-flowfish"

# Detect default StorageClass
STORAGE_CLASS=$(kubectl get storageclass -o jsonpath='{.items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")].metadata.name}')
if [ -z "$STORAGE_CLASS" ]; then
  # Fallback: get first available StorageClass
  STORAGE_CLASS=$(kubectl get storageclass -o jsonpath='{.items[0].metadata.name}')
fi
echo "Using StorageClass: $STORAGE_CLASS"

echo "Creating test namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "Preparing manifests..."
TEMP_DIR="/tmp/flowfish-neo4j-test"
mkdir -p $TEMP_DIR

# Copy manifests
cp deployment/kubernetes-manifests/07-neo4j.yaml $TEMP_DIR/
cp deployment/kubernetes-manifests/08-neo4j-init.yaml $TEMP_DIR/

# Create test secret
cat > $TEMP_DIR/secrets.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: flowfish-secrets
  namespace: {{NAMESPACE}}
type: Opaque
stringData:
  NEO4J_AUTH: "neo4j/testpassword123"
EOF

# Replace namespace in secret
sed -i '' "s/{{NAMESPACE}}/$NAMESPACE/g" $TEMP_DIR/secrets.yaml

# Replace placeholders
cd $TEMP_DIR
sed -i '' "s/{{OPENSHIFT_NAMESPACE}}/$NAMESPACE/g" *.yaml
sed -i '' "s/{{STORAGE_CLASS}}/$STORAGE_CLASS/g" *.yaml

echo ""
echo "Deploying Neo4j..."
kubectl apply -f secrets.yaml
kubectl apply -f 07-neo4j.yaml

echo ""
echo "================================================"
echo "Waiting for Neo4j to be ready..."
echo "================================================"

echo ""
echo "Waiting for Neo4j pod (this may take 60-90 seconds)..."
kubectl wait --for=condition=ready pod -l app=neo4j -n $NAMESPACE --timeout=5m || {
  echo "❌ Neo4j failed to start!"
  echo ""
  echo "Pod status:"
  kubectl get pods -n $NAMESPACE -l app=neo4j
  echo ""
  echo "Pod describe:"
  kubectl describe pod -n $NAMESPACE -l app=neo4j
  echo ""
  echo "Neo4j logs:"
  kubectl logs -n $NAMESPACE -l app=neo4j --tail=100 || true
  exit 1
}

echo "✅ Neo4j is ready!"

echo ""
echo "Deploying Neo4j init job..."
kubectl apply -f 08-neo4j-init.yaml

echo ""
echo "Waiting for init job to complete..."
kubectl wait --for=condition=complete job/neo4j-init -n $NAMESPACE --timeout=3m || {
  echo "❌ Init job failed!"
  echo ""
  echo "Job status:"
  kubectl get job -n $NAMESPACE
  echo ""
  echo "Init logs:"
  kubectl logs -n $NAMESPACE job/neo4j-init --tail=100 || true
  exit 1
}

echo "✅ Init job completed!"

echo ""
echo "================================================"
echo "✅ NEO4J SUCCESSFULLY DEPLOYED!"
echo "================================================"

echo ""
echo "Pod Status:"
kubectl get pods -n $NAMESPACE -l app=neo4j

echo ""
echo "Service:"
kubectl get svc -n $NAMESPACE neo4j

echo ""
echo "================================================"
echo "Test Neo4j Connection:"
echo "================================================"
echo ""
echo "Port forward:"
echo "  kubectl port-forward -n $NAMESPACE svc/neo4j 7474:7474 7687:7687"
echo ""
echo "Then open browser:"
echo "  http://localhost:7474"
echo "  Username: neo4j"
echo "  Password: testpassword123"
echo ""
echo "Or use cypher-shell:"
echo "  kubectl exec -it -n $NAMESPACE neo4j-0 -- cypher-shell -u neo4j -p testpassword123"
echo ""
echo "Cleanup:"
echo "  kubectl delete namespace $NAMESPACE"
echo "================================================"

