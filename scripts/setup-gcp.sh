#!/bin/bash

###############################################################################
# Google Cloud Run CI/CD Setup Script
# 
# This script automates the setup of Workload Identity Federation and 
# service account configuration for GitHub Actions CI/CD deployment.
#
# Usage: ./setup-gcp.sh <project-id> <github-owner> <github-repo> [region]
###############################################################################

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${1:-}"
GITHUB_OWNER="${2:-}"
GITHUB_REPO="${3:-projet08}"
GCP_REGION="${4:-europe-west1}"

SERVICE_ACCOUNT_NAME="github-actions-sa"
WORKLOAD_IDENTITY_POOL_ID="github-actions-pool"
WORKLOAD_IDENTITY_PROVIDER_ID="github-provider"

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo ""
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===================================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}! $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    if ! command -v gcloud &> /dev/null; then
        print_error "gcloud CLI not found. Please install it from https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    print_success "gcloud CLI is installed"
    
    if ! command -v git &> /dev/null; then
        print_error "git not found"
        exit 1
    fi
    print_success "git is installed"
}

validate_inputs() {
    print_header "Validating Inputs"
    
    if [ -z "$PROJECT_ID" ]; then
        print_error "PROJECT_ID is required"
        echo "Usage: $0 <project-id> <github-owner> [github-repo] [region]"
        exit 1
    fi
    
    if [ -z "$GITHUB_OWNER" ]; then
        print_error "GITHUB_OWNER is required"
        echo "Usage: $0 <project-id> <github-owner> [github-repo] [region]"
        exit 1
    fi
    
    print_info "Project ID: $PROJECT_ID"
    print_info "GitHub Owner: $GITHUB_OWNER"
    print_info "GitHub Repo: $GITHUB_REPO"
    print_info "GCP Region: $GCP_REGION"
    
    print_success "All inputs validated"
}

set_gcp_project() {
    print_header "Setting GCP Project"
    
    gcloud config set project $PROJECT_ID
    print_success "GCP project set to $PROJECT_ID"
    
    CURRENT_PROJECT=$(gcloud config get-value project)
    if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
        print_error "Failed to set project"
        exit 1
    fi
}

enable_apis() {
    print_header "Enabling Required APIs"
    
    APIS=(
        "iap.googleapis.com"
        "cloudresourcemanager.googleapis.com"
        "iam.googleapis.com"
        "containerregistry.googleapis.com"
        "artifactregistry.googleapis.com"
        "run.googleapis.com"
    )
    
    for api in "${APIS[@]}"; do
        print_info "Enabling $api..."
        gcloud services enable $api --project=$PROJECT_ID || print_warning "Could not enable $api"
    done
    
    print_success "APIs enabled"
}

create_service_account() {
    print_header "Creating Service Account"
    
    SA_EXISTS=$(gcloud iam service-accounts list --project=$PROJECT_ID \
        --filter="email:$SERVICE_ACCOUNT_NAME@*.iam.gserviceaccount.com" \
        --format='value(email)' || echo "")
    
    if [ -n "$SA_EXISTS" ]; then
        print_warning "Service account $SA_EXISTS already exists"
        SERVICE_ACCOUNT_EMAIL="$SA_EXISTS"
    else
        print_info "Creating service account $SERVICE_ACCOUNT_NAME..."
        gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
            --project=$PROJECT_ID \
            --display-name="Service account for GitHub Actions CI/CD"
        
        SERVICE_ACCOUNT_EMAIL=$(gcloud iam service-accounts list \
            --project=$PROJECT_ID \
            --filter="displayName:Service account for GitHub Actions CI/CD" \
            --format='value(email)')
        
        print_success "Service account created: $SERVICE_ACCOUNT_EMAIL"
    fi
}

add_iam_bindings() {
    print_header "Adding IAM Bindings"
    
    ROLES=(
        "roles/run.admin"
        "roles/storage.admin"
        "roles/iam.serviceAccountUser"
        "roles/artifactregistry.writer"
        "roles/cloudbuild.builds.editor"
    )
    
    for role in "${ROLES[@]}"; do
        print_info "Adding $role..."
        gcloud projects add-iam-policy-binding $PROJECT_ID \
            --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL" \
            --role="$role" \
            --quiet > /dev/null 2>&1 || print_warning "Could not add $role"
    done
    
    print_success "IAM bindings added"
}

