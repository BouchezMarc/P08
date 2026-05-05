from pathlib import Path

from lightgbm.sklearn import LGBMClassifier


def export_lightgbm_to_onnx(model: LGBMClassifier, n_features: int, output_path: Path) -> Path:
    try:
        import onnxmltools
        from onnxmltools.convert.common.data_types import FloatTensorType
        from onnx import save_model
    except ImportError as exc:
        raise ImportError(
            "ONNX export requires onnxmltools and onnx to be installed. "
            "Install them with: pip install onnxmltools onnx"
        ) from exc

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    initial_types = [("input", FloatTensorType([None, n_features]))]
    onnx_model = onnxmltools.convert_lightgbm(model, initial_types=initial_types)
    save_model(onnx_model, str(output_path))

    return output_path


if __name__ == "__main__":
    raise SystemExit(
        "Use export_lightgbm_to_onnx() from model/train.py after fitting the model."
    )