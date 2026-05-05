import logging
import time
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List
from datetime import datetime

import numpy as np
import pandas as pd
import onnxruntime as ort
from sqlalchemy import text

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    REGISTRY,
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, PlainTextResponse

from db.database import SessionLocal
from db.models import Prediction

# =========================================================
# CONFIG
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "model" / "artifacts" / "model.onnx"
TEST_CSV_PATH = PROJECT_ROOT / "data" / "split" / "test_poc.csv"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# GLOBAL STATE
# =========================================================

MODEL_READY = False
_test_csv_cache = None
DEFAULT_ROW = None
FEATURE_ORDER = None

# =========================================================
# METRICS
# =========================================================

request_count = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

request_latency = Histogram(
    "api_latency_seconds",
    "API latency",
    ["endpoint"],
)

errors_total = Counter(
    "api_errors_total",
    "Total API errors",
    ["endpoint", "error_type"],
)

inference_time = Histogram(
    "onnx_inference_seconds",
    "ONNX inference time",
    ["endpoint"],
)

predictions_total = Counter(
    "predictions_total",
    "Total predictions"
)

model_success_total = Counter(
    "model_inference_success_total",
    "Successful model inferences"
)

model_failure_total = Counter(
    "model_inference_failure_total",
    "Failed model inferences"
)

batch_size_hist = Histogram(
    "prediction_batch_size",
    "Batch size distribution",
    buckets=(1, 10, 50, 100, 500, 1000)
)

inference_in_progress = Gauge(
    "inference_in_progress",
    "Concurrent inferences"
)

# =========================================================
# REQUEST MODEL (Swagger FIX)
# =========================================================

class PredictionRequest(BaseModel):
    features: Dict[str, float]

    class Config:
        json_schema_extra = {
            "example": {
                "features": {
                    "amt_income_total": 247500,
                    "amt_credit": 497520,
                    "cnt_children": 0
                }
            }
        }

# =========================================================
# DB LOGGING
# =========================================================

async def log_predictions(rows: List[dict]):
    async with SessionLocal() as session:
        try:
            session.add_all([Prediction(**r) for r in rows])
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"[DB ERROR] {e}")

# =========================================================
# LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global MODEL_READY, _test_csv_cache, DEFAULT_ROW, FEATURE_ORDER

    logger.info("Loading ONNX model...")

    session_options = ort.SessionOptions()
    session_options.enable_profiling = True
    session_options.profile_file_prefix = "onnx_profile"

    session = ort.InferenceSession(
        str(MODEL_PATH),
        sess_options=session_options,
        providers=["CPUExecutionProvider"]
    )
    app.state.model = session
    # storage for latest ONNX Runtime profiling trace (Chrome trace JSON)
    app.state.ort_last_profile = None

    logger.info("Loading CSV baseline...")

    if TEST_CSV_PATH.exists():
        _test_csv_cache = pd.read_csv(TEST_CSV_PATH)

        DEFAULT_ROW = _test_csv_cache.iloc[0].drop("TARGET", errors="ignore").to_dict()
        FEATURE_ORDER = list(DEFAULT_ROW.keys())

        MODEL_READY = True
        logger.info(f"MODEL READY - {len(FEATURE_ORDER)} features")

    else:
        MODEL_READY = False
        logger.error("CSV missing → MODEL NOT READY")

    yield

# =========================================================
# APP
# =========================================================

app = FastAPI(lifespan=lifespan)

# =========================================================
# MIDDLEWARE
# =========================================================

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()

        try:
            inference_in_progress.inc()
            response = await call_next(request)
            status = response.status_code

        except Exception as exc:
            status = 500
            errors_total.labels(
                endpoint=request.url.path,
                error_type=type(exc).__name__
            ).inc()
            raise

        finally:
            inference_in_progress.dec()

        duration = time.time() - start

        request_count.labels(
            method=request.method,
            endpoint=request.url.path,
            status=status
        ).inc()

        request_latency.labels(
            endpoint=request.url.path
        ).observe(duration)

        return response

app.add_middleware(MetricsMiddleware)

# =========================================================
# UTILS
# =========================================================

def build_input(features: dict):
    if not MODEL_READY:
        raise HTTPException(503, "Model not ready")

    row = DEFAULT_ROW.copy()
    row.update(features)

    try:
        vector = [float(row[f]) for f in FEATURE_ORDER]
    except KeyError as e:
        raise HTTPException(400, f"Missing feature: {e}")

    return np.array([vector], dtype=np.float32)


def predict(session, batch: np.ndarray, endpoint: str):
    input_name = session.get_inputs()[0].name

    start = time.time()

    try:
        outputs = session.run(None, {input_name: batch})
        model_success_total.inc()

        # Attempt to end profiling and capture trace file
        try:
            profile_path = session.end_profiling()
            if profile_path:
                try:
                    profile_text = Path(profile_path).read_text(encoding="utf-8")
                    app.state.ort_last_profile = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "trace": profile_text,
                    }
                    logger.info(f"ONNX profiler trace captured at {profile_path}")
                except Exception:
                    # ignore filesystem errors
                    pass
            else:
                logger.warning("ONNX profiler did not return a trace path.")
        except Exception:
            pass

    except Exception:
        model_failure_total.inc()
        raise

    inference_time.labels(endpoint=endpoint).observe(time.time() - start)

    # ONNX model returns [label, probabilities]
    # Probabilities are dicts: [{0: float, 1: float}, ...]
    probs = outputs[1]
    
    scores = []
    for prob_dict in probs:
        if isinstance(prob_dict, dict):
            # Extract probability for class 1
            scores.append(prob_dict.get(1, 0.0))
        else:
            # Fallback if format is different
            prob_array = np.asarray(prob_dict)
            if prob_array.ndim == 1 and len(prob_array) > 1:
                scores.append(prob_array[1])
            else:
                scores.append(float(prob_array.flatten()[0]))
    
    return scores