create_workload_identity_pool() {
    print_header "Creating Workload Identity Pool"
    
    POOL_EXISTS=$(gcloud iam workload-identity-pools list \
        --project=$PROJECT_ID \
        --location=global \
        --filter="displayName:GitHub" \
        --format='value(name)' || echo "")
    
    if [ -n "$POOL_EXISTS" ]; then
        print_warning "Workload Identity Pool already exists: $POOL_EXISTS"
        WORKLOAD_IDENTITY_POOL="$POOL_EXISTS"
    else
        print_info "Creating workload identity pool..."
        gcloud iam workload-identity-pools create $WORKLOAD_IDENTITY_POOL_ID \
            --project=$PROJECT_ID \
            --location=global \
            --display-name="GitHub Actions Pool" \
            --disabled=false \
            --quiet
        
        WORKLOAD_IDENTITY_POOL=$(gcloud iam workload-identity-pools describe \
            $WORKLOAD_IDENTITY_POOL_ID \
            --project=$PROJECT_ID \
            --location=global \
            --format='value(name)')
        
        print_success "Workload Identity Pool created"
    fi
}

create_workload_identity_provider() {
    print_header "Creating Workload Identity Provider"
    
    PROVIDER_EXISTS=$(gcloud iam workload-identity-pools providers list \
        --project=$PROJECT_ID \
        --location=global \
        --workload-identity-pool=$WORKLOAD_IDENTITY_POOL_ID \
        --filter="displayName:GitHub" \
        --format='value(name)' || echo "")
    
    if [ -n "$PROVIDER_EXISTS" ]; then
        print_warning "Workload Identity Provider already exists: $PROVIDER_EXISTS"
        WORKLOAD_IDENTITY_PROVIDER="$PROVIDER_EXISTS"
    else
        print_info "Creating workload identity provider..."
        gcloud iam workload-identity-pools providers create-oidc $WORKLOAD_IDENTITY_PROVIDER_ID \
            --project=$PROJECT_ID \
            --location=global \
            --workload-identity-pool=$WORKLOAD_IDENTITY_POOL_ID \
            --display-name="GitHub Provider" \
            --attribute-mapping='google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner' \
            --issuer-uri=https://token.actions.githubusercontent.com \
            --attribute-condition="assertion.repository_owner == '${GITHUB_OWNER}'" \
            --disabled=false \
            --quiet
        
        WORKLOAD_IDENTITY_PROVIDER=$(gcloud iam workload-identity-pools providers describe \
            $WORKLOAD_IDENTITY_PROVIDER_ID \
            --project=$PROJECT_ID \
            --location=global \
            --workload-identity-pool=$WORKLOAD_IDENTITY_POOL_ID \
            --format='value(name)')
        
        print_success "Workload Identity Provider created"
    fi
}

configure_service_account_impersonation() {
    print_header "Configuring Service Account Impersonation"
    
    print_info "Allowing GitHub to impersonate service account..."
    
    gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL \
        --project=$PROJECT_ID \
        --role="roles/iam.workloadIdentityUser" \
        --subject="principalSet://iam.googleapis.com/projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/$WORKLOAD_IDENTITY_POOL_ID/attribute.repository/$GITHUB_OWNER/$GITHUB_REPO" \
        --quiet > /dev/null 2>&1
    
    print_success "Service account impersonation configured"
}

display_summary() {
    print_header "Configuration Complete!"
    
    echo -e "${GREEN}Add these secrets to your GitHub repository:${NC}"
    echo ""
    echo "Go to: https://github.com/$GITHUB_OWNER/$GITHUB_REPO/settings/secrets/actions"
    echo ""
    echo "Add these repository secrets:"
    echo ""
    echo "Name: GCP_PROJECT_ID"
    echo "Value: $PROJECT_ID"
    echo ""
    echo "Name: GCP_SERVICE_ACCOUNT"
    echo "Value: $SERVICE_ACCOUNT_EMAIL"
    echo ""
    echo "Name: GCP_WORKLOAD_IDENTITY_PROVIDER"
    echo "Value: $WORKLOAD_IDENTITY_PROVIDER"
    echo ""
    echo "Name: CLOUD_RUN_DATABASE_URL"
    echo "Value: postgresql+asyncpg://user:password@host:5432/projet08"
    echo ""
    echo -e "${BLUE}Optional secrets (if needed):${NC}"
    echo ""
    echo "Name: GITHUB_TOKEN (auto-generated, usually already available)"
    echo ""
}

cleanup_on_error() {
    print_error "Setup failed. Please check the errors above and try again."
    exit 1
}

trap cleanup_on_error ERR

###############################################################################
# Main Execution
###############################################################################

main() {
    print_header "Google Cloud Run CI/CD Setup"
    
    check_prerequisites
    validate_inputs
    set_gcp_project
    enable_apis
    create_service_account
    add_iam_bindings
    create_workload_identity_pool
    create_workload_identity_provider
    configure_service_account_impersonation
    display_summary
    
    print_success "All steps completed successfully!"
    echo ""
}

main "$@"
