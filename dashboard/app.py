"""
Streamlit Dashboard – Credit Scoring & Monitoring.

Features
--------
1. **Client scoring** – select a client from the reference dataset,
   adjust features, send to the API and visualise the score.
2. **Feature importance** – global feature importance from the model.
3. **Data drift monitoring** – compare the reference distribution to the
   current (simulated) distribution using statistical tests.

Usage
-----
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import os
import sys

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Crédit Scoring Dashboard",
    page_icon="💳",
    layout="wide",
)

# Add project root to path so we can import monitoring module directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitoring.drift import compute_drift_report  # noqa: E402


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _api_get(path: str) -> dict | None:
    try:
        r = requests.get(f"{API_URL}{path}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"API call failed ({path}): {exc}")
        return None


def _api_post(path: str, payload: dict) -> dict | None:
    try:
        r = requests.post(f"{API_URL}{path}", json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"API call failed ({path}): {exc}")
        return None


@st.cache_data(ttl=300)
def get_client_ids() -> list[int]:
    data = _api_get("/clients?limit=100")
    return data["client_ids"] if data else []


@st.cache_data(ttl=300)
def get_client_features(client_id: int) -> dict | None:
    data = _api_get(f"/clients/{client_id}")
    return data["features"] if data else None


@st.cache_data(ttl=3600)
def get_feature_importance() -> pd.DataFrame:
    data = _api_get("/feature_importance")
    if data is None:
        return pd.DataFrame()
    return pd.DataFrame(data["feature_importance"])


@st.cache_data(ttl=3600)
def load_reference_data() -> pd.DataFrame | None:
    """Load training reference data directly from disk (for drift monitoring)."""
    data_path = os.path.join(os.path.dirname(__file__), "..", "model", "train_data.pkl")
    if not os.path.exists(data_path):
        return None
    df: pd.DataFrame = joblib.load(data_path)
    return df.drop(columns=["SK_ID_CURR"], errors="ignore")


def gauge_chart(probability: float) -> go.Figure:
    """Return a Plotly gauge figure for the probability of default."""
    score = int(round((1 - probability) * 1000))
    color = "green" if probability < 0.3 else ("orange" if probability < 0.5 else "red")
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=score,
            domain={"x": [0, 1], "y": [0, 1]},
            title={"text": "Score crédit (0 = très risqué, 1 000 = très sûr)"},
            delta={"reference": 500},
            gauge={
                "axis": {"range": [0, 1000]},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 400], "color": "#ffcccc"},
                    {"range": [400, 600], "color": "#fff3cc"},
                    {"range": [600, 1000], "color": "#ccffcc"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 4},
                    "thickness": 0.75,
                    "value": 500,
                },
            },
        )
    )
    fig.update_layout(height=300, margin=dict(t=50, b=20, l=20, r=20))
    return fig


# ---------------------------------------------------------------------------
# Sidebar – navigation
# ---------------------------------------------------------------------------

st.sidebar.title("💳 Crédit Scoring")
page = st.sidebar.radio(
    "Navigation",
    ["Scoring Client", "Importance des variables", "Monitoring dérive"],
)
st.sidebar.markdown("---")
health = _api_get("/health")
if health and health.get("status") == "ok":
    st.sidebar.success("✅ API connectée")
else:
    st.sidebar.error("❌ API non disponible")

# ---------------------------------------------------------------------------
# Page 1 – Client scoring
# ---------------------------------------------------------------------------

if page == "Scoring Client":
    st.title("Scoring Client")
    st.markdown(
        "Sélectionnez un client dans le jeu de données de référence ou "
        "saisissez manuellement ses caractéristiques, puis obtenez sa "
        "probabilité de défaut et la décision de crédit."
    )

    client_ids = get_client_ids()
    if not client_ids:
        st.error("Aucun client disponible (API non connectée ou modèle non chargé).")
        st.stop()

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_id = st.selectbox("Identifiant client", client_ids)
        features = get_client_features(selected_id)

        if features is None:
            st.warning("Impossible de récupérer les données client.")
            st.stop()

        st.subheader("Paramètres client")
        amt_income = st.number_input(
            "Revenus annuels (€)", value=float(features.get("AMT_INCOME_TOTAL", 135000)), step=1000.0
        )
        amt_credit = st.number_input(
            "Montant du crédit (€)", value=float(features.get("AMT_CREDIT", 406597)), step=1000.0
        )
        amt_annuity = st.number_input(
            "Annuité (€)", value=float(features.get("AMT_ANNUITY", 24700)), step=100.0
        )
        days_birth = st.slider(
            "Âge (années)", min_value=18, max_value=70,
            value=abs(int(features.get("DAYS_BIRTH", -12005))) // 365,
        )
        days_employed = st.slider(
            "Ancienneté emploi (années)", min_value=0, max_value=40,
            value=min(40, abs(int(features.get("DAYS_EMPLOYED", -2329))) // 365),
        )
        ext2 = st.slider("Score externe 2", 0.0, 1.0, float(features.get("EXT_SOURCE_2", 0.6)), step=0.01)
        ext3 = st.slider("Score externe 3", 0.0, 1.0, float(features.get("EXT_SOURCE_3", 0.7)), step=0.01)
        cnt_children = st.number_input("Nombre d'enfants", min_value=0, max_value=10, value=int(features.get("CNT_CHILDREN", 0)))
        gender = st.selectbox("Genre", ["Femme", "Homme"])
        own_car = st.checkbox("Possède une voiture", value=bool(features.get("FLAG_OWN_CAR", 0)))
        own_realty = st.checkbox("Possède un bien immobilier", value=bool(features.get("FLAG_OWN_REALTY", 1)))

        predict_btn = st.button("Calculer le score", type="primary")

    with col2:
        if predict_btn:
            payload = {
                "AMT_INCOME_TOTAL": amt_income,
                "AMT_CREDIT": amt_credit,
                "AMT_ANNUITY": amt_annuity,
                "DAYS_BIRTH": -(days_birth * 365),
                "DAYS_EMPLOYED": -(days_employed * 365) if days_employed > 0 else -1,
                "CODE_GENDER": 1 if gender == "Homme" else 0,
                "FLAG_OWN_CAR": int(own_car),
                "FLAG_OWN_REALTY": int(own_realty),
                "CNT_CHILDREN": cnt_children,
                "AMT_GOODS_PRICE": float(features.get("AMT_GOODS_PRICE", amt_credit * 0.85)),
                "REGION_POPULATION_RELATIVE": float(features.get("REGION_POPULATION_RELATIVE", 0.02)),
                "DAYS_REGISTRATION": int(features.get("DAYS_REGISTRATION", -3648)),
                "EXT_SOURCE_2": ext2,
                "EXT_SOURCE_3": ext3,
            }

            result = _api_post("/predict", payload)

            if result:
                prob = result["probability_of_default"]
                decision = result["decision"]
                threshold = result["threshold"]

                st.plotly_chart(gauge_chart(prob), use_container_width=True)

                if decision == "approved":
                    st.success(f"✅ Crédit **ACCORDÉ** (probabilité de défaut : {prob:.1%})")
                else:
                    st.error(f"❌ Crédit **REFUSÉ** (probabilité de défaut : {prob:.1%})")

                st.caption(f"Seuil de décision : {threshold:.0%}")

                # Feature comparison table
                st.subheader("Données envoyées à l'API")
                st.json(payload)
        else:
            st.info("👈 Configurez les paramètres puis cliquez sur **Calculer le score**.")

# ---------------------------------------------------------------------------
# Page 2 – Feature importance
# ---------------------------------------------------------------------------

elif page == "Importance des variables":
    st.title("Importance globale des variables")
    st.markdown(
        "Ce graphique représente l'importance relative de chaque variable "
        "dans les prédictions du modèle LightGBM."
    )

    fi_df = get_feature_importance()
    if fi_df.empty:
        st.error("Impossible de récupérer l'importance des variables (API non disponible).")
    else:
        fi_df_sorted = fi_df.sort_values("importance")
        fig = go.Figure(
            go.Bar(
                x=fi_df_sorted["importance"],
                y=fi_df_sorted["feature"],
                orientation="h",
                marker_color="steelblue",
            )
        )
        fig.update_layout(
            title="Importance des variables (normalisée)",
            xaxis_title="Importance relative",
            yaxis_title="Variable",
            height=500,
            margin=dict(l=200, r=20, t=60, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(fi_df.sort_values("importance", ascending=False).reset_index(drop=True))

# ---------------------------------------------------------------------------
# Page 3 – Data drift monitoring
# ---------------------------------------------------------------------------

elif page == "Monitoring dérive":
    st.title("Monitoring de la dérive des données")
    st.markdown(
        "Comparaison entre la distribution de référence (données d'entraînement) "
        "et une distribution courante simulée. "
        "Les tests statistiques utilisés sont :\n"
        "- **Kolmogorov-Smirnov** pour les variables continues\n"
        "- **Chi²** pour les variables catégorielles"
    )

    reference_df = load_reference_data()
    if reference_df is None:
        st.error(
            "Données de référence non disponibles. "
            "Lancez `python -m model.train_model` pour les générer."
        )
        st.stop()

    # Simulate current data with slight distributional shift
    st.subheader("Simulation de dérive")
    drift_intensity = st.slider(
        "Intensité de la dérive simulée", min_value=0.0, max_value=1.0, value=0.2, step=0.05
    )

    rng = np.random.default_rng(2024)
    current_df = reference_df.copy()
    n = len(current_df)

    # Apply drift to a few continuous features
    current_df["EXT_SOURCE_2"] = np.clip(
        current_df["EXT_SOURCE_2"] - drift_intensity * rng.uniform(0, 0.3, n), 0, 1
    )
    current_df["AMT_INCOME_TOTAL"] = current_df["AMT_INCOME_TOTAL"] * (
        1 + drift_intensity * rng.normal(0.1, 0.05, n)
    )
    current_df["AMT_CREDIT"] = current_df["AMT_CREDIT"] * (
        1 + drift_intensity * rng.normal(0.05, 0.03, n)
    )

    report = compute_drift_report(reference_df, current_df)

    col1, col2, col3 = st.columns(3)
    col1.metric("Données de référence", f"{report['n_reference']:,}")
    col2.metric("Données courantes", f"{report['n_current']:,}")
    col3.metric(
        "Variables avec dérive",
        f"{report['n_drifted']} / {len(report['features'])}",
        delta=f"{report['drift_share']:.0%}",
        delta_color="inverse",
    )

    st.subheader("Résultats par variable")
    rows = []
    for feat, res in report["features"].items():
        rows.append(
            {
                "Variable": feat,
                "Statistique": res.get("statistic"),
                "p-value": res.get("p_value"),
                "Dérive détectée": "⚠️ Oui" if res.get("drift_detected") else "✅ Non",
            }
        )
    result_df = pd.DataFrame(rows)
    st.dataframe(result_df, use_container_width=True)

    # Distribution plots for drifted features
    drifted_features = [
        f for f, r in report["features"].items() if r.get("drift_detected")
    ]
    if drifted_features:
        st.subheader("Distributions des variables avec dérive")
        for feat in drifted_features:
            fig = go.Figure()
            fig.add_trace(
                go.Histogram(
                    x=reference_df[feat],
                    name="Référence",
                    opacity=0.6,
                    histnorm="probability density",
                    marker_color="steelblue",
                )
            )
            fig.add_trace(
                go.Histogram(
                    x=current_df[feat],
                    name="Courant",
                    opacity=0.6,
                    histnorm="probability density",
                    marker_color="orange",
                )
            )
            fig.update_layout(
                title=f"Distribution : {feat}",
                barmode="overlay",
                height=300,
                margin=dict(t=50, b=30, l=30, r=30),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.success("Aucune dérive significative détectée avec l'intensité sélectionnée.")
