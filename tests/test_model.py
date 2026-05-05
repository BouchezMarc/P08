"""
Tests for the model training module (model/train_model.py) and
the drift monitoring module (monitoring/drift.py).
"""

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Model training tests
# ---------------------------------------------------------------------------


def test_generate_synthetic_data():
    from model.train_model import generate_synthetic_data, FEATURES

    df = generate_synthetic_data(n_samples=100, random_state=42)
    assert len(df) == 100
    for feat in FEATURES:
        assert feat in df.columns
    assert "TARGET" in df.columns
    assert df["TARGET"].isin([0, 1]).all()


def test_generate_synthetic_data_default_rate():
    """Default rate should be between 5% and 50% (reasonable range)."""
    from model.train_model import generate_synthetic_data

    df = generate_synthetic_data(n_samples=500, random_state=42)
    default_rate = df["TARGET"].mean()
    assert 0.05 < default_rate < 0.50


def test_build_pipeline():
    from model.train_model import build_pipeline
    from sklearn.pipeline import Pipeline

    pipeline = build_pipeline()
    assert isinstance(pipeline, Pipeline)
    assert "preprocessor" in pipeline.named_steps
    assert "classifier" in pipeline.named_steps


def test_pipeline_fit_predict(trained_model_path):
    """The fitted pipeline (from conftest fixture) should produce valid probabilities."""
    import joblib
    from model.train_model import generate_synthetic_data, FEATURES

    model_path, _ = trained_model_path
    model_data = joblib.load(model_path)
    pipeline = model_data["pipeline"]

    df = generate_synthetic_data(n_samples=20, random_state=99)
    X = df[FEATURES]
    proba = pipeline.predict_proba(X)

    assert proba.shape == (20, 2)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-6)
    assert (proba >= 0).all() and (proba <= 1).all()


def test_model_data_keys(trained_model_path):
    import joblib

    model_path, _ = trained_model_path
    model_data = joblib.load(model_path)

    for key in ("pipeline", "features", "numeric_features", "binary_features"):
        assert key in model_data


# ---------------------------------------------------------------------------
# Drift monitoring tests
# ---------------------------------------------------------------------------


def test_ks_drift_no_drift():
    from monitoring.drift import ks_drift

    rng = np.random.default_rng(0)
    ref = rng.normal(0, 1, 200)
    cur = rng.normal(0, 1, 200)
    result = ks_drift(ref, cur)
    assert "statistic" in result
    assert "p_value" in result
    assert "drift_detected" in result
    assert isinstance(result["drift_detected"], bool)


def test_ks_drift_with_drift():
    """Clearly different distributions should be flagged."""
    from monitoring.drift import ks_drift

    ref = np.random.default_rng(0).normal(0, 1, 500)
    cur = np.random.default_rng(1).normal(5, 1, 500)  # large shift
    result = ks_drift(ref, cur)
    assert result["drift_detected"] is True
    assert result["p_value"] < 0.05


def test_chi2_drift_no_drift():
    from monitoring.drift import chi2_drift

    rng = np.random.default_rng(0)
    ref = rng.choice([0, 1], 300, p=[0.6, 0.4])
    cur = rng.choice([0, 1], 300, p=[0.6, 0.4])
    result = chi2_drift(ref, cur)
    assert isinstance(result["drift_detected"], bool)


def test_chi2_drift_with_drift():
    from monitoring.drift import chi2_drift

    ref = np.zeros(300, dtype=int)  # all 0s
    cur = np.ones(300, dtype=int)   # all 1s
    result = chi2_drift(ref, cur)
    assert result["drift_detected"] is True


def test_compute_drift_report():
    from monitoring.drift import compute_drift_report
    from model.train_model import generate_synthetic_data, FEATURES

    ref_df = generate_synthetic_data(n_samples=200, random_state=0)[FEATURES]
    cur_df = generate_synthetic_data(n_samples=200, random_state=1)[FEATURES]

    report = compute_drift_report(ref_df, cur_df)
    assert "n_reference" in report
    assert "n_current" in report
    assert "n_drifted" in report
    assert "drift_share" in report
    assert "features" in report
    assert 0.0 <= report["drift_share"] <= 1.0
    assert report["n_drifted"] <= len(report["features"])


def test_compute_drift_report_with_shift():
    """A large distributional shift should detect drift in at least one feature."""
    from monitoring.drift import compute_drift_report
    from model.train_model import generate_synthetic_data, FEATURES

    ref_df = generate_synthetic_data(n_samples=500, random_state=0)[FEATURES]
    cur_df = ref_df.copy()
    cur_df["EXT_SOURCE_2"] = 1.0 - cur_df["EXT_SOURCE_2"]  # Invert the distribution
    cur_df["EXT_SOURCE_3"] = 1.0 - cur_df["EXT_SOURCE_3"]

    report = compute_drift_report(ref_df, cur_df)
    assert report["n_drifted"] >= 2
