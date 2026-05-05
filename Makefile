.PHONY: help install test lint format build run clean validate docker-build docker-up docker-down profiling gcp-setup gcp-deploy gcp-logs gcp-status

PYTHON := python3
PIP := pip3
PYTEST := pytest
DOCKER_COMPOSE := docker-compose -f docker/docker-compose.yml

GCP_PROJECT_ID ?= 
GITHUB_OWNER ?= 
GITHUB_REPO ?= projet08

help:
	@echo "Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install           - Install dependencies"
	@echo "  make test              - Run all tests"
	@echo "  make test-coverage     - Run tests with coverage"
	@echo "  make lint              - Run linting (ruff, black, isort)"
	@echo "  make format            - Format code (black, isort)"
	@echo "  make validate          - Validate CI/CD setup"
	@echo "  make profiling         - Run ONNX profiling"
	@echo ""
	@echo "Build & Run:"
	@echo "  make build             - Build everything"
	@echo "  make run               - Run API locally"
	@echo "  make docker-build      - Build Docker image"
	@echo "  make docker-up         - Start Docker services (API + DB)"
	@echo "  make docker-down       - Stop Docker services"
	@echo "  make docker-logs       - Show Docker logs"
	@echo ""
	@echo "Monitoring (Local Development Only):"
	@echo "  make monitoring-up     - Start Prometheus + Grafana"
	@echo "  make monitoring-down   - Stop Prometheus + Grafana"
	@echo ""
	@echo "Google Cloud Deployment:"
	@echo "  make gcp-setup         - Setup GCP/Cloud Run configuration"
	@echo "  make gcp-deploy        - Deploy to Cloud Run (manual)"
	@echo "  make gcp-logs          - Show Cloud Run logs"
	@echo "  make gcp-status        - Show Cloud Run service status"
	@echo ""
	@echo "Other:"
	@echo "  make clean             - Clean build artifacts"

install:
	@echo "📦 Installing dependencies..."
	$(PIP) install -e .
	$(PIP) install pytest-cov ruff black isort

test:
	@echo "🧪 Running tests..."
	$(PYTEST) tests/ -v

test-coverage:
	@echo "📊 Running tests with coverage..."
	$(PYTEST) tests/ -v --cov=model --cov=api --cov-report=html --cov-report=term

lint:
	@echo "🔍 Running linters..."
	ruff check . --select=E,W,F,N
	black --check api/ model/ tests/ profiling/ --diff
	isort --check-only api/ model/ tests/ profiling/ --diff

format:
	@echo "✨ Formatting code..."
	black api/ model/ tests/ profiling/
	isort api/ model/ tests/ profiling/
	ruff check . --select=E,W,F,N --fix

validate:
	@echo "🔐 Validating CI/CD setup..."
	$(PYTHON) scripts/validate_cicd.py

profiling:
	@echo "📊 Running ONNX profiling..."
	$(PYTHON) -m profiling.onnx_optimization

build: test lint
	@echo "🏗️  Build complete!"

run:
	@echo "🚀 Starting API..."
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	@echo "🐳 Building Docker image..."
	docker build -f docker/Dockerfile -t projet08-api:latest .

docker-up:
	@echo "🐳 Starting Docker services..."
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "Services are starting:"
	@echo "  📡 API:        http://localhost:8000"
	@echo "  📊 Prometheus: http://localhost:9090"
	@echo "  📈 Grafana:    http://localhost:3000 (admin/admin)"
	@echo "  🗄️  Database:   localhost:5432"

docker-down:
	@echo "🛑 Stopping Docker services..."
	$(DOCKER_COMPOSE) down

docker-logs:
	@echo "📋 Showing Docker logs..."
	$(DOCKER_COMPOSE) logs -f api

monitoring-up:
	@echo "📊 Starting monitoring stack (Prometheus + Grafana)..."
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml -f docker/docker-compose.monitoring.yml up -d
	@echo "📈 Grafana:    http://localhost:3000 (admin/admin)"
	@echo "📊 Prometheus: http://localhost:9090"

monitoring-down:
	@echo "🛑 Stopping monitoring stack..."
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml -f docker/docker-compose.monitoring.yml down

clean:
	@echo "🧹 Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/
	@echo "✅ Cleaned"

gcp-setup:
	@echo "🔧 Setting up Google Cloud..."
	@if [ -z "$(GCP_PROJECT_ID)" ] || [ -z "$(GITHUB_OWNER)" ]; then \
		echo "Usage: make gcp-setup GCP_PROJECT_ID=<id> GITHUB_OWNER=<owner> [GITHUB_REPO=projet08]"; \
		exit 1; \
	fi
	chmod +x scripts/setup-gcp.sh
	bash scripts/setup-gcp.sh $(GCP_PROJECT_ID) $(GITHUB_OWNER) $(GITHUB_REPO)

gcp-deploy:
	@echo "🚀 Deploying to Cloud Run..."
	@if [ -z "$(GCP_PROJECT_ID)" ]; then \
		echo "Usage: make gcp-deploy GCP_PROJECT_ID=<id>"; \
		exit 1; \
	fi
	gcloud run deploy projet08-api \
		--image=gcr.io/$(GCP_PROJECT_ID)/projet08-api:latest \
		--region=europe-west1 \
		--platform=managed \
		--allow-unauthenticated \
		--memory=2Gi \
		--cpu=1 \
		--project=$(GCP_PROJECT_ID)

gcp-logs:
	@echo "📋 Cloud Run logs..."
	@if [ -z "$(GCP_PROJECT_ID)" ]; then \
		echo "Usage: make gcp-logs GCP_PROJECT_ID=<id>"; \
		exit 1; \
	fi
	gcloud run logs read projet08-api --follow --project=$(GCP_PROJECT_ID)

gcp-status:
	@echo "📊 Cloud Run service status..."
	@if [ -z "$(GCP_PROJECT_ID)" ]; then \
		echo "Usage: make gcp-status GCP_PROJECT_ID=<id>"; \
		exit 1; \
	fi
	gcloud run services describe projet08-api \
		--region=europe-west1 \
		--project=$(GCP_PROJECT_ID) \
		--format='table(status.conditions[].type,status.conditions[].status)'

.DEFAULT_GOAL := help
