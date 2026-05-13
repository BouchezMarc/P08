# Configuration Google Cloud Run pour CI/CD GitHub Actions

## Vue d'ensemble

Ce guide explique comment configurer le déploiement automatique sur Google Cloud Run via GitHub Actions.

## Architecture du Pipeline

```
GitHub Push (main) 
    ↓
Tests (pytest)
    ↓
Build Docker → Push à GCR
    ↓
Deploy à Cloud Run
    ↓
Smoke Tests
    ↓
Notification
```

## Prérequis

- Compte Google Cloud Platform (GCP) avec billing activé
- Projet GCP créé
- GitHub repository configuré
- Docker image correctement packagée

## Étape 1: Configuration du Service Account GCP

### 1.1 Créer un service account

```bash
# Remplacer PROJECT_ID par votre ID de projet GCP
export PROJECT_ID="your-gcp-project-id"
export SERVICE_ACCOUNT_NAME="github-actions-sa"

# Créer le service account
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --project=$PROJECT_ID \
  --display-name="Service account for GitHub Actions CI/CD"
```

### 1.2 Accorder les permissions nécessaires

```bash
# Get service account email
export SERVICE_ACCOUNT_EMAIL=$(gcloud iam service-accounts list \
  --project=$PROJECT_ID \
  --filter="displayName:$SERVICE_ACCOUNT_NAME" \
  --format='value(email)')

echo "Service Account Email: $SERVICE_ACCOUNT_EMAIL"

# Permissions pour Cloud Run
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/run.admin"

# Permissions pour Container Registry/Artifact Registry
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/storage.admin"

# Permissions pour service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/iam.serviceAccountUser"

# Permissions pour Cloud Build (optionnel)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/cloudbuild.builds.editor"

# Permissions pour Artifact Registry
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
  --role="roles/artifactregistry.writer"
```

## Étape 2: Configuration Workload Identity Federation

La Workload Identity Federation permet à GitHub Actions de s'authentifier à GCP sans clés API.

### 2.1 Activer les APIs nécessaires

```bash
gcloud services enable iap.googleapis.com \
  --project=$PROJECT_ID

gcloud services enable cloudresourcemanager.googleapis.com \
  --project=$PROJECT_ID

gcloud services enable iam.googleapis.com \
  --project=$PROJECT_ID
```

### 2.2 Créer Workload Identity Pool

```bash
export WORKLOAD_IDENTITY_POOL_ID="github-actions-pool"
export WORKLOAD_IDENTITY_POOL_DISPLAY_NAME="GitHub Actions Pool"

# Créer le pool
gcloud iam workload-identity-pools create $WORKLOAD_IDENTITY_POOL_ID \
  --project=$PROJECT_ID \
  --location=global \
  --display-name=$WORKLOAD_IDENTITY_POOL_DISPLAY_NAME \
  --disabled=false
```

### 2.3 Créer Workload Identity Provider

```bash
export WORKLOAD_IDENTITY_PROVIDER_ID="github-provider"
export GITHUB_OWNER="your-github-username-or-org"
export GITHUB_REPO="projet08"

# Créer le provider
gcloud iam workload-identity-pools providers create-oidc $WORKLOAD_IDENTITY_PROVIDER_ID \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$WORKLOAD_IDENTITY_POOL_ID \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner,attribute.aud=assertion.aud" \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-condition="assertion.repository_owner == '${GITHUB_OWNER}'" \
  --disabled=false
```

### 2.4 Configurer Service Account Impersonation

```bash
# Obtenir le Workload Identity Provider resource name
export WORKLOAD_IDENTITY_PROVIDER=$(gcloud iam workload-identity-pools providers \
  describe $WORKLOAD_IDENTITY_PROVIDER_ID \
  --workload-identity-pool=$WORKLOAD_IDENTITY_POOL_ID \
  --location=global \
  --project=$PROJECT_ID \
  --format='value(name)')

echo "Workload Identity Provider: $WORKLOAD_IDENTITY_PROVIDER"

# Configurer le service account pour accepter l'impersonation
gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --subject="principalSet://iam.googleapis.com/projects/${PROJECT_ID}/locations/global/workloadIdentityPools/${WORKLOAD_IDENTITY_POOL_ID}/attribute.repository/${GITHUB_OWNER}/${GITHUB_REPO}"
```

