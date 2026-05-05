import numpy as np
import pandas as pd

# calcul manuel du PSI (Population Stability Index)

def psi(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)

    breakpoints = np.quantile(expected, np.linspace(0, 1, bins + 1))

    expected_counts = np.histogram(expected, breakpoints)[0] + 1e-6
    actual_counts = np.histogram(actual, breakpoints)[0] + 1e-6

    expected_perc = expected_counts / expected_counts.sum()
    actual_perc = actual_counts / actual_counts.sum()

    psi_value = np.sum((actual_perc - expected_perc) * np.log(actual_perc / expected_perc))

    return float(psi_value)

def compute_drift(train_df, prod_df, profile):
    drift_report = {}

    for col, meta in profile["features"].items():

        if col not in prod_df.columns:
            continue

        if meta["type"] == "num" and not pd.api.types.is_bool_dtype(train_df[col]):
            psi_val = psi(train_df[col].dropna(), prod_df[col].dropna())
            drift_report[col] = psi_val

        else:
            # simple shift categorical
            train_dist = train_df[col].value_counts(normalize=True)
            prod_dist = prod_df[col].value_counts(normalize=True)

            diff = (train_dist - prod_dist).abs().sum()
            drift_report[col] = float(diff)

    return drift_report



from prometheus_client import Gauge

drift_gauge = Gauge('feature_drift_psi', 'Drift PSI per feature', ['feature'])

def push_to_prometheus(drift_report):
    for k, v in drift_report.items():
        drift_gauge.labels(feature=k).set(v)