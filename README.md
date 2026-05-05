# P08 – Déploiement et Monitoring d'un Modèle de Scoring Crédit

Ce projet implémente le déploiement et le monitoring d'un modèle de scoring
crédit (prédiction du risque de défaut de paiement), conformément au projet
**P08** de la formation Data Scientist OpenClassrooms.

---

## Architecture

```
P08/
├── model/
│   ├── train_model.py      # Entraînement du modèle LightGBM
│   ├── credit_model.pkl    # Modèle entraîné (généré, non versionné)
│   └── train_data.pkl      # Données de référence (générées, non versionnées)
├── api/
│   └── app.py              # API FastAPI – serveur de prédictions
├── dashboard/
│   └── app.py              # Dashboard Streamlit – interface de visualisation
├── monitoring/
│   └── drift.py            # Détection de dérive statistique (KS / Chi²)
├── tests/
│   ├── conftest.py         # Fixtures pytest
│   ├── test_api.py         # Tests de l'API
│   └── test_model.py       # Tests du modèle et du monitoring
├── requirements.txt
└── README.md
```

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Démarrage rapide

### 1. Entraîner le modèle

```bash
python -m model.train_model
```

Cela génère :
- `model/credit_model.pkl` – pipeline sklearn + LightGBM sérialisé
- `model/train_data.pkl` – échantillon de données d'entraînement (référence pour le monitoring)

### 2. Lancer l'API

```bash
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

Documentation Swagger disponible sur : http://localhost:8000/docs

### 3. Lancer le Dashboard

```bash
streamlit run dashboard/app.py
```

Le dashboard se connecte automatiquement à `http://localhost:8000`.

---

## API – Endpoints principaux

| Méthode | Chemin                   | Description                                      |
|---------|--------------------------|--------------------------------------------------|
| GET     | `/health`                | Statut de l'API                                  |
| POST    | `/predict`               | Prédiction pour un client                        |
| POST    | `/predict/batch`         | Prédiction pour plusieurs clients                |
| GET     | `/feature_importance`    | Importance globale des variables                 |
| GET     | `/clients`               | Liste des clients de référence disponibles       |
| GET     | `/clients/{client_id}`   | Caractéristiques d'un client spécifique          |

---

## Dashboard – Pages

1. **Scoring Client** – Sélection d'un client, modification des paramètres,
   visualisation du score (jauge 0–1000) et décision de crédit.
2. **Importance des variables** – Graphique en barres de l'importance relative
   des variables dans les prédictions du modèle.
3. **Monitoring dérive** – Comparaison entre la distribution de référence et
   la distribution courante via des tests statistiques (KS pour les variables
   continues, Chi² pour les variables catégorielles).

---

## Tests

```bash
pytest tests/ -v
```

---

## Modèle

- **Algorithme** : LightGBM (classification binaire)
- **Prétraitement** : Imputation médiane + normalisation StandardScaler
- **Cible** : `TARGET` – 1 = défaut de paiement, 0 = remboursement correct
- **Seuil de décision** : 0.50 (probabilité de défaut)
- **Données** : Synthétiques (structure inspirée du dataset Home Credit Default Risk)

---

## Monitoring

Le module `monitoring/drift.py` détecte la dérive entre les données
d'entraînement et les données en production :
- **Test de Kolmogorov-Smirnov** pour les variables continues
- **Test du Chi²** pour les variables catégorielles
- Seuil de signification : α = 0.05
