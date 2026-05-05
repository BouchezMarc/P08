"""
Pytest configuration and shared fixtures for the test suite.

The conftest creates a fresh model artefact in a temporary directory before any
tests run, and tears it down afterwards.  This avoids writing permanent files to
the repository during CI while keeping tests fully self-contained.
"""

import os
import sys
import tempfile

import pytest

# Make sure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def tmp_model_dir(tmp_path_factory):
    """Create a temporary directory for model artefacts used in tests."""
    return tmp_path_factory.mktemp("model_artefacts")


@pytest.fixture(scope="session")
def trained_model_path(tmp_model_dir):
    """Train a small model and return paths to the model and training data."""
    import joblib
    from model.train_model import (
        FEATURES,
        generate_synthetic_data,
        build_pipeline,
        NUMERIC_FEATURES,
        BINARY_FEATURES,
    )
    from sklearn.model_selection import train_test_split

    df = generate_synthetic_data(n_samples=200, random_state=0)
    X = df[FEATURES]
    y = df["TARGET"]
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=0)

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    model_data = {
        "pipeline": pipeline,
        "features": FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "binary_features": BINARY_FEATURES,
        "auc": 0.0,
    }

    model_path = str(tmp_model_dir / "credit_model.pkl")
    data_path = str(tmp_model_dir / "train_data.pkl")

    joblib.dump(model_data, model_path)

    train_sample = X_train.copy()
    train_sample = train_sample.reset_index()
    joblib.dump(train_sample, data_path)

    return model_path, data_path


@pytest.fixture(scope="session")
def api_client(trained_model_path):
    """Return a TestClient for the FastAPI app with the test model loaded."""
    model_path, data_path = trained_model_path

    os.environ["MODEL_PATH"] = model_path
    os.environ["DATA_PATH"] = data_path

    # Import after setting env vars so the app picks them up
    from fastapi.testclient import TestClient
    from api.app import app, load_model

    # Reload model with test paths
    load_model()

    with TestClient(app) as client:
        yield client
