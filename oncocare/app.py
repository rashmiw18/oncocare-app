"""
OncoCare AI - Flask Application
=================================
Health-monitoring dashboard for cancer patients with:
  - Separate doctor / patient login & registration
  - Per-patient ML risk prediction (classifier + regressor + anomaly detector)
  - SQLite-backed reading history and doctor clinical notes
  - Downloadable PDF patient reports
  - Gemini-powered chatbot grounded in the patient's latest reading

Run:
    pip install -r requirements.txt
    python app.py
"""

import os
from datetime import datetime, timedelta

import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash

import db
import ml
from auth import login_required, role_required, current_user

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "oncocare-dev-secret-change-me")

db.init_db()

FEATURES = ml.FEATURES


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if session.get("role") == "doctor":
        return redirect(url_for("doctor_home"))
    return redirect(url_for("dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("home"))
        return render_template("login.html")

    data = request.form
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") or "patient"

    user = db.get_user_by_username(username)
    if not user or user["role"] != role or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Incorrect username, password, or role.", role=role), 401

    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["full_name"] = user["full_name"]
    return redirect(url_for("home"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        if session.get("user_id"):
            return redirect(url_for("home"))
        doctors = db.list_doctors()
        return render_template("register.html", doctors=doctors)

    data = request.form
    role = data.get("role") or "patient"
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip() or None
    specialization = (data.get("specialization") or "").strip() or None
    doctor_id = data.get("doctor_id") or None

    doctors = db.list_doctors()

    if not username or not password or not full_name:
        return render_template("register.html", error="Please fill in all required fields.", doctors=doctors, role=role), 400

    if db.get_user_by_username(username):
        return render_template("register.html", error="That username is already taken.", doctors=doctors, role=role), 400

    if role == "patient" and doctor_id:
        doctor_id = int(doctor_id)

    user_id = db.create_user(
        username=username,
        password_hash=generate_password_hash(password),
        role=role,
        full_name=full_name,
        email=email,
        specialization=specialization if role == "doctor" else None,
        doctor_id=doctor_id if role == "patient" else None,
    )

    session["user_id"] = user_id
    session["role"] = role
    session["full_name"] = full_name
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@role_required("patient")
def dashboard():
    user = current_user()
    doctor = db.get_user_by_id(user["doctor_id"]) if user["doctor_id"] else None
    return render_template(
        "dashboard.html",
        viewer=user, patient=user, doctor=doctor,
        is_doctor_view=False, model_metrics=ml.MODEL_METRICS
    )


@app.route("/doctor")
@role_required("doctor")
def doctor_home():
    doctor = current_user()
    patients = db.list_patients_for_doctor(doctor["id"])

    patient_cards = []
    high_risk_count = 0
    for p in patients:
        latest = db.get_latest_reading(p["id"])
        if latest and latest["risk_level"] == "High":
            high_risk_count += 1
        patient_cards.append({**p, "latest": latest})

    return render_template(
        "doctor_home.html",
        doctor=doctor, patients=patient_cards, high_risk_count=high_risk_count
    )


@app.route("/patient/<int:patient_id>")
@role_required("doctor")
def patient_detail(patient_id):
    doctor = current_user()
    patient = db.get_user_by_id(patient_id)
    if not patient or patient["role"] != "patient" or patient["doctor_id"] != doctor["id"]:
        return redirect(url_for("doctor_home"))

    return render_template(
        "dashboard.html",
        viewer=doctor, patient=patient, doctor=doctor,
        is_doctor_view=True, model_metrics=ml.MODEL_METRICS
    )


# ---------------------------------------------------------------------------
# Report page + download
# ---------------------------------------------------------------------------

@app.route("/report")
@login_required
def report_page():
    viewer = current_user()
    if viewer["role"] == "patient":
        target_patient = viewer
        patients = None
    else:
        patients = db.list_patients_for_doctor(viewer["id"])
        pid = request.args.get("patient_id", type=int)
        target_patient = db.get_user_by_id(pid) if pid else (patients[0] if patients else None)
        if target_patient and (target_patient["role"] != "patient" or target_patient["doctor_id"] != viewer["id"]):
            target_patient = None

    return render_template(
        "report.html", viewer=viewer, patient=target_patient, patients=patients
    )


def _resolve_report_patient(viewer):
    """Return (patient_dict, doctor_dict) for the report target, honoring role scoping."""
    if viewer["role"] == "patient":
        patient = viewer
    else:
        pid = request.args.get("patient_id", type=int)
        patient = db.get_user_by_id(pid) if pid else None
        if not patient or patient["role"] != "patient" or patient["doctor_id"] != viewer["id"]:
            return None, None
    doctor = db.get_user_by_id(patient["doctor_id"]) if patient["doctor_id"] else None
    return patient, doctor


@app.route("/report/download")
@login_required
def report_download():
    import report as report_mod

    viewer = current_user()
    patient, doctor = _resolve_report_patient(viewer)
    if not patient:
        return jsonify({"error": "Patient not found or not permitted"}), 404

    start_str = request.args.get("start")
    end_str = request.args.get("end")
    try:
        start_dt = datetime.fromisoformat(start_str) if start_str else datetime.utcnow() - timedelta(days=30)
        end_dt = datetime.fromisoformat(end_str) if end_str else datetime.utcnow()
    except ValueError:
        start_dt = datetime.utcnow() - timedelta(days=30)
        end_dt = datetime.utcnow()
    end_dt = end_dt + timedelta(days=1)  # inclusive of end date

    history = db.get_history_between(
        patient["id"], start_dt.isoformat() + "Z", end_dt.isoformat() + "Z"
    )
    notes = db.get_notes(patient["id"])

    pdf_buf = report_mod.generate_patient_report(
        patient, doctor, history, notes,
        start_dt.strftime("%b %d, %Y"), (end_dt - timedelta(days=1)).strftime("%b %d, %Y")
    )

    filename = f"oncocare_report_{patient['username']}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    return send_file(pdf_buf, mimetype="application/pdf", as_attachment=True, download_name=filename)


# ---------------------------------------------------------------------------
# API: scoping helper
# ---------------------------------------------------------------------------

def _resolve_target_patient_id():
    """Determine which patient the current API call applies to, respecting role rules.
    Returns (patient_id, error_response_or_None)."""
    viewer = current_user()
    if viewer["role"] == "patient":
        return viewer["id"], None

    # doctor: patient_id must be supplied (json body or query string) and owned by this doctor
    pid = request.args.get("patient_id", type=int)
    if pid is None and request.is_json:
        pid = (request.get_json(silent=True) or {}).get("patient_id")
    if pid is None:
        return None, (jsonify({"error": "patient_id is required for doctor requests"}), 400)

    patient = db.get_user_by_id(int(pid))
    if not patient or patient["role"] != "patient" or patient["doctor_id"] != viewer["id"]:
        return None, (jsonify({"error": "Patient not found or not permitted"}), 403)

    return patient["id"], None


# ---------------------------------------------------------------------------
# API: predictions & history
# ---------------------------------------------------------------------------

@app.route("/api/predict", methods=["POST"])
@login_required
def predict():
    data = request.get_json(force=True)
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err

    try:
        vitals = {f: float(data[f]) for f in FEATURES}
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Missing or invalid vitals. Required: " + ", ".join(FEATURES)}), 400

    # Run prediction but tolerate failures so raw vitals are still persisted.
    try:
        result = ml.make_prediction(vitals)
    except Exception as e:
        app.logger.exception("ML prediction failed")
        # Build a safe fallback prediction so the reading is still stored.
        proba_map = {}
        le = getattr(ml, "label_encoder", None)
        if le and getattr(le, "classes_", None) is not None:
            proba_map = {cls: 0.0 for cls in le.classes_}
        result = {
            "risk_level": "Unknown",
            "risk_score": 0.0,
            "risk_probabilities": proba_map,
            "is_anomaly": False,
            "anomaly_score": 0.0,
            "flags": [],
            "feature_importance": getattr(ml, "MODEL_METRICS", {}).get("feature_importance", {}),
            "_prediction_error": str(e)
        }

    db.insert_reading(patient_id, session["user_id"], vitals, result)

    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "vitals": vitals,
        **result
    }
    return jsonify(record)


@app.route("/api/history", methods=["GET"])
@login_required
def history():
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err
    limit = request.args.get("limit", default=50, type=int)
    return jsonify(db.get_history(patient_id, limit=limit))


@app.route("/api/history/clear", methods=["POST"])
@login_required
def clear_history():
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err
    db.clear_history(patient_id)
    return jsonify({"status": "cleared"})


@app.route("/api/stats", methods=["GET"])
@login_required
def stats():
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err

    hist = db.get_history(patient_id, limit=500)
    if not hist:
        return jsonify({
            "total_readings": 0,
            "risk_distribution": {"Low": 0, "Medium": 0, "High": 0},
            "anomaly_count": 0,
            "latest": None,
            "forecast": None,
            "model_metrics": ml.MODEL_METRICS
        })

    dist = {"Low": 0, "Medium": 0, "High": 0}
    anomaly_count = 0
    for r in hist:
        # Some readings may have fallback/failed predictions with non-standard levels
        lvl = r.get("risk_level")
        if lvl in dist:
            dist[lvl] += 1
        else:
            # Ignore unknown/unsupported levels for distribution (they still appear in "latest")
            app.logger.debug(f"Skipping unknown risk_level in stats aggregation: %s", lvl)
        if r["is_anomaly"]:
            anomaly_count += 1

    forecast = ml.forecast_next_score([r["risk_score"] for r in hist])

    return jsonify({
        "total_readings": len(hist),
        "risk_distribution": dist,
        "anomaly_count": anomaly_count,
        "latest": hist[-1],
        "forecast": forecast,
        "model_metrics": ml.MODEL_METRICS
    })


@app.route("/api/sample", methods=["GET"])
@login_required
def sample_vitals():
    import numpy as np
    rng = np.random.default_rng()
    profile = request.args.get("profile", "random")

    if profile == "healthy":
        vitals = {
            "temperature": round(float(rng.uniform(97.5, 98.9)), 1),
            "heart_rate": int(rng.integers(62, 90)),
            "spo2": int(rng.integers(96, 100)),
            "sleep_hours": round(float(rng.uniform(6.5, 8.5)), 1),
            "pain_level": int(rng.integers(0, 3)),
            "fatigue_level": int(rng.integers(0, 3)),
            "nausea_level": int(rng.integers(0, 2)),
            "dizziness": 0,
        }
    elif profile == "concerning":
        vitals = {
            "temperature": round(float(rng.uniform(101.5, 104.0)), 1),
            "heart_rate": int(rng.integers(115, 140)),
            "spo2": int(rng.integers(82, 90)),
            "sleep_hours": round(float(rng.uniform(2.0, 4.5)), 1),
            "pain_level": int(rng.integers(6, 10)),
            "fatigue_level": int(rng.integers(6, 10)),
            "nausea_level": int(rng.integers(5, 10)),
            "dizziness": 1,
        }
    else:
        vitals = {
            "temperature": round(float(rng.uniform(97.0, 104.0)), 1),
            "heart_rate": int(rng.integers(45, 140)),
            "spo2": int(rng.integers(80, 100)),
            "sleep_hours": round(float(rng.uniform(1.0, 9.5)), 1),
            "pain_level": int(rng.integers(0, 11)),
            "fatigue_level": int(rng.integers(0, 11)),
            "nausea_level": int(rng.integers(0, 11)),
            "dizziness": int(rng.integers(0, 2)),
        }
    return jsonify(vitals)


# ---------------------------------------------------------------------------
# API: doctor clinical notes
# ---------------------------------------------------------------------------

@app.route("/api/notes", methods=["GET"])
@login_required
def get_notes():
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err
    return jsonify(db.get_notes(patient_id))


@app.route("/api/notes", methods=["POST"])
@role_required("doctor")
def add_note():
    data = request.get_json(force=True)
    patient_id, err = _resolve_target_patient_id()
    if err:
        return err
    note_text = (data.get("note") or "").strip()
    if not note_text:
        return jsonify({"error": "Note text is required"}), 400
    db.add_note(patient_id, session["user_id"], note_text)
    return jsonify(db.get_notes(patient_id))


# ---------------------------------------------------------------------------
# Gemini-powered chatbot
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

SYSTEM_CONTEXT_TMPL = """You are OncoBot, a supportive AI assistant embedded inside OncoCare AI, \
a health-monitoring dashboard for cancer patients. You are currently talking to {viewer_role} named {viewer_name}, \
about patient {patient_name}.

Rules:
- Be warm, clear, and reassuring but never alarmist.
- You are NOT a doctor. For any sign of serious deterioration, clearly recommend contacting the \
oncology care team or emergency services rather than giving a diagnosis.
- Keep answers concise (3-6 sentences) unless asked for more detail.
- When relevant, refer to the patient's latest vitals and risk prediction given below.
- Do not invent lab results or diagnoses that aren't in the provided context.

Latest patient context (may be empty if no readings yet):
{context}
"""


def build_patient_context(patient_id):
    latest = db.get_latest_reading(patient_id)
    if not latest:
        return "No readings recorded yet."
    lines = [f"- Timestamp: {latest['timestamp']}"]
    for f in FEATURES:
        lines.append(f"- {f.replace('_', ' ').title()}: {latest['vitals'][f]}")
    lines.append(f"- Predicted risk level: {latest['risk_level']} (score {latest['risk_score']}/15)")
    if latest["is_anomaly"]:
        lines.append("- NOTE: this reading was flagged as an unusual pattern by the anomaly detector.")
    if latest["flags"]:
        flag_str = "; ".join(f"{fl['feature']} is {fl['direction']} ({fl['value']}, normal {fl['normal_range']})" for fl in latest["flags"])
        lines.append(f"- Out-of-range readings: {flag_str}")
    return "\n".join(lines)


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json(force=True)
    user_message = (data.get("message") or "").strip()
    api_key = (data.get("api_key") or os.environ.get("GEMINI_API_KEY") or "").strip()
    chat_history = data.get("history", [])

    patient_id, err = _resolve_target_patient_id()
    if err:
        return err

    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    if not api_key:
        return jsonify({"error": "No Gemini API key provided. Add your key in the chatbot settings."}), 400

    viewer = current_user()
    patient = db.get_user_by_id(patient_id)
    system_context = SYSTEM_CONTEXT_TMPL.format(
        viewer_role=viewer["role"], viewer_name=viewer["full_name"],
        patient_name=patient["full_name"], context=build_patient_context(patient_id)
    )

    contents = [
        {"role": "user", "parts": [{"text": system_context}]},
        {"role": "model", "parts": [{"text": "Understood. I'm ready to help with the OncoCare dashboard."}]},
    ]
    for turn in chat_history[-10:]:
        role = "model" if turn.get("role") == "model" else "user"
        text = turn.get("text", "")
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    url = GEMINI_URL_TMPL.format(model=GEMINI_MODEL, key=api_key)
    payload = {"contents": contents, "generationConfig": {"temperature": 0.6, "maxOutputTokens": 500}}

    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        reply = result["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify({"reply": reply})
    except requests.exceptions.HTTPError as e:
        try:
            err_body = resp.json()
            msg = err_body.get("error", {}).get("message", str(e))
        except Exception:
            msg = str(e)
        return jsonify({"error": f"Gemini API error: {msg}"}), 502
    except Exception as e:
        return jsonify({"error": f"Failed to reach Gemini API: {str(e)}"}), 502


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
