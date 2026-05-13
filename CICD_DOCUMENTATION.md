# CI/CD Pipeline Documentation

## Overview

This project includes a comprehensive CI/CD pipeline using GitHub Actions that:

1. **Tests** - Runs all pytest test suites
2. **Profiling** - Executes ONNX model profiling and optimization
3. **Build** - Creates a Docker image and pushes to Google Container Registry (GCR)
4. **Deploy** - Deploys to Google Cloud Run (API + Database only)

**Important:** Monitoring services (Prometheus, Grafana) are **NOT** deployed to Cloud Run. They are only for local development.

### Architecture

```
Local Development                    Cloud Run Production
├─ API + Database                    └─ API + Database
├─ Prometheus (optional)             
└─ Grafana (optional)                

Cloud Run auto-exports metrics to:
- Cloud Run native metrics dashboard
- Cloud Monitoring (GCP)
- Optional: Prometheus server (external)
```

## Workflow Triggers

The pipeline is triggered automatically on:

- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches
- Manual trigger via `workflow_dispatch`

## Pipeline Stages

### 1. Test Stage (`test` job)

Runs all unit tests with coverage reporting:

```bash
# Tests included:
- tests/test_data_utils.py      # Data loading and preprocessing
- tests/test_onnx_integration.py # ONNX model operations
- tests/test_api.py              # API endpoints
```

**Outputs:**
- pytest results
- coverage report uploaded to Codecov

### 2. Profiling Stage (`profiling` job)

Depends on: `test` job

Profiles ONNX model performance and attempts optimization:

```bash
# Operations:
- Load test data (50 samples)
- Profile original model (5 runs)
- Optimize model with onnx-simplifier
- Profile optimized model
- Compare latency improvements
```

**Artifacts:**
- `onnx_profile_*.json` files (retained for 30 days)

### 3. Build Stage (`build` job)

Depends on: `test` job

Builds Docker image with multi-stage optimization:

```dockerfile
# Build stage: Install all dependencies
# Runtime stage: Copy only necessary packages

# Features:
- Multi-stage build for smaller final image
- Docker Buildx with caching
- Image scanning with Trivy for vulnerabilities
- Push to Docker Hub (main branch only)
```

**Docker Image Tags:**
- `latest` (main branch only)
- `main-{sha}` (latest commit on main)
- `develop-{sha}` (latest commit on develop)
- `v{version}` (on semantic version tags)

### 4. Lint Stage (`lint` job)

Code quality checks:

```bash
# Tools:
- ruff          # Fast Python linter
- black         # Code formatter
- isort         # Import sorting
```

### 5. Deploy Stage (`deploy` job)

Depends on: `test`, `build`, `profiling` jobs
Runs only on: `push` to `main` branch

Creates deployment summary and optionally notifies webhook.

### 6. Notify Stage (`notify` job)

Final notification of pipeline status.

## GitHub Secrets Setup

To make this pipeline work, configure these secrets in your GitHub repository:

1. **Docker Hub Credentials** (for image push)
   - `DOCKER_USERNAME` - Your Docker Hub username
   - `DOCKER_PASSWORD` - Your Docker Hub access token

2. **Optional: Deployment Webhook**
   - `DEPLOYMENT_WEBHOOK_URL` - Endpoint to notify on successful deploy

### How to set secrets:

1. Go to `Settings` → `Secrets and variables` → `Actions`
2. Click `New repository secret`
3. Add each secret name and value

## Local Development

### Option 1: Using Docker Compose

```bash
# Copy environment template
cp .env.example .env

# Start API + Database only
docker-compose -f docker/docker-compose.yml up -d

# API will be available at:
# - http://localhost:8000/docs      (Swagger UI)
# - http://localhost:8000/health    (Health check)
# - http://localhost:8000/metrics   (Prometheus metrics)

# Optional: Add monitoring stack (local development only)
# This does NOT deploy to Cloud Run
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.monitoring.yml up -d

# Or via make
make docker-up
make monitoring-up
```

Monitor with:
- Prometheus: http://localhost:9090
- Grafana:    http://localhost:3000 (admin/admin)

### Option 2: Local Development Without Docker

```bash
# Install dependencies
pip install -e .

# Set up database
# (requires PostgreSQL running locally or via container)

# Run tests
pytest tests/ -v

# Run API directly
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Run profiling
python profiling/onnx_optimization.py
```

## Build Docker Image Locally

```bash
# Build
docker build -f docker/Dockerfile -t projet08-api:latest .

# Run
docker run -p 8000:8000 projet08-api:latest

# Test
curl http://localhost:8000/health
```

## Monitoring

### Prometheus Metrics

Available at `/metrics` endpoint:

- `api_requests_total` - Total API requests by method, endpoint, status
- `api_latency_seconds` - API request latency
- `onnx_inference_seconds` - Model inference time
- `api_errors_total` - Total errors by endpoint and type
- `predictions_total` - Total predictions made

### Grafana Dashboards

Pre-built dashboards available at:

```
./monitoring/grafana_drift_dashboard.json
```

Import this dashboard in Grafana to visualize:
- Request latency trends
- Error rates
- Model inference times
- Data drift detection

## Troubleshooting

### Pipeline fails on Docker build

1. Check Dockerfile syntax
2. Ensure all source files are present
3. Verify dependencies in `pyproject.toml`
4. Check Docker Hub credentials

### Tests fail

1. Run locally: `pytest tests/ -v`
2. Check test requirements are installed
3. Verify test data is available in `data/split/`

### Image scan fails (Trivy)

- Review security issues in GitHub Actions logs
- Update dependencies to latest secure versions
- Suppress false positives if needed

### Deploy webhook doesn't work

- Verify `DEPLOYMENT_WEBHOOK_URL` secret is set
- Check webhook endpoint is accessible
- Review webhook logs on receiving end

## Customization

### Modify build configuration

Edit `.github/workflows/ci-cd.yml`:

- Change `PYTHON_VERSION` to different Python version
- Add/remove test suites
- Modify Docker image tags
- Update registry (currently Docker Hub)

### Modify Docker image

Edit `docker/Dockerfile`:

- Add system dependencies in RUN commands
- Change base image (currently `python:3.14-slim`)
- Modify startup command
- Adjust health check parameters

### Modify docker-compose services

Edit `docker/docker-compose.yml`:

- Add environment variables
- Change exposed ports
- Add additional services (Redis, Elasticsearch, etc.)
- Modify volume mappings

## Best Practices

1. **Always run tests before pushing** - Catch issues locally
2. **Use semantic versioning for releases** - Tags are automatically converted to Docker image versions
3. **Review security scan results** - Address Trivy vulnerabilities promptly
4. **Monitor pipeline run times** - Optimize slow steps
5. **Keep secrets secure** - Never commit `.env` files with real credentials

## Performance Optimization

- Multi-stage Docker build reduces image size ~50%
- GitHub Actions cache speeds up dependency installation
- Parallel test execution with pytest-xdist (optional)
- Docker layer caching via Buildx

---

For more information, see:
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
