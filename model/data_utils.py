from pathlib import Path
from typing import Optional

import json
import numpy as np
import pandas as pd



DATA_DIR = Path(__file__).resolve().parents[1] / 'data'


def create_df(name: str, data_dir: Optional[Path] = None) -> pd.DataFrame:
    base_dir = data_dir or DATA_DIR
    return pd.read_csv(base_dir / f'{name}.csv', encoding='latin-1')


def load_training_data(name: str = 'df_droped', data_dir: Optional[Path] = None):
    df = create_df(name, data_dir=data_dir)
    df_train = df[df['TARGET'].notna()].copy()
    X = df_train.drop(columns=['TARGET'])
    X = X.replace([np.inf, -np.inf], np.nan)
    valid_idx = X.notna().all(axis=1)
    X = X.loc[valid_idx]
    y = df_train.loc[valid_idx, 'TARGET'].astype(int)
    X.columns = X.columns.str.replace(r'\W', '_', regex=True)
    return X, y


def build_light_profile(df, n_bins=10):
    profile = {
        "n_rows": len(df),
        "features": {}
    }

    for col in df.columns:
        s = df[col].dropna()

        # NUMERICAL
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            
            # histogram
            counts, bins = np.histogram(s, bins=n_bins)

            profile["features"][col] = {
                "type": "num",
                "mean": float(s.mean()),
                "std": float(s.std()),
                "p10": float(s.quantile(0.10)),
                "p50": float(s.quantile(0.50)),
                "p90": float(s.quantile(0.90)),
                "missing": float(df[col].isna().mean()),
                "bins": bins.tolist(),
                "counts": counts.tolist()
            }

        # CATEGORICAL / BINARY
        else:
            value_counts = s.value_counts(normalize=False)

            profile["features"][col] = {
                "type": "cat",
                "cardinality": int(s.nunique()),
                "missing": float(df[col].isna().mean()),
                "counts": value_counts.to_dict()
            }

    return profile



def build_profile_with_reference_bins(df, reference_profile):
    profile = {
        "n_rows": len(df),
        "features": {}
    }

    ref_features = reference_profile.get("features", {})

    for col, ref_meta in ref_features.items():

        # -------------------------
        # récupération série
        # -------------------------
        if col in df.columns:
            s = df[col]
            missing = float(s.isna().mean())
            s = s.dropna()
        else:
            s = pd.Series(dtype=float)
            missing = 1.0

        # -------------------------
        # NUMERICAL
        # -------------------------
        if ref_meta.get("type") == "num":

            s_num = pd.to_numeric(s, errors="coerce").dropna()
            bins = ref_meta.get("bins")

            # fallback propre
            if bins is None:
                bins = np.histogram_bin_edges(s_num if not s_num.empty else [0, 1], bins=10)

            bins = np.asarray(bins, dtype=float)

            if s_num.empty:
                counts = np.zeros(len(bins) - 1, dtype=int)
            else:
                counts, _ = np.histogram(s_num, bins=bins)

            profile["features"][col] = {
                "type": "num",
                "mean": float(s_num.mean()) if not s_num.empty else None,
                "std": float(s_num.std()) if not s_num.empty else None,
                "p10": float(s_num.quantile(0.10)) if not s_num.empty else None,
                "p50": float(s_num.quantile(0.50)) if not s_num.empty else None,
                "p90": float(s_num.quantile(0.90)) if not s_num.empty else None,
                "missing": missing,
                "bins": bins.tolist(),
                "counts": counts.tolist(),
            }

        # -------------------------
        # CATEGORICAL / BINARY
        # -------------------------
        else:

            s_cat = s.astype(str)
            observed_counts = s_cat.value_counts().to_dict()
            ref_counts = ref_meta.get("counts", {})

            # alignement strict avec train
            aligned_counts = {
                str(k): int(observed_counts.get(str(k), 0))
                for k in ref_counts.keys()
            }

            # nouvelles catégories (important)
            new_categories = {
                k: v for k, v in observed_counts.items()
                if k not in ref_counts
            }

            profile["features"][col] = {
                "type": "cat",
                "cardinality": int(s.nunique()),
                "missing": missing,
                "counts": aligned_counts,
                "new_categories": new_categories
            }

    return profile