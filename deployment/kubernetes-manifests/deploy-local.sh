#!/bin/bash

# Flowfish Local Deployment Script for Minikube
# Usage: ./deploy-local.sh [deploy|destroy|status|logs]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="flowfish"
GADGET_NAMESPACE="gadget"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if Kubernetes is accessible
    if ! kubectl cluster-info >/dev/null 2>&1; then
        print_error "Kubernetes cluster is not accessible. Please ensure:"
        echo "  - Docker Desktop Kubernetes is enabled, OR"
        echo "  - Minikube is running, OR"
        echo "  - kubectl is configured for your cluster"
        exit 1
    fi
    
    # Get current context
    CONTEXT=$(kubectl config current-context)
    print_status "Using Kubernetes context: $CONTEXT"
    
    # Check if it's Docker Desktop
    if [[ "$CONTEXT" == "docker-desktop" ]]; then
        print_status "Docker Desktop Kubernetes detected"
        USE_MINIKUBE=false
    elif [[ "$CONTEXT" == *"minikube"* ]] || command -v minikube >/dev/null; then
        print_status "Minikube detected"
        USE_MINIKUBE=true
        
        # Check if minikube is running
        if ! minikube status >/dev/null 2>&1; then
            print_error "Minikube is not running. Please start it first:"
            echo "  minikube start --cpus=4 --memory=8g --disk-size=50g"
            exit 1
        fi
        
        # Check if ingress addon is enabled
        if ! minikube addons list | grep -E "ingress.*enabled" >/dev/null; then
            print_warning "Ingress addon is not enabled. Enabling now..."
            minikube addons enable ingress
        fi
    else
        print_status "Generic Kubernetes cluster detected"
        USE_MINIKUBE=false
    fi
    
    print_success "Prerequisites check passed"
}

# Deploy function
deploy_flowfish() {
    print_status "Starting Flowfish deployment..."
    
    check_prerequisites
    
    # Apply manifests in order
    print_status "Creating namespaces and RBAC..."
    kubectl apply -f 01-namespace.yaml
    kubectl apply -f 02-rbac.yaml
    
    print_status "Creating configurations..."
    kubectl apply -f 03-configmaps.yaml
    kubectl apply -f 04-secrets.yaml
    
    print_status "Deploying databases (this may take a few minutes)..."
    kubectl apply -f 05-postgresql.yaml
    kubectl apply -f 06-redis.yaml
    kubectl apply -f 06-rabbitmq.yaml
    kubectl apply -f 07-neo4j.yaml
    kubectl apply -f 08-clickhouse.yaml
    
    print_status "Waiting for databases to be ready..."
    echo "  - PostgreSQL..."
    kubectl wait --for=condition=ready pod -l component=postgres -n $NAMESPACE --timeout=300s
    echo "  - Redis..."
    kubectl wait --for=condition=ready pod -l component=redis -n $NAMESPACE --timeout=120s
    echo "  - RabbitMQ..."
    kubectl wait --for=condition=ready pod -l component=rabbitmq -n $NAMESPACE --timeout=120s
    echo "  - ClickHouse..."
    kubectl wait --for=condition=ready pod -l component=clickhouse -n $NAMESPACE --timeout=300s
    echo "  - Neo4j..."
    kubectl wait --for=condition=ready pod -l app=neo4j -n $NAMESPACE --timeout=300s
    
    print_status "Deploying applications..."
    kubectl apply -f 08-backend.yaml
    kubectl apply -f 09-frontend.yaml
    
    print_status "Deploying Inspektor Gadget..."
    kubectl apply -f 10-inspektor-gadget.yaml
    
    print_status "Setting up ingress..."
    kubectl apply -f 11-ingress.yaml
    
    print_status "Waiting for applications to be ready..."
    kubectl wait --for=condition=ready pod -l app=backend -n $NAMESPACE --timeout=300s
    kubectl wait --for=condition=ready pod -l app=frontend -n $NAMESPACE --timeout=120s
    
    # Update /etc/hosts if needed
    if [ "$USE_MINIKUBE" = true ]; then
        CLUSTER_IP=$(minikube ip)
    else
        # For Docker Desktop, use localhost
        CLUSTER_IP="127.0.0.1"
    fi
    
    if ! grep -q "flowfish.local" /etc/hosts; then
        print_status "Adding flowfish.local to /etc/hosts..."
        echo "$CLUSTER_IP flowfish.local" | sudo tee -a /etc/hosts
    fi
    
    print_success "Flowfish deployment completed!"
    echo
    echo "Access your Flowfish instance:"
    echo "   Web UI: http://flowfish.local"
    echo "   API:    http://flowfish.local/api"
    echo
    echo "Default credentials:"
    echo "   Username: admin"
    echo "   Password: admin123"
    echo
    echo "Useful commands:"
    echo "   Status:    $0 status"
    echo "   Logs:      $0 logs"
    echo "   Dashboard: minikube dashboard"
    echo
}

