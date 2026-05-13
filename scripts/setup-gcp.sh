#!/bin/bash
set -euo pipefail

# ---------------------------
# CONFIG
# ---------------------------
PROJECT_ID="${1:-}"
GITHUB_OWNER="${2:-}"
GITHUB_REPO="${3:-projet08}"

SERVICE_ACCOUNT_NAME="github-actions-sa"
WORKLOAD_POOL="github-actions-pool"
WORKLOAD_PROVIDER="github-provider"

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------------------------
# Helper Functions
# ---------------------------
info() { echo -e "${BLUE}ℹ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}! $1${NC}"; }

# ---------------------------
# MAIN
# ---------------------------

# 1️⃣ Choix du projet
info "Setting GCP project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# 2️⃣ Activer les API
info "Enabling required APIs..."
gcloud services enable \
    iam.googleapis.com \
    cloudresourcemanager.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    serviceusage.googleapis.com \
    >/dev/null

# 3️⃣ Créer service account
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
if gcloud iam service-accounts list --format="value(email)" | grep -q "$SA_EMAIL"; then
    warn "Service account exists"
else
    gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
        --display-name "GitHub Actions CI/CD"
    success "Service account created"
fi

# 4️⃣ Ajouter les rôles
info "Adding IAM roles..."
ROLES=(roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer roles/cloudbuild.builds.editor)
for role in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$role" >/dev/null
done
success "Roles added"

# 5️⃣ Créer Workload Identity Pool
if gcloud iam workload-identity-pools describe "$WORKLOAD_POOL" --location=global >/dev/null 2>&1; then
    warn "Workload Identity Pool exists"
else
    gcloud iam workload-identity-pools create "$WORKLOAD_POOL" \
        --location=global \
        --display-name "GitHub Actions Pool"
    success "Pool created"
fi

# 6️⃣ Créer Workload Identity Provider
POOL_FULL="projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/$WORKLOAD_POOL"

if gcloud iam workload-identity-pools providers describe "$WORKLOAD_PROVIDER" \
    --location=global \
    --workload-identity-pool="$POOL_FULL" >/dev/null 2>&1; then
    warn "Provider already exists"
else
    info "Creating Workload Identity Provider..."
    gcloud iam workload-identity-pools providers create-oidc "$WORKLOAD_PROVIDER" \
        --location=global \
        --workload-identity-pool="$POOL_FULL" \
        --display-name "GitHub Provider" \
        --issuer-uri "https://token.actions.githubusercontent.com" \
        --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
        --attribute-condition "assertion.repository=='${GITHUB_OWNER}/${GITHUB_REPO}'"
    success "Provider created"
fi

# 7️⃣ Lier service account au provider
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
    --role "roles/iam.workloadIdentityUser" \
    --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WORKLOAD_POOL}/attribute.repository/${GITHUB_OWNER}/${GITHUB_REPO}" >/dev/null
success "Service account binding done"

# 8️⃣ Résumé
echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo "GitHub Secrets to add:"
echo "GCP_PROJECT_ID=$PROJECT_ID"
echo "GCP_SERVICE_ACCOUNT=$SA_EMAIL"
echo ""
echo "Workload Identity Provider:"
echo "$POOL_FULL/providers/$WORKLOAD_PROVIDER"