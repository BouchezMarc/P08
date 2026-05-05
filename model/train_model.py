"""
Credit scoring model training script.

Generates synthetic Home-Credit-like data and trains a LightGBM classifier.
The trained model pipeline and a sample of training data (for drift monitoring)
are saved to disk using joblib.

Usage:
    python -m model.train_model
"""

import os
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Feature definitions
# ---------------------------------------------------------------------------

NUMERIC_FEATURES = [
    "AMT_INCOME_TOTAL",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "DAYS_BIRTH",
    "DAYS_EMPLOYED",
    "CNT_CHILDREN",
    "AMT_GOODS_PRICE",
    "REGION_POPULATION_RELATIVE",
    "DAYS_REGISTRATION",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
]

BINARY_FEATURES = [
    "CODE_GENDER",  # 0 = F, 1 = M
    "FLAG_OWN_CAR",
    "FLAG_OWN_REALTY",
]

FEATURES = NUMERIC_FEATURES + BINARY_FEATURES

MODEL_PATH = os.path.join(os.path.dirname(__file__), "credit_model.pkl")
TRAIN_DATA_PATH = os.path.join(os.path.dirname(__file__), "train_data.pkl")


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

def generate_synthetic_data(n_samples: int = 2000, random_state: int = 42) -> pd.DataFrame:
    """Return a synthetic dataset that mimics Home Credit Default Risk data."""
    rng = np.random.default_rng(random_state)

    data: dict = {
        "AMT_INCOME_TOTAL": rng.lognormal(11.0, 0.5, n_samples),
        "AMT_CREDIT": rng.lognormal(12.0, 0.5, n_samples),
        "AMT_ANNUITY": rng.lognormal(9.0, 0.4, n_samples),
        "DAYS_BIRTH": -rng.integers(7000, 25000, n_samples),
        "DAYS_EMPLOYED": -rng.integers(0, 15000, n_samples),
        "CODE_GENDER": rng.choice([0, 1], n_samples),
        "FLAG_OWN_CAR": rng.choice([0, 1], n_samples),
        "FLAG_OWN_REALTY": rng.choice([0, 1], n_samples),
        "CNT_CHILDREN": rng.choice([0, 1, 2, 3], n_samples, p=[0.50, 0.25, 0.15, 0.10]),
        "AMT_GOODS_PRICE": rng.lognormal(11.5, 0.5, n_samples),
        "REGION_POPULATION_RELATIVE": rng.uniform(0.001, 0.090, n_samples),
        "DAYS_REGISTRATION": -rng.integers(0, 20000, n_samples),
        "EXT_SOURCE_2": rng.beta(3, 2, n_samples),
        "EXT_SOURCE_3": rng.beta(3, 2, n_samples),
    }

    # Target correlated with features (default risk).
    # Log-odds centered so that baseline default rate ≈ 15 %.
    log_odds = (
        -(data["EXT_SOURCE_2"] - 0.6) * 3.0   # normalised around mean
        - (data["EXT_SOURCE_3"] - 0.6) * 3.0  # normalised around mean
        + data["CNT_CHILDREN"] * 0.3
        - 1.5                                   # baseline offset → ~15 % default rate
    )
    prob = 1.0 / (1.0 + np.exp(-log_odds))
    data["TARGET"] = (rng.random(n_samples) < prob).astype(int)

    df = pd.DataFrame(data)
    # Assign integer IDs
    df.index = pd.RangeIndex(start=100000, stop=100000 + n_samples, name="SK_ID_CURR")
    return df


# ---------------------------------------------------------------------------
# Model pipeline
# ---------------------------------------------------------------------------

def build_pipeline() -> Pipeline:
    """Return an sklearn Pipeline with preprocessing and LightGBM classifier."""
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    binary_transformer = Pipeline(
        steps=[("imputer", SimpleImputer(strategy="most_frequent"))]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_FEATURES),
            ("bin", binary_transformer, BINARY_FEATURES),
        ]
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                LGBMClassifier(
                    n_estimators=200,
                    learning_rate=0.05,
                    max_depth=5,
                    num_leaves=31,
                    class_weight="balanced",
                    random_state=42,
                    verbose=-1,
                ),
            ),
        ]
    )
    return pipeline


# ---------------------------------------------------------------------------
# Train & save
# ---------------------------------------------------------------------------

def train_and_save() -> None:
    """Train the model on synthetic data and persist artefacts to disk."""
    print("Generating synthetic data …")
    df = generate_synthetic_data(n_samples=2000)

    X = df[FEATURES]
    y = df["TARGET"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("Training LightGBM pipeline …")
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred_proba = pipeline.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"ROC-AUC on test set: {auc:.4f}")

    # Persist artefacts
    model_data = {
        "pipeline": pipeline,
        "features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "binary_features": BINARY_FEATURES,
        "auc": auc,
    }
    joblib.dump(model_data, MODEL_PATH)
    print(f"Model saved to {MODEL_PATH}")

    # Save a sample of training data for drift monitoring (no labels)
    train_sample = X_train.copy()
    train_sample.reset_index(inplace=True)
    joblib.dump(train_sample, TRAIN_DATA_PATH)
    print(f"Training sample saved to {TRAIN_DATA_PATH}")


if __name__ == "__main__":
    train_and_save()