# Destroy function
destroy_flowfish() {
    print_warning "Destroying Flowfish deployment..."
    
    print_status "Removing all Flowfish resources..."
    kubectl delete namespace $NAMESPACE --ignore-not-found=true
    kubectl delete namespace $GADGET_NAMESPACE --ignore-not-found=true
    
    # Remove from /etc/hosts
    if grep -q "flowfish.local" /etc/hosts; then
        print_status "Removing flowfish.local from /etc/hosts..."
        sudo sed -i '' '/flowfish.local/d' /etc/hosts
    fi
    
    print_success "Flowfish has been removed"
}

# Status function
show_status() {
    print_status "Flowfish deployment status:"
    echo
    
    # Check if namespaces exist
    if kubectl get namespace $NAMESPACE >/dev/null 2>&1; then
        echo "Namespaces:"
        kubectl get namespace $NAMESPACE $GADGET_NAMESPACE 2>/dev/null || true
        echo
        
        echo "Pods:"
        kubectl get pods -n $NAMESPACE -o wide
        echo
        
        echo " Services:"
        kubectl get svc -n $NAMESPACE
        echo
        
        echo "Ingress:"
        kubectl get ingress -n $NAMESPACE
        echo
        
        echo "Persistent Volumes:"
        kubectl get pvc -n $NAMESPACE
        echo
        
        # Check resource usage if metrics-server is available
        if kubectl get apiservice v1beta1.metrics.k8s.io >/dev/null 2>&1; then
            echo "Resource Usage:"
            kubectl top pods -n $NAMESPACE 2>/dev/null || echo "Metrics not available"
            echo
        fi
        
        # Check if app is accessible
        echo "Connectivity Test:"
        MINIKUBE_IP=$(minikube ip)
        if curl -s -o /dev/null -w "%{http_code}" http://flowfish.local/api/v1/health | grep -q "200"; then
            print_success "Flowfish API is accessible"
        else
            print_warning " Flowfish API is not responding"
        fi
        
        if curl -s -o /dev/null -w "%{http_code}" http://flowfish.local | grep -q "200"; then
            print_success "Flowfish UI is accessible"
        else
            print_warning " Flowfish UI is not responding"
        fi
    else
        print_warning "Flowfish is not deployed"
    fi
}

# Logs function
show_logs() {
    if ! kubectl get namespace $NAMESPACE >/dev/null 2>&1; then
        print_error "Flowfish is not deployed"
        exit 1
    fi
    
    echo " Available pods:"
    kubectl get pods -n $NAMESPACE --no-headers | awk '{print "  - " $1 " (" $3 ")"}'
    echo
    
    if [ $# -eq 2 ]; then
        # Show specific pod logs
        POD_NAME=$2
        print_status "Showing logs for $POD_NAME..."
        kubectl logs $POD_NAME -n $NAMESPACE -f
    else
        # Show all logs
        print_status "Showing logs for all pods (last 50 lines each)..."
        echo
        
        for pod in $(kubectl get pods -n $NAMESPACE --no-headers | awk '{print $1}'); do
            echo "=== Logs for $pod ==="
            kubectl logs $pod -n $NAMESPACE --tail=50
            echo
        done
    fi
}

# Update function
update_flowfish() {
    print_status "Updating Flowfish deployment..."
    
    # Re-apply configurations
    kubectl apply -f 03-configmaps.yaml
    kubectl apply -f 04-secrets.yaml
    
    # Restart deployments to pick up config changes
    kubectl rollout restart deployment/backend -n $NAMESPACE
    kubectl rollout restart deployment/frontend -n $NAMESPACE
    kubectl rollout restart deployment/neo4j-graphd -n $NAMESPACE
    
    print_success "Flowfish updated successfully"
}

# Main script logic
case "${1:-deploy}" in
    "deploy"|"install"|"up")
        deploy_flowfish
        ;;
    "destroy"|"delete"|"down")
        destroy_flowfish
        ;;
    "status"|"info")
        show_status
        ;;
    "logs")
        show_logs "$@"
        ;;
    "update"|"refresh")
        update_flowfish
        ;;
    "help"|"-h"|"--help")
        echo "Flowfish Local Deployment Script"
        echo
        echo "Usage: $0 [COMMAND] [OPTIONS]"
        echo
        echo "Commands:"
        echo "  deploy   Deploy Flowfish to minikube (default)"
        echo "  destroy  Remove Flowfish from minikube"
        echo "  status   Show deployment status"
        echo "  logs     Show pod logs (use 'logs <pod-name>' for specific pod)"
        echo "  update   Update configurations and restart"
        echo "  help     Show this help message"
        echo
        echo "Examples:"
        echo "  $0 deploy          # Deploy Flowfish"
        echo "  $0 status          # Check status"
        echo "  $0 logs            # Show all logs"
        echo "  $0 logs backend-xxx # Show specific pod logs"
        echo "  $0 destroy         # Remove everything"
        ;;
    *)
        print_error "Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac
