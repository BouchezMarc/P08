"""
ONNX Model Optimization with Profiling.
Compares performance (latency, memory) of original vs optimized ONNX model.
"""

import time
from pathlib import Path

import numpy as np
import pandas as pd


def _select_profile_output_names(session):
    """Pick an output suited for latency profiling and avoid label-shape warnings."""
    outputs = session.get_outputs()
    if not outputs:
        return None

    # Prefer score/probability-like outputs first.
    preferred_names = (
        "probabilities",
        "probability",
        "score",
        "scores",
        "output_probability",
    )
    for out in outputs:
        name = (out.name or "").lower()
        if any(p in name for p in preferred_names):
            return [out.name]

    # Otherwise choose the first non-label output when possible.
    for out in outputs:
        name = (out.name or "").lower()
        if "label" not in name:
            return [out.name]

    # Fallback to all outputs if we could not choose better.
    return None


def load_test_data(n_samples=100):
    """Load test data for inference."""
    project_root = Path(__file__).resolve().parents[1]
    test_csv_path = project_root / "data" / "split" / "test.csv"

    if not test_csv_path.exists():
        raise FileNotFoundError(f"Test CSV not found: {test_csv_path}")

    df = pd.read_csv(test_csv_path)
    features_df = df.drop(columns=["TARGET"], errors="ignore")
    features_df = features_df.iloc[:n_samples].copy()

    return features_df.to_numpy(dtype=np.float32)


def profile_onnx_model(model_path, batch_data, runs=5):
    """Profile ONNX model inference."""
    try:
        import onnxruntime as ort
    except ImportError:
        raise ImportError("onnxruntime not installed. Install with: pip install onnxruntime")

    if not Path(model_path).exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_names = _select_profile_output_names(session)

    available_outputs = [out.name for out in session.get_outputs()]
    selected_outputs = output_names if output_names is not None else available_outputs
    print(f"    Outputs available: {available_outputs}")
    print(f"    Profiling outputs: {selected_outputs}")

    latencies = []
    for _ in range(runs):
        start = time.time()
        session.run(output_names, {input_name: batch_data})
        latencies.append(time.time() - start)

    avg_latency = np.mean(latencies)
    std_latency = np.std(latencies)
    min_latency = np.min(latencies)
    max_latency = np.max(latencies)

    return {
        "avg_ms": avg_latency * 1000,
        "std_ms": std_latency * 1000,
        "min_ms": min_latency * 1000,
        "max_ms": max_latency * 1000,
    }


def optimize_onnx_model(input_path, output_path):
    """Optimize ONNX model using onnx-simplifier."""
    try:
        from onnxsim import simplify
    except ImportError:
        raise ImportError(
            "onnx-simplifier not installed. "
            "Install with: pip install onnx-simplifier"
        )

    import onnx

    # Load and simplify model
    model = onnx.load(str(input_path))
    simplified_model, check_ok = simplify(model)

    if not check_ok:
        print("    ⚠️  Simplified model validation failed")

    onnx.save(simplified_model, str(output_path))
    return output_path


def compare_models():
    """Main: Compare original vs optimized ONNX model."""
    project_root = Path(__file__).resolve().parents[1]
    original_model_path = project_root / "model" / "artifacts" / "model.onnx"
    optimized_model_path = project_root / "model" / "artifacts" / "model_optimized.onnx"

    print("=" * 60)
    print("ONNX Model Optimization & Profiling")
    print("=" * 60)

    # Load test data
    print("\n[1] Loading test data...")
    batch_data = load_test_data(n_samples=100)
    print(f"    Batch shape: {batch_data.shape}")

    # Profile original model
    print("\n[2] Profiling ORIGINAL model (5 runs)...")
    original_perf = profile_onnx_model(original_model_path, batch_data, runs=5)
    print(f"    Avg latency: {original_perf['avg_ms']:.2f} ms")
    print(f"    Std latency: {original_perf['std_ms']:.2f} ms")
    print(f"    Min latency: {original_perf['min_ms']:.2f} ms")
    print(f"    Max latency: {original_perf['max_ms']:.2f} ms")

    # Optimize model
    print("\n[3] Optimizing model...")
    try:
        optimize_onnx_model(original_model_path, optimized_model_path)
        print(f"    Optimized model saved to: {optimized_model_path}")
    except Exception as e:
        print(f"    ⚠️  Optimization skipped: {e}")
        print("    Proceeding with original model only.")
        return

    # Profile optimized model
    print("\n[4] Profiling OPTIMIZED model (5 runs)...")
    optimized_perf = profile_onnx_model(optimized_model_path, batch_data, runs=5)
    print(f"    Avg latency: {optimized_perf['avg_ms']:.2f} ms")
    print(f"    Std latency: {optimized_perf['std_ms']:.2f} ms")
    print(f"    Min latency: {optimized_perf['min_ms']:.2f} ms")
    print(f"    Max latency: {optimized_perf['max_ms']:.2f} ms")

    # Compare results
    print("\n[5] Comparison")
    print("=" * 60)
    speedup = original_perf["avg_ms"] / optimized_perf["avg_ms"]
    improvement = (1 - optimized_perf["avg_ms"] / original_perf["avg_ms"]) * 100

    print(f"Speedup: {speedup:.2f}x")
    print(f"Improvement: {improvement:.2f}%")

    if speedup > 1.0:
        print(f"✅ Optimization improved latency by {improvement:.2f}%")
    else:
        print(f"⚠️  Optimization did NOT improve latency.")

    print("=" * 60)

    return {
        "original": original_perf,
        "optimized": optimized_perf,
        "speedup": speedup,
        "improvement_pct": improvement,
    }


if __name__ == "__main__":
    results = compare_models()