## Étape 3: Configurer les GitHub Secrets

Aller sur: `Settings` → `Secrets and variables` → `Actions`

Ajouter les secrets suivants:

### 3.1 GCP Project Configuration

- **GCP_PROJECT_ID**: Votre ID de projet GCP (ex: `my-project-id`)
- **GCP_WORKLOAD_IDENTITY_PROVIDER**: Le resource name du provider (ex: `projects/123456/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider`)
- **GCP_SERVICE_ACCOUNT**: Email du service account (ex: `github-actions-sa@my-project.iam.gserviceaccount.com`)

### 3.2 Database Configuration (Cloud Run)

- **CLOUD_RUN_DATABASE_URL**: URL de connexion à la base de données (ex: `postgresql+asyncpg://user:pass@host:5432/dbname`)

```bash
# Exemple pour obtenir les values:
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "GCP_WORKLOAD_IDENTITY_PROVIDER: $WORKLOAD_IDENTITY_PROVIDER"
echo "GCP_SERVICE_ACCOUNT: $SERVICE_ACCOUNT_EMAIL"
```

## Étape 4: Configuration Cloud Run

### 4.1 Vérifier que l'image Docker est prête

```bash
# Test local
docker build -f docker/Dockerfile -t projet08-api:local .
docker run -p 8000:8000 projet08-api:local

# Vérifier les endpoints
curl http://localhost:8000/health
curl http://localhost:8000/schema
```

### 4.2 Créer un artifact repository (optionnel)

```bash
gcloud artifacts repositories create projet08-repo \
  --repository-format=docker \
  --location=$GCP_REGION \
  --project=$PROJECT_ID \
  --description="Repository for projet08 API images"
```

### 4.3 Configurer variables d'environnement dans Cloud Run

Les variables d'environnement suivantes sont définis automatiquement par le workflow:

```yaml
DATABASE_URL: ${{ secrets.CLOUD_RUN_DATABASE_URL }}
ONNXRUNTIME_PROVIDERS: CPUExecutionProvider
```

Pour ajouter d'autres variables:
1. Éditer le job `deploy-cloud-run` dans `.github/workflows/ci-cd.yml`
2. Ajouter les variables dans `--set-env-vars`

## Étape 5: Tester le Pipeline

### 5.1 Test local du workflow

```bash
# Installer act (GitHub Actions local runner)
# https://github.com/nektos/act

# Créer un fichier .actrc avec les secrets
cat > .actrc << 'EOF'
-s GCP_PROJECT_ID=your-project-id
-s GCP_WORKLOAD_IDENTITY_PROVIDER=your-provider
-s GCP_SERVICE_ACCOUNT=your-sa@project.iam.gserviceaccount.com
-s CLOUD_RUN_DATABASE_URL=postgresql://user:pass@localhost/dbname
EOF

# Exécuter le workflow localement
act push --job=test
act push --job=build
act push --job=deploy-cloud-run
```

### 5.2 Déclencher manuellement

Aller sur: `Actions` → `CI/CD Pipeline - Test & Deploy to Cloud Run` → `Run workflow`

### 5.3 Vérifier le déploiement

```bash
# Voir le statut du service
gcloud run services describe projet08-api \
  --region=europe-west1 \
  --project=$PROJECT_ID

# Voir les logs
gcloud run logs read projet08-api \
  --region=europe-west1 \
  --limit=50 \
  --project=$PROJECT_ID

# Tester l'endpoint
export SERVICE_URL=$(gcloud run services describe projet08-api \
  --region=europe-west1 \
  --format='value(status.url)' \
  --project=$PROJECT_ID)

curl $SERVICE_URL/health
curl $SERVICE_URL/schema
```

## Monitoring et Maintenance

### Cloud Run Console

https://console.cloud.google.com/run

Voir:
- Revisions (versions déployées)
- Traffic split (routing entre versions)
- Logs
- Metrics (CPU, memory, request rate)

### Logs

```bash
# Voir les logs en temps réel
gcloud run logs read projet08-api --follow --project=$PROJECT_ID

# Filtrer par sévérité
gcloud run logs read projet08-api --project=$PROJECT_ID | grep ERROR
```

### Metrics

```bash
# Requêtes par minute
gcloud monitoring time-series list \
  --filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count"'

# Latence
gcloud monitoring time-series list \
  --filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_latencies"'
```

