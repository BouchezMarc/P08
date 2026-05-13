API de prediction ONNX avec FastAPI, monitoring local et déploiement Cloud Run

## Quick Start (2 minutes)

### 1. Installer les dépendances

```bash
uv sync
```

### 2. Lancer l'API localement

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Avec Docker Compose

```bash
# API + Database uniquement
docker-compose -f docker/docker-compose.yml up -d

# API + Database + Monitoring (Prometheus + Grafana)
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.monitoring.yml up -d
```

### 4. Vérifier rapidement

- API: `http://127.0.0.1:8000/health`
- Métriques: `http://127.0.0.1:8000/metrics`
- Grafana (optionnel): `http://127.0.0.1:3000` (admin/admin)
- Prometheus (optionnel): `http://127.0.0.1:9090`

## Déploiement

### Production (Cloud Run - Automatique via GitHub)

Push vers `main` déclenche automatiquement:
1. Tests (pytest)
2. Build Docker
3. Deploy à Cloud Run
4. Smoke tests

Voir [CLOUD_RUN_DEPLOYMENT.md](CLOUD_RUN_DEPLOYMENT.md) pour la configuration initiale.

### Configuration GCP initiale

Le script de préparation se trouve dans [scripts/setup-gcp.sh](scripts/setup-gcp.sh) et doit être lancé depuis un shell bash, pas directement depuis PowerShell.

Exemple recommandé via le Makefile:

```bash
make gcp-setup GCP_PROJECT_ID=<project-id> GITHUB_OWNER=<github-owner> GITHUB_REPO=projet08
```

Si tu veux l'appeler directement, fais-le depuis Git Bash ou WSL:

```bash
bash scripts/setup-gcp.sh <project-id> <github-owner> projet08
```

### Monitoring

**Local (développement):**
- Prometheus + Grafana via docker-compose (optionnel)

**Production (Cloud Run):**
- Métriques natives Cloud Run
- Cloud Monitoring (GCP)
- Optional: scraper Prometheus externe

## Ce projet implémente un pipeline ML complet

- Entraînement LightGBM et export ONNX dans `model/`
- Inférence via API FastAPI dans `api/main.py`
- Monitoring/performance via Prometheus + Grafana (local)
- Scripts de profiling dans `profiling/`
- Déploiement automatique sur Cloud Run

## Points clés actuels

- Endpoint principal: `POST /predict/test-csv`
- Pagination: `page`, `page_size`
- Simulation drift: `income_multiplier`
- Cache CSV au démarrage via lifespan FastAPI
- Métriques Prometheus exposées sur `GET /metrics`

## Prérequis

- Python >= 3.14
- `uv` (recommandé) ou `pip`
- Docker (optionnel, pour Compose)
- Compte GCP (pour Cloud Run)

## Installation

### 1. Cloner le dépôt

```bash
git clone <votre-repo>
cd projet08
```

### 2. Installer les dépendances

Option A (recommandé):

```bash
uv sync
```

Option B:

```bash
pip install -e .
```

## Arborescence (principale)

```text
projet08/
|-- api/
|   `-- main.py                 # FastAPI (health, predict, metrics)
|-- dashboard/
|   `-- app.py                  # UI dashboard
|-- model/
|   |-- train.py                # Entraînement
|   |-- convert_to_onnx.py      # Export ONNX
|   |-- data_utils.py
|   |-- handler.py
|   `-- artifacts/
|       `-- model.onnx
|-- monitoring/
|   |-- monitoring_utils.py
|   `-- grafana_drift_dashboard.json
|-- profiling/
|   |-- onnx_optimization.py
|-- docker/
|   |-- Dockerfile              # Image pour API + DB
|   |-- docker-compose.yml      # API + DB
|   |-- docker-compose.monitoring.yml  # Optional: Prometheus + Grafana
|-- tests/
|   |-- test_api.py
|   |-- test_data_utils.py
|   |-- test_onnx_integration.py
|-- .github/workflows/
|   |-- ci-cd.yml               # Pipeline GitHub Actions
|-- db/
|   |-- database.py
|   |-- models.py
`-- ...
```

## Commandes utiles

```bash
# Tests
make test
make test-coverage

# Linting & format
make lint
make format

# Docker local
make docker-up
make docker-down
make docker-logs

# Monitoring local (optionnel)
make monitoring-up
make monitoring-down

# Profiling ONNX
make profiling

# Cloud Run (après setup initial)
make gcp-setup GCP_PROJECT_ID=... GITHUB_OWNER=...
make gcp-logs GCP_PROJECT_ID=...
make gcp-status GCP_PROJECT_ID=...
```

Si tu exécutes le setup GCP manuellement, utilise toujours `bash scripts/setup-gcp.sh ...` depuis Git Bash ou WSL; PowerShell ne lance pas correctement ce script `.sh`.

Voir [Makefile](Makefile) pour plus de commandes.

## Documentation

- [CICD_DOCUMENTATION.md](CICD_DOCUMENTATION.md) - Pipeline GitHub Actions détaillé
- [CLOUD_RUN_DEPLOYMENT.md](CLOUD_RUN_DEPLOYMENT.md) - Configuration Cloud Run
- [GCP_SETUP.md](GCP_SETUP.md) - Configuration GCP détaillée

Endpoints utiles

- `GET /` : etat API
- `GET /health` : sante service
- `GET /metrics` : metriques Prometheus
- `POST /predict/test-csv?page=1&page_size=100&income_multiplier=1.0`
- `POST /drift/run?sample_size=5000` : calcule un rapport drift et publie les gauges Prometheus
- `GET /drift/latest` : retourne le dernier rapport drift en memoire

Profiling et monitoring

- Profiling local (benchmark): `profiling/onnx_optimization.py`
- Monitoring runtime: `monitoring/monitoring_utils.py` + dashboard Grafana
- Le fichier `config.ini` permet d'activer/desactiver:
  - CPU profiling
  - Memory profiling
  - Latency profiling
  - Drift monitoring periodique (`[monitoring]`)

Prometheus + Grafana (Docker)

1. Lancer Prometheus

```bash
docker run -d -p 9090:9090 -v H:\python_project\projet08\prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus
```

2. Lancer Grafana

```bash
docker run -d -p 3000:3000 grafana/grafana
```

3. Configuration recommandee

- Dans `prometheus.yml`, cible FastAPI depuis Docker:
  - `host.docker.internal:8000` (ou IP locale machine)
- Datasource Grafana Prometheus:
  - `http://host.docker.internal:9090` ou `http://prometheus:9090` (si reseau/service Docker commun)
- Dashboard drift pret a importer: `monitoring/grafana_drift_dashboard.json`

Tests

```bash
uv run pytest -q
```

Notes

- La latence API totale inclut pre/post-traitements Pandas + serialisation JSON.
- Le temps d'inference ONNX est mesure separement via metrique histogramme.
- Les colonnes booleennes sont traitees correctement dans les scripts de monitoring/drift.
