"""
FastAPI application – Credit Scoring API.

Endpoints
---------
GET  /health                  – Health check
POST /predict                 – Predict default probability for one client
POST /predict/batch           – Predict for multiple clients
GET  /feature_importance      – Global feature importance from the model
GET  /clients                 – List available sample clients (from train data)
GET  /clients/{client_id}     – Return feature values for a specific client

Usage
-----
    uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Paths (can be overridden via environment variables)
# ---------------------------------------------------------------------------
_DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "credit_model.pkl")
_DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "model", "train_data.pkl")

MODEL_PATH = os.environ.get("MODEL_PATH", _DEFAULT_MODEL_PATH)
DATA_PATH = os.environ.get("DATA_PATH", _DEFAULT_DATA_PATH)

# Loaded at startup
_model_data: dict = {}
_train_df: Optional[pd.DataFrame] = None


def load_model() -> None:
    """Load the model and training reference data into memory."""
    global _model_data, _train_df

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError(
            f"Model file not found: {MODEL_PATH}. "
            "Run `python -m model.train_model` first."
        )
    _model_data = joblib.load(MODEL_PATH)

    if os.path.exists(DATA_PATH):
        _train_df = joblib.load(DATA_PATH)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """Load model artefacts at startup."""
    load_model()
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Credit Scoring API",
    description="Prédiction du risque de défaut de paiement (scoring crédit).",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ClientFeatures(BaseModel):
    AMT_INCOME_TOTAL: float = Field(..., gt=0, description="Annual income (€)")
    AMT_CREDIT: float = Field(..., gt=0, description="Credit amount (€)")
    AMT_ANNUITY: float = Field(..., gt=0, description="Loan annuity (€)")
    DAYS_BIRTH: int = Field(..., lt=0, description="Days since birth (negative integer)")
    DAYS_EMPLOYED: int = Field(..., description="Days employed (negative = employed; 365243 = unemployed)")
    CODE_GENDER: int = Field(..., ge=0, le=1, description="Gender (0=F, 1=M)")
    FLAG_OWN_CAR: int = Field(..., ge=0, le=1, description="Owns a car (0/1)")
    FLAG_OWN_REALTY: int = Field(..., ge=0, le=1, description="Owns real estate (0/1)")
    CNT_CHILDREN: int = Field(..., ge=0, description="Number of children")
    AMT_GOODS_PRICE: float = Field(..., gt=0, description="Price of goods for which loan is given")
    REGION_POPULATION_RELATIVE: float = Field(..., gt=0, description="Normalized population of the region")
    DAYS_REGISTRATION: int = Field(..., le=0, description="Days since registration changed (negative)")
    EXT_SOURCE_2: float = Field(..., ge=0.0, le=1.0, description="External source score 2")
    EXT_SOURCE_3: float = Field(..., ge=0.0, le=1.0, description="External source score 3")

    model_config = {"json_schema_extra": {"example": {
        "AMT_INCOME_TOTAL": 135000,
        "AMT_CREDIT": 406597,
        "AMT_ANNUITY": 24700,
        "DAYS_BIRTH": -12005,
        "DAYS_EMPLOYED": -2329,
        "CODE_GENDER": 0,
        "FLAG_OWN_CAR": 0,
        "FLAG_OWN_REALTY": 1,
        "CNT_CHILDREN": 0,
        "AMT_GOODS_PRICE": 351000,
        "REGION_POPULATION_RELATIVE": 0.018850,
        "DAYS_REGISTRATION": -3648,
        "EXT_SOURCE_2": 0.6,
        "EXT_SOURCE_3": 0.7,
    }}}


class PredictionResult(BaseModel):
    probability_of_default: float
    score: int  # 0–1000, higher = better
    decision: str  # "approved" or "rejected"
    threshold: float


class BatchPredictionRequest(BaseModel):
    clients: list[ClientFeatures]


class BatchPredictionResult(BaseModel):
    predictions: list[PredictionResult]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DECISION_THRESHOLD = 0.5  # probability above this → rejected


def _features_to_df(client: ClientFeatures) -> pd.DataFrame:
    return pd.DataFrame([client.model_dump()])


def _predict_one(client: ClientFeatures) -> PredictionResult:
    pipeline = _model_data["pipeline"]
    X = _features_to_df(client)
    prob = float(pipeline.predict_proba(X)[0, 1])
    score = max(0, min(1000, int(round((1 - prob) * 1000))))
    decision = "rejected" if prob >= DECISION_THRESHOLD else "approved"
    return PredictionResult(
        probability_of_default=round(prob, 4),
        score=score,
        decision=decision,
        threshold=DECISION_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    loaded = bool(_model_data)
    return {"status": "ok" if loaded else "model_not_loaded", "model_loaded": loaded}


@app.post("/predict", response_model=PredictionResult)
def predict(client: ClientFeatures) -> PredictionResult:
    """Return the default probability and credit decision for one client."""
    if not _model_data:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return _predict_one(client)


@app.post("/predict/batch", response_model=BatchPredictionResult)
def predict_batch(request: BatchPredictionRequest) -> BatchPredictionResult:
    """Return predictions for a list of clients."""
    if not _model_data:
        raise HTTPException(status_code=503, detail="Model not loaded")
    predictions = [_predict_one(c) for c in request.clients]
    return BatchPredictionResult(predictions=predictions)


@app.get("/feature_importance")
def feature_importance() -> dict:
    """Return global feature importance from the trained LightGBM model."""
    if not _model_data:
        raise HTTPException(status_code=503, detail="Model not loaded")
    pipeline = _model_data["pipeline"]
    features = _model_data["features"]
    classifier = pipeline.named_steps["classifier"]
    importances = classifier.feature_importances_.tolist()
    total = sum(importances) or 1.0
    result = [
        {"feature": f, "importance": round(imp / total, 4)}
        for f, imp in sorted(
            zip(features, importances), key=lambda x: x[1], reverse=True
        )
    ]
    return {"feature_importance": result}


@app.get("/clients")
def list_clients(limit: int = 50) -> dict:
    """Return a list of sample client IDs from the reference training set."""
    if _train_df is None:
        raise HTTPException(status_code=404, detail="Reference data not available")
    ids = _train_df["SK_ID_CURR"].head(limit).tolist()
    return {"client_ids": ids}


@app.get("/clients/{client_id}")
def get_client(client_id: int) -> dict:
    """Return the features for a specific client from the reference dataset."""
    if _train_df is None:
        raise HTTPException(status_code=404, detail="Reference data not available")
    row = _train_df[_train_df["SK_ID_CURR"] == client_id]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    features = row.drop(columns=["SK_ID_CURR"]).iloc[0].to_dict()
    # Round floats for readability
    features = {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items()}
    return {"client_id": client_id, "features": features}
