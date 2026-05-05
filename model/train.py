from pathlib import Path
import sys

import json
import numpy as np
from lightgbm.sklearn import LGBMClassifier
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.data_utils import create_df, build_light_profile
from model.convert_to_onnx import export_lightgbm_to_onnx
from model.handler import ModelHandler


def clean_columns(cols):
    return (
        cols.str.strip()
        .str.lower()
        .str.replace(r"\W+", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )


def main():
    best_params = {
        "n_estimators": 66,
        "max_depth": 4,
        "learning_rate": 0.05049675100862447,
        "num_leaves": 22,
        "subsample": 0.5893294941045972,
        "colsample_bytree": 0.6263030969016153,
        "random_state": 42,
        "class_weight": "balanced",
    }

    model = LGBMClassifier(**best_params)

    data_dir = Path(__file__).resolve().parents[1] / "data/raw/"
    df_droped = create_df("df_droped", data_dir=data_dir)

    df = df_droped[df_droped["TARGET"].notna()].copy()

    df_train, df_test = train_test_split(
        df,
        test_size=0.2,
        random_state=42,
        stratify=df["TARGET"],
    )

    X_train = df_train.drop(columns=["TARGET"])
    y_train = df_train["TARGET"].astype(int)

    X_test = df_test.drop(columns=["TARGET"])
    y_test = df_test["TARGET"].astype(int)

    X_train.columns = clean_columns(X_train.columns)
    X_test.columns = clean_columns(X_test.columns)

    X_train = X_train.replace([np.inf, -np.inf], np.nan)
    X_test = X_test.replace([np.inf, -np.inf], np.nan)

    X_train = X_train.fillna(X_train.median(numeric_only=True))
    X_test = X_test.fillna(X_train.median(numeric_only=True))

    split_dir = Path(__file__).resolve().parents[1] / "data" / "split"
    split_dir.mkdir(parents=True, exist_ok=True)

    profile = build_light_profile(X_train)
    with open(split_dir / "train_profile.json", "w") as f:
        json.dump(profile, f)

    train_output = X_train.copy()
    train_output["TARGET"] = y_train.values
    test_output = X_test.copy()
    test_output["TARGET"] = y_test.values

    train_output.to_csv(split_dir / "train.csv", index=False)
    test_output.to_csv(split_dir / "test.csv", index=False)

    handler = ModelHandler(
        model=model,
        param_grid={},
        use_smote=False,
        use_enn=False,
        n_splits=3,
    )

    handler.build_pipeline()
    handler.train_model(X_train, y_train)

    handler.pipeline.fit(X_train, y_train)

    handler.optimal_threshold = 0.54

    final_metrics = handler.evaluate_with_optimal_threshold(X_test, y_test)

    artifacts_dir = Path(__file__).resolve().parent / "artifacts"
    onnx_path = artifacts_dir / "model.onnx"
    export_lightgbm_to_onnx(handler.pipeline.named_steps["model"], X_train.shape[1], onnx_path)

    print("Métriques finales avec seuil optimal:")
    for key, value in final_metrics.items():
        print(f"{key}: {value:.4f}")

    print(f"Modèle ONNX exporté vers: {onnx_path}")

    y_test_prob = handler.pipeline.predict_proba(X_test)[:, 1]
    y_test_pred = (y_test_prob >= handler.optimal_threshold).astype(int)

    return final_metrics, y_test_pred


if __name__ == "__main__":
    main()