# =========================================================
# ROUTES
# =========================================================

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health():
    return {
        "model_ready": MODEL_READY,
        "features": len(FEATURE_ORDER) if FEATURE_ORDER else 0
    }

@app.get("/metrics")
def metrics():
    # Get Prometheus metrics text
    metrics_bytes = generate_latest(REGISTRY)
    try:
        metrics_text = metrics_bytes.decode("utf-8")
    except Exception:
        metrics_text = str(metrics_bytes)

    # Append latest ONNX Runtime profiler trace as commented lines
    profiler_block = ""
    ort_prof = getattr(app.state, "ort_last_profile", None)
    if ort_prof and isinstance(ort_prof, dict) and ort_prof.get("trace"):
        lines = []
        lines.append("# ONNX_PROFILER_BEGIN")
        lines.append(f"# timestamp: {ort_prof.get('timestamp')}")
        for l in ort_prof["trace"].splitlines():
            lines.append("# " + l)
        lines.append("# ONNX_PROFILER_END")
        profiler_block = "\n" + "\n".join(lines) + "\n"

    return PlainTextResponse(metrics_text + profiler_block)

@app.get("/schema")
def schema():
    if not MODEL_READY:
        raise HTTPException(503, "Model not ready")

    return {
        "feature_count": len(FEATURE_ORDER),
        "features": FEATURE_ORDER,
        "defaults": DEFAULT_ROW
    }


@app.get("/drift/latest")
async def get_latest_drift_report(env: str = "prod"):
    """Fetch the newest drift report JSON from Supabase/Postgres."""
    query = text(
        """
        SELECT timestamp, report, env
        FROM drift_reports
        WHERE env = :env
        ORDER BY timestamp DESC
        LIMIT 1
        """
    )

    async with SessionLocal() as session:
        try:
            result = await session.execute(query, {"env": env})
            row = result.mappings().first()
        except Exception as exc:
            logger.error(f"[DB ERROR] latest drift report fetch failed: {exc}")
            raise HTTPException(500, "Failed to fetch latest drift report")

    if row is None:
        raise HTTPException(404, f"No drift report found for env='{env}'")

    return {
        "timestamp": row.get("timestamp"),
        "env": row.get("env"),
        "report": row.get("report"),
    }

# ===========================
# /predict
# ===========================
@app.post("/predict")
async def predict_endpoint(payload: PredictionRequest):
    # Vérifier que le modèle est prêt
    if not MODEL_READY:
        raise HTTPException(status_code=503, detail="Model not ready")

    # Vérifier que les features ne sont pas vides
    if not payload.features:
        raise HTTPException(status_code=422, detail="Features cannot be empty")

    # Compléter les features manquantes avec DEFAULT_ROW
    row = DEFAULT_ROW.copy()
    row.update(payload.features)

    # Construire le batch ONNX dans l'ordre strict
    try:
        batch_vector = [float(row[f]) for f in FEATURE_ORDER]
    except KeyError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required feature: {e}"
        )

    batch = np.array([batch_vector], dtype=np.float32)
    batch_size_hist.observe(len(batch))

    # Prédiction
    try:
        scores = predict(app.state.model, batch, "/predict")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    predictions_total.inc(len(scores))

    # Préparer les logs DB async
    rows = [{
        "input_features": row,
        "prediction": bool(scores[0] >= 0.5)
    }]
    asyncio.create_task(log_predictions(rows))

    # Retour
    return {
        "prediction": float(scores[0]),   # toujours float pour pytest
        "probability": float(scores[0])
    }

# ===========================
# /predict/test-csv
# ===========================
@app.post("/predict/test-csv")
async def predict_test_csv(
    page: int = 1,
    page_size: int = 100,
    feature: str = "amt_income_total",
    multiplier: float = 1.0,
):
    # Vérifications d’entrée
    if page < 1:
        raise HTTPException(status_code=422, detail="Page must be >= 1")
    if page_size < 1 or page_size > 1000:
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 1000")
    if multiplier <= 0:
        raise HTTPException(status_code=422, detail="multiplier must be positive")

    if _test_csv_cache is None:
        raise HTTPException(status_code=503, detail="No CSV loaded")

    df = _test_csv_cache.copy()
    total_rows = len(df)
    total_pages = (total_rows + page_size - 1) // page_size

    if page > total_pages:
        raise HTTPException(status_code=422, detail="Page out of range")

    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end].copy()

    # Appliquer le multiplicateur
    features_df = page_df.drop(columns=["TARGET"], errors="ignore")
    if feature not in features_df.columns:
        raise HTTPException(status_code=422, detail=f"Feature '{feature}' not in CSV columns")

    features_df[feature] = pd.to_numeric(features_df[feature], errors="coerce") * multiplier

    # Réindexer et remplir valeurs manquantes
    features_df = features_df.reindex(columns=FEATURE_ORDER)
    features_df = features_df.fillna(DEFAULT_ROW)

    batch = features_df.to_numpy(dtype=np.float32)
    scores = predict(app.state.model, batch, "/predict/test-csv")

    page_df["prediction_score"] = scores
    page_df["prediction_label"] = (page_df["prediction_score"] >= 0.5).astype(int)

    rows = [
        {
            "input_features": features_df.iloc[i].to_dict(),
            "prediction": bool(scores[i] >= 0.5)
        }
        for i in range(len(scores))
    ]

    asyncio.create_task(log_predictions(rows))
    predictions_total.inc(len(scores))

    return {
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "rows": page_df.to_dict(orient="records"),
    }