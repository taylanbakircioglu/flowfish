# Flowfish Development Makefile

.PHONY: help setup-local deploy-k8s deploy-compose status logs clean test build docs

# Default target
help: ## Show this help message
	@echo "🐟🌊 Flowfish Development Commands"
	@echo
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ 🏠 Local Development

setup-local: ## Setup complete local environment (macOS)
	@echo "🚀 Setting up Flowfish local environment..."
	./setup-local-env.sh

deploy-k8s: ## Deploy to minikube (Kubernetes)
	@echo "☸️  Deploying Flowfish to minikube..."
	cd deployment/kubernetes-manifests && ./deploy-local.sh deploy

deploy-compose: ## Start with Docker Compose
	@echo "🐳 Starting Flowfish with Docker Compose..."
	docker-compose up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 30
	@echo "✅ Flowfish is ready at http://localhost:3000"

status-k8s: ## Show Kubernetes deployment status
	@echo "📊 Checking Kubernetes deployment status..."
	cd deployment/kubernetes-manifests && ./deploy-local.sh status

status-compose: ## Show Docker Compose status
	@echo "📊 Docker Compose services status:"
	docker-compose ps

logs-k8s: ## Show Kubernetes logs
	cd deployment/kubernetes-manifests && ./deploy-local.sh logs

logs-compose: ## Show Docker Compose logs
	docker-compose logs -f

##@ 🧹 Cleanup

clean-k8s: ## Clean up Kubernetes deployment
	cd deployment/kubernetes-manifests && ./deploy-local.sh destroy

clean-compose: ## Stop and remove Docker Compose services
	docker-compose down -v

clean-minikube: ## Delete minikube cluster completely
	minikube delete

clean-all: clean-compose clean-k8s clean-minikube ## Clean everything

##@ 🔧 Development

build-backend: ## Build backend Docker image
	docker build -t flowfish/backend:dev ./backend

build-frontend: ## Build frontend Docker image  
	docker build -t flowfish/frontend:dev ./frontend

build-all: build-backend build-frontend ## Build all Docker images

test-backend: ## Run backend tests
	cd backend && python -m pytest

test-frontend: ## Run frontend tests
	cd frontend && npm test

lint-backend: ## Lint backend code
	cd backend && black . && flake8 . && mypy .

lint-frontend: ## Lint frontend code
	cd frontend && npm run lint

##@ 📚 Documentation

docs: ## Generate/serve documentation
	@echo "📚 Documentation locations:"
	@echo "  Executive Summary:    docs/01-executive-summary.md"
	@echo "  Feature List:         docs/02-feature-list.md"
	@echo "  Architecture:         docs/03-architecture.md"
	@echo "  API Docs:            api/openapi-spec.yaml"
	@echo "  Database Schemas:    schemas/"
	@echo "  UI Wireframes:       ui/page-structure.md"

serve-docs: ## Serve documentation with live reload
	# Requires npx/node
	npx @marp-team/marp-cli docs/ -s

##@ 🎯 Quick Actions

quick-start-k8s: setup-local ## Complete Kubernetes setup (one command)
	@echo "🎉 Flowfish is ready!"
	@echo "   Access: http://flowfish.local"
	@echo "   Login:  admin / admin123"

quick-start-compose: deploy-compose ## Quick Docker Compose start
	@echo "🎉 Flowfish is ready!"
	@echo "   Access: http://localhost:3000"
	@echo "   Login:  admin / admin123"

demo: deploy-compose ## Start demo environment
	@echo "🎬 Starting Flowfish demo..."
	@make deploy-compose
	@echo "📖 Open browser and follow these steps:"
	@echo "   1. Go to http://localhost:3000"
	@echo "   2. Login with admin/admin123" 
	@echo "   3. Add a cluster (local minikube)"
	@echo "   4. Create an analysis"
	@echo "   5. View the live dependency map"

##@ ℹ️  Information

info: ## Show environment information
	@echo "🐟 Flowfish Environment Information"
	@echo
	@echo "Prerequisites:"
	@command -v docker >/dev/null && echo "  ✅ Docker: $(docker --version)" || echo "  ❌ Docker: Not installed"
	@command -v kubectl >/dev/null && echo "  ✅ kubectl: $(kubectl version --client --short)" || echo "  ❌ kubectl: Not installed"
	@command -v minikube >/dev/null && echo "  ✅ minikube: $(minikube version --short)" || echo "  ❌ minikube: Not installed"
	@echo
	@if minikube status >/dev/null 2>&1; then \
		echo "Minikube Status: ✅ Running"; \
		echo "  IP: $(minikube ip)"; \
		echo "  Profile: $(minikube profile)"; \
	else \
		echo "Minikube Status: ❌ Not running"; \
	fi

version: ## Show Flowfish version
	@echo "Flowfish Platform v1.0.0"
	@echo "https://github.com/yourusername/flowfish"
