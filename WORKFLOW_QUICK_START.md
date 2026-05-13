# 🎯 Guide d'Utilisation - Déclenchements du Pipeline

## 🎮 Accès au Déclenchement Manuel

```
GitHub.com
  ↓
Ton Repository
  ↓
Actions (onglet)
  ↓
CI/CD Pipeline - Test & Deploy to Cloud Run
  ↓
Run workflow (bouton blanc)
  ↓
Remplir les options
  ↓
Run workflow (vert)
```

## 📊 Déclenchements Automatiques

### 1️⃣ Push vers `main` (Production)
```bash
git commit -am "fix: bug fix"
git push origin main
```
**Résultat:** Tests + Build + Deploy automatiques (production live)

### 2️⃣ Push vers `develop` (Staging)
```bash
git commit -am "feat: new feature"
git push origin develop
```
**Résultat:** Tests + Build (pas de deploy)

### 3️⃣ Pull Request
```bash
git push origin feature/xyz
# Créer PR sur GitHub
```
**Résultat:** Tests uniquement (validation avant merge)

### 4️⃣ Tag Version (Release)
```bash
git tag v1.0.0
git push origin v1.0.0
```
**Résultat:** Tests + Build + Deploy (version spécifique)

## 🎮 Déclenchement Manuel (Workflow Dispatch)

### Scénario A: Valider les tests uniquement

**Quand:** Avant de merger une branche
**Durée:** ~6 minutes

```
Actions → Run workflow
  └─ Run tests: true
  └─ Run build: false
  └─ Run deploy: false
  └─ Target branch: main
```

### Scénario B: Build et test

**Quand:** Préparer une image sans déployer
**Durée:** ~14 minutes

```
Actions → Run workflow
  └─ Run tests: true
  └─ Run build: true
  └─ Run deploy: false
  └─ Target branch: main
```

### Scénario C: Déploiement complet

**Quand:** Déploiement manual (urgence, hotfix, etc.)
**Durée:** ~19 minutes

```
Actions → Run workflow
  └─ Run tests: true
  └─ Run build: true
  └─ Run deploy: true
  └─ Target branch: main
```
**Note:** Demande approbation avant le déploiement

### Scénario D: Déployer l'image actuelle

**Quand:** Déployer une image déjà built sans rebuild
**Durée:** ~5 minutes

```
Actions → Run workflow
  └─ Run tests: false
  └─ Run build: false
  └─ Run deploy: true
  └─ Target branch: main
```

## ✨ Flux Recommandé

```
1. Créer une branche feature
   git checkout -b feature/ma-feature develop
   
2. Faire les changements
   git add .
   git commit -m "feat: ma feature"
   
3. Pousser et créer une PR (auto-tests)
   git push origin feature/ma-feature
   # Créer PR vers develop sur GitHub
   
4. PR Reviews & Tests passent ✅
   
5. Merger vers develop
   # Tests + Build auto

6. Vérifier sur staging
   
7. Créer une PR develop→main
   # Tests auto

8. Reviews & Tests passent ✅
   
9. Merger vers main
   # Tests + Build + Deploy auto

10. Production live! 🎉
```

## 📋 Résultats des Jobs

### Test Job
```
✓ Install dependencies
✓ Run pytest - Data Utils
✓ Run pytest - ONNX Integration
✓ Run pytest - API Tests
✓ Upload coverage
```
**Durée:** ~5 minutes

### Profiling Job
```
✓ Load test data
✓ Profile ONNX model
✓ Optimize model
✓ Upload results
```
**Durée:** ~3 minutes (après tests)

### Build Job
```
✓ Authenticate GCP
✓ Build Docker image
✓ Push to GCR
✓ Scan vulnerabilities
✓ Upload metadata
```
**Durée:** ~8 minutes (après tests)

### Deploy Job
```
✓ Deploy to Cloud Run
✓ Wait for readiness
✓ Run smoke tests
✓ Verify deployment
```
**Durée:** ~5 minutes (après build)

## 🔔 Notifications

### En cas de succès
- ✅ Workflow badge tourne au vert
- ✅ Notification GitHub (si configurée)
- ✅ URL du service en logs

### En cas d'échec
- ❌ Badge rouge
- ❌ Email de notification (optionnel)
- ❌ Logs d'erreur disponibles dans Actions

## 🛑 Arrêter un Workflow en Cours

1. Aller sur **Actions**
2. Cliquer sur le run en cours
3. Cliquer sur **Cancel workflow** (haut à droite)

## 📊 Vérifier l'État du Déploiement

### Pendant le run
```
Actions → Cliquer sur le run
  └─ Voir tous les jobs en temps réel
```

### Après le run
```bash
# Vérifier que le service est live
curl https://projet08-api-xxxxx.a.run.app/health

# Voir les logs
gcloud run logs read projet08-api --follow --region=europe-west1

# Vérifier le statut
gcloud run services describe projet08-api --region=europe-west1
```

## 🆘 Troubleshooting

### "Workflow doesn't appear in Actions tab"
- Vérifier que le fichier `.github/workflows/ci-cd.yml` existe
- Vérifier la syntaxe YAML (pas de tabs, indentation correcte)
- Attendre quelques minutes après le push

### "Run workflow button is greyed out"
- Workflows ne peut se déclencher que depuis `main` ou `develop`
- Aller sur une de ces branches avant de cliquer

### "Tests fail"
- Voir les logs: Actions → Cliquer sur le job → Voir l'erreur
- Reproduire localement: `make test`

### "Build fails"
- Vérifier que Dockerfile est correct
- Vérifier que toutes les dépendances sont dans `pyproject.toml`
- Tester localement: `docker build -f docker/Dockerfile .`

### "Deploy fails"
- Vérifier les secrets GCP
- Vérifier que la base de données est accessible
- Voir les logs Cloud Run: `gcloud run logs read projet08-api`

## 📚 Ressources

- [CI/CD Documentation](CICD_DOCUMENTATION.md) - Pipeline détaillé
- [Cloud Run Deployment](CLOUD_RUN_DEPLOYMENT.md) - Configuration Cloud Run
- [Workflow Advanced](WORKFLOW_TRIGGERS.md) - Options avancées
- [GCP Setup](GCP_SETUP.md) - Configuration GCP

## 🎯 À Retenir

| Action | Résultat |
|--------|----------|
| `git push origin main` | Auto: test→build→deploy |
| `git push origin develop` | Auto: test→build |
| `git push origin feature` | Auto: test only |
| `Tag v1.0.0` | Auto: test→build→deploy |
| **Manual dispatch** | **Configurable** |

---

**Besoin d'aide?** Voir [WORKFLOW_TRIGGERS.md](WORKFLOW_TRIGGERS.md) pour plus de détails.
