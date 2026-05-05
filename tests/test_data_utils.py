from pathlib import Path

import numpy as np
import pandas as pd

from model.data_utils import (
    build_light_profile,
    build_profile_with_reference_bins,
    create_df,
    load_training_data,
)


def test_create_df_reads_csv_from_custom_directory(tmp_path: Path):
    csv_path = tmp_path / "sample.csv"
    pd.DataFrame({"col": [1, 2]}).to_csv(csv_path, index=False, encoding="latin-1")

    df = create_df("sample", data_dir=tmp_path)

    assert list(df.columns) == ["col"]
    assert df.shape == (2, 1)


def test_load_training_data_filters_invalid_rows_and_sanitizes_columns(tmp_path: Path):
    pd.DataFrame(
        {
            "A-1": [1.0, np.inf, 3.0, 4.0],
            "B value": [10.0, 20.0, np.nan, 40.0],
            "TARGET": [1, 0, 1, np.nan],
        }
    ).to_csv(tmp_path / "df_droped.csv", index=False, encoding="latin-1")

    x_train, y_train = load_training_data(data_dir=tmp_path)

    assert x_train.shape == (1, 2)
    assert list(x_train.columns) == ["A_1", "B_value"]
    assert y_train.tolist() == [1]


def test_build_light_profile_returns_num_and_cat_sections():
    df = pd.DataFrame(
        {
            "num_feature": [1.0, 2.0, 3.0, np.nan],
            "cat_feature": ["a", "b", "a", None],
        }
    )

    profile = build_light_profile(df, n_bins=3)

    assert profile["n_rows"] == 4
    assert profile["features"]["num_feature"]["type"] == "num"
    assert len(profile["features"]["num_feature"]["counts"]) == 3
    assert profile["features"]["num_feature"]["missing"] == 0.25

    assert profile["features"]["cat_feature"]["type"] == "cat"
    assert profile["features"]["cat_feature"]["cardinality"] == 2
    assert profile["features"]["cat_feature"]["counts"] == {"a": 2, "b": 1}
    assert profile["features"]["cat_feature"]["missing"] == 0.25


def test_build_profile_with_reference_bins_aligns_counts_and_detects_new_categories():
    reference_profile = {
        "features": {
            "num_feature": {
                "type": "num",
                "bins": [0.0, 1.0, 2.0, 3.0],
            },
            "cat_feature": {
                "type": "cat",
                "counts": {"x": 5, "y": 2},
            },
        }
    }

    df = pd.DataFrame(
        {
            "num_feature": [0.2, 2.5, np.nan, 0.8],
            "cat_feature": ["x", "z", "z", None],
        }
    )

    profile = build_profile_with_reference_bins(df, reference_profile)

    num_meta = profile["features"]["num_feature"]
    assert num_meta["type"] == "num"
    assert num_meta["bins"] == [0.0, 1.0, 2.0, 3.0]
    assert num_meta["counts"] == [2, 0, 1]
    assert num_meta["missing"] == 0.25

    cat_meta = profile["features"]["cat_feature"]
    assert cat_meta["type"] == "cat"
    assert cat_meta["counts"] == {"x": 1, "y": 0}
    assert cat_meta["new_categories"] == {"z": 2}
    assert cat_meta["missing"] == 0.25
    assert cat_meta["cardinality"] == 2
