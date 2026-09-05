"""
OncoCare AI — ML inference layer
==================================
Loads the trained artifacts once and exposes make_prediction(vitals).
Shared by the Flask routes and the PDF report generator.
"""

import os
import json
import joblib
import numpy as np
import logging
import warnings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")

logger = logging.getLogger(__name__)

# Defer loading large pickled models until first use. This avoids import-time
# side-effects (and multiprocessing spawn issues on Windows) and lets the
# app start even if model unpickling will fail due to sklearn version.
clf = reg = iso = scaler = label_encoder = None


def load_models():
    global clf, reg, iso, scaler, label_encoder
    if any(v is not None for v in (clf, reg, iso, scaler, label_encoder)):
        return
    try:
        clf = joblib.load(os.path.join(MODEL_DIR, "risk_classifier.pkl"))
        reg = joblib.load(os.path.join(MODEL_DIR, "risk_regressor.pkl"))
        iso = joblib.load(os.path.join(MODEL_DIR, "anomaly_detector.pkl"))
        scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
        label_encoder = joblib.load(os.path.join(MODEL_DIR, "label_encoder.pkl"))
    except Exception as e:
        warnings.warn(str(e))
        logger.exception("Model loading failed")
        clf = reg = iso = scaler = label_encoder = None

with open(os.path.join(MODEL_DIR, "metrics.json")) as f:
    MODEL_METRICS = json.load(f)

FEATURES = MODEL_METRICS["features"]

NORMAL_RANGES = {
    "temperature": (97.0, 99.5, "\u00b0F"),
    "heart_rate": (60, 100, "bpm"),
    "spo2": (95, 100, "%"),
    "sleep_hours": (6, 9, "hrs"),
    "pain_level": (0, 3, "/10"),
    "fatigue_level": (0, 3, "/10"),
    "nausea_level": (0, 3, "/10"),
    "dizziness": (0, 0, "0/1"),
}


def make_prediction(vitals: dict):
    """Run the ML pipeline on a single vitals reading and return a rich result dict."""
    # Ensure models are loaded lazily on first call. If loading fails we'll
    # surface a clear error which the caller can handle (app now persists
    # raw vitals even when prediction fails).
    load_models()
    if any(v is None for v in (clf, reg, iso, scaler, label_encoder)):
        raise RuntimeError(
            "ML artifacts not loaded. Check application logs. "
            "If you see scikit-learn InconsistentVersionWarning, install the "
            "matching version used to save the models: pip install scikit-learn==1.8.0 "
            "or re-train/resave the models with your current scikit-learn.")
    x = np.array([[vitals[f] for f in FEATURES]], dtype=float)
    x_scaled = scaler.transform(x)

    risk_level_idx = clf.predict(x_scaled)[0]
    risk_level = label_encoder.inverse_transform([risk_level_idx])[0]
    risk_proba = clf.predict_proba(x_scaled)[0]
    proba_map = {cls: round(float(p) * 100, 1) for cls, p in zip(label_encoder.classes_, risk_proba)}

    risk_score = float(reg.predict(x_scaled)[0])
    risk_score = max(0.0, min(15.0, risk_score))

    anomaly_flag = iso.predict(x_scaled)[0] == -1
    anomaly_score = float(iso.decision_function(x_scaled)[0])

    flags = []
    for feat, (lo, hi, unit) in NORMAL_RANGES.items():
        val = vitals[feat]
        if val < lo or val > hi:
            direction = "high" if val > hi else "low"
            flags.append({
                "feature": feat, "value": val,
                "normal_range": f"{lo}-{hi} {unit}", "direction": direction
            })

    return {
        "risk_level": risk_level,
        "risk_score": round(risk_score, 2),
        "risk_probabilities": proba_map,
        "is_anomaly": bool(anomaly_flag),
        "anomaly_score": round(anomaly_score, 4),
        "flags": flags,
        "feature_importance": MODEL_METRICS["feature_importance"],
    }


def forecast_next_score(history_scores, horizon=1):
    """Very lightweight linear-trend forecast of the next risk score(s),
    used as an 'advanced' early-signal indicator on the dashboard.
    Not a clinical prediction — purely a trend extrapolation."""
    n = len(history_scores)
    if n < 3:
        return None
    y = np.array(history_scores[-10:], dtype=float)
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    next_x = len(y) - 1 + horizon
    forecast = slope * next_x + intercept
    forecast = max(0.0, min(15.0, forecast))
    return {
        "forecast_score": round(float(forecast), 2),
        "trend": "rising" if slope > 0.15 else ("falling" if slope < -0.15 else "stable"),
        "slope": round(float(slope), 3)
    }
