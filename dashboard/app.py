import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
import matplotlib.pyplot as plt
import re
from pydantic import BaseModel, ValidationError
from typing import Dict

# Configure Streamlit page
st.set_page_config(
    page_title="ML Inference & Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API configuration
API_URL = st.sidebar.text_input("API URL", value="http://127.0.0.1:8000")

# ============ Header ============
st.title("🔮 ML Inference & Monitoring Dashboard")
st.markdown("---")


def parse_prometheus_metrics(metrics_text: str) -> pd.DataFrame:
    rows = []

    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if " " not in line:
            continue

        metric_part, value_part = line.rsplit(" ", 1)

        labels = {}
        if "{" in metric_part and metric_part.endswith("}"):
            metric_name, labels_part = metric_part.split("{", 1)
            labels_part = labels_part[:-1]
            for item in re.finditer(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', labels_part):
                labels[item.group(1)] = item.group(2)
        else:
            metric_name = metric_part

        try:
            value = float(value_part)
        except ValueError:
            continue

        row = {"metric": metric_name, "value": value}
        row.update(labels)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["metric", "value"])

    return pd.DataFrame(rows)


def _first_metric_frame(df_metrics: pd.DataFrame, metric_names: list[str]) -> pd.DataFrame:
    for metric_name in metric_names:
        subset = df_metrics[df_metrics["metric"] == metric_name]
        if not subset.empty:
            return subset
    return pd.DataFrame(columns=df_metrics.columns)

# ============ Health Check ============
try:
    health_resp = requests.get(f"{API_URL}/health", timeout=2)
    if health_resp.status_code == 200:
        st.sidebar.success("✅ API Connected")
    else:
        st.sidebar.error("❌ API Error")
except Exception as e:
    st.sidebar.error(f"❌ API Unreachable: {e}")

# ============ Pydantic Model ============
class PredictionRequest(BaseModel):
    features: Dict[str, float]

# ============ Tabs ============
tab0, tab1, tab2, tab3 = st.tabs(["Prediction", "Predictions", "Drift Detection", "Metrics"])

# ============ TAB 0: PREDICTION FORM ============
with tab0:
    st.header("🎯 Single Prediction")
    
    # Load schema from API
    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def load_schema(api_url):
        try:
            r = requests.get(f"{api_url}/schema", timeout=5)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            return None
    
    schema = load_schema(API_URL)
    
    if not schema:
        st.error("❌ Unable to load model schema. API might not be ready.")
    else:
        features = schema.get("features", [])
        defaults = schema.get("defaults", {})
        
        st.info(f"✅ Model ready - Expects {len(features)} features")
        
        # Create form
        with st.form(key="prediction_form"):
            st.subheader("Enter Feature Values")
            
            user_features = {}
            
            # Create input fields dynamically in 2 columns
            cols = st.columns(2)
            for i, feature in enumerate(features):
                with cols[i % 2]:
                    default_val = defaults.get(feature, 0.0)
                    user_features[feature] = st.number_input(
                        label=feature,
                        value=float(default_val),
                        format="%.2f",
                        help=f"Default: {default_val}"
                    )
            
            submit_btn = st.form_submit_button(label="🚀 Get Prediction", width='stretch')
        
        if submit_btn:
            # Validate with Pydantic
            try:
                payload = PredictionRequest(features=user_features)
                st.success("✅ Input validation passed")
            except ValidationError as e:
                st.error(f"❌ Validation error: {e}")
                st.stop()
            
            # Send to API
            with st.spinner("🔄 Sending prediction request..."):
                try:
                    r = requests.post(
                        f"{API_URL}/predict",
                        json=payload.dict(),
                        timeout=10
                    )
                    
                    if r.status_code == 200:
                        result = r.json()
                        
                        st.divider()
                        st.subheader("🎯 Prediction Result")
                        
                        col_pred, col_prob = st.columns(2)
                        with col_pred:
                            pred_label = "Positive" if result["prediction"] >= 0.5 else "Negative"
                            st.metric("Prediction", pred_label)
                        
                        with col_prob:
                            st.metric("Probability", f"{result['probability']:.4f}")
                        
                        # Show score visualization
                        fig, ax = plt.subplots(figsize=(8, 3))
                        color = "green" if result["probability"] >= 0.5 else "red"
                        ax.barh(["Score"], [result["probability"]], color=color, height=0.5)
                        ax.set_xlim(0, 1)
                        ax.set_xlabel("Prediction Score", fontsize=12)
                        ax.set_title("Prediction Confidence", fontsize=14, fontweight="bold")
                        st.pyplot(fig)
                        plt.close(fig)
                        
                    else:
                        st.error(f"❌ API Error {r.status_code}: {r.text}")
                except requests.exceptions.Timeout:
                    st.error("❌ Request timeout. API might be busy.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")

# ============ TAB 1: PREDICTIONS ============
with tab1:
    st.header("📈 Predictions on Test Data")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        page = st.number_input("Page", value=1, min_value=1, help="1-based page index")
    with col2:
        page_size = st.slider("Page size", 1, 20, 5, help="Rows per page")
    with col3:
        feature = st.text_input("Feature to multiply", value="amt_income_total", help="Column name to apply multiplier to")
    with col4:
        multiplier = st.number_input("Multiplier", value=1.0, step=0.1, min_value=0.1, max_value=5.0, help="Multiply feature by this value")
    
    if st.button("🔍 Get Predictions", key="pred_btn"):
        with st.spinner("Fetching predictions..."):
            try:
                r = requests.post(
                    f"{API_URL}/predict/test-csv",
                    params={
                        "page": page,
                        "page_size": page_size,
                        "feature": feature,
                        "multiplier": multiplier
                    },
                    timeout=30
                )

                st.subheader("API Response")
                st.caption(f"HTTP status: {r.status_code}")
                
                if r.status_code == 200:
                    data = r.json()

                    with st.expander("Show raw API response", expanded=False):
                        st.json(data)
                    
                    # Show summary
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("Total Rows", data['total_rows'])
                    with col_b:
                        st.metric("Total Pages", data['total_pages'])
                    with col_c:
                        st.metric("Current Page", data['page'])
                    
                    st.divider()
                    
                    # Show dataframe
                    df_results = pd.DataFrame(data['rows'])
                    
                    # Highlight predictions
                    if 'prediction_score' in df_results.columns and 'prediction_label' in df_results.columns:
                        st.subheader(f"Results (Page {data['page']}/{data['total_pages']})")
                        
                        # Show top columns + predictions
                        display_cols = [
                            col for col in df_results.columns 
                            if col in ['name_contract_type', 'code_gender', 'amt_income_total', 'prediction_score', 'prediction_label']
                            or col.startswith('prediction_')
                        ]
                        if not display_cols:
                            display_cols = df_results.columns.tolist()
                        
                        st.dataframe(df_results[display_cols], width='stretch')
                        
                        # Prediction distribution
                        pred_dist = df_results['prediction_label'].value_counts()
                        st.bar_chart(pred_dist, width='stretch')
                    else:
                        st.dataframe(df_results, width='stretch')
                    
                    # Download option
                    csv = df_results.to_csv(index=False)
                    st.download_button(
                        label="📥 Download CSV",
                        data=csv,
                        file_name=f"predictions_page_{page}.csv",
                        mime="text/csv"
                    )
                else:
                    with st.expander("Show API error response", expanded=True):
                        st.code(r.text)
                    st.error(f"API Error {r.status_code}")
            except requests.exceptions.Timeout:
                st.error("Request timeout. API might be busy.")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============ TAB 2: DRIFT DETECTION ============
with tab2:
    st.header("🔴 Drift Detection")

    def _extract_dataset_drift_section(payload: dict):
        """Support multiple Evidently JSON layouts and return dataset drift section."""
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None

        # Common API layout can return the report nested or stringified.
        report_payload = payload.get("report", payload)
        if isinstance(report_payload, str):
            try:
                report_payload = json.loads(report_payload)
            except json.JSONDecodeError:
                return None

        # Expected layout from user snippet
        metrics = report_payload.get("metrics")
        if isinstance(metrics, dict) and "dataset_drift" in metrics:
            return metrics["dataset_drift"]

        # Evidently list-style layouts
        if isinstance(metrics, list):
            # Layout A: metric result contains drift_by_columns
            for metric in metrics:
                result = metric.get("result", {})
                if "number_of_drifted_columns" in result and "drift_by_columns" in result:
                    drift_by_columns = result.get("drift_by_columns", {})
                    top_cols = sorted(
                        [
                            {
                                "column": col,
                                "drift_score": details.get("drift_score", 0.0),
                                "current": details.get("current", {}),
                                "reference": details.get("reference", {}),
                            }
                            for col, details in drift_by_columns.items()
                        ],
                        key=lambda x: x["drift_score"],
                        reverse=True,
                    )
                    return {
                        "top_drifted_columns": [item["column"] for item in top_cols],
                        "column_drift": {
                            item["column"]: {
                                "drift_score": item["drift_score"],
                                "train": item["reference"],
                                "production": item["current"],
                            }
                            for item in top_cols
                        },
                    }

            # Layout B: flat ValueDrift metrics list (metric_name/config/value)
            drift_items = []
            for metric in metrics:
                metric_name = metric.get("metric_name", "")
                if not metric_name.startswith("ValueDrift("):
                    continue

                cfg = metric.get("config", {})
                col = cfg.get("column")
                score = metric.get("value")

                if col is None or score is None:
                    continue

                try:
                    score = float(score)
                except (TypeError, ValueError):
                    continue

                drift_items.append({"column": col, "drift_score": score})

            if drift_items:
                drift_items.sort(key=lambda x: x["drift_score"], reverse=True)
                return {
                    "top_drifted_columns": [item["column"] for item in drift_items],
                    "column_drift": {
                        item["column"]: {
                            "drift_score": item["drift_score"],
                        }
                        for item in drift_items
                    },
                }

        return None

    st.subheader("📋 Latest Drift Report")
    if st.button("📖 Fetch Latest", key="latest_drift_btn"):
        with st.spinner("Fetching latest drift..."):
            try:
                r = requests.get(f"{API_URL}/drift/latest", timeout=10)
                
                if r.status_code == 200:
                    drift_report = r.json()

                    dataset_drift = _extract_dataset_drift_section(drift_report)
                    if not dataset_drift:
                        st.error("Format de drift_report non reconnu (dataset_drift introuvable).")
                        st.json(drift_report)
                        st.stop()

                    top_cols = dataset_drift.get("top_drifted_columns", [])
                    column_drift = dataset_drift.get("column_drift", {})

                    if not top_cols:
                        st.info("Aucune colonne driftée trouvée dans le dernier rapport.")
                    else:
                        st.subheader("Top colonnes driftées")
                        summary_rows = []
                        for col in top_cols:
                            drift_score = column_drift.get(col, {}).get("drift_score")
                            if drift_score is not None:
                                summary_rows.append({"column": col, "drift_score": drift_score})

                        if summary_rows:
                            df_summary = pd.DataFrame(summary_rows).sort_values("drift_score", ascending=False)
                            st.dataframe(df_summary, width='stretch')

                            st.subheader("Graphique des drift scores (Top 20)")
                            chart_df = df_summary.head(20).set_index("column")
                            st.bar_chart(chart_df["drift_score"], width='stretch')

                        plotted_histograms = 0
                        for col in top_cols[:5]:
                            details = column_drift.get(col, {})
                            train_hist = details.get("train", {}).get("histogram")
                            prod_hist = details.get("production", {}).get("histogram")

                            if not train_hist or not prod_hist:
                                continue

                            if not all(k in train_hist for k in ["counts", "buckets"]) or not all(k in prod_hist for k in ["counts", "buckets"]):
                                continue

                            plotted_histograms += 1
                            st.write(f"Histogramme pour {col}")
                            df_plot = pd.DataFrame(
                                {
                                    "train": train_hist["counts"],
                                    "prod": prod_hist["counts"],
                                },
                                index=train_hist["buckets"],
                            )

                            fig, ax = plt.subplots(figsize=(8, 4))
                            df_plot.plot(kind="bar", alpha=0.6, ax=ax)
                            ax.set_xlabel("Buckets")
                            ax.set_ylabel("Count")
                            ax.set_title(f"Distribution - {col}")
                            st.pyplot(fig)
                            plt.close(fig)

                        if plotted_histograms == 0:
                            st.info("Le tableau et le bar chart des drift scores sont affichés.")
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============ TAB 3: METRICS ============
with tab3:
    st.header("📈 Prometheus Metrics")
    
    if st.button("🔄 Refresh Metrics", key="metrics_btn"):
        with st.spinner("Fetching metrics..."):
            try:
                r = requests.get(f"{API_URL}/metrics", timeout=10)
                
                if r.status_code == 200:
                    metrics_text = r.text

                    df_metrics = parse_prometheus_metrics(metrics_text)

                    if not df_metrics.empty:
                        request_df = _first_metric_frame(
                            df_metrics,
                            ["api_requests_total", "requests_total", "predictions_total"]
                        )
                        latency_df = _first_metric_frame(
                            df_metrics,
                            ["api_latency_seconds", "onnx_inference_seconds", "prediction_latency_seconds"]
                        )

                        total_requests = request_df['value'].sum() if not request_df.empty else 0.0
                        avg_latency = latency_df['value'].mean() if not latency_df.empty else 0.0

                        col1, col2 = st.columns(2)
                        col1.metric("Total Requests", int(total_requests))
                        col2.metric("Average Latency (s)", round(float(avg_latency), 3))

                        st.subheader("Metrics Table")
                        st.dataframe(df_metrics, width='stretch')

                        st.divider()
                        st.subheader("Visualizations")

                        req_df = request_df
                        if not req_df.empty and 'endpoint' in req_df.columns:
                            req_plot_df = req_df.groupby('endpoint', as_index=False)['value'].sum()
                            fig, ax = plt.subplots(figsize=(6, 4))
                            ax.bar(req_plot_df['endpoint'].astype(str), req_plot_df['value'])
                            ax.set_ylabel("Nombre de requêtes")
                            ax.set_xlabel("Endpoint")
                            ax.set_title("Requêtes totales par endpoint")
                            ax.tick_params(axis='x', rotation=30)
                            st.pyplot(fig)
                            plt.close(fig)
                        else:
                            st.info("No request metrics with endpoint labels found in the current Prometheus output.")

                        if not latency_df.empty and 'endpoint' in latency_df.columns:
                            latency_plot_df = latency_df.groupby('endpoint', as_index=False)['value'].mean()
                            fig, ax = plt.subplots(figsize=(6, 4))
                            ax.bar(latency_plot_df['endpoint'].astype(str), latency_plot_df['value'], color='darkred')
                            ax.set_ylabel("Latence (s)")
                            ax.set_xlabel("Endpoint")
                            ax.set_title("Latence moyenne par endpoint")
                            ax.tick_params(axis='x', rotation=30)
                            st.pyplot(fig)
                            plt.close(fig)
                        else:
                            st.info("No latency metrics with endpoint labels found in the current Prometheus output.")

                        st.divider()
                        st.download_button(
                            label="📥 Download Metrics",
                            data=metrics_text,
                            file_name="metrics.txt",
                            mime="text/plain"
                        )
                    else:
                        st.info("No metrics available.")
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# ============ Sidebar Info ============
st.sidebar.divider()
st.sidebar.subheader("ℹ️ About")
st.sidebar.markdown("""
**ML Inference & Monitoring**
- Predictions on test data with drift simulation
- Latest drift report visualization
- Real-time Prometheus metrics
 - Real-time Prometheus metrics

**Endpoints (API):**
- `POST /predict` - Single prediction. Body: `{"features": {"f1": val, ...}}`
- `POST /predict/test-csv` - Batch predictions from test CSV. Query params: `page`, `page_size`, `feature`, `multiplier`
- `GET /schema` - Returns feature names and default values used to build the Prediction form
- `GET /drift/latest` - Retrieve latest drift report (optional `env` parameter)
- `GET /metrics` - Prometheus metrics (used by Metrics tab)

**Notes:**
- Ensure the API URL at the top of the sidebar is correct before using the dashboard.
- If you update or replace the model, restart the API so `/schema` and model endpoints reflect changes.
""")

st.sidebar.markdown("---")
st.sidebar.caption(f"Dashboard loaded at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
