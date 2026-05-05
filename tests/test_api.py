import json
import sys
from pathlib import Path


import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parent.parent))
import api.main as api_main


# ====== Dummy Classes pour Mock ======

class DummyInput:
    def __init__(self, name="input"):
        self.name = name


class DummyOrtSession:
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.profile_path.write_text(
            json.dumps(
                [
                    {
                        "name": "model_run",
                        "cat": "Session",
                        "ph": "X",
                        "ts": 1,
                        "dur": 2,
                    }
                ]
            ),
            encoding="utf-8",
        )

    def get_inputs(self):
        return [DummyInput()]

    def run(self, output_names, feeds):
        batch = next(iter(feeds.values()))
        batch_size = int(np.asarray(batch).shape[0])
        labels = np.zeros(batch_size, dtype=np.int64)
        probabilities = [{0: 0.2, 1: 0.8} for _ in range(batch_size)]
        return [labels, probabilities]

    def end_profiling(self):
        return str(self.profile_path)


class DummyResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class DummyDBSession:
    def __init__(self, row=None, should_fail=False):
        self.row = row
        self.should_fail = should_fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query, params):
        if self.should_fail:
            raise RuntimeError("db failure")
        return DummyResult(self.row)

    def add_all(self, rows):
        self.rows = rows

    async def commit(self):
        return None

    async def rollback(self):
        return None


async def noop_log_predictions(rows):
    return None


# ====== Fixture Client ======

@pytest.fixture()
def client(monkeypatch, tmp_path):
    profile_path = tmp_path / "onnx_profile_trace.json"
    dummy_session = DummyOrtSession(profile_path)

    monkeypatch.setattr(api_main.ort, "InferenceSession", lambda *args, **kwargs: dummy_session)
    monkeypatch.setattr(api_main, "log_predictions", noop_log_predictions)

    with TestClient(api_main.app) as test_client:
        yield test_client


# ====== Tests Existants ======

def test_root_health_and_schema(client):
    root = client.get("/")
    assert root.status_code == 200
    assert root.json() == {"status": "ok"}

    health = client.get("/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["model_ready"] is True
    assert health_payload["features"] == len(api_main.FEATURE_ORDER)

    schema = client.get("/schema")
    assert schema.status_code == 200
    schema_payload = schema.json()
    assert schema_payload["feature_count"] == len(api_main.FEATURE_ORDER)
    first_feature = api_main.FEATURE_ORDER[0]
    assert schema_payload["features"][0] == first_feature
    assert schema_payload["defaults"][first_feature] == api_main.DEFAULT_ROW[first_feature]


def test_predict_and_test_csv(client):
    feature_name = api_main.FEATURE_ORDER[0]
    feature_value = float(api_main.DEFAULT_ROW[feature_name])

    predict_resp = client.post("/predict", json={"features": {feature_name: feature_value}})
    assert predict_resp.status_code == 200
    predict_payload = predict_resp.json()
    assert predict_payload["prediction"] == pytest.approx(0.8)
    assert predict_payload["probability"] == pytest.approx(0.8)

    batch_resp = client.post(
        "/predict/test-csv",
        params={
            "page": 1,
            "page_size": 2,
            "feature": feature_name,
            "multiplier": 1.0,
        },
    )
    assert batch_resp.status_code == 200
    batch_payload = batch_resp.json()
    assert batch_payload["page"] == 1
    assert batch_payload["page_size"] == 2
    assert batch_payload["total_rows"] == len(api_main._test_csv_cache)
    assert batch_payload["total_pages"] == (len(api_main._test_csv_cache) + 1) // 2
    assert len(batch_payload["rows"]) == 2
    assert batch_payload["rows"][0]["prediction_score"] == pytest.approx(0.8)
    assert batch_payload["rows"][0]["prediction_label"] == 1


def test_metrics_includes_profiler_trace(client):
    api_main.app.state.ort_last_profile = {
        "timestamp": "2026-05-04T00:00:00Z",
        "trace": "[{\"name\": \"model_run\", \"cat\": \"Session\"}]",
    }

    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    assert "api_requests_total" in body
    assert "# ONNX_PROFILER_BEGIN" in body
    assert '"name": "model_run"' in body
    assert "# ONNX_PROFILER_END" in body


def test_drift_latest_success_and_missing(client, monkeypatch):
    monkeypatch.setattr(
        api_main,
        "get_db_session",
        lambda: DummyDBSession(row={"timestamp": "2026-05-04T00:00:00Z", "env": "prod", "report": {"ok": True}}),
    )

    resp = client.get("/drift/latest", params={"env": "prod"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["env"] == "prod"
    assert payload["report"] == {"ok": True}

    monkeypatch.setattr(api_main, "get_db_session", lambda: DummyDBSession(row=None))
    missing = client.get("/drift/latest", params={"env": "stage"})
    assert missing.status_code == 404


# ====== Tests additionnels ======

def test_predict_validation_errors(client):
    # Empty features
    resp = client.post("/predict", json={"features": {}})
    assert resp.status_code in (400, 422)

    # Missing required feature
    some_feature = api_main.FEATURE_ORDER[0]
    resp = client.post("/predict", json={"features": {some_feature: None}})
    assert resp.status_code in (400, 422)

    # Wrong type
    resp = client.post("/predict", json={"features": {some_feature: "not a number"}})
    assert resp.status_code in (400, 422)


def test_predict_test_csv_invalid_params(client):
    feature_name = api_main.FEATURE_ORDER[0]

    # Page number too low
    resp = client.post("/predict/test-csv", params={"page": 0, "page_size": 10, "feature": feature_name, "multiplier": 1})
    assert resp.status_code in (400, 422)

    # Page size too high
    resp = client.post("/predict/test-csv", params={"page": 1, "page_size": 10000, "feature": feature_name, "multiplier": 1})
    assert resp.status_code in (400, 422)

    # Multiplier invalid
    resp = client.post("/predict/test-csv", params={"page": 1, "page_size": 10, "feature": feature_name, "multiplier": -5})
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_drift_latest_db_failure(client, monkeypatch):
    # Simule une DB qui lève une erreur
    monkeypatch.setattr(api_main, "get_db_session", lambda: DummyDBSession(should_fail=True))

    resp = client.get("/drift/latest", params={"env": "prod"})
    assert resp.status_code in (500, 400)


def test_predict_value_ranges(client):
    feature_name = api_main.FEATURE_ORDER[0]
    resp = client.post("/predict", json={"features": {feature_name: float(api_main.DEFAULT_ROW[feature_name])}})
    payload = resp.json()

    # prediction entre 0 et 1
    assert 0.0 <= payload["prediction"] <= 1.0
    assert 0.0 <= payload["probability"] <= 1.0
    assert isinstance(payload["prediction"], float)
    assert isinstance(payload["probability"], float)