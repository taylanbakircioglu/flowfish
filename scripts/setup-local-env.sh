#!/bin/bash

# Flowfish Local Environment Setup Script
# This script sets up minikube, docker, and all dependencies for Flowfish

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Print functions
print_header() {
    echo -e "${PURPLE}================================================================${NC}"
    echo -e "${PURPLE} $1${NC}"
    echo -e "${PURPLE}================================================================${NC}"
}

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

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    print_error "This script is designed for macOS. For other platforms, please install manually."
    exit 1
fi

print_header "🐟 Flowfish Local Environment Setup"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check and install Homebrew
check_homebrew() {
    print_status "Checking Homebrew installation..."
    if ! command_exists brew; then
        print_status "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        print_success "Homebrew installed"
    else
        print_success "Homebrew is already installed"
    fi
}

# Check and install Docker
check_docker() {
    print_status "Checking Docker installation..."
    if ! command_exists docker; then
        print_status "Installing Docker Desktop..."
        brew install --cask docker
        print_warning "Please start Docker Desktop manually and then re-run this script"
        exit 1
    elif ! docker info >/dev/null 2>&1; then
        print_error "Docker is installed but not running. Please start Docker Desktop."
        exit 1
    else
        print_success "Docker is running"
    fi
}

# Check and install kubectl
check_kubectl() {
    print_status "Checking kubectl installation..."
    if ! command_exists kubectl; then
        print_status "Installing kubectl..."
        brew install kubectl
        print_success "kubectl installed"
    else
        print_success "kubectl is already installed"
    fi
}

# Check and install minikube
check_minikube() {
    print_status "Checking minikube installation..."
    if ! command_exists minikube; then
        print_status "Installing minikube..."
        brew install minikube
        print_success "minikube installed"
    else
        print_success "minikube is already installed"
    fi
}

# Start minikube with proper configuration
setup_minikube() {
    print_status "Setting up minikube..."
    
    # Check if minikube is running
    if minikube status >/dev/null 2>&1; then
        print_warning "Minikube is already running. Do you want to restart with optimal settings? [y/N]"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            minikube stop
            minikube delete
        else
            print_status "Continuing with existing minikube instance..."
            return 0
        fi
    fi
    
    print_status "Starting minikube with Flowfish-optimized settings..."
    minikube start \
        --cpus=4 \
        --memory=8g \
        --disk-size=50g \
        --driver=docker \
        --kubernetes-version=v1.28.3
    
    print_success "Minikube started successfully"
}

# Enable required addons
setup_addons() {
    print_status "Enabling minikube addons..."
    
    # Enable ingress
    minikube addons enable ingress
    print_success "Ingress addon enabled"
    
    # Enable metrics-server
    minikube addons enable metrics-server  
    print_success "Metrics server enabled"
    
    # Enable dashboard (optional)
    minikube addons enable dashboard
    print_success "Dashboard addon enabled"
    
    print_status "Waiting for ingress controller to be ready..."
    kubectl wait --namespace ingress-nginx \
        --for=condition=ready pod \
        --selector=app.kubernetes.io/component=controller \
        --timeout=300s
}

# Deploy Flowfish
deploy_flowfish() {
    print_status "Deploying Flowfish to minikube..."
    
    cd deployment/kubernetes-manifests
    
    # Run the deployment script
    if [ -f "./deploy-local.sh" ]; then
        print_status "Using automated deployment script..."
        ./deploy-local.sh deploy
    else
        print_error "Deployment script not found. Please run from flowfish project root."
        exit 1
    fi
    
    cd - > /dev/null
}

# Show final status and URLs
show_completion() {
    print_header "🎉 Flowfish Setup Complete!"
    
    echo
    echo -e "${GREEN}✅ Installation completed successfully!${NC}"
    echo
    echo -e "${BLUE}🌐 Access URLs:${NC}"
    echo "   Web UI:  http://flowfish.local"
    echo "   API:     http://flowfish.local/api"
    echo "   Health:  http://flowfish.local/api/v1/health"
    echo
    echo -e "${BLUE}🔐 Default Credentials:${NC}"
    echo "   Username: admin"
    echo "   Password: admin123"
    echo
    echo -e "${BLUE}📊 Useful Commands:${NC}"
    echo "   Status:      cd deployment/kubernetes-manifests && ./deploy-local.sh status"
    echo "   Logs:        cd deployment/kubernetes-manifests && ./deploy-local.sh logs"
    echo "   Dashboard:   minikube dashboard"
    echo "   Cleanup:     cd deployment/kubernetes-manifests && ./deploy-local.sh destroy"
    echo
    echo -e "${YELLOW}💡 Next Steps:${NC}"
    echo "   1. Open http://flowfish.local in your browser"
    echo "   2. Login with admin credentials"
    echo "   3. Add your local cluster (minikube)"
    echo "   4. Create your first analysis"
    echo "   5. View the live dependency map"
    echo
    echo -e "${PURPLE}🐟🌊 Happy analyzing with Flowfish!${NC}"
}

# Main execution
main() {
    case "${1:-full}" in
        "full"|"install"|"setup")
            check_homebrew
            check_docker
            check_kubectl
            check_minikube
            setup_minikube
            setup_addons
            deploy_flowfish
            show_completion
            ;;
        "minikube-only")
            check_minikube
            setup_minikube
            setup_addons
            print_success "Minikube setup complete. Run '$0 deploy' to install Flowfish."
            ;;
        "deploy-only")
            deploy_flowfish
            show_completion
            ;;
        "check")
            check_homebrew
            check_docker
            check_kubectl
            check_minikube
            print_success "All prerequisites are installed"
            ;;
        "help"|"-h"|"--help")
            echo "Flowfish Local Environment Setup"
            echo
            echo "Usage: $0 [COMMAND]"
            echo
            echo "Commands:"
            echo "  full          Install everything (default)"
            echo "  minikube-only Setup minikube only"
            echo "  deploy-only   Deploy Flowfish only (assumes minikube ready)"
            echo "  check         Check if prerequisites are installed"
            echo "  help          Show this help"
            echo
            echo "Examples:"
            echo "  $0            # Full installation"
            echo "  $0 check      # Check prerequisites"
            echo "  $0 deploy-only # Deploy Flowfish to existing minikube"
            ;;
        *)
            print_error "Unknown command: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
