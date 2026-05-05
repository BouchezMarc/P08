"""
Data drift monitoring module.

Detects statistical drift between a reference dataset (training distribution)
and a current dataset (recent predictions / incoming requests).

Methods used:
- Kolmogorov-Smirnov test for continuous features
- Chi-squared test for binary / categorical features
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALPHA = 0.05  # significance level for drift detection

CONTINUOUS_FEATURES = [
    "AMT_INCOME_TOTAL",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "DAYS_BIRTH",
    "DAYS_EMPLOYED",
    "CNT_CHILDREN",
    "AMT_GOODS_PRICE",
    "REGION_POPULATION_RELATIVE",
    "DAYS_REGISTRATION",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
]

CATEGORICAL_FEATURES = [
    "CODE_GENDER",
    "FLAG_OWN_CAR",
    "FLAG_OWN_REALTY",
]

ALL_FEATURES = CONTINUOUS_FEATURES + CATEGORICAL_FEATURES


# ---------------------------------------------------------------------------
# Core drift detection functions
# ---------------------------------------------------------------------------


def ks_drift(reference: np.ndarray, current: np.ndarray) -> dict[str, Any]:
    """Run Kolmogorov-Smirnov test between two 1-D samples.

    Parameters
    ----------
    reference:
        1-D array from the reference (training) distribution.
    current:
        1-D array from the current (production) distribution.

    Returns
    -------
    dict with keys: statistic, p_value, drift_detected
    """
    ref_clean = reference[~np.isnan(reference)]
    cur_clean = current[~np.isnan(current)]
    if len(ref_clean) == 0 or len(cur_clean) == 0:
        return {"statistic": None, "p_value": None, "drift_detected": False}
    result = stats.ks_2samp(ref_clean, cur_clean)
    return {
        "statistic": round(float(result.statistic), 4),
        "p_value": round(float(result.pvalue), 4),
        "drift_detected": bool(result.pvalue < ALPHA),
    }


def chi2_drift(reference: np.ndarray, current: np.ndarray) -> dict[str, Any]:
    """Run chi-squared test between observed category frequencies.

    Parameters
    ----------
    reference:
        1-D array of category values from reference.
    current:
        1-D array of category values from current.

    Returns
    -------
    dict with keys: statistic, p_value, drift_detected
    """
    categories = np.union1d(np.unique(reference), np.unique(current))
    ref_counts = np.array([np.sum(reference == c) for c in categories], dtype=float)
    cur_counts = np.array([np.sum(current == c) for c in categories], dtype=float)

    # Avoid zero expected frequencies
    if ref_counts.sum() == 0 or cur_counts.sum() == 0:
        return {"statistic": None, "p_value": None, "drift_detected": False}

    # Normalize reference to obtain expected frequencies
    expected = ref_counts / ref_counts.sum() * cur_counts.sum()

    # Replace zeros in expected with a small number to avoid division errors
    expected = np.where(expected == 0, 1e-6, expected)

    chi2, p_value = stats.chisquare(f_obs=cur_counts, f_exp=expected)
    return {
        "statistic": round(float(chi2), 4),
        "p_value": round(float(p_value), 4),
        "drift_detected": bool(p_value < ALPHA),
    }


# ---------------------------------------------------------------------------
# High-level drift report
# ---------------------------------------------------------------------------


def compute_drift_report(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    features: list[str] | None = None,
) -> dict[str, Any]:
    """Compute a full drift report comparing reference vs current DataFrames.

    Parameters
    ----------
    reference_df:
        Reference (training) dataset.
    current_df:
        Current (production) dataset.
    features:
        Subset of features to analyse. Defaults to ALL_FEATURES.

    Returns
    -------
    dict with keys:
        - n_reference: int
        - n_current: int
        - n_drifted: int
        - drift_share: float (0-1)
        - features: dict[str, dict] – per-feature results
    """
    if features is None:
        features = ALL_FEATURES

    report: dict[str, Any] = {
        "n_reference": len(reference_df),
        "n_current": len(current_df),
        "features": {},
    }

    n_drifted = 0
    for feature in features:
        if feature not in reference_df.columns or feature not in current_df.columns:
            continue

        ref_vals = reference_df[feature].values
        cur_vals = current_df[feature].values

        if feature in CATEGORICAL_FEATURES:
            result = chi2_drift(ref_vals, cur_vals)
        else:
            result = ks_drift(ref_vals.astype(float), cur_vals.astype(float))

        report["features"][feature] = result
        if result.get("drift_detected"):
            n_drifted += 1

    analysed = len(report["features"])
    report["n_drifted"] = n_drifted
    report["drift_share"] = round(n_drifted / analysed, 4) if analysed > 0 else 0.0
    return report
