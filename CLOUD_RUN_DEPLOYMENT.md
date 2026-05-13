# Déploiement Automatique sur Google Cloud Run

## Vue d'ensemble du Pipeline

```
Push vers GitHub (main)
        ↓
    1. Tests (pytest)
        ↓
    2. Build Docker → Google Container Registry (GCR)
        ↓
    3. Deploy à Cloud Run (API + Database)
        ↓
    4. Smoke Tests (vérification que l'API démarre)
        ↓
    ✅ Service Live!

Note: Prometheus & Grafana ne sont PAS déployés sur Cloud Run
      Ils restent locaux pour le développement
      Cloud Run expose ses propres métriques via GCP Monitoring
```

## Configuration rapide (5 minutes)

### Étape 1: Prérequis

```bash
# Installer Google Cloud CLI
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Créer un projet GCP
gcloud projects create projet08-prod --name="Projet 08 Production"

# Définir le projet par défaut
export PROJECT_ID="projet08-prod"
gcloud config set project $PROJECT_ID

# Activer la facturation (requis pour Cloud Run)
# Aller sur https://console.cloud.google.com/billing
```

### Étape 2: Configuration GCP automatique

```bash
# La script setup-gcp.sh automatise tout
bash scripts/setup-gcp.sh $PROJECT_ID my-github-username projet08

# Ou via make (plus simple)
make gcp-setup \
  GCP_PROJECT_ID=$PROJECT_ID \
  GITHUB_OWNER=my-github-username \
  GITHUB_REPO=projet08
```

### Étape 3: Ajouter les secrets GitHub

Après que le script complète, tu verras les valeurs à copier.

Aller sur: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Ajouter:
- `GCP_PROJECT_ID` → ID du projet GCP
- `GCP_SERVICE_ACCOUNT` → Email du service account
- `GCP_WORKLOAD_IDENTITY_PROVIDER` → Resource name du provider
- `CLOUD_RUN_DATABASE_URL` → Connection string PostgreSQL

```bash
# Exemple de DATABASE_URL (si tu utilises Cloud SQL)
postgresql+asyncpg://user:password@cloudsql-proxy-host:5432/projet08
```

### Étape 4: Déclencher le déploiement

```bash
# Option A: Push sur main (déclenche automatiquement)
git add .
git commit -m "feat: déploiement GCP"
git push origin main

# Option B: Déclencher manuellement
# Aller sur Actions → CI/CD Pipeline → Run workflow → main branch
```

## Architecture Cloud Run

### Configuration automatique du service

Le workflow configure Cloud Run avec:

```yaml
CPU: 1 vCPU
Memory: 2 GB
Timeout: 120 secondes
Min instances: 1 (toujours chaud)
Max instances: 100 (auto-scaling)
Port: 8000
Authentification: ❌ (public, peut être modifié)
```

### Variables d'environnement

```yaml
DATABASE_URL: ${{ secrets.CLOUD_RUN_DATABASE_URL }}
ONNXRUNTIME_PROVIDERS: CPUExecutionProvider
```

Pour ajouter d'autres variables:
1. Éditer `.github/workflows/ci-cd.yml`
2. Dans le job `deploy-cloud-run`, ajouter à `--set-env-vars`
3. Ou créer des secrets GCP et les référencer

## Monitoring après déploiement

### URL du service

```bash
# Récupérer l'URL
gcloud run services describe projet08-api \
  --region=europe-west1 \
  --format='value(status.url)'

# Tester l'API
curl https://projet08-api-xxxxx.a.run.app/health
curl https://projet08-api-xxxxx.a.run.app/schema
```

### Logs

```bash
# Affichage en temps réel
make gcp-logs GCP_PROJECT_ID=$PROJECT_ID

# Ou via gcloud
gcloud run logs read projet08-api --follow
```

### Métriques

```bash
# Voir le statut du service
make gcp-status GCP_PROJECT_ID=$PROJECT_ID

# Via console: https://console.cloud.google.com/run/detail/europe-west1/projet08-api
```

## Déploiement manuel (optionnel)

Si tu veux déployer manuellement sans attendre un push GitHub:

```bash
# 1. Build l'image localement
docker build -f docker/Dockerfile -t gcr.io/$PROJECT_ID/projet08-api:manual .

# 2. Push à GCR
docker push gcr.io/$PROJECT_ID/projet08-api:manual

# 3. Deploy
make gcp-deploy GCP_PROJECT_ID=$PROJECT_ID

# Ou manuellement:
gcloud run deploy projet08-api \
  --image=gcr.io/$PROJECT_ID/projet08-api:manual \
  --region=europe-west1 \
  --allow-unauthenticated \
  --memory=2Gi \
  --project=$PROJECT_ID
```

## Rollback à une version précédente

```bash
# Voir les revisions déployées
gcloud run revisions list --service=projet08-api --region=europe-west1

# Rediriger le trafic vers une ancienne revision
gcloud run services update-traffic projet08-api \
  --to-revisions=REVISION_NAME=100 \
  --region=europe-west1
```

## Scaling et coûts

### Configuration de scaling

