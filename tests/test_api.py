"""
Tests for the FastAPI credit scoring API (api/app.py).
"""

import pytest


# ---------------------------------------------------------------------------
# Sample valid payload
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "AMT_INCOME_TOTAL": 135000.0,
    "AMT_CREDIT": 406597.0,
    "AMT_ANNUITY": 24700.0,
    "DAYS_BIRTH": -12005,
    "DAYS_EMPLOYED": -2329,
    "CODE_GENDER": 0,
    "FLAG_OWN_CAR": 0,
    "FLAG_OWN_REALTY": 1,
    "CNT_CHILDREN": 0,
    "AMT_GOODS_PRICE": 351000.0,
    "REGION_POPULATION_RELATIVE": 0.01885,
    "DAYS_REGISTRATION": -3648,
    "EXT_SOURCE_2": 0.6,
    "EXT_SOURCE_3": 0.7,
}


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_ok(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_loaded"] is True


# ---------------------------------------------------------------------------
# Predict endpoint
# ---------------------------------------------------------------------------


def test_predict_valid(api_client):
    response = api_client.post("/predict", json=VALID_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert "probability_of_default" in data
    assert "score" in data
    assert "decision" in data
    assert 0.0 <= data["probability_of_default"] <= 1.0
    assert 0 <= data["score"] <= 1000
    assert data["decision"] in ("approved", "rejected")


def test_predict_low_risk_client(api_client):
    """A client with very high external scores should have a low default probability."""
    low_risk = {**VALID_PAYLOAD, "EXT_SOURCE_2": 0.99, "EXT_SOURCE_3": 0.99}
    response = api_client.post("/predict", json=low_risk)
    assert response.status_code == 200
    data = response.json()
    # The score should be higher for a lower-risk client
    assert data["score"] >= 500


def test_predict_high_risk_client(api_client):
    """A client with very low external scores should have a higher default probability."""
    high_risk = {**VALID_PAYLOAD, "EXT_SOURCE_2": 0.01, "EXT_SOURCE_3": 0.01}
    response = api_client.post("/predict", json=high_risk)
    assert response.status_code == 200
    data = response.json()
    assert data["probability_of_default"] > 0.0


def test_predict_missing_field(api_client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "AMT_INCOME_TOTAL"}
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422  # Unprocessable Entity


def test_predict_invalid_ext_source(api_client):
    """EXT_SOURCE values must be between 0 and 1."""
    payload = {**VALID_PAYLOAD, "EXT_SOURCE_2": 1.5}
    response = api_client.post("/predict", json=payload)
    assert response.status_code == 422


def test_predict_decision_consistency(api_client):
    """Decision should be consistent with probability and threshold."""
    response = api_client.post("/predict", json=VALID_PAYLOAD)
    data = response.json()
    prob = data["probability_of_default"]
    threshold = data["threshold"]
    expected_decision = "rejected" if prob >= threshold else "approved"
    assert data["decision"] == expected_decision


# ---------------------------------------------------------------------------
# Batch predict endpoint
# ---------------------------------------------------------------------------


def test_predict_batch(api_client):
    batch = {"clients": [VALID_PAYLOAD, VALID_PAYLOAD]}
    response = api_client.post("/predict/batch", json=batch)
    assert response.status_code == 200
    data = response.json()
    assert len(data["predictions"]) == 2


def test_predict_batch_empty(api_client):
    """An empty batch should return an empty list."""
    response = api_client.post("/predict/batch", json={"clients": []})
    assert response.status_code == 200
    assert response.json()["predictions"] == []


# ---------------------------------------------------------------------------
# Feature importance endpoint
# ---------------------------------------------------------------------------


def test_feature_importance(api_client):
    response = api_client.get("/feature_importance")
    assert response.status_code == 200
    data = response.json()
    assert "feature_importance" in data
    fi = data["feature_importance"]
    assert len(fi) > 0
    for item in fi:
        assert "feature" in item
        assert "importance" in item
        assert item["importance"] >= 0


# ---------------------------------------------------------------------------
# Clients endpoints
# ---------------------------------------------------------------------------


def test_list_clients(api_client):
    response = api_client.get("/clients?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "client_ids" in data
    assert len(data["client_ids"]) <= 10


def test_get_client_valid(api_client):
    # Fetch first client ID
    ids_resp = api_client.get("/clients?limit=1")
    client_id = ids_resp.json()["client_ids"][0]

    response = api_client.get(f"/clients/{client_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["client_id"] == client_id
    assert "features" in data
    assert len(data["features"]) > 0


def test_get_client_not_found(api_client):
    response = api_client.get("/clients/9999999")
    assert response.status_code == 404
