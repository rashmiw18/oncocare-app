"""
OncoCare AI - Model Training Script
Trains two models on the patient vitals dataset:
  1. RandomForestClassifier -> predicts risk_level (Low/Medium/High)
  2. RandomForestRegressor  -> predicts risk_score (0-15 continuous)
Also fits an IsolationForest for anomaly / unusual-pattern detection.

Artifacts saved to model/ as .pkl files, loaded by the Flask app at runtime.
"""

import pandas as pd
import numpy as np
import joblib
import json
import os

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, IsolationForest
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.metrics import accuracy_score, classification_report, mean_absolute_error, r2_score

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "synthetic_oncocare_health_dataset.csv")
MODEL_DIR = os.path.dirname(os.path.abspath(__file__))

FEATURES = [
    "temperature", "heart_rate", "spo2", "sleep_hours",
    "pain_level", "fatigue_level", "nausea_level", "dizziness"
]

def main():
    print("Loading dataset...")
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} rows")

    X = df[FEATURES]
    y_class = df["risk_level"]
    y_reg = df["risk_score"]

    # Encode risk_level labels
    le = LabelEncoder()
    y_class_enc = le.fit_transform(y_class)
    print("Classes:", list(le.classes_))

    # Scale features (helps anomaly detection & is good practice; RF doesn't strictly need it)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train/test split
    X_train, X_test, yc_train, yc_test, yr_train, yr_test = train_test_split(
        X_scaled, y_class_enc, y_reg, test_size=0.2, random_state=42, stratify=y_class_enc
    )

    # --- Classifier: risk level ---
    print("\nTraining RandomForestClassifier (risk_level)...")
    clf = RandomForestClassifier(
        n_estimators=300, max_depth=12, min_samples_split=4,
        random_state=42, class_weight="balanced", n_jobs=-1
    )
    clf.fit(X_train, yc_train)
    yc_pred = clf.predict(X_test)
    acc = accuracy_score(yc_test, yc_pred)
    print(f"Classifier accuracy: {acc:.4f}")
    print(classification_report(yc_test, yc_pred, target_names=le.classes_))

    # --- Regressor: risk score ---
    print("Training RandomForestRegressor (risk_score)...")
    reg = RandomForestRegressor(
        n_estimators=300, max_depth=12, min_samples_split=4,
        random_state=42, n_jobs=-1
    )
    reg.fit(X_train, yr_train)
    yr_pred = reg.predict(X_test)
    mae = mean_absolute_error(yr_test, yr_pred)
    r2 = r2_score(yr_test, yr_pred)
    print(f"Regressor MAE: {mae:.4f}   R2: {r2:.4f}")

    # --- Anomaly detector (unsupervised, trained on ALL data) ---
    print("Training IsolationForest for anomaly detection...")
    iso = IsolationForest(
        n_estimators=250, contamination=0.05, random_state=42, n_jobs=-1
    )
    iso.fit(X_scaled)

    # Feature importance (from classifier) for dashboard insights
    importances = dict(zip(FEATURES, clf.feature_importances_.round(4).tolist()))
    importances = dict(sorted(importances.items(), key=lambda x: -x[1]))

    # Save all artifacts
    joblib.dump(clf, os.path.join(MODEL_DIR, "risk_classifier.pkl"))
    joblib.dump(reg, os.path.join(MODEL_DIR, "risk_regressor.pkl"))
    joblib.dump(iso, os.path.join(MODEL_DIR, "anomaly_detector.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))
    joblib.dump(le, os.path.join(MODEL_DIR, "label_encoder.pkl"))

    metrics = {
        "features": FEATURES,
        "classes": list(le.classes_),
        "classifier_accuracy": round(acc, 4),
        "regressor_mae": round(mae, 4),
        "regressor_r2": round(r2, 4),
        "feature_importance": importances,
        "n_train_rows": len(df)
    }
    with open(os.path.join(MODEL_DIR, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print("\nAll model artifacts saved to:", MODEL_DIR)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
