# GitHub Actions Workflow - Advanced Triggers & Manual Controls

## 📋 Tableau des Déclenchements

| Trigger | Tests | Build | Deploy | Notes |
|---------|-------|-------|--------|-------|
| **Push main** | ✅ | ✅ | ✅ | Automatique, déploie en production |
| **Push develop** | ✅ | ✅ | ❌ | Automatique, teste et build seulement |
| **Tag v\*.\*.\*** | ✅ | ✅ | ✅ | Automatique (release), déploie |
| **Pull Request** | ✅ | ❌ | ❌ | Tests uniquement, pas de build |
| **Manual Dispatch** | 🎮 | 🎮 | 🎮 | Contrôle total, configurable |

## 🎮 Déclenchement Manuel (Workflow Dispatch)

### Accès à l'interface manuelle

1. Aller sur: **GitHub** → **Actions** → **CI/CD Pipeline - Test & Deploy to Cloud Run**
2. Cliquer sur **Run workflow** (bouton blanc en haut à droite)
3. Un formulaire apparaît avec des options configurables

### Options disponibles

```yaml
1. Run tests
   Options: true / false
   Default: true
   
2. Run build
   Options: true / false
   Default: true
   
3. Run deploy
   Options: true / false
   Default: false (prudent, demande approbation)
   
4. Target branch
   Options: main / develop
   Default: main
```

### Scénarios courants

#### Scénario 1: Tester uniquement (sans build)
```
- Run tests: true
- Run build: false
- Run deploy: false
```
**Temps:** ~6 minutes
**Usage:** Valider les tests sans toucher à l'image

#### Scénario 2: Tests + Build (pas de déploiement)
```
- Run tests: true
- Run build: true
- Run deploy: false
```
**Temps:** ~14 minutes
**Usage:** Préparer une nouvelle image, attendre avant de déployer

#### Scénario 3: Pipeline complet
```
- Run tests: true
- Run build: true
- Run deploy: true
```
**Temps:** ~19 minutes
**Usage:** Déploiement complet sur production

#### Scénario 4: Déployer une image existante
```
- Run tests: false
- Run build: false
- Run deploy: true
```
**Temps:** ~5 minutes
**Usage:** Déployer l'image actuelle sans rebuild

## 🏷️ Tags et Versions

### Créer une release
```bash
# Create and push a version tag
git tag v1.0.0
git push origin v1.0.0
```

Le workflow se déclenche automatiquement:
1. Tests ✅
2. Build ✅
3. Deploy ✅

L'image est taguée avec la version: `gcr.io/project/projet08-api:v1.0.0`

### Voir les tags
```bash
# List all tags
git tag

# List recent tags with info
git log --oneline --decorate | head -10
```

## 🔐 Approbations et Environnements

### Protection de l'environnement production

L'environnement `production` requiert une approbation manuelle avant le déploiement.

Pour configurer:
1. **Settings** → **Environments** → **production**
2. Cocher: "Required reviewers"
3. Ajouter les reviewers qui peuvent approuver

Lors d'un déploiement, une notification d'approbation est envoyée.

## 📊 Suivi et Monitoring

### Pendant l'exécution

1. Aller sur **Actions** tab
2. Cliquer sur le run en cours
3. Voir les logs de chaque job en temps réel

### Après exécution

**Logs détaillés:**
- Actions → Run → Cliquer sur un job
- Chaque étape affiche ses logs complets

**Résumé:**
- Tests: couverture de code, résultats des tests
- Build: taille de l'image, scan de vulnérabilités
- Deploy: URL du service, résultats des smoke tests

## 🛠️ Dépannage

### Le workflow ne s'exécute pas

**Cause 1:** Secrets GCP manquants
```
❌ Error: Unable to authenticate
```
Solution: Vérifier les secrets dans Settings → Secrets

**Cause 2:** Permissions insuffisantes
```
❌ Error: Permission denied
```
Solution: Vérifier les rôles IAM du service account GCP

### Le build échoue

```
❌ Docker build failed
```
Vérifier:
1. Dockerfile est correct
2. Toutes les dépendances sont dans `pyproject.toml`
3. Les fichiers source existent

### Le déploiement échoue

```
❌ Cloud Run deployment failed
```
Vérifier:
1. Image est poussée à GCR
2. Base de données est accessible
3. Modèle ONNX existe dans l'image

## 📝 Conditions Avancées

### Conditions dans le YAML

```yaml
# Exécuter uniquement si c'est un push sur main
if: github.event_name == 'push' && github.ref == 'refs/heads/main'

# Exécuter uniquement sur les tags
if: startsWith(github.ref, 'refs/tags/v')

# Exécuter sauf sur les PRs
if: github.event_name != 'pull_request'

# Combiner plusieurs conditions
if: |
  (github.event_name == 'push' && github.ref == 'refs/heads/main') ||
  (github.event_name == 'workflow_dispatch' && github.event.inputs.run_deploy == 'true')
```

## 🚀 Bonnes Pratiques

### 1. Toujours tester localement d'abord
```bash
make test
make lint
```

### 2. Utiliser les branches de développement
```bash
git checkout -b feature/my-feature develop
# Faire les changements
git push origin feature/my-feature
# Créer une PR vers develop
```

### 3. Tester sur develop avant main
- PRs vers `develop`: tests uniquement
- Merge vers `develop`: tests + build
- PRs vers `main`: tests uniquement
- Merge vers `main`: déploiement auto complet

### 4. Utiliser les tags pour les releases
```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```

### 5. Monitorer les déploiements
```bash
# Voir les logs du service
gcloud run logs read projet08-api --follow

# Vérifier le statut
gcloud run services describe projet08-api --region=europe-west1
```

## 🔄 Variables d'Environnement

### GitHub Context Variables

```yaml
# Branch/tag names
github.ref           # refs/heads/main, refs/tags/v1.0.0
github.ref_name      # main, v1.0.0
github.sha           # commit SHA

# Event info
github.event_name    # push, pull_request, workflow_dispatch
github.actor         # username qui a déclenché

# Workflow inputs (dispatch only)
github.event.inputs.run_tests
github.event.inputs.run_build
github.event.inputs.run_deploy
```

## 📋 Checklist Avant Production

- [ ] Tests passent localement: `make test`
- [ ] Linting OK: `make lint`
- [ ] Dockerfile fonctionne: `docker build ...`
- [ ] Base de données est accessible
- [ ] Modèle ONNX existe: `ls model/artifacts/model.onnx`
- [ ] Secrets GCP configurés
- [ ] Environnement production protégé
- [ ] Tests Cloud Run réussis après déploiement

## 📚 Ressources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Context Variables](https://docs.github.com/en/actions/learn-github-actions/contexts)
- [Environments](https://docs.github.com/en/actions/deployment/targeting-different-environments)