```bash
# Augmenter les instances minimales (pour moins de cold starts)
gcloud run services update projet08-api \
  --min-instances=3 \
  --region=europe-west1

# Diminuer les instances maximales (pour contrôler les coûts)
gcloud run services update projet08-api \
  --max-instances=50 \
  --region=europe-west1
```

### Estimation des coûts

- **Compute**: ~$0.00002400/vCPU-second
- **Requests**: $0.40 par million de requests (gratuit jusqu'à 2M/mois)
- **Outbound data**: $0.12 par GB

Pour une API avec:
- 1 vCPU, 2 GB RAM
- 100k requests/jour
- Temps moyen: 500ms

Coût estimé: **~$50-100/mois** (avec free tier appliqué)

## Troubleshooting

### Pipeline échoue à l'authentification GCP

```
Error: Unable to authenticate
```

**Solution:**
1. Vérifier que les secrets sont configurés correctement
2. Vérifier le Workload Identity Provider dans GCP Console
3. Relancer le script setup: `bash scripts/setup-gcp.sh ...`

### Service retourne 502 Bad Gateway

```
Typical error after deployment
```

**Solution:**
1. Vérifier les logs: `make gcp-logs`
2. Vérifier que la BASE DE DONNÉES est accessible
3. Vérifier que le modèle ONNX existe dans l'image
4. Vérifier les variables d'environnement

### Cloud Run service est "Updating" depuis longtemps

```
Status: Updating for >5 minutes
```

**Solution:**
1. Aller sur [Cloud Run Console](https://console.cloud.google.com/run)
2. Cliquer sur le service
3. Arrêter le déploiement ou attendre (timeout après 30 min)
4. Voir les logs pour trouver l'erreur

### Image trop grande

```
Error: Image exceeds size limit
```

**Solution:**
1. Réduire la taille de l'image (utiliser slim Python base)
2. Exclure les fichiers inutiles via `.dockerignore`
3. Utiliser un registre privé pour les gros artifacts

## Sécurité

### Recommandations

1. **Authentification du service**
   ```bash
   # Désactiver l'accès public si possible
   gcloud run services update projet08-api \
     --no-allow-unauthenticated \
     --region=europe-west1
   
   # Puis utiliser des identity tokens pour appeler l'API
   ```

2. **Private Cloud Run (VPC)**
   ```bash
   # Déployer dans un VPC privé
   gcloud run deploy projet08-api \
     --vpc-connector=my-connector \
     --region=europe-west1
   ```

3. **Secrets GCP**
   ```bash
   # Utiliser Secret Manager au lieu de variables d'env
   gcloud secrets create db-password --data-file=-
   
   # Référencer dans Cloud Run
   gcloud run deploy projet08-api \
     --set-secrets="DB_PASSWORD=db-password:latest"
   ```

## CI/CD avancé

### Deploy vers un environnement de staging d'abord

Modifier `.github/workflows/ci-cd.yml`:

```yaml
deploy-staging:
  # Déployer vers staging sur develop branch
  if: github.ref == 'refs/heads/develop'
  # Configuration Cloud Run pour staging
  
deploy-production:
  # Déployer vers prod sur main branch
  if: github.ref == 'refs/heads/main'
  needs: deploy-staging
```

### Approval manual avant production

```yaml
deploy-production:
  needs: test
  environment: production  # Ajoute une approbation manuelle
```

### Notification Slack/Discord

```yaml
- name: Notify Slack
  uses: slackapi/slack-github-action@v1
  with:
    webhook-url: ${{ secrets.SLACK_WEBHOOK }}
    payload: |
      {
        "text": "✅ Deployment successful",
        "blocks": [...]
      }
```

## Documentation complète

Pour plus de détails, voir:
- [GCP_SETUP.md](GCP_SETUP.md) - Configuration détaillée
- [CICD_DOCUMENTATION.md](CICD_DOCUMENTATION.md) - Pipeline GitHub Actions
- [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) - Workflow complet

## Résumé des commandes utiles

```bash
# Configuration
make gcp-setup GCP_PROJECT_ID=... GITHUB_OWNER=...

# Monitoring
make gcp-logs GCP_PROJECT_ID=...
make gcp-status GCP_PROJECT_ID=...

# Déploiement manuel
make gcp-deploy GCP_PROJECT_ID=...

# Logs locaux du workflow
# Via GitHub Actions UI: Actions → CI/CD Pipeline → Latest run
```

## Questions fréquentes

**Q: Combien de temps prend le déploiement?**
A: ~5-10 minutes (tests + build + deploy)

**Q: Puis-je déployer vers plusieurs régions?**
A: Oui, dupliquer le job `deploy-cloud-run` avec différentes régions

**Q: Puis-je garder plusieurs versions actives?**
A: Oui, Cloud Run gère les revisions automatiquement, tu peux router le trafic

**Q: Comment déployer depuis une branche PR?**
A: Ajouter une condition dans le workflow pour les PRs (requiert approbation)

---

Besoin d'aide? Voir [GCP_SETUP.md](GCP_SETUP.md) pour une configuration pas à pas.
