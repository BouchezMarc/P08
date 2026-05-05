import types
from pathlib import Path

import numpy as np
import pandas as pd

from model.convert_to_onnx import export_lightgbm_to_onnx
from profiling import onnx_optimization


def test_select_profile_output_names_prefers_probability_like_output():
    class DummyOutput:
        def __init__(self, name):
            self.name = name

    class DummySession:
        def get_outputs(self):
            return [DummyOutput("label"), DummyOutput("probabilities")]

    selected = onnx_optimization._select_profile_output_names(DummySession())
    assert selected == ["probabilities"]


def test_load_test_data_reads_csv_from_project_layout(tmp_path: Path, monkeypatch):
    fake_module_file = tmp_path / "profiling" / "onnx_optimization.py"
    fake_module_file.parent.mkdir(parents=True, exist_ok=True)
    fake_module_file.write_text("# stub", encoding="utf-8")

    test_csv = tmp_path / "data" / "split" / "test.csv"
    test_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "f1": [1.0, 2.0, 3.0],
            "f2": [10.0, 20.0, 30.0],
            "TARGET": [0, 1, 0],
        }
    ).to_csv(test_csv, index=False)

    monkeypatch.setattr(onnx_optimization, "__file__", str(fake_module_file))

    arr = onnx_optimization.load_test_data(n_samples=2)
    assert arr.shape == (2, 2)
    assert arr.dtype == np.float32


def test_profile_onnx_model_returns_latency_stats(tmp_path: Path, monkeypatch):
    class DummyInput:
        def __init__(self, name):
            self.name = name

    class DummyOutput:
        def __init__(self, name):
            self.name = name

    class DummySession:
        def __init__(self, *_args, **_kwargs):
            self.calls = 0

        def get_inputs(self):
            return [DummyInput("input")]

        def get_outputs(self):
            return [DummyOutput("label"), DummyOutput("probability")]

        def run(self, output_names, feeds):
            self.calls += 1
            assert output_names == ["probability"]
            assert "input" in feeds
            return [[0], [{0: 0.2, 1: 0.8}]]

    fake_ort = types.SimpleNamespace(InferenceSession=DummySession)
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", fake_ort)

    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"fake")

    batch = np.array([[1.0, 2.0]], dtype=np.float32)
    stats = onnx_optimization.profile_onnx_model(model_path, batch, runs=3)

    assert set(stats.keys()) == {"avg_ms", "std_ms", "min_ms", "max_ms"}
    assert stats["avg_ms"] >= 0.0
    assert stats["min_ms"] <= stats["max_ms"]


def test_optimize_onnx_model_saves_simplified_model(tmp_path: Path, monkeypatch):
    calls = {}

    def fake_simplify(model):
        calls["simplify_input"] = model
        return ({"simplified": True}, True)

    def fake_load(path):
        calls["load_path"] = path
        return {"model": "raw"}

    def fake_save(model, path):
        calls["save_model"] = model
        calls["save_path"] = path

    monkeypatch.setitem(__import__("sys").modules, "onnxsim", types.SimpleNamespace(simplify=fake_simplify))
    monkeypatch.setitem(__import__("sys").modules, "onnx", types.SimpleNamespace(load=fake_load, save=fake_save))

    input_path = tmp_path / "in.onnx"
    output_path = tmp_path / "out.onnx"
    input_path.write_bytes(b"dummy")

    result = onnx_optimization.optimize_onnx_model(input_path, output_path)

    assert result == output_path
    assert calls["load_path"] == str(input_path)
    assert calls["save_model"] == {"simplified": True}
    assert calls["save_path"] == str(output_path)


def test_export_lightgbm_to_onnx_creates_output_and_calls_converter(tmp_path: Path, monkeypatch):
    calls = {}

    class DummyFloatTensorType:
        def __init__(self, shape):
            self.shape = shape

    def fake_convert_lightgbm(model, initial_types):
        calls["model"] = model
        calls["initial_types"] = initial_types
        return {"onnx": "model"}

    def fake_save_model(model, path):
        calls["saved_model"] = model
        calls["saved_path"] = path

    fake_onnxmltools = types.SimpleNamespace(convert_lightgbm=fake_convert_lightgbm)
    fake_data_types = types.SimpleNamespace(FloatTensorType=DummyFloatTensorType)

    monkeypatch.setitem(__import__("sys").modules, "onnxmltools", fake_onnxmltools)
    monkeypatch.setitem(
        __import__("sys").modules,
        "onnxmltools.convert.common.data_types",
        fake_data_types,
    )
    monkeypatch.setitem(__import__("sys").modules, "onnx", types.SimpleNamespace(save_model=fake_save_model))

    output_path = tmp_path / "artifacts" / "model.onnx"
    fake_model = object()

    result = export_lightgbm_to_onnx(fake_model, n_features=7, output_path=output_path)

    assert result == output_path
    assert output_path.parent.exists()
    assert calls["model"] is fake_model
    assert calls["initial_types"][0][0] == "input"
    assert calls["initial_types"][0][1].shape == [None, 7]
    assert calls["saved_model"] == {"onnx": "model"}
    assert calls["saved_path"] == str(output_path)