### Rollback à une version précédente

```bash
# Voir les revisions
gcloud run revisions list \
  --service=projet08-api \
  --region=europe-west1 \
  --project=$PROJECT_ID

# Diriger le trafic vers une ancienne revision
gcloud run services update-traffic projet08-api \
  --to-revisions=REVISION_NAME=100 \
  --region=europe-west1 \
  --project=$PROJECT_ID
```

## Troubleshooting

### Le workflow ne démarre pas

1. Vérifier que les secrets GCP sont configurés correctement
2. Vérifier que le repository permission permet les workflows
3. Vérifier que le fichier YAML est bien formaté

### Erreur d'authentification

```
Error: Unable to authenticate to service account
```

Solutions:
1. Vérifier le `GCP_WORKLOAD_IDENTITY_PROVIDER` dans les secrets
2. Vérifier que le service account a les bonnes permissions
3. Recréer le provider si nécessaire

### Image ne se pousse pas à GCR

```
Error: denied: Permission denied
```

Solutions:
1. Vérifier que le service account a `roles/storage.admin`
2. Vérifier que GCR est activé: `gcloud services enable containerregistry.googleapis.com`

### Cloud Run deployment fails

```
Error: Service is not ready yet
```

Solutions:
1. Vérifier que l'image est accessible depuis Cloud Run
2. Vérifier que la base de données est accessible
3. Voir les logs: `gcloud run logs read projet08-api`

### Smoke tests fail après déploiement

```
Error: Service returned 500
```

Solutions:
1. Vérifier que `CLOUD_RUN_DATABASE_URL` est correct
2. Vérifier les logs: `gcloud run logs read projet08-api --follow`
3. Tester manuellement le modèle ONNX est présent dans l'image

## Script de setup complet

```bash
#!/bin/bash
set -e

PROJECT_ID=${1:-"my-project-id"}
GITHUB_OWNER=${2:-"my-github-org"}
GITHUB_REPO=${3:-"projet08"}

echo "🔧 Setting up Google Cloud configuration for GitHub Actions"
echo "Project ID: $PROJECT_ID"
echo "GitHub: $GITHUB_OWNER/$GITHUB_REPO"

# 1. Create service account
SA_NAME="github-actions-sa"
gcloud iam service-accounts create $SA_NAME --project=$PROJECT_ID || echo "SA already exists"

SA_EMAIL=$(gcloud iam service-accounts list --project=$PROJECT_ID \
  --filter="displayName:$SA_NAME" --format='value(email)')

# 2. Add IAM bindings
for role in "roles/run.admin" "roles/storage.admin" "roles/iam.serviceAccountUser" "roles/artifactregistry.writer"; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$role" || true
done

# 3. Create Workload Identity Pool and Provider
POOL_ID="github-actions-pool"
PROVIDER_ID="github-provider"

gcloud iam workload-identity-pools create $POOL_ID \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions Pool" || echo "Pool already exists"

gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool=$POOL_ID \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub" \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-condition="assertion.repository_owner == '$GITHUB_OWNER'" || echo "Provider already exists"

# 4. Get resource names
PROVIDER=$(gcloud iam workload-identity-pools providers describe $PROVIDER_ID \
  --workload-identity-pool=$POOL_ID \
  --location=global \
  --project=$PROJECT_ID \
  --format='value(name)')

# 5. Configure service account impersonation
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --subject="principalSet://iam.googleapis.com/projects/$PROJECT_ID/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$GITHUB_OWNER/$GITHUB_REPO" || true

echo ""
echo "✅ Configuration complete!"
echo ""
echo "Add these secrets to your GitHub repository:"
echo "GCP_PROJECT_ID: $PROJECT_ID"
echo "GCP_SERVICE_ACCOUNT: $SA_EMAIL"
echo "GCP_WORKLOAD_IDENTITY_PROVIDER: $PROVIDER"
echo ""
```

Sauvegarder en `setup-gcp.sh` et exécuter:

```bash
chmod +x setup-gcp.sh
./setup-gcp.sh my-project-id my-github-org projet08
```

## Références

- [Google Cloud Run Documentation](https://cloud.google.com/run/docs)
- [GitHub Actions & Google Cloud](https://github.com/google-github-actions)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Container Registry](https://cloud.google.com/container-registry/docs)
